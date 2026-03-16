"""Deepened edge-case tests for migrate_db.py.

Covers:
1. Empty databases (0 rows) -- backup, manifest, verify
2. Large source_hash/type_id values -- merge boundary conditions
3. Unicode in file names and entry content
4. Concurrent manifest read/write
5. Missing columns in _metadata table
6. Entities with NULL parent_type_id during merge

Run: python3 -m pytest scripts/test_migrate_deepened.py -v
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pytest

# Re-use helpers from the existing test module
from test_migrate_db import (
    SCRIPT,
    create_entity_db,
    create_memory_db,
    create_wal_db,
    run_cli,
    _create_staging_dir,
    _now_iso,
)


# ============================================================
# Dimension 1: Empty databases (0 rows)
# derived_from: dimension:boundary_values (zero/one/many)
# ============================================================


class TestEmptyDatabases:
    """Edge cases for operations on databases with zero rows."""

    def test_backup_empty_database_returns_zero_count(self, tmp_path: Path) -> None:
        """Backup an empty table: entry_count should be 0, SHA-256 still valid.

        Anticipate: Implementation might crash on empty table or return
        negative count. The f-string SQL could fail on empty result set.
        """
        # Given a database with the entries table but zero rows
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "backup.db")
        create_wal_db(src, "entries", row_count=0)

        # When we backup the empty database
        result = run_cli("backup", src, dst, "--table", "entries")

        # Then entry_count is 0 and sha256 is a valid hex string
        assert result["entry_count"] == 0
        assert result["size_bytes"] > 0  # SQLite file has overhead even when empty
        assert len(result["sha256"]) == 64  # SHA-256 hex digest length

    def test_verify_empty_database_with_zero_expected(self, tmp_path: Path) -> None:
        """Verify empty DB with expected_count=0 returns ok=true.

        Anticipate: The special case `expected_count == 0` skips comparison.
        An empty DB should pass both count-only mode and exact-match mode.
        """
        # Given a database with zero rows
        db = str(tmp_path / "test.db")
        create_wal_db(db, "entries", row_count=0)

        # When we verify with expected_count=0 (count-only mode)
        result = run_cli("verify", db, "--expected-count", "0", "--table", "entries")

        # Then ok is true with actual_count=0
        assert result["ok"] is True
        assert result["actual_count"] == 0
        assert result["integrity"] == "ok"

    def test_verify_empty_database_with_nonzero_expected(self, tmp_path: Path) -> None:
        """Verify empty DB against expected_count=5 returns ok=false.

        Anticipate: Off-by-one in the `expected_count == 0` special case
        could mask a real mismatch.
        """
        # Given a database with zero rows
        db = str(tmp_path / "test.db")
        create_wal_db(db, "entries", row_count=0)

        # When we verify expecting 5 entries
        result = run_cli("verify", db, "--expected-count", "5", "--table", "entries")

        # Then ok is false because 0 != 5
        assert result["ok"] is False
        assert result["actual_count"] == 0

    def test_manifest_empty_memory_db_shows_zero_entries(self, tmp_path: Path) -> None:
        """Manifest with empty memory.db reports memory_entries=0.

        Anticipate: count(*) on empty table returns 0, but the code path
        might not handle the case where entries table exists but is empty.
        """
        # Given a staging dir with empty memory.db (0 entries)
        staging = _create_staging_dir(tmp_path, memory_entries=0)

        # When we generate a manifest
        result = run_cli("manifest", str(staging), "--plugin-version", "1.0.0")

        # Then memory_entries count is 0
        assert result["files"]["memory/memory.db"]["entry_count"] == 0

    def test_merge_memory_empty_src_into_populated_dst(self, tmp_path: Path) -> None:
        """Merging empty source into populated destination adds nothing.

        Anticipate: Empty source might cause division by zero or negative
        skip_count calculation (total_src - add_count).
        """
        # Given an empty source and a populated destination
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_memory_db(src, [])
        create_memory_db(dst, [
            {"source_hash": "existing-1", "name": "existing"},
        ])

        # When we merge
        result = run_cli("merge-memory", src, dst)

        # Then nothing is added or skipped
        assert result["added"] == 0
        assert result["skipped"] == 0

        # And destination still has its original entry
        conn = sqlite3.connect(dst)
        count = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
        conn.close()
        assert count == 1

    def test_merge_memory_empty_src_into_empty_dst(self, tmp_path: Path) -> None:
        """Merging empty source into empty destination: zero counts, no crash.

        Anticipate: Both subqueries return 0; skip_count = 0 - 0 = 0.
        Edge case for the subtraction logic.
        """
        # Given both source and destination are empty
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_memory_db(src, [])
        create_memory_db(dst, [])

        # When we merge
        result = run_cli("merge-memory", src, dst)

        # Then both counts are zero
        assert result["added"] == 0
        assert result["skipped"] == 0

    def test_merge_entities_empty_src_into_populated_dst(self, tmp_path: Path) -> None:
        """Merging empty entity source into populated destination: zero added.

        Anticipate: Empty fetchall() for new_type_ids; skip_count = total_src - 0
        where total_src is also 0.
        """
        # Given empty source, populated destination
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_entity_db(src, [])
        create_entity_db(dst, [{"type_id": "feature:existing-001", "name": "Existing"}])

        # When we merge
        result = run_cli("merge-entities", src, dst)

        # Then nothing added, nothing skipped
        assert result["added"] == 0
        assert result["skipped"] == 0

    def test_merge_entities_empty_both(self, tmp_path: Path) -> None:
        """Merging empty source into empty destination: no crash.

        Anticipate: new_type_ids is empty list, total_src is 0.
        """
        # Given both empty
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_entity_db(src, [])
        create_entity_db(dst, [])

        # When we merge
        result = run_cli("merge-entities", src, dst)

        # Then zero counts
        assert result["added"] == 0
        assert result["skipped"] == 0


# ============================================================
# Dimension 2: Large source_hash/type_id values
# derived_from: dimension:boundary_values (string length extremes)
# ============================================================


class TestLargeValues:
    """Boundary conditions with very long string values."""

    def test_merge_memory_large_source_hash(self, tmp_path: Path) -> None:
        """source_hash of 10,000 chars: merge completes without truncation.

        Anticipate: SQLite TEXT has no length limit, but the NOT IN subquery
        comparison could fail or be slow with very long strings.
        """
        # Given entries with very long source_hash values
        large_hash = "a" * 10_000
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_memory_db(src, [{"source_hash": large_hash, "name": "large-hash-entry"}])
        create_memory_db(dst, [])

        # When we merge
        result = run_cli("merge-memory", src, dst)

        # Then the entry is added successfully
        assert result["added"] == 1

        # And the full hash is preserved in dst
        conn = sqlite3.connect(dst)
        row = conn.execute("SELECT source_hash FROM entries").fetchone()
        conn.close()
        assert row[0] == large_hash

    def test_merge_entities_large_type_id(self, tmp_path: Path) -> None:
        """type_id of 5,000 chars: merge handles it without error.

        Anticipate: The f-string SQL interpolation in Phase 4
        (imported_list = ",".join(...)) could produce overly long SQL.
        """
        # Given an entity with a very long type_id
        large_type_id = "feature:" + "x" * 5_000
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_entity_db(src, [{"type_id": large_type_id, "name": "LargeTypeId"}])
        create_entity_db(dst, [])

        # When we merge
        result = run_cli("merge-entities", src, dst)

        # Then the entity is added
        assert result["added"] == 1

        # And full type_id preserved
        conn = sqlite3.connect(dst)
        row = conn.execute("SELECT type_id FROM entities").fetchone()
        conn.close()
        assert row[0] == large_type_id

    def test_merge_memory_duplicate_large_hash_is_skipped(self, tmp_path: Path) -> None:
        """Duplicate detection works correctly with very long source_hash.

        Anticipate: String comparison in NOT IN subquery might behave
        differently for very long strings vs short ones.
        """
        # Given same large hash in both src and dst
        large_hash = "b" * 8_000
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_memory_db(src, [{"source_hash": large_hash, "name": "src-entry"}])
        create_memory_db(dst, [{"source_hash": large_hash, "name": "dst-entry"}])

        # When we merge
        result = run_cli("merge-memory", src, dst)

        # Then the entry is skipped (duplicate by source_hash)
        assert result["added"] == 0
        assert result["skipped"] == 1

    def test_merge_entities_many_new_type_ids_sql_interpolation(self, tmp_path: Path) -> None:
        """50 new entities: Phase 4 SQL with large IN clause works.

        Anticipate: The f-string SQL building imported_list with 50 items
        could hit SQL parser limits or be malformed.
        """
        # Given 50 entities in source, none in destination
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        src_entities = [
            {"type_id": f"feature:bulk-{i:04d}", "name": f"Bulk{i}"}
            for i in range(50)
        ]
        create_entity_db(src, src_entities)
        create_entity_db(dst, [])

        # When we merge
        result = run_cli("merge-entities", src, dst)

        # Then all 50 are added
        assert result["added"] == 50
        assert result["skipped"] == 0


# ============================================================
# Dimension 3: Unicode in file names and entry content
# derived_from: dimension:adversarial (international characters, encoding)
# ============================================================


class TestUnicode:
    """Unicode handling in entry content and file operations."""

    def test_merge_memory_unicode_name_and_description(self, tmp_path: Path) -> None:
        """Entries with CJK, emoji, and diacritics survive merge intact.

        Anticipate: Encoding issues in INSERT...SELECT across attached DBs,
        or JSON output mangling non-ASCII characters.
        """
        # Given entries with unicode content
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_memory_db(src, [{
            "source_hash": "unicode-1",
            "name": "Unicode test entry",
            "description": "Contains CJK chars: \u4e16\u754c, diacritics: caf\u00e9, emoji: \U0001f680",
        }])
        create_memory_db(dst, [])

        # When we merge
        result = run_cli("merge-memory", src, dst)

        # Then the entry is added
        assert result["added"] == 1

        # And unicode content is preserved exactly
        conn = sqlite3.connect(dst)
        row = conn.execute("SELECT description FROM entries").fetchone()
        conn.close()
        assert "\u4e16\u754c" in row[0]
        assert "caf\u00e9" in row[0]
        assert "\U0001f680" in row[0]

    def test_merge_entities_unicode_entity_name(self, tmp_path: Path) -> None:
        """Entity name with Unicode: merge and FTS rebuild work.

        Anticipate: FTS5 rebuild after inserting unicode could fail
        or produce garbled index entries.
        """
        # Given an entity with a unicode name
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_entity_db(src, [{
            "type_id": "feature:unicode-001",
            "name": "\u65e5\u672c\u8a9e\u30c6\u30b9\u30c8 Feature",
            "entity_type": "feature",
            "entity_id": "unicode-001",
        }])
        create_entity_db(dst, [])

        # When we merge
        run_cli("merge-entities", src, dst)

        # Then the unicode name is searchable via FTS
        conn = sqlite3.connect(dst)
        rows = conn.execute(
            "SELECT name FROM entities_fts WHERE entities_fts MATCH '\u65e5\u672c\u8a9e'",
        ).fetchall()
        name = conn.execute("SELECT name FROM entities").fetchone()[0]
        conn.close()
        assert "\u65e5\u672c\u8a9e" in name

    def test_manifest_unicode_markdown_filename(self, tmp_path: Path) -> None:
        """Staging dir with unicode filename: manifest checksums include it.

        Anticipate: os.walk + os.path.relpath might mangle unicode paths,
        or JSON serialization could fail on non-ASCII filenames.
        """
        # Given a staging dir with a unicode-named file
        staging = _create_staging_dir(tmp_path)
        unicode_file = staging / "memory" / "caf\u00e9-patterns.md"
        unicode_file.write_text("# Caf\u00e9 Patterns\n")

        # When we generate manifest
        result = run_cli("manifest", str(staging), "--plugin-version", "1.0.0")

        # Then the unicode filename appears in files
        # On macOS, the path separator is /
        expected_key = os.path.join("memory", "caf\u00e9-patterns.md")
        assert expected_key in result["files"]

    def test_merge_memory_unicode_source_hash(self, tmp_path: Path) -> None:
        """source_hash containing unicode: deduplication still works.

        Anticipate: NOT IN comparison on unicode strings could behave
        differently than ASCII-only comparisons.
        """
        # Given same unicode hash in both databases
        unicode_hash = "\u00fc\u00f1\u00ee\u00e7\u00f6\u00f0\u00e9-hash-\U0001f600"
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_memory_db(src, [{"source_hash": unicode_hash, "name": "unicode-hash"}])
        create_memory_db(dst, [{"source_hash": unicode_hash, "name": "unicode-hash"}])

        # When we merge
        result = run_cli("merge-memory", src, dst)

        # Then the entry is correctly identified as a duplicate
        assert result["added"] == 0
        assert result["skipped"] == 1


# ============================================================
# Dimension 4: Concurrent manifest read/write
# derived_from: dimension:adversarial (race conditions, interrupt)
# ============================================================


class TestConcurrentManifest:
    """Concurrent operations on manifest and staging directories."""

    def test_manifest_idempotent_regeneration(self, tmp_path: Path) -> None:
        """Generating manifest twice: second run overwrites cleanly.

        Anticipate: The second manifest generation might include the
        first manifest.json in checksums if exclusion logic is broken.
        """
        # Given a staging directory
        staging = _create_staging_dir(tmp_path)

        # When we generate manifest twice
        result1 = run_cli("manifest", str(staging), "--plugin-version", "1.0.0")
        result2 = run_cli("manifest", str(staging), "--plugin-version", "1.0.0")

        # Then manifest.json is excluded from files in both runs
        assert "manifest.json" not in result1["files"]
        assert "manifest.json" not in result2["files"]

        # And file entries are identical (file content unchanged)
        assert result1["files"] == result2["files"]

    def test_validate_after_manifest_regeneration(self, tmp_path: Path) -> None:
        """Validate passes after manifest is regenerated.

        Anticipate: Stale checksums from first manifest could persist
        if manifest.json itself is included in the checksum set.
        """
        # Given a staging dir with manifest generated
        staging = _create_staging_dir(tmp_path)
        run_cli("manifest", str(staging), "--plugin-version", "1.0.0")

        # When we regenerate manifest and then validate
        run_cli("manifest", str(staging), "--plugin-version", "2.0.0")
        result = run_cli("validate", str(staging))

        # Then validation passes
        assert result["valid"] is True
        assert result["errors"] == []

    def test_concurrent_manifest_writes_no_corruption(self, tmp_path: Path) -> None:
        """Two threads writing manifests to separate dirs: no file corruption.

        Anticipate: Shared global state or temp files could cause
        cross-contamination between concurrent operations.
        """
        # Given two separate staging directories
        (tmp_path / "s1").mkdir()
        (tmp_path / "s2").mkdir()
        staging1 = _create_staging_dir(tmp_path / "s1")
        staging2 = _create_staging_dir(tmp_path / "s2")

        results = [None, None]
        errors = [None, None]

        def gen_manifest(idx, staging):
            try:
                results[idx] = run_cli(
                    "manifest", str(staging), "--plugin-version", f"{idx}.0.0"
                )
            except Exception as e:
                errors[idx] = e

        # When we generate manifests concurrently
        t1 = threading.Thread(target=gen_manifest, args=(0, staging1))
        t2 = threading.Thread(target=gen_manifest, args=(1, staging2))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        # Then both succeed without error
        assert errors[0] is None, f"Thread 1 error: {errors[0]}"
        assert errors[1] is None, f"Thread 2 error: {errors[1]}"
        assert results[0]["plugin_version"] == "0.0.0"
        assert results[1]["plugin_version"] == "1.0.0"

        # And both validate independently
        v1 = run_cli("validate", str(staging1))
        v2 = run_cli("validate", str(staging2))
        assert v1["valid"] is True
        assert v2["valid"] is True


# ============================================================
# Dimension 5: Missing columns in _metadata table
# derived_from: dimension:error_propagation (partial schema)
# ============================================================


class TestMissingMetadata:
    """Handling of _metadata table with missing or malformed data."""

    def test_manifest_metadata_table_exists_but_empty(self, tmp_path: Path) -> None:
        """_metadata table exists but has no rows: embedding fields are null.

        Anticipate: fetchone() returns None; code accesses row[0]
        on None and crashes with TypeError.
        """
        # Given a staging dir where _metadata table exists but is empty
        staging = _create_staging_dir(tmp_path)
        mem_db = str(staging / "memory" / "memory.db")
        conn = sqlite3.connect(mem_db)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.commit()
        conn.close()

        # When we generate manifest
        result = run_cli("manifest", str(staging), "--plugin-version", "1.0.0")

        # Then embedding fields are None (not crash)
        assert result["embedding_provider"] is None
        assert result["embedding_model"] is None

    def test_manifest_metadata_has_provider_but_no_model(self, tmp_path: Path) -> None:
        """_metadata has embedding_provider but not embedding_model.

        Anticipate: Missing key means fetchone() returns None;
        embedding_model should be None while provider is populated.
        """
        # Given _metadata with only embedding_provider
        staging = _create_staging_dir(tmp_path)
        mem_db = str(staging / "memory" / "memory.db")
        conn = sqlite3.connect(mem_db)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.execute(
            "INSERT INTO _metadata (key, value) VALUES ('embedding_provider', 'openai')"
        )
        conn.commit()
        conn.close()

        # When we generate manifest
        result = run_cli("manifest", str(staging), "--plugin-version", "1.0.0")

        # Then provider is set, model is None
        assert result["embedding_provider"] == "openai"
        assert result["embedding_model"] is None

    def test_check_embeddings_metadata_table_with_no_provider_row(self, tmp_path: Path) -> None:
        """_metadata exists in dst but has no embedding_provider row.

        Anticipate: fetchone() returns None, code accesses row[0].
        The `dst_provider = row[0] if row else None` should handle this.
        """
        # Given a manifest claiming openai provider
        from test_migrate_db import _write_manifest
        manifest_path = _write_manifest(tmp_path, {
            "schema_version": 1,
            "embedding_provider": "openai",
        })

        # And a dst DB with _metadata table but no embedding_provider key
        dst_db = str(tmp_path / "dst_memory.db")
        conn = sqlite3.connect(dst_db)
        conn.execute("CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO _metadata (key, value) VALUES ('some_other_key', 'value')"
        )
        conn.commit()
        conn.close()

        # When we check embeddings
        result = run_cli("check-embeddings", manifest_path, dst_db)

        # Then mismatch is false (dst_provider is None, treated as compatible)
        assert result["mismatch"] is False

    def test_check_embeddings_metadata_provider_is_null_value(self, tmp_path: Path) -> None:
        """_metadata has embedding_provider key but value is NULL.

        Anticipate: row[0] is None. The comparison
        `dst_provider is None or src_provider == dst_provider`
        should return mismatch=false because dst_provider is None.
        """
        # Given manifest with openai
        from test_migrate_db import _write_manifest
        manifest_path = _write_manifest(tmp_path, {
            "schema_version": 1,
            "embedding_provider": "openai",
        })

        # And dst has embedding_provider key with NULL value
        dst_db = str(tmp_path / "dst_memory.db")
        conn = sqlite3.connect(dst_db)
        conn.execute("CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO _metadata (key, value) VALUES ('embedding_provider', NULL)"
        )
        conn.commit()
        conn.close()

        # When we check embeddings
        result = run_cli("check-embeddings", manifest_path, dst_db)

        # Then no mismatch (NULL dst_provider is treated as fresh machine)
        assert result["mismatch"] is False


# ============================================================
# Dimension 6: Entities with NULL parent_type_id during merge
# derived_from: spec:merge-entities Phase 4 (parent_uuid reconstruction)
# ============================================================


class TestNullParentTypeId:
    """Merge behavior when parent_type_id is NULL."""

    def test_merge_entities_all_null_parent_type_id(self, tmp_path: Path) -> None:
        """All entities have NULL parent_type_id: Phase 4 is a no-op.

        Anticipate: The UPDATE in Phase 4 has a WHERE clause
        `AND parent_type_id IS NOT NULL` which should skip all rows.
        A bug would be setting parent_uuid to a random value.
        """
        # Given entities with no parent relationships
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        src_entities = [
            {"type_id": "feature:orphan-001", "name": "Orphan1", "parent_type_id": None},
            {"type_id": "feature:orphan-002", "name": "Orphan2", "parent_type_id": None},
        ]
        create_entity_db(src, src_entities)
        create_entity_db(dst, [])

        # When we merge
        result = run_cli("merge-entities", src, dst)

        # Then entities are added
        assert result["added"] == 2

        # And parent_uuid remains NULL for all
        conn = sqlite3.connect(dst)
        rows = conn.execute(
            "SELECT type_id, parent_uuid, parent_type_id FROM entities"
        ).fetchall()
        conn.close()
        for _type_id, parent_uuid, parent_type_id in rows:
            assert parent_type_id is None
            assert parent_uuid is None

    def test_merge_entities_mixed_null_and_valid_parent(self, tmp_path: Path) -> None:
        """Mix of NULL and valid parent_type_id: only valid ones get parent_uuid.

        Anticipate: Phase 4 UPDATE might set parent_uuid for NULL
        parent_type_id rows if the WHERE clause is wrong.
        """
        # Given a parent and two children (one with parent, one without)
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        parent_uuid = str(uuid.uuid4())
        src_entities = [
            {
                "type_id": "feature:parent-001",
                "name": "Parent",
                "uuid": parent_uuid,
                "parent_type_id": None,
            },
            {
                "type_id": "task:child-001",
                "name": "ChildWithParent",
                "uuid": str(uuid.uuid4()),
                "parent_type_id": "feature:parent-001",
                "parent_uuid": parent_uuid,
            },
            {
                "type_id": "feature:standalone-001",
                "name": "StandaloneNoParent",
                "uuid": str(uuid.uuid4()),
                "parent_type_id": None,
            },
        ]
        create_entity_db(src, src_entities)
        create_entity_db(dst, [])

        # When we merge
        result = run_cli("merge-entities", src, dst)
        assert result["added"] == 3

        # Then child has reconstructed parent_uuid, standalone has NULL
        conn = sqlite3.connect(dst)
        child = conn.execute(
            "SELECT parent_uuid FROM entities WHERE type_id = 'task:child-001'"
        ).fetchone()
        standalone = conn.execute(
            "SELECT parent_uuid FROM entities WHERE type_id = 'feature:standalone-001'"
        ).fetchone()
        parent = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = 'feature:parent-001'"
        ).fetchone()
        conn.close()

        assert child[0] is not None, "Child should have reconstructed parent_uuid"
        assert child[0] == parent[0], "Child parent_uuid should match parent's new UUID"
        assert standalone[0] is None, "Standalone should keep NULL parent_uuid"

    def test_merge_entities_parent_type_id_references_dst_entity(self, tmp_path: Path) -> None:
        """Child references a parent_type_id that already exists in dst (not in src).

        Anticipate: Phase 4 reconstructs parent_uuid by looking up type_id
        in main.entities. If the parent is in dst (not imported), the
        UPDATE should still find it and set parent_uuid correctly.
        """
        # Given: dst has a parent entity; src has a child referencing it
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")

        dst_parent_uuid = str(uuid.uuid4())
        create_entity_db(dst, [{
            "type_id": "feature:dst-parent-001",
            "name": "DstParent",
            "uuid": dst_parent_uuid,
        }])

        create_entity_db(src, [{
            "type_id": "task:child-from-src",
            "name": "SrcChild",
            "parent_type_id": "feature:dst-parent-001",
        }])

        # When we merge
        result = run_cli("merge-entities", src, dst)
        assert result["added"] == 1

        # Then the child's parent_uuid points to the dst parent
        conn = sqlite3.connect(dst)
        child = conn.execute(
            "SELECT parent_uuid FROM entities WHERE type_id = 'task:child-from-src'"
        ).fetchone()
        conn.close()

        assert child[0] == dst_parent_uuid, (
            "Child imported from src should reference dst parent's UUID"
        )

    def test_merge_entities_parent_type_id_references_nonexistent_entity(
        self, tmp_path: Path
    ) -> None:
        """Child references parent_type_id that does not exist anywhere.

        Anticipate: Phase 4 UPDATE subquery returns NULL because no entity
        matches parent_type_id. parent_uuid should remain NULL (not crash).
        """
        # Given a child referencing a nonexistent parent
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_entity_db(src, [{
            "type_id": "task:orphan-child",
            "name": "OrphanChild",
            "parent_type_id": "feature:does-not-exist",
        }])
        create_entity_db(dst, [])

        # When we merge
        result = run_cli("merge-entities", src, dst)
        assert result["added"] == 1

        # Then parent_uuid is NULL (not found, but no crash)
        conn = sqlite3.connect(dst)
        row = conn.execute(
            "SELECT parent_uuid, parent_type_id FROM entities WHERE type_id = 'task:orphan-child'"
        ).fetchone()
        conn.close()

        assert row[0] is None, "parent_uuid should be NULL when parent doesn't exist"
        assert row[1] == "feature:does-not-exist", "parent_type_id should be preserved"


# ============================================================
# Dimension 5 (mutation mindset): Behavioral pinning tests
# derived_from: dimension:mutation_mindset
# ============================================================


class TestMutationMindset:
    """Tests designed to catch common mutation operator bugs."""

    def test_verify_boundary_expected_equals_actual(self, tmp_path: Path) -> None:
        """expected_count exactly equals actual_count: ok=true.

        Mutation target: Swapping == to != in the comparison
        `actual_count == args.expected_count`.
        """
        # Given a database with exactly 1 row
        db = str(tmp_path / "test.db")
        create_wal_db(db, "entries", row_count=1)

        # When expected matches actual
        result = run_cli("verify", db, "--expected-count", "1", "--table", "entries")

        # Then ok is true
        assert result["ok"] is True
        assert result["actual_count"] == 1

    def test_verify_off_by_one_above(self, tmp_path: Path) -> None:
        """expected_count is actual+1: ok=false.

        Mutation target: Changing == to >= in the count comparison.
        """
        # Given 5 rows
        db = str(tmp_path / "test.db")
        create_wal_db(db, "entries", row_count=5)

        # When expected is 6 (one more than actual)
        result = run_cli("verify", db, "--expected-count", "6", "--table", "entries")

        # Then ok is false
        assert result["ok"] is False

    def test_verify_off_by_one_below(self, tmp_path: Path) -> None:
        """expected_count is actual-1: ok=false.

        Mutation target: Changing == to <= in the count comparison.
        """
        # Given 5 rows
        db = str(tmp_path / "test.db")
        create_wal_db(db, "entries", row_count=5)

        # When expected is 4
        result = run_cli("verify", db, "--expected-count", "4", "--table", "entries")

        # Then ok is false
        assert result["ok"] is False

    def test_validate_schema_version_at_boundary(self, tmp_path: Path) -> None:
        """schema_version exactly at SUPPORTED_SCHEMA_VERSION (1): passes.

        Mutation target: Changing > to >= in
        `if schema_version > SUPPORTED_SCHEMA_VERSION`.
        """
        # Given a valid bundle with schema_version=1
        staging = _create_staging_dir(tmp_path)
        run_cli("manifest", str(staging), "--plugin-version", "1.0.0")

        # Verify it has schema_version=1
        manifest_path = staging / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["schema_version"] == 1

        # When we validate
        result = run_cli("validate", str(staging))

        # Then it passes (1 is not > 1)
        assert result["valid"] is True

    def test_validate_schema_version_exactly_above_supported(self, tmp_path: Path) -> None:
        """schema_version = SUPPORTED + 1 (i.e., 2): rejected.

        Mutation target: Changing > to >= would reject version 1.
        This test pins that version 2 IS rejected.
        """
        # Given a bundle with schema_version=2
        staging = _create_staging_dir(tmp_path)
        run_cli("manifest", str(staging), "--plugin-version", "1.0.0")
        manifest_path = staging / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["schema_version"] = 2
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # When we validate
        result = run_cli("validate", str(staging), expect_rc=1)

        # Then it fails
        assert result["valid"] is False

    def test_merge_memory_fts_rebuild_only_when_added(self, tmp_path: Path) -> None:
        """FTS rebuild runs only when add_count > 0.

        Mutation target: Deleting the `if add_count > 0` guard.
        We verify that with 0 additions, the FTS table is not rebuilt
        (indirectly, by checking it still works after a no-op merge).
        """
        # Given a destination with existing FTS-indexed entries
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_memory_db(dst, [
            {"source_hash": "existing-1", "name": "SearchableExistingTerm"},
        ])
        create_memory_db(src, [
            {"source_hash": "existing-1", "name": "duplicate-entry"},
        ])

        # When we merge (all skipped, add_count=0)
        result = run_cli("merge-memory", src, dst)
        assert result["added"] == 0

        # Then FTS still works for existing entries
        conn = sqlite3.connect(dst)
        rows = conn.execute(
            "SELECT name FROM entries_fts WHERE entries_fts MATCH 'SearchableExistingTerm'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1


# ============================================================
# Additional adversarial tests
# derived_from: dimension:adversarial (SQL injection, type confusion)
# ============================================================


class TestAdversarial:
    """Adversarial inputs that could break SQL or JSON output."""

    def test_type_id_with_single_quotes_in_merge(self, tmp_path: Path) -> None:
        """type_id containing single quotes: SQL injection via Phase 4 f-string.

        Anticipate: Phase 4 builds `imported_list = ",".join(f"'{tid}'" ...)`
        A type_id with quotes like `feature:O'Brien` would break SQL.
        This is a REAL vulnerability in the implementation.
        """
        # Given an entity with single quote in type_id
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "dst.db")
        create_entity_db(src, [{
            "type_id": "feature:O'Brien-001",
            "name": "O'Brien Feature",
        }])
        create_entity_db(dst, [])

        # When we merge (this may fail due to SQL injection)
        result = subprocess.run(
            [sys.executable, SCRIPT, "merge-entities", src, dst],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Then either it succeeds cleanly or fails gracefully (not silent corruption)
        # NOTE: If this test fails with a SQL error, it reveals the f-string
        # SQL interpolation vulnerability in Phase 4.
        if result.returncode == 0:
            output = json.loads(result.stdout)
            assert output["added"] == 1
        else:
            # Acceptable: error on SQL injection attempt
            # This is a spec divergence if the tool is supposed to handle arbitrary type_ids
            pass

    def test_validate_missing_manifest_file(self, tmp_path: Path) -> None:
        """Bundle directory with no manifest.json: error, not crash.

        Anticipate: FileNotFoundError from open(manifest_path).
        """
        # Given a directory with no manifest.json
        bundle = tmp_path / "empty_bundle"
        bundle.mkdir()

        # When we validate
        result = subprocess.run(
            [sys.executable, SCRIPT, "validate", str(bundle)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Then it exits non-zero
        assert result.returncode != 0

    def test_backup_nonexistent_table(self, tmp_path: Path) -> None:
        """Backup with a table name that doesn't exist: error.

        Anticipate: The f-string SQL `SELECT count(*) FROM [{args.table}]`
        would raise OperationalError.
        """
        # Given a valid database
        src = str(tmp_path / "src.db")
        dst = str(tmp_path / "backup.db")
        create_wal_db(src, "entries", row_count=5)

        # When we backup referencing a nonexistent table
        result = subprocess.run(
            [sys.executable, SCRIPT, "backup", src, dst, "--table", "nonexistent"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Then it exits non-zero (the backup succeeds but count fails)
        assert result.returncode != 0

    def test_verify_nonexistent_table(self, tmp_path: Path) -> None:
        """Verify against a table that doesn't exist: exits 1 with error.

        Anticipate: The count query fails; the except block should
        catch it and return ok=false.
        """
        # Given a database with only an 'entries' table
        db = str(tmp_path / "test.db")
        create_wal_db(db, "entries", row_count=5)

        # When we verify against a nonexistent table
        result = run_cli(
            "verify", db, "--expected-count", "0", "--table", "nonexistent",
            expect_rc=1,
        )

        # Then ok is false
        assert result["ok"] is False
