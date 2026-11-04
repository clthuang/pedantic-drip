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
    # scripts/release-pr.sh:36 keeps the first `## [Unreleased]` line, then an empty line and the new version's heading
    released, done = [], False
    for l in changelog.split("\n"):
        released.append(l)
        if not done and l.startswith("## [Unreleased]"):
            released += ["", "## [9.9.9] - 2026-01-01"]
            done = True
    assert done
    for text in (changelog, "\n".join(released)):
        assert any("commit_target.py" in l and "wrapper" in l and "-c" in l for l in text.splitlines())


# ---- Task 2: `-c` scripts, nested at any depth ----

import ast
import shlex

_PD_NEW = os.path.join(os.path.dirname(_HOOKS), "scripts", "pd-new")


@pytest.fixture
def pd_repo(tmp_path):
    """An adopted layout with one work item made by pd-new, committed (as test-pd-commit-lint.sh builds it)."""
    path = tmp_path / "pd repo"
    (path / ".claude").mkdir(parents=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    _git(path, "config", "commit.gpgsign", "false")
    (path / ".claude" / "pd.local.md").write_text("---\nartifacts_root: docs/dev_artifacts\nsop: 1\n---\n")
    subprocess.run([_PD_NEW, "workitem", "Parse the input"], cwd=path, check=True, capture_output=True, env=_ENV)
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "base")
    return str(path.resolve())


def test_c15_shell_forms(repo):
    forms = ["bash -c", "sh -c", "zsh -lc", "/bin/bash -c", "bash -o pipefail -c", "bash -eo pipefail -c",
             "dash -c", "ksh -c", "bash +O extglob -c", "bash --norc -c"]
    empty_branch(repo, [f"{f} 'git commit -m x'" for f in forms])
    assert seen("bash -c 'cd sub; git commit -m x'", repo) == f"{repo}/sub\t\n"


def test_c16_cd_in_script(repo):
    assert seen("bash -c 'cd sub && git commit -m x'", repo) == f"{repo}/sub\t\n"
    assert seen("bash -c 'cd sub'; git commit -m x", repo) == f"{repo}\t\n"


def test_c17_switch_in_script(repo):
    _on(repo, "workitem/x")
    for cmd in ("bash -c 'git switch main && git commit -m x'", "bash -c 'git switch main'; git commit -m x"):
        assert seen(cmd, repo) == f"{repo}\tmain\n", cmd


def _nested(levels):
    cmd = "git commit -m x"
    for _ in range(levels):
        cmd = "bash -c " + shlex.quote(cmd)
    return cmd


def test_c18_wrappers_and_depth(repo):
    empty_branch(repo, ["timeout 30 bash -c 'git commit -m x'", "bash -c 'timeout 30 git commit -m x'",
                        "bash -c \"sh -c 'git commit -m x'\"", _nested(10)])


def test_c19_directory_option_reaches_script(repo):
    assert seen("env -C sub bash -c 'git commit -m x'", repo) == f"{repo}/sub\t\n"


def test_c20_lint_through_script(pd_repo):
    log = next(p for p in (os.path.join(r, f) for r, _, fs in os.walk(os.path.join(pd_repo, "docs")) for f in fs) if p.endswith("/log.md"))
    with open(log, "a") as f:
        f.write("\n## 2026-11-03 10:00+08:00 bogus\n")
    _git(pd_repo, "add", "-A")
    _, err, code = hook("pd-commit-lint.sh", "bash -c 'git commit -m x'", pd_repo)
    assert code == 2
    assert "entry kind bogus" in err


def test_c21_not_commits(repo):
    for cmd in ("bash -c 'echo \"git commit\"'", "bash ./commit.sh", "fish -c 'git commit -m x'",
                "bash -c $'# git commit\ntrue'", "bash -c $'cat <<EOF\ngit commit -m x\nEOF'"):
        assert seen(cmd, repo) == "", cmd


def test_empty_shell_argument_keeps_later_commit(repo):
    for cmd in ("bash -c ''; git commit -m x", 'bash ""; git commit -m x'):
        assert seen(cmd, repo) == f"{repo}\t\n", cmd
    assert seen("bash '' -c 'git commit -m x'", repo) == ""  # the empty word is the script file; `-c` comes too late


def test_wrapper_option_without_value_stops_at_separator(repo):
    for cmd in ("env -C sub -u ; git commit -m x", "sudo -D sub -u ; git commit -m x"):
        assert seen(cmd, repo) == f"{repo}\t\n", cmd


def test_ansi_c_quoted_script_is_seen(repo):
    assert seen("bash -c $'git commit -m x'", repo) == f"{repo}\t\n"


