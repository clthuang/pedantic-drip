"""Tests for semantic deduplication checker."""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from semantic_memory.dedup import DedupResult, check_duplicate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(ids: list[str] | None, matrix: np.ndarray | None):
    """Create a mock MemoryDatabase with controlled get_all_embeddings()."""
    db = MagicMock()
    if ids is None:
        db.get_all_embeddings.return_value = None
    else:
        db.get_all_embeddings.return_value = (ids, matrix)
    return db


def _normalized(vec: np.ndarray) -> np.ndarray:
    """L2-normalize a vector."""
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return (vec / norm).astype(np.float32)


# ---------------------------------------------------------------------------
# Test: similarity > threshold returns duplicate
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    """Tests for the core duplicate detection logic."""

    def test_above_threshold_returns_duplicate(self):
        """When cosine similarity > threshold, result is_duplicate=True."""
        # Two nearly identical normalized vectors
        base = _normalized(np.array([1.0, 0.0, 0.0], dtype=np.float32))
        query = _normalized(np.array([1.0, 0.01, 0.0], dtype=np.float32))
        # Similarity should be ~0.99995
        matrix = base.reshape(1, -1)
        db = _make_db(["entry-1"], matrix)

        result = check_duplicate(query, db, threshold=0.90)

        assert result.is_duplicate is True
        assert result.existing_entry_id == "entry-1"
        assert result.similarity > 0.90

    def test_below_threshold_returns_non_duplicate(self):
        """When cosine similarity < threshold, result is_duplicate=False."""
        # Two orthogonal-ish vectors
        existing = _normalized(np.array([1.0, 0.0, 0.0], dtype=np.float32))
        query = _normalized(np.array([0.0, 1.0, 0.0], dtype=np.float32))
        # Similarity should be ~0.0
        matrix = existing.reshape(1, -1)
        db = _make_db(["entry-1"], matrix)

        result = check_duplicate(query, db, threshold=0.90)

        assert result.is_duplicate is False
        assert result.existing_entry_id is None
        assert result.similarity < 0.90

    def test_correct_entry_id_via_argmax(self):
        """When multiple entries exist, the highest-similarity entry ID is returned."""
        dim = 4
        v1 = _normalized(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
        v2 = _normalized(np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32))
        v3 = _normalized(np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32))  # closest to query

        query = _normalized(np.array([0.95, 0.05, 0.0, 0.0], dtype=np.float32))

        matrix = np.stack([v1, v2, v3])
        db = _make_db(["entry-a", "entry-b", "entry-c"], matrix)

        result = check_duplicate(query, db, threshold=0.50)

        # entry-a or entry-c should be the best match (both close to query)
        # v1 dot query ~ 0.998, v3 dot query ~ 0.998 -- v1 slightly closer
        # The important thing is the ID matches argmax
        assert result.is_duplicate is True
        assert result.existing_entry_id is not None
        # Verify the returned ID corresponds to the actual argmax
        scores = matrix @ query
        expected_idx = np.argmax(scores)
        expected_id = ["entry-a", "entry-b", "entry-c"][expected_idx]
        assert result.existing_entry_id == expected_id


# ---------------------------------------------------------------------------
# Test: empty database / no embeddings
# ---------------------------------------------------------------------------

class TestEmptyDatabase:
    """Tests for edge cases with empty or missing embeddings."""

    def test_get_all_embeddings_returns_none(self):
        """When get_all_embeddings() returns None, result is non-duplicate."""
        db = _make_db(None, None)
        query = _normalized(np.array([1.0, 0.0, 0.0], dtype=np.float32))

        result = check_duplicate(query, db)

        assert result.is_duplicate is False
        assert result.existing_entry_id is None
        assert result.similarity == 0.0

    def test_empty_ids_list(self):
        """When get_all_embeddings() returns empty ids, result is non-duplicate."""
        db = _make_db([], np.array([]).reshape(0, 3))
        query = _normalized(np.array([1.0, 0.0, 0.0], dtype=np.float32))

        result = check_duplicate(query, db)

        assert result.is_duplicate is False
        assert result.existing_entry_id is None
        assert result.similarity == 0.0


# ---------------------------------------------------------------------------
# Test: graceful degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """Tests for error handling and graceful degradation."""

    def test_db_raises_exception(self):
        """When db.get_all_embeddings() raises, result is non-duplicate with 0.0 similarity."""
        db = MagicMock()
        db.get_all_embeddings.side_effect = RuntimeError("DB error")
        query = _normalized(np.array([1.0, 0.0, 0.0], dtype=np.float32))

        result = check_duplicate(query, db)

        assert result.is_duplicate is False
        assert result.existing_entry_id is None
        assert result.similarity == 0.0

    def test_corrupted_matrix_shape(self):
        """When matrix shape is incompatible, graceful degradation."""
        db = MagicMock()
        # Return a matrix with wrong dimensions
        db.get_all_embeddings.return_value = (
            ["entry-1"],
            np.array([[1.0, 0.0]], dtype=np.float32),  # 2 dims
        )
        query = _normalized(np.array([1.0, 0.0, 0.0], dtype=np.float32))  # 3 dims

        result = check_duplicate(query, db)

        # Should degrade gracefully (matmul will fail with shape mismatch)
        assert result.is_duplicate is False
        assert result.similarity == 0.0


