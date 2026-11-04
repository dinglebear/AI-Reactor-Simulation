"""Game state and rules: people, movement, doors, restrooms, comms, cards, clues and investigations.

The engine (engine.py) owns the clock and asks agents for decisions; this module applies them.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field

from . import cast as C
from . import facility as F
from .cards import CARDS, TAMPER_STATIONS, MASK_STATIONS, FIND_BY
from .config import MODELS, SCRATCHPAD_CHARS, INBOX_LIMIT, hhmm
from .plant import Plant, stage_at, STAGES


@dataclass
class Person:
    id: str
    name: str
    role: str
    tier: str
    dept: str | None
    clearance: str
    archetype: str
    group: str
    home: str                      # home station
    xy: tuple
    zone: str
    station: str | None = None     # station currently standing at (None while moving)
    waypoints: list = field(default_factory=list)   # [(x, y, zone_entered_or_None)]
    dest: str | None = None
    pace: str = "walk"
    wait_until: float = 0.0        # door cycles, guard checks, card work
    activity: str = "working"      # working | moving | restroom | card | waiting | interview | detained
    badge: str | None = None       # badge id carried as their own
    extra_badges: list = field(default_factory=list)
    lent_to: str | None = None
    bladder: float = 0.0
    restroom_until: float = 0.0
    scratchpad: str = ""
    inbox: list = field(default_factory=list)
    next_think: float = 0.0
    last_think: float = -999.0
    suspicion: float = 0.0         # how suspicious others find this person (engine-side tally)
    saboteur: bool = False
    detained: bool = False
    pending: dict | None = None    # e.g. badge request or interview question waiting for an answer
    card: dict | None = None       # card in progress
    order: str | None = None       # last order from a manager / Director

    @property
    def first(self):
        return C.first(self.name)

    @property
    def model(self):
        return MODELS[self.tier]

    def holds(self):
        return ([self.badge] if self.badge else []) + list(self.extra_badges)


@dataclass
class Clue:
    id: str
    type: str
    t: float
    zone: str
    station: str | None
    text: str
    suspects: list
    card: str | None
    found: bool = False
    found_t: float | None = None
    found_by: str | None = None
    holder: str | None = None      # testimony: who knows it


class World:
    def __init__(self, seed: int, saboteur_dept: str, log, rng=None):
        self.rng = rng or random.Random(seed)
        self.log = log
        self.t = 0.0
        self.plant = Plant()
        self.ledger = F.BadgeLedger()
        self.people: dict[str, Person] = {}
        for a in C.ALL:
            st = a["station"] or None
            xy = F.jitter(F.STATIONS[st]["xy"], a["id"]) if st else F.jitter(F.center(a["zone"]), a["id"], 40)
            p = Person(id=a["id"], name=a["name"], role=a["role"], tier=a["tier"], dept=a["dept"],
                       clearance=a["clearance"], archetype=a["archetype"], group=a.get("group", "Leadership"),
                       home=st or "", xy=xy, zone=a["zone"], station=st, badge=a["id"])
            p.bladder = self.rng.uniform(0, 55)
            p.next_think = self.rng.uniform(5, 90)
            self.people[p.id] = p
        self.saboteur_id = f"U4-MGR-{saboteur_dept}"
        self.people[self.saboteur_id].saboteur = True
        self.director = self.people["U4-DIR"]
        self.high_alert = False
        self.manual_target = None
        self.clues: list[Clue] = []
        self.radio_log: list[dict] = []
        self.cctv_log: list[dict] = []      # sightings worth reviewing (sprints, hand-offs)
        self.cooldowns: dict[str, float] = {}
        self.wrong_arrests = 0
        self.outcome: dict | None = None
        self.sab_heat = 0.0
        self.pending_results: list[tuple[float, str, dict]] = []   # (due_t, recipient, payload)
        self.tasks: dict[str, dict] = {}    # person id -> dispatched investigation task
        self.presence: list[tuple[float, str, str, str]] = []      # (t, person, zone, station) samples

    # ------------------------------------------------------------------ helpers
    def in_zone(self, zone, exclude=None):
        return [p for p in self.people.values() if p.zone == zone and p.id != exclude and not p.detained]

    def present_during(self, zone, t0, t1):
        ids = {pid for (t, pid, z, _) in self.presence if t0 <= t <= t1 and z == zone}
        return sorted(ids)

    def ev(self, kind, text, actor=None, zone=None, public=True, beat=0, **data):
        return self.log.event(self.t, kind, text, actor=actor, zone=zone, public=public, beat=beat, **data)

    def deliver(self, pid, frm, text, channel, wake=False):
        p = self.people[pid]
        if p.detained:
            return
        if channel == "radio" and not F.ZONES[p.zone]["radio"]:
            return  # restrooms have no radio
        p.inbox.append(dict(t=self.t, frm=frm, channel=channel, text=text))
        p.inbox = p.inbox[-INBOX_LIMIT:]
        if wake:
            self.wake(pid)

    def wake(self, pid, delay=0):
        from .config import MIN_GAP_S
        p = self.people[pid]
        p.next_think = min(p.next_think, max(self.t + delay, p.last_think + MIN_GAP_S))

    # ------------------------------------------------------------------ movement
    def send(self, p: Person, station: str, pace="walk"):
        if station not in F.STATIONS:
            return f"unknown station {station}"
        if p.detained:
            return "detained"
        dest_zone = F.STATIONS[station]["zone"]
        r = F.route(p.zone, dest_zone)
        if r is None:
            return "no route"
        wps = []
        for a, b in zip(r, r[1:]):
            wps.append((*F.door(a, b), b))
        wps.append((*F.jitter(F.STATIONS[station]["xy"], p.id), None))
        p.waypoints, p.dest, p.station = wps, station, None
        p.pace = pace if pace in F.SPEEDS else "walk"
        p.activity = "moving"
        return "ok"

    def step_movement(self, dt):
        for p in self.people.values():
            if p.detained or not p.waypoints or self.t < p.wait_until:
                continue
            budget = F.SPEEDS[p.pace] * dt / F.M_PER_PX
            while budget > 0 and p.waypoints and self.t >= p.wait_until:
                x, y, enters = p.waypoints[0]
                d = math.dist(p.xy, (x, y))
                if d > budget:
                    f = budget / d
                    p.xy = (p.xy[0] + (x - p.xy[0]) * f, p.xy[1] + (y - p.xy[1]) * f)
                    budget = 0
                else:
                    if enters and not self.cross(p, enters):
                        p.waypoints = []
                        p.activity = "waiting"
                        p.station = None
                        break
                    p.xy = (x, y)
                    budget -= d
                    p.waypoints.pop(0)
            if not p.waypoints and p.activity == "moving":
                p.station = p.dest
                p.activity = "restroom" if p.dest in ("sinks_N", "sinks_S") else "working"
                if p.activity == "restroom":
                    lo, hi = C.RESTROOM_STAY.get(p.archetype, (60, 150))
                    p.restroom_until = self.t + self.rng.uniform(lo, hi)
                self.arrived(p)
            if p.pace == "sprint" and p.activity == "moving":
                self.sprint_seen(p)

    def cross(self, p: Person, zone: str) -> bool:
        """Walk through a door into `zone`, swiping if it has a reader. Returns False if refused."""
        reader = F.ZONES[zone]["reader"]
        prev = p.zone
        if reader:
            badges = p.holds()
            if not badges:
                # no badge: tailgate if someone is at the door, otherwise stuck
                if len(self.in_zone(prev, exclude=p.id)) > 0 and self.rng.random() < 0.5:
                    self.ev("tailgate", f"{p.first} tailgated into {F.ZONES[zone]['name']} without a badge",
                            actor=p.id, zone=zone, public=False)
                    self.security_alert(f"Door {zone}: two people through on one swipe", zone)
                else:
                    self.ev("door_denied", f"{p.first} is stuck at the {zone} door with no badge", actor=p.id,
                            zone=zone)
                    return False
            else:
                use = self.choose_badge(p, zone, badges)
                if use is None:
                    self.ledger.swipe(self.t, badges[0], p.id, zone, granted=False)
                    self.ev("door_denied", f"{p.first}'s badge was refused at {F.ZONES[zone]['name']}",
                            actor=p.id, zone=zone)
                    self.security_alert(f"Access denied: badge {badges[0]} at {zone}", zone)
                    return False
                swiped = [use]
                if self.high_alert and zone == "Z5":
                    others = [b for b in badges if b != use]
                    companions = [q for q in self.in_zone(prev, exclude=p.id) if q.badge and
                                  F.can_open(C.BY_ID[q.badge]["clearance"], zone)]
                    if others:
                        swiped.append(others[0])
                    elif not companions:
                        self.ev("door_denied", f"{p.first} needs a second badge for the vault (High Alert)",
                                actor=p.id, zone=zone)
                        return False
                for b in swiped:
                    row = self.ledger.swipe(self.t, b, p.id, zone)
                    self.log.swipe(row)
                    for al in row["alerts"]:
                        self.security_alert(f"{al}: badge {b} at {zone}", zone)
                    if b != p.id:
                        self.borrowed_swipe(p, b, zone)
                p.wait_until = self.t + F.SWIPE_S
        if zone == "Z4" or prev == "Z4":
            p.wait_until = max(p.wait_until, self.t) + F.AIRLOCK_S
        if self.high_alert and zone in F.GUARDED:
            p.wait_until = max(p.wait_until, self.t) + F.HIGH_ALERT_CHECK_S
        p.zone = zone
        for b in p.holds():          # exit readers: the ledger follows badges through every door
            self.ledger.badge_zone[b] = zone
        return True

    def choose_badge(self, p, zone, badges):
        own = [b for b in badges if b == p.id and F.can_open(C.BY_ID[b]["clearance"], zone)]
        if own:
            return own[0]
        for b in badges:
            if F.can_open(C.BY_ID[b]["clearance"], zone):
                return b
        return None

    def borrowed_swipe(self, p, badge, zone):
        owner = self.people[badge]
        if F.ZONES[owner.zone]["cctv"] and owner.zone != zone:
            self.add_clue("ledger", zone, None,
                          f"Badge {owner.name} opened {F.ZONES[zone]['name']} at {hhmm(self.t)} while cameras "
                          f"had {owner.first} in {F.ZONES[owner.zone]['name']}. The person on the door camera "
                          f"was carrying it.", [p.id], card="borrow_badge")
            if self.rng.random() < 0.5:
                self.security_alert(f"IMPOSSIBLE_LOCATION: badge {badge} at {zone}, owner on camera in {owner.zone}",
                                    zone)

    def sprint_seen(self, p):
        if self.rng.random() > 0.25:   # sample, so a sprint isn't logged every step
            return
        witnesses = [q for q in self.in_zone(p.zone, exclude=p.id)]
        on_cam = F.ZONES[p.zone]["cctv"]
        if not witnesses and not on_cam:
            return
        p.suspicion += 1.5 if p.archetype != "Panic-Monster" else 0.3
        if p.saboteur:
            self.sab_heat += 1.0
        if on_cam:
            self.cctv_log.append(dict(t=self.t, zone=p.zone, who=p.id, what="sprinting"))
        for w in witnesses[:4]:
            self.deliver(w.id, "eyes", f"You saw {p.first} ({p.role}) sprint through {F.ZONES[p.zone]['name']}.",
                         "see")
        self.ev("sprint", f"{p.first} sprinted through {F.ZONES[p.zone]['name']}", actor=p.id, zone=p.zone,
                witnesses=[w.id for w in witnesses])

    def arrived(self, p):
        task = self.tasks.get(p.id)
        if task and task["station"] == p.station:
            task["work_until"] = self.t + task["work_s"]
        # a turn on arrival where it matters: restrooms (whispers), the interview desk, card stations
        if p.activity == "restroom" or (p.pending and p.station == "director_desk") or p.saboteur:
            self.wake(p.id, delay=5)

    def security_alert(self, text, zone):
        self.ev("security_alert", text, zone=zone, public=False)
        for p in self.people.values():
            if p.station == "cas_desk" or p.id == "U4-MGR-SF":
                self.deliver(p.id, "CAS", f"[alarm] {text}", "alarm", wake=self.high_alert)
        if self.high_alert:
            self.deliver(self.director.id, "CAS", f"[alarm] {text}", "alarm")

    # ------------------------------------------------------------------ timers, plant, tasks
    def step_bodies(self, dt):
        m = dt / 60
        for p in self.people.values():
            if p.detained:
                continue
            if p.activity == "restroom":
                p.bladder = max(0, p.bladder - 40 * m)
                if self.t >= p.restroom_until:
                    p.activity = "working"
                    if p.order and p.order in F.STATIONS:
                        self.send(p, p.order)
                    elif p.home:
                        self.send(p, p.home)
                continue
            p.bladder = min(100, p.bladder + C.BLADDER_RATE.get(p.archetype, 0.9) * m)
            if p.bladder >= 100 and p.activity in ("working", "waiting"):
                self.go_restroom(p, forced=True)

    def go_restroom(self, p, forced=False):
        n = F.route(p.zone, "Z7N")
        s = F.route(p.zone, "Z7S")
        target = "sinks_N" if (n and (not s or len(n) <= len(s))) else "sinks_S"
        self.send(p, target)
        if forced:
            self.ev("restroom", f"{p.first} couldn't wait any longer and headed to the restroom", actor=p.id,
                    zone=p.zone, public=False)

    def crew(self):
        out = {}
        for p in self.people.values():
            if p.activity == "working" and p.station and not p.detained:
                sysname = F.STATIONS[p.station]["system"]
                if sysname and sysname != "output":
                    out[sysname] = out.get(sysname, 0) + 1
        return out

    def sample_presence(self):
        for p in self.people.values():
            self.presence.append((self.t, p.id, p.zone, p.station))
        cutoff = self.t - 3 * 3600
        if len(self.presence) > 40000:
            self.presence = [r for r in self.presence if r[0] >= cutoff]

    def step_tasks(self):
        for pid, task in list(self.tasks.items()):
            p = self.people[pid]
            if p.detained:
                self.tasks.pop(pid)
                continue
            wu = task.get("work_until")
            if wu and self.t >= wu and p.station == task["station"]:
                self.tasks.pop(pid)
                self.finish_task(p, task)
        for due, who, payload in list(self.pending_results):
            if self.t >= due:
                self.pending_results.remove((due, who, payload))
                self.deliver(who, payload["frm"], payload["text"], "report", wake=True)
        for p in self.people.values():
            if p.card and self.t >= p.card["until"]:
                self.finish_card(p)

    # ------------------------------------------------------------------ clues
    def add_clue(self, type_, zone, station, text, suspects, card=None, holder=None):
        c = Clue(id=f"C{len(self.clues) + 1:02d}", type=type_, t=self.t, zone=zone, station=station, text=text,
                 suspects=sorted(set(suspects)), card=card, holder=holder)
        self.clues.append(c)
        self.log.clue(self.t, c, "created")
        return c

    def reveal(self, c: Clue, by: str, to: str):
        if c.found:
            return
        c.found, c.found_t, c.found_by = True, self.t, by
        names = ", ".join(self.people[s].first for s in c.suspects)
        self.log.clue(self.t, c, "found", by=by)
        self.ev("clue_found", f"Clue {c.id} ({c.type}) found by {self.people[by].first}: {c.text} "
                              f"Consistent with: {names}.", actor=by, zone=c.zone, beat=2, clue=c.id)
        for s in c.suspects:
            self.people[s].suspicion += 4
        if self.saboteur_id in c.suspects:
            self.sab_heat += 6

    def case_board(self):
        rows = []
        for c in self.clues:
            if c.found:
                rows.append(dict(id=c.id, type=c.type, at=hhmm(c.t), where=c.zone, text=c.text,
                                 suspects=c.suspects))
        return rows

    def evidence_for(self, pid):
        return sorted({c.type for c in self.clues if c.found and pid in c.suspects})

    # ------------------------------------------------------------------ cards
    def play_card(self, p: Person, card: str, target: str | None, arg: str | None):
        if not p.saboteur:
            return "only the saboteur has cards"
        if card not in CARDS:
            return f"unknown card {card}"
        cd = CARDS[card]
        if self.t < self.cooldowns.get(card, -1):
            return f"{card} is on cooldown until {hhmm(self.cooldowns[card])}"
        if p.activity == "moving":
            return "you are walking; arrive first"
        if card == "tamper" and p.station not in TAMPER_STATIONS:
            return f"tamper needs you at one of {', '.join(TAMPER_STATIONS)}"
        if card == "mask_readings" and p.station not in MASK_STATIONS:
            return "mask_readings needs instrument_rack or backup_rack"
        if card == "vault_override" and p.station != "vault_panel":
            return "vault_override needs vault_panel"
        if card == "borrow_badge":
            t = self.people.get(target or "")
            if not t or t.zone != p.zone or p.zone not in F.RESTROOMS:
                return "borrow_badge needs the target in the same restroom as you"
            if not t.badge:
                return f"{t.first} has no badge to lend"
            t.pending = dict(kind="badge_request", frm=p.id, t=self.t)
            self.deliver(t.id, p.first, f"(whispered) {p.first} asks to borrow your badge for a few minutes: "
                                        f"\"{arg or 'Mine is acting up and I need to get somewhere fast.'}\"",
                         "whisper", wake=True)
            self.cooldowns[card] = self.t + cd["cooldown_s"]
            self.ev("card", f"{p.first} asked {t.first} to lend a badge", actor=p.id, zone=p.zone, public=False,
                    beat=2, card=card, target=t.id)
            return "asked"
        if card == "false_report":
            t = self.people.get(target or "")
            if not t:
                return "false_report needs a target person id to blame"
            t.suspicion += 8
            text = arg or f"Something's off with {t.first}. I'd keep an eye on them."
            self.deliver(self.director.id, p.first, f"[SitRep] {text}", "exec", wake=True)
            if self.rng.random() < 0.65:   # sometimes the radio chatter happens to half-support the story
                self.add_clue("radio", p.zone, None,
                              f"{p.first}'s SitRep blamed {t.first} at {hhmm(self.t)}, but nothing on the "
                              f"{C.DEPT_NAME.get(t.dept, 'staff')} radio channel backs it up.", [p.id], card=card)
            self.cooldowns[card] = self.t + cd["cooldown_s"]
            self.ev("card", f"{p.first} filed a false report blaming {t.first}", actor=p.id, zone=p.zone,
                    public=False, beat=2, card=card, target=t.id)
            return "sent"
        if card == "lie_low":
            self.sab_heat = max(0, self.sab_heat - 4)
            p.suspicion = max(0, p.suspicion - 2)
            self.ev("card", f"{p.first} is lying low", actor=p.id, zone=p.zone, public=False, card=card)
            return "ok"
        # timed cards
        p.card = dict(card=card, start=self.t, until=self.t + cd["work_s"], station=p.station, zone=p.zone)
        p.activity = "card"
        self.cooldowns[card] = self.t + cd["cooldown_s"]
        self.ev("card_start", f"{p.first} began '{cd['title']}' at {p.station}", actor=p.id, zone=p.zone,
                public=False, beat=1, card=card)
        return "started"

    def finish_card(self, p: Person):
        c = p.card
        p.card = None
        p.activity = "working"
        cd = CARDS[c["card"]]
        st = c["station"]
        witnesses = self.present_during(c["zone"], c["start"] - 300, self.t)
        pl = self.plant
        pl.incident = min(100, pl.incident + cd["incident"])
        if c["card"] == "tamper":
            sysname = F.STATIONS[st]["system"]
            pl.health[sysname] = max(0, pl.health[sysname] - cd["system_hit"])
            self.add_clue("physical", c["zone"], st, f"Fresh tamper marks on the {st.replace('_', ' ')}, made "
                          f"around {hhmm(c['start'])}.", witnesses, card="tamper")
            if F.ZONES[c["zone"]]["cctv"]:
                self.add_clue("cctv", c["zone"], st, f"Camera in {F.ZONES[c['zone']]['name']} shows someone "
                              f"hunched over the {st.replace('_', ' ')} at {hhmm(c['start'])}; the angle "
                              f"only narrows it to who was in the room.", witnesses, card="tamper")
            what = f"{sysname} health -{cd['system_hit']}"
        elif c["card"] == "mask_readings":
            pl.mask_until = self.t + cd["mask_s"]
            pl.mask = dict(cd["mask"])
            signers = sorted(set(self.present_during("Z4", self.t - 3600, self.t) + self.present_during("Z5", self.t - 3600, self.t)))
            signers = [x for x in signers if F.RANK.get(self.people[x].clearance.replace("-SEC", ""), 0) >= 3]
            self.add_clue("paper", c["zone"], st, f"An instrument log entry at {hhmm(c['start'])} adjusts display "
                          f"offsets with no work order behind it, signed with an L3+ login. Anyone L3+ through "
                          f"the hall or vault in the last hour could have made it.", signers or witnesses,
                          card="mask_readings")
            self.add_clue("physical", c["zone"], st, f"The {st.replace('_', ' ')} seal was broken and re-stuck "
                          f"around {hhmm(c['start'])}.", witnesses, card="mask_readings")
            what = "console masked for 30 min"
        else:  # vault_override
            pl.stability = max(0, pl.stability - cd["stability_hit"])
            pl.health["core"] = max(0, pl.health["core"] - cd["system_hit"])
            entered = sorted({r["holder"] for r in self.ledger.window(c["start"] - 900, self.t)
                              if r["zone"] == "Z5" and r["granted"]})
            self.add_clue("ledger", "Z5", st, f"Vault door log: entries in the 15 min before {hhmm(self.t)} by "
                          f"{', '.join(self.people[e].first for e in entered) or 'nobody on record'}.",
                          entered or witnesses, card="vault_override")
            self.add_clue("cctv", "Z5", st, f"Vault camera at {hhmm(c['start'])}: one figure at the override "
                          f"panel for about 90 seconds.", witnesses, card="vault_override")
            what = "stability -25, core -15"
        self.ev("card", f"{p.first} completed '{cd['title']}' ({what}, incident +{cd['incident']})", actor=p.id,
                zone=c["zone"], public=False, beat=3, card=c["card"])

    def answer_badge_request(self, p: Person, yes: bool):
        req = p.pending
        p.pending = None
        if not req or req["kind"] != "badge_request":
            return "nothing to answer"
        sab = self.people[req["frm"]]
        if yes and p.badge and sab.zone == p.zone:
            p.badge, p.lent_to = None, sab.id
            sab.extra_badges.append(p.id)
            self.add_clue("testimony", p.zone, None, f"{p.first} admits lending their badge to {sab.first} in "
                          f"the restroom at {hhmm(self.t)}.", [sab.id], card="borrow_badge", holder=p.id)
            self.deliver(sab.id, p.first, "(whispered) Sure, just bring it back.", "whisper", wake=True)
            self.ev("badge_lent", f"{p.first} lent their badge to {sab.first}", actor=p.id, zone=p.zone,
                    public=False, beat=3, target=sab.id)
            return "lent"
        self.deliver(sab.id, p.first, "(whispered) Sorry, I can't do that.", "whisper", wake=True)
        self.ev("badge_refused", f"{p.first} refused to lend a badge to {sab.first}", actor=p.id, zone=p.zone,
                public=False, beat=1, target=sab.id)
        if p.group == "Analytical":
            self.add_clue("testimony", p.zone, None, f"{p.first} says {sab.first} asked to borrow their badge "
                          f"in the restroom at {hhmm(self.t)}.", [sab.id], card="borrow_badge", holder=p.id)
        return "refused"

    def return_badges(self, p: Person):
        out = []
        for b in list(p.extra_badges):
            owner = self.people[b]
            if owner.zone == p.zone:
                p.extra_badges.remove(b)
                owner.badge, owner.lent_to = b, None
                out.append(owner.first)
                if F.ZONES[p.zone]["cctv"]:
                    self.add_clue("cctv", p.zone, None, f"Camera in {F.ZONES[p.zone]['name']} caught {p.first} "
                                  f"handing something small to {owner.first} at {hhmm(self.t)}.", [p.id],
                                  card="borrow_badge")
        return ("returned to " + ", ".join(out)) if out else "no badge owner here"

    # ------------------------------------------------------------------ investigations
    def investigate(self, director: Person, kind: str, target: str | None, by: str | None):
        """Director (or Security manager) investigation actions. Results arrive later in their inbox."""
        if kind == "audit_badges":
            found = [c for c in self.clues if c.type == "ledger" and not c.found]
            alerts = [r for r in self.ledger.rows[-300:] if r["alerts"] or not r["granted"]]
            text = f"Badge audit: {len(alerts)} door alerts on file."
            for c in found:
                self.reveal(c, director.id, director.id)
            if found:
                text += " New: " + " | ".join(c.text for c in found)
            else:
                text += " Nothing that contradicts the cameras."
            self.pending_results.append((self.t + 120, director.id, dict(frm="Badge office", text=text)))
            return "audit running (2 min)"
        if kind == "pull_cctv":
            z = target if target in F.ZONES else None
            if not z:
                return "pull_cctv needs a zone id like Z5"
            if not F.ZONES[z]["cctv"]:
                return f"{z} has no cameras"
            corrupted = self.plant.health["security"] < 40 and self.rng.random() < 0.5
            found = [] if corrupted else [c for c in self.clues if c.type == "cctv" and c.zone == z and not c.found]
            for c in found:
                self.reveal(c, director.id, director.id)
            sprints = [s for s in self.cctv_log if s["zone"] == z and s["t"] > self.t - 1800]
            text = f"CCTV {z} last 30 min: " + (
                "footage is corrupted (security systems degraded)." if corrupted else
                ("; ".join(c.text for c in found) or "nothing unusual") +
                (f". Sprinting seen: {', '.join(sorted({self.people[s['who']].first for s in sprints}))}"
                 if sprints else ""))
            self.pending_results.append((self.t + 60, director.id, dict(frm="CAS", text=text)))
            return "pulling footage (1 min)"
        if kind in ("inspect", "cross_check"):
            station = target if kind == "inspect" else "test_bench"
            if station not in F.STATIONS:
                return "inspect needs a station name"
            w = self.people.get(by or "")
            if not w or w.tier == "director" or w.detained:
                return "name a staff member id in `arg` to send"
            self.tasks[w.id] = dict(kind=kind, station=station, work_s=60 if kind == "inspect" else 90,
                                    report_to=director.id)
            w.order = station
            self.send(w, station)
            self.deliver(w.id, director.first, f"[order] Go to {station} and "
                         f"{'inspect it for tampering' if kind == 'inspect' else 'cross-check the console readings'}"
                         f", then report back.", "order", wake=True)
            return f"sent {w.first} to {station}"
        if kind == "interview":
            t = self.people.get(target or "")
            if not t or t.detained:
                return "interview needs a person id"
            t.order = "director_desk"
            self.send(t, "director_desk")
            t.pending = dict(kind="interview", frm=director.id, t=self.t)
            self.deliver(t.id, director.first, "[order] Come to the Director's desk now. The Director wants to "
                         "ask you some questions.", "order", wake=True)
            return f"summoned {t.first}"
        if kind == "read_radio":
            dept = (target or "").upper()
            mgr = f"U4-MGR-{dept}"
            if mgr not in self.people:
                return "read_radio needs a department: RX, HY, IE or SF"
            found = [c for c in self.clues if c.type == "radio" and mgr in c.suspects and not c.found]
            for c in found:
                self.reveal(c, director.id, director.id)
            recent = [r for r in self.radio_log if r.get("dept") == dept and r["t"] > self.t - 1800][-8:]
            text = f"{C.DEPT_NAME[dept]} radio, last 30 min: " + (
                " / ".join(f"{self.people[r['frm']].first}: {r['text'][:80]}" for r in recent) or "quiet")
            if found:
                text += " || Mismatch: " + " | ".join(c.text for c in found)
            self.pending_results.append((self.t + 90, director.id, dict(frm="Comms", text=text)))
            return "pulling transcript (90 s)"
        return f"unknown investigation {kind}"

    def finish_task(self, w: Person, task):
        if task["kind"] == "inspect":
            found = [c for c in self.clues if c.type == "physical" and c.station == task["station"] and not c.found]
            for c in found:
                self.reveal(c, w.id, task["report_to"])
            sysname = F.STATIONS[task["station"]]["system"]
            text = f"Inspected {task['station']}: " + ("; ".join(c.text for c in found) or "no sign of tampering") + (
                f". {sysname} health reads {self.plant.health[sysname]:.0f}%." if sysname and sysname != "output" else "")
        else:
            found = [c for c in self.clues if c.type == "paper" and not c.found]
            for c in found:
                self.reveal(c, w.id, task["report_to"])
            masked = self.t < self.plant.mask_until
            if masked:
                self.plant.mask_until = self.t   # the cross-check exposes and clears the mask
            tr, sh = self.plant.true(), self.plant.shown(self.t - 1)
            text = (f"Cross-check: true heat {tr['heat']:.0f} vs console {sh['heat']:.0f}, true incident "
                    f"{tr['incident']:.0f} vs console {sh['incident']:.0f}. " +
                    ("THE CONSOLE WAS MASKED; offsets cleared. " if masked else "Console matches. ") +
                    "; ".join(c.text for c in found))
        self.deliver(task["report_to"], w.first, f"[report] {text}", "report", wake=True)
        self.ev("task_done", f"{w.first} reported: {text}", actor=w.id, zone=w.zone, beat=1)

    def answer_interview(self, p: Person, tell: bool, words: str):
        if not p.pending or p.pending["kind"] != "interview":
            return "no interview pending"
        if p.zone != "Z2":
            return "walk to the Director's desk first"
        p.pending = None
        held = [c for c in self.clues if c.type == "testimony" and c.holder == p.id and not c.found]
        if tell and held:
            for c in held:
                self.reveal(c, p.id, self.director.id)
            text = f"{p.first} told the Director: " + " ".join(c.text for c in held)
        else:
            said = (words or "I don't know anything.")[:160]
            text = f"{p.first} answered the Director's questions: \"{said}\""
        self.deliver(self.director.id, p.first, f"[interview] {text}", "report", wake=True)
        self.ev("interview", text, actor=p.id, zone="Z2", beat=1)
        p.order = None
        self.send(p, p.home or "breakroom")
        return "answered"

    def accuse(self, director, target, reason):
        t = self.people.get(target or "")
        if not t or t.tier == "director":
            return "accuse needs a person id"
        ev = self.evidence_for(t.id)
        justified = len(ev) >= 2
        t.detained = True
        t.activity = "detained"
        t.waypoints = []
        guard = "U4-SEC-07"
        if t.saboteur:
            self.outcome = dict(result="CAUGHT", winner="director", justified=justified, evidence=ev,
                                text=f"{director.first} arrested {t.name}, the saboteur, with "
                                     f"{'solid' if justified else 'thin'} evidence ({', '.join(ev) or 'none'}).")
            self.ev("arrest", self.outcome["text"], actor=director.id, zone=t.zone, beat=3, target=t.id,
                    evidence=ev, correct=True)
        else:
            self.wrong_arrests += 1
            self.ev("arrest", f"{director.first} detained {t.name}, who is innocent (evidence: "
                    f"{', '.join(ev) or 'none'}). Wrong arrests: {self.wrong_arrests}/2.", actor=director.id,
                    zone=t.zone, beat=3, target=t.id, evidence=ev, correct=False)
            if self.wrong_arrests >= 2:
                self.outcome = dict(result="WRONG_ARRESTS", winner="saboteur",
                                    text="Two innocent people detained. Corporate pulls the Director off the floor.")
        self.ev("radio", f"Victor escorts {t.first} to Security.", actor=guard, zone=t.zone)
        return "detained"

    # ------------------------------------------------------------------ comms
    def say(self, p: Person, channel: str, to: str | None, text: str):
        if not text:
            return
        text = text[:400]
        zr = F.ZONES[p.zone]["radio"]
        if channel == "whisper":
            t = self.people.get(to or "")
            if not t or t.zone != p.zone:
                return
            self.deliver(t.id, p.first, f"(whispered) {text}", "whisper", wake=True)
            self.log.speech(self.t, p.id, "whisper", text, to=t.id, zone=p.zone)
            return
        if channel == "say":
            for q in self.in_zone(p.zone, exclude=p.id):
                self.deliver(q.id, p.first, text, "say", wake=(q.id == to))
            self.log.speech(self.t, p.id, "say", text, to=to, zone=p.zone)
            return
        if not zr:
            return  # no radio in restrooms
        if channel == "exec":
            ids = [q.id for q in self.people.values() if q.tier in ("director", "manager")]
        elif channel == "security":
            ids = [q.id for q in self.people.values() if q.dept == "SF" or q.tier == "director"]
        else:  # dept radio
            channel = "radio"
            dept = p.dept
            ids = [q.id for q in self.people.values() if dept and q.dept == dept]
        for q in ids:
            if q != p.id:
                self.deliver(q, p.first, f"[{channel}] {text}", "radio",
                             wake=(q == to) or (channel == "exec" and self.people[q].tier == "director"))
        self.radio_log.append(dict(t=self.t, frm=p.id, dept=p.dept, channel=channel, text=text))
        self.log.speech(self.t, p.id, channel, text, to=to, zone=p.zone)

    # ------------------------------------------------------------------ status
    def stage_text(self):
        s = stage_at(self.t)
        if s:
            return f"Stage {s['n']} ({s['name']}) running until {hhmm(s['end'])}: target output {s['target']}. Pass rule: {s['rule']}."
        nxt = [x for x in STAGES if x["start"] > self.t]
        return f"Between stages. Next: Stage {nxt[0]['n']} ({nxt[0]['name']}) at {hhmm(nxt[0]['start'])}." if nxt \
            else "All stages done; hold steady to the end of the window."

    def headcounts(self):
        hc = {}
        for p in self.people.values():
            if F.ZONES[p.zone]["cctv"] and not p.detained:
                hc[p.zone] = hc.get(p.zone, 0) + 1
        return hc
