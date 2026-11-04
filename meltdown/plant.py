"""Abstract, game-tuned plant model. Not a physics simulation.

Everything is a 0-100 meter. Four systems wear down and are kept up by staff working at stations.
The saboteur's cards (cards.py) knock systems down and push the INCIDENT meter up; at 100 the game ends.
The control room only ever sees the *shown* values, which can be masked by a card.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .config import at

SYSTEMS = ("core", "coolant", "instruments", "security")
WEAR_PER_MIN = {"core": 0.25, "coolant": 0.35, "instruments": 0.2, "security": 0.15}
REPAIR_PER_MIN = 1.0          # one worker at a matching station
INCIDENT_LIMIT = 100.0

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
    # masking: until time T, the console subtracts these from what it shows
    mask_until: float = -1
    mask: dict = field(default_factory=dict)
    scrammed: bool = False
    status: str = "RUNNING"       # RUNNING | INCIDENT | SCRAM
    stage_minutes: dict = field(default_factory=lambda: {1: 0.0, 2: 0.0, 3: 0.0})

    def step(self, t: float, dt: float, crew_at: dict):
        """crew_at: system -> number of workers currently maintaining it."""
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
        heat_target = 30 + self.output * 0.5 + load * 0.9 - 35 * h["coolant"] / 100
        self.heat += (heat_target - self.heat) * min(1.0, m / 6)
        self.heat = max(10.0, min(100.0, self.heat))
        # stability falls with heat and weak core/instruments
        st_target = 100 - max(0, self.heat - 55) * 1.2 - (100 - h["core"]) * 0.35 - (100 - h["instruments"]) * 0.2
        self.stability += (st_target - self.stability) * min(1.0, 0.15 * m * 6)
        self.stability = max(0.0, min(100.0, self.stability))
        # incident meter: driven by danger zones, slowly calms when the plant is healthy
        danger = max(0, self.heat - 80) * 0.5 + max(0, 40 - self.stability) * 0.4
        calm = 0.1 if (self.heat < 65 and self.stability > 70) else 0.0
        self.incident = max(0.0, self.incident + (danger - calm) * m)
        if self.incident >= INCIDENT_LIMIT:
            self.incident = INCIDENT_LIMIT
            self.status = "INCIDENT"
        self._grade(t, m)

    def shown(self, t: float) -> dict:
        """What the control room console displays."""
        d = dict(output=self.output, heat=self.heat, stability=self.stability, incident=self.incident,
                 **{f"h_{k}": v for k, v in self.health.items()})
        noise = max(0, 50 - self.health["instruments"]) * 0.2      # bad instruments = vague readings
        if t < self.mask_until:
            for k, v in self.mask.items():
                d[k] = d[k] + v
        for k in ("heat", "stability", "incident"):
            d[k] = max(0.0, min(100.0, d[k]))
        d["uncertainty"] = round(noise, 1)
        return {k: round(v, 1) if isinstance(v, float) else v for k, v in d.items()}

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
