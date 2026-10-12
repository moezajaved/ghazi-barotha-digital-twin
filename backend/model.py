"""Single-unit Ghazi Barotha (GBHP) hydropower model, linearisation and export.

SIMULATION ONLY. Not connected to the real plant; not validated against real data.

Parameter classes
  published  : read from source_data/source_data_register.csv (teacher brochure, with PDF page)
  calculated : derived from published and/or assumed values (formula in `source`)
  assumed    : educational assumption NOT in the brochure (rationale recorded; easy to override)

State x = [h_p, Q, y, w, delta]   input u = [y_cmd, P_load, Q_in]   output = [Q, h_t, P_gen, f]
Equations are documented in documentation/mathematical_model.md.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "source_data" / "source_data_register.csv"
G = 9.81      # m/s2, standard value
RHO = 1000.0  # kg/m3, standard value

STATES = [
    ("h_p", "Headpond level (per-unit share of pond)", "m"),
    ("Q", "Penstock / turbine flow", "m3/s"),
    ("y", "Gate (wicket gate) position", "pu, 0..1"),
    ("w", "Rotor speed", "pu of synchronous speed"),
    ("delta", "Rotor angle relative to synchronous reference", "rad"),
]
INPUTS = [
    ("y_cmd", "Gate position command", "pu, 0..1"),
    ("P_load", "Electrical load on the unit", "MW"),
    ("Q_in", "Inflow to this unit's share of the headpond (power channel)", "m3/s"),
]
OUTPUTS = [
    ("Q", "Turbine flow", "m3/s"),
    ("h_t", "Net head across turbine", "m"),
    ("P_gen", "Generated electrical power = eta*rho*g*Q*h_t", "MW"),
    ("f", "Electrical frequency = f_nom*w", "Hz"),
]


@dataclass(frozen=True)
class Param:
    key: str
    description: str
    value: float
    unit: str
    classification: str  # published | calculated | assumed
    source: str


# (key, register category, register parameter, description, unit, scale to SI)
_PUBLISHED = [
    ("n_units", "Plant", "Number of units", "Number of generating units", "-", 1.0),
    ("Q_full", "Plant", "Design flow per unit, full gate", "Flow per unit at full gate, design head", "m3/s", 1.0),
    ("Q_opt", "Plant", "Design flow per unit, optimum gate", "Flow per unit at optimum gate, design head", "m3/s", 1.0),
    ("H_design", "Plant", "Design head", "Design (net) head", "m", 1.0),
    ("eta", "Plant", "Combined generating efficiency", "Combined turbine+generator efficiency", "pu", 0.01),
    ("D_pen", "Penstock", "Diameter", "Penstock diameter", "m", 1.0),
    ("L_pen", "Penstock", "Length", "Penstock length", "m", 1.0),
    ("z_pond", "Power complex", "Headponds normal pond level", "Headpond normal pond level", "m", 1.0),
    ("V_live", "Power complex", "Headponds live volume (two ponds combined)", "Headpond live volume, both ponds", "m3", 1e6),
    ("S_trafo_1ph", "Electrical", "Transformer rating (single-phase unit)", "Single-phase transformer rating", "MVA", 1.0),
]

# key: (value, unit, description, rationale/effect)
_ASSUMED = {
    "hf_design": (0.5, "m", "Penstock friction head loss at Q_opt",
                  "Loss data not in brochure; short 222 m, 10.6 m-bore penstock so small. Sets tailwater level and damping."),
    "dh_live": (3.0, "m", "Usable headpond drawdown spanning the live volume",
                "Level-volume curve not in brochure. Sets pond area, i.e. only the slow pond-level dynamics."),
    "T_y": (0.5, "s", "Gate servo time constant", "Servo data not in brochure; typical order for large Francis units."),
    "H_inertia": (3.0, "s", "Unit inertia constant (on S_base)", "Not in brochure; typical hydro generator 2-4 s."),
    "D_damp": (1.0, "pu", "Load damping (pu power per pu speed)", "Not in brochure; typical load-frequency dependence 1-2 pu."),
    "f_nom": (50.0, "Hz", "Nominal frequency", "Not stated in brochure; 50 Hz is the Pakistani grid standard."),
    "y_min": (0.02, "pu", "Numerical floor on gate opening", "Avoids division by zero when the gate is fully closed. Not physical."),
    "S_base": (None, "MVA", "Generator MVA base",
               "Generator MVA is not in brochure; 3 x single-phase transformer rating (pp.12,17) is used as the base."),
}


def load_register(path: Path = REGISTER) -> dict:
    with open(path, newline="") as f:
        return {(r["category"], r["parameter"]): r for r in csv.DictReader(f)}


def build_parameters(overrides: dict | None = None, register_path: Path = REGISTER) -> dict[str, Param]:
    """Build the full parameter set. `overrides` may change ASSUMED values only."""
    overrides = dict(overrides or {})
    bad = [k for k in overrides if k not in _ASSUMED]
    if bad:
        raise ValueError(f"Only assumed parameters can be overridden, not: {bad}")
    reg = load_register(register_path)
    P: dict[str, Param] = {}
    for key, cat, name, desc, unit, scale in _PUBLISHED:
        row = reg[(cat, name)]
        P[key] = Param(key, desc, float(row["value"]) * scale, unit, "published",
                       f"Brochure PDF p.{row['pdf_page']} ({cat}: {name})")
    for key, (val, unit, desc, why) in _ASSUMED.items():
        if key == "S_base" and val is None:
            val = 3 * P["S_trafo_1ph"].value
        P[key] = Param(key, desc, float(overrides.get(key, val)), unit, "assumed", why)
    v = {k: q.value for k, q in P.items()}

    def calc(key, desc, value, unit, formula):
        P[key] = Param(key, desc, float(value), unit, "calculated", formula)

    calc("A_pen", "Penstock cross-section", np.pi * v["D_pen"] ** 2 / 4, "m2", "pi*D_pen^2/4")
    calc("Cg", "Gate-flow coefficient (Q = Cg*y*sqrt(h_t))", v["Q_full"] / np.sqrt(v["H_design"]), "m2.5/s",
         "Q_full/sqrt(H_design), taking y=1 as full gate at design head (brochure p.17)")
    calc("y_opt", "Gate position at optimum flow", v["Q_opt"] / v["Q_full"], "pu",
         "Q_opt/Q_full, assuming flow proportional to gate opening at fixed head")
    calc("kf", "Penstock friction coefficient (h_f = kf*Q^2)", v["hf_design"] / v["Q_opt"] ** 2, "s2/m5",
         "hf_design/Q_opt^2 (depends on assumed hf_design)")
    calc("z_tw", "Tailwater level (derived)", v["z_pond"] - v["H_design"] - v["hf_design"], "m",
         "z_pond - H_design - hf_design (depends on assumed hf_design)")
    calc("A_pond", "Headpond surface area per unit", v["V_live"] / v["dh_live"] / v["n_units"], "m2",
         "V_live/dh_live/n_units (depends on assumed dh_live)")
    return P


def values(params: dict[str, Param]) -> dict[str, float]:
    return {k: q.value for k, q in params.items()}


# ---------------------------------------------------------------- dynamics
def _head(Q, y, p):
    """Net turbine head from Q = Cg*y*sqrt(h_t)."""
    ye = min(max(y, p["y_min"]), 1.0)
    return Q * abs(Q) / (p["Cg"] * ye) ** 2


def rhs(x, u, p) -> np.ndarray:
    h_p, Q, y, w, delta = x
    y_cmd, P_load, Q_in = u
    h_t = _head(Q, y, p)
    h_f = p["kf"] * Q * abs(Q)
    P_gen = p["eta"] * RHO * G * Q * h_t / 1e6
    return np.array([
        (Q_in - Q) / p["A_pond"],
        (G * p["A_pen"] / p["L_pen"]) * (h_p - p["z_tw"] - h_f - h_t),
        (y_cmd - y) / p["T_y"],
        ((P_gen - P_load) / p["S_base"] - p["D_damp"] * (w - 1.0)) / (2.0 * p["H_inertia"]),
        2.0 * np.pi * p["f_nom"] * (w - 1.0),
    ])


def outputs(x, u, p) -> np.ndarray:
    h_p, Q, y, w, delta = x
    h_t = _head(Q, y, p)
    return np.array([Q, h_t, p["eta"] * RHO * G * Q * h_t / 1e6, p["f_nom"] * w])


def steady_state(p, y0: float | None = None, h_p0: float | None = None) -> dict:
    """Equilibrium for a given gate position and pond level (w=1, delta=0, Q_in=Q, P_load=P_gen)."""
    y0 = p["y_opt"] if y0 is None else y0
    h_p0 = p["z_pond"] if h_p0 is None else h_p0
    Q0 = np.sqrt((h_p0 - p["z_tw"]) / (p["kf"] + 1.0 / (p["Cg"] * y0) ** 2))
    x0 = np.array([h_p0, Q0, y0, 1.0, 0.0])
    P0 = outputs(x0, None, p)[2]
    u0 = np.array([y0, P0, Q0])
    return {"x0": x0, "u0": u0, "y0": outputs(x0, u0, p)}


def water_starting_time(p, x0) -> float:
    """T_w = L*Q0/(g*A*H0) [s], using the operating-point head."""
    return p["L_pen"] * x0[1] / (G * p["A_pen"] * _head(x0[1], x0[2], p))


# ------------------------------------------------------------ linearisation
def _central_jacobian(f, z0, rel: float = 1e-5) -> np.ndarray:
    z0 = np.asarray(z0, float)
    n_out = np.asarray(f(z0)).size
    J = np.zeros((n_out, z0.size))
    for j in range(z0.size):
        h = rel * max(abs(z0[j]), 1.0)
        zp, zm = z0.copy(), z0.copy()
        zp[j] += h
        zm[j] -= h
        J[:, j] = (np.asarray(f(zp)) - np.asarray(f(zm))) / (2 * h)
    return J


def numerical_jacobians(p, x0, u0):
    A = _central_jacobian(lambda x: rhs(x, u0, p), x0)
    B = _central_jacobian(lambda u: rhs(x0, u, p), u0)
    C = _central_jacobian(lambda x: outputs(x, u0, p), x0)
    D = _central_jacobian(lambda u: outputs(x0, u, p), u0)
    return A, B, C, D


def analytic_jacobians(p, x0, u0):
    """Hand-derived Jacobians (independent check of the numerical ones). Valid for Q>0, y_min<y<1."""
    _, Q, y, _, _ = x0
    a = G * p["A_pen"] / p["L_pen"]
    h_t = Q * Q / (p["Cg"] * y) ** 2
    k = p["eta"] * RHO * G / 1e6
    two_H = 2.0 * p["H_inertia"]
    dPdQ, dPdy = 3 * k * h_t, -2 * k * Q * h_t / y
    A = np.zeros((5, 5))
    A[0, 1] = -1.0 / p["A_pond"]
    A[1, 0] = a
    A[1, 1] = -a * (2 * p["kf"] * Q + 2 * h_t / Q)
    A[1, 2] = 2 * a * h_t / y
    A[2, 2] = -1.0 / p["T_y"]
    A[3, 1] = dPdQ / (p["S_base"] * two_H)
    A[3, 2] = dPdy / (p["S_base"] * two_H)
    A[3, 3] = -p["D_damp"] / two_H
    A[4, 3] = 2 * np.pi * p["f_nom"]
    B = np.zeros((5, 3))
    B[0, 2] = 1.0 / p["A_pond"]
    B[2, 0] = 1.0 / p["T_y"]
    B[3, 1] = -1.0 / (p["S_base"] * two_H)
    C = np.zeros((4, 5))
    C[0, 1] = 1.0
    C[1, 1], C[1, 2] = 2 * h_t / Q, -2 * h_t / y
    C[2, 1], C[2, 2] = dPdQ, dPdy
    C[3, 3] = p["f_nom"]
    return A, B, C, np.zeros((4, 3))


def linearize(p, y0: float | None = None, h_p0: float | None = None) -> dict:
    ss = steady_state(p, y0, h_p0)
    x0, u0 = ss["x0"], ss["u0"]
    A, B, C, D = numerical_jacobians(p, x0, u0)
    Aa, Ba, Ca, Da = analytic_jacobians(p, x0, u0)
    return {"A": A, "B": B, "C": C, "D": D, "x0": x0, "u0": u0, "y0": ss["y0"],
            "max_abs_diff_vs_analytic": float(max(np.abs(A - Aa).max(), np.abs(B - Ba).max(),
                                                  np.abs(C - Ca).max(), np.abs(D - Da).max())),
            "Tw": water_starting_time(p, x0)}


# ---------------------------------------------------------------- simulation
def simulate(p, x0, u_fn, t_end: float, n_out: int = 501):
    """Nonlinear simulation. u_fn(t) -> [y_cmd, P_load, Q_in]; y_cmd is clipped to [0, 1]."""
    def f(t, x):
        u = np.array(u_fn(t), float)
        u[0] = min(max(u[0], 0.0), 1.0)
        return rhs(x, u, p)

    sol = solve_ivp(f, (0.0, t_end), np.asarray(x0, float), method="Radau",
                    t_eval=np.linspace(0.0, t_end, n_out), rtol=1e-8,
                    atol=[1e-6, 1e-6, 1e-9, 1e-11, 1e-9])
    if not sol.success:
        raise RuntimeError(sol.message)
    return sol.t, sol.y.T


# -------------------------------------------------------------------- export
def export_state_space(outdir: Path, params: dict[str, Param], lin: dict) -> None:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for name in "ABCD":
        np.savetxt(outdir / f"{name}.csv", lin[name], delimiter=",", fmt="%.10e")
    eig = np.sort_complex(np.linalg.eigvals(lin["A"]))
    meta = {
        "model": "GBHP single generating unit, open-loop plant (no governor), rigid water column",
        "status": "SIMULATION MODEL. Not connected to the real plant. Not validated against real operating data.",
        "equations": "documentation/mathematical_model.md",
        "form": "dx/dt = A x + B u ; y = C x + D u  (deviation variables about the operating point)",
        "states": [dict(name=n, description=d, unit=u) for n, d, u in STATES],
        "inputs": [dict(name=n, description=d, unit=u) for n, d, u in INPUTS],
        "outputs": [dict(name=n, description=d, unit=u) for n, d, u in OUTPUTS],
        "operating_point": {
            "definition": "Normal pond level, gate at optimum opening (Q_opt/Q_full), unit in equilibrium (w=1, P_load=P_gen, Q_in=Q)",
            "x0": dict(zip([s[0] for s in STATES], map(float, lin["x0"]))),
            "u0": dict(zip([i[0] for i in INPUTS], map(float, lin["u0"]))),
            "y0": dict(zip([o[0] for o in OUTPUTS], map(float, lin["y0"]))),
            "water_starting_time_s": float(lin["Tw"]),
        },
        "linearization": {
            "method": "Numerical Jacobian, central differences, step = 1e-5*max(|z0|,1)",
            "check": "Compared with hand-derived analytic Jacobians (backend.model.analytic_jacobians)",
            "max_abs_diff_vs_analytic": lin["max_abs_diff_vs_analytic"],
            "D_note": "D is zero because the outputs depend on states only (the gate is a servo state, not a direct input).",
        },
        "eigenvalues": [{"re": float(e.real), "im": float(e.imag)} for e in eig],
        "parameters": [dict(key=q.key, description=q.description, value=q.value, unit=q.unit,
                            classification=q.classification, source=q.source) for q in params.values()],
        "known_limitations": [
            "Rigid water column; no water hammer / elasticity.",
            "Francis speed effects on flow and efficiency ignored; constant eta.",
            "Isolated-unit swing equation with load damping; no grid or network model.",
            "Brochure has a 290 MW vs 295 MW per-unit discrepancy; the model does not use either rating.",
        ],
    }
    (outdir / "state_space_model.json").write_text(json.dumps(meta, indent=2, sort_keys=False) + "\n")


def main() -> None:
    params = build_parameters()
    p = values(params)
    lin = linearize(p)
    export_state_space(ROOT / "exports", params, lin)
    print("Operating point:", dict(zip([o[0] for o in OUTPUTS], np.round(lin["y0"], 4))))
    print("Water starting time Tw = %.3f s" % lin["Tw"])
    print("Max |numerical - analytic| Jacobian difference: %.2e" % lin["max_abs_diff_vs_analytic"])
    print("Eigenvalues:", np.round(np.sort_complex(np.linalg.eigvals(lin["A"])), 6))
    print("Exported to", ROOT / "exports")


if __name__ == "__main__":
    main()
