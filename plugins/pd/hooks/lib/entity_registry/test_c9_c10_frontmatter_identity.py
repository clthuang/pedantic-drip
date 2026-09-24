"""C8 (frontmatter_sync's kind), C9 (seq/slug) and C10 (parent) in frontmatter headers.

- **C8** — ``frontmatter_sync`` decides "is this a feature" from the
  ``kind`` column, not the ``type_id`` prefix.
- **C9** — ``feature_id`` / ``feature_slug`` come from the ``entity_display``
  row (``read_display_identity``), not from splitting the ``type_id``.
- **C10** — ``project_id`` comes from ``parent_uuid`` → the parent row: its
  ``kind`` column decides whether it is a project, and its stored
  ``entity_id`` is read whole (design D9). A parent with no display row —
  an archived legacy project — still resolves.

Both surfaces are exercised: the ``frontmatter_inject.py`` CLI that phase exit
runs, and ``frontmatter_sync.stamp_header``. Every fixture makes the text the
old code split disagree with the structured source, so a reader that still
splits text fails.
"""
from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from entity_registry import frontmatter_inject, frontmatter_sync
from entity_registry.database import EntityDatabase
from entity_registry.frontmatter import read_frontmatter
from entity_registry.frontmatter_sync import stamp_header
from entity_registry.test_helpers import seed_legacy_entity

_INJECT_SCRIPT = str(Path(frontmatter_inject.__file__))
_HOOKS_LIB = str(Path(frontmatter_inject.__file__).resolve().parent.parent)


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "entities.db")


@pytest.fixture
def db(db_path):
    database = EntityDatabase(db_path)
    yield database
    database.close()


def _store_under(db: EntityDatabase, entity_uuid: str, type_id: str) -> None:
    """Store an entity under a different ``type_id`` text, keeping its
    ``entity_id`` column. Nothing guards ``type_id`` after insert."""
    db._conn.execute("UPDATE entities SET type_id = ? WHERE uuid = ?", (type_id, entity_uuid))
    db._conn.commit()


def _store_id_under(db: EntityDatabase, entity_uuid: str, kind: str, stored_entity_id: str) -> str:
    """Store an entity under an older text form of its identity (both
    ``type_id`` and ``entity_id``). Returns the new type_id."""
    type_id = f"{kind}:{stored_entity_id}"
    db._conn.execute(
        "UPDATE entities SET type_id = ?, entity_id = ? WHERE uuid = ?",
        (type_id, stored_entity_id, entity_uuid),
    )
    db._conn.commit()
    return type_id


def _set_metadata(db: EntityDatabase, entity_uuid: str, metadata: dict) -> None:
    db._conn.execute(
        "UPDATE entities SET metadata = ? WHERE uuid = ?", (json.dumps(metadata), entity_uuid),
    )
    db._conn.commit()


def _inject(artifact: Path, type_id: str, db_path: str) -> dict:
    """Run the phase-exit CLI against *db_path* and return the header it wrote.

    ``ENTITY_DB_PATH`` is set explicitly: the CLI must never fall back to the
    live registry.
    """
    result = subprocess.run(
        [sys.executable, _INJECT_SCRIPT, str(artifact), type_id],
        capture_output=True, text=True,
        env={"PYTHONPATH": _HOOKS_LIB, "ENTITY_DB_PATH": db_path},
    )
    assert result.returncode == 0, result.stderr
    header = read_frontmatter(str(artifact))
    assert header is not None, f"no header written; stderr: {result.stderr}"
    return header


def _spec(tmp_path: Path) -> Path:
    artifact = tmp_path / "spec.md"
    artifact.write_text("# Spec\n", encoding="utf-8")
    return artifact


def _stamp(db: EntityDatabase, tmp_path: Path, type_id: str) -> dict:
    artifact = _spec(tmp_path)
    result = stamp_header(db, str(artifact), type_id, "spec")
    assert result.action == "created", result.message
    return read_frontmatter(str(artifact))


# ---------------------------------------------------------------------------
# C9 — feature_id / feature_slug from the display row
# ---------------------------------------------------------------------------


