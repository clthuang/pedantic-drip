"""pd-read-budget.sh: the main-session read budget (shape.md ReadBudget)."""
import os
import shutil
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "pd-read-budget.sh"
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
CHECK_FAILED = "pd-read-budget: check failed; call allowed"


@pytest.fixture
def make_repo(tmp_path):
    def make(config=None):
        repo = tmp_path / "repo"
        shutil.rmtree(repo, ignore_errors=True)
        (repo / ".claude").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        if config is not None:
            (repo / ".claude" / "pd.local.md").write_text(f"---\n{config}\n---\n")
        return repo
    return make


@pytest.fixture
def reads_file(gate_home):
    return gate_home / ".claude" / "pd" / "gate" / "s1.reads"


def size(path):
    return path.stat().st_size if path.exists() else 0


def call(run_hook, repo, tool="Read", tool_input=None, env=None, **extra):
    payload = {"session_id": "s1", "cwd": str(repo), "hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": tool_input if tool_input is not None else {"file_path": str(repo / "src" / "a.py")}}
    payload.update(extra)
    return run_hook(HOOK, payload, env=env)


def assert_allowed(result):
    assert result == (0, "")


def assert_refused(result, *needles):
    code, err = result
    assert code == 2, (code, err)
    assert "check failed" not in err
    for n in needles:
        assert n in err


def test_c1_no_budget_allows_everything_and_writes_nothing(make_repo, run_hook, gate_home):
    for repo_config in (None, "tracker: none"):
        repo = make_repo(repo_config)
        for _ in range(10):
            assert_allowed(call(run_hook, repo))
        assert_allowed(call(run_hook, repo, "WebFetch", {"url": "https://x"}))
        assert os.listdir(gate_home / ".claude" / "pd" / "gate") == []


def test_c2b_budget_holds_when_the_gate_directory_does_not_exist_yet(make_repo, run_hook, gate_home):
    (gate_home / ".claude" / "pd" / "gate").rmdir()
    repo = make_repo("main_read_budget: 3")
    for _ in range(3):
        assert_allowed(call(run_hook, repo))
    assert_refused(call(run_hook, repo), "4 reads this turn (budget 3)")


def test_c2_fourth_read_is_refused(make_repo, run_hook, reads_file):
    repo = make_repo("main_read_budget: 3")
    for n in (1, 2, 3):
        assert_allowed(call(run_hook, repo))
        assert size(reads_file) == n
    assert_refused(call(run_hook, repo), "4 reads this turn (budget 3)", "pd:codebase-explorer")
    assert size(reads_file) == 4


@pytest.mark.parametrize("tool", ["WebFetch", "WebSearch"])
def test_c3_web_lookups_are_refused_at_once(make_repo, run_hook, reads_file, tool):
    repo = make_repo("main_read_budget: 3")
    assert_refused(call(run_hook, repo, tool, {"url": "https://x"}), "pd:internet-researcher")
    assert size(reads_file) == 0


def test_c4_subagent_calls_are_not_counted(make_repo, run_hook, reads_file):
    repo = make_repo("main_read_budget: 1")
    for _ in range(5):
        assert_allowed(call(run_hook, repo, agent_id="a1"))
    assert_allowed(call(run_hook, repo, "Grep", {"pattern": "x"}, agent_id="a1"))
    assert_allowed(call(run_hook, repo, "WebFetch", {"url": "https://x"}, agent_id="a1"))
    assert size(reads_file) == 0


def test_c5_artifacts_and_plugin_reads_are_free(make_repo, run_hook, reads_file):
    repo = make_repo("main_read_budget: 1")
    art = repo / "docs" / "dev_artifacts" / "workitems" / "x" / "shape.md"
    skill = PLUGIN_ROOT / "skills" / "a" / "SKILL.md"
    for path in [art] * 5 + [skill] * 5:
        assert_allowed(call(run_hook, repo, tool_input={"file_path": str(path)}))
    assert size(reads_file) == 0
    assert_allowed(call(run_hook, repo, tool_input={"file_path": str(repo / "src" / "a.py")}))
    assert size(reads_file) == 1


def test_c6_what_counts(make_repo, run_hook, reads_file):
    repo = make_repo("main_read_budget: 100")
    counted = [("Grep", {"pattern": "x"}), ("mcp__codegraph__codegraph_explore", {"query": "x"}),
               ("Bash", {"command": "git log | grep x"}), ("Bash", {"command": "/usr/bin/head f"})]
    counted += [("Bash", {"command": f"{w} f"}) for w in
                "cat head tail less more sed awk grep egrep fgrep rg find fd".split()]
    free = [("Glob", {"pattern": "*"}), ("Bash", {"command": "ls"}), ("Bash", {"command": "git status"}),
            ("Bash", {"command": 'bash -c "cat f"'}), ("Bash", {"command": "echo cat"})]
    before = 0
    for tool, tool_input in counted:
        assert_allowed(call(run_hook, repo, tool, tool_input))
        before += 1
        assert size(reads_file) == before, (tool, tool_input)
    for tool, tool_input in free:
        assert_allowed(call(run_hook, repo, tool, tool_input))
        assert size(reads_file) == before, (tool, tool_input)