# ---------------------------------------------------------------------------
# Test: threshold parameter
# ---------------------------------------------------------------------------

class TestThresholdParameter:
    """Tests that the threshold parameter is respected."""

    def _make_pair_with_similarity(self, target_sim: float):
        """Create a query and matrix entry with approximately the target similarity.

        Uses 2D vectors: [cos(theta), sin(theta)] where theta = arccos(target_sim).
        """
        theta = np.arccos(np.clip(target_sim, -1.0, 1.0))
        existing = np.array([1.0, 0.0], dtype=np.float32)
        query = np.array([np.cos(theta), np.sin(theta)], dtype=np.float32)
        # Already unit vectors
        return existing.reshape(1, -1), query

    def test_threshold_090_default(self):
        """Default threshold of 0.90 correctly classifies."""
        matrix, query = self._make_pair_with_similarity(0.92)
        db = _make_db(["entry-1"], matrix)

        result = check_duplicate(query, db)  # default threshold=0.90

        assert result.is_duplicate is True

    def test_threshold_080_more_lenient(self):
        """Threshold 0.80 catches entries that 0.90 would miss."""
        matrix, query = self._make_pair_with_similarity(0.85)
        db = _make_db(["entry-1"], matrix)

        # At 0.90 threshold: not a duplicate
        result_strict = check_duplicate(query, db, threshold=0.90)
        assert result_strict.is_duplicate is False

        # At 0.80 threshold: is a duplicate
        result_lenient = check_duplicate(query, db, threshold=0.80)
        assert result_lenient.is_duplicate is True

    def test_threshold_095_more_strict(self):
        """Threshold 0.95 is stricter than default 0.90."""
        matrix, query = self._make_pair_with_similarity(0.92)
        db = _make_db(["entry-1"], matrix)

        # At 0.90 threshold: is a duplicate
        result_default = check_duplicate(query, db, threshold=0.90)
        assert result_default.is_duplicate is True

        # At 0.95 threshold: not a duplicate
        result_strict = check_duplicate(query, db, threshold=0.95)
        assert result_strict.is_duplicate is False

    def test_exact_threshold_boundary(self):
        """Similarity exactly at threshold is NOT a duplicate (> not >=)."""
        # Create vectors with similarity very close to 0.90
        matrix, query = self._make_pair_with_similarity(0.90)
        db = _make_db(["entry-1"], matrix)

        result = check_duplicate(query, db, threshold=0.90)

        # Exactly at threshold should NOT be duplicate (strict >)
        assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# Test: AC-6 near-duplicate detection scenario
# ---------------------------------------------------------------------------

class TestAC6NearDuplicateDetection:
    """AC-6: Given two entries with cosine similarity > 0.90, the second
    store_memory call should detect the duplicate."""

    def test_near_duplicate_detected(self):
        """Simulate two similar entries: first stored, second checked for dedup."""
        dim = 8
        # Simulate an existing entry's embedding
        existing_vec = _normalized(np.random.RandomState(42).randn(dim).astype(np.float32))

        # Simulate a new entry that is very similar (add small noise)
        noise = np.random.RandomState(43).randn(dim).astype(np.float32) * 0.01
        new_vec = _normalized(existing_vec + noise)

        # Verify the vectors are indeed similar > 0.90
        actual_sim = float(existing_vec @ new_vec)
        assert actual_sim > 0.90, f"Test setup error: similarity={actual_sim}"

        matrix = existing_vec.reshape(1, -1)
        db = _make_db(["existing-entry-id"], matrix)

        result = check_duplicate(new_vec, db, threshold=0.90)

        assert result.is_duplicate is True
        assert result.existing_entry_id == "existing-entry-id"
        assert result.similarity > 0.90

    def test_distinct_entries_not_merged(self):
        """Entries on different topics should NOT be detected as duplicates."""
        dim = 8
        rs = np.random.RandomState(99)
        existing_vec = _normalized(rs.randn(dim).astype(np.float32))
        # Create a very different vector
        different_vec = _normalized(np.array([-x for x in existing_vec], dtype=np.float32))

        actual_sim = float(existing_vec @ different_vec)
        assert actual_sim < 0.90, f"Test setup error: similarity={actual_sim}"

        matrix = existing_vec.reshape(1, -1)
        db = _make_db(["existing-entry-id"], matrix)

        result = check_duplicate(different_vec, db, threshold=0.90)

        assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# Test: DedupResult dataclass
# ---------------------------------------------------------------------------

class TestDedupResult:
    """Tests for the DedupResult dataclass."""

    def test_fields(self):
        r = DedupResult(is_duplicate=True, existing_entry_id="abc", similarity=0.95)
        assert r.is_duplicate is True
        assert r.existing_entry_id == "abc"
        assert r.similarity == 0.95

    def test_non_duplicate_result(self):
        r = DedupResult(is_duplicate=False, existing_entry_id=None, similarity=0.3)
        assert r.is_duplicate is False
        assert r.existing_entry_id is None
        assert r.similarity == 0.3
