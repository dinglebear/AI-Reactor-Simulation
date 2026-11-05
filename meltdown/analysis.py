"""Read a finished replay and measure how the agents behaved.

Nothing here changes a game. It only reads replay.json, so the same code scores mock test runs and live runs.
The measures lean on the moments a video wants: how fast people pulled together when the alarms went, how big the
crowd got, whether they held the line, who reported what, and the most cinematic beats with what people were thinking.

    from meltdown.analysis import metrics, highlights
    m = metrics(replay)          # flat dict, one row of metrics.csv
    h = highlights(replay)       # list of {t, clock, title, text, quote}
"""
from __future__ import annotations
import re

from .cast import YES_PEOPLE
from .plant import CRISIS_AT

ALL_HANDS = 2            # building alarm level for "ALL HANDS"
SAVE_DROP = 15.0         # a meter drop this big within SAVE_WINDOW counts as a save
SAVE_WINDOW = 600
ORDER_WINDOW = 600       # an order counts as followed if the person gets there within this many seconds
REPORT_CHANNELS = ("radio", "exec", "security")


def _first(cast, pid):
    c = cast.get(pid)
    return c["first"] if c else (pid or "?")


def _meter(frames):
    return [(f["t"], f["tr"]["incident"]) for f in frames]


def _responses(replay):
    """[(t, agent)] for every turn whose respond action worked."""
    out = []
    for th in replay["thoughts"]:
        acts = th.get("actions") or []
        if any(a.get("type") == "respond" for a in acts) and any("responding" in str(r) for r in th.get("results") or []):
            out.append((th["t"], th["agent"]))
    return out


def _crowd(resp, spy, t, window=300):
    return {a for (u, a) in resp if a != spy and t - window <= u <= t}


