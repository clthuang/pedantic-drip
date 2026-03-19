"""Tests for semantic_memory.keywords module."""
from __future__ import annotations

import pytest

from semantic_memory.keywords import (
    KEYWORD_PROMPT,
    STOPWORD_LIST,
    KeywordGenerator,
    SkipKeywordGenerator,
    TieredKeywordGenerator,
)


# ---------------------------------------------------------------------------
# STOPWORD_LIST tests
# ---------------------------------------------------------------------------


class TestStopwordList:
    def test_contains_required_words(self):
        expected = [
            "code", "development", "software", "system", "application",
            "implementation", "feature", "project", "function", "method",
            "file", "data", "error", "bug", "fix", "update", "change",
        ]
        for word in expected:
            assert word in STOPWORD_LIST, f"Missing stopword: {word}"

    def test_is_list_of_strings(self):
        assert isinstance(STOPWORD_LIST, list)
        assert all(isinstance(w, str) for w in STOPWORD_LIST)

    def test_length_matches_spec(self):
        assert len(STOPWORD_LIST) == 17


# ---------------------------------------------------------------------------
# KEYWORD_PROMPT tests
# ---------------------------------------------------------------------------


class TestKeywordPrompt:
    def test_contains_placeholders(self):
        assert "{name}" in KEYWORD_PROMPT
        assert "{description}" in KEYWORD_PROMPT
        assert "{reasoning}" in KEYWORD_PROMPT
        assert "{category}" in KEYWORD_PROMPT

    def test_contains_json_array_instruction(self):
        assert "JSON array" in KEYWORD_PROMPT

    def test_contains_example(self):
        assert '["fts5"' in KEYWORD_PROMPT

    def test_contains_min_max(self):
        assert "Minimum 3" in KEYWORD_PROMPT
        assert "maximum 10" in KEYWORD_PROMPT


# ---------------------------------------------------------------------------
# KeywordGenerator Protocol tests
# ---------------------------------------------------------------------------


class TestKeywordGeneratorProtocol:
    def test_skip_generator_satisfies_protocol(self):
        gen = SkipKeywordGenerator()
        assert isinstance(gen, KeywordGenerator)


# ---------------------------------------------------------------------------
# SkipKeywordGenerator tests
# ---------------------------------------------------------------------------


class TestSkipKeywordGenerator:
    def test_returns_empty_list(self):
        gen = SkipKeywordGenerator()
        result = gen.generate(
            name="Test",
            description="A test entry",
            reasoning="Because testing",
            category="patterns",
        )
        assert result == []

    def test_always_returns_empty_list(self):
        gen = SkipKeywordGenerator()
        for _ in range(5):
            assert gen.generate("x", "y", "z", "w") == []


# ---------------------------------------------------------------------------
# TieredKeywordGenerator — validation tests
# ---------------------------------------------------------------------------


class _FakeProvider:
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


class TestKeywordValidation:
    """Tests for TieredKeywordGenerator._validate_keyword method."""

    def _make_generator(self) -> TieredKeywordGenerator:
        config = {"memory_keyword_provider": "off"}
        return TieredKeywordGenerator(config)

    def test_valid_simple_keyword(self):
        gen = self._make_generator()
        assert gen._validate_keyword("sqlite") is True

    def test_valid_hyphenated_keyword(self):
        gen = self._make_generator()
        assert gen._validate_keyword("content-hash") is True

    def test_valid_numeric_keyword(self):
        gen = self._make_generator()
        assert gen._validate_keyword("fts5") is True

    def test_valid_all_numeric(self):
        gen = self._make_generator()
        assert gen._validate_keyword("404") is True

    def test_rejects_uppercase(self):
        gen = self._make_generator()
        assert gen._validate_keyword("SQLite") is False

    def test_rejects_spaces(self):
        gen = self._make_generator()
        assert gen._validate_keyword("content hash") is False

    def test_rejects_leading_hyphen(self):
        gen = self._make_generator()
        assert gen._validate_keyword("-sqlite") is False

    def test_rejects_underscores(self):
        gen = self._make_generator()
        assert gen._validate_keyword("content_hash") is False

    def test_rejects_special_chars(self):
        gen = self._make_generator()
        for bad in ['["fts5"]', '"keyword"', "key,word", "key[0]"]:
            assert gen._validate_keyword(bad) is False, f"Should reject: {bad}"

    def test_rejects_empty_string(self):
        gen = self._make_generator()
        assert gen._validate_keyword("") is False

    def test_rejects_stopword(self):
        gen = self._make_generator()
        assert gen._validate_keyword("code") is False
        assert gen._validate_keyword("development") is False
        assert gen._validate_keyword("system") is False

    def test_accepts_non_stopword(self):
        gen = self._make_generator()
        assert gen._validate_keyword("sqlite") is True
        assert gen._validate_keyword("parser-error") is True


