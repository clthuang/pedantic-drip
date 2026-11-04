"""Tests for pd-worktrees (shape.md ## Design; plan Task 1, cases C1 to C24)."""
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[2]
REAL_GIT = shutil.which("git")

FAKE_GIT = f"""#!{sys.executable}
import json, os, subprocess, sys
args = sys.argv[1:]
with open(os.environ["GIT_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
mode = os.environ.get("FAKE_MODE", "log")
real = "{REAL_GIT}"
if mode == "fail-for-each-ref" and "for-each-ref" in args:
    sys.stderr.write("fatal: fake for-each-ref failure\\n")
    sys.exit(128)
if mode == "lock" and args[:2] == ["worktree", "remove"]:
    subprocess.check_call([real, "worktree", "lock", args[2]])
if mode == "fail-delete" and "update-ref" in args and "-d" in args:
    sys.exit(1)
if mode == "fail-delete" and "rev-parse" in args and "--verify" in args:
    sys.stderr.write("fatal: fake rev-parse failure\\n")
    sys.exit(128)
code = subprocess.call([real, *args])
if mode in ("move", "occupy") and "for-each-ref" in args and "--contains" in args:
    stray = os.environ["FAKE_STRAY"]
    if mode == "move":
        tree = subprocess.check_output([real, "rev-parse", stray + "^{{tree}}"], text=True).strip()
        new = subprocess.check_output([real, "commit-tree", tree, "-p", stray, "-m", "moved"], text=True).strip()
        subprocess.check_call([real, "update-ref", "refs/heads/" + stray, new])
    else:
        subprocess.check_call([real, "worktree", "add", "-q", os.environ["FAKE_OCCUPY_DIR"], stray])
sys.exit(code)
"""

ARG_FORBIDDEN = ("--force", "-f", "unlock", "prune")


def shown(path):
    return path.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def check_guard(calls):
    """The must-nots on forcing, unlocking and deleting task branches, over logged git argument lists."""
    for args in calls:
        for bad in ARG_FORBIDDEN:
            assert bad not in args, f"forbidden {bad}: {args}"
        rest = list(args)
        while rest[:1] == ["-C"]:
            rest = rest[2:]
        assert not (rest[:1] == ["branch"] and rest[1:2] in (["-d"], ["-D"])), f"branch delete: {args}"
        if "update-ref" in args:
            assert "--no-deref" in args, f"update-ref without --no-deref: {args}"
            if "-d" in args:
                for ref in args:
                    assert not ref.startswith(("refs/heads/pd/", "refs/heads/workitem/")), f"deletes {ref}"


@pytest.fixture
def wt(pd_repo, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "git"
    fake.write_text(FAKE_GIT)
    fake.chmod(0o755)
    log = tmp_path / "git.log"

    def run(*args, cwd=None, mode="log", closed_stdout=False, **extra_env):
        log.write_text("")
        env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "GIT_LOG": str(log),
               "FAKE_MODE": mode, **extra_env}
        command = [sys.executable, str(SCRIPTS / "pd-worktrees"), *args]
        if closed_stdout:  # stdout is a pipe whose read end is already closed
            read_end, write_end = os.pipe()
            os.close(read_end)
            r = subprocess.run(command, cwd=cwd or pd_repo.root, env=env, stdout=write_end, stderr=subprocess.PIPE)
            os.close(write_end)
            r.stdout = b""
        else:
            r = subprocess.run(command, cwd=cwd or pd_repo.root, env=env, capture_output=True)
        stdout = r.stdout.decode("utf-8", "surrogateescape")
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        check_guard(calls)
        return SimpleNamespace(stdout=stdout, lines=stdout.split("\n")[:-1] if stdout else [],
                               stderr=r.stderr.decode("utf-8", "replace"), code=r.returncode, calls=calls)
    return run


def multiset(lines):
    return Counter(lines)


def stray_on(pd_repo, name, tip):
    pd_repo.git("branch", name, tip)


