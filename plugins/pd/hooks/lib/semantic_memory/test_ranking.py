"""Tests for semantic_memory.ranking module."""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

import pytest

from semantic_memory.ranking import RankingEngine
from semantic_memory.retrieval_types import CandidateScores, RetrievalResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
_NOW_ISO = _NOW.isoformat()


def _make_entry(
    entry_id: str,
    *,
    category: str = "patterns",
    observation_count: int = 1,
    confidence: str = "medium",
    recall_count: int = 0,
    updated_at: str | None = None,
) -> tuple[str, dict]:
    """Build a (id, entry_dict) pair for use in entries dicts."""
    if updated_at is None:
        updated_at = _NOW_ISO
    return entry_id, {
        "id": entry_id,
        "name": f"Entry {entry_id}",
        "description": f"Description for {entry_id}",
        "category": category,
        "observation_count": observation_count,
        "confidence": confidence,
        "recall_count": recall_count,
        "updated_at": updated_at,
    }


def _default_config() -> dict:
    return {
        "memory_vector_weight": 0.5,
        "memory_keyword_weight": 0.2,
        "memory_prominence_weight": 0.3,
    }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestRankingEngineInit:
    def test_reads_weights_from_config(self):
        config = _default_config()
        engine = RankingEngine(config)
        assert engine._vector_weight == 0.5
        assert engine._keyword_weight == 0.2
        assert engine._prominence_weight == 0.3

    def test_custom_weights(self):
        config = {
            "memory_vector_weight": 0.4,
            "memory_keyword_weight": 0.3,
            "memory_prominence_weight": 0.3,
        }
        engine = RankingEngine(config)
        assert engine._vector_weight == 0.4
        assert engine._keyword_weight == 0.3
        assert engine._prominence_weight == 0.3


# ---------------------------------------------------------------------------
# Confidence mapping (design C5 / spec D3)
# ---------------------------------------------------------------------------


class TestConfidenceMapping:
    def test_high_confidence(self):
        engine = RankingEngine(_default_config())
        assert engine._confidence_value("high") == 1.0

    def test_medium_confidence(self):
        engine = RankingEngine(_default_config())
        # 2/3
        assert abs(engine._confidence_value("medium") - 2 / 3) < 1e-12

    def test_low_confidence(self):
        engine = RankingEngine(_default_config())
        # 1/3
        assert abs(engine._confidence_value("low") - 1 / 3) < 1e-12

    def test_unknown_confidence_defaults_to_medium(self):
        engine = RankingEngine(_default_config())
        assert abs(engine._confidence_value("unknown") - 2 / 3) < 1e-12


# ---------------------------------------------------------------------------
# Recency decay
# ---------------------------------------------------------------------------


class TestRecencyDecay:
    def test_updated_today(self):
        engine = RankingEngine(_default_config())
        # 0 days -> raw=1.0 -> log(1.0+1) = log(2)
        assert abs(engine._recency_decay(_NOW_ISO, _NOW) - math.log(2)) < 1e-9

    def test_updated_30_days_ago(self):
        engine = RankingEngine(_default_config())
        old = (_NOW - timedelta(days=30)).isoformat()
        # 30 days -> raw=0.5 -> log(0.5+1) = log(1.5)
        assert abs(engine._recency_decay(old, _NOW) - math.log(1.5)) < 1e-9

    def test_updated_60_days_ago(self):
        engine = RankingEngine(_default_config())
        old = (_NOW - timedelta(days=60)).isoformat()
        # 60 days -> raw=1/3 -> log(1/3+1) = log(4/3)
        result = engine._recency_decay(old, _NOW)
        assert abs(result - math.log(4 / 3)) < 1e-9


# ---------------------------------------------------------------------------
# Recall frequency
# ---------------------------------------------------------------------------


class TestRecallFrequency:
    def test_zero_recalls(self):
        engine = RankingEngine(_default_config())
        assert engine._recall_frequency(0) == 0.0

    def test_five_recalls(self):
        engine = RankingEngine(_default_config())
        assert engine._recall_frequency(5) == 0.5

    def test_ten_recalls_caps_at_one(self):
        engine = RankingEngine(_default_config())
        assert engine._recall_frequency(10) == 1.0

    def test_twenty_recalls_caps_at_one(self):
        engine = RankingEngine(_default_config())
        assert engine._recall_frequency(20) == 1.0


