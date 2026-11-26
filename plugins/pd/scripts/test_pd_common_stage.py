"""Tests for pd_common's stage, issue-line, risk and base-branch helpers, and pd-lint --risk reading them (plan Task 1, C1-C8)."""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[2]
sys.path.insert(0, str(SCRIPTS))
import pd_common as pc  # noqa: E402

REVIEW_ENTRY = (
    "## 2026-11-26 10:00+08:00 review\n"
    "- R3 warning harden-later shape.md:12 — edge case deferred\n"
    "- R1 blocker src/a.py:3 — wrong exit\n")
WAIVER = "Risk: none (security) — the matches are pd's own message text"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def commit_files(root, files, message="add"):
    for rel, text in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", message)


def decision(body):
    return pc.parse_log(f"## 2026-11-26 11:00+08:00 decision\n{body}\n")


def test_c1_stage_vocabulary_and_defaults(pd_repo):
    assert pc.STAGES == ("mvp", "production")
    assert pc.load_config(pd_repo.root)["stage"] == "production"
    cfg = pd_repo.root / ".claude" / "pd.local.md"
    cfg.write_text(cfg.read_text().replace("sop: 1\n", "sop: 1\nstage: mvp\n"))
    assert pc.load_config(pd_repo.root)["stage"] == "mvp"
    assert pc.item_stage({}) == "production"
    assert pc.item_stage({"stage": "mvp"}) == "mvp"


def test_c2_issue_re_named_groups():
    m = pc.ISSUE_RE.match("- R3 warning harden-later shape.md:12 — edge case deferred")
    assert m.group("id", "sev", "cat", "file", "line", "claim") == (
        "R3", "warning", "harden-later", "shape.md", "12", "edge case deferred")
    m = pc.ISSUE_RE.match("- R1 blocker src/a.py:3 — wrong exit")
    assert m.group("id", "sev", "cat", "file", "line", "claim") == (
        "R1", "blocker", None, "src/a.py", "3", "wrong exit")


def test_c3_open_blockers_ignores_harden_later_warning():
    found = pc.open_blockers(pc.parse_log(REVIEW_ENTRY))
    assert len(found) == 1
    assert found[0]["ref"].endswith("#R1") and found[0]["file"] == "src/a.py" and found[0]["line"] == 3


def test_c4_risk_signals(pd_repo):
    root = pd_repo.root
    line = "@app.get('/x')\n"
    commit_files(root, {"src/pkg/api.py": line})
    assert pc.risk_signals(root, "HEAD~1..HEAD") == [("security", "src/pkg/api.py", 1)]
    for rel in ("docs/dev_artifacts/notes.md", "tests/test_api.py", "café.py"):
        (root / "tests").mkdir(exist_ok=True)
        commit_files(root, {rel: line})
        assert pc.risk_signals(root, "HEAD~1..HEAD") == [], rel


def test_c5_risk_waivers():
    assert pc.risk_waivers(decision(WAIVER)) == {"security"}
    assert pc.risk_waivers(decision("Risk: none (security)")) == set()
    assert pc.risk_waivers(decision("Risk: none (perf) — x")) == set()
    note = pc.parse_log(f"## 2026-11-26 11:00+08:00 note\n{WAIVER}\n")
    assert pc.risk_waivers(note) == set()


def test_c6_base_branch(pd_repo, tmp_path):
    root = pd_repo.root
    cfg = root / ".claude" / "pd.local.md"
    cfg.write_text("---\nartifacts_root: docs/dev_artifacts\nsop: 1\nbase_branch: develop\n---\n")
    assert pc.base_branch(root, pc.load_config(root)) == "develop"
    cfg.write_text("---\nartifacts_root: docs/dev_artifacts\nsop: 1\nbase_branch: auto\n---\n")
    assert pc.base_branch(root, pc.load_config(root)) == "main"
    origin = tmp_path / "origin"
    git(tmp_path, "init", "-q", "-b", "trunk", str(origin))
    git(origin, "config", "user.email", "t@t")
    git(origin, "config", "user.name", "t")
    git(origin, "commit", "-q", "--allow-empty", "-m", "init")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    assert pc.base_branch(clone, {"base_branch": "auto"}) == "trunk"


def run_risk(root):
    r = subprocess.run([sys.executable, str(SCRIPTS / "pd-lint"), "--risk", "main..HEAD"],
                       cwd=root, capture_output=True, text=True)
    return r.stdout + r.stderr


def test_c7_pd_lint_risk_reads_helpers_and_waivers(pd_repo):
    root = pd_repo.root
    git(root, "checkout", "-q", f"workitem/{pd_repo.id}")
    commit_files(root, {"src/pkg/api.py": "@app.get('/x')\n"})
    expected = (f"pd-lint: WARN src/pkg/api.py:1: risk signal (security) and the work item has no "
                "risk: [security] tag: set it, or the user clears it with a decision entry")
    assert expected in run_risk(root)
    log = root / "docs" / "dev_artifacts" / "workitems" / pd_repo.id / "log.md"
    log.write_text(log.read_text() + f"\n## 2026-11-26 11:00+08:00 decision\nQ: risk?\n{WAIVER}\n")
    commit_files(root, {})
    assert "WARN" not in run_risk(root)


SELF_TESTS = [["python3", "plugins/pd/scripts/pd_common.py", "--self-test"]] + [
    [f"plugins/pd/scripts/{s}", "--self-test"]
    for s in ("pd-lint", "pd-status", "pd-new", "pd-adopt", "pd-init", "pd-proof", "pd-review-filter")] + [
    ["uv", "run", "--script", "plugins/pd/scripts/pd-html.py", "--self-test"],
    ["bash", "plugins/pd/scripts/test-phase-gate.sh"],
    ["bash", "plugins/pd/hooks/tests/test-pd-stop-gate.sh"],
    ["node", "plugins/pd/workflows/tests/test-workflows.mjs"]]


@pytest.mark.parametrize("cmd", SELF_TESTS, ids=lambda c: " ".join(c[-2:]))
def test_c8_dependent_suites_pass(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
