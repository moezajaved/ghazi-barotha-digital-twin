"""OPTIONAL end-to-end browser test of the real dashboard (not collected by pytest; needs Playwright + Chromium).

    pip install playwright && python -m playwright install chromium
    python -m streamlit run app.py --server.headless true --server.port 8765     (in one terminal)
    python tests/e2e_browser.py http://localhost:8765                              (in another)

Drives the live app like a user: Run, Pause mid-run, resume, change an input while running, overload, Step, CSV download,
Reset, governor off. Saves reports/dashboard_phase2.png. Prints PASS/FAIL per check; exit code 1 if any fail.
"""
import csv
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
SHOT = Path(__file__).resolve().parents[1] / "reports" / "dashboard_phase2.png"


def metrics(pg):
    return {el.locator('[data-testid="stMetricLabel"]').inner_text().strip():
            el.locator('[data-testid="stMetricValue"]').inner_text().strip()
            for el in pg.locator('[data-testid="stMetric"]').all()}


def setnum(pg, label, val):
    i = pg.get_by_label(label)
    i.fill(str(val))
    i.press("Enter")
    time.sleep(1.5)


def btn(pg, name):
    return pg.get_by_role("button", name=name, exact=True)


results = []


def check(name, cond, info=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, info)


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_context(viewport={"width": 1500, "height": 1450}, accept_downloads=True).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_selector('[data-testid="stMetric"]', timeout=30000)
    time.sleep(2)
    m = metrics(pg)
    check("initial equilibrium", m["Time (s)"] == "0.0" and m["Flow (m3/s)"] == "400.0" and m["Power (MW)"] == "254.5"
          and m["Frequency (Hz)"] == "50.000", m)
    setnum(pg, "Simulation duration (s)", 3000)
    setnum(pg, "Electrical load at nominal frequency (MW)", 280)
    btn(pg, "Run").click()
    time.sleep(5)
    t1 = float(metrics(pg)["Time (s)"])
    time.sleep(3)
    t2 = float(metrics(pg)["Time (s)"])
    check("Run advances live", 0 < t1 < t2 < 3000, f"t={t1} -> {t2}")
    SHOT.parent.mkdir(exist_ok=True)
    pg.screenshot(path=str(SHOT))
    btn(pg, "Pause").click()
    time.sleep(2.5)
    t3 = float(metrics(pg)["Time (s)"])
    time.sleep(3)
    t4 = float(metrics(pg)["Time (s)"])
    check("Pause stops mid-run", t3 == t4 and t3 < 3000, f"t={t3},{t4}")
    check("chart present after pause", pg.locator(".js-plotly-plot").count() == 1)
    btn(pg, "Run").click()
    time.sleep(4)
    t5 = float(metrics(pg)["Time (s)"])
    check("Resume continues from paused time", t5 > t4, f"{t4} -> {t5}")
    setnum(pg, "Electrical load at nominal frequency (MW)", 320)
    time.sleep(8)
    m = metrics(pg)
    check("overload applied live (gate saturates, f<46.5)", float(m["Gate (pu)"]) > 0.99 and float(m["Frequency (Hz)"]) < 46.5, m)
    btn(pg, "Pause").click()
    time.sleep(2.5)
    with pg.expect_download(timeout=15000) as dl:
        pg.get_by_role("button", name="Download results (CSV)").click()
    rows = list(csv.reader(open(dl.value.path())))
    last = dict(zip(rows[0], rows[-1]))
    check("CSV downloads with full history", len(rows) > 100 and last["P_load"] == "320" and float(last["t"]) >= t5,
          f"{len(rows) - 1} rows, last t={last['t']}")
    check("CSV matches displayed time", abs(float(last["t"]) - float(metrics(pg)["Time (s)"])) < 0.06)
    btn(pg, "Step").click()
    time.sleep(2)
    t6 = float(metrics(pg)["Time (s)"])
    check("Step advances 5 s", abs(t6 - float(last["t"]) - 5) < 0.06, f"{last['t']} -> {t6}")
    btn(pg, "Reset").click()
    time.sleep(2.5)
    m = metrics(pg)
    check("Reset restores equilibrium", m["Time (s)"] == "0.0" and m["Power (MW)"] == "254.5" and m["Frequency (Hz)"] == "50.000", m)
    setnum(pg, "Electrical load at nominal frequency (MW)", 275)
    pg.get_by_text("PI/droop governor").first.click()
    time.sleep(1.5)
    setnum(pg, "Simulation duration (s)", 60)
    btn(pg, "Run").click()
    time.sleep(14)
    m = metrics(pg)
    check("governor OFF: open-loop frequency far from 50 Hz", abs(float(m["Frequency (Hz)"]) - 50) > 2, m)
    pg.get_by_text("Parameter register").first.click()
    time.sleep(1.5)
    check("parameter register visible", pg.get_by_text("assumed").count() > 3)
    check("no exception boxes / page errors", pg.locator('[data-testid="stException"]').count() == 0 and not errs, errs)
    browser.close()

print("ALL PASS" if all(results) else "SOME FAILED", f"({sum(results)}/{len(results)})")
sys.exit(0 if all(results) else 1)
