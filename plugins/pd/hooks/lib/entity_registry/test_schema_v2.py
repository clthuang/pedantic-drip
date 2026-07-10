"""Tests for entity_registry.schema_v2 (dark-shipped v2 core schema/bootstrap).

Covers design 118 Testing Strategy #1-6: bootstrap shape (uuid PKs, UNIQUE
index sweep), business-key non-uniqueness, the DDL registry extension point,
bootstrap idempotency, the one-version-write source discipline, and the
PRAGMA contract (WAL / foreign_keys / busy_timeout) on the connection
bootstrap_v2 returns.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from entity_registry import schema_v2

# The 4 core tables carrying a uuid7 TEXT primary key. `_metadata` is
# deliberately excluded — it's key/value bookkeeping with PK `key` (task 4's
# own DDL), not an entity-shaped table.
_CORE_TABLES_WITH_UUID_PK = ("workspaces", "entities", "entity_relations", "sequences")

# Business-key / human-readable fields FR-4 forbids UNIQUE constraints on.
_FORBIDDEN_UNIQUE_COLUMNS = {"type_id", "slug", "name", "display_name", "display"}

_NOW = "2026-01-01T00:00:00Z"

# Matches an executable SQL write statement (INSERT/UPDATE/REPLACE) that
# targets _metadata. Deliberately tight (requires the real SQL shape, e.g.
# "INSERT ... INTO _metadata" / "UPDATE _metadata" / "REPLACE INTO
# _metadata") rather than loose keyword co-occurrence, so prose mentioning
# both a write verb and "_metadata" in the same paragraph can't false-positive.
_METADATA_WRITE_RE = re.compile(
    r"\bINSERT(?:\s+OR\s+\w+)?\s+INTO\s+_metadata\b"
    r"|\bUPDATE\s+_metadata\b"
    r"|\bREPLACE\s+INTO\s+_metadata\b",
    re.IGNORECASE,
)


def _strip_comments(source: str) -> str:
    """Strip '--' SQL comments and '#' Python comments, line by line.

    Adequate (not a general SQL/Python parser) because we control the
    source being scanned: neither language construct spans multiple lines
    in schema_v2.py, and no string literal in that file contains a literal
    '--' or '#'.
    """
    cleaned_lines = []
    for line in source.splitlines():
        sql_comment_at = line.find("--")
        if sql_comment_at != -1:
            line = line[:sql_comment_at]
        hash_comment_at = line.find("#")
        if hash_comment_at != -1:
            line = line[:hash_comment_at]
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _unique_indexes(conn: sqlite3.Connection):
    """Yield (table, index_name, covered_columns) for every UNIQUE index
    across every table in *conn*, including implicit PK autoindexes."""
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    for table in tables:
        for index_row in conn.execute(f"PRAGMA index_list({table})").fetchall():
            index_name, is_unique = index_row[1], index_row[2]
            if not is_unique:
                continue
            covered_columns = frozenset(
                info_row[2]
                for info_row in conn.execute(
                    f"PRAGMA index_info({index_name})"
                ).fetchall()
            )
            yield table, index_name, covered_columns


@pytest.fixture(autouse=True)
def _reset_ddl_registry():
    """Snapshot/restore DDL_REGISTRY around every test.

    It's a module-level list mutated by register_ddl() — without this,
    a test that registers a "dummy" owner would leak that registration
    into every test that runs after it in the same process.
    """
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


@pytest.fixture
def bootstrapped_conn(tmp_path):
    """A connection from a fresh bootstrap_v2() call, closed after the test."""
    conn = schema_v2.bootstrap_v2(str(tmp_path / "v2.db"))
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Design test #1: bootstrap shape — uuid PKs + UNIQUE index sweep
# ---------------------------------------------------------------------------
class TestBootstrapShape:
    def test_uuid_text_primary_key_on_core_tables(self, bootstrapped_conn):
        """Each of the 4 core tables has exactly one PK column, named
        'uuid', typed TEXT."""
        for table in _CORE_TABLES_WITH_UUID_PK:
            columns = bootstrapped_conn.execute(f"PRAGMA table_info({table})").fetchall()
            # table_info's pk field is the column's 1-based POSITION within
            # the PK (0 = not part of it) — filtering == 1 would match only
            # the first column of a composite key and mask that regression.
            pk_columns = [col for col in columns if col[5] != 0]
            assert len(pk_columns) == 1, f"{table} must have exactly one PK column"
            pk_name, pk_type = pk_columns[0][1], pk_columns[0][2]
            assert pk_name == "uuid", f"{table} PK must be 'uuid', got {pk_name!r}"
            assert pk_type.upper() == "TEXT", f"{table}.uuid must be TEXT, got {pk_type!r}"

    def test_metadata_primary_key_is_key_not_uuid(self, bootstrapped_conn):
        """_metadata is excluded from the uuid-PK sweep: its PK is `key`
        (key/value bookkeeping, per this task's own DDL)."""
        columns = bootstrapped_conn.execute("PRAGMA table_info(_metadata)").fetchall()
        pk_columns = [col for col in columns if col[5] == 1]
        assert len(pk_columns) == 1
        assert pk_columns[0][1] == "key"
        assert not any(col[1] == "uuid" for col in columns)

    def test_no_unique_index_covers_business_key_columns(self, bootstrapped_conn):
        """Sweep every UNIQUE index (by covered column set, not per-table
        hardcode): only idx_relations_dedup (from_uuid, to_uuid, kind) is
        allowed. No UNIQUE index may cover type_id/slug/name/display fields
        (FR-4: no uniqueness on human-readable business keys)."""
        seen_dedup_index = False
        for table, index_name, covered_columns in _unique_indexes(bootstrapped_conn):
            if index_name == "idx_relations_dedup":
                assert table == "entity_relations"
                assert covered_columns == {"from_uuid", "to_uuid", "kind"}
                seen_dedup_index = True
                continue
            forbidden_hit = covered_columns & _FORBIDDEN_UNIQUE_COLUMNS
            assert not forbidden_hit, (
                f"UNIQUE index {index_name!r} on {table} covers business-key "
                f"column(s) {forbidden_hit} — FR-4 forbids uniqueness on "
                f"human-readable fields"
            )
        assert seen_dedup_index, "expected idx_relations_dedup to exist"


# ---------------------------------------------------------------------------
# Design test #2: business-key non-uniqueness
# ---------------------------------------------------------------------------
class TestBusinessKeyNonUniqueness:
    def test_duplicate_type_id_same_workspace_both_insert_succeed(self, bootstrapped_conn):
        """Two entities sharing the same (type_id, workspace) both insert
        without error — there is no UNIQUE constraint on type_id (FR-4)."""
        conn = bootstrapped_conn
        workspace_uuid = "workspace-uuid-1"
        conn.execute(
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (workspace_uuid, "/tmp/project", _NOW, _NOW),
        )
        for entity_uuid in ("entity-uuid-1", "entity-uuid-2"):
            conn.execute(
                "INSERT INTO entities (uuid, workspace_uuid, type, kind, "
                "lifecycle_class, type_id, name, artifact_path, parent_uuid, "
                "created_at, updated_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entity_uuid, workspace_uuid, "feature", "feature",
                    "artifact", "shared-type-id", "Some Name", None, None,
                    _NOW, _NOW, None,
                ),
            )
        row_count = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE type_id = ?", ("shared-type-id",)
        ).fetchone()[0]
        assert row_count == 2


