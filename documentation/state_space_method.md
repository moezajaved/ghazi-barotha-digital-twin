# State-space extraction

Form: `dx/dt = A x + B u`, `y = C x + D u`, in deviation variables about the operating point (x0, u0) of `mathematical_model.md`.

**Method:** numerical Jacobians of `rhs()` and `outputs()` by central differences, step `1e-5*max(|z0|,1)` (`backend.model.numerical_jacobians`).
**Independent check:** hand-derived analytic Jacobians (`analytic_jacobians`); the maximum absolute difference is 1.6e-7 (A[1,2] is about 619).

Matrix sizes: A 5x5, B 5x3, C 4x5, D 4x3 (D = 0 because the outputs depend on states only).

**Reproduce:** `python -m backend.model` writes `exports/A.csv, B.csv, C.csv, D.csv, state_space_model.json`
(CSV: no header, rows/columns in the order of the state/input/output lists in the JSON). Output is byte-identical across runs.
The linear model is valid for small deviations; tested against the nonlinear model for a +1% gate, +2 MW load, +5 m3/s inflow step (within 3% at 20 s).

# Phase 4: state-space at a selected operating point (`backend/state_space.py`, dashboard tab "State-space model")
**Are the matrices linearised around an operating point? Yes.** `exports/A.csv ... D.csv` are the Jacobians of the nonlinear plant
at ONE equilibrium: normal pond level 334 m (published), gate 400/460 = 0.8696 pu, Q = 400 m3/s, h_t = 69 m, P = 254.51 MW (calculated),
w = 1. They act on deviation variables (dx = x - x0, du = u - u0, dy = y - y0), not on absolute values.

What the tab / module adds:
- **Operating point:** nominal (= exports/) or "current simulation state". The latter uses the *equilibrium* with the current gate
  opening and pond level; a transient state (speed not 1 pu, power != load) is not an equilibrium, so it cannot be a linearisation
  point, and the tab says so. Gate openings at a limit (<= y_min 0.02 or >= 1.0 pu) are rejected with a reason: the model is not
  differentiable there.
- **Model:** plant only (open loop, 5 states, inputs y_cmd, P_load, Q_in; identical code path to Phase 1, so the nominal CSVs are
  identical to exports/) or plant + governor (closed loop, 6 states incl. integrator xi, inputs y_set, P_load, Q_in, ASSUMED governor
  settings). Closed-loop eigenvalues equal `governor.closed_loop_poles` (tested).
- **Export:** ZIP with A, B, C, D (CSV, same format as exports/) and state_space_model.json (states/inputs/outputs with units,
  operating point x0/u0/y0, eigenvalues, parameter sources, limitations). exports/ itself is not modified.
- **Linear vs nonlinear:** the linear model is driven with the input history of the current run (zero-order hold, scipy.signal.lsim)
  and compared with the nonlinear results. Measured (largest error / largest change of the run):

| Scenario (closed loop, nominal point) | Power | Frequency | Flow |
|---|---|---|---|
| Load step 254.5 -> 280 MW | 0.45 / 25.5 MW (1.8 %) | 0.035 / 2.08 Hz (1.7 %) | 0.45 / 40.6 m3/s (1.1 %) |
| Full load rejection to 0 MW | 40.3 / 243 MW (17 %) | 2.7 / 18.5 Hz (15 %) | 32 / 382 m3/s (8 %) |
| Overload 320 MW (gate saturates) | 27.8 / 37.2 MW (75 %) | 3.9 / 5.3 Hz (74 %) | 44 / 60 m3/s (74 %) |
| Governor OFF load step (open loop) | 0 | < 1e-6 Hz | 0 |

The last row is exact because with a fixed gate the flow and power do not change and only the (linear) swing equation acts.
**Limitations:** valid for small deviations only; gate, command and rate limits and the y_min floor are not in the linear model;
head and power are nonlinear in Q and y; rotor angle has a zero eigenvalue (no grid); same physical assumptions as the nonlinear
model. The matrices are a model of the *model*, not of the real plant; they are not validated against plant data.