def test_c22_degenerate_scripts(repo):
    assert seen("bash -c", repo) == ""
    assert seen("bash -c 'echo \"unclosed'; git commit -m x", repo) == f"{repo}\t\n"


def test_c23_existing_hook_tests_pass():
    for script in ("test-hooks.sh", "test-pd-commit-lint.sh"):
        r = subprocess.run(["bash", os.path.join(_HOOKS, "tests", script)], cwd=_ROOT, capture_output=True, text=True, env=_ENV)
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    with open(os.path.join(_HOOKS, "tests", "test-hooks.sh")) as f:
        text = f.read()
    for literal in ("\"main|grep -n 'git commit' README.md|no\"",
                    "\"main|\"$'cat > n.md <<\\'EOF\\'\\nstep; git commit -m x\\nEOF'\"|no\"",
                    "\"workitem/x|printf '%s\\\\n' ';' git switch main ';' git commit|no\""):
        assert literal in text, literal


# Task 3 inputs: the shell spelling of `$'…'` escapes, never Python escapes.
_C29_SWITCH = r"bash -c $'git switch main\ngit commit -m x'"
_C29_SEEN_ON_MAIN = [r"bash -c $'git commit\t-m x'", r"bash -c $'\x67it commit -m x'", r"bash -c $'\147it commit -m x'",
                     r"bash -c $'git commit -m \'x\''", r"bash -c $'true\x3b git commit -m x'"]
_C29_NOT_SEEN = [r"bash -c $'echo \'git commit\''", r"echo $'a\ngit commit -m x'", r"echo $'\x3b' git commit -m x",
                 r"echo $'\x26\x7c\x28\x29' git commit -m x"]
_C30_SEEN = ["bash +c 'git commit -m x'", "bash +ec 'git commit -m x'"]
_C30_NOT_SEEN = ["bash +x 'git commit -m x'"]
_C32_SEEN = ['bash -c $"git commit -m x"']

# C25: the subprocess calls, traced at run time through an audit hook.
_DRIVER = """
import json, os, runpy, sys
trace, script = os.environ["TRACE_FILE"], sys.argv[1]
FORBIDDEN = ("os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork")
def audit(event, args):
    if event == "subprocess.Popen":
        line = {"popen": list(args[1])}
    elif event.startswith(FORBIDDEN):
        line = {"forbidden": event}
    else:
        return
    with open(trace, "a") as f:
        f.write(json.dumps(line) + "\\n")
sys.addaudithook(audit)
sys.argv = [script]
runpy.run_path(script, run_name="__main__")
"""


