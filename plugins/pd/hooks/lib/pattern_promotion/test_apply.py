"""Tests for the apply orchestrator (Stages 1-4).

Covers:
  Task 3.1 / 3.2 happy path (Stages 1-4):
    - Stage 1 pre-flight: existence, JSON validity, TD-8 collision
    - Stage 2: snapshot
    - Stage 3: write in write_order
    - Stage 4: re-parse validation for hooks.json
    - stage-boundary log lines to stderr
  Task 3.3 / 3.4 rollback (6 cases):
    - File write failure mid-batch
    - JSON validation failure on hooks.json
    - Post-write file missing
    - TD-8 collision detected at Stage 1 -> no changes applied
    - Disk space / IOError during write
    - Baseline-run-failure (post-write validation fails)
  Task 3.5 hook-target test script execution (4 cases):
    - positive+negative both pass -> success
    - positive fails -> rollback
    - negative fails -> rollback
    - timeout -> rollback

Stage 5 (KB marker append) is NOT covered here — that is the `mark` CLI
subcommand (Task 3.6).
"""
from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from pathlib import Path
from unittest import mock

import pytest

# Ensure sibling imports work when pytest runs from repo root without PYTHONPATH.
_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from pattern_promotion.apply import apply  # noqa: E402
from pattern_promotion.kb_parser import KBEntry  # noqa: E402
from pattern_promotion.types import DiffPlan, FileEdit  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_entry(name: str = "Test Entry") -> KBEntry:
    return KBEntry(
        name=name,
        description="desc",
        confidence="high",
        effective_observation_count=3,
        category="patterns",
        file_path=Path("/tmp/fake.md"),
        line_range=(1, 5),
    )


def _make_skill_plan(tmp_path: Path, entry_name: str = "Test Entry") -> DiffPlan:
    """Single-file modify plan (skill-style)."""
    target = tmp_path / "SKILL.md"
    original = "# Skill\n\n## Rules\n- existing rule\n"
    target.write_text(original)
    new_text = (
        "# Skill\n\n## Rules\n- existing rule\n"
        f"<!-- Promoted: {entry_name} -->\n- new rule\n"
    )
    return DiffPlan(
        edits=[
            FileEdit(
                path=target,
                action="modify",
                before=original,
                after=new_text,
                write_order=0,
            )
        ],
        target_type="skill",
        target_path=target,
    )


def _make_hook_plan(
    tmp_path: Path,
    entry_name: str = "Test Hook",
    positive_blocks: bool = True,
    negative_allows: bool = True,
    hang: bool = False,
) -> DiffPlan:
    """3-edit hook plan: .sh + test-.sh + hooks.json (create/create/modify)."""
    hooks_dir = tmp_path / "hooks"
    tests_dir = hooks_dir / "tests"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    hooks_json_path = hooks_dir / "hooks.json"
    original_json = json.dumps({"hooks": {}}, indent=2) + "\n"
    hooks_json_path.write_text(original_json)

    sh_path = hooks_dir / "test-hook.sh"
    test_path = tests_dir / "test-test-hook.sh"

    # Hook body: honor positive_blocks / negative_allows deterministically.
    # Uses stdin JSON {"verdict": "block"|"allow"}.
    hook_body = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        # Promoted from KB entry: {entry_name}
        set -eu
        INPUT=$(cat)
        if echo "$INPUT" | grep -q '"verdict":"block"'; then
          exit {"2" if positive_blocks else "0"}
        fi
        exit {"0" if negative_allows else "2"}
        """
    )

    # Test script: deterministic positive/negative verdicts.
    if hang:
        test_body = textwrap.dedent(
            """\
            #!/usr/bin/env bash
            sleep 600
            """
        )
    else:
        test_body = textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -u
            SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
            HOOK="$SCRIPT_DIR/../{sh_path.name}"
            fail=0
            if echo '{{"verdict":"block"}}' | bash "$HOOK" >/dev/null 2>&1; then
              echo "FAIL positive" >&2
              fail=1
            fi
            if ! echo '{{"verdict":"allow"}}' | bash "$HOOK" >/dev/null 2>&1; then
              echo "FAIL negative" >&2
              fail=1
            fi
            exit $fail
            """
        )

    patched_json = (
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Edit",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": str(sh_path),
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n"
    )

    return DiffPlan(
        edits=[
            FileEdit(
                path=sh_path,
                action="create",
                before=None,
                after=hook_body,
                write_order=0,
            ),
            FileEdit(
                path=test_path,
                action="create",
                before=None,
                after=test_body,
                write_order=1,
            ),
            FileEdit(
                path=hooks_json_path,
                action="modify",
                before=original_json,
                after=patched_json,
                write_order=2,
            ),
        ],
        target_type="hook",
        target_path=sh_path,
    )


