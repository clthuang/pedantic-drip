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
- ``_warn_and_default`` and ``_resolve_int_config`` share a single
  implementation at ``semantic_memory._config_utils`` (feature 088 FR-6.7);
  each caller binds its own stderr prefix (``[memory-decay]`` vs
  ``[refresh]``) and clamp-warning policy via ``functools.partial``.
"""
from __future__ import annotations

import argparse
import functools
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from semantic_memory._config_utils import (
    _resolve_int_config as _resolve_int_config_core,
    _warn_and_default as _warn_and_default_core,
)
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

# Threshold-days clamp bounds (feature 088 FR-3.2).  Widening MUST re-audit
# overflow safety: Python ``timedelta`` raises ``OverflowError`` for day counts
# above ~2.7M, and ``datetime`` subtraction can produce ``year < MINYEAR=1``.
# Any increase requires adding ``test_overflow_config_returns_error_dict``-
# style coverage.
_DAYS_MIN = 0
_DAYS_MAX = 365


def _iso_utc(dt: datetime) -> str:
    """Return Z-suffix UTC ISO-8601 (``YYYY-MM-DDTHH:MM:SSZ``).

    Single source-of-truth for timestamp formatting inside decay_confidence
    so cutoffs and ``now_iso`` compare lexicographically against stored
    ``last_recalled_at`` / ``created_at`` values written by ``merge_duplicate``
    (which uses the same Z-suffix format).  Feature 088 FR-3.1.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


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
# Config helpers (shared with refresh.py via _config_utils; prefix/clamp
# policy bound per caller via functools.partial)
# ---------------------------------------------------------------------------


# Shared config helpers bound with the maintenance caller's prefix + clamp
# policy (feature 088 FR-6.7).  Implementation lives in ``_config_utils.py``;
# ``functools.partial`` preserves the caller-visible signatures
# (``_warn_and_default(key, raw, default, warned)`` and
# ``_resolve_int_config(config, key, default, *, clamp=None, warned)``) so
# tests that reference ``maintenance._warn_and_default`` /
# ``maintenance._resolve_int_config`` continue to work unchanged.
#
# Divergence from ``refresh.py`` preserved per spec FR-8 near-identical-reuse
# contract: stderr prefix ``[memory-decay]`` and ``warn_on_clamp=True``.
_warn_and_default = functools.partial(
    _warn_and_default_core, prefix="[memory-decay]"
)
_resolve_int_config = functools.partial(
    _resolve_int_config_core, prefix="[memory-decay]", warn_on_clamp=True
)


def _emit_decay_diagnostic(diag: dict) -> None:
    """Append one JSON line to INFLUENCE_DEBUG_LOG_PATH.

    One-shot stderr warning on OSError (dedup via ``_decay_log_warned``).
    Sole write owner of ``_decay_log_warned`` per spec FR-8a.

    Pattern copied from refresh._emit_refresh_diagnostic.  Writes to the
    same filesystem path as 080/081 (re-declared constant per TD-2).
    """
    line = json.dumps({
        "ts": _iso_utc(datetime.now(timezone.utc)),
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
    *,
    scan_limit: int = 100000,
):
    """Yield decay-candidate rows (up to ``scan_limit``) — design I-2, FR-9.6.

    Single SQL query fetches a staleness superset bounded by ``LIMIT ?`` so
    unbounded scans are impossible in production (feature 088 FR-9.6,
    #00107).  Returns a generator of ``sqlite3.Row`` — callers wrap with
    ``list(...)`` and partition via ``_partition_candidates``.

    The NOT-NULL branch uses ``max(high_cutoff, med_cutoff)`` so all
    potential demotable rows are returned; the NULL branch returns every
    never-recalled row so the Python partitioner can distinguish past-grace
    (demote) from in-grace (skipped_grace) entries.

    Feature 088 FR-3.3 removed the dead ``now_iso`` parameter.
    """
    not_null_cutoff = max(high_cutoff, med_cutoff)

    cursor = db._conn.execute(
        "SELECT id, confidence, source, last_recalled_at, created_at "
        "FROM entries "
        "WHERE (last_recalled_at IS NOT NULL AND last_recalled_at < ?) "
        "   OR (last_recalled_at IS NULL) "
        "LIMIT ?",
        (not_null_cutoff, scan_limit),
    )
    for row in cursor:
        yield row


def _partition_candidates(
    rows,
    *,
    high_cutoff: str,
    med_cutoff: str,
    grace_cutoff: str,
) -> dict:
    """Partition candidate rows into per-tier buckets (design I-2).

    Extracted from ``_select_candidates`` in feature 088 (FR-9.6) so the SQL
    layer can stream rows while Python partition rules remain in one place.

    Bucket partitioning rules:
    - ``source == "import"`` → ``import_count`` (skipped)
    - ``confidence == "low"`` → ``floor_count`` (skipped, floor)
    - ``last_recalled_at IS NULL AND created_at >= grace_cutoff``
      → ``grace_count`` (skipped, grace)
    - ``confidence == "high" AND staleness_ts < high_cutoff`` → ``high_ids``
    - ``confidence == "medium" AND staleness_ts < med_cutoff`` → ``medium_ids``
    where ``staleness_ts = last_recalled_at if NOT NULL else created_at``.
    """
    high_ids: list[str] = []
    medium_ids: list[str] = []
    floor_count = 0
    import_count = 0
    grace_count = 0
    row_total = 0

    for row in rows:
        row_total += 1
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
        "scanned_total": row_total - import_count,
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
    # Declare all module-global flags mutated in this function up-front (PEP 8).
    global _decay_config_warned, _decay_error_warned
    if med_days < high_days and not _decay_config_warned:
        sys.stderr.write(
            "[memory-decay] memory_decay_medium_threshold_days "
            f"({med_days}) < memory_decay_high_threshold_days ({high_days}); "
            "medium tier will decay faster than high\n"
        )
        _decay_config_warned = True

    # Compute staleness cutoffs (Z-suffix UTC — FR-3.1).  Guard against
    # OverflowError/ValueError raised by timedelta + datetime arithmetic for
    # pathological config values (FR-3.2, AC-11) — route through the zero-
    # diagnostic error path.
    try:
        high_cutoff = _iso_utc(now - timedelta(days=high_days))
        med_cutoff = _iso_utc(now - timedelta(days=med_days))
        grace_cutoff = _iso_utc(now - timedelta(days=grace_days))
        now_iso = _iso_utc(now)
    except (OverflowError, ValueError) as exc:
        if not _decay_error_warned:
            sys.stderr.write(
                f"[memory-decay] cutoff computation overflow: "
                f"{type(exc).__name__}: {str(exc)[:200]}\n"
            )
            _decay_error_warned = True
        return {
            **_zero_diag(dry_run=dry_run),
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
        }

    # FR-9.6: bound candidate scan.  Clamp to (1000, 10_000_000) — low end
    # protects against degenerate config; high end covers realistic DB sizes
    # well above the 100k default.  Bundle G.1 later adds
    # ``memory_decay_scan_limit`` to config.DEFAULTS; until then, ``config.get``
    # falls back to 100000 here.
    scan_limit = _resolve_int_config(
        config,
        "memory_decay_scan_limit",
        100000,
        clamp=(1000, 10_000_000),
        warned=_decay_warned_fields,
    )

    try:
        rows = list(_select_candidates(
            db, high_cutoff, med_cutoff, grace_cutoff, scan_limit=scan_limit,
        ))
        candidates = _partition_candidates(
            rows,
            high_cutoff=high_cutoff,
            med_cutoff=med_cutoff,
            grace_cutoff=grace_cutoff,
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
