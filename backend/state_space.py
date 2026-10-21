"""State-space integration (Phase 4): linearise at a chosen operating point, export, compare with the nonlinear run.

The matrices are a LINEARISATION of the nonlinear model about an EQUILIBRIUM operating point, in deviation variables:
    d(dx)/dt = A dx + B du,   dy = C dx + D du,   dx = x - x0, du = u - u0, dy = y - y0.
They describe small deviations only. They are not measured plant data and are not validated against the real plant.

Two variants:
  * "open_loop"   : plant only, states [h_p, Q, y, w, delta], inputs [y_cmd, P_load, Q_in]. At the nominal point this is
                    exactly the Phase 1 export in exports/ (same code path: backend.model.linearize / export_state_space).
  * "closed_loop" : plant + PI/droop governor, states [h_p, Q, y, w, delta, xi], inputs [y_set, P_load, Q_in].
                    Valid only while no governor limit is active (command limits, gate-rate limits are nonlinear).
"""
from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from scipy import signal

from backend import model as m
from backend.governor import GOVERNOR_ASSUMPTIONS, GovernorSettings, rhs_closed_loop

CL_STATES = m.STATES + [("xi", "Governor PI integrator", "pu")]
CL_INPUTS = [("y_set", "Gate set-point / load reference (governor input)", "pu, 0..1")] + m.INPUTS[1:]


def operating_point_errors(p: dict, y0, h_p0) -> list[str]:
    """Why an operating point cannot be used (empty list = usable). Nothing is clipped."""
    errs = []
    if not (np.isfinite(y0) and p["y_min"] < y0 < 1.0):
        errs.append(f"Gate opening {y0:.4f} pu must be strictly between y_min = {p['y_min']:g} pu (assumed numerical floor) and "
                    "1.0 pu: at a limit the model is not differentiable, so a linearisation would be meaningless.")
    if not (np.isfinite(h_p0) and h_p0 > p["z_tw"] + 1.0):
        errs.append(f"Pond level {h_p0:.3f} m must be above the tailwater level {p['z_tw']:.2f} m (calculated).")
    return errs


def linearize_at(p: dict, y0: float, h_p0: float, kind: str = "open_loop", gov: GovernorSettings | None = None) -> dict:
    """Linearise at the equilibrium with gate y0 and pond level h_p0. Raises ValueError for unusable points."""
    errs = operating_point_errors(p, y0, h_p0)
    if errs:
        raise ValueError(" ".join(errs))
    lin = m.linearize(p, y0, h_p0)                      # Phase 1 code (numerical + analytic check)
    lin["kind"] = kind
    if kind == "open_loop":
        return lin
    if kind != "closed_loop":
        raise ValueError("kind must be 'open_loop' or 'closed_loop'")
    gov = gov or GovernorSettings()
    z0 = np.append(lin["x0"], 0.0)                      # integrator is zero at equilibrium when y_set = y0
    u0 = lin["u0"].copy()                               # y_set = y0, P_load = P0, Q_in = Q0
    f = lambda z: rhs_closed_loop(z, u0, p, gov, True)
    if np.abs(f(z0)).max() > 1e-8:
        raise ValueError("Closed-loop operating point is not an equilibrium (unexpected).")
    J = m._central_jacobian
    A = J(f, z0)
    B = J(lambda u: rhs_closed_loop(z0, u, p, gov, True), u0)
    C = J(lambda z: m.outputs(z[:5], u0, p), z0)
    D = J(lambda u: m.outputs(z0[:5], u, p), u0)
    lin.update(A=A, B=B, C=C, D=D, x0=z0, u0=u0, gov=gov, max_abs_diff_vs_analytic=None)
    return lin


def eigenvalues(lin: dict) -> np.ndarray:
    return np.sort_complex(np.linalg.eigvals(lin["A"]))


