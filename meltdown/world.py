"""Game state and rules: people, movement, doors, restrooms, comms, stations, clues and investigations.

The engine (engine.py) owns the clock and asks agents for decisions; this module applies them.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field

from . import cast as C
from . import facility as F
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
    wait_until: float = 0.0        # door cycles, guard checks
    activity: str = "working"      # working | moving | restroom | waiting | detained
    badge: str | None = None       # badge id carried as their own
    extra_badges: list = field(default_factory=list)
    lent_to: str | None = None
    bladder: float = 0.0
    restroom_until: float = 0.0
    breaks: list = field(default_factory=list)     # [(kind, start, minutes)] from the rota
    break_until: float = 0.0
    break_kind: str = ""
    responding_until: float = 0.0
    exposed: bool = False
    scratchpad: str = ""
    inbox: list = field(default_factory=list)
    next_think: float = 0.0
    last_think: float = -999.0
    suspicion: float = 0.0         # how suspicious others find this person (engine-side tally)
    saboteur: bool = False
    detained: bool = False
    pending: dict | None = None    # e.g. badge request or interview question waiting for an answer
    last_badge: str | None = None  # badge used on the last door; stations log changes under it
    order: str | None = None       # last order from a manager / Director
    listening: dict = field(default_factory=dict)  # channel -> until (eavesdropping on a channel that isn't yours)
    carrying: list = field(default_factory=list)   # small things picked up or taken (not badges)

    @property
    def first(self):
        return C.first(self.name)

    @property
    def model(self):
        from .config import model_for
        return model_for(self)

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
        self.opinions = C.opinions(seed)
        for a in C.ALL:
            st = a["station"] or None
            xy = F.jitter(F.STATIONS[st]["xy"], a["id"]) if st else F.jitter(F.center(a["zone"]), a["id"], 40)
            p = Person(id=a["id"], name=a["name"], role=a["role"], tier=a["tier"], dept=a["dept"],
                       clearance=a["clearance"], archetype=a["archetype"], group=a.get("group", "Leadership"),
                       home=st or "", xy=xy, zone=F.STATIONS[st]["zone"] if st else a["zone"], station=st,
                       badge=a["id"])
            p.bladder = self.rng.uniform(0, 55)
            p.next_think = self.rng.uniform(5, 90)
            self.people[p.id] = p
        self.make_rota()
        self.alarm_level = 0
        self.contaminated: list[str] = []
        self.saboteur_id = f"U4-MGR-{saboteur_dept}"
        self.people[self.saboteur_id].saboteur = True
        self.director = self.people["U4-DIR"]
        self.high_alert = False
        self.manual_target = None
        self.clues: list[Clue] = []
        self.radio_log: list[dict] = []
        self.cctv_log: list[dict] = []      # sightings worth reviewing (runs, hand-offs)
        self.cooldowns: dict[str, float] = {}
        self.station_log: list[dict] = []
        self.holds: dict[str, tuple] = {}           # station -> (who said 'leave it', when)
        self.station_login: dict[str, tuple] = {}   # station -> (person id, last time they worked it)
        self.wrong_arrests = 0
        self.outcome: dict | None = None
        self.sab_heat = 0.0
        self.pending_results: list[tuple[float, str, dict]] = []   # (due_t, recipient, payload)
        self.tasks: dict[str, dict] = {}    # person id -> dispatched investigation task
        self.presence: list[tuple[float, str, str, str]] = []      # (t, person, zone, station) samples
        self.stashes: list[dict] = []       # things people hid: zone, who, t, badges, items, found
        self.listen_log: list[dict] = []    # radio handset log: who tuned to which channel, when

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
    # ------------------------------------------------------------------ break rota
    COFFEE = {"RX": "09:05", "HY": "09:25", "IE": "10:05", "SF": "10:25"}
    LUNCH = {"RX": "10:50", "HY": "11:05", "IE": "11:20", "SF": "11:35"}

    def make_rota(self):
        """Staggered coffee (15 min) and early lunch (30 min). Each department splits into two halves 20 minutes
        apart, so stations thin out rather than empty, but a quiet station is never far away."""
        from .config import at
        for i, p in enumerate(sorted((q for q in self.people.values() if q.tier == "staff"), key=lambda q: q.id)):
            half = 0 if (int(p.id[-2:]) % 2) else 1200
            p.breaks = [("coffee", at(self.COFFEE[p.dept]) + half, 15), ("lunch", at(self.LUNCH[p.dept]) + half // 2, 30)]

    def step_rota(self):
        started = {}
        for p in self.people.values():
            if p.detained:
                continue
            if p.break_kind and self.t >= p.break_until:
                p.break_kind = ""
                self.deliver(p.id, "Rota", "Your break is over. Back to your post.", "rota", wake=True)
            for b in list(p.breaks):
                kind, start, mins = b
                if self.t >= start:
                    p.breaks.remove(b)
                    p.break_kind, p.break_until = kind, self.t + mins * 60
                    spot = "the canteen" if kind == "lunch" else "the breakroom"
                    self.deliver(p.id, "Rota", f"Your {kind} break starts now ({mins} min). {spot.capitalize()} is open.",
                                 "rota", wake=True)
                    started.setdefault(kind, []).append(p.first)

        for kind, names in started.items():
            where = "the canteen" if kind == "lunch" else "coffee"
            self.ev("break", f"{kind.capitalize()} break: {', '.join(names)} head off to {where}.", beat=1)

    def clearances(self, p):
        return [p.clearance] + [self.people[b].clearance for b in p.extra_badges if b in self.people]

    @staticmethod
    def nearest_restroom(zone):
        return min(F.RESTROOMS, key=lambda z: len(F.route(zone, z) or range(99)))

    def send(self, p: Person, station: str, pace="walk"):
        if station not in F.STATIONS:
            return f"unknown station {station}"
        if p.detained:
            return "detained"
        dest_zone = F.STATIONS[station]["zone"]
        if dest_zone in self.contaminated and p.zone != dest_zone:
            return f"{F.ZONES[dest_zone]['name']} is contaminated and sealed off"
        r = F.route(p.zone, dest_zone, self.clearances(p))
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
                p.activity = "restroom" if p.dest in F.SINKS.values() else "working"
                if p.activity == "restroom":
                    lo, hi = C.RESTROOM_STAY.get(p.archetype, (60, 150))
                    p.restroom_until = self.t + self.rng.uniform(lo, hi)
                self.arrived(p)
            if p.pace == "run" and p.activity == "moving":
                self.run_seen(p)

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
                    self.deliver(p.id, "Door", f"Your badge ({C.BY_ID[badges[0]]['clearance']}) doesn't open the "
                                 f"{F.ZONES[zone]['name']} ({F.door_rule(zone)}). The refusal was logged.", "see",
                                 wake=True)
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
                p.last_badge = use
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
                          f"was carrying it.", [p.id])
            if self.rng.random() < 0.5:
                self.security_alert(f"IMPOSSIBLE_LOCATION: badge {badge} at {zone}, owner on camera in {owner.zone}",
                                    zone)

    def run_seen(self, p):
        if self.rng.random() > 0.25:   # sample, so a run isn't logged every step
            return
        witnesses = [q for q in self.in_zone(p.zone, exclude=p.id)]
        on_cam = F.ZONES[p.zone]["cctv"]
        if not witnesses and not on_cam:
            return
        p.suspicion += 1.5 if p.archetype != "Panic-Monster" else 0.3
        if p.saboteur:
            self.sab_heat += 1.0
        if on_cam:
            self.cctv_log.append(dict(t=self.t, zone=p.zone, who=p.id, what="running"))
        for w in witnesses[:4]:
            self.deliver(w.id, "eyes", f"You saw {p.first} ({p.role}) run through {F.ZONES[p.zone]['name']}.",
                         "see")
        self.ev("run", f"{p.first} ran through {F.ZONES[p.zone]['name']}", actor=p.id, zone=p.zone,
                witnesses=[w.id for w in witnesses])

    def arrived(self, p):
        task = self.tasks.get(p.id)
        if task and task.get("station") and task["station"] == p.station:
            task["work_until"] = self.t + task["work_s"]
        # a turn on arrival where it matters: restrooms (whispers), the interview desk
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
        target = F.SINKS[self.nearest_restroom(p.zone)]
        self.send(p, target)
        if forced:
            self.ev("restroom", f"{p.first} couldn't wait any longer and headed to the restroom", actor=p.id,
                    zone=p.zone, public=False)

    # ------------------------------------------------------------------ crisis response and contamination
    RESPONSE_STATIONS = ("control_console", "primary_thermal_loop", "stabilizer_override", "backup_rack",
                         "coolant_bus_a", "coolant_bus_b", "test_bench", "ventilation_shunt")

    def respond(self, p):
        if p.station not in self.RESPONSE_STATIONS:
            return f"respond only counts at a response station: {', '.join(self.RESPONSE_STATIONS)}"
        if F.STATIONS[p.station]["zone"] in self.contaminated:
            return "that room is sealed off"
        p.activity = "working"
        p.responding_until = self.t + 300
        return "responding"

    def response(self):
        """(helpers, spoilers) on crisis response this step. The spy's 'help' counts against the plant."""
        from .plant import RESPONSE_CAP
        per = {}
        spoilers = 0
        for p in self.people.values():
            if p.detained or p.activity != "working" or p.responding_until < self.t or p.station not in self.RESPONSE_STATIONS:
                continue
            if F.STATIONS[p.station]["zone"] in self.contaminated:
                continue
            if p.saboteur:
                spoilers += 1
                self._maybe_notice_spoiler(p)
                continue
            per[p.station] = per.get(p.station, 0) + 1
        return sum(min(v, RESPONSE_CAP) for v in per.values()), spoilers

    def _maybe_notice_spoiler(self, p):
        label = F.STATIONS[p.station]["label"]
        for q in self.occupants(p.station, exclude=p.id):
            chance = {"Analytical": 0.012, "Volatile": 0.006}.get(q.group, 0.002)   # per 5 s step
            if self.rng.random() < chance and not any(c.holder == q.id and c.station == p.station and p.id in c.suspects
                                                     for c in self.clues):
                self.add_clue("testimony", p.zone, p.station, f"{q.first} says {p.first} was 'helping' at the {label} "
                              f"around {hhmm(self.t)}, but every time {p.first} touched it the numbers got worse.",
                              [p.id], holder=q.id)
                self.deliver(q.id, "eyes", f"{p.first} is 'helping' at the {label}, but it keeps getting worse when "
                                           f"{p.first} touches it.", "see", wake=True)

    def contaminate(self, zones, why):
        new = [z for z in zones if z not in self.contaminated and not F.ZONES[z].get("hall")]
        if not new:
            return
        self.contaminated += new
        names = ", ".join(F.ZONES[z]["name"] for z in new)
        self.ev("contamination", f"{why} {names} {'is' if len(new) == 1 else 'are'} contaminated and sealed off.",
                zone=new[0], beat=3, zones=new)
        for p in self.people.values():
            if p.zone in new and not p.detained:
                p.exposed = True
                self.deliver(p.id, "Building", f"[building alarm] {F.ZONES[p.zone]['name']} is contaminated. Get out now.",
                             "alarm", wake=True)
            else:
                self.deliver(p.id, "Building", f"[building alarm] Contamination: {names} sealed off. Stay out.", "alarm")

    def step_contamination(self):
        """Game rule: big spikes leave rooms contaminated even if the meltdown itself is stopped."""
        inc = self.plant.incident
        off = [F.STATIONS[k]["zone"] for k in self.plant.off_nominal() if k != "display_calibration"]
        if inc >= 85 and not self.contaminated:
            self.contaminate(sorted(set(off)) or ["Z4"], "The meltdown meter spiked past 85.")
        if inc >= 95 and "Z4" not in self.contaminated:
            self.contaminate(["Z4", "Z5"], "The meltdown meter spiked past 95.")
        for p in self.people.values():
            if p.zone in self.contaminated and not p.detained and not p.exposed:
                p.exposed = True

    def crew(self):
        out = {}
        for p in self.people.values():
            if p.activity == "working" and p.station in F.SETTINGS and p.station == p.home and not p.detained:
                self.station_login[p.station] = (p.id, self.t)
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
            if task["kind"] == "frisk":
                continue
            wu = task.get("work_until")
            if wu and self.t >= wu and p.station == task["station"]:
                self.tasks.pop(pid)
                self.finish_task(p, task)
        self.step_searches()
        for due, who, payload in list(self.pending_results):
            if self.t >= due:
                self.pending_results.remove((due, who, payload))
                self.deliver(who, payload["frm"], payload["text"], "report", wake=True)

    # ------------------------------------------------------------------ clues
    def add_clue(self, type_, zone, station, text, suspects, holder=None):
        c = Clue(id=f"C{len(self.clues) + 1:02d}", type=type_, t=self.t, zone=zone, station=station, text=text,
                 suspects=sorted(set(suspects)), holder=holder)
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
                rows.append(dict(id=c.id, t=c.t, type=c.type, at=hhmm(c.t), where=c.zone, text=c.text,
                                 suspects=c.suspects))
        return rows

    def evidence_for(self, pid):
        return sorted({c.type for c in self.clues if c.found and pid in c.suspects})

    # ------------------------------------------------------------------ stations
    NOTICE_P = {"Analytical": 0.85, "Volatile": 0.6, "Compliance": 0.5, "Low-Effort": 0.25, "Leadership": 0.7}

    def occupants(self, station, exclude=None):
        return [q for q in self.people.values() if q.station == station and q.id != exclude and not q.detained
                and q.activity in ("working", "waiting")]

    LOGIN_TTL = 600      # a station stays logged in this long after its operator walks away
    CCTV_WINDOW = 900

    def interact(self, p: Person, station: str, setting: str):
        """Change a station's setting. You must be standing at it; a manned station can't be touched unnoticed."""
        if station not in F.SETTINGS:
            return f"{station} has no settings; stations with settings: {', '.join(F.SETTINGS)}"
        spec = F.SETTINGS[station]
        if setting not in spec["options"]:
            return f"setting must be one of {', '.join(spec['options'])}"
        if p.station != station:
            return f"you must be at {station} first (move there)"
        label = F.STATIONS[station]["label"]
        old = self.plant.settings[station]
        if old == setting:
            return f"{label} is already {setting}"
        nominal = setting == spec["nominal"]
        others = self.occupants(station, exclude=p.id)
        if others and not nominal:
            w = others[0]
            self.add_clue("testimony", p.zone, station, f"{w.first} says {p.first} tried to switch the {label} "
                          f"to '{setting}' at {hhmm(self.t)} while {w.first} was standing at it.", [p.id],
                          holder=w.id)
            self.deliver(w.id, "eyes", f"{p.first} just tried to switch the {label} to '{setting}' right in front "
                         f"of you. You stopped them.", "see", wake=True)
            p.suspicion += 6
            if p.saboteur:
                self.sab_heat += 6
            self.security_alert(f"Station {label}: change to '{setting}' attempted while manned by {w.first}", p.zone)
            self.ev("blocked", f"{p.first} tried to set the {label} to '{setting}', but {w.first} was at it",
                    actor=p.id, zone=p.zone, beat=2, station=station, target=w.id)
            return f"blocked: {w.first} is working at the {label} and saw you"
        self.plant.settings[station] = setting
        badge = p.last_badge or p.badge or p.id
        sess = self.station_login.get(station)
        if sess and sess[0] != p.id and self.t - sess[1] < self.LOGIN_TTL:
            badge = self.people[sess[0]].badge or sess[0]     # the previous operator never logged out
        self.station_login[station] = (self.people[badge].id if badge in self.people else p.id, self.t)
        self.station_log.append(dict(t=self.t, station=station, old=old, new=setting, badge=badge, by=p.id))
        if not nominal:
            owner = self.people.get(badge)
            self.add_clue("paper", p.zone, station, f"{label} log: switched to '{setting}' at {hhmm(self.t)} under "
                          f"the login of badge {owner.name if owner else badge}.", [badge if owner else p.id])
            here = [q for q in self.in_zone(p.zone, exclude=p.id) if q.activity != "restroom"]
            if F.ZONES[p.zone]["cctv"]:
                recent = {r["holder"] for r in self.ledger.window(self.t - self.CCTV_WINDOW, self.t)
                          if r["zone"] == p.zone and r["granted"]}
                pool = [p.id] + [q.id for q in here] + sorted(recent - {p.id} - {q.id for q in here})
                self.add_clue("cctv", p.zone, station, f"Camera in {F.ZONES[p.zone]['name']} around {hhmm(self.t)}: "
                              f"a figure at the {label}, face turned away. Anyone in the room in the last "
                              f"{self.CCTV_WINDOW // 60} minutes fits.", pool)
            for q in here:
                if self.rng.random() < self.NOTICE_P.get(q.group, 0.5):
                    self.add_clue("testimony", p.zone, station, f"{q.first} saw {p.first} working the {label} "
                                  f"around {hhmm(self.t)}.", [p.id], holder=q.id)
                    self.deliver(q.id, "eyes", f"You noticed {p.first} adjusting the {label}.", "see")
        self.ev("interact", f"{p.first} set the {label} from '{old}' to '{setting}'", actor=p.id, zone=p.zone,
                public=nominal, beat=1 if nominal else 3, station=station, old=old, new=setting, badge=badge)
        return f"{label} now {setting}"

    def ask_badge(self, p: Person, target: str | None, text: str | None):
        t = self.people.get(target or "")
        if not t or t.zone != p.zone or t.detained:
            return "ask_badge needs the person in the same zone as you"
        if not t.badge:
            return f"{t.first} has no badge to lend"
        t.pending = dict(kind="badge_request", frm=p.id, t=self.t)
        self.deliver(t.id, p.first, f"(whispered) {p.first} asks to borrow your badge for a few minutes: "
                                    f"\"{text or 'Mine is acting up and I need to get somewhere fast.'}\"",
                     "whisper", wake=True)
        if F.ZONES[p.zone]["cctv"]:
            self.add_clue("cctv", p.zone, None, f"Camera in {F.ZONES[p.zone]['name']} shows {p.first} in a quiet "
                          f"word with {t.first} at {hhmm(self.t)}.", [p.id])
        self.ev("badge_ask", f"{p.first} asked {t.first} to lend a badge", actor=p.id, zone=p.zone, public=False,
                beat=2, target=t.id)
        return "asked"

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
                          f"the restroom at {hhmm(self.t)}.", [sab.id], holder=p.id)
            self.deliver(sab.id, p.first, "(whispered) Sure, just bring it back.", "whisper", wake=True)
            self.ev("badge_lent", f"{p.first} lent their badge to {sab.first}", actor=p.id, zone=p.zone,
                    public=False, beat=3, target=sab.id)
            return "lent"
        self.deliver(sab.id, p.first, "(whispered) Sorry, I can't do that.", "whisper", wake=True)
        self.ev("badge_refused", f"{p.first} refused to lend a badge to {sab.first}", actor=p.id, zone=p.zone,
                public=False, beat=1, target=sab.id)
        if p.group == "Analytical":
            self.add_clue("testimony", p.zone, None, f"{p.first} says {sab.first} asked to borrow their badge "
                          f"in the restroom at {hhmm(self.t)}.", [sab.id], holder=p.id)
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
                                  f"handing something small to {owner.first} at {hhmm(self.t)}.", [p.id])
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
            runs = [s for s in self.cctv_log if s["zone"] == z and s["t"] > self.t - 1800]
            text = f"CCTV {z} last 30 min: " + (
                "footage is corrupted (security systems degraded)." if corrupted else
                ("; ".join(c.text for c in found) or "nothing unusual") +
                (f". Running seen: {', '.join(sorted({self.people[s['who']].first for s in runs}))}"
                 if runs else ""))
            self.pending_results.append((self.t + 60, director.id, dict(frm="CAS", text=text)))
            return "pulling footage (1 min)"
        if kind in ("inspect", "cross_check"):
            station = target if kind == "inspect" else "test_bench"
            if station not in F.STATIONS:
                return "inspect needs a station name"
            w = self.people.get(by or "")
            if not w or w.tier == "director" or w.detained:
                return "name a staff member id in `arg` to send"
            if not F.reachable(self.clearances(w), F.STATIONS[station]["zone"]):
                return (f"{w.first}'s badge ({w.clearance}) can't open the {F.ZONES[F.STATIONS[station]['zone']]['name']} "
                        f"({F.door_rule(F.STATIONS[station]['zone'])}). Send someone who can get in.")
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
            raw = (target or "").strip()
            key = raw.upper() if raw.upper() in C.DEPT_NAME else raw.lower()
            if key not in list(C.DEPT_NAME) + ["exec", "security"]:
                return "read_radio needs a channel: RX, HY, IE, SF, exec or security"
            found = []
            if key in C.DEPT_NAME:
                mgr = f"U4-MGR-{key}"
                found = [c for c in self.clues if c.type == "radio" and mgr in c.suspects and not c.found]
                recent = [r for r in self.radio_log if r.get("dept") == key and r["channel"] == "radio"
                          and r["t"] > self.t - 1800][-8:]
            else:
                recent = [r for r in self.radio_log if r["channel"] == key and r["t"] > self.t - 1800][-8:]
            # the handset log: radios report which channel they are on
            taps = [r for r in self.listen_log if r["key"] == key and r["t"] > self.t - 3600]
            for r in taps:
                if not r.get("clue"):
                    who = self.people[r["who"]]
                    r["clue"] = self.add_clue("radio", who.zone, None, f"Handset log: {who.name}'s radio was tuned "
                                              f"to {self.channel_name(key)} at {hhmm(r['t'])}, not their own "
                                              f"channel.", [who.id]).id
                found += [c for c in self.clues if c.id == r["clue"] and not c.found]
            for c in found:
                self.reveal(c, director.id, director.id)
            name = self.channel_name(key)
            text = f"{name[0].upper() + name[1:]}, last 30 min: " + (
                " / ".join(f"{self.people[r['frm']].first}: {r['text'][:80]}" for r in recent) or "quiet")
            if found:
                text += " || " + " | ".join(c.text for c in found)
            self.pending_results.append((self.t + 90, director.id, dict(frm="Comms", text=text)))
            return "pulling transcript (90 s)"
        if kind == "search":
            return self.call_search(director, target, by)
        return f"unknown investigation {kind}"

    @staticmethod
    def spot_in(zone):
        return next((k for k, v in F.STATIONS.items() if v["zone"] == zone), None)

    def call_search(self, director: Person, target: str | None, by: str | None):
        """Security goes looking: for a person (locate + a guard checks their pockets) or a room (a sweep for
        anything hidden). The call goes out on the security channel, so anyone on it hears who is wanted."""
        tgt = (target or "").strip()
        person = self.people.get(tgt)
        zone = tgt if tgt in F.ZONES else None
        if not person and not zone:
            return "search needs a person id or a zone id"
        if person and (person.detained or person.tier == "director"):
            return "search needs someone who isn't detained"
        guards = [q for q in self.people.values() if q.dept == "SF" and q.id.startswith("U4-SEC") and not q.detained
                  and q.id != tgt and q.id not in self.tasks]
        g = self.people.get(by or "")
        if not g or g.detained or g.tier == "director" or g.id == tgt:
            dest = person.zone if person else zone
            guards = [q for q in guards if F.reachable(self.clearances(q), dest)] or guards
            g = min(guards, key=lambda q: len(F.route(q.zone, dest, self.clearances(q)) or range(99)), default=None)
        if not g:
            return "no free guard to send"
        if person:
            where, on_cam = self.locate(person.id)
            call = f"CAS: locate {person.name} for the Director. {g.first}, go find them."
            self.pending_results.append((self.t + 60, director.id, dict(frm="CAS", text=f"Locate {person.first}: {where}.")))
            spot = person.station or self.spot_in(person.zone)
            self.tasks[g.id] = dict(kind="frisk", station=None, who=person.id, until=self.t + 900,
                                    report_to=director.id, next_chase=0)
        else:
            spot = self.spot_in(zone)
            if not spot:
                return f"{zone} is a corridor; sweep a room"
            if not F.reachable(self.clearances(g), zone):
                return f"{g.first}'s badge can't open the {F.ZONES[zone]['name']}"
            call = f"CAS: {g.first}, sweep the {F.ZONES[zone]['name']} for anything that shouldn't be there."
            self.tasks[g.id] = dict(kind="sweep", station=spot, work_s=90, report_to=director.id)
        g.order = spot
        self.send(g, spot, "walk")
        self.deliver(g.id, "CAS", f"[order] {call}", "order", wake=True)
        for q in self.people.values():   # the call goes out on the security channel
            if q.id != g.id and (q.dept == "SF" or q.tier == "director" or q.listening.get("security", -1) > self.t):
                self.deliver(q.id, "CAS", f"[security] {call}", "radio")
        self.radio_log.append(dict(t=self.t, frm=director.id, dept="SF", channel="security", text=call))
        self.ev("search", call, actor=director.id, zone=director.zone, beat=2, target=tgt, guard=g.id)
        return f"{g.first} is on it" + (f"; locate result in 1 min" if person else "")

    def step_searches(self):
        for gid, task in list(self.tasks.items()):
            if task["kind"] != "frisk":
                continue
            g, who = self.people[gid], self.people[task["who"]]
            if g.detained or self.t > task["until"]:
                self.tasks.pop(gid)
                self.deliver(task["report_to"], g.first, f"[report] Couldn't catch up with {who.first}.", "report",
                             wake=True)
                continue
            if g.zone == who.zone:
                self.tasks.pop(gid)
                self.frisk(g, who, task["report_to"])
            elif self.t >= task["next_chase"]:
                task["next_chase"] = self.t + 45
                spot = who.station or who.dest or self.spot_in(who.zone)
                if spot and g.dest != spot:
                    self.send(g, spot, "walk")

    def frisk(self, g: Person, who: Person, report_to: str):
        found = []
        if who.extra_badges:
            found.append("badges that aren't theirs (" + ", ".join(self.people[b].name for b in who.extra_badges) + ")")
        found += who.carrying
        self.deliver(who.id, g.first, f"(in person) {g.first} stops you: \"Director's orders, quick check of your "
                     "pockets.\"" + (f" {g.first} finds: {'; '.join(found)}." if found else " Nothing turns up."),
                     "say", wake=True)
        if found:
            c = self.add_clue("physical", who.zone, None, f"{g.first} searched {who.first} at {hhmm(self.t)} and "
                              f"found {'; '.join(found)}.", [who.id], holder=g.id)
            self.reveal(c, g.id, report_to)
        text = f"Found {who.first} in the {F.ZONES[who.zone]['name']} and checked their pockets: " + (
            "; ".join(found) if found else "nothing unusual") + "."
        self.deliver(report_to, g.first, f"[report] {text}", "report", wake=True)
        self.ev("frisk", f"{g.first} searched {who.first}: " + ("; ".join(found) or "nothing"), actor=g.id,
                zone=who.zone, beat=3 if found else 2, target=who.id)
        g.order = None

    def finish_task(self, w: Person, task):
        st = task["station"]
        if task["kind"] == "sweep":
            r = self.rummage(w, chance=0.8, report_to=task["report_to"])
            self.deliver(task["report_to"], w.first, f"[report] Swept the {F.ZONES[w.zone]['name']}: {r}.", "report",
                         wake=True)
            self.ev("task_done", f"{w.first} swept the {F.ZONES[w.zone]['name']}: {r}", actor=w.id, zone=w.zone, beat=1)
            return
        if task["kind"] == "inspect":
            found = [c for c in self.clues if c.type == "paper" and c.station == st and not c.found]
            for c in found:
                self.reveal(c, w.id, task["report_to"])
            label = F.STATIONS[st]["label"]
            text = f"Inspected the {label}."
            if st in F.SETTINGS:
                cur, nom = self.plant.settings[st], F.SETTINGS[st]["nominal"]
                if cur != nom:
                    self.plant.settings[st] = nom
                    self.station_log.append(dict(t=self.t, station=st, old=cur, new=nom, badge=w.badge or w.id, by=w.id))
                    text += f" It was set to '{cur}'. Reset to '{nom}'."
                else:
                    text += f" Setting is '{cur}', as it should be."
            text += " " + (" ".join(c.text for c in found) if found else "Nothing odd in the station log.")
            sysname = F.STATIONS[st]["system"]
            if sysname and sysname != "output":
                text += f" {sysname.title()} health {self.plant.health[sysname]:.0f}%."
        else:
            masked = self.plant.masked
            found = [c for c in self.clues if c.type == "paper" and c.station == "display_calibration" and not c.found]
            if masked:
                for c in found:
                    self.reveal(c, w.id, task["report_to"])
            tr, sh = self.plant.true(), self.plant.shown(self.t)
            off = ", ".join(f"{F.STATIONS[k]['label']}={v}" for k, v in self.plant.off_nominal().items())
            text = (f"Cross-check: true heat {tr['heat']:.0f} vs console {sh['heat']:.0f}, true stability "
                    f"{tr['stability']:.0f} vs console {sh['stability']:.0f}, true incident {tr['incident']:.0f} vs "
                    f"console {sh['incident']:.0f}. " +
                    ("THE CONSOLE DISAGREES WITH THE TRUTH: the Display Calibration Rack is on 'offset'. " if masked
                     else "Console matches. ") +
                    (f"Stations off their normal setting: {off}. " if off else "") + " ".join(c.text for c in found if c.found))
        self.deliver(task["report_to"], w.first, f"[report] {text}", "report", wake=True)
        self.ev("task_done", f"{w.first} reported: {text}", actor=w.id, zone=w.zone, beat=1)

    def answer_interview(self, p: Person, tell: bool, words: str):
        if not p.pending or p.pending["kind"] != "interview":
            return "no interview pending"
        if p.zone != "Z2":
            return "walk to the Director's desk first"
        p.pending = None
        held = [c for c in self.clues if c.type in ("testimony", "physical") and c.holder == p.id and not c.found]
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

    def is_suspect(self, pid):
        return any(pid in c["suspects"] for c in self.case_board())

    def accuse(self, director, target, reason):
        t = self.people.get(target or "")
        if not t or t.tier == "director":
            return "accuse needs a person id"
        if t.detained:
            return f"{t.first} is already detained"
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
    def mentioned_station(self, text):
        low = text.lower()
        for k, v in F.STATIONS.items():
            if k in low or v["label"].lower() in low:
                return k
        return None

    ASK_WORDS = ("go to", "head to", "head over", "come to", "wants you", "need you", "can you",
                 "could you", "run a", "right away", "go check", "swing by", "get over", "report to", "grab", "with your name")

    def note_request(self, p: Person, to: str | None, text: str, channel: str):
        """Someone tells a person to go somewhere. If they aren't that person's boss, it becomes a witness account."""
        t = self.people.get(to or "")
        st = self.mentioned_station(text)
        if not t or not st or t.id == p.id:
            return
        low = text.lower()
        if "leave it" in low and p.tier in ("manager", "director"):
            self.holds[st] = (p.id, self.t)
            if p.saboteur:
                self.ev("lure", f"{p.first} told {t.first} to leave the {F.STATIONS[st]['label']} alone: "
                        f"\"{text[:140]}\"", actor=p.id, zone=p.zone, public=False, beat=2, target=t.id)
            self.add_clue("testimony", t.zone, st, f"{p.first} told {t.first} at {hhmm(self.t)} to leave the "
                          f"{F.STATIONS[st]['label']} as it was: \"{text[:120]}\"", [p.id], holder=t.id)
            return
        if not any(k in low for k in self.ASK_WORDS):
            return
        claims = any(w in low for w in ("director", "hart", "simone"))
        if t.inbox and t.inbox[-1]["frm"] == p.first:
            t.inbox[-1]["go"] = st
            t.inbox[-1]["claims_director"] = claims
        boss = p.tier == "director" or (p.tier == "manager" and p.dept == t.dept)
        if boss and not (claims and p.tier != "director"):
            return
        what = f"{p.first} told {t.first} to go to the {F.STATIONS[st]['label']} at {hhmm(self.t)}" + (
            ", saying the Director wanted it" if claims and p.tier != "director" else "") + f": \"{text[:120]}\""
        self.add_clue("testimony", t.zone, None, what + ".", [p.id], holder=t.id)
        if p.saboteur:
            self.ev("lure", f"{p.first} to {t.first}: \"{text[:140]}\"", actor=p.id, zone=p.zone, public=False,
                    beat=2, target=t.id)
        if channel in ("radio", "exec", "security") and p.dept:
            self.add_clue("radio", p.zone, None, f"Radio log: {what}. No matching order from the Director.", [p.id])

    def say(self, p: Person, channel: str, to: str | None, text: str):
        if not text:
            return
        text = text[:400]
        self._say(p, channel, to, text)
        self.note_request(p, to, text, channel)

    def _say(self, p: Person, channel: str, to: str | None, text: str):
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
        if channel == "pa" and p.tier == "director":     # site-wide speakers, restrooms included
            for q in self.people.values():
                if q.id != p.id:
                    self.deliver(q.id, p.first, f"[PA] {text}", "pa", wake=(q.id == to))
            self.log.speech(self.t, p.id, "pa", text, to=to, zone=p.zone)
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
        key = channel if channel in ("exec", "security") else (p.dept or "")
        for q in self.people.values():
            if q.id != p.id and q.id not in ids and q.listening.get(key, -1) > self.t:
                self.deliver(q.id, p.first, f"[overheard on {self.channel_name(key)}] {text}", "radio")
                self._listen_noticed(q, key, chance=0.12)
        self.radio_log.append(dict(t=self.t, frm=p.id, dept=p.dept, channel=channel, text=text))
        self.log.speech(self.t, p.id, channel, text, to=to, zone=p.zone)

    # ------------------------------------------------------------------ eavesdropping and hiding
    LISTEN_S = 600

    @staticmethod
    def channel_name(key):
        return {"exec": "the exec channel", "security": "the security channel"}.get(
            key, f"the {C.DEPT_NAME.get(key, key)} radio")

    def own_channels(self, p):
        own = {p.dept} if p.dept else set()
        if p.tier in ("director", "manager"):
            own.add("exec")
        if p.dept == "SF" or p.tier == "director":
            own.add("security")
        return own

    def listen_in(self, p: Person, target: str):
        key = (target or "").strip()
        key = key.upper() if key.upper() in C.DEPT_NAME else key.lower()
        if key in ("off", "stop", "none", ""):
            p.listening = {}
            return "radio back on your own channels"
        if key not in list(C.DEPT_NAME) + ["exec", "security"]:
            return "listen_in needs a channel: RX, HY, IE, SF, exec or security"
        if key in self.own_channels(p):
            return f"you already hear {self.channel_name(key)}"
        if not F.ZONES[p.zone]["radio"]:
            return "no radio signal here"
        p.listening[key] = self.t + self.LISTEN_S
        self.listen_log.append(dict(t=self.t, who=p.id, key=key))
        self.ev("listen_in", f"{p.first} tuned in to {self.channel_name(key)}", actor=p.id, zone=p.zone,
                public=False, beat=1, channel=key)
        self._listen_noticed(p, key, chance=None)
        return f"listening to {self.channel_name(key)} for the next {self.LISTEN_S // 60} minutes"

    def _listen_noticed(self, p: Person, key: str, chance=None):
        """Doing it in public turns heads: anyone nearby may notice the chatter on the wrong channel."""
        here = [q for q in self.in_zone(p.zone, exclude=p.id) if q.activity != "restroom"]
        for q in here:
            pr = self.NOTICE_P.get(q.group, 0.5) * (0.6 if chance is None else chance * 3)
            if self.rng.random() < pr:
                p.suspicion += 2
                if p.saboteur:
                    self.sab_heat += 2
                self.add_clue("testimony", p.zone, None, f"{q.first} heard {self.channel_name(key)} chatter coming "
                              f"from {p.first}'s radio at {hhmm(self.t)}, which isn't {p.first}'s channel.",
                              [p.id], holder=q.id)
                self.deliver(q.id, "eyes", f"You notice {p.first}'s radio is playing {self.channel_name(key)}, "
                             f"not their own channel.", "see")
                self.ev("listen_noticed", f"{q.first} noticed {p.first} listening to {self.channel_name(key)}",
                        actor=q.id, zone=p.zone, beat=2, target=p.id)
                return

    def hide(self, p: Person, what: str, text: str):
        if p.activity == "moving":
            return "you can't hide anything on the move; stop somewhere first"
        badges = list(p.extra_badges) if (what or "").lower().startswith("badge") else []
        items = []
        if not badges:
            desc = (text or what or "").strip()[:120]
            if not desc:
                return "say what you hide: arg = badges, or text = what it is"
            items = [desc]
            p.carrying = [c for c in p.carrying if c.lower() not in desc.lower()]
        for b in badges:
            p.extra_badges.remove(b)
        st = dict(id=f"S{len(self.stashes) + 1}", zone=p.zone, who=p.id, t=self.t, badges=badges, items=items,
                  found=False)
        self.stashes.append(st)
        what_s = ("borrowed badges (" + ", ".join(self.people[b].first for b in badges) + ")") if badges else items[0]
        self.ev("hide", f"{p.first} hid {what_s} in the {F.ZONES[p.zone]['name']}", actor=p.id, zone=p.zone,
                public=False, beat=2, stash=st["id"])
        if F.ZONES[p.zone]["cctv"]:
            self.add_clue("cctv", p.zone, None, f"Camera in {F.ZONES[p.zone]['name']} shows {p.first} tucking "
                          f"something out of sight at {hhmm(self.t)}.", [p.id])
        for q in [q for q in self.in_zone(p.zone, exclude=p.id) if q.activity != "restroom" or p.activity == "restroom"]:
            if self.rng.random() < self.NOTICE_P.get(q.group, 0.5) * 0.6:
                self.add_clue("testimony", p.zone, None, f"{q.first} saw {p.first} hide something in the "
                              f"{F.ZONES[p.zone]['name']} around {hhmm(self.t)}.", [p.id], holder=q.id)
                self.deliver(q.id, "eyes", f"You saw {p.first} tuck something out of sight.", "see")
        return f"hidden in the {F.ZONES[p.zone]['name']}" + ("" if not F.ZONES[p.zone]["cctv"] else
                                                             " (there are cameras here)")

    def retrieve(self, p: Person):
        mine = [s for s in self.stashes if s["zone"] == p.zone and s["who"] == p.id and not s["found"]]
        if not mine:
            return "you have nothing hidden here"
        got = []
        for s in mine:
            s["found"] = True
            p.extra_badges += s["badges"]
            p.carrying += s["items"]
            got += [self.people[b].first + "'s badge" for b in s["badges"]] + s["items"]
        self.ev("retrieve", f"{p.first} took back {', '.join(got)}", actor=p.id, zone=p.zone, public=False, beat=1)
        return "you have " + ", ".join(got)

    def rummage(self, p: Person, chance=0.5, report_to=None):
        """Look around the room for anything hidden. Returns text; found stashes become physical clues."""
        hits = [s for s in self.stashes if s["zone"] == p.zone and not s["found"] and s["who"] != p.id
                and self.rng.random() < chance]
        if not hits:
            return f"nothing hidden that you could find in the {F.ZONES[p.zone]['name']}"
        out = []
        for s in hits:
            s["found"] = True
            what = ("badges belonging to " + ", ".join(self.people[b].name for b in s["badges"])) if s["badges"] \
                else s["items"][0]
            pool = self.present_during(s["zone"], s["t"] - 120, s["t"] + 120) or [s["who"]]
            if s["who"] not in pool:
                pool.append(s["who"])
            c = self.add_clue("physical", s["zone"], None, f"{p.first} found {what} hidden in the "
                              f"{F.ZONES[s['zone']]['name']} at {hhmm(self.t)}. Whoever was in there around "
                              f"{hhmm(s['t'])} could have left it.", pool, holder=p.id)
            for b in s["badges"]:   # the owner gets their badge back via security
                o = self.people[b]
                if o.lent_to:
                    o.lent_to = None
                    o.badge = b
            if report_to:
                self.reveal(c, p.id, report_to)
            out.append(what)
            self.ev("stash_found", f"{p.first} found {what} in the {F.ZONES[s['zone']]['name']}", actor=p.id,
                    zone=p.zone, beat=3, stash=s["id"])
        return "found: " + "; ".join(out)

    def locate(self, pid):
        """What CAS can tell about where someone is: cameras if they're on one, else the last door swipe."""
        t = self.people[pid]
        if F.ZONES[t.zone]["cctv"] and not (self.plant.health["security"] < 40 and self.rng.random() < 0.5):
            return (f"cameras have {t.first} in the {F.ZONES[t.zone]['name']}"
                    + (f" at the {t.station}" if t.station else "") + f" ({t.activity})", True)
        rows = [r for r in self.ledger.rows if r["badge"] == pid and r["granted"]]   # CAS sees badges, not faces
        last = rows[-1] if rows else None
        return (f"{t.first} is not on any camera. " + (
            f"Last badge swipe: {F.ZONES[last['zone']]['name']} at {hhmm(last['t'])}." if last else
            "No badge swipes on record."), False)

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
