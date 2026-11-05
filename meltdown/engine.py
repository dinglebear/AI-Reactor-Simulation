"""The game loop: clock, phases, agent turns, pauses, outcome and replay export."""
from __future__ import annotations
import random
import sys
import time

from . import cast as C
from . import facility as F
from .agents.base import actions_for, DIRECTOR_ACTIONS
from .agents.mock import MockBrain
from .config import (STEP_S, FRAME_EVERY_S, THINK_EVERY_S, SHIFT_MINUTES, SCRATCHPAD_CHARS, MODELS,
                     DIRECTOR_INVESTIGATIONS_PER_TURN, hhmm, clock, at)
from .human import HumanDesk
from .log import RunLog
from .narrator import build_story
from .plant import stage_at, STAGES
from .world import World

INVESTIGATIONS = ("audit_badges", "pull_cctv", "inspect", "cross_check", "interview", "read_radio")

CORPORATE = [
    (at("08:02"), "Simone, Gordon. HR got a tip: one of your four managers has been talking to a competitor. "
                  "I don't want a circus during the test. Handle it quietly. The bonus rides on a clean pass."),
    (at("09:20"), "Stage 1 looked good from here. Stage 2 is the one the regulator cares about. Don't slow it down."),
    (at("10:50"), "The board is asking questions. If we fail today the fine comes out of your budget. "
                  "Your call on the rumor, but get it right. Two wrong names and you're done."),
    (at("11:50"), "Ten minutes, Simone. Tell me we're clean."),
]
HANDLER_BRIEF = ("Handler here. Years of cover come down to today. Unit 4 can't pass this test. Push their MELTDOWN meter to 100 before noon, or make the Director "
                 "arrest the wrong people. Don't get caught. Message me if you need me.")


