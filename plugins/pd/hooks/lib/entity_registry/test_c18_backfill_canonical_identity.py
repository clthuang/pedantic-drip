"""C18: the startup backfill registers canonical identities or nothing.

Stated as an invariant, not as the string ``P``: every entity ``run_backfill``
creates has an ``entity_display`` row and an ``entity_id`` equal to
``render_display_id(kind, seq, slug)``. Kinds in ``NON_SEQUENCE_KINDS``
(brainstorm) are exempt: their identity is a verbatim ``display_id`` with no
display row. A re-run over projects that already carry display rows leaves
the project row count unchanged.

The historic hazard was ``_scan_projects`` reading a project's display row
and re-registering it as ``str(row["seq"])``, dropping the slug (``project:5``
beside the real row), after a lookup that omitted the slug. Two live
workspaces carried project display rows, so that branch was reachable.
"""
from __future__ import annotations

import json

import pytest

from entity_registry.backfill import run_backfill
from entity_registry.database import EntityDatabase, _UNKNOWN_WORKSPACE_UUID
from entity_registry.id_generator import NON_SEQUENCE_KINDS, render_display_id
from entity_registry.test_helpers import bootstrap_test_workspace, seed_legacy_entity


def _assert_canonical(db: EntityDatabase, entity_uuids) -> None:
    """Every entity in *entity_uuids* carries canonical structured identity."""
    for entity_uuid in entity_uuids:
        entity = db.get_entity_by_uuid(entity_uuid, include_deleted=True)
        kind, entity_id = entity["kind"], entity["entity_id"]
        display = db.get_entity_display(entity_uuid)
        if kind in NON_SEQUENCE_KINDS:
            assert display is None, f"{entity['type_id']}: a {kind} has no display row"
        else:
            assert display is not None, f"{entity['type_id']} has no entity_display row"
            assert entity_id == render_display_id(kind, display["seq"], display["slug"]), (
                f"{entity['type_id']} does not render from its display row {dict(display)}")
        assert entity["type_id"] == f"{kind}:{entity_id}"


def _uuids(db: EntityDatabase, kind: str | None = None, workspace_uuid: str | None = None) -> set[str]:
    return {e["uuid"] for e in db.list_entities(entity_type=kind, workspace_uuid=workspace_uuid,
                                                include_deleted=True)}


def _write_meta(root, folder: str, name: str, meta: dict) -> None:
    directory = root / folder / name
    directory.mkdir(parents=True)
    (directory / ".meta.json").write_text(json.dumps(meta))


def _mixed_tree(root) -> None:
    """Every scanner's input, canonical and legacy, with absent parents."""
    (root / "backlog.md").write_text(
        "| ID | Timestamp | Description |\n|----|-----------|-------------|\n"
        "| 019-kept | 2026-01-01T00:00:00Z | Kept item |\n"
        "| 00020 | 2026-01-01T00:00:00Z | Legacy five-digit id |\n"
        "| 00021-old-form | 2026-01-01T00:00:00Z | Legacy id with a slug |\n")
    brainstorms = root / "brainstorms"
    brainstorms.mkdir()
    (brainstorms / "20260101-idea.prd.md").write_text("# Idea\n\n*Source: Backlog #019-kept*\n")
    (brainstorms / "20260101-idea.md").write_text("# Idea, draft\n")
    (brainstorms / "20260102-note.md").write_text("# Note\n\n*Source: Backlog #00020*\n")
    _write_meta(root, "projects", "001-alpha", {"id": "001", "slug": "alpha"})
    _write_meta(root, "projects", "P002-beta", {"id": "P002", "slug": "beta"})
    _write_meta(root, "features", "010-first", {"id": "010", "slug": "first", "project_id": "001-alpha"})
    _write_meta(root, "features", "011-second", {"id": "011", "slug": "second", "backlog_source": "019-kept"})
    _write_meta(root, "features", "012-third", {"id": "012", "slug": "third", "project_id": "009-absent"})
    _write_meta(root, "features", "13-unpadded", {"id": "13", "slug": "unpadded"})
    _write_meta(root, "features", "014-external", {
        "id": "014", "slug": "external", "brainstorm_source": "~/.claude/plans/x.md"})


@pytest.fixture
def db(tmp_path):
    database = EntityDatabase(str(tmp_path / "test.db"))
    yield database
    database.close()


