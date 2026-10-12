# Testing and validation

## Phase 1: `python -m pytest` (run 2026-10-12; Python 3.13.16, numpy 2.5.3, scipy 1.18.1)
**Result: 16 passed in 1.40 s.** After the engineering review (below): **18 passed in 1.17 s.**

## Engineering review (2026-10-12)
Checked: dimensional consistency of every equation (all terms reduce to m/s, m3/s2, 1/s, 1/s, rad/s as appropriate); matrix sizes (A 5x5, B 5x3, C 4x5, D 4x3, exported files reloaded and matched);
independent closed-form hand values for P(400,69) = 254.511 MW and for A[1,0], A[1,1], A[1,2], A[3,1], A[3,2], A[3,3], B[3,1] (all agree to 6 digits); eigenvalues.
Findings and fixes:
1. 292.69 MW is a calibration identity, not a model result; the model's full-gate equilibrium is 291.67 MW. Docs corrected; tests now separate the two.
2. `steady_state()` silently accepted gate y0 > 1 (residual 118, not an equilibrium). Now raises ValueError; test added.
3. Pond eigenvalue is -1.69e-6 (docs said -2e-6, a rounding). Corrected.
4. Swing equation uses P_gen (net of generator losses) as input power: documented as a simplification, no code change.
No error found in the equations, power calculation, operating point, matrix dimensions or published values.

| Area | Tests |
|---|---|
| Register | 64 unique rows, all pdf_page 1-20, all `published`; 290/295 MW conflict and garbled voltage preserved and flagged |
| Parameters | Published values equal the register (69 m, 460/400 m3/s, 222 m, 10.6 m, 94%, 25.5 Mm3, 334 m); published values cannot be overridden |
| Steady state | Residual of rhs < 1e-9; Q0 = 400, h_t0 = 69, P0 = 0.94*rho*g*400*69; full-gate hand calc 292.687 MW |
| Linearisation | Numerical = analytic Jacobian (< 1e-6); shapes; D = 0; one zero eigenvalue (angle), all others negative |
| Linear vs nonlinear | Small step response agrees within 3% (Q, w, P) |
| Physics | Gate opening is non-minimum phase; load drop raises frequency; gate command clipped to 1 |
| Export | Files and shapes, CSV round-trip, metadata contents, byte-identical on re-run |

## What this does and does not show
Verification: the code matches hand calculations and its own analytic derivation. Validation: **none**. There is no real operating data,
so no claim is made that the model reproduces the real plant. The 292.69 MW figure is a calculated estimate.
