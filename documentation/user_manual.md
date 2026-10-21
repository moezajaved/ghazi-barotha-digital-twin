# User manual: dashboard and 3D plant (Phases 2-3)
## Launch (Windows)
1. Install Python 3.11+ from python.org (tick "Add Python to PATH").
2. Open Command Prompt in the project folder: `cd %USERPROFILE%\Documents\Ghazi_Barotha_Digital_Twin`
3. First time only: `pip install -r requirements.txt`
4. Start: `python -m streamlit run app.py` (a browser tab opens at http://localhost:8501; if Streamlit asks for an email, press Enter). Stop with Ctrl+C.
Run the tests: `python -m pytest`

## Using it
- **Run** starts the simulation and updates numbers and graphs live; **Pause** stops it; **Step** advances by the chosen number of seconds; **Reset** returns to the equilibrium start (t = 0).
- **Inputs (sidebar):** governor on/off; gate command/set-point (pu); electrical load (MW); inflow (m3/s); duration (s); simulated seconds per refresh (bigger = faster);
  governor settings (assumed values). Inputs can be changed while running; out-of-range values are rejected with a message.
- **Indicators:** time, flow, net head, power, frequency, gate position, pond level, each with change from the starting equilibrium.
- **Graphs:** power (with load), frequency, flow, head, gate (actual and command), pond level. Zoom/pan with the mouse; double-click to reset zoom.
- **Download results (CSV)** is available when paused or finished. The parameter register at the bottom lists every parameter as published, calculated or assumed.

## Suggested demonstration
1. Reset, governor ON, load 280 MW, Run: power dips first (water-column inertia) then rises; frequency recovers to just under 50 Hz (droop).
2. Reset, governor OFF, load 275 MW, Run: frequency falls away; shows why a governor is needed.
3. Reset, governor ON, load 320 MW: the unit cannot supply it, the gate saturates and frequency settles near 45.6 Hz.
All values are simulated from an educational model with assumed governor and dynamic parameters; they are not plant measurements.

## 3D plant tab (Phase 3)
- Open the **3D plant** tab. Drag to rotate, scroll to zoom, right-drag to pan; double-click resets.
- **Jump to** moves the camera to a preset (Overview, Powerhouse, Penstocks (side), Headpond & intake, Plan (top)); after that your own view is kept, even while running.
- **Show all 5 units:** on = units 2-5 repeat the simulated unit 1; off = only unit 1 is live, the others are grey.
- What moves, all from the model: headpond surface (pond level), penstock colour (flow), markers in the penstocks (positions = simulated water travel, integral of Q/A; follow the orange tracer: the white ones are 22.2 m apart and can look still because water moves about that far per refresh),
  green bar (gate position), turbine colour (gate), generator and power-line colour (power), and the readout panel (time, level, flow, velocity, gate, speed, power, frequency, head).
- Labels say [published], [calculated], [schematic] or [simulated]; hover for details. The **Geometry provenance table** lists every dimension and its source.
- Buttons and inputs are shared with the Simulation tab: press Run there or here and both update.

## Suggested 3D demonstration
1. 3D plant tab, preset Powerhouse. Set load 280 MW, press Run: watch the gate bar and turbine colour rise, the orange tracer moves along the penstock, and the readout frequency dip then recover.
2. Rotate the view while it runs: the camera stays where you put it.
3. Set load 320 MW: gate bar reaches full scale, generator colour saturates, frequency falls to about 45.6 Hz.
Say clearly in a demonstration: the layout is schematic (the brochure has no site plan), elevations and pipe/channel sizes are published, and every moving value is simulated.
