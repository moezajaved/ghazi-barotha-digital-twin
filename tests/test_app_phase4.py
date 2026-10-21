"""Headless dashboard tests for Phase 4 (scenarios, result checks, state-space tab). AppTest executes app.py for real."""
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from backend.scenarios import SCENARIOS, build_scenario, run_scenario
from ui.state_space_tab import KINDS, POINTS

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture()
def at(monkeypatch):
    monkeypatch.setenv("GBHP_REFRESH_SECONDS", "0.05")
    return AppTest.from_file(APP, default_timeout=60).run()


def start(at, key, **settings):
    at.selectbox(key="scn_key").set_value(key).run()
    for name, val in settings.items():
        at.number_input(key=f"scn_{name}_{key}").set_value(val).run()
    at.button(key="start_scn").click().run()


def play_to_end(at, max_ticks=500):
    ticks = 0
    while at.session_state["running"] and ticks < max_ticks:
        at.run()                                   # one fragment-timer tick (AppTest has no timers)
        ticks += 1
    assert not at.session_state["running"]


def values(at):
    return {m_.label: m_.value for m_ in at.metric}


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_each_scenario_runs_in_dashboard_and_matches_backend(at, key):
    start(at, key)
    assert not at.exception and at.session_state["scenario"].key == key and at.session_state["running"]
    play_to_end(at)
    sim = at.session_state["sim"]
    ref = run_scenario(build_scenario(key)[0])                 # independent backend run, same scenario
    assert sim.t == pytest.approx(ref.main.t)
    np.testing.assert_allclose(sim.arrays()["f"][-1], ref.main.arrays()["f"][-1], atol=1e-6)
    np.testing.assert_allclose(sim.arrays()["P_gen"][-1], ref.main.arrays()["P_gen"][-1], atol=1e-5)
    v = values(at)
    assert v["Power (MW)"] == f"{sim.latest()['P_gen']:.1f}" and v["Frequency (Hz)"] == f"{sim.latest()['f']:.3f}"
    assert not at.exception


def test_governor_comparison_shows_reference_run(at):
    start(at, "governor_compare")
    ref = at.session_state["scn_ref"]
    assert ref is not None and np.all(ref.arrays()["governor_on"] == 0.0) and ref.t == pytest.approx(120.0)
    play_to_end(at)
    assert at.session_state["sim"].latest()["governor_on"] == 1.0


def test_scenario_disables_manual_inputs_and_exit_restores(at):
    start(at, "load_step")
    assert at.number_input(key="P_load").disabled and at.toggle(key="gov_on").disabled
    at.button(key="pause").click().run()
    at.button(key="exit_scn").click().run()
    assert at.session_state["scenario"] is None and at.session_state["sim"].t == 0.0
    assert not at.number_input(key="P_load").disabled


def test_reset_restarts_scenario_and_step_applies_event(at):
    start(at, "load_step")
    at.button(key="pause").click().run()
    at.button(key="reset").click().run()
    sim = at.session_state["sim"]
    assert at.session_state["scenario"] is not None and sim.t == 0.0
    at.button(key="step").click().run()                       # default step 5 s: reaches the event time
    at.button(key="step").click().run()
    a = sim.arrays()
    assert sim.t == pytest.approx(10.0) and a["P_load"][-1] == 280.0 and a["f"][-1] < 50.0


def test_invalid_scenario_input_blocks_start_with_message(at):
    at.selectbox(key="scn_key").set_value("overload").run()
    at.number_input(key="scn_load_overload").set_value(500.0).run()
    assert any("outside the allowed range" in e.value for e in at.error)
    assert at.button(key="start_scn").disabled
    at.number_input(key="scn_load_overload").set_value(320.0).run()
    assert any("NOT reduced" in w.value for w in at.warning)   # over capacity: warned, not clipped
    assert not at.button(key="start_scn").disabled


def test_event_after_duration_rejected(at):
    at.selectbox(key="scn_key").set_value("load_step").run()
    at.number_input(key="scn_t_load_step").set_value(200.0).run()
    assert any("earlier than the duration" in e.value for e in at.error) and at.button(key="start_scn").disabled


def test_result_checks_shown_after_overload(at):
    start(at, "overload")
    play_to_end(at)
    notes = at.session_state["result_notices"]
    assert any(lv == "warning" and "upper limit" in msg for lv, msg in notes)
    assert any("upper limit" in w.value for w in at.warning)


def test_state_space_tab_default_and_closed_loop_comparison(at):
    assert at.session_state["ss_last"]["kind"] == "open_loop"
    start(at, "load_step")
    play_to_end(at)
    at.radio(key="ss_kind").set_value(KINDS[1]).run()
    assert not at.exception and at.session_state["ss_last"]["kind"] == "closed_loop"
    err = at.session_state["ss_compare"]
    assert err["P_gen"] < 1.0 and err["f"] < 0.1               # small step: linear model close to the nonlinear one


def test_state_space_at_current_state(at):
    start(at, "load_step")
    play_to_end(at)
    at.radio(key="ss_point").set_value(POINTS[1]).run()
    last = at.session_state["sim"].latest()
    assert not at.exception
    assert at.session_state["ss_last"]["y0"] == pytest.approx(last["y"]) and at.session_state["ss_last"]["h_p0"] == pytest.approx(last["h_p"])


def test_manual_mode_unchanged_and_result_checks(at):
    at.number_input(key="P_load").set_value(280.0).run()
    at.button(key="step").click().run()
    assert at.session_state["scenario"] is None and at.session_state["sim"].t == 5.0
    assert any(lv == "info" and "Ranges" in msg for lv, msg in at.session_state["result_notices"])
