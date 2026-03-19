"""Consolidated Phase 2 unit tests for the semantic memory system.

Covers all Phase 2 modules in a single file:
  - NormalizingWrapper (semantic_memory.embedding)
  - create_provider (semantic_memory.embedding)
  - Keyword validation (semantic_memory.keywords)
  - Ranking formula (semantic_memory.ranking)
  - Weight redistribution (semantic_memory.ranking)
  - Category-balanced selection (semantic_memory.ranking)
  - Prominence sub-components (semantic_memory.ranking)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# Allow imports from hooks/lib/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import numpy as np
import pytest

from semantic_memory import EmbeddingError
from semantic_memory.embedding import NormalizingWrapper, create_provider, EmbeddingProvider
from semantic_memory.keywords import TieredKeywordGenerator, SkipKeywordGenerator, STOPWORD_LIST
from semantic_memory.ranking import RankingEngine
from semantic_memory.retrieval_types import CandidateScores, RetrievalResult


# =========================================================================
# Helpers
# =========================================================================


class _FakeEmbeddingProvider:
    """Minimal EmbeddingProvider for testing NormalizingWrapper."""

    def __init__(self, embed_result=None, batch_result=None):
        self._embed_result = embed_result
        self._batch_result = batch_result

    @property
    def dimensions(self) -> int:
        return 5

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-model"

    def embed(self, text: str, task_type: str = "query") -> np.ndarray:
        return self._embed_result

    def embed_batch(
        self, texts: list[str], task_type: str = "document"
    ) -> list[np.ndarray]:
        return self._batch_result


class _FakeKeywordProvider:
    """A fake keyword provider that returns a pre-configured response."""

    def __init__(self, response: list[str]):
        self._response = response

    def generate(
        self,
        name: str,
        description: str,
        reasoning: str,
        category: str,
    ) -> list[str]:
        return self._response


_NOW = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
_NOW_ISO = _NOW.isoformat()


def _default_ranking_config() -> dict:
    return {
        "memory_vector_weight": 0.5,
        "memory_keyword_weight": 0.2,
        "memory_prominence_weight": 0.3,
    }


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


# =========================================================================
# 1. NormalizingWrapper tests
# =========================================================================


class TestNormalizingWrapperNormalization:
    """NormalizingWrapper normalizes vectors to unit length."""

    def test_normalizes_to_unit_length(self):
        """embed() should L2-normalize the vector to unit length."""
        # [3, 4, 0, 0, 0] has norm 5.0 -> expected [0.6, 0.8, 0, 0, 0]
        raw = np.array([3.0, 4.0, 0.0, 0.0, 0.0], dtype=np.float32)
        inner = _FakeEmbeddingProvider(embed_result=raw)
        wrapper = NormalizingWrapper(inner)

        result = wrapper.embed("hello")
        norm = float(np.linalg.norm(result))
        assert abs(norm - 1.0) < 1e-6, f"Expected unit norm, got {norm}"
        np.testing.assert_array_almost_equal(
            result, [0.6, 0.8, 0.0, 0.0, 0.0]
        )

    def test_already_unit_vector_unchanged(self):
        """A vector that is already unit-length should remain unchanged."""
        raw = np.array([1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        inner = _FakeEmbeddingProvider(embed_result=raw)
        wrapper = NormalizingWrapper(inner)

        result = wrapper.embed("hello")
        np.testing.assert_array_almost_equal(result, [1.0, 0.0, 0.0, 0.0, 0.0])

    def test_zero_vector_raises_embedding_error(self):
        """embed() should raise EmbeddingError for zero vectors."""
        raw = np.zeros(5, dtype=np.float32)
        inner = _FakeEmbeddingProvider(embed_result=raw)
        wrapper = NormalizingWrapper(inner)

        with pytest.raises(EmbeddingError, match="Zero vector detected"):
            wrapper.embed("empty")

    def test_near_zero_vector_raises_embedding_error(self):
        """Vectors with norm < 1e-9 should be treated as zero vectors."""
        raw = np.array([1e-10, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        inner = _FakeEmbeddingProvider(embed_result=raw)
        wrapper = NormalizingWrapper(inner)

        with pytest.raises(EmbeddingError, match="Zero vector detected"):
            wrapper.embed("tiny")


class TestNormalizingWrapperBatch:
    """embed_batch() normalizes each vector independently."""

    def test_normalizes_each_vector_independently(self):
        batch = [
            np.array([3.0, 4.0, 0.0], dtype=np.float32),  # norm 5
            np.array([0.0, 0.0, 2.0], dtype=np.float32),  # norm 2
        ]
        inner = _FakeEmbeddingProvider(batch_result=batch)
        wrapper = NormalizingWrapper(inner)

        results = wrapper.embed_batch(["a", "b"])
        assert len(results) == 2

        for result in results:
            norm = float(np.linalg.norm(result))
            assert abs(norm - 1.0) < 1e-6

        np.testing.assert_array_almost_equal(results[0], [0.6, 0.8, 0.0])
        np.testing.assert_array_almost_equal(results[1], [0.0, 0.0, 1.0])

    def test_zero_vector_in_batch_raises(self):
        """embed_batch() should raise if any vector in the batch is zero."""
        batch = [
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
            np.zeros(3, dtype=np.float32),
        ]
        inner = _FakeEmbeddingProvider(batch_result=batch)
        wrapper = NormalizingWrapper(inner)

        with pytest.raises(EmbeddingError, match="Zero vector detected"):
            wrapper.embed_batch(["ok", "zero"])


class TestNormalizingWrapperProperties:
    """Properties should be forwarded from the inner provider."""

    def test_dimensions_forwarded(self):
        inner = _FakeEmbeddingProvider()
        wrapper = NormalizingWrapper(inner)
        assert wrapper.dimensions == 5

    def test_provider_name_forwarded(self):
        inner = _FakeEmbeddingProvider()
        wrapper = NormalizingWrapper(inner)
        assert wrapper.provider_name == "fake"

    def test_model_name_forwarded(self):
        inner = _FakeEmbeddingProvider()
        wrapper = NormalizingWrapper(inner)
        assert wrapper.model_name == "fake-model"

    def test_satisfies_embedding_provider_protocol(self):
        inner = _FakeEmbeddingProvider()
        wrapper = NormalizingWrapper(inner)
        assert isinstance(wrapper, EmbeddingProvider)


# =========================================================================
# 2. create_provider tests
# =========================================================================


class TestCreateProvider:
    """create_provider returns None or a NormalizingWrapper based on config."""

    def test_returns_none_when_gemini_env_var_missing(self):
        """create_provider should return None when GEMINI_API_KEY is not set."""
        config = {
            "memory_embedding_provider": "gemini",
            "memory_embedding_model": "gemini-embedding-001",
        }
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = create_provider(config)
        assert result is None

    def test_returns_none_for_unknown_provider(self):
        """create_provider should return None for an unrecognized provider name."""
        config = {
            "memory_embedding_provider": "nonexistent-provider",
            "memory_embedding_model": "some-model",
        }
        result = create_provider(config)
        assert result is None

    @patch("semantic_memory.embedding.GeminiProvider")
    def test_returns_normalizing_wrapper_with_valid_env(self, mock_gemini_cls):
        """create_provider should return NormalizingWrapper when API key is set."""
        mock_gemini_cls.return_value = _FakeEmbeddingProvider()
        config = {
            "memory_embedding_provider": "gemini",
            "memory_embedding_model": "gemini-embedding-001",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            result = create_provider(config)

        assert result is not None
        assert isinstance(result, NormalizingWrapper)
        mock_gemini_cls.assert_called_once_with(
            api_key="test-key", model="gemini-embedding-001"
        )

    def test_ollama_returns_none_no_constructor(self):
        """Ollama provider returns None (no constructor yet)."""
        config = {
            "memory_embedding_provider": "ollama",
            "memory_embedding_model": "nomic-embed-text",
        }
        result = create_provider(config)
        assert result is None

    def test_returns_none_for_empty_api_key(self):
        """An empty API key env var should still return None."""
        config = {
            "memory_embedding_provider": "gemini",
            "memory_embedding_model": "gemini-embedding-001",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            result = create_provider(config)
        assert result is None

    @patch("semantic_memory.embedding.GeminiProvider", side_effect=Exception("SDK error"))
    def test_returns_none_on_construction_error(self, mock_gemini_cls):
        """create_provider should return None if provider construction fails."""
        config = {
            "memory_embedding_provider": "gemini",
            "memory_embedding_model": "gemini-embedding-001",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            result = create_provider(config)
        assert result is None


# =========================================================================
# 3. Keyword validation tests
# =========================================================================


class TestKeywordValidation:
    """Per-keyword filtering: regex validation and stopword rejection."""

    def _make_generator(self) -> TieredKeywordGenerator:
        config = {"memory_keyword_provider": "off"}
        return TieredKeywordGenerator(config)

    def test_valid_simple_keyword(self):
        gen = self._make_generator()
        assert gen._validate_keyword("sqlite") is True

    def test_valid_hyphenated_keyword(self):
        gen = self._make_generator()
        assert gen._validate_keyword("content-hash") is True

    def test_valid_keyword_starting_with_digit(self):
        gen = self._make_generator()
        assert gen._validate_keyword("fts5") is True
        assert gen._validate_keyword("3d-model") is True

    def test_rejects_uppercase(self):
        gen = self._make_generator()
        assert gen._validate_keyword("SQLite") is False

    def test_rejects_spaces(self):
        gen = self._make_generator()
        assert gen._validate_keyword("content hash") is False

    def test_rejects_underscores(self):
        gen = self._make_generator()
        assert gen._validate_keyword("content_hash") is False

    def test_rejects_leading_hyphen(self):
        gen = self._make_generator()
        assert gen._validate_keyword("-sqlite") is False

    def test_rejects_empty_string(self):
        gen = self._make_generator()
        assert gen._validate_keyword("") is False

    def test_rejects_special_characters(self):
        gen = self._make_generator()
        for bad in ['["fts5"]', '"keyword"', "key,word", "key[0]", "foo!"]:
            assert gen._validate_keyword(bad) is False, f"Should reject: {bad}"

    def test_rejects_all_stopwords(self):
        """Every word in STOPWORD_LIST should be rejected."""
        gen = self._make_generator()
        for stopword in STOPWORD_LIST:
            assert gen._validate_keyword(stopword) is False, (
                f"Stopword '{stopword}' was not rejected"
            )

    def test_stopword_list_has_17_entries(self):
        assert len(STOPWORD_LIST) == 17

    def test_non_stopwords_accepted(self):
        gen = self._make_generator()
        non_stopwords = ["sqlite", "fts5", "parser-error", "retry", "backoff"]
        for kw in non_stopwords:
            assert gen._validate_keyword(kw) is True, (
                f"Non-stopword '{kw}' was incorrectly rejected"
            )

    def test_regex_pattern_anchored(self):
        """Regex must match full string, not partial."""
        gen = self._make_generator()
        # Valid at start but has trailing space
        assert gen._validate_keyword("fts5 ") is False
        # Valid chars but starts with special
        assert gen._validate_keyword(".fts5") is False


class TestKeywordGeneratePipeline:
    """Full generate() pipeline with fake providers."""

    def _make_generator_with_fake(
        self, fake_response: list[str]
    ) -> TieredKeywordGenerator:
        config = {"memory_keyword_provider": "off"}
        gen = TieredKeywordGenerator(config)
        gen._tiers = [_FakeKeywordProvider(fake_response)]
        return gen

    def test_filters_stopwords_from_results(self):
        gen = self._make_generator_with_fake(
            ["sqlite", "code", "development", "fts5", "system", "parser"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["sqlite", "fts5", "parser"]

    def test_filters_invalid_format_keywords(self):
        gen = self._make_generator_with_fake(
            ["sqlite", "UPPERCASE", "content hash", "fts5", "parser"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["sqlite", "fts5", "parser"]

    def test_returns_empty_if_fewer_than_3_valid(self):
        gen = self._make_generator_with_fake(["sqlite", "fts5"])
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == []

    def test_caps_at_10_keywords(self):
        keywords = [f"kw{i}" for i in range(15)]
        gen = self._make_generator_with_fake(keywords)
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert len(result) == 10

    def test_deduplicates_keywords(self):
        gen = self._make_generator_with_fake(
            ["sqlite", "sqlite", "fts5", "fts5", "parser"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["sqlite", "fts5", "parser"]


class TestSkipKeywordGeneratorConsolidated:
    """SkipKeywordGenerator always returns an empty list."""

    def test_returns_empty_list(self):
        gen = SkipKeywordGenerator()
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == []


# =========================================================================
# 4. Ranking formula tests
# =========================================================================


class TestRankingFormula:
    """Known score inputs produce expected ordering."""

    def test_higher_vector_and_bm25_ranks_first(self):
        """Entry with higher vector and BM25 scores should rank first."""
        engine = RankingEngine(_default_ranking_config())
        entries = dict([
            _make_entry("high", observation_count=5, confidence="high",
                        recall_count=5, updated_at=_NOW_ISO),
            _make_entry("low", observation_count=1, confidence="low",
                        recall_count=0,
                        updated_at=(_NOW - timedelta(days=60)).isoformat()),
        ])
        result = RetrievalResult(
            candidates={
                "high": CandidateScores(vector_score=0.9, bm25_score=10.0),
                "low": CandidateScores(vector_score=0.1, bm25_score=1.0),
            },
            vector_candidate_count=2,
            fts5_candidate_count=2,
        )
        ranked = engine.rank(result, entries, limit=10, now=_NOW)
        assert ranked[0]["id"] == "high"
        assert ranked[1]["id"] == "low"
        assert ranked[0]["final_score"] > ranked[1]["final_score"]

    def test_known_exact_score_computation(self):
        """Verify final_score for a known scenario with exact numeric values."""
        config = _default_ranking_config()
        engine = RankingEngine(config)

        _, entry_a = _make_entry(
            "a",
            observation_count=10,
            confidence="high",
            recall_count=10,
            updated_at=_NOW_ISO,
        )
        _, entry_b = _make_entry(
            "b",
            observation_count=5,
            confidence="low",
            recall_count=0,
            updated_at=(_NOW - timedelta(days=30)).isoformat(),
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

        # Entry "a":
        # norm_vector: (0.9-0.1)/(0.9-0.1) = 1.0
        # norm_bm25: (8.0-2.0)/(8.0-2.0) = 1.0
        # norm_obs: 10/10 = 1.0
        # confidence: high = 1.0
        # recency: 1.0 / (1+0/30) = 1.0
        # recall: min(10/10, 1.0) = 1.0
        # prominence = 0.3*1.0 + 0.2*1.0 + 0.3*1.0 + 0.2*1.0 = 1.0
        # final = 0.5*1.0 + 0.2*1.0 + 0.3*1.0 = 1.0
        assert abs(ranked[0]["final_score"] - 1.0) < 1e-9
        assert ranked[0]["id"] == "a"

        # Entry "b":
        # norm_vector: 0.0, norm_bm25: 0.0
        # norm_obs: 5/10 = 0.5
        # confidence: low = 1/3
        # recency: 1.0 / (1+30/30) = 0.5
        # recall: 0.0
        # prominence = 0.3*0.5 + 0.2*(1/3) + 0.3*0.5 + 0.2*0.0
        expected_prominence_b = 0.3 * 0.5 + 0.2 * (1 / 3) + 0.3 * 0.5 + 0.2 * 0.0
        expected_b = 0.3 * expected_prominence_b
        assert abs(ranked[1]["final_score"] - expected_b) < 1e-9

    def test_all_candidates_get_final_score_key(self):
        """Every ranked entry should have a 'final_score' key."""
        engine = RankingEngine(_default_ranking_config())
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
        ranked = engine.rank(result, entries, limit=10, now=_NOW)
        for item in ranked:
            assert "final_score" in item
            assert isinstance(item["final_score"], float)

    def test_results_ordered_descending_by_score(self):
        """Ranked results should be sorted by final_score descending."""
        engine = RankingEngine(_default_ranking_config())
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
        ranked = engine.rank(result, entries, limit=10, now=_NOW)
        scores = [r["final_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_empty_candidates_returns_empty(self):
        """No candidates should return an empty list."""
        engine = RankingEngine(_default_ranking_config())
        entries = dict([_make_entry("a")])
        result = RetrievalResult(
            candidates={},
            vector_candidate_count=0,
            fts5_candidate_count=0,
        )
        ranked = engine.rank(result, entries, limit=10)
        assert ranked == []


# =========================================================================
# 5. Weight redistribution tests
# =========================================================================


class TestWeightRedistribution:
    """vector_candidate_count=0 or fts5_candidate_count=0 redistributes weight."""

    def test_no_vector_candidates_redistributes_to_keyword_and_prominence(self):
        """When vector_candidate_count=0, vector weight is redistributed."""
        engine = RankingEngine(_default_ranking_config())

        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.0, bm25_score=5.0),
            },
            vector_candidate_count=0,
            fts5_candidate_count=1,
        )
        vw, kw, pw = engine._adjust_weights(result)

        # Original: vw=0.5, kw=0.2, pw=0.3
        # After redistribution: vw=0
        # kw = 0.2 + 0.5 * (0.2/0.5) = 0.2 + 0.2 = 0.4
        # pw = 0.3 + 0.5 * (0.3/0.5) = 0.3 + 0.3 = 0.6
        assert vw == 0.0
        assert abs(kw - 0.4) < 1e-9
        assert abs(pw - 0.6) < 1e-9

    def test_no_fts5_candidates_redistributes_to_vector_and_prominence(self):
        """When fts5_candidate_count=0, keyword weight is redistributed."""
        engine = RankingEngine(_default_ranking_config())

        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.8, bm25_score=0.0),
            },
            vector_candidate_count=1,
            fts5_candidate_count=0,
        )
        vw, kw, pw = engine._adjust_weights(result)

        # Original: vw=0.5, kw=0.2, pw=0.3
        # After redistribution: kw=0
        # vw = 0.5 + 0.2 * (0.5/0.8) = 0.5 + 0.125 = 0.625
        # pw = 0.3 + 0.2 * (0.3/0.8) = 0.3 + 0.075 = 0.375
        assert kw == 0.0
        assert abs(vw - 0.625) < 1e-9
        assert abs(pw - 0.375) < 1e-9

    def test_both_signals_zero_all_weight_to_prominence(self):
        """When both signals are 0, all weight goes to prominence."""
        engine = RankingEngine(_default_ranking_config())

        result = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.0, bm25_score=0.0),
            },
            vector_candidate_count=0,
            fts5_candidate_count=0,
        )
        vw, kw, pw = engine._adjust_weights(result)

        assert vw == 0.0
        assert kw == 0.0
        assert abs(pw - 1.0) < 1e-9

    def test_redistribution_preserves_total_weight(self):
        """Total weight should always sum to 1.0 after redistribution."""
        engine = RankingEngine(_default_ranking_config())

        for vec_count, fts_count in [(0, 1), (1, 0), (0, 0), (1, 1)]:
            result = RetrievalResult(
                candidates={"a": CandidateScores()},
                vector_candidate_count=vec_count,
                fts5_candidate_count=fts_count,
            )
            vw, kw, pw = engine._adjust_weights(result)
            total = vw + kw + pw
            assert abs(total - 1.0) < 1e-9, (
                f"Total weight {total} != 1.0 for "
                f"vec={vec_count}, fts={fts_count}"
            )


# =========================================================================
# 6. Category-balanced selection tests
# =========================================================================


class TestCategoryBalance:
    """Category-balanced selection with min-3 per category."""

    def _build_three_category_scenario(
        self,
    ) -> tuple[dict, RetrievalResult]:
        """Build 3 categories: 8 patterns, 6 heuristics, 4 anti-patterns."""
        entries = {}
        candidates = {}

        for i in range(8):
            eid, entry = _make_entry(
                f"pat{i}", category="patterns", observation_count=10
            )
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.9 - i * 0.05,
                bm25_score=10.0 - i,
            )

        for i in range(6):
            eid, entry = _make_entry(
                f"heur{i}", category="heuristics", observation_count=5
            )
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.5 - i * 0.05,
                bm25_score=5.0 - i,
            )

        for i in range(4):
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
            vector_candidate_count=18,
            fts5_candidate_count=18,
        )
        return entries, result

    def test_three_categories_limit_20_min_3_each(self):
        """3 categories with limit=20: each non-empty category gets min 3."""
        engine = RankingEngine(_default_ranking_config())
        entries, result = self._build_three_category_scenario()
        ranked = engine.rank(result, entries, limit=20, now=_NOW)

        # All 18 entries fit within limit=20
        assert len(ranked) == 18

        cats = {}
        for item in ranked:
            cat = item["category"]
            cats[cat] = cats.get(cat, 0) + 1

        assert cats.get("patterns", 0) >= 3
        assert cats.get("heuristics", 0) >= 3
        assert cats.get("anti-patterns", 0) >= 3

    def test_balanced_with_limit_9(self):
        """With limit=9, category balancing applies: min(3, available) per category."""
        engine = RankingEngine(_default_ranking_config())
        entries, result = self._build_three_category_scenario()
        ranked = engine.rank(result, entries, limit=9, now=_NOW)
        assert len(ranked) == 9

        cats = {}
        for item in ranked:
            cat = item["category"]
            cats[cat] = cats.get(cat, 0) + 1

        # Each category should have at least 3 entries
        assert cats.get("patterns", 0) >= 3
        assert cats.get("heuristics", 0) >= 3
        assert cats.get("anti-patterns", 0) >= 3

    def test_no_balancing_when_limit_lt_9(self):
        """With limit < 9, no category balancing -- just top by score."""
        engine = RankingEngine(_default_ranking_config())
        entries, result = self._build_three_category_scenario()
        ranked = engine.rank(result, entries, limit=5, now=_NOW)
        assert len(ranked) == 5

    def test_category_with_fewer_than_3_entries(self):
        """A category with fewer than 3 entries gives all it has."""
        engine = RankingEngine(_default_ranking_config())
        entries = {}
        candidates = {}

        # 5 patterns
        for i in range(5):
            eid, entry = _make_entry(f"pat{i}", category="patterns")
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.9 - i * 0.05, bm25_score=10.0 - i
            )

        # 2 heuristics (fewer than 3)
        for i in range(2):
            eid, entry = _make_entry(f"heur{i}", category="heuristics")
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.4 - i * 0.05, bm25_score=4.0 - i
            )

        # 5 anti-patterns
        for i in range(5):
            eid, entry = _make_entry(f"anti{i}", category="anti-patterns")
            entries[eid] = entry
            candidates[eid] = CandidateScores(
                vector_score=0.3 - i * 0.02, bm25_score=3.0 - i * 0.5
            )

        result = RetrievalResult(
            candidates=candidates,
            vector_candidate_count=12,
            fts5_candidate_count=12,
        )
        ranked = engine.rank(result, entries, limit=9, now=_NOW)
        assert len(ranked) == 9

        cats = {}
        for item in ranked:
            cat = item["category"]
            cats[cat] = cats.get(cat, 0) + 1

        # heuristics has only 2, so it gets 2
        assert cats.get("heuristics", 0) == 2
        # patterns and anti-patterns have enough for min 3
        assert cats.get("patterns", 0) >= 3
        assert cats.get("anti-patterns", 0) >= 3


# =========================================================================
# 7. Prominence sub-component tests
# =========================================================================


class TestProminenceSubComponents:
    """Known obs/confidence/recency/recall produce expected prominence."""

    def test_confidence_mapping(self):
        """Confidence level -> numeric value mapping."""
        engine = RankingEngine(_default_ranking_config())
        assert engine._confidence_value("high") == 1.0
        assert abs(engine._confidence_value("medium") - 2 / 3) < 1e-12
        assert abs(engine._confidence_value("low") - 1 / 3) < 1e-12
        # Unknown defaults to medium
        assert abs(engine._confidence_value("unknown") - 2 / 3) < 1e-12

    def test_recency_decay_updated_today(self):
        """Updated now -> recency = 1.0."""
        engine = RankingEngine(_default_ranking_config())
        assert engine._recency_decay(_NOW_ISO, _NOW) == 1.0

    def test_recency_decay_30_days_ago(self):
        """Updated 30 days ago -> recency = 0.5."""
        engine = RankingEngine(_default_ranking_config())
        old = (_NOW - timedelta(days=30)).isoformat()
        assert engine._recency_decay(old, _NOW) == 0.5

    def test_recency_decay_60_days_ago(self):
        """Updated 60 days ago -> recency = 1/3."""
        engine = RankingEngine(_default_ranking_config())
        old = (_NOW - timedelta(days=60)).isoformat()
        result = engine._recency_decay(old, _NOW)
        assert abs(result - 1 / 3) < 1e-9

    def test_recall_frequency_zero(self):
        engine = RankingEngine(_default_ranking_config())
        assert engine._recall_frequency(0) == 0.0

    def test_recall_frequency_five(self):
        engine = RankingEngine(_default_ranking_config())
        assert engine._recall_frequency(5) == 0.5

    def test_recall_frequency_caps_at_one(self):
        engine = RankingEngine(_default_ranking_config())
        assert engine._recall_frequency(10) == 1.0
        assert engine._recall_frequency(20) == 1.0

    def test_prominence_formula_known_values(self):
        """Verify prominence = 0.3*norm_obs + 0.2*confidence + 0.3*recency + 0.2*recall."""
        engine = RankingEngine(_default_ranking_config())

        entry = {
            "observation_count": 10,
            "confidence": "high",
            "recall_count": 10,
            "updated_at": _NOW_ISO,
        }
        max_obs = 10

        # norm_obs = 10/10 = 1.0
        # confidence = 1.0
        # recency = 1.0 (updated now)
        # recall = min(10/10, 1.0) = 1.0
        # prominence = 0.3*1.0 + 0.2*1.0 + 0.3*1.0 + 0.2*1.0 = 1.0
        prominence = engine._prominence(entry, max_obs, _NOW)
        assert abs(prominence - 1.0) < 1e-9

    def test_prominence_formula_mixed_values(self):
        """Prominence with partial values produces expected result."""
        engine = RankingEngine(_default_ranking_config())

        entry = {
            "observation_count": 5,
            "confidence": "low",
            "recall_count": 0,
            "updated_at": (_NOW - timedelta(days=30)).isoformat(),
        }
        max_obs = 10

        # norm_obs = 5/10 = 0.5
        # confidence = 1/3
        # recency = 0.5
        # recall = 0.0
        # prominence = 0.3*0.5 + 0.2*(1/3) + 0.3*0.5 + 0.2*0.0
        expected = 0.3 * 0.5 + 0.2 * (1 / 3) + 0.3 * 0.5 + 0.2 * 0.0
        prominence = engine._prominence(entry, max_obs, _NOW)
        assert abs(prominence - expected) < 1e-9

    def test_prominence_zero_max_obs_means_zero_norm_obs(self):
        """When max_obs is 0, norm_obs should be 0 for all entries."""
        engine = RankingEngine(_default_ranking_config())

        entry = {
            "observation_count": 0,
            "confidence": "medium",
            "recall_count": 5,
            "updated_at": _NOW_ISO,
        }
        max_obs = 0

        # norm_obs = 0.0 (max_obs is 0)
        # confidence = 2/3
        # recency = 1.0
        # recall = 0.5
        # prominence = 0.3*0.0 + 0.2*(2/3) + 0.3*1.0 + 0.2*0.5
        expected = 0.0 + 0.2 * (2 / 3) + 0.3 * 1.0 + 0.2 * 0.5
        prominence = engine._prominence(entry, max_obs, _NOW)
        assert abs(prominence - expected) < 1e-9

    def test_prominence_uses_global_max_obs(self):
        """norm_obs should be computed against global max_obs across ALL entries."""
        engine = RankingEngine(_default_ranking_config())

        # Entry with obs_count=2, but max_obs=10 (from another entry)
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
        ranked = engine.rank(result, entries, limit=10, now=_NOW)

        # norm_obs for "a" should be 2/10 = 0.2 (global max is 10, not 2)
        assert len(ranked) == 1
        # Verify the score uses global max_obs by checking it differs from
        # a scenario where only entry_a exists
        result2 = RetrievalResult(
            candidates={
                "a": CandidateScores(vector_score=0.5, bm25_score=5.0),
            },
            vector_candidate_count=1,
            fts5_candidate_count=1,
        )
        ranked2 = engine.rank(result2, {"a": entry_a}, limit=10, now=_NOW)
        # With only entry_a, norm_obs = 2/2 = 1.0 (higher prominence)
        # So ranked2 score should be higher than ranked score
        assert ranked2[0]["final_score"] > ranked[0]["final_score"]
