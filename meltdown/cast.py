"""The 30-agent roster (see docs/DESIGN.md section 4)."""

LEADERS = [
    dict(id="U4-DIR", name="Simone Hart", role="Plant Director", tier="director", dept=None, clearance="L4", zone="Z2", station="director_desk", archetype="Director"),
    dict(id="U4-MGR-RX", name="Dr. Elena Voss", role="Reactor Core & Reactivity Manager", tier="manager", dept="RX", clearance="L4", zone="Z2", station="console", archetype="Manager"),
    dict(id="U4-MGR-HY", name="Frank Delacroix", role="Hydraulics, Turbines & Steam Manager", tier="manager", dept="HY", clearance="L4", zone="Z3", station="pump_B", archetype="Manager"),
    dict(id="U4-MGR-IE", name="Dr. Mei Lin Park", role="Instrumentation, Electrical & Sensors Manager", tier="manager", dept="IE", clearance="L4", zone="Z4", station="cabinet_A", archetype="Manager"),
    dict(id="U4-MGR-SF", name="Ruth Abara", role="Nuclear Security & Facilities Manager", tier="manager", dept="SF", clearance="L4-SEC", zone="Z6", station="cas_desk", archetype="Manager"),
]

_S = [  # id, name, job, dept, clearance, zone, station, archetype, group
    ("U4-OP-01", "Maya Okafor", "Control Room Operator", "RX", "L3", "Z2", "console", "Paranoid Skeptic", "Analytical"),
    ("U4-OP-02", "Dale Hutchins", "Control Room Operator", "RX", "L3", "Z2", "console", "Weary Veteran", "Analytical"),
    ("U4-OP-03", "Priya Raman", "Control Room Operator", "RX", "L2", "Z2", "console", "Daydreamer", "Low-Effort"),
    ("U4-OP-04", "Kevin Brandt", "Control Room Operator", "RX", "L2", "Z2", "console", "Corporate Yes-Man", "Compliance"),
    ("U4-OP-05", "Lucy Tran", "Control Room Operator", "RX", "L2", "Z1", "breakroom", "Panic-Monster", "Volatile"),
    ("U4-OP-06", "Marcus Bell", "Control Room Operator", "RX", "L3", "Z2", "console", "Chaos Prankster", "Low-Effort"),
    ("U4-ME-01", "Hank Kowalski", "Balance-of-Plant Mechanic", "HY", "L3", "Z3", "pump_B", "Weary Veteran", "Analytical"),
    ("U4-ME-02", "Rosa Delgado", "Balance-of-Plant Mechanic", "HY", "L3", "Z3", "pump_B", "Hot-Head", "Volatile"),
    ("U4-ME-03", "Tim Fenwick", "Balance-of-Plant Mechanic", "HY", "L2", "Z1", "breakroom", "Bureaucratic Slacker", "Low-Effort"),
    ("U4-ME-04", "Jamal Price", "Balance-of-Plant Mechanic", "HY", "L2", "Z3", "heat_balance", "People Pleaser", "Compliance"),
    ("U4-ME-05", "Gus Lindqvist", "Balance-of-Plant Mechanic", "HY", "L2", "Z3", "pump_B", "Bureaucratic Slacker", "Low-Effort"),
    ("U4-ME-06", "Nadia Petrova", "Balance-of-Plant Mechanic", "HY", "L2", "Z3", "heat_balance", "Friendly Optimist", "Compliance"),
    ("U4-IE-01", "Ada Whitfield", "I&E Technician", "IE", "L4", "Z4", "cabinet_B", "Literal Robot", "Analytical"),
    ("U4-IE-02", "Sam Oyelaran", "I&E Technician", "IE", "L3", "Z2", "console", "Perfectionist", "Analytical"),
    ("U4-IE-03", "Chris Yamada", "I&E Technician", "IE", "L3", "Z3", "heat_balance", "People Pleaser", "Compliance"),
    ("U4-IE-04", "Brett Coyle", "I&E Technician", "IE", "L3", "Z4", "cabinet_A", "Brown-Noser", "Compliance"),
    ("U4-FC-01", "Earl Mabry", "Custodian", "SF", "L1-U", "Z8", None, "Spooky Mystic", "Volatile"),
    ("U4-FC-02", "Tina Vasquez", "Custodian", "SF", "L1-U", "Z1", "breakroom", "Bureaucratic Slacker", "Low-Effort"),
    ("U4-SEC-01", "Ray Dunham", "Checkpoint Guard", "SF", "L3-SEC", "Z1", "gate", "Paranoid Skeptic", "Analytical"),
    ("U4-SEC-02", "Benji Carter", "Checkpoint Guard", "SF", "L2-SEC", "Z2", None, "Friendly Optimist", "Compliance"),
    ("U4-SEC-03", "Doug Pruitt", "Patrol Guard", "SF", "L2-SEC", "Z3", None, "Corporate Yes-Man", "Compliance"),
    ("U4-SEC-04", "Kayla Moss", "Patrol Guard", "SF", "L2-SEC", "Z1", None, "People Pleaser", "Compliance"),
    ("U4-SEC-05", "Owen Strand", "CAS Monitor", "SF", "L3-SEC", "Z6", "cas_desk", "Quiet Quitter", "Low-Effort"),
    ("U4-SEC-06", "Leah Ingram", "CAS Monitor", "SF", "L3-SEC", "Z6", "cas_desk", "Panic-Monster", "Volatile"),
    ("U4-SEC-07", "Victor Hale", "Armory / Rover Guard", "SF", "L4-SEC", "Z6", None, "Corporate Yes-Man", "Compliance"),
]
STAFF = [dict(id=i, name=n, role=j, tier="staff", dept=d, clearance=c, zone=z, station=s, archetype=a, group=g)
         for (i, n, j, d, c, z, s, a, g) in _S]

ALL = LEADERS + STAFF

# Which pawn each possible spy leans on for a borrowed badge (a People Pleaser they can reach)
PAWN_FOR = {"RX": "U4-ME-04", "HY": "U4-ME-04", "IE": "U4-IE-03", "SF": "U4-SEC-04"}

RESTROOM_BREAKS = {"Bureaucratic Slacker": (4, 6)}   # everyone else (1, 2)


def first(name):
    return name.replace("Dr. ", "").split()[0]
