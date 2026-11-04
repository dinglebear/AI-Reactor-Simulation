"""0-D reactor engine. Port of sandbox/unit4-sandbox.html; constants are per *beat* (4 game-min).

Game-tuned, not a licensed plant model. Primary pressure is scaled (32 bar nominal) so the
spec's 50 bar breach line sits a meaningful distance above normal operation.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field, asdict

DEFAULTS = dict(rodWorth=8.0, rho0=3.6, doppler=0.004, xenonWorth=2.0, voidCoef=3.0,
                kinetics=1.5, heatCap=2.0, xenonSpeed=1.0, reliefSetpoint=42.0,
                breachBar=50.0, meltC=2000.0)


@dataclass
class Core:
    P: float = 1.0          # thermal power fraction of rated
    T: float = 300.0        # core temp °C
    p: float = 32.0         # primary pressure bar
    rod: float = 45.0       # % inserted
    pumpA: float = 100.0
    pumpB: float = 100.0
    I: float = 1.0
    X: float = 1.0          # xenon-135, 1.0 = full-power equilibrium
    voidF: float = 0.0
    rho: float = 0.0        # reactivity, dollars
    flow: float = 1.0
    scram: bool = False
    relief_open: bool = False
    status: str = "RUNNING"
    # instrument channels: fractional under-read of flux per channel, and thermocouple offset
    flux_drift: dict = field(default_factory=lambda: {"A": 0.0, "B": 0.0, "C": 0.0})
    temp_offset_c: float = 0.0

    def console_power(self) -> float:
        reads = sorted(self.P * (1 - d) for d in self.flux_drift.values())
        return reads[1]  # median select

    def channel_spread(self) -> float:
        reads = [self.P * (1 - d) for d in self.flux_drift.values()]
        return (max(reads) - min(reads)) / max(1e-6, self.P)

    def console_temp(self) -> float:
        return self.T - self.temp_offset_c

    def grid_mw(self) -> int:
        return round(self.P * 1000 * min(1.0, self.flow + 0.2))

    def snapshot(self) -> dict:
        d = asdict(self)
        d.update(console_power=self.console_power(), console_temp=self.console_temp(),
                 spread=self.channel_spread(), grid_mw=self.grid_mw())
        return d


def step(c: Core, ctl: dict, prm: dict, seconds: float) -> None:
    """Advance the core by `seconds` of game time. ctl: rod, pumpA, pumpB, relief_locked, rod_locked, scram."""
    if c.status != "RUNNING":
        return
    beats = seconds / 240.0
    n = max(1, round(beats * 20))
    dt = beats / n
    if ctl.get("scram"):
        c.scram = True
    frozen = ctl.get("rod_locked") and not c.scram
    rod_target = 100.0 if c.scram else (c.rod if frozen else ctl["rod"])
    rod_speed = 50.0 if c.scram else 6.0
    for _ in range(n):
        for name in ("pumpA", "pumpB"):
            cur = getattr(c, name)
            setattr(c, name, cur + max(-25 * dt, min(25 * dt, ctl[name] - cur)))
        flow = max(0.05, 0.5 * c.pumpA / 100 + 0.5 * c.pumpB / 100)
        c.flow = flow
        dr = rod_target - c.rod
        c.rod += math.copysign(min(abs(dr), rod_speed * dt), dr)
        v_target = max(0.0, min(0.85, (c.T - 295) / 180 * (1.3 - flow)))
        c.voidF += (v_target - c.voidF) * min(1.0, 2 * dt)
        rho = (prm["rho0"] - prm["rodWorth"] * c.rod / 100 - prm["doppler"] * (c.T - 300)
               - prm["xenonWorth"] * (c.X - 1) + prm["voidCoef"] * c.voidF)
        c.rho = rho
        rate = prm["kinetics"] * rho if rho < 1 else prm["kinetics"] + 40 * (rho - 1)
        c.P = max(0.0005, min(60.0, c.P * math.exp(rate * dt)))
        H = flow * (1 - 0.6 * c.voidF)
        c.T = max(120.0, c.T + (100 * c.P - H * (c.T - 200)) / prm["heatCap"] * dt)
        k = prm["xenonSpeed"] * dt
        dI = 0.05 * c.P - 0.05 * c.I
        dX = 0.065 * c.P + 0.05 * c.I - 0.035 * c.X - 0.08 * c.P * c.X
        c.I += dI * k
        c.X += dX * k
        p_target = 32 + 0.2 * (c.T - 300) + 24 * c.voidF
        c.p += (p_target - c.p) * min(1.0, 1.5 * dt)
        c.relief_open = False
        if not ctl.get("relief_locked") and c.p > prm["reliefSetpoint"]:
            c.relief_open = True
            c.p = prm["reliefSetpoint"] + (c.p - prm["reliefSetpoint"]) * 0.6
        if c.T >= prm["meltC"]:
            c.status = "MELTDOWN"
            return
        if c.p >= prm["breachBar"]:
            c.status = "BREACH"
            return


def auto_rod(c: Core, target: float, prm: dict) -> float:
    """Auto rod control. Trusts the console (median-selected) flux reading."""
    desired = 0.35 * math.log(target / max(1e-4, c.console_power()))
    return max(0.0, min(100.0, c.rod + (c.rho - desired) * 100 / prm["rodWorth"]))
