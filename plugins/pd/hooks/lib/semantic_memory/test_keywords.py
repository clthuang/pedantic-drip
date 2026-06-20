"""Tests for tiered keyword extraction (keywords.py).

Covers Tier 1 regex/heuristic, Tier 2 LLM fallback, and the
extract_keywords orchestrator. Tests AC-1 and AC-2 from the spec.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from semantic_memory.keywords import (
    KEYWORD_PROMPT,
    _KEYWORD_RE,
    _STOPWORDS,
    _strip_code_fences,
    _tier1_extract,
    _tier2_extract,
    extract_keywords,
)


# ---------------------------------------------------------------------------
# Tier 1 tests
# ---------------------------------------------------------------------------


class TestTier1Extract:
    """Tests for _tier1_extract regex/heuristic extraction."""

    def test_technical_text_produces_keywords(self):
        """Tier 1 should extract >= 3 keywords from technical text."""
        text = (
            "Use grep to search source files for factual claims. "
            "Always verify codebase facts before artifact review. "
            "Check pytest output and sqlite queries carefully."
        )
        result = _tier1_extract(text)
        assert len(result) >= 3
        # Should contain domain-specific terms
        assert all(_KEYWORD_RE.match(kw) for kw in result)
        assert all(kw not in _STOPWORDS for kw in result)

    def test_pure_stopwords_returns_empty(self):
        """Tier 1 should return empty list when text is only stopwords."""
        text = "code development software system application implementation feature"
        result = _tier1_extract(text)
        assert result == []

    def test_hyphenated_terms_extracted(self):
        """Tier 1 should extract hyphenated multi-word terms from text."""
        text = "The content-hash and fts5-search are important for the pipeline."
        result = _tier1_extract(text)
        assert "content-hash" in result
        assert "fts5-search" in result

    def test_capitalized_sequences_become_hyphenated(self):
        """Consecutive capitalized words joined as hyphenated terms."""
        text = "the Entity Registry stores metadata for all components."
        result = _tier1_extract(text)
        assert "entity-registry" in result

    def test_deduplication(self):
        """Keywords should not contain duplicates."""
        text = "sqlite sqlite sqlite pytest pytest"
        result = _tier1_extract(text)
        assert len(result) == len(set(result))

    def test_limit_to_10(self):
        """At most 10 keywords returned."""
        text = " ".join(f"term{i}" for i in range(20))
        result = _tier1_extract(text)
        assert len(result) <= 10

    def test_all_lowercase(self):
        """All returned keywords are lowercase."""
        text = "SQLite PostgreSQL Docker Kubernetes React"
        result = _tier1_extract(text)
        assert all(kw == kw.lower() for kw in result)

    def test_filters_invalid_tokens(self):
        """Tokens not matching _KEYWORD_RE are excluded."""
        text = "the _private 123valid a! b@ c#"
        result = _tier1_extract(text)
        # "the" is too short but valid; "_private" starts with underscore
        assert "_private" not in result
        assert "123valid" in result

    def test_empty_text(self):
        """Empty text returns empty list."""
        assert _tier1_extract("") == []


# ---------------------------------------------------------------------------
# Tier 2 tests
# ---------------------------------------------------------------------------


class TestTier2Extract:
    """Tests for _tier2_extract LLM-based extraction."""

    def _make_mock_response(self, text: str) -> MagicMock:
        """Create a mock Gemini API response."""
        resp = MagicMock()
        resp.text = text
        return resp

    @patch("semantic_memory.keywords._get_genai_client")
    def test_mock_api_returns_keywords(self, mock_get_client):
        """Tier 2 should parse valid JSON array from API."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '["sqlite", "fts5", "content-hash"]'
        )
        mock_get_client.return_value = mock_client

        result = _tier2_extract("test", "desc", "reason", "pattern")
        assert result == ["sqlite", "fts5", "content-hash"]

    @patch("semantic_memory.keywords._get_genai_client")
    def test_strips_code_fences(self, mock_get_client):
        """Tier 2 should strip markdown code fences before parsing."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '```json\n["sqlite", "pytest"]\n```'
        )
        mock_get_client.return_value = mock_client

        result = _tier2_extract("test", "desc", "reason", "pattern")
        assert result == ["sqlite", "pytest"]

    @patch("semantic_memory.keywords._get_genai_client")
    def test_malformed_json_returns_empty(self, mock_get_client):
        """Tier 2 should return [] on malformed JSON."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            "not json at all"
        )
        mock_get_client.return_value = mock_client

        result = _tier2_extract("test", "desc", "reason", "pattern")
        assert result == []

    @patch("semantic_memory.keywords._get_genai_client")
    def test_stopwords_filtered(self, mock_get_client):
        """Tier 2 should filter out stopwords from API response."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '["sqlite", "code", "development", "pytest"]'
        )
        mock_get_client.return_value = mock_client

        result = _tier2_extract("test", "desc", "reason", "pattern")
        assert "code" not in result
        assert "development" not in result
        assert "sqlite" in result
        assert "pytest" in result

    @patch("semantic_memory.keywords._get_genai_client")
    def test_invalid_keywords_filtered(self, mock_get_client):
        """Tier 2 should filter out keywords not matching _KEYWORD_RE."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '["valid-kw", "_invalid", "also valid", 123]'
        )
        mock_get_client.return_value = mock_client

        result = _tier2_extract("test", "desc", "reason", "pattern")
        assert "valid-kw" in result
        assert "_invalid" not in result

    @patch("semantic_memory.keywords._get_genai_client")
    def test_api_failure_returns_empty(self, mock_get_client):
        """Tier 2 should return [] when API call raises."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("API down")
        mock_get_client.return_value = mock_client

        result = _tier2_extract("test", "desc", "reason", "pattern")
        assert result == []

    @patch("semantic_memory.keywords._get_genai_client")
    def test_no_client_returns_empty(self, mock_get_client):
        """Tier 2 should return [] when client is unavailable."""
        mock_get_client.return_value = None

        result = _tier2_extract("test", "desc", "reason", "pattern")
        assert result == []

    @patch("semantic_memory.keywords._get_genai_client")
    def test_non_array_response_returns_empty(self, mock_get_client):
        """Tier 2 should return [] when response is JSON but not an array."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '{"keywords": ["sqlite"]}'
        )
        mock_get_client.return_value = mock_client

        result = _tier2_extract("test", "desc", "reason", "pattern")
        assert result == []


