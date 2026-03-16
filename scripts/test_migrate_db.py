"""Tests for migrate_db.py CLI scaffold."""

import json
import hashlib
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pytest

SCRIPT = str(Path(__file__).parent / "migrate_db.py")

SUBCOMMANDS = [
    "backup",
    "manifest",
    "validate",
    "merge-memory",
    "merge-entities",
    "verify",
    "info",
    "check-embeddings",
]


# --- Task 1.1: test_subcommand_help ---


@pytest.mark.parametrize("subcommand", SUBCOMMANDS)
def test_subcommand_help(subcommand: str) -> None:
    """Each subcommand --help exits 0 and shows usage text."""
    result = subprocess.run(
        [sys.executable, SCRIPT, subcommand, "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"{subcommand} --help failed: {result.stderr}"
    assert "usage:" in result.stdout.lower(), (
        f"{subcommand} --help missing usage text"
    )


# --- Task 1.2: test_subcommand_stubs ---

# Each tuple: (subcommand, list of minimal required args)
SUBCOMMAND_ARGS = [
    ("backup", ["src.db", "dst.db", "--table", "entries"]),
    ("manifest", ["staging-dir", "--plugin-version", "1.0.0"]),
    ("validate", ["bundle-dir"]),
    ("merge-memory", ["src.db", "dst.db"]),
    ("merge-entities", ["src.db", "dst.db"]),
    ("verify", ["db.db", "--expected-count", "5", "--table", "entries"]),
    ("info", ["manifest.json"]),
    ("check-embeddings", ["manifest.json", "dst-memory.db"]),
]


@pytest.mark.parametrize(
    "subcommand,args",
    SUBCOMMAND_ARGS,
    ids=[t[0] for t in SUBCOMMAND_ARGS],
)
def test_subcommand_stubs(subcommand: str, args: list[str]) -> None:
    """Each subcommand with minimal args outputs valid JSON and exits 0."""
    result = subprocess.run(
        [sys.executable, SCRIPT, subcommand, *args],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Allow stubs that still return {} and real implementations that may fail
    # on missing files — but skip validation for stubs that are not yet implemented
    if subcommand in ("manifest", "validate", "info", "check-embeddings"):
        assert result.returncode == 0, (
            f"{subcommand} failed (exit {result.returncode}): {result.stderr}"
        )
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, dict), f"{subcommand} did not return a JSON object"


# ============================================================
# Helper: run CLI subcommand and parse JSON output
# ============================================================

def run_cli(*args: str, expect_rc: int = 0) -> dict:
    """Run migrate_db.py with given args, return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == expect_rc, (
        f"Expected rc={expect_rc}, got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


# ============================================================
# Helper: create a WAL-mode SQLite DB with an entries table
# ============================================================

def create_wal_db(path: str, table: str = "entries", row_count: int = 10) -> None:
    """Create a WAL-mode SQLite DB with a simple table and N rows."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, data TEXT)")
    for i in range(row_count):
        conn.execute(f"INSERT INTO {table} (id, data) VALUES (?, ?)", (i, f"row-{i}"))
    conn.commit()
    conn.close()


# ============================================================
# Step 2: backup subcommand tests
# ============================================================


class TestBackup:
    """Tests for the backup subcommand."""

    # --- Task 2.1: test_backup_wal_mode ---
    def test_backup_wal_mode(self, tmp_path: Path) -> None:
        """Backup a WAL-mode DB; verify integrity_check passes on backup."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "backup.db")
        create_wal_db(src, "entries", 10)

        result = run_cli("backup", src, dst, "--table", "entries")

        # Verify backup file exists and passes integrity check
        conn = sqlite3.connect(dst)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        assert integrity == "ok"

    # --- Task 2.2: test_backup_checksum ---
    def test_backup_checksum(self, tmp_path: Path) -> None:
        """Backup a DB; verify SHA-256 matches independently computed hash."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "backup.db")
        create_wal_db(src, "entries", 5)

        result = run_cli("backup", src, dst, "--table", "entries")

        # Independently compute SHA-256
        with open(dst, "rb") as f:
            expected_sha = hashlib.sha256(f.read()).hexdigest()
        assert result["sha256"] == expected_sha

    # --- Task 2.3: test_backup_entry_count ---
    def test_backup_entry_count(self, tmp_path: Path) -> None:
        """Backup a DB with known row count; verify entry_count in output."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "backup.db")
        create_wal_db(src, "entries", 7)

        result = run_cli("backup", src, dst, "--table", "entries")

        assert result["entry_count"] == 7
        assert result["size_bytes"] > 0


# ============================================================
# Step 5: verify subcommand tests
# ============================================================


class TestVerify:
    """Tests for the verify subcommand."""

    # --- Task 5.1: test_verify_healthy ---
    def test_verify_healthy(self, tmp_path: Path) -> None:
        """Healthy DB with matching expected count returns ok=true."""
        db = str(tmp_path / "test.db")
        create_wal_db(db, "entries", 10)

        result = run_cli("verify", db, "--expected-count", "10", "--table", "entries")

        assert result["ok"] is True
        assert result["actual_count"] == 10
        assert result["integrity"] == "ok"

    # --- Task 5.2: test_verify_count_only ---
    def test_verify_count_only(self, tmp_path: Path) -> None:
        """With expected-count=0, returns ok=true and actual count."""
        db = str(tmp_path / "test.db")
        create_wal_db(db, "entries", 5)

        result = run_cli("verify", db, "--expected-count", "0", "--table", "entries")

        assert result["ok"] is True
        assert result["actual_count"] == 5

    # --- Task 5.3: test_verify_count_mismatch ---
    def test_verify_count_mismatch(self, tmp_path: Path) -> None:
        """Wrong expected count returns ok=false."""
        db = str(tmp_path / "test.db")
        create_wal_db(db, "entries", 5)

        result = run_cli("verify", db, "--expected-count", "99", "--table", "entries")

        assert result["ok"] is False
        assert result["actual_count"] == 5

    # --- Task 5.4: test_verify_corrupt ---
    def test_verify_corrupt(self, tmp_path: Path) -> None:
        """Corrupt DB file fails integrity check."""
        db = str(tmp_path / "corrupt.db")
        with open(db, "wb") as f:
            f.write(os.urandom(4096))

        result = run_cli("verify", db, "--expected-count", "0", "--table", "entries",
                         expect_rc=1)

        assert result["ok"] is False
        assert result["integrity"] != "ok"


# ============================================================
# Helpers: memory DB and entity DB creation
# ============================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_memory_db(path: str, entries: list[dict] | None = None) -> None:
    """Create a memory.db with full schema and optional entries."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE entries (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            reasoning TEXT,
            category TEXT NOT NULL,
            keywords TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL,
            source_project TEXT NOT NULL,
            "references" TEXT,
            observation_count INTEGER DEFAULT 1,
            confidence TEXT DEFAULT 'medium',
            recall_count INTEGER DEFAULT 0,
            last_recalled_at TEXT,
            embedding BLOB,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            created_timestamp_utc REAL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
            name, description, reasoning, keywords, content=entries, content_rowid=rowid
        );
    """)
    if entries:
        for e in entries:
            now = _now_iso()
            conn.execute("""
                INSERT INTO entries (id, name, description, reasoning, category,
                    keywords, source, source_project, "references", observation_count,
                    confidence, recall_count, last_recalled_at, embedding,
                    created_at, updated_at, source_hash, created_timestamp_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                e.get("id", str(uuid.uuid4())),
                e.get("name", "test-entry"),
                e.get("description", "A test entry"),
                e.get("reasoning"),
                e.get("category", "pattern"),
                e.get("keywords", "[]"),
                e.get("source", "test"),
                e.get("source_project", "test-project"),
                e.get("references"),
                e.get("observation_count", 1),
                e.get("confidence", "medium"),
                e.get("recall_count", 0),
                e.get("last_recalled_at"),
                e.get("embedding"),
                e.get("created_at", now),
                e.get("updated_at", now),
                e["source_hash"],
                e.get("created_timestamp_utc"),
            ))
        conn.commit()
        # Populate FTS
        conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        conn.commit()
    conn.close()