def test_c1_list_every_state(pd_repo, task_worktree, wt):
    id_ = pd_repo.id
    p1, p2 = task_worktree(1, "clean"), task_worktree(2, "dirty")
    p3, p4 = task_worktree(3, "locked"), task_worktree(4, "gone")
    pd_repo.git("branch", "worktree-wf_r-1")
    before = pd_repo.snapshot()
    r = wt(id_)
    assert multiset(r.lines) == multiset([
        f"clean {p1} pd/{id_}/task-1", f"dirty {p2} pd/{id_}/task-2", f"locked {p3} pd/{id_}/task-3",
        f"gone {p4} pd/{id_}/task-4", "stray worktree-wf_r-1"])
    assert pd_repo.snapshot() == before
    assert r.code == 0


def test_c2_remove_clean(pd_repo, task_worktree, wt):
    p1, p2 = task_worktree(1, "clean"), task_worktree(2, "clean")
    r = wt(pd_repo.id, "--remove")
    assert multiset(r.lines) == multiset([f"removed {p1}", f"removed {p2}"])
    assert not Path(p1).exists() and not Path(p2).exists()
    assert not {p1, p2} & {w["path"] for w in pd_repo.listed()}
    assert pd_repo.has_branch(f"pd/{pd_repo.id}/task-1") and pd_repo.has_branch(f"pd/{pd_repo.id}/task-2")
    assert r.code == 0


def test_c3_dirty_is_kept(pd_repo, task_worktree, wt):
    p1, p2 = task_worktree(1, "clean"), task_worktree(2, "dirty")
    r = wt(pd_repo.id, "--remove")
    assert f"removed {p1}" in r.lines and f"kept (dirty): {p2}" in r.lines
    assert (Path(p2) / "untracked.txt").exists()
    assert not Path(p1).exists() and p1 not in {w["path"] for w in pd_repo.listed()}
    assert r.code == 1


def test_c4_locked_and_gone_is_kept(pd_repo, task_worktree, wt):
    p1 = task_worktree(1, "locked")
    shutil.rmtree(p1)
    r = wt(pd_repo.id, "--remove")
    assert f"kept (locked): {p1}" in r.lines
    assert next(w for w in pd_repo.listed() if w["path"] == p1)["locked"]
    assert r.code == 1


def test_c5_gone_cleared_by_path(pd_repo, task_worktree, wt):
    p1 = task_worktree(1, "gone")
    pd_repo.git("worktree", "add", "-q", "-b", "other", ".claude/worktrees/other")
    other = pd_repo.path_of("other")
    shutil.rmtree(other)
    r = wt(pd_repo.id, "--remove")
    assert f"removed {p1}" in r.lines
    assert p1 not in {w["path"] for w in pd_repo.listed()}
    pd_repo.git("branch", "-D", f"pd/{pd_repo.id}/task-1")
    assert other in {w["path"] for w in pd_repo.listed()}
    assert r.code == 0


def test_c6_strays_by_containment(pd_repo, wt):
    contained = pd_repo.advance(f"workitem/{pd_repo.id}", "on the work item branch")
    stray_on(pd_repo, "worktree-wf_r-2", contained)
    unique = pd_repo.commit_on("refs/heads/main", "only on the stray")
    stray_on(pd_repo, "worktree-wf_r-3", unique)
    r = wt(pd_repo.id, "--remove")
    assert "deleted worktree-wf_r-2" in r.lines and "kept (unique commits): worktree-wf_r-3" in r.lines
    assert not pd_repo.has_branch("worktree-wf_r-2")
    assert pd_repo.tip("worktree-wf_r-3") == unique
    assert r.code == 0


