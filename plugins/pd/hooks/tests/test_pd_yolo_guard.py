"""YoloGuard (shape.md Contracts): the PreToolUse hook that refuses questions and hard-stop commands while YOLO is on."""
import os
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOOK = PLUGIN_ROOT / "hooks" / "pd-yolo-guard.sh"
PD_YOLO = PLUGIN_ROOT / "scripts" / "pd-yolo"
DECISION_LABELS = ("Session:", "Stage:", "Pros/cons:", "Trade-off:", "Implications:", "Premortem:")
CHECK_FAILED_QUESTION = "pd-yolo-guard: check failed; question allowed"
CHECK_FAILED_COMMAND = "pd-yolo-guard: check failed; command refused while YOLO is on"
GIT_IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_IDENTITY})
    if check:
        assert r.returncode == 0, r.stderr
    return r


def make_repo(path, branch="workitem/x"):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "commit", "-q", "--allow-empty", "-m", "init")
    if branch != "main":
        git(path, "checkout", "-q", "-b", branch)
    for name in ("sub", "other"):
        (path / name).mkdir()
    return path


def conflicted_repo(path, kind):
    """A repo stopped mid-merge, mid-rebase or mid-cherry-pick on a conflict in conflicted.txt."""
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / "conflicted.txt").write_text("base\n")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "base")
    git(path, "checkout", "-q", "-b", "side")
    (path / "conflicted.txt").write_text("side\n")
    git(path, "commit", "-q", "-am", "side")
    git(path, "checkout", "-q", "main")
    (path / "conflicted.txt").write_text("main\n")
    git(path, "commit", "-q", "-am", "main")
    if kind == "merge":
        git(path, "merge", "side", check=False)
    elif kind == "cherry-pick":
        git(path, "cherry-pick", "side", check=False)
    else:
        git(path, "checkout", "-q", "side")
        git(path, "rebase", "main", check=False)
    assert git(path, "ls-files", "-u").stdout.strip()
    return path


@pytest.fixture
def yolo(gate_home):
    (gate_home / ".claude" / "pd" / "gate" / "s1.yolo").write_text("2026-11-26T10:00:00+08:00\n")


def question_call(*questions, sid="s1", **extra):
    return {"session_id": sid, "hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "cwd": "/",
            "tool_input": {"questions": [{"question": q} for q in questions]}, **extra}


def bash_call(command, cwd, sid="s1", **extra):
    return {"session_id": sid, "hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(cwd),
            "tool_input": {"command": command}, **extra}


def put_first_on_path(tmp_path, body):
    """A python3 script first on PATH: returns the env entry for run_hook."""
    d = tmp_path / "fakebin"
    d.mkdir()
    script = d / "python3"
    script.write_text("#!/bin/sh\n" + body + "\n")
    script.chmod(0o755)
    return {"PATH": f"{d}:{os.environ['PATH']}"}


def assert_allowed(result):
    code, err = result
    assert (code, err) == (0, "")


def assert_hard_stop(result, simple_command):
    code, err = result
    assert code == 2, err
    assert simple_command in err
    assert "Hard stop:" in err and "! " in err and "Never run it yourself" in err
    assert "check failed" not in err


def test_c1_yolo_off_allows_everything_without_python(run_hook, tmp_path):
    marker = tmp_path / "python-ran"
    env = put_first_on_path(tmp_path, f"touch {marker}\nexit 1")
    repo = make_repo(tmp_path / "repo")
    assert_allowed(run_hook(HOOK, question_call("Pick a name?"), env))
    assert_allowed(run_hook(HOOK, bash_call("git push -f origin x", repo), env))
    assert not marker.exists()


def test_c2_yolo_on_refuses_a_soft_question(run_hook, yolo):
    code, err = run_hook(HOOK, question_call("Hard stop: merge?", "Pick a name?"))
    assert code == 2
    assert "decide this yourself" in err and "A (conductor, on the user's behalf):" in err
    assert all(label in err for label in DECISION_LABELS)


