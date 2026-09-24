"""C3 — fail-closed completeness guard on allocation.

``next_sequence_value`` refuses a bucket — the allocation's
``(kind, workspace_uuid)`` — that holds an entity breaking the display-row
invariant: no ``entity_display`` row and not exempt. Such an entity's number
lives only in its ``entity_id`` text, which the structural census cannot
see, so allocating anyway could hand that number out a second time.

**Every test builds a FRESH database** (same rule as
``test_census_and_issuance.py``): the allocator increments its counter on
every call, so a shared fixture would drift between tests and let a
counter assertion pass for the wrong reason.

**Every "does not refuse" test carries a refusing control** in the same
database. Without the guard, every allocation succeeds, so "no exception"
alone would pass with no guard at all.
"""
from __future__ import annotations

import sqlite3
import uuid as _uuid

import pytest

from doctor.checks import check_display_row_invariant
from entity_registry.database import EntityDatabase, IncompleteBucketError
from entity_registry.test_helpers import seed_legacy_entity

_DB_FILE = "c3.db"


def _add_workspace(db: EntityDatabase, label: str) -> str:
    workspace_uuid = str(_uuid.uuid4())
    now = db._now_iso()
    db._conn.execute(
        "INSERT INTO workspaces(uuid, project_id_legacy, project_root, "
        "created_at, updated_at) VALUES(?,?,?,?,?)",
        (workspace_uuid, f"__{label}_{workspace_uuid[:8]}__", f"/{label}", now, now),
    )
    db._conn.commit()
    return workspace_uuid


def _fresh_db(tmp_path) -> tuple[EntityDatabase, str]:
    db = EntityDatabase(str(tmp_path / _DB_FILE))
    return db, _add_workspace(db, "c3")


def _register(db: EntityDatabase, workspace_uuid: str, kind: str, seq: int, slug: str) -> str:
    """A complete entity: registration always writes its entity_display row."""
    return db.register_entity(kind, seq=seq, slug=slug, name=slug,
                              workspace_uuid=workspace_uuid)


def _register_display_less(db: EntityDatabase, workspace_uuid: str, kind: str,
                           seq: int, slug: str) -> str:
    """The violation: a non-legacy sequence-kind entity with no display row —
    what a pre-Wave-2 non-strict writer left behind."""
    entity_uuid = _register(db, workspace_uuid, kind, seq, slug)
    db._conn.execute("DELETE FROM entity_display WHERE uuid = ?", (entity_uuid,))
    db._conn.commit()
    return entity_uuid


def _register_brainstorm(db: EntityDatabase, workspace_uuid: str, stem: str) -> str:
    """A brainstorm's identity is its stem; it registers with no display row."""
    return db.register_entity("brainstorm", display_id=stem, name=stem,
                              workspace_uuid=workspace_uuid)


def _soft_delete(db: EntityDatabase, entity_uuid: str) -> None:
    db._conn.execute("UPDATE entities SET is_deleted = 1 WHERE uuid = ?", (entity_uuid,))
    db._conn.commit()


def _set_counter(db: EntityDatabase, workspace_uuid: str, kind: str, next_val: int) -> None:
    db._conn.execute(
        "INSERT OR REPLACE INTO sequences(workspace_uuid, entity_type, next_val) "
        "VALUES(?,?,?)", (workspace_uuid, kind, next_val))
    db._conn.commit()


def _counter(db: EntityDatabase, workspace_uuid: str, kind: str) -> int | None:
    row = db._conn.execute(
        "SELECT next_val FROM sequences WHERE workspace_uuid = ? AND entity_type = ?",
        (workspace_uuid, kind)).fetchone()
    return None if row is None else row[0]


def _sequences_snapshot(db: EntityDatabase) -> list[tuple]:
    return [tuple(row) for row in db._conn.execute(
        "SELECT workspace_uuid, entity_type, next_val FROM sequences "
        "ORDER BY workspace_uuid, entity_type")]


class TestEmptyBucket:
    def test_fresh_database_allocates_one(self, tmp_path):
        """An empty bucket is complete: no census maximum means zero, an
        absent counter starts at one."""
        db, ws = _fresh_db(tmp_path)
        assert db.next_sequence_value(entity_type="feature", workspace_uuid=ws) == 1
        assert _counter(db, ws, "feature") == 2

        # Control: the same bucket, no longer complete, refuses.
        _register_display_less(db, ws, "feature", 1, "lost")
        with pytest.raises(IncompleteBucketError):
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)
        assert _counter(db, ws, "feature") == 2


