# PROGRESS
**Phase:** 3 (interactive 3D plant) COMPLETE. Phases 0-2 complete. Next: Phase 4 (integration, scenarios, testing).

## Done (Phase 3, 2026-10-21)
- 3D plant tab in `app.py`, built with Plotly 3D in a local Streamlit component (`frontend/plant3d/index.html`, offline, keeps the user's camera during live updates).
- `backend/plant3d.py`: geometry with provenance (published from the register with page / calculated / schematic), `SceneState.from_simulator`, `build_figure`, camera presets. `backend/scene_geometry.py`: mesh primitives.
- Bound to the model: headpond level, flow (colour + advected markers + tracer), gate (bar + turbine colour), speed, power (generator/line colour), frequency, head; readout panel. `view3d()` fragment refreshes during Run.
- Shows: barrage (20 bays) and pool, power channel (published section, compressed length), headpond, intake, 5 penstocks (D 10.6 m, L 222 m), powerhouse, 5 turbines + generators, transformers, 500 kV switchyard and lines, tailrace.
- No new dependencies. Phase 1-2 code, exports, register and tests unchanged.

## Files created/changed this phase
New: backend/{plant3d,plant3d_component,scene_geometry}.py, frontend/plant3d/index.html, tests/{test_plant3d,test_app_3d,e2e_browser_3d}.py, reports/plant3d_phase3.png, reports/plant3d_phase3_powerhouse.png.
Changed: app.py (tabs + 3D tab), .gitignore (plotly.min.js), README, PROGRESS, PROJECT_CONTEXT, CHANGELOG, documentation/{system_architecture,assumptions_and_limitations,testing_and_validation,user_manual}.md.

## Tests actually run (2026-10-21, Linux)
- `python -m pytest`: **142 passed in ~20 s** (77 existing + 65 new).
- `tests/e2e_browser_3d.py` (Chromium): **12/12 passed**. `tests/e2e_browser.py` (Phase 2 regression): **13/13 passed**.
- Not run on Windows.

## Known issues / limitations
- Layout, unit spacing, building and machine sizes are schematic (brochure has no site plan); labelled and listed in the provenance table.
- Single simulated unit; units 2-5 replicate it. No barrage/channel dynamics.
- Flow markers sampled once per refresh (white markers can look still; orange tracer shows travel). Labels crowd in Overview.
- All Phase 2 limitations still apply (assumed governor/dynamics, no validation, 290/295 MW conflict, garbled voltage).

## Exact next task
Phase 4: integration and scenarios. Suggested: preset demo scenarios (load step, load rejection, overload, governor off) with one click; scenario result export (CSV + state-space at the current operating point, re-linearised on demand); multi-unit option (5 independent units sharing the headpond) only if kept clearly labelled; Windows install check script; tidy final tests. Keep all existing tests passing.
