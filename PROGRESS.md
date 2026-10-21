# PROGRESS
**Phase:** 4 (scenarios, state-space integration, export, testing) COMPLETE. Phases 0-3 complete. Next: Phase 5 (final report, demonstration guide).

## Done (Phase 4, 2026-10-22)
- 5 one-click scenarios (sidebar): normal operation, load step (+10 %), sudden load rejection, overload, governor ON vs OFF. Each is an input
  schedule run on the real model + governor; results never stored or drawn separately. Assumed scenario values labelled.
- Validation: scenario inputs rejected with a message (never clipped); over-capacity load warned; result checks after each run (governor/gate
  limits, gate floor, rate limit, speed outside 0.9-1.1 pu, pond above spillway crest, head rise, NaN); solver failures keep partial results.
- State-space tab: matrices at the nominal point (= exports/) or at the current-gate equilibrium, open or closed loop, eigenvalues, ZIP export,
  linear vs nonlinear comparison chart and error table. Limitations documented.
- Results package ZIP: results.csv (named columns with units, governor-OFF reference rows), metadata.json (settings, assumptions, sources,
  warnings, versions), README.txt. Original CSV download kept.
- `check_setup.py` installation check for Windows users.

## Files created/changed this phase
New: backend/{scenarios,state_space}.py, ui/{__init__,scenario_panel,state_space_tab}.py, check_setup.py, tests/{test_scenarios,test_state_space,
test_app_phase4,test_check_setup,e2e_browser_phase4}.py, reports/phase4_governor_compare.png, reports/phase4_state_space.png.
Changed: app.py; tests/test_app.py and tests/test_app_3d.py (exact button/tab lists extended); README, PROGRESS, PROJECT_CONTEXT, CHANGELOG,
documentation/{state_space_method,assumptions_and_limitations,system_architecture,testing_and_validation,user_manual}.md.
Unchanged: backend/{model,governor,simulator,plant3d,plant3d_component,scene_geometry}.py, frontend/, exports/, source_data/.

## Tests actually run (2026-10-22, Linux)
- `python -m pytest`: **210 passed in ~100 s** (142 earlier + 68 new). `python check_setup.py`: 7/7 PASS.
- Browser (Chromium): `e2e_browser_phase4.py` **16/16**, `e2e_browser.py` **13/13**, `e2e_browser_3d.py` **12/12**.
- Not run on Windows (no Windows machine here). User confirmed Phase 3 runs on Windows.

## Known issues / limitations
- Full load rejection leaves the model's valid speed range (68.5 Hz peak): flagged in the app; no overspeed protection / trip / speed-dependent
  turbine model. Linear model diverges for rejection (~15-17 %) and overload (~75 %), by design of linearisation; documented.
- Comparison chart only for the nominal point and a run started from Reset with matching governor mode.
- All earlier limitations apply (assumed governor/dynamics, single unit, schematic 3D layout, no validation, 290/295 MW conflict, garbled voltage).

## Exact next task
Phase 5: final technical report and demonstration guide (methods, equations, data provenance table, results of the 5 scenarios with figures
exported from the app, state-space results and linear-vs-nonlinear comparison, testing summary, limitations, references to brochure pages),
plus a short presentation outline. No new simulation features unless required by the report.
