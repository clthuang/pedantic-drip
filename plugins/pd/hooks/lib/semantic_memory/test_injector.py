"""Tests for semantic_memory.injector module."""
from __future__ import annotations

from unittest import mock

from semantic_memory.retrieval_types import CandidateScores, RetrievalResult


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
    """Build a minimal entry dict."""
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


# ---------------------------------------------------------------------------
# Tests: format_output
# ---------------------------------------------------------------------------


class TestFormatOutput:
    """Test format_output with known entries matches I10 format."""

    def test_basic_output_structure(self):
        """Output has header, diagnostic, category sections, entries, and closing rule."""
        from semantic_memory.injector import format_output

        entries = [
            _make_entry("e1", "Stale Review Counts", "anti-patterns"),
            _make_entry("e2", "Use Structured Logging", "patterns"),
            _make_entry("e3", "Check Before Write", "heuristics"),
        ]

        result = RetrievalResult(
            candidates={},
            vector_candidate_count=142,
            fts5_candidate_count=38,
            context_query="memory-semantic-search: Build a personal knowledge retrieval system",
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=154,
            pending=0,
            model="gemini-embedding-001",
        )

        # Header
        assert "## Engineering Memory (from knowledge bank)" in output
        # Diagnostic line
        assert "*Memory: 3 entries from 154" in output
        assert "vector=142" in output
        assert "fts5=38" in output
        assert "model: gemini-embedding-001*" in output
        # Category headers
        assert "### Anti-Patterns to Avoid" in output
        assert "### Patterns to Follow" in output
        assert "### Heuristics" in output
        # Entry headers with correct prefixes
        assert "### Anti-Pattern: Stale Review Counts" in output
        assert "### Pattern: Use Structured Logging" in output
        assert "### Check Before Write" in output  # heuristics have no prefix
        # Metadata lines
        assert "- Observation count: 3" in output
        assert "- Confidence: high" in output
        # Closing rule
        assert output.rstrip().endswith("---")

    def test_entry_format_includes_description(self):
        """Each entry should include its description text."""
        from semantic_memory.injector import format_output

        entries = [
            _make_entry("e1", "My Pattern", "patterns", description="Do this thing carefully."),
        ]

        result = RetrievalResult(
            vector_candidate_count=10,
            fts5_candidate_count=5,
            context_query="test",
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=50,
            pending=0,
            model="gemini-embedding-001",
        )

        assert "Do this thing carefully." in output


class TestDiagnosticLine:
    """Test diagnostic line construction."""

    def test_correct_vector_fts5_counts(self):
        """Diagnostic line shows vector and fts5 counts from RetrievalResult."""
        from semantic_memory.injector import format_output

        entries = [_make_entry("e1", "Test", "patterns")]
        result = RetrievalResult(
            vector_candidate_count=100,
            fts5_candidate_count=25,
            context_query="some query",
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=200,
            pending=0,
            model="test-model",
        )

        assert "vector=100" in output
        assert "fts5=25" in output
        assert "entries from 200" in output

    def test_pending_embedding_shown_when_positive(self):
        """Diagnostic line includes pending_embedding when > 0."""
        from semantic_memory.injector import format_output

        entries = [_make_entry("e1", "Test", "heuristics")]
        result = RetrievalResult(
            vector_candidate_count=12,
            fts5_candidate_count=38,
            context_query="test context",
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=54,
            pending=42,
            model="gemini-embedding-001",
        )

        assert "pending_embedding=42" in output

    def test_pending_embedding_omitted_when_zero(self):
        """Diagnostic line omits pending_embedding when it is 0."""
        from semantic_memory.injector import format_output

        entries = [_make_entry("e1", "Test", "heuristics")]
        result = RetrievalResult(
            vector_candidate_count=50,
            fts5_candidate_count=20,
            context_query="test context",
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=100,
            pending=0,
            model="test-model",
        )

        assert "pending_embedding" not in output

    def test_context_query_truncated_at_30_chars(self):
        """Context query longer than 30 chars is truncated with '...'."""
        from semantic_memory.injector import format_output

        entries = [_make_entry("e1", "Test", "patterns")]
        long_query = "memory-semantic-search: Build a personal knowledge retrieval system"
        result = RetrievalResult(
            vector_candidate_count=1,
            fts5_candidate_count=1,
            context_query=long_query,
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=10,
            pending=0,
            model="m",
        )

        # Should be truncated to first 30 chars + "..."
        expected_fragment = long_query[:30] + "..."
        assert expected_fragment in output

    def test_short_context_query_not_truncated(self):
        """Context query 30 chars or less is not truncated."""
        from semantic_memory.injector import format_output

        entries = [_make_entry("e1", "Test", "patterns")]
        short_query = "short query"
        result = RetrievalResult(
            vector_candidate_count=1,
            fts5_candidate_count=1,
            context_query=short_query,
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=10,
            pending=0,
            model="m",
        )

        assert f'context: "{short_query}"' in output
        assert "..." not in output.split("context:")[1].split("|")[0]


