"""C19 + C20b: the rebuild carries identity STRUCTURE across the uuid remap
and seeds ``sequences`` from structure plus the stored high-water mark.

C19 — an ``entity_display`` row is carried from the old file onto the
entity's NEW uuid, never re-derived from ``entity_id`` text. The entity
flags travel with it, so B8's invariant ("a display row unless
``is_legacy``") means the same thing on both sides of a rebuild. Dedup
accounting reads the ``kind`` column, never the ``type_id`` prefix.

C20b — ``next_val = max(stored counter, structural census max + 1)``. The
census is C1's (``entity_display.seq`` per ``entities.kind`` x workspace);
the stored counter is the only thing that covers legacy rows, which have no
display row by definition. Two of the Verify cases already hold since C20a
(``12f1b571``) and are kept here as regression pins, labelled as such.

Every test builds its own old file through the real v1 chain, so the old
file's constraints are genuinely in force, then seeds it with raw SQL: the
states under test (a ``P004-slug`` id with a display row, a ``type_id``
whose prefix disagrees with its ``kind``) cannot be registered any more.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from entity_registry import database
from entity_registry import rebuild_tool
from entity_registry import schema_v2
from entity_registry.test_rebuild_tool import _relax_entities_unique_constraint

_NOW = "2026-01-01T00:00:00Z"
_LATER = "2026-01-02T00:00:00Z"
_WORKSPACE = "ws-rebuild"


@pytest.fixture(autouse=True)
def _reset_ddl_registry():
    """``build_staging_database`` registers the axes vocab DDL as production
    behaviour; restore the registry so it cannot leak into later tests
    (the idiom test_rebuild_tool.py uses)."""
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


class _OldFile:
    """A chain-built v1 file, seeded with raw SQL, then rebuilt."""

    def __init__(self, tmp_path, *, relax_unique: bool = False) -> None:
        self._tmp_path = tmp_path
        self.path = str(tmp_path / "old.db")
        database.EntityDatabase(self.path).close()
        self.conn = sqlite3.connect(self.path)
        if relax_unique:
            # Within-workspace duplicate type_ids: the one pathology a live
            # file cannot reach, needed to drive the dedup accounting.
            _relax_entities_unique_constraint(self.conn)
        self.workspace(_WORKSPACE)

    def workspace(self, workspace_uuid: str) -> None:
        self.conn.execute(
            "INSERT INTO workspaces (uuid, project_id_legacy, project_root, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (workspace_uuid, workspace_uuid, f"/tmp/{workspace_uuid}", _NOW, _NOW),
        )

    def entity(
        self, old_uuid: str, kind: str, entity_id: str, *,
        type_id: str | None = None, display: tuple[int, str] | None = None,
        is_legacy: int = 0, is_archived: int = 0, is_deleted: int = 0,
        updated_at: str = _NOW, workspace_uuid: str = _WORKSPACE,
    ) -> None:
        entity_type, lifecycle_class = database._derive_type_and_lifecycle(kind)
        self.conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, name, "
            "status, created_at, updated_at, type, kind, lifecycle_class, "
            "is_legacy, is_archived, is_deleted) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)",
            (old_uuid, workspace_uuid, type_id or f"{kind}:{entity_id}", entity_id,
             entity_id, _NOW, updated_at, entity_type, kind, lifecycle_class,
             is_legacy, is_archived, is_deleted),
        )
        if display is not None:
            seq, slug = display
            self.conn.execute(
                "INSERT INTO entity_display (uuid, seq, slug) VALUES (?, ?, ?)",
                (old_uuid, seq, slug),
            )

    def counter(self, kind: str, next_val: int, *, workspace_uuid: str = _WORKSPACE) -> None:
        self.conn.execute(
            "INSERT INTO sequences (workspace_uuid, entity_type, next_val) VALUES (?, ?, ?)",
            (workspace_uuid, kind, next_val),
        )

    def rebuild(self) -> tuple[str, dict]:
        """Commit, close, and rebuild into a fresh staging file."""
        self.conn.commit()
        self.conn.close()
        staging_path = str(self._tmp_path / "staging.db")
        rebuild_tool.build_staging_database(staging_path)
        report = rebuild_tool.run_backfill(self.path, staging_path)
        return staging_path, report


def _query(staging_path: str, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(staging_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _rebuilt_display(staging_path: str, type_id: str) -> sqlite3.Row:
    """The rebuilt entity's uuid and its display row (``seq`` None if absent)."""
    rows = _query(
        staging_path,
        "SELECT e.uuid, d.seq, d.slug FROM entities e "
        "LEFT JOIN entity_display d ON d.uuid = e.uuid "
        "WHERE e.type_id = ? AND e.workspace_uuid = ?",
        (type_id, _WORKSPACE),
    )
    assert len(rows) == 1, f"expected exactly one rebuilt {type_id}, got {len(rows)}"
    return rows[0]


