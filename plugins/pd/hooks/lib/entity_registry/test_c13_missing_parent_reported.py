"""C13: a parent backfill cannot resolve is reported, never minted (design D8).

Files name parents as text: a feature's ``project_id``, ``brainstorm_source``
and ``backlog_source``, a project's ``brainstorm_source``, a brainstorm's
backlog marker. Before C13 a feature whose named parent was not registered in
the workspace got a synthetic parent minted from that text, with status
``orphaned`` or ``external``. Now the link is left unset and one stderr line
names both ends, so an import with an absent parent registers only what is on
disk.

Supersedes ``test_backfill.py``'s ``TestOrphanedAndExternal`` and
``TestParentReferenceToNonexistentEntity``, which pinned the minting.
"""
from __future__ import annotations

import json

import pytest

from entity_registry.backfill import run_backfill
from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import bootstrap_test_workspace


def _unresolved(child: str, parent: str) -> str:
    """The diagnostic for a parent this workspace has not registered."""
    return (f"entity-server: backfill: set_parent {child}->{parent} skipped: "
            f"parent is not registered in this workspace")


def _tree(root) -> None:
    for sub in ("brainstorms", "features", "projects"):
        (root / sub).mkdir()


def _write_meta(root, folder: str, name: str, meta: dict) -> None:
    directory = root / folder / name
    directory.mkdir()
    (directory / ".meta.json").write_text(json.dumps(meta))


def _feature(root, seq: int, slug: str, **meta) -> None:
    _write_meta(root, "features", f"{seq:03d}-{slug}", {"id": f"{seq:03d}", "slug": slug, **meta})


def _type_ids(db: EntityDatabase, workspace_uuid: str | None = None) -> set[str]:
    return {e["type_id"] for e in db.list_entities(workspace_uuid=workspace_uuid,
                                                   include_deleted=True)}


@pytest.fixture
def db(tmp_path):
    database = EntityDatabase(str(tmp_path / "test.db"))
    yield database
    database.close()


# Each case: the feature's parent field, as a function of the artifacts root,
# and the parent type_id backfill derives from it.
_ABSENT_FEATURE_PARENTS = [
    pytest.param(lambda root: {"project_id": "001-absent"}, "project:001-absent",
                 id="project_id"),
    pytest.param(lambda root: {"project_id": "P001"}, "project:P001",
                 id="legacy project_id"),
    pytest.param(lambda root: {"brainstorm_source": "docs/brainstorms/20260301-missing.prd.md"},
                 "brainstorm:20260301-missing", id="in-repo brainstorm"),
    pytest.param(lambda root: {"brainstorm_source": str(root / "brainstorms" / "20260101-gone.prd.md")},
                 "brainstorm:20260101-gone", id="absolute in-repo brainstorm"),
    pytest.param(lambda root: {"brainstorm_source": "~/.claude/plans/some-plan.md"},
                 "brainstorm:some-plan", id="external brainstorm"),
    pytest.param(lambda root: {"brainstorm_source": "/home/user/plans/plan.prd.md"},
                 "brainstorm:plan", id="absolute external brainstorm"),
    pytest.param(lambda root: {"backlog_source": "099-orphan-item"}, "backlog:099-orphan-item",
                 id="backlog_source"),
]


@pytest.mark.parametrize("parent_field, parent", _ABSENT_FEATURE_PARENTS)
def test_an_absent_feature_parent_is_reported_and_nothing_is_minted(
        tmp_path, db, capsys, parent_field, parent):
    _tree(tmp_path)
    _feature(tmp_path, 31, "child", **parent_field(tmp_path))
    run_backfill(db, str(tmp_path))
    # The one entity on disk; nothing minted from the text naming its parent.
    assert _type_ids(db) == {"feature:031-child"}
    assert db.get_entity("feature:031-child")["parent_uuid"] is None
    assert _unresolved("feature:031-child", parent) in capsys.readouterr().err