def export_zip(lin: dict, params: dict, label: str) -> bytes:
    """ZIP with A.csv, B.csv, C.csv, D.csv and state_space_model.json.
    Open loop: written by the Phase 1 exporter, so the nominal point is byte-identical to exports/."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        if lin["kind"] == "open_loop":
            m.export_state_space(out, params, lin)
            meta = json.loads((out / "state_space_model.json").read_text(encoding="utf-8"))
        else:
            for name in "ABCD":
                np.savetxt(out / f"{name}.csv", lin[name], delimiter=",", fmt="%.10e")
            meta = {
                "model": "GBHP single generating unit WITH PI/droop governor (closed loop), rigid water column",
                "status": "SIMULATION MODEL. Not connected to the real plant. Not validated against real operating data.",
                "form": "dx/dt = A x + B u ; y = C x + D u  (deviation variables about the operating point)",
                "states": [dict(name=n, description=d, unit=u) for n, d, u in CL_STATES],
                "inputs": [dict(name=n, description=d, unit=u) for n, d, u in CL_INPUTS],
                "outputs": [dict(name=n, description=d, unit=u) for n, d, u in m.OUTPUTS],
                "linearization": {"method": "Numerical Jacobian of backend.governor.rhs_closed_loop, central differences",
                                  "validity": "Small deviations with no governor limit active (command limits 0..1 pu, "
                                              "gate rate limits, gate floor y_min). Saturation is NOT represented."},
                "governor_settings_ASSUMED": {k: getattr(lin["gov"], k) for k in GOVERNOR_ASSUMPTIONS},
                "parameters": [dict(key=q.key, value=q.value, unit=q.unit, classification=q.classification, source=q.source)
                               for q in params.values()],
            }
        meta["operating_point_label"] = label
        meta["operating_point_values"] = {
            "x0": dict(zip([s[0] for s in (CL_STATES if lin["kind"] == "closed_loop" else m.STATES)], map(float, lin["x0"]))),
            "u0": dict(zip([s[0] for s in (CL_INPUTS if lin["kind"] == "closed_loop" else m.INPUTS)], map(float, lin["u0"]))),
            "y0": dict(zip([s[0] for s in m.OUTPUTS], map(float, lin["y0"])))}
        meta["eigenvalues"] = [{"re": float(e.real), "im": float(e.imag)} for e in eigenvalues(lin)]
        meta["linear_vs_nonlinear"] = LIMITATIONS
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name in "ABCD":
                z.write(out / f"{name}.csv", f"{name}.csv")
            z.writestr("state_space_model.json", json.dumps(meta, indent=2) + "\n")
    return buf.getvalue()


LIMITATIONS = [
    "Linearised about an equilibrium: accurate only for small deviations from that operating point.",
    "Gate limits, governor command limits, gate rate limits and the y_min floor are not in the linear model.",
    "Head h_t = Q^2/(Cg y)^2 and power P = eta rho g Q h_t are nonlinear: large flow or gate changes give growing errors.",
    "The rotor angle delta has a zero eigenvalue (no grid connection); pond level has a very slow mode.",
    "Same physical assumptions as the nonlinear model (rigid water column, constant efficiency, isolated unit, assumed H, D, T_y).",
    "Not validated against the real plant.",
]


def compare_with_run(sim, lin: dict) -> dict:
    """Drive the linear model with the input history of a run and compare outputs with the nonlinear results.

    Requires the run to start at the linearisation point and the governor mode to match the linear model.
    Returns dict(t, nonlinear{Q,h_t,P_gen,f}, linear{...}, max_abs_err{...}) or raises ValueError with the reason.
    """
    a = sim.arrays()
    if len(a["t"]) < 3:
        raise ValueError("Run the simulation first (at least one step).")
    gov_rows = a["governor_on"][1:] > 0.5
    want = lin["kind"] == "closed_loop"
    if not (gov_rows.all() == want and gov_rows.any() == want):
        raise ValueError("The governor mode of the run does not match the linear model "
                         f"({'closed loop needs the governor ON' if want else 'open loop needs the governor OFF'} for the whole run).")
    x_start = np.array([a["h_p"][0], a["Q"][0], a["y"][0], a["w"][0], a["delta"][0]])
    if np.abs(x_start - lin["x0"][:5]).max() > 1e-6:
        raise ValueError("The run did not start at this operating point (press Reset and run again, or choose the nominal point).")
    # Row k holds the inputs applied during (t[k-1], t[k]]; zero-order hold needs them at the start of each interval.
    U = np.column_stack([a["y_set"], a["P_load"], a["Q_in"]])
    U = np.vstack([U[1:], U[-1:]]) - lin["u0"]
    sys = signal.StateSpace(lin["A"], lin["B"], lin["C"], lin["D"])
    _, Y, _ = signal.lsim(sys, U, a["t"], interp=False)
    Y = Y + lin["y0"]
    names = ["Q", "h_t", "P_gen", "f"]
    lin_out = {n: Y[:, i] for i, n in enumerate(names)}
    non = {n: a[n] for n in names}
    return dict(t=a["t"], nonlinear=non, linear=lin_out,
                max_abs_err={n: float(np.abs(lin_out[n] - non[n]).max()) for n in names},
                max_dev={n: float(np.abs(non[n] - non[n][0]).max()) for n in names})
