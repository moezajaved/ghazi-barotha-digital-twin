"""Phase 4: demonstration scenarios, result checks and results export (backend only)."""
import csv
import io
import json
import zipfile

import numpy as np
import pytest

from backend import model as m
from backend.governor import GovernorSettings
from backend.scenarios import (EXPORT_COLUMNS, SCENARIOS, ScenarioPlayer, assess, build_scenario, full_gate_capacity,
                               results_csv, results_zip, run_scenario)
from backend.simulator import Simulator

P = m.values(m.build_parameters())
SS = m.steady_state(P)
Y0, P0, Q0 = SS["u0"]


@pytest.fixture(scope="module")
def results():
    out = {}
    for k in SCENARIOS:
        spec, errors, _ = build_scenario(k)
        assert spec is not None and not errors
        out[k] = run_scenario(spec)
    return out


def last(sim, c):
    return sim.hist[c][-1]


# ------------------------------------------------------------------ every scenario
@pytest.mark.parametrize("key", list(SCENARIOS))
def test_every_scenario_completes_without_error(results, key):
    r = results[key]
    assert r.error is None
    assert r.main.t == pytest.approx(r.spec.duration)
    assert all(np.isfinite(r.main.arrays()[c]).all() for c in ("Q", "h_t", "P_gen", "f", "y", "w", "h_p"))
    assert not [n for n in r.notices if n[0] == "error"]


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_scenario_equals_manual_stepping_of_the_model(results, key):
    """A scenario is only an input schedule: stepping the Simulator by hand with the same inputs gives identical results."""
    spec = results[key].spec
    s = Simulator()
    s.reset(governor_on=spec.governor_on)
    t_ev = [e.t for e in spec.events] + [spec.duration]
    t = 0.0
    for te in t_ev:
        if te > t:
            s.step(te - t, *spec.inputs_at(t), spec.governor_on)
            t = te
    for c in ("t", "Q", "P_gen", "f", "y", "h_p"):
        np.testing.assert_array_equal(s.arrays()[c], results[key].main.arrays()[c])


def test_normal_operation_stays_at_equilibrium(results):
    a = results["normal"].main.arrays()
    assert np.ptp(a["P_gen"]) < 1e-6 and np.ptp(a["f"]) < 1e-9 and np.ptp(a["Q"]) < 1e-6
    assert a["P_gen"][-1] == pytest.approx(P0) and a["f"][-1] == pytest.approx(50.0)


def test_load_step_physics(results):
    r = results["load_step"]
    a = r.main.arrays()
    i_ev = int(np.searchsorted(a["t"], 5.0))
    assert a["t"][i_ev] == pytest.approx(5.0)                      # the event time is a record point
    assert np.all(a["P_load"][: i_ev + 1] == pytest.approx(P0)) and np.all(a["P_load"][i_ev + 1:] == 280.0)
    after = slice(i_ev + 1, i_ev + 12)
    assert a["P_gen"][after].min() < P0 - 0.5                     # non-minimum-phase dip right after the gate starts opening
    assert 49.5 < a["f"][-1] < 50.0                                # droop: settles slightly below 50 Hz
    assert a["y"][-1] > Y0                                         # gate opened
    # steady balance at the end: P_gen = P_load + D*S_base*(w-1)  (load damping, assumed D)
    assert a["P_gen"][-1] == pytest.approx(280.0 + P["D_damp"] * P["S_base"] * (a["w"][-1] - 1.0), abs=0.05)
    # droop: governor error e = (1-w) - R (y - y_set) -> 0 at steady state
    assert (1 - a["w"][-1]) == pytest.approx(0.05 * (a["y"][-1] - Y0), abs=2e-4)


def test_load_rejection_physics_and_validity_warning(results):
    r = results["load_rejection"]
    a = r.main.arrays()
    assert a["f"].max() > 55.0 and a["f"][-1] > 50.0                # overspeed, then droop at no load
    assert a["y"][-1] < 0.1                                          # gate closed by the governor
    assert a["h_t"].max() > P["H_design"] * 1.1                      # pressure rise when the flow is decelerated
    msgs = " ".join(m_ for _, m_ in r.notices)
    assert "outside 0.9-1.1 pu" in msgs                              # flagged as outside the model's valid range
    assert "Net head peaked" in msgs


