"""End-to-end integration tests for Feature 024 (memory-semantic-search).

AC1 (full embedding quality with live API) intentionally omitted --
environment-dependent, not suitable for CI.  AC1b provides deterministic
ranking validation with pre-computed embeddings.

Tests:
  AC1b  - Semantic relevance with pre-computed embeddings
  AC9a  - Timeout safety (matmul + ranking < 100ms at 10K x 768)
  AC2   - Cross-project retrieval
  AC3   - Recall tracking across injection cycles
  AC4   - MCP capture -> retrieval round-trip
  AC6   - Toggle fallback (semantic vs legacy paths)
  AC7   - Degradation chain (provider=None, fts5=False, both)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Path setup -- make hooks/lib and mcp/ importable
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "mcp"))

import numpy as np
import pytest

from semantic_memory import content_hash
from semantic_memory.database import MemoryDatabase
from semantic_memory.retrieval_types import CandidateScores, RetrievalResult
from semantic_memory.retrieval import RetrievalPipeline
from semantic_memory.ranking import RankingEngine
from semantic_memory.config import read_config


# =========================================================================
# Helpers
# =========================================================================


def _make_mock_provider(query_vector: np.ndarray):
    """Create a mock embedding provider that returns *query_vector* on embed()."""
    provider = MagicMock()
    provider.dimensions = len(query_vector)
    provider.provider_name = "mock"
    provider.model_name = "mock-v1"
    provider.embed.return_value = query_vector
    return provider


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert_entry(
    db: MemoryDatabase,
    entry_id: str,
    name: str,
    description: str,
    category: str,
    *,
    source: str = "manual",
    source_project: str | None = None,
    embedding_vec: np.ndarray | None = None,
    keywords: list[str] | None = None,
    observation_count: int = 1,
    confidence: str = "medium",
) -> None:
    """Insert an entry into the DB with optional pre-computed embedding."""
    now = _now_iso()
    entry: dict = {
        "id": entry_id,
        "name": name,
        "description": description,
        "category": category,
        "source": source,
        "source_project": source_project,
        "keywords": json.dumps(keywords) if keywords else None,
        "observation_count": observation_count,
        "confidence": confidence,
        "created_at": now,
        "updated_at": now,
    }
    db.upsert_entry(entry)

    if embedding_vec is not None:
        db.update_embedding(entry_id, embedding_vec.astype(np.float32).tobytes())


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def memdb():
    """Provide an in-memory MemoryDatabase, closed after test."""
    database = MemoryDatabase(":memory:")
    yield database
    database.close()


# =========================================================================
# AC1b: Semantic relevance with pre-computed embeddings
# =========================================================================


class TestAC1bSemanticRelevance:
    """50 entries with controlled embeddings -- parser entries dominate top 25."""

    def test_parser_entries_dominate_top_25(self, memdb):
        """With pre-computed embeddings, >= 18 of 20 parser entries appear
        in the top 25 results after retrieval + ranking."""
        rng = np.random.RandomState(42)
        dims = 10

        # Query vector: unit vector along first axis
        query_vec = np.zeros(dims, dtype=np.float32)
        query_vec[0] = 1.0

        # Insert 20 parser entries with embeddings close to query vector
        # cosine similarity > 0.8 to query
        parser_ids = set()
        for i in range(20):
            eid = f"parser-{i:03d}"
            parser_ids.add(eid)
            # Base vector heavily weighted toward first axis
            vec = np.zeros(dims, dtype=np.float32)
            vec[0] = 0.9
            noise = rng.randn(dims).astype(np.float32) * 0.1
            noise[0] = 0.0  # keep first dim dominant
            vec = vec + noise
            vec = vec / np.linalg.norm(vec)  # normalize
            _insert_entry(
                memdb, eid,
                name=f"Parser Rule {i}",
                description=f"Parser optimization technique number {i} for AST handling",
                category="patterns",
                embedding_vec=vec,
                keywords=["parser", "ast"],
            )

        # Insert 20 deployment entries -- orthogonal to query
        for i in range(20):
            eid = f"deploy-{i:03d}"
            vec = np.zeros(dims, dtype=np.float32)
            vec[1] = 0.9
            noise = rng.randn(dims).astype(np.float32) * 0.1
            noise[0] = 0.0  # keep orthogonal
            vec = vec + noise
            vec = vec / np.linalg.norm(vec)
            _insert_entry(
                memdb, eid,
                name=f"Deployment Step {i}",
                description=f"Deployment strategy for containerized service {i}",
                category="heuristics",
                embedding_vec=vec,
                keywords=["deploy", "container"],
            )

        # Insert 10 testing entries -- orthogonal to query
        for i in range(10):
            eid = f"testing-{i:03d}"
            vec = np.zeros(dims, dtype=np.float32)
            vec[2] = 0.9
            noise = rng.randn(dims).astype(np.float32) * 0.1
            noise[0] = 0.0
            vec = vec + noise
            vec = vec / np.linalg.norm(vec)
            _insert_entry(
                memdb, eid,
                name=f"Testing Strategy {i}",
                description=f"Testing methodology for integration suite {i}",
                category="anti-patterns",
                embedding_vec=vec,
                keywords=["testing", "integration"],
            )

        assert memdb.count_entries() == 50

        # Mock provider returns query vector
        provider = _make_mock_provider(query_vec)

        # Retrieve
        pipeline = RetrievalPipeline(db=memdb, provider=provider, config={})
        result = pipeline.retrieve("parser AST optimization")

        assert result.vector_candidate_count == 50

        # Rank
        all_entries = memdb.get_all_entries()
        entries_by_id = {e["id"]: e for e in all_entries}
        config = {
            "memory_vector_weight": 0.5,
            "memory_keyword_weight": 0.2,
            "memory_prominence_weight": 0.3,
        }
        engine = RankingEngine(config)
        selected = engine.rank(result, entries_by_id, limit=25)

        assert len(selected) == 25

        # Count parser entries in top 25
        parser_in_top25 = sum(1 for e in selected if e["id"] in parser_ids)
        assert parser_in_top25 >= 18, (
            f"Expected >= 18 parser entries in top 25, got {parser_in_top25}. "
            f"Top 25 IDs: {[e['id'] for e in selected]}"
        )


# =========================================================================
# AC9a: Timeout safety -- matmul + ranking < 100ms at 10K x 768
# =========================================================================


class TestAC9aTimeoutSafety:
    """Matrix multiply (10K x 768) + ranking must complete in < 100ms."""

    def test_matmul_plus_ranking_under_100ms(self):
        """Time only the matmul + RankingEngine.rank() -- exclude DB I/O,
        embedding generation, and FTS5 search."""
        rng = np.random.RandomState(123)
        n_entries = 10_000
        dims = 768

        # Pre-build normalized matrix and query
        matrix = rng.randn(n_entries, dims).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / norms

        query_vec = rng.randn(dims).astype(np.float32)
        query_vec = query_vec / np.linalg.norm(query_vec)

        # Build synthetic candidates and entries dicts
        entry_ids = [f"e-{i}" for i in range(n_entries)]
        now_iso = _now_iso()

        entries_by_id: dict[str, dict] = {}
        candidates: dict[str, CandidateScores] = {}

        # Pre-compute (not timed): we build the dicts
        scores_array = matrix @ query_vec
        for i, eid in enumerate(entry_ids):
            candidates[eid] = CandidateScores(
                vector_score=float(scores_array[i])
            )
            entries_by_id[eid] = {
                "id": eid,
                "name": f"Entry {i}",
                "description": f"Description {i}",
                "category": ["patterns", "heuristics", "anti-patterns"][i % 3],
                "observation_count": 1,
                "confidence": "medium",
                "recall_count": 0,
                "last_recalled_at": None,
                "updated_at": now_iso,
            }

        result = RetrievalResult(
            candidates=candidates,
            vector_candidate_count=n_entries,
            fts5_candidate_count=0,
            context_query="performance test",
        )

        config = {
            "memory_vector_weight": 0.5,
            "memory_keyword_weight": 0.2,
            "memory_prominence_weight": 0.3,
        }
        engine = RankingEngine(config)

        # --- Timed section: matmul + ranking ---
        start = time.perf_counter()
        _scores = matrix @ query_vec  # matmul
        selected = engine.rank(result, entries_by_id, limit=20)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, (
            f"matmul + ranking took {elapsed:.3f}s, exceeds 100ms budget"
        )
        assert len(selected) == 20


# =========================================================================
# AC2: Cross-project retrieval
# =========================================================================


class TestAC2CrossProjectRetrieval:
    """Entry from project-a is retrievable regardless of current project context."""

    def test_cross_project_entry_found_via_fts5(self, memdb):
        """An entry with source_project='project-a' appears in FTS5 results
        when searched from a different project context."""
        _insert_entry(
            memdb,
            entry_id="cross-proj-001",
            name="Cross Project Pattern",
            description="Reusable error handling pattern discovered in project-a",
            category="patterns",
            source_project="/path/to/project-a",
            keywords=["error-handling", "reusable"],
        )

        # FTS5 search should find it by keyword regardless of project context
        fts_results = memdb.fts5_search("error handling pattern", limit=10)
        found_ids = [r[0] for r in fts_results]
        assert "cross-proj-001" in found_ids, (
            f"Cross-project entry not found in FTS5 results: {found_ids}"
        )

        # Also test via the full pipeline with a different project context
        pipeline = RetrievalPipeline(db=memdb, provider=None, config={})
        result = pipeline.retrieve("error handling pattern")

        assert "cross-proj-001" in result.candidates
        assert result.fts5_candidate_count >= 1

        # Verify the entry retains its original source_project
        entry = memdb.get_entry("cross-proj-001")
        assert entry["source_project"] == "/path/to/project-a"


# =========================================================================
# AC3: Recall tracking across injection cycles
# =========================================================================


class TestAC3RecallTracking:
    """Recall count increments and last_recalled_at updates across 3 cycles."""

    def test_recall_count_increments_over_3_cycles(self, memdb):
        """After 3 update_recall calls, recall_count=3 and
        last_recalled_at reflects the latest timestamp."""
        _insert_entry(
            memdb,
            entry_id="recall-test-001",
            name="Recall Test Entry",
            description="Entry for testing recall tracking",
            category="heuristics",
        )

        # Verify initial state
        entry = memdb.get_entry("recall-test-001")
        assert entry["recall_count"] == 0
        assert entry["last_recalled_at"] is None

        timestamps = []
        for cycle in range(1, 4):
            ts = f"2026-02-{10 + cycle}T00:00:00Z"
            timestamps.append(ts)
            memdb.update_recall(["recall-test-001"], ts)

            entry = memdb.get_entry("recall-test-001")
            assert entry["recall_count"] == cycle, (
                f"After cycle {cycle}: expected recall_count={cycle}, "
                f"got {entry['recall_count']}"
            )
            assert entry["last_recalled_at"] == ts, (
                f"After cycle {cycle}: expected last_recalled_at={ts}, "
                f"got {entry['last_recalled_at']}"
            )

        # Final verification
        entry = memdb.get_entry("recall-test-001")
        assert entry["recall_count"] == 3
        assert entry["last_recalled_at"] == timestamps[-1]


# =========================================================================
# AC4: MCP capture -> retrieval round-trip
# =========================================================================


class TestAC4McpCaptureRetrieval:
    """_process_store_memory creates entry retrievable via FTS5."""

    def test_mcp_store_then_retrieve(self, memdb):
        """Store a memory via MCP, then retrieve it via the pipeline."""
        from memory_server import _process_store_memory

        result_msg = _process_store_memory(
            db=memdb,
            provider=None,
            keyword_gen=None,
            name="MCP Round Trip Pattern",
            description="Always validate inputs before processing in pipeline stages",
            reasoning="Discovered during integration testing of the MCP server",
            category="patterns",
            references=["hooks/tests/test_integration.py"],
        )

        assert "Stored" in result_msg

        # Verify entry exists in DB
        expected_id = content_hash(
            "Always validate inputs before processing in pipeline stages"
        )
        entry = memdb.get_entry(expected_id)
        assert entry is not None
        assert entry["source"] == "session-capture"
        assert entry["name"] == "MCP Round Trip Pattern"

        # Retrieve via FTS5 keyword search
        fts_results = memdb.fts5_search("validate inputs pipeline", limit=10)
        found_ids = [r[0] for r in fts_results]
        assert expected_id in found_ids, (
            f"MCP-stored entry not found via FTS5: {found_ids}"
        )

        # Retrieve via full pipeline
        pipeline = RetrievalPipeline(db=memdb, provider=None, config={})
        retrieval_result = pipeline.retrieve("validate inputs pipeline")
        assert expected_id in retrieval_result.candidates


# =========================================================================
# AC6: Toggle fallback (semantic vs legacy paths)
# =========================================================================


class TestAC6ToggleFallback:
    """Config toggle controls semantic vs legacy memory path."""

    def test_session_start_has_semantic_toggle_branch(self):
        """session-start.sh contains the if/else branch for
        memory_semantic_enabled that selects injector.py vs memory.py."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "session-start.sh"
        )
        assert os.path.isfile(script_path), (
            f"session-start.sh not found at {script_path}"
        )

        with open(script_path, "r") as fh:
            content = fh.read()

        # The script must read the toggle
        assert "memory_semantic_enabled" in content, (
            "session-start.sh does not reference memory_semantic_enabled"
        )
        # Semantic path: injector.py
        assert "injector.py" in content, (
            "session-start.sh does not reference injector.py (semantic path)"
        )
        # Legacy path: memory.py
        assert "memory.py" in content, (
            "session-start.sh does not reference memory.py (legacy path)"
        )

    def test_config_reader_semantic_enabled_true(self, tmp_path):
        """Config with memory_semantic_enabled: true returns True."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "pd.local.md").write_text(
            "memory_semantic_enabled: true\n"
        )

        config = read_config(str(tmp_path))
        assert config["memory_semantic_enabled"] is True

    def test_config_reader_semantic_enabled_false(self, tmp_path):
        """Config with memory_semantic_enabled: false returns False."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "pd.local.md").write_text(
            "memory_semantic_enabled: false\n"
        )

        config = read_config(str(tmp_path))
        assert config["memory_semantic_enabled"] is False

    def test_config_default_is_true(self, tmp_path):
        """Without config file, memory_semantic_enabled defaults to True."""
        config = read_config(str(tmp_path))
        assert config["memory_semantic_enabled"] is True