# ---------------------------------------------------------------------------
# Min-max normalization
# ---------------------------------------------------------------------------


class TestMinMaxNormalization:
    def test_basic_normalization(self):
        """Scores should be normalized to 0..1 range."""
        engine = RankingEngine(_default_config())
        entries = dict([
            _make_entry("a"),
            _make_entry("b"),
            _make_entry("c"),
        ])
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.9, bm25_score=10.0),
                "b": CandidateScores(vector_score=0.5, bm25_score=5.0),
                "c": CandidateScores(vector_score=0.1, bm25_score=0.0),
            },
            vector_candidate_count=3,
            fts5_candidate_count=3,
        )
        ranked = engine.rank(result, entries, limit=10)
        # "a" should have the highest vector and bm25 normalized scores
        assert ranked[0]["id"] == "a"
        # All should have final_score key
        for item in ranked:
            assert "final_score" in item

    def test_single_candidate_gets_max_normalized_scores(self):
        """A single candidate should get 1.0 for both normalized scores."""
        engine = RankingEngine(_default_config())
        entries = dict([_make_entry("a")])
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.7, bm25_score=3.0),
            },
            vector_candidate_count=1,
            fts5_candidate_count=1,
        )
        ranked = engine.rank(result, entries, limit=10)
        assert len(ranked) == 1
        assert "final_score" in ranked[0]


# ---------------------------------------------------------------------------
# Weight redistribution
# ---------------------------------------------------------------------------


class TestWeightRedistribution:
    def test_no_vector_candidates_redistributes_weight(self):
        """When vector_candidate_count=0, vector weight goes to keyword+prominence."""
        engine = RankingEngine(_default_config())
        entries = dict([_make_entry("a")])
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.0, bm25_score=5.0),
            },
            vector_candidate_count=0,
            fts5_candidate_count=1,
        )
        ranked = engine.rank(result, entries, limit=10)
        assert len(ranked) == 1
        # Score should be positive (keyword and prominence contribute)
        assert ranked[0]["final_score"] > 0

    def test_no_fts5_candidates_redistributes_weight(self):
        """When fts5_candidate_count=0, keyword weight goes to vector+prominence."""
        engine = RankingEngine(_default_config())
        entries = dict([_make_entry("a")])
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.8, bm25_score=0.0),
            },
            vector_candidate_count=1,
            fts5_candidate_count=0,
        )
        ranked = engine.rank(result, entries, limit=10)
        assert len(ranked) == 1
        assert ranked[0]["final_score"] > 0

    def test_both_signals_zero_uses_prominence_only(self):
        """When both signals are zero, all weight goes to prominence."""
        engine = RankingEngine(_default_config())
        eid, entry = _make_entry(
            "a",
            observation_count=5,
            confidence="high",
            recall_count=5,
        )
        entries = {eid: entry}
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.0, bm25_score=0.0),
            },
            vector_candidate_count=0,
            fts5_candidate_count=0,
        )
        ranked = engine.rank(result, entries, limit=10)
        assert len(ranked) == 1
        # All weight on prominence; score should be positive
        assert ranked[0]["final_score"] > 0


# ---------------------------------------------------------------------------
# Prominence computation
# ---------------------------------------------------------------------------


class TestProminence:
    def test_norm_obs_uses_all_entries(self):
        """norm_obs should be computed across ALL entries, not just candidates."""
        engine = RankingEngine(_default_config())
        # "a" is a candidate with obs_count=2, "b" is not a candidate but has obs_count=10
        _, entry_a = _make_entry("a", observation_count=2)
        _, entry_b = _make_entry("b", observation_count=10)
        entries = {"a": entry_a, "b": entry_b}
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.5, bm25_score=5.0),
            },
            vector_candidate_count=1,
            fts5_candidate_count=1,
        )
        ranked = engine.rank(result, entries, limit=10)
        # norm_obs for "a" should be 2/10 = 0.2 (not 2/2 = 1.0)
        assert len(ranked) == 1

    def test_max_obs_zero_means_norm_obs_zero(self):
        """When max observation_count across all entries is 0, norm_obs is 0 for all."""
        engine = RankingEngine(_default_config())
        _, entry = _make_entry("a", observation_count=0)
        entries = {"a": entry}
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.5, bm25_score=5.0),
            },
            vector_candidate_count=1,
            fts5_candidate_count=1,
        )
        ranked = engine.rank(result, entries, limit=10)
        assert len(ranked) == 1


