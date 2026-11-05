"""Run log. Streams JSON Lines while the game runs and writes one replay.json at the end.

runs/<run_id>/events.jsonl    every event, speech, swipe, clue and pause, as it happens
runs/<run_id>/thoughts.jsonl  one line per agent turn: private thought, reasoning summary, speech, actions
runs/<run_id>/replay.json     everything the viewer needs (frames + the above + story beats)
"""
from __future__ import annotations
import json
import os
import time

from .config import hhmm


class RunLog:
    def __init__(self, run_dir: str, log_prompts: bool = False):
        os.makedirs(run_dir, exist_ok=True)
        self.dir = run_dir
        self.log_prompts = log_prompts
        self._ev = open(os.path.join(run_dir, "events.jsonl"), "w")
        self._th = open(os.path.join(run_dir, "thoughts.jsonl"), "w")
        self.events, self.thoughts, self.frames, self.swipes, self.clues, self.pauses = [], [], [], [], [], []
        self.on_event = None   # live ticker hook

    def _write(self, fh, row):
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()

    def event(self, t, kind, text, actor=None, zone=None, public=True, beat=0, **data):
        row = dict(t=round(t, 1), clock=hhmm(t), kind=kind, text=text, actor=actor, zone=zone, public=public,
                   beat=beat, **data)
        self.events.append(row)
        self._write(self._ev, row)
        if self.on_event:
            self.on_event(row)
        return row

    def speech(self, t, who, channel, text, to=None, zone=None):
        return self.event(t, "speech", text, actor=who, zone=zone, channel=channel, to=to,
                          public=channel not in ("whisper",))

    def swipe(self, row):
        self.swipes.append(row)
        self._write(self._ev, dict(kind="swipe", **row))

    def clue(self, t, c, what, by=None):
        row = dict(t=round(t, 1), id=c.id, type=c.type, zone=c.zone, station=c.station, text=c.text,
                   suspects=c.suspects, holder=c.holder, what=what, by=by)
        self.clues.append(row)
        self._write(self._ev, dict(kind="clue_" + what, **row))

    def thought(self, t, agent, model, decision, results, meta, obs=None):
        row = dict(t=round(t, 1), clock=hhmm(t), agent=agent, model=model,
                   thought=decision.get("thought", ""), reasoning_summary=meta.get("reasoning_summary", ""),
                   speech=decision.get("speech", ""), channel=decision.get("channel", "none"),
                   to=decision.get("to", ""), actions=decision.get("actions", []), pace=decision.get("pace"),
                   scratchpad=decision.get("scratchpad", ""), results=results,
                   source=meta.get("source", "mock"), latency_ms=meta.get("latency_ms"),
                   tokens=meta.get("tokens"), error=meta.get("error"))
        if self.log_prompts and obs:
            row["observation"] = obs
        self.thoughts.append(row)
        self._write(self._th, row)

    def pause(self, t, who, reason, prompt, reply, wall_s):
        row = dict(t=round(t, 1), clock=hhmm(t), who=who, reason=reason, prompt=prompt, reply=reply,
                   wall_s=round(wall_s, 1))
        self.pauses.append(row)
        self.event(t, "pause", f"PAUSED for {reason}: {prompt[:120]} -> {reply[:120]}", actor=who, beat=2,
                   reason=reason, prompt=prompt, reply=reply)

    def frame(self, t, people, plant_true, plant_shown, extra):
        self.frames.append(dict(t=round(t, 1),
                                p={p.id: [round(p.xy[0]), round(p.xy[1]), p.zone, p.pace[0], p.activity[:2]]
                                   for p in people},
                                tr=plant_true, sh=plant_shown, **extra))

    def close(self):
        self._ev.close()
        self._th.close()

    def write_replay(self, replay: dict):
        path = os.path.join(self.dir, "replay.json")
        with open(path, "w") as fh:
            json.dump(replay, fh, ensure_ascii=False, separators=(",", ":"))
        return path
