# Assumptions and limitations

Full list with values and sources: `exports/state_space_model.json` ("parameters"). Override an assumption with
`build_parameters({"T_y": 1.0})`; published values cannot be overridden (the function raises an error).

| Key | Value | Unit | Rationale / effect |
|---|---|---|---|
| hf_design | 0.5 | m | Penstock loss data missing. Sets tailwater level (264.5 m, derived) and damping. |
| dh_live | 3.0 | m | Level-volume curve missing. Sets pond area (1.7 km2 per unit); affects only the slow pond mode. |
| T_y | 0.5 | s | Gate servo data missing. Sets the gate pole (-1/T_y). |
| H_inertia | 3.0 | s | Generator inertia missing (typical hydro 2-4 s). Sets speed response. |
| D_damp | 1.0 | pu | Load damping missing. Sets the speed pole and the open-loop frequency excursion. |
| f_nom | 50 | Hz | Not stated in brochure. |
| S_base | 322.5 | MVA | Generator MVA missing; 3 x 107.5 MVA transformer rating (pp.12, 17) used as base. |
| y_min | 0.02 | pu | Numerical floor, not physical. |

Calculated (depend on the above): kf, z_tw, A_pond, and Cg / y_opt (which assume y = 1 is full gate at design head and flow proportional to gate opening).

## Brochure issues carried forward (not resolved)
- 290 MW (pp.4, 7, 17) vs 295 MW (p.12) per unit: both flagged `conflict` in the register; the model uses neither.
- Voltage "515v 3:18 KV" (p.12) is garbled: flagged `unconfirmed`, not used.

## Limitations
Rigid water column (no water hammer); constant efficiency, and P_gen (already net of generator losses via the combined 94%) is used as the swing-equation input, a small simplification;
live volume supports 3.1-3.5 h of 5-unit operation at 460-400 m3/s versus the brochure's ~4 h (channel inflow during peak not modelled; consistent, no change needed); Francis speed effects ignored; isolated-unit swing equation, no grid;
single unit; the Phase 1 plant is open loop (a governor is added in Phase 2, below); no headpond level-volume curve; no validation against plant data.

---
# Phase 2 additions
## Governor settings (ALL ASSUMED, not GBHP values)
| Key | Value | Unit | Rationale / effect |
|---|---|---|---|
| R | 0.05 | pu/pu | Permanent droop 5%, common utility practice. Sets steady frequency offset per load change. |
| Kp | 1.0 | pu/pu | Chosen by scanning Kp 0.5-3, Ki 0.05-0.4 on the assumed plant: damping ratio 0.85. |
| Ki | 0.20 | pu/pu/s | As Kp. |
| rate_open / rate_close | 0.10 / 0.20 | pu/s | Gate velocity limits (about 10 s / 5 s stroke), typical order. Limits how fast power can rise. |
| Kb | 2.0 | 1/s | Anti-windup back-calculation gain; bounds integrator overshoot beyond a limit to about Ki*e/Kb. |
| y_lo / y_hi | 0 / 1 | pu | Command limits. |
| w_ref | 1.0 | pu | Synchronous speed reference. |
Settings can be changed in the dashboard (expander) or via `GovernorSettings(...)`; ranges are validated.

## Phase 2 limitations
- Single unit; no grid; load is a fixed input (no frequency-dependent load other than the assumed damping D).
- The "load" input is the load at nominal frequency; generation differs by D*S_base*(w-1) off-nominal. Expected, noted on the dashboard.
- Pond level has no regulation (closed-loop pole +3.2e-6 1/s, see mathematical_model.md); runs are capped at 1 h.
- Default inflow (400 m3/s) exceeds this unit's share of the channel design flow (1600/5 = 320 m3/s, brochure p.12); the dashboard says so.
- Live charts are redrawn from scratch by Streamlit on each update; at the default 0.6 s refresh they are blank about 3% of the time (measured).
- Dashboard is a local single-user app; "live" speed is `chunk / refresh` (default 5 s per 0.6 s, about 9x real time), not real time.

