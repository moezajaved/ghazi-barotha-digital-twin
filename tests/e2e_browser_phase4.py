"""OPTIONAL real-browser test of Phase 4 (not collected by pytest; needs Playwright + Chromium).

    python -m streamlit run app.py --server.headless true --server.port 8765     (in one terminal)
    python tests/e2e_browser_phase4.py http://localhost:8765                       (in another)

Checks: one-click scenario starts and plays live; event line and governor-OFF reference appear; result checks;
results package ZIP (CSV + metadata); state-space tab matrices + ZIP download; linear-vs-nonlinear chart; Exit; no errors.
Saves reports/phase4_*.png.
"""
import csv
import io
import json
import sys
import time
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
REPORTS = Path(__file__).resolve().parents[1] / "reports"
results = []


def check(name, cond, info=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, info)


def metrics(pg):
    return {el.locator('[data-testid="stMetricLabel"]').inner_text().strip():
            el.locator('[data-testid="stMetricValue"]').inner_text().strip()
            for el in pg.locator('[data-testid="stMetric"]').all()}


def btn(pg, name):
    return pg.get_by_role("button", name=name, exact=True)


def choose(pg, label, option):
    pg.get_by_role("combobox", name=label).click()
    pg.get_by_role("option", name=option).click()
    time.sleep(1.5)


def wait_finished(pg, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pg.get_by_text("Run finished.").count():
            return True
        time.sleep(0.5)
    return False


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    pg = browser.new_context(viewport={"width": 1500, "height": 1500}, accept_downloads=True).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_selector('[data-testid="stMetric"]', timeout=30000)
    time.sleep(2)

    # --- governor comparison scenario, live
    choose(pg, "Scenario", "Governor enabled vs disabled")
    btn(pg, "Start scenario").click()
    time.sleep(3)
    t1 = float(metrics(pg)["Time (s)"])
    time.sleep(3)
    t2 = float(metrics(pg)["Time (s)"])
    check("scenario plays live after one click", 0 < t1 < t2, f"t {t1} -> {t2}")
    check("manual inputs disabled during scenario", pg.get_by_label("Electrical load at nominal frequency (MW)").is_disabled())
    legend = pg.locator('[data-testid="stPlotlyChart"]').first.inner_text()
    check("governor-OFF reference curve in chart", "Governor OFF (reference)" in legend)
    check("scenario finishes", wait_finished(pg), metrics(pg).get("Time (s)"))
    m_ = metrics(pg)
    check("governor ON restores frequency (live run)", 49.5 < float(m_["Frequency (Hz)"]) < 50.0, m_["Frequency (Hz)"])
    check("event marker drawn", pg.locator("path.vline, .shapelayer path").count() > 0)
    pg.screenshot(path=str(REPORTS / "phase4_governor_compare.png"), full_page=False)

    # --- results package
    with pg.expect_download() as d:
        btn(pg, "Download results package (ZIP: CSV + settings + assumptions)").click()
    z = zipfile.ZipFile(io.BytesIO(Path(d.value.path()).read_bytes()))
    rows = list(csv.DictReader(io.StringIO(z.read("results.csv").decode())))
    meta = json.loads(z.read("metadata.json"))
    labels = {r["run"] for r in rows}
    check("results ZIP: both runs, named columns", labels == {"scenario_run", "governor_off_reference"} and "frequency_Hz" in rows[0],
          f"{len(rows)} rows, runs {sorted(labels)}")
    last_main = [r for r in rows if r["run"] == "scenario_run"][-1]
    check("results ZIP matches displayed values", f"{float(last_main['power_MW']):.1f}" == m_["Power (MW)"]
          and f"{float(last_main['frequency_Hz']):.3f}" == m_["Frequency (Hz)"])
    check("metadata: scenario settings + assumptions", meta["scenario"]["key"] == "governor_compare"
          and meta["scenario"]["scenario_assumptions"] and "Kp" in meta["governor_settings_ASSUMED"])

    # --- state-space tab
    pg.get_by_role("tab", name="State-space model").click()
    time.sleep(2)
    pg.get_by_text("Plant + governor (closed loop)").click()
    time.sleep(2.5)
    check("closed-loop matrices shown", pg.get_by_text("A (6 x 6)").count() > 0)
    check("linear-vs-nonlinear chart shown", pg.get_by_text("Linear state-space model").count() > 0)
    with pg.expect_download() as d2:
        pg.get_by_role("button", name="Download matrices at this operating point (ZIP: A, B, C, D CSV + JSON)").click()
    z2 = zipfile.ZipFile(io.BytesIO(Path(d2.value.path()).read_bytes()))
    check("state-space ZIP", sorted(z2.namelist()) == ["A.csv", "B.csv", "C.csv", "D.csv", "state_space_model.json"])
    pg.screenshot(path=str(REPORTS / "phase4_state_space.png"), full_page=True)

    # --- overload: result checks, then exit
    pg.get_by_role("tab", name="Simulation").click()
    btn(pg, "Exit scenario").click()
    time.sleep(2)
    check("exit returns to manual mode", not pg.get_by_label("Electrical load at nominal frequency (MW)").is_disabled()
          and metrics(pg)["Time (s)"] == "0.0")
    choose(pg, "Scenario", "Overload")
    btn(pg, "Start scenario").click()
    check("overload finishes", wait_finished(pg))
    time.sleep(1)
    check("result check: gate limit warning", pg.get_by_text("upper limit 1 pu").count() > 0)
    check("no page errors / exceptions", not errs and pg.locator('[data-testid="stException"]').count() == 0, errs[:2])
    browser.close()

print(f"{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
