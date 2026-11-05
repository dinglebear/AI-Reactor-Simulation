"""Zones, doors, stations, badge readers and the badge ledger. Coordinates (px) feed the replay viewer."""
from __future__ import annotations
import heapq
import math
import zlib

M_PER_PX = 0.3
SPEEDS = {"stroll": 0.8, "walk": 1.4, "run": 4.2}   # metres per game second
SWIPE_S = 4
AIRLOCK_S = 30                          # Z4 interlock cycle
HIGH_ALERT_CHECK_S = 20                 # guard cross-check per guarded door in High Alert

MAP_W, MAP_H = 1640, 940

ZONES = {
    # top row: the secure side of the plant
    "Z6": dict(name="Central Alarm Station", rect=(40, 40, 280, 240), reader="SEC", cctv=True, radio=True),
    "Z2": dict(name="Master Control Room", rect=(340, 40, 440, 240), reader="L2", cctv=True, radio=True),
    "Z4": dict(name="Reactor Hall Airlock", rect=(800, 40, 340, 240), reader="L3", cctv=True, radio=True),
    "Z5": dict(name="Override Vault", rect=(1160, 40, 260, 240), reader="L4", cctv=True, radio=True),
    "Z12": dict(name="Records Office", rect=(1440, 40, 160, 240), reader="L2", cctv=True, radio=True),
    # corridors
    "H1": dict(name="Main Corridor", rect=(40, 300, 1560, 60), reader=None, cctv=True, radio=True, hall=True),
    "H4": dict(name="Center Stairwell", rect=(680, 360, 60, 280), reader=None, cctv=False, radio=True, hall=True),
    "H3": dict(name="East Link", rect=(1520, 360, 80, 280), reader=None, cctv=True, radio=True, hall=True),
    "H2": dict(name="Service Corridor", rect=(40, 640, 1560, 60), reader=None, cctv=True, radio=True, hall=True),
    # middle row
    "Z1": dict(name="Admin & Lobby", rect=(40, 380, 300, 240), reader="L1", cctv=True, radio=True),
    "Z9": dict(name="Breakroom & Canteen", rect=(360, 380, 300, 240), reader="L1", cctv=True, radio=True),
    "Z7N": dict(name="Restroom North", rect=(760, 380, 140, 110), reader=None, cctv=False, radio=True),
    "Z10": dict(name="Locker Room", rect=(760, 510, 140, 110), reader="L1", cctv=False, radio=True),
    "Z3": dict(name="Turbine & Pump Bay", rect=(920, 380, 420, 240), reader="L2", cctv=True, radio=True),
    "Z8": dict(name="Janitor Closet", rect=(1360, 380, 140, 110), reader="L1-U", cctv=True, radio=True),
    "Z11": dict(name="Storage", rect=(1360, 510, 140, 110), reader="L1", cctv=True, radio=True),
    # bottom row
    "Z7S": dict(name="Restroom South", rect=(40, 720, 180, 180), reader=None, cctv=False, radio=True),
    "Z14": dict(name="Training Room", rect=(240, 720, 320, 180), reader="L1", cctv=True, radio=True),
    "Z15": dict(name="Loading Dock", rect=(580, 720, 440, 180), reader="L1", cctv=True, radio=True),
    "Z7E": dict(name="Restroom East", rect=(1040, 720, 180, 180), reader=None, cctv=False, radio=True),
    "Z16": dict(name="Smoking Courtyard", rect=(1240, 720, 360, 180), reader=None, cctv=True, radio=True),
}
RESTROOMS = ("Z7N", "Z7S", "Z7E")
SINKS = {"Z7N": "sinks_N", "Z7S": "sinks_S", "Z7E": "sinks_E"}
HALLS = tuple(z for z, d in ZONES.items() if d.get("hall"))

