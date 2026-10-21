"""Tests for Phase 3: scene_geometry, plant3d, plant3d_component. (no Streamlit imports needed)"""
import json
import math

import numpy as np
import pytest

from backend.scene_geometry import box, cylinder, merge, validate, bounds
from backend.plant3d import (
    Geometry, SceneState, build_geometry, build_figure,
    camera_presets, figure_payload, particle_fractions,
    provenance_rows, scene_extent, aspect_ratio, PUBLISHED, CALCULATED, SCHEMATIC, SIMULATED,
)
from backend.simulator import Simulator


# ================================================================ scene_geometry
class TestBox:
    def test_vertex_count(self):
        m = box(0, 1, 0, 1, 0, 1)
        assert len(m["x"]) == 8

    def test_triangle_count(self):
        m = box(0, 1, 0, 1, 0, 1)
        assert len(m["i"]) == 12

    def test_validate_passes(self):
        validate(box(0, 10, -5, 5, 100, 200))

    def test_bounds(self):
        b = bounds(box(2, 5, -1, 3, 10, 20))
        assert b[0] == (2.0, 5.0)
        assert b[1] == (-1.0, 3.0)
        assert b[2] == (10.0, 20.0)


class TestCylinder:
    def test_basic_structure(self):
        m = cylinder((0, 0, 0), (0, 0, 10), 2.0)
        validate(m)

    def test_angled_cylinder(self):
        m = cylinder((0, 0, 0), (10, 5, -5), 1.0, n=12)
        validate(m)

    def test_no_caps(self):
        m_full = cylinder((0, 0, 0), (1, 0, 0), 1.0, n=8, caps=True)
        m_open = cylinder((0, 0, 0), (1, 0, 0), 1.0, n=8, caps=False)
        # No caps -> fewer vertices (no cap centre points) and fewer triangles
        assert len(m_open["x"]) < len(m_full["x"])

    def test_bad_radius_raises(self):
        with pytest.raises(ValueError):
            cylinder((0, 0, 0), (1, 0, 0), 0.0)

    def test_degenerate_axis_raises(self):
        with pytest.raises(ValueError):
            cylinder((0, 0, 0), (0, 0, 0), 1.0)


class TestMerge:
    def test_empty(self):
        m = merge([])
        for k in "xyzijk":
            assert len(m[k]) == 0

    def test_index_offset(self):
        a = box(0, 1, 0, 1, 0, 1)
        b = box(2, 3, 0, 1, 0, 1)
        ab = merge([a, b])
        assert len(ab["x"]) == 16
        assert ab["i"].max() < 16

    def test_merge_validates(self):
        m = merge([box(i, i + 1, 0, 1, 0, 1) for i in range(4)])
        validate(m)


# ================================================================ plant3d geometry
class TestBuildGeometry:
    @pytest.fixture
    def geom(self):
        return build_geometry()

    def test_returns_geometry(self, geom):
        assert isinstance(geom, Geometry)

    def test_n_units_published(self, geom):
        assert geom.n_units == 5  # brochure

    def test_penstock_diameter_published(self, geom):
        assert math.isclose(geom.D, 10.6, rel_tol=1e-6)  # brochure p.12

    def test_penstock_length_published(self, geom):
        assert math.isclose(geom.L, 222.0, rel_tol=1e-6)  # brochure p.12

    def test_pond_level_published(self, geom):
        assert math.isclose(geom.z_pond, 334.0, rel_tol=1e-6)  # brochure p.12

    def test_pen_area_calculated(self, geom):
        expected = math.pi * geom.D ** 2 / 4
        assert math.isclose(geom.pen_area, expected, rel_tol=1e-9)

    def test_horizontal_run_calculated(self, geom):
        # sqrt(L^2 - dz^2)
        dz = geom.z_pen_in - geom.z_tw
        expected = math.sqrt(geom.L ** 2 - dz ** 2)
        assert math.isclose(geom.run, expected, rel_tol=1e-9)

    def test_unit_pitch_count(self, geom):
        assert len(geom.y_units) == geom.n_units

    def test_provenance_has_published_and_schematic(self, geom):
        klasses = {r["klass"] for r in geom.provenance}
        assert PUBLISHED in klasses
        assert SCHEMATIC in klasses
        assert CALCULATED in klasses

    def test_provenance_no_invented_values(self, geom):
        # every row must have a non-empty source
        for row in geom.provenance:
            assert row["source"], f"Empty source for {row['component']}: {row['item']}"

    def test_q_full_published(self, geom):
        assert math.isclose(geom.q_full, 460.0, rel_tol=1e-6)  # brochure


