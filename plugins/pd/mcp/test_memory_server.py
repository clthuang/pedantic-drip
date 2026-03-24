"""Tests for memory-server MCP tool functions.

Tests _process_store_memory() directly for fast, isolated verification
without needing a running MCP server.
"""
from __future__ import annotations

import json
import sys
import os

# Ensure semantic_memory package and mcp/ module are importable.
_test_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _test_hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _test_hooks_lib)
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pytest

from semantic_memory import content_hash
from semantic_memory.database import MemoryDatabase


# ---------------------------------------------------------------------------
# Import guard: ensure the module is importable (verifies MCP structure)
# ---------------------------------------------------------------------------


def test_memory_server_importable():
    """memory_server module should be importable and expose _process_store_memory."""
    import memory_server  # noqa: F401

    assert hasattr(memory_server, "_process_store_memory")
    assert hasattr(memory_server, "mcp")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Deterministic embedding provider for testing."""

    def __init__(self, dims: int = 768) -> None:
        self._dims = dims

    @property
    def dimensions(self) -> int:
        return self._dims

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-model"

    def embed(self, text: str, task_type: str = "query") -> np.ndarray:
        # Deterministic: hash the text into a repeatable float
        val = float(hash(text) % 1000) / 1000.0
        return np.full(self._dims, val, dtype=np.float32)

    def embed_batch(
        self, texts: list[str], task_type: str = "document"
    ) -> list[np.ndarray]:
        return [self.embed(t, task_type) for t in texts]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Provide an in-memory MemoryDatabase, closed after test."""
    database = MemoryDatabase(":memory:")
    yield database
    database.close()


# ---------------------------------------------------------------------------
# Import _process_store_memory for direct testing
# ---------------------------------------------------------------------------

from memory_server import _process_store_memory  # noqa: E402


# ---------------------------------------------------------------------------
# Test: valid store_memory
# ---------------------------------------------------------------------------


class TestValidStoreMemory:
    def test_creates_entry_with_correct_fields(self, db: MemoryDatabase):
        """A valid store should create an entry with all expected fields."""
        result = _process_store_memory(
            db=db,
            provider=None,
            name="Test pattern",
            description="Always validate inputs before processing",
            reasoning="Prevents runtime errors from bad data",
            category="patterns",
            references=["file.py:42"],
        )
        expected_hash = content_hash("Always validate inputs before processing")
        assert result == f"Stored: Test pattern (id: {expected_hash})"

        entry = db.get_entry(expected_hash)
        assert entry is not None
        assert entry["name"] == "Test pattern"
        assert entry["description"] == "Always validate inputs before processing"
        assert entry["reasoning"] == "Prevents runtime errors from bad data"
        assert entry["category"] == "patterns"
        assert entry["source"] == "session-capture"
        assert json.loads(entry["references"]) == ["file.py:42"]
        assert entry["observation_count"] == 1

    def test_source_is_session_capture(self, db: MemoryDatabase):
        """Source must be 'session-capture' per spec D6."""
        _process_store_memory(
            db=db,
            provider=None,
            name="Test",
            description="Source test",
            reasoning="Reason",
            category="patterns",
            references=[],
        )
        expected_hash = content_hash("Source test")
        entry = db.get_entry(expected_hash)
        assert entry["source"] == "session-capture"


# ---------------------------------------------------------------------------
# Test: validation errors
# ---------------------------------------------------------------------------