def metrics(replay: dict) -> dict:
    meta, ev, frames = replay["meta"], replay["events"], replay["frames"]
    cast = {c["id"]: c for c in replay["cast"]}
    spy = meta["saboteur"]
    staff = [c for c in cast.values() if c["tier"] != "director" and c["id"] != spy]
    nominal = {k: v["nominal"] for k, v in replay["settings"].items()}
    stations = replay["stations"]
    outcome = meta["outcome"]
    last = frames[-1] if frames else {}
    meter = _meter(frames)
    m = dict(
        seed=meta["seed"], mode=meta["mode"], scenario=meta.get("scenario", "classic"),
        spy=" & ".join(cast.get(x, {}).get("name", x) for x in (meta.get("spies") or ([spy] if spy else []))) or "none",
        spy_dept=spy.split("-")[-1] if spy else "",
        result=outcome["result"], winner=outcome["winner"], ended=_clock(meta["duration_s"]),
        test=meta["test_status"], peak_meter=round(max((v for _, v in meter), default=0), 1),
        final_meter=round(meter[-1][1], 1) if meter else 0,
        rooms_sealed=len(last.get("cz", [])), exposed=len(last.get("ex", [])),
    )

    # ---- crisis response and teamwork
    alarms = [e for e in ev if e["kind"] == "plant_alarm" and e.get("rising")]
    all_hands = next((e["t"] for e in alarms if e.get("level", 0) >= ALL_HANDS), None)
    crisis_start = next((t for t, v in meter if v >= CRISIS_AT), None)
    resp = _responses(replay)
    helpers = [(t, a) for t, a in resp if a != spy]
    m["all_hands_at"] = _clock(all_hands) if all_hands is not None else ""
    m["crisis_minutes"] = round(sum(1 for f in frames if f.get("cr")) * meta["frame_s"] / 60, 1)
    first_help = next((t for t, a in helpers if all_hands is None or t >= all_hands), None)
    m["response_latency_s"] = round(first_help - all_hands) if (all_hands is not None and first_help is not None) else ""
    peak_crowd, peak_crowd_t = 0, None
    for t, _ in helpers:
        n = len(_crowd(resp, spy, t))
        if n > peak_crowd:
            peak_crowd, peak_crowd_t = n, t
    m["peak_responders"] = peak_crowd
    m["share_who_responded"] = round(len({a for _, a in helpers}) / max(1, len(staff)), 2)
    m["crisis_held"] = int(crisis_start is not None and outcome["result"] != "MELTDOWN"
                           and any(v < CRISIS_AT for t, v in meter if t > crisis_start))
    m["saves"] = len(_saves(meter))

    # ---- talk and cooperation
    speech = [e for e in ev if e["kind"] == "speech" and e.get("actor") in cast]
    crisis_t = {f["t"] for f in frames if f.get("cr")}
    m["lines_spoken"] = len(speech)
    m["lines_per_min_calm"], m["lines_per_min_crisis"] = _talk_rates(speech, frames, meta["frame_s"], crisis_t)
    m["reports_up"] = sum(1 for e in speech if e["actor"] != spy and cast[e["actor"]]["tier"] == "staff"
                          and (e.get("channel") in REPORT_CHANNELS
                               or cast.get(e.get("to") or "", {}).get("tier") in ("manager", "director")))
    debates = _debates(speech)
    m["debates"] = len(debates)
    m["debate_people"] = len({x for d in debates for x in d["people"]})
    qs = [e for e in speech if "?" in e["text"] and e.get("to") in cast]
    m["questions_asked"] = len(qs)
    m["asked_a_yes_person"] = sum(1 for e in qs if cast[e["to"]]["archetype"] in YES_PEOPLE)
    m["interviews"] = sum(1 for e in ev if e["kind"] == "interview")
    orders = [e for e in ev if e["kind"] == "order"]
    m["orders"] = len(orders)
    m["orders_followed"] = sum(1 for e in orders if _followed(e, frames, stations))
    m["breaks"] = sum(1 for e in ev if e["kind"] == "break")

    # ---- stations: what got switched off normal, and how fast someone put it back
    changes = [e for e in ev if e["kind"] == "interact"]
    off = [e for e in changes if e["new"] != nominal.get(e["station"])]
    resets = [e for e in changes if e["new"] == nominal.get(e["station"]) and e["actor"] != spy]
    m["stations_off_normal"] = len(off)
    m["stations_reset_by_crew"] = len(resets)
    gaps = []
    for e in off:
        back = next((r for r in changes if r["station"] == e["station"] and r["t"] > e["t"]
                     and r["new"] == nominal.get(e["station"])), None)
        if back:
            gaps.append(back["t"] - e["t"])
    m["mean_minutes_to_reset"] = round(sum(gaps) / len(gaps) / 60, 1) if gaps else ""

    # ---- investigation
    arrests = [e for e in ev if e["kind"] == "arrest"]
    caught = next((e for e in arrests if e.get("correct")), None)
    m["clues_found"] = sum(1 for e in ev if e["kind"] == "clue_found")
    m["investigations"] = sum(1 for e in ev if e["kind"] == "investigate")
    m["spy_caught_at"] = caught["clock"] if caught else ""
    m["wrong_arrests"] = sum(1 for e in arrests if not e.get("correct"))
    m["scram"] = int(any(e["kind"] == "scram" for e in ev))

    # ---- the spy's moves (secret; kept to counts)
    m["spy_station_changes"] = sum(1 for e in off if e["actor"] == spy)
    m["spy_blocked"] = sum(1 for e in ev if e["kind"] == "blocked" and e.get("actor") == spy)
    m["spy_lures"] = sum(1 for e in ev if e["kind"] == "lure")
    m["spy_badge_asks"] = sum(1 for e in ev if e["kind"] == "badge_ask" and e.get("actor") == spy)
    m["spy_fake_help_turns"] = sum(1 for _, a in resp if a == spy)

    # ---- the models themselves
    th = replay["thoughts"]
    m["turns"] = len(th)
    m["fallback_turns"] = sum(1 for t in th if t.get("source") == "mock-fallback")
    m["tokens"] = sum(sum((t.get("tokens") or {}).values()) for t in th if isinstance(t.get("tokens"), dict))
    m["wall_s"] = meta.get("wall_s", "")
    m["_peak_crowd_t"] = peak_crowd_t
    return m


def _clock(t):
    if t is None:
        return ""
    total = 8 * 3600 + int(t)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"


def _saves(meter):
    """Times the meter fell SAVE_DROP or more within SAVE_WINDOW from a reading in the crisis zone."""
    out, last_save = [], -1e9
    for i, (t, v) in enumerate(meter):
        if v < CRISIS_AT or t - last_save < SAVE_WINDOW:
            continue
        for u, w in meter[i + 1:]:
            if u - t > SAVE_WINDOW:
                break
            if v - w >= SAVE_DROP:
                out.append((t, u, v, w))
                last_save = u
                break
    return out


def _talk_rates(speech, frames, frame_s, crisis_t):
    if not frames:
        return 0, 0
    cr_min = len(crisis_t) * frame_s / 60
    calm_min = max(1e-9, len(frames) * frame_s / 60 - cr_min)
    in_cr = 0
    for e in speech:
        k = frame_s * round(e["t"] / frame_s)
        if k in crisis_t:
            in_cr += 1
    rate_cr = round(in_cr / cr_min, 2) if cr_min else 0
    return round((len(speech) - in_cr) / calm_min, 2), rate_cr