def _seeded_counters(staging_path: str) -> dict[tuple[str, str], int]:
    return {
        (row["workspace_uuid"], row["entity_type"]): row["next_val"]
        for row in _query(
            staging_path, "SELECT workspace_uuid, entity_type, next_val FROM sequences"
        )
    }


def _next_allocation(staging_path: str, kind: str) -> int:
    """What the allocator issues next from the rebuilt file."""
    rebuilt = database.EntityDatabase(staging_path)
    try:
        return rebuilt.next_sequence_value(entity_type=kind, workspace_uuid=_WORKSPACE)
    finally:
        rebuilt.close()


# ---------------------------------------------------------------------------
# C19 — display rows and flags are carried, not re-parsed
# ---------------------------------------------------------------------------
class TestDisplayRowsCarriedThroughTheRemap:
    def test_p_prefixed_ids_keep_their_exact_seq_and_slug(self, tmp_path):
        """The plan's C19 Verify. ``^(\\d+)-(.+)$`` never matched a leading
        ``P``, so these rows came out of a rebuild with no display row."""
        old = _OldFile(tmp_path)
        old.entity("old-p004", "project", "P004-entity-db-redesign",
                   display=(4, "entity-db-redesign"))
        old.entity("old-p001", "project", "P001-openclaw-gap-analysis",
                   display=(1, "openclaw-gap-analysis"))
        staging_path, _ = old.rebuild()

        p004 = _rebuilt_display(staging_path, "project:P004-entity-db-redesign")
        p001 = _rebuilt_display(staging_path, "project:P001-openclaw-gap-analysis")
        assert (p004["seq"], p004["slug"]) == (4, "entity-db-redesign")
        assert (p001["seq"], p001["slug"]) == (1, "openclaw-gap-analysis")
        # Carried THROUGH the remap: keyed by the new uuid7, not the old uuid.
        assert {p004["uuid"], p001["uuid"]}.isdisjoint({"old-p004", "old-p001"})

    def test_display_row_wins_over_disagreeing_id_text(self, tmp_path):
        """Text says (5, lying-text); structure says (7, true-slug). A
        re-parse reproduces the text, so only the carry passes."""
        old = _OldFile(tmp_path)
        old.entity("old-feature", "feature", "005-lying-text", display=(7, "true-slug"))
        staging_path, _ = old.rebuild()

        rebuilt = _rebuilt_display(staging_path, "feature:005-lying-text")
        assert (rebuilt["seq"], rebuilt["slug"]) == (7, "true-slug")

    def test_display_less_row_is_not_given_one_from_its_text(self, tmp_path):
        """``is_legacy = 0`` with no display row is a bug the old file already
        had, and C3 reports it there. The rebuild must carry it as it is,
        not invent a number from id text."""
        old = _OldFile(tmp_path)
        old.entity("old-feature", "feature", "006-no-display")
        staging_path, _ = old.rebuild()

        assert _rebuilt_display(staging_path, "feature:006-no-display")["seq"] is None

    def test_entity_flags_are_carried(self, tmp_path):
        """The old-file SELECT never read the flag columns, so ``_flag``
        defaulted every one to 0: a rebuild un-archived, un-deleted and
        un-legacied every row. ``is_legacy`` is immutable after insert, so
        the rebuilt 0 could never be put back."""
        old = _OldFile(tmp_path)
        old.entity("old-legacy", "project", "P002", is_legacy=1)
        old.entity("old-archived", "feature", "001-done", display=(1, "done"), is_archived=1)
        old.entity("old-deleted", "feature", "002-gone", display=(2, "gone"), is_deleted=1)
        old.entity("old-plain", "feature", "003-live", display=(3, "live"))
        staging_path, _ = old.rebuild()

        flags = {
            row["type_id"]: (row["is_legacy"], row["is_archived"], row["is_deleted"])
            for row in _query(
                staging_path,
                "SELECT type_id, is_legacy, is_archived, is_deleted FROM entities",
            )
        }
        assert flags == {
            "project:P002": (1, 0, 0),
            "feature:001-done": (0, 1, 0),
            "feature:002-gone": (0, 0, 1),
            "feature:003-live": (0, 0, 0),
        }
        # B8 holds after the rebuild exactly as before it: the legacy row is
        # display-less because it is legacy, not because a write failed.
        assert _rebuilt_display(staging_path, "project:P002")["seq"] is None