class TestValidationErrors:
    def test_invalid_category_returns_error(self, db: MemoryDatabase):
        """Invalid category should return an error string, not raise."""
        result = _process_store_memory(
            db=db,
            provider=None,
            name="Test",
            description="Desc",
            reasoning="Reason",
            category="invalid-cat",
            references=[],
        )
        assert "error" in result.lower() or "Error" in result
        assert db.count_entries() == 0

    def test_empty_name_returns_error(self, db: MemoryDatabase):
        result = _process_store_memory(
            db=db,
            provider=None,
            name="",
            description="Desc",
            reasoning="Reason",
            category="patterns",
            references=[],
        )
        assert "error" in result.lower() or "Error" in result
        assert db.count_entries() == 0

    def test_empty_description_returns_error(self, db: MemoryDatabase):
        result = _process_store_memory(
            db=db,
            provider=None,
            name="Test",
            description="",
            reasoning="Reason",
            category="patterns",
            references=[],
        )
        assert "error" in result.lower() or "Error" in result
        assert db.count_entries() == 0

    def test_empty_reasoning_returns_error(self, db: MemoryDatabase):
        result = _process_store_memory(
            db=db,
            provider=None,
            name="Test",
            description="Desc",
            reasoning="",
            category="patterns",
            references=[],
        )
        assert "error" in result.lower() or "Error" in result
        assert db.count_entries() == 0

    def test_whitespace_only_name_returns_error(self, db: MemoryDatabase):
        result = _process_store_memory(
            db=db,
            provider=None,
            name="   ",
            description="Desc",
            reasoning="Reason",
            category="patterns",
            references=[],
        )
        assert "error" in result.lower() or "Error" in result
        assert db.count_entries() == 0


# ---------------------------------------------------------------------------
# Test: duplicate entry (upsert)
# ---------------------------------------------------------------------------


class TestDuplicateEntry:
    def test_duplicate_increments_observation_count(self, db: MemoryDatabase):
        """Storing the same description twice should increment observation_count."""
        for _ in range(2):
            _process_store_memory(
                db=db,
                provider=None,
                    name="Dup pattern",
                description="Identical description for dedup test",
                reasoning="Reason",
                category="patterns",
                references=[],
            )
        expected_hash = content_hash("Identical description for dedup test")
        entry = db.get_entry(expected_hash)
        assert entry["observation_count"] == 2


# ---------------------------------------------------------------------------
# Test: confidence parameter
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_confidence_defaults_to_medium(self, db: MemoryDatabase):
        """When confidence kwarg is omitted, the DB DEFAULT 'medium' applies."""
        _process_store_memory(
            db=db,
            provider=None,
            name="test",
            description="test description for confidence default",
            reasoning="testing",
            category="heuristics",
            references=[],
        )
        expected_hash = content_hash("test description for confidence default")
        entry = db.get_entry(expected_hash)
        assert entry["confidence"] == "medium"

    def test_confidence_low_stored_correctly(self, db: MemoryDatabase):
        """Passing confidence='low' should persist that value."""
        _process_store_memory(
            db=db,
            provider=None,
            name="test",
            description="test description for low confidence",
            reasoning="testing",
            category="heuristics",
            references=[],
            confidence="low",
        )
        expected_hash = content_hash("test description for low confidence")
        entry = db.get_entry(expected_hash)
        assert entry["confidence"] == "low"

    def test_invalid_confidence_returns_error(self, db: MemoryDatabase):
        """Invalid confidence value should return an error, not store."""
        result = _process_store_memory(
            db=db,
            provider=None,
            name="test",
            description="test description for invalid confidence",
            reasoning="testing",
            category="heuristics",
            references=[],
            confidence="invalid",
        )
        assert "Error" in result
        expected_hash = content_hash("test description for invalid confidence")
        assert db.get_entry(expected_hash) is None

    def test_new_entry_with_confidence_returns_stored(self, db: MemoryDatabase):
        """A new entry with confidence='low' should return 'Stored:' prefix."""
        result = _process_store_memory(
            db=db,
            provider=None,
            name="test",
            description="test description for new entry confidence",
            reasoning="testing",
            category="heuristics",
            references=[],
            confidence="low",
        )
        assert result.startswith("Stored:")

    def test_duplicate_entry_returns_reinforced(self, db: MemoryDatabase):
        """Second store of same description should return 'Reinforced:' with count."""
        desc = "test description for duplicate reinforced"
        for _ in range(2):
            result = _process_store_memory(
                db=db,
                provider=None,
                    name="test",
                description=desc,
                reasoning="testing",
                category="heuristics",
                references=[],
                confidence="low",
            )
        assert result.startswith("Reinforced:")
        assert "observation" in result.lower()


# ---------------------------------------------------------------------------
# Test: keywords always stored as empty JSON
# ---------------------------------------------------------------------------