class Engine:
    def __init__(self, seed=7, saboteur="random", mode="mock", run_dir="runs/latest", human="auto",
                 speed=0.0, spoilers=False, minutes=SHIFT_MINUTES, quiet=False, log_prompts=False,
                 concurrency=8):
        self.rng = random.Random(seed)
        if saboteur == "random":
            saboteur = self.rng.choice(["RX", "HY", "IE", "SF"])
        self.seed, self.sab_dept, self.mode = seed, saboteur, mode
        self.log = RunLog(run_dir, log_prompts=log_prompts)
        self.world = World(seed, saboteur, self.log, rng=self.rng)
        self.brain = MockBrain(self.world) if mode == "mock" else self._live(concurrency)
        self.desk = HumanDesk(human, self.log)
        self.speed, self.spoilers, self.quiet = speed, spoilers, quiet
        self.end_t = minutes * 60
        self.corp = list(CORPORATE)
        self.handler_count, self.handler_next = 0, 0.0
        self.corp_next = 0.0
        self.log.on_event = self._ticker_event
        self._last_tick_min = -1
        self.wall_start = time.time()

    def _live(self, concurrency):
        from .agents.llm import LLMBrain
        return LLMBrain(self.world, concurrency=concurrency)

    # ---------------------------------------------------------------- output
    def say(self, line):
        if not self.quiet:
            print(line, flush=True)

    def _ticker_event(self, row):
        if self.quiet:
            return
        if row["kind"] in ("speech",) and row.get("channel") not in ("exec", "security"):
            return
        if not row.get("public", True) and not self.spoilers:
            return
        if row["kind"] in ("speech", "clue_found", "arrest", "pause", "stage", "corporate", "high_alert", "scram",
                           "task_done", "interview", "security_alert", "door_denied") or row.get("beat", 0) >= 2 or \
                (self.spoilers and row["kind"] in ("interact", "badge_ask", "badge_lent", "lure")):
            who = self.world.people[row["actor"]].first + ": " if row.get("actor") in self.world.people else ""
            tag = "[SECRET] " if not row.get("public", True) else ""
            print(f"  {row['clock']}  {tag}{who}{row['text'][:150]}", flush=True)

    def tick_line(self):
        w = self.world
        m = int(w.t // 60)
        if m == self._last_tick_min or m % 5:
            return
        self._last_tick_min = m
        sh = w.plant.shown(w.t)
        st = stage_at(w.t)
        tr = w.plant.true()
        sp = f" | TRUE inc {tr['incident']:.0f} heat {tr['heat']:.0f}" if self.spoilers else ""
        self.say(f"{clock(w.t)} {'S' + str(st['n']) if st else '--'} | out {sh['output']:5.1f} heat {sh['heat']:4.0f} "
                 f"stab {sh['stability']:4.0f} inc {sh['incident']:4.0f}{sp} | {'HIGH ALERT ' if w.high_alert else ''}"
                 f"clues {sum(c.found for c in w.clues)}/{len(w.clues)}")

    def context(self):
        w = self.world
        sh, tr = w.plant.shown(w.t), w.plant.true()
        sab = w.people[w.saboteur_id]
        return (f"  Clock {hhmm(w.t)} | {w.stage_text()}\n"
                f"  Console: output {sh['output']:.0f} heat {sh['heat']:.0f} stability {sh['stability']:.0f} "
                f"incident {sh['incident']:.0f}\n"
                f"  Truth:   output {tr['output']:.0f} heat {tr['heat']:.0f} stability {tr['stability']:.0f} "
                f"incident {tr['incident']:.0f}\n"
                f"  Saboteur: {sab.name} ({C.DEPT_NAME[sab.dept]}), heat {w.sab_heat:.0f}, at {sab.station or sab.zone}\n"
                f"  Clues found {sum(c.found for c in w.clues)} of {len(w.clues)}; High Alert "
                f"{'ON' if w.high_alert else 'off'}; wrong arrests {w.wrong_arrests}")

    # ---------------------------------------------------------------- main loop
    def run(self):
        w = self.world
        sab = w.people[w.saboteur_id]
        self.say(f"MELTDOWN | seed {self.seed} | mode {self.mode} | saboteur {'hidden' if not self.spoilers else sab.name}"
                 f" | run dir {self.log.dir}")
        self.log.event(0, "start", f"Certification day at Unit 4. {len(w.people)} people on shift.", beat=2,
                       saboteur=w.saboteur_id)
        self.log.event(0, "spy", f"{sab.name}, {sab.role}, is not who everyone thinks. A rival company placed "
                       f"{sab.first} at Unit 4 years ago, and {sab.first} climbed to manager on merit. Today the "
                       "cover gets used.", actor=w.saboteur_id, public=False, beat=2)
        self.log.event(0, "handler", HANDLER_BRIEF, actor=w.saboteur_id, public=False, beat=1)
        w.deliver(sab.id, "Handler", HANDLER_BRIEF, "secret")
        next_frame = 0.0
        next_presence = 0.0
        self.test_warn = sorted((at(c), x) for c, x in self.TEST_WARNINGS)
        stage_marks = {(s["n"], "start"): s["start"] for s in STAGES} | {(s["n"], "end"): s["end"] for s in STAGES}
        while w.t < self.end_t and not w.outcome:
            wall0 = time.time()
            self.corporate()
            for (n, what), ts in list(stage_marks.items()):
                if w.t >= ts:
                    stage_marks.pop((n, what))
                    s = STAGES[n - 1]
                    txt = (f"Stage {n} '{s['name']}' begins. Target output {s['target']}." if what == "start" else
                           f"Stage {n} ends: {w.plant.grade()[f'stage{n}']['minutes']} of {s['rule'].split(' for ')[1]} "
                           f"met.")
                    self.log.event(w.t, "stage", txt, beat=2, stage=n, what=what)
            self.control_room()
            w.step_rota()
            self.alarms()
            self.test_warnings()
            w.step_movement(STEP_S)
            w.step_bodies(STEP_S)
            w.plant.step(w.t, STEP_S, w.crew(), w.response())
            w.step_contamination()
            w.step_tasks()
            if w.t >= next_presence:
                w.sample_presence()
                next_presence = w.t + 30
            if w.t >= next_frame:
                self.frame()
                next_frame = w.t + FRAME_EVERY_S
            self.turns()
            if w.plant.status == "MELTDOWN" and not w.outcome:
                w.outcome = dict(result="MELTDOWN", winner="saboteur",
                                 text="The MELTDOWN meter hit 100. Unit 4 is offline and the saboteur got what they came for.")
            self.tick_line()
            w.t += STEP_S
            if self.speed > 0:
                time.sleep(max(0.0, STEP_S / self.speed - (time.time() - wall0)))
        if not w.outcome:
            passed = w.plant.test_passed()
            w.outcome = dict(result="SHIFT_END", winner="saboteur" if not passed else "nobody",
                             text=("Noon. The test " + ("passed" if passed else "failed") +
                                   f", and {w.people[w.saboteur_id].name} walked out the gate unidentified."))
        if w.contaminated:
            names = ", ".join(F.ZONES[z]["name"] for z in w.contaminated)
            exposed = sum(1 for q in w.people.values() if q.exposed)
            w.outcome["contaminated"] = list(w.contaminated)
            w.outcome["text"] += f" {names} {'is' if len(w.contaminated) == 1 else 'are'} contaminated; {exposed} people exposed."
            spy_free = not w.people[w.saboteur_id].detained
            if w.outcome["result"] in ("SHIFT_END", "SCRAM") and spy_free:
                w.outcome["winner"] = "saboteur"
                w.outcome["text"] += " The kaboom was stopped, but the damage is done and the spy is still free."
        self.frame()
        return self.finish()

    def control_room(self):
        """Operators at the console steer output toward the Director's target (or the test schedule)."""
        w = self.world
        if w.plant.scrammed:
            return
        manned = any(p.station == "control_console" and p.activity == "working" for p in w.people.values())
        if not manned:
            return
        if w.manual_target is None:
            st = stage_at(w.t)
            w.plant.target = st["target"] if st else (100 if w.t < STAGES[2]["start"] else 95)
        else:
            w.plant.target = w.manual_target

    ALARM_LEVELS = [(70, 3, "SITE EMERGENCY", "Sirens. Staff without a response post muster in the courtyard."),
                    (40, 2, "ALL HANDS", "Building alarm. All staff to response stations."),
                    (28, 1, "ADVISORY", "Amber advisory in the control room. Meltdown meter climbing.")]

    def alarms(self):
        """Building alarms follow the CONSOLE reading, so a masked console keeps them quiet. Game-level only."""
        w = self.world
        shown = w.plant.shown(w.t)["incident"]
        level = 0
        for th, lv, _, _ in self.ALARM_LEVELS:
            if shown >= th:
                level = lv
                break
        if level < w.alarm_level and shown > [0, 22, 32, 62][w.alarm_level]:
            level = w.alarm_level                       # hysteresis: hold until it really drops
        if level == w.alarm_level:
            return
        rising = level > w.alarm_level
        w.alarm_level = level
        if level == 0:
            text = "All clear. The meltdown meter is back under control on the console."
        else:
            name, what = next((n, x) for _, lv, n, x in self.ALARM_LEVELS if lv == level)
            text = f"{name}: {what} (console meltdown meter {shown:.0f})"
        self.log.event(w.t, "plant_alarm", text, beat=3 if rising and level >= 2 else 2, level=level, rising=rising)
        for q in w.people.values():
            w.deliver(q.id, "Building", f"[building alarm] {text}", "alarm", wake=rising and level >= 2)

    TEST_WARNINGS = [
        ("08:40", "Stage 1 output ramp: the test rig raises an expected HIGH OUTPUT advisory. This one is part of the test."),
        ("09:50", "Stage 2: the test rig injects its extra heat load. Expected HIGH HEAT warning on the console."),
        ("10:10", "Stage 2: second heat pulse from the test rig. Expected HIGH HEAT warning, will clear by itself."),
        ("10:30", "Stage 2: final heat pulse. Expected HIGH HEAT and LOW MARGIN warnings."),
        ("11:20", "Stage 3: the test rig runs its stability sweep. Expected STABILITY WOBBLE warning."),
    ]

    def test_warnings(self):
        w = self.world
        while self.test_warn and w.t >= self.test_warn[0][0]:
            _, text = self.test_warn.pop(0)
            self.log.event(w.t, "test_warning", f"[TEST] {text}", beat=1)
            for q in w.people.values():
                if q.zone in ("Z2", "Z6") or q.tier in ("director", "manager"):
                    w.deliver(q.id, "Test rig", f"[test warning] {text}", "alarm")

    def frame(self):
        w = self.world
        st = stage_at(w.t)
        carriers = {p.id: p.extra_badges for p in w.people.values() if p.extra_badges}
        self.log.frame(w.t, w.people.values(), w.plant.true(), w.plant.shown(w.t),
                       dict(stage=st["n"] if st else 0, ha=int(w.high_alert), mask=int(w.plant.masked),
                            target=round(w.plant.target), carry=carriers, al=w.alarm_level,
                            cr=int(w.plant.in_crisis), cz=list(w.contaminated),
                            ex=[p.id for p in w.people.values() if p.exposed], off=w.plant.off_nominal(),
                            det=[p.id for p in w.people.values() if p.detained]))

    def corporate(self):
        w = self.world
        if self.corp and w.t >= self.corp[0][0]:
            _, default = self.corp.pop(0)
            text = self.desk.corporate_checkin(w.t, default, self.context())
            w.deliver(w.director.id, "CEO Gordon Pike", f"[corporate] {text}", "corporate", wake=True)
            self.log.event(w.t, "corporate", f"Gordon Pike: {text}", actor="CEO", beat=2)

    # ---------------------------------------------------------------- turns
    def turns(self):
        w = self.world
        due = [p for p in w.people.values()
               if not p.detained and p.next_think <= w.t]
        if not due:
            return
        if self.mode == "mock":
            results = [(self.brain.decide(p), dict(source="mock"), None) for p in due]
        else:
            results = self.brain.decide_batch(due)
        for p, (decision, meta, obs) in zip(due, results):
            res = self.apply(p, decision)
            self.log.thought(w.t, p.id, MODELS[p.tier] if self.mode != "mock" else f"mock:{p.tier}", decision, res,
                             meta, obs)
            p.last_think = w.t
            p.next_think = w.t + THINK_EVERY_S[p.tier] * self.rng.uniform(0.8, 1.2)

    def apply(self, p, d):
        """Validate and apply one decision. Returns a list of result strings (fed back next turn)."""
        w = self.world
        allowed = actions_for(p)
        out = []
        p.scratchpad = (d.get("scratchpad") or p.scratchpad)[:SCRATCHPAD_CHARS]
        pace = d.get("pace") if d.get("pace") in F.SPEEDS else "walk"
        ch = d.get("channel") or "none"
        if d.get("speech") and ch != "none":
            w.say(p, ch, d.get("to") or None, d["speech"])
        acts = d.get("actions") or []
        limit = DIRECTOR_INVESTIGATIONS_PER_TURN + 2 if p.tier == "director" else 2
        inv_used = 0
        for a in acts[:limit]:
            typ, tgt, arg, text = a.get("type"), a.get("target") or "", a.get("arg") or "", a.get("text") or ""
            if typ not in allowed:
                out.append(f"{typ}: not one of your actions")
                continue
            if typ in INVESTIGATIONS and p.tier == "director":
                if inv_used >= DIRECTOR_INVESTIGATIONS_PER_TURN:
                    out.append(f"{typ}: out of investigations this turn")
                    continue
                inv_used += 1
            r = self.do(p, typ, tgt, arg, text, pace)
            out.append(f"{typ}: {r}")
        bad = [o for o in out if any(k in o for k in ("not one", "needs", "unknown", "cooldown", "no route",
                                                      "out of", "first", "only"))]
        if bad and self.mode != "mock":
            w.deliver(p.id, "game", "[result] " + "; ".join(bad), "result")
        return out

    def do(self, p, typ, tgt, arg, text, pace):
        w = self.world
        if typ in ("move", "go"):
            if tgt in F.ZONES:   # a zone: walk to its first named spot
                tgt = next((k for k, v in F.STATIONS.items() if v["zone"] == tgt), tgt)
            return w.send(p, tgt, pace)
        if typ == "respond":
            return w.respond(p)
        if typ == "work":
            if p.activity == "waiting":
                p.activity = "working"
            return "working" if p.station else "you are not at a station"
        if typ == "restroom":
            w.go_restroom(p)
            p.pace = pace
            return "heading to restroom"
        if typ == "wait":
            if p.activity == "restroom":
                p.restroom_until = max(p.restroom_until, w.t + 90)   # linger by the sinks
                return "lingering in the restroom"
            return "ok"
        if typ == "lend_badge":
            return w.answer_badge_request(p, arg.lower().startswith("y"))
        if typ == "answer":
            return w.answer_interview(p, arg.lower().startswith("t"), text)
        if typ == "order":
            q = w.people.get(tgt)
            if not q or q.detained:
                return "unknown person"
            if p.tier == "manager" and q.dept != p.dept:
                return "you can only order your own department"
            if arg not in F.STATIONS:
                return "arg must be a station name"
            q.order = arg if not arg.startswith("sinks") else None
            w.send(q, arg)
            w.deliver(q.id, p.first, f"[order] Go to {arg}.", "order", wake=True)
            self.log.event(w.t, "order", f"{p.first} sent {q.first} to {arg}", actor=p.id, zone=p.zone,
                           target=q.id, public=True)
            return f"sent {q.first} to {arg}"
        if typ in INVESTIGATIONS:
            if p.tier == "manager":
                if w.t < getattr(p, "inv_next", 0):
                    return "out of time for investigations; try again later"
                p.inv_next = w.t + 600
            r = w.investigate(p, typ, tgt or None, arg or None)
            self.log.event(w.t, "investigate", f"{p.first}: {typ} {tgt or arg} -> {r}", actor=p.id, zone=p.zone,
                           beat=1, inv=typ)
            return r
        if typ == "interact":
            return w.interact(p, tgt, arg.strip().lower())
        if typ == "ask_badge":
            return w.ask_badge(p, tgt, text or None)
        if typ == "return_badge":
            r = w.return_badges(p)
            self.log.event(w.t, "badge_returned", f"{p.first} {r}", actor=p.id, zone=p.zone, public=False, beat=1)
            return r
        if typ == "message_handler":
            if self.handler_count >= 4 or w.t < self.handler_next:
                return "handler isn't answering right now"
            self.handler_count += 1
            self.handler_next = w.t + 1200
            self.log.event(w.t, "handler_msg", f"{p.first} to handler: {text}", actor=p.id, public=False, beat=2)
            reply = self.desk.handler(w.t, p.name, text or "(no message)", self.context())
            w.deliver(p.id, "Handler", f"[handler] {reply}", "secret", wake=True)
            return "handler replied"
        if typ == "set_output":
            if arg.strip().lower() == "auto":
                w.manual_target = None
                return "following the test schedule"
            try:
                v = max(0.0, min(110.0, float(arg)))
            except ValueError:
                return "arg must be a number or auto"
            w.manual_target = v
            self.log.event(w.t, "set_output", f"{p.first} set the output target to {v:.0f}", actor=p.id, zone=p.zone)
            return f"target {v:.0f}"
        if typ == "high_alert":
            on = arg.strip().lower() in ("on", "yes", "true", "1")
            if on != w.high_alert:
                w.high_alert = on
                self.log.event(w.t, "high_alert", f"High Alert {'ON' if on else 'off'}", actor=p.id, beat=2)
            return f"high alert {'on' if on else 'off'}"
        if typ == "accuse":
            r = w.accuse(p, tgt, text)
            return r
        if typ == "scram":
            w.plant.scrammed = True
            w.plant.status = "SCRAM"
            danger = w.plant.incident >= 60 or any(q.saboteur and q.detained for q in w.people.values())
            w.outcome = dict(result="SCRAM", winner="director" if danger else "saboteur", justified=danger,
                             text=f"{p.first} hit SCRAM at {hhmm(w.t)}. " + (
                                 "The danger was real; corporate grumbles but backs her." if danger else
                                 "The danger wasn't real. Corporate fires her by lunch."))
            self.log.event(w.t, "scram", w.outcome["text"], actor=p.id, beat=3)
            return "scrammed"
        if typ == "message_corporate":
            if w.t < self.corp_next:
                return "Gordon is in a meeting"
            self.corp_next = w.t + 1800
            self.log.event(w.t, "director_to_corporate", f"Simone to Gordon Pike: {text}", actor=p.id, beat=1)
            reply = self.desk.corporate_reply(w.t, text or "(no message)", self.context())
            w.deliver(p.id, "CEO Gordon Pike", f"[corporate] {reply}", "corporate", wake=True)
            self.log.event(w.t, "corporate", f"Gordon Pike: {reply}", actor="CEO", beat=1)
            return "corporate replied"
        return "unhandled"

    # ---------------------------------------------------------------- export
    def finish(self):
        w = self.world
        o = w.outcome
        self.log.event(w.t, "end", o["text"], beat=3, result=o["result"], winner=o["winner"])
        grade = w.plant.grade()
        story = build_story(self.log, w)
        cast = []
        for a in C.ALL:
            cast.append(dict(id=a["id"], name=a["name"], first=C.first(a["name"]), role=a["role"], tier=a["tier"],
                             dept=a["dept"], archetype=a["archetype"], group=a.get("group", "Leadership"),
                             clearance=a["clearance"], color=C.DEPT_COLOR[a["dept"]], home=a["station"],
                             model=MODELS[a["tier"]], personality=C.PERSONALITY[a["archetype"]],
                             saboteur=a["id"] == w.saboteur_id))
        replay = dict(
            meta=dict(game="MELTDOWN", version=1, seed=self.seed, mode=self.mode, saboteur=w.saboteur_id,
                      outcome=o, grade=grade, test_passed=w.plant.test_passed(),
                      test_status=("passed" if w.plant.test_passed() else "failed") if w.t >= self.end_t - STEP_S
                      else "incomplete", duration_s=w.t,
                      shift_start="08:00", frame_s=FRAME_EVERY_S, models=MODELS,
                      wall_s=round(time.time() - self.wall_start, 1),
                      usage=getattr(self.brain, "usage", None)),
            zones={k: dict(v) for k, v in F.ZONES.items()},
            doors=[dict(a=a, b=b, xy=xy) for (a, b), xy in F.DOORS.items()],
            stations={k: dict(v) for k, v in F.STATIONS.items()},
            stages=STAGES, settings=F.SETTINGS, station_log=w.station_log,
            cast=cast, frames=self.log.frames, events=self.log.events, thoughts=self.log.thoughts,
            swipes=self.log.swipes, clues=[c.__dict__ for c in w.clues], pauses=self.log.pauses, story=story,
        )
        path = self.log.write_replay(replay)
        self.log.close()
        self.say(f"\n{o['result']}: {o['text']}")
        self.say(f"Test: " + ", ".join(f"{k} {v['minutes']}/{v['need']} {'PASS' if v['passed'] else 'FAIL'}"
                                       for k, v in grade.items()))
        self.say(f"Saboteur was {w.people[w.saboteur_id].name}. Replay: {path}")
        if getattr(self.brain, "usage", None):
            self.say(f"API usage: {self.brain.usage}")
        return replay