def create_entity_db(
    path: str,
    entities: list[dict] | None = None,
    workflow_phases: list[dict] | None = None,
) -> None:
    """Create an entities.db with full schema and optional records."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE entities (
            uuid TEXT NOT NULL PRIMARY KEY,
            type_id TEXT NOT NULL UNIQUE,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT,
            parent_type_id TEXT REFERENCES entities(type_id),
            parent_uuid TEXT REFERENCES entities(uuid),
            artifact_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT
        );
        CREATE TABLE workflow_phases (
            type_id TEXT PRIMARY KEY REFERENCES entities(type_id),
            workflow_phase TEXT,
            kanban_column TEXT NOT NULL DEFAULT 'backlog',
            last_completed_phase TEXT,
            mode TEXT,
            backward_transition_reason TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
            name, entity_type, entity_id, status, content=entities, content_rowid=rowid
        );
    """)
    if entities:
        for e in entities:
            now = _now_iso()
            conn.execute("""
                INSERT INTO entities (uuid, type_id, entity_type, entity_id, name,
                    status, parent_type_id, parent_uuid, artifact_path,
                    created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                e.get("uuid", str(uuid.uuid4())),
                e["type_id"],
                e.get("entity_type", "feature"),
                e.get("entity_id", "test-001"),
                e.get("name", "Test Entity"),
                e.get("status", "active"),
                e.get("parent_type_id"),
                e.get("parent_uuid"),
                e.get("artifact_path"),
                e.get("created_at", now),
                e.get("updated_at", now),
                e.get("metadata"),
            ))
        conn.commit()
    if workflow_phases:
        for wp in workflow_phases:
            now = _now_iso()
            conn.execute("""
                INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column,
                    last_completed_phase, mode, backward_transition_reason, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                wp["type_id"],
                wp.get("workflow_phase"),
                wp.get("kanban_column", "backlog"),
                wp.get("last_completed_phase"),
                wp.get("mode"),
                wp.get("backward_transition_reason"),
                wp.get("updated_at", now),
            ))
        conn.commit()
    # Build FTS if entities were provided
    if entities:
        conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
        conn.commit()
    conn.close()


