# Ghazi Barotha Digital Twin (simulation prototype)
University EE project: simulation-based model of the Ghazi Barotha Hydropower Project (1450 MW, Pakistan).
Not connected to the real plant and not validated against real operating data.

## Status
Phases 1-3 done and tested: model + state-space export, PI/droop governor + Streamlit dashboard, and an interactive 3D plant view driven by the simulation. See `PROGRESS.md`.

## Run (Windows, once Python 3 is installed from python.org; tick "Add Python to PATH")
```
cd Documents\Ghazi_Barotha_Digital_Twin
pip install -r requirements.txt
python -m pytest          # runs the 142 tests
python -m streamlit run app.py   # starts the dashboard + 3D plant tab (opens http://localhost:8501); stop with Ctrl+C
python -m backend.model   # prints the operating point and writes exports\A.csv, B.csv, C.csv, D.csv, state_space_model.json
```

## Layout
`app.py` dashboard (Streamlit + Plotly; tabs Simulation / 3D plant / Parameter register); `backend/plant3d.py` 3D scene from simulator state + geometry provenance; `backend/scene_geometry.py` mesh primitives; `backend/plant3d_component.py` + `frontend/plant3d/index.html` offline 3D component; `backend/model.py` plant + linearisation + export; `backend/governor.py` PI/droop governor; `backend/simulator.py` stepping engine; `tests/`; `exports/` generated matrices; `source_data/` brochure + parameter register;
`documentation/` equations, assumptions, method, testing; recovery files `PROGRESS.md`, `PROJECT_CONTEXT.md`, `CHANGELOG.md`.

## Data labelling
Every value is `published` (brochure, with page), `calculated`, or `assumed`; simulation results are labelled as simulated.

Tested with Python 3.13, streamlit 1.65.0, plotly 7.1.0, numpy 2.5.3, scipy 1.18.1. Usage guide: `documentation/user_manual.md`.

3D geometry: elevations, penstock and channel dimensions, counts are published (brochure); the plan layout and machine sizes are schematic (labelled). No internet needed at runtime (plotly.js is copied from the installed package on first launch).