class TestFeatureFieldsFromTheDisplayRow:
    """Textual id ``5-textual-slug``, display row (42, ``display-slug``),
    metadata id ``0000007`` / slug ``meta-slug``: all three disagree. The old
    code split the text into ``5`` / ``textual-slug``."""

    @staticmethod
    def _disagreeing_feature(db) -> str:
        entity_uuid = db.register_entity(
            "feature", name="Display Slug", seq=42, slug="display-slug",
            metadata={"id": "0000007", "slug": "meta-slug"}, project_id="__unknown__",
        )
        return _store_id_under(db, entity_uuid, "feature", "5-textual-slug")

    def test_inject_cli(self, db, db_path, tmp_path):
        type_id = self._disagreeing_feature(db)
        header = _inject(_spec(tmp_path), type_id, db_path)
        assert (header["feature_id"], header["feature_slug"]) == ("042", "display-slug")

    def test_stamp_header(self, db, tmp_path):
        type_id = self._disagreeing_feature(db)
        header = _stamp(db, tmp_path, type_id)
        assert (header["feature_id"], header["feature_slug"]) == ("042", "display-slug")

    def test_unpadded_live_feature_keeps_its_number(self, db, db_path, tmp_path):
        """The live unpadded shape (seq 74 stored as ``74-sse-event-stream``)
        keeps the header it always had, matching its directory and
        ``.meta.json``."""
        entity_uuid = db.register_entity(
            "feature", name="Sse Event Stream", seq=74, slug="sse-event-stream",
            project_id="__unknown__",
        )
        type_id = _store_id_under(db, entity_uuid, "feature", "74-sse-event-stream")

        header = _inject(_spec(tmp_path), type_id, db_path)

        assert (header["feature_id"], header["feature_slug"]) == ("74", "sse-event-stream")

    def test_legacy_feature_reads_its_metadata_not_its_id_text(self, db, tmp_path):
        """No display row: the header takes the ``id``/``slug`` metadata stored
        at registration — the ``.meta.json`` projection's fallback — never
        the split text (``043`` / ``legacy``)."""
        legacy_uuid = seed_legacy_entity(db, "feature", "043-legacy", "Legacy", status="completed")
        _set_metadata(db, legacy_uuid, {"id": "0431", "slug": "meta-slug"})

        header = _stamp(db, tmp_path, "feature:043-legacy")

        assert (header["feature_id"], header["feature_slug"]) == ("0431", "meta-slug")

    def test_legacy_feature_without_metadata_identity_gets_no_feature_fields(self, db, tmp_path):
        """No display row and no metadata id/slug: the fields are omitted, as
        optional header fields always were when absent."""
        seed_legacy_entity(db, "feature", "043-legacy", "Legacy", status="completed")

        header = _stamp(db, tmp_path, "feature:043-legacy")

        assert "feature_id" not in header
        assert "feature_slug" not in header


# ---------------------------------------------------------------------------
# C8 — frontmatter_sync reads kind from the kind column
# ---------------------------------------------------------------------------


class TestKindFromTheKindColumn:
    def test_a_feature_stored_under_a_project_prefix_still_gets_feature_fields(self, db, tmp_path):
        entity_uuid = db.register_entity(
            "feature", name="Feat", seq=3, slug="feat", project_id="__unknown__",
        )
        _store_under(db, entity_uuid, "project:003-feat")

        header = _stamp(db, tmp_path, "project:003-feat")

        assert (header.get("feature_id"), header.get("feature_slug")) == ("003", "feat")

    def test_a_project_stored_under_a_feature_prefix_gets_no_feature_fields(self, db, tmp_path):
        entity_uuid = db.register_entity(
            "project", name="Proj", seq=4, slug="proj", project_id="__unknown__",
        )
        _store_under(db, entity_uuid, "feature:004-proj")

        header = _stamp(db, tmp_path, "feature:004-proj")

        assert "feature_id" not in header
        assert "feature_slug" not in header


# ---------------------------------------------------------------------------
# C10 — project_id from the parent row
# ---------------------------------------------------------------------------


def _child_of(db: EntityDatabase, parent_uuid: str, *, seq: int = 2, slug: str = "child") -> str:
    db.register_entity(
        "feature", name=slug.title(), seq=seq, slug=slug, status="active",
        parent_uuid=parent_uuid, project_id="__unknown__",
    )
    return f"feature:{seq:03d}-{slug}"


