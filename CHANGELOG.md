# CHANGELOG
## 2026-10-12 (Phase 1)
- Added `backend/model.py`, `tests/test_model.py`, `pytest.ini`, `requirements.txt`. Why: single-unit model with state-space extraction.
- Generated `exports/` (A, B, C, D CSV and state_space_model.json). Why: required exportable matrices with metadata.
- Changed register schema: `classification` is now `published` for all rows; new `flag` column marks the 290/295 MW conflict (2 rows) and the unconfirmed voltage (1 row). Why: classification scheme requested (published/calculated/assumed/missing); no values changed. Count verified as 64 rows (earlier "63" was a miscount).
- Wrote documentation/{mathematical_model, assumptions_and_limitations, state_space_method, testing_and_validation}.md and rewrote README, PROGRESS, PROJECT_CONTEXT.

## 2026-10-12 (Phase 0)
- Created project structure, source data register, missing-parameter list, docs stubs, git repo. Why: persistent recovery files.
