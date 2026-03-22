"""Secretary intelligence module — testable logic for secretary mode detection and entity analysis.

Functions extracted from secretary prompt logic to enable unit testing.
Implements Plan Step 2.0, AC-17 (CREATE), AC-18 (QUERY), AC-22a (weight escalation).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entity_registry.database import EntityDatabase


# ---------------------------------------------------------------------------
# Keyword sets for mode detection
# ---------------------------------------------------------------------------
_CREATE_KEYWORDS: set[str] = {
    "create", "add", "build", "implement", "start", "make", "new",
    "need", "want", "fix", "set up", "setup",
}

_QUERY_KEYWORDS: set[str] = {
    "what", "how", "where", "which", "list", "show", "find",
    "status", "progress",
}

_CONTINUE_KEYWORDS: set[str] = {
    "continue", "resume", "next", "finish",
}

# Multi-word keywords need special handling (checked before single-word)
_CREATE_MULTI: list[str] = ["set up"]

# ---------------------------------------------------------------------------
# Parent type hierarchy — maps entity type to plausible parent types
# ---------------------------------------------------------------------------
_PARENT_TYPES: dict[str, list[str]] = {
    "task": ["feature", "project", "key_result"],
    "feature": ["project", "key_result", "objective", "initiative"],
    "project": ["key_result", "objective", "initiative"],
    "key_result": ["objective", "initiative"],
    "objective": ["initiative"],
    "initiative": [],
}

# ---------------------------------------------------------------------------
# Weight signal patterns
# ---------------------------------------------------------------------------
_LIGHT_SIGNALS: list[str] = [
    "quick fix", "small", "simple", "typo", "one liner", "trivial",
    "minor", "tiny", "cosmetic",
]

_FULL_SIGNALS: list[str] = [
    "rewrite", "refactor", "breaking change", "complex", "cross-team",
    "architecture", "migration", "security", "multi-service",
]

# Scope expansion signals — indicate work is growing
_EXPANSION_STANDARD_SIGNALS: list[str] = [
    "multiple components", "needs design review", "design review",
    "needs spec", "growing scope", "more involved than expected",
    "add more", "additional features", "scope change",
]

_EXPANSION_FULL_SIGNALS: list[str] = [
    "cross-team impact", "cross-team", "breaking change", "architecture change",
    "architecture", "rewrite", "security review", "multi-service",
]


def detect_mode(request_text: str, context: dict | None) -> str:
    """Detect secretary operating mode from request text and context.

    Resolution order (AC-17):
    1. Context check — feature_branch present AND no explicit CREATE/QUERY intent
       -> CONTINUE
    2. Keyword classification — first match wins:
       - Action verbs -> CREATE
       - Question/status words -> QUERY
       - Continuation words -> CONTINUE
    3. Ambiguous -> CREATE (safe default)

    Parameters
    ----------
    request_text:
        Raw user request string.
    context:
        Dict with optional keys like ``feature_branch``. None treated as empty.

    Returns
    -------
    str
        One of "CREATE", "CONTINUE", or "QUERY".
    """
    ctx = context or {}
    text_lower = request_text.lower().strip()

    # On feature branch: check for explicit intent overrides first
    if ctx.get("feature_branch"):
        # Explicit CREATE intent — "add a task" pattern
        if _has_explicit_create_task_intent(text_lower):
            return "CREATE"
        # Explicit QUERY intent
        if _first_keyword_match(text_lower, "QUERY") == "QUERY":
            return "QUERY"
        return "CONTINUE"

    # No feature branch context — pure keyword classification
    mode = _first_keyword_match(text_lower, None)
    return mode if mode else "CREATE"  # ambiguous -> CREATE


def _has_explicit_create_task_intent(text: str) -> bool:
    """Check if text explicitly wants to create a sub-entity (task, item)."""
    # Patterns like "add a task", "create a task to track"
    return bool(re.search(r'\b(add|create|make|new)\b.*\b(task|item|entity)\b', text))


def _first_keyword_match(text: str, default: str | None) -> str | None:
    """Find the first keyword match in text, scanning left to right.

    Returns the mode string or default if nothing matches.
    """
    # Build a list of (position, mode) tuples
    matches: list[tuple[int, str]] = []

    # Multi-word CREATE keywords
    for kw in _CREATE_MULTI:
        pos = text.find(kw)
        if pos >= 0:
            matches.append((pos, "CREATE"))

    # Single-word keywords via word boundary regex
    for kw in _CREATE_KEYWORDS - set(_CREATE_MULTI):
        m = re.search(rf'\b{re.escape(kw)}\b', text)
        if m:
            matches.append((m.start(), "CREATE"))

    for kw in _QUERY_KEYWORDS:
        m = re.search(rf'\b{re.escape(kw)}\b', text)
        if m:
            matches.append((m.start(), "QUERY"))

    for kw in _CONTINUE_KEYWORDS:
        m = re.search(rf'\b{re.escape(kw)}\b', text)
        if m:
            matches.append((m.start(), "CONTINUE"))

    if not matches:
        return default

    # Sort by position, return first match's mode
    matches.sort(key=lambda x: x[0])
    return matches[0][1]


def find_parent_candidates(
    db: EntityDatabase,
    entity_type: str,
    name: str,
) -> list[dict]:
    """Search for potential parent entities using FTS5.

    Only returns entities whose type is a plausible parent for the given
    entity_type (per the type hierarchy).

    Parameters
    ----------
    db:
        EntityDatabase instance with FTS5 index.
    entity_type:
        The type of entity being created (e.g., "feature", "task").
    name:
        The name/description to search for parent matches.

    Returns
    -------
    list[dict]
        Matching entities with uuid, type_id, name, entity_type, status.
    """
    parent_types = _PARENT_TYPES.get(entity_type, [])
    if not parent_types or not name or not name.strip():
        return []

    results: list[dict] = []
    for ptype in parent_types:
        try:
            matches = db.search_entities(name, entity_type=ptype, limit=5)
            results.extend(matches)
        except ValueError:
            # FTS not available or bad query — skip
            continue

    # Deduplicate by uuid, preserve order
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in results:
        uid = r.get("uuid", "")
        if uid not in seen:
            seen.add(uid)
            deduped.append(r)

    return deduped


def check_duplicates(db: EntityDatabase, name: str) -> list[dict]:
    """Detect potential duplicate entities by name similarity.

    Uses FTS5 search across all entity types.

    Parameters
    ----------
    db:
        EntityDatabase instance.
    name:
        The name to check for duplicates.

    Returns
    -------
    list[dict]
        Matching entities with type_id, name, status, uuid.
    """
    if not name or not name.strip():
        return []

    try:
        return db.search_entities(name, limit=10)
    except ValueError:
        return []


def recommend_weight(scope_signals: list[str]) -> str:
    """Recommend workflow weight based on scope signals.

    Signal matching is case-insensitive substring matching.

    Parameters
    ----------
    scope_signals:
        List of scope descriptor strings from user context.

    Returns
    -------
    str
        One of "light", "standard", or "full".
    """
    if not scope_signals:
        return "standard"

    has_light = False
    has_full = False

    for signal in scope_signals:
        sl = signal.lower()
        for pattern in _FULL_SIGNALS:
            if pattern in sl:
                has_full = True
                break
        for pattern in _LIGHT_SIGNALS:
            if pattern in sl:
                has_light = True
                break

    if has_full:
        return "full"
    if has_light:
        return "light"
    return "standard"


def detect_scope_expansion(
    current_mode: str,
    signals: list[str],
) -> str | None:
    """Detect if scope signals indicate work has grown beyond current weight.

    Parameters
    ----------
    current_mode:
        Current weight: "light", "standard", or "full".
    signals:
        List of scope/expansion signal strings.

    Returns
    -------
    str | None
        Recommended upgraded weight, or None if no upgrade needed.
    """
    if current_mode == "full" or not signals:
        return None

    # Check for full-level expansion signals
    has_full_signal = False
    has_standard_signal = False

    for signal in signals:
        sl = signal.lower()
        for pattern in _EXPANSION_FULL_SIGNALS:
            if pattern in sl:
                has_full_signal = True
                break
        for pattern in _EXPANSION_STANDARD_SIGNALS:
            if pattern in sl:
                has_standard_signal = True
                break

    if has_full_signal:
        if current_mode in ("light", "standard"):
            return "full"

    if has_standard_signal:
        if current_mode == "light":
            return "standard"

    return None
