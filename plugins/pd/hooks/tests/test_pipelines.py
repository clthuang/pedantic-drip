"""Consolidated Phase 3 unit tests for the semantic memory pipeline modules.

Covers:
  - RetrievalPipeline.retrieve: all 4 degradation paths + None query
  - RetrievalPipeline.collect_context: active feature, git-only, no signals
  - MarkdownImporter: parse, idempotent re-import, keywords NULL
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
from unittest import mock
from unittest.mock import MagicMock, patch

# Allow imports from hooks/lib/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import numpy as np
import pytest

from semantic_memory import content_hash
from semantic_memory.retrieval_types import CandidateScores, RetrievalResult
from semantic_memory.retrieval import RetrievalPipeline
from semantic_memory.importer import MarkdownImporter
from semantic_memory.database import MemoryDatabase


# =========================================================================
# Mock helpers
# =========================================================================


class MockDB:
    """Minimal mock database for retrieval tests."""

    def __init__(
        self,
        *,
        embeddings=None,
        fts_results=None,
        fts5_available=True,
    ):
        self._embeddings = embeddings
        self._fts_results = fts_results or []
        self._fts5_available = fts5_available

    @property
    def fts5_available(self) -> bool:
        return self._fts5_available

    def get_all_embeddings(
        self, expected_dims: int = 768
    ) -> tuple[list[str], np.ndarray] | None:
        return self._embeddings

    def fts5_search(
        self, query: str, limit: int = 100
    ) -> list[tuple[str, float]]:
        return self._fts_results

    def get_all_entries(self) -> list[dict]:
        return []


class MockProvider:
    """Minimal mock embedding provider for retrieval tests."""

    def __init__(self, embed_result: np.ndarray):
        self._embed_result = embed_result

    @property
    def dimensions(self) -> int:
        return len(self._embed_result)

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-v1"

    def embed(self, text: str, task_type: str = "query") -> np.ndarray:
        return self._embed_result


def _make_normalized_matrix(
    ids: list[str], dims: int = 3
) -> tuple[list[str], np.ndarray]:
    """Create a matrix of normalized vectors for testing."""
    rng = np.random.RandomState(42)
    matrix = rng.randn(len(ids), dims).astype(np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / norms
    return ids, matrix


# =========================================================================
# Sample markdown content for importer tests
# =========================================================================

ANTI_PATTERNS_MD = textwrap.dedent("""\
    # Anti-Patterns

    ## Observed Anti-Patterns

    ### Anti-Pattern: Premature Optimisation
    Optimising code before profiling leads to complex,
    hard-to-maintain solutions.
    - Observation Count: 5
    - Confidence: high
    - Last Observed: 2026-01-15

    ### Anti-Pattern: God Object
    A single class that knows too much or does too much.
    - Observation Count: 3
    - Confidence: medium
    - Last Observed: 2026-02-01

    ### Anti-Pattern: Copy-Paste Programming
    Duplicating code instead of abstracting shared logic.
    - Observation Count: 2
    - Confidence: low
    - Last Observed: 2026-01-20
""")

PATTERNS_MD = textwrap.dedent("""\
    # Patterns

    ## Observed Patterns

    ### Pattern: Early Return
    Return early from functions to reduce nesting.
    - Observation Count: 4
    - Confidence: high
    - Last Observed: 2026-01-10
