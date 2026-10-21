"""Quick installation check (Phase 4). Run in the project folder:   python check_setup.py

Checks Python and package versions, reads the brochure register, runs one scenario, the state-space export and the
results export, and prepares the offline 3D component. Prints PASS/FAIL per check; exit code 1 if anything fails.
Does not change any project file except copying plotly.min.js next to the 3D component (git-ignored).
"""
import platform
import sys

TESTED = {"python": "3.13", "numpy": "2.5.3", "scipy": "1.18.1", "plotly": "7.1.0", "streamlit": "1.65.0", "pytest": "9"}
ok = True


def check(name, func):
    global ok
    try:
        info = func()
        print(f"PASS  {name}" + (f"  ({info})" if info else ""))
    except Exception as exc:                      # report every failure plainly, keep checking the rest
        ok = False
        print(f"FAIL  {name}: {type(exc).__name__}: {exc}")


def python_version():
    if sys.version_info < (3, 10):
        raise RuntimeError(f"Python {platform.python_version()} is too old; install Python 3.11 or newer from python.org")
    return f"Python {platform.python_version()} on {platform.system()} {platform.release()}; tested with {TESTED['python']}"


def packages():
    import importlib
    out = []
    for name in ("numpy", "scipy", "plotly", "streamlit", "pytest"):
        mod = importlib.import_module(name)
        out.append(f"{name} {mod.__version__}")
    return ", ".join(out) + "  [tested: " + ", ".join(f"{k} {v}" for k, v in TESTED.items() if k != "python") + "]"


def register():
    from backend import model as m
    reg = m.load_register()
    if len(reg) != 64:
        raise RuntimeError(f"expected 64 register rows, found {len(reg)}")
    return f"{len(reg)} brochure parameters"


def scenario():
    from backend.scenarios import build_scenario, run_scenario
    spec, errors, _ = build_scenario("load_step")
    if errors:
        raise RuntimeError(errors)
    r = run_scenario(spec)
    if r.error:
        raise RuntimeError(r.error)
    f = r.main.latest()["f"]
    if not 49.5 < f < 50.0:
        raise RuntimeError(f"unexpected final frequency {f:.3f} Hz")
    return f"load step: final frequency {f:.3f} Hz, power {r.main.latest()['P_gen']:.1f} MW"


def state_space():
    import io
    import zipfile
    from pathlib import Path

    from backend import model as m
    from backend.state_space import export_zip, linearize_at
    params = m.build_parameters()
    p = m.values(params)
    x0 = m.steady_state(p)["x0"]
    z = zipfile.ZipFile(io.BytesIO(export_zip(linearize_at(p, x0[2], x0[0]), params, "nominal")))
    root = Path(__file__).resolve().parent / "exports"
    for n in "ABCD":
        if z.read(f"{n}.csv").replace(b"\r\n", b"\n") != (root / f"{n}.csv").read_bytes().replace(b"\r\n", b"\n"):
            raise RuntimeError(f"{n}.csv differs from exports/{n}.csv")
    return "nominal A, B, C, D equal exports/"


def results_export():
    from backend import model as m
    from backend.governor import GovernorSettings
    from backend.scenarios import build_scenario, results_zip, run_scenario
    r = run_scenario(build_scenario("normal")[0])
    b = results_zip([("scenario_run", r.main)], r.spec, GovernorSettings(), m.build_parameters(), r.notices)
    return f"results package {len(b) // 1024} KB"


def plotly_js():
    from backend.plant3d_component import ensure_plotly_js
    return f"{ensure_plotly_js().name} ready for the offline 3D view"


def main() -> int:
    for name, f in [("Python", python_version), ("Packages", packages), ("Brochure register", register),
                    ("Scenario simulation", scenario), ("State-space export", state_space),
                    ("Results export", results_export), ("3D component files", plotly_js)]:
        check(name, f)
    print("\nAll checks passed. Start the dashboard with:  python -m streamlit run app.py" if ok else
          "\nSome checks failed: see the messages above (install packages with: pip install -r requirements.txt).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
