# State-space extraction

Form: `dx/dt = A x + B u`, `y = C x + D u`, in deviation variables about the operating point (x0, u0) of `mathematical_model.md`.

**Method:** numerical Jacobians of `rhs()` and `outputs()` by central differences, step `1e-5*max(|z0|,1)` (`backend.model.numerical_jacobians`).
**Independent check:** hand-derived analytic Jacobians (`analytic_jacobians`); the maximum absolute difference is 1.6e-7 (A[1,2] is about 619).

Matrix sizes: A 5x5, B 5x3, C 4x5, D 4x3 (D = 0 because the outputs depend on states only).

**Reproduce:** `python -m backend.model` writes `exports/A.csv, B.csv, C.csv, D.csv, state_space_model.json`
(CSV: no header, rows/columns in the order of the state/input/output lists in the JSON). Output is byte-identical across runs.
The linear model is valid for small deviations; tested against the nonlinear model for a +1% gate, +2 MW load, +5 m3/s inflow step (within 3% at 20 s).