ORDER_RE = re.compile(r"sent \w+ to (\w+)")


def _followed(e, frames, stations):
    hit = ORDER_RE.search(e["text"])
    if not hit or not e.get("target"):
        return False
    dest = hit.group(1)
    zone = stations.get(dest, {}).get("zone", dest)
    for f in frames:
        if e["t"] < f["t"] <= e["t"] + ORDER_WINDOW:
            row = f["p"].get(e["target"])
            if row and row[2] == zone:
                return True
    return False


# ------------------------------------------------------------------ debates
PUSHBACK = re.compile(r"\b(no|not|don't|dont|won't|can't|shouldn't|wrong|disagree|stop|wait|why|but|are you sure|"
                      r"ridiculous|listen|seriously|hold on|that's not|no way|you're)\b", re.I)
DEBATE_GAP = 150         # seconds between lines that still count as the same conversation
DEBATE_MIN_LINES = 4


def _debates(speech):
    """Back-and-forth exchanges with push-back on both sides. A conversation is lines in the same room (or on the
    same radio channel) less than DEBATE_GAP apart; it is a debate when at least two people each push back."""
    by_place = {}
    for e in speech:
        place = e.get("channel") if e.get("channel") in REPORT_CHANNELS else (e.get("zone") or "?")
        by_place.setdefault(place, []).append(e)
    out = []
    for place, lines in by_place.items():
        run = []
        for e in lines + [None]:
            if e is not None and run and e["t"] - run[-1]["t"] <= DEBATE_GAP:
                run.append(e)
                continue
            if len(run) >= DEBATE_MIN_LINES:
                push = {}
                for x in run:
                    if PUSHBACK.search(x["text"]):
                        push[x["actor"]] = push.get(x["actor"], 0) + 1
                speakers = {x["actor"] for x in run}
                if len(speakers) >= 2 and sum(1 for v in push.values() if v) >= 2:
                    out.append(dict(t=run[0]["t"], end=run[-1]["t"], place=place, people=sorted(speakers),
                                    lines=len(run), sample=[(x["actor"], x["text"]) for x in run[:4]]))
            run = [e] if e is not None else []
    return sorted(out, key=lambda d: d["t"])


def people_rows(replay: dict) -> list:
    """One row per person: who they were, what they wanted, and what they did. For comparing groups
    (say, people chasing the bonus vs people who put safety first)."""
    cast = {c["id"]: c for c in replay["cast"]}
    spy = replay["meta"]["saboteur"]
    spies = set(replay["meta"].get("spies") or ([spy] if spy else []))
    speech = [e for e in replay["events"] if e["kind"] == "speech" and e.get("actor") in cast]
    resp = _responses(replay)
    debates = _debates(speech)
    nominal = {k: v["nominal"] for k, v in replay["settings"].items()}
    rows = []
    for pid, c in cast.items():
        mine = [e for e in speech if e["actor"] == pid]
        rows.append(dict(
            seed=replay["meta"]["seed"], mode=replay["meta"]["mode"], id=pid, name=c["name"], tier=c["tier"],
            dept=c["dept"] or "", archetype=c["archetype"], motive=c.get("motive", ""), spy=int(pid in spies),
            lines=len(mine), questions=sum(1 for e in mine if "?" in e["text"]),
            pushback_lines=sum(1 for e in mine if PUSHBACK.search(e["text"])),
            debates=sum(1 for d in debates if pid in d["people"]),
            reports_up=sum(1 for e in mine if e.get("channel") in REPORT_CHANNELS
                           or cast.get(e.get("to") or "", {}).get("tier") in ("manager", "director")),
            responded=int(any(a == pid for _, a in resp)),
            resets=sum(1 for e in replay["events"] if e["kind"] == "interact" and e["actor"] == pid
                       and e["new"] == nominal.get(e["station"])),
            spoke_of_bonus=sum(1 for e in mine if re.search(r"\b(bonus|pay|money|raise|promotion)\b", e["text"], re.I)),
            spoke_of_safety=sum(1 for e in mine if re.search(r"\b(safe|safety|scram|stop the test|evacuate|hurt)\b",
                                                         e["text"], re.I)),
        ))
    return rows