def test_c7_other_worktrees_untouched(pd_repo, task_worktree, wt):
    pd_repo.git("worktree", "add", "-q", "-b", "worktree-thin-pd-release", ".claude/worktrees/thin-pd-release")
    pd_repo.git("worktree", "add", "-q", "-b", "followups", ".pd-worktrees/followups")
    task_worktree(1, "clean", id="other-item", path=".claude/worktrees/other-1")
    p1 = task_worktree(1, "clean")
    r = wt(pd_repo.id, "--remove")
    assert r.lines == [f"removed {p1}"]
    kept = {w["branch"] for w in pd_repo.listed()}
    assert {"worktree-thin-pd-release", "followups", "pd/other-item/task-1"} <= kept
    assert all(pd_repo.has_branch(b) for b in ("worktree-thin-pd-release", "followups", "pd/other-item/task-1"))
    assert r.code == 0


def test_c8_only_the_named_task(pd_repo, task_worktree, wt):
    p1, p2 = task_worktree(1, "clean"), task_worktree(2, "clean")
    stray_on(pd_repo, "worktree-wf_r-2", pd_repo.tip(f"workitem/{pd_repo.id}"))
    r = wt(pd_repo.id, "--remove", "--task", "2")
    assert r.lines == [f"removed {p2}"]
    assert not Path(p2).exists() and p2 not in {w["path"] for w in pd_repo.listed()}
    assert pd_repo.has_branch(f"pd/{pd_repo.id}/task-2")
    assert Path(p1).exists() and pd_repo.has_branch("worktree-wf_r-2")
    assert r.code == 0


def test_c9_run_in_flight_removes_nothing(pd_repo, task_worktree, wt):
    pd_repo.set_now("a first line", "run in flight: implement-tasks session x")
    task_worktree(1, "clean")
    before = pd_repo.snapshot()
    r = wt(pd_repo.id, "--remove")
    assert r.lines == ["run in flight: implement-tasks session x"]
    assert pd_repo.snapshot() == before
    assert r.code == 1


def test_run_in_flight_is_checked_with_nothing_to_remove(pd_repo, wt):
    pd_repo.set_now("a first line", "run in flight: implement-tasks session x")
    for extra in ((), ("--task", "9")):
        r = wt(pd_repo.id, "--remove", *extra)
        assert r.lines == ["run in flight: implement-tasks session x"]
        assert r.code == 1


def test_refused_removal_reads_lock_state_again(pd_repo, task_worktree, wt):
    p1 = task_worktree(1, "clean")
    r = wt(pd_repo.id, "--remove", mode="lock")
    assert r.lines == [f"kept (locked): {p1}"]
    assert r.code == 1


def test_failed_lookup_after_failed_delete_is_exit_2(pd_repo, wt):
    stray_on(pd_repo, "worktree-wf_r-2", pd_repo.tip(f"workitem/{pd_repo.id}"))
    r = wt(pd_repo.id, "--remove", mode="fail-delete")
    assert r.stderr.startswith("pd-worktrees:")
    assert r.code == 2


def test_c10_work_item_branch_gone(pd_repo, task_worktree, wt):
    p1 = task_worktree(1, "clean")
    pd_repo.git("branch", "-D", f"workitem/{pd_repo.id}")
    r = wt(pd_repo.id, "--remove")
    assert f"removed {p1}" in r.lines
    assert not Path(p1).exists() and p1 not in {w["path"] for w in pd_repo.listed()}
    assert pd_repo.has_branch(f"pd/{pd_repo.id}/task-1")
    assert r.code == 0


def test_c11_nothing_to_show(pd_repo, wt):
    expected = [f"no worktrees for {pd_repo.id}"]
    before = pd_repo.snapshot()
    r = wt(pd_repo.id)
    assert r.lines == expected and r.code == 0
    r = wt(pd_repo.id, "--remove")
    assert r.lines == expected and r.code == 0
    assert pd_repo.snapshot() == before