# ---------------------------------------------------------------------------
# extract_keywords orchestrator tests
# ---------------------------------------------------------------------------


class TestExtractKeywords:
    """Tests for extract_keywords orchestrator."""

    def test_returns_tier1_when_sufficient(self):
        """When Tier 1 produces >= 3 keywords, Tier 2 should NOT be called."""
        with patch("semantic_memory.keywords._tier2_extract") as mock_t2:
            result = extract_keywords(
                name="SQLite FTS5 content-hash indexing",
                description="Use content-hash for FTS5 sqlite indexing with pytest",
                reasoning="Improves search ranking accuracy",
                category="pattern",
            )
            assert len(result) >= 3
            mock_t2.assert_not_called()

    @patch("semantic_memory.keywords._tier2_extract")
    def test_calls_tier2_when_insufficient(self, mock_t2):
        """When Tier 1 produces < 3 keywords, Tier 2 should be called."""
        mock_t2.return_value = ["sqlite", "fts5", "indexing"]

        result = extract_keywords(
            name="a",
            description="a",
            reasoning="a",
            category="pattern",
        )
        mock_t2.assert_called_once()
        assert len(result) >= 3

    @patch("semantic_memory.keywords._tier2_extract")
    def test_combines_tier1_and_tier2(self, mock_t2):
        """When Tier 1 < 3, results from both tiers are combined."""
        mock_t2.return_value = ["extra-kw1", "extra-kw2", "extra-kw3"]

        # "ab" alone is short but valid, giving Tier 1 exactly 1 keyword
        result = extract_keywords(
            name="pytest",
            description="",
            reasoning="",
            category="pattern",
        )
        mock_t2.assert_called_once()
        # Should contain Tier 1 result + Tier 2 results
        assert "pytest" in result
        assert "extra-kw1" in result

    @patch("semantic_memory.keywords._tier2_extract")
    def test_combined_deduplication(self, mock_t2):
        """Combined results are deduplicated."""
        mock_t2.return_value = ["pytest", "sqlite", "new-term"]

        result = extract_keywords(
            name="pytest sqlite",
            description="",
            reasoning="",
            category="pattern",
        )
        # pytest appears in both tiers but should only appear once
        assert result.count("pytest") == 1

    @patch("semantic_memory.keywords._tier2_extract")
    def test_combined_limited_to_10(self, mock_t2):
        """Combined results capped at 10."""
        mock_t2.return_value = [f"tier2-{i}" for i in range(15)]

        result = extract_keywords(
            name="one",
            description="",
            reasoning="",
            category="pattern",
        )
        assert len(result) <= 10