def test_every_entity_backfill_creates_is_canonical(tmp_path, db):
    _mixed_tree(tmp_path)
    before = _uuids(db)
    run_backfill(db, str(tmp_path))
    created = _uuids(db) - before
    _assert_canonical(db, created)
    by_type_id = {db.get_entity_by_uuid(u)["type_id"] for u in created}
    # Not vacuous: each scanner created something, and exactly what is on
    # disk in a registrable form -- no legacy id, no absent parent.
    assert by_type_id == {
        "backlog:019-kept",
        "brainstorm:20260101-idea", "brainstorm:20260102-note",
        "project:001-alpha",
        "feature:010-first", "feature:011-second", "feature:012-third", "feature:014-external",
    }


def test_a_second_scan_creates_nothing(tmp_path, db):
    _mixed_tree(tmp_path)
    run_backfill(db, str(tmp_path))
    after_first = _uuids(db)
    # The done-marker would skip the scan; clear it so the scanners run again.
    db.set_metadata("backfill_complete", "0")
    run_backfill(db, str(tmp_path))
    assert _uuids(db) == after_first
    assert db.get_metadata("backfill_complete") == "1"


def _register_under(db: EntityDatabase, kind: str, seq: int, slug: str, stored_id: str,
                    **workspace) -> str:
    """Register ``(seq, slug)`` with its display row, then store it under an
    older text form, as registries written before the structural model hold
    it. Nothing guards ``type_id`` after insert."""
    entity_uuid = db.register_entity(kind, name=slug.title(), seq=seq, slug=slug, **workspace)
    db._conn.execute("UPDATE entities SET type_id = ?, entity_id = ? WHERE uuid = ?",
                     (f"{kind}:{stored_id}", stored_id, entity_uuid))
    db._conn.commit()
    return entity_uuid


def test_a_rerun_over_projects_with_display_rows_leaves_the_project_row_count_unchanged(tmp_path, db):
    """Each project on disk is already registered with a display row, under
    the forms the live registries hold: canonical, ``P{NNN}`` with no slug,
    ``P{NNN}-{slug}``, and unpadded."""
    _write_meta(tmp_path, "projects", "005-x", {"id": "005", "slug": "x"})
    _write_meta(tmp_path, "projects", "P006-y", {"id": "P006", "slug": "y"})
    _write_meta(tmp_path, "projects", "P008-w", {"id": "P008", "slug": "w"})
    _write_meta(tmp_path, "projects", "007-z", {"id": "007", "slug": "z"})
    db.register_entity("project", name="X", seq=5, slug="x", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    _register_under(db, "project", 6, "y", "P006", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    _register_under(db, "project", 8, "w", "P008-w", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    _register_under(db, "project", 7, "z", "7-z", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    projects_before = _uuids(db, "project")
    assert len(projects_before) == 4

    run_backfill(db, str(tmp_path))

    assert _uuids(db, "project") == projects_before
    # The slug-dropping re-registration would have added these.
    for bare in ("project:5", "project:6", "project:7", "project:8"):
        assert db.get_entity(bare) is None


def test_display_rows_are_matched_only_in_the_backfilled_workspace(tmp_path, db):
    """Another workspace's rows for the same projects neither suppress this
    workspace's registration (its ``5-x`` matches ours by (seq, slug)) nor
    lend it their display rows (its ``P008-w`` would resolve our legacy
    ``P008``)."""
    _write_meta(tmp_path, "projects", "005-x", {"id": "005", "slug": "x"})
    _write_meta(tmp_path, "projects", "P008-w", {"id": "P008", "slug": "w"})
    ours = bootstrap_test_workspace(db, "ours")
    theirs = bootstrap_test_workspace(db, "theirs")
    _register_under(db, "project", 5, "x", "5-x", workspace_uuid=theirs)
    _register_under(db, "project", 8, "w", "P008-w", workspace_uuid=theirs)
    theirs_before = {e["uuid"]: e["type_id"] for e in db.list_entities(workspace_uuid=theirs)}

    run_backfill(db, str(tmp_path), project_id="ours")

    created = _uuids(db, workspace_uuid=ours)
    _assert_canonical(db, created)
    assert {db.get_entity_by_uuid(u)["type_id"] for u in created} == {"project:005-x"}
    assert {e["uuid"]: e["type_id"] for e in db.list_entities(workspace_uuid=theirs)} == theirs_before


def test_the_invariant_check_is_not_vacuous(db):
    """The check fails on the two shapes it exists to catch."""
    no_display_row = seed_legacy_entity(db, "project", "P001", "Old")
    with pytest.raises(AssertionError, match="has no entity_display row"):
        _assert_canonical(db, {no_display_row})
    unrendered = _register_under(db, "feature", 66, "x", "66-x", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    with pytest.raises(AssertionError, match="does not render from its display row"):
        _assert_canonical(db, {unrendered})