DOORS = {
    ("Z6", "Z2"): (330, 160), ("Z2", "Z4"): (790, 160), ("Z4", "Z5"): (1150, 160),
    ("Z6", "H1"): (180, 290), ("Z2", "H1"): (560, 290), ("Z4", "H1"): (970, 290), ("Z12", "H1"): (1520, 290),
    ("Z1", "H1"): (190, 370), ("Z9", "H1"): (510, 370), ("H4", "H1"): (710, 360), ("Z3", "H1"): (1130, 370),
    ("Z8", "H1"): (1430, 370), ("H3", "H1"): (1560, 360),
    ("Z7N", "H4"): (750, 435), ("Z10", "H4"): (750, 565), ("Z11", "H3"): (1510, 565), ("Z3", "Z8"): (1350, 435),
    ("Z1", "Z9"): (350, 500),
    ("Z1", "H2"): (190, 630), ("Z9", "H2"): (510, 630), ("H4", "H2"): (710, 640), ("Z3", "H2"): (1130, 630),
    ("H3", "H2"): (1560, 640),
    ("Z7S", "H2"): (130, 710), ("Z14", "H2"): (400, 710), ("Z15", "H2"): (800, 710), ("Z7E", "H2"): (1130, 710),
    ("Z16", "H2"): (1420, 710),
}
GUARDED = {"Z2", "Z4", "Z5", "Z6"}

# Work spots. `system` = which plant system staff keep healthy by working here (see plant.py).
# Stations with SETTINGS can be changed with the `interact` verb. All labels are fictional.
STATIONS = {
    "control_console": dict(zone="Z2", xy=(600, 190), system="output", label="Unit Output Desk"),
    "director_desk": dict(zone="Z2", xy=(420, 100), system=None, label="Director's Desk"),
    "primary_thermal_loop": dict(zone="Z4", xy=(880, 120), system="core", label="Primary Thermal Loop"),
    "display_calibration": dict(zone="Z4", xy=(1070, 230), system="instruments", label="Display Calibration Rack"),
    "stabilizer_override": dict(zone="Z5", xy=(1230, 120), system="core", label="Stabilizer Override Console"),
    "backup_rack": dict(zone="Z5", xy=(1360, 230), system="instruments", label="Backup Instrument Rack"),
    "coolant_bus_a": dict(zone="Z3", xy=(1050, 560), system="coolant", label="Coolant Bus A"),
    "coolant_bus_b": dict(zone="Z3", xy=(1250, 560), system="coolant", label="Coolant Bus B"),
    "test_bench": dict(zone="Z3", xy=(990, 440), system="coolant", label="Cross-check Test Bench"),
    "ventilation_shunt": dict(zone="Z8", xy=(1440, 450), system=None, label="Ventilation Shunt"),
    "cas_desk": dict(zone="Z6", xy=(170, 150), system="security", label="Alarm Station Desk"),
    "gate": dict(zone="Z1", xy=(90, 520), system="security", label="Main Gate"),
    "breakroom": dict(zone="Z9", xy=(510, 500), system=None, label="Breakroom"),
    "supply_locker": dict(zone="Z11", xy=(1430, 575), system=None, label="Supply Locker"),
    "sinks_N": dict(zone="Z7N", xy=(830, 440), system=None, label="Restroom North"),
    "sinks_S": dict(zone="Z7S", xy=(130, 820), system=None, label="Restroom South"),
    "sinks_E": dict(zone="Z7E", xy=(1130, 820), system=None, label="Restroom East"),
    # filler places: somewhere to be, nothing to change
    "lockers": dict(zone="Z10", xy=(830, 570), system=None, label="Lockers"),
    "records_desk": dict(zone="Z12", xy=(1520, 160), system=None, label="Records Desk"),
    "training_room": dict(zone="Z14", xy=(400, 810), system=None, label="Training Room"),
    "loading_dock": dict(zone="Z15", xy=(800, 810), system=None, label="Loading Dock"),
    "courtyard": dict(zone="Z16", xy=(1420, 810), system=None, label="Smoking Courtyard"),
    "admin_office": dict(zone="Z1", xy=(250, 450), system=None, label="Admin Office"),
    # corridor patrol points
    "hall_west": dict(zone="H1", xy=(300, 330), system=None, label="Main Corridor (west)"),
    "hall_east": dict(zone="H1", xy=(1300, 330), system=None, label="Main Corridor (east)"),
    "service_west": dict(zone="H2", xy=(300, 670), system=None, label="Service Corridor (west)"),
    "service_east": dict(zone="H2", xy=(1300, 670), system=None, label="Service Corridor (east)"),
    "stairwell": dict(zone="H4", xy=(710, 500), system=None, label="Center Stairwell"),
}
PATROL = ["hall_west", "admin_office", "service_west", "loading_dock", "stairwell", "hall_east", "service_east",
          "courtyard", "hall_west"]

