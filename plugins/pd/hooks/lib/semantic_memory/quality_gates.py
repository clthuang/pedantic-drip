"""Feature 115 FR-B-H3.1 / 114 IF-2: shared quality-gate logic for memory entries.

Single source of truth for the 20-char-min / 0.95 near-dup / 0.90 dedup-merge
gates. Called by:
- ``memory_server._process_store_memory`` (MCP write path)
- ``writer.py:main`` (CLI write path) — previously bypassed the gates per
  spec FR-B-H3.2

The helper takes a pre-computed embedding (or None for length-only checks)
and a MemoryDatabase instance; it does not compute embeddings itself.
"""
from __future__ import annotations

from dataclasses import dataclass

from semantic_memory.database import MemoryDatabase
from semantic_memory.dedup import check_duplicate


# Thresholds — SINGLE SOURCE OF TRUTH per spec AC-B-H3.2 (no inline duplicates
# in memory_server.py or writer.py).
DESCRIPTION_MIN_LEN = 20
NEAR_DUP_THRESHOLD = 0.95
DEDUP_MERGE_THRESHOLD = 0.90


@dataclass
class QualityGateResult:
    """Result of running quality gates against a candidate memory entry.

    Attributes
    ----------
    passed:
        True if the gates allow upsert; False if the gates reject or merge.
    reason:
        One of: None (passed), 'too_short' (length < 20), 'near_dup' (≥0.95
        match against different-named entry), 'deduped' (≥0.90 match → merged).
    merged_entry_id:
        Set when reason='deduped' — the existing entry that absorbed this one's
        observation_count bump.
    matched_entry_name:
        Set when reason='near_dup' — the name of the existing entry that
        triggered the near-dup rejection (so error messages can include it).
    """

    passed: bool
    reason: str | None = None
    merged_entry_id: str | None = None
    matched_entry_name: str | None = None


def apply_quality_gates(
    description: str,
    name: str,
    db: MemoryDatabase,
    embedding_vec=None,
    config: dict | None = None,
    keywords: list[str] | None = None,
) -> QualityGateResult:
    """Apply the three quality gates in order: length → near-dup → dedup-merge.

    Parameters
    ----------
    description:
        The candidate entry's description (the load-bearing text content).
    name:
        The candidate entry's name (used to distinguish "near-dup with same name"
        from "near-dup with different name" — only the latter is rejected).
    db:
        Open MemoryDatabase. Used for cosine-similarity comparisons against
        existing entries.
    embedding_vec:
        Pre-computed embedding vector. If None, near-dup and dedup-merge gates
        are SKIPPED (length-only check); caller is responsible for emitting a
        diagnostic in that case.
    config:
        Memory config dict. May override ``memory_dedup_threshold`` per
        feature 086 #00091.
    keywords:
        Keyword list for the merge-duplicate path. If None, merge passes an
        empty list (legacy memory_server behavior).
    """
    # Gate 1: minimum length (20 chars per spec FR-B-H3 inheritance).
    if len(description) < DESCRIPTION_MIN_LEN:
        return QualityGateResult(passed=False, reason="too_short")

    # Gates 2 + 3 require an embedding; skip if unavailable.
    if embedding_vec is None:
        return QualityGateResult(passed=True)

    # Gate 2: near-duplicate rejection (≥0.95, stricter than dedup merge).
    neardupe = check_duplicate(embedding_vec, db, threshold=NEAR_DUP_THRESHOLD)
    if neardupe.is_duplicate:
        matched_entry = db.get_entry(neardupe.existing_entry_id)
        matched_name = matched_entry["name"] if matched_entry else "unknown"
        if matched_name != name:
            return QualityGateResult(
                passed=False,
                reason="near_dup",
                matched_entry_name=matched_name,
            )

    # Gate 3: dedup-merge (≥0.90; merges into existing entry).
    threshold = DEDUP_MERGE_THRESHOLD
    cfg = config or {}
    # Allow config override per feature 086 #00091 (resolve_float_config is
    # the canonical resolver elsewhere; replicate the minimal behavior here
    # to avoid an import cycle).
    raw = cfg.get("memory_dedup_threshold")
    if raw is not None:
        try:
            threshold = max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            pass  # keep default

    dedup_result = check_duplicate(embedding_vec, db, threshold)
    if dedup_result.is_duplicate:
        merged = db.merge_duplicate(
            dedup_result.existing_entry_id,
            keywords if keywords is not None else [],
            config=cfg,
        )
        return QualityGateResult(
            passed=False,
            reason="deduped",
            merged_entry_id=merged["id"] if merged else None,
        )

    return QualityGateResult(passed=True)