## Phase 3: 3D geometry provenance
Full table in the dashboard (3D plant tab -> "Geometry provenance table"; 43 rows, from `backend.plant3d.build_geometry`).
| Class | What |
|---|---|
| published (brochure, page) | 5 units; penstocks: 5, D 10.6 m, L 222 m; headpond normal level 334 m; intake crest 305.5 m, 10 openings; siphon spillway crest; barrage normal pond 340 m, 20 standard bays, crest 332.2 m; power channel bed width, full supply depth, side slope, slope 1:9600, length 51.9 km; 500 kV switchyard 6 bays, breaker-and-half; 500 kV transmission; 5 three-phase transformer banks; Francis turbines; full-gate flow 460 m3/s |
| calculated | tailwater 264.5 m (model z_tw); penstock horizontal run 217.1 m (sqrt(L^2-dz^2)); penstock area 88.25 m2; channel flow area; channel fall; 292.69 MW colour-scale maximum (eta*rho*g*460*69, the calibration estimate; the model's own full-gate equilibrium is 291.67 MW) |
| schematic (illustrative, NOT plant dimensions) | plan layout and relative positions of all structures; unit spacing 45 m; headpond, tailrace and barrage-pool extents; channel drawn 255 m long (~200:1 compressed); powerhouse size; turbine/generator/shaft sizes; transformer and switchyard positions; straight penstock alignment; gate-bar size |
| simulated | every changing quantity (pond level, flow, gate, speed, power, frequency, head, flow-marker positions) |

## Phase 3 limitations
- The brochure has no site plan, powerhouse drawings or machine dimensions, so the scene is a **schematic arrangement** with true elevations
  and published pipe/channel dimensions; it is not a survey-accurate model of the real site.
- Only unit 1 is simulated; units 2-5 show the same state (or are shown idle). No unit-to-unit differences.
- The barrage and power channel are context only: the model has no barrage or channel dynamics; channel inflow is the dashboard input.
- Headpond level changes are millimetres over typical runs (the readout shows them; the surface movement is not visible at plant scale).
- Labels overlap in the Overview preset at small window sizes; use the Powerhouse/Penstocks presets or zoom.
- Flow markers are drawn once per refresh (5 simulated s); the white markers can appear stationary (aliasing), the orange tracer shows the travel.
- Needs WebGL in the browser (standard in current Chrome/Edge/Firefox on Windows).

## Phase 4: scenarios
| Item | Value | Class | Note |
|---|---|---|---|
| Starting point (all scenarios) | gate 0.8696 pu, pond 334 m, 254.51 MW | published level + calculated | Phase 1 operating point |
| Inflow during scenarios | 400 m3/s (= starting turbine flow) | assumed | Keeps the pond balanced at the start; exceeds the per-unit share of the channel design flow (320 m3/s, p.12) |
| Load step | 254.51 -> 280 MW (about +10 %) at 5 s | assumed (demonstration) | Adjustable 0 .. S_base |
| Load rejection | to 0 MW at 5 s | assumed (demonstration) | Ideal instantaneous breaker opening |
| Overload | 320 MW at 5 s | assumed (demonstration) | Above the model's full-gate capacity 291.67 MW (calculated); warned, not reduced |
| Durations | 60 / 120 s | assumed | 1 s .. 3600 s allowed |
| Model validity speed band | 0.9 .. 1.1 pu | assumed | Outside it results are flagged as indicative only |
Result checks (`backend.scenarios.assess`) report: governor command at a limit (with duration), gate below y_min, gate at its rate
limit, speed outside 0.9-1.1 pu, pond above the siphon spillway crest 334.5 m (published, p.12; spilling not modelled) or below the
assumed live range, head rise above 110 % of 69 m, non-finite values, and solver failures (results up to the failure are kept).
**Not modelled (affects load rejection most):** overspeed protection, unit trip, speed effect on Francis flow/efficiency, water hammer
(rigid column), spillway, other units, the grid. A full load rejection therefore reaches 68.5 Hz in the model; a real unit would be
protected long before that. The dashboard flags this run as outside the valid range.