def test_c3_yolo_on_allows_hard_stop_questions(run_hook, yolo):
    assert_allowed(run_hook(HOOK, question_call("Hard stop: merge?", "Hard stop: push?")))


def test_c4_another_session_is_not_guarded(run_hook, yolo):
    assert_allowed(run_hook(HOOK, question_call("Pick a name?", sid="s2")))
    assert run_hook(HOOK, question_call("Pick a name?", sid="s1"))[0] == 2


def test_c5_pd_yolo_off_lifts_the_guard(run_hook, yolo, gate_home):
    assert run_hook(HOOK, question_call("Pick a name?"))[0] == 2
    subprocess.run([str(PD_YOLO), "off", "--session", "s1"], check=True, env={**os.environ, "HOME": str(gate_home)})
    assert_allowed(run_hook(HOOK, question_call("Pick a name?")))


def test_c6_malformed_questions_fail_open(run_hook, yolo):
    payload = question_call("x")
    payload["tool_input"]["questions"] = "Pick a name?"
    assert run_hook(HOOK, payload) == (0, CHECK_FAILED_QUESTION + "\n")


DESTRUCTIVE = [
    "git push -f origin x", "git push --force-with-lease=x origin x", "git push origin +x",
    "git push --delete origin x", "git push origin :x", "git push origin main",
    "git push origin HEAD:refs/heads/main", "git push --all origin", "gh pr merge 3 --squash",
    "gh --repo owner/repo pr merge 3", "gh -R owner/repo pr merge 3",
    "gh pr --repo owner/repo merge 3", "gh pr -R owner/repo merge 3", "gh pr --repo=o/r merge 3",
    "git branch -D x", "git branch -d x", "git branch --delete x", "git reset --hard HEAD~1",
    "git clean -fd", "git clean --force", "rm -rf /tmp/elsewhere", "git -C other push -f origin x",
    "cd sub && git push -f origin x", "git status && git push -f",
]


@pytest.mark.parametrize("command", DESTRUCTIVE)
def test_c7_destructive_commands_are_hard_stops(run_hook, yolo, tmp_path, command):
    repo = make_repo(tmp_path / "repo")
    assert_hard_stop(run_hook(HOOK, bash_call(command, repo)), command.split("&& ")[-1])


@pytest.mark.parametrize("command", ["rm -rf /tmp/elsewhere", "git reset --hard HEAD", "gh pr merge 1"])
def test_c7b_an_escaped_backtick_hides_no_command(run_hook, yolo, tmp_path, command):
    repo = make_repo(tmp_path / "repo")
    assert_hard_stop(run_hook(HOOK, bash_call("echo \\`; " + command, repo)), command)


def test_c8_push_without_refspec_depends_on_the_branch(run_hook, yolo, tmp_path):
    on_main = make_repo(tmp_path / "main-repo", branch="main")
    on_item = make_repo(tmp_path / "item-repo")
    for command in ("git push", "git push origin HEAD"):
        assert_hard_stop(run_hook(HOOK, bash_call(command, on_main)), command)
        assert_allowed(run_hook(HOOK, bash_call(command, on_item)))


@pytest.mark.parametrize("command", [
    "git push -u origin workitem/x", "git push -o ci.skip origin workitem/x", 'git commit -m "never rm -rf /"',
    "rm -rf agent_sandbox/2026-11-26/x", "rm notes.txt", "git branch -v", "git clean -n", "git reset --soft HEAD~1",
])
def test_c9_ordinary_commands_pass(run_hook, yolo, tmp_path, command):
    assert_allowed(run_hook(HOOK, bash_call(command, make_repo(tmp_path / "repo"))))


def test_c10_worktree_remove_only_for_task_branches(run_hook, yolo, tmp_path):
    main = make_repo(tmp_path / "main", branch="main")
    task1, task2, other = tmp_path / "w1", tmp_path / "w2", tmp_path / "w3"
    git(main, "worktree", "add", "-q", "-b", "pd/2026-11-26-x/task-1", str(task1))
    git(main, "worktree", "add", "-q", "-b", "pd/2026-11-26-x/task-2", str(task2))
    git(main, "worktree", "add", "-q", "-b", "feature/y", str(other))
    for cwd in (main, task2):
        assert_allowed(run_hook(HOOK, bash_call(f"git worktree remove --force {task1}", cwd)))
        assert_hard_stop(run_hook(HOOK, bash_call(f"git worktree remove --force {other}", cwd)), f"git worktree remove --force {other}")