class TestKeywords:
    def test_keywords_stored_as_empty_json(self, db: MemoryDatabase):
        """Keywords should always be '[]' (keyword system removed)."""
        _process_store_memory(
            db=db,
            provider=None,
            name="No KW",
            description="No keyword gen test",
            reasoning="Reason",
            category="patterns",
            references=[],
        )
        expected_hash = content_hash("No keyword gen test")
        entry = db.get_entry(expected_hash)
        assert entry["keywords"] == "[]"


# ---------------------------------------------------------------------------
# Test: source_project
# ---------------------------------------------------------------------------


class TestSourceProject:
    def test_source_project_stored(self, db: MemoryDatabase):
        """store_memory should set source_project."""
        _process_store_memory(
            db=db,
            provider=None,
            name="SP test",
            description="Source project test",
            reasoning="For source project",
            category="patterns",
            references=[],
            source_project="/my/project",
        )
        expected_hash = content_hash("Source project test")
        entry = db.get_entry(expected_hash)
        assert entry["source_project"] == "/my/project"


# ---------------------------------------------------------------------------
# Test: source_hash
# ---------------------------------------------------------------------------


class TestSourceHash:
    def test_source_hash_stored(self, db: MemoryDatabase):
        """store_memory should set source_hash from description."""
        from semantic_memory import source_hash as sh_fn

        desc = "Source hash test description"
        _process_store_memory(
            db=db,
            provider=None,
            name="SH test",
            description=desc,
            reasoning="For source hash",
            category="patterns",
            references=[],
            source_project="/proj",
        )
        expected_content_hash = content_hash(desc)
        expected_source_hash = sh_fn(desc)
        entry = db.get_entry(expected_content_hash)
        assert entry["source_hash"] == expected_source_hash


# ---------------------------------------------------------------------------
# Test: embeddings
# ---------------------------------------------------------------------------


class TestEmbeddings:
    def test_embedding_generated_when_provider_available(self, db: MemoryDatabase):
        """Embedding should be stored when a provider is available."""
        provider = FakeEmbeddingProvider()
        _process_store_memory(
            db=db,
            provider=provider,
            name="Emb test",
            description="Embedding generation test",
            reasoning="For embedding",
            category="anti-patterns",
            references=[],
        )
        expected_hash = content_hash("Embedding generation test")
        entry = db.get_entry(expected_hash)
        assert entry["embedding"] is not None
        # Verify it's a valid float32 blob of correct size
        assert len(entry["embedding"]) == 768 * 4

    def test_no_provider_stores_without_embedding(self, db: MemoryDatabase):
        """Without a provider, entry should be stored with NULL embedding."""
        _process_store_memory(
            db=db,
            provider=None,
            name="No emb",
            description="No embedding test",
            reasoning="Reason",
            category="patterns",
            references=[],
        )
        expected_hash = content_hash("No embedding test")
        entry = db.get_entry(expected_hash)
        assert entry["embedding"] is None

    def test_embedding_text_includes_name_description_reasoning(self, db: MemoryDatabase):
        """Embedding should include name, description, and reasoning via _embed_text_for_entry."""
        call_log: list[str] = []

        class LoggingProvider(FakeEmbeddingProvider):
            def embed(self, text: str, task_type: str = "query") -> np.ndarray:
                call_log.append(text)
                return super().embed(text, task_type)

        provider = LoggingProvider()
        _process_store_memory(
            db=db,
            provider=provider,
            name="MyName",
            description="MyDescription",
            reasoning="Reason",
            category="patterns",
            references=[],
        )
        # The embed call should use _embed_text_for_entry which includes reasoning
        assert any("MyName" in c and "MyDescription" in c and "Reason" in c for c in call_log)


# ---------------------------------------------------------------------------
# Test: references
# ---------------------------------------------------------------------------


class TestReferences:
    def test_references_stored_as_json_array(self, db: MemoryDatabase):
        """References should be stored as a JSON array."""
        _process_store_memory(
            db=db,
            provider=None,
            name="Ref test",
            description="References test",
            reasoning="Reason",
            category="patterns",
            references=["file1.py:10", "file2.py:20"],
        )
        expected_hash = content_hash("References test")
        entry = db.get_entry(expected_hash)
        assert entry["references"] is not None
        refs = json.loads(entry["references"])
        assert refs == ["file1.py:10", "file2.py:20"]

    def test_empty_references_stored_as_empty_json_array(self, db: MemoryDatabase):
        """Empty references list should be stored as '[]'."""
        _process_store_memory(
            db=db,
            provider=None,
            name="Empty ref",
            description="Empty references test",
            reasoning="Reason",
            category="patterns",
            references=[],
        )
        expected_hash = content_hash("Empty references test")
        entry = db.get_entry(expected_hash)
        assert entry["references"] is not None
        assert json.loads(entry["references"]) == []