# ================================================================ SceneState
class TestSceneState:
    @pytest.fixture
    def geom(self):
        return build_geometry()

    @pytest.fixture
    def state(self, geom):
        sim = Simulator()
        return SceneState.from_simulator(sim, geom.pen_area)

    def test_fields_finite(self, state):
        for f in ["t", "h_p", "Q", "y", "w", "f", "P_gen", "h_t"]:
            assert math.isfinite(getattr(state, f)), f

    def test_initial_frequency(self, state):
        assert math.isclose(state.f, 50.0, rel_tol=1e-4)

    def test_initial_pond_level(self, state, geom):
        assert math.isclose(state.h_p, geom.z_pond, rel_tol=1e-4)

    def test_advection_zero_at_start(self, state):
        assert state.advection_m == 0.0

    def test_advection_grows_after_step(self, geom):
        sim = Simulator()
        sim.step(5.0, 1.0, 254.51, 400.0, False)
        s = SceneState.from_simulator(sim, geom.pen_area)
        assert s.advection_m > 0.0

    def test_summary_keys(self, state, geom):
        d = state.summary(geom, replicate=True)
        for k in ["t", "h_p", "Q", "f", "P_gen", "y", "w", "v_pen", "advection_m", "units_live"]:
            assert k in d, f"Missing key {k}"

    def test_summary_replicate_units(self, state, geom):
        d_rep = state.summary(geom, replicate=True)
        d_no = state.summary(geom, replicate=False)
        assert d_rep["units_live"] == geom.n_units
        assert d_no["units_live"] == 1


# ================================================================ particle fractions
class TestParticlefractions:
    def test_length(self):
        fr = particle_fractions(0.0, 100.0, 10)
        assert len(fr) == 10

    def test_range_0_1(self):
        fr = particle_fractions(25.0, 100.0, 5)
        assert np.all((fr >= 0) & (fr <= 1))

    def test_wraps(self):
        fr1 = particle_fractions(0.0, 100.0, 4)
        fr2 = particle_fractions(100.0, 100.0, 4)
        np.testing.assert_allclose(fr1, fr2, atol=1e-10)

    def test_advances_with_flow(self):
        fr1 = particle_fractions(0.0, 100.0, 5)
        fr2 = particle_fractions(10.0, 100.0, 5)
        # each position should have advanced by 0.1 (mod 1)
        diff = (fr2 - fr1) % 1.0
        np.testing.assert_allclose(diff, 0.1, atol=1e-10)


# ================================================================ build_figure
class TestBuildFigure:
    @pytest.fixture
    def fig_and_state(self):
        geom = build_geometry()
        sim = Simulator()
        state = SceneState.from_simulator(sim, geom.pen_area)
        fig = build_figure(state, geom, replicate=True)
        return fig, state, geom

    def test_returns_figure(self, fig_and_state):
        fig, _, _ = fig_and_state
        import plotly.graph_objects as go
        assert isinstance(fig, go.Figure)

    def test_has_traces(self, fig_and_state):
        fig, _, _ = fig_and_state
        assert len(fig.data) >= 10, "expected at least 10 traces"

    def test_headpond_trace_present(self, fig_and_state):
        fig, _, _ = fig_and_state
        names = [t.name for t in fig.data]
        assert "Headpond" in names

    def test_penstocks_trace_present(self, fig_and_state):
        fig, _, _ = fig_and_state
        names = [t.name for t in fig.data]
        assert "Penstocks" in names

    def test_generators_trace_present(self, fig_and_state):
        fig, _, _ = fig_and_state
        names = [t.name for t in fig.data]
        assert "Generators" in names

    def test_no_nan_in_mesh_coords(self, fig_and_state):
        fig, _, _ = fig_and_state
        import plotly.graph_objects as go
        for tr in fig.data:
            if isinstance(tr, go.Mesh3d):
                for attr in ("x", "y", "z"):
                    arr = np.array(getattr(tr, attr), float)
                    assert np.all(np.isfinite(arr)), f"NaN/Inf in {tr.name}.{attr}"

    def test_replicate_false_fewer_live_meshes(self):
        geom = build_geometry()
        sim = Simulator()
        state = SceneState.from_simulator(sim, geom.pen_area)
        fig_rep = build_figure(state, geom, replicate=True)
        fig_no = build_figure(state, geom, replicate=False)
        # replicate=False should have more "not simulated" named traces
        def _count_not_sim(fig):
            return sum(1 for t in fig.data if "not simulated" in (t.name or ""))
        assert _count_not_sim(fig_no) > _count_not_sim(fig_rep)

    def test_headpond_colour_reflects_level(self):
        geom = build_geometry()
        sim = Simulator()
        state_low = SceneState.from_simulator(sim, geom.pen_area)
        # manually build a higher pond-level state
        state_high = SceneState(t=0, h_p=state_low.h_p + 0.5, h_p0=state_low.h_p0,
                                Q=state_low.Q, y=state_low.y, y_cmd=state_low.y_cmd,
                                w=state_low.w, f=state_low.f, P_gen=state_low.P_gen,
                                h_t=state_low.h_t, Q_in=state_low.Q_in, P_load=state_low.P_load,
                                governor_on=state_low.governor_on, advection_m=state_low.advection_m)
        fig_h = build_figure(state_high, geom)
        # find headpond trace; z_max should equal the new pond level
        import plotly.graph_objects as go
        for tr in fig_h.data:
            if isinstance(tr, go.Mesh3d) and tr.name == "Headpond":
                assert max(tr.z) >= state_high.h_p - 0.01
                break
        else:
            pytest.fail("Headpond trace not found")


