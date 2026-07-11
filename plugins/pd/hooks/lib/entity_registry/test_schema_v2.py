"""Tests for entity_registry.schema_v2 (dark-shipped v2 core schema/bootstrap).

Covers design 118 Testing Strategy #1-6: bootstrap shape (uuid PKs, UNIQUE
index sweep), business-key non-uniqueness, the DDL registry extension point,
bootstrap idempotency, the one-version-write source discipline, and the
PRAGMA contract (WAL / foreign_keys / busy_timeout) on the connection
bootstrap_v2 returns.
"""
from __future__ import annotations

import fcntl
import multiprocessing
import re
import sqlite3
from pathlib import Path

import pytest

from entity_registry import events  # noqa: F401 -- side effect: registers "events" DDL (design D4); needed by TestEventsDdlRegistrationPin
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
    def test_bootstrap_missing_parent_directory_raises_file_not_found_error(self, tmp_path):
        """bootstrap_v2 does not create intermediate directories: a path
        whose parent is missing fails loudly, not silently or with a
        confusing later error.

        Feature 119 (design D3) wraps bootstrap_v2's entire body — including
        the sqlite3.connect call — in `_bootstrap_lock`, which opens a
        sidecar lock file under the same (missing) parent directory FIRST.
        That `open()` call now fails with FileNotFoundError before sqlite3
        ever gets a chance to raise its own "unable to open database file"
        error — design's Error Handling section documents this class of
        failure as "OSError propagates ... fail loud ... not defended
        further" (FileNotFoundError is a subclass of OSError).

        Anticipate: a caller might assume bootstrap_v2 behaves like
        `os.makedirs(..., exist_ok=True)` for its target's parent — it
        does not. This pins the actual failure mode so a future refactor
        that adds directory auto-creation (to either the lock file or the
        database file) is a deliberate, visible design change rather than
        an accidental behavior shift this suite stays silent on.
        derived_from: dimension:error_propagation, dimension:boundary_values
        """
        # Given a path whose parent directory was never created
        missing_parent_path = str(tmp_path / "does-not-exist" / "v2.db")
        # When bootstrap_v2 is called against it
        # Then the lock sidecar's open() raises FileNotFoundError rather
        # than succeeding or raising some unrelated/confusing error downstream
        with pytest.raises(FileNotFoundError):
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
#
# Re-scoped for feature 119 (design D6): the dark set grew from a single
# module (schema_v2.py) to a named set (_V2_DARK_MODULES), and the needle
# set widened to catch every import spelling of the new `events` module.
# ---------------------------------------------------------------------------

# Every dark v2 module this guard exempts from being its own offender (a
# dark module's own source legitimately mentions its sibling dark modules
# — e.g. events.py imports schema_v2, display.py imports events). uuid7.py
# is deliberately NOT in this set: it is already live via database.py's
# uuid7 mints (design D6).
_V2_DARK_MODULES = {"schema_v2.py", "events.py", "display.py"}

# Every import spelling that would wire a dark v2 module into a live path.
# A bare "events" needle is deliberately excluded — it false-positives on
# unrelated names like phase_events / event_type. Same rationale keeps a
# bare "display" needle out — it would false-positive on unrelated names
# like entity_display_table / display_name.
_V2_LIVE_REFERENCE_NEEDLES = (
    "schema_v2",
    "entity_registry.events",
    "from entity_registry import events",
    "from .events import",
    "entity_registry.display",
    "from entity_registry import display",
    "from .display import",
)


def _scan_for_live_v2_references(
    root: Path, dark_modules: set[str], needles: tuple[str, ...]
) -> list[str]:
    """Return paths of every ``*.py`` file under *root* (recursively) whose
    content contains at least one of *needles*, excluding test files
    (name starts with "test_") and files named in *dark_modules*.

    Shared by the real-source scan (expects []) and the seeded-fixture
    teeth test (expects the offender) below — see TestSchemaV2ShipsDark.
    """
    offending_files = []
    for py_file in root.rglob("*.py"):
        if py_file.name.startswith("test_") or py_file.name in dark_modules:
            continue
        content = py_file.read_text()
        if any(needle in content for needle in needles):
            offending_files.append(str(py_file))
    return offending_files


