# CHANGELOG
## 2026-10-19 (Phase 2)
- Added `backend/governor.py` (PI/droop, limits, rate limits, back-calculation anti-windup; Kb added to settings), `backend/simulator.py`, `app.py` (Streamlit + Plotly), `.streamlit/config.toml`. Why: governed single unit and a working dashboard.
- Fixed: conditional anti-windup chattered at saturation (solvers failed at load > full-gate capacity) -> back-calculation. Fixed `test_pond_mass_balance` (used pre-step inflow). Dashboard charts were blank while running -> fragment timer, stable chart key, default refresh 0.6 s (measured), legend moved.
- Tests 18 -> 77; added optional `tests/e2e_browser.py` (13 checks, real browser); `reports/dashboard_phase2.png`.
- requirements.txt: + plotly, streamlit. Docs: mathematical_model, assumptions_and_limitations, testing_and_validation, system_architecture, user_manual, README. Phase 1 files and exports unchanged.

## 2026-10-12 (Phase 1 review)
- `backend/model.py`: `steady_state()` raises ValueError for y0 outside [y_min, 1] or h_p0 <= tailwater (previously produced a non-equilibrium silently); added swing-equation note to JSON limitations.
- Tests: 16 -> 18 (calibration identity separated from the model's full-gate equilibrium 291.67 MW; invalid steady-state inputs).
- Docs corrected: 292.69 MW described as a calibration identity; pond eigenvalue -1.7e-6; review section in testing_and_validation.md. No published value changed.
## 2026-10-12 (Phase 1)
- Added `backend/model.py`, `tests/test_model.py`, `pytest.ini`, `requirements.txt`. Why: single-unit model with state-space extraction.
- Generated `exports/` (A, B, C, D CSV and state_space_model.json). Why: required exportable matrices with metadata.
- Changed register schema: `classification` is now `published` for all rows; new `flag` column marks the 290/295 MW conflict (2 rows) and the unconfirmed voltage (1 row). Why: classification scheme requested (published/calculated/assumed/missing); no values changed. Count verified as 64 rows (earlier "63" was a miscount).
- Wrote documentation/{mathematical_model, assumptions_and_limitations, state_space_method, testing_and_validation}.md and rewrote README, PROGRESS, PROJECT_CONTEXT.

## 2026-10-12 (Phase 0)
- Created project structure, source data register, missing-parameter list, docs stubs, git repo. Why: persistent recovery files.
