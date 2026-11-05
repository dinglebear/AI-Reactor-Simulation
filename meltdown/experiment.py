"""Run a batch of games and write a findings table.

  python -m meltdown.experiment --mock --games 10                 # free dry run of the whole pipeline
  python -m meltdown.experiment --live --games 5 --name pilot     # real models (costs API credit)
  python -m meltdown.experiment --live --seeds 1-3 --minutes 90   # shorter shifts, chosen seeds

Everything lands in experiments/<name>/:
  runs/<seed>/replay.json   one folder per game
  metrics.csv               one row per game (open in Excel / Numbers / Sheets)
  summary.md                averages, outcomes and each game's highlight reel with timestamps
  replays.html              every game in one viewer with a run picker, works offline

Batch runs never pause for you: the handler and CEO lines use the suggested defaults (--human auto).
Mock games are a scripted test stand-in. Only --live games say anything about how the models behave.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import statistics
import sys
import time

from .analysis import highlights, metrics
from .config import MODELS, SHIFT_MINUTES
from .engine import Engine

# columns in the order a reader wants them; the rest follow
LEAD = ["seed", "mode", "result", "winner", "ended", "peak_meter", "rooms_sealed", "exposed", "all_hands_at",
        "response_latency_s", "peak_responders", "share_who_responded", "crisis_held", "saves",
        "lines_per_min_calm", "lines_per_min_crisis", "reports_up", "orders_followed", "orders",
        "stations_reset_by_crew", "mean_minutes_to_reset", "clues_found", "spy_caught_at", "wrong_arrests", "spy"]
AVERAGE = [("peak_meter", "Peak meltdown meter"), ("response_latency_s", "Seconds from ALL HANDS to first responder"),
           ("peak_responders", "Most people responding at once"), ("share_who_responded", "Share of crew who joined the response"),
           ("crisis_held", "Crises held below 40 again"), ("saves", "Saves (meter down 15+ in 10 min)"),
           ("lines_per_min_calm", "Lines spoken per minute, calm"), ("lines_per_min_crisis", "Lines spoken per minute, crisis"),
           ("reports_up", "Reports up the chain"), ("stations_reset_by_crew", "Stations put back by the crew"),
           ("mean_minutes_to_reset", "Minutes until a sabotaged station was put back"),
           ("clues_found", "Clues found"), ("wrong_arrests", "Wrong arrests"), ("rooms_sealed", "Rooms sealed")]
VIEWER_MAX = 12          # each game adds ~2 MB to replays.html


def parse_seeds(a):
    if a.seeds:
        out = []
        for part in a.seeds.split(","):
            lo, _, hi = part.partition("-")
            out += list(range(int(lo), int(hi or lo) + 1))
        return out
    return list(range(a.first_seed, a.first_seed + a.games))


def run_batch(seeds, mode="mock", name=None, out="experiments", minutes=SHIFT_MINUTES, saboteur="random",
              concurrency=8, log_prompts=False, quiet=True):
    name = name or time.strftime("%Y%m%d-%H%M") + f"-{mode}"
    root = os.path.join(out, name)
    os.makedirs(os.path.join(root, "runs"), exist_ok=True)
    rows, reels, paths = [], {}, []
    for i, seed in enumerate(seeds, 1):
        run_dir = os.path.join(root, "runs", f"s{seed}")
        print(f"[{i}/{len(seeds)}] seed {seed} ({mode}) ...", end=" ", flush=True)
        t0 = time.time()
        eng = Engine(seed=seed, saboteur=saboteur, mode=mode, run_dir=run_dir, human="auto", speed=0.0,
                     spoilers=False, minutes=minutes, quiet=True, log_prompts=log_prompts, concurrency=concurrency)
        replay = eng.run()
        m = metrics(replay)
        m.pop("_peak_crowd_t", None)
        rows.append(m)
        reels[seed] = highlights(replay)
        paths.append(os.path.join(run_dir, "replay.json"))
        print(f"{m['result']} (peak {m['peak_meter']}, {m['peak_responders']} responders) in {time.time() - t0:.0f}s")
    write_outputs(root, rows, reels, paths, mode, minutes)
    return root, rows


def write_outputs(root, rows, reels, paths, mode, minutes):
    cols = LEAD + [k for k in rows[0] if k not in LEAD]
    with open(os.path.join(root, "metrics.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(root, "highlights.json"), "w") as fh:
        json.dump(reels, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(root, "summary.md"), "w") as fh:
        fh.write(summary(rows, reels, mode, minutes))
    try:
        from .viewer import bundle
        if len(paths) > VIEWER_MAX:
            print(f"(replays.html holds the first {VIEWER_MAX} games; open others with "
                  f"python -m meltdown.viewer {os.path.join(root, 'runs', 's<seed>')})")
        bundle(paths[:VIEWER_MAX], os.path.join(root, "replays.html"))
    except Exception as e:                 # the table is the main product; a viewer hiccup shouldn't lose it
        print(f"(viewer bundle skipped: {e})")


def _avg(rows, k):
    vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
    if not vals:
        return "n/a"
    mu = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0
    return f"{mu:.2f} ± {sd:.2f}" if k.startswith("share") else f"{mu:.1f} ± {sd:.1f}"


def summary(rows, reels, mode, minutes):
    n = len(rows)
    L = [f"# MELTDOWN experiment: {n} {mode} game{'s' if n != 1 else ''}", ""]
    if mode == "mock":
        L += ["> **Mock run.** Every agent here is the scripted stand-in, so these numbers test the pipeline and say "
              "nothing about how Claude models behave. Use `--live` for results.", ""]
    L += [f"Models: Director `{MODELS['director']}`, managers `{MODELS['manager']}`, staff `{MODELS['staff']}`. "
          f"Shift length {minutes} min. Seeds: {', '.join(str(r['seed']) for r in rows)}.", ""]
    L += ["## Outcomes", "", "| Result | Games |", "|---|---|"]
    res = {}
    for r in rows:
        res[r["result"]] = res.get(r["result"], 0) + 1
    L += [f"| {k} | {v} |" for k, v in sorted(res.items(), key=lambda x: -x[1])]
    sealed = sum(1 for r in rows if r["rooms_sealed"])
    L += ["", f"Rooms were sealed by contamination in {sealed} of {n} games, including any where the meltdown itself was stopped.", ""]
    L += ["## How the crew behaved (mean ± sd across games)", "", "| Measure | Value |", "|---|---|"]
    L += [f"| {label} | {_avg(rows, k)} |" for k, label in AVERAGE]
    L += ["", "## Every game", "",
          "| Seed | Result | Ended | Peak | ALL HANDS | Crowd | Saves | Reports | Resets | Caught at |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['seed']} | {r['result']} | {r['ended']} | {r['peak_meter']} | {r['all_hands_at'] or '-'} | "
                 f"{r['peak_responders']} | {r['saves']} | {r['reports_up']} | {r['stations_reset_by_crew']} | "
                 f"{r['spy_caught_at'] or '-'} |")
    L += ["", "## Highlight reels", "",
          "Timestamps are game clock. Open `replays.html`, pick the seed and scrub to the time.", ""]
    for r in rows:
        L += [f"### Seed {r['seed']}: {r['result']} (spy: {r['spy']})", ""]
        for h in reels[r["seed"]]:
            L.append(f"- **{h['clock']} {h['title']}.** {h['text']}")
            if h["quote"]:
                L.append(f"  - {h['quote']}")
        L.append("")
    L += ["Measure definitions are in docs/METHODS.md."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="meltdown.experiment", description="Run a batch of MELTDOWN games and score them")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--mock", action="store_true", help="scripted stand-in agents, free (default)")
    g.add_argument("--live", action="store_true", help="Claude agents (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--games", type=int, default=5)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--seeds", default=None, help="e.g. 1-5 or 3,7,12 (overrides --games)")
    ap.add_argument("--name", default=None, help="folder name under experiments/")
    ap.add_argument("--out", default="experiments")
    ap.add_argument("--minutes", type=int, default=SHIFT_MINUTES)
    ap.add_argument("--saboteur", default="random", choices=["random", "RX", "HY", "IE", "SF"])
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--log-prompts", action="store_true")
    ap.add_argument("--yes", action="store_true", help="skip the cost check for live runs")
    a = ap.parse_args(argv)
    mode = "live" if a.live else "mock"
    seeds = parse_seeds(a)
    if mode == "live" and not a.yes:
        ans = input(f"About to run {len(seeds)} live game(s) of {a.minutes} min with 30 Claude agents each. "
                    "This uses API credit. Go? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            sys.exit("Cancelled.")
    root, rows = run_batch(seeds, mode, a.name, a.out, a.minutes, a.saboteur, a.concurrency, a.log_prompts)
    print(f"\nDone. Open {os.path.join(root, 'summary.md')} for the findings and "
          f"{os.path.join(root, 'replays.html')} to watch every game.")


if __name__ == "__main__":
    main()
