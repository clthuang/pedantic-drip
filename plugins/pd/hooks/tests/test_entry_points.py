"""Phase 4 consolidation tests for semantic memory entry points.

Tests the three entry points (injector, writer, MCP server) end-to-end,
verifying integration behaviour that the per-module unit tests do not cover.

These are *consolidation* tests -- they exercise public APIs of each module
in a more integrated way rather than duplicating the existing granular tests
in ``test_injector.py``, ``test_writer.py``, and ``test_memory_server.py``.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Path setup -- make both hooks/lib and mcp/ importable
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "mcp"))

import numpy as np
import pytest

from semantic_memory import content_hash
from semantic_memory.database import MemoryDatabase
from semantic_memory.retrieval_types import CandidateScores, RetrievalResult

# Lazy imports inside each test class to keep module-level clean.

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id: str,
    name: str,
    category: str,
    description: str = "A test description.",
    observation_count: int = 3,
    confidence: str = "high",
    recall_count: int = 0,
    **kwargs,
) -> dict:
    """Build a minimal entry dict for injector tests."""
    entry = {
        "id": entry_id,
        "name": name,
        "category": category,
        "description": description,
        "observation_count": observation_count,
        "confidence": confidence,
        "recall_count": recall_count,
        "last_recalled_at": None,
        "updated_at": "2025-01-01T00:00:00Z",
        "final_score": 0.9,
    }
    entry.update(kwargs)
    return entry


def _make_mock_provider(dimensions: int = 768):
    """Create a mock embedding provider that returns deterministic vectors."""
    provider = MagicMock()
    provider.dimensions = dimensions
    provider.provider_name = "mock"
    provider.model_name = "mock-model"

    def embed_side_effect(text, task_type="document"):
        return np.ones(dimensions, dtype=np.float32) * 0.5

    provider.embed.side_effect = embed_side_effect
    return provider


def _run_writer_main(args: list[str]) -> tuple[int, str, str]:
    """Run writer.main() capturing exit code, stdout, and stderr."""
    from semantic_memory.writer import main as writer_main

    import io

    captured_code = [0]

    def fake_exit(code=0):
        captured_code[0] = code
        raise SystemExit(code)

    with patch("sys.argv", ["writer.py"] + args), \
         patch("sys.exit", fake_exit):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            writer_main()
        except SystemExit:
            pass
        stdout_val = sys.stdout.getvalue()
        stderr_val = sys.stderr.getvalue()
        sys.stdout, sys.stderr = old_stdout, old_stderr

    return captured_code[0], stdout_val, stderr_val


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def global_store(tmp_path):
    """Provide a temp directory as the global store."""
    store = tmp_path / "global-store"
    store.mkdir()
    return str(store)


@pytest.fixture
def mem_db():
    """Provide an in-memory MemoryDatabase, closed after test."""
    database = MemoryDatabase(":memory:")
    yield database
    database.close()


# ===========================================================================
# Injector entry point tests
# ===========================================================================


class TestInjectorFormatI10:
    """format_output produces correctly structured I10 markdown."""

    def test_header_diagnostic_categories_and_closing_rule(self):
        """Full output includes header, diagnostic line, category sections,
        entry formatting, and closing horizontal rule."""
        from semantic_memory.injector import format_output

        entries = [
            _make_entry("e1", "Avoid Null Returns", "anti-patterns",
                        description="Return empty collections instead of null."),
            _make_entry("e2", "Retry with Backoff", "patterns",
                        description="Use exponential backoff for retries."),
            _make_entry("e3", "Fail Fast on Bad Input", "heuristics",
                        description="Validate early, reject invalid data immediately."),
        ]

        result = RetrievalResult(
            candidates={},
            vector_candidate_count=80,
            fts5_candidate_count=22,
            context_query="semantic search integration tests",
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=120,
            pending=3,
            model="gemini-embedding-001",
        )

        # Header
        assert "## Engineering Memory (from knowledge bank)" in output
        # Diagnostic line has entry/total counts
        assert "3 entries from 120" in output
        # Category section headers present
        assert "### Anti-Patterns to Avoid" in output
        assert "### Patterns to Follow" in output
        assert "### Heuristics" in output
        # Individual entries with correct prefix
        assert "### Anti-Pattern: Avoid Null Returns" in output
        assert "### Pattern: Retry with Backoff" in output
        assert "### Fail Fast on Bad Input" in output
        # Metadata per entry
        assert "- Observation count: 3" in output
        assert "- Confidence: high" in output
        # Descriptions present
        assert "Return empty collections instead of null." in output
        assert "Use exponential backoff for retries." in output
        assert "Validate early, reject invalid data immediately." in output
        # Closing rule
        assert output.rstrip().endswith("---")


class TestInjectorDiagnosticCounts:
    """Diagnostic line reports accurate vector and fts5 candidate counts."""

    def test_vector_and_fts5_counts_appear(self):
        from semantic_memory.injector import format_output

        entries = [_make_entry("e1", "Test Entry", "heuristics")]
        result = RetrievalResult(
            vector_candidate_count=256,
            fts5_candidate_count=64,
            context_query="test",
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=500,
            pending=0,
            model="test-model",
        )

        assert "vector=256" in output
        assert "fts5=64" in output


class TestInjectorRecallTracking:
    """After main() runs, db.update_recall is called with selected entry IDs."""

    def test_recall_tracking_increments_after_injection(self):
        from semantic_memory.injector import main as injector_main

        mock_db = MagicMock()
        mock_db.count_entries.return_value = 20
        mock_db.get_metadata.return_value = "0"
        mock_db.get_all_entries.return_value = [
            _make_entry("id_a", "Entry A", "patterns"),
            _make_entry("id_b", "Entry B", "heuristics"),
            _make_entry("id_c", "Entry C", "anti-patterns"),
        ]

        mock_result = RetrievalResult(
            candidates={
                "id_a": CandidateScores(vector_score=0.95),
                "id_b": CandidateScores(bm25_score=0.7),
                "id_c": CandidateScores(vector_score=0.6, bm25_score=0.3),
            },
            vector_candidate_count=10,
            fts5_candidate_count=5,
            context_query="integration test recall",
        )

        ranked = [
            _make_entry("id_a", "Entry A", "patterns"),
            _make_entry("id_b", "Entry B", "heuristics"),
            _make_entry("id_c", "Entry C", "anti-patterns"),
        ]

        with patch("semantic_memory.injector.read_config", return_value={
                 "memory_injection_limit": 20, "memory_embedding_model": "test"}), \
             patch("semantic_memory.injector.MemoryDatabase", return_value=mock_db), \
             patch("semantic_memory.injector.create_provider", return_value=None), \
             patch("semantic_memory.injector.RetrievalPipeline") as mock_pipeline_cls, \
             patch("semantic_memory.injector.RankingEngine") as mock_ranking_cls, \
             patch("semantic_memory.injector.MarkdownImporter"):

            mock_pipeline_cls.return_value.collect_context.return_value = "test"
            mock_pipeline_cls.return_value.retrieve.return_value = mock_result
            mock_ranking_cls.return_value.rank.return_value = ranked

            injector_main(["--project-root", "/tmp/test",
                           "--global-store", "/tmp/store"])

        mock_db.update_recall.assert_called_once()
        recalled_ids = mock_db.update_recall.call_args[0][0]
        assert set(recalled_ids) == {"id_a", "id_b", "id_c"}


class TestInjectorEmptyDbImport:
    """When DB has 0 entries, MarkdownImporter.import_all is called
    with provider=None and keyword_gen=None."""

    def test_import_called_when_db_empty(self):
        from semantic_memory.injector import main as injector_main

        mock_db = MagicMock()
        mock_db.count_entries.return_value = 0
        mock_db.get_metadata.return_value = "0"
        mock_db.get_all_entries.return_value = []

        mock_result = RetrievalResult(context_query=None)

        with patch("semantic_memory.injector.read_config", return_value={
                 "memory_injection_limit": 20, "memory_embedding_model": "t"}), \
             patch("semantic_memory.injector.MemoryDatabase", return_value=mock_db), \
             patch("semantic_memory.injector.create_provider", return_value=None), \
             patch("semantic_memory.injector.RetrievalPipeline") as mock_pipeline_cls, \
             patch("semantic_memory.injector.RankingEngine") as mock_ranking_cls, \
             patch("semantic_memory.injector.MarkdownImporter") as mock_importer_cls:

            mock_pipeline_cls.return_value.collect_context.return_value = None
            mock_pipeline_cls.return_value.retrieve.return_value = mock_result
            mock_ranking_cls.return_value.rank.return_value = []

            injector_main(["--project-root", "/tmp/test",
                           "--global-store", "/tmp/store"])

        # import_all should have been called
        mock_importer_cls.assert_called_once_with(mock_db)
        mock_importer_cls.return_value.import_all.assert_called_once_with(
            "/tmp/test", "/tmp/store"
        )


# ===========================================================================
# Writer entry point tests
# ===========================================================================


class TestWriterValidEntry:
    """Valid entry JSON produces a DB entry with the correct content_hash."""

    def test_valid_entry_stored_with_content_hash(self, global_store, tmp_path):
        entry_data = {
            "name": "Integration Test Pattern",
            "description": "Consolidation tests verify entry-point integration",
            "category": "patterns",
        }
        entry_json = json.dumps(entry_data)
        expected_hash = content_hash(entry_data["description"])

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_writer_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 0
        assert f"id: {expected_hash}" in stdout

        db = MemoryDatabase(os.path.join(global_store, "memory.db"))
        entry = db.get_entry(expected_hash)
        assert entry is not None
        assert entry["name"] == "Integration Test Pattern"
        assert entry["description"] == entry_data["description"]
        assert entry["category"] == "patterns"
        db.close()


class TestWriterInvalidJson:
    """Invalid JSON input causes exit code 1."""

    def test_garbage_json_exits_1(self, global_store, tmp_path):
        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_writer_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", "{not valid json!!!",
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 1
        assert "json" in stderr.lower()


class TestWriterPendingBatch:
    """Pending entries without embeddings are processed (up to 50)
    when a provider is available."""

    def test_pending_entries_get_embeddings_via_writer(self, global_store, tmp_path):
        # Pre-populate DB with entries that lack embeddings
        db_path = os.path.join(global_store, "memory.db")
        db = MemoryDatabase(db_path)
        for i in range(5):
            db.upsert_entry({
                "id": f"pending_{i}",
                "name": f"Pending Entry {i}",
                "description": f"Description for pending entry {i}",
                "category": "heuristics",
                "source": "manual",
                "source_project": str(tmp_path),
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            })
        pending_before = db.get_entries_without_embedding()
        assert len(pending_before) == 5
        db.close()

        mock_provider = _make_mock_provider()

        # Upsert a new entry which also triggers pending batch processing
        new_entry = json.dumps({
            "name": "Trigger Entry",
            "description": "Triggers pending batch processing",
            "category": "patterns",
        })

        with patch("semantic_memory.writer.create_provider",
                    return_value=mock_provider), \
             patch("semantic_memory.writer.read_config", return_value={
                 "memory_embedding_provider": "mock",
                 "memory_embedding_model": "mock-model",
             }):
            exit_code, stdout, stderr = _run_writer_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", new_entry,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 0

        # All pending entries should now have embeddings
        db = MemoryDatabase(db_path)
        pending_after = db.get_entries_without_embedding()
        assert len(pending_after) == 0, \
            f"Expected 0 pending entries, got {len(pending_after)}"
        db.close()


# ===========================================================================
# MCP entry point tests
# ===========================================================================


class TestMcpStoreMemory:
    """_process_store_memory creates an entry with source='session-capture'."""

    def test_creates_entry_with_session_capture_source(self, mem_db):
        from memory_server import _process_store_memory

        result = _process_store_memory(
            db=mem_db,
            provider=None,
            keyword_gen=None,
            name="Session Learning",
            description="Learned during a coding session",
            reasoning="Captured automatically",
            category="heuristics",
            references=["src/main.py:10"],
        )

        expected_hash = content_hash("Learned during a coding session")
        assert f"id: {expected_hash}" in result

        entry = mem_db.get_entry(expected_hash)
        assert entry is not None
        assert entry["source"] == "session-capture"
        assert entry["name"] == "Session Learning"
        assert entry["category"] == "heuristics"
        assert json.loads(entry["references"]) == ["src/main.py:10"]


class TestMcpInvalidCategory:
    """Invalid category returns an error string without storing."""

    def test_invalid_category_rejected(self, mem_db):
        from memory_server import _process_store_memory

        result = _process_store_memory(
            db=mem_db,
            provider=None,
            keyword_gen=None,
            name="Bad Category Entry",
            description="This should not be stored",
            reasoning="Testing validation",
            category="not-a-real-category",
            references=[],
        )

        assert "error" in result.lower()
        assert mem_db.count_entries() == 0


class TestMcpEmptyName:
    """Empty name returns an error string without storing."""

    def test_empty_name_rejected(self, mem_db):
        from memory_server import _process_store_memory

        result = _process_store_memory(
            db=mem_db,
            provider=None,
            keyword_gen=None,
            name="",
            description="Valid description",
            reasoning="Valid reasoning",
            category="patterns",
            references=[],
        )

        assert "error" in result.lower()
        assert mem_db.count_entries() == 0


class TestMcpDuplicateEntry:
    """Second call with same description increments observation_count."""

    def test_duplicate_increments_observation_count(self, mem_db):
        from memory_server import _process_store_memory

        desc = "Unique description for dedup consolidation test"

        # First store
        result1 = _process_store_memory(
            db=mem_db,
            provider=None,
            keyword_gen=None,
            name="Dup Entry",
            description=desc,
            reasoning="First observation",
            category="patterns",
            references=[],
        )
        assert "Stored" in result1

        # Second store (same description -> same content hash)
        result2 = _process_store_memory(
            db=mem_db,
            provider=None,
            keyword_gen=None,
            name="Dup Entry",
            description=desc,
            reasoning="Second observation",
            category="patterns",
            references=[],
        )
        assert "Stored" in result2

        expected_hash = content_hash(desc)
        entry = mem_db.get_entry(expected_hash)
        assert entry is not None
        assert entry["observation_count"] == 2