def test_c12_usage_errors(pd_repo, task_worktree, wt, tmp_path):
    pd_repo.git("branch", "pd/ghost/task-1")
    outside = tmp_path / "outside"
    outside.mkdir()
    before = pd_repo.snapshot()
    id_ = pd_repo.id
    for args, cwd in (((), None), (("--remove",), None), ((id_, "--task", "1"), None),
                      ((id_, "--strays"), None), (("ghost",), None), ((id_,), outside)):
        r = wt(*args, cwd=cwd)
        assert r.stdout == "", args
        assert r.stderr.startswith("pd-worktrees:"), (args, r.stderr)
        assert r.code == 2, args
        assert pd_repo.snapshot() == before, args


def test_c13_main_checkout_on_task_branch(pd_repo, wt):
    pd_repo.git("switch", "-q", "-c", f"pd/{pd_repo.id}/task-1")
    r = wt(pd_repo.id, "--remove")
    assert f"kept (main checkout): {pd_repo.main_path()}" in r.lines
    assert pd_repo.git("branch", "--show-current") == f"pd/{pd_repo.id}/task-1"
    assert r.code == 1


def test_c14_strays_without_a_work_item(pd_repo, wt):
    pd_repo.git("branch", "worktree-wf_r-2", "main")
    unique = pd_repo.commit_on("refs/heads/main", "shared stray tip")
    stray_on(pd_repo, "worktree-wf_r-3", unique)
    stray_on(pd_repo, "worktree-wf_r-4", unique)
    pd_repo.git("checkout", "-q", "--orphan", "bare")
    pd_repo.git("rm", "-rf", "-q", ".")
    pd_repo.git("commit", "-q", "--allow-empty", "-m", "bare")
    assert not (pd_repo.root / "docs").exists()
    before = pd_repo.snapshot()
    r = wt("--strays")
    assert multiset(r.lines) == multiset(["stray worktree-wf_r-2", "stray worktree-wf_r-3", "stray worktree-wf_r-4"])
    assert pd_repo.snapshot() == before and r.code == 0
    r = wt("--strays", "--remove")
    assert multiset(r.lines) == multiset(["deleted worktree-wf_r-2", "kept (unique commits): worktree-wf_r-3",
                                          "kept (unique commits): worktree-wf_r-4"])
    assert not pd_repo.has_branch("worktree-wf_r-2")
    assert pd_repo.tip("worktree-wf_r-3") == unique == pd_repo.tip("worktree-wf_r-4")
    assert r.code == 0


def test_c15_stray_moved_before_delete(pd_repo, wt):
    old = pd_repo.tip(f"workitem/{pd_repo.id}")
    stray_on(pd_repo, "worktree-wf_r-2", old)
    r = wt(pd_repo.id, "--remove", mode="move", FAKE_STRAY="worktree-wf_r-2")
    assert "kept (unique commits): worktree-wf_r-2" in r.lines
    assert pd_repo.has_branch("worktree-wf_r-2") and pd_repo.tip("worktree-wf_r-2") != old
    assert r.code == 0


def test_c16_newline_in_path(pd_repo, task_worktree, wt):
    p1 = task_worktree(1, "clean", path=".claude/worktrees/task-1\nlocked")
    assert "\n" in p1
    r = wt(pd_repo.id)
    assert r.lines == [f"clean {p1.replace(chr(10), chr(92) + 'n')} pd/{pd_repo.id}/task-1"]
    r = wt(pd_repo.id, "--remove")
    assert r.lines == [f"removed {shown(p1)}"]
    assert not Path(p1).exists() and r.code == 0


def test_c17_invoked_from_inside_a_removed_worktree(pd_repo, task_worktree, wt):
    p1, p2 = task_worktree(1, "clean"), task_worktree(2, "clean")
    r = wt(pd_repo.id, "--remove", cwd=p1)
    assert multiset(r.lines) == multiset([f"removed {p1}", f"removed {p2}"])
    assert not Path(p1).exists() and not Path(p2).exists()
    assert r.code == 0