class TestEmptyEntries:
    """Test that zero entries produce no output."""

    def test_empty_list_returns_empty_string(self):
        """format_output with empty entries returns empty string."""
        from semantic_memory.injector import format_output

        result = RetrievalResult(
            vector_candidate_count=0,
            fts5_candidate_count=0,
            context_query=None,
        )

        output = format_output(
            selected=[],
            result=result,
            total_count=0,
            pending=0,
            model="none",
        )

        assert output == ""


# ---------------------------------------------------------------------------
# Tests: Recall tracking
# ---------------------------------------------------------------------------


class TestRecallTracking:
    """After injection, selected entry IDs have recall_count incremented."""

    def test_update_recall_called_with_selected_ids(self):
        """main() calls db.update_recall with the IDs of all selected entries."""
        from semantic_memory.injector import main

        mock_db = mock.MagicMock()
        mock_db.count_entries.return_value = 10
        mock_db.get_metadata.return_value = "0"
        mock_db.get_all_entries.return_value = [
            _make_entry("e1", "Name1", "patterns"),
            _make_entry("e2", "Name2", "heuristics"),
        ]

        mock_result = RetrievalResult(
            candidates={
                "e1": CandidateScores(vector_score=0.9),
                "e2": CandidateScores(bm25_score=0.5),
            },
            vector_candidate_count=1,
            fts5_candidate_count=1,
            context_query="test query",
        )

        ranked = [
            _make_entry("e1", "Name1", "patterns"),
            _make_entry("e2", "Name2", "heuristics"),
        ]

        with mock.patch("semantic_memory.injector.read_config", return_value={"memory_injection_limit": 20, "memory_embedding_model": "test"}), \
             mock.patch("semantic_memory.injector.MemoryDatabase", return_value=mock_db), \
             mock.patch("semantic_memory.injector.create_provider", return_value=None), \
             mock.patch("semantic_memory.injector.RetrievalPipeline") as mock_pipeline_cls, \
             mock.patch("semantic_memory.injector.RankingEngine") as mock_ranking_cls, \
             mock.patch("semantic_memory.injector.MarkdownImporter"):

            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.collect_context.return_value = "test query"
            mock_pipeline.retrieve.return_value = mock_result

            mock_ranking = mock_ranking_cls.return_value
            mock_ranking.rank.return_value = ranked

            main(["--project-root", "/tmp/test", "--global-store", "/tmp/store"])

        # Verify update_recall was called with both IDs
        mock_db.update_recall.assert_called_once()
        call_args = mock_db.update_recall.call_args
        recalled_ids = call_args[0][0]
        assert set(recalled_ids) == {"e1", "e2"}


# ---------------------------------------------------------------------------
# Tests: Empty DB triggers import
# ---------------------------------------------------------------------------


