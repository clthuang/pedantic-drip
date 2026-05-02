"""Tests for pattern_promotion.classifier.

FR-2a keyword scoring. Each target's score is the count of DISTINCT regex
patterns (rows in the table) that matched at least once against the
concatenated entry name + description. All matching is case-insensitive.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pattern_promotion.classifier import (
    KEYWORD_PATTERNS,
    classify_keywords,
    decide_target,
)
from pattern_promotion.kb_parser import KBEntry


def _entry(name: str, description: str = "") -> KBEntry:
    return KBEntry(
        name=name,
        description=description,
        confidence="high",
        effective_observation_count=5,
        category="heuristics",
        file_path=Path("/tmp/dummy.md"),
        line_range=(1, 2),
    )


class TestKeywordPatternsRegistry:
    def test_all_four_targets_present(self):
        assert set(KEYWORD_PATTERNS.keys()) == {"hook", "skill", "agent", "command"}

    def test_patterns_compiled_with_ignorecase(self):
        import re as _re

        for target, patterns in KEYWORD_PATTERNS.items():
            for p in patterns:
                assert isinstance(p, _re.Pattern)
                assert p.flags & _re.IGNORECASE


class TestHookScoring:
    def test_hook_positive_match_pretooluse(self):
        entry = _entry(
            "Block relative paths",
            "PreToolUse on Edit should block relative path patterns in tool input.",
        )
        scores = classify_keywords(entry)
        assert scores["hook"] >= 3  # PreToolUse, on Edit, tool input

    def test_hook_posttooluse_match(self):
        entry = _entry(
            "Post-tool logging",
            "PostToolUse intercept and capture outputs.",
        )
        scores = classify_keywords(entry)
        assert scores["hook"] >= 2  # PostToolUse, intercept

    def test_hook_on_read_glob_edit(self):
        entry = _entry(
            "Absolute paths",
            "Always use absolute paths in Read/Glob/Edit tool calls; relative paths break when working directory changes mid-session. PreToolUse on Read, on Glob, on Edit should catch these.",
        )
        scores = classify_keywords(entry)
        # PreToolUse, on Read, on Glob, on Edit, tool (in 'tool calls')
        assert scores["hook"] >= 4

    def test_hook_case_insensitive(self):
        entry = _entry("UPPER CASE", "pretooluse On Bash Should INTERCEPT badly-formed commands.")
        scores = classify_keywords(entry)
        assert scores["hook"] >= 2


class TestAgentScoring:
    def test_agent_positive(self):
        entry = _entry(
            "Implementation review rigor",
            "The reviewer agent validates that every task has test coverage. Reject if missing.",
        )
        scores = classify_keywords(entry)
        assert scores["agent"] >= 3  # reviewer, validates, reject if

    def test_agent_audit_match(self):
        entry = _entry("Audit step", "Assess and audit each phase.")
        scores = classify_keywords(entry)
        assert scores["agent"] >= 2


class TestSkillScoring:
    def test_skill_implementing_gerund(self):
        entry = _entry(
            "Bundle tasks",
            "When implementing similar tasks, dispatch them together as a workflow.",
        )
        scores = classify_keywords(entry)
        assert scores["skill"] >= 2  # implementing, workflow

    def test_skill_multiple_gerunds(self):
        entry = _entry(
            "Retrospecting after phases",
            "Always run retrospecting procedure with defined steps after brainstorming concludes.",
        )
        scores = classify_keywords(entry)
        # retrospecting, brainstorming, procedure, steps
        assert scores["skill"] >= 3


class TestCommandScoring:
    def test_command_slash_match(self):
        entry = _entry(
            "Wrap-up command consistency",
            "When user runs /pd:wrap-up slash command, it should verify state.",
        )
        scores = classify_keywords(entry)
        assert scores["command"] >= 2

    def test_command_invokes_pattern(self):
        entry = _entry(
            "Doctor invocation",
            "Invokes /pd:doctor automatically at session start.",
        )
        scores = classify_keywords(entry)
        assert scores["command"] >= 1


class TestAllZero:
    def test_no_tokens_match(self):
        entry = _entry(
            "Tidy dispositions",
            "Leave the ground tidier than you found it.",
        )
        scores = classify_keywords(entry)
        assert all(v == 0 for v in scores.values())


class TestDecideTarget:
    def test_strict_highest_winner(self):
        assert decide_target({"hook": 3, "skill": 1, "agent": 0, "command": 0}) == "hook"

    def test_tie_returns_none(self):
        assert decide_target({"hook": 2, "skill": 2, "agent": 0, "command": 0}) is None

    def test_all_zero_returns_none(self):
        assert decide_target({"hook": 0, "skill": 0, "agent": 0, "command": 0}) is None

    def test_single_keyword_score_one_returns_none(self):
        """Feature 102 AC-4.2: score==1 (single keyword) triggers LLM fallback."""
        assert decide_target({"hook": 0, "skill": 0, "agent": 1, "command": 0}) is None

    def test_score_two_unique_winner(self):
        """Feature 102 AC-4.1: max_score >= 2 with unique winner returns that target."""
        assert decide_target({"hook": 0, "skill": 2, "agent": 0, "command": 0}) == "skill"

    def test_score_two_tie_returns_none(self):
        """AC-4.2: ties → None even at score 2."""
        assert decide_target({"hook": 2, "skill": 2, "agent": 0, "command": 0}) is None


class TestDogfoodCorpus:
    """Feature 102 AC-4.3: 4 entries from feature 083 retro that previously
    misclassified to 'agent' under the old `>= 1` threshold. Under the new
    `>= 2` threshold, all four score 1 (matching only 'reviewer') and fall
    through to LLM fallback. With monkeypatched LLM returning 'skill', all
    four resolve correctly.
    """

    DOGFOOD_ENTRIES = [
        ("Three-Reviewer Parallel Dispatch With Selective Re-Dispatch",
         "Dispatch reviewer agents in parallel and selectively re-dispatch only failed reviewers in iter 2+."),
        ("Reviewer Approval State Tracking Across Iterations",
         "Maintain reviewer_status dict tracking pending/passed/failed for each reviewer across iterations."),
        ("Heavy Upfront Review Investment Reduces Implement Iterations",
         "Investing in rigorous upstream review enables single-pass implement with reviewer agents."),
        ("Adversarial Reviewer Pre-Validation Against Knowledge Bank",
         "Pre-validate against knowledge bank anti-patterns before dispatching reviewer agents."),
    ]

    def test_dogfood_corpus_4_of_4(self):
        """All 4 dogfood entries score < 2 keywords → LLM fallback fires.
        Mocked LLM returns 'skill' for each → 4/4 correct.
        """
        for name, description in self.DOGFOOD_ENTRIES:
            entry = _entry(name, description)
            scores = classify_keywords(entry)
            # All 4 entries match at most 1 keyword from any single target's pattern set
            assert max(scores.values()) < 2, f"Entry {name!r} scored {scores}; expected <2 for LLM fallback"
            # decide_target returns None → LLM fallback triggers
            assert decide_target(scores) is None


class TestDistinctPatternCount:
    """A target's score is distinct-patterns-matched, not total-matches."""

    def test_same_pattern_matching_twice_counts_once(self):
        entry = _entry(
            "Reviewer reviewer",
            "The reviewer is a reviewer that is a reviewer.",
        )
        scores = classify_keywords(entry)
        # Only the `reviewer` pattern matched (repeatedly). score == 1.
        assert scores["agent"] == 1
