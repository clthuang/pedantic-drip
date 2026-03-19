"""Keyword generation with tiered providers for semantic memory entries.

Extracts keyword labels from knowledge bank entries using a tiered
approach: try the preferred LLM provider, fall back through cheaper
alternatives, and ultimately skip keyword generation if all tiers fail.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STOPWORD_LIST: list[str] = [
    "code", "development", "software", "system", "application",
    "implementation", "feature", "project", "function", "method",
    "file", "data", "error", "bug", "fix", "update", "change",
]

_STOPWORD_SET: frozenset[str] = frozenset(STOPWORD_LIST)

KEYWORD_PROMPT: str = (
    "Extract 3-10 keyword labels from this knowledge bank entry.\n"
    "\n"
    "Title: {name}\n"
    "Content: {description}\n"
    "Reasoning: {reasoning}\n"
    "Category: {category}\n"
    "\n"
    'Return ONLY a JSON array of lowercase keyword strings. Example: ["fts5", "sqlite", "content-hash", "parser-error"]\n'
    "\n"
    "Rules:\n"
    "- Use specific technical terms from the content (tool names, patterns, file types, techniques)\n"
    "- 1-3 words per keyword, lowercase, hyphenated if multi-word\n"
    "- EXCLUDE these generic words: code, development, software, system, application, "
    "implementation, feature, project, function, method, file, data, error, bug, fix, update, change\n"
    "- Minimum 3, maximum 10 keywords"
)

# Regex for valid keyword format: starts with alphanumeric, then
# alphanumeric or hyphens.  No underscores, spaces, or special chars.
_KEYWORD_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class KeywordGenerator(Protocol):
    """Protocol for keyword generation providers."""

    def generate(
        self,
        name: str,
        description: str,
        reasoning: str,
        category: str,
    ) -> list[str]:
        """Generate keyword labels for a knowledge bank entry.

        Returns a list of 3-10 lowercase, hyphenated keyword strings,
        or an empty list if generation is skipped/fails.
        """
        ...


# ---------------------------------------------------------------------------
# SkipKeywordGenerator (no-op / "off" mode)
# ---------------------------------------------------------------------------

class SkipKeywordGenerator:
    """No-op generator that always returns an empty list."""

    def generate(
        self,
        name: str,
        description: str,
        reasoning: str,
        category: str,
    ) -> list[str]:
        return []


# ---------------------------------------------------------------------------
# TieredKeywordGenerator
# ---------------------------------------------------------------------------


class TieredKeywordGenerator:
    """Keyword generator that tries providers in priority order.

    Walks through configured tiers until one succeeds, then validates
    and filters the returned keywords.
    """

    def __init__(self, config: dict) -> None:
        # Currently only SkipKeywordGenerator is available.
        # When real LLM providers are added, extend this mapping.
        self._tiers: list[KeywordGenerator] = [SkipKeywordGenerator()]

    def generate(
        self,
        name: str,
        description: str,
        reasoning: str,
        category: str,
    ) -> list[str]:
        """Try each tier, validate results, return 3-10 keywords or []."""
        raw_keywords: list[str] = []

        for tier in self._tiers:
            try:
                raw_keywords = tier.generate(name, description, reasoning, category)
                break  # First successful tier wins
            except Exception:
                continue

        # Validate and filter
        seen: set[str] = set()
        valid: list[str] = []
        for kw in raw_keywords:
            if kw in seen:
                continue
            seen.add(kw)
            if self._validate_keyword(kw):
                valid.append(kw)

        # Enforce 3-10 bounds
        if len(valid) < 3:
            return []
        return valid[:10]

    def _validate_keyword(self, kw: str) -> bool:
        """Check a single keyword against format regex and stopword list.

        Valid keywords must:
        - Match ^[a-z0-9][a-z0-9-]*$
        - Not be in the stopword list
        """
        if not _KEYWORD_RE.match(kw):
            return False
        if kw in _STOPWORD_SET:
            return False
        return True