class TestProjectIdFromTheParentRow:
    def test_parent_kind_comes_from_its_kind_column(self, db, db_path, tmp_path):
        """A project parent whose type_id text says ``brainstorm:``: the old
        split found no project and wrote no ``project_id``."""
        parent_uuid = db.register_entity(
            "project", name="Real Parent", seq=1, slug="real-parent", project_id="__unknown__",
        )
        _store_under(db, parent_uuid, "brainstorm:001-real-parent")
        child_type_id = _child_of(db, parent_uuid)

        header = _inject(_spec(tmp_path), child_type_id, db_path)

        assert header.get("project_id") == "001-real-parent"

    def test_a_parent_that_is_not_a_project_gives_no_project_id(self, db, db_path, tmp_path):
        """A brainstorm parent whose type_id text says ``project:P999``: the
        old split wrote ``project_id: P999``."""
        parent_uuid = db.register_entity(
            "brainstorm", name="Idea", display_id="20260924-120000-idea",
            project_id="__unknown__",
        )
        _store_under(db, parent_uuid, "project:P999")
        child_type_id = _child_of(db, parent_uuid)

        header = _inject(_spec(tmp_path), child_type_id, db_path)

        assert "project_id" not in header

    def test_parent_identity_is_its_stored_entity_id_read_whole(self, db, tmp_path):
        """The parent's ``type_id`` text says ``P777-text``; its stored
        ``entity_id`` column says ``001-real-parent``. The column is the
        identity."""
        parent_uuid = db.register_entity(
            "project", name="Real Parent", seq=1, slug="real-parent", project_id="__unknown__",
        )
        _store_under(db, parent_uuid, "project:P777-text")
        child_type_id = _child_of(db, parent_uuid)

        header = _stamp(db, tmp_path, child_type_id)

        assert header.get("project_id") == "001-real-parent"

    def test_a_soft_deleted_parent_project_still_resolves(self, db, tmp_path):
        """The ``parent_type_id`` join the old code read did not filter
        ``is_deleted``, so a soft-deleted parent project still named its
        children's ``project_id``. The parent-row read keeps that."""
        parent_uuid = db.register_entity(
            "project", name="Gone Parent", seq=1, slug="gone-parent", project_id="__unknown__",
        )
        child_type_id = _child_of(db, parent_uuid)
        db._conn.execute("UPDATE entities SET is_deleted = 1 WHERE uuid = ?", (parent_uuid,))
        db._conn.commit()
        assert db.get_entity_by_uuid(parent_uuid) is None, (
            "setup failed: the parent must be hidden from the default read"
        )

        header = _stamp(db, tmp_path, child_type_id)

        assert header.get("project_id") == "001-gone-parent"

    @pytest.mark.parametrize("surface", ["inject", "stamp"])
    def test_child_of_an_archived_legacy_parent_keeps_its_project_id(
        self, db, db_path, tmp_path, surface,
    ):
        """Retained lineage (design D9): D0 left live children attached to
        archived legacy parents that have no display row. The parent exists,
        so this is not D8's missing-parent case; its identity is readable
        whole even though it cannot be decomposed."""
        parent_uuid = seed_legacy_entity(db, "project", "P001", "Legacy Project", status="active")
        db._conn.execute("UPDATE entities SET is_archived = 1 WHERE uuid = ?", (parent_uuid,))
        db._conn.commit()
        premise = db._conn.execute(
            "SELECT e.is_legacy, e.is_archived, d.uuid AS display_uuid "
            "FROM entities e LEFT JOIN entity_display d ON d.uuid = e.uuid WHERE e.uuid = ?",
            (parent_uuid,),
        ).fetchone()
        assert (premise["is_legacy"], premise["is_archived"], premise["display_uuid"]) == (1, 1, None), (
            "setup failed: the parent must be legacy, archived and display-less"
        )
        child_type_id = _child_of(db, parent_uuid, seq=3, slug="live-child")

        if surface == "inject":
            header = _inject(_spec(tmp_path), child_type_id, db_path)
        else:
            header = _stamp(db, tmp_path, child_type_id)

        assert header.get("project_id") == "P001"


# ---------------------------------------------------------------------------
# Static: no identity text is taken apart
# ---------------------------------------------------------------------------

_SEPARATOR_METHODS = {"split", "rsplit", "partition", "rpartition"}


def _separator_splits(source: str) -> list[str]:
    """Every ``x.split(sep)`` / ``x.partition(sep)`` with a ``-`` or ``:``
    separator, whatever the receiver is called."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _SEPARATOR_METHODS
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in {"-", ":"}
        ):
            found.append(f"line {node.lineno}: {ast.unparse(node)}")
    return found


def test_frontmatter_inject_splits_no_identity_text():
    assert _separator_splits(Path(frontmatter_inject.__file__).read_text()) == []


def test_frontmatter_sync_derives_header_fields_without_splitting():
    source = textwrap.dedent(inspect.getsource(frontmatter_sync._derive_optional_fields))
    assert _separator_splits(source) == []
