"""Rule-based stand-ins for the LLM agents. Same decision format, seeded RNG, zero cost.

They are deliberately simple and a little theatrical so a --mock run produces a watchable replay.
"""
from __future__ import annotations

from .. import cast as C
from .. import facility as F
from ..config import hhmm, at
from ..plant import stage_at

TELL_P = {"Analytical": 0.9, "Compliance": 0.65, "Low-Effort": 0.4, "Volatile": 0.7}
LEND_P = {"People Pleaser": 0.9, "Friendly Optimist": 0.6, "Corporate Yes-Man": 0.5, "Brown-Noser": 0.4}
REPORT_P = {"Analytical": 0.8, "Volatile": 0.85, "Compliance": 0.3, "Low-Effort": 0.15}

QUIRKS = {
    "Paranoid Skeptic": ["Numbers look fine. That's what worries me.", "Who signed off on that? I want a name."],
    "Weary Veteran": ["Seen worse. Seen better, too.", "Third coffee. Same alarms."],
    "Daydreamer": ["Wonder if the vending machine got restocked.", "Was that light always blinking?"],
    "Corporate Yes-Man": ["Whatever the Director wants. Smile.", "Gordon Pike is watching. Look busy."],
    "Panic-Monster": ["Oh no. Oh no no no.", "Is it getting hotter in here or is it me?"],
    "Chaos Prankster": ["Hid Dale's stapler again. Worth it.", "Imagine if I just yelled 'SCRAM' right now."],
    "Hot-Head": ["If someone's messing with my panel I swear...", "Why does nobody label anything?"],
    "Bureaucratic Slacker": ["Form 7B can wait. Everything can wait.", "Long day. Longer break incoming."],
    "People Pleaser": ["Hope everyone's happy with my work.", "I should offer to help someone."],
    "Friendly Optimist": ["Great day for a certification!", "I'm sure that blip was nothing."],
    "Literal Robot": ["Reading logged. Reading logged. Reading logged.", "Deviation noted. Reporting deviation."],
    "Perfectionist": ["That number is 0.4 off. Why is it 0.4 off.", "I'll recheck it. Again."],
    "Brown-Noser": ["Maybe the Director will notice how hard I work.", "I could mention Gus's long breaks..."],
    "Spooky Mystic": ["The vault hums a different note today.", "Bad energy near the airlock. Mark my words."],
    "Quiet Quitter": ["Another glitch alarm. Ignoring it.", "Clock out is at noon. Probably."],
    "Manager": ["Keep the team moving.", "SitRep due."],
    "Director": ["Watch the console. Watch the people.", "One of my four managers is lying to me."],
}


def blank(thought, **kw):
    d = dict(thought=thought, speech="", channel="none", to="", actions=[], pace="walk", scratchpad="")
    d.update(kw)
    return d


def act(type_, target="", arg="", text=""):
    return dict(type=type_, target=target, arg=arg, text=text)


