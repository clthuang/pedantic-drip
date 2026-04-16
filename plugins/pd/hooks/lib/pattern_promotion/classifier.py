"""Deterministic keyword classifier for KB entry -> target type.

FR-2a spec regex table. Single source of truth: patterns are compiled at
module import with `re.IGNORECASE`. A target's score is the number of
*distinct patterns* (rows) that matched at least once in the concatenated
`name + ' ' + description` string — not the total match count.

FR-2b tie-break: strictly-highest winner returned, or None (caller escalates
to LLM fallback per FR-2c).
"""
from __future__ import annotations

import re
from typing import Optional

from pattern_promotion.kb_parser import KBEntry


# ---------------------------------------------------------------------------
# Regex table (FR-2a)
# ---------------------------------------------------------------------------
# Each entry represents one "row" in the spec table; its score contribution
# is 1 if any match is found against the entry text, else 0.

_HOOK_PATTERNS = [
    r"\bPreToolUse\b",
    r"\bPostToolUse\b",
    r"\bon\s+Edit\b",
    r"\bon\s+Bash\b",
    r"\bon\s+Write\b",
    r"\bon\s+Read\b",
    r"\bon\s+Glob\b",
    r"\btool\s+input\b",
    r"\bblock\b.*\btool\b",
    r"\bprevent\b.*\bcall\b",
    r"\bintercept\b",
    r"\bvalidate\s+cron\b",
    r"\bregex\s+check\b",
    r"\bbefore\b.*\bruns\b",
]

_AGENT_PATTERNS = [
    r"\breviewer\b",
    r"\breviewing\b",
    r"\bvalidates\b",
    r"\bcatches\s+in\s+review\b",
    r"\breject\s+if\b",
    r"\bassess\b",
    r"\breview\b.*\bphase\b",
    r"\baudit\b",
]

# Gerund-form skills match existing skill directory names plus generic tokens.
_SKILL_PATTERNS = [
    r"\bimplementing\b",
    r"\bcreating\b",
    r"\bbrainstorming\b",
    r"\bspecifying\b",
    r"\bdesigning\b",
    r"\bplanning\b",
    r"\bretrospecting\b",
    r"\bresearching\b",
    r"\bsimplifying\b",
    r"\bwrap-up\b",
    r"\bfinishing\b",
    r"\bdecomposing\b",
    r"\bbreaking-down\b",
    r"\bcommitting\b",
    r"\bdebugging\b",
    r"\bdispatching\b",
    r"\bprocedure\b",
    r"\bsteps\b",
    r"\bworkflow\b",
]

_COMMAND_PATTERNS = [
    r"/[a-z][a-z-]+\s+command",
    r"\bwhen\s+user\s+runs\b",
    r"\binvokes\s+/pd:",
    r"\bslash\s+command\b",
]


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


KEYWORD_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "hook": _compile(_HOOK_PATTERNS),
    "agent": _compile(_AGENT_PATTERNS),
    "skill": _compile(_SKILL_PATTERNS),
    "command": _compile(_COMMAND_PATTERNS),
}


def classify_keywords(entry: KBEntry) -> dict[str, int]:
    """Return per-target counts of DISTINCT matched patterns."""
    text = f"{entry.name} {entry.description}"
    scores: dict[str, int] = {}
    for target, patterns in KEYWORD_PATTERNS.items():
        matched = sum(1 for pat in patterns if pat.search(text))
        scores[target] = matched
    return scores


def decide_target(scores: dict[str, int]) -> Optional[str]:
    """FR-2b: strictly-highest winner, else None (escalate to LLM fallback)."""
    if not scores:
        return None
    max_score = max(scores.values())
    if max_score == 0:
        return None
    winners = [t for t, s in scores.items() if s == max_score]
    if len(winners) == 1:
        return winners[0]
    return None
