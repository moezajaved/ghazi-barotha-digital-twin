# Ghazi Barotha Digital Twin (simulation prototype)
University EE project: simulation-based model of the Ghazi Barotha Hydropower Project (1450 MW, Pakistan).
Not connected to the real plant and not validated against real operating data.

## Status
Phase 1 (data + mathematical model + state-space export) done and tested. See `PROGRESS.md`. Dashboard and 3D scene not built yet.

## Run (Windows, once Python 3 is installed from python.org; tick "Add Python to PATH")
```
cd Documents\Ghazi_Barotha_Digital_Twin
pip install -r requirements.txt
python -m pytest          # runs the 18 tests
python -m backend.model   # prints the operating point and writes exports\A.csv, B.csv, C.csv, D.csv, state_space_model.json
```

## Layout
`backend/model.py` model + linearisation + export; `tests/`; `exports/` generated matrices; `source_data/` brochure + parameter register;
`documentation/` equations, assumptions, method, testing; recovery files `PROGRESS.md`, `PROJECT_CONTEXT.md`, `CHANGELOG.md`.

## Data labelling
Every value is `published` (brochure, with page), `calculated`, or `assumed`; simulation results are labelled as simulated.