class TestSchemaV2ShipsDark:
    """Design D1 (schema_v2) + D6 (events, re-scoped for 119): every dark
    v2 module in _V2_DARK_MODULES ships with no live importer anywhere
    under hooks/lib — only test_ files (and the dark modules' own mutual
    references) may mention them.

    Scope note: the scan root is hooks/lib (this guard's historical
    scope, D1) — it does NOT cover plugins/pd/mcp/. MCP wiring is
    enforced separately by spec SC6's repo-wide grep at verification
    time, not by this every-pytest guard.
    """

    def test_no_non_test_importer_of_dark_v2_modules(self):
        """No non-test file under hooks/lib references a dark v2 module
        via any known import spelling (design D6; spec Out of Scope:
        "nothing reads the v2 DB in this feature").

        Anticipate: a future feature (120/121/122) could accidentally
        wire schema_v2 or events into a live code path before feature
        132's cutover decides where the v2 DB lives. Task 4's tasks.md
        Verify step has the equivalent grep, but as a one-time manual
        check it does not run on every `pytest` invocation the way this
        does — mirrors the residual-uuid4 scan test's source-scan style
        (test_database.py).
        derived_from: design:D1/D6 (ships dark), spec:Out-of-Scope
        (consumer rewiring deferred), dimension:adversarial (Never/Always
        heuristic)
        """
        hooks_lib_root = Path(__file__).resolve().parent.parent
        assert hooks_lib_root.name == "lib", (
            f"expected .../hooks/lib, got {hooks_lib_root}"
        )

        offending_files = _scan_for_live_v2_references(
            hooks_lib_root, _V2_DARK_MODULES, _V2_LIVE_REFERENCE_NEEDLES
        )

        assert offending_files == [], (
            f"v2 dark modules must ship dark (no non-test importers), but "
            f"found references in: {offending_files}"
        )

    def test_scan_flags_seeded_offender_with_nondotted_import_spelling(self, tmp_path):
        """Teeth check the other direction: a fixture dir containing a
        file that imports events via the NON-dotted spelling (`from
        entity_registry import events`) IS flagged — proves the widened
        needle set actually catches this spelling, not just the dotted
        `entity_registry.events` one (design D6: "the seeded-offender
        fixture uses one of the NON-dotted spellings so the teeth test is
        non-vacuous for the hardened gap").
        """
        offender_path = tmp_path / "some_consumer.py"
        offender_path.write_text("from entity_registry import events\n")

        offending_files = _scan_for_live_v2_references(
            tmp_path, _V2_DARK_MODULES, _V2_LIVE_REFERENCE_NEEDLES
        )

        assert offending_files == [str(offender_path)]

    # -------------------------------------------------------------
    # Gap pass (test-deepener, dimension:mutation_mindset): the sibling
    # test above only seeds the NON-dotted spelling (`from entity_registry
    # import events`) — the DOTTED needle ("entity_registry.events") had
    # no seeded-offender regression test of its own, even though design
    # D6 explicitly widened the needle set to catch both spellings.
    # -------------------------------------------------------------
    def test_scan_flags_seeded_offender_with_dotted_import_spelling(self, tmp_path):
        """Anticipate: a future edit to _V2_LIVE_REFERENCE_NEEDLES that
        dropped or typo'd the "entity_registry.events" entry (leaving
        only the "schema_v2" and "from entity_registry import events"
        needles) would still pass the non-dotted sibling test above,
        since that needle isn't the one it seeds — this test fails
        against that specific regression because its fixture contains
        ONLY the dotted spelling (no "schema_v2" substring, no
        non-dotted "from entity_registry import events" substring), so
        detection here can only be coming from the "entity_registry.events"
        needle itself.
        """
        offender_path = tmp_path / "some_other_consumer.py"
        offender_path.write_text(
            "import entity_registry.events\n"
            "\n"
            "def wire_it_up():\n"
            "    entity_registry.events.append_event(entity_uuid='x')\n"
        )

        offending_files = _scan_for_live_v2_references(
            tmp_path, _V2_DARK_MODULES, _V2_LIVE_REFERENCE_NEEDLES
        )

        assert offending_files == [str(offender_path)]

    # -------------------------------------------------------------
    # Design D8 (feature 121): display.py joins the dark-module set — its
    # own three-way needle coverage (dotted / non-dotted / relative) gets
    # the same seeded-offender teeth as the events.py pair above, PLUS the
    # relative-import spelling neither events.py test exercises (the
    # likeliest false-negative per D8: "the relative form is exactly how
    # a same-package sibling like database.py would wire it at 132").
    # -------------------------------------------------------------
    def test_scan_flags_seeded_offender_with_display_nondotted_import_spelling(
        self, tmp_path
    ):
        """Mirrors test_scan_flags_seeded_offender_with_nondotted_import_spelling
        above, for the "display" needle set instead of "events"."""
        offender_path = tmp_path / "some_display_consumer.py"
        offender_path.write_text("from entity_registry import display\n")

        offending_files = _scan_for_live_v2_references(
            tmp_path, _V2_DARK_MODULES, _V2_LIVE_REFERENCE_NEEDLES
        )

        assert offending_files == [str(offender_path)]

    def test_scan_flags_seeded_offender_with_display_dotted_import_spelling(
        self, tmp_path
    ):
        """Mirrors test_scan_flags_seeded_offender_with_dotted_import_spelling
        above, for the "display" needle set instead of "events"."""
        offender_path = tmp_path / "some_other_display_consumer.py"
        offender_path.write_text(
            "import entity_registry.display\n"
            "\n"
            "def wire_it_up():\n"
            "    entity_registry.display.next_display_seq(\n"
            "        conn, workspace_uuid='x', kind='feature')\n"
        )

        offending_files = _scan_for_live_v2_references(
            tmp_path, _V2_DARK_MODULES, _V2_LIVE_REFERENCE_NEEDLES
        )

        assert offending_files == [str(offender_path)]

    def test_scan_flags_seeded_offender_with_display_relative_import_spelling(
        self, tmp_path
    ):
        """The relative spelling design D8 singles out as the likeliest
        false-negative — exactly how a same-package sibling (e.g.
        database.py at feature 132's cutover) would wire display.py in:
        neither of the two sibling tests above seeds this form, so a
        typo'd or dropped "from .display import" entry in
        _V2_LIVE_REFERENCE_NEEDLES would pass both of them silently.

        Anticipate: an implementation of the needle-set widening that
        added only the dotted and non-dotted display spellings (the
        pattern the existing events.py pair already established) and
        forgot the relative form would still pass both sibling tests
        above — this test fails against that specific omission because
        its fixture contains ONLY the relative spelling.
        """
        offender_path = tmp_path / "some_relative_display_consumer.py"
        offender_path.write_text("from .display import next_display_seq\n")

        offending_files = _scan_for_live_v2_references(
            tmp_path, _V2_DARK_MODULES, _V2_LIVE_REFERENCE_NEEDLES
        )

        assert offending_files == [str(offender_path)]


