"""One-click demonstration scenarios (Phase 4). Pure Python (no Streamlit), unit-testable.

A scenario is only a SCHEDULE OF INPUTS (load, gate set-point, inflow, governor on/off) applied to the real model:
every result comes from backend.simulator.Simulator (plant = backend.model, governor = backend.governor).
Nothing here stores or draws output traces.

Typical use:
    spec, errors, warnings = build_scenario("load_step", new_load=280.0)
    result = run_scenario(spec)                 # complete run (tests, export)
or, for a live dashboard run, ScenarioPlayer(spec).advance(sim, dt) once per refresh.
"""
from __future__ import annotations

import csv
import io
import json
import platform
import zipfile
from dataclasses import asdict, dataclass, field

import numpy as np

from backend import model as m
from backend.governor import GOVERNOR_ASSUMPTIONS, GovernorSettings
from backend.simulator import COLUMNS, MAX_DURATION, RECORD_DT, Simulator, _is_number, validate_inputs

# ----------------------------------------------------------------------- definitions
# Defaults are DEMONSTRATION CHOICES (assumed), not plant operating records. The start is always the Phase 1 operating
# point (gate 400/460, pond 334 m, 254.51 MW, calculated); "+10 %" is about 280 MW.
SCENARIOS = {
    "normal": dict(
        title="Normal operation",
        purpose="Unit held at the steady operating point with no disturbance. Shows that the model sits in equilibrium.",
        governor_on=True, new_load=None, t_event=None, duration=60.0, compare=False,
        watch="All values stay constant: flow 400 m3/s, head 69 m, power 254.5 MW, 50 Hz."),
    "load_step": dict(
        title="Electrical load increase (load step)",
        purpose="Load steps up by about 10 % at t_event. The governor opens the gate; power first dips (water inertia) then rises.",
        governor_on=True, new_load=280.0, t_event=5.0, duration=120.0, compare=False,
        watch="Non-minimum-phase power dip, frequency dip then recovery to slightly below 50 Hz (5 % droop)."),
    "load_rejection": dict(
        title="Sudden load rejection",
        purpose="Load is disconnected at t_event. The governor closes the gate; its speed is set by the (assumed) PI gains and limited by the closing-rate limit.",
        governor_on=True, new_load=0.0, t_event=5.0, duration=120.0, compare=False,
        watch="Large overspeed while the gate closes, head rise in the penstock, settling above 50 Hz (droop at no load). "
              "Full rejection leaves the model's valid speed range: see the warnings."),
    "overload": dict(
        title="Overload",
        purpose="Load above what the unit can deliver at full gate. The governor drives the gate to its limit.",
        governor_on=True, new_load=320.0, t_event=5.0, duration=120.0, compare=False,
        watch="Gate saturates at 1.0 pu; power stops at the full-gate value; frequency settles far below 50 Hz."),
    "governor_compare": dict(
        title="Governor enabled vs disabled",
        purpose="The same load step is simulated twice: governor ON (live run) and governor OFF (reference run, dashed).",
        governor_on=True, new_load=280.0, t_event=5.0, duration=120.0, compare=True,
        watch="With the governor, frequency recovers near 50 Hz; without it the gate stays fixed and frequency keeps falling "
              "until load damping balances the deficit."),
}


@dataclass(frozen=True)
class Event:
    t: float
    P_load: float


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    title: str
    purpose: str
    watch: str
    governor_on: bool
    duration: float
    events: tuple                      # tuple[Event]
    compare: bool                      # also run with governor OFF as a reference
    y_set: float                       # gate set-point (pu): operating-point value
    Q_in: float                        # inflow (m3/s): operating-point value
    P_load0: float                     # load before the first event (MW)
    assumed: tuple = field(default_factory=tuple)   # human-readable list of scenario assumptions

    def inputs_at(self, t: float):
        """(y_set, P_load, Q_in) in force at time t (an event at t_e applies from t_e onwards)."""
        P = self.P_load0
        for e in self.events:
            if t >= e.t - 1e-9:
                P = e.P_load
        return self.y_set, P, self.Q_in


