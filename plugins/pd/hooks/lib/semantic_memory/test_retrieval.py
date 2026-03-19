"""Tests for semantic_memory.retrieval module."""
from __future__ import annotations

import json
import textwrap
from unittest import mock

import numpy as np
import pytest

from semantic_memory.retrieval_types import CandidateScores, RetrievalResult
from semantic_memory.retrieval import RetrievalPipeline


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockProvider:
    """Minimal mock embedding provider for testing."""

    def __init__(self, dimensions: int = 768):
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str, task_type: str = "query") -> np.ndarray:
        """Return a deterministic unit vector based on text hash."""
        rng = np.random.RandomState(hash(text) % (2**31))
        vec = rng.randn(self._dimensions).astype(np.float32)
        vec /= np.linalg.norm(vec)
        return vec


class MockDatabase:
    """Minimal mock database for testing retrieval."""

    def __init__(
        self,
        *,
        fts5_available: bool = True,
        embeddings: tuple[list[str], np.ndarray] | None = None,
        fts5_results: list[tuple[str, float]] | None = None,
        all_entries: list[dict] | None = None,
    ):
        self._fts5_available = fts5_available
        self._embeddings = embeddings
        self._fts5_results = fts5_results if fts5_results is not None else []
        self._all_entries = all_entries if all_entries is not None else []

    @property
    def fts5_available(self) -> bool:
        return self._fts5_available

    def get_all_embeddings(
        self, expected_dims: int = 768
    ) -> tuple[list[str], np.ndarray] | None:
        return self._embeddings

    def fts5_search(
        self, query: str, limit: int = 100
    ) -> list[tuple[str, float]]:
        return self._fts5_results

    def get_all_entries(self) -> list[dict]:
        return self._all_entries


def _make_normalized_matrix(ids: list[str], dims: int = 768) -> tuple[list[str], np.ndarray]:
    """Create a matrix of normalized vectors for testing."""
    n = len(ids)
    rng = np.random.RandomState(42)
    matrix = rng.randn(n, dims).astype(np.float32)
    # L2-normalize each row
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / norms
    return ids, matrix


# ---------------------------------------------------------------------------
# Tests: retrieve()
# ---------------------------------------------------------------------------


class TestRetrieveBothSignals:
    """retrieve with both vector and FTS5 signals."""

    def test_entries_found_by_both_carry_both_scores(self):
        """When an entry appears in both vector and FTS5 results,
        its CandidateScores should have both vector_score and bm25_score."""
        ids = ["entry-a", "entry-b", "entry-c"]
        emb_ids, matrix = _make_normalized_matrix(ids)
        provider = MockProvider(dimensions=768)

        fts5_results = [
            ("entry-b", 5.0),
            ("entry-c", 3.0),
            ("entry-d", 1.0),
        ]

        db = MockDatabase(
            fts5_available=True,
            embeddings=(emb_ids, matrix),
            fts5_results=fts5_results,
        )

        pipeline = RetrievalPipeline(db=db, provider=provider, config={})
        result = pipeline.retrieve("test query")

        assert isinstance(result, RetrievalResult)
        # entry-b and entry-c should have both scores
        assert "entry-b" in result.candidates
        assert result.candidates["entry-b"].vector_score != 0.0
        assert result.candidates["entry-b"].bm25_score == 5.0

        assert "entry-c" in result.candidates
        assert result.candidates["entry-c"].vector_score != 0.0
        assert result.candidates["entry-c"].bm25_score == 3.0

        # entry-a: vector only
        assert "entry-a" in result.candidates
        assert result.candidates["entry-a"].vector_score != 0.0
        assert result.candidates["entry-a"].bm25_score == 0.0

        # entry-d: FTS5 only
        assert "entry-d" in result.candidates
        assert result.candidates["entry-d"].vector_score == 0.0
        assert result.candidates["entry-d"].bm25_score == 1.0

    def test_metadata_counts(self):
        """vector_candidate_count and fts5_candidate_count are populated."""
        ids = ["entry-a", "entry-b"]
        emb_ids, matrix = _make_normalized_matrix(ids)
        provider = MockProvider(dimensions=768)

        fts5_results = [("entry-b", 5.0), ("entry-c", 3.0)]

        db = MockDatabase(
            fts5_available=True,
            embeddings=(emb_ids, matrix),
            fts5_results=fts5_results,
        )

        pipeline = RetrievalPipeline(db=db, provider=provider, config={})
        result = pipeline.retrieve("test query")

        assert result.vector_candidate_count == 2
        assert result.fts5_candidate_count == 2
        assert result.context_query == "test query"


