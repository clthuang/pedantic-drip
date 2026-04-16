"""Tests for pattern_promotion.kb_parser.

Per FR-1:
- below-threshold entries are excluded
- `- Promoted:` entries are excluded (idempotent re-runs)
- constitution.md is excluded entirely
- `Observation count: N` field is parsed when present
- distinct `Feature #NNN` lines are counted when field is absent
- line_range is captured for each entry
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pattern_promotion.kb_parser import (
    KBEntry,
    enumerate_qualifying_entries,
    mark_entry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HEURISTICS_MD = textwrap.dedent("""\
    # Heuristics

    ## Decision Heuristics

    ### High-Confidence Qualifying Heuristic
    A heuristic with explicit observation count above threshold.
    - Source: Feature #001
    - Confidence: high
    - Last observed: Feature #005
    - Observation count: 5

    ### Below Threshold Heuristic
    Has observation count below threshold.
    - Source: Feature #002
    - Confidence: high
    - Observation count: 1

    ### Already Promoted Heuristic
    Has explicit observation count above threshold but is marked promoted.
    - Source: Feature #003
    - Confidence: high
    - Observation count: 7
    - Promoted: skill:plugins/pd/skills/creating-tests/SKILL.md

    ### Feature Count Derived Heuristic
    No observation count field, use distinct Feature #NNN.
    - Used in: Feature #010
    - Used in: Feature #011
    - Used in: Feature #012
    - Used in: Feature #010
    - Confidence: high

    ### Medium Confidence Heuristic
    Confidence is explicitly not high — excluded by FR-1.
    - Confidence: medium
    - Observation count: 9
    """)

PATTERNS_MD = textwrap.dedent("""\
    # Patterns

    ## Development Patterns

    ### Pattern: Qualifying Pattern
    Patterns file has no explicit Confidence field; qualifies on count alone.
    - Used in: Feature #020
    - Used in: Feature #021
    - Used in: Feature #022

    ### Pattern: Below Threshold Pattern
    Only one feature observation.
    - Used in: Feature #030
    """)

ANTI_PATTERNS_MD = textwrap.dedent("""\
    # Anti-Patterns

    ## Known Anti-Patterns

    ### Anti-Pattern: Qualifying Anti-Pattern
    High confidence, above threshold.
    - Observed in: Feature #040
    - Confidence: high
    - Observation count: 4

    ### Anti-Pattern: Low Confidence
    - Confidence: low
    - Observation count: 8
    """)

CONSTITUTION_MD = textwrap.dedent("""\
    # Constitution

    ## Non-negotiable rules

    ### Constitution: Should Be Excluded
    This entry is excluded regardless of threshold.
    - Confidence: high
    - Observation count: 99
    """)


@pytest.fixture
def kb_dir(tmp_path: Path) -> Path:
    d = tmp_path / "knowledge-bank"
    d.mkdir()
    (d / "heuristics.md").write_text(HEURISTICS_MD)
    (d / "patterns.md").write_text(PATTERNS_MD)
    (d / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
    (d / "constitution.md").write_text(CONSTITUTION_MD)
    return d


# ---------------------------------------------------------------------------
# enumerate_qualifying_entries
# ---------------------------------------------------------------------------


class TestEnumerate:
    def test_threshold_excludes_below(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        names = [e.name for e in entries]
        assert "Below Threshold Heuristic" not in names
        assert "Pattern: Below Threshold Pattern" not in names

    def test_promoted_marker_excludes(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        names = [e.name for e in entries]
        assert "Already Promoted Heuristic" not in names

    def test_constitution_excluded(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        names = [e.name for e in entries]
        assert "Constitution: Should Be Excluded" not in names
        assert not any(e.category == "constitution" for e in entries)

    def test_observation_count_field_parsed(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        qualifying = next(
            e for e in entries if e.name == "High-Confidence Qualifying Heuristic"
        )
        assert qualifying.effective_observation_count == 5
        assert qualifying.confidence == "high"

    def test_distinct_feature_count_when_field_absent(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        derived = next(
            e for e in entries if e.name == "Feature Count Derived Heuristic"
        )
        # 3 distinct features (#010 appears twice but dedupes)
        assert derived.effective_observation_count == 3

    def test_line_range_captured(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        qualifying = next(
            e for e in entries if e.name == "High-Confidence Qualifying Heuristic"
        )
        start, end = qualifying.line_range
        assert start > 0
        assert end >= start
        # Read the file and verify the header at start line
        lines = (kb_dir / "heuristics.md").read_text().splitlines()
        assert lines[start - 1].startswith("### High-Confidence Qualifying Heuristic")

    def test_patterns_file_no_confidence_field_eligible_on_count(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        names = [e.name for e in entries]
        assert "Pattern: Qualifying Pattern" in names

    def test_medium_confidence_excluded_for_heuristics(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        names = [e.name for e in entries]
        assert "Medium Confidence Heuristic" not in names

    def test_low_confidence_excluded_for_anti_patterns(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        names = [e.name for e in entries]
        assert "Anti-Pattern: Low Confidence" not in names

    def test_anti_pattern_high_confidence_included(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        names = [e.name for e in entries]
        assert "Anti-Pattern: Qualifying Anti-Pattern" in names

    def test_kb_entry_fields_populated(self, kb_dir: Path):
        entries = enumerate_qualifying_entries(kb_dir, min_observations=3)
        for e in entries:
            assert isinstance(e, KBEntry)
            assert e.name
            assert e.description
            assert e.confidence in {"high", "medium", "low", "n/a"}
            assert e.category in {"heuristics", "patterns", "anti-patterns"}
            assert e.file_path.exists()
            assert e.effective_observation_count >= 3


# ---------------------------------------------------------------------------
# mark_entry
# ---------------------------------------------------------------------------


class TestMarkEntry:
    def test_insert_after_confidence_line(self, kb_dir: Path):
        path = kb_dir / "heuristics.md"
        mark_entry(
            path,
            entry_name="High-Confidence Qualifying Heuristic",
            target_type="skill",
            target_path="plugins/pd/skills/creating-tests/SKILL.md",
        )
        text = path.read_text()
        assert (
            "- Promoted: skill:plugins/pd/skills/creating-tests/SKILL.md" in text
        )
        # Marker should sit immediately after the `- Confidence:` line of that entry
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("### High-Confidence Qualifying Heuristic"):
                # Find the Confidence line within the block
                j = i + 1
                while j < len(lines) and not lines[j].startswith("### "):
                    if lines[j].startswith("- Confidence:"):
                        assert lines[j + 1].startswith("- Promoted:")
                        break
                    j += 1
                break

    def test_mark_at_eof_for_last_entry(self, tmp_path: Path):
        path = tmp_path / "only.md"
        path.write_text(textwrap.dedent("""\
            # File

            ## Heading

            ### Solo Entry
            No more entries after this one.
            - Used in: Feature #100
            - Used in: Feature #101
            - Used in: Feature #102
            """))
        mark_entry(
            path,
            entry_name="Solo Entry",
            target_type="hook",
            target_path="plugins/pd/hooks/check-x.sh",
        )
        text = path.read_text()
        assert "- Promoted: hook:plugins/pd/hooks/check-x.sh" in text

    def test_mark_before_next_sibling_when_no_confidence(self, tmp_path: Path):
        path = tmp_path / "siblings.md"
        path.write_text(textwrap.dedent("""\
            # File

            ## Group

            ### Entry A
            No confidence line here.
            - Used in: Feature #200
            - Used in: Feature #201
            - Used in: Feature #202

            ### Entry B
            The next sibling.
            - Used in: Feature #300
            """))
        mark_entry(
            path,
            entry_name="Entry A",
            target_type="agent",
            target_path="plugins/pd/agents/code-reviewer.md",
        )
        text = path.read_text()
        lines = text.splitlines()
        # Find Entry A's promoted line; verify it appears before "### Entry B"
        a_promoted = next(
            i for i, ln in enumerate(lines) if ln.startswith("- Promoted: agent:")
        )
        b_start = next(i for i, ln in enumerate(lines) if ln.startswith("### Entry B"))
        assert a_promoted < b_start