# ---------------------------------------------------------------------------
# Import _process_search_memory for direct testing
# ---------------------------------------------------------------------------

from memory_server import _process_search_memory  # noqa: E402


# ---------------------------------------------------------------------------
# Test: search_memory
# ---------------------------------------------------------------------------


class TestSearchMemory:
    def test_returns_matching_entries(self, db: MemoryDatabase):
        """Search should find relevant entries by keyword."""
        # Seed two entries
        _process_store_memory(
            db=db,
            provider=None,
            name="Hook patterns",
            description="Always suppress stderr in hook subprocesses to prevent JSON corruption",
            reasoning="Hooks output JSON and stderr corrupts the protocol",
            category="patterns",
            references=[],
        )
        _process_store_memory(
            db=db,
            provider=None,
            name="Testing heuristic",
            description="Run tests before committing to catch regressions early",
            reasoning="Prevents broken commits",
            category="heuristics",
            references=[],
        )

        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="hook stderr JSON",
            limit=10,
        )

        assert "Hook patterns" in result
        assert "Found" in result

    def test_empty_query_returns_error(self, db: MemoryDatabase):
        """Empty query should return an error."""
        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="",
            limit=10,
        )
        assert "Error" in result

    def test_whitespace_query_returns_error(self, db: MemoryDatabase):
        """Whitespace-only query should return an error."""
        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="   ",
            limit=10,
        )
        assert "Error" in result

    def test_no_entries_returns_no_matches(self, db: MemoryDatabase):
        """Empty DB should return 'no matching memories'."""
        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="anything",
            limit=10,
        )
        assert "No matching memories found" in result

    def test_limit_respected(self, db: MemoryDatabase):
        """Should respect the limit parameter."""
        # Seed many entries
        for i in range(10):
            _process_store_memory(
                db=db,
                provider=None,
                    name=f"Pattern {i}",
                description=f"Pattern description number {i} about testing workflows",
                reasoning=f"Reason {i}",
                category="patterns",
                references=[],
            )

        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="testing workflows",
            limit=3,
        )

        assert "Found 3" in result

    def test_includes_reasoning_and_confidence(self, db: MemoryDatabase):
        """Search results should include reasoning and confidence."""
        _process_store_memory(
            db=db,
            provider=None,
            name="Test entry",
            description="Always check permissions before file operations",
            reasoning="Prevents permission-denied errors at runtime",
            category="heuristics",
            references=[],
        )

        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="file permissions check",
            limit=10,
        )

        assert "Heuristic: Test entry" in result
        assert "Prevents permission-denied errors" in result
        assert "Confidence:" in result


# ---------------------------------------------------------------------------
# Test: store_memory MCP tool accepts confidence parameter (Task 1.4)
# ---------------------------------------------------------------------------

import inspect

from memory_server import store_memory  # noqa: E402


class TestStoreMemoryMCPToolConfidence:
    def test_store_memory_has_confidence_parameter(self):
        """The store_memory MCP tool must accept a 'confidence' parameter."""
        sig = inspect.signature(store_memory)
        assert "confidence" in sig.parameters, (
            "store_memory() is missing 'confidence' parameter"
        )

    def test_store_memory_confidence_defaults_to_medium(self):
        """The confidence parameter should default to 'medium'."""
        sig = inspect.signature(store_memory)
        param = sig.parameters["confidence"]
        assert param.default == "medium", (
            f"Expected default 'medium', got {param.default!r}"
        )

    def test_store_memory_confidence_type_is_str(self):
        """The confidence parameter should be typed as str."""
        sig = inspect.signature(store_memory)
        param = sig.parameters["confidence"]
        assert param.annotation is str or param.annotation == "str", (
            f"Expected str annotation, got {param.annotation!r}"
        )


# ---------------------------------------------------------------------------
# Test: sys.path idempotency (B6)
# ---------------------------------------------------------------------------