def test_c18_clean_worktree_with_submodule(pd_repo, task_worktree, wt, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "s"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=sub, check=True)
    p1 = task_worktree(1, "clean")
    pd_repo.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "vendor", cwd=p1)
    pd_repo.git("commit", "-q", "-m", "add submodule", cwd=p1)
    assert pd_repo.git("status", "--porcelain", cwd=p1) == ""
    r = wt(pd_repo.id, "--remove")
    assert f"kept (clean): {p1}" in r.lines
    assert Path(p1).exists()
    assert r.code == 1


def test_c19_git_failure_is_exit_2(pd_repo, wt):
    pd_repo.git("branch", "worktree-wf_r-2")
    r = wt(pd_repo.id, "--remove", mode="fail-for-each-ref")
    assert r.stderr.startswith("pd-worktrees:")
    assert r.code == 2


def test_c20_symbolic_ref_stray(pd_repo, wt):
    tip = pd_repo.tip(f"workitem/{pd_repo.id}")
    pd_repo.git("symbolic-ref", "refs/heads/worktree-wf_alias", f"refs/heads/workitem/{pd_repo.id}")
    r = wt(pd_repo.id, "--remove")
    assert "deleted worktree-wf_alias" in r.lines
    assert not pd_repo.has_branch("worktree-wf_alias")
    assert pd_repo.tip(f"workitem/{pd_repo.id}") == tip
    assert r.code == 0


def test_c20b_symbolic_ref_to_a_stray_does_not_vouch(pd_repo, wt):
    unique = pd_repo.commit_on("refs/heads/main", "only the stray has it")
    stray_on(pd_repo, "worktree-wf_r-3", unique)
    pd_repo.git("symbolic-ref", "refs/heads/saved", "refs/heads/worktree-wf_r-3")
    r = wt(pd_repo.id, "--remove")
    assert "kept (unique commits): worktree-wf_r-3" in r.lines
    assert pd_repo.tip("worktree-wf_r-3") == unique
    assert pd_repo.git("rev-parse", "--verify", "-q", "saved") == unique
    assert r.code == 0


def test_c21_stray_taken_by_a_worktree(pd_repo, wt, tmp_path):
    stray_on(pd_repo, "worktree-wf_r-2", pd_repo.tip(f"workitem/{pd_repo.id}"))
    r = wt(pd_repo.id, "--remove", mode="occupy", FAKE_STRAY="worktree-wf_r-2",
           FAKE_OCCUPY_DIR=str(tmp_path / "occupied"))
    assert not any("worktree-wf_r-2" in line for line in r.lines)
    assert pd_repo.has_branch("worktree-wf_r-2")
    assert "worktree-wf_r-2" in {w["branch"] for w in pd_repo.listed()}
    assert r.code == 0


def test_c22_carriage_return_in_path(pd_repo, task_worktree, wt):
    p1 = task_worktree(1, "clean", path=".claude/worktrees/a\rb")
    pd_repo.git("worktree", "add", "-q", "-b", "other", ".claude/worktrees/a\nb")
    p2 = pd_repo.path_of("other")
    r = wt(pd_repo.id, "--remove")
    assert r.lines == [f"removed {p1.replace(chr(13), chr(92) + 'r')}"]
    assert not Path(p1).exists()
    assert p2 in {w["path"] for w in pd_repo.listed()}
    assert r.code == 0


def test_c23_guard_is_not_vacuous():
    oid = "a" * 40
    forbidden = [
        ["worktree", "remove", "--force", "/p"], ["worktree", "remove", "-f", "/p"], ["worktree", "unlock", "/p"],
        ["worktree", "prune"], ["branch", "-d", "x"], ["branch", "-D", "x"], ["-C", "/p", "branch", "-D", "x"],
        ["update-ref", "--no-deref", "-d", "refs/heads/pd/i/task-1", oid],
        ["update-ref", "--no-deref", "-d", "refs/heads/workitem/i", oid],
        ["update-ref", "-d", "refs/heads/worktree-wf_r-1", oid],
    ]
    for call in forbidden:
        with pytest.raises(AssertionError):
            check_guard([call])
    check_guard([["worktree", "list", "--porcelain", "-z"], ["worktree", "remove", "/p"],
                 ["update-ref", "--no-deref", "-d", "refs/heads/worktree-wf_r-1", oid]])


