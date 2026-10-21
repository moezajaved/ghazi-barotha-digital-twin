"""GBHP digital twin: simulation dashboard + 3D plant view (Phase 2 + Phase 3).
Run with:  python -m streamlit run app.py

Every number shown comes from backend.simulator / backend.governor / backend.model. SIMULATION ONLY.
"""
import os

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from backend.governor import GOVERNOR_ASSUMPTIONS, GovernorSettings
from backend.plant3d import (Geometry, SceneState, build_figure, build_geometry, camera_presets,
                              figure_payload, provenance_rows)
from backend.plant3d_component import plant3d_view
from backend.simulator import Simulator, channel_share_per_unit, validate_inputs

REFRESH = max(float(os.environ.get("GBHP_REFRESH_SECONDS", "0.6")), 0.05)
# Wall-clock seconds between live updates. Measured in Chromium: the chart is repainted from scratch on each update and is
# blank for a short time, so 0.25 s left it blank ~29% of the time, 0.6 s ~3%, 1.0 s 0%.

st.set_page_config(page_title="GBHP Digital Twin", layout="wide")

# ------------------------------------------------------------------ session
if "sim" not in st.session_state:
    st.session_state.sim = Simulator()
    st.session_state.running = False
    st.session_state.cam_preset = "Overview"
    st.session_state.cam_nonce = 0   # incremented each time a preset is applied
if "geom3d" not in st.session_state:
    st.session_state.geom3d = build_geometry()  # loads once; brochure values don't change at runtime
sim: Simulator = st.session_state.sim
geom3d: Geometry = st.session_state.geom3d
p = sim.p
u0 = sim.ss["u0"]

st.title("Ghazi Barotha Hydropower: single-unit simulation dashboard and 3D plant")
st.caption("Educational simulation of one generating unit. Values are SIMULATED from the model in `backend/`; parameters are "
           "published (brochure), calculated or assumed (see the register below). Not connected to the real plant and not "
           "validated against operating data.")

# ------------------------------------------------------------------- inputs
with st.sidebar:
    st.header("Inputs")
    gov_on = st.toggle("PI/droop governor", value=True, key="gov_on",
                       help="On: the gate command below is the governor set-point (load/speed reference). "
                            "Off: it is applied directly to the gate (open loop).")
    y_set = st.number_input("Gate command / set-point (pu)", 0.0, 1.0, float(u0[0]), 0.01, format="%.3f", key="y_set")
    P_load = st.number_input("Electrical load at nominal frequency (MW)", 0.0, float(p["S_base"]), float(u0[1]), 1.0, format="%.2f", key="P_load")
    Q_in = st.number_input("Inflow to unit (m3/s)", 0.0, float(p["Q_full"]), float(u0[2]), 5.0, format="%.1f", key="Q_in")
    duration = st.number_input("Simulation duration (s)", 1.0, 3600.0, 120.0, 10.0, format="%.0f", key="duration")
    chunk = st.selectbox("Simulated seconds per refresh", [1, 2, 5, 10], index=2, key="chunk",
                         help="Larger = faster run, coarser live updates. Results are the same (the solver is accurate at any size).")
    step_dt = st.selectbox("Step button advances (s)", [1, 5, 10, 30], index=1, key="step_dt")
    with st.expander("Governor settings (ASSUMED, not brochure data)"):
        g0 = sim.gov
        R = st.number_input("Droop R (pu/pu)", 0.01, 0.10, g0.R, 0.005, format="%.3f", key="g_R")
        Kp = st.number_input("Kp (pu/pu)", 0.0, 10.0, g0.Kp, 0.1, key="g_Kp")
        Ki = st.number_input("Ki (pu/pu/s)", 0.0, 5.0, g0.Ki, 0.05, key="g_Ki")
        ro = st.number_input("Gate opening rate limit (pu/s)", 0.01, 1.0, g0.rate_open, 0.01, key="g_ro")
        rc = st.number_input("Gate closing rate limit (pu/s)", 0.01, 1.0, g0.rate_close, 0.01, key="g_rc")
    gov = GovernorSettings(R=R, Kp=Kp, Ki=Ki, rate_open=ro, rate_close=rc)

errors = validate_inputs(p, y_set, P_load, Q_in, duration) + gov.validate()
if errors:
    for e in errors:
        st.error(e)
