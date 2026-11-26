"""The Stop gate's goal messages, brainstorm and rca goals, and the read-count reset (shape.md StopGate; B31, B32, B39, B56)."""
import json
import re
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent
GATE = HOOKS / "pd-stop-gate.sh"
PD_NEW = HOOKS.parent / "scripts" / "pd-new"
GATE_BASH_SUITE = HOOKS / "tests" / "test-pd-stop-gate.sh"
SESSION = "s1"
ART = "docs/dev_artifacts"


class Repo:
    def __init__(self, path):
        self.path = path
        self.wid = next((path / ART / "workitems").iterdir()).name
        self.item = path / ART / "workitems" / self.wid / "README.md"


def sh(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def set_now(path, text):
    s = path.read_text()
    path.write_text(re.sub(r"(## Now\n\n)(.*?)(\n\n## )", lambda m: m.group(1) + text + m.group(3), s, count=1, flags=re.S))


def set_field(path, key, value):
    path.write_text(re.sub(rf"^{key}: .*$", f"{key}: {value}", path.read_text(), count=1, flags=re.M))


@pytest.fixture
def repo(tmp_path):
    """An adopted repo with one work item, its branch checked out."""
    r = tmp_path / "repo"
    (r / ".claude").mkdir(parents=True)
    sh("git", "init", "-q", "-b", "main", cwd=r)
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        sh("git", "config", k, v, cwd=r)
    (r / ".claude" / "pd.local.md").write_text(f"---\nartifacts_root: {ART}\nsop: 1\n---\n")
    sh(str(PD_NEW), "workitem", "Parse the input", cwd=r)
    sh("git", "add", "-A", cwd=r)
    sh("git", "commit", "-qm", "base", cwd=r)
    result = Repo(r)
    sh("git", "checkout", "-qb", f"workitem/{result.wid}", cwd=r)
    return result


def single_file_item(repo, kind, title):
    sh(str(PD_NEW), kind, title, cwd=repo.path)
    path = next((repo.path / ART / ("brainstorms" if kind == "brainstorm" else "rca")).glob("*.md"))
    return path.stem, path


def payload(repo, **extra):
    return {"session_id": SESSION, "cwd": str(repo.path), "transcript_path": str(repo.path.parent / "t.jsonl"),
            "stop_hook_active": False, **extra}


def test_c1_token_cap_asks_with_hard_stop(repo, run_hook):
    (repo.path / ".claude" / "pd.local.md").write_text(
        f"---\nartifacts_root: {ART}\nsop: 1\nworkitem_token_budget: 100\n---\n")
    set_now(repo.item, f"goal: {repo.wid} target finish session {SESSION}")
    (repo.path.parent / "t.jsonl").write_text(
        json.dumps({"message": {"usage": {"input_tokens": 100, "output_tokens": 50}}}) + "\n")
    code, err = run_hook(GATE, payload(repo))
    assert code == 2 and "Ask the owner: Hard stop:" in err and "budget spent: continue or stop?" in err


def test_c1_no_progress_asks_with_hard_stop(repo, run_hook):
    set_now(repo.item, f"goal: {repo.wid} target finish session {SESSION}")
    run_hook(GATE, payload(repo))  # records the state
    code, err = run_hook(GATE, payload(repo, stop_hook_active=True))
    assert code == 2 and "Ask the owner: Hard stop:" in err and "no progress since the last check" in err


def test_c2_goal_reached_keeps_yolo_on(repo, run_hook):
    set_field(repo.item, "phase", "design")
    set_now(repo.item, f"goal: {repo.wid} target specify session {SESSION}")
    d = repo.item.parent
    (d / "shape.md").write_text("## Requirements\n\nB1: an empty input -> EmptyInput is raised\n")
    with open(d / "log.md", "a") as fh:
        fh.write('## 2026-10-15 09:00+08:00 decision\nQ: criteria signed off?\nA (user, verbatim): "Yes."\n')
    code, err = run_hook(GATE, payload(repo))
    assert code == 2 and "reached specify with no open blockers" in err
    assert "clear the goal: line" in err
    assert "YOLO stays on until pd-yolo off or the session ends." in err


@pytest.mark.parametrize("kind,title", [("brainstorm", "Better onboarding"), ("rca", "Crash on empty input")])
def test_c3_brainstorm_or_rca_goal_holds_the_stop(repo, run_hook, kind, title):
    item_id, path = single_file_item(repo, kind, title)
    set_field(path, "status", "active")
    set_now(path, f"goal: {item_id} target finish session {SESSION}")
    code, err = run_hook(GATE, payload(repo))
    assert code == 2
    assert (f"pd gate: goal {item_id} is a {kind}; carry it to promotion. "
            "Promotion moves the goal line to the new work item.") in err
    set_now(path, f"goal: {item_id} target finish session s9")
    assert run_hook(GATE, payload(repo)) == (0, "")


@pytest.mark.parametrize("kind,title", [("brainstorm", "Better onboarding"), ("rca", "Crash on empty input")])
def test_c3b_promotion_hold_yields_to_background_work_and_stops_nagging(repo, run_hook, kind, title):
    item_id, path = single_file_item(repo, kind, title)
    set_field(path, "status", "active")
    set_now(path, f"goal: {item_id} target finish session {SESSION}")
    running = [{"type": "subagent", "status": "running"}]
    assert run_hook(GATE, payload(repo, background_tasks=running)) == (0, "")
    assert run_hook(GATE, payload(repo))[0] == 2  # first hold
    code, err = run_hook(GATE, payload(repo, stop_hook_active=True))  # nothing moved since
    assert code == 2 and "no progress" in err


def test_c4_promoted_brainstorm_defers_to_its_work_item(repo, run_hook):
    item_id, path = single_file_item(repo, "brainstorm", "Better onboarding")
    set_field(path, "status", "done")
    set_now(path, "Promoted.")
    set_field(repo.item, "phase", "design")
    set_now(repo.item, f"goal: {repo.wid} target finish session {SESSION}")
    code, err = run_hook(GATE, payload(repo))
    assert code == 2 and f"the goal on {repo.wid} is not met" in err
    assert item_id not in err and "carry it to promotion" not in err


def test_c5_a_held_stop_resets_the_read_count(repo, run_hook, gate_home):
    reads = gate_home / ".claude" / "pd" / "gate" / f"{SESSION}.reads"
    reads.write_bytes(b"xxxxx")
    assert run_hook(GATE, payload(repo)) == (0, "")  # no goal line: allowed
    assert reads.stat().st_size == 5
    set_now(repo.item, f"goal: {repo.wid} target finish session {SESSION}")
    code, _ = run_hook(GATE, payload(repo))
    assert code == 2 and reads.stat().st_size == 0


def test_c6_existing_stop_gate_suite_passes():
    r = subprocess.run(["bash", str(GATE_BASH_SUITE)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
