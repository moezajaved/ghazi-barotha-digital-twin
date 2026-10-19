"""PI governor with permanent droop for the single GBHP unit (Phase 2).

SIMULATION ONLY. The brochure gives NO governor data: every setting below is an ASSUMED educational value,
tuned only so the assumed plant is well damped. See documentation/mathematical_model.md (section Governor).

Control law (all quantities per unit):
    e      = (w_ref - w) - R*(y - y_set)            speed error with permanent droop R from gate feedback
    y_cmd  = clip(y_set + Kp*e + xi, y_lo, y_hi)    xi = integrator state, dxi/dt = Ki*e
Gate servo velocity limit:  -rate_close <= dy/dt <= +rate_open.
Anti-windup: back-calculation, dxi/dt = Ki*e + Kb*(y_cmd - unsat). It is continuous, and zero while the command is unsaturated.
(An earlier conditional-integration scheme froze xi at saturation; it chattered on the saturation boundary and made every
ODE solver fail when a load beyond full-gate capacity was applied, so it was replaced.)
In steady state e = 0, so w = w_ref - R*(y - y_set): y_set acts as the load/speed reference.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np

from backend import model as m


@dataclass(frozen=True)
class GovernorSettings:
    R: float = 0.05           # pu speed per pu gate (permanent droop)
    Kp: float = 1.0           # pu gate per pu speed error
    Ki: float = 0.20          # pu gate per pu speed error per second
    rate_open: float = 0.10   # pu/s, gate opening velocity limit
    rate_close: float = 0.20  # pu/s, gate closing velocity limit
    Kb: float = 2.0           # 1/s, back-calculation anti-windup gain
    y_lo: float = 0.0         # pu, command lower limit
    y_hi: float = 1.0         # pu, command upper limit
    w_ref: float = 1.0        # pu, speed reference

    def validate(self) -> list[str]:
        errs = []
        for f in fields(self):
            v = getattr(self, f.name)
            if not isinstance(v, (int, float)) or not np.isfinite(v):
                errs.append(f"{f.name} must be a finite number")
        if errs:
            return errs
        rng = {"R": (0.01, 0.10), "Kp": (0.0, 10.0), "Ki": (0.0, 5.0), "rate_open": (0.01, 1.0),
               "rate_close": (0.01, 1.0), "Kb": (0.1, 10.0), "y_lo": (0.0, 0.5), "y_hi": (0.5, 1.0), "w_ref": (0.95, 1.05)}
        for k, (lo, hi) in rng.items():
            if not lo <= getattr(self, k) <= hi:
                errs.append(f"{k} must be between {lo} and {hi}")
        if self.y_lo >= self.y_hi:
            errs.append("y_lo must be below y_hi")
        return errs


# unit, meaning/rationale (all ASSUMED: not in brochure)
GOVERNOR_ASSUMPTIONS = {
    "R": ("pu/pu", "Permanent droop 5%: common utility practice; not a GBHP value."),
    "Kp": ("pu/pu", "Chosen by scanning Kp 0.5-3, Ki 0.05-0.4 on the assumed plant (Tw=1.49 s, H=3 s): Kp=1, Ki=0.2 gives a "
                    "complex pole pair with damping ratio 0.85; after a +20 MW load step frequency dips to 48.37 Hz (5.8 s) and "
                    "is within +/-0.05 Hz of its final value after about 22 s. Not a GBHP value."),
    "Ki": ("pu/pu/s", "As Kp."),
    "rate_open": ("pu/s", "Gate opening velocity limit (about 10 s stroke); typical order, not a GBHP value."),
    "rate_close": ("pu/s", "Gate closing velocity limit (about 5 s stroke); typical order, not a GBHP value."),
    "Kb": ("1/s", "Anti-windup back-calculation gain: bounds the integrator overshoot beyond a limit to about Ki*e/Kb. Not a GBHP value."),
    "y_lo": ("pu", "Command lower limit (gate closed)."),
    "y_hi": ("pu", "Command upper limit (gate fully open)."),
    "w_ref": ("pu", "Speed reference = synchronous speed."),
}


def command(z, u, g: GovernorSettings, governor_on: bool):
    """Return (y_cmd, e, unsaturated command). Without the governor the gate command is y_set (clipped)."""
    y, w, xi = z[2], z[3], z[5]
    y_set = u[0]
    if not governor_on:
        c = min(max(y_set, 0.0), 1.0)
        return c, 0.0, c
    e = (g.w_ref - w) - g.R * (y - y_set)
    unsat = y_set + g.Kp * e + xi
    return min(max(unsat, g.y_lo), g.y_hi), e, unsat


def rhs_closed_loop(z, u, p, g: GovernorSettings, governor_on: bool = True) -> np.ndarray:
    """z = [h_p, Q, y, w, delta, xi]; u = [y_set, P_load, Q_in]. Plant is backend.model.rhs, unchanged."""
    z = np.asarray(z, float)
    cmd, e, unsat = command(z, u, g, governor_on)
    dx = m.rhs(z[:5], [cmd, u[1], u[2]], p)
    dx[2] = min(max(dx[2], -g.rate_close), g.rate_open)          # servo velocity limit
    dxi = g.Ki * e + g.Kb * (cmd - unsat) if governor_on else 0.0   # back-calculation anti-windup
    return np.append(dx, dxi)


def closed_loop_poles(p, g: GovernorSettings, y0: float | None = None) -> np.ndarray:
    """Poles of the governed unit: numerical Jacobian of rhs_closed_loop at the operating point."""
    ss = m.steady_state(p, y0)
    z0 = np.append(ss["x0"], 0.0)
    u0 = ss["u0"]
    A = m._central_jacobian(lambda z: rhs_closed_loop(z, u0, p, g, True), z0)
    return np.sort_complex(np.linalg.eigvals(A))
