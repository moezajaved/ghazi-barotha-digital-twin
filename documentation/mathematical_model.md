# Mathematical model: one GBHP generating unit (open loop)

Simulation model only. Not connected to the real plant; not validated against real operating data.
Code: `backend/model.py`. Parameter classes: **published** (brochure + page), **calculated**, **assumed**.

## Variables
| Type | Symbol | Meaning | Unit |
|---|---|---|---|
| State | h_p | Headpond level (this unit's share of the pond) | m |
| State | Q | Penstock / turbine flow | m3/s |
| State | y | Gate position | pu (0..1) |
| State | w | Rotor speed | pu |
| State | delta | Rotor angle vs synchronous reference | rad |
| Input | y_cmd | Gate command | pu |
| Input | P_load | Electrical load | MW |
| Input | Q_in | Inflow from power channel (per unit) | m3/s |
| Output | Q, h_t, P_gen, f | Flow, net turbine head, generated power, frequency | m3/s, m, MW, Hz |

## Equations
```
h_t   = Q|Q| / (Cg*y)^2                       (turbine: Q = Cg*y*sqrt(h_t))
h_f   = kf*Q|Q|                                (penstock friction)
P_gen = eta*rho*g*Q*h_t / 1e6                  [MW]
dh_p/dt   = (Q_in - Q) / A_pond
dQ/dt     = (g*A_pen/L_pen) * (h_p - z_tw - h_f - h_t)     (rigid water column)
dy/dt     = (y_cmd - y) / T_y
dw/dt     = [ (P_gen - P_load)/S_base - D*(w-1) ] / (2H)
ddelta/dt = 2*pi*f_nom*(w-1)
f = f_nom*w
```
Gate position is clipped to [y_min, 1] inside the head calculation, and y_cmd to [0, 1] in `simulate()`.

## Consistency with available data
- **Penstock flow**: diameter 10.6 m, length 222 m (p.12) are published, so the water column is well defined.
- **Turbine**: design head 69 m, 460 m3/s at full gate and 400 m3/s at optimum gate (p.17) fix Cg and the optimum gate position.
- **Headpond level**: normal level 334 m and live volume 25.5 Mm3 are published, but the level-volume curve is missing, so pond area rests on an assumed usable drawdown. It affects only the very slow pond mode.
- **Gate servo, inertia, damping, MVA base**: not in the brochure, so assumed.
- **Rotor angle**: pure integrator of speed deviation; no network model, so no power-angle curve.

## Operating point (calculated)
Pond 334 m, gate y = 400/460 = 0.8696, equilibrium: Q = 400 m3/s, h_t = 69 m, **P_gen = 254.51 MW** (calculated, not measured), f = 50 Hz.
Full gate at 69 m gives 292.69 MW (calculated); the brochure's 290 MW and 295 MW per-unit figures are both within about 1% of it. The brochure conflict is preserved, and the model uses neither.
Water starting time T_w = L*Q0/(g*A*H0) = 1.487 s.

## Open-loop behaviour (simulated)
- Eigenvalues (1/s): -2.0 (gate servo, = 1/T_y), -1.355 (penstock flow), -0.1667 (speed, = D/2H), -2e-6 (pond level), 0 (rotor angle integrator).
- Gate opening is non-minimum phase: +2% gate command gives -3.7 MW at 0.3 s, then +5.7 MW at 15 s.
- A 20 MW load drop with no governor drives frequency to about 53 Hz (assumed D and H). A governor is needed; that is Phase 2.