class TestSysPathIdempotency:
    def test_sys_path_no_duplicate_hooks_lib(self):
        """hooks/lib should appear at most once in sys.path."""
        hooks_lib = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "hooks", "lib")
        )
        matches = [
            p for p in sys.path if os.path.normpath(p) == hooks_lib
        ]
        assert len(matches) <= 1, (
            f"hooks/lib appears {len(matches)} times in sys.path: {matches}"
        )


# ---------------------------------------------------------------------------
# Test: search_memory category filter and brief mode (Task 3.1)
# ---------------------------------------------------------------------------

from memory_server import search_memory  # noqa: E402


def _seed_entries(db):
    """Seed DB with entries across categories for filter tests.

    Each description includes the shared keyword 'workflow' so FTS5 can
    match all entries with a single-term query, letting category/brief
    filtering be tested independently of retrieval quirks.
    """
    entries = [
        ("Hook stderr pattern", "Suppress stderr in workflow hooks", "Prevents JSON corruption", "patterns"),
        ("Validate inputs pattern", "Always validate workflow inputs before processing", "Prevents runtime errors", "patterns"),
        ("Avoid global state", "Global workflow state causes hidden coupling", "Hard to test and debug", "anti-patterns"),
        ("Test before commit", "Run workflow tests before committing", "Catches regressions early", "heuristics"),
    ]
    for name, desc, reasoning, cat in entries:
        _process_store_memory(
            db=db,
            provider=None,
            name=name,
            description=desc,
            reasoning=reasoning,
            category=cat,
            references=[],
            confidence="high",
        )


class TestSearchMemoryCategoryFilter:
    def test_category_filters_to_matching_entries(self, db: MemoryDatabase):
        """search_memory(category='patterns') returns only pattern entries."""
        _seed_entries(db)

        # Use shared keyword 'workflow' that appears in all seeded entries
        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="workflow",
            limit=10,
            category="patterns",
        )

        # Should contain pattern entries
        assert "Hook stderr pattern" in result or "Validate inputs pattern" in result
        # Should NOT contain anti-pattern or heuristic entries
        assert "Avoid global state" not in result
        assert "Test before commit" not in result

    def test_non_matching_category_returns_empty_not_error(self, db: MemoryDatabase):
        """A category with no matching entries returns 'No matching', not an error."""
        # Seed only pattern entries
        _process_store_memory(
            db=db, provider=None,
            name="Only pattern", description="A workflow pattern entry",
            reasoning="Reason", category="patterns", references=[], confidence="high",
        )

        # Search with a category that has zero entries
        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="workflow",
            limit=10,
            category="anti-patterns",
        )

        assert "Error" not in result
        assert "No matching memories found" in result

    def test_category_with_zero_entries_returns_no_matches(self, db: MemoryDatabase):
        """Empty DB + category filter returns no-match, not error."""
        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="anything",
            limit=10,
            category="anti-patterns",
        )

        assert "Error" not in result
        assert "No matching memories found" in result


class TestSearchMemoryBriefMode:
    def test_brief_returns_plain_text_format(self, db: MemoryDatabase):
        """brief=True returns plain-text lines: '- {name} ({confidence})'."""
        _seed_entries(db)

        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="workflow",
            limit=10,
            brief=True,
        )

        # Should start with "Found N entries:"
        assert result.startswith("Found ")
        assert "entries:" in result
        # Each entry line should be "- {name} ({confidence})"
        lines = result.strip().split("\n")
        entry_lines = [l for l in lines if l.startswith("- ")]
        assert len(entry_lines) > 0
        # Verify format: each line has name and confidence in parens
        for line in entry_lines:
            assert line.startswith("- ")
            assert "(" in line and ")" in line

    def test_brief_does_not_contain_json_or_markdown(self, db: MemoryDatabase):
        """brief mode should NOT contain markdown headers or JSON structure."""
        _seed_entries(db)

        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="workflow",
            limit=10,
            brief=True,
        )

        assert "###" not in result
        assert "Why:" not in result
        assert "Confidence:" not in result

    def test_brief_with_category_combined(self, db: MemoryDatabase):
        """brief + category should work together."""
        _seed_entries(db)

        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="workflow",
            limit=10,
            category="patterns",
            brief=True,
        )

        assert result.startswith("Found ")
        # Should not mention non-pattern entries
        assert "Avoid global state" not in result
        assert "Test before commit" not in result

    def test_brief_shows_confidence(self, db: MemoryDatabase):
        """brief mode should show confidence in parentheses."""
        _seed_entries(db)

        result = _process_search_memory(
            db=db,
            provider=None,
            config={},
            query="workflow",
            limit=10,
            brief=True,
        )

        # All seeded entries have confidence="high"
        assert "(high)" in result