# ---------------------------------------------------------------------------
# Design test #9: events.py's module-import side effect registers
# ("events", _EVENTS_DDL) into schema_v2.DDL_REGISTRY, positioned after
# "core" — and a direct second register_ddl("events", ...) call still
# raises ValueError (118's double-registration contract, D4). Relies on
# the module-top `from entity_registry import events` import above (that
# import's side effect is what puts "events" into DDL_REGISTRY at all;
# the existing autouse _reset_ddl_registry fixture snapshots/restores
# around every test in this file, this test needs no fixture of its own).
# ---------------------------------------------------------------------------
class TestEventsDdlRegistrationPin:
    def test_core_then_events_membership_and_relative_order(self):
        """Membership + relative order, NOT whole-list equality —
        DDL_REGISTRY is shared module state and future registrants
        (120/121/122) may share the process (design D6/Testing Strategy
        #9)."""
        owners = [owner for owner, _ in schema_v2.DDL_REGISTRY]
        assert "core" in owners
        assert "events" in owners
        assert owners.index("core") < owners.index("events")

    def test_direct_second_register_ddl_events_raises_value_error(self):
        """events.py already registered "events" at import time (module
        top, D4) — a direct second call for the same owner still raises;
        the pre-mutation check in register_ddl fires regardless of how
        the first registration happened."""
        with pytest.raises(ValueError, match="events"):
            schema_v2.register_ddl(
                "events", "CREATE TABLE IF NOT EXISTS shadow_events (uuid TEXT PRIMARY KEY)"
            )


