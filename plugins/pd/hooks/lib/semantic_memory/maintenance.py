"""Confidence-decay maintenance job (Feature 082).

Implements the ``decay_confidence`` public function plus private helpers for
per-tier demotion of stale memory entries per spec FR-1 / FR-2 / FR-5.

Entry points:
- ``decay_confidence(db, config, *, now=None)`` — programmatic API used by
  session-start (via ``_main``) and by tests directly.
- ``_main()`` — CLI entry exposed as ``python -m semantic_memory.maintenance``.

Module-level state is per-process (matches refresh.py / memory_server.py
pattern). Dedup flags persist across invocations within a single process —
see spec FR-8a for the authoritative write-owner / reset-policy table.

Cross-reference to 081 (refresh.py):
- ``_warn_and_default`` and ``_resolve_int_config`` mirror refresh.py:127-183
  verbatim; only the stderr prefix differs (``[memory-decay]`` vs
  ``[refresh]``) per spec FR-8 near-identical-reuse contract.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from semantic_memory.database import MemoryDatabase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Re-declared per TD-2 (see design.md) + spec FR-7 — NOT imported from
# refresh.py.  The two modules run in the same process at CLI runtime but
# tests monkeypatch this symbol directly on the ``maintenance`` module, so
# sharing one binding would cause cross-test pollution.
INFLUENCE_DEBUG_LOG_PATH: Path = (
    Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"
)

# ---------------------------------------------------------------------------
# Module-level dedup state (per-process)
#
# Write ownership per spec FR-8a:
# - _decay_warned_fields : written by _resolve_int_config
# - _decay_config_warned : written by decay_confidence (semantic-coupling)
# - _decay_log_warned    : written by _emit_decay_diagnostic on OSError
# - _decay_error_warned  : written by decay_confidence's except handler
# ---------------------------------------------------------------------------

_decay_warned_fields: set[str] = set()
_decay_config_warned: bool = False
_decay_log_warned: bool = False
_decay_error_warned: bool = False


# ---------------------------------------------------------------------------
# Stubs — implementations land in Phase 1/3 tasks (TDD red→green).
# ---------------------------------------------------------------------------


def _warn_and_default(key: str, raw, default: int, warned: set[str]) -> int:
    """Emit one stderr warning (per-key-deduped) and return ``default``.

    Called from ``_resolve_int_config`` on any invalid-value path.  Mirrors
    refresh.py:127-140 verbatim; only the stderr prefix differs
    (``[memory-decay]`` vs ``[refresh]``) per spec FR-8.
    """
    if key not in warned:
        sys.stderr.write(
            f"[memory-decay] config field {key!r} value {raw!r} "
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
) -> int:
    """Resolve an int-valued config field with bool rejection + dedup warning.

    Body mirrors refresh._resolve_int_config (refresh.py:143-183) verbatim —
    spec FR-8 near-identical reuse contract.  Only stderr prefix differs
    (``[memory-decay]`` via ``_warn_and_default`` copy).

    Accepts ``int`` and numeric strings parseable via ``int(raw)``.  Rejects
    ``bool`` (bool-is-int-subclass trap) and ``float`` (this is the int
    variant; 5.7 is not a valid int).

    ``clamp`` — optional ``(min, max)`` tuple.  Out-of-range values are
    clamped SILENTLY (no warning) — operator-tuned values get corrected.
    """
    raw = config.get(key, default)

    # Bool rejection MUST come first: bool is int subclass, isinstance(True, int)
    # is True.  Without this, True would coerce to 1.
    if isinstance(raw, bool):
        value = _warn_and_default(key, raw, default, warned)
    elif isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        try:
            value = int(raw)
        except ValueError:
            value = _warn_and_default(key, raw, default, warned)
    else:
        # float, None, list, dict, ... → reject with warning
        value = _warn_and_default(key, raw, default, warned)

    if clamp is not None:
        lo, hi = clamp
        clamped = max(lo, min(hi, value))
        if clamped != value and key not in warned:
            sys.stderr.write(
                f"[memory-decay] config field {key!r} value {value} "
                f"out of range [{lo}, {hi}]; clamped to {clamped}\n"
            )
            warned.add(key)
        value = clamped
    return value


def _emit_decay_diagnostic(diag: dict) -> None:
    """Append one JSON line to INFLUENCE_DEBUG_LOG_PATH.

    One-shot stderr warning on OSError (dedup via ``_decay_log_warned``).
    Sole write owner of ``_decay_log_warned`` per spec FR-8a.

    Pattern copied from refresh._emit_refresh_diagnostic.  Writes to the
    same filesystem path as 080/081 (re-declared constant per TD-2).
    """
    line = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": "memory_decay",
        "scanned": diag["scanned"],
        "demoted_high_to_medium": diag["demoted_high_to_medium"],
        "demoted_medium_to_low": diag["demoted_medium_to_low"],
        "skipped_floor": diag["skipped_floor"],
        "skipped_import": diag["skipped_import"],
        "skipped_grace": diag["skipped_grace"],
        "elapsed_ms": diag["elapsed_ms"],
        "dry_run": diag["dry_run"],
    })
    try:
        # mkdir MUST be inside try/except so both "parent is a file" errors
        # and "path is a directory" errors (AC-19 monkeypatch) are caught.
        # OSError covers IsADirectoryError, PermissionError, FileNotFoundError,
        # and IOError (alias in Python 3).
        INFLUENCE_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with INFLUENCE_DEBUG_LOG_PATH.open("a") as f:
            f.write(line + "\n")
    except OSError as e:
        global _decay_log_warned
        if not _decay_log_warned:
            sys.stderr.write(f"[memory-decay] log write failed: {e}\n")
            _decay_log_warned = True


def _build_summary_line(diag: dict) -> str:
    """Build the ASCII-only summary line for session-start stdout.

    Per spec FR-4, format (ASCII, no Unicode arrows):
      'Decay: demoted high->medium: X, medium->low: Y (dry-run: false)'
      'Decay (dry-run): would demote high->medium: X, medium->low: Y'

    Returns empty string if nothing changed AND not dry-run (silent no-op).
    """
    h = diag["demoted_high_to_medium"]
    m = diag["demoted_medium_to_low"]

    if diag["dry_run"]:
        if h == 0 and m == 0:
            return ""  # dry-run with no candidates → silent
        return f"Decay (dry-run): would demote high->medium: {h}, medium->low: {m}"

    if h == 0 and m == 0:
        return ""  # normal run with no demotions → silent
    return f"Decay: demoted high->medium: {h}, medium->low: {m} (dry-run: false)"


def _select_candidates(
    db: MemoryDatabase,
    high_cutoff: str,
    med_cutoff: str,
    grace_cutoff: str,
    now_iso: str,
) -> dict:
    """SELECT decay candidates per tier + count skips (design I-2).

    Single SQL query fetches a staleness superset; Python partitions into
    per-tier buckets.  The NOT-NULL branch uses ``max(high_cutoff, med_cutoff)``
    so all potential demotable rows are returned; the NULL branch uses
    ``grace_cutoff`` so never-recalled rows past the grace window are included.

    Bucket partitioning rules:
    - ``source == "import"`` → ``import_count`` (skipped)
    - ``confidence == "low"`` → ``floor_count`` (skipped, floor)
    - ``last_recalled_at IS NULL AND created_at >= grace_cutoff``
      → ``grace_count`` (skipped, grace)
    - ``confidence == "high" AND staleness_ts < high_cutoff`` → ``high_ids``
    - ``confidence == "medium" AND staleness_ts < med_cutoff`` → ``medium_ids``
    where ``staleness_ts = last_recalled_at if NOT NULL else created_at``.
    """
    # NOT-NULL branch: use the later (less restrictive) cutoff so we get
    # rows potentially demotable under either the high OR medium threshold.
    # NULL branch: return ALL never-recalled rows so Python-side partition
    # can distinguish past-grace candidates (-> demote) from in-grace rows
    # (-> grace_count).  Spec FR-7 requires skipped_grace in the diagnostic.
    not_null_cutoff = max(high_cutoff, med_cutoff)

    cursor = db._conn.execute(
        "SELECT id, confidence, source, last_recalled_at, created_at "
        "FROM entries "
        "WHERE (last_recalled_at IS NOT NULL AND last_recalled_at < ?) "
        "   OR (last_recalled_at IS NULL)",
        (not_null_cutoff,),
    )
    rows = cursor.fetchall()

    high_ids: list[str] = []
    medium_ids: list[str] = []
    floor_count = 0
    import_count = 0
    grace_count = 0

    for row in rows:
        entry_id = row["id"]
        confidence = row["confidence"]
        source = row["source"]
        last_recalled = row["last_recalled_at"]
        created = row["created_at"]

        # Source filter first: import rows are always skipped regardless of tier.
        if source == "import":
            import_count += 1
            continue

        # Floor filter: low never decays further.
        if confidence == "low":
            floor_count += 1
            continue

        # Grace filter: never-recalled rows still inside grace window are skipped.
        if last_recalled is None and created >= grace_cutoff:
            grace_count += 1
            continue

        staleness_ts = last_recalled if last_recalled is not None else created

        if confidence == "high" and staleness_ts < high_cutoff:
            high_ids.append(entry_id)
        elif confidence == "medium" and staleness_ts < med_cutoff:
            medium_ids.append(entry_id)

    return {
        "high_ids": high_ids,
        "medium_ids": medium_ids,
        "floor_count": floor_count,
        "import_count": import_count,
        "grace_count": grace_count,
        "scanned_total": len(rows) - import_count,
    }


def _zero_diag(*, dry_run: bool) -> dict:
    """Build a zero-valued diagnostic dict for the disabled / no-op paths.

    Shape matches the FR-1 authoritative dict (minus ``error`` key which is
    added only on the sqlite3.Error branch) + ``elapsed_ms`` set to 0 so
    downstream summary-line code can rely on its presence.
    """
    return {
        "scanned": 0,
        "demoted_high_to_medium": 0,
        "demoted_medium_to_low": 0,
        "skipped_floor": 0,
        "skipped_import": 0,
        "skipped_grace": 0,
        "elapsed_ms": 0,
        "dry_run": dry_run,
    }


def decay_confidence(
    db: MemoryDatabase,
    config: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Demote confidence one tier for entries unobserved past thresholds.

    See spec FR-1 / FR-2 / FR-5 for the policy and UPDATE contract;
    design I-1 for the authoritative call flow.  Never raises for config /
    DB / IO errors — returns a diagnostic dict with ``"error"`` key appended
    on sqlite3.Error.  TypeError on non-datetime ``now`` IS propagated
    (caller bug per spec FR-8).
    """
    t0 = time.perf_counter()

    # NFR-3 zero-overhead: read flag FIRST, before anything else.
    if not config.get("memory_decay_enabled", False):
        return _zero_diag(dry_run=False)

    # Validate `now` kwarg (spec FR-8).
    if now is None:
        now = datetime.now(timezone.utc)
    elif not isinstance(now, datetime):
        raise TypeError(
            f"now must be datetime, got {type(now).__name__}"
        )
    # Normalize to UTC to prevent false-positive demotions from SQLite's
    # lexicographic string comparison on ISO-8601 timestamps with different
    # timezone offsets (adversarial QA finding #1).
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc)

    # Resolve config via shared helper (bool-reject + clamp + dedup-warn).
    high_days = _resolve_int_config(
        config,
        "memory_decay_high_threshold_days",
        30,
        clamp=(1, 365),
        warned=_decay_warned_fields,
    )
    med_days = _resolve_int_config(
        config,
        "memory_decay_medium_threshold_days",
        60,
        clamp=(1, 365),
        warned=_decay_warned_fields,
    )
    grace_days = _resolve_int_config(
        config,
        "memory_decay_grace_period_days",
        14,
        clamp=(0, 365),
        warned=_decay_warned_fields,
    )
    dry_run = bool(config.get("memory_decay_dry_run", False))

    # Semantic-coupling warning (spec FR-3 / AC-14) — dedup via module flag.
    global _decay_config_warned
    if med_days < high_days and not _decay_config_warned:
        sys.stderr.write(
            "[memory-decay] memory_decay_medium_threshold_days "
            f"({med_days}) < memory_decay_high_threshold_days ({high_days}); "
            "medium tier will decay faster than high\n"
        )
        _decay_config_warned = True

    # Compute staleness cutoffs.
    high_cutoff = (now - timedelta(days=high_days)).isoformat()
    med_cutoff = (now - timedelta(days=med_days)).isoformat()
    grace_cutoff = (now - timedelta(days=grace_days)).isoformat()
    now_iso = now.isoformat()

    try:
        candidates = _select_candidates(
            db, high_cutoff, med_cutoff, grace_cutoff, now_iso
        )

        diag = {
            "scanned": candidates["scanned_total"],
            "demoted_high_to_medium": 0,
            "demoted_medium_to_low": 0,
            "skipped_floor": candidates["floor_count"],
            "skipped_import": candidates["import_count"],
            "skipped_grace": candidates["grace_count"],
            "dry_run": dry_run,
        }

        if not dry_run:
            # Atomic: batch_demote opens BEGIN IMMEDIATE, chunks, commits.
            if candidates["high_ids"]:
                diag["demoted_high_to_medium"] = db.batch_demote(
                    candidates["high_ids"], "medium", now_iso
                )
            if candidates["medium_ids"]:
                diag["demoted_medium_to_low"] = db.batch_demote(
                    candidates["medium_ids"], "low", now_iso
                )
        else:
            # Dry-run: populate counts without UPDATE.
            diag["demoted_high_to_medium"] = len(candidates["high_ids"])
            diag["demoted_medium_to_low"] = len(candidates["medium_ids"])

    except sqlite3.Error as e:
        global _decay_error_warned
        if not _decay_error_warned:
            sys.stderr.write(
                f"[memory-decay] DB error during decay: {e}\n"
            )
            _decay_error_warned = True
        return {**_zero_diag(dry_run=dry_run), "error": str(e)}
    # NOTE: batch_demote raises ValueError for invalid new_confidence.
    # decay_confidence only ever passes 'medium' or 'low' — if ValueError
    # fires, it signals a bug in this function (not a user-facing error).
    # We intentionally let it propagate; tests catch it. FR-8's "never
    # propagate" invariant applies to config / DB / IO errors only.

    diag["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)

    # FR-7 diagnostic emission (zero-overhead short-circuit per NFR-3).
    if config.get("memory_influence_debug", False):
        _emit_decay_diagnostic(diag)

    return diag


def _main() -> None:
    """CLI entry exposed as ``python -m semantic_memory.maintenance``.

    Per design I-6: parse --decay / --project-root / --dry-run; resolve
    project root; read config; short-circuit (NFR-3) BEFORE opening the DB
    when memory_decay_enabled is False so fresh-system session-start never
    creates memory.db purely for decay.  On success, prints the summary line
    to stdout and exits 0.  Any failure → no stdout, exits non-zero,
    stderr suppressed by session-start's 2>/dev/null guard.
    """
    # Local import avoids elevating config.read_config to a hard module-level
    # dep (aligns with refresh.py's pattern of importing read_config only
    # from the CLI entry, not the library function).
    from semantic_memory.config import read_config

    parser = argparse.ArgumentParser(prog="semantic_memory.maintenance")
    parser.add_argument(
        "--decay",
        action="store_true",
        help="Run confidence decay pass",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Override config discovery root",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run (overrides memory_decay_dry_run config)",
    )
    args = parser.parse_args()

    if not args.decay:
        parser.print_usage()
        sys.exit(0)

    # Resolve project-root → config.  .resolve() normalizes + resolves
    # symlinks per spec FR-9.
    project_root = (
        Path(args.project_root).resolve()
        if args.project_root
        else Path.cwd().resolve()
    )
    if not project_root.is_dir():
        sys.exit(1)  # silent exit; session-start sees empty summary

    # read_config takes the project root DIRECTORY (str), not a file path.
    config = read_config(str(project_root))
    if args.dry_run:
        config["memory_decay_dry_run"] = True

    # NFR-3 zero-overhead at the PROCESS level: short-circuit BEFORE
    # MemoryDatabase(db_path) so a fresh-system session-start never creates
    # memory.db purely for decay.
    if not config.get("memory_decay_enabled", False):
        sys.exit(0)

    db_path = str(
        Path.home() / ".claude" / "pd" / "memory" / "memory.db"
    )
    db = MemoryDatabase(db_path)

    try:
        diag = decay_confidence(db, config)
        summary = _build_summary_line(diag)
        if summary:
            print(summary)
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    _main()
