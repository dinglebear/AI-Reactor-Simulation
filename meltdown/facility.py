"""Zones, doors, badge readers, CCTV and the badge ledger. Coordinates feed the Replay Viewer."""
from __future__ import annotations
import heapq
import math

M_PER_PX = 0.3
SPEEDS = {"walk": 1.3, "hurry": 2.1, "sprint": 4.6}   # m/s
SWIPE_S = 6
AIRLOCK_S = 45          # Z4 interlock cycle
HIGH_ALERT_CHECK_S = 25  # guard cross-check per guarded door

ZONES = {
    "Z1": dict(name="Admin & Breakroom", rect=(20, 370, 450, 150), reader="L1", cctv=True, radio=True),
    "Z2": dict(name="Master Control Room", rect=(260, 160, 300, 170), reader="L2", cctv=True, radio=True),
    "Z3": dict(name="Turbine & Pump Bay", rect=(500, 370, 300, 150), reader="L2", cctv=True, radio=True),
    "Z4": dict(name="Reactor Hall Airlock", rect=(590, 160, 210, 170), reader="L3", cctv=True, radio=True),
    "Z5": dict(name="Manual Safety Override Vault", rect=(330, 20, 320, 110), reader="L4", cctv=True, radio=True),
    "Z6": dict(name="Central Alarm Station", rect=(20, 160, 210, 170), reader="L3-SEC", cctv=True, radio=True),
    "Z7N": dict(name="Restroom North", rect=(20, 545, 210, 70), reader=None, cctv=False, radio=False),
    "Z7S": dict(name="Restroom South", rect=(560, 545, 210, 70), reader=None, cctv=False, radio=False),
    "Z8": dict(name="Janitor Closet / Maintenance Locker", rect=(830, 370, 150, 150), reader="L1-U", cctv=True, radio=True),
}
# door point on the shared wall; the reader guards entry into the *second* zone listed in READER_SIDE
DOORS = {
    ("Z5", "Z2"): (420, 145), ("Z5", "Z4"): (620, 145), ("Z6", "Z1"): (125, 350),
    ("Z2", "Z1"): (380, 350), ("Z2", "Z4"): (575, 245), ("Z4", "Z3"): (700, 350),
    ("Z1", "Z3"): (485, 445), ("Z3", "Z8"): (815, 445), ("Z1", "Z7N"): (125, 532),
    ("Z3", "Z7S"): (665, 532),
}
GUARDED = {"Z2", "Z4", "Z5", "Z6"}   # doors a checkpoint guard watches in High Alert

STATIONS = {  # named work spots inside zones, for the viewer and for actions
    "console": ("Z2", (410, 250)), "director_desk": ("Z2", (300, 200)),
    "cabinet_A": ("Z4", (650, 200)), "cabinet_B": ("Z4", (760, 300)), "cabinet_C": ("Z5", (600, 60)),
    "loto_lockbox": ("Z5", (370, 60)), "pump_B": ("Z3", (720, 470)), "heat_balance": ("Z3", (560, 400)),
    "cas_desk": ("Z6", (120, 240)), "gate": ("Z1", (50, 445)), "breakroom": ("Z1", (250, 470)),
}

CLEARANCE_RANK = {"L1": 1, "L1-U": 1, "L2": 2, "L3": 3, "L4": 4}


def neighbors(z):
    for (a, b) in DOORS:
        if a == z:
            yield b
        elif b == z:
            yield a


def door(a, b):
    return DOORS.get((a, b)) or DOORS.get((b, a))


def center(z):
    x, y, w, h = ZONES[z]["rect"]
    return (x + w / 2, y + h / 2)


def path(a, b):
    """Dijkstra over zone graph using door-to-door pixel distance."""
    pq = [(0.0, a, [a])]
    seen = set()
    while pq:
        d, z, route = heapq.heappop(pq)
        if z == b:
            return route
        if z in seen:
            continue
        seen.add(z)
        here = door(route[-2], z) if len(route) > 1 else center(z)
        for n in neighbors(z):
            if n not in seen:
                dd = math.dist(here, door(z, n))
                heapq.heappush(pq, (d + dd, n, route + [n]))
    return None


def can_open(badge_level: str, zone: str) -> bool:
    need = ZONES[zone]["reader"]
    if need is None:
        return True
    if need == "L1-U":
        return badge_level in ("L1-U", "L4")
    if need == "L3-SEC":
        return badge_level.endswith("SEC") or badge_level == "L4"
    lvl = badge_level.replace("-SEC", "")
    if badge_level == "L1-U":
        return zone in ("Z1", "Z2", "Z3")
    return CLEARANCE_RANK.get(lvl, 0) >= CLEARANCE_RANK[need]


def leg_seconds(route, speed, high_alert=False):
    """Total travel seconds and per-door timing along a zone route."""
    pts = [center(route[0])] + [door(route[i], route[i + 1]) for i in range(len(route) - 1)] + [center(route[-1])]
    dist_px = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    secs = dist_px * M_PER_PX / SPEEDS[speed]
    for z in route[1:]:
        if ZONES[z]["reader"]:
            secs += SWIPE_S
        if z == "Z4" or route[0] == "Z4":
            secs += AIRLOCK_S / 2
        if high_alert and z in GUARDED:
            secs += HIGH_ALERT_CHECK_S
    return secs, pts[1:-1]


class BadgeLedger:
    """Append-only swipe ledger that raises anti-passback and impossible-location alerts."""

    def __init__(self):
        self.rows = []
        self.badge_zone = {}     # where the ledger believes each badge is

    def swipe(self, t, badge_id, holder_id, zone, kind="door"):
        alerts = []
        believed = self.badge_zone.get(badge_id)
        if kind == "door":
            if believed == zone:
                alerts.append("ANTI_PASSBACK")
            self.badge_zone[badge_id] = zone
        elif kind == "tap" and believed is not None and believed != zone:
            alerts.append("IMPOSSIBLE_LOCATION")
        row = dict(t=t, badge=badge_id, holder=holder_id, zone=zone, kind=kind, alerts=alerts,
                   believed_zone=believed)
        self.rows.append(row)
        return row
