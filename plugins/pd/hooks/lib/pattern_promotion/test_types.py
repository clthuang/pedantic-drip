"""Round-trip serialization tests for pattern_promotion dataclasses.

FileEdit, DiffPlan, Result must survive dataclasses.asdict + json.dumps with
Path fields coerced to str. This is the subprocess serialization contract
(design TD-3 / I-6 / I-7).
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from pattern_promotion.types import DiffPlan, FileEdit, Result


def _to_json(obj) -> str:
    """Coerce Path fields to str, then asdict + json.dumps."""
    raw = dataclasses.asdict(obj)
    return json.dumps(raw, default=str)


class TestFileEdit:
    def test_create_edit_roundtrip(self):
        edit = FileEdit(
            path=Path("/tmp/new_file.sh"),
            action="create",
            before=None,
            after="#!/bin/bash\necho ok\n",
            write_order=0,
        )
        payload = _to_json(edit)
        data = json.loads(payload)
        assert data["path"] == "/tmp/new_file.sh"
        assert data["action"] == "create"
        assert data["before"] is None
        assert data["after"].startswith("#!/bin/bash")
        assert data["write_order"] == 0

    def test_modify_edit_roundtrip(self):
        edit = FileEdit(
            path=Path("/tmp/existing.md"),
            action="modify",
            before="old content\n",
            after="old content\nappended line\n",
            write_order=1,
        )
        payload = _to_json(edit)
        data = json.loads(payload)
        assert data["action"] == "modify"
        assert data["before"] == "old content\n"
        assert data["write_order"] == 1

    def test_write_order_is_int(self):
        edit = FileEdit(
            path=Path("/tmp/x"),
            action="create",
            before=None,
            after="x",
            write_order=2,
        )
        data = json.loads(_to_json(edit))
        assert isinstance(data["write_order"], int)


class TestDiffPlan:
    def test_empty_edits_roundtrip(self):
        plan = DiffPlan(
            edits=[],
            target_type="skill",
            target_path=Path("plugins/pd/skills/implementing/SKILL.md"),
        )
        data = json.loads(_to_json(plan))
        assert data["edits"] == []
        assert data["target_type"] == "skill"
        assert data["target_path"] == "plugins/pd/skills/implementing/SKILL.md"

    def test_multi_edit_roundtrip(self):
        edits = [
            FileEdit(
                path=Path("plugins/pd/hooks/check-x.sh"),
                action="create",
                before=None,
                after="#!/bin/bash\nexit 0\n",
                write_order=0,
            ),
            FileEdit(
                path=Path("plugins/pd/hooks/hooks.json"),
                action="modify",
                before='{"hooks": []}',
                after='{"hooks": [{"event": "PreToolUse"}]}',
                write_order=2,
            ),
        ]
        plan = DiffPlan(
            edits=edits,
            target_type="hook",
            target_path=Path("plugins/pd/hooks/check-x.sh"),
        )
        data = json.loads(_to_json(plan))
        assert len(data["edits"]) == 2
        assert data["edits"][0]["write_order"] == 0
        assert data["edits"][1]["write_order"] == 2
        assert data["target_type"] == "hook"

    def test_target_type_valid_enum(self):
        for tt in ("hook", "skill", "agent", "command"):
            plan = DiffPlan(edits=[], target_type=tt, target_path=Path("x"))
            data = json.loads(_to_json(plan))
            assert data["target_type"] == tt


class TestResult:
    def test_success_roundtrip(self):
        res = Result(
            success=True,
            target_path=Path("plugins/pd/hooks/check-x.sh"),
            reason=None,
            rolled_back=False,
            stage_completed=4,
        )
        data = json.loads(_to_json(res))
        assert data["success"] is True
        assert data["target_path"] == "plugins/pd/hooks/check-x.sh"
        assert data["reason"] is None
        assert data["rolled_back"] is False
        assert data["stage_completed"] == 4

    def test_failure_roundtrip(self):
        res = Result(
            success=False,
            target_path=None,
            reason="validate.sh introduced new error category",
            rolled_back=True,
            stage_completed=3,
        )
        data = json.loads(_to_json(res))
        assert data["success"] is False
        assert data["target_path"] is None
        assert data["rolled_back"] is True
        assert "validate.sh" in data["reason"]

    def test_stage_completed_range(self):
        for stage in range(0, 6):
            res = Result(
                success=False,
                target_path=None,
                reason="test",
                rolled_back=False,
                stage_completed=stage,
            )
            data = json.loads(_to_json(res))
            assert data["stage_completed"] == stage
