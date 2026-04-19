"""Configuration reader for semantic memory system.

Reads config from .claude/pd.local.md, matching the bash
read_local_md_field implementation in common.sh exactly:

    grep "^${field}:" "$file" | head -1 | sed 's/^[^:]*: *//' | tr -d ' '

No YAML library -- simple line-by-line scanning of the entire file.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any

DEFAULTS: dict[str, bool | int | float | str] = {
    "artifacts_root": "docs",
    "base_branch": "auto",
    "release_script": "",
    "backfill_scan_dirs": "",
    "memory_semantic_enabled": True,
    "memory_vector_weight": 0.5,
    "memory_keyword_weight": 0.2,
    "memory_prominence_weight": 0.3,
    "memory_embedding_provider": "gemini",
    "memory_embedding_model": "gemini-embedding-001",
    "memory_model_capture_mode": "ask-first",
    "memory_silent_capture_budget": 5,
    "memory_injection_limit": 15,
    "memory_relevance_threshold": 0.3,
    "memory_dedup_threshold": 0.90,
    "memory_auto_promote": False,
    "memory_promote_low_threshold": 3,
    "memory_promote_medium_threshold": 5,
    # Feature 088 Bundle G (FR-10.1, #00102) — memory decay keys.
    # Registering defaults allows session-start to detect typos like
    # ``memory_decay_enabaled`` via ``_warn_unknown_keys``.
    "memory_decay_enabled": False,
    "memory_decay_high_threshold_days": 30,
    "memory_decay_medium_threshold_days": 60,
    "memory_decay_grace_period_days": 14,
    "memory_decay_dry_run": False,
    "memory_decay_scan_limit": 100000,
}

# Precompiled regexes for type coercion (applied after space stripping).
_RE_INT = re.compile(r"^-?[0-9]+$")
_RE_FLOAT = re.compile(r"^-?[0-9]*\.[0-9]+$")

# Feature 088 Bundle G (FR-10.1, #00096 part B) — strict boolean coercion sets.
# Only these exact values (case-sensitive) are accepted; capital variants like
# ``'False'`` / ``'True'`` are rejected with a stderr warning to surface the
# historical truthiness bug where ``'False'`` was silently treated as True.
_TRUE_VALUES: frozenset = frozenset({True, 'true', '1', 1})
_FALSE_VALUES: frozenset = frozenset({False, 'false', '0', 0, ''})


def _coerce_bool(key: str, value: Any, default: bool) -> bool:
    """Strictly coerce ``value`` to bool with fallback-on-ambiguity.

    Members of ``_TRUE_VALUES`` return True; members of ``_FALSE_VALUES``
    return False.  Any other value (e.g., ``'False'``, ``'True'``, ``'yes'``)
    is ambiguous — emit a one-line stderr warning and return ``default``.

    Feature 088 FR-10.1 / AC-34b.
    """
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    sys.stderr.write(
        f"[pd-config] {key}: ambiguous boolean {value!r}; "
        f"falling back to default={default}\n"
    )
    return default


def _warn_unknown_keys(config: dict) -> None:
    """Emit a stderr warning for each key in ``config`` not present in DEFAULTS.

    Scope filter: only keys beginning with ``memory_`` or ``pd_`` — other
    namespaces (e.g., ``yolo_mode``) are intentionally tolerated for forward
    compatibility.  Feature 088 FR-10.1 / AC-34 (e.g., typo
    ``memory_decay_enabaled``).
    """
    for key in sorted(config.keys()):
        if key in DEFAULTS:
            continue
        if not (key.startswith("memory_") or key.startswith("pd_")):
            continue
        sys.stderr.write(
            f"[pd-config] unknown key {key!r}; "
            f"did you mean one of the registered memory_*/pd_* keys?\n"
        )


def _coerce(raw: str) -> bool | int | float | str:
    """Type-coerce a raw string value after space stripping.

    Rules (matching bash read_local_md_field + tr -d ' '):
      - "true"/"false" -> bool
      - Integer pattern -> int
      - Float pattern -> float
      - Everything else -> str
    """
    if raw == "true":
        return True
    if raw == "false":
        return False
    if _RE_INT.match(raw):
        return int(raw)
    if _RE_FLOAT.match(raw):
        return float(raw)
    return raw


def read_config(project_root: str) -> dict:
    """Read config from .claude/pd.local.md.

    Matches bash read_local_md_field:
        grep "^${field}:" "$file" | head -1 | sed 's/^[^:]*: *//' | tr -d ' '

    Scans ALL lines for ^key: patterns (no --- delimiter awareness).
    Returns merged defaults + parsed values.  Missing file returns all defaults.
    """
    config_path = os.path.join(project_root, ".claude", "pd.local.md")

    # Start with a copy of defaults.
    result: dict = dict(DEFAULTS)

    if not os.path.isfile(config_path):
        return result

    # Track seen keys so we only take the first occurrence (head -1).
    seen: set[str] = set()

    with open(config_path, "r") as fh:
        for line in fh:
            # Match lines starting with a key: pattern.
            # bash: grep "^${field}:" -- we match any key.
            # Key is everything before the first colon at the start of the line.
            if not line or line[0] in (" ", "\t", "#"):
                continue

            colon_pos = line.find(":")
            if colon_pos < 1:
                continue

            key = line[:colon_pos]

            # Skip if we already saw this key (head -1 semantics).
            if key in seen:
                continue
            seen.add(key)

            # sed 's/^[^:]*: *//' -- remove key, colon, and optional leading spaces.
            raw_after_colon = line[colon_pos + 1:]
            # Strip leading spaces (sed 's/^[^:]*: *//' removes colon + leading spaces).
            raw_value = raw_after_colon.lstrip(" ")
            # Strip trailing newline.
            raw_value = raw_value.rstrip("\n").rstrip("\r")
            # tr -d ' ' -- strip ALL remaining spaces.
            raw_value = raw_value.replace(" ", "")

            # Treat empty or "null" as missing (matches bash behavior).
            if not raw_value or raw_value == "null":
                continue

            result[key] = _coerce(raw_value)

    # Feature 088 FR-10.1 / AC-34: surface typos like ``memory_decay_enabaled``
    # so operators see them at session-start instead of silently missing the
    # real key and keeping the DEFAULTS value.
    _warn_unknown_keys(result)

    return result
