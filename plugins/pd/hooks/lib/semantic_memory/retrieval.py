"""Retrieval pipeline for semantic memory.

Collects session context from the project and performs hybrid retrieval
(vector similarity + BM25 keyword search), merging results into a single
RetrievalResult for downstream ranking.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING

try:
    import numpy as np
    _numpy_available = True
except ImportError:  # pragma: no cover
    _numpy_available = False

from semantic_memory.retrieval_types import CandidateScores, RetrievalResult

if TYPE_CHECKING:
    from semantic_memory.database import MemoryDatabase
    from semantic_memory.embedding import EmbeddingProvider


# Regex to extract the leading numeric ID from a feature directory name.
# e.g. "024-memory-semantic-search" -> 24
_FEATURE_ID_RE = re.compile(r"^(\d+)-")


class RetrievalPipeline:
    """Hybrid retrieval pipeline combining vector and keyword search.

    Parameters
    ----------
    db:
        The memory database instance.
    provider:
        An embedding provider, or ``None`` if embeddings are unavailable.
        When ``None``, vector retrieval is skipped (graceful degradation).
    config:
        Configuration dictionary (currently unused, reserved for future
        tuning parameters).
    """

    def __init__(
        self,
        db: MemoryDatabase,
        provider: EmbeddingProvider | None,
        config: dict,
    ) -> None:
        self._db = db
        self._provider = provider
        self._config = config
        self._artifacts_root = config.get("artifacts_root", "docs")

    # ------------------------------------------------------------------
    # Context collection
    # ------------------------------------------------------------------

    def collect_context(self, project_root: str) -> str | None:
        """Collect session context signals from the project.

        Gathers up to seven signal types:

        1. Active feature slug (from ``{artifacts_root}/features/*/.meta.json``)
        2. Feature description (first paragraph of ``spec.md`` / ``prd.md``)
        3. Current phase (``lastCompletedPhase`` from ``.meta.json``)
        4. Project-level description (``CLAUDE.md``, ``README.md``,
           ``README_FOR_DEV.md`` — always included)
        5. Current git branch name
        6. Recently changed files (committed + working tree)

        Returns a composed context string, or ``None`` if no signals
        are found.
        """
        signals: list[str] = []

        # 1. Active feature .meta.json
        meta, feature_dir = self._find_active_feature(project_root)

        if meta is not None and feature_dir is not None:
            slug = meta.get("slug", "")
            if slug:
                signals.append(slug)

            # 2. Feature description (spec.md first paragraph, max 100 words)
            description = self._read_feature_description(feature_dir)
            if description:
                signals.append(description)

            # 3. Phase
            phase = meta.get("lastCompletedPhase", "unknown")
            signals.append(f"Phase: {phase}")

        # 4. Project-level description (always included)
        project_desc = self._read_project_descriptions(project_root)
        if project_desc:
            signals.append(project_desc)

        # 5. Branch name (skip generic names that add no signal)
        base_branch = self._config.get("base_branch", "auto")
        skip_branches = {"main", "master", "develop", "HEAD"}
        if base_branch not in ("auto", ""):
            skip_branches.add(base_branch)
        branch = self._git_branch_name(project_root)
        if branch and branch not in skip_branches:
            signals.append(f"Branch: {branch}")

        # 6a. Git committed changes
        committed_files = self._git_changed_files(project_root)
        if committed_files:
            signals.append(f"Files: {' '.join(committed_files)}")

        # 6b. Working tree changes (unstaged + staged), deduplicated
        working_files = self._git_working_tree_files(project_root)
        if working_files:
            committed_set = set(committed_files) if committed_files else set()
            new_files = [f for f in working_files if f not in committed_set]
            if new_files:
                signals.append(f"Editing: {' '.join(new_files)}")

        if not signals:
            return None

        return ". ".join(signals)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, context_query: str | None) -> RetrievalResult:
        """Perform hybrid retrieval using vector and keyword search.

        Parameters
        ----------
        context_query:
            The context string to search with. If ``None``, returns an
            empty result immediately.

        Returns
        -------
        RetrievalResult
            Merged candidates with vector and/or BM25 scores populated.
        """
        if context_query is None:
            # No signals — pass all entries to ranking with zero retrieval
            # scores so prominence-only ranking can still select entries.
            all_entries = self._db.get_all_entries()
            candidates = {e["id"]: CandidateScores() for e in all_entries}
            return RetrievalResult(
                candidates=candidates,
                context_query=None,
            )

        candidates: dict[str, CandidateScores] = {}
        vector_count = 0
        fts5_count = 0

        # --- Vector retrieval ---
        if self._provider is not None and _numpy_available:
            embeddings_result = self._db.get_all_embeddings(
                expected_dims=self._provider.dimensions
            )
            if embeddings_result is not None:
                ids, matrix = embeddings_result
                query_vec = self._provider.embed(context_query, task_type="query")
                scores = matrix @ query_vec  # cosine similarity (pre-normalized)

                for i, entry_id in enumerate(ids):
                    score = float(scores[i])
                    if entry_id not in candidates:
                        candidates[entry_id] = CandidateScores()
                    candidates[entry_id].vector_score = score

                vector_count = len(ids)

        # --- Keyword retrieval ---
        if self._db.fts5_available:
            fts_results = self._db.fts5_search(context_query, limit=100)
            for entry_id, score in fts_results:
                if entry_id not in candidates:
                    candidates[entry_id] = CandidateScores()
                candidates[entry_id].bm25_score = score

            fts5_count = len(fts_results)

        return RetrievalResult(
            candidates=candidates,
            vector_candidate_count=vector_count,
            fts5_candidate_count=fts5_count,
            context_query=context_query,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_active_feature(
        self, project_root: str
    ) -> tuple[dict | None, str | None]:
        """Find the active feature with the highest numeric ID.

        Returns ``(meta_dict, feature_dir)`` or ``(None, None)`` if no
        active feature is found.
        """
        pattern = os.path.join(project_root, self._artifacts_root, "features", "*", ".meta.json")
        meta_paths = glob.glob(pattern)

        best_meta: dict | None = None
        best_dir: str | None = None
        best_id: int = -1

        for meta_path in meta_paths:
            try:
                with open(meta_path, "r") as fh:
                    meta = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                print(
                    f"semantic_memory: error parsing {meta_path}: {exc}",
                    file=sys.stderr,
                )
                continue

            # Extract numeric ID from feature directory name
            feature_dir = os.path.dirname(meta_path)
            dir_name = os.path.basename(feature_dir)
            match = _FEATURE_ID_RE.match(dir_name)
            numeric_id = int(match.group(1)) if match else -1

            if meta.get("status") != "active":
                continue

            if numeric_id > best_id:
                best_id = numeric_id
                best_meta = meta
                best_dir = feature_dir

        return best_meta, best_dir

    @staticmethod
    def _read_feature_description(feature_dir: str) -> str | None:
        """Read the first paragraph of spec.md (or prd.md), max 100 words.

        Returns ``None`` if neither file exists or is empty.
        """
        # Try spec.md first, then prd.md
        for filename in ("spec.md", "prd.md"):
            desc_path = os.path.join(feature_dir, filename)
            if os.path.isfile(desc_path):
                try:
                    with open(desc_path, "r") as fh:
                        text = fh.read()
                except OSError:
                    continue

                # First paragraph: everything before the first "## " heading
                first_para = text.split("\n## ")[0].strip()
                words = first_para.split()[:100]
                if words:
                    return " ".join(words)

        return None

    @staticmethod
    def _git_branch_name(project_root: str) -> str | None:
        """Get the current git branch name.

        Returns ``None`` on any error or when HEAD is detached.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=2,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                return branch if branch else None
        except Exception:
            pass
        return None

    @staticmethod
    def _git_working_tree_files(project_root: str) -> list[str]:
        """Get files with uncommitted changes (unstaged + staged).

        Returns up to 20 file paths, sorted and deduplicated.
        Returns an empty list on any error.
        """
        files: set[str] = set()
        for cmd in (
            ["git", "diff", "--name-only"],             # unstaged
            ["git", "diff", "--cached", "--name-only"],  # staged
        ):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=project_root,
                    timeout=2,
                )
                if result.returncode == 0 and result.stdout.strip():
                    for f in result.stdout.strip().split("\n"):
                        files.add(f)
            except Exception:
                continue
        return sorted(files)[:20]

    @staticmethod
    def _read_project_descriptions(project_root: str) -> str | None:
        """Read project-level descriptions from multiple sources.

        Reads from up to three sources (each contributing max 50 words):

        1. ``CLAUDE.md`` — ``## Repository Overview`` section
        2. ``README.md`` — first paragraph
        3. ``README_FOR_DEV.md`` — first paragraph

        Returns a combined string prefixed with ``"Project:"``, or
        ``None`` if no source provides usable content.
        """
        parts: list[str] = []

        # 1. CLAUDE.md "Repository Overview" section
        claude_md = os.path.join(project_root, "CLAUDE.md")
        if os.path.isfile(claude_md):
            try:
                with open(claude_md, "r") as fh:
                    text = fh.read()
                match = re.search(
                    r"##\s*Repository Overview\s*\n(.*?)(?=\n##|\Z)",
                    text,
                    re.DOTALL,
                )
                if match:
                    overview = match.group(1).strip()
                    words = overview.split()[:50]
                    if words:
                        parts.append(" ".join(words))
            except OSError:
                pass

        # 2. README.md first paragraph
        readme = os.path.join(project_root, "README.md")
        if os.path.isfile(readme):
            try:
                with open(readme, "r") as fh:
                    text = fh.read()
                first_para = text.split("\n## ")[0].strip()
                words = first_para.split()[:50]
                if words:
                    parts.append(" ".join(words))
            except OSError:
                pass

        # 3. README_FOR_DEV.md first paragraph
        readme_dev = os.path.join(project_root, "README_FOR_DEV.md")
        if os.path.isfile(readme_dev):
            try:
                with open(readme_dev, "r") as fh:
                    text = fh.read()
                first_para = text.split("\n## ")[0].strip()
                words = first_para.split()[:50]
                if words:
                    parts.append(" ".join(words))
            except OSError:
                pass

        if not parts:
            return None

        return f"Project: {'. '.join(parts)}"

    @staticmethod
    def _git_changed_files(project_root: str) -> list[str]:
        """Get recently changed files via git diff.

        Tries ``HEAD~3..HEAD`` first, falls back to ``HEAD~1..HEAD``,
        and returns an empty list on any error.
        """
        for ref_range in ("HEAD~3..HEAD", "HEAD~1..HEAD"):
            try:
                result = subprocess.run(
                    ["git", "diff", "--name-only", ref_range],
                    capture_output=True,
                    text=True,
                    cwd=project_root,
                    timeout=2,
                )
                if result.returncode == 0:
                    stdout = result.stdout.strip()
                    if stdout:
                        return stdout.split("\n")[:20]
                    return []
            except Exception:
                continue

        return []
