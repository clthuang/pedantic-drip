"""End-to-end tests for the complete export -> import pipeline.

Each test invokes migrate.sh and/or migrate_db.py as actual CLI commands
via subprocess, exercising the full flow from export to import.

Run: python3 -m pytest scripts/test_migrate_e2e.py -v
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import tarfile
import uuid
from pathlib import Path

import pytest

# Re-use DB creation helpers from the unit test module
from test_migrate_db import create_entity_db, create_memory_db, _create_metadata_db

SCRIPT_DIR = Path(__file__).parent
MIGRATE_SH = str(SCRIPT_DIR / "migrate.sh")
MIGRATE_DB = str(SCRIPT_DIR / "migrate_db.py")


# ============================================================
# Helpers
# ============================================================


def _setup_iflow_state(
    base_dir: Path,
    *,
    memory_entries: list[dict] | None = None,
    entities: list[dict] | None = None,
    workflow_phases: list[dict] | None = None,
    markdown_files: dict[str, str] | None = None,
    projects_txt: bool = False,
    embedding_metadata: dict[str, str] | None = None,
) -> Path:
    """Create test iflow state under base_dir/.claude/iflow/.

    Returns the iflow_dir path.
    """
    iflow_dir = base_dir / ".claude" / "iflow"
    memory_dir = iflow_dir / "memory"
    entity_dir = iflow_dir / "entities"
    memory_dir.mkdir(parents=True, exist_ok=True)
    entity_dir.mkdir(parents=True, exist_ok=True)

    if memory_entries is not None:
        mem_db = str(memory_dir / "memory.db")
        create_memory_db(mem_db, memory_entries if memory_entries else None)
        if embedding_metadata:
            conn = sqlite3.connect(mem_db)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS _metadata (key TEXT PRIMARY KEY, value TEXT)"
            )
            for k, v in embedding_metadata.items():
                conn.execute(
                    "INSERT OR REPLACE INTO _metadata (key, value) VALUES (?, ?)",
                    (k, v),
                )
            conn.commit()
            conn.close()

    if entities is not None:
        ent_db = str(entity_dir / "entities.db")
        create_entity_db(
            ent_db,
            entities if entities else None,
            workflow_phases if workflow_phases else None,
        )

    if markdown_files:
        for name, content in markdown_files.items():
            (memory_dir / name).write_text(content)

    if projects_txt:
        (iflow_dir / "projects.txt").write_text(
            "/path/to/project1\n/path/to/project2\n"
        )

    return iflow_dir


def _run_migrate(
    base_dir: Path, args: list[str], *, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """Run migrate.sh with HOME set to base_dir."""
    env = os.environ.copy()
    env["HOME"] = str(base_dir)
    env["NO_COLOR"] = "1"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", MIGRATE_SH] + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _make_fake_pgrep(bin_dir: Path, *, exit_code: int = 0) -> None:
    """Create a fake pgrep script in bin_dir that exits with given code."""
    pgrep = bin_dir / "pgrep"
    pgrep.write_text(f"#!/usr/bin/env bash\nexit {exit_code}\n")
    pgrep.chmod(pgrep.stat().st_mode | stat.S_IEXEC)


def _find_bundle_dir(extract_dir: Path) -> Path:
    """Find the real bundle directory inside an extracted tar, ignoring macOS ._ files."""
    inner_dirs = [
        d for d in extract_dir.iterdir()
        if d.is_dir() and not d.name.startswith("._")
    ]
    assert len(inner_dirs) == 1, f"Expected 1 inner dir, found: {inner_dirs}"
    return inner_dirs[0]


# ============================================================
# Test 1: Export round-trip (AC-1, AC-2)
# ============================================================


class TestExportRoundTrip:
    """Export creates a valid tar.gz whose contents match the manifest checksums."""

    def test_export_round_trip(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()

        _setup_iflow_state(
            home,
            memory_entries=[
                {"source_hash": f"mem-{i}", "name": f"entry-{i}"} for i in range(3)
            ],
            entities=[
                {"type_id": f"feature:e-{i:03d}", "name": f"Feat{i}"} for i in range(2)
            ],
            workflow_phases=[{"type_id": "feature:e-000"}],
            markdown_files={"patterns.md": "# Patterns\n"},
            projects_txt=True,
        )

        # Create fake pgrep that reports no active session
        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)

        output_path = str(tmp_path / "export.tar.gz")
        result = _run_migrate(
            home,
            ["export", output_path],
            env_extra={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )
        assert result.returncode == 0, f"Export failed: {result.stderr}"
        assert os.path.isfile(output_path)

        # Extract and verify checksums match manifest
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        with tarfile.open(output_path, "r:gz") as tf:
            tf.extractall(extract_dir)

        # Find the inner directory (filter macOS ._ resource forks)
        bundle_dir = _find_bundle_dir(extract_dir)

        manifest_path = bundle_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())

        # Every file in manifest checksums must exist and match
        for rel_path, expected_sha in manifest["checksums"].items():
            fpath = bundle_dir / rel_path
            assert fpath.exists(), f"Missing file: {rel_path}"
            actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
            assert actual_sha == expected_sha, f"Checksum mismatch: {rel_path}"

        # Counts should match
        assert manifest["counts"]["memory_entries"] == 3
        assert manifest["counts"]["entities"] == 2


# ============================================================
# Test 2: Import fresh (AC-4)
# ============================================================


class TestImportFresh:
    """Import into an empty iflow directory restores all entries."""

    def test_import_fresh(self, tmp_path: Path) -> None:
        # Create source state and export
        src_home = tmp_path / "src_home"
        src_home.mkdir()
        _setup_iflow_state(
            src_home,
            memory_entries=[
                {"source_hash": f"mem-{i}", "name": f"entry-{i}"} for i in range(4)
            ],
            entities=[
                {"type_id": f"feature:f-{i:03d}", "name": f"F{i}"} for i in range(3)
            ],
            workflow_phases=[{"type_id": f"feature:f-{i:03d}"} for i in range(3)],
            markdown_files={"patterns.md": "# Patterns\n"},
            projects_txt=True,
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)
        env_extra = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        bundle_path = str(tmp_path / "bundle.tar.gz")
        result = _run_migrate(src_home, ["export", bundle_path], env_extra=env_extra)
        assert result.returncode == 0, f"Export failed: {result.stderr}"

        # Import into a fresh home with no iflow state
        dst_home = tmp_path / "dst_home"
        dst_home.mkdir()
        (dst_home / ".claude" / "iflow").mkdir(parents=True)

        result = _run_migrate(dst_home, ["import", bundle_path], env_extra=env_extra)
        assert result.returncode == 0, f"Import failed: {result.stderr}"

        # Verify all entries present
        mem_db = str(dst_home / ".claude" / "iflow" / "memory" / "memory.db")
        conn = sqlite3.connect(mem_db)
        mem_count = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
        conn.close()
        assert mem_count == 4

        ent_db = str(dst_home / ".claude" / "iflow" / "entities" / "entities.db")
        conn = sqlite3.connect(ent_db)
        ent_count = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        conn.close()
        assert ent_count == 3

        # Verify markdown and projects.txt restored
        assert (dst_home / ".claude" / "iflow" / "memory" / "patterns.md").exists()
        assert (dst_home / ".claude" / "iflow" / "projects.txt").exists()


# ============================================================
# Test 3: Import merge (AC-5)
# ============================================================


class TestImportMerge:
    """Import with overlapping state merges without duplicates."""

    def test_import_merge_no_duplicates(self, tmp_path: Path) -> None:
        # Source has entries A, B, C
        src_home = tmp_path / "src_home"
        src_home.mkdir()
        _setup_iflow_state(
            src_home,
            memory_entries=[
                {"source_hash": "shared-1", "name": "shared"},
                {"source_hash": "src-only-1", "name": "src-unique"},
            ],
            entities=[
                {"type_id": "feature:shared-001", "name": "SharedFeat"},
                {"type_id": "feature:src-only-001", "name": "SrcFeat"},
            ],
            workflow_phases=[
                {"type_id": "feature:shared-001"},
                {"type_id": "feature:src-only-001"},
            ],
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)
        env_extra = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        bundle_path = str(tmp_path / "bundle.tar.gz")
        result = _run_migrate(src_home, ["export", bundle_path], env_extra=env_extra)
        assert result.returncode == 0, f"Export failed: {result.stderr}"

        # Destination already has overlapping entries
        dst_home = tmp_path / "dst_home"
        dst_home.mkdir()
        _setup_iflow_state(
            dst_home,
            memory_entries=[
                {"source_hash": "shared-1", "name": "shared"},
                {"source_hash": "dst-only-1", "name": "dst-unique"},
            ],
            entities=[
                {"type_id": "feature:shared-001", "name": "SharedFeat"},
                {"type_id": "feature:dst-only-001", "name": "DstFeat"},
            ],
            workflow_phases=[
                {"type_id": "feature:shared-001"},
                {"type_id": "feature:dst-only-001"},
            ],
        )

        result = _run_migrate(dst_home, ["import", bundle_path], env_extra=env_extra)
        assert result.returncode == 0, f"Import failed: {result.stderr}"

        # Memory: shared-1 + src-only-1 + dst-only-1 = 3 (no duplicates)
        mem_db = str(dst_home / ".claude" / "iflow" / "memory" / "memory.db")
        conn = sqlite3.connect(mem_db)
        mem_count = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
        conn.close()
        assert mem_count == 3

        # Entities: shared-001 + src-only-001 + dst-only-001 = 3
        ent_db = str(dst_home / ".claude" / "iflow" / "entities" / "entities.db")
        conn = sqlite3.connect(ent_db)
        ent_count = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        conn.close()
        assert ent_count == 3


# ============================================================
# Test 4: Dry-run (AC-6)
# ============================================================


class TestDryRun:
    """Import with --dry-run makes zero filesystem changes."""

    def test_dry_run_no_changes(self, tmp_path: Path) -> None:
        # Create source and export
        src_home = tmp_path / "src_home"
        src_home.mkdir()
        _setup_iflow_state(
            src_home,
            memory_entries=[{"source_hash": "m-1", "name": "entry-1"}],
            entities=[{"type_id": "feature:e-001", "name": "Feat1"}],
            workflow_phases=[{"type_id": "feature:e-001"}],
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)
        env_extra = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        bundle_path = str(tmp_path / "bundle.tar.gz")
        result = _run_migrate(src_home, ["export", bundle_path], env_extra=env_extra)
        assert result.returncode == 0

        # Destination: empty iflow dir
        dst_home = tmp_path / "dst_home"
        dst_home.mkdir()
        (dst_home / ".claude" / "iflow").mkdir(parents=True)

        # Snapshot filesystem state before
        iflow_dir = dst_home / ".claude" / "iflow"
        before_files = set()
        for root, dirs, files in os.walk(str(iflow_dir)):
            for f in files:
                before_files.add(os.path.relpath(os.path.join(root, f), str(iflow_dir)))

        result = _run_migrate(
            dst_home, ["import", "--dry-run", bundle_path], env_extra=env_extra
        )
        assert result.returncode == 0, f"Dry-run failed: {result.stderr}"
        assert "dry-run" in result.stderr.lower() or "Dry-run" in result.stderr

        # Verify no new files created
        after_files = set()
        for root, dirs, files in os.walk(str(iflow_dir)):
            for f in files:
                after_files.add(os.path.relpath(os.path.join(root, f), str(iflow_dir)))

        assert after_files == before_files, (
            f"Dry-run created files: {after_files - before_files}"
        )


# ============================================================
# Test 5: Corrupt bundle (AC-7)
# ============================================================


class TestCorruptBundle:
    """Import rejects a tampered bundle with exit 3."""

    def test_corrupt_bundle_rejected(self, tmp_path: Path) -> None:
        # Export a valid bundle
        src_home = tmp_path / "src_home"
        src_home.mkdir()
        _setup_iflow_state(
            src_home,
            memory_entries=[{"source_hash": "m-1", "name": "entry-1"}],
            entities=[{"type_id": "feature:e-001", "name": "Feat1"}],
            workflow_phases=[{"type_id": "feature:e-001"}],
            projects_txt=True,
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)
        env_extra = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        bundle_path = str(tmp_path / "bundle.tar.gz")
        result = _run_migrate(src_home, ["export", bundle_path], env_extra=env_extra)
        assert result.returncode == 0

        # Tamper: extract, modify a file, re-pack
        tamper_dir = tmp_path / "tamper"
        tamper_dir.mkdir()
        with tarfile.open(bundle_path, "r:gz") as tf:
            tf.extractall(tamper_dir)

        bundle_inner = _find_bundle_dir(tamper_dir)
        # Tamper with projects.txt (it's in the manifest checksums)
        (bundle_inner / "projects.txt").write_text("TAMPERED\n")

        # Re-pack
        tampered_bundle = str(tmp_path / "tampered.tar.gz")
        with tarfile.open(tampered_bundle, "w:gz") as tf:
            tf.add(str(bundle_inner), arcname=bundle_inner.name)

        # Import should fail — migrate.sh calls validate which exits 3 on checksum mismatch,
        # then die() wraps it as exit 1 with "exit 3" in the message
        dst_home = tmp_path / "dst_home"
        dst_home.mkdir()
        (dst_home / ".claude" / "iflow").mkdir(parents=True)

        result = _run_migrate(
            dst_home, ["import", tampered_bundle], env_extra=env_extra
        )
        # The script die()s on validation failure. The exit code from die() is 1,
        # but the error message should mention checksum/exit 3
        assert result.returncode != 0, "Expected import to fail on corrupt bundle"
        assert (
            "checksum" in result.stderr.lower()
            or "exit 3" in result.stderr.lower()
            or "validation failed" in result.stderr.lower()
        ), f"Expected checksum error in stderr: {result.stderr}"


# ============================================================
# Test 6: Session detection (AC-3)
# ============================================================


class TestSessionDetection:
    """Active session detected causes abort with exit 2."""

    def test_session_detected_aborts(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        _setup_iflow_state(
            home,
            memory_entries=[{"source_hash": "m-1", "name": "entry-1"}],
            entities=[{"type_id": "feature:e-001", "name": "Feat1"}],
            workflow_phases=[{"type_id": "feature:e-001"}],
        )

        # Fake pgrep that reports active session
        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=0)  # 0 = process found

        result = _run_migrate(
            home,
            ["export"],
            env_extra={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )
        assert result.returncode == 2, (
            f"Expected exit 2 for active session, got {result.returncode}. "
            f"stderr: {result.stderr}"
        )
        assert "session" in result.stderr.lower()


# ============================================================
# Test 7: ENTITY_DB_PATH override (AC-12)
# ============================================================


class TestEntityDbPathOverride:
    """ENTITY_DB_PATH env var directs export to custom path."""

    def test_entity_db_path_override(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()

        # Create memory state at normal location
        _setup_iflow_state(
            home,
            memory_entries=[{"source_hash": "m-1", "name": "entry-1"}],
        )

        # Create entity DB at a custom location (NOT the default path)
        custom_dir = tmp_path / "custom_entities"
        custom_dir.mkdir()
        custom_db = str(custom_dir / "entities.db")
        create_entity_db(
            custom_db,
            [{"type_id": "feature:custom-001", "name": "CustomEntity"}],
            [{"type_id": "feature:custom-001"}],
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)

        bundle_path = str(tmp_path / "export.tar.gz")
        result = _run_migrate(
            home,
            ["export", bundle_path],
            env_extra={
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "ENTITY_DB_PATH": custom_db,
            },
        )
        assert result.returncode == 0, f"Export failed: {result.stderr}"

        # Extract and verify the custom entity was exported
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        with tarfile.open(bundle_path, "r:gz") as tf:
            tf.extractall(extract_dir)

        bundle_dir = _find_bundle_dir(extract_dir)
        exported_ent_db = str(bundle_dir / "entities" / "entities.db")
        assert os.path.exists(exported_ent_db)

        conn = sqlite3.connect(exported_ent_db)
        rows = conn.execute("SELECT type_id FROM entities").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "feature:custom-001"


# ============================================================
# Test 8: Embedding mismatch (AC-9)
# ============================================================


class TestEmbeddingMismatch:
    """Different embedding provider triggers warning on import."""

    def test_embedding_mismatch_warning(self, tmp_path: Path) -> None:
        # Source with openai embeddings
        src_home = tmp_path / "src_home"
        src_home.mkdir()
        _setup_iflow_state(
            src_home,
            memory_entries=[{"source_hash": "m-1", "name": "entry-1"}],
            entities=[{"type_id": "feature:e-001", "name": "Feat1"}],
            workflow_phases=[{"type_id": "feature:e-001"}],
            embedding_metadata={
                "embedding_provider": "openai",
                "embedding_model": "text-embedding-3-small",
            },
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)
        env_extra = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        bundle_path = str(tmp_path / "bundle.tar.gz")
        result = _run_migrate(src_home, ["export", bundle_path], env_extra=env_extra)
        assert result.returncode == 0

        # Destination with voyage embeddings
        dst_home = tmp_path / "dst_home"
        dst_home.mkdir()
        _setup_iflow_state(
            dst_home,
            memory_entries=[{"source_hash": "dst-1", "name": "dst-entry"}],
            embedding_metadata={
                "embedding_provider": "voyage",
                "embedding_model": "voyage-3",
            },
        )

        result = _run_migrate(dst_home, ["import", bundle_path], env_extra=env_extra)
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        # Should contain mismatch warning
        assert "mismatch" in result.stderr.lower() or "openai" in result.stderr.lower(), (
            f"Expected embedding mismatch warning in stderr: {result.stderr}"
        )


# ============================================================
# Test 9: Post-import doctor (AC-15)
# ============================================================


class TestPostImportDoctor:
    """Import runs integrity verification (step 8/8) as health check."""

    def test_post_import_verify_runs(self, tmp_path: Path) -> None:
        src_home = tmp_path / "src_home"
        src_home.mkdir()
        _setup_iflow_state(
            src_home,
            memory_entries=[{"source_hash": "m-1", "name": "entry-1"}],
            entities=[{"type_id": "feature:e-001", "name": "Feat1"}],
            workflow_phases=[{"type_id": "feature:e-001"}],
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)
        env_extra = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        bundle_path = str(tmp_path / "bundle.tar.gz")
        result = _run_migrate(src_home, ["export", bundle_path], env_extra=env_extra)
        assert result.returncode == 0

        dst_home = tmp_path / "dst_home"
        dst_home.mkdir()
        (dst_home / ".claude" / "iflow").mkdir(parents=True)

        result = _run_migrate(dst_home, ["import", bundle_path], env_extra=env_extra)
        assert result.returncode == 0, f"Import failed: {result.stderr}"

        # Verify step 8/8 ran — should mention integrity
        assert "integrity" in result.stderr.lower() or "Verifying" in result.stderr, (
            f"Expected integrity verification in stderr: {result.stderr}"
        )
        # Should report success
        assert "Import complete" in result.stderr


# ============================================================
# Test 10: Fresh machine embedding — no mismatch warning (AC-9)
# ============================================================


class TestFreshMachineEmbedding:
    """Import to empty dir with no _metadata produces no mismatch warning."""

    def test_no_mismatch_on_fresh_machine(self, tmp_path: Path) -> None:
        # Source with embedding metadata
        src_home = tmp_path / "src_home"
        src_home.mkdir()
        _setup_iflow_state(
            src_home,
            memory_entries=[{"source_hash": "m-1", "name": "entry-1"}],
            entities=[{"type_id": "feature:e-001", "name": "Feat1"}],
            workflow_phases=[{"type_id": "feature:e-001"}],
            embedding_metadata={
                "embedding_provider": "openai",
                "embedding_model": "text-embedding-3-small",
            },
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)
        env_extra = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        bundle_path = str(tmp_path / "bundle.tar.gz")
        result = _run_migrate(src_home, ["export", bundle_path], env_extra=env_extra)
        assert result.returncode == 0

        # Fresh destination — no iflow state at all
        dst_home = tmp_path / "dst_home"
        dst_home.mkdir()
        (dst_home / ".claude" / "iflow").mkdir(parents=True)

        result = _run_migrate(dst_home, ["import", bundle_path], env_extra=env_extra)
        assert result.returncode == 0, f"Import failed: {result.stderr}"

        # Should NOT contain mismatch warning
        assert "mismatch" not in result.stderr.lower(), (
            f"Unexpected mismatch warning on fresh machine: {result.stderr}"
        )


# ============================================================
# Test 11: UUID generation on merge (AC-5)
# ============================================================


class TestUuidGenerationOnMerge:
    """Imported entities get new UUIDs, not the source UUIDs."""

    def test_new_uuids_on_merge(self, tmp_path: Path) -> None:
        # Source entities with known UUIDs
        src_home = tmp_path / "src_home"
        src_home.mkdir()
        src_uuid_1 = str(uuid.uuid4())
        src_uuid_2 = str(uuid.uuid4())
        _setup_iflow_state(
            src_home,
            memory_entries=[{"source_hash": "m-1", "name": "entry-1"}],
            entities=[
                {"type_id": "feature:src-001", "name": "SrcFeat1", "uuid": src_uuid_1},
                {"type_id": "feature:src-002", "name": "SrcFeat2", "uuid": src_uuid_2},
            ],
            workflow_phases=[
                {"type_id": "feature:src-001"},
                {"type_id": "feature:src-002"},
            ],
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)
        env_extra = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        bundle_path = str(tmp_path / "bundle.tar.gz")
        result = _run_migrate(src_home, ["export", bundle_path], env_extra=env_extra)
        assert result.returncode == 0

        # Destination with different entities (no overlap on type_id)
        dst_home = tmp_path / "dst_home"
        dst_home.mkdir()
        _setup_iflow_state(
            dst_home,
            memory_entries=[{"source_hash": "dst-1", "name": "dst-entry"}],
            entities=[
                {"type_id": "feature:dst-001", "name": "DstFeat1"},
            ],
            workflow_phases=[{"type_id": "feature:dst-001"}],
        )

        result = _run_migrate(dst_home, ["import", bundle_path], env_extra=env_extra)
        assert result.returncode == 0, f"Import failed: {result.stderr}"

        # Verify imported entities have NEW UUIDs
        ent_db = str(dst_home / ".claude" / "iflow" / "entities" / "entities.db")
        conn = sqlite3.connect(ent_db)
        rows = conn.execute(
            "SELECT uuid, type_id FROM entities WHERE type_id IN ('feature:src-001', 'feature:src-002')"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        imported_uuids = {r[0] for r in rows}
        source_uuids = {src_uuid_1, src_uuid_2}
        assert imported_uuids.isdisjoint(source_uuids), (
            f"Imported UUIDs should differ from source. "
            f"Imported: {imported_uuids}, Source: {source_uuids}"
        )


# ============================================================
# Test 12: Force overwrite (AC-10)
# ============================================================


class TestForceOverwrite:
    """Import with --force overwrites existing markdown files."""

    def test_force_overwrites_markdown(self, tmp_path: Path) -> None:
        # Source with markdown
        src_home = tmp_path / "src_home"
        src_home.mkdir()
        _setup_iflow_state(
            src_home,
            memory_entries=[{"source_hash": "m-1", "name": "entry-1"}],
            entities=[{"type_id": "feature:e-001", "name": "Feat1"}],
            workflow_phases=[{"type_id": "feature:e-001"}],
            markdown_files={"patterns.md": "# Source Patterns\nNew content\n"},
            projects_txt=True,
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        _make_fake_pgrep(fake_bin, exit_code=1)
        env_extra = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        bundle_path = str(tmp_path / "bundle.tar.gz")
        result = _run_migrate(src_home, ["export", bundle_path], env_extra=env_extra)
        assert result.returncode == 0

        # Destination with existing markdown (different content)
        dst_home = tmp_path / "dst_home"
        dst_home.mkdir()
        _setup_iflow_state(
            dst_home,
            memory_entries=[{"source_hash": "dst-1", "name": "dst-entry"}],
            entities=[{"type_id": "feature:dst-001", "name": "DstFeat"}],
            workflow_phases=[{"type_id": "feature:dst-001"}],
            markdown_files={"patterns.md": "# Old Patterns\nOld content\n"},
            projects_txt=True,
        )

        # Verify existing content first
        dst_patterns = dst_home / ".claude" / "iflow" / "memory" / "patterns.md"
        assert "Old Patterns" in dst_patterns.read_text()

        # Import WITHOUT --force: markdown should be skipped
        result = _run_migrate(dst_home, ["import", bundle_path], env_extra=env_extra)
        assert result.returncode == 0
        assert "Old Patterns" in dst_patterns.read_text(), "Without --force, file should not be overwritten"

        # Import WITH --force: markdown should be overwritten
        result = _run_migrate(
            dst_home, ["import", "--force", bundle_path], env_extra=env_extra
        )
        assert result.returncode == 0
        assert "Source Patterns" in dst_patterns.read_text(), (
            f"With --force, file should be overwritten. Got: {dst_patterns.read_text()}"
        )
