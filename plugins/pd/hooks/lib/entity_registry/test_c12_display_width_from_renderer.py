"""C12: a displayed number's width comes from the renderer, never from text.

``render_display_seq`` renders the number part of every display id, and
``render_display_id`` is composed from it, so the zero-pad width lives in one
place. ``read_display_identity`` is the one reader of an entity's displayed
``(number, slug)`` — the ``.meta.json`` projection and both frontmatter
surfaces call it. It reads the ``entity_display`` row and renders the number;
the stored ``entity_id`` is compared WHOLE, only to recognise an id stored
unpadded before the renderer existed, and is never taken apart.
"""
from __future__ import annotations

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.id_generator import (
    NON_SEQUENCE_KINDS,
    read_display_identity,
    render_display_id,
    render_display_seq,
)
from entity_registry.test_helpers import seed_legacy_entity


@pytest.fixture
def db():
    database = EntityDatabase(":memory:")
    yield database
    database.close()


def _registered(db, kind: str, seq: int, slug: str, *, stored_entity_id: str | None = None) -> str:
    """Register ``(seq, slug)`` with its display row; with *stored_entity_id*,
    store it under that older text form, as pre-renderer registries hold it."""
    entity_uuid = db.register_entity(kind, name=slug.title(), seq=seq, slug=slug,
                                     project_id="__unknown__")
    if stored_entity_id is not None:
        db._conn.execute(
            "UPDATE entities SET type_id = ?, entity_id = ? WHERE uuid = ?",
            (f"{kind}:{stored_entity_id}", stored_entity_id, entity_uuid),
        )
        db._conn.commit()
    return entity_uuid


class TestRenderDisplaySeq:
    @pytest.mark.parametrize("seq,expected", [
        (1, "001"), (74, "074"), (135, "135"), (1000, "1000"),
    ])
    def test_zero_pads_to_a_minimum_of_three_digits(self, seq, expected):
        assert render_display_seq("feature", seq) == expected

    @pytest.mark.parametrize("kind,seq,slug", [
        ("feature", 74, "sse-event-stream"),
        ("project", 4, "entity-db-redesign"),
        ("backlog", 1000, "x"),
    ])
    def test_every_display_id_starts_with_it(self, kind, seq, slug):
        assert render_display_id(kind, seq, slug) == f"{render_display_seq(kind, seq)}-{slug}"

    def test_non_sequence_kinds_are_refused(self):
        for kind in NON_SEQUENCE_KINDS:
            with pytest.raises(ValueError, match="not a sequence"):
                render_display_seq(kind, 1)

    @pytest.mark.parametrize("seq", [0, -1, "3", 3.0, True, None])
    def test_non_positive_int_seq_is_refused(self, seq):
        with pytest.raises(ValueError):
            render_display_seq("feature", seq)


class TestReadDisplayIdentity:
    def test_a_canonical_id_shows_the_renderers_number(self, db):
        entity_uuid = _registered(db, "feature", 74, "sse-event-stream")
        assert read_display_identity(
            db, entity_uuid, "feature", "074-sse-event-stream",
        ) == ("074", "sse-event-stream")

    @pytest.mark.parametrize("seq,slug", [(74, "sse-event-stream"), (1, "causal-inference-training")])
    def test_an_id_stored_unpadded_keeps_its_unpadded_number(self, db, seq, slug):
        """The live pre-renderer shape: seq 74 stored as ``74-sse-event-stream``."""
        stored = f"{seq}-{slug}"
        entity_uuid = _registered(db, "feature", seq, slug, stored_entity_id=stored)
        assert read_display_identity(db, entity_uuid, "feature", stored) == (str(seq), slug)

    def test_stored_text_that_disagrees_with_the_display_row_decides_nothing(self, db):
        """Number, width and slug all differ from the display row: the row is
        shown, at the renderer's width."""
        entity_uuid = _registered(db, "feature", 42, "display-slug", stored_entity_id="5-textual-slug")
        assert read_display_identity(
            db, entity_uuid, "feature", "5-textual-slug",
        ) == ("042", "display-slug")

    def test_the_unpadded_number_with_another_slug_is_not_the_unpadded_form(self, db):
        entity_uuid = _registered(db, "feature", 74, "display-slug", stored_entity_id="74-other-slug")
        assert read_display_identity(
            db, entity_uuid, "feature", "74-other-slug",
        ) == ("074", "display-slug")

    def test_without_a_stored_id_the_renderers_number_is_shown(self, db):
        entity_uuid = _registered(db, "project", 4, "entity-db-redesign")
        assert read_display_identity(db, entity_uuid, "project", None) == ("004", "entity-db-redesign")

    def test_an_entity_without_a_display_row_reads_as_none(self, db):
        legacy_uuid = seed_legacy_entity(db, "feature", "043-legacy", "Legacy")
        assert read_display_identity(db, legacy_uuid, "feature", "043-legacy") is None

    def test_a_display_row_the_renderer_refuses_reads_as_none(self, db):
        entity_uuid = _registered(db, "feature", 7, "x")
        db._conn.execute("UPDATE entity_display SET seq = 0 WHERE uuid = ?", (entity_uuid,))
        db._conn.commit()
        assert read_display_identity(db, entity_uuid, "feature", "007-x") is None

    def test_no_uuid_reads_as_none(self, db):
        assert read_display_identity(db, None, "feature", "007-x") is None