# ================================================================ figure_payload
class TestFigurePayload:
    def test_json_serialisable(self):
        geom = build_geometry()
        sim = Simulator()
        state = SceneState.from_simulator(sim, geom.pen_area)
        fig = build_figure(state, geom)
        payload = figure_payload(fig)
        txt = json.dumps(payload)
        assert len(txt) > 1000

    def test_has_data_key(self):
        geom = build_geometry()
        sim = Simulator()
        state = SceneState.from_simulator(sim, geom.pen_area)
        payload = figure_payload(build_figure(state, geom))
        assert "data" in payload
        assert "layout" in payload


# ================================================================ camera presets
class TestCameraPresets:
    @pytest.fixture
    def presets(self):
        return camera_presets(build_geometry())

    def test_has_overview(self, presets):
        assert "Overview" in presets

    def test_has_powerhouse(self, presets):
        assert "Powerhouse" in presets

    def test_preset_has_eye_center_up(self, presets):
        for name, cam in presets.items():
            assert "eye" in cam and "center" in cam and "up" in cam, name

    def test_eye_and_center_differ(self, presets):
        for name, cam in presets.items():
            e, c = cam["eye"], cam["center"]
            dist = math.sqrt(sum((e[k] - c[k]) ** 2 for k in "xyz"))
            assert dist > 0.01, f"Eye == center for preset {name}"


# ================================================================ scene_extent and aspect_ratio
class TestExtentAndAspect:
    def test_extent_keys(self):
        geom = build_geometry()
        ext = scene_extent(geom)
        assert set(ext.keys()) == {"x", "y", "z"}

    def test_ranges_positive(self):
        geom = build_geometry()
        ext = scene_extent(geom)
        for k in "xyz":
            lo, hi = ext[k]
            assert hi > lo, f"Zero or negative range on {k}"

    def test_aspect_longest_axis(self):
        geom = build_geometry()
        ext = scene_extent(geom)
        ar = aspect_ratio(ext, longest=3.0)
        assert max(ar.values()) == pytest.approx(3.0, rel=1e-6)

    def test_aspect_proportional(self):
        geom = build_geometry()
        ext = scene_extent(geom)
        ar = aspect_ratio(ext, longest=3.0)
        r = {k: ext[k][1] - ext[k][0] for k in "xyz"}
        # ratios between axes must match the real-world ratios
        for k1, k2 in [("x", "y"), ("x", "z"), ("y", "z")]:
            assert ar[k1] / ar[k2] == pytest.approx(r[k1] / r[k2], rel=1e-6)


# ================================================================ provenance_rows
class TestProvenanceRows:
    def test_returns_list_of_dicts(self):
        geom = build_geometry()
        rows = provenance_rows(geom)
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)

    def test_required_keys(self):
        geom = build_geometry()
        for row in provenance_rows(geom):
            for k in ("component", "item", "value", "unit", "classification", "source"):
                assert k in row, f"Missing {k} in {row}"

    def test_no_unknown_classification(self):
        geom = build_geometry()
        valid = {PUBLISHED, CALCULATED, SCHEMATIC, SIMULATED}
        for row in provenance_rows(geom):
            assert row["classification"] in valid, f"Unknown class: {row['classification']}"

    def test_published_rows_have_brochure_source(self):
        geom = build_geometry()
        for row in provenance_rows(geom):
            if row["classification"] == PUBLISHED:
                assert "Brochure" in row["source"], f"Published row missing 'Brochure': {row}"


def test_flow_markers_have_one_tracer_per_live_penstock():
    geom = build_geometry()
    state = SceneState.from_simulator(Simulator(), geom.pen_area)
    for replicate, n_live in ((True, geom.n_units), (False, 1)):
        tr = [t for t in build_figure(state, geom, replicate=replicate).data if t.name == "Flow markers"][0]
        assert len(tr.x) == 10 * n_live
        assert sum(c == "#f97316" for c in tr.marker.color) == n_live