def test_c24_ci_and_changelog():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    line = next(l for l in ci.splitlines() if "uv run --project plugins/pd pytest" in l)
    for name in ("test_pd_worktrees.py", "test_pd_status_leftovers.py", "test_worktree_callers.py"):
        assert f"plugins/pd/scripts/{name}" in line
    changelog = (ROOT / "CHANGELOG.md").read_text()
    unreleased = changelog.split("## [Unreleased]")[1].split("\n## [")[0]
    assert "pd-worktrees" in unreleased


@pytest.mark.parametrize("remove_args", [None, ("--strays", "--remove")], ids=["by-id", "strays"])
def test_c38_same_named_tag_does_not_vouch(pd_repo, wt, remove_args):
    unique = pd_repo.commit_on("refs/heads/main", "only this stray has it")
    stray_on(pd_repo, "worktree-wf_r-3", unique)
    pd_repo.git("tag", "worktree-wf_r-3", unique)
    contained = pd_repo.tip(f"workitem/{pd_repo.id}")
    stray_on(pd_repo, "worktree-wf_r-2", contained)
    pd_repo.git("tag", "worktree-wf_r-2", contained)
    r = wt(*(remove_args or (pd_repo.id, "--remove")))
    assert multiset(r.lines) == multiset(["kept (unique commits): worktree-wf_r-3", "deleted worktree-wf_r-2"])
    assert pd_repo.tip("worktree-wf_r-3") == unique
    assert not pd_repo.has_branch("worktree-wf_r-2")
    assert r.code == 0


@pytest.mark.parametrize("args", [("..",), (".",), ("..", "--remove"), ("a/b", "--remove"),
                                  ("--strays", "--remove", "--task", "1")])
def test_c42_usage_errors(pd_repo, wt, args):
    stray_on(pd_repo, "worktree-wf_r-2", pd_repo.tip(f"workitem/{pd_repo.id}"))
    before = pd_repo.snapshot()
    r = wt(*args)
    assert r.stdout == "" and r.stderr.startswith("pd-worktrees:") and r.code == 2
    assert pd_repo.snapshot() == before and pd_repo.has_branch("worktree-wf_r-2")


def symref(pd_repo, name, target):
    pd_repo.git("symbolic-ref", f"refs/heads/{name}", f"refs/heads/{target}")


def contained_stray(pd_repo, name="worktree-wf_r-2"):
    """A stray whose tip workitem/<id> contains; returns the tip."""
    tip = pd_repo.advance(f"workitem/{pd_repo.id}", "on the work item branch")
    stray_on(pd_repo, name, tip)
    return tip


@pytest.mark.parametrize("remove_args", [None, ("--strays", "--remove")], ids=["by-id", "strays"])
def test_c44a_symbolic_branch_pointing_at_a_stray_keeps_it(pd_repo, wt, remove_args):
    tip = contained_stray(pd_repo)
    symref(pd_repo, "saved", "worktree-wf_r-2")
    r = wt(*(remove_args or (pd_repo.id, "--remove")))
    assert "kept (symbolic branch): worktree-wf_r-2" in r.lines
    assert pd_repo.tip("worktree-wf_r-2") == tip
    assert pd_repo.git("rev-parse", "--verify", "-q", "saved") == tip
    assert r.code == 0


def test_c44b_symbolic_branch_pointing_elsewhere_keeps_nothing(pd_repo, wt):
    contained_stray(pd_repo)
    symref(pd_repo, "saved", "main")
    r = wt(pd_repo.id, "--remove")
    assert "deleted worktree-wf_r-2" in r.lines
    assert not pd_repo.has_branch("worktree-wf_r-2")
    assert r.code == 0