def full_gate_capacity(p: dict) -> float:
    """Steady power with the gate fully open at normal pond level (CALCULATED from the model, about 291.67 MW)."""
    return float(m.steady_state(p, y0=1.0)["y0"][2])


def build_scenario(key: str, new_load=None, t_event=None, duration=None, params=None):
    """Return (spec or None, errors, warnings). Invalid inputs are REJECTED with a message, never clipped."""
    if key not in SCENARIOS:
        return None, [f"Unknown scenario '{key}'. Choose one of: {', '.join(SCENARIOS)}"], []
    d = SCENARIOS[key]
    p = m.values(params or m.build_parameters())
    ss = m.steady_state(p)
    y0, P0, Q0 = (float(v) for v in ss["u0"])
    new_load = d["new_load"] if new_load is None else new_load
    t_event = d["t_event"] if t_event is None else t_event
    duration = d["duration"] if duration is None else duration
    errors, warnings = [], []

    def num(name, v, lo, hi, unit, why=""):
        if not _is_number(v):
            errors.append(f"{name} must be a finite number (got {v!r}).")
            return False
        if not lo <= v <= hi:
            errors.append(f"{name} = {v:g} {unit} is outside the allowed range {lo:g} to {hi:g} {unit}{why}.")
            return False
        return True

    num("Duration", duration, 1.0, MAX_DURATION, "s", " (runs are capped at 1 h; see the pond-level note)")
    events = ()
    if d["new_load"] is not None:
        ok_l = num("New load", new_load, 0.0, p["S_base"], "MW", " (upper limit = assumed generator base S_base)")
        ok_t = num("Event time", t_event, 0.0, MAX_DURATION, "s")
        if ok_t and _is_number(duration) and t_event >= duration:
            errors.append(f"Event time ({t_event:g} s) must be earlier than the duration ({duration:g} s), "
                          "otherwise the disturbance never happens.")
        if ok_l:
            cap = full_gate_capacity(p)
            if new_load > cap:
                warnings.append(f"New load {new_load:.1f} MW exceeds the model's full-gate capacity {cap:.2f} MW "
                                f"(calculated at normal pond level). It is NOT reduced: the gate will saturate and "
                                f"frequency will fall until load damping (assumed D) balances the deficit.")
            if key in ("load_step", "governor_compare") and abs(new_load - P0) < 1e-6:
                warnings.append("New load equals the starting load: there is no disturbance to observe.")
        events = (Event(float(t_event), float(new_load)),) if not errors else ()
    if errors:
        return None, errors, warnings
    assumed = (
        f"Start: Phase 1 operating point (gate {y0:.4f} pu = 400/460, pond {p['z_pond']:g} m, load {P0:.2f} MW calculated).",
        f"Inflow held at {Q0:.1f} m3/s (equal to the starting turbine flow, so the pond starts in balance); "
        "this exceeds the per-unit share of the channel design flow (320 m3/s, brochure p.12).",
        "Gate set-point (governor load reference) is not changed by the scenario.",
        "Load changes are instantaneous steps (ideal breaker); load at nominal frequency, with assumed damping D.",
        "Governor settings, H, D, T_y, y_min, S_base and friction loss are ASSUMED (see parameter register).",
        "Event time, new load and duration are demonstration choices, not plant records.",
    )
    spec = ScenarioSpec(key=key, title=d["title"], purpose=d["purpose"], watch=d["watch"], governor_on=d["governor_on"],
                        duration=float(duration), events=events, compare=d["compare"], y_set=y0, Q_in=Q0, P_load0=P0,
                        assumed=assumed)
    # inputs must also pass the simulator's own validation
    for e in spec.events:
        errors += validate_inputs(p, spec.y_set, e.P_load, spec.Q_in, spec.duration)
    return (None if errors else spec), errors, warnings


