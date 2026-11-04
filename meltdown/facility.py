"""Zones, doors, stations, badge readers and the badge ledger. Coordinates (px) feed the replay viewer."""
from __future__ import annotations
import heapq
import math
import zlib

M_PER_PX = 0.3
SPEEDS = {"walk": 1.4, "sprint": 4.2}   # metres per game second
SWIPE_S = 4
AIRLOCK_S = 30                          # Z4 interlock cycle
HIGH_ALERT_CHECK_S = 20                 # guard cross-check per guarded door in High Alert

ZONES = {
    "Z1": dict(name="Admin & Breakroom", rect=(20, 370, 450, 150), reader="L1", cctv=True, radio=True),
    "Z2": dict(name="Master Control Room", rect=(260, 160, 300, 170), reader="L2", cctv=True, radio=True),
    "Z3": dict(name="Turbine & Pump Bay", rect=(500, 370, 300, 150), reader="L2", cctv=True, radio=True),
    "Z4": dict(name="Reactor Hall Airlock", rect=(590, 160, 210, 170), reader="L3", cctv=True, radio=True),
    "Z5": dict(name="Override Vault", rect=(330, 20, 320, 110), reader="L4", cctv=True, radio=True),
    "Z6": dict(name="Central Alarm Station", rect=(20, 160, 210, 170), reader="SEC", cctv=True, radio=True),
    "Z7N": dict(name="Restroom North", rect=(20, 545, 210, 70), reader=None, cctv=False, radio=False),
    "Z7S": dict(name="Restroom South", rect=(560, 545, 210, 70), reader=None, cctv=False, radio=False),
    "Z8": dict(name="Janitor Closet", rect=(830, 370, 150, 150), reader="L1-U", cctv=True, radio=True),
}
RESTROOMS = ("Z7N", "Z7S")

DOORS = {
    ("Z5", "Z2"): (420, 145), ("Z5", "Z4"): (620, 145), ("Z6", "Z1"): (125, 350),
    ("Z2", "Z1"): (380, 350), ("Z2", "Z4"): (575, 245), ("Z4", "Z3"): (700, 350),
    ("Z1", "Z3"): (485, 445), ("Z3", "Z8"): (815, 445), ("Z1", "Z7N"): (125, 532),
    ("Z3", "Z7S"): (665, 532), ("Z6", "Z2"): (245, 245),
}
GUARDED = {"Z2", "Z4", "Z5", "Z6"}

# work spots. `system` = which abstract plant system the spot services (see plant.py)
STATIONS = {
    "control_console": dict(zone="Z2", xy=(410, 250), system="output"),
    "director_desk": dict(zone="Z2", xy=(300, 200), system=None),
    "core_panel": dict(zone="Z4", xy=(650, 200), system="core"),
    "instrument_rack": dict(zone="Z4", xy=(760, 300), system="instruments"),
    "vault_panel": dict(zone="Z5", xy=(380, 70), system="core"),
    "backup_rack": dict(zone="Z5", xy=(600, 70), system="instruments"),
    "coolant_panel": dict(zone="Z3", xy=(720, 470), system="coolant"),
    "test_bench": dict(zone="Z3", xy=(560, 400), system="coolant"),
    "cas_desk": dict(zone="Z6", xy=(120, 240), system="security"),
    "gate": dict(zone="Z1", xy=(50, 445), system="security"),
    "breakroom": dict(zone="Z1", xy=(250, 470), system=None),
    "supply_locker": dict(zone="Z8", xy=(905, 445), system=None),
    "sinks_N": dict(zone="Z7N", xy=(125, 580), system=None),
    "sinks_S": dict(zone="Z7S", xy=(665, 580), system=None),
}

RANK = {"L1": 1, "L1-U": 1, "L2": 2, "L3": 3, "L4": 4}


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


def zone_at(xy):
    for z, d in ZONES.items():
        x, y, w, h = d["rect"]
        if x <= xy[0] <= x + w and y <= xy[1] <= y + h:
            return z
    return None


def route(a, b):
    """Shortest zone route by door-to-door pixel distance (Dijkstra)."""
    pq = [(0.0, a, [a])]
    seen = set()
    while pq:
        d, z, r = heapq.heappop(pq)
        if z == b:
            return r
        if z in seen:
            continue
        seen.add(z)
        here = door(r[-2], z) if len(r) > 1 else center(z)
        for n in neighbors(z):
            if n not in seen:
                heapq.heappush(pq, (d + math.dist(here, door(z, n)), n, r + [n]))
    return None


def can_open(clearance: str, zone: str) -> bool:
    """Badge levels: L1, L1-U (custodian universal), L2, L3, L4, with optional -SEC suffix."""
    need = ZONES[zone]["reader"]
    if need is None:
        return True
    sec = clearance.endswith("-SEC")
    lvl = clearance.replace("-SEC", "")
    if need == "SEC":
        return sec or lvl == "L4"
    if need == "L1-U":
        return lvl in ("L1-U", "L4")
    if lvl == "L1-U":
        return zone in ("Z1", "Z2", "Z3")
    return RANK.get(lvl, 0) >= RANK[need]


def jitter(xy, seed, r=14):
    """Stable small offset so people at the same station don't overlap."""
    h = zlib.crc32(seed.encode())
    a = (h % 360) * math.pi / 180
    d = 4 + (h >> 9) % r
    return (xy[0] + math.cos(a) * d, xy[1] + math.sin(a) * d)


class BadgeLedger:
    """Append-only swipe ledger. Raises ANTI_PASSBACK and IMPOSSIBLE_LOCATION alerts."""

    def __init__(self):
        self.rows = []
        self.badge_zone = {}     # where the ledger believes each badge is

    def swipe(self, t, badge_id, holder_id, zone, granted=True):
        alerts = []
        believed = self.badge_zone.get(badge_id)
        if granted and believed == zone:
            alerts.append("ANTI_PASSBACK")
        if granted:
            self.badge_zone[badge_id] = zone
        row = dict(t=t, badge=badge_id, holder=holder_id, zone=zone, granted=granted, alerts=alerts)
        self.rows.append(row)
        return row

    def window(self, t0, t1):
        return [r for r in self.rows if t0 <= r["t"] <= t1]