def test_overload_saturates_gate_and_is_flagged(results):
    r = results["overload"]
    a = r.main.arrays()
    assert a["y_cmd"].max() == pytest.approx(1.0) and a["y"][-1] > 0.999
    assert a["P_gen"][-1] == pytest.approx(full_gate_capacity(P), abs=0.5)    # pond 4 mm lower than nominal
    assert a["f"][-1] < 46.0
    assert any(lv == "warning" and "upper limit" in msg for lv, msg in r.notices)
    _, _, warnings = build_scenario("overload")
    assert any("exceeds the model's full-gate capacity" in w and "NOT reduced" in w for w in warnings)


def test_governor_on_vs_off(results):
    r = results["governor_compare"]
    on, off = r.main.arrays(), r.reference.arrays()
    assert np.all(on["governor_on"][1:] == 1.0) and np.all(off["governor_on"] == 0.0)
    np.testing.assert_array_equal(on["P_load"], off["P_load"])          # identical input schedule
    assert np.ptp(off["y"]) < 1e-12                                       # no governor: gate never moves
    assert abs(on["f"][-1] - 50) < 0.5 and off["f"][-1] < 47.0           # governor restores frequency, open loop does not
    # open loop steady state: deficit balanced by damping only: (P0 - 280)/S_base = D (w - 1)
    assert off["w"][-1] - 1 == pytest.approx((P0 - 280.0) / P["S_base"] / P["D_damp"], abs=2e-4)


def test_governor_off_load_step_without_comparison_flag():
    spec, _, _ = build_scenario("load_step")
    s = Simulator()
    s.reset(governor_on=False)
    ScenarioPlayer(spec).advance(s, spec.duration, governor_on=False)
    assert s.hist["y"][-1] == pytest.approx(Y0) and s.hist["f"][-1] < 47.0


def test_chunked_live_playback_equals_single_run(results):
    spec = results["load_step"].spec
    s = Simulator()
    pl = ScenarioPlayer(spec)
    while not pl.done(s):
        pl.advance(s, 5.0)                                     # dashboard default: 5 s per refresh
    a, b = s.arrays(), results["load_step"].main.arrays()
    np.testing.assert_allclose(a["t"], b["t"], atol=1e-9)
    np.testing.assert_allclose(a["f"], b["f"], atol=1e-6)


def test_event_inside_a_chunk_is_applied_exactly():
    spec, _, _ = build_scenario("load_step", t_event=7.3, duration=20.0)
    s = Simulator()
    ScenarioPlayer(spec).advance(s, 10.0)
    t = np.array(s.hist["t"])
    assert np.any(np.isclose(t, 7.3)) and s.t == pytest.approx(10.0)


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize("kw, text", [
    (dict(new_load=-5.0), "outside the allowed range"),
    (dict(new_load=400.0), "outside the allowed range"),
    (dict(new_load=float("nan")), "finite number"),
    (dict(new_load="abc"), "finite number"),
    (dict(t_event=-1.0), "outside the allowed range"),
    (dict(t_event=150.0), "earlier than the duration"),
    (dict(duration=0.5), "outside the allowed range"),
    (dict(duration=4000.0), "outside the allowed range"),
    (dict(duration=float("inf")), "finite number"),
])
def test_invalid_inputs_are_rejected_not_clipped(kw, text):
    spec, errors, _ = build_scenario("load_step", **kw)
    assert spec is None
    assert any(text in e for e in errors), errors


def test_unknown_scenario_rejected():
    spec, errors, _ = build_scenario("earthquake")
    assert spec is None and "Unknown scenario" in errors[0]


def test_valid_edge_values_accepted():
    for kw in (dict(new_load=0.0), dict(new_load=P["S_base"]), dict(duration=3600.0), dict(t_event=0.0)):
        spec, errors, _ = build_scenario("load_step", **kw)
        assert spec is not None and not errors, (kw, errors)


def test_no_disturbance_warning():
    _, errors, warnings = build_scenario("load_step", new_load=float(P0))
    assert not errors and any("no disturbance" in w for w in warnings)


