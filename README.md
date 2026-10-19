# Ghazi Barotha Digital Twin (simulation prototype)
University EE project: simulation-based model of the Ghazi Barotha Hydropower Project (1450 MW, Pakistan).
Not connected to the real plant and not validated against real operating data.

## Status
Phase 1 (model + state-space export) and Phase 2 (PI/droop governor + Streamlit dashboard) done and tested. See `PROGRESS.md`. 3D scene not built yet (Phase 3).

## Run (Windows, once Python 3 is installed from python.org; tick "Add Python to PATH")
```
cd Documents\Ghazi_Barotha_Digital_Twin
pip install -r requirements.txt
python -m pytest          # runs the 77 tests
python -m streamlit run app.py   # starts the dashboard (opens http://localhost:8501); stop with Ctrl+C
python -m backend.model   # prints the operating point and writes exports\A.csv, B.csv, C.csv, D.csv, state_space_model.json
```

## Layout
`app.py` dashboard (Streamlit + Plotly); `backend/model.py` plant + linearisation + export; `backend/governor.py` PI/droop governor; `backend/simulator.py` stepping engine; `tests/`; `exports/` generated matrices; `source_data/` brochure + parameter register;
`documentation/` equations, assumptions, method, testing; recovery files `PROGRESS.md`, `PROJECT_CONTEXT.md`, `CHANGELOG.md`.

## Data labelling
Every value is `published` (brochure, with page), `calculated`, or `assumed`; simulation results are labelled as simulated.

Tested with Python 3.13, streamlit 1.65.0, plotly 7.1.0, numpy 2.5.3, scipy 1.18.1. Usage guide: `documentation/user_manual.md`.