def _traced_cases(repo):
    """(command, branch to be on, expected Popen argument lists) for every `seen` command of C1 to C24."""
    root = ["git", "-C", repo, "rev-parse", "--show-toplevel"]
    show = lambda b: ["git", "-C", repo, "show-ref", "--verify", "--quiet", f"refs/heads/{b}"]
    commit = lambda b: ["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"{b}^{{commit}}"]
    on_main = (["timeout 30 git commit -m x", "timeout -s KILL -k 5 30 git commit -m x",
                "timeout --signal=KILL --kill-after 5 30 git commit -m x"]
               + [f"sudo {o} git commit -m x" for o in ("-u alice", "-ualice", "-Eu alice", "-E -H", "--", "--user alice", "-k")]
               + ["env -u FOO git commit -m x", "env --unset FOO git commit -m x", "env -i PATH=/usr/bin git commit -m x"]
               + [f"{w} git commit -m x" for w in ("nice -n 5", "nice --adjustment 5", "stdbuf -oL", "stdbuf --output L",
                                                   "time -p", "time --format %e", "nohup", "xargs --max-args 1")]
               + ["xargs -I{} git commit -m {}", "sudo -u alice timeout 30 git commit -m x",
                  "sudo -D sub git commit -m x", "sudo --chdir sub git commit -m x", "env -C sub git commit -m x",
                  "env --chdir sub git commit -m x", "env -C sub true; git commit -m x",
                  "timeout 30 cd sub && git commit -m x",
                  "env FOO=1 git commit -m x", "sudo git commit -m x", "exec git commit -m x", "command git commit -m x",
                  "exec -a name git commit -m x"]
               + [f"{f} 'git commit -m x'" for f in ("bash -c", "sh -c", "zsh -lc", "/bin/bash -c", "bash -o pipefail -c",
                                                     "bash -eo pipefail -c", "dash -c", "ksh -c", "bash +O extglob -c", "bash --norc -c")]
               + ["bash -c 'cd sub; git commit -m x'", "bash -c 'cd sub && git commit -m x'", "bash -c 'cd sub'; git commit -m x",
                  "timeout 30 bash -c 'git commit -m x'", "bash -c 'timeout 30 git commit -m x'",
                  "bash -c \"sh -c 'git commit -m x'\"", _nested(10), "env -C sub bash -c 'git commit -m x'",
                  "bash -c 'echo \"unclosed'; git commit -m x", "sudo -l git switch main; git commit -m x"]
               + _C29_SEEN_ON_MAIN + _C30_SEEN + _C32_SEEN)
    cases = [(c, "main", []) for c in on_main]
    cases.append(("git checkout main -- README.md && git commit -m t", "workitem/x", []))
    switch_cmds = ["timeout 30 git switch main && git commit -m x", "bash -c 'git switch main && git commit -m x'",
                   "bash -c 'git switch main'; git commit -m x"]
    switch_cmds.append(_C29_SWITCH)
    cases += [(c, "workitem/x", [root, root]) for c in switch_cmds]
    checkout_cmds = ["timeout 30 git checkout main && git commit -m x", "git checkout main -- && git commit -m t",
                     "git checkout main -- >/dev/null 2>&1 && git commit -m t"]
    cases += [(c, "workitem/x", [show("main"), root, root]) for c in checkout_cmds]
    cases.append(("git checkout HEAD~0 -- && git commit -m t", "workitem/x", [show("HEAD~0"), commit("HEAD~0"), root, root]))
    cases.append(("git checkout nosuch -- && git commit -m t", "workitem/x", [show("nosuch"), commit("nosuch")]))
    return cases


def _traced_negatives():
    """(command, branch) for every `seen` command of C1 to C24 that prints nothing: none may run a subprocess."""
    cmds = ["timeout 30 echo git commit", "sudo -u alice echo git commit", "command -v git commit", "command -V git commit",
            "sudo -l git commit", "sudo -v git commit", "sudo -K git commit", "timeout --help git commit",
            "nice --version git commit", 'echo "timeout 30 git commit"', "timeout 30", "env -u", "sudo -k",
            "bash -c 'echo \"git commit\"'", "bash ./commit.sh", "fish -c 'git commit -m x'",
            "bash -c $'# git commit\ntrue'", "bash -c $'cat <<EOF\ngit commit -m x\nEOF'", "bash -c"]
    cmds += _C29_NOT_SEEN + _C30_NOT_SEEN
    return [(c, "workitem/x", []) for c in cmds]


def _trace_mismatches(script, repo, cases, trace_dir, empty_ok=False):
    """Run `script` under the audit driver for each case; the (command, got, want, stdout, stderr) of every mismatch.
    The trace file lives in `trace_dir`, never beside the script."""
    bad = []
    trace = os.path.join(str(trace_dir), "trace.jsonl")
    for cmd, branch, expected in cases:
        _on(repo, branch)
        if os.path.exists(trace):
            os.remove(trace)
        r = subprocess.run(["python3", "-c", _DRIVER, script], input=json.dumps({"tool_input": {"command": cmd}, "cwd": repo}),
                           capture_output=True, text=True, env={**_ENV, "TRACE_FILE": trace})
        got = []
        if os.path.exists(trace):
            with open(trace) as f:
                got = [json.loads(l) for l in f]
        want = [{"popen": e} for e in expected]
        if r.returncode != 0 or r.stderr or (not r.stdout and not empty_ok) or (r.stdout and empty_ok) or got != want:
            bad.append((cmd, got, want, r.stdout, r.stderr))
    return bad


def test_c25_only_git_queries_run(repo, tmp_path):
    assert _trace_mismatches(_SCRIPT, repo, _traced_cases(repo), tmp_path) == []


def test_c25_no_subprocess_for_non_commits(repo, tmp_path):
    negatives = _traced_negatives()
    assert len(negatives) == 19 + len(_C29_NOT_SEEN) + len(_C30_NOT_SEEN)
    assert _trace_mismatches(_SCRIPT, repo, negatives, tmp_path, empty_ok=True) == []


def test_c25_leaves_no_trace_in_source_tree(repo, tmp_path):
    leftover = os.path.join(_LIB, "trace.jsonl")
    assert not os.path.exists(leftover)
    spawning = [c for c in _traced_cases(repo) if c[0] == "git checkout nosuch -- && git commit -m t"]
    assert len(spawning) == 1 and spawning[0][2]  # a case that runs git, so the audit hook writes a trace
    assert _trace_mismatches(_SCRIPT, repo, spawning, tmp_path) == []
    assert os.path.exists(tmp_path / "trace.jsonl")
    assert not os.path.exists(leftover)


def test_c25_negative_controls(repo, tmp_path):
    with open(_SCRIPT) as f:
        source = f.read()
    run_line = '    r = subprocess.run(["git", "-C", at, "rev-parse", "--show-toplevel"], capture_output=True, text=True)\n'
    controls = {"extra call in main": source.replace("def main():\n", 'def main():\n    subprocess.check_output(["true"])\n', 1),
                "repo_of runs twice": source.replace(run_line, run_line * 2, 1)}
    switch_case = [c for c in _traced_cases(repo) if c[0] == "timeout 30 git switch main && git commit -m x"]
    assert len(switch_case) == 1
    for name, text in controls.items():
        assert text != source, name
        copy_dir = tmp_path / name.replace(" ", "_")
        copy_dir.mkdir()
        copy = copy_dir / "commit_target.py"
        copy.write_text(text)
        assert _trace_mismatches(str(copy), repo, switch_case, copy_dir), name


# C27: the imports and subprocess calls, read statically.
_ALLOWED_IMPORTS = {"itertools", "json", "os", "re", "shlex", "subprocess", "sys"}
_FORBIDDEN_OS = ("system", "popen", "exec", "spawn", "posix_spawn", "fork")


def _is_git_list(node):
    return isinstance(node, ast.List) and bool(node.elts) and isinstance(node.elts[0], ast.Constant) and node.elts[0].value == "git"


def _is_subprocess_run(call):
    f = call.func
    return isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "subprocess" and f.attr == "run"


def _static_violations(source):
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if a.name.split(".")[0] not in _ALLOWED_IMPORTS]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] not in _ALLOWED_IMPORTS:
            found.append(f"from {node.module} import")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "subprocess" and node.attr != "run":
                found.append(f"subprocess.{node.attr}")
            if node.value.id == "os" and node.attr.startswith(_FORBIDDEN_OS):
                found.append(f"os.{node.attr}")
    run_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _is_subprocess_run(n)]
    if len(run_calls) != 3:
        found.append(f"{len(run_calls)} subprocess.run call sites, not 3")
    for func in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        git_lists = {t.id for n in ast.walk(func) if isinstance(n, ast.Assign) and _is_git_list(n.value)
                     for t in n.targets if isinstance(t, ast.Name)}
        for call in (n for n in ast.walk(func) if isinstance(n, ast.Call) and _is_subprocess_run(n)):
            first = call.args[0] if call.args else None
            if not (_is_git_list(first) or (isinstance(first, ast.BinOp) and isinstance(first.op, ast.Add)
                                            and isinstance(first.left, ast.Name) and first.left.id in git_lists)):
                found.append(f"subprocess.run at line {call.lineno} does not start with a git list")
    return found


