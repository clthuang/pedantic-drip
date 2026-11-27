"""Tests for pd-pr-checks (shape.md PrChecksCLI; plan Task 3, cases C6 to C12)."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "pd-pr-checks"

# Replays FAKE_GH_REPLIES, a JSON list of [exit, stdout, stderr], one per call (the last repeats), and counts calls.
FAKE_GH = f"""#!{sys.executable}
import json, os, sys, time
time.sleep(float(os.environ.get("FAKE_GH_SLEEP", "0")))
count_file = os.environ["FAKE_GH_COUNT"]
with open(count_file, "a") as f:
    f.write("x")
n = len(open(count_file).read())
replies = json.loads(os.environ["FAKE_GH_REPLIES"])
code, out, err = replies[min(n, len(replies)) - 1]
sys.stdout.write(out)
sys.stderr.write(err)
sys.exit(code)
"""


def checks(*buckets):
    return json.dumps([{"name": f"c{i}", "bucket": b} for i, b in enumerate(buckets)])


def run(tmp_path, replies, *args, extra_env=None):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    gh = bindir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    count = tmp_path / "count"
    count.write_text("")
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
           "FAKE_GH_COUNT": str(count), "FAKE_GH_REPLIES": json.dumps(replies), **(extra_env or {})}
    start = time.monotonic()
    r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)
    return r, len(count.read_text()), time.monotonic() - start


def test_c6_all_pass(tmp_path):
    out = checks("pass", "skipping", "pass")
    r, _, _ = run(tmp_path, [[0, out, ""]], "7")
    assert r.returncode == 0
    assert json.loads(r.stdout) == json.loads(out)


def test_c7_fail_and_cancel(tmp_path):
    r, _, _ = run(tmp_path, [[0, checks("pass", "fail"), ""]], "7")
    assert r.returncode == 1 and "c1" in r.stdout
    r, _, _ = run(tmp_path, [[0, checks("pass", "cancel"), ""]], "7")
    assert r.returncode == 1


def test_c8_no_checks(tmp_path):
    r, _, _ = run(tmp_path, [[1, "", "no checks reported on the 'x' branch\n"]], "7")
    assert r.returncode == 3 and r.stdout == ""


def test_c9_pending_until_for_runs_out(tmp_path):
    r, _, took = run(tmp_path, [[8, checks("pending", "pass"), ""]], "7", "--for", "2")
    assert r.returncode == 8
    assert took < 10


def test_c9b_a_stalled_gh_does_not_outlast_for(tmp_path):
    r, _, took = run(tmp_path, [[0, checks("pass"), ""]], "7", "--for", "2", extra_env={"FAKE_GH_SLEEP": "30"})
    assert r.returncode == 8
    assert took < 10


def test_c10_no_such_pr(tmp_path):
    r, _, _ = run(tmp_path, [[1, "", "no pull requests found\n"]], "7")
    assert r.returncode == 2
    assert "no pull requests found" in r.stderr


def test_c11_pending_then_pass(tmp_path):
    out = checks("pass")
    r, calls, took = run(tmp_path, [[8, checks("pending"), ""], [0, out, ""]], "7", "--for", "40")
    assert r.returncode == 0
    assert calls == 2
    assert 28 <= took < 38
    assert json.loads(r.stdout) == json.loads(out)


def test_c12_self_test(tmp_path):
    assert subprocess.run([sys.executable, str(SCRIPT), "--self-test"], capture_output=True).returncode == 0
