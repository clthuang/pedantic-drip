"""Configuration reader for the pd plugin.

Reads config from .claude/pd.local.md, matching the bash
read_local_md_field implementation in common.sh exactly:

    grep "^${field}:" "$file" | head -1 | sed 's/^[^:]*: *//' | tr -d ' '

No YAML library -- simple line-by-line scanning of the entire file.

This module is intentionally self-contained (stdlib only) so that the
entity registry, workflow engine, and doctor can resolve core project
configuration (artifacts_root, base_branch, release_script) without
pulling in any optional subsystem.
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
}

# Precompiled regexes for type coercion (applied after space stripping).
_RE_INT = re.compile(r"^-?[0-9]+$")
_RE_FLOAT = re.compile(r"^-?[0-9]*\.[0-9]+$")


def _coerce_bool(key: str, value: Any, default: bool) -> bool:
    """Strictly coerce ``value`` to bool with fallback-on-ambiguity.

    Type-exact acceptance (no frozenset ``in`` membership):

    - True iff ``value is True`` OR (``value`` is ``str`` AND ``value == 'true'``)
      OR (``value`` is ``int`` AND not ``bool`` AND ``value == 1``).
    - False iff ``value is False`` OR (``value`` is ``str`` AND ``value == 'false'``
      OR ``value == ''``) OR (``value`` is ``int`` AND not ``bool`` AND
      ``value == 0``).
    - Everything else (``'False'``, ``'TRUE'``, ``'yes'``, ``1.0``, ...) is
      ambiguous -- emit a one-line stderr warning and return ``default``.
    """
    # True branch (type-exact).
    if value is True:
        return True
    if isinstance(value, str) and value == 'true':
        return True
    if isinstance(value, int) and not isinstance(value, bool) and value == 1:
        return True

    # False branch (type-exact).
    if value is False:
        return False
    if isinstance(value, str) and (value == 'false' or value == ''):
        return False
    if isinstance(value, int) and not isinstance(value, bool) and value == 0:
        return False

    sys.stderr.write(
        f"[pd-config] {key}: ambiguous boolean {value!r}; "
        f"falling back to default={default}\n"
    )
    return default


def _warn_unknown_keys(config: dict) -> None:
    """Emit a stderr warning for each ``pd_``-prefixed key not in DEFAULTS.

    Scope filter: only keys beginning with ``pd_`` -- other namespaces
    (e.g., ``yolo_mode``, ``secretary_*``) are intentionally tolerated for
    forward compatibility.
    """
    for key in sorted(config.keys()):
        if key in DEFAULTS:
            continue
        if not key.startswith("pd_"):
            continue
        sys.stderr.write(
            f"[pd-config] unknown key {key!r}; "
            f"did you mean one of the registered pd_* keys?\n"
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
            raw_value = raw_after_colon.lstrip(" ")
            # Strip trailing newline.
            raw_value = raw_value.rstrip("\n").rstrip("\r")
            # tr -d ' ' -- strip ALL remaining spaces.
            raw_value = raw_value.replace(" ", "")

            # Treat empty or "null" as missing (matches bash behavior).
            if not raw_value or raw_value == "null":
                continue

            default_value = DEFAULTS.get(key)
            if isinstance(default_value, bool):
                result[key] = _coerce_bool(key, raw_value, default_value)
            else:
                result[key] = _coerce(raw_value)

    _warn_unknown_keys(result)

    return result