def test_c11_rm_is_judged_against_the_checkout_not_the_git_dir(run_hook, yolo, tmp_path):
    store, checkout = tmp_path / "store", tmp_path / "checkout"
    store.mkdir()
    checkout.mkdir()
    git(checkout, "init", "-q", "-b", "main", f"--separate-git-dir={store}/.git")
    assert_hard_stop(run_hook(HOOK, bash_call(f"rm -rf {store}/agent_sandbox/x", checkout)), f"rm -rf {store}/agent_sandbox/x")
    assert_allowed(run_hook(HOOK, bash_call("rm -rf agent_sandbox/x", checkout)))


@pytest.mark.parametrize("kind, command", [
    ("merge", "git commit -m x"), ("merge", "git merge --continue"),
    ("rebase", "git rebase --continue"), ("cherry-pick", "git cherry-pick --continue"),
])
def test_c12_unmerged_paths_block_the_commit(run_hook, yolo, tmp_path, kind, command):
    code, err = run_hook(HOOK, bash_call(command, conflicted_repo(tmp_path / "conflict", kind)))
    assert code == 2
    assert "conflicted.txt" in err and "! git commit" in err and "pd-yolo off" in err
    assert "Hard stop:" in err and "Resolve them" not in err


def test_c12_a_clean_repo_may_commit(run_hook, yolo, tmp_path):
    assert_allowed(run_hook(HOOK, bash_call("git commit -m x", make_repo(tmp_path / "repo"))))


def test_c15_the_selected_repo_is_read_not_the_cwd(run_hook, yolo, tmp_path):
    conflict, clean = conflicted_repo(tmp_path / "conflict", "merge"), make_repo(tmp_path / "clean")
    for command in (f"git -C {conflict} commit -m x", f"git --git-dir={conflict}/.git --work-tree={conflict} commit -m x"):
        code, err = run_hook(HOOK, bash_call(command, clean))
        assert code == 2 and "conflicted.txt" in err


@pytest.mark.parametrize("command", ['git push -f "x', "git p'ush' -f \"x", 'echo $(git status) "x'])
def test_c13_unsplittable_dangerous_lines_are_refused(run_hook, yolo, tmp_path, command):
    assert run_hook(HOOK, bash_call(command, make_repo(tmp_path / "repo"))) == (2, CHECK_FAILED_COMMAND + "\n")


def test_c13_an_unsplittable_harmless_line_passes(run_hook, yolo, tmp_path):
    assert run_hook(HOOK, bash_call('echo "hi', make_repo(tmp_path / "repo")))[0] == 0


def test_c16_a_broken_python_fails_closed_for_commands_only(run_hook, yolo, tmp_path):
    env = put_first_on_path(tmp_path, "exit 1")
    repo = make_repo(tmp_path / "repo")
    assert run_hook(HOOK, question_call("Pick a name?"), env) == (0, CHECK_FAILED_QUESTION + "\n")
    assert run_hook(HOOK, bash_call("git push -f origin x", repo), env) == (2, CHECK_FAILED_COMMAND + "\n")
    assert run_hook(HOOK, bash_call("git status", repo), env)[0] == 0


def test_c16_git_failing_inside_the_check_fails_closed(run_hook, yolo, tmp_path):
    repo = make_repo(tmp_path / "repo")
    assert run_hook(HOOK, bash_call(f"git -C {tmp_path}/missing commit -m x", repo)) == (2, CHECK_FAILED_COMMAND + "\n")


def test_c14_a_subagent_call_is_refused_like_the_main_session(run_hook, yolo, tmp_path):
    repo = make_repo(tmp_path / "repo")
    assert_hard_stop(run_hook(HOOK, bash_call("git push -f origin x", repo, agent_id="a1")), "git push -f origin x")
