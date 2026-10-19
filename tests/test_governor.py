import numpy as np
import pytest
from scipy.optimize import brentq

from backend import model as m
from backend.governor import GovernorSettings, closed_loop_poles, command, rhs_closed_loop
from backend.simulator import Simulator


@pytest.fixture(scope="module")
def p():
    return m.values(m.build_parameters())


def droop_prediction(sim, y_set, P_load):
    """Quasi-steady frequency and gate from the droop law w = w_ref - R*(y - y_set) and the plant balance."""
    p, g, hp = sim.p, sim.gov, sim.z[0]

    def resid(y):
        Q = np.sqrt((hp - p["z_tw"]) / (p["kf"] + 1 / (p["Cg"] * y) ** 2))
        ht = Q * Q / (p["Cg"] * y) ** 2
        P = p["eta"] * m.RHO * m.G * Q * ht / 1e6
        w = g.w_ref - g.R * (y - y_set)
        return P - (P_load + p["D_damp"] * p["S_base"] * (w - 1))

    y = brentq(resid, 0.3, 1.0)
    return 50 * (g.w_ref - g.R * (y - y_set)), y


# ---------------------------------------------------------------- structure
def test_default_settings_valid_and_documented():
    g = GovernorSettings()
    assert g.validate() == []
    from backend.governor import GOVERNOR_ASSUMPTIONS
    assert set(GOVERNOR_ASSUMPTIONS) >= {"R", "Kp", "Ki", "rate_open", "rate_close", "Kb", "y_lo", "y_hi", "w_ref"}


@pytest.mark.parametrize("bad", [dict(R=0.0), dict(R=0.5), dict(Kp=-1.0), dict(Ki=float("nan")), dict(Kp="x"),
                                 dict(rate_open=0.0), dict(Kb=0.0), dict(Kb=50.0), dict(y_lo=0.9, y_hi=0.6), dict(w_ref=2.0)])
def test_invalid_settings_rejected(bad):
    assert GovernorSettings(**bad).validate()


def test_equilibrium_both_modes(p):
    ss = m.steady_state(p)
    z0 = np.append(ss["x0"], 0.0)
    for on in (True, False):
        assert np.abs(rhs_closed_loop(z0, ss["u0"], p, GovernorSettings(), on)).max() < 1e-9


def test_closed_loop_poles(p):
    poles = closed_loop_poles(p, GovernorSettings())
    assert len(poles) == 6
    fast = poles[np.abs(poles) > 1e-4]          # excludes the angle integrator and the very slow pond-level mode
    assert np.all(fast.real < 0)
    zeta = -fast.real / np.abs(fast)
    assert zeta.min() > 0.7                     # well damped
    slow = poles[(np.abs(poles) > 1e-9) & (np.abs(poles) <= 1e-4)]
    assert len(slow) == 1 and abs(slow[0].imag) < 1e-12   # pond-level mode: real and extremely slow (|lambda| < 1e-4 1/s)


# ------------------------------------------------------------- behaviour
def test_droop_steady_state(p):
    s = Simulator()
    u0 = s.ss["u0"]
    s.step(300, u0[0], u0[1] + 20, u0[2], True)
    f_pred, y_pred = droop_prediction(s, u0[0], u0[1] + 20)
    assert s.latest()["f"] == pytest.approx(f_pred, abs=0.002)
    assert s.latest()["y"] == pytest.approx(y_pred, abs=0.002)
    assert 49.7 < s.latest()["f"] < 49.95 and abs(s.latest()["xi"]) < 0.2


def test_governor_beats_open_loop(p):
    on, off = Simulator(), Simulator()
    u0 = on.ss["u0"]
    for s, flag in ((on, True), (off, False)):
        s.step(100, u0[0], u0[1] + 20, u0[2], flag)
    assert abs(off.latest()["f"] - 50) > 2.0       # open loop: frequency runs away from nominal (Phase 1 finding)
    assert abs(on.latest()["f"] - 50) < 0.5
    assert np.abs(on.arrays()["f"] - 50).max() < np.abs(off.arrays()["f"] - 50).max()


def test_command_limits_and_anti_windup():
    s = Simulator()
    u0 = s.ss["u0"]
    s.step(120, u0[0], 320.0, u0[2], True)         # beyond full-gate capacity (~292 MW): gate saturates
    a = s.arrays()
    assert a["y"].max() <= 1.0 + 1e-9 and a["y_cmd"].max() <= 1.0 + 1e-12 and a["y_cmd"].min() >= 0.0
    assert a["y"].max() > 0.99                      # it really did saturate
    assert np.abs(a["xi"]).max() < 0.5              # integrator did not wind up
    s.step(200, u0[0], u0[1], u0[2], True)          # load returns to normal: must recover promptly
    assert abs(s.latest()["f"] - 50) < 0.5