def test_c7_user_prompt_resets_the_count(make_repo, run_hook, reads_file):
    repo = make_repo("main_read_budget: 1")
    assert_allowed(call(run_hook, repo))
    assert size(reads_file) == 1
    reset = run_hook(HOOK, {"session_id": "s1", "cwd": str(repo), "hook_event_name": "UserPromptSubmit"})
    assert reset == (0, "")
    assert size(reads_file) == 0
    assert_allowed(call(run_hook, repo))


def write_run_in_flight(repo, session):
    readme = repo / "docs" / "dev_artifacts" / "workitems" / "2026-11-26-x" / "README.md"
    readme.parent.mkdir(parents=True)
    readme.write_text(f"---\nid: 2026-11-26-x\n---\n# X\n\n## Now\n\nrun in flight: verify-change session {session}\n")


def test_c8_run_in_flight_stands_the_budget_down(make_repo, run_hook):
    repo = make_repo("main_read_budget: 1")
    write_run_in_flight(repo, "s1")
    for _ in range(5):
        assert_allowed(call(run_hook, repo))
    assert_allowed(call(run_hook, repo, "WebFetch", {"url": "https://x"}))


def test_c8_another_sessions_run_does_not(make_repo, run_hook):
    repo = make_repo("main_read_budget: 1")
    write_run_in_flight(repo, "s2")
    assert_allowed(call(run_hook, repo))
    assert_refused(call(run_hook, repo), "pd:codebase-explorer")
    assert_refused(call(run_hook, repo, "WebFetch", {"url": "https://x"}), "pd:internet-researcher")


def test_c9_bad_stdin_and_bad_budget_fail_open(make_repo, run_hook, reads_file, gate_home):
    repo = make_repo("main_read_budget: 3")
    r = subprocess.run(["bash", str(HOOK)], input="not json", capture_output=True, text=True,
                       env={**os.environ, "HOME": str(gate_home), "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)})
    assert (r.returncode, r.stderr.strip()) == (0, CHECK_FAILED)
    repo = make_repo("main_read_budget: abc")
    for _ in range(10):
        code, err = call(run_hook, repo)
        assert code == 0
        assert len(err.strip().splitlines()) == 1
    assert not reads_file.exists()


def test_c10_parallel_reads_all_count(make_repo, run_hook, reads_file):
    repo = make_repo("main_read_budget: 100")
    with ThreadPoolExecutor(20) as pool:
        results = list(pool.map(lambda _: call(run_hook, repo), range(20)))
    assert all(r == (0, "") for r in results)
    assert size(reads_file) == 20


def test_c11_agent_type_without_agent_id_is_the_main_session(make_repo, run_hook):
    repo = make_repo("main_read_budget: 1")
    assert_allowed(call(run_hook, repo, agent_type="pd:x"))
    assert_refused(call(run_hook, repo, agent_type="pd:x"), "2 reads this turn (budget 1)")


def test_c12_artifacts_root_comes_from_config(make_repo, run_hook, reads_file):
    repo = make_repo("main_read_budget: 1\nartifacts_root: notes/art")
    for _ in range(5):
        assert_allowed(call(run_hook, repo, tool_input={"file_path": str(repo / "notes" / "art" / "a.md")}))
    assert size(reads_file) == 0
    assert_allowed(call(run_hook, repo, tool_input={"file_path": str(repo / "docs" / "dev_artifacts" / "a.md")}))
    assert size(reads_file) == 1


def test_c13_broken_python_and_unwritable_state_fail_open(make_repo, run_hook, reads_file, tmp_path):
    repo = make_repo("main_read_budget: 1")
    fake = tmp_path / "fakebin"
    fake.mkdir()
    py = fake / "python3"
    py.write_text("#!/bin/sh\nexit 1\n")
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    for _ in range(3):
        code, err = call(run_hook, repo, env={"PATH": f"{fake}:{os.environ['PATH']}"})
        assert (code, err.strip()) == (0, CHECK_FAILED)
    reads_file.mkdir()
    code, err = call(run_hook, repo)
    assert (code, err.strip()) == (0, CHECK_FAILED)
