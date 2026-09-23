"""C1 structural census + C2 monotonic issuance.

**Every test builds a FRESH database.** The allocator increments its
counter on every call, so a reused fixture returns 134 then 135 and looks
correct whether or not the implementation changed. The plan calls this
out by name; a shared fixture here would make the whole module decorative.
"""
from __future__ import annotations

import uuid as _uuid

import pytest

from entity_registry.database import EntityDatabase, _census_max


def _db(tmp_path, name="e.db"):
    db = EntityDatabase(str(tmp_path / name))
    ws = str(_uuid.uuid4())
    now = db._now_iso()
    db._conn.execute(
        "INSERT INTO workspaces(uuid, project_id_legacy, project_root, "
        "created_at, updated_at) VALUES(?,?,?,?,?)",
        (ws, f"__t_{ws[:8]}__", str(tmp_path), now, now),
    )
    db._conn.commit()
    return db, ws


def _seed(db, ws, kind, entity_id, *, seq=None, slug="s", status="active",
          is_archived=0):
    db.register_entity(kind, entity_id=entity_id, name=entity_id,
                       workspace_uuid=ws, status=status,
                       _strict_id_format=False)
    row = db._conn.execute(
        "SELECT uuid FROM entities WHERE type_id=? AND workspace_uuid=?",
        (f"{kind}:{entity_id}", ws)).fetchone()
    if seq is not None:
        db._conn.execute(
            "INSERT OR REPLACE INTO entity_display(uuid, seq, slug) VALUES(?,?,?)",
            (row[0], seq, slug))
    if is_archived:
        db._conn.execute("UPDATE entities SET is_archived=1 WHERE uuid=?", (row[0],))
    db._conn.commit()
    return row[0]


class TestCensus:
    def test_empty_bucket_is_none_not_zero(self, tmp_path):
        """0 would mean "the highest number is zero" and make the next value
        1 for a bucket that may hold legacy rows."""
        db, ws = _db(tmp_path)
        assert _census_max(db._conn, kind="feature", workspace_uuid=ws) is None

    def test_reads_seq_from_structure(self, tmp_path):
        db, ws = _db(tmp_path)
        _seed(db, ws, "feature", "003-c", seq=3)
        _seed(db, ws, "feature", "007-g", seq=7)
        assert _census_max(db._conn, kind="feature", workspace_uuid=ws) == 7

    def test_disagreeing_text_is_ignored(self, tmp_path):
        """The id text says 999; the display row says 4. Structure wins.

        A census that still parsed text would return 999 here and pass any
        assertion phrased as "returns the max".
        """
        db, ws = _db(tmp_path)
        _seed(db, ws, "feature", "999-lying-text", seq=4)
        assert _census_max(db._conn, kind="feature", workspace_uuid=ws) == 4

    def test_legacy_project_shape_is_counted_when_it_has_a_display_row(self, tmp_path):
        """The plan's C1 Verify: a bucket whose only rows are P{NNN}-{slug}
        WITH display rows returns N. The old regex returned nothing for
        these — that is the original incident."""
        db, ws = _db(tmp_path)
        _seed(db, ws, "project", "001-p004-entity-db-redesign", seq=4)
        assert _census_max(db._conn, kind="project", workspace_uuid=ws) == 4

    def test_archived_rows_still_count(self, tmp_path):
        """A number is spent when issued. Archiving the entity holding the
        highest number must not hand it out again."""
        db, ws = _db(tmp_path)
        _seed(db, ws, "feature", "009-archived", seq=9, is_archived=1)
        assert _census_max(db._conn, kind="feature", workspace_uuid=ws) == 9

    def test_display_less_rows_are_invisible(self, tmp_path):
        """Legacy rows have no display row by definition; the stored counter
        is what reserves their numbers, not this."""
        db, ws = _db(tmp_path)
        _seed(db, ws, "project", "001-p004-entity-db-redesign", seq=None)
        assert _census_max(db._conn, kind="project", workspace_uuid=ws) is None

    def test_other_kinds_and_workspaces_do_not_leak(self, tmp_path):
        db, ws = _db(tmp_path)
        other = str(_uuid.uuid4())
        now = db._now_iso()
        db._conn.execute(
            "INSERT INTO workspaces(uuid, project_id_legacy, project_root, "
            "created_at, updated_at) VALUES(?,?,?,?,?)",
            (other, "__other__", "/other", now, now))
        db._conn.commit()
        _seed(db, ws, "feature", "005-f", seq=5)
        _seed(db, ws, "task", "050-t", seq=50)
        _seed(db, other, "feature", "500-elsewhere", seq=500)
        assert _census_max(db._conn, kind="feature", workspace_uuid=ws) == 5


