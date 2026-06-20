"""Secretary intelligence module — testable logic for secretary mode detection and entity analysis.

Functions extracted from secretary prompt logic to enable unit testing.
Implements Plan Step 2.0, AC-17 (CREATE), AC-18 (QUERY), AC-22a (weight escalation).
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
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
    "cross-service", "compliance", "performance-critical", "backward compat",
]

# Scope expansion signals — indicate work is growing
_EXPANSION_STANDARD_SIGNALS: list[str] = [
    "multiple components", "needs design review", "design review",
    "needs spec", "growing scope", "more involved than expected",
    "add more", "additional features", "scope change",
    "more complex than thought", "extra requirements", "new dependency",
]

_EXPANSION_FULL_SIGNALS: list[str] = [
    "cross-team impact", "cross-team", "breaking change", "architecture change",
    "architecture", "rewrite", "security review", "multi-service",
    "cross-service", "compliance-sensitive",
]


# Synonym groups for semantic matching in signal detection.
# Each group contains words that should be treated as equivalent.
_SIGNAL_SYNONYMS: dict[str, str] = {}
_SYNONYM_GROUPS: list[list[str]] = [
    ["extra", "additional", "more"],
    ["functionality", "features", "capabilities"],
    ["complex", "complicated", "involved"],
    # Note: "change"/"update"/"modification" deliberately excluded —
    # too common in benign descriptions, causes false positives.
    ["requirement", "requirements", "dependency", "dependencies"],
]
for _group in _SYNONYM_GROUPS:
    _canonical = _group[0]
    for _word in _group:
        _SIGNAL_SYNONYMS[_word] = _canonical


def _expand_synonyms(words: set[str]) -> set[str]:
    """Expand a word set with canonical synonyms."""
    expanded = set(words)
    for w in words:
        canonical = _SIGNAL_SYNONYMS.get(w)
        if canonical:
            expanded.add(canonical)
            # Also add all synonyms from the same group
            for group in _SYNONYM_GROUPS:
                if w in group:
                    expanded.update(group)
    return expanded


def _fuzzy_signal_match(signal: str, patterns: list[str], cutoff: float = 0.6) -> bool:
    """Three-tier fuzzy matching for signal detection.

    Tier 1: Substring match (fast path — preserves all existing behavior).
    Tier 2: Word-overlap Jaccard coefficient (threshold 0.3) with synonym expansion.
    Tier 3: difflib.get_close_matches on individual words (cutoff 0.6).

    Parameters
    ----------
    signal:
        The input signal string to check.
    patterns:
        List of known signal patterns to match against.
    cutoff:
        Similarity cutoff for difflib matching (default 0.6).

    Returns
    -------
    bool
        True if the signal matches any pattern.
    """
    sl = signal.lower()

    # Tier 1: Substring (preserves all existing behavior)
    for pattern in patterns:
        if pattern in sl:
            return True

    # Tier 2: Word-overlap Jaccard on tokenized words (with synonym expansion)
    signal_words = set(re.findall(r'[a-z]+', sl))
    if not signal_words:
        return False

    expanded_signal = _expand_synonyms(signal_words)

    for pattern in patterns:
        pattern_words = set(re.findall(r'[a-z]+', pattern.lower()))
        if not pattern_words:
            continue
        expanded_pattern = _expand_synonyms(pattern_words)
        intersection = expanded_signal & expanded_pattern
        union = expanded_signal | expanded_pattern
        # Require ≥2 words in intersection to avoid single-word false positives
        # (e.g., "trivial change" matching "breaking change" via shared "change")
        if len(intersection) >= 2 and len(intersection) / len(union) >= 0.3:
            return True

    # Tier 3: difflib near-matches on individual words
    # Only match words of similar length (±2 chars) to avoid
    # spurious matches like "multi" ↔ "multiple" or "compliance" ↔ "components"
    all_pattern_words = []
    for pattern in patterns:
        all_pattern_words.extend(re.findall(r'[a-z]+', pattern.lower()))
    all_pattern_words = list(set(all_pattern_words))  # deduplicate

    # For each pattern, check if the signal has a near-miss (typo) match
    # on at least one word AND shares at least one exact word with that pattern.
    # This catches "archtecture change" matching "architecture change"
    # (typo on "archtecture" + exact "change") without false-positives
    # from unrelated signals that happen to share one common word.
    for pattern in patterns:
        pattern_words = set(re.findall(r'[a-z]+', pattern.lower()))
        if not pattern_words:
            continue

        # Check for at least 1 exact word overlap
        exact_overlap = signal_words & pattern_words
        if not exact_overlap:
            continue

        # Check for at least 1 near-miss (typo) on a different word
        has_typo_match = False
        for word in signal_words:
            if word in exact_overlap:
                continue  # skip exact matches
            if len(word) < 5:
                continue
            candidates = [pw for pw in pattern_words if abs(len(pw) - len(word)) <= 2 and pw != word]
            close = difflib.get_close_matches(word, candidates, n=1, cutoff=cutoff)
            if close:
                has_typo_match = True
                break

        if has_typo_match:
            return True

    return False


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
        if _fuzzy_signal_match(signal, _FULL_SIGNALS):
            has_full = True
        if _fuzzy_signal_match(signal, _LIGHT_SIGNALS):
            has_light = True

    if has_full:
        return "full"
    if has_light:
        return "light"
    return "standard"


# ---------------------------------------------------------------------------
# OKR anti-pattern detection (AC-33)
# ---------------------------------------------------------------------------
_ACTIVITY_WORDS: list[str] = [
    "launch", "build", "implement", "create", "deploy",
    "migrate", "develop", "ship", "release", "complete",
]

_ACTIVITY_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in _ACTIVITY_WORDS) + r')\b',
    re.IGNORECASE,
)

_KR_COUNT_MAX = 5


def detect_activity_kr(text: str) -> str | None:
    """Check KR text for activity-word anti-patterns.

    Activity words indicate the KR describes an output (what to do) rather
    than an outcome (what to achieve).  Returns a warning message or None.

    Implements AC-33 (OKR Anti-Pattern Detection).

    Parameters
    ----------
    text:
        The key result description text to check.

    Returns
    -------
    str | None
        Warning message if an activity word is found, else None.
    """
    if not text or not text.strip():
        return None

    match = _ACTIVITY_PATTERN.search(text)
    if match:
        word = match.group(1)
        return (
            f"This looks like an output, not an outcome (found '{word}'). "
            "Consider reframing as a measurable result."
        )
    return None


def check_kr_count(db: "EntityDatabase", objective_uuid: str) -> str | None:
    """Check if an objective has more than the recommended max KR count.

    Only non-abandoned key_result children count toward the limit.

    Implements AC-33 (OKR Anti-Pattern Detection).

    Parameters
    ----------
    db:
        EntityDatabase instance for data access.
    objective_uuid:
        UUID of the objective entity to check.

    Returns
    -------
    str | None
        Warning message if KR count exceeds max, else None.
    """
    children = db.get_children_by_uuid(objective_uuid)
    if not children:
        return None

    active_krs = [
        c for c in children
        if c.get("entity_type") == "key_result"
        and c.get("status") != "abandoned"
    ]

    if len(active_krs) > _KR_COUNT_MAX:
        return (
            f"Objective has {len(active_krs)} KRs. "
            f"Consider reducing KR count. Recommended max: {_KR_COUNT_MAX}."
        )
    return None


def get_parent_context(db: "EntityDatabase", parent_type_id: str) -> dict | None:
    """Fetch parent entity context for Catchball display during child creation.

    Returns a dict with parent info including workflow phase and progress,
    or None if the parent entity doesn't exist.

    Implements AC-35a (Catchball — parent intent on creation).

    Parameters
    ----------
    db:
        EntityDatabase instance for data access.
    parent_type_id:
        The type_id of the parent entity (e.g., "project:003-platform").

    Returns
    -------
    dict | None
        Dict with keys: type_id, name, phase, progress, traffic_light.
        None if parent entity not found.
    """
    entity = db.get_entity(parent_type_id)
    if entity is None:
        return None

    # Extract workflow phase
    phase = None
    wp = db.get_workflow_phase(parent_type_id)
    if wp is not None:
        phase = wp.get("workflow_phase")

    # Extract progress from metadata
    progress = None
    if entity.get("metadata"):
        try:
            import json
            meta = json.loads(entity["metadata"]) if isinstance(entity["metadata"], str) else entity["metadata"]
            progress = meta.get("progress")
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    # Compute traffic light from progress
    traffic_light = None
    if progress is not None:
        if progress >= 70:
            traffic_light = "GREEN"
        elif progress >= 40:
            traffic_light = "YELLOW"
        else:
            traffic_light = "RED"

    return {
        "type_id": parent_type_id,
        "name": entity["name"],
        "phase": phase,
        "progress": progress,
        "traffic_light": traffic_light,
    }


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
        if _fuzzy_signal_match(signal, _EXPANSION_FULL_SIGNALS):
            has_full_signal = True
        if _fuzzy_signal_match(signal, _EXPANSION_STANDARD_SIGNALS):
            has_standard_signal = True

    if has_full_signal:
        if current_mode in ("light", "standard"):
            return "full"

    if has_standard_signal:
        if current_mode == "light":
            return "standard"

    return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
# Wires the logic above into ``/pd:secretary`` via
# ``python -m workflow_engine.secretary_intelligence <subcommand>``. Every
# subcommand emits exactly one JSON line on stdout. The four entity-aware
# subcommands open the entity registry via ``ENTITY_DB_PATH`` (default
# ``~/.claude/pd/entities/entities.db``); the four pure-text subcommands need
# no database. Errors are surfaced as ``{"error": ...}`` JSON, never tracebacks,
# so the calling command can parse stdout unconditionally.


def _emit(obj: object) -> None:
    """Write one JSON line to stdout (``default=str`` for Path/UUID safety)."""
    json.dump(obj, sys.stdout, default=str)
    sys.stdout.write("\n")


def _parse_json_list(raw: str, flag: str) -> list:
    """Parse a JSON-array CLI argument; emit a JSON error + exit(2) on failure."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit({"error": f"invalid {flag} JSON: {exc}"})
        sys.exit(2)
    if not isinstance(value, list):
        _emit({"error": f"{flag} must be a JSON array"})
        sys.exit(2)
    return value


