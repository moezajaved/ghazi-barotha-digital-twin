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

---
# Phase 2 (2026-10-19; Python 3.13.16, numpy 2.5.3, scipy 1.18.1, streamlit 1.65.0, plotly 7.1.0)
## Automated: `python -m pytest`  ->  **77 passed in ~10 s**
| File | Tests | Covers |
|---|---|---|
| tests/test_model.py | 18 | Phase 1 (unchanged) |
| tests/test_governor.py | 22 | settings validation (incl. bad Kb), equilibrium in both modes, closed-loop poles and damping, droop steady state vs independent prediction, governor vs open loop, command limits and anti-windup, gate rate limits, back-calculation term, overload regression, pond-mode pole vs constant-power estimate |
| tests/test_simulator.py | 27 | input validation, stepping, mass balance, reproducibility and reset, CSV export |
| tests/test_app.py | 10 | headless dashboard (Streamlit AppTest runs `app.py`): initial values, Step, Run vs independent backend calculation, governor toggle, Reset/Pause, per-tick advance, input change while running, overload, notices |
## Real browser: `tests/e2e_browser.py` (optional; Playwright + Chromium) -> **13/13 checks passed**
Run advances live; Pause stops mid-run; Resume; input changed while running; 320 MW overload (gate 1.000, 45.6 Hz); CSV download (761 rows, matches display);
Step (+5 s); Reset; governor OFF (46.8 Hz); parameter register; no exceptions. Screenshot: `reports/dashboard_phase2.png`.

## Defects found and fixed in Phase 2 (none touched published values or Phase 1 files/exports)
1. **Anti-windup chatter:** a 320 MW load (inputs allow up to 322.5 MW) made every ODE solver fail at t = 10.75 s. Cause: conditional integration slid on the saturation boundary. Fixed with back-calculation (continuous); regression tests added.
2. **Wrong test, not wrong model:** `test_pond_mass_balance` used the pre-step inflow stored in the t = 0 row (error exactly 25*0.25/A = 3.7e-6 m). Now integrates the inflow actually applied, with a 10x tighter tolerance.
3. **Charts invisible while running:** found only with real-browser tests (the headless tests passed). In the original blocking loop (a new chart element per refresh) the chart was blank in both mid-run screenshots and the element was detached in 12 of 12 sampling attempts. A fragment timer with a stable chart key alone did not fix it (Streamlit still repaints the chart from scratch each update: blank 29% of the time at a 0.25 s refresh). Measured blank fraction vs refresh interval: 0.25 s -> 29%, 0.6 s -> 3%, 1.0 s -> 0%. Default set to 0.6 s with 5 simulated seconds per refresh.
4. Legend overlapped the axis title (moved above the graphs). A tuning claim in a docstring was re-measured and its definition stated (within +/-0.05 Hz after about 22 s).
Also noted: the slightly positive closed-loop pond pole (explained and now tested), and the t = 0 history row holding pre-step inputs.

## Not shown
Validation against the real plant: none (no operating data). Governor gains are educational assumptions, tuned only for damping on the assumed plant.
Windows launch was not run on Windows; it was run here on Linux with the same commands (`python -m streamlit run app.py`).

---
# Phase 3 (2026-10-21; same versions as Phase 2)
## Automated: `python -m pytest` -> **142 passed in ~20 s** (77 Phase 1-2, unchanged and all passing, + 65 new)
| File | Tests | Covers |
|---|---|---|
| tests/test_plant3d.py | 57 | mesh primitives (box, cylinder, merge, validation, bad input); geometry equals published register values (5 units, D, L, 334 m, 460 m3/s); calculated values (area, run); provenance classes and sources; SceneState from simulator; flow-marker advection and tracer; figure traces, no NaN, headpond surface = h_p; JSON payload; camera presets; true-proportion aspect ratio; one flow tracer per live penstock |
| tests/test_app_3d.py | 8 | headless app: 3 tabs render; values given to the 3D view equal the simulator state (t, h_p, Q, y, y_cmd, w, f, P_gen, h_t, Q_in) at start, after Step, during and after Run, after Reset; advection = 5 s * 400/A; replicate toggle; camera preset applied once |
## Real browser (Chromium + Playwright, software WebGL)
- `tests/e2e_browser_3d.py` -> **12/12 passed:** component loads; Plotly from the local file; WebGL scene drawn (16 traces); 3D values = dashboard indicators at t = 0 and after the run;
  readout panel shows the model values; 3D view refreshes during Run (t = 0, 5, 10, 15, 20, 25, 35 s sampled); frequency dips under +25 MW load (49.79 Hz);
  user camera kept across live updates (change 2e-16); camera preset moves the camera; no page errors; **no internet requests**. Screenshots: `reports/plant3d_phase3*.png`.
- Phase 2 regression `tests/e2e_browser.py` re-run with the tabbed layout -> **13/13 passed**.
- Chart blanking re-measured with the 3D fragment also running: 0 of 153 samples blank over 30 s (Simulation tab, default 0.6 s refresh).
## Issues found and fixed during Phase 3
1. Existing test `test_initial_render` failed after my first integration (extra "Apply preset" button; title changed). The test was not changed: the preset now applies on selection (no extra button) and the title keeps "single-unit".
2. Mixed-type `value` column in the provenance table crashed Streamlit's dataframe conversion (pyarrow); values are shown as text.
3. Placing the 3D view in a normal tab would have frozen it during Run (only the fragment re-executes); it now has its own fragment. Verified in the real browser.
4. Overview camera cut off the barrage; widened. In-scene readout text was unreadable; added an HTML readout panel bound to the same values.
## Not shown
Not run on Windows (Linux, same commands). No validation of geometry or behaviour against the real plant.
