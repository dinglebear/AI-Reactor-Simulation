"""The 30-agent roster: 1 Director, 4 department managers, 25 staff (see docs/GAME.md)."""

LEADERS = [
    dict(id="U4-DIR", name="Simone Hart", role="Plant Director", tier="director", dept=None, clearance="L4", zone="Z2", station="director_desk", archetype="Director", group="Leadership"),
    dict(id="U4-MGR-RX", name="Dr. Elena Voss", role="Core Systems Manager", tier="manager", dept="RX", clearance="L4", zone="Z2", station="control_console", archetype="Manager", group="Leadership"),
    dict(id="U4-MGR-HY", name="Frank Delacroix", role="Coolant & Turbine Manager", tier="manager", dept="HY", clearance="L4", zone="Z3", station="coolant_bus_b", archetype="Manager", group="Leadership"),
    dict(id="U4-MGR-IE", name="Dr. Mei Lin Park", role="Instruments Manager", tier="manager", dept="IE", clearance="L4", zone="Z4", station="primary_thermal_loop", archetype="Manager", group="Leadership"),
    dict(id="U4-MGR-SF", name="Ruth Abara", role="Security & Facilities Manager", tier="manager", dept="SF", clearance="L4-SEC", zone="Z6", station="cas_desk", archetype="Manager", group="Leadership"),
]

