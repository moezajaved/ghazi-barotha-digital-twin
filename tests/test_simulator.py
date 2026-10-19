import csv
import io

import numpy as np
import pytest

from backend import model as m
from backend.governor import GovernorSettings
from backend.simulator import COLUMNS, RECORD_DT, Simulator, channel_share_per_unit, validate_inputs


@pytest.fixture()
def sim():
    return Simulator()


def test_reset_state_is_equilibrium_and_holds(sim):
    u0 = sim.ss["u0"]
    assert len(sim.hist["t"]) == 1 and sim.t == 0
    sim.step(100, *u0, True)
    last = sim.latest()
    assert last["Q"] == pytest.approx(400.0, abs=1e-6) and last["f"] == pytest.approx(50.0, abs=1e-9)
    assert last["P_gen"] == pytest.approx(254.5106, abs=1e-3)


def test_history_rows_and_time(sim):
    u0 = sim.ss["u0"]
    sim.step(10, *u0, True)
    assert len(sim.hist["t"]) == 1 + int(10 / RECORD_DT)
    t = sim.arrays()["t"]
    assert np.all(np.diff(t) > 0) and t[-1] == pytest.approx(10.0)
    assert set(sim.hist) == set(COLUMNS) and len({len(v) for v in sim.hist.values()}) == 1


def test_stepping_in_pieces_equals_one_step():
    a, b = Simulator(), Simulator()
    u = list(a.ss["u0"])
    u[1] += 15
    a.step(10, *u, True)
    b.step(5, *u, True)
    b.step(5, *u, True)
    for k in ("Q", "w", "y", "h_p", "xi"):
        assert a.latest()[k] == pytest.approx(b.latest()[k], rel=1e-6, abs=1e-9)


def test_pond_mass_balance(sim):
    u0 = sim.ss["u0"]
    sim.step(100, u0[0], u0[1], 350.0, False)
    a = sim.arrays()
    dh = a["h_p"][-1] - a["h_p"][0]
    # The t=0 history row still holds the pre-step inflow, so integrate the inflow actually applied (350 m3/s).
    expected = np.trapezoid(350.0 - a["Q"], a["t"]) / sim.p["A_pond"]
    assert dh == pytest.approx(expected, abs=2e-7) and dh < 0


def test_reproducible_and_reset(sim):
    other = Simulator()
    for s in (sim, other):
        u0 = s.ss["u0"]
        s.step(20, u0[0], u0[1] + 10, u0[2], True)
    assert sim.to_csv() == other.to_csv()
    sim.reset()
    assert sim.t == 0 and len(sim.hist["t"]) == 1 and sim.latest()["f"] == pytest.approx(50.0)


def test_governor_flag_recorded(sim):
    u0 = sim.ss["u0"]
    sim.step(2, *u0, False)
    assert sim.latest()["governor_on"] == 0.0
    sim.step(2, *u0, True)
    assert sim.latest()["governor_on"] == 1.0


def test_csv_export(sim):
    sim.step(5, *sim.ss["u0"], True)
    rows = list(csv.reader(io.StringIO(sim.to_csv())))
    assert rows[0] == COLUMNS and len(rows) == 1 + len(sim.hist["t"])
    assert float(rows[-1][0]) == pytest.approx(5.0)


# --------------------------------------------------------------- validation
@pytest.fixture(scope="module")
def p():
    return m.values(m.build_parameters())


def test_valid_inputs_pass(p):
    assert validate_inputs(p, 0.87, 254.5, 400.0, 120) == []
    assert validate_inputs(p, 0.0, 0.0, 0.0) == [] and validate_inputs(p, 1.0, p["S_base"], p["Q_full"], 3600) == []


@pytest.mark.parametrize("args", [(1.2, 250, 400), (-0.1, 250, 400), (0.87, -1, 400), (0.87, 400, 400),
                                  (0.87, 250, 500), (0.87, 250, -5), (float("nan"), 250, 400), (0.87, float("inf"), 400),
                                  ("0.8", 250, 400), (True, 250, 400), (None, 250, 400)])
def test_invalid_inputs_rejected(p, args):
    assert validate_inputs(p, *args)


@pytest.mark.parametrize("d", [0, -5, 4000, float("nan"), "x"])
def test_invalid_duration_rejected(p, d):
    assert validate_inputs(p, 0.87, 250, 400, d)


def test_step_rejects_bad_input_without_changing_state(sim):
    u0 = sim.ss["u0"]
    before = (sim.t, len(sim.hist["t"]), sim.z.copy())
    for bad_args in [(5, 2.0, u0[1], u0[2]), (5, u0[0], 1000, u0[2]), (5, u0[0], u0[1], float("nan")),
                     (0, *u0), (-1, *u0), (float("nan"), *u0)]:
        with pytest.raises(ValueError):
            sim.step(*bad_args)
    assert (sim.t, len(sim.hist["t"])) == before[:2] and np.array_equal(sim.z, before[2])


def test_step_rejects_invalid_governor_settings():
    s = Simulator(gov=GovernorSettings(Kp=-1.0))
    with pytest.raises(ValueError):
        s.step(1, *s.ss["u0"])


def test_channel_share_is_published_value_over_units():
    assert channel_share_per_unit() == pytest.approx(1600 / 5)
