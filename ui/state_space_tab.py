"""'State-space model' tab: matrices at a chosen operating point, download, and linear-vs-nonlinear comparison."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from backend import model as m
from backend.state_space import (CL_INPUTS, CL_STATES, LIMITATIONS, compare_with_run, eigenvalues, export_zip,
                                 linearize_at, operating_point_errors)

POINTS = ["Nominal operating point (same as exports/)", "Current simulation state"]
KINDS = ["Plant only (open loop, as exports/)", "Plant + governor (closed loop)"]


def _matrix(name, M, rows, cols):
    st.markdown(f"**{name}** ({M.shape[0]} x {M.shape[1]})")
    st.dataframe({"": rows} | {c: [f"{v:.4g}" for v in M[:, j]] for j, c in enumerate(cols)}, hide_index=True, width="stretch")


def render(sim, params, gov) -> None:
    p = sim.p
    st.markdown(
        "The state-space matrices are a **linearisation** of the nonlinear simulation model about an **equilibrium operating "
        "point**, in deviation variables: d(dx)/dt = A dx + B du, dy = C dx + D du, where dx = x - x0, du = u - u0, dy = y - y0. "
        "They are accurate for small deviations only and are **not** measured or validated plant data.")
    c1, c2 = st.columns(2)
    point = c1.radio("Operating point", POINTS, key="ss_point")
    kind_label = c2.radio("Model", KINDS, key="ss_kind")
    kind = "open_loop" if kind_label == KINDS[0] else "closed_loop"

    nominal = m.steady_state(p)
    if point == POINTS[0]:
        y0, h0, label = float(nominal["x0"][2]), float(nominal["x0"][0]), "nominal (gate 400/460, pond 334 m)"
    else:
        last = sim.latest()
        y0, h0 = float(last["y"]), float(last["h_p"])
        label = f"equilibrium at the current gate {y0:.4f} pu and pond level {h0:.3f} m (t = {last['t']:.1f} s)"
        # how far the running state is from that equilibrium (a transient state is not an equilibrium)
        if abs(last["w"] - 1.0) > 1e-3 or abs(last["P_gen"] - last["P_load"]) > 0.5:
            st.info(f"The simulation is not in equilibrium at t = {last['t']:.1f} s (speed {last['w']:.4f} pu, power "
                    f"{last['P_gen']:.1f} MW vs load {last['P_load']:.1f} MW). The matrices below are taken at the "
                    "equilibrium with the same gate opening and pond level, which is the standard choice; a transient state "
                    "cannot be used as a linearisation point.")
    errs = operating_point_errors(p, y0, h0)
    if errs:
        for e in errs:
            st.error(e)
        st.warning("No matrices for this operating point. Choose the nominal point, or Reset / change the run.")
        return
    try:
        lin = linearize_at(p, y0, h0, kind, gov)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.session_state.ss_last = {"kind": kind, "y0": y0, "h_p0": h0}           # for tests
    states = CL_STATES if kind == "closed_loop" else m.STATES
    inputs = CL_INPUTS if kind == "closed_loop" else m.INPUTS
    sn, inn, on = [s[0] for s in states], [s[0] for s in inputs], [s[0] for s in m.OUTPUTS]
    st.markdown(f"**Operating point:** {label}.  x0 = " + ", ".join(f"{n} {v:.4g}" for n, v in zip(sn, lin["x0"])) +
                ";  u0 = " + ", ".join(f"{n} {v:.4g}" for n, v in zip(inn, lin["u0"])) +
                ";  y0 = " + ", ".join(f"{n} {v:.4g}" for n, v in zip(on, lin["y0"])) + ".")
    if kind == "closed_loop":
        st.caption("Closed loop uses the ASSUMED governor settings from the sidebar. Limits (command 0..1 pu, gate rate limits, "
                   "gate floor) are not part of a linear model.")
    a, b = st.columns(2)
    with a:
        _matrix("A", lin["A"], sn, sn)
        _matrix("C", lin["C"], on, sn)
    with b:
        _matrix("B", lin["B"], sn, inn)
        _matrix("D", lin["D"], on, inn)
    ev = eigenvalues(lin)
    st.markdown("**Eigenvalues of A:** " + ", ".join(f"{e.real:.4g}{e.imag:+.4g}j" if abs(e.imag) > 1e-9 else f"{e.real:.4g}" for e in ev))
    st.caption("A zero eigenvalue belongs to the rotor angle (no grid connection); with the governor, a second near-zero one is the "
               "pond level (slow, no level control).")
    st.download_button("Download matrices at this operating point (ZIP: A, B, C, D CSV + JSON)", export_zip(lin, params, label),
                       f"gbhp_state_space_{kind}.zip", "application/zip", key="ss_download")
    if point == POINTS[0] and kind == "open_loop":
        st.caption("At the nominal point the open-loop CSV files are identical to exports/A.csv ... D.csv (Phase 1).")

    st.subheader("Linear model vs nonlinear simulation")
    st.caption("The linear model is driven with the same input history as the current run and compared with the nonlinear results. "
               "Needs: a run started from Reset at the selected point, and the governor mode matching the model type.")
    if point != POINTS[0]:
        st.info("Comparison is available for the nominal operating point (every run starts there).")
    else:
        try:
            cmp_ = compare_with_run(sim, lin)
        except ValueError as exc:
            st.info(str(exc))
        else:
            st.session_state.ss_compare = cmp_["max_abs_err"]                  # for tests
            fig = make_subplots(rows=1, cols=3, subplot_titles=("Power (MW)", "Frequency (Hz)", "Flow (m3/s)"))
            for j, n in enumerate(["P_gen", "f", "Q"], start=1):
                fig.add_scatter(x=cmp_["t"], y=cmp_["nonlinear"][n], name="Nonlinear simulation", line=dict(color="#2563eb"),
                                showlegend=j == 1, row=1, col=j)
                fig.add_scatter(x=cmp_["t"], y=cmp_["linear"][n], name="Linear state-space model", line=dict(color="#d97706", dash="dash"),
                                showlegend=j == 1, row=1, col=j)
            fig.update_layout(height=330, margin=dict(l=10, r=10, t=60, b=10), template="plotly_white",
                              legend=dict(orientation="h", y=1.25, x=0))
            st.plotly_chart(fig, width="stretch", key="ss_cmp_fig")
            st.dataframe([{"output": n, "largest change in run": f"{cmp_['max_dev'][n]:.4g}",
                           "largest linear-model error": f"{cmp_['max_abs_err'][n]:.4g}",
                           "error / change": (f"{100 * cmp_['max_abs_err'][n] / cmp_['max_dev'][n]:.1f} %" if cmp_['max_dev'][n] > 1e-9 else "-")}
                          for n in ["P_gen", "f", "Q", "h_t"]], hide_index=True, width="stretch")
    with st.expander("Limitations of the linear model"):
        for s in LIMITATIONS:
            st.markdown(f"- {s}")
