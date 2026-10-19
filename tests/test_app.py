"""Headless tests of the Streamlit dashboard (streamlit.testing.v1.AppTest executes app.py for real)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from backend.simulator import Simulator

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture()
def at(monkeypatch):
    monkeypatch.setenv("GBHP_REFRESH_SECONDS", "0.05")
    return AppTest.from_file(APP, default_timeout=60).run()


def values(at):
    return {m.label: m.value for m in at.metric}


def run_to_end(at, max_ticks=2000):
    """Click Run, then emulate Streamlit's run_every timer: each at.run() is one fragment tick (AppTest has no timers)."""
    at.button(key="run").click().run()
    ticks = 0
    while at.session_state["running"] and ticks < max_ticks:
        at.run()
        ticks += 1
    assert not at.session_state["running"], "run did not finish"


def test_initial_render(at):
    assert not at.exception
    assert [b.key for b in at.button] == ["run", "pause", "step", "reset"]
    v = values(at)
    assert v["Time (s)"] == "0.0" and v["Flow (m3/s)"] == "400.0" and v["Net head (m)"] == "69.00"
    assert v["Power (MW)"] == "254.5" and v["Frequency (Hz)"] == "50.000"
    assert "single-unit" in at.title[0].value


def test_step_button_advances_model(at):
    at.button(key="step").click().run()
    sim = at.session_state["sim"]
    assert not at.exception and sim.t == 5.0 and len(sim.hist["t"]) == 21
    assert values(at)["Time (s)"] == "5.0"


def test_run_matches_independent_model_calculation(at):
    """Dashboard numbers must equal a direct backend calculation with the same inputs (no fake data)."""
    at.number_input(key="duration").set_value(10.0).run()
    at.number_input(key="P_load").set_value(280.0).run()
    run_to_end(at)
    shown = at.session_state["sim"]
    assert not at.exception and shown.t == 10.0 and at.session_state["running"] is False
    ref = Simulator()
    u0 = ref.ss["u0"]
    for _ in range(2):                                   # dashboard refreshes in 5 s chunks (default)
        ref.step(5.0, u0[0], 280.0, u0[2], True)
    for k in ("Q", "h_t", "P_gen", "f", "y"):
        assert shown.latest()[k] == pytest.approx(ref.latest()[k], rel=1e-9)
    assert abs(shown.latest()["f"] - 50) > 0.5          # the load change really acted
    assert values(at)["Time (s)"] == "10.0"


def test_governor_toggle_changes_results(at):
    at.number_input(key="duration").set_value(30.0).run()
    at.number_input(key="P_load").set_value(275.0).run()
    run_to_end(at)
    f_on = at.session_state["sim"].latest()["f"]
    at.button(key="reset").click().run()
    at.toggle(key="gov_on").set_value(False).run()
    run_to_end(at)
    sim = at.session_state["sim"]
    assert sim.latest()["governor_on"] == 0.0 and abs(sim.latest()["f"] - f_on) > 0.5


def test_reset_and_pause(at):
    at.button(key="step").click().run()
    at.session_state["running"] = True
    at.button(key="pause").click().run()
    assert at.session_state["running"] is False and at.session_state["sim"].t == 5.0
    at.button(key="reset").click().run()
    assert at.session_state["sim"].t == 0.0 and len(at.session_state["sim"].hist["t"]) == 1
    assert values(at)["Time (s)"] == "0.0"


def test_run_after_duration_reached_warns(at):
    at.number_input(key="duration").set_value(5.0).run()
    run_to_end(at)
    at.button(key="run").click().run()
    assert any("Duration already reached" in w.value for w in at.warning)


def test_inflow_notice(at):
    assert any("power channel design flow" in i.value for i in at.info)       # default inflow 400 > 320 per unit
    at.number_input(key="Q_in").set_value(300.0).run()
    assert not any("power channel design flow" in i.value for i in at.info)


def test_overload_load_runs_without_error(at):
    """A load above full-gate capacity (320 MW) is allowed by the inputs; the dashboard must handle it."""
    at.number_input(key="duration").set_value(30.0).run()
    at.number_input(key="P_load").set_value(320.0).run()
    run_to_end(at)
    sim = at.session_state["sim"]
    assert not at.exception and not at.error and sim.t == 30.0
    assert sim.latest()["y"] > 0.99 and sim.latest()["f"] < 49


def test_each_tick_advances_one_chunk_and_pause_stops_it(at):
    at.number_input(key="duration").set_value(60.0).run()
    at.button(key="run").click().run()
    sim = at.session_state["sim"]
    assert at.session_state["running"] is True and sim.t == 5.0          # default chunk = 5 simulated seconds
    at.run()
    assert sim.t == 10.0 and values(at)["Time (s)"] == "10.0"
    at.button(key="pause").click().run()
    assert at.session_state["running"] is False and sim.t == 10.0
    at.run()
    assert sim.t == 10.0                                                   # stays paused
    at.button(key="step").click().run()
    assert sim.t == 15.0                                                  # Step advances 5 s


def test_input_change_while_running_is_applied(at):
    at.number_input(key="duration").set_value(60.0).run()
    at.button(key="run").click().run()
    at.number_input(key="P_load").set_value(300.0).run()                  # widget change = full rerun; run continues
    assert at.session_state["running"] is True
    at.run()
    sim = at.session_state["sim"]
    assert sim.hist["P_load"][-1] == 300.0 and sim.hist["P_load"][0] != 300.0
