"""Corporate certification script (game minutes from 08:00) and grading on console readings."""

STAGES = [
    dict(n=1, name="Thermal over-power ramp", start=40, end=80, power=1.05, pumpB=100,
         rule="console power >= 103% for 24 of 40 min"),
    dict(n=2, name="Single-pump loss of flow", start=100, end=160, power=0.92, pumpB=35,
         rule="pump B <= 36% with console power >= 85% for 48 of 60 min"),
    dict(n=3, name="Stabilize & sign-off", start=180, end=240, power=0.95, pumpB=100,
         rule="pump B >= 90% and console core temp < 350 C for the last 30 min"),
]


def setpoint(minute: float, stage2_aborted: bool = False) -> dict:
    for s in STAGES:
        if s["start"] <= minute < s["end"]:
            if s["n"] == 2 and stage2_aborted:
                return dict(stage=2, power=0.92, pumpB=100)
            return dict(stage=s["n"], power=s["power"], pumpB=s["pumpB"])
    if 160 <= minute < 180:
        return dict(stage=0, power=0.92, pumpB=70)
    return dict(stage=0, power=1.0, pumpB=100)


class Grader:
    def __init__(self):
        self.minutes = {1: 0.0, 2: 0.0, 3: 0.0}

    def observe(self, minute: float, snap: dict, dt_min: float):
        if 40 <= minute < 80 and snap["console_power"] >= 1.03:
            self.minutes[1] += dt_min
        if 100 <= minute < 160 and snap["pumpB"] <= 36 and snap["console_power"] >= 0.85:
            self.minutes[2] += dt_min
        if 210 <= minute < 240 and snap["pumpB"] >= 90 and snap["console_temp"] < 350:
            self.minutes[3] += dt_min

    def result(self) -> dict:
        need = {1: 24, 2: 48, 3: 29.5}
        return {f"stage{k}": {"minutes": round(v, 1), "need": need[k], "pass": v >= need[k]}
                for k, v in self.minutes.items()}