class TestEmptyDbTriggersImport:
    """When DB is empty, import_all should be called."""

    def test_import_called_when_db_empty(self):
        """main() calls MarkdownImporter.import_all when count_entries() == 0."""
        from semantic_memory.injector import main

        mock_db = mock.MagicMock()
        mock_db.count_entries.return_value = 0
        mock_db.get_metadata.return_value = "0"
        mock_db.get_all_entries.return_value = []

        mock_result = RetrievalResult(context_query=None)

        with mock.patch("semantic_memory.injector.read_config", return_value={"memory_injection_limit": 20, "memory_embedding_model": "test"}), \
             mock.patch("semantic_memory.injector.MemoryDatabase", return_value=mock_db), \
             mock.patch("semantic_memory.injector.create_provider", return_value=None), \
             mock.patch("semantic_memory.injector.RetrievalPipeline") as mock_pipeline_cls, \
             mock.patch("semantic_memory.injector.RankingEngine") as mock_ranking_cls, \
             mock.patch("semantic_memory.injector.MarkdownImporter") as mock_importer_cls:

            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.collect_context.return_value = None
            mock_pipeline.retrieve.return_value = mock_result

            mock_ranking = mock_ranking_cls.return_value
            mock_ranking.rank.return_value = []

            main(["--project-root", "/tmp/test", "--global-store", "/tmp/store"])

        mock_importer_cls.return_value.import_all.assert_called_once_with(
            "/tmp/test", "/tmp/store"
        )

    def test_import_not_called_when_db_has_entries(self):
        """main() does NOT call import_all when count_entries() > 0."""
        from semantic_memory.injector import main

        mock_db = mock.MagicMock()
        mock_db.count_entries.return_value = 50
        mock_db.get_metadata.return_value = "0"
        mock_db.get_all_entries.return_value = []

        mock_result = RetrievalResult(context_query=None)

        with mock.patch("semantic_memory.injector.read_config", return_value={"memory_injection_limit": 20, "memory_embedding_model": "test"}), \
             mock.patch("semantic_memory.injector.MemoryDatabase", return_value=mock_db), \
             mock.patch("semantic_memory.injector.create_provider", return_value=None), \
             mock.patch("semantic_memory.injector.RetrievalPipeline") as mock_pipeline_cls, \
             mock.patch("semantic_memory.injector.RankingEngine") as mock_ranking_cls, \
             mock.patch("semantic_memory.injector.MarkdownImporter") as mock_importer_cls:

            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.collect_context.return_value = None
            mock_pipeline.retrieve.return_value = mock_result

            mock_ranking = mock_ranking_cls.return_value
            mock_ranking.rank.return_value = []

            main(["--project-root", "/tmp/test", "--global-store", "/tmp/store"])

        mock_importer_cls.return_value.import_all.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Exception during retrieve -> empty stdout, stderr output."""

    def test_exception_produces_empty_stdout_and_stderr(self, capsys):
        """When retrieve raises, main() outputs nothing to stdout and logs to stderr."""
        from semantic_memory.injector import main

        mock_db = mock.MagicMock()
        mock_db.count_entries.return_value = 10
        mock_db.get_metadata.return_value = "0"

        with mock.patch("semantic_memory.injector.read_config", return_value={"memory_injection_limit": 20, "memory_embedding_model": "test"}), \
             mock.patch("semantic_memory.injector.MemoryDatabase", return_value=mock_db), \
             mock.patch("semantic_memory.injector.create_provider", return_value=None), \
             mock.patch("semantic_memory.injector.RetrievalPipeline") as mock_pipeline_cls, \
             mock.patch("semantic_memory.injector.RankingEngine"), \
             mock.patch("semantic_memory.injector.MarkdownImporter"):

            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.collect_context.return_value = "test"
            mock_pipeline.retrieve.side_effect = RuntimeError("test error")

            main(["--project-root", "/tmp/test", "--global-store", "/tmp/store"])

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "test error" in captured.err


# ---------------------------------------------------------------------------
# Tests: Category ordering in output
# ---------------------------------------------------------------------------


class TestCategoryOrdering:
    """Categories appear in canonical order: anti-patterns, heuristics, patterns."""

    def test_categories_ordered_correctly(self):
        """Anti-patterns section comes before heuristics, which comes before patterns."""
        from semantic_memory.injector import format_output

        entries = [
            _make_entry("e1", "My Pattern", "patterns"),
            _make_entry("e2", "My Anti-Pattern", "anti-patterns"),
            _make_entry("e3", "My Heuristic", "heuristics"),
        ]

        result = RetrievalResult(
            vector_candidate_count=5,
            fts5_candidate_count=5,
            context_query="test",
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=100,
            pending=0,
            model="test",
        )

        ap_pos = output.index("### Anti-Patterns to Avoid")
        h_pos = output.index("### Heuristics")
        p_pos = output.index("### Patterns to Follow")

        assert ap_pos < h_pos < p_pos

    def test_missing_category_omitted(self):
        """If no entries exist for a category, its section header is omitted."""
        from semantic_memory.injector import format_output

        entries = [
            _make_entry("e1", "Only Pattern", "patterns"),
        ]

        result = RetrievalResult(
            vector_candidate_count=1,
            fts5_candidate_count=1,
            context_query="test",
        )

        output = format_output(
            selected=entries,
            result=result,
            total_count=10,
            pending=0,
            model="test",
        )

        assert "### Patterns to Follow" in output
        assert "### Anti-Patterns to Avoid" not in output
        assert "### Heuristics" not in output