# ---------------------------------------------------------------------------
# C19 — kind comes from the kind column, never the type_id prefix
# ---------------------------------------------------------------------------
class TestKindComesFromTheColumn:
    def test_dedup_loss_is_explained_by_the_losers_kind_column(self, tmp_path):
        """The type_id says task; the kind column says feature. Counts are
        keyed by the column, so the count delta lands in the feature bucket.
        Booking the explanation to the type_id prefix put it in 'task' and
        aborted the import on an 'unexplained' delta it had caused itself."""
        old = _OldFile(tmp_path, relax_unique=True)
        old.entity("dup-loser", "feature", "003-dup", type_id="task:003-dup",
                   display=(3, "dup"), updated_at=_NOW)
        old.entity("dup-winner", "feature", "003-dup", type_id="task:003-dup",
                   display=(3, "dup"), updated_at=_LATER)
        _, report = old.rebuild()

        [anomaly] = report["anomalies"]["duplicate_type_id"]
        assert anomaly["old_uuid"] == "dup-loser"
        assert anomaly["kind"] == "feature"
        assert report["counts"]["feature"][_WORKSPACE] == {"old": 2, "new": 1}

    def test_seed_bucket_is_the_kind_column(self, tmp_path):
        """Regression pin: seeding keyed buckets by the column before C19
        too. Kept so the census rewrite cannot start reading the prefix."""
        old = _OldFile(tmp_path)
        old.entity("mislabelled", "feature", "005-x", type_id="task:005-x", display=(5, "x"))
        staging_path, _ = old.rebuild()

        seeded = _seeded_counters(staging_path)
        assert seeded[(_WORKSPACE, "feature")] == 6
        assert (_WORKSPACE, "task") not in seeded


