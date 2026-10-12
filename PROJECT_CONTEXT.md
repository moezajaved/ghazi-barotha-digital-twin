# PROJECT_CONTEXT
**Objective:** interactive 3D digital twin prototype + dynamic dashboard + state-space model (dx/dt=Ax+Bu, y=Cx+Du) of Ghazi Barotha; teacher brochure is primary source.
**Tools (all free):** Python (NumPy/SciPy/python-control), JS + Three.js + uPlot (CDN, no build), Git. Target machine: Windows laptop.
**Phases:** 0 data/setup, 1 Python state-space, 2 JS sim engine (RK4, PI governor), 3 dashboard, 4 Three.js scene, 5 integration/report.
**Source-data rules:** never invent plant data; never replace a brochure value with an assumption without logging it in CHANGELOG; tag Brochure/Assumption/Simulated.
**Key facts:** see source_data/source_data_register.csv. Working assumption: 290 MW rated, 295 MW full-gate.
**Model equations/state definitions:** TBD in Phase 1 (documentation/mathematical_model.md).
**Resuming in a new chat:** upload this folder (or at least README.md, PROGRESS.md, PROJECT_CONTEXT.md, source_data/), then say "Resume from PROGRESS.md". Inspect files first; do not redo completed work.
