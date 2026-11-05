"""Models and run-wide constants. Swap model IDs here only."""
MODELS = {
    "director": "claude-opus-5-5",
    "manager": "claude-sonnet-5-5",
    "staff": "claude-haiku-5-5",
}
SPY_MODEL = None   # e.g. "claude-opus-5-5" via --spy-model, to give the spy a stronger brain than the other managers


def model_for(p) -> str:
    return SPY_MODEL if (SPY_MODEL and getattr(p, "saboteur", False)) else MODELS[p.tier]


EFFORT = {"director": "medium", "manager": "low", "staff": "low"}
SPY_EFFORT = "medium"   # the spy has the hardest job on site: it gets to think as hard as the Director


PERSON_EFFORT = {"U4-FC-01": "medium"}   # Earl, the veteran janitor: same Haiku model, thinks harder


def effort_for(p) -> str:
    if getattr(p, "saboteur", False):
        return SPY_EFFORT
    return PERSON_EFFORT.get(getattr(p, "id", ""), EFFORT[p.tier])
MAX_TOKENS = {"director": 4000, "manager": 3000, "staff": 1500}

SHIFT_START_CLOCK = (8, 0)      # certification window opens 08:00
SHIFT_MINUTES = 240             # four game-hours
STEP_S = 5                      # engine step (movement, plant, timers)
FRAME_EVERY_S = 15              # replay frame cadence

# how often each tier gets a turn (game seconds); events can wake an agent early
THINK_EVERY_S = {"director": 300, "manager": 240, "staff": 180}
MIN_GAP_S = 45                  # an early wake never comes sooner than this after the last turn

# Tempo presets: how often agents think. "fast"/"max" cost 2-3x the calls per game minute (for a Max plan or an
# API key), but people react to a whisper or an alarm within seconds of game time instead of a minute or more.
TEMPO = {
    "normal": dict(think={"director": 300, "manager": 240, "staff": 180}, min_gap=45, cc_concurrency=4),
    "fast": dict(think={"director": 150, "manager": 120, "staff": 90}, min_gap=25, cc_concurrency=6),
    "max": dict(think={"director": 90, "manager": 75, "staff": 60}, min_gap=15, cc_concurrency=8),
}
TEMPO_NOW = "normal"


def set_tempo(name: str):
    """Switch tempo in place (the engine and world read these at call time)."""
    global MIN_GAP_S, TEMPO_NOW
    t = TEMPO[name]
    THINK_EVERY_S.clear()
    THINK_EVERY_S.update(t["think"])
    MIN_GAP_S = t["min_gap"]
    TEMPO_NOW = name
    return t

SCRATCHPAD_CHARS = 250
INBOX_LIMIT = 8
NEARBY_EVENTS = 8

DIRECTOR_INVESTIGATIONS_PER_TURN = 2


def clock(t_s: float) -> str:
    h, m = SHIFT_START_CLOCK
    total = h * 3600 + m * 60 + int(t_s)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def hhmm(t_s: float) -> str:
    return clock(t_s)[:5]


def at(hhmm_str: str) -> int:
    """'09:30' -> game seconds since shift start."""
    h, m = map(int, hhmm_str.split(":"))
    sh, sm = SHIFT_START_CLOCK
    return (h * 60 + m - sh * 60 - sm) * 60
