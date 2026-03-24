"""Configuration reader for semantic memory system.

Reads config from .claude/pd.local.md, matching the bash
read_local_md_field implementation in common.sh exactly:

    grep "^${field}:" "$file" | head -1 | sed 's/^[^:]*: *//' | tr -d ' '

No YAML library -- simple line-by-line scanning of the entire file.
"""
from __future__ import annotations

import os
import re

DEFAULTS: dict[str, bool | int | float | str] = {
    "artifacts_root": "docs",
    "base_branch": "auto",
    "release_script": "",
    "backfill_scan_dirs": "",
    "activation_mode": "manual",
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
}

# Precompiled regexes for type coercion (applied after space stripping).
_RE_INT = re.compile(r"^-?[0-9]+$")
_RE_FLOAT = re.compile(r"^-?[0-9]*\.[0-9]+$")


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

    return result
