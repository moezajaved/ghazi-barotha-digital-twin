"""Phase 4: the installation check script runs and passes in a working environment."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_check_setup_passes():
    r = subprocess.run([sys.executable, "check_setup.py"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("PASS") == 7 and "FAIL" not in r.stdout
