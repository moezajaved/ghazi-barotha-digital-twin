# User manual: dashboard (Phase 2)
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
