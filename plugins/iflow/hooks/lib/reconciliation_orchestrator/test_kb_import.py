"""Unit tests for kb_import wrapper module (TDD — tests first).

Tests cover:
- test_new_entries_imported: KB markdown with new entries → imported count > 0
- test_unchanged_entries_skipped: entries already in DB → skipped via source_hash
- test_correct_params_plumbing: verify project_root, artifacts_root, global_store_path
  passed correctly to MarkdownImporter
- test_empty_kb_directory: no KB files → imported=0, skipped=0
"""
import os
import tempfile
from unittest.mock import MagicMock, call, patch

import pytest

from semantic_memory.database import MemoryDatabase

# Function under test (not yet implemented — will raise ImportError until T1.6)
from reconciliation_orchestrator.kb_import import sync_knowledge_bank


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_PATTERNS_MD = """\
# Patterns

### Pattern: Use Source Hash For Dedup
Always hash the raw source text so re-imports are idempotent.
- Observation count: 1
- Confidence: high
"""

_SAMPLE_PATTERNS_MD_2 = """\
# Patterns

### Pattern: Fail Open In Hooks
Hooks should never block the main workflow. Catch all errors and warn.
- Observation count: 2
- Confidence: medium
"""


def _make_temp_memory_db() -> MemoryDatabase:
    """Return a fresh in-memory MemoryDatabase."""
    return MemoryDatabase(":memory:")


def _write_kb_file(kb_dir: str, filename: str, content: str) -> None:
    os.makedirs(kb_dir, exist_ok=True)
    with open(os.path.join(kb_dir, filename), "w") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSyncKnowledgeBank:
    """Tests for sync_knowledge_bank()."""

    def test_new_entries_imported(self, tmp_path):
        """KB markdown with new entries → imported count > 0."""
        project_root = str(tmp_path)
        artifacts_root = "docs"
        global_store_path = str(tmp_path / "global_store")

        # Write a patterns.md file under the local KB path
        local_kb = tmp_path / "docs" / "knowledge-bank"
        _write_kb_file(str(local_kb), "patterns.md", _SAMPLE_PATTERNS_MD)

        memory_db = _make_temp_memory_db()
        try:
            result = sync_knowledge_bank(
                memory_db=memory_db,
                project_root=project_root,
                artifacts_root=artifacts_root,
                global_store_path=global_store_path,
            )
        finally:
            memory_db.close()

        assert result["imported"] > 0, (
            "Expected at least one entry to be imported from patterns.md"
        )
        assert isinstance(result["skipped"], int)

    def test_unchanged_entries_skipped(self, tmp_path):
        """Entries already in DB with same source_hash → skipped on second import."""
        project_root = str(tmp_path)
        artifacts_root = "docs"
        global_store_path = str(tmp_path / "global_store")

        local_kb = tmp_path / "docs" / "knowledge-bank"
        _write_kb_file(str(local_kb), "patterns.md", _SAMPLE_PATTERNS_MD)

        memory_db = _make_temp_memory_db()
        try:
            # First import — entries go in
            first = sync_knowledge_bank(
                memory_db=memory_db,
                project_root=project_root,
                artifacts_root=artifacts_root,
                global_store_path=global_store_path,
            )
            assert first["imported"] > 0, "First import should have imported entries"

            # Second import — same content, same source_hash → all skipped
            second = sync_knowledge_bank(
                memory_db=memory_db,
                project_root=project_root,
                artifacts_root=artifacts_root,
                global_store_path=global_store_path,
            )
        finally:
            memory_db.close()

        assert second["skipped"] > 0, (
            "Expected entries to be skipped on second import (source_hash dedup)"
        )
        assert second["imported"] == 0, (
            "Expected zero new imports when content is unchanged"
        )

    def test_correct_params_plumbing(self, tmp_path):
        """MarkdownImporter receives the correct project_root, artifacts_root,
        and global_store_path arguments."""
        project_root = "/fake/project/root"
        artifacts_root = "custom_docs"
        global_store_path = "/fake/global/store"

        mock_importer_instance = MagicMock()
        mock_importer_instance.import_all.return_value = {"imported": 3, "skipped": 1}

        with patch(
            "reconciliation_orchestrator.kb_import.MarkdownImporter",
        ) as MockMarkdownImporter:
            MockMarkdownImporter.return_value = mock_importer_instance

            memory_db = MagicMock(spec=MemoryDatabase)

            result = sync_knowledge_bank(
                memory_db=memory_db,
                project_root=project_root,
                artifacts_root=artifacts_root,
                global_store_path=global_store_path,
            )

        # Verify MarkdownImporter was constructed with the right args
        MockMarkdownImporter.assert_called_once_with(
            db=memory_db,
            artifacts_root=artifacts_root,
        )

        # Verify import_all was called with project_root and global_store (path string)
        mock_importer_instance.import_all.assert_called_once_with(
            project_root=project_root,
            global_store=global_store_path,
        )

        # Verify the return values are correctly plumbed through
        assert result == {"imported": 3, "skipped": 1}

    def test_empty_kb_directory(self, tmp_path):
        """No KB files present → imported=0, skipped=0."""
        project_root = str(tmp_path)
        artifacts_root = "docs"
        global_store_path = str(tmp_path / "global_store")

        # Do NOT create any KB files — directories are absent entirely

        memory_db = _make_temp_memory_db()
        try:
            result = sync_knowledge_bank(
                memory_db=memory_db,
                project_root=project_root,
                artifacts_root=artifacts_root,
                global_store_path=global_store_path,
            )
        finally:
            memory_db.close()

        assert result == {"imported": 0, "skipped": 0}, (
            f"Expected {{imported: 0, skipped: 0}} when no KB files exist, got {result}"
        )