# ------------------------------------------------------------------------- running
class ScenarioPlayer:
    """Applies a scenario's input schedule to a Simulator, splitting steps exactly at event times."""

    def __init__(self, spec: ScenarioSpec):
        self.spec = spec

    def done(self, sim: Simulator) -> bool:
        return sim.t >= self.spec.duration - 1e-9

    def advance(self, sim: Simulator, dt: float, governor_on: bool | None = None) -> None:
        """Advance by dt (or to the end of the scenario). Raises RuntimeError/ValueError from the solver/validation."""
        gov = self.spec.governor_on if governor_on is None else governor_on
        t_stop = min(sim.t + dt, self.spec.duration)
        while sim.t < t_stop - 1e-9:
            nxt = [e.t for e in self.spec.events if sim.t + 1e-9 < e.t < t_stop - 1e-9]
            t_seg = min(nxt) if nxt else t_stop
            # tiny segments (shorter than the 0.25 s record interval) are still integrated exactly
            sim.step(t_seg - sim.t, *self.spec.inputs_at(sim.t), gov)


@dataclass
class ScenarioResult:
    spec: ScenarioSpec
    main: Simulator
    reference: Simulator | None
    error: str | None
    notices: list


def run_scenario(spec: ScenarioSpec, gov: GovernorSettings | None = None, params=None) -> ScenarioResult:
    """Run the full scenario (and its governor-OFF reference if requested). Solver failures are caught and reported,
    keeping the results computed up to the failure."""
    gov = gov or GovernorSettings()
    main = Simulator(params=params, gov=gov)
    main.reset(governor_on=spec.governor_on)
    err = None
    try:
        ScenarioPlayer(spec).advance(main, spec.duration)
    except (RuntimeError, ValueError) as exc:
        err = f"Simulation stopped at t = {main.t:.2f} s: {exc}"
    ref = run_reference(spec, gov, params) if spec.compare else None
    return ScenarioResult(spec, main, ref, err, assess(main, gov) + ([("error", err)] if err else []))


def run_reference(spec: ScenarioSpec, gov: GovernorSettings | None = None, params=None) -> Simulator:
    """Same inputs with the governor OFF (gate fixed at its set-point)."""
    ref = Simulator(params=params, gov=gov or GovernorSettings())
    ref.reset(governor_on=False)
    ScenarioPlayer(spec).advance(ref, spec.duration, governor_on=False)
    return ref


# ------------------------------------------------------------------- result checks
SPEED_VALID = (0.9, 1.1)    # pu: outside this the constant-efficiency, speed-independent turbine model is not credible