def test_c27_static_subprocess_audit():
    with open(_SCRIPT) as f:
        source = f.read()
    assert _static_violations(source) == []
    for extra in ("os.fork()", "import multiprocessing", 'subprocess.Popen(["true"])'):
        assert _static_violations(source + "\n" + extra + "\n"), extra


# ---- Task 3: Verify's fixes ----

def test_c29_ansi_c_decoding(repo):
    _on(repo, "workitem/x")
    assert seen(_C29_SWITCH, repo) == f"{repo}\tmain\n"
    _on(repo, "main")
    for cmd in _C29_SEEN_ON_MAIN:
        assert seen(cmd, repo) == f"{repo}\t\n", cmd
    for cmd in _C29_NOT_SEEN + [r"bash -c $'# git commit\ntrue'", r"bash -c $'cat <<EOF\ngit commit -m x\nEOF'"]:
        assert seen(cmd, repo) == "", cmd


def test_c30_plus_c(repo):
    for cmd in _C30_SEEN:
        assert seen(cmd, repo) == f"{repo}\t\n", cmd
    for cmd in _C30_NOT_SEEN:
        assert seen(cmd, repo) == "", cmd


def test_c32_dollar_double_quote(repo):
    assert seen(_C32_SEEN[0], repo) == f"{repo}\t\n"


_LIMITED = """
import itertools, json, os, re, shlex, subprocess, runpy, pkgutil, sys
sys.setrecursionlimit(int(sys.argv[2]))
runpy.run_path(sys.argv[1], run_name="__main__")
"""


def test_c31_recursion_limit_skips_deep_script(repo):
    def run(cmd, limit):
        argv = ["python3", "-c", _LIMITED, _SCRIPT, str(limit)]
        return subprocess.run(argv, input=json.dumps({"tool_input": {"command": cmd}, "cwd": repo}),
                              capture_output=True, text=True, env=_ENV)
    deep = _nested(10)
    assert seen(deep, repo) == f"{repo}\t\n"
    n = next((n for n in range(10, 301) if (r := run(deep, n)).returncode == 0 and r.stdout == "" and r.stderr == ""), None)
    assert n is not None
    r = run(deep + "; git commit -m x", n)
    assert (r.returncode, r.stdout, r.stderr) == (0, f"{repo}\t\n", "")
