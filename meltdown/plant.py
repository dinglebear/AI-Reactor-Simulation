"""Abstract, game-tuned plant model. Not a physics simulation.

Everything is a 0-100 meter. Four systems wear down and are kept up by staff working at stations.
Fictional station settings (facility.SETTINGS) change how the meters move; off-nominal settings push the
MELTDOWN meter up, and at 100 the game ends. The control room only sees the *shown* values, which the
Display Calibration Rack can skew.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .config import at
from .facility import SETTINGS

MASK = {"heat": -15, "stability": 15, "incident": -20}   # console skew while display_calibration = offset
BUS = {"nominal": 1.0, "reduced": 0.6, "standby": 0.25}

SYSTEMS = ("core", "coolant", "instruments", "security")
WEAR_PER_MIN = {"core": 0.25, "coolant": 0.35, "instruments": 0.2, "security": 0.15}
REPAIR_PER_MIN = 1.0          # one worker at a matching station
MELTDOWN_LIMIT = 100.0
# Crisis tuning (game numbers): past CRISIS_AT the meter snowballs; each responder pulls it back, the spy's "help" adds.
CRISIS_AT = 40.0
CASCADE = 0.15            # extra meter per minute for every point above CRISIS_AT
RESPOND_PER_MIN = 0.7    # each person working crisis response
SPOIL_PER_MIN = 1.6       # the spy "helping"
RESPONSE_CAP = 3          # responders per station that count

# Corporate certification test. Targets are console output %.
STAGES = [
    dict(n=1, name="Output ramp", start=at("08:30"), end=at("09:15"), target=105, load=0,
         rule="shown output >= 100 for 30 of 45 min"),
    dict(n=2, name="Cooling challenge", start=at("09:45"), end=at("10:45"), target=90, load=25,
         rule="shown output >= 85 with the extra heat load for 45 of 60 min"),
    dict(n=3, name="Steady sign-off", start=at("11:15"), end=at("12:00"), target=95, load=0,
         rule="shown heat < 70 and shown stability > 60 for the last 30 min"),
]
NEED_MIN = {1: 30, 2: 45, 3: 29.5}


def stage_at(t):
    for s in STAGES:
        if s["start"] <= t < s["end"]:
            return s
    return None


@dataclass
class Plant:
    output: float = 100.0
    target: float = 100.0
    heat: float = 48.0
    stability: float = 90.0
    incident: float = 0.0
    health: dict = field(default_factory=lambda: {s: 90.0 for s in SYSTEMS})
    settings: dict = field(default_factory=lambda: {k: v["nominal"] for k, v in SETTINGS.items()})
    scrammed: bool = False
    status: str = "RUNNING"       # RUNNING | MELTDOWN | SCRAM
    stage_minutes: dict = field(default_factory=lambda: {1: 0.0, 2: 0.0, 3: 0.0})
    in_crisis: bool = False
    peak: float = 0.0

    def step(self, t: float, dt: float, crew_at: dict, response: tuple = (0, 0)):
        """crew_at: system -> number of workers currently maintaining it.
        response: (helpers, spoilers) working crisis response right now. Game numbers only."""
        if self.status != "RUNNING":
            return
        m = dt / 60.0
        st = stage_at(t)
        load = st["load"] if st else 0
        for s in SYSTEMS:
            self.health[s] += (-WEAR_PER_MIN[s] + REPAIR_PER_MIN * min(2, crew_at.get(s, 0))) * m
            self.health[s] = max(0.0, min(100.0, self.health[s]))
        h = self.health
        if self.scrammed:
            self.target = 0
        # output chases target; a weak core makes it sluggish and jittery
        gain = 0.08 + 0.12 * h["core"] / 100
        self.output += (self.target - self.output) * min(1.0, gain * m * 6)
        # heat: produced by output and the stage's extra load, removed by coolant
        se = self.settings
        bus = (BUS[se["coolant_bus_a"]] + BUS[se["coolant_bus_b"]]) / 2
        load += 22 if se["primary_thermal_loop"] == "boost" else 0
        load += 12 if se["ventilation_shunt"] == "closed" else 0
        heat_target = 30 + self.output * 0.5 + load * 0.9 - 35 * h["coolant"] / 100 * bus
        self.heat += (heat_target - self.heat) * min(1.0, m / 6)
        self.heat = max(10.0, min(100.0, self.heat))
        # stability falls with heat and weak core/instruments
        st_target = 100 - max(0, self.heat - 55) * 1.2 - (100 - h["core"]) * 0.35 - (100 - h["instruments"]) * 0.2
        st_target -= {"auto": 0, "manual": 25, "off": 55}[se["stabilizer_override"]]
        self.stability += (st_target - self.stability) * min(1.0, 0.15 * m * 6)
        self.stability = max(0.0, min(100.0, self.stability))
        # incident meter: driven by danger zones, slowly calms when the plant is healthy
        off = sum(1 for k, v in se.items() if v != SETTINGS[k]["nominal"] and k != "display_calibration")
        danger = max(0, self.heat - 75) * 0.6 + max(0, 45 - self.stability) * 0.5 + 3.0 * off
        calm = 0.1 if (self.heat < 65 and self.stability > 70) else 0.0
        # crisis: past CRISIS_AT the meter feeds on itself and only a crowd of responders can hold it
        helpers, spoilers = response
        if self.incident >= CRISIS_AT:
            danger += 1.2 + CASCADE * (self.incident - CRISIS_AT)
            calm = RESPOND_PER_MIN * helpers
            danger += SPOIL_PER_MIN * spoilers
        self.in_crisis = self.incident >= CRISIS_AT
        self.incident = max(0.0, self.incident + (danger - calm) * m)
        self.peak = max(self.peak, self.incident)
        if self.incident >= MELTDOWN_LIMIT:
            self.incident = MELTDOWN_LIMIT
            self.status = "MELTDOWN"
        self._grade(t, m)

    def shown(self, t: float) -> dict:
        """What the control room console displays."""
        d = dict(output=self.output, heat=self.heat, stability=self.stability, incident=self.incident,
                 **{f"h_{k}": v for k, v in self.health.items()})
        noise = max(0, 50 - self.health["instruments"]) * 0.2      # bad instruments = vague readings
        if self.masked:
            for k, v in MASK.items():
                d[k] = d[k] + v
        for k in ("heat", "stability", "incident"):
            d[k] = max(0.0, min(100.0, d[k]))
        d["uncertainty"] = round(noise, 1)
        return {k: round(v, 1) if isinstance(v, float) else v for k, v in d.items()}

    @property
    def masked(self):
        return self.settings["display_calibration"] == "offset"

    def off_nominal(self):
        return {k: v for k, v in self.settings.items() if v != SETTINGS[k]["nominal"]}

    def true(self) -> dict:
        return {k: round(v, 1) for k, v in dict(output=self.output, heat=self.heat, stability=self.stability,
                                                 incident=self.incident,
                                                 **{f"h_{k}": v for k, v in self.health.items()}).items()}

    def _grade(self, t, m):
        sh = self.shown(t)
        if STAGES[0]["start"] <= t < STAGES[0]["end"] and sh["output"] >= 100:
            self.stage_minutes[1] += m
        if STAGES[1]["start"] <= t < STAGES[1]["end"] and sh["output"] >= 85:
            self.stage_minutes[2] += m
        if STAGES[2]["end"] - 1800 <= t < STAGES[2]["end"] and sh["heat"] < 70 and sh["stability"] > 60:
            self.stage_minutes[3] += m

    def grade(self) -> dict:
        return {f"stage{k}": dict(minutes=round(v, 1), need=NEED_MIN[k], passed=v >= NEED_MIN[k])
                for k, v in self.stage_minutes.items()}

    def test_passed(self) -> bool:
        return all(g["passed"] for g in self.grade().values())
