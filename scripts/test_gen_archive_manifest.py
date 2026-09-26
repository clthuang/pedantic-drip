"""The archive-manifest generator reads the registry without writing beside it.

``scripts/gen_archive_manifest.py`` defaults to the live registry,
``~/.claude/pd/entities/entities.db``, a WAL-mode file. Plain ``?mode=ro``
on such a file with no ``-wal`` beside it fails (SQLite 3.51) or creates
``-shm`` and ``-wal`` there (3.53). The generator opens it by the repo's
read-only rule instead:

- **No ``-wal``:** ``immutable=1``, which writes nothing beside the file.
- **A ``-wal``:** ``mode=ro``, which reads the commits a writer still holds
  in it; ``immutable=1`` would miss them.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_archive_manifest  # noqa: E402

# The columns and tables the generator's query reads.
_SCHEMA = (
    "CREATE TABLE workspaces (uuid TEXT PRIMARY KEY, project_root TEXT)",
    "CREATE TABLE entities (uuid TEXT PRIMARY KEY, workspace_uuid TEXT, "
    "kind TEXT, entity_id TEXT, name TEXT, status TEXT, "
    "is_legacy INTEGER NOT NULL DEFAULT 0, "
    "is_archived INTEGER NOT NULL DEFAULT 0, parent_uuid TEXT)",
    "CREATE TABLE entity_display (uuid TEXT PRIMARY KEY)",
    "CREATE TABLE entity_tags (entity_uuid TEXT, tag TEXT)",
)
_WORKSPACE_UUID = "workspace-uuid"


def _add_archived_row(connection: sqlite3.Connection, entity_id: str) -> None:
    connection.execute(
        "INSERT INTO entities (uuid, workspace_uuid, kind, entity_id, name, "
        "status, is_archived) VALUES (?, ?, 'brainstorm', ?, ?, 'active', 1)",
        (f"uuid-{entity_id}", _WORKSPACE_UUID, entity_id, entity_id),
    )


def _files_beside(registry: Path) -> list[str]:
    return sorted(path.name for path in registry.parent.iterdir())


@pytest.fixture
def generator(tmp_path, monkeypatch):
    """The generator pointed at a WAL-mode registry in a directory of its
    own, holding one archived row and closed cleanly, which checkpoints its
    WAL and removes the ``-wal`` and ``-shm`` files."""
    registry = tmp_path / "registry" / "entities.db"
    registry.parent.mkdir()
    connection = sqlite3.connect(registry)
    assert connection.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    for statement in _SCHEMA:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO workspaces (uuid, project_root) VALUES (?, '/projects/example')",
        (_WORKSPACE_UUID,),
    )
    _add_archived_row(connection, "row-in-the-file")
    connection.commit()
    connection.close()

    # The generator prints its output path relative to the working directory.
    monkeypatch.chdir(tmp_path)
    manifest = Path.cwd() / "manifest.md"
    monkeypatch.setattr(gen_archive_manifest, "DB", str(registry))
    monkeypatch.setattr(gen_archive_manifest, "OUT", manifest)
    return registry, manifest


def test_the_generator_writes_nothing_beside_the_registry_and_reads_a_live_wal(generator):
    registry, manifest = generator
    assert _files_beside(registry) == ["entities.db"]

    # No -wal beside the file: the run reads it and writes nothing there.
    assert gen_archive_manifest.main() == 0
    assert _files_beside(registry) == ["entities.db"]
    assert "`row-in-the-file`" in manifest.read_text()

    # A writer holds a commit in its -wal: the run reads that commit too.
    writer = sqlite3.connect(registry)
    try:
        _add_archived_row(writer, "row-in-the-wal")
        writer.commit()
        assert (registry.parent / "entities.db-wal").exists()
        file_only = sqlite3.connect(f"file:{registry}?mode=ro&immutable=1", uri=True)
        try:
            in_the_file = file_only.execute(
                "SELECT COUNT(*) FROM entities WHERE entity_id = 'row-in-the-wal'"
            ).fetchone()[0]
        finally:
            file_only.close()
        assert in_the_file == 0, "the commit must live only in the -wal"

        assert gen_archive_manifest.main() == 0
        assert "`row-in-the-wal`" in manifest.read_text()
    finally:
        writer.close()
