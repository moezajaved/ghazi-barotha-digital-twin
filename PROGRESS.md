# PROGRESS
**Phase:** 0 (data + project setup) complete. Next: Phase 1.

## Done
- Brochure inspected (20 PDF pages); 63 parameters extracted with page numbers.
- Missing-parameter list written.
- Project folder, docs skeleton, git repo created.

## Files
source_data/{original_brochure.pdf, source_data_register.csv, missing_parameters.md, GBHP_brochure_data.xlsx}; README, PROGRESS, PROJECT_CONTEXT, CHANGELOG; documentation/*.md (stubs).

## Tests actually run
- Spreadsheet recalculation: 0 formula errors.
- Sanity calc P = rho*g*Q*H*eta with brochure 460 m3/s, 69 m, 94% -> 292.69 MW/unit (brochure: 290 rated, 295 full-gate). Simulated value, not brochure data.

## Blockers / open issues
- 290 vs 295 MW conflict (p.12 vs pp.4,7,17); working assumption: 290 rated, 295 full-gate max.
- "515v 3:18 KV" (p.12) garbled; unconfirmed.
- Brochure pp.4 and 5 identical; some text pages start mid-section.

## Exact next task
Phase 1: backend/model.py - single-unit state-space model (headpond level, penstock flow, gate servo, rotor speed/angle), linearise to A,B,C,D, tests in tests/test_model.py, export matrices to exports/.