# ---------------------------------------------------------------------------
# TieredKeywordGenerator — generate() pipeline tests
# ---------------------------------------------------------------------------


class TestTieredGenerate:
    """Tests for the full generate() pipeline using fake providers."""

    def _make_generator_with_fake(
        self, fake_response: list[str]
    ) -> TieredKeywordGenerator:
        config = {"memory_keyword_provider": "off"}
        gen = TieredKeywordGenerator(config)
        # Replace tiers with our fake provider
        gen._tiers = [_FakeProvider(fake_response)]
        return gen

    def test_valid_keywords_pass_through(self):
        gen = self._make_generator_with_fake(
            ["sqlite", "fts5", "content-hash"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["sqlite", "fts5", "content-hash"]

    def test_filters_invalid_keywords(self):
        gen = self._make_generator_with_fake(
            ["sqlite", "UPPERCASE", "content hash", "fts5", "parser"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["sqlite", "fts5", "parser"]

    def test_filters_stopwords(self):
        gen = self._make_generator_with_fake(
            ["sqlite", "code", "development", "fts5", "system", "parser"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["sqlite", "fts5", "parser"]

    def test_filters_json_artifacts(self):
        gen = self._make_generator_with_fake(
            ['["sqlite"', 'fts5"]', "content-hash", "parser", "regex"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["content-hash", "parser", "regex"]

    def test_caps_at_10_keywords(self):
        keywords = [f"kw{i}" for i in range(15)]
        gen = self._make_generator_with_fake(keywords)
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert len(result) == 10

    def test_returns_empty_if_fewer_than_3_valid(self):
        gen = self._make_generator_with_fake(["sqlite", "fts5"])
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == []

    def test_returns_empty_if_zero_valid(self):
        gen = self._make_generator_with_fake(
            ["CODE", "System", "content hash"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == []

    def test_exactly_3_valid_returns_them(self):
        gen = self._make_generator_with_fake(
            ["sqlite", "fts5", "content-hash"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert len(result) == 3

    def test_deduplicates_keywords(self):
        gen = self._make_generator_with_fake(
            ["sqlite", "sqlite", "fts5", "fts5", "parser"]
        )
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["sqlite", "fts5", "parser"]


# ---------------------------------------------------------------------------
# TieredKeywordGenerator — tier configuration tests
# ---------------------------------------------------------------------------


class TestTierConfiguration:
    """Tests for tier list construction based on config value."""

    def test_always_has_skip_generator(self):
        config = {"memory_keyword_provider": "off"}
        gen = TieredKeywordGenerator(config)
        assert len(gen._tiers) == 1
        assert isinstance(gen._tiers[0], SkipKeywordGenerator)

    def test_any_config_value_uses_skip(self):
        """All config values currently resolve to SkipKeywordGenerator."""
        for provider in ["auto", "claude", "haiku", "ollama", "off", "unknown"]:
            gen = TieredKeywordGenerator({"memory_keyword_provider": provider})
            assert len(gen._tiers) == 1
            assert isinstance(gen._tiers[0], SkipKeywordGenerator)

    def test_missing_config_uses_skip(self):
        gen = TieredKeywordGenerator({})
        assert len(gen._tiers) == 1
        assert isinstance(gen._tiers[0], SkipKeywordGenerator)


# ---------------------------------------------------------------------------
# TieredKeywordGenerator — tier fallback tests
# ---------------------------------------------------------------------------


class _FailingProvider:
    """A provider that always raises NotImplementedError."""

    def generate(self, name: str, description: str, reasoning: str, category: str) -> list[str]:
        raise NotImplementedError("Stub provider")


class TestTierFallback:
    """Tests that the generator falls through tiers on failure."""

    def test_falls_through_to_next_tier_on_error(self):
        config = {"memory_keyword_provider": "off"}
        gen = TieredKeywordGenerator(config)
        gen._tiers = [
            _FailingProvider(),
            _FakeProvider(["sqlite", "fts5", "parser"]),
        ]
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["sqlite", "fts5", "parser"]

    def test_falls_through_multiple_failures(self):
        config = {"memory_keyword_provider": "off"}
        gen = TieredKeywordGenerator(config)
        gen._tiers = [
            _FailingProvider(),
            _FailingProvider(),
            _FakeProvider(["sqlite", "fts5", "parser"]),
        ]
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == ["sqlite", "fts5", "parser"]

    def test_returns_empty_if_all_tiers_fail(self):
        config = {"memory_keyword_provider": "off"}
        gen = TieredKeywordGenerator(config)
        gen._tiers = [_FailingProvider(), _FailingProvider()]
        result = gen.generate("Test", "desc", "reasoning", "patterns")
        assert result == []