def test_gate_rate_limits():
    for target, rate in ((1.0, GovernorSettings().rate_open), (0.2, GovernorSettings().rate_close)):
        s = Simulator()
        u0 = s.ss["u0"]
        s.step(20, target, u0[1], u0[2], False)    # open loop: servo asks for a fast move, limit must bind
        a = s.arrays()
        v = np.abs(np.diff(a["y"]) / np.diff(a["t"]))
        assert v.max() <= rate * 1.02
        assert v.max() >= rate * 0.9               # and it was actually the active constraint


def test_command_clipping_function():
    g = GovernorSettings()
    z = np.array([334, 400, 0.87, 1.0, 0, 5.0])    # huge integrator state forces saturation
    assert command(z, [0.87, 250, 400], g, True)[0] == g.y_hi
    z[5] = -5.0
    assert command(z, [0.87, 250, 400], g, True)[0] == g.y_lo
    assert command(z, [1.7, 250, 400], g, False)[0] == 1.0


def test_governor_off_matches_phase1_model(p):
    s = Simulator()
    u0 = s.ss["u0"]
    s.step(20, u0[0] + 0.01, u0[1], u0[2], False)   # 1% gate step: servo speed 0.02 pu/s, below the rate limit
    t, X = m.simulate(p, s.ss["x0"], lambda t: u0 + [0.01, 0, 0], 20.0, n_out=81)
    a = s.arrays()
    assert np.allclose(a["Q"], X[:, 1], rtol=1e-5) and np.allclose(a["w"], X[:, 3], rtol=1e-7)


def test_back_calculation_term(p):
    """Unsaturated: dxi/dt = Ki*e exactly. Saturated high: the Kb term pulls the integrator down."""
    g = GovernorSettings()
    ss = m.steady_state(p)
    z = np.append(ss["x0"], 0.0)
    u = ss["u0"]
    _, e, unsat = command(z, u, g, True)
    assert unsat < g.y_hi
    assert rhs_closed_loop(z, u, p, g, True)[5] == pytest.approx(g.Ki * e)
    z_sat = z.copy()
    z_sat[3], z_sat[5] = 0.90, 0.10                      # low speed + integrator -> command beyond y_hi
    cmd, e, unsat = command(z_sat, u, g, True)
    assert unsat > g.y_hi and cmd == g.y_hi and e > 0
    assert rhs_closed_loop(z_sat, u, p, g, True)[5] == pytest.approx(g.Ki * e + g.Kb * (g.y_hi - unsat))
    assert rhs_closed_loop(z_sat, u, p, g, True)[5] < g.Ki * e


def test_overload_is_integrated_without_chattering():
    """Regression: a load beyond full-gate capacity once made every ODE solver fail at t=10.75 s (conditional
    anti-windup chattered on the saturation boundary). It must now run, saturate the gate and settle."""
    import time
    s = Simulator()
    u0 = s.ss["u0"]
    t0 = time.time()
    s.step(120, u0[0], 320.0, u0[2], True)
    assert time.time() - t0 < 10
    a = s.arrays()
    assert a["y"].max() > 0.999 and a["xi"].max() < 0.1
    p, hp = s.p, s.latest()["h_p"]
    Q = np.sqrt((hp - p["z_tw"]) / (p["kf"] + 1 / p["Cg"] ** 2))
    P_full = p["eta"] * m.RHO * m.G * Q ** 3 / p["Cg"] ** 2 / 1e6                 # full-gate power at this pond level
    w_pred = 1 + (P_full - 320.0) / (p["D_damp"] * p["S_base"])
    assert s.latest()["f"] == pytest.approx(50 * w_pred, abs=0.05)


def test_pond_mode_is_slightly_unstable_with_governor_and_matches_constant_power_estimate(p):
    """With the governor holding power, lower head means more flow, so the unregulated pond drains slightly faster
    (pole ~ +3e-6 1/s, time constant ~ days). Independent check: pole = -(dQ/dh_p at constant power)/A_pond."""
    poles = closed_loop_poles(p, GovernorSettings())
    pond = poles[(np.abs(poles) > 1e-9) & (np.abs(poles) <= 1e-4)]
    assert len(pond) == 1 and pond[0].real > 0 and pond[0].real < 1e-5

    def Q_const_P(h, P=m.steady_state(p)["y0"][2]):
        y = brentq(lambda y: p["eta"] * m.RHO * m.G * (np.sqrt((h - p["z_tw"]) / (p["kf"] + 1 / (p["Cg"] * y) ** 2))) ** 3
                   / (p["Cg"] * y) ** 2 / 1e6 - P, 0.3, 1.0)
        return np.sqrt((h - p["z_tw"]) / (p["kf"] + 1 / (p["Cg"] * y) ** 2))

    dQdh = (Q_const_P(p["z_pond"] + 0.01) - Q_const_P(p["z_pond"] - 0.01)) / 0.02
    assert dQdh < 0
    assert pond[0].real == pytest.approx(-dQdh / p["A_pond"], rel=0.15)
    assert 3600 * pond[0].real < 0.02          # < 2% growth over the longest allowed run (1 h)
