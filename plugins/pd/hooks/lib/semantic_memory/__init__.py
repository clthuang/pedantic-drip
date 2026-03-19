"""Semantic memory system for skill retrieval."""
from __future__ import annotations

import hashlib

__version__ = "0.1.0"

VALID_CATEGORIES = frozenset({"anti-patterns", "patterns", "heuristics"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass


def content_hash(description: str) -> str:
    """SHA-256 of normalized description text, first 16 hex chars."""
    normalized = " ".join(description.lower().strip().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def source_hash(raw_text: str) -> str:
    """SHA-256 of raw markdown chunk, first 16 hex chars."""
    return hashlib.sha256(raw_text.encode()).hexdigest()[:16]