class TestRefusal:
    def test_display_less_entity_refuses_and_the_counter_does_not_move(self, tmp_path):
        """The plan's Verify: assert the counter, not just the exception.

        Without the guard this bucket allocates 7 — max(counter 7, census
        5 + 1) — and the counter moves to 8.
        """
        db, ws = _fresh_db(tmp_path)
        _register(db, ws, "feature", 5, "kept")
        _register_display_less(db, ws, "feature", 6, "lost")
        _set_counter(db, ws, "feature", 7)
        before = _sequences_snapshot(db)

        with pytest.raises(IncompleteBucketError) as excinfo:
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)

        assert _sequences_snapshot(db) == before
        assert _counter(db, ws, "feature") == 7
        refusal = excinfo.value
        assert (refusal.kind, refusal.workspace_uuid) == ("feature", ws)
        assert refusal.type_ids == ["feature:006-lost"]
        assert "feature:006-lost" in str(refusal)

    def test_refusing_a_counterless_bucket_leaves_no_counter_behind(self, tmp_path):
        """No sequences row yet. Without the guard the census (5) seeds a
        counter and 6 is issued; refusing must not insert that row either."""
        db, ws = _fresh_db(tmp_path)
        _register(db, ws, "feature", 5, "kept")
        _register_display_less(db, ws, "feature", 9, "lost")

        with pytest.raises(IncompleteBucketError):
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)

        assert _counter(db, ws, "feature") is None

    def test_the_refusal_names_every_offending_entity(self, tmp_path):
        db, ws = _fresh_db(tmp_path)
        _register_display_less(db, ws, "feature", 2, "second")
        _register_display_less(db, ws, "feature", 1, "first")
        _set_counter(db, ws, "feature", 3)

        with pytest.raises(IncompleteBucketError) as excinfo:
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)

        assert excinfo.value.type_ids == ["feature:001-first", "feature:002-second"]


class TestExemptions:
    """Exempt rows neither satisfy nor violate the guard (B8's invariant as
    restated by Wave 2 D3)."""

    def test_a_display_less_legacy_row_does_not_refuse(self, tmp_path):
        db, ws = _fresh_db(tmp_path)
        seed_legacy_entity(db, "feature", "00019", "legacy", workspace_uuid=ws)
        # B4's high-water sweep reserved the legacy number in the counter.
        _set_counter(db, ws, "feature", 20)

        assert db.next_sequence_value(entity_type="feature", workspace_uuid=ws) == 20

        # Control: the guard is live on this very bucket.
        _register_display_less(db, ws, "feature", 21, "lost")
        with pytest.raises(IncompleteBucketError) as excinfo:
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)
        assert excinfo.value.type_ids == ["feature:021-lost"]
        assert _counter(db, ws, "feature") == 21

    def test_a_brainstorm_row_does_not_refuse(self, tmp_path):
        """Brainstorms are display-less by design. Nothing allocates their
        numbers today, but a guard that counted them would refuse that bucket
        forever the first time anything did."""
        db, ws = _fresh_db(tmp_path)
        _register_brainstorm(db, ws, "20260101-000001-idea")
        _set_counter(db, ws, "brainstorm", 3)

        assert db.next_sequence_value(entity_type="brainstorm", workspace_uuid=ws) == 3

        # Control: the same display-less shape under a sequence kind refuses,
        # so the kind is what exempted the brainstorm.
        _register_display_less(db, ws, "feature", 1, "lost")
        with pytest.raises(IncompleteBucketError):
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)

    def test_a_soft_deleted_row_does_not_refuse(self, tmp_path):
        """check_display_row_invariant exempts is_deleted as well, and the
        guard enforces that same invariant, not a paraphrase of it."""
        db, ws = _fresh_db(tmp_path)
        _soft_delete(db, _register_display_less(db, ws, "feature", 4, "deleted"))
        _set_counter(db, ws, "feature", 5)

        assert db.next_sequence_value(entity_type="feature", workspace_uuid=ws) == 5

        _register_display_less(db, ws, "feature", 6, "lost")
        with pytest.raises(IncompleteBucketError) as excinfo:
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)
        assert excinfo.value.type_ids == ["feature:006-lost"]


class TestCounterlessExemptBucket:
    def test_legacy_rows_without_a_counter_are_still_refused(self, tmp_path):
        """The guard passes a bucket whose only rows are exempt, but a legacy
        row's number is reserved by the counter alone. With no counter the
        allocator still refuses (C2's refusal, not C3's) rather than issue 1
        over the legacy number. The test this refusal had before C3 now
        exercises the guard instead, so it is pinned here."""
        db, ws = _fresh_db(tmp_path)
        seed_legacy_entity(db, "project", "P001", "P001", workspace_uuid=ws)

        with pytest.raises(ValueError, match="unknowable from structure") as excinfo:
            db.next_sequence_value(entity_type="project", workspace_uuid=ws)

        assert not isinstance(excinfo.value, IncompleteBucketError)
        assert _counter(db, ws, "project") is None