# ---------------------------------------------------------------------------
# Module-level worker for the two-process bootstrap race (test group #7a).
# Must be a top-level function: the default multiprocessing start method on
# darwin (and this suite's CI) is "spawn", which pickles a module-qualified
# function reference to hand the target to the child process — a closure or
# nested function is not picklable under spawn.
# ---------------------------------------------------------------------------
def _bootstrap_v2_race_worker(db_path: str) -> None:
    """Worker process: bootstrap db_path and close the connection."""
    conn = schema_v2.bootstrap_v2(db_path)
    conn.close()


# ---------------------------------------------------------------------------
# Design test #7: bootstrap lock concurrency (feature 119, D3). #7a is the
# regression for feature 118's measured ~50% "database is locked" failure
# rate (15/30 trials) on two bootstrap_v2 calls racing the same path; #7b
# checks the sidecar lock is fully released once bootstrap_v2 returns.
# ---------------------------------------------------------------------------
class TestConcurrentBootstrapLock:
    def test_thirty_trials_two_process_bootstrap_race_both_succeed(self, tmp_path):
        """30 independent trials, each racing 2 fresh processes against a
        fresh db path. Pre-lock (feature 118), this failed ~50% of trials
        with "database is locked" (DDL takes locks busy_timeout does not
        retry). The sidecar flock in _bootstrap_lock (design D3) turns the
        race into a deterministic wait instead of a failure — both
        processes must exit 0 in every trial.
        """
        num_trials = 30
        for trial in range(num_trials):
            db_path = str(tmp_path / f"race-{trial}.db")
            processes = [
                multiprocessing.Process(
                    target=_bootstrap_v2_race_worker, args=(db_path,)
                )
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=10)

            for process in processes:
                assert process.exitcode == 0, (
                    f"trial {trial}: worker exited with code {process.exitcode}"
                )

    def test_lock_released_after_bootstrap_returns(self, tmp_path):
        """After bootstrap_v2() returns and its connection is closed, the
        sidecar lock file is fully released: a fresh, non-blocking
        LOCK_EX acquisition on it succeeds immediately — no leaked fd or
        lock (_bootstrap_lock's `finally` releases before bootstrap_v2
        returns)."""
        db_path = str(tmp_path / "v2.db")
        conn = schema_v2.bootstrap_v2(db_path)
        conn.close()

        lock_path = f"{db_path}.bootstrap.lock"
        with open(lock_path, "a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    # -------------------------------------------------------------
    # Gap pass (test-deepener, dimension:mutation_mindset): the sibling
    # test above only pins lock release on the SUCCESS path — whether
    # _bootstrap_lock's `finally` also releases when bootstrap_v2's body
    # raises partway through was unexercised.
    # -------------------------------------------------------------
    def test_lock_released_after_bootstrap_body_raises(self, tmp_path):
        """Same broken-DDL-entry recipe as TestPartialBootstrapRecovery
        above, but this test's own concern is the lock, not the
        registry's convergent-recovery contract.

        Anticipate: an implementation of _bootstrap_lock that released
        the lock via code placed after `yield` but OUTSIDE a try/finally
        (e.g. relying on the caller never raising) would leave the
        sidecar lock held forever once bootstrap_v2's body raises — this
        test fails against that mutation because the fresh non-blocking
        LOCK_EX attempt below would raise BlockingIOError instead of
        succeeding immediately, whereas the success-path sibling test
        above cannot exercise the finally-on-exception branch at all.
        derived_from: design:D3 (_bootstrap_lock finally-released
        contract), dimension:mutation_mindset
        """
        db_path = str(tmp_path / "v2.db")
        schema_v2.register_ddl(
            "broken-lock-release-probe",
            # Malformed SQL: trailing commas make this a syntax error,
            # same recipe as TestPartialBootstrapRecovery.
            "CREATE TABLE IF NOT EXISTS broken_probe_t (uuid TEXT PRIMARY KEY,,,,)",
        )

        # Given a registry entry that will make bootstrap_v2's body raise
        # When bootstrap_v2 is called
        # Then it raises, AFTER having acquired the lock...
        with pytest.raises(sqlite3.OperationalError):
            schema_v2.bootstrap_v2(db_path)

        # ...but the lock is nonetheless released: a fresh, non-blocking
        # LOCK_EX acquisition on the sidecar file succeeds immediately.
        lock_path = f"{db_path}.bootstrap.lock"
        with open(lock_path, "a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
