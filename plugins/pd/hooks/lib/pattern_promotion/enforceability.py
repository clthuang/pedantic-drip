"""FR-5 enforceability filter for feature 102.

Scores text for deontic-modal density. Strong markers (must, never, etc.)
score 2 each; soft markers (should, prefer, etc.) score 1 each. Used by
the enumerate subcommand to distinguish enforceable rules from
descriptive observations.
"""
from __future__ import annotations

import re


_STRONG_MARKERS = [
    "must",
    "never",
    "always",
    "don't",
    "do not",
    "required",
    "prohibited",
    "mandatory",
]

_SOFT_MARKERS = [
    "should",
    "avoid",
    "prefer",
    "ensure",
]


def _build_pattern(markers: list[str]) -> re.Pattern[str]:
    parts = []
    for m in markers:
        escaped = re.escape(m)
        parts.append(rf"(?<![A-Za-z]){escaped}(?![A-Za-z])")
    return re.compile("|".join(parts), re.IGNORECASE)


_STRONG_RE = _build_pattern(_STRONG_MARKERS)
_SOFT_RE = _build_pattern(_SOFT_MARKERS)


def score_enforceability(text: str) -> tuple[int, list[str]]:
    """Score deontic-modal density of text.

    Returns (score, matched_markers) where score = 2 * strong_count + 1 * soft_count.
    """
    if not text:
        return 0, []

    strong_matches = [m.group(0).lower() for m in _STRONG_RE.finditer(text)]
    soft_matches = [m.group(0).lower() for m in _SOFT_RE.finditer(text)]

    score = 2 * len(strong_matches) + 1 * len(soft_matches)
    markers = strong_matches + soft_matches
    return score, markers