""")


# =========================================================================
# 1. Retrieval tests: all 4 degradation paths + None query
# =========================================================================


class TestRetrieveBothSignals:
    """retrieve() with both vector and FTS5 signals active."""

    def test_candidates_have_both_scores(self):
        """Entries found by both signals carry both vector_score and bm25_score."""
        ids = ["e1", "e2", "e3"]
        emb_ids, matrix = _make_normalized_matrix(ids, dims=3)

        query_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        provider = MockProvider(embed_result=query_vec)

        fts_results = [("e2", 5.0), ("e3", 3.0), ("e4", 1.0)]

        db = MockDB(
            embeddings=(emb_ids, matrix),
            fts_results=fts_results,
            fts5_available=True,
        )

        pipeline = RetrievalPipeline(db=db, provider=provider, config={})
        result = pipeline.retrieve("test query")

        assert isinstance(result, RetrievalResult)

        # e2 and e3 appear in both vector and FTS5
        assert "e2" in result.candidates
        assert result.candidates["e2"].vector_score != 0.0
        assert result.candidates["e2"].bm25_score == 5.0

        assert "e3" in result.candidates
        assert result.candidates["e3"].vector_score != 0.0
        assert result.candidates["e3"].bm25_score == 3.0

        # e1: vector only
        assert "e1" in result.candidates
        assert result.candidates["e1"].vector_score != 0.0
        assert result.candidates["e1"].bm25_score == 0.0

        # e4: FTS5 only
        assert "e4" in result.candidates
        assert result.candidates["e4"].vector_score == 0.0
        assert result.candidates["e4"].bm25_score == 1.0

    def test_metadata_counts_correct(self):
        """vector_candidate_count and fts5_candidate_count are populated."""
        ids = ["e1", "e2", "e3"]
        emb_ids, matrix = _make_normalized_matrix(ids, dims=3)

        query_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        provider = MockProvider(embed_result=query_vec)

        fts_results = [("e2", 5.0), ("e3", 3.0)]

        db = MockDB(
            embeddings=(emb_ids, matrix),
            fts_results=fts_results,
            fts5_available=True,
        )

        pipeline = RetrievalPipeline(db=db, provider=provider, config={})
        result = pipeline.retrieve("test query")

        assert result.vector_candidate_count == 3
        assert result.fts5_candidate_count == 2
        assert result.context_query == "test query"


class TestRetrieveVectorOnly:
    """retrieve() with vector-only (fts5_available=False)."""

    def test_only_vector_scores_populated(self):
        ids = ["e1", "e2"]
        emb_ids, matrix = _make_normalized_matrix(ids, dims=3)

        query_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        provider = MockProvider(embed_result=query_vec)

        db = MockDB(
            embeddings=(emb_ids, matrix),
            fts5_available=False,
        )

        pipeline = RetrievalPipeline(db=db, provider=provider, config={})
        result = pipeline.retrieve("test query")

        assert result.vector_candidate_count == 2
        assert result.fts5_candidate_count == 0
        assert len(result.candidates) == 2
        for scores in result.candidates.values():
            assert scores.vector_score != 0.0
            assert scores.bm25_score == 0.0


class TestRetrieveFTS5Only:
    """retrieve() with FTS5-only (provider=None)."""

    def test_only_bm25_scores_populated(self):
        fts_results = [("e1", 5.0), ("e2", 3.0)]

        db = MockDB(
            fts_results=fts_results,
            fts5_available=True,
        )

        pipeline = RetrievalPipeline(db=db, provider=None, config={})
        result = pipeline.retrieve("test query")

        assert result.vector_candidate_count == 0
        assert result.fts5_candidate_count == 2
        assert len(result.candidates) == 2
        for scores in result.candidates.values():
            assert scores.vector_score == 0.0
            assert scores.bm25_score > 0.0


class TestRetrieveNeither:
    """retrieve() with neither signal (provider=None, fts5_available=False)."""

    def test_returns_empty_candidates(self):
        db = MockDB(fts5_available=False)

        pipeline = RetrievalPipeline(db=db, provider=None, config={})
        result = pipeline.retrieve("test query")

        assert result.candidates == {}
        assert result.vector_candidate_count == 0
        assert result.fts5_candidate_count == 0


class TestRetrieveNoneQuery:
    """retrieve() with None context_query passes all entries for prominence-only ranking."""

    def test_none_query_returns_empty_when_db_empty(self):
        ids = ["e1"]
        emb_ids, matrix = _make_normalized_matrix(ids, dims=3)
        query_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        provider = MockProvider(embed_result=query_vec)

        db = MockDB(
            embeddings=(emb_ids, matrix),
            fts_results=[("e1", 5.0)],
            fts5_available=True,
        )

        pipeline = RetrievalPipeline(db=db, provider=provider, config={})
        result = pipeline.retrieve(None)

        # MockDB.get_all_entries() returns [] by default
        assert result.candidates == {}
        assert result.vector_candidate_count == 0
        assert result.fts5_candidate_count == 0
        assert result.context_query is None


# =========================================================================
# 2. collect_context tests
# =========================================================================


class TestCollectContextActiveFeature:
    """collect_context with .meta.json + git output produces correct query."""

    def test_collects_slug_description_phase_files(self, tmp_path):
        """Active feature with spec.md and git diff yields complete context."""
        feature_dir = tmp_path / "docs" / "features" / "024-memory-search"
        feature_dir.mkdir(parents=True)

        meta = {
            "slug": "memory-search",
            "status": "active",
            "lastCompletedPhase": "design",
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))
        (feature_dir / "spec.md").write_text(
            "# Memory Search\n\nSemantic memory retrieval.\n\n## Reqs\n\nMore."
        )

        db = MockDB()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with patch("semantic_memory.retrieval.subprocess") as mock_sp:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = "src/retrieval.py\nsrc/importer.py"
            mock_sp.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "memory-search" in context
        assert "design" in context
        assert "src/retrieval.py" in context


class TestCollectContextNoActiveFeature:
    """collect_context with no active feature -- git diff filenames only."""

    def test_returns_files_from_git_diff(self, tmp_path):
        """When no .meta.json exists, git diff files still produce context."""
        (tmp_path / "docs" / "features").mkdir(parents=True)

        db = MockDB()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with patch("semantic_memory.retrieval.subprocess") as mock_sp:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = "hooks/lib/semantic_memory/retrieval.py"
            mock_sp.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "retrieval.py" in context
        # No slug or phase should be present
        assert "Phase:" not in context


class TestCollectContextNoSignals:
    """collect_context with no signals at all returns None."""

    def test_returns_none(self, tmp_path):
        """No .meta.json and git diff returns nothing -> None."""
        db = MockDB()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with patch("semantic_memory.retrieval.subprocess") as mock_sp:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_sp.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is None

    def test_returns_none_on_git_error(self, tmp_path):
        """Git diff exception and no feature -> None."""
        db = MockDB()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with patch("semantic_memory.retrieval.subprocess") as mock_sp:
            mock_sp.run.side_effect = Exception("git not found")

            context = pipeline.collect_context(str(tmp_path))

        assert context is None


# =========================================================================
# 3. Importer tests
# =========================================================================


@pytest.fixture
def memdb():
    """Provide an in-memory MemoryDatabase, closed after test."""
    database = MemoryDatabase(":memory:")
    yield database
    database.close()


@pytest.fixture
def importer_no_keywords(memdb):
    """MarkdownImporter with in-memory DB."""
    return MarkdownImporter(db=memdb)


class TestImporterParseRealFormat:
    """Parse real-format markdown file and verify correct entries."""

    def test_parse_three_anti_patterns(self, importer_no_keywords, memdb, tmp_path):
        """Import anti-patterns.md with 3 entries -> db has 3 entries."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        count = importer_no_keywords.import_all(
            project_root=str(tmp_path),
            global_store=str(tmp_path / "global"),
        )

        assert count == 3
        assert memdb.count_entries() == 3

    def test_entry_fields_correct(self, importer_no_keywords, memdb, tmp_path):
        """Imported entries have correct names, categories, and metadata."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        importer_no_keywords.import_all(
            project_root=str(tmp_path),
            global_store=str(tmp_path / "global"),
        )

        entries = memdb.get_all_entries()
        names = [e["name"] for e in entries]
        assert "Premature Optimisation" in names
        assert "God Object" in names
        assert "Copy-Paste Programming" in names

        for e in entries:
            assert e["category"] == "anti-patterns"
            assert e["source"] == "import"

    def test_content_hash_derived_from_description(
        self, importer_no_keywords, memdb, tmp_path
    ):
        """Each entry's id equals content_hash(description)."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        importer_no_keywords.import_all(
            project_root=str(tmp_path),
            global_store=str(tmp_path / "global"),
        )

        entries = memdb.get_all_entries()
        for e in entries:
            expected_hash = content_hash(e["description"])
            assert e["id"] == expected_hash


