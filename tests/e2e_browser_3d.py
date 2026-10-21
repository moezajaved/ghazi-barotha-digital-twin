"""OPTIONAL real-browser test of the 3D plant tab (not collected by pytest; needs Playwright + Chromium).

    python -m streamlit run app.py --server.headless true --server.port 8765     (in one terminal)
    python tests/e2e_browser_3d.py http://localhost:8765                           (in another)

Checks, inside the actual browser: the 3D component loads offline (local plotly.min.js), WebGL scene is drawn, the values
the 3D view received equal the dashboard indicators, the view refreshes DURING a run, the user's camera survives live
updates, a camera preset moves the camera, and there are no page errors. Saves reports/plant3d_phase3*.png.
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
REPORTS = Path(__file__).resolve().parents[1] / "reports"
results = []


def check(name, cond, info=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, info)


def frame3d(pg):
    for f in pg.frames:
        if "plant3d" in f.url or "gbhp_plant3d" in f.url:
            return f
    return None


def summary(fr):
    return fr.evaluate("() => window.__summary")


def metrics(pg):
    return {el.locator('[data-testid="stMetricLabel"]').inner_text().strip():
            el.locator('[data-testid="stMetricValue"]').inner_text().strip()
            for el in pg.locator('[data-testid="stMetric"]').all()}


def setnum(pg, label, val):
    i = pg.get_by_label(label)
    i.fill(str(val))
    i.press("Enter")
    time.sleep(1.5)


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    pg = browser.new_context(viewport={"width": 1500, "height": 1300}).new_page()
    errs, external = [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("request", lambda r: external.append(r.url) if not r.url.startswith(("http://localhost", "data:", "blob:", "about:")) else None)
    pg.goto(URL)
    pg.wait_for_selector('[data-testid="stMetric"]', timeout=30000)
    m0 = metrics(pg)
    pg.get_by_role("tab", name="3D plant").click()
    fr = None
    for _ in range(60):
        fr = frame3d(pg)
        if fr is not None and fr.evaluate("() => !!window.__ready"):
            break
        time.sleep(0.5)
    check("3D component loaded", fr is not None and fr.evaluate("() => !!window.__ready"))
    check("plotly loaded from local file", fr.evaluate("() => !!window.Plotly") and
          any("plotly.min.js" in s for s in fr.evaluate("() => [...document.scripts].map(s => s.src)")))
    n_traces = fr.evaluate("() => document.getElementById('g').data.length")
    has_gl = fr.evaluate("() => !!document.querySelector('#g canvas')")
    check("WebGL scene drawn", has_gl and n_traces >= 10, f"traces={n_traces}")
    s0 = summary(fr)
    check("3D values = dashboard indicators at t=0",
          f"{s0['Q']:.1f}" == m0["Flow (m3/s)"] and f"{s0['P_gen']:.1f}" == m0["Power (MW)"] and f"{s0['f']:.3f}" == m0["Frequency (Hz)"],
          json.dumps({k: round(s0[k], 3) for k in ("Q", "P_gen", "f", "h_p", "y")}))
    ro = fr.evaluate("() => document.getElementById('readout').innerText")
    check("readout panel shows the model values", f"{s0['P_gen']:.1f}" in ro and f"{s0['h_p']:.3f}" in ro and f"{s0['f']:.3f}" in ro, ro.replace("\n", " | ")[:160])
    pg.screenshot(path=str(REPORTS / "plant3d_phase3.png"), full_page=False)

    # user rotates the view; then a run must update values but keep this camera
    ifr = [e for e in pg.locator("iframe").all() if "plant3d" in (e.get_attribute("src") or "")][0].bounding_box()
    cx, cy = ifr["x"] + ifr["width"] * 0.45, ifr["y"] + ifr["height"] * 0.55
    pg.mouse.move(cx, cy); pg.mouse.down(); pg.mouse.move(cx + 160, cy + 40, steps=12); pg.mouse.up()
    time.sleep(1.0)
    cam_user = fr.evaluate("() => document.getElementById('g')._fullLayout.scene._scene.getCamera().eye")

    setnum(pg, "Simulation duration (s)", 60)
    setnum(pg, "Electrical load at nominal frequency (MW)", 280)
    pg.get_by_role("button", name="Run", exact=True).click()
    ts, renders = [], []
    t_end = time.time() + 6
    while time.time() < t_end:
        fr = frame3d(pg)
        try:
            ts.append(summary(fr)["t"]); renders.append(fr.evaluate("() => window.__renders"))
        except Exception:
            pass
        time.sleep(0.5)
    check("3D view refreshes during the run", len(set(ts)) >= 3 and max(renders) > min(renders),
          f"t samples={ts[:12]}")
    sm = summary(fr)
    check("frequency dips after +25 MW load (model-driven)", sm["f"] < 50.0, f"f={sm['f']:.3f} Hz at t={sm['t']}")
    cam_after = fr.evaluate("() => document.getElementById('g')._fullLayout.scene._scene.getCamera().eye")
    moved = lambda a, b: max(abs(a[k] - b[k]) for k in "xyz")
    check("user camera kept across live updates", moved(cam_user, cam_after) < 1e-3, f"delta={moved(cam_user, cam_after):.2e}")
    pg.get_by_role("button", name="Pause", exact=True).click()
    time.sleep(2.5)
    fr = frame3d(pg)
    sp = summary(fr)
    pg.get_by_role("tab", name="Simulation").click(); time.sleep(1.0)
    mp = metrics(pg)
    check("after stop: 3D values = indicators", f"{sp['t']:.1f}" == mp["Time (s)"] and f"{sp['P_gen']:.1f}" == mp["Power (MW)"]
          and f"{sp['f']:.3f}" == mp["Frequency (Hz)"], f"3D t={sp['t']} P={sp['P_gen']:.2f} | ind {mp['Time (s)']} {mp['Power (MW)']}")
    pg.get_by_role("tab", name="3D plant").click(); time.sleep(1.5)

    # camera preset
    fr = frame3d(pg)
    before = fr.evaluate("() => document.getElementById('g')._fullLayout.scene._scene.getCamera().eye")
    pg.get_by_role("combobox", name="Jump to").click(); pg.get_by_role("option", name="Powerhouse").click()
    time.sleep(3)
    fr = frame3d(pg)
    after = fr.evaluate("() => document.getElementById('g')._fullLayout.scene._scene.getCamera().eye")
    check("camera preset moves the camera", moved(before, after) > 0.05, f"delta={moved(before, after):.3f}")
    pg.screenshot(path=str(REPORTS / "plant3d_phase3_powerhouse.png"), full_page=False)
    check("no page errors", not errs, errs[:3])
    check("no internet requests at runtime", not external, external[:3])
    browser.close()

print(f"{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