# ---------------------------------------------------------------------------
# C20b — seed = max(stored high-water mark, structural census + 1)
# ---------------------------------------------------------------------------
class TestSeedFromStructureAndTheHighWaterMark:
    def test_p_prefixed_display_row_sets_the_floor(self, tmp_path):
        """C19's Verify on the seed side. The text scan read ``P004-...`` as
        0, so with no counter the bucket was seeded at 1."""
        old = _OldFile(tmp_path)
        old.entity("old-p004", "project", "P004-entity-db-redesign",
                   display=(4, "entity-db-redesign"))
        staging_path, report = old.rebuild()

        assert _seeded_counters(staging_path)[(_WORKSPACE, "project")] == 5
        assert report["sequences_seeded"]["project"][_WORKSPACE] == 5

    def test_disagreeing_id_text_does_not_set_the_floor(self, tmp_path):
        """Text says 999, the display row says 4 — C1's census rule."""
        old = _OldFile(tmp_path)
        old.entity("old-feature", "feature", "999-lying-text", display=(4, "lying-text"))
        staging_path, _ = old.rebuild()

        assert _seeded_counters(staging_path)[(_WORKSPACE, "feature")] == 5

    def test_census_counts_a_dedup_losers_display_row(self, tmp_path):
        """A number is spent the moment it is issued (C1). The loser's row
        is not carried — its survivor's is — but its seq still raises the
        floor, or the rebuilt counter could hand 12 out again."""
        old = _OldFile(tmp_path, relax_unique=True)
        old.entity("dup-loser", "feature", "003-dup", display=(12, "dup-old"),
                   updated_at=_NOW)
        old.entity("dup-winner", "feature", "003-dup", display=(3, "dup"),
                   updated_at=_LATER)
        staging_path, _ = old.rebuild()

        survivor = _rebuilt_display(staging_path, "feature:003-dup")
        assert (survivor["seq"], survivor["slug"]) == (3, "dup")
        assert _seeded_counters(staging_path)[(_WORKSPACE, "feature")] == 13

    def test_counter_above_the_census_max_is_not_lowered(self, tmp_path):
        """REGRESSION PIN — passes since C20a (12f1b571), before C20b."""
        old = _OldFile(tmp_path)
        for seq in (1, 2, 3):
            old.entity(f"old-f{seq}", "feature", f"00{seq}-f{seq}", display=(seq, f"f{seq}"))
        old.counter("feature", 10)
        staging_path, _ = old.rebuild()

        assert _seeded_counters(staging_path)[(_WORKSPACE, "feature")] == 10
        assert _next_allocation(staging_path, "feature") == 10

    def test_counter_only_bucket_keeps_its_reservation(self, tmp_path):
        """REGRESSION PIN — passes since C20a (12f1b571), before C20b.

        Buckets come from entities AND sequences: a counter with zero entity
        rows, in a populated workspace or an empty one, is still a
        reservation."""
        old = _OldFile(tmp_path)
        old.workspace("ws-without-entities")
        old.entity("old-feature", "feature", "001-f", display=(1, "f"))
        old.counter("bug", 42)
        old.counter("feature", 7, workspace_uuid="ws-without-entities")
        staging_path, report = old.rebuild()

        seeded = _seeded_counters(staging_path)
        assert seeded[(_WORKSPACE, "bug")] == 42
        assert seeded[("ws-without-entities", "feature")] == 7
        assert report["sequences_seeded"]["bug"][_WORKSPACE] == 42

    def test_legacy_number_stays_reserved_by_the_stored_counter(self, tmp_path):
        """REGRESSION PIN for the structural census's blind spot.

        A legacy row has no display row, so the census cannot see P007's 7.
        B4 raised the counter to 8 for exactly that reason; the seed keeps
        it rather than falling to census(001) + 1 = 2."""
        old = _OldFile(tmp_path)
        old.entity("old-legacy", "project", "P007-old-project", is_legacy=1)
        old.entity("old-fresh", "project", "001-fresh", display=(1, "fresh"))
        old.counter("project", 8)
        staging_path, _ = old.rebuild()

        assert _seeded_counters(staging_path)[(_WORKSPACE, "project")] == 8
        assert _next_allocation(staging_path, "project") == 8

    @pytest.mark.parametrize("kind, entity_id, is_legacy, refusal", [
        # legacy: exempt from C3's guard, so the counterless refusal names
        # the repair
        ("project", "P003", 1, ValueError),
        # display-less bug row: C3's completeness guard refuses it first
        ("task", "004-text-only", 0, database.IncompleteBucketError),
    ])
    def test_bucket_with_no_structure_and_no_counter_fails_closed(
        self, tmp_path, kind, entity_id, is_legacy, refusal,
    ):
        """Entities, but no display row and no counter. The highest number
        is readable only from id text, which the seed does not read, so it
        writes no counter; the allocator then refuses the bucket, exactly as
        it did against the old file. Seeding one instead would reissue the
        numbers those rows already carry.

        Which refusal fires depends on the row. A non-legacy display-less row
        breaks the display-row invariant, so C3's guard refuses first with
        ``IncompleteBucketError``. A legacy row is exempt from that guard and
        reaches the older counterless refusal, which names
        ``establish_high_water``."""
        old = _OldFile(tmp_path)
        old.entity("old-row", kind, entity_id, is_legacy=is_legacy)
        staging_path, report = old.rebuild()

        assert (_WORKSPACE, kind) not in _seeded_counters(staging_path)
        assert kind not in report["sequences_seeded"]
        with pytest.raises(ValueError) as refused:
            _next_allocation(staging_path, kind)
        assert type(refused.value) is refusal
        if refusal is ValueError:
            assert "establish_high_water" in str(refused.value)

