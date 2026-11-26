"""Tests for pd-yolo (shape.md YoloCLI, SessionState; plan Task 3, cases C1 to C5)."""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "pd-yolo"


def run(home, *args):
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)


def gate(home):
    return home / ".claude" / "pd" / "gate"


def test_c1_on_creates_session_file(tmp_path):
    r = run(tmp_path, "on", "--session", "s1")
    assert (r.returncode, r.stdout.strip()) == (0, "on")
    lines = (gate(tmp_path) / "s1.yolo").read_text().splitlines()
    assert len(lines) == 1
    datetime.fromisoformat(lines[0])
    assert run(tmp_path, "status", "--session", "s1").stdout.strip() == "on"


def test_c2_off_removes_file_and_is_idempotent(tmp_path):
    run(tmp_path, "on", "--session", "s1")
    r = run(tmp_path, "off", "--session", "s1")
    assert (r.returncode, r.stdout.strip()) == (0, "off")
    assert not (gate(tmp_path) / "s1.yolo").exists()
    assert run(tmp_path, "status", "--session", "s1").stdout.strip() == "off"
    r = run(tmp_path, "off", "--session", "s1")
    assert (r.returncode, r.stdout.strip()) == (0, "off")


def test_c3_status_of_other_session_writes_nothing(tmp_path):
    run(tmp_path, "on", "--session", "s1")
    assert run(tmp_path, "status", "--session", "s2").stdout.strip() == "off"
    assert sorted(p.name for p in gate(tmp_path).iterdir()) == ["s1.yolo"]


@pytest.mark.parametrize("sid", ["${CLAUDE_SESSION_ID}", "../x", ""])
def test_c4_bad_session_id_refused(tmp_path, sid):
    before = sorted(tmp_path.rglob("*"))
    r = run(tmp_path, "on", "--session", sid)
    assert r.returncode == 2
    assert f"pd-yolo: bad session id {sid}" in r.stderr
    assert sorted(tmp_path.rglob("*")) == before


def test_c5_self_test(tmp_path):
    assert run(tmp_path, "--self-test").returncode == 0