else:
    sim.gov = gov
    if Q_in > channel_share_per_unit() + 1e-9:
        st.info(f"Inflow {Q_in:.0f} m3/s exceeds this unit's share of the power channel design flow "
                f"({channel_share_per_unit():.0f} m3/s, brochure p.12); the headpond supplies the difference and drains.")

# ------------------------------------------------------------------ buttons
c1, c2, c3, c4, _ = st.columns([1, 1, 1, 1, 6])
run = c1.button("Run", key="run", type="primary", disabled=bool(errors))
pause = c2.button("Pause", key="pause")
step = c3.button("Step", key="step", disabled=bool(errors))
reset = c4.button("Reset", key="reset")

if reset:
    sim.reset(governor_on=gov_on)
    st.session_state.running = False
if pause:
    st.session_state.running = False
if step and not errors:
    st.session_state.running = False
    try:
        sim.step(step_dt, y_set, P_load, Q_in, gov_on)
    except (ValueError, RuntimeError) as exc:
        st.error(str(exc))
if run and not errors:
    if sim.t >= duration - 1e-9:
        st.warning("Duration already reached: press Reset or increase the duration.")
    else:
        st.session_state.running = True

# ------------------------------------------------------------------- display
if errors:
    st.session_state.running = False


def render() -> None:
    a = sim.arrays()
    last = sim.latest()
    ref = sim.ss["y0"]  # Q, h_t, P, f at the starting equilibrium
    k = st.columns(7)
    k[0].metric("Time (s)", f"{last['t']:.1f}")
    k[1].metric("Flow (m3/s)", f"{last['Q']:.1f}", f"{last['Q'] - ref[0]:+.1f}")
    k[2].metric("Net head (m)", f"{last['h_t']:.2f}", f"{last['h_t'] - ref[1]:+.2f}")
    k[3].metric("Power (MW)", f"{last['P_gen']:.1f}", f"{last['P_gen'] - ref[2]:+.1f}")
    k[4].metric("Frequency (Hz)", f"{last['f']:.3f}", f"{last['f'] - ref[3]:+.3f}")
    k[5].metric("Gate (pu)", f"{last['y']:.3f}", f"{last['y'] - sim.ss['x0'][2]:+.3f}")
    k[6].metric("Pond level (m)", f"{last['h_p']:.3f}", f"{last['h_p'] - sim.ss['x0'][0]:+.3f}")
    fig = make_subplots(rows=3, cols=2, shared_xaxes=True, vertical_spacing=0.09, horizontal_spacing=0.08,
                        subplot_titles=("Power (MW)", "Frequency (Hz)", "Flow (m3/s)", "Net head (m)",
                                        "Gate position (pu)", "Pond level (m)"))
    blue, orange, grey = "#2563eb", "#d97706", "#6b7280"
    t = a["t"]
    fig.add_scatter(x=t, y=a["P_gen"], name="Generated power", line=dict(color=blue), row=1, col=1)
    fig.add_scatter(x=t, y=a["P_load"], name="Electrical load", line=dict(color=grey, dash="dash"), row=1, col=1)
    fig.add_scatter(x=t, y=a["f"], name="Frequency", line=dict(color=blue), showlegend=False, row=1, col=2)
    fig.add_scatter(x=t, y=a["Q"], name="Flow", line=dict(color=blue), showlegend=False, row=2, col=1)
    fig.add_scatter(x=t, y=a["h_t"], name="Net head", line=dict(color=blue), showlegend=False, row=2, col=2)
    fig.add_scatter(x=t, y=a["y"], name="Gate (actual)", line=dict(color=blue), row=3, col=1)
    fig.add_scatter(x=t, y=a["y_cmd"], name="Gate command", line=dict(color=orange, dash="dot"), row=3, col=1)
    fig.add_scatter(x=t, y=a["h_p"], name="Pond level", line=dict(color=blue), showlegend=False, row=3, col=2)
    fig.update_layout(height=720, margin=dict(l=10, r=10, t=70, b=10), uirevision="keep",
                      legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="left", x=0), template="plotly_white")
    fig.update_xaxes(title_text="Time (s)", row=3)
    st.plotly_chart(fig, width="stretch", key="fig")   # one stable element: updated in place, no remount flicker