def assess(sim: Simulator, gov: GovernorSettings) -> list:
    """Plain-language checks of a finished (or partial) run: limits reached, validity range, numerical sanity.
    Returns [(level, message)], level in {"error", "warning", "info"}."""
    a = sim.arrays()
    p = sim.p
    out = []
    if len(a["t"]) < 2:
        return out
    if not all(np.isfinite(a[c]).all() for c in COLUMNS):
        out.append(("error", "Non-finite values (NaN/inf) in the results: the run is not usable."))
        return out
    dt = np.diff(a["t"])
    span = lambda mask: float(np.sum(dt[mask[1:]]))          # seconds for which a condition held
    gov_on = a["governor_on"] > 0.5
    sat_hi = gov_on & (a["y_cmd"] >= gov.y_hi - 1e-9)
    if sat_hi.any():
        out.append(("warning", f"Governor command at its upper limit {gov.y_hi:g} pu (gate fully open) for {span(sat_hi):.1f} s: "
                               "the unit cannot produce more power; frequency is not restored."))
    sat_lo = gov_on & (a["y_cmd"] <= gov.y_lo + 1e-9)
    if sat_lo.any():
        out.append(("warning", f"Governor command at its lower limit {gov.y_lo:g} pu for {span(sat_lo):.1f} s."))
    floor = a["y"] < p["y_min"]
    if floor.any():
        out.append(("warning", f"Gate below the model's numerical floor y_min = {p['y_min']:g} pu (assumed) for {span(floor):.1f} s: "
                               "the hydraulics treat it as {0:g} pu open, so the model cannot fully stop the flow.".format(p['y_min'])))
    vel = np.diff(a["y"]) / dt
    rate = (vel >= gov.rate_open * 0.98) | (vel <= -gov.rate_close * 0.98)
    if rate.any():
        out.append(("info", f"Gate moving at its assumed rate limit (open {gov.rate_open:g} / close {gov.rate_close:g} pu/s) "
                            f"for about {float(np.sum(dt[rate])):.1f} s."))
    w_lo, w_hi = float(a["w"].min()), float(a["w"].max())
    if w_hi > SPEED_VALID[1] or w_lo < SPEED_VALID[0]:
        out.append(("warning", f"Rotor speed reached {w_lo:.3f} to {w_hi:.3f} pu ({w_lo * p['f_nom']:.1f} to {w_hi * p['f_nom']:.1f} Hz), "
                               f"outside {SPEED_VALID[0]}-{SPEED_VALID[1]} pu. The model ignores the effect of speed on turbine flow "
                               "and efficiency and has no overspeed protection or unit trip, so values here are only indicative."))
    reg = m.load_register()
    spill = float(reg[("Power complex", "Siphon spillway crest level")]["value"])
    if a["h_p"].max() > spill:
        out.append(("warning", f"Pond level exceeded the siphon spillway crest {spill:g} m (brochure p.12); spilling is not modelled."))
    if a["h_p"].min() < p["z_pond"] - p["dh_live"]:
        out.append(("warning", f"Pond level fell below the assumed live range ({p['z_pond'] - p['dh_live']:g} m)."))
    hmax = float(a["h_t"].max())
    if hmax > 1.1 * p["H_design"]:
        out.append(("info", f"Net head peaked at {hmax:.1f} m (design 69 m, brochure): pressure rise from decelerating the water "
                            "column (rigid-column model, no water hammer waves)."))
    out.append(("info", f"Ranges: power {a['P_gen'].min():.1f} to {a['P_gen'].max():.1f} MW, frequency {a['f'].min():.2f} to "
                        f"{a['f'].max():.2f} Hz, flow {a['Q'].min():.1f} to {a['Q'].max():.1f} m3/s, gate {a['y'].min():.3f} to {a['y'].max():.3f} pu."))
    return out


# ------------------------------------------------------------------------- export
# Column order of the exported CSV, with plain names and units (same data as Simulator.COLUMNS, renamed).
EXPORT_COLUMNS = [
    ("t", "time_s", "s", "Simulation time"),
    ("Q", "flow_m3s", "m3/s", "Turbine / penstock flow (state)"),
    ("h_t", "net_head_m", "m", "Net head across the turbine (output)"),
    ("P_gen", "power_MW", "MW", "Generated electrical power (output)"),
    ("f", "frequency_Hz", "Hz", "Electrical frequency = 50 Hz x rotor speed (output)"),
    ("y", "gate_position_pu", "pu", "Gate (wicket gate) position (state)"),
    ("y_cmd", "gate_command_pu", "pu", "Gate command from the governor (or set-point if governor off)"),
    ("w", "rotor_speed_pu", "pu", "Rotor speed, per unit of synchronous speed (rated rpm is not in the brochure)"),
    ("delta", "rotor_angle_rad", "rad", "Rotor angle relative to the synchronous reference (state)"),
    ("h_p", "pond_level_m", "m", "Headpond level (state)"),
    ("xi", "governor_integrator_pu", "pu", "Governor PI integrator (state)"),
    ("P_load", "load_MW", "MW", "Electrical load input (at nominal frequency)"),
    ("Q_in", "inflow_m3s", "m3/s", "Inflow input"),
    ("y_set", "gate_setpoint_pu", "pu", "Gate set-point / load reference input"),
    ("governor_on", "governor_on", "0/1", "1 = governor active"),
]


