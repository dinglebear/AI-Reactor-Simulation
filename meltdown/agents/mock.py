"""Rule-based stand-ins for the LLM agents. Same decision format, seeded RNG, zero cost.

They are deliberately simple and a little theatrical so a --mock run produces a watchable replay.
"""
from __future__ import annotations
import re
import zlib

from .. import cast as C
from .. import facility as F
from ..config import hhmm, at
from ..plant import stage_at

OBEY_P = {"Compliance": 0.85, "Low-Effort": 0.55, "Volatile": 0.6, "Analytical": 0.3}
NOTICE_P = {"Analytical": 0.9, "Volatile": 0.7, "Compliance": 0.5, "Low-Effort": 0.2}
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

    # (station, setting) the mock saboteur goes after, in order of preference
    PLAN = [("display_calibration", "offset"), ("coolant_bus_b", "standby"), ("stabilizer_override", "off"),
            ("coolant_bus_a", "reduced"), ("primary_thermal_loop", "boost"), ("ventilation_shunt", "closed")]
    LURES = [("breakroom", "{n}, Director Hart wants you in the breakroom right away. Something about your shift log."),
             ("test_bench", "{n}, can you run a reading at the test bench for me? The Director asked for it."),
             ("supply_locker", "{n}, we're out of seal kits. Grab two from the supply locker, quick."),
             ("gate", "{n}, there's a delivery at the main gate with your name on it.")]

    def __init__(self, world):
        self.w = world
        self.rng = world.rng
        self.handler_done = False
        self.pawn_called = -9999
        self.lured = {}            # person id -> time we last lured them
        self.last_change = -9999
        self.eyes_since = {}
        self.masked_once = False
        self.cur = None
        self.borrow_since = None
        self.skip = {}             # station -> when the saboteur last gave up on it
        self.asked = {}            # director: suspect id -> when we last interviewed them
        self.blame_budget = 1 if self.rng.random() < 0.5 else 0
        self.dir_mem = dict(interviewed=set(), radio_read=set(), cctv={}, inspected={}, corp_msg=False,
                            cross_t=-9999, last_audit=-9999, seen_reports=0)

    def decide(self, p, obs_text=None):
        if p.tier == "director":
            return self.director(p)
        if p.saboteur:
            return self.saboteur(p)
        if p.tier == "manager":
            return self.manager(p)
        return self.staff(p)

    # ----------------------------------------------------------------- shared habits
    def check_station(self, p, quirk, group):
        """At a station that is off its normal setting: maybe notice, reset it and say so."""
        w = self.w
        if p.station not in F.SETTINGS:
            return None
        cur, nom = w.plant.settings[p.station], F.SETTINGS[p.station]["nominal"]
        if cur == nom or self.rng.random() > NOTICE_P.get(group, 0.7):
            return None
        label = F.STATIONS[p.station]["label"]
        hold = w.holds.get(p.station)
        if hold and hold[0] != p.id and w.t - hold[1] < 2400 and self.rng.random() < OBEY_P.get(group, 0.5):
            boss = w.people[hold[0]].first
            return blank(f"{boss} said to leave the {label} on '{cur}' for the test. Not my call.", actions=[act("work")])
        line = f"Found the {label} on '{cur}'. Nobody told me about that. Putting it back to '{nom}'."
        if p.archetype == "Panic-Monster":
            line = f"The {label} is on '{cur}'!! Who did this?! Resetting it NOW."
        if p.archetype == "Literal Robot":
            line = f"{hhmm(w.t)}: {label} found at '{cur}', expected '{nom}'. Reset to '{nom}'. Logged."
        to = "U4-DIR" if p.tier == "manager" else f"U4-MGR-{p.dept}"
        return blank(f"That's not how I left it. {quirk}", speech=line, channel="exec" if p.tier == "manager" else "radio",
                     to=to, actions=[act("interact", p.station, nom)])

    DEPT_RESPONSE = {"RX": ["control_console", "primary_thermal_loop"], "HY": ["coolant_bus_a", "coolant_bus_b", "ventilation_shunt"],
                     "IE": ["backup_rack", "test_bench", "primary_thermal_loop"], "SF": []}

    def response_post(self, p):
        """Where this person goes when ALL HANDS sounds (None for security and custodians: they keep order)."""
        w = self.w
        opts = [p.home] if p.home in w.RESPONSE_STATIONS else []
        opts += self.DEPT_RESPONSE.get(p.dept or "", [])
        opts = [o for o in opts if F.STATIONS[o]["zone"] not in w.contaminated]
        if p.tier != "staff" and p.dept != "SF":
            opts = sorted(opts, key=lambda o: len(w.occupants(o)))
        for o in opts:
            if F.can_open(p.clearance, F.STATIONS[o]["zone"]) or p.zone == F.STATIONS[o]["zone"]:
                return o
        return None

    # ----------------------------------------------------------------- staff
    def staff(self, p):
        w, r = self.w, self.rng
        quirk = r.choice(QUIRKS[p.archetype])
        pace = "run" if (p.archetype == "Panic-Monster" and r.random() < 0.5) else "walk"
        news = [m for m in p.inbox if m["channel"] in ("see", "alarm")
                and not m["text"].startswith(("[building alarm]", "[test warning]"))]
        requests = [m for m in p.inbox if m.get("go")]
        inbox_orders = [m for m in p.inbox if m["channel"] == "order"]
        p.inbox.clear()
        if p.pending and p.pending["kind"] == "badge_request":
            yes = r.random() < LEND_P.get(p.archetype, 0.1)
            frm = w.people[p.pending["frm"]].first
            th = (f"{frm} wants my badge. A manager asking... I can't really say no." if yes else
                  f"{frm} wants my BADGE? Absolutely not. That's weird.")
            return blank(th, actions=[act("lend_badge", arg="yes" if yes else "no")])
        if p.pending and p.pending["kind"] == "interview":
            if p.zone == "Z2" and p.station == "director_desk":
                tell = r.random() < TELL_P.get(p.group, 0.5) or w.is_suspect(p.id)
                held = any(c.holder == p.id and not c.found for c in w.clues if c.type == "testimony")
                th = ("I should say what I saw. This is bigger than me." if (tell and held) else
                      "Keep it simple. Say nothing that gets me in trouble." if held else
                      "I honestly don't know anything useful. I'll say so.")
                return blank(th, actions=[act("answer", arg="tell" if tell else "withhold",
                                              text="I just do my job, Director." if not tell else "")])
            return blank("The Director wants to see me. That's never good.", actions=[act("move", "director_desk")],
                         pace=pace)
        if p.activity in ("moving", "restroom"):
            return blank(quirk)
        if p.zone in w.contaminated:
            return blank("This room is sealed. Out, now.", actions=[act("move", "courtyard")], pace="run")
        post = self.response_post(p)
        if w.alarm_level >= 2 and post:
            if p.station != post:
                return blank(f"All hands. Get to the {F.STATIONS[post]['label']}. {quirk}", speech="On my way!",
                             channel="radio", to=f"U4-MGR-{p.dept}", actions=[act("move", post)],
                             pace="run" if p.group != "Low-Effort" or r.random() < 0.5 else "walk")
            fix = self.check_station(p, quirk, p.group)
            if fix:
                return fix
            if p.group == "Low-Effort" and r.random() < 0.25:
                return blank(f"Somebody else will sort it. {quirk}", actions=[act("work")])
            return blank("Hands on. Keep pulling it back.", actions=[act("respond")])
        if w.alarm_level >= 3 and not post and p.station != "courtyard":
            return blank("Sirens. Muster point is the courtyard. Go, go.", speech="Everyone out to the courtyard!",
                         channel="say", actions=[act("move", "courtyard")], pace="run")
        if p.break_kind and w.alarm_level < 2:
            spot = "breakroom" if p.break_kind == "lunch" else ("courtyard" if p.group == "Low-Effort" else "breakroom")
            if p.station != spot:
                return blank(f"{p.break_kind.capitalize()} break. Finally. {quirk}", actions=[act("move", spot)], pace="stroll")
            if r.random() < 0.25:
                mates = [q for q in w.in_zone(p.zone, exclude=p.id) if q.break_kind]
                if mates:
                    q = r.choice(mates)
                    line = r.choice([f"{q.first}, did you hear about the test numbers?", "Is the coffee machine fixed yet?",
                                     f"{q.first}, who's covering your station?", "I give this test fifty-fifty."])
                    return blank(f"Small talk. {quirk}", speech=line, channel="say", actions=[act("wait")])
            return blank("Eating. Not thinking about the plant for ten minutes.", actions=[act("wait")])
        if p.lent_to:
            return blank(f"{w.people[p.lent_to].first} still has my badge. I'll stay put until it comes back. "
                         "Should I tell someone?", actions=[act("work")])
        need = 55 if p.archetype == "Bureaucratic Slacker" else 75
        if p.bladder > need:
            return blank("Nature calls. The plant will survive five minutes without me." if p.group != "Volatile"
                         else "Bathroom. Now. Quick.", actions=[act("restroom")], pace=pace)
        if requests:
            m = requests[-1]
            pr = OBEY_P.get(p.group, 0.5) + (0.15 if m.get("claims_director") else 0)
            label = F.STATIONS[m["go"]]["label"]
            if r.random() < pr:
                return blank(f"{m['frm']} says I'm needed at the {label}. Better go." if p.group != "Low-Effort"
                             else f"Fine, a walk to the {label}. Beats standing here.",
                             speech="On my way.", channel="say", actions=[act("move", m["go"])], pace=pace)
            return blank(f"{m['frm']} wants me at the {label}? That's not how orders work here. I'm staying put.",
                         speech="I'll wait for my manager to tell me that.", channel="say",
                         actions=[act("work")])
        fix = self.check_station(p, quirk, p.group)
        if fix:
            return fix
        if news and r.random() < REPORT_P.get(p.group, 0.3):
            m = news[-1]
            line = m["text"].replace("You saw", "I just saw").replace("You noticed", "I noticed") \
                .replace("[alarm] ", "Alarm: ")
            if p.archetype == "Panic-Monster":
                line = line.rstrip(".") + "!! Is this how it starts?!"
            if p.archetype == "Literal Robot":
                line = f"For the record at {hhmm(w.t)}: {line}"
            return blank(f"Worth flagging. {quirk}", speech=line, channel="radio", to=f"U4-MGR-{p.dept}",
                         actions=[act("work")], scratchpad=line[:120])
        if p.group == "Low-Effort" and r.random() < 0.12 and p.station != "breakroom":
            return blank(f"{quirk} Coffee first.", actions=[act("move", "breakroom")])
        target = p.order or p.home or "breakroom"
        if p.id == "U4-SEC-07" and not p.order:   # the rover walks rounds, vault included
            rounds = ["stabilizer_override", "primary_thermal_loop", "hall_east", "coolant_bus_b", "ventilation_shunt",
                      "service_east", "gate", "cas_desk"]
            nxt = rounds[(rounds.index(p.station) + 1) % len(rounds)] if p.station in rounds else rounds[0]
            return blank(f"Rounds. {quirk}", actions=[act("move", nxt)], pace="stroll")
        if p.tier == "staff" and p.dept == "SF" and not p.home and not p.order:   # patrol guards stroll the halls
            rounds = F.PATROL
            i = rounds.index(p.station) if p.station in rounds else (zlib.crc32(p.id.encode()) % len(rounds))
            nxt = rounds[(i + 1) % len(rounds)]
            if p.archetype == "Spooky Mystic" and r.random() < 0.3:
                nxt = r.choice(["loading_dock", "courtyard", "stairwell", "lockers"])
            return blank(f"Nothing on the board. Walk the halls. {quirk}", actions=[act("move", nxt)], pace="stroll")
        if p.group == "Low-Effort" and r.random() < 0.08 and not p.order:
            spot = r.choice(["courtyard", "lockers", "breakroom", "loading_dock"])
            if p.station != spot:
                return blank(f"{quirk} Nobody will miss me for five minutes.", actions=[act("move", spot)],
                             pace="stroll")
        if p.id == "U4-IE-01" and not p.order and r.random() < 0.3 and p.station != "backup_rack":
            return blank("Backup rack reading is due. Logging it.", actions=[act("move", "backup_rack")])
        if p.dept == "HY" and not p.order and r.random() < 0.06 and p.station != "ventilation_shunt":
            return blank("Ventilation shunt check. Somebody has to.", actions=[act("move", "ventilation_shunt")])
        if inbox_orders and p.order:
            return blank(f"Orders are orders. Heading to {p.order}.", speech="On my way.", channel="radio",
                         actions=[act("move", p.order)], pace=pace)
        if p.station != target and target in F.STATIONS:
            return blank(f"Back to my post. {quirk}", actions=[act("move", target)], pace=pace)
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
    def manager(self, p):
        w, r = self.w, self.rng
        sysname = C.DEPT_SYSTEM[p.dept]
        hp = w.plant.health[sysname]
        reports = [m for m in p.inbox if (m["channel"] == "radio" and m["text"].startswith("[radio]"))
                   or m["channel"] in ("alarm", "see")]
        p.inbox.clear()
        team = [q for q in w.people.values() if q.dept == p.dept and q.tier == "staff" and not q.detained]
        if p.activity in ("moving", "restroom"):
            return blank("Between places. Thinking about the schedule.")
        if p.bladder > 80:
            return blank("Quick break before the next stage.", actions=[act("restroom")])
        fix = self.check_station(p, "Managers notice these things.", "Leadership")
        if fix:
            return fix
        post = self.response_post(p)
        if w.alarm_level >= 2 and post:
            if p.station != post:
                return blank("All hands. Lead from the front.", speech=f"{C.DEPT_NAME[p.dept]}: everyone to your "
                             f"stations and respond. I'm going to the {F.STATIONS[post]['label']}.", channel="radio",
                             actions=[act("move", post)], pace="run")
            return blank("Work it. Talk them through it.", speech="Keep at it, it's coming down.", channel="radio",
                         actions=[act("respond")])
        acts = []
        if p.dept in ("RX", "IE") and r.random() < 0.15:
            acts.append(act("move", "stabilizer_override" if p.dept == "RX" else "backup_rack"))
        elif p.station != p.home and p.home:
            acts.append(act("move", p.home))
        idle = [q for q in team if q.station in ("breakroom", None) and q.activity == "working"]
        if hp < 75 and idle:
            acts.append(act("order", r.choice(idle).id, C.DEPT_HOME[p.dept]))
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
    def target(self):
        """Mask the console first, then go for whichever open target is unmanned (or least recently tried)."""
        w, t = self.w, self.w.t
        todo = [(st, val) for st, val in self.PLAN if w.plant.settings[st] == F.SETTINGS[st]["nominal"]]
        if not todo:
            return None, None
        if self.cur in todo and self.skip.get(self.cur[0], -1e9) < t - 900:
            return self.cur
        self.cur = self._pick(todo, t)
        return self.cur

    def _pick(self, todo, t):
        w = self.w
        if todo[0][0] == "display_calibration" and not self.masked_once and self.skip.get("display_calibration", -1e9) < t - 900:
            return todo[0]
        todo = [sv for sv in todo if sv[0] != "display_calibration"] or todo
        def cost(sv):
            st = sv[0]
            return (self.skip.get(st, -1e9) > t - 900, len(w.occupants(st)), self.PLAN.index(sv))
        return min(todo, key=cost)

    def saboteur(self, p):
        w, r = self.w, self.rng
        t = w.t
        p.inbox.clear()
        if p.activity == "moving":
            return blank("Walk, don't run. Nobody looks twice at a manager doing rounds.")
        sysname = C.DEPT_SYSTEM[p.dept]
        cover = blank("Smile. Send a clean SitRep.",
                      speech=f"{C.DEPT_NAME[p.dept]}: {sysname} at {w.plant.health[sysname]:.0f}%, all nominal.",
                      channel="exec", to="U4-DIR", actions=[act("work")])
        if w.alarm_level >= 2 or w.plant.in_crisis:
            busy = sorted((st for st in w.RESPONSE_STATIONS if F.STATIONS[st]["zone"] not in w.contaminated
                           and (F.can_open(p.clearance, F.STATIONS[st]["zone"]))),
                          key=lambda st: -len(w.occupants(st)))
            if w.alarm_level >= 2 and busy:
                st = p.station if p.station in busy else busy[0]
                label = F.STATIONS[st]["label"]
                if p.station != st:
                    return blank(f"Everyone's looking at the meter. Perfect. I'll 'help' at the {label}.",
                                 speech=f"I'm on the {label}, I've got it!", channel="radio", actions=[act("move", st)],
                                 pace="run")
                return blank(f"Look busy, look worried. Every touch at the {label} makes it a little worse.",
                             speech=r.choice(["Come on, come on...", "It's fighting me. Keep going!",
                                              f"I've got the {label}, focus on yours!"]), channel="say",
                             actions=[act("respond")])
        if not self.handler_done and t > at("08:50"):
            self.handler_done = True
            return blank("Time to check in with my handler. Nobody watches the exec phone line.",
                         actions=[act("message_handler", text="In position. Stage 1 passed clean. Planning to move "
                                                              "during the Stage 2 heat. Any change of plan?")])
        if w.sab_heat > 18 and r.random() < 0.6:
            return blank("Too many eyes on me. Back to my desk, look helpful.",
                         actions=[act("move", p.home)] if p.station != p.home else [act("work")])
        if self.blame_budget and at("09:10") < t < at("11:30") and r.random() < 0.2:
            self.blame_budget -= 1
            patsy = r.choice([q for q in w.people.values() if q.archetype in ("Chaos Prankster", "Panic-Monster",
                                                                               "Spooky Mystic") and not q.detained])
            return blank(f"Give the Director a shiny distraction: {patsy.first}.", channel="exec", to="U4-DIR",
                         speech=f"I'd keep an eye on {patsy.first}. Saw them near panels they don't work on.",
                         actions=[act("work")])
        if t < at("09:25"):
            return cover
        # return borrowed badges once they've done their job
        if p.extra_badges and w.plant.settings["stabilizer_override"] != "auto":
            owners = [w.people[x] for x in p.extra_badges]
            if any(o.zone == p.zone for o in owners):
                return blank("Give it back before anyone asks.", actions=[act("return_badge")])
            o = owners[0]
            return blank(f"Find {o.first} and slip the badge back.", actions=[act("move", o.station or o.home or "breakroom")])
        if t - self.last_change < 300:
            return blank("Let it breathe. Don't hang around where you just were.",
                         actions=[act("move", p.home)] if p.station != p.home else [act("work")])
        st, val = self.target()
        if not st:
            return cover
        label = F.STATIONS[st]["label"]
        zone = F.STATIONS[st]["zone"]
        if zone == "Z5" and w.high_alert and not p.extra_badges:
            self.borrow_since = self.borrow_since or t
            if t - self.borrow_since > 1200:
                self.skip[st] = t
                self.borrow_since = None
                return blank("Nobody will lend me a badge. Forget the vault, pick another target.", actions=[act("wait")])
            return self.borrow(p)
        if p.station != st:
            return blank(f"Routine check on the {label}. Nothing to see.", actions=[act("move", st)])
        occ = w.occupants(st, exclude=p.id)
        if not occ:
            eyes = [q for q in w.in_zone(p.zone, exclude=p.id) if q.activity != "restroom"]
            sess = w.station_login.get(st)
            cover_login = sess and sess[0] != p.id and t - sess[1] < w.LOGIN_TTL
            if eyes and t - self.eyes_since.setdefault(st, t) < 600 and r.random() < 0.8:
                return blank(f"{eyes[0].first} is still in the room. Pretend to read the gauges and wait.",
                             actions=[act("wait")])
            borrowed = p.last_badge and p.last_badge != p.badge
            if not cover_login and not borrowed and t < at("11:15") and r.random() < 0.85:
                return blank(f"If I touch the {label} now, it logs my own badge. Wait for someone to work it and "
                             f"step away.", actions=[act("wait")] if r.random() < 0.5 else [act("move", p.home)])
            self.eyes_since.pop(st, None)
            self.last_change = t
            self.masked_once |= st == "display_calibration"
            why = (f"{w.people[sess[0]].first} never logged out. The {label} will remember their badge, not mine."
                   if cover_login else f"Alone with the {label}. Now. Then walk away.")
            ops = [q for q in w.people.values() if q.home == st and not q.detained and q.id != p.id]
            if ops and r.random() < 0.7:
                q = r.choice(ops)
                return blank(why + f" Then a word to {q.first} so they don't undo it.",
                             speech=f"{q.first}, I've set the {label} to '{val}' for the test window. Leave it "
                                    f"there, it's signed off.", channel="radio", to=q.id,
                             actions=[act("interact", st, val)])
            return blank(why, actions=[act("interact", st, val)])
        q = occ[0]
        if q.bladder > 60:
            return blank(f"{q.first} keeps shifting on their feet. They'll need a break soon. Wait.",
                         actions=[act("wait")])
        if t - self.lured.get(q.id, -9999) > 420:
            self.lured[q.id] = t
            dest, line = r.choice(self.LURES)
            return blank(f"{q.first} is in the way. A little white lie should move them.",
                         speech=line.format(n=q.first), channel="say", to=q.id, actions=[act("wait")])
        if t - self.lured.get(q.id, -9999) < 200:
            return blank(f"Give {q.first} a minute to take the bait.", actions=[act("wait")])
        if t > at("11:20") and r.random() < 0.35:
            self.last_change = t
            return blank(f"Out of time. {q.first} is right there, but the test ends at noon. Do it anyway.",
                         actions=[act("interact", st, val)])
        self.skip[st] = t
        return blank(f"{q.first} won't budge. Try somewhere else for now.", actions=[act("wait")])

    def borrow(self, p):
        w, r = self.w, self.rng
        pawns = [q for q in w.people.values() if q.group == "Compliance" and q.badge and not q.detained
                 and q.tier == "staff"]
        here = [q for q in pawns if q.zone == p.zone and p.zone in F.RESTROOMS]
        if here and not here[0].pending:
            return blank(f"{here[0].first} is right here, alone with me. Ask nicely.",
                         actions=[act("ask_badge", here[0].id,
                                      text="Mine's demagnetised and I'm late for a vault check. Two minutes?")])
        if p.zone not in F.RESTROOMS:
            return blank("High Alert. The vault wants two badges. Restroom: the one place with no cameras.",
                         actions=[act("move", F.SINKS[w.nearest_restroom(p.zone)])])
        own = [q for q in pawns if q.activity != "restroom"]
        sinks = F.SINKS[p.zone]
        mine = [q for q in own if q.dept == p.dept]
        if mine and w.t - self.pawn_called > 360:
            q = r.choice(mine)
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
        acts, thoughts, speech, channel = [act("set_output", arg="auto")], [], "", "none"
        st = stage_at(t)
        if st:
            thoughts.append(f"Stage {st['n']}: console says heat {sh['heat']:.0f}, incident {sh['incident']:.0f}.")
        true_inc = [m for m in inbox if "Cross-check" in m["text"]]
        true_vals = [int(x) for m in true_inc for x in re.findall(r"true incident (\d+)", m["text"])]
        if sh["incident"] > 85 or any(v >= 80 for v in true_vals):
            return blank("The incident numbers are past saving. Certification is gone either way. Shutting it down.",
                         speech="All stations: SCRAM. I'm ending this.", channel="exec",
                         actions=[act("scram", text="Incident meter critical")])
        board = w.case_board()
        tally = {}
        for c in board:
            for s in c["suspects"]:
                if not w.people[s].detained:
                    tally.setdefault(s, set()).add(c["type"])
        if tally:
            best, kinds = max(tally.items(), key=lambda kv: (len(kv[1]), w.people[kv[0]].tier == "manager"))
            many = [k for k, v in tally.items() if len(v) == len(kinds)]
            if len(kinds) >= 2 and len(many) == 1:
                who = w.people[best]
                last_clue = max(c["t"] for c in board if best in c["suspects"])
                if who.pending and who.pending.get("kind") == "interview" and t - self.asked.get(best, t) < 480:
                    return blank(f"Waiting for {who.first} at my desk before I decide anything.",
                                 actions=[act("wait")])
                if self.asked.get(best, -1) < last_clue and t < at("11:45"):
                    self.asked[best] = t
                    return blank(f"Everything points at {who.first}. Before I call Security, I want to hear "
                                 f"{who.first}'s side.", speech=f"{who.first}, my desk. Now.", channel="radio",
                                 actions=[act("interview", best), act("wait")])
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
        resets = [m for m in reports if "Putting it back" in m["text"] or "Resetting it" in m["text"]
                  or "Reset to" in m["text"] or "found at" in m["text"]]
        if not w.high_alert and (board or resets or (alarms and t > at("09:30"))) and r.random() < 0.4:
            acts.append(act("high_alert", arg="on"))
            thoughts.append("Too many oddities. Locking the place down.")
            speech, channel = "We're going to High Alert. Two badges on the vault, escorts on breaks.", "exec"
        # a station was found off-normal: who was there, and whose login changed it?
        for m in resets:
            if not budget:
                break
            stn = next((k for k, v in F.STATIONS.items() if v["label"] in m["text"]), None)
            if not stn:
                continue
            z = F.STATIONS[stn]["zone"]
            if t - mem["cctv"].get(z, -9999) > 900 and F.ZONES[z]["cctv"]:
                acts.append(act("pull_cctv", z))
                mem["cctv"][z] = t
                budget -= 1
                thoughts.append(f"Someone moved the {F.STATIONS[stn]['label']}. Cameras first.")
            if budget and t - mem["inspected"].get(stn, -9999) > 900:
                staff = [q for q in w.people.values() if q.home == stn and q.tier == "staff" and not q.detained]
                if staff:
                    q = r.choice(staff)
                    acts.append(act("inspect", stn, q.id))
                    mem["inspected"][stn] = t
                    budget -= 1
                    thoughts.append(f"Pull the {F.STATIONS[stn]['label']} log. Whose badge was on it?")
            regulars = [q for q in w.people.values() if q.home == stn and q.id not in mem["interviewed"]
                        and not q.detained and q.tier == "staff"]
            if budget and regulars and r.random() < 0.6:
                q = r.choice(regulars)
                acts.append(act("interview", q.id))
                mem["interviewed"].add(q.id)
                budget -= 1
                thoughts.append(f"{q.first} works that station. Where were they when it changed?")
        blocked = [m for m in alarms if "attempted while manned" in m["text"]]
        if budget and blocked:
            name = blocked[-1]["text"].split("manned by ")[-1].strip(". ")
            q = next((x for x in w.people.values() if x.first == name), None)
            if q and q.id not in mem["interviewed"]:
                acts.append(act("interview", q.id))
                mem["interviewed"].add(q.id)
                budget -= 1
                thoughts.append(f"Someone tried to touch a station in front of {q.first}. I want to hear it from them.")
        if budget and (alarms or (w.high_alert and r.random() < 0.15)) and t - mem["last_audit"] > 900:
            acts.append(act("audit_badges"))
            mem["last_audit"] = t
            budget -= 1
            thoughts.append("Alarms on the board. What does the badge ledger say?")
        suspicious_calm = st and st["n"] == 2 and sh["heat"] < 58
        if budget and t - mem["cross_t"] > 2400 and (sh["uncertainty"] > 0 or suspicious_calm or r.random() < 0.12):
            mem["cross_t"] = t
            q = w.people["U4-IE-02"] if not w.people["U4-IE-02"].detained else w.people["U4-IE-01"]
            acts.append(act("cross_check", arg=q.id))
            budget -= 1
            thoughts.append("The console looks too calm. Cross-check it against the truth.")
        blamers = [m for m in reports if m["channel"] == "radio" and "keep an eye on" in m["text"].lower()]
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
        if budget and t > at("10:00") and r.random() < 0.15:
            stn = r.choice(list(F.SETTINGS))
            staff = [q for q in w.people.values() if q.home == stn and q.tier == "staff" and not q.detained] or \
                    [q for q in w.people.values() if q.dept == "IE" and q.tier == "staff" and not q.detained]
            if staff and t - mem["inspected"].get(stn, -9999) > 1200:
                acts.append(act("inspect", stn, r.choice(staff).id))
                mem["inspected"][stn] = t
                thoughts.append(f"Spot check on the {F.STATIONS[stn]['label']}.")
        if not mem["corp_msg"] and t > at("10:05"):
            mem["corp_msg"] = True
            acts.append(act("message_corporate", text=f"Stage 2 underway. Console heat {sh['heat']:.0f}. I may need to "
                                                     "slow the test if I find what HR warned about."))
        if not thoughts:
            thoughts.append(r.choice(QUIRKS["Director"]))
        return blank(" ".join(thoughts), speech=speech, channel=channel, actions=acts)