# ---------------------------------------------------------------------------
# A file that does not state its identity structure is refused
# ---------------------------------------------------------------------------
_NO_DISPLAY_TABLE = "the entity_display table (migration 13)"
_NO_LEGACY_COLUMN = "the entities.is_legacy column (migration 22)"


def _chain_built_file(path: str, schema_version: int) -> sqlite3.Connection:
    """A v1 file built by the real chain up to *schema_version* only: the
    shape a file of that age has on disk. ``_OldFile`` always runs the whole
    chain, so it cannot build one."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE IF NOT EXISTS _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    for version in range(1, schema_version + 1):
        database.MIGRATIONS[version](conn)
        database._upsert_metadata(conn, "schema_version", str(version))
        conn.commit()
    conn.execute(
        "INSERT INTO workspaces (uuid, project_id_legacy, project_root, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (_WORKSPACE, _WORKSPACE, f"/tmp/{_WORKSPACE}", _NOW, _NOW),
    )
    return conn


def _raw_entity(conn: sqlite3.Connection, old_uuid: str, kind: str, entity_id: str) -> None:
    """An entities row naming only the columns every file since migration 12 has."""
    entity_type, lifecycle_class = database._derive_type_and_lifecycle(kind)
    conn.execute(
        "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, name, "
        "status, created_at, updated_at, type, kind, lifecycle_class) "
        "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)",
        (old_uuid, _WORKSPACE, f"{kind}:{entity_id}", entity_id, entity_id,
         _NOW, _NOW, entity_type, kind, lifecycle_class),
    )


def _staging_row_counts(staging_path: str) -> dict[str, int]:
    return {
        table: _query(staging_path, f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        for table in ("workspaces", "entities", "entity_display", "sequences", "events")
    }


def _refused_before_any_write(old_path: str, staging_path: str) -> str:
    """Rebuild *old_path* expecting the missing-structure refusal; return its
    message. The staging file must be exactly as ``build_staging_database``
    left it."""
    rebuild_tool.build_staging_database(staging_path)
    before = _staging_row_counts(staging_path)
    with pytest.raises(rebuild_tool.BackfillMissingStructureError) as refused:
        rebuild_tool.run_backfill(old_path, staging_path)
    assert _staging_row_counts(staging_path) == before
    return str(refused.value)


def _rebuild_a_migrated_copy(tmp_path, old_path: str) -> str:
    """The repair the refusal names: open a copy with ``EntityDatabase``,
    which runs the migrations the file is missing, then rebuild the copy."""
    migrated_path = str(tmp_path / "migrated.db")
    shutil.copyfile(old_path, migrated_path)
    database.EntityDatabase(migrated_path).close()
    rebuilt_path = str(tmp_path / "rebuilt.db")
    rebuild_tool.build_staging_database(rebuilt_path)
    rebuild_tool.run_backfill(migrated_path, rebuilt_path)
    return rebuilt_path


def _rebuilt_identity(staging_path: str) -> dict[str, tuple[int, int | None]]:
    """type_id -> (is_legacy, display seq or None) for every rebuilt row."""
    return {
        row["type_id"]: (row["is_legacy"], row["seq"])
        for row in _query(
            staging_path,
            "SELECT e.type_id, e.is_legacy, d.seq FROM entities e "
            "LEFT JOIN entity_display d ON d.uuid = e.uuid",
        )
    }


class TestAFileThatDoesNotStateItsStructureIsRefused:
    """The rebuild carries display rows and ``is_legacy`` as the old file
    states them, and derives neither. Carried from a file that states
    neither, a row arrives with no display row and no legacy exemption, so
    C3's guard refuses its bucket: the rebuilt file cannot allocate. Such a
    file is refused before any write, and the refusal names the repair:
    migrate a copy, then rebuild the copy."""

    def test_a_file_whose_entity_display_table_is_gone_is_refused(self, tmp_path):
        """Before this refusal, the rebuild carried this file's 005-x with no
        display row and ``is_legacy`` 0, and C3 then refused the feature
        bucket. The file is at the current schema version, so no migration
        brings the table back; the refusal is the whole contract here."""
        old = _OldFile(tmp_path)
        old.entity("old-feature", "feature", "005-x")
        old.counter("feature", 6)
        old.conn.execute("DROP TABLE entity_display")
        old.conn.commit()
        old.conn.close()

        message = _refused_before_any_write(old.path, str(tmp_path / "staging.db"))

        assert _NO_DISPLAY_TABLE in message
        assert _NO_LEGACY_COLUMN not in message

    def test_a_file_older_than_migration_13_is_refused_and_a_migrated_copy_rebuilds(self, tmp_path):
        """A genuine schema-version-12 file. The refusal comes before the
        vocabulary diff, which would otherwise stop on the missing
        ``entity_relations`` table (migration 14) with an OperationalError
        that names no repair."""
        old_path = str(tmp_path / "old.db")
        conn = _chain_built_file(old_path, 12)
        _raw_entity(conn, "old-feature", "feature", "005-x")
        conn.execute(
            "INSERT INTO sequences (workspace_uuid, entity_type, next_val) VALUES (?, 'feature', 6)",
            (_WORKSPACE,),
        )
        conn.commit()
        conn.close()

        message = _refused_before_any_write(old_path, str(tmp_path / "staging.db"))

        assert _NO_DISPLAY_TABLE in message
        assert _NO_LEGACY_COLUMN in message
        rebuilt_path = _rebuild_a_migrated_copy(tmp_path, old_path)
        # Migration 13 wrote the display row, at the migration boundary.
        assert _rebuilt_identity(rebuilt_path) == {"feature:005-x": (0, 5)}
        assert _next_allocation(rebuilt_path, "feature") == 6

    def test_a_file_older_than_migration_22_is_refused_and_a_migrated_copy_rebuilds(self, tmp_path):
        """A genuine schema-version-19 file, the shape of the v1 file archived
        at the v2 cutover. It has display rows, but a legacy row is still
        marked only by the absence of one; migration 22 turns that absence
        into ``is_legacy``. Carried without it, P001 would be a display-less
        non-legacy row, and C3 would refuse the project bucket."""
        old_path = str(tmp_path / "old.db")
        conn = _chain_built_file(old_path, 19)
        _raw_entity(conn, "old-legacy", "project", "P001")
        _raw_entity(conn, "old-fresh", "project", "002-fresh")
        conn.execute("INSERT INTO entity_display (uuid, seq, slug) VALUES ('old-fresh', 2, 'fresh')")
        conn.execute(
            "INSERT INTO sequences (workspace_uuid, entity_type, next_val) VALUES (?, 'project', 3)",
            (_WORKSPACE,),
        )
        conn.commit()
        conn.close()

        message = _refused_before_any_write(old_path, str(tmp_path / "staging.db"))

        assert _NO_LEGACY_COLUMN in message
        assert _NO_DISPLAY_TABLE not in message
        rebuilt_path = _rebuild_a_migrated_copy(tmp_path, old_path)
        assert _rebuilt_identity(rebuilt_path) == {
            "project:P001": (1, None),
            "project:002-fresh": (0, 2),
        }
        assert _next_allocation(rebuilt_path, "project") == 3

    def test_the_cli_reports_the_refusal_and_exits_1(self, tmp_path, capsys):
        old = _OldFile(tmp_path)
        old.conn.execute("DROP TABLE entity_display")
        old.conn.commit()
        old.conn.close()
        report_dir = tmp_path / "reports"

        exit_code = rebuild_tool.main([
            "--db", old.path,
            "--staging-path", str(tmp_path / "staging.db"),
            "--report-dir", str(report_dir),
        ])

        assert exit_code == 1
        assert f"Backfill aborted: the old file lacks {_NO_DISPLAY_TABLE}" in capsys.readouterr().err
        assert not report_dir.exists()