def results_csv(runs: list) -> str:
    """runs = [(label, Simulator)]. One CSV, a 'run' column distinguishes them. Plain ASCII, opens in Excel."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["run"] + [c[1] for c in EXPORT_COLUMNS])
    for label, sim in runs:
        for i in range(len(sim.hist["t"])):
            w.writerow([label] + [f"{sim.hist[c[0]][i]:.8g}" for c in EXPORT_COLUMNS])
    return buf.getvalue()


def _versions() -> dict:
    import scipy
    v = {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__}
    try:
        import streamlit
        v["streamlit"] = streamlit.__version__
    except Exception:            # pragma: no cover - streamlit is a requirement, but the backend does not need it
        pass
    return v


def build_metadata(runs: list, spec: ScenarioSpec | None, gov: GovernorSettings, params: dict, notices: list,
                   manual_inputs: dict | None = None) -> dict:
    return {
        "status": "SIMULATION RESULTS from an educational model. Not measured plant data. Not connected to the real "
                  "Ghazi Barotha plant and not validated against real operating data.",
        "scenario": None if spec is None else {
            "key": spec.key, "title": spec.title, "purpose": spec.purpose, "what_to_watch": spec.watch,
            "governor_on": spec.governor_on, "duration_s": spec.duration,
            "events": [asdict(e) | {"unit_t": "s", "unit_P_load": "MW"} for e in spec.events],
            "starting_inputs": {"gate_setpoint_pu": spec.y_set, "load_MW": spec.P_load0, "inflow_m3s": spec.Q_in},
            "governor_off_reference_included": spec.compare,
            "scenario_assumptions": list(spec.assumed)},
        "manual_inputs": manual_inputs,
        "runs": [{"label": lab, "rows": len(s.hist["t"]), "end_time_s": s.t} for lab, s in runs],
        "record_interval_s": RECORD_DT,
        "columns": [{"name": c[1], "unit": c[2], "description": c[3]} for c in EXPORT_COLUMNS],
        "governor_settings_ASSUMED": {k: {"value": getattr(gov, k), "unit": u, "note": why}
                                      for k, (u, why) in GOVERNOR_ASSUMPTIONS.items()},
        "model_parameters": [{"key": q.key, "value": q.value, "unit": q.unit, "classification": q.classification,
                              "source": q.source} for q in params.values()],
        "checks_and_warnings": [{"level": lv, "message": msg} for lv, msg in notices],
        "solver": "scipy.integrate.solve_ivp Radau, rtol 1e-8 (backend/simulator.py)",
        "software_versions": _versions(),
    }


def results_zip(runs: list, spec: ScenarioSpec | None, gov: GovernorSettings, params: dict, notices: list,
                manual_inputs: dict | None = None) -> bytes:
    """ZIP with results.csv, metadata.json (settings, assumptions, warnings) and README.txt."""
    meta = build_metadata(runs, spec, gov, params, notices, manual_inputs)
    name = spec.title if spec else "Manual run"
    readme = (f"GBHP digital twin - {name}\r\n\r\nresults.csv : time series (one row per {RECORD_DT} s; column 'run' separates "
              "the live run from a governor-OFF reference if present).\r\nmetadata.json : scenario settings, assumptions, "
              "governor settings (ASSUMED), model parameters with sources, warnings, software versions.\r\n\r\n"
              "SIMULATED values from an educational model; not plant measurements; not validated against plant data.\r\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("results.csv", results_csv(runs))
        z.writestr("metadata.json", json.dumps(meta, indent=2, default=float))
        z.writestr("README.txt", readme)
    return buf.getvalue()