def _open_db():
    """Open the entity registry honoring ``ENTITY_DB_PATH`` (see CLAUDE.md)."""
    from entity_registry.database import EntityDatabase

    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/pd/entities/entities.db"),
    )
    return EntityDatabase(db_path)


def _with_db(handler) -> None:
    """Open the DB, run ``handler(db)``, emit its result, always close.

    Open failures and handler failures both surface as ``{"error": ...}`` with
    a non-zero exit so the caller never sees a raw traceback on stdout.
    """
    try:
        db = _open_db()
    except Exception as exc:  # noqa: BLE001 — surface as JSON, never a traceback
        _emit({"error": f"cannot open database: {exc}"})
        sys.exit(1)
    try:
        _emit(handler(db))
    except Exception as exc:  # noqa: BLE001
        _emit({"error": f"handler failed: {exc}"})
        sys.exit(1)
    finally:
        db.close()


def _cmd_detect_mode(args) -> None:
    try:
        context = json.loads(args.context)
    except json.JSONDecodeError as exc:
        _emit({"error": f"invalid --context JSON: {exc}"})
        sys.exit(2)
    _emit({"mode": detect_mode(args.text, context)})


def _cmd_recommend_weight(args) -> None:
    _emit({"weight": recommend_weight(_parse_json_list(args.signals, "--signals"))})


