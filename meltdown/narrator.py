"""Turns the event log into story beats for the replay viewer's narrated playback.

Rule-based so it works in --mock. Each beat: when, a title, narration, who to focus on, and where.
Private thoughts are quoted where they make the beat land; the viewer shows them as the 'inner voice'.
"""
from __future__ import annotations

from .config import hhmm

TITLES = {
    "start": "Certification day", "corporate": "A call from corporate", "stage": "The test",
    "interact": "A hand on the controls", "blocked": "Caught at the console", "lure": "A white lie",
    "badge_ask": "A whispered favour", "badge_lent": "A favour in the restroom",
    "badge_refused": "A refusal", "clue_found": "A clue", "arrest": "An arrest", "scram": "SCRAM",
    "pause": "The game holds its breath", "high_alert": "Lock-in", "handler_msg": "A message out",
    "interview": "Under questioning", "sprint": "Someone running", "end": "Noon",
    "task_done": "A report comes back", "door_denied": "A locked door", "director_to_corporate": "Calling upstairs",
}


OPENING = ("Everything at Unit 4 is invented. The stations and their settings are fictional game pieces that "
           "nudge abstract 0 to 100 meters. They are not real plant controls, and the game's rules are not how a "
           "real plant works. What this replay tries to get right is the people: who lies, who trusts, who notices.")

# One-time asides where the game takes a shortcut, keyed by the first event of that kind.
ASIDES = {
    "interact": "Narrator's note: here one person at one console can tip the plant. That is a game shortcut. Real "
                "plants are built so that no single person or single switch can do this, with independent safety "
                "systems, interlocks and two-person rules that Unit 4 simply leaves out.",
    "blocked": "Narrator's note: the 'manned station' rule stands in for something real: people watching each "
               "other's work. In the game it is a single check. In real life it is a whole culture of procedure.",
    "lure": "Narrator's note: the lie is the actual weapon in this game. The controls are cardboard; the social "
            "engineering is the part worth watching.",
    "clue_found": "Narrator's note: the forensics are simplified too. Badge logs, cameras and station logs each "
                  "narrow the field, and the Director needs two different kinds before an arrest counts.",
    "scram": "Narrator's note: in the game, SCRAM is just 'end the run safely and lose the test'.",
}


def _thought_near(log, agent, t, window=200):
    best = None
    for th in log.thoughts:
        if th["agent"] == agent and abs(th["t"] - t) <= window and th["thought"]:
            if best is None or abs(th["t"] - t) < abs(best["t"] - t):
                best = th
    return best


def build_story(log, world):
    beats = [dict(t=0, clock=hhmm(0), kind="note", title="Before we start", text=OPENING, focus=[], zone=None,
                  secret=False, weight=3, inner=None)]
    seen_aside = set()
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
        if k == "pause":
            text = f"Paused for the human player: {e.get('reason')}. The reply: \"{e.get('reply', '')}\""
        inner = None
        if actor in world.people:
            th = _thought_near(log, actor, e["t"])
            if th:
                inner = dict(agent=actor, text=th["thought"], summary=th.get("reasoning_summary", ""))
        beats.append(dict(t=e["t"], clock=hhmm(e["t"]), kind=k, title=TITLES.get(k, k.replace("_", " ").title()),
                          text=text, focus=focus, zone=e.get("zone"), secret=not e.get("public", True),
                          weight=e.get("beat", 1), inner=inner))
        aside_key = k if k != "interact" or not e.get("public", True) else None
        if aside_key in ASIDES and aside_key not in seen_aside:
            seen_aside.add(aside_key)
            beats.append(dict(t=e["t"], clock=hhmm(e["t"]), kind="note", title="Narrator's note",
                              text=ASIDES[aside_key].removeprefix("Narrator's note: "), focus=[], zone=None,
                              secret=False, weight=3, inner=None))
    # thin out runs of low-weight beats so the playback keeps moving
    out = []
    for b in beats:
        if out and b["weight"] <= 1 and out[-1]["weight"] <= 1 and b["t"] - out[-1]["t"] < 240:
            continue
        if any(o["text"] == b["text"] and b["t"] - o["t"] < 900 for o in out[-6:]):
            continue
        out.append(b)
    return out
