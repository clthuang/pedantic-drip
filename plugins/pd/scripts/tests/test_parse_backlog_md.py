"""Feature 110 Task 12.4 — Tests for ``parse_backlog_md.py`` apply mode.

Verifies the apply-mode contract (per Task 12.4 DoD):
  * ``--apply`` invokes ``update_entity`` for existing rows whose
    metadata-subset differs from the parsed record.
  * ``--apply`` invokes ``register_entity`` defensively for rows
    missing from the DB.
  * Re-running ``--apply`` against an unchanged DB is a no-op
    (idempotent).
  * ``_metadata_subset`` omits None values (preserves existing keys
    under ``update_entity``'s shallow-merge).
  * ``_has_drift`` distinguishes equal vs. divergent subsets.

The tests run against an in-memory ``EntityDatabase`` so no live DB is
touched. Pytest discovers this file via the existing
``plugins/pd/scripts/tests/`` directory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Path setup: import the script + entity_registry modules.
_SCRIPT_DIR = Path(__file__).resolve().parents[1]
_HOOKS_LIB = (
    Path(__file__).resolve().parents[2] / "hooks" / "lib"
)
for _p in (_SCRIPT_DIR, _HOOKS_LIB):
    sp = str(_p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import parse_backlog_md  # noqa: E402
from entity_registry.database import EntityDatabase  # noqa: E402
from entity_registry.test_helpers import (  # noqa: E402
    TEST_PROJECT_ID,
    bootstrap_test_workspace,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    """In-memory EntityDatabase with workspace bootstrapped."""
    database = EntityDatabase(":memory:")
    bootstrap_test_workspace(database)
    yield database
    database.close()


# ---------------------------------------------------------------------------
# Pure-function tests (no DB needed)
# ---------------------------------------------------------------------------


def test_metadata_subset_omits_none_values():
    """``_metadata_subset`` drops keys whose parsed value is None.

    Rationale: ``update_entity`` shallow-merges metadata, so emitting a
    None value would clobber a key the entity already carries.
    """
    rec = {
        "entity_id": "00400",
        "format": "table_row",
        "section": None,
        "section_intro": None,
        "subsection": None,
        "name": "test",
    }
    sub = parse_backlog_md._metadata_subset(rec)
    assert sub == {"format": "table_row"}
    assert "section" not in sub
    assert "section_intro" not in sub
    assert "subsection" not in sub


def test_metadata_subset_keeps_all_present_keys():
    """All non-None keys round-trip into the subset."""
    rec = {
        "entity_id": "00500",
        "format": "bullet_item",
        "section": "From Feature 99",
        "section_intro": "Intro text",
        "subsection": "MED findings",
        "name": "test",
    }
    sub = parse_backlog_md._metadata_subset(rec)
    assert sub == {
        "format": "bullet_item",
        "section": "From Feature 99",
        "section_intro": "Intro text",
        "subsection": "MED findings",
    }


def test_has_drift_returns_false_on_equal_subset():
    """When existing metadata already carries the parsed values, drift = False."""
    existing = {
        "format": "table_row",
        "description": "Other key preserved",
    }
    target = {"format": "table_row"}
    assert parse_backlog_md._has_drift(existing, target) is False


def test_has_drift_returns_true_on_missing_key():
    """Missing key in existing metadata triggers drift."""
    existing = {"description": "no format here"}
    target = {"format": "table_row"}
    assert parse_backlog_md._has_drift(existing, target) is True


def test_has_drift_returns_true_on_value_mismatch():
    """Different value for same key triggers drift."""
    existing = {"format": "bullet_item"}
    target = {"format": "table_row"}
    assert parse_backlog_md._has_drift(existing, target) is True


# ---------------------------------------------------------------------------
# Apply-mode DB tests
# ---------------------------------------------------------------------------


def test_apply_mode_updates_existing_entity(db, monkeypatch):
    """``apply_records`` updates metadata on a pre-existing backlog entity."""
    # Pre-register a backlog entity WITHOUT format metadata.
    db.register_entity(
        entity_type="backlog",
        entity_id="00010-existing",
        name="Existing item",
        project_id=TEST_PROJECT_ID,
        status="open",
        metadata={"description": "Pre-existing description"},
    )

    # Stub the EntityDatabase import inside apply_records to point at our
    # in-memory db. We monkey-patch the module's import chain by inserting
    # the in-memory db lookup before apply_records imports its own.
    _monkeypatch_apply_db(monkeypatch, db)

    records = [{
        "entity_id": "00010-existing",
        "format": "table_row",
        "section": None,
        "section_intro": None,
        "subsection": None,
        "name": "Existing item",
    }]

    result = parse_backlog_md.apply_records(records, db_path=":memory:")
    assert result["updated"] == 1
    assert result["inserted"] == 0
    assert result["failed"] == 0

    # Verify the metadata was merged (description preserved, format added).
    rows = db.list_entities(entity_type="backlog")
    matching = [r for r in rows if r["entity_id"] == "00010-existing"]
    assert len(matching) == 1
    md = json.loads(matching[0]["metadata"])
    assert md.get("format") == "table_row"
    assert md.get("description") == "Pre-existing description"


def test_apply_mode_idempotent(db, monkeypatch):
    """Re-running ``apply_records`` against the same DB is a no-op."""
    # Pre-register with the exact metadata we'll try to apply.
    db.register_entity(
        entity_type="backlog",
        entity_id="00020-idempotent",
        name="Idempotent test",
        project_id=TEST_PROJECT_ID,
        status="open",
        metadata={
            "description": "x",
            "format": "table_row",
        },
    )

    _monkeypatch_apply_db(monkeypatch, db)

    records = [{
        "entity_id": "00020-idempotent",
        "format": "table_row",
        "section": None,
        "section_intro": None,
        "subsection": None,
        "name": "Idempotent test",
    }]

    # First run: drift is False (format already matches), so skipped.
    result1 = parse_backlog_md.apply_records(records, db_path=":memory:")
    assert result1["skipped"] == 1
    assert result1["updated"] == 0
    assert result1["inserted"] == 0
    assert result1["failed"] == 0

    # Second run: same result (still skipped).
    result2 = parse_backlog_md.apply_records(records, db_path=":memory:")
    assert result2 == result1, "Re-running --apply must be a no-op"


def test_apply_mode_inserts_missing_entity(db, monkeypatch):
    """Defensive insert: rows missing from DB are registered."""
    _monkeypatch_apply_db(monkeypatch, db)

    # Use {seq}-{slug} format per feature 110 Group 2 register_entity
    # contract (entity_id MUST match ^\d+-.+ post-migration-13).
    records = [{
        "entity_id": "00099-new-row",
        "format": "bullet_item",
        "section": "From Feature 99 Pre-Release QA Findings",
        "section_intro": None,
        "subsection": "MED findings",
        "name": "New backlog row backfilled from markdown",
    }]

    result = parse_backlog_md.apply_records(records, db_path=":memory:")
    assert result["inserted"] == 1
    assert result["updated"] == 0
    assert result["failed"] == 0

    rows = db.list_entities(entity_type="backlog")
    matching = [r for r in rows if r["entity_id"] == "00099-new-row"]
    assert len(matching) == 1
    md = json.loads(matching[0]["metadata"])
    assert md.get("format") == "bullet_item"
    assert md.get("section") == "From Feature 99 Pre-Release QA Findings"
    assert md.get("subsection") == "MED findings"


def test_apply_mode_double_run_after_insert_is_noop(db, monkeypatch):
    """End-to-end idempotency: insert then re-apply records yields no
    additional writes.
    """
    _monkeypatch_apply_db(monkeypatch, db)

    records = [{
        "entity_id": "00200-end-to-end",
        "format": "table_row",
        "section": None,
        "section_intro": None,
        "subsection": None,
        "name": "End-to-end idempotency check",
    }]

    # First run: inserts.
    r1 = parse_backlog_md.apply_records(records, db_path=":memory:")
    assert r1["inserted"] == 1

    # Second run: existing entity matches subset → skipped.
    r2 = parse_backlog_md.apply_records(records, db_path=":memory:")
    assert r2["inserted"] == 0
    assert r2["updated"] == 0
    assert r2["skipped"] == 1
    assert r2["failed"] == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _monkeypatch_apply_db(monkeypatch, db):
    """Make ``apply_records`` use the supplied in-memory ``db``.

    ``apply_records`` constructs an ``EntityDatabase`` from
    ``db_path``; we redirect that constructor to return our fixture
    instance regardless of the ``db_path`` argument.

    Because apply_records imports lazily (``from entity_registry.database
    import EntityDatabase`` inside the function body), patching
    ``db_module.EntityDatabase`` is sufficient — monkeypatch restores
    on test teardown.
    """
    from entity_registry import database as db_module

    class _StubEntityDatabase:
        def __new__(cls, *args, **kwargs):
            return db

    monkeypatch.setattr(db_module, "EntityDatabase", _StubEntityDatabase)