class TestSearchMemoryMCPToolParams:
    def test_search_memory_has_category_parameter(self):
        """The search_memory MCP tool must accept a 'category' parameter."""
        sig = inspect.signature(search_memory)
        assert "category" in sig.parameters

    def test_search_memory_category_defaults_to_none(self):
        """category parameter should default to None."""
        sig = inspect.signature(search_memory)
        param = sig.parameters["category"]
        assert param.default is None

    def test_search_memory_has_brief_parameter(self):
        """The search_memory MCP tool must accept a 'brief' parameter."""
        sig = inspect.signature(search_memory)
        assert "brief" in sig.parameters

    def test_search_memory_brief_defaults_to_false(self):
        """brief parameter should default to False."""
        sig = inspect.signature(search_memory)
        param = sig.parameters["brief"]
        assert param.default is False


# ---------------------------------------------------------------------------
# Test: FTS5 sanitization via MCP search (Task 1.5)
# ---------------------------------------------------------------------------


class TestSearchMemoryFts5Sanitization:
    """Integration tests for FTS5 query sanitization through _process_search_memory."""

    def _seed_fts5_entries(self, db):
        """Seed entries with terms that exercise FTS5 sanitization."""
        entries = [
            ("Firebase auth", "Firebase authentication for serverless typescript apps",
             "Standard auth pattern", "patterns"),
            ("Firestore queries", "Optimize Firestore queries for typescript projects",
             "Performance pattern", "patterns"),
            ("Anti-patterns in hooks", "Common anti-patterns when writing shell hooks",
             "Avoid these mistakes", "anti-patterns"),
            ("Claude plugin config", "Register plugins in the claude marketplace using json config",
             "Plugin distribution pattern", "heuristics"),
            ("Session capture source", "Use session-capture source for automated knowledge extraction",
             "Knowledge management", "patterns"),
        ]
        for name, desc, reasoning, cat in entries:
            _process_store_memory(
                db=db, provider=None,
                name=name, description=desc, reasoning=reasoning,
                category=cat, references=[],
            )

    def test_multiword_query_returns_results(self, db: MemoryDatabase):
        """Multi-word query with OR semantics should find matching entries."""
        self._seed_fts5_entries(db)
        result = _process_search_memory(
            db=db, provider=None, config={},
            query="firebase firestore typescript",
            limit=10,
        )
        assert "Found" in result
        assert "No matching memories found" not in result
        # Should find entries mentioning firebase or firestore
        assert "Firebase" in result or "Firestore" in result

    def test_hyphenated_query_returns_results(self, db: MemoryDatabase):
        """Hyphenated query terms should be quoted and match correctly."""
        self._seed_fts5_entries(db)
        result = _process_search_memory(
            db=db, provider=None, config={},
            query="anti-patterns",
            limit=10,
        )
        assert "Found" in result
        assert "No matching memories found" not in result
        assert "Anti-patterns in hooks" in result or "anti-patterns" in result.lower()

    def test_special_char_query_no_error(self, db: MemoryDatabase):
        """Queries with special chars should not produce errors."""
        self._seed_fts5_entries(db)
        result = _process_search_memory(
            db=db, provider=None, config={},
            query=".claude-plugin/marketplace.json",
            limit=10,
        )
        # Should not error out
        assert "Error" not in result
        # Should find the claude marketplace entry
        assert "claude" in result.lower() or "marketplace" in result.lower() or "No matching" in result

    def test_category_filter_with_sanitized_query(self, db: MemoryDatabase):
        """Category filter should work with sanitized queries."""
        self._seed_fts5_entries(db)
        result = _process_search_memory(
            db=db, provider=None, config={},
            query="source:session-capture",
            limit=10,
            category="patterns",
        )
        # Should not error
        assert "Error" not in result
        # If results found, should be patterns only (not anti-patterns or heuristics)
        if "Found" in result:
            assert "Anti-patterns in hooks" not in result