# ---------------------------------------------------------------------------
# Acceptance criteria tests
# ---------------------------------------------------------------------------


class TestAcceptanceCriteria:
    """Tests verifying spec acceptance criteria."""

    def test_ac1_domain_specific_extraction(self):
        """AC-1: extract_keywords returns >= 3 domain-specific keywords
        for an entry about verifying codebase facts.
        """
        result = extract_keywords(
            name="Verify codebase facts before artifact review",
            description=(
                "When reviewing artifacts, grep source files to verify "
                "factual claims. Check imports, function signatures, and "
                "module structure rather than trusting descriptions."
            ),
            reasoning=(
                "Prevents hallucinated references. Grep and ast-based "
                "verification catches misattributed code patterns."
            ),
            category="pattern",
        )
        assert len(result) >= 3
        # All should be valid keywords
        for kw in result:
            assert _KEYWORD_RE.match(kw), f"Invalid keyword: {kw}"
            assert kw not in _STOPWORDS, f"Stopword not filtered: {kw}"

    def test_ac2_tier1_handles_representative_entries(self):
        """AC-2: Tier 1 produces >= 3 keywords for at least 7 of 10
        representative entries (no API calls needed).
        """
        entries = [
            "SQLite write contention causes WAL checkpoint stalls",
            "FTS5 BM25 scoring with content-hash triggers needs careful indexing",
            "Entity Registry backfill scans use batch INSERT for performance",
            "Python venv activation in MCP server bootstrap scripts",
            "Frontmatter YAML sync must preserve existing manual edits",
            "Semantic Memory embedding provider graceful degradation pattern",
            "Hook subprocess stderr suppression prevents JSON output corruption",
            "Git branch cleanup after retrospective preserves context",
            "Transition Gate phase validation uses frozen dataclass constants",
            "Workflow Engine reconciliation detects drift between meta-json and database",
        ]
        successes = 0
        for entry in entries:
            result = _tier1_extract(entry)
            if len(result) >= 3:
                successes += 1

        assert successes >= 7, (
            f"Only {successes}/10 entries produced >= 3 Tier 1 keywords"
        )


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestStripCodeFences:
    """Tests for _strip_code_fences helper."""

    def test_strips_json_fence(self):
        assert _strip_code_fences('```json\n["a"]\n```') == '["a"]'

    def test_strips_plain_fence(self):
        assert _strip_code_fences('```\n["a"]\n```') == '["a"]'

    def test_no_fences_unchanged(self):
        assert _strip_code_fences('["a"]') == '["a"]'

    def test_strips_whitespace(self):
        assert _strip_code_fences('  ["a"]  ') == '["a"]'


class TestConstants:
    """Verify constants match spec FR-1."""

    def test_keyword_re(self):
        assert _KEYWORD_RE.match("sqlite")
        assert _KEYWORD_RE.match("content-hash")
        assert _KEYWORD_RE.match("123valid")
        assert not _KEYWORD_RE.match("_private")
        assert not _KEYWORD_RE.match("-leading")
        assert not _KEYWORD_RE.match("")

    def test_stopwords_contains_expected_terms(self):
        assert "code" in _STOPWORDS
        assert "development" in _STOPWORDS
        assert "change" in _STOPWORDS

    def test_keyword_prompt_has_placeholders(self):
        assert "{name}" in KEYWORD_PROMPT
        assert "{description}" in KEYWORD_PROMPT
        assert "{reasoning}" in KEYWORD_PROMPT
        assert "{category}" in KEYWORD_PROMPT


# ---------------------------------------------------------------------------
# Backfill tests (Tasks 3.1.1 / 3.1.2, AC-5)
# ---------------------------------------------------------------------------


