# PROGRESS
**Phase:** 1 (data + mathematical model + state-space) COMPLETE. Next: Phase 2 (dashboard).

## Done
- Register verified from the CSV itself: 64 rows (the earlier "63" was a miscount); schema now has `classification` = published and a `flag` column (2 conflict rows, 1 unconfirmed row).
- `backend/model.py`: single-unit model, steady state, numerical + analytic Jacobians, nonlinear `simulate()`, export.
- Exports generated: `exports/A.csv, B.csv, C.csv, D.csv, state_space_model.json`.
- Docs written: mathematical_model, assumptions_and_limitations, state_space_method, testing_and_validation.

## Files created/changed this phase
backend/{__init__,model}.py, tests/test_model.py, pytest.ini, requirements.txt, exports/*, source_data/source_data_register.csv (schema), documentation/*, README, PROGRESS, PROJECT_CONTEXT, CHANGELOG.

## Tests actually run
`python -m pytest`: 16 passed in 1.40 s (2026-10-12). `python -m backend.model` ran; Jacobian numeric-vs-analytic max diff 1.6e-7.
Calculated/simulated (not measured): P0 = 254.51 MW at Q=400 m3/s, 69 m; full-gate calc 292.69 MW; Tw = 1.487 s.

## Known issues
- Open loop has no governor: a 20 MW load drop pushes frequency to ~53 Hz. Needs a PI/droop governor (Phase 2).
- Several dynamic parameters are assumptions (see assumptions_and_limitations.md); no validation data.
- 290 vs 295 MW conflict and the garbled voltage remain unresolved and are not used by the model.
- Project exists only in Claude's temporary cloud workspace until the user downloads the zip.

## Exact next task
Phase 2: add a PI governor (assumed gains, documented) in `backend/`, then a minimum local dashboard (Plotly graphs; start/pause/reset/step; inputs: gate/load/inflow; live indicators) driven by `backend.model.simulate`/`rhs`. Add input validation and tests. Update recovery files.
