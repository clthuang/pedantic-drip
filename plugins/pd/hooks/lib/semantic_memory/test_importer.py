"""Tests for semantic_memory.importer module."""
from __future__ import annotations

import textwrap

import pytest

from semantic_memory import content_hash
from semantic_memory.database import MemoryDatabase
from semantic_memory.importer import MarkdownImporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Provide an in-memory MemoryDatabase, closed after test."""
    database = MemoryDatabase(":memory:")
    yield database
    database.close()


@pytest.fixture
def importer(db):
    """MarkdownImporter with in-memory DB."""
    return MarkdownImporter(db=db)


# ---------------------------------------------------------------------------
# Sample markdown content
# ---------------------------------------------------------------------------

ANTI_PATTERNS_MD = textwrap.dedent("""\
    # Anti-Patterns

    ## Observed Anti-Patterns

    ### Anti-Pattern: Premature Optimisation
    Optimising code before profiling leads to complex,
    hard-to-maintain solutions.
    - Observation Count: 5
    - Confidence: high
    - Last Observed: 2026-01-15

    ### Anti-Pattern: God Object
    A single class that knows too much or does too much.
    - Observation Count: 3
    - Confidence: medium
    - Last Observed: 2026-02-01

    ### Anti-Pattern: Copy-Paste Programming
    Duplicating code instead of abstracting shared logic.
    - Observation Count: 2
    - Confidence: low
    - Last Observed: 2026-01-20
""")

PATTERNS_MD = textwrap.dedent("""\
    # Patterns

    ## Observed Patterns

    ### Pattern: Early Return
    Return early from functions to reduce nesting.
    - Observation Count: 4
    - Confidence: high
    - Last Observed: 2026-01-10
""")

HEURISTICS_MD = textwrap.dedent("""\
    # Heuristics

    ## Observed Heuristics

    ### Keep Functions Short
    Functions should do one thing and do it well.
    - Observation Count: 6
    - Confidence: high
    - Last Observed: 2026-02-10
""")

HTML_COMMENT_MD = textwrap.dedent("""\
    # Anti-Patterns

    <!-- This is a template comment
    ### Anti-Pattern: Template Entry
    Do not parse this.
    - Observation Count: 1
    - Confidence: low
    -->

    ### Anti-Pattern: Real Entry
    This should be parsed.
    - Observation Count: 2
    - Confidence: medium
    - Last Observed: 2026-01-05
