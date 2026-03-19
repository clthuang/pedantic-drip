"""Data types for the semantic memory retrieval system."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CandidateScores:
    """Scores for a single retrieval candidate."""
    vector_score: float = 0.0
    bm25_score: float = 0.0


@dataclass
class RetrievalResult:
    """Result of a semantic memory retrieval query."""
    candidates: dict[str, CandidateScores] = field(default_factory=dict)
    vector_candidate_count: int = 0
    fts5_candidate_count: int = 0
    context_query: str | None = None
