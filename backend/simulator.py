"""Stepping simulation engine behind the dashboard (Phase 2).

Integrates the Phase 1 plant (backend.model.rhs, unchanged) together with the PI/droop governor
(backend.governor) from the equilibrium operating point, in chunks, with validated inputs.
SIMULATION ONLY: not connected to the real plant; assumed parameters are labelled in the parameter register.
"""
from __future__ import annotations

import csv
import io
import math

import numpy as np
from scipy.integrate import solve_ivp

from backend import model as m
from backend.governor import GovernorSettings, command, rhs_closed_loop

RECORD_DT = 0.25       # s, history sampling interval
MAX_DURATION = 3600.0  # s
_ATOL = [1e-6, 1e-6, 1e-9, 1e-11, 1e-9, 1e-9]
COLUMNS = ["t", "h_p", "Q", "y", "y_cmd", "w", "delta", "xi", "h_t", "P_gen", "f",
           "P_load", "Q_in", "y_set", "governor_on"]


def _is_number(v) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) and math.isfinite(v)


def validate_inputs(p: dict, y_set, P_load, Q_in, duration=None) -> list[str]:
    """Return a list of error messages (empty if all inputs are valid)."""
    errs: list[str] = []

    def check(name, v, lo, hi, unit):
        if not _is_number(v):
            errs.append(f"{name} must be a finite number")
        elif not lo <= v <= hi:
            errs.append(f"{name} must be between {lo:g} and {hi:g} {unit}")

    check("Gate command", y_set, 0.0, 1.0, "pu")
    check("Electrical load", P_load, 0.0, p["S_base"], "MW (assumed generator base)")
    check("Inflow", Q_in, 0.0, p["Q_full"], "m3/s")
    if duration is not None:
        check("Duration", duration, 1.0, MAX_DURATION, "s")
    return errs


def channel_share_per_unit() -> float:
    """Power channel design flow (published, p.12) divided by the number of units: sustained inflow per unit."""
    reg = m.load_register()
    return float(reg[("Power channel", "Design flow")]["value"]) / float(reg[("Plant", "Number of units")]["value"])


class Simulator:
    def __init__(self, params=None, gov: GovernorSettings | None = None):
        self.params = params or m.build_parameters()
        self.p = m.values(self.params)
        self.gov = gov or GovernorSettings()
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self, governor_on: bool = True) -> None:
        self.ss = m.steady_state(self.p)                      # equilibrium at the Phase 1 operating point
        self.z = np.append(self.ss["x0"], 0.0)                # [h_p, Q, y, w, delta, xi]
        self.t = 0.0
        self.hist = {c: [] for c in COLUMNS}
        self._record(0.0, self.z, self.ss["u0"], governor_on)

    def _record(self, t, z, u, governor_on) -> None:
        cmd, _, _ = command(z, u, self.gov, governor_on)
        Q, h_t, P, f = m.outputs(z[:5], u, self.p)
        row = [t, z[0], z[1], z[2], cmd, z[3], z[4], z[5], h_t, P, f, u[1], u[2], u[0], float(governor_on)]
        for c, v in zip(COLUMNS, row):
            self.hist[c].append(float(v))

    # --------------------------------------------------------------- stepping
    def step(self, dt: float, y_set: float, P_load: float, Q_in: float, governor_on: bool = True) -> None:
        errs = validate_inputs(self.p, y_set, P_load, Q_in) + self.gov.validate()
        if not (_is_number(dt) and 0 < dt <= MAX_DURATION):
            errs.append(f"Step must be between 0 and {MAX_DURATION:g} s")
        if errs:
            raise ValueError("; ".join(errs))
        u = np.array([y_set, P_load, Q_in], float)
        n = max(1, int(round(dt / RECORD_DT)))
        t_eval = self.t + np.linspace(0.0, dt, n + 1)[1:]
        sol = solve_ivp(lambda t, z: rhs_closed_loop(z, u, self.p, self.gov, governor_on),
                        (self.t, self.t + dt), self.z, method="Radau", t_eval=t_eval, rtol=1e-8, atol=_ATOL)
        if not sol.success:
            raise RuntimeError(f"Integration failed: {sol.message}")
        for k in range(n):
            self._record(sol.t[k], sol.y[:, k], u, governor_on)
        self.z = sol.y[:, -1].copy()
        self.t = float(sol.t[-1])

    # ---------------------------------------------------------------- results
    def latest(self) -> dict:
        return {c: v[-1] for c, v in self.hist.items()}

    def arrays(self) -> dict:
        return {c: np.asarray(v) for c, v in self.hist.items()}

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(COLUMNS)
        for row in zip(*(self.hist[c] for c in COLUMNS)):
            w.writerow([f"{v:.8g}" for v in row])
        return buf.getvalue()
