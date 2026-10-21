"""Headless tests of the 3D tab in app.py: the values handed to the 3D view must be the simulator's own state."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from backend.plant3d import build_geometry
from backend.simulator import Simulator

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture()
def at(monkeypatch):
    monkeypatch.setenv("GBHP_REFRESH_SECONDS", "0.05")
    return AppTest.from_file(APP, default_timeout=60).run()


def _matches_sim(summary, sim):
    last = sim.latest()
    for k in ("t", "h_p", "Q", "y", "y_cmd", "w", "f", "P_gen", "h_t", "Q_in"):
        assert summary[k] == pytest.approx(last[k], abs=1e-12), k


def test_3d_tab_renders_without_error(at):
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Simulation", "3D plant", "Parameter register"]
    assert "view3d_summary" in at.session_state


def test_3d_initial_state_is_model_equilibrium(at):
    s = at.session_state["view3d_summary"]
    _matches_sim(s, at.session_state["sim"])
    assert s["Q"] == pytest.approx(400.0, abs=1e-6) and s["f"] == pytest.approx(50.0, abs=1e-9)
    assert s["units_live"] == 5


def test_3d_follows_step(at):
    at.number_input(key="P_load").set_value(280.0).run()
    at.button(key="step").click().run()
    sim = at.session_state["sim"]
    s = at.session_state["view3d_summary"]
    assert sim.t == 5.0 and s["t"] == 5.0
    _matches_sim(s, sim)
    assert s["f"] < 50.0             # load step above generation -> frequency dips (from the model, not scripted)


def test_3d_updates_during_run(at):
    """While running, each timer tick must also refresh the 3D view (it has its own fragment)."""
    at.number_input(key="duration").set_value(20.0).run()
    at.button(key="run").click().run()
    seen = []
    ticks = 0
    while at.session_state["running"] and ticks < 50:
        at.run()
        seen.append(at.session_state["view3d_summary"]["t"])
        ticks += 1
    assert not at.session_state["running"]
    assert len(set(seen)) >= 2, f"3D view did not change during the run: {seen}"
    _matches_sim(at.session_state["view3d_summary"], at.session_state["sim"])


def test_3d_advection_matches_integral_of_velocity(at):
    at.button(key="step").click().run()
    sim = at.session_state["sim"]
    geom = build_geometry()
    s = at.session_state["view3d_summary"]
    # steady 400 m3/s for 5 s -> 5 * 400 / A metres travelled
    assert s["advection_m"] == pytest.approx(5.0 * 400.0 / geom.pen_area, rel=1e-6)
    assert s["v_pen"] == pytest.approx(sim.latest()["Q"] / geom.pen_area, rel=1e-12)


def test_3d_replicate_toggle(at):
    at.toggle(key="replicate").set_value(False).run()
    assert not at.exception and at.session_state["view3d_summary"]["units_live"] == 1


def test_camera_preset_changes_nonce(at):
    n0 = at.session_state["cam_nonce"]
    at.selectbox(key="cam_sel").set_value("Powerhouse").run()
    assert at.session_state["cam_nonce"] == n0 + 1 and at.session_state["cam_preset"] == "Powerhouse"
    at.run()                                             # an unrelated rerun must not re-apply the preset
    assert at.session_state["cam_nonce"] == n0 + 1


def test_reset_returns_3d_to_equilibrium(at):
    at.number_input(key="P_load").set_value(200.0).run()
    at.button(key="step").click().run()
    at.button(key="reset").click().run()
    s = at.session_state["view3d_summary"]
    assert s["t"] == 0.0 and s["P_gen"] == pytest.approx(Simulator().latest()["P_gen"], rel=1e-9)