# =========================================================================
# AC7: Degradation chain
# =========================================================================


class TestAC7DegradationChain:
    """Graceful degradation when provider and/or FTS5 are unavailable."""

    def _seed_db_with_entries(self, memdb, count=5):
        """Insert entries with FTS5 data and embeddings."""
        dims = 10
        rng = np.random.RandomState(99)
        for i in range(count):
            vec = rng.randn(dims).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            _insert_entry(
                memdb,
                entry_id=f"degrade-{i:03d}",
                name=f"Degradation Entry {i}",
                description=f"Pattern for graceful degradation testing number {i}",
                category="patterns",
                embedding_vec=vec,
                keywords=["degradation", "graceful"],
            )

    def test_ac7a_no_provider_uses_fts5_only(self, memdb):
        """provider=None: retrieval uses FTS5+prominence only, no errors."""
        self._seed_db_with_entries(memdb)

        pipeline = RetrievalPipeline(db=memdb, provider=None, config={})
        result = pipeline.retrieve("degradation graceful pattern")

        # Vector signal should be absent
        assert result.vector_candidate_count == 0
        # FTS5 signal should be present (entries contain matching keywords)
        assert result.fts5_candidate_count > 0
        assert len(result.candidates) > 0

        # All candidates should have bm25 scores, no vector scores
        for cid, scores in result.candidates.items():
            assert scores.vector_score == 0.0
            assert scores.bm25_score > 0.0

    def test_ac7b_no_fts5_uses_vector_only(self, memdb):
        """fts5_available=False: retrieval uses vector+prominence only."""
        self._seed_db_with_entries(memdb)
        dims = 10

        query_vec = np.random.RandomState(77).randn(dims).astype(np.float32)
        query_vec = query_vec / np.linalg.norm(query_vec)
        provider = _make_mock_provider(query_vec)

        # Patch fts5_available to False on the real DB
        memdb._fts5_available = False

        pipeline = RetrievalPipeline(db=memdb, provider=provider, config={})
        result = pipeline.retrieve("degradation pattern")

        # FTS5 should be absent
        assert result.fts5_candidate_count == 0
        # Vector should be present
        assert result.vector_candidate_count > 0
        assert len(result.candidates) > 0

        for cid, scores in result.candidates.items():
            assert scores.bm25_score == 0.0
            assert scores.vector_score != 0.0

    def test_ac7c_both_unavailable_returns_empty(self, memdb):
        """provider=None + fts5_available=False: empty result, no errors."""
        self._seed_db_with_entries(memdb)

        # Disable FTS5
        memdb._fts5_available = False

        pipeline = RetrievalPipeline(db=memdb, provider=None, config={})
        result = pipeline.retrieve("degradation pattern")

        assert result.candidates == {}
        assert result.vector_candidate_count == 0
        assert result.fts5_candidate_count == 0
        # No exception raised -- graceful degradation
