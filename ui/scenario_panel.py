"""Sidebar panel: choose a demonstration scenario, adjust its settings (validated), start / exit it."""
from __future__ import annotations

import streamlit as st

from backend.scenarios import SCENARIOS, build_scenario


def render(active_spec):
    """Draw the panel. Returns (spec_to_start or None, exit_clicked)."""
    st.header("Demonstration scenarios")
    keys = list(SCENARIOS)
    key = st.selectbox("Scenario", keys, format_func=lambda k: SCENARIOS[k]["title"], key="scn_key",
                       disabled=active_spec is not None)
    d = SCENARIOS[key]
    st.caption(d["purpose"])
    # Widget keys include the scenario key, so each scenario keeps its own (default) settings.
    new_load = t_event = None
    if d["new_load"] is not None:
        new_load = st.number_input("New load after the event (MW)", value=float(d["new_load"]), step=5.0, format="%.1f",
                                   key=f"scn_load_{key}", disabled=active_spec is not None,
                                   help="Starting load is 254.51 MW (calculated operating point). Allowed 0 to S_base.")
        t_event = st.number_input("Event time (s)", value=float(d["t_event"]), step=1.0, format="%.1f",
                                  key=f"scn_t_{key}", disabled=active_spec is not None)
    duration = st.number_input("Scenario duration (s)", value=float(d["duration"]), step=10.0, format="%.0f",
                               key=f"scn_dur_{key}", disabled=active_spec is not None)
    # No min/max on these widgets on purpose: out-of-range values are REPORTED below instead of silently clamped.
    spec, errors, warnings = build_scenario(key, new_load, t_event, duration)
    for e in errors:
        st.error(e)
    for w in warnings:
        st.warning(w)
    c1, c2 = st.columns(2)
    start = c1.button("Start scenario", key="start_scn", type="primary", disabled=bool(errors) or active_spec is not None)
    exit_ = c2.button("Exit scenario", key="exit_scn", disabled=active_spec is None)
    if active_spec is not None:
        st.success(f"Active: {active_spec.title}. Inputs below are controlled by the scenario. Run / Pause / Step / Reset work as usual.")
        st.caption("What to watch: " + active_spec.watch)
    return (spec if start and not errors else None), exit_