_S = [  # id, name, job, dept, clearance, zone, station, archetype, group
    ("U4-OP-01", "Maya Okafor", "Control Room Operator", "RX", "L3", "Z2", "control_console", "Paranoid Skeptic", "Analytical"),
    ("U4-OP-02", "Dale Hutchins", "Control Room Operator", "RX", "L3", "Z2", "control_console", "Weary Veteran", "Analytical"),
    ("U4-OP-03", "Priya Raman", "Control Room Operator", "RX", "L2", "Z2", "control_console", "Daydreamer", "Low-Effort"),
    ("U4-OP-04", "Kevin Brandt", "Control Room Operator", "RX", "L2", "Z2", "control_console", "Corporate Yes-Man", "Compliance"),
    ("U4-OP-05", "Lucy Tran", "Control Room Operator", "RX", "L2", "Z1", "breakroom", "Panic-Monster", "Volatile"),
    ("U4-OP-06", "Marcus Bell", "Control Room Operator", "RX", "L3", "Z2", "control_console", "Chaos Prankster", "Low-Effort"),
    ("U4-ME-01", "Hank Kowalski", "Balance-of-Plant Mechanic", "HY", "L3", "Z3", "coolant_bus_b", "Weary Veteran", "Analytical"),
    ("U4-ME-02", "Rosa Delgado", "Balance-of-Plant Mechanic", "HY", "L3", "Z3", "coolant_bus_a", "Hot-Head", "Volatile"),
    ("U4-ME-03", "Tim Fenwick", "Balance-of-Plant Mechanic", "HY", "L2", "Z1", "breakroom", "Bureaucratic Slacker", "Low-Effort"),
    ("U4-ME-04", "Jamal Price", "Balance-of-Plant Mechanic", "HY", "L2", "Z3", "test_bench", "People Pleaser", "Compliance"),
    ("U4-ME-05", "Gus Lindqvist", "Balance-of-Plant Mechanic", "HY", "L2", "Z3", "coolant_bus_a", "Bureaucratic Slacker", "Low-Effort"),
    ("U4-ME-06", "Nadia Petrova", "Balance-of-Plant Mechanic", "HY", "L2", "Z3", "test_bench", "Friendly Optimist", "Compliance"),
    ("U4-IE-01", "Ada Whitfield", "I&E Technician", "IE", "L4", "Z4", "display_calibration", "Literal Robot", "Analytical"),
    ("U4-IE-02", "Sam Oyelaran", "I&E Technician", "IE", "L3", "Z2", "control_console", "Perfectionist", "Analytical"),
    ("U4-IE-03", "Chris Yamada", "I&E Technician", "IE", "L3", "Z3", "test_bench", "People Pleaser", "Compliance"),
    ("U4-IE-04", "Brett Coyle", "I&E Technician", "IE", "L3", "Z4", "primary_thermal_loop", "Brown-Noser", "Compliance"),
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

BY_ID = {a["id"]: a for a in ALL}

DEPT_NAME = {"RX": "Core", "HY": "Coolant", "IE": "Instruments", "SF": "Security"}
DEPT_SYSTEM = {"RX": "core", "HY": "coolant", "IE": "instruments", "SF": "security"}
DEPT_HOME = {"RX": "primary_thermal_loop", "HY": "coolant_bus_b", "IE": "display_calibration", "SF": "cas_desk"}

# One-paragraph personalities. These go into every agent prompt and drive the mock agents.
PERSONALITY = {
    "Director": "Calm under pressure, allergic to guesswork. Wants the certification AND a clean plant, and knows corporate only cares about the first.",
    "Manager": "Runs a department of people with opinions. Juggles the test schedule, the Director's questions and their own team's gossip.",
    "Paranoid Skeptic": "Trusts nobody's numbers until they check them twice. Notices who is where and says so out loud.",
    "Weary Veteran": "Has seen every alarm this plant can throw. Slow to panic, quick to spot something that doesn't fit the pattern.",
    "Daydreamer": "Means well, drifts off. Misses things right in front of them, then remembers them hours later.",
    "Corporate Yes-Man": "Repeats whatever the boss said last. Will report a problem only if someone senior already did.",
    "Panic-Monster": "Every blip is the end of the world. Runs everywhere, escalates everything, cries wolf a lot.",
    "Chaos Prankster": "Bored and mischievous. Starts rumors for fun and hides people's coffee mugs.",
    "Hot-Head": "Short fuse, big heart. Confronts people directly and loudly when something seems off.",
    "Bureaucratic Slacker": "Long restroom breaks, longer coffee breaks. Knows every form and fills in none of them.",
    "People Pleaser": "Can't say no. Will lend you a pen, a hand, or a badge if you ask nicely.",
    "Friendly Optimist": "Sure everything is fine. Explains away anomalies with a smile.",
    "Literal Robot": "Reports exactly what the instruments say, every time, in full. No tact, no filter, no exceptions.",
    "Perfectionist": "Cannot let a number that's slightly off go. Will chase a small discrepancy until it's explained.",
    "Brown-Noser": "Flatters whoever has power and reports colleagues for points.",
    "Spooky Mystic": "Talks about 'bad energy' in the vault. Weirdly often right about where trouble is.",
    "Quiet Quitter": "Does the minimum. Dismisses alarms as glitches unless one becomes impossible to ignore.",
}

# how long restroom visits last (game seconds) and how fast the need builds (points per minute)
RESTROOM_STAY = {"Bureaucratic Slacker": (240, 420), "Quiet Quitter": (180, 300)}   # default (60, 150)
BLADDER_RATE = {"Bureaucratic Slacker": 1.6}                                          # default 0.9

DEPT_COLOR = {"RX": "#e8a33d", "HY": "#3d9be8", "IE": "#9a6ce8", "SF": "#4fb87a", None: "#e05561"}


def first(name):
    return name.replace("Dr. ", "").split()[0]


# ---------------------------------------------------------------- what people want, and what they think of each other
# The four managers get their own personas (the spy is one of them at random, so none of these give it away).
PERSONA = {
    "U4-MGR-RX": "Brilliant, impatient and ambitious. Talks fast, hates being second-guessed, and has a reputation for "
                 "getting results.",
    "U4-MGR-HY": "Old-school and warm. Knows every mechanic's kids' names, tells long stories, and hates paperwork.",
    "U4-MGR-IE": "Meticulous and soft-spoken. Will stop anything that doesn't add up, and rarely raises her voice.",
    "U4-MGR-SF": "Dry humour, steady nerves, fiercely protective of her people. Twenty years on site, trusted by everyone.",
}

# Corporate's bonus is the money on the table today (see GAME_RULES). tag is for the analysis; text goes in the prompt.
MOTIVE_TEXT = {
    "money": "You want the certification bonus badly. You'd rather push through a scare than lose the payout.",
    "safety": "Safety first. You'd give up the bonus without a second thought if something looked wrong.",
    "career": "This test is your shot at a promotion. You want to be seen as the one who got Unit 4 through it.",
    "team": "You care most about your crew. Nobody on your team gets hurt or blamed on your watch.",
    "home": "You just want the shift to end so you can go home. Drama is the enemy.",
    "prove": "People underestimate you. Today you want to prove you're good at this.",
    "truth": "You want to know what's really going on, even if the answer is awkward for everyone.",
}
MOTIVE = {
    "U4-DIR": ("safety", "You want the pass, but not at any price. Corporate wants the bonus headline; you want everyone home."),
    "U4-MGR-RX": ("career", "Corporate has hinted you're next in line for Director if this test passes."),
    "U4-MGR-HY": ("money", "The bonus would cover your daughter's first year of college. You've already told her."),
    "U4-MGR-IE": ("safety", "You'd rather fail the test than sign off numbers you don't believe."),
    "U4-MGR-SF": ("team", "Your guards and custodians come first. You've fought corporate for them before."),
    "U4-OP-01": ("truth", None), "U4-OP-02": ("safety", None), "U4-OP-03": ("home", None),
    "U4-OP-04": ("money", None), "U4-OP-05": ("safety", None), "U4-OP-06": ("home", None),
    "U4-ME-01": ("safety", None), "U4-ME-02": ("money", "Rent went up again and the bonus is the only way you catch up."),
    "U4-ME-03": ("home", None), "U4-ME-04": ("team", None), "U4-ME-05": ("money", None),
    "U4-ME-06": ("money", None), "U4-IE-01": ("truth", None), "U4-IE-02": ("safety", None),
    "U4-IE-03": ("team", None), "U4-IE-04": ("career", None), "U4-FC-01": ("truth", None),
    "U4-FC-02": ("home", None), "U4-SEC-01": ("safety", None), "U4-SEC-02": ("prove", None),
    "U4-SEC-03": ("money", None), "U4-SEC-04": ("prove", None), "U4-SEC-05": ("money", "You're quitting next month. "
                 "The bonus is your going-away present to yourself."),
    "U4-SEC-06": ("safety", None), "U4-SEC-07": ("career", None),
}


def motive(pid):
    tag, extra = MOTIVE[pid]
    return tag, (extra + " " if extra else "") + MOTIVE_TEXT[tag]


# How most people on site see someone, by archetype (managers and the Director by persona).
REPUTATION_BY_ARCHETYPE = {
    "Paranoid Skeptic": "sharp but exhausting; questions everything", "Weary Veteran": "solid and dependable, a bit grumpy",
    "Daydreamer": "sweet, but don't count on them to notice anything", "Corporate Yes-Man": "a yes-man; agrees with whoever spoke last",
    "Panic-Monster": "cries wolf; lovely, but you take their alarms with salt", "Chaos Prankster": "funny, but you can't believe half of what they say",
    "Hot-Head": "rude and loud, but honest to a fault", "Bureaucratic Slacker": "lazy; never where they should be",
    "People Pleaser": "very kind; would do anything you ask", "Friendly Optimist": "very kind; thinks everything is fine",
    "Literal Robot": "blunt to the point of rude, but always accurate", "Perfectionist": "nitpicky, but catches what others miss",
    "Brown-Noser": "a suck-up who reports colleagues to look good", "Spooky Mystic": "odd; talks about 'bad energy', weirdly often right",
    "Quiet Quitter": "checked out; does the minimum",
}
REPUTATION = {
    "U4-DIR": "fair and calm; hard to fool", "U4-MGR-RX": "brilliant but arrogant; steamrolls people",
    "U4-MGR-HY": "everyone's favourite uncle; a bit disorganised", "U4-MGR-IE": "kind and careful; slow to decide",
    "U4-MGR-SF": "trusted completely; the steadiest person on site",
}
YES_PEOPLE = ("Corporate Yes-Man", "People Pleaser", "Brown-Noser")

# Personal history between two people, used for a share of opinions so not everyone thinks the same.
TWISTS = [
    ("warm", "you think they're one of the kindest people here"), ("warm", "they covered for you once; you owe them"),
    ("warm", "you have lunch together most days"), ("warm", "they're secretly the smartest person in the room"),
    ("cold", "they were rude to you in a meeting last month and never apologised"),
    ("cold", "they took credit for your work once"), ("cold", "you think they're two-faced"),
    ("cold", "you find them arrogant"), ("neutral", "you barely know them"),
    ("neutral", "they talk a lot; you tune out"),
]


def reputation(pid):
    a = BY_ID[pid]
    return REPUTATION.get(pid) or REPUTATION_BY_ARCHETYPE[a["archetype"]]


def opinions(seed: int) -> dict:
    """{holder: {other: (feeling, text)}}. Mostly the person's reputation, sometimes a personal history.
    Each person knows their department, their manager, the Director and the other managers, plus a few others."""
    import random
    rng = random.Random(seed * 7919 + 17)        # separate stream, so it never shifts the game's own randomness
    out = {}
    for a in ALL:
        known = [b["id"] for b in ALL if b["id"] != a["id"] and
                 (b["tier"] != "staff" or (a["dept"] and b["dept"] == a["dept"]) or a["tier"] == "director")]
        others = [b["id"] for b in ALL if b["id"] != a["id"] and b["id"] not in known]
        known += rng.sample(others, min(3, len(others)))
        mine = {}
        for b in known:
            if rng.random() < 0.3:
                mine[b] = rng.choice(TWISTS)
            else:
                rep = reputation(b)
                feel = ("warm" if any(w in rep for w in ("kind", "dependable", "trusted", "favourite", "fair", "honest"))
                        else "cold" if any(w in rep for w in ("rude", "lazy", "suck-up", "arrogant", "yes-man"))
                        else "neutral")
                mine[b] = (feel, rep)
        out[a["id"]] = mine
    return out