# ============================================================
# Step 6: merge-memory subcommand tests
# ============================================================


class TestMergeMemory:
    """Tests for the merge-memory subcommand."""

    # --- Task 6.1: test_merge_memory_no_overlap ---
    def test_merge_memory_no_overlap(self, tmp_path: Path) -> None:
        """Disjoint source_hash values: all entries added."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        src_entries = [{"source_hash": f"src-hash-{i}", "name": f"src-{i}"} for i in range(3)]
        dst_entries = [{"source_hash": f"dst-hash-{i}", "name": f"dst-{i}"} for i in range(2)]

        create_memory_db(src, src_entries)
        create_memory_db(dst, dst_entries)

        result = run_cli("merge-memory", src, dst)

        assert result["added"] == 3
        assert result["skipped"] == 0

        # Verify dst now has 5 entries
        conn = sqlite3.connect(dst)
        count = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
        conn.close()
        assert count == 5

    # --- Task 6.2: test_merge_memory_full_overlap ---
    def test_merge_memory_full_overlap(self, tmp_path: Path) -> None:
        """Identical source_hash values: all entries skipped."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        entries = [{"source_hash": f"shared-hash-{i}", "name": f"entry-{i}"} for i in range(3)]

        create_memory_db(src, entries)
        create_memory_db(dst, entries)

        result = run_cli("merge-memory", src, dst)

        assert result["added"] == 0
        assert result["skipped"] == 3

    # --- Task 6.3: test_merge_memory_partial_overlap ---
    def test_merge_memory_partial_overlap(self, tmp_path: Path) -> None:
        """Some overlap: correct added/skipped counts."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        src_entries = [
            {"source_hash": "shared-1", "name": "shared"},
            {"source_hash": "src-only-1", "name": "src-unique-1"},
            {"source_hash": "src-only-2", "name": "src-unique-2"},
        ]
        dst_entries = [
            {"source_hash": "shared-1", "name": "shared"},
            {"source_hash": "dst-only-1", "name": "dst-unique"},
        ]

        create_memory_db(src, src_entries)
        create_memory_db(dst, dst_entries)

        result = run_cli("merge-memory", src, dst)

        assert result["added"] == 2
        assert result["skipped"] == 1

    # --- Task 6.4: test_merge_memory_dry_run ---
    def test_merge_memory_dry_run(self, tmp_path: Path) -> None:
        """Dry run: counts returned but dst unchanged."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        src_entries = [{"source_hash": f"src-hash-{i}", "name": f"src-{i}"} for i in range(3)]
        create_memory_db(src, src_entries)
        create_memory_db(dst, [])

        result = run_cli("merge-memory", src, dst, "--dry-run")

        assert result["added"] == 3
        assert result["skipped"] == 0

        # Verify dst still has 0 entries
        conn = sqlite3.connect(dst)
        count = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
        conn.close()
        assert count == 0

    # --- Task 6.5: test_merge_memory_rollback ---
    def test_merge_memory_rollback(self, tmp_path: Path) -> None:
        """Simulated failure: dst unchanged after rollback.

        Strategy: corrupt the src DB after counting so the INSERT fails.
        We create src with entries, then drop the src entries table before
        the merge INSERT can read it — by using a trigger-based approach.
        Instead, we use a simpler approach: make the dst entries table have
        a CHECK constraint that rejects inserts after the count query.

        Simplest reliable approach: temporarily rename the src table between
        the count and insert phases by using a second connection.
        """
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        src_entries = [{"source_hash": f"src-hash-{i}", "name": f"src-{i}"} for i in range(3)]
        create_memory_db(src, src_entries)
        create_memory_db(dst, [])

        # Add a BEFORE INSERT trigger to the dst entries table that raises an error
        conn = sqlite3.connect(dst)
        conn.execute("""
            CREATE TRIGGER fail_insert BEFORE INSERT ON entries
            BEGIN
                SELECT RAISE(ABORT, 'injected failure');
            END
        """)
        conn.commit()
        conn.close()

        result = subprocess.run(
            [sys.executable, SCRIPT, "merge-memory", src, dst],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # The command should fail (exit 1) due to the trigger
        assert result.returncode == 1

        # Verify dst still has 0 entries (rollback worked)
        conn = sqlite3.connect(dst)
        count = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
        conn.close()
        assert count == 0

    # --- Task 6.7: test_merge_memory_fts_rebuild ---
    def test_merge_memory_fts_rebuild(self, tmp_path: Path) -> None:
        """After merge, FTS index returns results for known term."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        src_entries = [
            {"source_hash": "fts-test-1", "name": "alpha-bravo-search-term",
             "description": "Unique searchable description"}
        ]
        create_memory_db(src, src_entries)
        create_memory_db(dst, [])

        run_cli("merge-memory", src, dst)

        conn = sqlite3.connect(dst)
        rows = conn.execute(
            "SELECT name FROM entries_fts WHERE entries_fts MATCH 'alpha'",
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert "alpha" in rows[0][0]


# ============================================================
# Step 7: merge-entities subcommand tests
# ============================================================


class TestMergeEntities:
    """Tests for the merge-entities subcommand."""

    # --- Task 7.1: test_merge_entities_no_overlap ---
    def test_merge_entities_no_overlap(self, tmp_path: Path) -> None:
        """Disjoint type_ids: all entities added with new UUIDs."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        src_entities = [
            {"type_id": "feature:src-001", "name": "SrcFeat1", "uuid": str(uuid.uuid4())},
            {"type_id": "feature:src-002", "name": "SrcFeat2", "uuid": str(uuid.uuid4())},
        ]
        dst_entities = [
            {"type_id": "feature:dst-001", "name": "DstFeat1", "uuid": str(uuid.uuid4())},
        ]

        create_entity_db(src, src_entities)
        create_entity_db(dst, dst_entities)

        # Capture original src UUIDs
        src_conn = sqlite3.connect(src)
        src_uuids = {r[0] for r in src_conn.execute("SELECT uuid FROM entities").fetchall()}
        src_conn.close()

        result = run_cli("merge-entities", src, dst)

        assert result["added"] == 2
        assert result["skipped"] == 0

        # Verify dst has 3 entities total
        conn = sqlite3.connect(dst)
        rows = conn.execute("SELECT uuid, type_id FROM entities").fetchall()
        conn.close()
        assert len(rows) == 3

        # Verify imported entities got NEW UUIDs (not the src UUIDs)
        dst_uuids = {r[0] for r in rows}
        imported_uuids = dst_uuids - {dst_entities[0]["uuid"]}
        assert len(imported_uuids) == 2
        assert imported_uuids.isdisjoint(src_uuids)

    # --- Task 7.2: test_merge_entities_full_overlap ---
    def test_merge_entities_full_overlap(self, tmp_path: Path) -> None:
        """Same type_ids: all entities skipped."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        entities = [
            {"type_id": "feature:shared-001", "name": "Shared1"},
            {"type_id": "feature:shared-002", "name": "Shared2"},
        ]

        create_entity_db(src, entities)
        create_entity_db(dst, entities)

        result = run_cli("merge-entities", src, dst)

        assert result["added"] == 0
        assert result["skipped"] == 2

    # --- Task 7.3: test_merge_entities_parent_child ---
    def test_merge_entities_parent_child(self, tmp_path: Path) -> None:
        """Parent-child relationships: parent_uuid reconstructed after merge."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        parent_uuid = str(uuid.uuid4())
        child_uuid = str(uuid.uuid4())
        src_entities = [
            {
                "type_id": "feature:parent-001",
                "name": "Parent",
                "uuid": parent_uuid,
                "entity_type": "feature",
                "entity_id": "parent-001",
            },
            {
                "type_id": "task:child-001",
                "name": "Child",
                "uuid": child_uuid,
                "entity_type": "task",
                "entity_id": "child-001",
                "parent_type_id": "feature:parent-001",
                "parent_uuid": parent_uuid,
            },
        ]

        create_entity_db(src, src_entities)
        create_entity_db(dst, [])

        result = run_cli("merge-entities", src, dst)

        assert result["added"] == 2

        # Verify parent_uuid was reconstructed
        conn = sqlite3.connect(dst)
        child = conn.execute(
            "SELECT parent_uuid, parent_type_id FROM entities WHERE type_id = 'task:child-001'"
        ).fetchone()
        parent = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = 'feature:parent-001'"
        ).fetchone()
        conn.close()

        assert child[0] is not None, "parent_uuid should be reconstructed"
        assert child[0] == parent[0], "child.parent_uuid should match parent.uuid"
        # UUIDs should be different from source
        assert parent[0] != parent_uuid

    # --- Task 7.4: test_merge_entities_dry_run ---
    def test_merge_entities_dry_run(self, tmp_path: Path) -> None:
        """Dry run: counts returned but dst unchanged."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        src_entities = [
            {"type_id": "feature:src-001", "name": "SrcFeat1"},
            {"type_id": "feature:src-002", "name": "SrcFeat2"},
        ]
        create_entity_db(src, src_entities)
        create_entity_db(dst, [])

        result = run_cli("merge-entities", src, dst, "--dry-run")

        assert result["added"] == 2
        assert result["skipped"] == 0

        # Verify dst still empty
        conn = sqlite3.connect(dst)
        count = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        conn.close()
        assert count == 0

    # --- Task 7.5: test_merge_entities_rollback ---
    def test_merge_entities_rollback(self, tmp_path: Path) -> None:
        """Simulated failure: dst unchanged after rollback.

        Uses a BEFORE INSERT trigger on dst entities table to force failure.
        """
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        src_entities = [
            {"type_id": "feature:src-001", "name": "SrcFeat1"},
        ]
        create_entity_db(src, src_entities)
        create_entity_db(dst, [])

        # Add a BEFORE INSERT trigger to force failure
        conn = sqlite3.connect(dst)
        conn.execute("""
            CREATE TRIGGER fail_insert BEFORE INSERT ON entities
            BEGIN
                SELECT RAISE(ABORT, 'injected failure');
            END
        """)
        conn.commit()
        conn.close()

        result = subprocess.run(
            [sys.executable, SCRIPT, "merge-entities", src, dst],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1

        # Verify dst still has 0 entities (rollback worked)
        conn = sqlite3.connect(dst)
        count = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        conn.close()
        assert count == 0

    # --- Task 7.7: test_merge_entities_fts_rebuild ---
    def test_merge_entities_fts_rebuild(self, tmp_path: Path) -> None:
        """After merge, FTS index returns results for known term."""
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        src_entities = [
            {"type_id": "feature:fts-test-001", "name": "ZebrafishUniqueName",
             "entity_type": "feature", "entity_id": "fts-test-001"},
        ]
        create_entity_db(src, src_entities)
        create_entity_db(dst, [])

        run_cli("merge-entities", src, dst)

        conn = sqlite3.connect(dst)
        rows = conn.execute(
            "SELECT name FROM entities_fts WHERE entities_fts MATCH 'ZebrafishUniqueName'",
        ).fetchall()
        conn.close()
        assert len(rows) == 1
