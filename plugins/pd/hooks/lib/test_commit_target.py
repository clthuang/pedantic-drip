"""Tests of commit_target.py through its stdin/stdout contract, and of the hooks that call it.

Shared terms: `seen(cmd, cwd)` runs commit_target.py with the hook JSON on stdin and returns stdout;
`hook(script, cmd, cwd)` runs a hook script the same way. `repo` is a git repository on `main` with a
local branch `workitem/x` and a `sub/` directory.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

_LIB = os.path.dirname(os.path.abspath(__file__))
_HOOKS = os.path.dirname(_LIB)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HOOKS)))
_SCRIPT = os.path.join(_LIB, "commit_target.py")
_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=_ENV)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    (path / "sub").mkdir(parents=True)
    (path / "README.md").write_text("x\n")
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")
    _git(path, "branch", "workitem/x")
    return str(path.resolve())


def _on(repo, branch):
    _git(repo, "checkout", branch)


def seen(cmd, cwd):
    r = subprocess.run(["python3", _SCRIPT], input=json.dumps({"tool_input": {"command": cmd}, "cwd": cwd}),
                       capture_output=True, text=True, env=_ENV)
    assert r.returncode == 0, r.stderr
    assert r.stderr == ""
    return r.stdout


def hook(script, cmd, cwd):
    r = subprocess.run(["bash", os.path.join(_HOOKS, script)], input=json.dumps({"tool_input": {"command": cmd}, "cwd": cwd}),
                       capture_output=True, text=True, cwd=cwd, env=_ENV)
    return r.stdout, r.stderr, r.returncode


def empty_branch(repo, cmds):
    for cmd in cmds:
        assert seen(cmd, repo) == f"{repo}\t\n", cmd


def test_c1_timeout(repo):
    empty_branch(repo, ["timeout 30 git commit -m x", "timeout -s KILL -k 5 30 git commit -m x",
                        "timeout --signal=KILL --kill-after 5 30 git commit -m x"])


def test_c2_sudo(repo):
    empty_branch(repo, [f"sudo {o} git commit -m x" for o in ("-u alice", "-ualice", "-Eu alice", "-E -H", "--", "--user alice", "-k")])


def test_c3_env(repo):
    empty_branch(repo, ["env -u FOO git commit -m x", "env --unset FOO git commit -m x", "env -i PATH=/usr/bin git commit -m x"])


def test_c4_other_wrappers(repo):
    empty_branch(repo, [f"{w} git commit -m x" for w in ("nice -n 5", "nice --adjustment 5", "stdbuf -oL", "stdbuf --output L",
                                                         "time -p", "time --format %e", "nohup", "xargs --max-args 1")]
                 + ["xargs -I{} git commit -m {}"])


def test_c5_switch_behind_wrapper(repo):
    _on(repo, "workitem/x")
    for cmd in ("timeout 30 git switch main && git commit -m x", "timeout 30 git checkout main && git commit -m x"):
        assert seen(cmd, repo) == f"{repo}\tmain\n", cmd


def test_c6_nested_wrappers(repo):
    empty_branch(repo, ["sudo -u alice timeout 30 git commit -m x"])


def test_c7_directory_options(repo):
    sub = os.path.join(repo, "sub")
    for cmd in ("sudo -D sub git commit -m x", "sudo --chdir sub git commit -m x", "env -C sub git commit -m x", "env --chdir sub git commit -m x"):
        assert seen(cmd, repo) == f"{sub}\t\n", cmd
    assert seen("env -C sub true; git commit -m x", repo) == f"{repo}\t\n"


def test_c8_trailing_double_dash(repo):
    _on(repo, "workitem/x")
    cmd = "git checkout main -- && git commit -m t"
    assert seen(cmd, repo) == f"{repo}\tmain\n"
    out, _, _ = hook("pre-commit-guard.sh", cmd, repo)
    assert "Committing directly to 'main'" in out


def test_c9_file_restore(repo):
    _on(repo, "workitem/x")
    assert seen("git checkout main -- README.md && git commit -m t", repo) == f"{repo}\t\n"


def test_c10_guard_through_wrapper(repo):
    out, _, _ = hook("pre-commit-guard.sh", "timeout 30 git commit -m t", repo)
    assert "Committing directly to 'main'" in out


def test_c11_no_command_runs(repo):
    _on(repo, "workitem/x")
    for cmd in ("timeout 30 echo git commit", "sudo -u alice echo git commit", "command -v git commit", "command -V git commit",
                "sudo -l git commit", "sudo -v git commit", "sudo -K git commit", "timeout --help git commit",
                "nice --version git commit", 'echo "timeout 30 git commit"'):
        assert seen(cmd, repo) == "", cmd
    assert seen("sudo -l git switch main; git commit -m x", repo) == f"{repo}\t\n"


def test_c12_wrapper_alone(repo):
    for cmd in ("timeout 30", "env -u", "sudo -k"):
        assert seen(cmd, repo) == "", cmd


def test_c13_cd_behind_wrapper(repo):
    assert seen("timeout 30 cd sub && git commit -m x", repo) == f"{repo}\t\n"


def test_c14_regressions_and_other_rows(repo):
    empty_branch(repo, ["env FOO=1 git commit -m x", "sudo git commit -m x", "exec git commit -m x",
                        "command git commit -m x", "exec -a name git commit -m x"])


def test_c24_double_dash_edges(repo):
    _on(repo, "workitem/x")
    assert seen("git checkout main -- >/dev/null 2>&1 && git commit -m t", repo) == f"{repo}\tmain\n"
    assert seen("git checkout HEAD~0 -- && git commit -m t", repo) == f"{repo}\t?\n"
    assert seen("git checkout nosuch -- && git commit -m t", repo) == f"{repo}\t\n"


def test_c26_ci_and_changelog():
    with open(os.path.join(_ROOT, ".github/workflows/ci.yml")) as f:
        ci = f.read()
    line = next(l for l in ci.splitlines() if "uv run --project plugins/pd pytest" in l)
    assert "plugins/pd/hooks/lib/test_commit_target.py" in line
    with open(os.path.join(_ROOT, "CHANGELOG.md")) as f:
        changelog = f.read()
    unreleased = re.search(r"## \[Unreleased\](.*?)(?=\n## \[)", changelog, re.S).group(1)
    assert any("commit_target.py" in l and "wrapper" in l and "-c" in l for l in unreleased.splitlines())