def test_c44c_symbolic_stray_is_deleted_and_its_target_kept(pd_repo, wt):
    tip = contained_stray(pd_repo)
    symref(pd_repo, "worktree-wf_a-sym", "worktree-wf_r-2")
    r = wt(pd_repo.id, "--remove")
    assert "deleted worktree-wf_a-sym" in r.lines
    assert not pd_repo.has_branch("worktree-wf_a-sym")
    assert "kept (symbolic branch): worktree-wf_r-2" in r.lines
    assert pd_repo.tip("worktree-wf_r-2") == tip
    assert r.code == 0


def test_c44d_chain_keeps_the_middle_link(pd_repo, wt):
    contained_stray(pd_repo)
    symref(pd_repo, "worktree-wf_r-2", "main")
    symref(pd_repo, "saved", "worktree-wf_r-2")
    r = wt(pd_repo.id, "--remove")
    assert "kept (symbolic branch): worktree-wf_r-2" in r.lines
    assert pd_repo.git("symbolic-ref", "--no-recurse", "refs/heads/saved") == "refs/heads/worktree-wf_r-2"
    assert pd_repo.git("rev-parse", "--verify", "-q", "saved")
    assert r.code == 0


def test_c46_stray_name_with_a_slash(pd_repo, wt):
    name = "worktree-wf_a/b"
    main_tip = pd_repo.tip("main")
    stray_on(pd_repo, name, main_tip)
    for args in ((pd_repo.id,), ("--strays",)):
        r = wt(*args)
        assert f"stray {name}" in r.lines and r.code == 0, args
    for args in (("--strays", "--remove"), (pd_repo.id, "--remove")):
        r = wt(*args)
        assert f"deleted {name}" in r.lines and r.code == 0, args
        assert not pd_repo.has_branch(name), args
        stray_on(pd_repo, name, main_tip)


def test_c47a_listing_to_a_closed_pipe(pd_repo, task_worktree, wt):
    task_worktree(1, "clean")
    pd_repo.git("branch", "worktree-wf_r-1")
    for args in ((pd_repo.id,), ("--strays",)):
        r = wt(*args, closed_stdout=True)
        assert r.stderr == "" and r.code == 0, (args, r.stderr)


def test_c47b_remove_finishes_with_a_closed_pipe(pd_repo, task_worktree, wt):
    p1 = task_worktree(1, "clean")
    contained_stray(pd_repo)
    r = wt(pd_repo.id, "--remove", closed_stdout=True)
    assert r.stderr == "" and r.code == 0
    assert not Path(p1).exists() and p1 not in {w["path"] for w in pd_repo.listed()}
    assert not pd_repo.has_branch("worktree-wf_r-2")


def test_c47c_exit_1_survives_a_closed_pipe(pd_repo, task_worktree, wt):
    p1, p2 = task_worktree(1, "clean"), task_worktree(2, "dirty")
    r = wt(pd_repo.id, "--remove", closed_stdout=True)
    assert r.stderr == "" and r.code == 1
    assert not Path(p1).exists() and Path(p2).exists()


def test_c47d_exit_2_message_with_a_closed_pipe(pd_repo, task_worktree, wt):
    task_worktree(1, "clean")
    contained_stray(pd_repo)
    r = wt(pd_repo.id, "--remove", mode="fail-delete", closed_stdout=True)
    assert r.stderr.startswith("pd-worktrees:")
    assert "Traceback" not in r.stderr and "BrokenPipeError" not in r.stderr
    assert r.code == 2


def test_c48_id_with_a_slash_is_refused(pd_repo, wt):
    contained_stray(pd_repo)
    before = pd_repo.snapshot()
    for args in ((f"{pd_repo.id}/..",), (f"{pd_repo.id}/..", "--remove"), (f"{pd_repo.id}/",)):
        r = wt(*args)
        assert r.stdout == "" and r.stderr.startswith("pd-worktrees:") and r.code == 2, args
        assert pd_repo.snapshot() == before, args