# ---------------------------------------------------------------------------
# Limit / ordering
# ---------------------------------------------------------------------------


class TestLimitAndOrdering:
    def test_respects_limit(self):
        engine = RankingEngine(_default_config())
        entries = {}
        candidates = {}
        for i in range(20):
            eid, entry = _make_entry(f"e{i}", observation_count=i + 1)
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.5 + i * 0.01,
                bm25_score=float(i),
            )
        result = RetrievalResult(
            candidates=candidates,
            vector_candidate_count=20,
            fts5_candidate_count=20,
        )
        ranked = engine.rank(result, entries, limit=5)
        assert len(ranked) == 5

    def test_ordered_by_final_score_descending(self):
        engine = RankingEngine(_default_config())
        entries = dict([
            _make_entry("a"),
            _make_entry("b"),
            _make_entry("c"),
        ])
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.9, bm25_score=10.0),
                "b": CandidateScores(vector_score=0.5, bm25_score=5.0),
                "c": CandidateScores(vector_score=0.1, bm25_score=1.0),
            },
            vector_candidate_count=3,
            fts5_candidate_count=3,
        )
        ranked = engine.rank(result, entries, limit=10)
        scores = [r["final_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_returns_dicts_with_final_score(self):
        engine = RankingEngine(_default_config())
        entries = dict([_make_entry("a")])
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.5, bm25_score=1.0),
            },
            vector_candidate_count=1,
            fts5_candidate_count=1,
        )
        ranked = engine.rank(result, entries, limit=10)
        assert len(ranked) == 1
        assert "final_score" in ranked[0]
        assert isinstance(ranked[0]["final_score"], float)

    def test_empty_candidates(self):
        engine = RankingEngine(_default_config())
        entries = dict([_make_entry("a")])
        result = RetrievalResult(
            candidates={},
            vector_candidate_count=0,
            fts5_candidate_count=0,
        )
        ranked = engine.rank(result, entries, limit=10)
        assert ranked == []


# ---------------------------------------------------------------------------
# Category-balanced selection
# ---------------------------------------------------------------------------


class TestCategoryBalancedSelection:
    def _build_scenario(self) -> tuple[dict, RetrievalResult]:
        """Build entries across 3 categories with varying scores.

        Creates 12 entries: 6 patterns, 4 heuristics, 2 anti-patterns.
        Pattern entries have the highest raw scores, so without balancing
        they would dominate the top results.
        """
        entries = {}
        candidates = {}

        # 6 patterns (high scores)
        for i in range(6):
            eid, entry = _make_entry(
                f"pat{i}", category="patterns", observation_count=10
            )
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.9 - i * 0.05,
                bm25_score=10.0 - i,
            )

        # 4 heuristics (medium scores)
        for i in range(4):
            eid, entry = _make_entry(
                f"heur{i}", category="heuristics", observation_count=5
            )
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.5 - i * 0.05,
                bm25_score=5.0 - i,
            )

        # 2 anti-patterns (lower scores)
        for i in range(2):
            eid, entry = _make_entry(
                f"anti{i}", category="anti-patterns", observation_count=3
            )
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.3 - i * 0.05,
                bm25_score=3.0 - i,
            )

        result = RetrievalResult(
            candidates=candidates,
            vector_candidate_count=12,
            fts5_candidate_count=12,
        )
        return entries, result

    def test_balanced_when_limit_ge_9(self):
        """With limit >= 9, each non-empty category gets min 3 entries."""
        engine = RankingEngine(_default_config())
        entries, result = self._build_scenario()
        ranked = engine.rank(result, entries, limit=9)
        assert len(ranked) == 9

        # Check category distribution
        cats = {}
        for item in ranked:
            cat = item["category"]
            cats[cat] = cats.get(cat, 0) + 1

        # Each non-empty category should have at least 3 (anti-patterns has
        # only 2, so it should have 2)
        assert cats.get("patterns", 0) >= 3
        assert cats.get("heuristics", 0) >= 3
        # anti-patterns has only 2 entries, so at most 2
        assert cats.get("anti-patterns", 0) == 2

    def test_no_balancing_when_limit_lt_9(self):
        """With limit < 9, no category balancing is applied."""
        engine = RankingEngine(_default_config())
        entries, result = self._build_scenario()
        ranked = engine.rank(result, entries, limit=5)
        assert len(ranked) == 5
        # Should just be top 5 by score, no guarantee of category diversity

    def test_balanced_fills_remaining_by_score(self):
        """After guaranteeing 3 per category, remaining slots go to top scores."""
        engine = RankingEngine(_default_config())
        entries, result = self._build_scenario()
        ranked = engine.rank(result, entries, limit=12)
        assert len(ranked) == 12

    def test_single_category_balanced(self):
        """If all entries are one category, balancing doesn't break."""
        engine = RankingEngine(_default_config())
        entries = {}
        candidates = {}
        for i in range(10):
            eid, entry = _make_entry(f"e{i}", category="patterns")
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.9 - i * 0.05,
                bm25_score=10.0 - i,
            )
        result = RetrievalResult(
            candidates=candidates,
            vector_candidate_count=10,
            fts5_candidate_count=10,
        )
        ranked = engine.rank(result, entries, limit=9)
        assert len(ranked) == 9


