"""3D plant scene for the GBHP digital twin (Phase 3). Pure Python: no Streamlit import, unit-testable.

Two things live here:
  1. Geometry with provenance. Every dimension is tagged PUBLISHED (brochure value + PDF page, read from the source
     register), CALCULATED (derived from published/assumed values), or SCHEMATIC (illustrative layout, NOT a plant
     dimension). The brochure gives levels, counts, the penstock diameter/length and the channel cross-section; it gives
     no plan layout, powerhouse size, unit spacing or machine dimensions, so those are schematic.
  2. The mapping from simulation state (backend.simulator history) to visuals; see `SceneState` and `build_figure`.
     Nothing is animated independently of the model.

Axes: x downstream (m), y across (m), z elevation (m, true published levels).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import plotly.graph_objects as go

from backend import model as m
from backend.scene_geometry import box, cylinder, merge, validate

PUBLISHED, CALCULATED, SCHEMATIC, SIMULATED = "published", "calculated", "schematic", "simulated"

# Illustrative layout constants (metres). NOT plant dimensions: none of these appears in the brochure.
SCHEMATIC_LAYOUT = {
    "unit_pitch": (45.0, "Spacing between unit centre lines (about 4 penstock diameters)"),
    "pond_length": (215.0, "Headpond drawn length (plan shape is not in the brochure)"),
    "pond_margin": (40.0, "Headpond half-width beyond the outer penstocks"),
    "intake_length": (25.0, "Intake structure length in flow direction"),
    "powerhouse_len_x": (40.0, "Powerhouse size along flow"),
    "powerhouse_height": (52.0, "Powerhouse height above tailwater datum"),
    "turbine_radius": (7.0, "Turbine / spiral case radius"),
    "generator_radius": (8.5, "Generator radius"),
    "generator_height": (10.0, "Generator height"),
    "tailrace_length": (140.0, "Tailrace drawn length"),
    "transformer_size": (7.0, "Transformer bank footprint"),
    "switchyard_offset": (60.0, "Switchyard distance beyond the unit row"),
    "channel_drawn_length": (255.0, "Power channel drawn length (real length 51 906 m is compressed)"),
    "barrage_y_half": (60.0, "Barrage half-width as drawn"),
}
_UNIT_OFFSET_GATE_X = -16.0     # gate indicator position upstream of the powerhouse (schematic)
GATE_BAR_HEIGHT = 16.0          # full-scale height of the gate-opening bar (schematic)
N_PARTICLES = 10                # flow markers per penstock


def _reg(reg: dict, cat: str, name: str):
    row = reg[(cat, name)]
    return row["value"], int(row["pdf_page"]), row["unit"]


@dataclass(frozen=True)
class Geometry:
    n_units: int
    D: float
    L: float
    z_pond: float
    z_intake: float
    z_tw: float
    z_pen_in: float
    run: float
    pitch: float
    y_units: tuple
    pond_normal_barrage: float
    barrage_bays: int
    barrage_crest: float
    channel_bed: float
    channel_depth: float
    channel_side: float
    channel_length: float
    channel_slope_den: float
    channel_area: float
    pen_area: float
    p_full: float
    sw_bays: int
    q_full: float
    provenance: tuple = field(default_factory=tuple)

    def lay(self, key: str) -> float:
        return SCHEMATIC_LAYOUT[key][0]


def build_geometry(params: dict | None = None) -> Geometry:
    """Collect published values (from the register), calculated values, and schematic constants, with provenance rows."""
    reg = m.load_register()
    p = m.values(params or m.build_parameters())
    prov: list[dict] = []

    def pub(component, item, cat, name, scale=1.0, cast=float):
        v, page, unit = _reg(reg, cat, name)
        val = cast(v) * scale if cast is float else cast(v)
        prov.append(dict(component=component, item=item, value=val if cast is float else v, unit=unit, klass=PUBLISHED,
                         source=f"Brochure p.{page} ({cat}: {name})"))
        return val

    n = int(pub("Plant", "Number of units", "Plant", "Number of units"))
    D = pub("Penstocks", "Diameter (x5)", "Penstock", "Diameter")
    L = pub("Penstocks", "Length", "Penstock", "Length")
    pub("Penstocks", "Number", "Penstock", "Number")
    z_pond = pub("Headpond", "Normal pond level", "Power complex", "Headponds normal pond level")
    z_intake = pub("Intake", "Crest level", "Power complex", "Intake - crest level")
    pub("Intake", "Openings", "Power complex", "Intake - openings")
    pub("Headpond", "Siphon spillway crest level", "Power complex", "Siphon spillway crest level")
    pond_barrage = pub("Barrage", "Normal pond level", "Barrage", "Normal pond level")
    bays = int(pub("Barrage", "Standard bays (openings)", "Barrage", "Standard bays - openings"))
    crest = pub("Barrage", "Standard bays crest level", "Barrage", "Standard bays - crest level")
    bed = pub("Power channel", "Bed width", "Power channel", "Bed width")
    depth = pub("Power channel", "Full supply depth", "Power channel", "Full supply depth")
    clen = pub("Power channel", "Length", "Power channel", "Length")
    slope_txt = reg[("Power channel", "Longitudinal slope")]
    slope_den = float(re.match(r"1:(\d+)", slope_txt["value"]).group(1))
    prov.append(dict(component="Power channel", item="Longitudinal slope", value=slope_txt["value"], unit="-", klass=PUBLISHED,
                     source=f"Brochure p.{slope_txt['pdf_page']} (Power channel: Longitudinal slope)"))
    side_txt = reg[("Power channel", "Side slope")]
    side = float(re.match(r"1V:(\d+(?:\.\d+)?)H", side_txt["value"]).group(1))
    prov.append(dict(component="Power channel", item="Side slope (H per 1 V)", value=side_txt["value"], unit="-", klass=PUBLISHED,
                     source=f"Brochure p.{side_txt['pdf_page']} (Power channel: Side slope)"))
    sw_bays = int(pub("Switchyard", "500 kV bays", "Electrical", "Switchyard 500 kV bays"))
    pub("Switchyard", "Layout", "Electrical", "Switchyard layout", cast=str)
    pub("Transmission", "Voltage / circuits", "Electrical", "Transmission", cast=str)
    pub("Transformers", "Banks (3-phase)", "Electrical", "Transformer banks (3-phase)")
    q_full = pub("Units", "Full-gate flow per unit", "Plant", "Design flow per unit, full gate")
    pub("Units", "Turbine type", "Plant", "Turbine type", cast=str)

    z_tw = p["z_tw"]
    prov.append(dict(component="Tailwater", item="Tailwater level", value=round(z_tw, 2), unit="m", klass=CALCULATED,
                     source="pond level - design head - assumed friction head loss (model parameter z_tw)"))
    z_in = z_intake + D / 2
    dz = z_in - z_tw
    run = float(np.sqrt(L ** 2 - dz ** 2))
    prov.append(dict(component="Penstocks", item="Horizontal run of a straight 222 m pipe", value=round(run, 1), unit="m",
                     klass=CALCULATED, source="sqrt(L^2 - dz^2), dz = intake crest + D/2 - tailwater; straight alignment is an assumption"))
    pen_area = float(np.pi * D ** 2 / 4)
    prov.append(dict(component="Penstocks", item="Cross-section area", value=round(pen_area, 2), unit="m2", klass=CALCULATED,
                     source="pi*D^2/4; water velocity = Q/area"))
    ch_area = (bed + side * depth) * depth
    prov.append(dict(component="Power channel", item="Flow area at full supply depth", value=round(ch_area, 1), unit="m2",
                     klass=CALCULATED, source="(bed + side*depth)*depth from the published section"))
    prov.append(dict(component="Power channel", item="Fall over its length", value=round(clen / slope_den, 2), unit="m",
                     klass=CALCULATED, source="length / 9600 (published slope)"))
    p_full = float(p["eta"] * m.RHO * m.G * q_full * p["H_design"] / 1e6)
    prov.append(dict(component="Units", item="Power at full gate, design head (colour-scale maximum)", value=round(p_full, 2), unit="MW",
                     klass=CALCULATED, source="eta*rho*g*Q_full*H (estimate, not a measurement)"))
    for k, (v, why) in SCHEMATIC_LAYOUT.items():
        prov.append(dict(component="Layout", item=k, value=v, unit="m", klass=SCHEMATIC, source=why + " (illustrative, not a plant dimension)"))
    prov.append(dict(component="Layout", item="Penstock alignment / powerhouse position / machine sizes", value="illustrative", unit="-",
                     klass=SCHEMATIC, source="not documented in the brochure; drawn for visualisation only"))
    pitch = SCHEMATIC_LAYOUT["unit_pitch"][0]
    ys = tuple(float((i - (n - 1) / 2) * pitch) for i in range(n))
    return Geometry(n, D, L, z_pond, z_intake, z_tw, z_in, run, pitch, ys, pond_barrage, bays, crest, bed, depth, side, clen,
                    slope_den, ch_area, pen_area, p_full, sw_bays, q_full, tuple(prov))


# ------------------------------------------------------------------ state
@dataclass(frozen=True)
class SceneState:
    """Everything the scene shows, taken from the simulator (nothing else)."""
    t: float
    h_p: float
    h_p0: float
    Q: float
    y: float
    y_cmd: float
    w: float
    f: float
    P_gen: float
    h_t: float
    Q_in: float
    P_load: float
    governor_on: bool
    advection_m: float      # distance a water particle has travelled in the penstock: integral of Q/A dt

    @classmethod
    def from_simulator(cls, sim, pen_area: float) -> "SceneState":
        a = sim.arrays()
        last = sim.latest()
        adv = float(np.trapezoid(a["Q"], a["t"]) / pen_area) if len(a["t"]) > 1 else 0.0
        return cls(t=last["t"], h_p=last["h_p"], h_p0=float(a["h_p"][0]), Q=last["Q"], y=last["y"], y_cmd=last["y_cmd"],
                   w=last["w"], f=last["f"], P_gen=last["P_gen"], h_t=last["h_t"], Q_in=last["Q_in"], P_load=last["P_load"],
                   governor_on=bool(last["governor_on"]), advection_m=adv)

    def summary(self, geom: Geometry, replicate: bool) -> dict:
        """The numbers bound to the visuals (also shipped to the browser so it can be checked there)."""
        return dict(t=self.t, h_p=self.h_p, dh_p_mm=(self.h_p - self.h_p0) * 1000, Q=self.Q, v_pen=self.Q / geom.pen_area,
                    y=self.y, y_cmd=self.y_cmd, w=self.w, f=self.f, P_gen=self.P_gen, h_t=self.h_t, Q_in=self.Q_in,
                    advection_m=self.advection_m, units_live=geom.n_units if replicate else 1, governor_on=self.governor_on)


def particle_fractions(advection_m: float, length: float, n: int = N_PARTICLES) -> np.ndarray:
    """Positions (0..1 along the pipe) of n equally spaced water markers advected by the real bulk velocity."""
    spacing = length / n
    return ((advection_m + np.arange(n) * spacing) % length) / length


# ------------------------------------------------------------------ figure
def _mesh(mesh, name, hover, **kw):
    r = lambda a: np.round(np.asarray(a, float), 2)
    return go.Mesh3d(x=r(mesh["x"]), y=r(mesh["y"]), z=r(mesh["z"]), i=mesh["i"], j=mesh["j"], k=mesh["k"], name=name,
                     hovertext=hover, hoverinfo="text", flatshading=True, lighting=dict(ambient=0.75, diffuse=0.6), **kw)


def _channel_prism(x0, x1, bed, depth, side, z_surf):
    """Water prism with the published trapezoidal section (bed width, depth, side slope), drawn over a compressed length."""
    top = bed / 2 + side * depth
    zb = z_surf - depth
    sec = [(-bed / 2, zb), (bed / 2, zb), (top, z_surf), (-top, z_surf)]
    x = [x0] * 4 + [x1] * 4
    y = [s[0] for s in sec] * 2
    z = [s[1] for s in sec] * 2
    quads = [(0, 1, 5, 4), (1, 2, 6, 5), (3, 0, 4, 7), (3, 2, 1, 0), (7, 6, 2, 3)]
    tri = []
    for a, b, c, d in quads:
        tri += [(a, b, c), (a, c, d)]
    tri = np.array(tri)
    return {"x": np.array(x, float), "y": np.array(y, float), "z": np.array(z, float), "i": tri[:, 0], "j": tri[:, 1], "k": tri[:, 2]}


def _lerp_color(c0, c1, f):
    f = float(min(max(f, 0.0), 1.0))
    return "rgb(%d,%d,%d)" % tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))


def build_figure(state: SceneState, geom: Geometry, replicate: bool = True, p_ref: float | None = None) -> go.Figure:
    g = geom
    p_ref = p_ref or g.p_full
    n = g.n_units
    xt = g.run
    half = (n - 1) / 2 * g.pitch
    zt = g.z_tw
    traces = []
    q_frac = state.Q / g.q_full
    p_frac = state.P_gen / p_ref
    live = [True] * n if replicate else [i == 0 for i in range(n)]

    def tag(name, klass, detail=""):
        return f"<b>{name}</b><br>[{klass}]" + (f"<br>{detail}" if detail else "")

    # --- water bodies (translucent)
    pond_x0 = -g.lay("pond_length") - g.lay("intake_length")
    pond = box(pond_x0, -g.lay("intake_length"), -half - g.lay("pond_margin"), half + g.lay("pond_margin"), g.z_intake, state.h_p)
    traces.append(_mesh(pond, "Headpond", tag("Headpond", SIMULATED + " level", f"surface {state.h_p:.3f} m ({(state.h_p - state.h_p0) * 1000:+.2f} mm from start)<br>"
                        f"normal pond level 334 m [{PUBLISHED}]; plan shape + floor at intake crest are schematic"), color="#3b82c4", opacity=0.35))
    tail = box(xt + 50, xt + 50 + g.lay("tailrace_length"), -half - 40, half + 40, zt - 10, zt)
    traces.append(_mesh(tail, "Tailrace", tag("Tailrace / tailwater", CALCULATED, f"level {zt:.2f} m = pond - design head - assumed friction loss<br>tailrace shape is schematic"),
                        color="#5b9bd5", opacity=0.35))
    sy = g.lay("barrage_y_half")
    pool = box(-565 - 70, -565, -sy, sy, g.barrage_crest - 12, g.pond_normal_barrage)
    traces.append(_mesh(pool, "Barrage pool", tag("Barrage pool", PUBLISHED, f"normal pond level {g.pond_normal_barrage:g} m (p.12); extent schematic"),
                        color="#3b82c4", opacity=0.30))
    cx0, cx1 = -548.0, -548.0 + g.lay("channel_drawn_length")
    traces.append(_mesh(_channel_prism(cx0, cx1, g.channel_bed, g.channel_depth, g.channel_side, g.z_pond), "Power channel",
                        tag("Power channel", PUBLISHED + " section", f"bed {g.channel_bed:g} m, depth {g.channel_depth:g} m, side slope 1V:{g.channel_side:g}H (p.12)<br>"
                            f"real length {g.channel_length:,.0f} m, drawn compressed (~{g.channel_length / g.lay('channel_drawn_length'):.0f}:1); "
                            f"fall {g.channel_length / g.channel_slope_den:.1f} m (calculated)<br>"
                            f"inflow per unit share {state.Q_in:.0f} m3/s ({SIMULATED})"),
                        color="#3b82c4", opacity=0.45))

    # --- grey structures
    parts = [box(-g.lay("intake_length"), 0, -half - 12, half + 12, g.z_intake, g.z_pond + 8)]
    parts.append(box(-565, -548, -sy, sy, g.barrage_crest - 12, g.barrage_crest))                       # barrage weir body
    for k in range(g.barrage_bays + 1):                                               # piers between the published 20 bays
        yy = -sy + k * (2 * sy / g.barrage_bays)
        parts.append(box(-565, -548, yy - 0.8, yy + 0.8, g.barrage_crest, g.pond_normal_barrage + 3))
    tz = g.lay("transformer_size")
    for y in g.y_units:
        parts.append(box(xt + 34, xt + 34 + tz, y - tz / 2, y + tz / 2, zt, zt + tz))      # transformer bank
    sw_y0 = half + g.lay("switchyard_offset")
    parts.append(box(xt - 10, xt + 70, sw_y0, sw_y0 + 70, zt - 0.5, zt + 1.5))             # switchyard slab
    for k in range(g.sw_bays):                                                        # published: 6 bays
        xx = xt - 5 + k * (70 / g.sw_bays)
        parts.append(box(xx, xx + 5, sw_y0 + 25, sw_y0 + 45, zt + 1.5, zt + 14))
    struct = merge(parts)
    traces.append(_mesh(struct, "Structures", tag("Structures", SCHEMATIC, "intake (crest 305.5 m, 10 openings, p.12), barrage (20 bays, crest 332.2 m, p.12), "
                        "transformers (5 banks, p.17), switchyard (6 x 500 kV bays, breaker-and-half, p.12/17)<br>positions and sizes are schematic"),
                        color="#9aa3ad", opacity=1.0))
    ph = box(xt - 14, xt + g.lay("powerhouse_len_x") - 14, -half - 25, half + 25, zt - 12, zt + g.lay("powerhouse_height"))
    traces.append(_mesh(ph, "Powerhouse", tag("Powerhouse", SCHEMATIC, "size and position are illustrative (not in the brochure)"), color="#c9ced4", opacity=0.16))

    # --- penstocks (published count / diameter / length; straight alignment assumed)
    pen_live, pen_dead = [], []
    for i, y in enumerate(g.y_units):
        c = cylinder((0, y, g.z_pen_in), (xt, y, zt), g.D / 2, n=16, caps=False)
        (pen_live if live[i] else pen_dead).append(c)
    if pen_live:
        mm = merge(pen_live)
        traces.append(_mesh(mm, "Penstocks", tag(f"Penstock (x{n})", PUBLISHED + " D, L; " + SIMULATED + " flow",
                            f"diameter {g.D:g} m, length {g.L:g} m (p.12); straight alignment is an assumption<br>flow {state.Q:.1f} m3/s, "
                            f"velocity {state.Q / g.pen_area:.2f} m/s (calculated Q/A)"),
                            intensity=np.full(len(mm["x"]), q_frac), colorscale=[[0, "#cfe3f4"], [1, "#08306b"]], cmin=0, cmax=1, showscale=True, opacity=0.55,
                            colorbar=dict(title=dict(text="Flow / 460 m3/s", side="right"), x=1.0, y=0.78, len=0.38, thickness=12)))
    if pen_dead:
        traces.append(_mesh(merge(pen_dead), "Penstocks (not simulated)", tag("Penstock", PUBLISHED + " D, L", "unit not simulated (replicas off)"), color="#b8bec6", opacity=0.9))

    # --- turbines, generators, gate bars
    turb_l, turb_d, gen_l, gen_d, shaft, gate_fill = [], [], [], [], [], []
    tr, gr = g.lay("turbine_radius"), g.lay("generator_radius")
    for i, y in enumerate(g.y_units):
        (turb_l if live[i] else turb_d).append(cylinder((xt, y, zt - 3), (xt, y, zt + 5), tr, n=20))
        (gen_l if live[i] else gen_d).append(cylinder((xt, y, zt + 8), (xt, y, zt + 8 + g.lay("generator_height")), gr, n=20))
        shaft.append(cylinder((xt, y, zt + 5), (xt, y, zt + 8), 1.5, n=10))
        draft = box(xt - 5, xt + 50, y - 5, y + 5, zt - 9, zt - 1)
        (turb_l if live[i] else turb_d).append(draft)
        if live[i]:
            h = max(GATE_BAR_HEIGHT * state.y, 0.05)
            gate_fill.append(box(xt + _UNIT_OFFSET_GATE_X, xt + _UNIT_OFFSET_GATE_X + 2, y + 9, y + 11, zt + 2, zt + 2 + h))
    if turb_l:
        traces.append(_mesh(merge(turb_l), "Turbines", tag("Francis turbine + draft tube", SCHEMATIC + " geometry; " + SIMULATED + " state",
                            f"turbine type Francis [{PUBLISHED}, p.12]; net head {state.h_t:.2f} m, flow {state.Q:.1f} m3/s, gate {state.y:.3f} pu<br>machine sizes are schematic"),
                            intensity=np.full(len(merge(turb_l)["x"]), state.y), colorscale=[[0, "#d8e6d2"], [1, "#2f7d32"]], cmin=0, cmax=1, showscale=False))
    if turb_d:
        traces.append(_mesh(merge(turb_d), "Turbines (not simulated)", tag("Francis turbine (not simulated)", SCHEMATIC), color="#b8bec6"))
    if gen_l:
        gm = merge(gen_l)
        traces.append(_mesh(gm, "Generators", tag("Generator", SCHEMATIC + " geometry; " + SIMULATED + " state",
                            f"power {state.P_gen:.1f} MW (colour), frequency {state.f:.3f} Hz, speed {state.w:.4f} pu<br>"
                            f"colour scale max {p_ref:.1f} MW = full-gate estimate [{CALCULATED}]"),
                            intensity=np.full(len(gm["x"]), p_frac), colorscale=[[0, "#fff1d6"], [1, "#d62f0f"]], cmin=0, cmax=1, showscale=True,
                            colorbar=dict(title=dict(text="Power / 292.7 MW (estimate)", side="right"), x=1.0, y=0.30, len=0.38, thickness=12)))
    if gen_d:
        traces.append(_mesh(merge(gen_d), "Generators (not simulated)", tag("Generator (not simulated)", SCHEMATIC), color="#b8bec6"))
    traces.append(_mesh(merge(shaft), "Shafts", tag("Shaft", SCHEMATIC), color="#6b7280"))
    if gate_fill:
        traces.append(_mesh(merge(gate_fill), "Gate opening", tag("Gate opening bar", SIMULATED, f"gate position {state.y:.3f} pu (command {state.y_cmd:.3f} pu); full scale = 1.0 pu"), color="#16a34a"))
    # gate bar outlines (full scale)
    ox, oy, oz = [], [], []
    for i, y in enumerate(g.y_units):
        if live[i]:
            x0 = xt + _UNIT_OFFSET_GATE_X
            for (xa, ya, za), (xb, yb, zb) in [((x0, y + 9, zt + 2), (x0, y + 9, zt + 2 + GATE_BAR_HEIGHT)),
                                                ((x0 + 2, y + 9, zt + 2), (x0 + 2, y + 9, zt + 2 + GATE_BAR_HEIGHT))]:
                ox += [xa, xb, None]; oy += [ya, yb, None]; oz += [za, zb, None]
    if ox:
        traces.append(go.Scatter3d(x=ox, y=oy, z=oz, mode="lines", line=dict(color="#374151", width=3), hoverinfo="skip", showlegend=False, name="Gate scale"))

    # --- water-flow markers: advected by the real bulk velocity Q/A (integrated from the simulation history)
    fr = particle_fractions(state.advection_m, g.L)
    px, py, pz = [], [], []
    for i, y in enumerate(g.y_units):
        if live[i]:
            px += list(fr * xt); py += [y] * len(fr); pz += list(g.z_pen_in + fr * (zt - g.z_pen_in))
    # Marker 0 of each pipe is an orange "tracer": the white markers are 22.2 m apart, and one refresh (5 s at ~4.5 m/s) moves
    # water about that far, so they can look stationary (sampling/aliasing). The tracer repeats only every 222 m, so its
    # motion per refresh is unambiguous.
    is_tracer = np.tile(np.arange(len(fr)) == 0, len(px) // max(len(fr), 1))
    traces.append(go.Scatter3d(x=np.round(px, 2), y=np.round(py, 2), z=np.round(pz, 2), mode="markers",
                               marker=dict(size=np.where(is_tracer, 8, 5).tolist(), color=np.where(is_tracer, "#f97316", "#e0f2fe").tolist(),
                                           line=dict(color="#08306b", width=1.5)),
                               hovertext=f"Water marker: moves at the simulated bulk velocity {state.Q / g.pen_area:.2f} m/s", hoverinfo="text", name="Flow markers", showlegend=False))

    # --- electrical: transformer -> switchyard lines, coloured by simulated power; transmission lines to the grid
    col = _lerp_color((120, 130, 140), (214, 47, 15), p_frac)
    lx, ly, lz = [], [], []
    for i, y in enumerate(g.y_units):
        if live[i]:
            lx += [xt + 34 + tz / 2, xt + 34 + tz / 2, None]; ly += [y, sw_y0 + 35, None]; lz += [zt + tz, zt + tz, None]
    if lx:
        traces.append(go.Scatter3d(x=lx, y=ly, z=lz, mode="lines", line=dict(color=col, width=5), hovertext=f"Generator to switchyard: {state.P_gen:.1f} MW per live unit ({SIMULATED}); routing is schematic",
                                   hoverinfo="text", showlegend=False, name="Power"))
    gx, gy, gz = [], [], []
    for dx in (-2.0, 2.0):
        gx += [xt + 35 + dx, xt + 35 + dx, None]; gy += [sw_y0 + 35, sw_y0 + 140, None]; gz += [zt + 13, zt + 13, None]
    traces.append(go.Scatter3d(x=gx, y=gy, z=gz, mode="lines", line=dict(color="#1f2937", width=4), hovertext="500 kV double circuit (published, p.17); route is schematic",
                               hoverinfo="text", showlegend=False, name="Transmission"))

    # --- labels (text markers). Tags show provenance; hover gives details.
    lab = [
        (pond_x0 + 20, 60, state.h_p + 14, f"Headpond {state.h_p:.3f} m [{SIMULATED}]"),
        (-g.lay("intake_length") / 2, half + 30, g.z_pond + 16, "Intake [crest 305.5 m: published]"),
        (xt * 0.5, half + 25, (g.z_pen_in + zt) / 2 + 12, f"{n} penstocks, D {g.D:g} m, L {g.L:g} m [published]"),
        (xt - 14, -half - 45, zt + g.lay("powerhouse_height") + 8, "Powerhouse [schematic size]"),
        (xt + 120, 0, zt + 6, f"Tailwater {zt:.1f} m [calculated]"),
        (xt + 35, sw_y0 + 35, zt + 24, f"Switchyard {g.sw_bays} x 500 kV [published]"),
        (xt + 60, -half - 28, zt + 6, "Transformers [schematic position]"),
        (-556, sy + 12, g.pond_normal_barrage + 10, f"Barrage, {g.barrage_bays} bays, pool {g.pond_normal_barrage:g} m [published]"),
        ((cx0 + cx1) / 2, -50, g.z_pond + 16, f"Power channel {g.channel_length / 1000:.1f} km, compressed [published section]"),
        (xt, g.y_units[0], zt + 8 + g.lay("generator_height") + 5, "U1 (simulated)"),
    ]
    for i in range(1, n):
        lab.append((xt, g.y_units[i], zt + 8 + g.lay("generator_height") + 5, f"U{i + 1}" + (" (replica)" if replicate else " (off)")))
    lab.append((xt + 120, 40, zt + 34, f"Live unit: {state.P_gen:.1f} MW | {state.f:.2f} Hz | gate {state.y:.3f} | {state.Q:.0f} m3/s | head {state.h_t:.1f} m [{SIMULATED}]"))
    lab.append((xt + 120, -40, zt + 26, "Units 2-5 repeat unit 1 (identical-unit assumption)" if replicate else "Units 2-5 not simulated"))
    traces.append(go.Scatter3d(x=[a for a, *_ in lab], y=[b for _, b, *_ in lab], z=[c for _, _, c, _ in lab], mode="text", text=[t for *_, t in lab],
                               textfont=dict(size=11, color="#111827"), hoverinfo="skip", showlegend=False, name="Labels"))

    fig = go.Figure(traces)
    ext = scene_extent(g)
    ar = aspect_ratio(ext)
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0), showlegend=False, uirevision="plant3d", paper_bgcolor="#f4f6f8",
        scene=dict(aspectmode="manual", aspectratio=ar,      # true proportions: same metres-per-unit on every axis (no vertical exaggeration)
                   xaxis=dict(range=ext["x"], title="x downstream (m)", showbackground=False, gridcolor="#d5dae0"),
                   yaxis=dict(range=ext["y"], title="y across (m)", showbackground=False, gridcolor="#d5dae0"),
                   zaxis=dict(range=ext["z"], title="elevation (m)", showbackground=True, backgroundcolor="#eef1f4", gridcolor="#d5dae0"),
                   camera=camera_presets(g)["Overview"]),
    )
    return fig


def scene_extent(g: Geometry) -> dict:
    half = (g.n_units - 1) / 2 * g.pitch
    sw_y0 = half + g.lay("switchyard_offset")
    return dict(x=(-640.0, g.run + 200), y=(-half - 60, sw_y0 + 150), z=(g.z_tw - 14, g.z_pond + 40))


def aspect_ratio(ext: dict, longest: float = 3.0) -> dict:
    r = {k: ext[k][1] - ext[k][0] for k in "xyz"}
    s = longest / max(r.values())
    return {k: r[k] * s for k in "xyz"}


def to_scene(point, ext: dict) -> dict:
    """Data coordinates (m) -> plotly camera coordinates, for the manual aspect ratio used above."""
    ar = aspect_ratio(ext)
    out = {}
    for k, v in zip("xyz", point):
        lo, hi = ext[k]
        out[k] = (v - (lo + hi) / 2) / (hi - lo) * ar[k]
    return out


def _cam(g, target, offset, up=(0, 0, 1)):
    ext = scene_extent(g)
    c = to_scene(target, ext)
    s = aspect_ratio(ext)["x"] / (ext["x"][1] - ext["x"][0])        # camera units per metre (same on all axes)
    eye = {k: c[k] + s * o for k, o in zip("xyz", offset)}
    return dict(eye=eye, center=c, up=dict(x=up[0], y=up[1], z=up[2]))


def camera_presets(g: Geometry) -> dict:
    """Named viewpoints, defined in metres around real plant points (the user can still rotate, zoom and pan freely)."""
    xt, zt = g.run, g.z_tw
    return {
        "Overview": _cam(g, (-200, 60, zt + 30), (-330, -1150, 820)),
        "Powerhouse": _cam(g, (xt + 10, 0, zt + 12), (170, -330, 210)),
        "Penstocks (side)": _cam(g, (xt / 2, 0, (g.z_pen_in + zt) / 2), (0, -420, 30)),
        "Headpond & intake": _cam(g, (-110, 0, g.z_pond - 10), (-120, -420, 230)),
        "Plan (top)": _cam(g, (xt / 2 - 60, 30, zt), (0, 1, 1100), up=(0, 1, 0)),
    }


def figure_payload(fig: go.Figure) -> dict:
    """JSON-safe dict for the browser component."""
    import json
    return json.loads(fig.to_json())


def provenance_rows(geom: Geometry) -> list[dict]:
    return [dict(component=r["component"], item=r["item"], value=r["value"], unit=r["unit"], classification=r["klass"], source=r["source"])
            for r in geom.provenance]
