"""Phase 4: state-space at a chosen operating point, export, and linear-vs-nonlinear comparison."""
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from backend import model as m
from backend.governor import GovernorSettings, closed_loop_poles, rhs_closed_loop
from backend.scenarios import build_scenario, run_scenario
from backend.state_space import compare_with_run, eigenvalues, export_zip, linearize_at, operating_point_errors

ROOT = Path(__file__).resolve().parents[1]
PARAMS = m.build_parameters()
P = m.values(PARAMS)
X0 = m.steady_state(P)["x0"]
Y_NOM, H_NOM = float(X0[2]), float(X0[0])


def lf(b: bytes) -> bytes:
    """Compare content, not line endings: numpy/pathlib write CRLF on Windows and LF on Linux."""
    return b.replace(b"\r\n", b"\n")


def zfiles(b):
    z = zipfile.ZipFile(io.BytesIO(b))
    return {n: z.read(n) for n in z.namelist()}


def test_nominal_open_loop_export_identical_to_phase1_files():
    f = zfiles(export_zip(linearize_at(P, Y_NOM, H_NOM), PARAMS, "nominal"))
    for n in "ABCD":
        assert lf(f[f"{n}.csv"]) == lf((ROOT / "exports" / f"{n}.csv").read_bytes())
    meta = json.loads(f["state_space_model.json"])
    assert "Not validated" in meta["status"] and meta["linear_vs_nonlinear"]
    assert meta["operating_point_values"]["y0"]["P_gen"] == pytest.approx(254.511, abs=1e-3)


def test_closed_loop_shapes_eigenvalues_and_export():
    lin = linearize_at(P, Y_NOM, H_NOM, "closed_loop", GovernorSettings())
    assert lin["A"].shape == (6, 6) and lin["B"].shape == (6, 3) and lin["C"].shape == (4, 6) and lin["D"].shape == (4, 3)
    np.testing.assert_allclose(eigenvalues(lin), closed_loop_poles(P, GovernorSettings()), atol=1e-6)
    f = zfiles(export_zip(lin, PARAMS, "nominal"))
    meta = json.loads(f["state_space_model.json"])
    assert meta["inputs"][0]["name"] == "y_set" and "Saturation is NOT represented" in meta["linearization"]["validity"]
    A = np.loadtxt(io.StringIO(f["A.csv"].decode()), delimiter=",")
    np.testing.assert_allclose(A, lin["A"], rtol=1e-9)


def test_other_operating_point_is_an_equilibrium_and_differs():
    lin = linearize_at(P, 0.5, 333.0)
    assert np.abs(m.rhs(lin["x0"], lin["u0"], P)).max() < 1e-9
    assert lin["max_abs_diff_vs_analytic"] < 1e-5            # numerical vs hand-derived Jacobian
    nom = linearize_at(P, Y_NOM, H_NOM)
    assert not np.allclose(lin["A"], nom["A"])
    cl = linearize_at(P, 0.5, 333.0, "closed_loop")
    assert np.abs(rhs_closed_loop(cl["x0"], cl["u0"], P, GovernorSettings())).max() < 1e-9


@pytest.mark.parametrize("y0, h0", [(1.0, 334.0), (0.02, 334.0), (0.0, 334.0), (1.2, 334.0), (0.5, 260.0), (float("nan"), 334.0)])
def test_invalid_operating_points_rejected_with_reason(y0, h0):
    assert operating_point_errors(P, y0, h0)
    with pytest.raises(ValueError):
        linearize_at(P, y0, h0)


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        linearize_at(P, Y_NOM, H_NOM, "bogus")


@pytest.fixture(scope="module")
def runs():
    out = {}
    for k in ("load_step", "overload", "governor_compare", "normal"):
        out[k] = run_scenario(build_scenario(k)[0])
    return out


def test_linear_model_matches_small_load_step(runs):
    c = compare_with_run(runs["load_step"].main, linearize_at(P, Y_NOM, H_NOM, "closed_loop"))
    for n in ("P_gen", "f", "Q"):
        assert c["max_abs_err"][n] < 0.05 * c["max_dev"][n], n          # within 5 % of the change (measured ~2 %)


def test_linear_model_diverges_in_overload(runs):
    """Documented limitation: gate saturation is not in the linear model."""
    c = compare_with_run(runs["overload"].main, linearize_at(P, Y_NOM, H_NOM, "closed_loop"))
    assert c["max_abs_err"]["P_gen"] > 0.3 * c["max_dev"]["P_gen"]


def test_open_loop_matches_governor_off_run_exactly(runs):
    """With the gate fixed, flow and power stay constant and the swing equation is linear: errors are ~0.
    This also checks the time alignment of the inputs (zero-order hold)."""
    c = compare_with_run(runs["governor_compare"].reference, linearize_at(P, Y_NOM, H_NOM, "open_loop"))
    assert c["max_dev"]["f"] > 3.0 and c["max_abs_err"]["f"] < 1e-6


def test_normal_operation_zero_error(runs):
    c = compare_with_run(runs["normal"].main, linearize_at(P, Y_NOM, H_NOM, "closed_loop"))
    assert max(c["max_abs_err"].values()) < 1e-9


def test_comparison_refuses_mismatched_inputs(runs):
    with pytest.raises(ValueError, match="governor mode"):
        compare_with_run(runs["governor_compare"].reference, linearize_at(P, Y_NOM, H_NOM, "closed_loop"))
    with pytest.raises(ValueError, match="did not start"):
        compare_with_run(runs["load_step"].main, linearize_at(P, 0.6, H_NOM, "closed_loop"))
    from backend.simulator import Simulator
    with pytest.raises(ValueError, match="Run the simulation first"):
        compare_with_run(Simulator(), linearize_at(P, Y_NOM, H_NOM, "closed_loop"))


def test_phase1_exports_unchanged_on_disk():
    """Regenerating the Phase 1 exports must reproduce the committed files (no Phase 4 side effects)."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        m.export_state_space(Path(td), PARAMS, m.linearize(P))
        for n in ("A.csv", "B.csv", "C.csv", "D.csv", "state_space_model.json"):
            assert lf((Path(td) / n).read_bytes()) == lf((ROOT / "exports" / n).read_bytes()), n
