"""Models and run-wide constants. Swap model IDs here only."""
MODELS = {
    "director": "claude-opus-5-5",
    "manager": "claude-sonnet-5-5",
    "staff": "claude-haiku-5-5",
}
EFFORT = {"director": "medium", "manager": "low", "staff": "low"}
MAX_TOKENS = {"director": 4000, "manager": 3000, "staff": 1500}

SHIFT_START_CLOCK = (8, 0)      # certification window opens 08:00
SHIFT_MINUTES = 240             # four game-hours
STEP_S = 5                      # engine step (movement, plant, timers)
FRAME_EVERY_S = 15              # replay frame cadence

# how often each tier gets a turn (game seconds); events can wake an agent early
THINK_EVERY_S = {"director": 300, "manager": 240, "staff": 180}
MIN_GAP_S = 45                  # an early wake never comes sooner than this after the last turn

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