# While running, this fragment re-executes by itself every REFRESH seconds (Streamlit's own timer) and advances the
# model by `chunk` simulated seconds per tick. Pause/Reset/Step/input changes trigger a normal full rerun instead.
@st.fragment(run_every=REFRESH if st.session_state.running else None)
def live() -> None:
    if st.session_state.running and not errors:
        try:
            sim.step(min(float(chunk), duration - sim.t), y_set, P_load, Q_in, gov_on)
        except (ValueError, RuntimeError) as exc:
            st.session_state.running = False
            st.error(str(exc))
            st.rerun()
        if sim.t >= duration - 1e-9:
            st.session_state.running = False
            st.rerun()          # full rerun: stops the timer, re-enables the download button
    render()
    if st.session_state.running:
        st.caption("Running. Press Pause to stop; inputs can be changed while running.")
    else:
        st.caption("Run finished." if sim.t >= duration - 1e-9 and sim.t > 0 else
                   "Stopped. Press Run or Step." if sim.t == 0 else f"Paused/stopped at t = {sim.t:.1f} s.")


# The 3D view has its own fragment on the same timer, so it also refreshes during a run (a fragment only re-executes
# its own body). It only READS the simulator (live() advances it), so at most one tick behind the indicators.
@st.fragment(run_every=REFRESH if st.session_state.running else None)
def view3d(replicate: bool) -> None:
    state = SceneState.from_simulator(sim, geom3d.pen_area)
    cams = camera_presets(geom3d)
    cam = cams.get(st.session_state.cam_preset, cams["Overview"])
    summary = state.summary(geom3d, replicate=replicate)
    st.session_state.view3d_summary = summary          # exactly what the 3D view was given (checked by tests)
    plant3d_view(figure_payload(build_figure(state, geom3d, replicate=replicate)), cam, st.session_state.cam_nonce,
                 summary, height=680)


tab_sim, tab_3d, tab_reg = st.tabs(["Simulation", "3D plant", "Parameter register"])

with tab_sim:
    live()
    st.caption("The load input is the load at nominal frequency. The model includes load damping D (assumed), so the unit's steady "
               "generation differs from it by D*S_base*(w-1) when frequency is off-nominal; this is expected, not an error.")
    st.download_button("Download results (CSV)", sim.to_csv(), "gbhp_simulation.csv", "text/csv", key="download",
                       disabled=bool(st.session_state.running), help="Pause (or let the run finish) to download the full history.")

with tab_3d:
    _3d_cols = st.columns([3, 1])
    with _3d_cols[1]:
        st.markdown("**Camera preset**")
        _presets = list(camera_presets(geom3d).keys())
        _selected = st.selectbox("Jump to", _presets, index=_presets.index(st.session_state.cam_preset), key="cam_sel",
                                 help="Choosing a preset moves the camera once; afterwards your own rotation/zoom is kept.")
        if _selected != st.session_state.cam_preset:
            st.session_state.cam_preset = _selected
            st.session_state.cam_nonce += 1
        st.markdown("---")
        replicate = st.toggle("Show all 5 units", value=True, key="replicate",
                              help="All 5 units show the simulated unit 1 state. Turn off to show only unit 1 and the other 4 as idle.")
        st.markdown("---")
        st.caption("Penstock colour: flow 0 to 460 m3/s  \nGenerator colour: power 0 to 292.7 MW (estimate)  \nGreen bar: gate 0 to 1 pu  \n\n"
                   "Drag to rotate · scroll to zoom · right-drag to pan.\n\n"
                   "**Geometry provenance:** labels show [published] / [calculated] / [schematic] / [simulated].\n\n"
                   "All simulated values come from `backend.simulator` at the current step — nothing is invented.")
        with st.expander("Geometry provenance table"):
            st.dataframe([{**r, "value": str(r["value"])} for r in provenance_rows(geom3d)], hide_index=True, width="stretch")
    with _3d_cols[0]:
        view3d(replicate)
        st.caption("SIMULATED values (isolated single-unit model, assumed parameters). "
                   "Geometry is schematic (illustrative) unless tagged [published]. "
                   "Not connected to the real plant. Not validated against operating data.")

with tab_reg:
    with st.expander("Simulation parameter register (published / calculated / assumed)", expanded=True):
        rows = [{"key": q.key, "description": q.description, "value": q.value, "unit": q.unit,
                 "class": q.classification, "source / rationale": q.source} for q in sim.params.values()]
        rows += [{"key": f"governor.{k}", "description": "Governor setting", "value": getattr(sim.gov, k), "unit": u,
                  "class": "assumed", "source / rationale": why} for k, (u, why) in GOVERNOR_ASSUMPTIONS.items()]
        st.dataframe(rows, width="stretch", hide_index=True)
