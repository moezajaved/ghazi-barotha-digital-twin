import csv
import json

import numpy as np
import pytest
from scipy.signal import StateSpace, lsim

from backend import model as m

RHO_G = m.RHO * m.G


@pytest.fixture(scope="module")
def params():
    return m.build_parameters()


@pytest.fixture(scope="module")
def p(params):
    return m.values(params)


@pytest.fixture(scope="module")
def lin(p):
    return m.linearize(p)


# ---------------------------------------------------------- source register
def test_register_rows_and_classification():
    rows = list(csv.DictReader(open(m.REGISTER, newline="")))
    assert len(rows) == 64
    assert len({(r["category"], r["parameter"]) for r in rows}) == 64
    assert {r["classification"] for r in rows} == {"published"}
    assert all(1 <= int(r["pdf_page"]) <= 20 for r in rows)


def test_discrepancy_and_garbled_voltage_preserved():
    reg = m.load_register()
    rated = reg[("Plant", "Rated output per unit")]
    full = reg[("Plant", "Turbine full-gate output")]
    assert float(rated["value"]) == 290 and float(full["value"]) == 295
    assert "conflict" in rated["flag"] and "conflict" in full["flag"]
    volt = reg[("Electrical", "Rated voltage HV:LV")]
    assert "515v" in volt["value"] and "unconfirmed" in volt["flag"]


def test_published_params_match_register(params):
    reg = m.load_register()
    assert params["H_design"].value == float(reg[("Plant", "Design head")]["value"]) == 69
    assert params["Q_full"].value == 460 and params["Q_opt"].value == 400
    assert params["L_pen"].value == 222 and params["D_pen"].value == 10.6
    assert params["eta"].value == pytest.approx(0.94)
    assert params["V_live"].value == pytest.approx(25.5e6)
    assert params["z_pond"].value == 334
    for q in params.values():
        assert q.classification in {"published", "calculated", "assumed"}
        assert q.source


def test_only_assumed_parameters_can_be_overridden():
    assert m.build_parameters({"T_y": 1.0})["T_y"].value == 1.0
    with pytest.raises(ValueError):
        m.build_parameters({"H_design": 70})


# ----------------------------------------------------------- steady state
def test_operating_point_is_equilibrium(p, lin):
    f = m.rhs(lin["x0"], lin["u0"], p)
    assert np.abs(f).max() < 1e-9
    Q0, h_t0, P0, f0 = lin["y0"]
    assert Q0 == pytest.approx(400.0, rel=1e-9)
    assert h_t0 == pytest.approx(69.0, rel=1e-9)
    assert P0 == pytest.approx(0.94 * RHO_G * 400 * 69 / 1e6, rel=1e-9)
    assert f0 == pytest.approx(50.0)


def test_full_gate_design_point_matches_hand_calc(p):
    # y=1 at design head must give Q_full; power = eta*rho*g*Q*H (calculated estimate, not a measurement)
    Q = p["Cg"] * 1.0 * np.sqrt(69.0)
    assert Q == pytest.approx(460.0)
    assert 0.94 * RHO_G * Q * 69 / 1e6 == pytest.approx(292.687, abs=1e-3)


def test_water_starting_time(p, lin):
    Tw = p["L_pen"] * 400.0 / (m.G * np.pi * 10.6 ** 2 / 4 * 69.0)
    assert lin["Tw"] == pytest.approx(Tw, rel=1e-9)
    assert 1.0 < lin["Tw"] < 3.0


# ----------------------------------------------------------- linearisation
def test_numerical_matches_analytic_jacobian(lin):
    assert lin["max_abs_diff_vs_analytic"] < 1e-6


def test_shapes_and_D_zero(lin):
    assert lin["A"].shape == (5, 5) and lin["B"].shape == (5, 3)
    assert lin["C"].shape == (4, 5) and lin["D"].shape == (4, 3)
    assert np.all(lin["D"] == 0)
    assert np.isfinite(lin["A"]).all()


def test_eigenvalues_stable_with_single_integrator(lin):
    eig = np.linalg.eigvals(lin["A"])
    assert np.sum(np.abs(eig) < 1e-9) == 1          # rotor angle integrator
    assert np.all(eig.real[np.abs(eig) >= 1e-9] < 0)


def test_linear_vs_nonlinear_small_step(p, lin):
    du = np.array([0.01, 2.0, 5.0])  # +1% gate, +2 MW load, +5 m3/s inflow
    T = np.linspace(0, 20, 2001)
    sys = StateSpace(lin["A"], lin["B"], lin["C"], lin["D"])
    _, y_lin, x_lin = lsim(sys, np.tile(du, (T.size, 1)), T)
    t, X = m.simulate(p, lin["x0"], lambda t: lin["u0"] + du, 20.0, n_out=2001)
    dx = X - lin["x0"]
    for i in (1, 3):  # Q and w
        assert abs(dx[-1, i] - x_lin[-1, i]) < 0.03 * abs(x_lin[-1, i])
    P_nl = np.array([m.outputs(x, None, p)[2] for x in X]) - lin["y0"][2]
    assert abs(P_nl[-1] - y_lin[-1, 2]) < 0.03 * abs(y_lin[-1, 2])


# ---------------------------------------------------------------- physics
def test_gate_opening_is_non_minimum_phase(p, lin):
    t, X = m.simulate(p, lin["x0"], lambda t: lin["u0"] + [0.02, 0, 0], 15.0, n_out=1501)
    P = np.array([m.outputs(x, None, p)[2] for x in X]) - lin["y0"][2]
    assert P[np.searchsorted(t, 0.3)] < 0     # head drops first
    assert P[-1] > 0                          # then flow catches up


def test_load_drop_raises_frequency(p, lin):
    t, X = m.simulate(p, lin["x0"], lambda t: lin["u0"] - [0, 20.0, 0], 20.0)
    assert X[-1, 3] > 1.0


def test_gate_command_is_clipped(p, lin):
    t, X = m.simulate(p, lin["x0"], lambda t: [5.0, lin["u0"][1], lin["u0"][2]], 10.0)
    assert X[:, 2].max() <= 1.0 + 1e-6


# ------------------------------------------------------------------ export
def test_export_files_and_metadata(tmp_path, params, lin):
    m.export_state_space(tmp_path, params, lin)
    for n, shape in zip("ABCD", [(5, 5), (5, 3), (4, 5), (4, 3)]):
        M = np.loadtxt(tmp_path / f"{n}.csv", delimiter=",").reshape(shape)
        assert np.allclose(M, lin[n], rtol=1e-9, atol=1e-12)
    meta = json.loads((tmp_path / "state_space_model.json").read_text())
    assert [s["name"] for s in meta["states"]] == ["h_p", "Q", "y", "w", "delta"]
    assert {q["classification"] for q in meta["parameters"]} == {"published", "calculated", "assumed"}
    assert "Not validated" in meta["status"] and meta["linearization"]["method"]
    assert len(meta["eigenvalues"]) == 5


def test_export_is_reproducible(tmp_path, params, lin):
    m.export_state_space(tmp_path / "a", params, lin)
    m.export_state_space(tmp_path / "b", params, m.linearize(m.values(params)))
    for f in ["A.csv", "B.csv", "C.csv", "D.csv", "state_space_model.json"]:
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()
