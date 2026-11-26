"""Tests for hook registration, CI and the docs (shape.md Test strategy "Cross-file invariants"; plan Task 12, cases C1 to C7)."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOOKS = json.loads((ROOT / "plugins/pd/hooks/hooks.json").read_text())["hooks"]
SELF_TESTED = ("pd-yolo", "pd-review-prompt", "pd-pr-checks")
READ_BUDGET_MATCHER = "Read|Grep|Bash|WebFetch|WebSearch|mcp__codegraph__codegraph_explore"


def text(relative):
    return (ROOT / relative).read_text()


def matchers_running(event, script):
    return {
        entry.get("matcher")
        for entry in HOOKS.get(event, [])
        if any(hook["command"] == f"${{CLAUDE_PLUGIN_ROOT}}/hooks/{script}" for hook in entry["hooks"])
    }


def names_word(content, name):
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", content) is not None


def table_rows(content):
    return [line for line in content.splitlines() if line.startswith("|")]


def test_c1_yolo_guard_registered_for_question_and_bash():
    assert {"AskUserQuestion", "Bash"} <= matchers_running("PreToolUse", "pd-yolo-guard.sh")


def test_c2_read_budget_registered_for_reads_and_prompts():
    assert READ_BUDGET_MATCHER in matchers_running("PreToolUse", "pd-read-budget.sh")
    assert matchers_running("UserPromptSubmit", "pd-read-budget.sh")


def test_c3_ci_runs_the_new_suites_and_self_tests():
    ci = text(".github/workflows/ci.yml")
    pytest_line = next(line for line in ci.splitlines() if "pytest" in line)
    for name in (
        "test_pd_common_stage.py", "test_pd_yolo.py", "test_pd_pr_checks.py", "test_severity_note.py",
        "test_pd_yolo_guard.py", "test_pd_read_budget.py", "test_pd_stop_gate_goals.py",
        "test_stage_new_status.py", "test_stage_lint_gate.py", "test_pd_review_prompt.py",
        "test_workflows_node.py", "test_yolo_prose.py", "test_registration_docs.py",
    ):
        assert name in pytest_line, name
    loop = next(line for line in ci.splitlines() if "--self-test" in line and "for s in" in line)
    for name in SELF_TESTED:
        assert names_word(loop, name), name


def test_c4_config_table_has_stage_and_read_budget_rows():
    rows = table_rows(text("docs/dev-guide/getting-started.md"))
    assert any(r.startswith("| `stage` | `production` |") for r in rows)
    assert any(r.startswith("| `main_read_budget` |") and "unset" in r.split("|")[2] for r in rows)


def test_c5_hook_and_script_docs_name_the_new_components():
    for doc in ("README_FOR_DEV.md", "docs/dev-guide/hook-development.md"):
        rows = " ".join(table_rows(text(doc)))
        for hook in ("pd-yolo-guard", "pd-read-budget"):
            assert names_word(rows, hook), (doc, hook)
    scripts_line = next(l for l in text("README_FOR_DEV.md").splitlines() if l.startswith("- **The scripts**"))
    loop = next(l for l in text("docs/dev-guide/commands-reference.md").splitlines() if l.startswith("for s in"))
    for name in SELF_TESTED:
        assert names_word(scripts_line, name), name
        assert names_word(loop, name), name
        for doc in ("docs/technical/architecture.md", "docs/technical/api-reference.md"):
            assert names_word(text(doc), name), (doc, name)
    registered = {hook["command"] for entries in HOOKS.values() for e in entries for hook in e["hooks"]}
    row = next(r for r in table_rows(text("plugins/pd/README.md")) if r.startswith("| Hooks |"))
    assert int(row.split("|")[2]) == len(registered)


def test_c6_readme_secretary_rows_document_yolo_and_stage():
    rows = " ".join(r for r in table_rows(text("README.md")) if "/pd:secretary" in r).replace("\\|", "|")  # table cells escape the pipe
    assert "--yolo" in rows
    assert "--stage mvp|production" in rows


def test_c7_drift_validate_and_hook_suites_pass():
    for command in (
        "scripts/check-doc-drift.sh", "./validate.sh",
        "plugins/pd/hooks/tests/test-hooks.sh", "plugins/pd/hooks/tests/test-pd-stop-gate.sh",
    ):
        run = subprocess.run(["bash", command], cwd=ROOT, capture_output=True, text=True)
        assert run.returncode == 0, (command, run.stdout[-800:], run.stderr[-800:])