def _cmd_detect_activity_kr(args) -> None:
    _emit({"warning": detect_activity_kr(args.text)})


def _cmd_scope_expansion(args) -> None:
    signals = _parse_json_list(args.signals, "--signals")
    _emit({"upgrade": detect_scope_expansion(args.current_mode, signals)})


def _cmd_find_parents(args) -> None:
    _with_db(
        lambda db: {
            "candidates": find_parent_candidates(db, args.entity_type, args.name)
        }
    )


def _cmd_check_duplicates(args) -> None:
    _with_db(lambda db: {"duplicates": check_duplicates(db, args.name)})


def _cmd_check_okr(args) -> None:
    _with_db(lambda db: {"warning": check_kr_count(db, args.objective_uuid)})


def _cmd_parent_context(args) -> None:
    _with_db(lambda db: {"context": get_parent_context(db, args.parent_type_id)})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="secretary_intelligence",
        description="Secretary routing intelligence (JSON-emitting subcommands).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("detect-mode", help="Classify a request as CREATE/CONTINUE/QUERY.")
    p.add_argument("--text", required=True)
    p.add_argument(
        "--context",
        default="{}",
        help='JSON object, e.g. \'{"feature_branch":"feature/x"}\'.',
    )
    p.set_defaults(func=_cmd_detect_mode)

    p = sub.add_parser("recommend-weight", help="Recommend light/standard/full from scope signals.")
    p.add_argument("--signals", required=True, help="JSON array of signal strings.")
    p.set_defaults(func=_cmd_recommend_weight)

    p = sub.add_parser("detect-activity-kr", help="Flag the activity-word OKR anti-pattern in KR text.")
    p.add_argument("--text", required=True)
    p.set_defaults(func=_cmd_detect_activity_kr)

    p = sub.add_parser("scope-expansion", help="Recommend a weight upgrade from expansion signals.")
    p.add_argument("--current-mode", required=True, choices=["light", "standard", "full"])
    p.add_argument("--signals", required=True, help="JSON array of signal strings.")
    p.set_defaults(func=_cmd_scope_expansion)

    p = sub.add_parser("find-parents", help="Search the entity registry for plausible parents.")
    p.add_argument("--entity-type", required=True)
    p.add_argument("--name", required=True)
    p.set_defaults(func=_cmd_find_parents)

    p = sub.add_parser("check-duplicates", help="Search the entity registry for duplicate names.")
    p.add_argument("--name", required=True)
    p.set_defaults(func=_cmd_check_duplicates)

    p = sub.add_parser("check-okr", help="Warn if an objective exceeds the recommended KR count.")
    p.add_argument("--objective-uuid", required=True)
    p.set_defaults(func=_cmd_check_okr)

    p = sub.add_parser("parent-context", help="Fetch parent entity context for catchball display.")
    p.add_argument("--parent-type-id", required=True)
    p.set_defaults(func=_cmd_parent_context)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
