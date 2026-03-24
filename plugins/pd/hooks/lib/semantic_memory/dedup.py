"""Semantic deduplication checker for memory entries.

Compares a new entry's embedding vector against all existing entries
using cosine similarity (matmul on pre-normalized vectors). Returns a
DedupResult indicating whether the entry is a near-duplicate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from semantic_memory.database import MemoryDatabase

try:
    import numpy as np

    _numpy_available = True
except ImportError:  # pragma: no cover
    _numpy_available = False


@dataclass
class DedupResult:
    """Result of a deduplication check."""

    is_duplicate: bool
    existing_entry_id: str | None
    similarity: float


def check_duplicate(
    embedding_vec: "np.ndarray",
    db: "MemoryDatabase",
    threshold: float = 0.90,
) -> DedupResult:
    """Check if a new entry (by its pre-computed embedding) is a near-duplicate.

    Compares embedding_vec against all existing entries via matmul on
    normalized vectors. Uses db.get_all_embeddings() which returns
    (ids: list[str], matrix: np.ndarray). Match lookup: ids[np.argmax(scores)].

    Self-matching is not possible -- the new entry hasn't been inserted yet.

    Graceful degradation: returns DedupResult(is_duplicate=False, None, 0.0)
    if numpy is unavailable, no entries exist, or any error occurs.
    """
    try:
        if not _numpy_available:  # pragma: no cover
            return DedupResult(False, None, 0.0)

        result = db.get_all_embeddings()
        if result is None:
            return DedupResult(False, None, 0.0)

        ids, matrix = result

        if len(ids) == 0:
            return DedupResult(False, None, 0.0)

        scores = matrix @ embedding_vec
        best_idx = np.argmax(scores)

        if scores[best_idx] > threshold:
            return DedupResult(True, ids[best_idx], float(scores[best_idx]))
        else:
            return DedupResult(False, None, float(scores[best_idx]))

    except Exception:
        return DedupResult(False, None, 0.0)
