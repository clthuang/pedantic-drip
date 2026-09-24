"""Wave 2: registration takes structured identity — (seq, slug) or display_id.

Step 5 deleted the entity_id text form; there is no other way in.
"""
import pytest

from entity_registry.database import EntityDatabase, _UNKNOWN_WORKSPACE_UUID


@pytest.fixture
def db():
    database = EntityDatabase(":memory:")
    yield database
    database.close()


def _display_row(db, entity_uuid):
    return db.get_entity_display(entity_uuid)


def test_seq_and_slug_render_the_id_and_always_write_the_display_row(db):
    entity_uuid = db.register_entity("feature", name="Alpha", seq=7, slug="alpha",
                                     workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    assert db.get_entity("feature:007-alpha")["uuid"] == entity_uuid
    row = _display_row(db, entity_uuid)
    assert (row["seq"], row["slug"]) == (7, "alpha")


def test_display_id_is_stored_verbatim_with_no_display_row(db):
    entity_uuid = db.register_entity("brainstorm", name="Idea", display_id="bs-no-number",
                                     workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    assert db.get_entity("brainstorm:bs-no-number")["uuid"] == entity_uuid
    assert _display_row(db, entity_uuid) is None


@pytest.mark.parametrize("identity", [
    {},                                                    # none
    {"seq": 1, "slug": "a", "display_id": "001-a"},        # two forms
    {"seq": 1},                                            # seq without slug
    {"display_id": "001-a"},                               # display_id on a sequence kind
    {"seq": 0, "slug": "a"},                               # no sequence number 0
])
def test_a_feature_takes_exactly_one_well_formed_identity(db, identity):
    with pytest.raises(ValueError):
        db.register_entity("feature", name="X", workspace_uuid=_UNKNOWN_WORKSPACE_UUID, **identity)


def test_a_brainstorm_has_no_sequence_to_take(db):
    with pytest.raises(ValueError):
        db.register_entity("brainstorm", name="X", seq=1, slug="x", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)


def test_upsert_with_seq_and_slug_inserts_then_updates_the_same_row(db):
    first = db.upsert_entity("feature", name="Beta", seq=2, slug="beta",
                             status="active", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    again = db.upsert_entity("feature", name="Beta", seq=2, slug="beta",
                             status="completed", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    assert again == first
    assert db.get_entity("feature:002-beta")["status"] == "completed"
    assert (_display_row(db, first)["seq"], _display_row(db, first)["slug"]) == (2, "beta")


def test_batch_entries_take_seq_and_slug_or_display_id(db):
    feature_uuid, brainstorm_uuid = db.register_entities_batch([
        {"entity_type": "feature", "seq": 3, "slug": "gamma", "name": "Gamma"},
        {"entity_type": "brainstorm", "display_id": "20260101-000001-idea", "name": "Idea"},
    ], workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
    assert db.get_entity("feature:003-gamma")["uuid"] == feature_uuid
    assert _display_row(db, feature_uuid)["seq"] == 3
    assert _display_row(db, brainstorm_uuid) is None


@pytest.mark.parametrize("method", ["register_entity", "upsert_entity"])
def test_name_is_keyword_only(db, method):
    """A stale call with the old entity_id in second place fails when it is
    made, not as a confusing identity error further in."""
    with pytest.raises(TypeError, match="positional argument"):
        getattr(db, method)("feature", "001-a", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