# ---------------------------------------------------------------------------
# Task 3.1 / 3.2 — Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_skill_target_applies_and_succeeds(self, tmp_path, capfd):
        entry = _make_entry()
        plan = _make_skill_plan(tmp_path)
        result = apply(entry, plan, target_type="skill")
        assert result.success is True
        assert result.rolled_back is False
        assert result.stage_completed == 4
        assert plan.edits[0].after == plan.edits[0].path.read_text()

    def test_hook_target_applies_all_three_edits(self, tmp_path):
        entry = _make_entry("Test Hook")
        plan = _make_hook_plan(tmp_path)
        result = apply(entry, plan, target_type="hook")
        assert result.success is True
        assert result.rolled_back is False
        for edit in plan.edits:
            assert edit.path.exists(), edit.path
        # hooks.json must parse after write
        json.loads(plan.edits[2].path.read_text())

    def test_stage_one_rejects_missing_modify_target(self, tmp_path):
        entry = _make_entry()
        target = tmp_path / "absent.md"  # does NOT exist
        plan = DiffPlan(
            edits=[
                FileEdit(
                    path=target,
                    action="modify",
                    before="x",
                    after="y",
                    write_order=0,
                )
            ],
            target_type="skill",
            target_path=target,
        )
        result = apply(entry, plan, target_type="skill")
        assert result.success is False
        assert result.stage_completed == 1
        assert result.rolled_back is False  # nothing written
        assert not target.exists()
        assert result.reason and "exist" in result.reason.lower()

    def test_stage_one_rejects_existing_create_target(self, tmp_path):
        entry = _make_entry()
        target = tmp_path / "already.sh"
        target.write_text("# preexisting\n")
        plan = DiffPlan(
            edits=[
                FileEdit(
                    path=target,
                    action="create",
                    before=None,
                    after="new\n",
                    write_order=0,
                )
            ],
            target_type="hook",
            target_path=target,
        )
        result = apply(entry, plan, target_type="hook")
        assert result.success is False
        assert result.stage_completed == 1
        assert target.read_text() == "# preexisting\n"  # untouched

    def test_stage_one_rejects_invalid_patched_hooks_json(self, tmp_path):
        entry = _make_entry("Bad JSON")
        plan = _make_hook_plan(tmp_path, entry_name="Bad JSON")
        # Replace the hooks.json edit's `after` with invalid JSON.
        bad_edit = plan.edits[2]
        plan.edits[2] = FileEdit(
            path=bad_edit.path,
            action=bad_edit.action,
            before=bad_edit.before,
            after="{not valid json",
            write_order=bad_edit.write_order,
        )
        result = apply(entry, plan, target_type="hook")
        assert result.success is False
        assert result.stage_completed == 1
        # Nothing should have been written.
        assert not plan.edits[0].path.exists()
        assert not plan.edits[1].path.exists()
        # hooks.json content unchanged (still the original stub).
        assert json.loads(plan.edits[2].path.read_text()) == {"hooks": {}}

    def test_stage_one_td8_collision_detection_aborts(self, tmp_path):
        """Pre-existing file in the hooks dir carries the TD-8 marker for
        the same entry name -> abort."""
        entry = _make_entry("Duplicate Entry")
        plan = _make_hook_plan(tmp_path, entry_name="Duplicate Entry")
        # Seed a stale hook in the hooks dir with the same TD-8 marker.
        hooks_dir = plan.edits[0].path.parent
        stale = hooks_dir / "stale-prior-run.sh"
        stale.write_text(
            "#!/usr/bin/env bash\n"
            "# Promoted from KB entry: Duplicate Entry\n"
            "echo stale\n"
        )
        # also add a file touching the new slug location is not needed
        # (collision detection runs on entry name)
        result = apply(entry, plan, target_type="hook")
        assert result.success is False
        assert result.stage_completed == 1
        assert result.reason is not None
        assert "partial" in result.reason.lower() or "collision" in result.reason.lower()
        # .sh was never created (stale was pre-existing and should remain)
        assert stale.exists()
        assert not plan.edits[0].path.exists()

    def test_stage_logs_emitted_to_stderr(self, tmp_path, capfd):
        entry = _make_entry()
        plan = _make_skill_plan(tmp_path)
        apply(entry, plan, target_type="skill")
        err = capfd.readouterr().err
        assert "Stage 1" in err
        assert "Stage 2" in err
        assert "Stage 3" in err
        assert "Stage 4" in err


# ---------------------------------------------------------------------------
# Task 3.3 / 3.4 — Rollback scenarios (6)
# ---------------------------------------------------------------------------