# ---------------------------------------------------------------------------
# Design test #3: DDL registry extension point
# ---------------------------------------------------------------------------
class TestDdlRegistryExtensionPoint:
    def test_register_ddl_entry_is_applied_by_bootstrap(self, tmp_path):
        schema_v2.register_ddl(
            "dummy", "CREATE TABLE IF NOT EXISTS dummy_t (uuid TEXT PRIMARY KEY)"
        )
        conn = schema_v2.bootstrap_v2(str(tmp_path / "v2.db"))
        try:
            table_names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            assert "dummy_t" in table_names
        finally:
            conn.close()

    def test_register_ddl_duplicate_owner_raises(self):
        schema_v2.register_ddl("dummy", "CREATE TABLE IF NOT EXISTS dummy_t (uuid TEXT PRIMARY KEY)")
        with pytest.raises(ValueError):
            schema_v2.register_ddl(
                "dummy", "CREATE TABLE IF NOT EXISTS other_t (uuid TEXT PRIMARY KEY)"
            )

    def test_register_ddl_owner_core_collision_raises(self):
        """Registering owner="core" collides with the built-in entry that
        ships pre-registered in DDL_REGISTRY (not just a test-added dummy).

        Anticipate: a duplicate-owner check implemented as "does this
        owner appear among entries registered VIA register_ddl this
        session" (e.g. a separate tracking set populated only inside
        register_ddl, instead of scanning DDL_REGISTRY itself) would miss
        the pre-seeded "core" entry and silently accept the collision —
        this test fails against that mutation, since it never calls
        register_ddl("core", ...) from a prior test in the same run.
        """
        with pytest.raises(ValueError, match="core"):
            schema_v2.register_ddl(
                "core", "CREATE TABLE IF NOT EXISTS shadow_core (uuid TEXT PRIMARY KEY)"
            )


