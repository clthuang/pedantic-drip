"""Tests for the pd-worktrees callers and docs (shape.md ## Design; plan Task 3, cases C32 to C36)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IMPLEMENTING = ROOT / "plugins/pd/skills/implementing/SKILL.md"
FINISHING = ROOT / "plugins/pd/skills/finishing-branch/SKILL.md"
ABANDON = ROOT / "plugins/pd/commands/abandon-workitem.md"
REMOVE = "pd-worktrees <id> --remove"


def step(path, number):
    """The span from line `number. **` to the next numbered line of the list (or a heading, or the end)."""
    lines = path.read_text().split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{number}. **"))
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"\d+\. \*\*", lines[i]) or lines[i].startswith("#")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def wrong_test_bullet():
    span = step(IMPLEMENTING, 6)
    lines = span.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("   - **a task `wrong-test`**"))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("   - **")), len(lines))
    return "\n".join(lines[start:end])


def in_order(text, *needles):
    positions = []
    for needle in needles:
        assert needle in text, needle
        positions.append(text.index(needle))
    assert positions == sorted(positions), needles


def has_all(text, *needles):
    for needle in needles:
        assert needle in text, needle


def test_c32_implementing_step_5_clears_worktrees_after_the_run():
    span = step(IMPLEMENTING, 5)
    in_order(span, "Clear `run in flight:`", REMOVE)
    has_all(
        span,
        "whatever stopped the run",
        "AskUserQuestion",
        "dirty",
        "clean",
        "git worktree remove --force <path>",
        "discard",
        "Execute deletes no branch",
        "locked",
        "main checkout",
        "reported",
        "no question",
        "stops the caller",
        "not deleted",
        "exit 2",
        "hard stop",
        "before step 6",
    )


def test_c33_wrong_test_bullet_removes_by_task_before_branch_delete():
    bullet = wrong_test_bullet()
    in_order(bullet, "pd-worktrees <id> --remove --task <n>", "git branch -D pd/<id>/task-<n>")
    has_all(bullet, "stops the move", "`discard`", "`stop the move`")
    assert "--force" not in bullet


def test_c34_finishing_step_9_uses_pd_worktrees_before_branch_delete():
    span = step(FINISHING, 9)
    in_order(span, REMOVE, "git branch -d")
    has_all(span, "`implementing` step 5", "exit 1", "pd/<id>/task-*", "left out", "exit 2", "hard stop")
    in_order(span, "exit 2", "hard stop", "git branch -d")
    assert "git worktree remove" not in span.replace(REMOVE, "")


def test_c35_abandon_step_3_uses_pd_worktrees_before_switching_off():
    span = step(ABANDON, 3)
    in_order(span, REMOVE, "switch off", "git branch -D")
    has_all(span, "accepts", "on the work item's branch", "`implementing` step 5", "exit 1", "pd/<id>/task-*", "left out", "exit 2", "hard stop")
    in_order(span, "accepts", REMOVE)
    in_order(span, "exit 2", "hard stop", "git branch -D")


def test_c36_docs_name_pd_worktrees():
    dev = (ROOT / "README_FOR_DEV.md").read_text()
    scripts_line = next(l for l in dev.split("\n") if "`pd-review-filter`" in l and "scripts" in l)
    assert "pd-worktrees" in scripts_line
    computed_line = next(l for l in dev.split("\n") if l.startswith("- **Everything else is computed**"))
    assert "leftover worktrees" in computed_line

    api = (ROOT / "docs/technical/api-reference.md").read_text()
    sections = re.split(r"^## ", api, flags=re.M)
    worktrees = next(s for s in sections if s.startswith("pd-worktrees"))
    has_all(worktrees, "pd-worktrees <id>", "pd-worktrees --strays", "0", "1", "2")
    status = next(s for s in sections if s.startswith("pd-status"))
    has_all(status, "Leftover worktrees", "live git state")

    arch = (ROOT / "docs/technical/architecture.md").read_text()
    pd_common_line = next(l for l in arch.split("\n") if l.startswith("- **`scripts/pd_common.py`**"))
    has_all(pd_common_line, "worktrees", "run_in_flight")

    commands = (ROOT / "docs/dev-guide/commands-reference.md").read_text()
    pytest_line = next(l for l in commands.split("\n") if "pytest -q plugins/pd/hooks" in l)
    assert "plugins/pd/scripts" in pytest_line
    loop = next(l for l in commands.split("\n") if l.startswith("for s in pd-lint"))
    assert "pd-worktrees" not in loop