# Fictional controls. Each moves abstract game meters only (plant.py); none model real equipment.
SETTINGS = {
    "coolant_bus_a": dict(options=["nominal", "reduced", "standby"], nominal="nominal",
                          effect="reduced/standby: the coolant system removes less heat"),
    "coolant_bus_b": dict(options=["nominal", "reduced", "standby"], nominal="nominal",
                          effect="reduced/standby: the coolant system removes less heat"),
    "primary_thermal_loop": dict(options=["nominal", "boost"], nominal="nominal",
                                 effect="boost: extra heat load on the unit"),
    "stabilizer_override": dict(options=["auto", "manual", "off"], nominal="auto",
                                effect="manual/off: stability stops recovering and drains"),
    "ventilation_shunt": dict(options=["open", "closed"], nominal="open", effect="closed: heat runs higher"),
    "display_calibration": dict(options=["nominal", "offset"], nominal="nominal",
                                effect="offset: the control room console shows calmer numbers than the truth"),
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


ROOM_TRANSIT_PX = 180     # cutting through someone else's room costs this much extra, so people use corridors


def route(a, b, clearances=None):
    """Shortest zone route by door-to-door pixel distance (Dijkstra). With `clearances`, avoid rooms none of
    those badges open (the destination is always allowed, so a locked target still gets a route to its door)."""
    if clearances:
        ok = lambda z: z == b or ZONES[z]["reader"] is None or any(can_open(c, z) for c in clearances)
        r = _route(a, b, ok)
        return r or _route(a, b, lambda z: True)
    return _route(a, b, lambda z: True)


def _route(a, b, ok):
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
            if n not in seen and ok(n):
                extra = ROOM_TRANSIT_PX if (n != b and not ZONES[n].get("hall")) else 0
                heapq.heappush(pq, (d + math.dist(here, door(z, n)) + extra, n, r + [n]))
    return None


def door_rule(zone: str) -> str:
    need = ZONES[zone]["reader"]
    return {None: "no reader", "SEC": "security badges and L4 only", "L1-U": "custodians and L4 only"}.get(
        need, f"{need} or higher")


def reachable(clearances, zone: str) -> bool:
    return any(can_open(c, zone) for c in clearances)


def can_open(clearance: str, zone: str) -> bool:
    """Badge levels: L1, L1-U (custodian universal), L2, L3, L4, with optional -SEC suffix."""
    need = ZONES[zone]["reader"]
    if need is None or clearance == "KEY":      # KEY = a physical skeleton key: opens any door, no swipe
        return True
    sec = clearance.endswith("-SEC")
    lvl = clearance.replace("-SEC", "")
    if need == "SEC":
        return sec or lvl == "L4"
    if need == "L1-U":
        return lvl in ("L1-U", "L4")
    if lvl == "L1-U":
        return RANK[need] <= 1 or zone in ("Z2", "Z3")
    return RANK.get(lvl, 0) >= RANK[need]


def jitter(xy, seed, r=24):
    """Stable small offset so people at the same station don't overlap."""
    h = zlib.crc32(seed.encode())
    a = (h % 360) * math.pi / 180
    d = 10 + (h >> 9) % r
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