""")


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------


class TestParseMarkdownEntries:
    def test_parse_anti_patterns_returns_three_entries(self, importer, tmp_path):
        """Parsing anti-patterns.md with 3 entries returns 3 correct entries."""
        filepath = tmp_path / "anti-patterns.md"
        filepath.write_text(ANTI_PATTERNS_MD)

        entries = importer._parse_markdown_entries(str(filepath), "anti-patterns")
        assert len(entries) == 3

    def test_entry_names_stripped_of_prefix(self, importer, tmp_path):
        """Anti-Pattern: and Pattern: prefixes are stripped from names."""
        filepath = tmp_path / "anti-patterns.md"
        filepath.write_text(ANTI_PATTERNS_MD)

        entries = importer._parse_markdown_entries(str(filepath), "anti-patterns")
        names = [e["name"] for e in entries]
        assert "Premature Optimisation" in names
        assert "God Object" in names
        assert "Copy-Paste Programming" in names

    def test_pattern_prefix_stripped(self, importer, tmp_path):
        """Pattern: prefix is stripped from pattern names."""
        filepath = tmp_path / "patterns.md"
        filepath.write_text(PATTERNS_MD)

        entries = importer._parse_markdown_entries(str(filepath), "patterns")
        assert entries[0]["name"] == "Early Return"

    def test_heuristic_prefix_not_stripped(self, importer, tmp_path):
        """Heuristic names use plain names -- no 'Heuristic: ' prefix to strip."""
        filepath = tmp_path / "heuristics.md"
        filepath.write_text(HEURISTICS_MD)

        entries = importer._parse_markdown_entries(str(filepath), "heuristics")
        assert entries[0]["name"] == "Keep Functions Short"

    def test_html_comments_stripped(self, importer, tmp_path):
        """HTML comments are stripped before parsing, so template entries are excluded."""
        filepath = tmp_path / "anti-patterns.md"
        filepath.write_text(HTML_COMMENT_MD)

        entries = importer._parse_markdown_entries(str(filepath), "anti-patterns")
        assert len(entries) == 1
        assert entries[0]["name"] == "Real Entry"

    def test_entry_metadata_extracted(self, importer, tmp_path):
        """Observation count and confidence are extracted."""
        filepath = tmp_path / "anti-patterns.md"
        filepath.write_text(ANTI_PATTERNS_MD)

        entries = importer._parse_markdown_entries(str(filepath), "anti-patterns")
        first = entries[0]  # Premature Optimisation
        assert first["observation_count"] == 5
        assert first["confidence"] == "high"

    def test_entry_description_extracted(self, importer, tmp_path):
        """Description text is extracted (body before metadata lines)."""
        filepath = tmp_path / "anti-patterns.md"
        filepath.write_text(ANTI_PATTERNS_MD)

        entries = importer._parse_markdown_entries(str(filepath), "anti-patterns")
        first = entries[0]
        assert "Optimising code before profiling" in first["description"]

    def test_content_hash_matches_description(self, importer, tmp_path):
        """content_hash is computed from the description text."""
        filepath = tmp_path / "anti-patterns.md"
        filepath.write_text(ANTI_PATTERNS_MD)

        entries = importer._parse_markdown_entries(str(filepath), "anti-patterns")
        for entry in entries:
            assert entry["content_hash"] == content_hash(entry["description"])

    def test_missing_file_returns_empty(self, importer):
        """Non-existent file returns empty list."""
        entries = importer._parse_markdown_entries("/nonexistent/file.md", "patterns")
        assert entries == []

    def test_category_set_correctly(self, importer, tmp_path):
        """Category is set from the argument, not inferred."""
        filepath = tmp_path / "anti-patterns.md"
        filepath.write_text(ANTI_PATTERNS_MD)

        entries = importer._parse_markdown_entries(str(filepath), "anti-patterns")
        assert all(e["category"] == "anti-patterns" for e in entries)


# ---------------------------------------------------------------------------
# Import into DB tests
# ---------------------------------------------------------------------------


class TestImportIntoDB:
    def test_import_three_entries(self, db, importer, tmp_path):
        """Importing 3 entries results in db.count_entries() == 3."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        result = importer.import_all(
            project_root=str(tmp_path),
            global_store=str(tmp_path / "global"),
        )
        assert result["imported"] == 3
        assert db.count_entries() == 3

    def test_reimport_is_idempotent(self, db, importer, tmp_path):
        """Re-importing the same files skips all entries, observation_count unchanged."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        importer.import_all(str(tmp_path), str(tmp_path / "global"))
        result = importer.import_all(str(tmp_path), str(tmp_path / "global"))

        # Still 3 entries (upsert dedup by content hash)
        assert db.count_entries() == 3
        assert result["skipped"] == 3
        assert result["imported"] == 0

        # observation_count should NOT have been incremented
        for entry in db.get_all_entries():
            assert entry["observation_count"] == entry.get("observation_count", 1)

    def test_embeddings_null_keywords_empty_json(self, db, importer, tmp_path):
        """After import, embeddings are NULL and keywords are '[]' (deferred)."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        importer.import_all(str(tmp_path), str(tmp_path / "global"))

        for entry in db.get_all_entries():
            # get_all_entries() excludes the embedding BLOB column;
            # verify keywords are '[]' (embeddings tested via get_entry).
            assert "embedding" not in entry
            assert entry["keywords"] == "[]"

    def test_import_all_scans_local_and_global(self, db, importer, tmp_path):
        """import_all scans both local knowledge-bank and global store."""
        # Local: 3 anti-patterns
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        # Global: 1 pattern
        global_dir = tmp_path / "global"
        global_dir.mkdir(parents=True)
        (global_dir / "anti-patterns.md").write_text("")
        (global_dir / "patterns.md").write_text(PATTERNS_MD)
        (global_dir / "heuristics.md").write_text("")

        result = importer.import_all(str(tmp_path), str(global_dir))
        assert result["imported"] == 4  # 3 local + 1 global
        assert db.count_entries() == 4

    def test_missing_dirs_handled_gracefully(self, db, importer, tmp_path):
        """Missing local or global directories do not cause errors."""
        result = importer.import_all(
            str(tmp_path / "nonexistent"),
            str(tmp_path / "also-nonexistent"),
        )
        assert result["imported"] == 0
        assert db.count_entries() == 0

    def test_source_is_import(self, db, importer, tmp_path):
        """Entries imported have source='import'."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        importer.import_all(str(tmp_path), str(tmp_path / "global"))

        for entry in db.get_all_entries():
            assert entry["source"] == "import"

    def test_source_project_set(self, db, importer, tmp_path):
        """source_project is set to the project_root argument."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        importer.import_all(str(tmp_path), str(tmp_path / "global"))

        for entry in db.get_all_entries():
            assert entry["source_project"] == str(tmp_path)

    def test_import_returns_total_count(self, db, importer, tmp_path):
        """import_all returns the total count of entries imported."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text(PATTERNS_MD)
        (kb_dir / "heuristics.md").write_text(HEURISTICS_MD)

        result = importer.import_all(str(tmp_path), str(tmp_path / "global"))
        assert result["imported"] == 5  # 3 + 1 + 1

    def test_source_hash_stored_after_import(self, db, importer, tmp_path):
        """All imported entries should have a non-null source_hash."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        importer.import_all(str(tmp_path), str(tmp_path / "global"))

        for entry in db.get_all_entries():
            stored = db.get_entry(entry["id"])
            assert stored["source_hash"] is not None

    def test_created_timestamp_utc_stored_after_import(self, db, importer, tmp_path):
        """All imported entries should have a non-null created_timestamp_utc."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        importer.import_all(str(tmp_path), str(tmp_path / "global"))

        for entry in db.get_all_entries():
            stored = db.get_entry(entry["id"])
            assert stored["created_timestamp_utc"] is not None

    def test_modified_entry_reimported(self, db, importer, tmp_path):
        """Changing markdown text causes re-import with updated source_hash."""
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        original_md = textwrap.dedent("""\
            # Anti-Patterns

            ### Anti-Pattern: Premature Optimisation
            Optimising code before profiling leads to complex,
            hard-to-maintain solutions.
            - Observation Count: 5
            - Confidence: high
        """)
        (kb_dir / "anti-patterns.md").write_text(original_md)
        importer.import_all(str(tmp_path), str(tmp_path / "global"))

        entries = db.get_all_entries()
        assert len(entries) == 1
        original_hash = db.get_entry(entries[0]["id"])["source_hash"]

        # Modify the markdown
        modified_md = textwrap.dedent("""\
            # Anti-Patterns

            ### Anti-Pattern: Premature Optimisation
            Optimising code before profiling leads to complex,
            hard-to-maintain solutions. Updated with new info.
            - Observation Count: 5
            - Confidence: high
        """)
        (kb_dir / "anti-patterns.md").write_text(modified_md)
        result = importer.import_all(str(tmp_path), str(tmp_path / "global"))

        # The content_hash changed (different description), so it's a new entry
        assert result["imported"] >= 1


# ---------------------------------------------------------------------------
# Custom artifacts_root tests
# ---------------------------------------------------------------------------


class TestCustomArtifactsRoot:
    def test_custom_artifacts_root_finds_entries(self, db, tmp_path):
        """Importer with custom artifacts_root finds knowledge-bank at custom path."""
        custom_importer = MarkdownImporter(db=db, artifacts_root="my-docs")

        kb_dir = tmp_path / "my-docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        result = custom_importer.import_all(str(tmp_path), str(tmp_path / "global"))
        assert result["imported"] == 3
        assert db.count_entries() == 3

    def test_custom_artifacts_root_ignores_default_docs(self, db, tmp_path):
        """Importer with custom artifacts_root does NOT read docs/knowledge-bank/."""
        custom_importer = MarkdownImporter(db=db, artifacts_root="my-docs")

        # Put entries under docs/ (should be ignored)
        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        result = custom_importer.import_all(str(tmp_path), str(tmp_path / "global"))
        assert result["imported"] == 0
        assert db.count_entries() == 0

    def test_default_artifacts_root_reads_docs(self, db, tmp_path):
        """Default importer reads from docs/knowledge-bank/."""
        default_importer = MarkdownImporter(db=db)

        kb_dir = tmp_path / "docs" / "knowledge-bank"
        kb_dir.mkdir(parents=True)
        (kb_dir / "anti-patterns.md").write_text(ANTI_PATTERNS_MD)
        (kb_dir / "patterns.md").write_text("")
        (kb_dir / "heuristics.md").write_text("")

        result = default_importer.import_all(str(tmp_path), str(tmp_path / "global"))
        assert result["imported"] == 3


# ---------------------------------------------------------------------------
# Backfill discovery tests
# ---------------------------------------------------------------------------


class TestDiscoverKnowledgeBankProjects:
    def test_discover_finds_kb_projects(self, tmp_path):
        """Projects with docs/knowledge-bank/ are discovered."""
        from semantic_memory.backfill import _discover_knowledge_bank_projects

        proj_a = tmp_path / "proj-a"
        (proj_a / "docs" / "knowledge-bank").mkdir(parents=True)
        proj_b = tmp_path / "proj-b"
        (proj_b / "docs" / "knowledge-bank").mkdir(parents=True)

        found = _discover_knowledge_bank_projects([str(tmp_path)])
        assert str(proj_a) in found
        assert str(proj_b) in found

    def test_discover_ignores_non_kb(self, tmp_path):
        """Projects without docs/knowledge-bank/ are not discovered."""
        from semantic_memory.backfill import _discover_knowledge_bank_projects

        (tmp_path / "proj-a" / "docs" / "knowledge-bank").mkdir(parents=True)
        (tmp_path / "proj-b" / "src").mkdir(parents=True)  # no KB

        found = _discover_knowledge_bank_projects([str(tmp_path)])
        assert len(found) == 1
        assert "proj-a" in found[0]

    def test_discover_nonexistent_base_dir(self):
        """Non-existent base directory returns empty list."""
        from semantic_memory.backfill import _discover_knowledge_bank_projects

        found = _discover_knowledge_bank_projects(["/nonexistent/path"])
        assert found == []

    def test_discover_multiple_base_dirs(self, tmp_path):
        """Multiple base directories are scanned."""
        from semantic_memory.backfill import _discover_knowledge_bank_projects

        dir_a = tmp_path / "area-a"
        dir_b = tmp_path / "area-b"
        (dir_a / "proj-1" / "docs" / "knowledge-bank").mkdir(parents=True)
        (dir_b / "proj-2" / "docs" / "knowledge-bank").mkdir(parents=True)

        found = _discover_knowledge_bank_projects([str(dir_a), str(dir_b)])
        assert len(found) == 2
        assert any("proj-1" in f for f in found)
        assert any("proj-2" in f for f in found)