def test_a_brainstorm_whose_backlog_marker_is_unregistered_is_reported(tmp_path, db, capsys):
    _tree(tmp_path)
    (tmp_path / "brainstorms" / "20260101-idea.prd.md").write_text(
        "# Idea\n\n*Source: Backlog #019-absent*\n")
    run_backfill(db, str(tmp_path))
    assert _type_ids(db) == {"brainstorm:20260101-idea"}
    assert db.get_entity("brainstorm:20260101-idea")["parent_uuid"] is None
    assert _unresolved("brainstorm:20260101-idea", "backlog:019-absent") in capsys.readouterr().err


def test_a_project_whose_brainstorm_is_unregistered_is_reported(tmp_path, db, capsys):
    _tree(tmp_path)
    _write_meta(tmp_path, "projects", "001-plan", {
        "id": "001", "slug": "plan",
        "brainstorm_source": "docs/brainstorms/20260301-missing.prd.md"})
    run_backfill(db, str(tmp_path))
    assert _type_ids(db) == {"project:001-plan"}
    assert db.get_entity("project:001-plan")["parent_uuid"] is None
    assert _unresolved("project:001-plan", "brainstorm:20260301-missing") in capsys.readouterr().err


def test_a_missing_legacy_backlog_source_is_logged_as_legacy_and_reported(tmp_path, db, capsys):
    """Wave 2's skip-and-log line for a legacy id stays; the unset link is
    reported beside it."""
    _tree(tmp_path)
    _feature(tmp_path, 31, "child", backlog_source="00099")
    run_backfill(db, str(tmp_path))
    err = capsys.readouterr().err
    assert _type_ids(db) == {"feature:031-child"}
    assert "entity-server: backfill: skipping backlog '00099': no seq/slug form" in err
    assert _unresolved("feature:031-child", "backlog:00099") in err


def test_a_parent_registered_only_in_another_workspace_is_reported_not_minted_here(
        tmp_path, db, capsys):
    """Before C13 the missing-parent path minted ``project:001-shared`` in this
    workspace, because the scoped lookup rightly did not see the other one."""
    _tree(tmp_path)
    _feature(tmp_path, 40, "child", project_id="001-shared")
    ours = bootstrap_test_workspace(db, "ours")
    theirs = bootstrap_test_workspace(db, "theirs")
    db.register_entity("project", name="Shared", seq=1, slug="shared", workspace_uuid=theirs)
    run_backfill(db, str(tmp_path), project_id="ours")
    assert _type_ids(db, ours) == {"feature:040-child"}
    assert _type_ids(db, theirs) == {"project:001-shared"}
    [child] = [e for e in db.list_entities(workspace_uuid=ours)
               if e["type_id"] == "feature:040-child"]
    assert child["parent_uuid"] is None
    assert _unresolved("feature:040-child", "project:001-shared") in capsys.readouterr().err


def test_a_second_scan_mints_nothing_either(tmp_path, db, capsys):
    _tree(tmp_path)
    _feature(tmp_path, 31, "child", project_id="001-absent")
    run_backfill(db, str(tmp_path))
    first = _type_ids(db)
    capsys.readouterr()
    # The done-marker would skip the scan; clear it so the scanners run again.
    db.set_metadata("backfill_complete", "0")
    run_backfill(db, str(tmp_path))
    assert _type_ids(db) == first == {"feature:031-child"}
    # The scan did run: the absent parent is reported a second time.
    assert _unresolved("feature:031-child", "project:001-absent") in capsys.readouterr().err


def test_a_registered_parent_is_linked_without_a_diagnostic(tmp_path, db, capsys):
    """The diagnostic belongs to the absent-parent path only."""
    _tree(tmp_path)
    _write_meta(tmp_path, "projects", "001-present", {"id": "001", "slug": "present"})
    _feature(tmp_path, 31, "child", project_id="001-present")
    run_backfill(db, str(tmp_path))
    assert db.get_entity("feature:031-child")["parent_type_id"] == "project:001-present"
    assert "set_parent" not in capsys.readouterr().err