class TestRetrieveVectorOnly:
    """retrieve with vector-only (fts5_available=False)."""

    def test_vector_only_retrieval(self):
        ids = ["entry-a", "entry-b"]
        emb_ids, matrix = _make_normalized_matrix(ids)
        provider = MockProvider(dimensions=768)

        db = MockDatabase(
            fts5_available=False,
            embeddings=(emb_ids, matrix),
        )

        pipeline = RetrievalPipeline(db=db, provider=provider, config={})
        result = pipeline.retrieve("test query")

        assert result.vector_candidate_count == 2
        assert result.fts5_candidate_count == 0
        assert len(result.candidates) == 2
        for cid, scores in result.candidates.items():
            assert scores.vector_score != 0.0
            assert scores.bm25_score == 0.0


class TestRetrieveFTS5Only:
    """retrieve with FTS5-only (provider=None)."""

    def test_fts5_only_retrieval(self):
        fts5_results = [("entry-a", 5.0), ("entry-b", 3.0)]

        db = MockDatabase(
            fts5_available=True,
            fts5_results=fts5_results,
        )

        pipeline = RetrievalPipeline(db=db, provider=None, config={})
        result = pipeline.retrieve("test query")

        assert result.vector_candidate_count == 0
        assert result.fts5_candidate_count == 2
        assert len(result.candidates) == 2
        for cid, scores in result.candidates.items():
            assert scores.vector_score == 0.0
            assert scores.bm25_score > 0.0


class TestRetrieveNeither:
    """retrieve with neither (provider=None, fts5_available=False)."""

    def test_returns_empty(self):
        db = MockDatabase(fts5_available=False)

        pipeline = RetrievalPipeline(db=db, provider=None, config={})
        result = pipeline.retrieve("test query")

        assert result.candidates == {}
        assert result.vector_candidate_count == 0
        assert result.fts5_candidate_count == 0


class TestRetrieveNoneQuery:
    """retrieve with None context_query passes all entries for prominence-only ranking."""

    def test_returns_all_entries_with_zero_scores(self):
        ids = ["entry-a"]
        emb_ids, matrix = _make_normalized_matrix(ids)
        provider = MockProvider(dimensions=768)

        db = MockDatabase(
            fts5_available=True,
            embeddings=(emb_ids, matrix),
            fts5_results=[("entry-a", 5.0)],
            all_entries=[{"id": "entry-a"}, {"id": "entry-b"}],
        )

        pipeline = RetrievalPipeline(db=db, provider=provider, config={})
        result = pipeline.retrieve(None)

        assert len(result.candidates) == 2
        assert "entry-a" in result.candidates
        assert "entry-b" in result.candidates
        # All scores should be zero (no retrieval signals)
        for cand in result.candidates.values():
            assert cand.vector_score == 0.0
            assert cand.bm25_score == 0.0
        assert result.vector_candidate_count == 0
        assert result.fts5_candidate_count == 0
        assert result.context_query is None

    def test_empty_db_returns_empty_candidates(self):
        provider = MockProvider(dimensions=768)
        db = MockDatabase(all_entries=[])

        pipeline = RetrievalPipeline(db=db, provider=provider, config={})
        result = pipeline.retrieve(None)

        assert result.candidates == {}
        assert result.context_query is None


# ---------------------------------------------------------------------------
# Tests: collect_context()
# ---------------------------------------------------------------------------