class TestBackfillKeywords:
    """Tests for _backfill_keywords and CLI dispatch."""

    def _make_db(self, tmp_path):
        """Create a MemoryDatabase with auto-migrations."""
        from semantic_memory.database import MemoryDatabase

        db = MemoryDatabase(str(tmp_path / "memory.db"))
        return db

    def _insert_entry(self, db, entry_id, name, description, keywords="[]",
                      reasoning="", category="patterns"):
        """Insert a minimal test entry directly."""
        import uuid as _uuid

        db._conn.execute(
            """INSERT OR IGNORE INTO entries
               (id, name, description, reasoning, category, keywords,
                source, source_project, confidence, created_at, updated_at,
                source_hash, created_timestamp_utc)
               VALUES (?, ?, ?, ?, ?, ?, 'manual', 'test', 'medium',
                       '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z',
                       ?, 1704067200.0)""",
            (entry_id, name, description, reasoning, category, keywords,
             entry_id),
        )
        db._conn.commit()

    def test_backfill_processes_empty_keyword_entries(self, tmp_path):
        """Backfill should extract keywords for entries with keywords='[]'."""
        from semantic_memory.writer import _backfill_keywords

        db = self._make_db(tmp_path)
        self._insert_entry(db, "e1", "SQLite FTS5 indexing patterns",
                           "Use FTS5 for full-text search in sqlite databases")

        entry_before = db.get_entry("e1")
        assert entry_before["keywords"] == "[]"

        _backfill_keywords(db, {})

        entry_after = db.get_entry("e1")
        kws = json.loads(entry_after["keywords"])
        assert len(kws) >= 1  # Should have extracted keywords
        assert entry_after["keywords"] != "[]"
        db.close()

    def test_backfill_skips_entries_with_existing_keywords(self, tmp_path):
        """Backfill should not modify entries that already have keywords."""
        from semantic_memory.writer import _backfill_keywords

        db = self._make_db(tmp_path)
        existing_kws = '["sqlite", "fts5", "indexing"]'
        self._insert_entry(db, "e1", "test entry", "some desc",
                           keywords=existing_kws)

        _backfill_keywords(db, {})

        entry_after = db.get_entry("e1")
        assert entry_after["keywords"] == existing_kws
        db.close()

    def test_backfill_continues_on_per_entry_failure(self, tmp_path):
        """Backfill should skip failing entries and continue with the rest."""
        from semantic_memory.writer import _backfill_keywords

        db = self._make_db(tmp_path)
        self._insert_entry(db, "e1", "SQLite FTS5 content-hash patterns",
                           "FTS5 sqlite content-hash indexing")
        self._insert_entry(db, "e2", "pytest fixture patterns",
                           "Use pytest fixtures for database testing")

        # Patch extract_keywords to fail on first call, succeed on second
        call_count = 0

        def flaky_extract(name, desc, reasoning, category, config=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated failure")
            return ["pytest", "fixtures", "testing"]

        with patch("semantic_memory.writer.extract_keywords", side_effect=flaky_extract):
            _backfill_keywords(db, {})

        # First entry should still be empty (failed), second should be populated
        e1 = db.get_entry("e1")
        e2 = db.get_entry("e2")
        assert e1["keywords"] == "[]"
        assert json.loads(e2["keywords"]) == ["pytest", "fixtures", "testing"]
        db.close()

    def test_cli_dispatch_routes_to_backfill(self, tmp_path):
        """main() with --action backfill-keywords should call _backfill_keywords."""
        from semantic_memory.writer import main

        db_dir = tmp_path / "store"
        db_dir.mkdir()
        # Create a DB so the action has something to open
        db = self._make_db(db_dir)
        db.close()

        with patch("semantic_memory.writer._backfill_keywords") as mock_bf:
            with pytest.raises(SystemExit) as exc_info:
                with patch(
                    "sys.argv",
                    ["writer", "--action", "backfill-keywords",
                     "--global-store", str(db_dir)],
                ):
                    main()
            assert exc_info.value.code == 0
            mock_bf.assert_called_once()

    def test_ac5_backfill_keywords_processes_empty(self, tmp_path):
        """AC-5: backfill-keywords processes entries with empty keywords."""
        from semantic_memory.writer import _backfill_keywords

        db = self._make_db(tmp_path)
        # Insert multiple entries with empty keywords
        self._insert_entry(db, "a1",
                           "Hook subprocess stderr suppression",
                           "Always suppress stderr in hook subprocess calls to prevent JSON corruption")
        self._insert_entry(db, "a2",
                           "Git branch cleanup after retrospective",
                           "Run retrospective before deleting branch so context is available")
        self._insert_entry(db, "a3",
                           "Entity Registry batch INSERT performance",
                           "Use register_entities_batch for bulk entity registration in sqlite")

        _backfill_keywords(db, {})

        for eid in ("a1", "a2", "a3"):
            entry = db.get_entry(eid)
            kws = json.loads(entry["keywords"])
            assert len(kws) >= 1, f"Entry {eid} should have keywords after backfill"
            assert entry["keywords"] != "[]"
        db.close()
