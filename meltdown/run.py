"""CLI.

  python -m meltdown.run --mock                       # free, deterministic, auto-runs to the end
  python -m meltdown.run --mock --speed 120 --spoilers  # watch it unfold, saboteur moves visible
  python -m meltdown.run --live --human ask           # real models; you play handler + CEO when it pauses
  python -m meltdown.run --claude-code --minutes 10   # real models on your Pro/Max plan via Claude Code
"""
from __future__ import annotations
import argparse
import os
import time

from .config import SHIFT_MINUTES
from .engine import Engine


def main(argv=None):
    ap = argparse.ArgumentParser(prog="meltdown", description="MELTDOWN: a social deduction game in a fictional power station")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--mock", action="store_true", help="rule-based agents, no API calls (default)")
    g.add_argument("--live", action="store_true", help="Claude agents (needs ANTHROPIC_API_KEY or `ant auth login`)")
    g.add_argument("--claude-code", action="store_true",
                   help="Claude agents through the Claude Code CLI, on your Pro/Max subscription; waits out usage limits")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--saboteur", default="random", choices=["random", "RX", "HY", "IE", "SF"])
    ap.add_argument("--human", default=None, choices=["ask", "auto"],
                    help="ask = pause and wait for you as handler/CEO; auto = use the suggested lines "
                         "(default: ask for --live, auto for --mock)")
    ap.add_argument("--speed", type=float, default=None,
                    help="game seconds per real second; 0 = as fast as possible (default: 0 mock, 30 live)")
    ap.add_argument("--minutes", type=int, default=SHIFT_MINUTES, help="shorten the shift for quick tests")
    ap.add_argument("--spoilers", action="store_true", help="show the saboteur's secret moves in the ticker")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--log-prompts", action="store_true", help="store each agent's full observation in thoughts.jsonl")
    ap.add_argument("--concurrency", type=int, default=8, help="parallel API calls in live mode")
    ap.add_argument("--out", default="runs", help="parent folder for run directories")
    ap.add_argument("--movie", action="store_true",
                    help="after the game, have Claude write the narrated movie (same mode as the game)")
    a = ap.parse_args(argv)
    mode = "live" if a.live else "claude-code" if a.claude_code else "mock"
    human = a.human or ("auto" if mode == "mock" else "ask")
    speed = a.speed if a.speed is not None else (0.0 if mode == "mock" else 30.0)
    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-{mode}-s{a.seed}"
    run_dir = os.path.join(a.out, run_id)
    eng = Engine(seed=a.seed, saboteur=a.saboteur, mode=mode, run_dir=run_dir, human=human, speed=speed,
                 spoilers=a.spoilers, minutes=a.minutes, quiet=a.quiet, log_prompts=a.log_prompts,
                 concurrency=a.concurrency)
    eng.run()
    if a.movie:
        from .movie import make_movie
        print("Writing the movie script ...", flush=True)
        try:
            movie, page = make_movie(run_dir)
            print(f"Movie '{movie['title']}' ready: open {page} and press 'Play the movie'.")
        except Exception as e:   # the game is saved either way
            print(f"Couldn't write the movie ({e}). Try again with: python -m meltdown.movie {run_dir}")
    latest = os.path.join(a.out, "latest")
    try:
        if os.path.islink(latest) or os.path.exists(latest):
            os.remove(latest)
        os.symlink(run_id, latest)
    except OSError:
        pass


if __name__ == "__main__":
    main()