class TestBucketScope:
    def test_violations_in_other_buckets_do_not_refuse_this_one(self, tmp_path):
        db, ws = _fresh_db(tmp_path)
        other_ws = _add_workspace(db, "other")
        _register(db, ws, "feature", 4, "kept")
        _register_display_less(db, ws, "task", 50, "lost-task")
        _register_display_less(db, other_ws, "feature", 500, "lost-elsewhere")

        assert db.next_sequence_value(entity_type="feature", workspace_uuid=ws) == 5

        # Controls: each of those buckets does refuse, so the guard ran and
        # scoped itself rather than never firing.
        with pytest.raises(IncompleteBucketError) as other_kind:
            db.next_sequence_value(entity_type="task", workspace_uuid=ws)
        assert other_kind.value.type_ids == ["task:050-lost-task"]
        with pytest.raises(IncompleteBucketError) as other_workspace:
            db.next_sequence_value(entity_type="feature", workspace_uuid=other_ws)
        assert other_workspace.value.type_ids == ["feature:500-lost-elsewhere"]


class TestConnectionAfterRefusal:
    def test_the_refusal_releases_the_write_lock(self, tmp_path):
        db, ws = _fresh_db(tmp_path)
        _register_display_less(db, ws, "feature", 1, "lost")

        with pytest.raises(IncompleteBucketError):
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)

        assert not db._conn.in_transaction
        # A transaction left open would still hold the RESERVED lock, and a
        # second writer with no busy timeout would fail at once.
        other = sqlite3.connect(str(tmp_path / _DB_FILE), timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.execute("ROLLBACK")
        finally:
            other.close()

    def test_a_later_write_on_the_same_connection_commits(self, tmp_path):
        db, ws = _fresh_db(tmp_path)
        _register_display_less(db, ws, "feature", 1, "lost")

        with pytest.raises(IncompleteBucketError):
            db.next_sequence_value(entity_type="feature", workspace_uuid=ws)

        assert db.next_sequence_value(entity_type="task", workspace_uuid=ws) == 1
        # Seen from a second connection, so the write was committed rather
        # than absorbed into a transaction the refusal left open.
        other = sqlite3.connect(str(tmp_path / _DB_FILE))
        try:
            assert other.execute(
                "SELECT next_val FROM sequences "
                "WHERE workspace_uuid = ? AND entity_type = 'task'", (ws,),
            ).fetchone() == (2,)
        finally:
            other.close()


class TestOneInvariant:
    def test_guard_and_doctor_check_agree_on_every_row_shape(self, tmp_path):
        """One invariant, two enforcers: the doctor check reports it across
        the registry, the guard refuses one bucket at a time. For every
        bucket, the guard must refuse exactly the entities the check reports
        in that bucket — no more (an exemption the guard forgot) and no fewer
        (a clause only the check applies)."""
        db, ws = _fresh_db(tmp_path)
        other_ws = _add_workspace(db, "other")
        _register(db, ws, "feature", 1, "complete")
        _register_display_less(db, ws, "feature", 2, "lost")
        seed_legacy_entity(db, "feature", "00003", "legacy", workspace_uuid=ws)
        _soft_delete(db, _register_display_less(db, ws, "feature", 4, "deleted"))
        _register_brainstorm(db, ws, "20260101-000001-idea")
        _register_display_less(db, ws, "task", 5, "lost-task")
        _register(db, ws, "task", 6, "complete-task")
        _register_display_less(db, other_ws, "feature", 7, "lost-elsewhere")
        _register(db, other_ws, "project", 8, "complete-project")

        check_conn = sqlite3.connect(str(tmp_path / _DB_FILE))
        try:
            reported = {issue.entity for issue in check_display_row_invariant(check_conn).issues}
        finally:
            check_conn.close()
        # Pinned so a check that went silent cannot make the agreement vacuous.
        assert reported == {"feature:002-lost", "task:005-lost-task",
                            "feature:007-lost-elsewhere"}

        bucket_of = {
            row[0]: (row[1], row[2]) for row in db._conn.execute(
                "SELECT type_id, kind, workspace_uuid FROM entities")
        }
        for bucket in sorted(set(bucket_of.values())):
            kind, bucket_ws = bucket
            # A counter per bucket, so the only refusal left is the guard's.
            _set_counter(db, bucket_ws, kind, 100)
            expected = sorted(t for t in reported if bucket_of[t] == bucket)
            try:
                db.next_sequence_value(entity_type=kind, workspace_uuid=bucket_ws)
                refused: list[str] = []
            except IncompleteBucketError as refusal:
                refused = refusal.type_ids
            assert refused == expected, f"bucket {bucket}"
