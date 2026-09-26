"""C5b step 1: the reconciler's brainstorm registration takes one workspace uuid.

``_sync_brainstorm_entities`` used to hand its registration call either its
``workspace_uuid`` or, when it had none, the ``project_id`` alias. It now
resolves the workspace once — the given one, else the one the legacy
``project_id`` names — and passes only ``workspace_uuid``. The
``entity_created`` label is unchanged: the legacy id when that is how the
workspace was found (it is that workspace's ``project_id_legacy``), the given
workspace's legacy id otherwise.

Task 1C made that call ``register_entity``, insert-only, where it was
``upsert_entity``: the tests record the call it makes now.
"""
from __future__ import annotations

import inspect

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import bootstrap_test_workspace
from reconciliation_orchestrator import entity_status

LEGACY_A = "c5b-ws-a"
LEGACY_B = "c5b-ws-b"
_STEM = "20260101-000000-reconciled"
_TYPE_ID = f"brainstorm:{_STEM}"


def _record_calls(monkeypatch, target, method_name: str) -> list[dict]:
    """Wrap ``target.method_name``; return every call's arguments by parameter
    name, positional ones included."""
    calls: list[dict] = []
    original = getattr(target, method_name)
    signature = inspect.signature(original)

    def recording(*args, **kwargs):
        calls.append(dict(signature.bind(*args, **kwargs).arguments))
        return original(*args, **kwargs)

    monkeypatch.setattr(target, method_name, recording)
    return calls


def _created_label(db: EntityDatabase, type_id: str) -> str:
    rows = db._conn.execute(
        "SELECT project_id FROM phase_events "
        "WHERE type_id = ? AND event_type = 'entity_created'",
        (type_id,),
    ).fetchall()
    assert len(rows) == 1, f"{type_id}: expected one entity_created event, got {len(rows)}"
    return rows[0][0]


@pytest.mark.parametrize("given_workspace, expected_workspace, expected_label", [
    (None, "ws_a", LEGACY_A),
    ("ws_b", "ws_b", LEGACY_B),
])
def test_brainstorm_sync_registers_in_one_resolved_workspace(
    tmp_path, monkeypatch, given_workspace, expected_workspace, expected_label,
):
    db = EntityDatabase(":memory:")
    workspaces = {"ws_a": bootstrap_test_workspace(db, LEGACY_A),
                  "ws_b": bootstrap_test_workspace(db, LEGACY_B)}
    (tmp_path / "brainstorms").mkdir()
    (tmp_path / "brainstorms" / f"{_STEM}.prd.md").touch()
    # Task 1C: registration is register_entity (insert-only), not upsert_entity.
    registrations = _record_calls(monkeypatch, db, "register_entity")

    result = entity_status._sync_brainstorm_entities(
        db, str(tmp_path), "docs", str(tmp_path), LEGACY_A,
        workspaces.get(given_workspace),
    )

    assert result["registered"] == 1
    assert len(registrations) == 1
    assert registrations[0].get("project_id") is None, registrations[0]
    assert registrations[0].get("workspace_uuid") == workspaces[expected_workspace], registrations[0]
    assert db.get_entity(_TYPE_ID)["workspace_uuid"] == workspaces[expected_workspace]
    assert _created_label(db, _TYPE_ID) == expected_label
    db.close()


# ---------------------------------------------------------------------------
# Degenerate inputs report exactly what the pre-C5b build reported
# ---------------------------------------------------------------------------

_STALE_WORKSPACE_UUID = "01900000-0000-7000-8000-00000000dead"


def test_brainstorm_sync_with_nothing_to_register_resolves_no_workspace(tmp_path):
    """No brainstorm file means no workspace is resolved: an unknown legacy
    id goes unreported. (Before W1.1 the archive pass's read that followed
    reported it; that pass is deleted. Since task 1C the workspace is
    resolved at the first ``.prd.md`` file, registered or not: the existence
    check reads that workspace.)"""
    db = EntityDatabase(":memory:")
    (tmp_path / "brainstorms").mkdir()

    result = entity_status.sync_entity_statuses(
        db, str(tmp_path), project_id="no-such-legacy-id",
        artifacts_root="docs", project_root=str(tmp_path),
    )

    assert result == {"registered": 0, "skipped": 0, "warnings": []}
    db.close()


def test_brainstorm_sync_into_a_stale_workspace_reports_register_entity_as_before(tmp_path):
    """A given workspace with no workspaces row (the split-brain) is refused
    by the registration, under register_entity()'s name, as before C5b."""
    db = EntityDatabase(":memory:")
    bootstrap_test_workspace(db, LEGACY_A)
    (tmp_path / "brainstorms").mkdir()
    (tmp_path / "brainstorms" / f"{_STEM}.prd.md").touch()

    result = entity_status.sync_entity_statuses(
        db, str(tmp_path), project_id=LEGACY_A, artifacts_root="docs",
        project_root=str(tmp_path), workspace_uuid=_STALE_WORKSPACE_UUID,
    )

    assert result["registered"] == 0
    assert result["warnings"] == [
        f"brainstorms: register_entity(): workspace_uuid={_STALE_WORKSPACE_UUID!r} not "
        f"present in the workspaces table — workspace.json/DB split-brain detected. Run "
        f"pd:doctor --fix, then restart the session (MCP servers cache the workspace UUID "
        f"at startup)."
    ]
    assert db.get_entity(_TYPE_ID) is None
    db.close()