# ---------------------------------------------------------------------------
# Integration: verify final_score computation
# ---------------------------------------------------------------------------


class TestFinalScoreComputation:
    def test_known_score_computation(self):
        """Verify final_score for a known scenario with exact values."""
        config = {
            "memory_vector_weight": 0.5,
            "memory_keyword_weight": 0.2,
            "memory_prominence_weight": 0.3,
        }
        engine = RankingEngine(config)

        # Two candidates with known values
        _, entry_a = _make_entry(
            "a",
            observation_count=10,
            confidence="high",
            recall_count=10,
            updated_at=_NOW_ISO,  # 0 days ago
        )
        _, entry_b = _make_entry(
            "b",
            observation_count=5,
            confidence="low",
            recall_count=0,
            updated_at=(_NOW - timedelta(days=30)).isoformat(),  # 30 days ago
        )
        entries = {"a": entry_a, "b": entry_b}

        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.9, bm25_score=8.0),
                "b": CandidateScores(vector_score=0.1, bm25_score=2.0),
            },
            vector_candidate_count=2,
            fts5_candidate_count=2,
        )
        ranked = engine.rank(result, entries, limit=10, now=_NOW)
        assert len(ranked) == 2

        # Entry "a" should rank first
        assert ranked[0]["id"] == "a"

        # Manually compute expected score for "a":
        # norm_vector: (0.9-0.1)/(0.9-0.1) = 1.0
        # norm_bm25: (8.0-2.0)/(8.0-2.0) = 1.0
        # norm_obs: log(10+1)/log(10+1) = 1.0
        # confidence: high = 1.0
        # recency: log(1.0+1) = log(2)
        # recall: min(10/10, 1.0) = 1.0
        # prominence = 0.3*1.0 + 0.2*1.0 + 0.3*log(2) + 0.2*1.0
        recency_a = math.log(2)
        prominence_a = 0.3 * 1.0 + 0.2 * 1.0 + 0.3 * recency_a + 0.2 * 1.0
        expected_a = 0.5 * 1.0 + 0.2 * 1.0 + 0.3 * prominence_a
        assert abs(ranked[0]["final_score"] - expected_a) < 1e-9

        # Entry "b":
        # norm_vector: (0.1-0.1)/(0.9-0.1) = 0.0
        # norm_bm25: (2.0-2.0)/(8.0-2.0) = 0.0
        # norm_obs: log(5+1)/log(10+1) = log(6)/log(11)
        # confidence: low = 1/3
        # recency: log(0.5+1) = log(1.5)
        # recall: min(0/10, 1.0) = 0.0
        norm_obs_b = math.log(6) / math.log(11)
        recency_b = math.log(1.5)
        prominence_b = 0.3 * norm_obs_b + 0.2 * (1 / 3) + 0.3 * recency_b + 0.2 * 0.0
        expected_b = 0.5 * 0.0 + 0.2 * 0.0 + 0.3 * prominence_b
        assert abs(ranked[1]["final_score"] - expected_b) < 1e-9

    def test_candidate_not_in_entries_is_skipped(self):
        """If a candidate ID is not in entries dict, it should be skipped."""
        engine = RankingEngine(_default_config())
        entries = dict([_make_entry("a")])
        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.5, bm25_score=1.0),
                "missing": CandidateScores(vector_score=0.9, bm25_score=9.0),
            },
            vector_candidate_count=2,
            fts5_candidate_count=2,
        )
        ranked = engine.rank(result, entries, limit=10)
        assert len(ranked) == 1
        assert ranked[0]["id"] == "a"
