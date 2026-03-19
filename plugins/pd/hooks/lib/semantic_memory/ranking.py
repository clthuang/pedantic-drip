"""Ranking engine for semantic memory retrieval results."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from semantic_memory.retrieval_types import RetrievalResult


class RankingEngine:
    """Score and rank semantic memory retrieval candidates.

    Combines three signals -- vector similarity, BM25 keyword match, and
    entry prominence -- into a weighted final score, then applies
    category-balanced selection.

    Parameters
    ----------
    config:
        Configuration dict with keys ``memory_vector_weight``,
        ``memory_keyword_weight``, ``memory_prominence_weight``.
    """

    # Confidence level -> numeric value.
    # Fixed mapping, not data-dependent.  (Design C5, Spec D3)
    _CONFIDENCE_MAP: dict[str, float] = {
        "high": 1.0,
        "medium": 2 / 3,   # exact fraction 2/3  (design C5 / spec D3)
        "low": 1 / 3,      # exact fraction 1/3  (design C5 / spec D3)
    }

    def __init__(self, config: dict) -> None:
        self._vector_weight: float = float(config.get("memory_vector_weight", 0.5))
        self._keyword_weight: float = float(config.get("memory_keyword_weight", 0.2))
        self._prominence_weight: float = float(config.get("memory_prominence_weight", 0.3))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank(
        self,
        result: RetrievalResult,
        entries: dict[str, dict],
        limit: int,
        *,
        now: datetime | None = None,
    ) -> list[dict]:
        """Rank retrieval candidates and return the top *limit* entries.

        Parameters
        ----------
        result:
            A ``RetrievalResult`` containing candidate IDs with their
            vector and BM25 scores, plus counts of how many candidates
            came from each signal.
        entries:
            ALL entries from the database, keyed by ID.  Used for
            prominence normalization (``observation_count`` max is
            computed across every entry, not just candidates).
        limit:
            Maximum number of entries to return.
        now:
            Override for the current timestamp (for testing).  Defaults
            to ``datetime.now(timezone.utc)``.

        Returns
        -------
        list[dict]
            Entry dicts ordered by ``final_score`` descending, with a
            ``final_score`` key added to each dict.
        """
        candidates = result.candidates
        if not candidates:
            return []

        if now is None:
            now = datetime.now(timezone.utc)

        # --- Adjusted weights (redistribute if a signal is absent) --------
        vw, kw, pw = self._adjust_weights(result)

        # --- Min-max normalize vector and bm25 scores --------------------
        norm_vector = self._min_max_normalize(
            {cid: sc.vector_score for cid, sc in candidates.items()}
        )
        norm_bm25 = self._min_max_normalize(
            {cid: sc.bm25_score for cid, sc in candidates.items()}
        )

        # --- Global max observation count (across ALL entries) ------------
        max_obs = max(
            (e.get("observation_count", 0) for e in entries.values()),
            default=0,
        )

        # --- Score each candidate -----------------------------------------
        scored: list[dict] = []
        for cid in candidates:
            entry = entries.get(cid)
            if entry is None:
                continue

            prominence = self._prominence(entry, max_obs, now)
            final_score = (
                vw * norm_vector.get(cid, 0.0)
                + kw * norm_bm25.get(cid, 0.0)
                + pw * prominence
            )

            scored_entry = dict(entry)
            scored_entry["final_score"] = final_score
            scored.append(scored_entry)

        # --- Category-balanced selection ----------------------------------
        return self._balanced_select(scored, limit)

    # ------------------------------------------------------------------
    # Component helpers (kept non-private for testing)
    # ------------------------------------------------------------------

    def _confidence_value(self, level: str) -> float:
        """Map a confidence level string to a numeric value.

        Fixed mapping (not data-dependent).
        Provenance: design C5, spec D3.
        """
        return self._CONFIDENCE_MAP.get(level, 2 / 3)  # default to medium

    def _recency_decay(self, updated_at_iso: str, now: datetime) -> float:
        """Compute recency decay with log compression.

        Raw hyperbolic decay ``1/(1 + days/30)`` is compressed via
        ``log(raw + 1)`` to reduce the penalty gap between recent and
        older entries.
        """
        updated = datetime.fromisoformat(updated_at_iso)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        delta = now - updated
        days_since = max(delta.total_seconds() / 86400.0, 0.0)
        raw_recency = 1.0 / (1.0 + days_since / 30.0)
        return math.log(raw_recency + 1)

    def _recall_frequency(self, recall_count: int) -> float:
        """Compute recall frequency: ``min(recall_count / 10.0, 1.0)``."""
        return min(recall_count / 10.0, 1.0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _adjust_weights(
        self, result: RetrievalResult
    ) -> tuple[float, float, float]:
        """Adjust weights based on available signals.

        If ``vector_candidate_count == 0``, redistribute vector weight
        proportionally to keyword and prominence.  Same for
        ``fts5_candidate_count == 0``.
        """
        vw = self._vector_weight
        kw = self._keyword_weight
        pw = self._prominence_weight

        if result.vector_candidate_count == 0:
            total_remaining = kw + pw
            if total_remaining > 0:
                kw = kw + vw * (kw / total_remaining)
                pw = pw + vw * (pw / total_remaining)
            vw = 0.0

        if result.fts5_candidate_count == 0:
            total_remaining = vw + pw
            if total_remaining > 0:
                vw = vw + kw * (vw / total_remaining)
                pw = pw + kw * (pw / total_remaining)
            kw = 0.0

        return vw, kw, pw

    @staticmethod
    def _min_max_normalize(scores: dict[str, float]) -> dict[str, float]:
        """Min-max normalize a dict of scores to [0, 1].

        If max == min (all scores identical or single entry), all values
        are set to 1.0 when max > 0, or 0.0 when max == 0.
        """
        if not scores:
            return {}

        min_val = min(scores.values())
        max_val = max(scores.values())
        spread = max_val - min_val

        if spread == 0.0:
            # All identical: 1.0 if there is signal, 0.0 if max is 0
            fill = 1.0 if max_val > 0.0 else 0.0
            return {cid: fill for cid in scores}

        return {
            cid: (val - min_val) / spread
            for cid, val in scores.items()
        }

    def _prominence(
        self, entry: dict, max_obs: int, now: datetime
    ) -> float:
        """Compute prominence for a single entry.

        ``prominence = 0.3 * norm_obs + 0.2 * confidence + 0.3 * recency + 0.2 * recall``
        """
        obs_count = entry.get("observation_count", 0)
        norm_obs = math.log(obs_count + 1) / math.log(max_obs + 1) if max_obs > 0 else 0.0

        confidence = self._confidence_value(entry.get("confidence", "medium"))
        recency = self._recency_decay(entry.get("updated_at", now.isoformat()), now)
        recall = self._recall_frequency(entry.get("recall_count", 0))

        return 0.3 * norm_obs + 0.2 * confidence + 0.3 * recency + 0.2 * recall

    @staticmethod
    def _balanced_select(scored: list[dict], limit: int) -> list[dict]:
        """Apply category-balanced selection.

        When ``limit >= 9``:
        1. Group by category.
        2. For each non-empty category, take min(3, available) entries
           sorted by ``final_score`` descending.
        3. Fill remaining slots by ``final_score`` descending across all
           remaining candidates.

        When ``limit < 9``: simply take top *limit* by ``final_score``.
        """
        # Sort all by final_score descending first
        scored.sort(key=lambda e: e["final_score"], reverse=True)

        if limit < 9 or len(scored) <= limit:
            if len(scored) <= limit:
                return scored
            return scored[:limit]

        # Category-balanced selection
        by_category: dict[str, list[dict]] = {}
        for entry in scored:
            cat = entry.get("category", "unknown")
            by_category.setdefault(cat, []).append(entry)

        selected: list[dict] = []
        selected_ids: set[str] = set()

        # Phase 1: guarantee min(3, available) per non-empty category
        for cat, cat_entries in by_category.items():
            take = min(3, len(cat_entries))
            for entry in cat_entries[:take]:
                selected.append(entry)
                selected_ids.add(entry["id"])

        # Phase 2: fill remaining slots by global score order
        remaining = limit - len(selected)
        if remaining > 0:
            for entry in scored:
                if entry["id"] not in selected_ids:
                    selected.append(entry)
                    selected_ids.add(entry["id"])
                    remaining -= 1
                    if remaining <= 0:
                        break

        # Final sort by score descending
        selected.sort(key=lambda e: e["final_score"], reverse=True)
        return selected
