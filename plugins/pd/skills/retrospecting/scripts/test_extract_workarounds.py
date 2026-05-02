"""Tests for FR-3 extract_workarounds (feature 102)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from extract_workarounds import extract_workarounds


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "workaround-fixture.md"


def test_fixture_extraction_returns_one_candidate():
    """AC-3.2: synthetic fixture with 1 decision-followed-by-2-failures block produces exactly 1 candidate."""
    log_text = FIXTURE_PATH.read_text()
    result = extract_workarounds(log_text, {"specify": 3})
    assert len(result) == 1
    candidate = result[0]
    assert candidate["category"] == "heuristics"
    assert candidate["confidence"] == "low"
    assert "name" in candidate
    assert len(candidate["name"]) <= 60


def test_empty_log_returns_empty_list():
    """AC-3.3: empty log_text → []."""
    assert extract_workarounds("", {"specify": 3}) == []


def test_missing_phase_iterations_returns_empty_list():
    """AC-3.3: empty phase_iterations → []."""
    log_text = FIXTURE_PATH.read_text()
    assert extract_workarounds(log_text, {}) == []


def test_low_iterations_returns_empty_list():
    """No phase shows iterations >= 3 → []."""
    log_text = FIXTURE_PATH.read_text()
    assert extract_workarounds(log_text, {"specify": 2}) == []


def test_control_block_not_extracted():
    """The control block (decision without ≥2 failures) is NOT extracted."""
    log_text = FIXTURE_PATH.read_text()
    result = extract_workarounds(log_text, {"specify": 3})
    # Only the positive block extracts
    assert len(result) == 1
    # Description should reference the positive block's content (ISO timestamp parsing)
    assert "iso" in result[0]["description"].lower() or "datetime" in result[0]["description"].lower() or "decision" in result[0]["description"].lower()


def test_returns_dict_with_required_keys():
    """Each candidate has the required keys."""
    log_text = FIXTURE_PATH.read_text()
    result = extract_workarounds(log_text, {"design": 3})
    for c in result:
        assert "name" in c
        assert "description" in c
        assert "category" in c
        assert "confidence" in c
        assert "reasoning" in c