class TestRollback:
    def test_write_failure_midbatch_restores_snapshots(self, tmp_path):
        """Mid-batch write failure restores all earlier writes."""
        entry = _make_entry()
        # 2-file plan: first succeeds (create), second fails (read-only dir).
        file_a = tmp_path / "a.sh"
        ro_dir = tmp_path / "ro_dir"
        ro_dir.mkdir()
        file_b = ro_dir / "b.sh"
        os.chmod(ro_dir, stat.S_IRUSR | stat.S_IXUSR)  # remove write perm
        try:
            plan = DiffPlan(
                edits=[
                    FileEdit(
                        path=file_a,
                        action="create",
                        before=None,
                        after="A\n",
                        write_order=0,
                    ),
                    FileEdit(
                        path=file_b,
                        action="create",
                        before=None,
                        after="B\n",
                        write_order=1,
                    ),
                ],
                target_type="hook",
                target_path=file_a,
            )
            result = apply(entry, plan, target_type="hook")
        finally:
            os.chmod(ro_dir, stat.S_IRWXU)
        assert result.success is False
        assert result.rolled_back is True
        assert not file_a.exists(), "first create should have been rolled back"
        assert not file_b.exists()
        assert result.stage_completed == 3

    def test_postwrite_hooksjson_invalid_triggers_rollback(self, tmp_path):
        """Stage 4 re-parse: force hooks.json to become invalid AFTER write
        (simulated by corrupting content with a side-effect in apply's Stage 4
        validation). We simulate by patching json.loads used during Stage 4."""
        entry = _make_entry("PW JSON")
        plan = _make_hook_plan(tmp_path, entry_name="PW JSON")
        # Capture original contents of hooks.json for rollback check.
        original_json = plan.edits[2].path.read_text()
        sh_path = plan.edits[0].path
        # Patch stage-4 json.loads (in apply module) to simulate a post-write
        # parse failure only for the hooks.json path.
        import pattern_promotion.apply as apply_mod
        real_loads = apply_mod.json.loads
        hooks_json_path = plan.edits[2].path

        def flaky_loads(text, *a, **kw):
            # Simulate corruption: raise only during Stage 4 re-parse.
            # apply_mod sets a module-level flag `_in_stage4` we can inspect;
            # but to avoid coupling, just raise on any input equal to the
            # patched hooks.json content during stage 4. Since stage 1 parses
            # the same content, we use a counter: trip after the first call.
            flaky_loads.calls += 1
            if flaky_loads.calls >= 2:
                raise ValueError("simulated stage-4 post-write parse failure")
            return real_loads(text, *a, **kw)
        flaky_loads.calls = 0
        with mock.patch.object(apply_mod.json, "loads", side_effect=flaky_loads):
            result = apply(entry, plan, target_type="hook")
        assert result.success is False
        assert result.rolled_back is True
        # .sh and test-.sh were created then unlinked
        assert not sh_path.exists()
        assert not plan.edits[1].path.exists()
        # hooks.json restored to original content
        assert plan.edits[2].path.read_text() == original_json

    def test_postwrite_file_missing_triggers_rollback(self, tmp_path):
        """Simulate a write that silently drops a file (e.g. antivirus quarantine).
        We delete the file between Stage 3 and Stage 4 via a post-write hook."""
        entry = _make_entry()
        plan = _make_skill_plan(tmp_path)
        target = plan.edits[0].path
        original_before = plan.edits[0].before
        import pattern_promotion.apply as apply_mod
        real_validate = apply_mod._stage4_validate

        def pw(diff_plan, target_type):
            # Remove the written file to simulate missing post-write.
            if target.exists():
                target.unlink()
            return real_validate(diff_plan, target_type)

        with mock.patch.object(apply_mod, "_stage4_validate", side_effect=pw):
            result = apply(entry, plan, target_type="skill")
        assert result.success is False
        assert result.rolled_back is True
        # Rollback for a modify restores original content.
        assert target.read_text() == original_before

    def test_td8_collision_results_in_zero_writes(self, tmp_path):
        """Duplicate of stage-one test, but asserted from the rollback contract:
        NO files were written even though the plan included creates."""
        entry = _make_entry("Collide Me")
        plan = _make_hook_plan(tmp_path, entry_name="Collide Me")
        hooks_dir = plan.edits[0].path.parent
        (hooks_dir / "prior.sh").write_text(
            "#!/usr/bin/env bash\n# Promoted from KB entry: Collide Me\n"
        )
        result = apply(entry, plan, target_type="hook")
        assert result.success is False
        assert result.rolled_back is False  # Stage 1 abort, nothing to roll back
        assert not plan.edits[0].path.exists()
        assert not plan.edits[1].path.exists()
        # hooks.json untouched
        assert json.loads(plan.edits[2].path.read_text()) == {"hooks": {}}

    def test_ioerror_during_write_triggers_rollback(self, tmp_path):
        """Simulate IOError on a specific write -> rollback."""
        entry = _make_entry()
        # Two creates; the second one will fail via mocked write_text.
        file_a = tmp_path / "ok.sh"
        file_b = tmp_path / "will_fail.sh"
        plan = DiffPlan(
            edits=[
                FileEdit(
                    path=file_a,
                    action="create",
                    before=None,
                    after="A\n",
                    write_order=0,
                ),
                FileEdit(
                    path=file_b,
                    action="create",
                    before=None,
                    after="B\n",
                    write_order=1,
                ),
            ],
            target_type="hook",
            target_path=file_a,
        )
        real_write_text = Path.write_text

        def flaky_write(self, data, *a, **kw):
            if self == file_b:
                raise OSError("simulated disk full")
            return real_write_text(self, data, *a, **kw)

        with mock.patch.object(Path, "write_text", flaky_write):
            result = apply(entry, plan, target_type="hook")
        assert result.success is False
        assert result.rolled_back is True
        assert not file_a.exists(), "first file should have been rolled back"
        assert not file_b.exists()

    def test_baseline_run_failure_modify_restored(self, tmp_path):
        """A modify-action file is written, but Stage 4 validation fails via
        post-write validation callable; snapshot must restore the original
        content byte-for-byte."""
        entry = _make_entry("Bline")
        plan = _make_skill_plan(tmp_path, entry_name="Bline")
        target = plan.edits[0].path
        original = target.read_text()
        import pattern_promotion.apply as apply_mod

        def fail(diff_plan, target_type):
            return False, "simulated post-write validation failure"

        with mock.patch.object(apply_mod, "_stage4_validate", side_effect=fail):
            result = apply(entry, plan, target_type="skill")
        assert result.success is False
        assert result.rolled_back is True
        assert target.read_text() == original
        assert result.reason and "validation" in result.reason.lower()


