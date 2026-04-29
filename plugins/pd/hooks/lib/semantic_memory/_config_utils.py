"""Shared config-resolution helpers for decay maintenance and memory refresh.

Extracted from ``maintenance.py`` (lines 65-129) and ``refresh.py`` (lines
127-184) per feature 088 FR-6.7 — eliminates duplication that was the root
cause of finding #00098 (silent divergence between the two caller modules).

Callers bind the stderr prefix and clamp-warning policy via ``functools.partial``
(see each caller's module top for the concrete binding). This keeps the
caller-visible signatures identical to their pre-088 shape so tests that
reference ``maintenance._resolve_int_config`` / ``refresh._resolve_int_config``
continue to work unchanged.

Behavior divergence (intentional, preserved across the extraction):

- ``maintenance`` passes ``prefix='[memory-decay]'`` and
  ``warn_on_clamp=True`` — stderr warning on out-of-range config clamp
  (test_maintenance.py pins this via ``assert '[memory-decay]' in captured.err``).
- ``refresh`` passes ``prefix='[refresh]'`` and ``warn_on_clamp=False`` —
  clamp is silent (test_refresh.py pins this via
  ``assert captured.err == ''`` in ``test_clamp_above_max`` / ``test_clamp_below_min``).

FR-6.6 alignment is a separate follow-up task; this extraction deliberately
preserves the existing divergence so no test regresses from Bundle A alone.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone


def _iso_utc(dt: datetime) -> str:
    """Return Z-suffix UTC ISO-8601 (``YYYY-MM-DDTHH:MM:SSZ``).

    Single source-of-truth for timestamp formatting shared by
    ``semantic_memory.maintenance`` (decay cutoffs + diagnostic ``ts``) and
    ``semantic_memory.refresh`` (diagnostic ``ts``).  Feature 088 FR-3.1
    introduced the helper in ``maintenance.py``; feature 089 FR-3.2 / AC-12
    (#00148) relocated it here to eliminate the inline
    ``strftime('%Y-%m-%dT%H:%M:%SZ')`` duplicate in ``refresh.py``.

    Feature 089 FR-1.3 / AC-3 (#00141): tz-naive datetimes are REJECTED with
    ``ValueError`` — silent fall-through previously allowed local-time values
    to be stamped as ``Z`` (UTC) and mis-compare against stored timestamps.
    """
    if dt.tzinfo is None:
        raise ValueError("_iso_utc requires timezone-aware datetime")
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# Feature 093 FR-1 (#00219, #00220): Z-suffix ISO-8601 format matching production
# `_iso_utc` output (strftime("%Y-%m-%dT%H:%M:%SZ")).
# Used symmetrically by `MemoryDatabase.scan_decay_candidates` (read path, log-and-skip)
# and `MemoryDatabase.batch_demote` (write path, raise) to validate ISO-8601 Z-suffix
# timestamps. Feature 092 shipped `\d` without `re.ASCII` which accepted Unicode digit
# codepoints (Arabic-Indic ٠١٢, Devanagari ०१२, fullwidth ０１２); 093 hardens via:
#   - `[0-9]` literal (ASCII-only, primary defense against Unicode homograph)
#   - `re.ASCII` flag (defense-in-depth against future class expansion)
#   - call sites use `.fullmatch()` instead of `.match()` to reject trailing `\n` (#00220)
#
# Feature 096 #00277: relocated here from `database.py` to co-locate with `_iso_utc`
# (the producer). Source-level pins now use `_ISO8601_Z_PATTERN.pattern` and `.flags`
# directly without `inspect.getsource()` brittleness.
_ISO8601_Z_PATTERN = re.compile(
    r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',
    re.ASCII,
)

# Convention: validators for formats produced by this module live here (see _iso_utc + _ISO8601_Z_PATTERN).


def _warn_and_default(
    key: str,
    raw,
    default: int,
    warned: set[str],
    *,
    prefix: str,
) -> int:
    """Emit one stderr warning (per-key-deduped) and return ``default``.

    Called from ``_resolve_int_config`` on any invalid-value path.  The
    caller-facing bound wrapper in each module hardcodes ``prefix`` via
    ``functools.partial`` so caller signatures stay
    ``(key, raw, default, warned)`` — identical to the pre-extraction shape.
    """
    if key not in warned:
        sys.stderr.write(
            f"{prefix} config field {key!r} value {raw!r} "
            f"is not an int; using default {default}\n"
        )
        warned.add(key)
    return default


def _resolve_int_config(
    config: dict,
    key: str,
    default: int,
    *,
    clamp: tuple[int, int] | None = None,
    warned: set[str],
    prefix: str,
    warn_on_clamp: bool,
) -> int:
    """Resolve an int-valued config field with bool rejection + dedup warning.

    Accepts ``int`` and numeric strings parseable via ``int(raw)``.  Rejects
    ``bool`` (bool-is-int-subclass trap) and ``float`` (this is the int
    variant; 5.7 is not a valid int).  Invalid values emit one stderr warning
    per key per process (via ``_warn_and_default``) and return ``default``.

    ``clamp`` — optional ``(min, max)`` tuple.  Out-of-range values are
    clamped; when ``warn_on_clamp=True`` a stderr warning is emitted (deduped
    via the same ``warned`` set as the type-rejection path), otherwise the
    clamp is silent.  The caller-facing bound wrapper in each module hardcodes
    ``prefix`` and ``warn_on_clamp`` via ``functools.partial`` so the
    caller-visible signature stays
    ``(config, key, default, *, clamp=None, warned)`` — identical to the
    pre-extraction shape.
    """
    raw = config.get(key, default)

    # Bool rejection MUST come first: bool is int subclass, isinstance(True, int)
    # is True.  Without this, True would coerce to 1.
    if isinstance(raw, bool):
        value = _warn_and_default(key, raw, default, warned, prefix=prefix)
    elif isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        try:
            value = int(raw)
        except ValueError:
            value = _warn_and_default(
                key, raw, default, warned, prefix=prefix
            )
    else:
        # float, None, list, dict, ... → reject with warning
        value = _warn_and_default(key, raw, default, warned, prefix=prefix)

    if clamp is not None:
        lo, hi = clamp
        clamped = max(lo, min(hi, value))
        if clamped != value and warn_on_clamp and key not in warned:
            sys.stderr.write(
                f"{prefix} config field {key!r} value {value} "
                f"out of range [{lo}, {hi}]; clamped to {clamped}\n"
            )
            warned.add(key)
        value = clamped
    return value
