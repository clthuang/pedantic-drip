"""Tests for pd-status's `Leftover worktrees` section and its session-start pass-through (plan Task 2, cases C25 to C31, C37)."""
import ast
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[2]
PD_STATUS = SCRIPTS / "pd-status"
HOOK = ROOT / "plugins" / "pd" / "hooks" / "pd-session-start.sh"
HOOK_TEST = ROOT / "plugins" / "pd" / "hooks" / "tests" / "test-pd-session-start.sh"
REAL_GIT = shutil.which("git")
SECTION = "Leftover worktrees"
FIRST_LINE = ("clear with `pd-worktrees <id> --remove` (a work item's worktrees) or `pd-worktrees --strays --remove`; "
              "delete other listed branches by hand")

# A git on PATH that logs its argument list as one JSON line, then fails per FAKE_FAIL or runs the real git.
FAKE_GIT = f"""#!{sys.executable}
import json, os, subprocess, sys
args = sys.argv[1:]
if os.environ.get("GIT_LOG"):
    with open(os.environ["GIT_LOG"], "a") as log:
        log.write(json.dumps(args) + "\\n")
fail = os.environ.get("FAKE_FAIL", "")
if fail == "all" or (fail and args[:len(fail.split())] == fail.split()):
    sys.exit(1)
sys.exit(subprocess.call(["{REAL_GIT}", *args]))
"""


@pytest.fixture
def fake_bin(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "git"
    fake.write_text(FAKE_GIT)
    fake.chmod(0o755)
    return bindir


def make_item(root, id_, status, now="", log=""):
    d = Path(root) / "docs" / "dev_artifacts" / "workitems" / id_
    d.mkdir(parents=True)
    (d / "README.md").write_text(f"---\nid: {id_}\ntype: workitem\ntitle: {id_}\nstatus: {status}\n"
                                 f"phase: implement\nmode: standard\n---\n# {id_}\n\n## Now\n\n{now}\n\n## Links\n")
    (d / "log.md").write_text(log)


def pd_status(cwd, *args, bindir=None, **env):
    path = f"{bindir}{os.pathsep}{os.environ['PATH']}" if bindir else os.environ["PATH"]
    return subprocess.run([sys.executable, str(PD_STATUS), *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, "PATH": path, **env})


def section(out, title):
    """The lines of a report section (title to the next blank line), or None."""
    lines = out.split("\n")
    if title not in lines:
        return None
    rest = lines[lines.index(title) + 1:]
    return rest[:rest.index("")] if "" in rest else rest


def titles(out):
    return [block.split("\n")[0] for block in out.split("\n\n")]


def test_c25_every_reason_in_order(pd_repo, task_worktree):
    review = ("## 2026-11-03 10:00+08:00 review\nVerdict: changes requested. Commit: abc1234.\n"
              "- R1 blocker src/a.py:1 — claim\n")
    capped = "## 2026-11-03 11:00+08:00 capped\nDeferred: none\n"
    make_item(pd_repo.root, "A", "active", log=review)
    make_item(pd_repo.root, "B", "done", log=capped)
    make_item(pd_repo.root, "C", "abandoned")
    path1 = task_worktree(1, "clean", id="A")
    for branch in ("pd/B/task-1", "pd/C/task-1", "pd/ghost/task-1", "worktree-wf_r-1"):
        pd_repo.git("branch", branch)
    r = pd_status(pd_repo.root)
    assert r.returncode == 0, r.stderr
    order = titles(r.stdout)
    assert "Open blockers" in order and "Retros owed" in order
    assert order[-1] == SECTION
    assert order.index(SECTION) > max(order.index("Open blockers"), order.index("Retros owed"))
    assert section(r.stdout, SECTION) == [
        FIRST_LINE,
        f"A: {path1} — worktree after its run",
        "B: pd/B/task-1 — branch of a done work item",
        "C: pd/C/task-1 — branch of an abandoned work item",
        "ghost: pd/ghost/task-1 — no work item",
        "-: worktree-wf_r-1 — stray branch"]
    pd_repo.git("worktree", "lock", path1)
    locked = section(pd_status(pd_repo.root).stdout, SECTION)
    assert f"A: {path1} (locked) — worktree after its run" in locked
    assert not any("pd/A/task-1" in line for line in locked)


def test_c26_no_leftovers_and_early_reports(pd_repo, tmp_path):
    assert SECTION not in pd_status(pd_repo.root).stdout
    adopted = tmp_path / "adopted"
    old = tmp_path / "old"
    for repo in (adopted, old):
        repo.mkdir()
        for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                     ["commit", "-q", "--allow-empty", "-m", "init"], ["branch", "worktree-wf_r-1"]):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        (repo / ".claude").mkdir()
    (adopted / ".claude" / "pd.local.md").write_text("---\nsop: 1\n---\n")
    (old / ".claude" / "pd.local.md").write_text("---\nartifacts_root: docs\n---\n")
    (old / "docs" / "features").mkdir(parents=True)
    out = pd_status(adopted).stdout.rstrip("\n")
    assert out.endswith("no items under docs/dev_artifacts") and SECTION not in out and "worktree-wf_r-1" not in out
    out = pd_status(old).stdout.rstrip("\n")
    assert out.startswith("run /pd:adopt") and SECTION not in out and "worktree-wf_r-1" not in out


