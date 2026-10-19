# System architecture (Phase 2)
```
app.py (Streamlit + Plotly)  ->  backend/simulator.py  ->  backend/governor.py  ->  backend/model.py  ->  source_data/source_data_register.csv
   dashboard, buttons, graphs        stepping, history,          PI/droop, limits,        plant equations,        published brochure values
                                     input validation, CSV       closed-loop poles        Jacobians, export
```
- **Single source of truth:** every number on the dashboard comes from `Simulator`; no values are stored or faked in `app.py`.
- **Live updates:** while running, a Streamlit fragment (`@st.fragment(run_every=...)`) advances the model by one chunk per tick; Pause/Reset/Step/input
  changes cause a normal rerun. State lives in `st.session_state` (`sim`, `running`).
- **Why Streamlit + Plotly:** free, pure Python, one command to launch, no separate front-end build. Phase 3 (3D) will add a Three.js or Plotly 3D view.
- **Tests:** `tests/` (pytest: model, governor, simulator, headless dashboard) and the optional `tests/e2e_browser.py` (real browser).
