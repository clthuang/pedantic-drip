"""Runs test-workflows.mjs, whose cases carry VerifyArgs and ReviewSchema (plan Task 10, case C11)."""
import subprocess
from pathlib import Path

MJS = Path(__file__).resolve().parent / "test-workflows.mjs"


def test_c11_workflow_stubs_pass():
    r = subprocess.run(["node", str(MJS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]