def test_c27_run_in_flight_and_other_branch_items_not_listed(pd_repo, task_worktree):
    pd_repo.set_now("first line", "", "run in flight: implement-tasks session y")
    path1 = task_worktree(1, "clean")
    pd_repo.git("branch", "workitem/D")
    path2 = task_worktree(2, "clean", id="D")
    r = pd_status(pd_repo.root)
    assert r.returncode == 0, r.stderr
    assert SECTION not in r.stdout and path1 not in r.stdout and path2 not in r.stdout
    # Positive controls: each worktree shows once its exclusion is lifted.
    readme = pd_repo.root / "docs" / "dev_artifacts" / "workitems" / pd_repo.id / "README.md"
    readme.write_text(readme.read_text().replace("run in flight: implement-tasks session y", ""))
    assert f"{pd_repo.id}: {path1} \u2014 worktree after its run" in section(pd_status(pd_repo.root).stdout, SECTION)
    pd_repo.git("branch", "-D", "workitem/D")
    assert f"D: {path2} \u2014 no work item" in section(pd_status(pd_repo.root).stdout, SECTION)


def hook_context(cwd, source, home):
    r = subprocess.run(["bash", str(HOOK)], input=json.dumps({"session_id": "s1", "source": source, "cwd": str(cwd)}),
                       capture_output=True, text=True, env={**os.environ, "HOME": str(home)})
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact"])
def test_c28_session_start_passes_the_section(pd_repo, tmp_path, source):
    pd_repo.git("branch", "worktree-wf_r-1")
    lines = hook_context(pd_repo.root, source, tmp_path / "home").split("\n")
    assert SECTION in lines and "-: worktree-wf_r-1 — stray branch" in lines
    assert ("pd: active and blocked items, next ready, retros owed, leftover worktrees "
            "(pd-status prints the rest)") in lines


def test_c28_comment_and_hook_test():
    lines = HOOK.read_text().split("\n")
    awk = next(i for i, line in enumerate(lines) if "summary=$(" in line)
    assert "leftover worktrees" in lines[awk - 1].lower()
    assert SECTION in HOOK_TEST.read_text()
    r = subprocess.run(["bash", str(HOOK_TEST)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("fail", ["all", "worktree list", "branch --list"])
def test_c29_git_failure_drops_the_section(pd_repo, fake_bin, fail):
    pd_repo.git("branch", "worktree-wf_r-1")
    real = pd_status(pd_repo.root)
    assert SECTION in real.stdout
    r = pd_status(pd_repo.root, bindir=fake_bin, FAKE_FAIL=fail)
    assert r.returncode == 0 and SECTION not in r.stdout
    assert section(r.stdout, "Items") == section(real.stdout, "Items")


def test_c29_outside_git(pd_repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copytree(pd_repo.root / ".claude", outside / ".claude")
    shutil.copytree(pd_repo.root / "docs", outside / "docs")
    pd_repo.git("branch", "worktree-wf_r-1")
    r = pd_status(outside)
    assert r.returncode == 0 and SECTION not in r.stdout
    assert section(r.stdout, "Items") == section(pd_status(pd_repo.root).stdout, "Items")


def test_c30_git_cost_is_two_calls(pd_repo, task_worktree, fake_bin, tmp_path):
    expected = Counter(["rev-parse --show-toplevel", "worktree list --porcelain -z",
                        "branch --list pd/* workitem/* worktree-wf_* --format=%(refname:short)"])
    log = tmp_path / "git.log"

    def calls():
        log.write_text("")
        r = pd_status(pd_repo.root, bindir=fake_bin, GIT_LOG=str(log))
        assert r.returncode == 0 and SECTION in r.stdout
        return Counter(" ".join(json.loads(line)) for line in log.read_text().splitlines())

    pd_repo.git("branch", "worktree-wf_r-1")
    assert calls() == expected
    for name in ("A", "B", "C"):
        make_item(pd_repo.root, name, "active")
    make_item(pd_repo.root, "D", "done")
    for n, name in enumerate(("A", "B", "C"), start=1):
        task_worktree(n, "clean", id=name)
    pd_repo.git("branch", "pd/D/task-1")
    assert calls() == expected


def call_violations(source):
    """Problems in a script's source: missing imports or calls, or a worktree-list git call built by hand."""
    tree = ast.parse(source)
    problems = []
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "pd_common"
                for a in n.names}
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    for name in ("worktrees", "run_in_flight"):
        if name not in imported or name not in called:
            problems.append(f"{name} not imported and called")
    messages = {id(n.exc) for n in ast.walk(tree) if isinstance(n, ast.Raise)}  # a raised message isn't a git call
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        if id(call) in messages or (isinstance(call.func, ast.Name) and call.func.id == "print"):
            continue
        for arg in call.args + [k.value for k in call.keywords]:
            for node in ast.walk(arg):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and "worktree list" in node.value:
                    problems.append("worktree list string")
                if isinstance(node, (ast.List, ast.Tuple)):
                    words = [e.value for e in node.elts if isinstance(e, ast.Constant)]
                    if any(a == "worktree" and b == "list" for a, b in zip(words, words[1:])):
                        problems.append("worktree, list pair")
    return problems


def test_c31_shared_helpers_only():
    for script in ("pd-worktrees", "pd-status"):
        assert call_violations((SCRIPTS / script).read_text()) == [], script
    control = (SCRIPTS / "pd-status").read_text() + (
        '\nimport subprocess\nsubprocess.run(["git", "worktree", "list", "--porcelain", "-z"])\n'
        "from pd_common import worktrees, run_in_flight\nworktrees(1)\nrun_in_flight(1)\n")
    assert "worktree, list pair" in call_violations(control)


def test_c37_self_test_and_docstring():
    r = subprocess.run([sys.executable, str(PD_STATUS), "--self-test"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    source = (SCRIPTS / "pd-status").read_text()
    tree = ast.parse(source)
    assert "live git state" in ast.get_docstring(tree)
    self_test = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_self_test")
    assert SECTION in ast.get_source_segment(source, self_test)