# ---------------------------------------------------------------------------
# Deepened tests Phase B: MCP Audit Token Efficiency
# ---------------------------------------------------------------------------


class TestSearchMemoryCategoryFilterBeforeRankingDeepened:
    """Mutation test: category filter must apply BEFORE ranking, not after.
    derived_from: spec:AC-7 (category pre-filtering), dimension:mutation_mindset
    """

    def test_search_memory_category_filters_before_ranking(self, db: MemoryDatabase):
        """Category filter narrows candidates before ranking, not after.
        derived_from: spec:AC-7, dimension:mutation_mindset

        Anticipate: If category filtering happens AFTER ranking (post-filter),
        the limit would be applied to unfiltered results first, potentially
        returning fewer than `limit` results even when enough category-matching
        entries exist. Pre-filtering ensures the ranking engine sees only
        category-matching candidates.

        Setup: 5 'patterns' entries and 5 'heuristics' entries, all sharing
        the keyword 'workflow'. With limit=3 and category='heuristics',
        pre-filtering gives ranking 5 heuristics to choose 3 from.
        Post-filtering might give ranking all 10, pick top 3, then filter
        out patterns -- potentially returning <3 results.

        Challenge: swapping the order of filter-then-rank to rank-then-filter
        would produce different (likely fewer) results for the filtered category.
        """
        # Given 5 patterns and 5 heuristics entries sharing keyword 'workflow'
        for i in range(5):
            _process_store_memory(
                db=db, provider=None,
                name=f"Pattern workflow {i}",
                description=f"A workflow pattern about testing number {i}",
                reasoning=f"Pattern reason {i}",
                category="patterns", references=[],
            )
        for i in range(5):
            _process_store_memory(
                db=db, provider=None,
                name=f"Heuristic workflow {i}",
                description=f"A workflow heuristic about testing number {i}",
                reasoning=f"Heuristic reason {i}",
                category="heuristics", references=[],
            )

        # When searching with category filter and limit
        result = _process_search_memory(
            db=db, provider=None, config={},
            query="workflow testing",
            limit=3,
            category="heuristics",
        )

        # Then results contain ONLY heuristic entries (not patterns)
        assert "Pattern workflow" not in result, (
            "Category filter should exclude 'patterns' entries"
        )
        # And we get the requested number of results
        assert "Found 3" in result, (
            "Pre-ranking filter should provide enough candidates for limit=3"
        )


# ---------------------------------------------------------------------------
# Delete memory MCP tests (feature 047)
# ---------------------------------------------------------------------------


class TestDeleteMemoryMCP:
    """Tests for MCP delete_memory tool."""

    def test_mcp_delete_memory_success(self, db: MemoryDatabase):
        """AC-11: delete_memory returns success JSON."""
        import asyncio
        import memory_server

        # Store an entry first
        entry = {
            "id": "mcp-del-test",
            "name": "MCP Delete Test",
            "description": "To be deleted via MCP",
            "category": "patterns",
            "source": "manual",
            "keywords": "[]",
            "source_project": "/tmp",
            "source_hash": "0000",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        db.upsert_entry(entry)
        assert db.get_entry("mcp-del-test") is not None

        # Set module global
        old_db = memory_server._db
        memory_server._db = db
        try:
            result = asyncio.run(memory_server.delete_memory(entry_id="mcp-del-test"))
            data = json.loads(result)
            assert data["result"] == "Deleted memory: mcp-del-test"
            assert db.get_entry("mcp-del-test") is None
        finally:
            memory_server._db = old_db

    def test_mcp_delete_memory_not_found(self, db: MemoryDatabase):
        """delete_memory returns error JSON when entry not found."""
        import asyncio
        import memory_server

        old_db = memory_server._db
        memory_server._db = db
        try:
            result = asyncio.run(memory_server.delete_memory(entry_id="nonexistent"))
            data = json.loads(result)
            assert "error" in data
            assert "not found" in data["error"].lower()
        finally:
            memory_server._db = old_db
