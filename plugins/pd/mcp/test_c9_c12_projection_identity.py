"""C9 + C12 at the ``.meta.json`` and ``backlog.md`` projections.

- **C9** — a projected ``id``/``slug`` and a backlog row's ``seq`` come from
  the ``entity_display`` row, never from the characters of the ``type_id``
  or ``entity_id``.
- **C12** — the zero-pad width of a projected ``id`` comes from the renderer
  (``render_display_seq``), never from ``metadata.id`` or the stored id.

Every fixture that asserts the structured result disagrees on ALL THREE
sources the old readers could consult — the textual id, the display row and
metadata — because ``_read_entity_display`` falls back to ``metadata``
id/slug when it finds no display row. A fixture on which that fallback agrees
would pass whether or not the display row was read.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import sys
import textwrap

import pytest

# Ensure hooks/lib is on path for imports (mirrors test_workflow_state_server.py).
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in sys.path:
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import seed_legacy_entity

import workflow_state_server as wss
from workflow_state_server import _project_backlog_md, _project_meta_json


@pytest.fixture
def db():
    database = EntityDatabase(":memory:")
    yield database
    database.close()


def _store_under(db: EntityDatabase, entity_uuid: str, kind: str, stored_entity_id: str) -> str:
    """Store an entity under an older text form of its identity, as registries
    written before the renderer hold it. Nothing guards ``type_id`` after
    insert. Returns the new type_id."""
    type_id = f"{kind}:{stored_entity_id}"
    db._conn.execute(
        "UPDATE entities SET type_id = ?, entity_id = ? WHERE uuid = ?",
        (type_id, stored_entity_id, entity_uuid),
    )
    db._conn.commit()
    return type_id


def _set_metadata(db: EntityDatabase, entity_uuid: str, metadata: dict) -> None:
    db._conn.execute(
        "UPDATE entities SET metadata = ? WHERE uuid = ?",
        (json.dumps(metadata), entity_uuid),
    )
    db._conn.commit()


def _projected(db: EntityDatabase, type_id: str, directory) -> dict:
    """Run the projection for *type_id* into *directory* and read it back."""
    os.makedirs(directory, exist_ok=True)
    warning = _project_meta_json(db, None, type_id, str(directory))
    assert warning is None, f"projection returned a warning: {warning}"
    with open(os.path.join(directory, ".meta.json")) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# .meta.json, feature kind
# ---------------------------------------------------------------------------


class TestFeatureProjection:
    def test_id_and_slug_come_from_the_display_row_at_the_renderer_width(self, db, tmp_path):
        """Textual id ``5-textual-slug``, display row (42, ``display-slug``),
        metadata id ``0000007`` / slug ``meta-slug``: all three disagree.

        The old reader already took seq/slug from the display row but took the
        WIDTH from ``metadata.id`` first, so it projected ``0000042``. The
        renderer's width gives ``042``.
        """
        entity_uuid = db.register_entity(
            "feature", name="Display Slug", seq=42, slug="display-slug",
            metadata={"id": "0000007", "slug": "meta-slug"},
            project_id="__unknown__",
        )
        type_id = _store_under(db, entity_uuid, "feature", "5-textual-slug")

        meta = _projected(db, type_id, tmp_path / "features" / "5-textual-slug")

        assert (meta["id"], meta["slug"]) == ("042", "display-slug")

    @pytest.mark.parametrize("seq,slug", [
        (74, "sse-event-stream"),
        (1, "causal-inference-training"),
    ])
    def test_unpadded_live_feature_projects_exactly_what_it_did(self, db, tmp_path, seq, slug):
        """The live shape: a display row and an id stored UNPADDED, with no
        ``metadata.id`` (e.g. fractorg's ``74-sse-event-stream``, whose
        directory and ``.meta.json`` both carry ``74``). Readers rebuild
        ``feature:{id}-{slug}`` from the projection (``yolo-stop.sh``'s
        ``--feature=`` ref, ``create-specialist-team.md``'s ``get_phase``
        call), so the projected id must stay unpadded.
        """
        stored_entity_id = f"{seq}-{slug}"
        unpadded_uuid = db.register_entity(
            "feature", name=slug.title(), seq=seq, slug=slug,
            metadata={"mode": "standard"}, project_id="__unknown__",
        )
        type_id = _store_under(db, unpadded_uuid, "feature", stored_entity_id)

        meta = _projected(db, type_id, tmp_path / "features" / stored_entity_id)
        assert (meta["id"], meta["slug"]) == (str(seq), slug)
        assert f"feature:{meta['id']}-{meta['slug']}" == type_id, (
            "a reader rebuilding the type_id from this projection must find the entity"
        )

    def test_the_same_display_row_under_its_canonical_id_renders_padded(self, db, tmp_path):
        """The counterpart of the unpadded pin: it is the stored id being the
        unpadded form of these same (seq, slug) that keeps ``74``, nothing
        else — the canonical registration of seq 74 projects ``074``."""
        db.register_entity(
            "feature", name="Sse Event Stream", seq=74, slug="sse-event-stream",
            metadata={"mode": "standard"}, project_id="__unknown__",
        )
        meta = _projected(db, "feature:074-sse-event-stream", tmp_path / "features" / "074")
        assert (meta["id"], meta["slug"]) == ("074", "sse-event-stream")

    def test_a_display_row_the_renderer_refuses_reads_like_a_missing_one(self, db, tmp_path, capsys):
        """A non-positive seq cannot be rendered. The projection runs after the
        mutation commits, so it must not raise: the row is treated like a
        missing one — metadata id/slug, and a stderr warning."""
        entity_uuid = db.register_entity(
            "feature", name="X", seq=7, slug="x",
            metadata={"id": "meta-7", "slug": "meta-x"}, project_id="__unknown__",
        )
        db._conn.execute("UPDATE entity_display SET seq = 0 WHERE uuid = ?", (entity_uuid,))
        db._conn.commit()

        meta = _projected(db, "feature:007-x", tmp_path / "features" / "007-x")

        assert (meta["id"], meta["slug"]) == ("meta-7", "meta-x")
        assert "no usable entity_display row for 'feature:007-x'" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# .meta.json, project kind
# ---------------------------------------------------------------------------


class TestProjectProjection:
    def test_id_and_slug_come_from_the_display_row_not_the_type_id_text(self, db, tmp_path):
        """Textual id ``005-text-slug``, display row (1, ``p02-widget``),
        metadata id ``P09`` / slug ``meta-slug``. The old project branch split
        the type_id, so it projected ``005`` / ``text-slug``."""
        entity_uuid = db.register_entity(
            "project", name="Widget", seq=1, slug="p02-widget",
            metadata={"id": "P09", "slug": "meta-slug", "features": [], "milestones": []},
            project_id="__unknown__",
        )
        type_id = _store_under(db, entity_uuid, "project", "005-text-slug")

        meta = _projected(db, type_id, tmp_path / "projects" / "005-text-slug")

        assert (meta["id"], meta["slug"]) == ("001", "p02-widget")

    def test_legacy_project_reads_its_metadata_not_its_type_id_text(self, db, tmp_path, capsys):
        """A legacy project has no display row. ``init_project_state`` has
        always stored ``id``/``slug`` in metadata, and that is what projects —
        here deliberately disagreeing with the id text, which the old branch
        split into ``P004`` / ``entity-db-redesign``."""
        legacy_uuid = seed_legacy_entity(
            db, "project", "P004-entity-db-redesign", "Entity Db Redesign", status="active",
        )
        _set_metadata(db, legacy_uuid, {
            "id": "P044", "slug": "meta-slug", "features": [], "milestones": [],
        })

        meta = _projected(db, "project:P004-entity-db-redesign", tmp_path / "projects" / "P004")

        assert (meta["id"], meta["slug"]) == ("P044", "meta-slug")
        assert "no usable entity_display row" in capsys.readouterr().err

    def test_legacy_project_with_no_metadata_id_projects_its_stored_id_whole(self, db, tmp_path):
        """Old backfill registered ``project:P002`` from a ``.meta.json`` id
        alone, with no metadata. With no display row and no metadata id, the
        stored entity_id IS the id it displays — read whole (design D9), as
        the old split also yielded for a dash-free id."""
        seed_legacy_entity(db, "project", "P002", "Memory Flywheel", status="active")

        meta = _projected(db, "project:P002", tmp_path / "projects" / "P002")

        assert (meta["id"], meta["slug"]) == ("P002", "")


# ---------------------------------------------------------------------------
# backlog.md
# ---------------------------------------------------------------------------


def _table_ids(markdown: str) -> list[str]:
    return [
        line.split("|")[1].strip()
        for line in markdown.splitlines()
        if line.startswith("| ") and not line.startswith("| ID")
    ]


class TestBacklogProjectionOrder:
    def test_rows_with_a_display_row_sort_by_its_seq_not_by_their_text(self, db):
        """``001-alpha`` holds display seq 50 and ``002-beta`` display seq 7:
        text order and seq order disagree, and seq order wins."""
        alpha = db.register_entity("backlog", name="Alpha", seq=50, slug="alpha",
                                   status="open", project_id="__unknown__")
        beta = db.register_entity("backlog", name="Beta", seq=7, slug="beta",
                                  status="open", project_id="__unknown__")
        _store_under(db, alpha, "backlog", "001-alpha")
        _store_under(db, beta, "backlog", "002-beta")

        assert _table_ids(_project_backlog_md(db)) == ["002-beta", "001-alpha"]

    def test_rows_without_a_display_row_follow_in_their_own_id_order(self, db):
        """A legacy row's number exists only inside its id text, so it has no
        seq. The old reader parsed one out and interleaved the rows
        (``00003, 005-e, 00081, 090-n``); now the display-row rows come first
        in seq order and the legacy rows follow, ordered by their own ids
        compared whole."""
        db.register_entity("backlog", name="Ninety", seq=90, slug="n",
                           status="open", project_id="__unknown__")
        db.register_entity("backlog", name="Five", seq=5, slug="e",
                           status="open", project_id="__unknown__")
        seed_legacy_entity(db, "backlog", "00081", "Legacy eighty-one", status="open")
        seed_legacy_entity(db, "backlog", "00003", "Legacy three", status="open")

        assert _table_ids(_project_backlog_md(db)) == ["005-e", "090-n", "00003", "00081"]


# ---------------------------------------------------------------------------
# Static: the touched readers take no id apart
# ---------------------------------------------------------------------------

_SEPARATOR_METHODS = {"split", "rsplit", "partition", "rpartition"}


def _separator_splits(function) -> list[str]:
    """Every ``x.split(sep)`` / ``x.partition(sep)`` with a ``-`` or ``:``
    separator inside *function* — the receiver name does not matter, which is
    how ``id_and_slug.partition("-")`` and ``value.split("-", 1)`` escaped the
    receiver-keyed inventory scan."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _SEPARATOR_METHODS
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in {"-", ":"}
        ):
            found.append(ast.unparse(node))
    return found


@pytest.mark.parametrize("function", [
    wss._read_entity_display,
    wss._project_meta_json,
    wss._project_backlog_md,
], ids=lambda f: f.__name__)
def test_projection_readers_split_no_identity_text(function):
    assert _separator_splits(function) == []
