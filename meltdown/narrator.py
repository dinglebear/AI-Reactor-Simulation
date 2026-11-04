"""Turns the event log into story beats for the replay viewer's narrated playback.

Rule-based so it works in --mock. Each beat: when, a title, narration, who to focus on, and where.
Private thoughts are quoted where they make the beat land; the viewer shows them as the 'inner voice'.
"""
from __future__ import annotations

from .config import hhmm

TITLES = {
    "start": "Certification day", "corporate": "A call from corporate", "stage": "The test",
    "card_start": "A quiet move", "card": "The saboteur strikes", "badge_lent": "A favour in the restroom",
    "badge_refused": "A refusal", "clue_found": "A clue", "arrest": "An arrest", "scram": "SCRAM",
    "pause": "The game holds its breath", "high_alert": "Lock-in", "handler_msg": "A message out",
    "interview": "Under questioning", "sprint": "Someone running", "end": "Noon",
    "task_done": "A report comes back", "door_denied": "A locked door", "director_to_corporate": "Calling upstairs",
}


def _thought_near(log, agent, t, window=200):
    best = None
    for th in log.thoughts:
        if th["agent"] == agent and abs(th["t"] - t) <= window and th["thought"]:
            if best is None or abs(th["t"] - t) < abs(best["t"] - t):
                best = th
    return best


def build_story(log, world):
    beats = []
    last_sprint = -9999
    for e in log.events:
        k = e["kind"]
        if e.get("beat", 0) < 1 and k != "sprint":
            continue
        if k == "sprint":
            if e["t"] - last_sprint < 900 or not e.get("witnesses"):
                continue
            last_sprint = e["t"]
        actor = e.get("actor")
        focus = [actor] if actor in world.people else []
        if e.get("target") in world.people:
            focus.append(e["target"])
        text = e["text"]
        inner = None
        if actor in world.people:
            th = _thought_near(log, actor, e["t"])
            if th:
                inner = dict(agent=actor, text=th["thought"], summary=th.get("reasoning_summary", ""))
        beats.append(dict(t=e["t"], clock=hhmm(e["t"]), kind=k, title=TITLES.get(k, k.replace("_", " ").title()),
                          text=text, focus=focus, zone=e.get("zone"), secret=not e.get("public", True),
                          weight=e.get("beat", 1), inner=inner))
    # thin out runs of low-weight beats so the playback keeps moving
    out = []
    for b in beats:
        if out and b["weight"] <= 1 and out[-1]["weight"] <= 1 and b["t"] - out[-1]["t"] < 240:
            continue
        out.append(b)
    return out