class TestCollectContextWithMetaJson:
    """collect_context with mock .meta.json showing active feature."""

    def test_collects_from_active_feature(self, tmp_path):
        """Should find the active feature and compose a context string."""
        # Create feature directory structure
        feature_dir = tmp_path / "docs" / "features" / "024-memory-semantic-search"
        feature_dir.mkdir(parents=True)

        meta = {
            "slug": "memory-semantic-search",
            "status": "active",
            "lastCompletedPhase": "design",
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        spec_content = textwrap.dedent("""\
            # Memory Semantic Search

            This feature adds semantic memory retrieval to the development workflow.

            ## Requirements

            More details here.
        """)
        (feature_dir / "spec.md").write_text(spec_content)

        # Mock git diff
        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = "src/foo.py\nsrc/bar.py"
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "memory-semantic-search" in context
        assert "design" in context
        assert "src/foo.py" in context or "foo.py" in context

    def test_picks_highest_numeric_id_among_active(self, tmp_path):
        """When multiple active features exist, pick highest numeric ID."""
        docs = tmp_path / "docs" / "features"

        # Feature 020 (active)
        f020 = docs / "020-older-feature"
        f020.mkdir(parents=True)
        (f020 / ".meta.json").write_text(json.dumps({
            "slug": "older-feature",
            "status": "active",
            "lastCompletedPhase": "implement",
        }))
        (f020 / "spec.md").write_text("# Older Feature\n\nOlder desc.")

        # Feature 024 (active)
        f024 = docs / "024-newer-feature"
        f024.mkdir(parents=True)
        (f024 / ".meta.json").write_text(json.dumps({
            "slug": "newer-feature",
            "status": "active",
            "lastCompletedPhase": "design",
        }))
        (f024 / "spec.md").write_text("# Newer Feature\n\nNewer desc.")

        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "newer-feature" in context
        assert "older-feature" not in context

    def test_uses_prd_fallback_when_no_spec(self, tmp_path):
        """Should fall back to prd.md when spec.md is absent."""
        feature_dir = tmp_path / "docs" / "features" / "024-feature"
        feature_dir.mkdir(parents=True)

        meta = {
            "slug": "fallback-feature",
            "status": "active",
            "lastCompletedPhase": "brainstorm",
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))
        (feature_dir / "prd.md").write_text("# PRD\n\nPRD description here.")

        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "fallback-feature" in context

    def test_meta_json_parse_error_logged(self, tmp_path, capsys):
        """Malformed .meta.json should log to stderr and be skipped."""
        feature_dir = tmp_path / "docs" / "features" / "024-bad"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{invalid json!!!")

        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = "somefile.py"
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        captured = capsys.readouterr()
        assert "meta.json" in captured.err.lower() or ".meta.json" in captured.err


class TestCollectContextGitDiffOnly:
    """collect_context with no active feature but git diff files."""

    def test_returns_context_from_git_diff_only(self, tmp_path):
        """When no .meta.json found, git diff files should still produce context."""
        # Create docs/features dir but no .meta.json files
        (tmp_path / "docs" / "features").mkdir(parents=True)

        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = "src/main.py\nsrc/utils.py\ntests/test_main.py"
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "src/main.py" in context


class TestCollectContextNoSignals:
    """collect_context with no signals at all."""

    def test_returns_none(self, tmp_path):
        """When no .meta.json and git diff returns nothing, return None."""
        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is None

    def test_returns_none_on_git_error(self, tmp_path):
        """When git diff fails entirely, return None if no other signals."""
        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_subprocess.run.side_effect = Exception("git not found")

            context = pipeline.collect_context(str(tmp_path))

        assert context is None


class TestCollectContextGitFallback:
    """collect_context git diff fallback behavior."""

    def test_falls_back_to_head1_on_head3_failure(self, tmp_path):
        """When HEAD~3 fails, should fall back to HEAD~1."""
        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            result = mock.Mock()
            if "HEAD~3..HEAD" in cmd:
                result.returncode = 128  # git error
                result.stdout = ""
            else:
                result.returncode = 0
                result.stdout = "fallback_file.py"
            return result

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_subprocess.run.side_effect = mock_run

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "fallback_file.py" in context


class TestCollectContextBranchName:
    """collect_context includes branch name when it's descriptive."""

    def test_includes_branch_name(self, tmp_path):
        """Should include branch name in context string."""
        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            def mock_run(cmd, **kwargs):
                result = mock.Mock()
                if "rev-parse" in cmd:
                    result.returncode = 0
                    result.stdout = "feature/024-memory-semantic-search"
                elif "--cached" in cmd:
                    result.returncode = 0
                    result.stdout = ""
                elif "--name-only" in cmd and "HEAD" not in "".join(cmd):
                    result.returncode = 0
                    result.stdout = ""
                else:
                    result.returncode = 0
                    result.stdout = "some_file.py"
                return result

            mock_subprocess.run.side_effect = mock_run

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "Branch: feature/024-memory-semantic-search" in context

    def test_skips_generic_branch_names(self, tmp_path):
        """Generic branch names (main, master, develop) should be skipped."""
        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        for branch_name in ("main", "master", "develop", "HEAD"):
            with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
                def mock_run(cmd, **kwargs):
                    result = mock.Mock()
                    if "rev-parse" in cmd:
                        result.returncode = 0
                        result.stdout = branch_name
                    else:
                        result.returncode = 0
                        result.stdout = "file.py"
                    return result

                mock_subprocess.run.side_effect = mock_run

                context = pipeline.collect_context(str(tmp_path))

            assert context is not None
            assert "Branch:" not in context


class TestCollectContextWorkingTree:
    """collect_context includes working tree (unstaged + staged) files."""

    def test_includes_working_tree_files(self, tmp_path):
        """Unstaged and staged files should appear as 'Editing:' signal."""
        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            def mock_run(cmd, **kwargs):
                result = mock.Mock()
                if "rev-parse" in cmd:
                    result.returncode = 0
                    result.stdout = "main"
                elif "HEAD~3..HEAD" in cmd or "HEAD~1..HEAD" in cmd:
                    result.returncode = 0
                    result.stdout = ""
                elif "--cached" in cmd:
                    result.returncode = 0
                    result.stdout = "staged_file.py"
                elif cmd == ["git", "diff", "--name-only"]:
                    result.returncode = 0
                    result.stdout = "unstaged_file.py"
                else:
                    result.returncode = 0
                    result.stdout = ""
                return result

            mock_subprocess.run.side_effect = mock_run

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "Editing:" in context
        assert "staged_file.py" in context
        assert "unstaged_file.py" in context

    def test_deduplicates_with_committed_files(self, tmp_path):
        """Files already in committed changes should not appear in Editing."""
        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            def mock_run(cmd, **kwargs):
                result = mock.Mock()
                if "rev-parse" in cmd:
                    result.returncode = 0
                    result.stdout = "main"
                elif "HEAD~3..HEAD" in cmd:
                    result.returncode = 0
                    result.stdout = "shared.py"
                elif cmd == ["git", "diff", "--name-only"]:
                    result.returncode = 0
                    result.stdout = "shared.py\nnew_file.py"
                elif "--cached" in cmd:
                    result.returncode = 0
                    result.stdout = ""
                else:
                    result.returncode = 0
                    result.stdout = ""
                return result

            mock_subprocess.run.side_effect = mock_run

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "Files: shared.py" in context
        # Editing should only include the file NOT already in committed
        assert "Editing: new_file.py" in context
        # shared.py should NOT appear in Editing
        assert "Editing: shared.py" not in context


class TestCollectContextProjectDescription:
    """collect_context uses project-level description when no active feature."""

    def test_reads_claude_md_repository_overview(self, tmp_path):
        """Should extract Repository Overview section from CLAUDE.md."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(textwrap.dedent("""\
            # CLAUDE.md

            ## Repository Overview

            Claude Code plugin providing a structured feature development workflow.

            ## Key Principles

            Other content here.
        """))

        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "Project:" in context
        assert "structured feature development workflow" in context

    def test_falls_back_to_readme(self, tmp_path):
        """Should fall back to README.md when CLAUDE.md has no overview."""
        readme = tmp_path / "README.md"
        readme.write_text(textwrap.dedent("""\
            # My Project

            This is a web application for managing tasks.

            ## Installation

            More content.
        """))

        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "Project:" in context
        assert "managing tasks" in context

    def test_project_description_always_included_with_active_feature(self, tmp_path):
        """Project description should be included even when an active feature exists."""
        feature_dir = tmp_path / "docs" / "features" / "024-feature"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text(json.dumps({
            "slug": "test-feature",
            "status": "active",
            "lastCompletedPhase": "design",
        }))
        (feature_dir / "spec.md").write_text("# Spec\n\nFeature description.")

        # Create a CLAUDE.md — should now be included alongside feature signals
        (tmp_path / "CLAUDE.md").write_text(
            "## Repository Overview\n\nProject context always present.\n"
        )

        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "test-feature" in context
        assert "Project:" in context
        assert "Project context always present" in context

    def test_reads_readme_for_dev(self, tmp_path):
        """Should include README_FOR_DEV.md content in project description."""
        (tmp_path / "README_FOR_DEV.md").write_text(textwrap.dedent("""\
            # Developer Guide

            Internal developer documentation for the workflow system.

            ## Architecture

            More content.
        """))

        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "Project:" in context
        assert "workflow system" in context


class TestCollectContextCustomArtifactsRoot:
    """collect_context with custom artifacts_root config."""

    def test_finds_feature_under_custom_root(self, tmp_path):
        """Should find active feature under custom artifacts_root."""
        feature_dir = tmp_path / "custom-docs" / "features" / "024-test-feature"
        feature_dir.mkdir(parents=True)

        meta = {
            "slug": "test-feature",
            "status": "active",
            "lastCompletedPhase": "design",
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))
        (feature_dir / "spec.md").write_text("# Test\n\nCustom root feature.")

        db = MockDatabase()
        pipeline = RetrievalPipeline(
            db=db, provider=None, config={"artifacts_root": "custom-docs"}
        )

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "test-feature" in context

    def test_ignores_default_docs_with_custom_root(self, tmp_path):
        """With custom artifacts_root, features under docs/ are not found."""
        # Feature under default docs/ (should be ignored)
        feature_dir = tmp_path / "docs" / "features" / "024-default-feature"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text(json.dumps({
            "slug": "default-feature",
            "status": "active",
            "lastCompletedPhase": "design",
        }))
        (feature_dir / "spec.md").write_text("# Default\n\nShould be ignored.")

        db = MockDatabase()
        pipeline = RetrievalPipeline(
            db=db, provider=None, config={"artifacts_root": "custom-docs"}
        )

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        # No feature found under custom-docs, and git diff is empty
        assert context is None or "default-feature" not in context

    def test_custom_base_branch_skipped_in_context(self, tmp_path):
        """Custom base_branch should be added to skip set for branch filtering."""
        db = MockDatabase()
        pipeline = RetrievalPipeline(
            db=db, provider=None,
            config={"base_branch": "release"}
        )

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            def mock_run(cmd, **kwargs):
                result = mock.Mock()
                if "rev-parse" in cmd:
                    result.returncode = 0
                    result.stdout = "release"
                else:
                    result.returncode = 0
                    result.stdout = "file.py"
                return result

            mock_subprocess.run.side_effect = mock_run

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        assert "Branch:" not in context  # "release" should be skipped


class TestCollectContextWordLimit:
    """collect_context respects the 100-word limit for spec description."""

    def test_description_truncated_to_100_words(self, tmp_path):
        """Spec first paragraph should be truncated to 100 words."""
        feature_dir = tmp_path / "docs" / "features" / "024-feature"
        feature_dir.mkdir(parents=True)

        meta = {
            "slug": "long-feature",
            "status": "active",
            "lastCompletedPhase": "design",
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        # Create a spec with a very long first paragraph (150 words)
        words = ["word" + str(i) for i in range(150)]
        long_para = " ".join(words)
        spec_content = f"# Title\n\n{long_para}\n\n## Requirements\n\nMore."
        (feature_dir / "spec.md").write_text(spec_content)

        db = MockDatabase()
        pipeline = RetrievalPipeline(db=db, provider=None, config={})

        with mock.patch("semantic_memory.retrieval.subprocess") as mock_subprocess:
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_subprocess.run.return_value = mock_result

            context = pipeline.collect_context(str(tmp_path))

        assert context is not None
        # The first paragraph (before "## ") is "# Title\n\nword0 word1 ...".
        # When split by whitespace: "#", "Title", "word0" ... = 2 title words.
        # So 100-word limit gives: #, Title, word0..word97 (100 total).
        assert "word97" in context
        assert "word98" not in context
