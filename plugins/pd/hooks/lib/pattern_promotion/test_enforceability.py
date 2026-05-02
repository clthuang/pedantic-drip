"""Tests for FR-5 enforceability filter (feature 102)."""
from __future__ import annotations

import pytest

from pattern_promotion.enforceability import score_enforceability


class TestStrongMarkers:
    """AC-5.2: strong markers each contribute 2 to score."""

    def test_must(self):
        score, markers = score_enforceability("must validate input")
        assert score == 2
        assert "must" in markers

    def test_never(self):
        score, _ = score_enforceability("never use eval")
        assert score == 2

    def test_always(self):
        score, _ = score_enforceability("always log errors")
        assert score == 2

    def test_dont(self):
        score, _ = score_enforceability("don't trust external input")
        assert score == 2

    def test_do_not(self):
        score, _ = score_enforceability("do not commit secrets")
        assert score == 2

    def test_required(self):
        score, _ = score_enforceability("explicit type hints are required")
        assert score == 2

    def test_prohibited(self):
        score, _ = score_enforceability("nested transactions are prohibited")
        assert score == 2

    def test_mandatory(self):
        score, _ = score_enforceability("ISO-8601 timestamps are mandatory")
        assert score == 2


class TestSoftMarkers:
    """AC-5.3: soft markers each contribute 1 to score."""

    def test_should(self):
        score, _ = score_enforceability("should prefer composition")
        assert score == 2  # should + prefer = 1 + 1

    def test_avoid(self):
        score, _ = score_enforceability("avoid global state")
        assert score == 1

    def test_prefer(self):
        score, _ = score_enforceability("prefer pure functions")
        assert score == 1

    def test_ensure(self):
        score, _ = score_enforceability("ensure idempotency")
        assert score == 1


class TestZeroMarkers:
    """AC-5.4: zero markers → (0, [])."""

    def test_empty_string(self):
        assert score_enforceability("") == (0, [])

    def test_descriptive_text(self):
        score, markers = score_enforceability("Heavy upfront review investment reduces iterations")
        assert score == 0
        assert markers == []


class TestCaseInsensitive:
    def test_uppercase_must(self):
        score, _ = score_enforceability("MUST validate")
        assert score == 2

    def test_mixed_case_dont(self):
        score, _ = score_enforceability("Don't ignore errors")
        assert score == 2


class TestAdditive:
    """Score is additive across multiple markers."""

    def test_two_strong(self):
        score, markers = score_enforceability("must always validate")
        assert score == 4
        assert "must" in markers and "always" in markers

    def test_strong_plus_soft(self):
        score, _ = score_enforceability("must avoid eval")
        assert score == 3  # must=2 + avoid=1


class TestReturnType:
    def test_returns_tuple(self):
        result = score_enforceability("must")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_score_is_int(self):
        score, _ = score_enforceability("must")
        assert isinstance(score, int)

    def test_markers_is_list(self):
        _, markers = score_enforceability("must")
        assert isinstance(markers, list)
