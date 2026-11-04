"""Models and run-wide constants. Swap model IDs here only."""
MODELS = {
    "director": "claude-opus-5-5",
    "manager": "claude-sonnet-5-5",
    "staff": "claude-haiku-5-5",
    "narrator": "claude-opus-5-5",
}

SHIFT_START_CLOCK = (8, 0)      # test window opens 08:00
SHIFT_MINUTES = 240             # 4 game-hours (old spec's 60 ticks x 4 min)
BEAT_MINUTES = 4                # one physics "beat" = the sandbox's tick
PHYSICS_STEP_S = 10             # physics integrates every 10 game-seconds
FRAME_EVERY_S = 30              # telemetry frame written for replay every 30 s

SCRATCHPAD_CHARS = 250
WINDOW_EVENTS = 8               # recent local events shown to an agent each wake


def clock(t_s: float) -> str:
    h, m = SHIFT_START_CLOCK
    total = h * 3600 + m * 60 + int(t_s)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
