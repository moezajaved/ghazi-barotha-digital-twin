# Testing and validation

## Phase 1: `python -m pytest` (run 2026-10-12; Python 3.13.16, numpy 2.5.3, scipy 1.18.1)
**Result: 16 passed in 1.40 s.**

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