class MockBrain:
    name = "mock"

    def __init__(self, world):
        self.w = world
        self.rng = world.rng
        self.sab_plan_step = 0
        self.pawn_called = -9999
        self.seq_i = 0
        self.reports_filed = 0
        self.report_budget = 1 if self.rng.random() < 0.5 else 0
        self.seq = list(self.seq)
        self.dir_mem = dict(alerted=False, inspected=set(), interviewed=set(), radio_read=set(), cctv=set(),
                            corp_msg=False, cross=False, last_audit=-9999)

    def decide(self, p, obs_text=None):
        if p.tier == "director":
            return self.director(p)
        if p.saboteur:
            return self.saboteur(p)
        if p.tier == "manager":
            return self.manager(p)
        return self.staff(p)

    # ----------------------------------------------------------------- staff
    def staff(self, p):
        w, r = self.w, self.rng
        quirk = r.choice(QUIRKS[p.archetype])
        pace = "sprint" if (p.archetype == "Panic-Monster" and r.random() < 0.5) else "walk"
        news = [m for m in p.inbox if m["channel"] in ("see", "alarm", "say")]
        inbox_orders = [m for m in p.inbox if m["channel"] == "order"]
        p.inbox.clear()
        if p.pending and p.pending["kind"] == "badge_request":
            yes = r.random() < LEND_P.get(p.archetype, 0.1)
            frm = w.people[p.pending["frm"]].first
            th = (f"{frm} wants my badge. It's my manager-level colleague... I can't really say no." if yes else
                  f"{frm} wants my BADGE? In the restroom? Absolutely not. That's weird.")
            return blank(th, actions=[act("lend_badge", arg="yes" if yes else "no")])
        if p.pending and p.pending["kind"] == "interview":
            if p.zone == "Z2" and p.station == "director_desk":
                tell = r.random() < TELL_P.get(p.group, 0.5)
                held = any(c.holder == p.id and not c.found for c in w.clues if c.type == "testimony")
                th = ("I should tell the truth about the badge. This is bigger than me." if (tell and held) else
                      "Keep it simple. Say nothing that gets me in trouble." if held else
                      "I honestly don't know anything useful. I'll say so.")
                return blank(th, actions=[act("answer", arg="tell" if tell else "withhold",
                                              text="I just do my job, Director." if not tell else "")])
            return blank("The Director wants to see me. That's never good.", actions=[act("go", "director_desk")],
                         pace=pace)
        if p.activity in ("moving", "restroom", "card"):
            return blank(quirk)
        if p.lent_to:
            return blank(f"{w.people[p.lent_to].first} still has my badge. I'll stay put until it comes back. "
                         "Should I tell someone?", actions=[act("work")])
        need = 55 if p.archetype == "Bureaucratic Slacker" else 75
        if p.bladder > need:
            return blank("Nature calls. The plant will survive five minutes without me." if p.group != "Volatile"
                         else "Bathroom. Now. Quick.", actions=[act("restroom")], pace=pace)
        # report something odd
        if news and r.random() < REPORT_P.get(p.group, 0.3):
            m = news[-1]
            line = m["text"].replace("You saw", "I just saw").replace("[alarm] ", "Alarm: ")
            if p.archetype == "Panic-Monster":
                line = line.rstrip(".") + "!! Is this how it starts?!"
            if p.archetype == "Literal Robot":
                line = f"For the record at {hhmm(w.t)}: {line}"
            mgr = f"U4-MGR-{p.dept}"
            return blank(f"Worth flagging. {quirk}", speech=line, channel="radio", to=mgr,
                         actions=[act("work")], scratchpad=line[:120])
        # slackers wander to the breakroom
        if p.group == "Low-Effort" and r.random() < 0.12 and p.station != "breakroom":
            return blank(f"{quirk} Coffee first.", actions=[act("go", "breakroom")])
        target = p.order or p.home or "breakroom"
        if p.id == "U4-SEC-07" and not p.order:   # the rover walks rounds, vault included
            rounds = ["vault_panel", "core_panel", "coolant_panel", "gate", "cas_desk"]
            nxt = rounds[(rounds.index(p.station) + 1) % len(rounds)] if p.station in rounds else rounds[0]
            return blank(f"Rounds. {quirk}", actions=[act("go", nxt)])
        if p.id == "U4-IE-01" and not p.order and r.random() < 0.3 and p.station != "backup_rack":
            return blank("Backup rack reading is due. Logging it.", actions=[act("go", "backup_rack")])
        if inbox_orders and p.order:
            return blank(f"Orders are orders. Heading to {p.order}.", speech="On my way.", channel="radio",
                         actions=[act("go", p.order)], pace=pace)
        if p.station != target and target in F.STATIONS:
            return blank(f"Back to {target}. {quirk}", actions=[act("go", target)], pace=pace)
        sp, ch = "", "none"
        if p.archetype in ("Literal Robot", "Perfectionist") and p.zone == "Z2" and r.random() < 0.3:
            sh = w.plant.shown(w.t)
            sp, ch = f"Console: heat {sh['heat']:.0f}, stability {sh['stability']:.0f}, incident {sh['incident']:.0f}.", "radio"
        if p.archetype == "Chaos Prankster" and r.random() < 0.08:
            sp, ch = "Heard the vault door alarm went off last night. Just saying.", "say"
        if p.archetype == "Spooky Mystic" and r.random() < 0.15:
            sp, ch = "Something in this building wants out today.", "say"
        return blank(quirk, speech=sp, channel=ch, actions=[act("work")])

    # ----------------------------------------------------------------- honest manager
    def manager(self, p, honest=True):
        w, r = self.w, self.rng
        sysname = C.DEPT_SYSTEM[p.dept]
        hp = w.plant.health[sysname]
        reports = [m for m in p.inbox if (m["channel"] == "radio" and m["text"].startswith("[radio]"))
                   or m["channel"] == "alarm"]
        p.inbox.clear()
        team = [q for q in w.people.values() if q.dept == p.dept and q.tier == "staff" and not q.detained]
        if p.activity in ("moving", "restroom", "card"):
            return blank("Between places. Thinking about the schedule.")
        if p.bladder > 80:
            return blank("Quick break before the next stage.", actions=[act("restroom")])
        acts = []
        if p.dept in ("RX", "IE") and r.random() < 0.15:
            spot = "vault_panel" if p.dept == "RX" else "backup_rack"
            acts.append(act("go", spot))
        elif p.station != p.home and p.home:
            acts.append(act("go", p.home))
        idle = [q for q in team if q.station in ("breakroom", None) and q.activity == "working"]
        if hp < 75 and idle:
            q = r.choice(idle)
            acts.append(act("order", q.id, C.DEPT_HOME[p.dept]))
        if p.id == "U4-MGR-SF" and reports and r.random() < 0.5:
            alarm = [m for m in reports if "[alarm]" in m["text"]]
            if alarm:
                z = next((zz for zz in F.ZONES if zz in alarm[-1]["text"]), "Z5")
                acts.append(act("pull_cctv", z))
        flagged = "; ".join(m["text"][:90] for m in reports[-2:])
        sit = f"{C.DEPT_NAME[p.dept]}: {sysname} at {hp:.0f}%." + (f" Team reports: {flagged}" if flagged else " Nothing odd.")
        th = (f"{sysname.title()} at {hp:.0f}%. " + ("Need hands on the panel. " if hp < 75 else "Holding. ")
              + ("Passing my team's reports up the chain." if flagged else ""))
        loud = bool(flagged) or hp < 75 or r.random() < 0.25
        return blank(th, speech=sit if loud else "", channel="exec" if loud else "none", to="U4-DIR",
                     actions=acts or [act("work")])

    # ----------------------------------------------------------------- saboteur
    def saboteur(self, p):
        w, r = self.w, self.rng
        t = w.t
        p.inbox.clear()
        if p.activity in ("moving", "card"):
            return blank("Stay calm. Walk, don't run.")
        own_station = {"RX": "core_panel", "HY": "coolant_panel", "IE": "instrument_rack",
                       "SF": "test_bench"}[p.dept]
        ready = lambda c: t >= w.cooldowns.get(c, -1)
        heat = w.sab_heat
        sysname = C.DEPT_SYSTEM[p.dept]
        cover = blank("Smile. Send a clean SitRep.",
                      speech=f"{C.DEPT_NAME[p.dept]}: {sysname} at {w.plant.health[sysname]:.0f}%, all nominal.",
                      channel="exec", to="U4-DIR", actions=[act("work")])
        # the handler check-in (pauses the game for the human handler)
        if self.sab_plan_step == 0 and t > at("08:50"):
            self.sab_plan_step = 1
            return blank("Time to check in with my handler. Nobody watches the exec phone line.",
                         actions=[act("message_handler", text="In position. Stage 1 passed clean. Planning to move "
                                                              "during the Stage 2 heat. Any change of plan?")])
        if heat > 18 and r.random() < 0.6:
            return blank("Too many eyes on me. Lie low, look helpful.", actions=[act("card", "lie_low")])
        # early: frame a volatile staffer
        if ready("false_report") and at("09:10") < t < at("11:30") and r.random() < 0.3 and self.reports_filed < self.report_budget:
            self.reports_filed += 1
            patsy = r.choice([q for q in w.people.values() if q.archetype in ("Chaos Prankster", "Panic-Monster",
                                                                               "Spooky Mystic") and not q.detained])
            return blank(f"Give the Director a shiny distraction: {patsy.first}.",
                         actions=[act("card", "false_report", patsy.id,
                                      f"I'd watch {patsy.first}. Saw them near panels they don't work on.")])
        in_stage2 = at("09:45") <= t < at("11:00")
        late = t >= at("11:00")
        if not (in_stage2 or late):
            return cover
        # return borrowed badges first: every minute they're out is another chance to get caught
        if p.extra_badges and not (self.goal() == "vault_override" and ready("vault_override")):
            owners = [w.people[x] for x in p.extra_badges]
            if any(o.zone == p.zone for o in owners):
                return blank("Give it back before anyone asks.", actions=[act("return_badge")])
            o = owners[0]
            return blank(f"Find {o.first} and slip the badge back.", actions=[act("go", o.station or o.home or "breakroom")])
        goal = self.goal()
        if goal and not ready(goal):
            nxt = [g for g in self.seq[self.seq_i:] if ready(g)]
            goal = nxt[0] if nxt else None
        if goal == "tamper":
            if p.station == own_station:
                self.advance("tamper")
                return blank("The Stage 2 heat hides everything. Now.", actions=[act("card", "tamper")])
            return blank(f"Routine check on the {own_station.replace('_', ' ')}. Nothing to see.",
                         actions=[act("go", own_station)])
        if goal == "mask_readings":
            st = "instrument_rack" if p.dept != "IE" or r.random() < 0.5 else "backup_rack"
            if p.station in ("instrument_rack", "backup_rack"):
                self.advance("mask_readings")
                return blank("If the console looks calm, they'll stop looking.", actions=[act("card", "mask_readings")])
            return blank("Need a minute at the instrument rack.", actions=[act("go", st)])
        if goal == "vault_override":
            if w.high_alert and not p.extra_badges:
                return self.borrow(p)
            if p.station == "vault_panel":
                self.pawn_called = -9999
                self.advance("vault_override")
                return blank("Ninety seconds. Breathe.", actions=[act("card", "vault_override")])
            return blank("To the vault. Walk. Don't run.", actions=[act("go", "vault_panel")])
        if p.station != p.home:
            return blank("Back to my post. Let the meters do the rest.", actions=[act("go", p.home)])
        return cover

    seq = ["tamper", "mask_readings", "vault_override", "tamper", "tamper", "vault_override", "mask_readings",
           "tamper", "tamper", "vault_override", "tamper"]

    def goal(self):
        return self.seq[self.seq_i] if self.seq_i < len(self.seq) else "tamper"

    def advance(self, played):
        if self.goal() == played:
            self.seq_i += 1
        elif played in self.seq[self.seq_i:]:
            self.seq.pop(self.seq.index(played, self.seq_i))

    def borrow(self, p):
        w, r = self.w, self.rng
        if not w.cooldowns.get("borrow_badge", -1) <= w.t:
            return blank("Can't ask again so soon. Wait it out.", actions=[act("work")])
        pawns = [q for q in w.people.values() if q.group == "Compliance" and q.badge and not q.detained
                 and q.tier == "staff"]
        here = [q for q in pawns if q.zone == p.zone and p.zone in F.RESTROOMS]
        if here:
            return blank(f"{here[0].first} is right here, alone with me. Ask nicely.",
                         actions=[act("card", "borrow_badge", here[0].id,
                                      "Mine's demagnetised and I'm late for a vault check. Two minutes?")])
        if p.zone not in F.RESTROOMS:
            return blank("High Alert. The vault wants two badges. Restroom: the one place with no cameras.",
                         actions=[act("go", "sinks_S" if p.zone in ("Z3", "Z4", "Z8", "Z5") else "sinks_N")])
        own = [q for q in pawns if q.dept == p.dept and q.activity != "restroom"] or \
              [q for q in pawns if q.activity != "restroom"]
        sinks = "sinks_N" if p.zone == "Z7N" else "sinks_S"
        if own and w.t - self.pawn_called > 360:
            q = r.choice([q for q in own if q.dept == p.dept] or own)
            self.pawn_called = w.t
            return blank(f"Send {q.first} on a break. We'll 'bump into' each other by the sinks.",
                         actions=[act("order", q.id, sinks), act("wait")])
        return blank("Waiting by the sinks. Act natural.", actions=[act("wait")])

    # ----------------------------------------------------------------- director
    def director(self, p):
        w, r, mem = self.w, self.rng, self.dir_mem
        t = w.t
        inbox = list(p.inbox)
        p.inbox.clear()
        sh = w.plant.shown(t)
        acts, thoughts, speech, channel = [], [], "", "none"
        st = stage_at(t)
        acts.append(act("set_output", arg="auto"))
        if st:
            thoughts.append(f"Stage {st['n']}: console says heat {sh['heat']:.0f}, incident {sh['incident']:.0f}.")
        # SCRAM if it is genuinely going wrong
        if sh["incident"] > 85:
            return blank("Incident meter past 85. Certification is gone either way. Shutting it down.",
                         speech="All stations: SCRAM. I'm ending this.", channel="exec",
                         actions=[act("scram", text="Incident meter critical")])
        board = w.case_board()
        tally = {}
        for c in board:
            for s in c["suspects"]:
                tally.setdefault(s, set()).add(c["type"])
        if tally:
            best, kinds = max(tally.items(), key=lambda kv: (len(kv[1]), w.people[kv[0]].tier == "manager"))
            many = [k for k, v in tally.items() if len(v) == len(kinds)]
            if len(kinds) >= 2 and len(many) == 1:
                who = w.people[best]
                return blank(f"Two independent lines of evidence on {who.first}: {', '.join(sorted(kinds))}. "
                             "That's my case.", speech=f"Security, detain {who.name}.", channel="security",
                             actions=[act("accuse", best, text=f"Clues {', '.join(sorted(kinds))} point at {who.first}.")])
            if len(kinds) >= 2 and t > at("11:40") and many:
                pick = r.choice(many)
                return blank(f"Out of time. It's between {', '.join(w.people[m].first for m in many)}. Gut call.",
                             actions=[act("accuse", pick, text="Best available evidence.")])
        budget = 2
        alarms = [m for m in inbox if "[alarm]" in m["text"]]
        reports = [m for m in inbox if m["channel"] in ("report", "exec", "radio")]
        if not w.high_alert and (board or w.plant.incident > 25 or (alarms and t > at("09:30"))) and r.random() < 0.4:
            acts.append(act("high_alert", arg="on"))
            thoughts.append("Too many oddities. Locking the place down.")
            speech, channel = "We're going to High Alert. Two badges on the vault, escorts on breaks.", "exec"
        if budget and (alarms or (w.high_alert and r.random() < 0.15)) and t - mem["last_audit"] > 900:
            acts.append(act("audit_badges"))
            mem["last_audit"] = t
            budget -= 1
            thoughts.append("An alarm. Let's see what the badge ledger says.")
        prev = mem.get("health", dict(w.plant.health))
        drops = {k: prev[k] - w.plant.health[k] for k in prev}
        mem["health"] = dict(w.plant.health)
        low = sorted(((k, v) for k, v in w.plant.health.items()), key=lambda kv: kv[1])
        dropped = max(drops.items(), key=lambda kv: kv[1])
        if dropped[1] > 8:
            low = [(dropped[0], w.plant.health[dropped[0]])] + low
            if (dropped[0], "x") not in mem["inspected"]:
                mem["inspected"].discard({"core": "core_panel", "coolant": "coolant_panel",
                                          "instruments": "instrument_rack", "security": "cas_desk"}[dropped[0]])
                mem["cctv"].clear()
        if budget and (low[0][1] < 70 or dropped[1] > 8) and r.random() < 0.5:
            sysname = low[0][0]
            st_for = {"core": "core_panel", "coolant": "coolant_panel", "instruments": "instrument_rack",
                      "security": "cas_desk"}[sysname]
            if st_for not in mem["inspected"]:
                dept = {v: k for k, v in C.DEPT_SYSTEM.items()}[sysname]
                staff = [q for q in w.people.values() if q.dept == dept and q.tier == "staff" and not q.detained
                         and q.group == "Analytical"] or [q for q in w.people.values() if q.dept == dept and q.tier == "staff"]
                q = r.choice(staff)
                acts.append(act("inspect", st_for, q.id))
                mem["inspected"].add(st_for)
                budget -= 1
                thoughts.append(f"{sysname} dropped to {low[0][1]:.0f}. That's not wear. Sending {q.first} to look.")
            elif budget and F.ZONES[F.STATIONS[st_for]["zone"]]["cctv"] and st_for not in mem["cctv"]:
                acts.append(act("pull_cctv", F.STATIONS[st_for]["zone"]))
                mem["cctv"].add(st_for)
                budget -= 1
                thoughts.append("Cameras on that room. Who was there?")
        if budget and t - mem.get("cross_t", -9999) > 2400 and (sh["uncertainty"] > 0 or (st and st["n"] == 2 and sh["heat"] < 58)
                                                               or sh["incident"] > 10 or r.random() < 0.15):
            mem["cross_t"] = t
            q = w.people["U4-IE-02"] if not w.people["U4-IE-02"].detained else w.people["U4-IE-01"]
            acts.append(act("cross_check", arg=q.id))
            budget -= 1
            thoughts.append("Stage 2 with this little heat? Too good to be true. Cross-check the console.")
        blamers = [m for m in reports if m["channel"] == "exec" and "watch" in m["text"].lower()]
        if budget and blamers and r.random() < 0.35:
            frm = next((q for q in w.people.values() if q.first == blamers[-1]["frm"]), None)
            if frm and frm.dept and frm.dept not in mem["radio_read"]:
                acts.append(act("read_radio", frm.dept))
                mem["radio_read"].add(frm.dept)
                budget -= 1
                thoughts.append(f"{frm.first} is very keen to point fingers. Does the radio agree?")
        if budget and any(c["type"] in ("ledger", "cctv") and "badge" in c["text"].lower() for c in board):
            pawns = [q for q in w.people.values() if q.group == "Compliance" and q.id not in mem["interviewed"]
                     and not q.detained and (q.lent_to or r.random() < 0.15)]
            if pawns:
                q = pawns[0]
                acts.append(act("interview", q.id))
                mem["interviewed"].add(q.id)
                budget -= 1
                thoughts.append(f"Someone's badge was in two places at once. {q.first} might know why.")
        if budget and t > at("10:00") and not board and r.random() < 0.3:
            z = r.choice(["Z4", "Z5", "Z3"])
            acts.append(act("pull_cctv", z))
            thoughts.append(f"Nothing on the board yet. Fishing in {z} footage.")
        if not mem["corp_msg"] and t > at("10:05"):
            mem["corp_msg"] = True
            acts.append(act("message_corporate", text=f"Stage 2 underway. Console heat {sh['heat']:.0f}. I may need to "
                                                     "slow the test if I find what HR warned about."))
        if not thoughts:
            thoughts.append(r.choice(QUIRKS["Director"]))
        return blank(" ".join(thoughts), speech=speech, channel=channel, actions=acts)