# ---------------------------------------------------------------------------
# Task 3.5 — Hook-target test script execution at Stage 4
# ---------------------------------------------------------------------------


class TestHookTestScript:
    def test_positive_and_negative_pass_success(self, tmp_path):
        entry = _make_entry("OK Hook")
        plan = _make_hook_plan(
            tmp_path,
            entry_name="OK Hook",
            positive_blocks=True,
            negative_allows=True,
        )
        result = apply(entry, plan, target_type="hook")
        assert result.success is True
        assert result.rolled_back is False

    def test_positive_fails_triggers_rollback(self, tmp_path):
        entry = _make_entry("Bad Positive")
        plan = _make_hook_plan(
            tmp_path,
            entry_name="Bad Positive",
            positive_blocks=False,  # hook fails to block -> positive case fails
            negative_allows=True,
        )
        original_json = plan.edits[2].path.read_text()
        result = apply(entry, plan, target_type="hook")
        assert result.success is False
        assert result.rolled_back is True
        assert not plan.edits[0].path.exists()
        assert not plan.edits[1].path.exists()
        assert plan.edits[2].path.read_text() == original_json

    def test_negative_fails_triggers_rollback(self, tmp_path):
        entry = _make_entry("Bad Negative")
        plan = _make_hook_plan(
            tmp_path,
            entry_name="Bad Negative",
            positive_blocks=True,
            negative_allows=False,  # hook blocks legitimate input -> negative fails
        )
        original_json = plan.edits[2].path.read_text()
        result = apply(entry, plan, target_type="hook")
        assert result.success is False
        assert result.rolled_back is True
        assert not plan.edits[0].path.exists()
        assert plan.edits[2].path.read_text() == original_json

    def test_test_script_timeout_triggers_rollback(self, tmp_path, monkeypatch):
        """Hang the test script; apply should timeout and roll back."""
        entry = _make_entry("Hangy")
        plan = _make_hook_plan(
            tmp_path,
            entry_name="Hangy",
            hang=True,
        )
        # Shorten the timeout to keep tests fast. The apply module reads
        # HOOK_TEST_TIMEOUT from env (with a sensible default).
        monkeypatch.setenv("PATTERN_PROMOTION_HOOK_TEST_TIMEOUT", "1")
        original_json = plan.edits[2].path.read_text()
        result = apply(entry, plan, target_type="hook")
        assert result.success is False
        assert result.rolled_back is True
        assert not plan.edits[0].path.exists()
        assert plan.edits[2].path.read_text() == original_json
        assert result.reason and "timeout" in result.reason.lower()