class TestMonotonicIssuance:
    def test_fresh_bucket_starts_at_one(self, tmp_path):
        db, ws = _db(tmp_path)
        assert db.next_sequence_value(entity_type="feature", workspace_uuid=ws) == 1

    def test_bootstrap_uses_the_census_not_text(self, tmp_path):
        """No sequences row; the id text says 999 and the display row says 6.
        Bootstrapping from text would issue 1000."""
        db, ws = _db(tmp_path)
        _seed(db, ws, "feature", "999-lying-text", seq=6)
        assert db.next_sequence_value(entity_type="feature", workspace_uuid=ws) == 7

    def test_counter_below_the_census_is_repaired(self, tmp_path):
        """A pre-C20a rebuild could leave the counter BELOW reality. Trusting
        it alone reissues a live number."""
        db, ws = _db(tmp_path)
        _seed(db, ws, "feature", "010-ten", seq=10)
        db._conn.execute(
            "INSERT OR REPLACE INTO sequences(workspace_uuid, entity_type, next_val) "
            "VALUES(?,?,?)", (ws, "feature", 4))
        db._conn.commit()
        assert db.next_sequence_value(entity_type="feature", workspace_uuid=ws) == 11

    def test_counter_above_the_census_is_honoured(self, tmp_path):
        """The live project bucket's exact shape: every row legacy, so the
        census is None, and the stored counter is the only reservation.
        Taking the census alone would restart at 1 and collide with P001."""
        db, ws = _db(tmp_path)
        _seed(db, ws, "project", "001-p001", seq=None)
        _seed(db, ws, "project", "001-p004-entity-db-redesign", seq=None)
        db._conn.execute(
            "INSERT OR REPLACE INTO sequences(workspace_uuid, entity_type, next_val) "
            "VALUES(?,?,?)", (ws, "project", 5))
        db._conn.commit()
        assert _census_max(db._conn, kind="project", workspace_uuid=ws) is None
        assert db.next_sequence_value(entity_type="project", workspace_uuid=ws) == 5

    def test_archiving_the_top_entity_does_not_lower_the_next_value(self, tmp_path):
        """The plan's monotonicity pin."""
        db, ws = _db(tmp_path)
        _seed(db, ws, "feature", "020-top", seq=20)
        first = db.next_sequence_value(entity_type="feature", workspace_uuid=ws)
        db._conn.execute("UPDATE entities SET is_archived=1 WHERE entity_id='020-top'")
        db._conn.commit()
        second = db.next_sequence_value(entity_type="feature", workspace_uuid=ws)
        assert second > first, (
            f"issued {second} after {first}; archiving must not free a number"
        )

    def test_issuance_never_repeats(self, tmp_path):
        db, ws = _db(tmp_path)
        issued = [
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)
            for _ in range(25)
        ]
        assert issued == sorted(issued)
        assert len(set(issued)) == len(issued)

    def test_a_gap_is_never_reclaimed(self, tmp_path):
        """Gaps are permitted by contract. Reclaiming one reissues a number
        whose entity may have been deleted but whose directory and branch
        still exist on disk."""
        db, ws = _db(tmp_path)
        for _ in range(5):
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)
        _seed(db, ws, "feature", "002-kept", seq=2)
        assert db.next_sequence_value(entity_type="feature", workspace_uuid=ws) == 6