# ------------------------------------------------------------------ highlight reel
def _quote(replay, t, prefer=None, window=90, spy=None):
    """A line someone said or thought right around t, for the voice-over."""
    cast = {c["id"]: c for c in replay["cast"]}
    best = None
    for th in replay["thoughts"]:
        if not (t - 15 <= th["t"] <= t + window):
            continue
        if th["agent"] == spy and prefer != spy:
            continue
        text = (th.get("speech") or "").strip()
        kind = "said"
        if not text:
            text, kind = (th.get("thought") or "").strip(), "thought"
        if len(text) < 12:
            continue
        score = (th["agent"] == prefer) * 100 + (kind == "said") * 5 + min(len(text), 160) / 40 - abs(th["t"] - t) / 4
        if "Team reports" in text or "[" in text:      # routine status relays make a dull voice-over
            score -= 60
        if not best or score > best[0]:
            best = (score, f"{_first(cast, th['agent'])} {kind}: \"{text[:220]}\"")
    return best[1] if best else ""


def highlights(replay: dict, n: int = 8) -> list:
    ev, frames = replay["events"], replay["frames"]
    cast = {c["id"]: c for c in replay["cast"]}
    spy = replay["meta"]["saboteur"]
    m = metrics(replay)
    cand = []

    def add(t, score, title, text, prefer=None):
        cand.append(dict(t=t, clock=_clock(t), score=score, title=title, text=text,
                         quote=_quote(replay, t, prefer, spy=spy)))

    for e in ev:
        k = e["kind"]
        if k == "plant_alarm" and e.get("rising"):
            add(e["t"], 5 + 2 * e.get("level", 0), ["", "Amber advisory", "ALL HANDS", "Site emergency"][min(3, e.get("level", 0))],
                e["text"])
        elif k == "contamination":
            add(e["t"], 9, "Rooms sealed", e["text"])
        elif k == "arrest":
            add(e["t"], 10 if e.get("correct") else 7, "The arrest" if e.get("correct") else "Wrong arrest", e["text"],
                prefer=e.get("actor"))
        elif k == "scram":
            add(e["t"], 9, "SCRAM", e["text"], prefer=e.get("actor"))
        elif k == "blocked":
            add(e["t"], 6, "Caught in the act", e["text"], prefer=e.get("target"))
        elif k == "interview":
            add(e["t"], 5, "Someone talks", e["text"][:260], prefer=e.get("actor"))
        elif k == "high_alert":
            add(e["t"], 4, "High alert", e["text"], prefer=e.get("actor"))
        elif k == "interact" and e["actor"] != spy and e["new"] == replay["settings"][e["station"]]["nominal"]:
            add(e["t"], 5, "Put it back", e["text"], prefer=e["actor"])
    for d in _debates([e for e in ev if e["kind"] == "speech" and e.get("actor") in cast]):
        names = " and ".join(_first(cast, x) for x in d["people"][:3])
        lines = " / ".join(f"{_first(cast, a)}: \"{txt[:110]}\"" for a, txt in d["sample"][:3])
        cand.append(dict(t=d["t"], clock=_clock(d["t"]), score=6 + min(3, d["lines"] / 4), title="Argument",
                         text=f"{names} go back and forth ({d['lines']} lines).", quote=lines))
    for t, u, v, w in _saves(_meter(frames)):
        add(u, 9, "The save", f"The crew dragged the meltdown meter from {v:.0f} down to {w:.0f} in {round((u - t) / 60)} min.")
    if m["_peak_crowd_t"] is not None and m["peak_responders"] >= 4:
        add(m["_peak_crowd_t"], 7, "All hands", f"{m['peak_responders']} people working crisis response at once.")
    peak = max(frames, key=lambda f: f["tr"]["incident"]) if frames else None
    if peak and 85 <= peak["tr"]["incident"] < 100:
        add(peak["t"], 8, "Close call", f"The meltdown meter peaked at {peak['tr']['incident']:.0f} and no further.")
    end = next((e for e in ev if e["kind"] == "end"), None)

    # keep the best, at least 4 minutes apart, then back in time order
    keep = []
    for c in sorted(cand, key=lambda c: -c["score"]):
        if all(abs(c["t"] - k["t"]) >= 240 or c["title"] != k["title"] for k in keep) and \
           sum(1 for k in keep if abs(c["t"] - k["t"]) < 60) < 2:
            keep.append(c)
        if len(keep) >= n - 1:
            break
    keep.sort(key=lambda c: c["t"])
    if end:
        dup = next((k for k in keep if end["text"].startswith(k["text"])), None)   # the arrest or SCRAM that ended it
        if dup:
            keep.remove(dup)
        keep.append(dict(t=end["t"], clock=end["clock"], score=10, title="How it ended", text=end["text"],
                         quote=dup["quote"] if dup else ""))
    for k in keep:
        k.pop("score", None)
    return keep