class TestImporterIdempotent:
    """Re-import is idempotent -- same entry count after second import."""

    def test_reimport_does_not_duplicate(self, importer_no_keywords, memdb, tmp_path):
        """Importing the same files twice does not create duplicates."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        global_store = str(tmp_path / "global")

        importer_no_keywords.import_all(str(tmp_path), global_store)
        assert memdb.count_entries() == 3

        importer_no_keywords.import_all(str(tmp_path), global_store)
        assert memdb.count_entries() == 3  # still 3, not 6


class TestImporterKeywordsNull:
    """With keyword_gen=None, imported entries have keywords=NULL in DB."""

    def test_keywords_null_after_import(self, importer_no_keywords, memdb, tmp_path):
        """All imported entries have keywords=None when keyword_gen is None."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        importer_no_keywords.import_all(
            project_root=str(tmp_path),
            global_store=str(tmp_path / "global"),
        )

        for entry in memdb.get_all_entries():
            assert entry["keywords"] is None


class TestImporterLocalAndGlobal:
    """Import from both local and global paths."""

    def test_both_paths_imported(self, importer_no_keywords, memdb, tmp_path):
        """Entries from both local knowledge-bank and global store are imported."""
        # Local: 3 anti-patterns
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        # Global: 1 pattern
        global_dir = tmp_path / "global"
        global_dir.mkdir(parents=True)
        (global_dir / "anti-patterns.md").write_text("")
        (global_dir / "patterns.md").write_text(PATTERNS_MD)
        (global_dir / "heuristics.md").write_text("")

        count = importer_no_keywords.import_all(str(tmp_path), str(global_dir))
        assert count == 4  # 3 local + 1 global
        assert memdb.count_entries() == 4
