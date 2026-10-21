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

# Phase 3 additions: 3D plant view
```
app.py tab "3D plant"  --view3d() fragment-->  backend/plant3d.py  --uses-->  backend/scene_geometry.py (mesh primitives, pure numpy)
        |                                        SceneState.from_simulator(sim)   build_geometry() <- source_data register (published values)
        v                                        build_figure(state, geometry)     camera_presets(), provenance_rows()
backend/plant3d_component.py  ->  frontend/plant3d/index.html (local Streamlit component, no build step; plotly.min.js copied from the installed plotly package)
```
- **Technology choice:** Plotly 3D (Mesh3d/Scatter3d) inside a small local Streamlit component. Plotly is already a dependency (no new
  install, no download, works offline, runs in any browser on Windows). PyVista/VTK was rejected (large native dependency, desktop-window
  or extra server for web embedding); Three.js was rejected (hand-written JS scene, separate asset pipeline, more to maintain for a beginner).
  The custom component exists only to update the figure *in place* with `Plotly.react`, so the user's rotation/zoom survives live updates
  (a plain `st.plotly_chart` would reset or flicker the 3D camera each tick).
- **Data flow:** `view3d()` is a second `st.fragment` on the same timer as `live()`. `live()` advances the `Simulator`; `view3d()` only reads it
  (`SceneState.from_simulator`) and builds the figure. The 3D view is therefore at most one tick behind the indicators, and identical when stopped.
  The exact dict shown is stored as `st.session_state.view3d_summary` (tests compare it with the simulator) and sent to the browser as `window.__summary`.
- **Visual bindings (all from the simulation):** headpond water surface = h_p; penstock colour = Q/460; flow markers advance by the integral of Q/A
  (real bulk velocity); green bar = gate y; turbine colour = y; generator colour = P_gen/292.7 MW; power lines colour = P_gen; readout panel =
  t, h_p, Q, Q/A, y, w, P_gen, f, h_t. Units 2-5 replicate unit 1 (identical-unit assumption) or can be shown idle.
- **Cost:** ~63 ms per figure build, ~72 KB per update (measured).

# Phase 4 additions
```
app.py sidebar  -> ui/scenario_panel.py -> backend/scenarios.py (build_scenario: validation; ScenarioPlayer: input schedule; assess; results_zip)
app.py live()   -> ScenarioPlayer.advance(sim, chunk) -> Simulator.step (split exactly at event times)
app.py tab "State-space model" -> ui/state_space_tab.py -> backend/state_space.py (linearize_at, export_zip, compare_with_run) -> backend/model.py
check_setup.py  -> quick installation check (no Streamlit needed)
```
- A scenario is only a schedule of inputs (load events, governor mode, duration). Results always come from `Simulator`; tests check that a
  scenario equals stepping the Simulator by hand with the same inputs (identical arrays).
- While a scenario is active the manual sidebar inputs are disabled (shown, not used); Exit returns to manual mode. Reset restarts the scenario.
- The governor-OFF reference of the comparison scenario is computed by the same model when the scenario starts (about 0.1 s).
- `backend/` still has no Streamlit imports; `ui/` only displays.
