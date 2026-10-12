# CHANGELOG
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