# ---------------------------------------------------------------------------
# Design test #4: bootstrap idempotency
# ---------------------------------------------------------------------------
class TestBootstrapIdempotency:
    def test_double_bootstrap_no_error_version_unchanged_single_row(self, tmp_path):
        db_path = str(tmp_path / "v2.db")
        first_conn = schema_v2.bootstrap_v2(db_path)
        first_conn.close()

        second_conn = schema_v2.bootstrap_v2(db_path)  # must not raise
        try:
            rows = second_conn.execute(
                "SELECT value FROM _metadata WHERE key = 'schema_version'"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == str(schema_v2.V2_SCHEMA_VERSION)

            total_metadata_rows = second_conn.execute(
                "SELECT COUNT(*) FROM _metadata"
            ).fetchone()[0]
            assert total_metadata_rows == 1
        finally:
            second_conn.close()

    def test_registry_extended_between_bootstraps_picks_up_new_entry(self, tmp_path):
        """A sibling's register_ddl() call made AFTER a path's first
        bootstrap is picked up by that path's SECOND bootstrap_v2 call
        (design D4 / Error Handling: "the registry is input to bootstrap,
        not a post-hoc migration" — re-running replays the full registry,
        it does not track "what's new since last time").

        Anticipate: a stateful implementation that short-circuits DDL
        application once `_metadata.schema_version` already exists (e.g.
        "if already bootstrapped, skip the DDL loop entirely") would never
        create the newly-registered table on the second call — this test
        fails against that mutation, while the existing idempotency test
        (which never extends the registry) would still pass it.
        """
        db_path = str(tmp_path / "v2.db")
        first_conn = schema_v2.bootstrap_v2(db_path)
        first_conn.close()

        schema_v2.register_ddl(
            "extra", "CREATE TABLE IF NOT EXISTS extra_t (uuid TEXT PRIMARY KEY)"
        )
        second_conn = schema_v2.bootstrap_v2(db_path)
        try:
            table_names = {
                row[0]
                for row in second_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            assert "extra_t" in table_names

            # Version write stays idempotent even though a new DDL entry
            # was applied — only the version row itself is INSERT OR IGNORE.
            version_rows = second_conn.execute(
                "SELECT value FROM _metadata WHERE key = 'schema_version'"
            ).fetchall()
            assert len(version_rows) == 1
            assert version_rows[0][0] == str(schema_v2.V2_SCHEMA_VERSION)
        finally:
            second_conn.close()


# ---------------------------------------------------------------------------
# Design test #5: one-version-location source discipline
# ---------------------------------------------------------------------------
class TestSchemaVersionWriteDiscipline:
    def test_exactly_one_metadata_write_statement_in_source(self):
        source = Path(schema_v2.__file__).read_text()
        cleaned_source = _strip_comments(source)
        matches = _METADATA_WRITE_RE.findall(cleaned_source)
        assert len(matches) == 1, (
            f"expected exactly one executable write statement targeting "
            f"_metadata, found {len(matches)}: {matches}"
        )


# ---------------------------------------------------------------------------
# Design test #6: PRAGMA contract on the connection bootstrap_v2 returns
# ---------------------------------------------------------------------------
class TestConnectionPragmas:
    def test_wal_mode_on_returned_connection(self, bootstrapped_conn):
        journal_mode = bootstrapped_conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"

    def test_foreign_keys_enforced_on_returned_connection(self, bootstrapped_conn):
        foreign_keys_status = bootstrapped_conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert foreign_keys_status == 1

        # Non-vacuous: an FK-violating insert must actually be rejected.
        with pytest.raises(sqlite3.IntegrityError):
            bootstrapped_conn.execute(
                "INSERT INTO entities (uuid, workspace_uuid, type, kind, "
                "lifecycle_class, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "entity-uuid-orphan", "nonexistent-workspace-uuid",
                    "feature", "feature", "artifact", _NOW, _NOW,
                ),
            )

    def test_busy_timeout_value_on_returned_connection(self, bootstrapped_conn):
        busy_timeout_ms = bootstrapped_conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert busy_timeout_ms == schema_v2._BUSY_TIMEOUT_MS


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:error_propagation / dimension:boundary_values):
# bootstrap_v2 on a path whose parent directory does not exist.
# ---------------------------------------------------------------------------
class TestBootstrapPathErrors:
    def test_bootstrap_missing_parent_directory_raises_operational_error(self, tmp_path):
        """bootstrap_v2 does not create intermediate directories: a path
        whose parent is missing fails loudly via sqlite3, not silently or
        with a confusing later error.

        Anticipate: a caller might assume bootstrap_v2 behaves like
        `os.makedirs(..., exist_ok=True)` for its target's parent — it
        does not. This pins the actual failure mode (sqlite3.connect
        itself refuses to open the file) so a future refactor that adds
        directory auto-creation is a deliberate, visible design change
        rather than an accidental behavior shift this suite stays silent on.
        derived_from: dimension:error_propagation, dimension:boundary_values
        """
        # Given a path whose parent directory was never created
        missing_parent_path = str(tmp_path / "does-not-exist" / "v2.db")
        # When bootstrap_v2 is called against it
        # Then sqlite3 raises OperationalError rather than succeeding or
        # raising some unrelated/confusing error downstream
        with pytest.raises(sqlite3.OperationalError, match="unable to open database file"):
            schema_v2.bootstrap_v2(missing_parent_path)


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:adversarial — "Interrupt" heuristic):
# D4's documented "convergent, not atomic" recovery contract had zero
# coverage — every existing test either succeeds cleanly or never partially
# applies the registry.
# ---------------------------------------------------------------------------
class TestPartialBootstrapRecovery:
    def test_mid_bootstrap_failure_preserves_earlier_entries_then_retry_converges(
        self, tmp_path
    ):
        """A later registry entry with invalid SQL fails its executescript
        call; the earlier ("core") entry's tables stay applied (each
        registry entry commits independently — design D4). Fixing the bad
        entry and re-running bootstrap_v2 on the SAME path then converges,
        without re-doing (or erroring on) the already-applied prefix.

        Anticipate: if bootstrap_v2 wrapped the whole registry loop in one
        outer transaction instead of one executescript() per entry, the
        "core" tables would roll back along with the broken entry, and the
        post-failure table check below would find them MISSING — this
        test fails against that "make it atomic" mutation, which is
        exactly the behavior D4's docstring explicitly rejects.
        derived_from: design:D4 (convergent-not-atomic recovery contract),
        dimension:adversarial (Interrupt heuristic)
        """
        db_path = str(tmp_path / "v2.db")
        schema_v2.register_ddl(
            "broken",
            # Malformed SQL: trailing commas make this a syntax error.
            "CREATE TABLE IF NOT EXISTS broken_t (uuid TEXT PRIMARY KEY,,,,)",
        )

        # Given a registry with a malformed entry AFTER the working "core" entry
        # When bootstrap_v2 applies the registry in order
        # Then it raises on the broken entry...
        with pytest.raises(sqlite3.OperationalError):
            schema_v2.bootstrap_v2(db_path)

        # ...but the earlier "core" entry's tables (applied via their own
        # executescript call, before "broken" was reached) already committed.
        verify_conn = sqlite3.connect(db_path)
        try:
            table_names = {
                row[0]
                for row in verify_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            for table in _CORE_TABLES_WITH_UUID_PK:
                assert table in table_names, (
                    f"{table} should have survived the later entry's failure"
                )
            # The version write happens strictly AFTER the registry loop —
            # a failure mid-loop means it never ran on this attempt.
            version_rows = verify_conn.execute(
                "SELECT value FROM _metadata WHERE key = 'schema_version'"
            ).fetchall()
            assert version_rows == []
        finally:
            verify_conn.close()

        # Now correct the broken entry in place and retry on the SAME path.
        schema_v2.DDL_REGISTRY[-1] = (
            "broken", "CREATE TABLE IF NOT EXISTS broken_t (uuid TEXT PRIMARY KEY)"
        )
        retry_conn = schema_v2.bootstrap_v2(db_path)
        try:
            table_names = {
                row[0]
                for row in retry_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            assert "broken_t" in table_names
            version_rows = retry_conn.execute(
                "SELECT value FROM _metadata WHERE key = 'schema_version'"
            ).fetchall()
            assert len(version_rows) == 1
        finally:
            retry_conn.close()


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:bdd_scenarios): spec's In-Scope bullet
# ("an allocator `kind` column carries no business-key UNIQUE constraint —
# not in the forbidden set") pins the sequences table specifically, the way
# TestBusinessKeyNonUniqueness already pins entities.type_id.
# ---------------------------------------------------------------------------
class TestSequencesBusinessKeyNonUniqueness:
    def test_duplicate_workspace_and_kind_both_insert_succeed(self, bootstrapped_conn):
        """Two `sequences` rows sharing the same (workspace_uuid, kind)
        both insert without error — `kind` carries no UNIQUE constraint
        (spec In Scope: "not in the forbidden set: type_id/slug/name/
        display fields"; 121 owns allocation atomicity via BEGIN IMMEDIATE,
        not a UNIQUE index here).

        Anticipate: the generic UNIQUE-index sweep in
        TestBootstrapShape only checks the named FORBIDDEN columns
        (type_id/slug/name/display*) — it would stay green even if a
        UNIQUE(workspace_uuid, kind) index were added to `sequences`,
        since "kind" alone isn't in that forbidden set. This test closes
        that blind spot with a direct positive-insertion pin, the same
        way the entities-table duplicate-type_id test does.
        derived_from: spec:Scope (sequences kind column, no business-key
        UNIQUE), design:D3
        """
        conn = bootstrapped_conn
        workspace_uuid = "workspace-uuid-seq-1"
        conn.execute(
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (workspace_uuid, "/tmp/project", _NOW, _NOW),
        )
        for sequence_uuid in ("seq-uuid-1", "seq-uuid-2"):
            conn.execute(
                "INSERT INTO sequences (uuid, workspace_uuid, kind, current_value) "
                "VALUES (?, ?, ?, ?)",
                (sequence_uuid, workspace_uuid, "feature", 0),
            )
        row_count = conn.execute(
            "SELECT COUNT(*) FROM sequences WHERE workspace_uuid = ? AND kind = ?",
            (workspace_uuid, "feature"),
        ).fetchone()[0]
        assert row_count == 2


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:adversarial — "Never" heuristic): design
# D1's "ships dark: no live code imports it except its tests" invariant was
# only pinned by a manual grep in tasks.md's Task 4 Verify step, never by an
# automated regression test that runs on every suite invocation.
# ---------------------------------------------------------------------------
class TestSchemaV2ShipsDark:
    def test_no_non_test_importer_of_schema_v2(self):
        """No file under plugins/pd/hooks/lib (other than schema_v2.py
        itself and test_ files) references `schema_v2` — the module ships
        dark; only its own tests exercise it (design D1; spec Out of
        Scope: "nothing reads the v2 DB in this feature").

        Anticipate: a future feature (119/120/121/122) could accidentally
        wire schema_v2 into a live code path before feature 132's cutover
        decides where the v2 DB lives. Task 4's tasks.md Verify step has
        the equivalent grep, but as a one-time manual check it does not
        run on every `pytest` invocation the way this does — mirrors the
        residual-uuid4 scan test's source-scan style (test_database.py).
        derived_from: design:D1 (ships dark), spec:Out-of-Scope (consumer
        rewiring deferred), dimension:adversarial (Never/Always heuristic)
        """
        import pathlib

        hooks_lib_root = pathlib.Path(__file__).resolve().parent.parent
        assert hooks_lib_root.name == "lib", (
            f"expected .../hooks/lib, got {hooks_lib_root}"
        )

        offending_files = []
        for py_file in hooks_lib_root.rglob("*.py"):
            if py_file.name.startswith("test_") or py_file.name == "schema_v2.py":
                continue
            if "schema_v2" in py_file.read_text():
                offending_files.append(str(py_file))

        assert offending_files == [], (
            f"schema_v2 must ship dark (no non-test importers), but found "
            f"references in: {offending_files}"
        )