def test_scenario_assumptions_are_labelled():
    spec, _, _ = build_scenario("load_step")
    text = " ".join(spec.assumed)
    assert "ASSUMED" in text and "demonstration choices" in text and "320 m3/s" in text


# ------------------------------------------------------------------ failures and checks
def test_solver_failure_is_caught_and_partial_results_kept(monkeypatch):
    spec, _, _ = build_scenario("load_step")
    real = Simulator.step

    def flaky(self, dt, *a, **k):
        if self.t >= 5.0:                                   # the segment after the load event (t = 5 s)
            raise RuntimeError("Integration failed: simulated failure")
        return real(self, dt, *a, **k)

    monkeypatch.setattr(Simulator, "step", flaky)
    r = run_scenario(spec)
    assert r.error and "t = 5.00 s" in r.error and "simulated failure" in r.error
    assert r.main.t == pytest.approx(5.0) and len(r.main.hist["t"]) == 21      # results up to the failure are kept
    assert ("error", r.error) in r.notices


def test_assess_flags_non_finite_values():
    s = Simulator()
    s.step(1.0, Y0, P0, Q0, True)
    s.hist["f"][-1] = float("nan")
    out = assess(s, GovernorSettings())
    assert out[0][0] == "error" and "Non-finite" in out[0][1]


def test_assess_flags_gate_floor():
    s = Simulator()
    s.step(30.0, 0.0, 0.0, Q0, False)                           # open loop gate command 0 -> below the y_min floor
    msgs = " ".join(m_ for _, m_ in assess(s, GovernorSettings()))
    assert "numerical floor" in msgs


# ------------------------------------------------------------------ export
def test_results_csv_columns_and_values(results):
    r = results["governor_compare"]
    text = results_csv([("scenario_run", r.main), ("governor_off_reference", r.reference)])
    text.encode("ascii")                                         # plain ASCII: opens cleanly in Excel on Windows
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    for col in ("time_s", "flow_m3s", "net_head_m", "power_MW", "frequency_Hz", "gate_position_pu", "rotor_speed_pu"):
        assert col in header
    n = len(r.main.hist["t"])
    assert len(rows) == 1 + n + len(r.reference.hist["t"])
    main_rows = [x for x in rows[1:] if x[0] == "scenario_run"]
    i_p, i_f = header.index("power_MW"), header.index("frequency_Hz")
    assert float(main_rows[-1][i_p]) == pytest.approx(last(r.main, "P_gen"), rel=1e-7)
    assert float(main_rows[-1][i_f]) == pytest.approx(last(r.main, "f"), rel=1e-7)


def test_results_zip_contains_settings_assumptions_and_warnings(results):
    r = results["overload"]
    params = m.build_parameters()
    z = zipfile.ZipFile(io.BytesIO(results_zip([("scenario_run", r.main)], r.spec, GovernorSettings(), params, r.notices)))
    assert sorted(z.namelist()) == ["README.txt", "metadata.json", "results.csv"]
    meta = json.loads(z.read("metadata.json"))
    assert "Not measured plant data" in meta["status"] and "not validated" in meta["status"]
    assert meta["scenario"]["key"] == "overload" and meta["scenario"]["events"][0]["P_load"] == 320.0
    assert meta["scenario"]["scenario_assumptions"] and "Kp" in meta["governor_settings_ASSUMED"]
    assert {c["name"] for c in meta["columns"]} == {c[1] for c in EXPORT_COLUMNS}
    assert any(w["level"] == "warning" for w in meta["checks_and_warnings"])
    classes = {q["classification"] for q in meta["model_parameters"]}
    assert {"published", "assumed"} <= classes


def test_results_zip_for_manual_run():
    s = Simulator()
    s.step(5.0, Y0, 270.0, Q0, True)
    z = zipfile.ZipFile(io.BytesIO(results_zip([("governor_on", s)], None, GovernorSettings(), m.build_parameters(), [],
                                               {"load_MW": 270.0})))
    meta = json.loads(z.read("metadata.json"))
    assert meta["scenario"] is None and meta["manual_inputs"]["load_MW"] == 270.0
