"""Shared memory refresh helper module (Feature 081).

Extracted retrieval + ranking + serialization logic used by both
``memory_server.py`` (via ``hybrid_retrieve``) and ``workflow_state_server.py``
(via ``refresh_memory_digest``, added in Phase 3).

Module-level state is per-process (each MCP subprocess gets its own copy —
the two servers run as separate stdio subprocesses, so dedup is always
scoped to a single process).

Phase 1 public surface:
- ``build_refresh_query`` — slug+phase → query string (or None on mismatch).
- ``hybrid_retrieve`` — thin wrapper over RetrievalPipeline + RankingEngine,
  used by both servers to keep ranking parity structural.

Phase 1 internals:
- ``_resolve_int_config`` — int config resolver with bool/float rejection +
  one-shot dedup warning (int-variant of the shared float helper at
  ``semantic_memory.config_utils.resolve_float_config``).
- ``_emit_refresh_diagnostic`` — appends a JSON line to
  ``INFLUENCE_DEBUG_LOG_PATH`` (reused from 080; duplicated constant to
  avoid cross-subprocess import).
- ``_serialize_entries`` — 240-char description truncation + UTF-8 byte cap
  at 2000 bytes via drop-from-end.

Phase 3 will add ``refresh_memory_digest`` as the public entry that combines
the helpers here.
"""
from __future__ import annotations

import functools
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from semantic_memory._config_utils import (
    _resolve_int_config as _resolve_int_config_core,
    _warn_and_default as _warn_and_default_core,
)
from semantic_memory.database import MemoryDatabase
from semantic_memory.embedding import EmbeddingProvider
from semantic_memory.ranking import RankingEngine
from semantic_memory.retrieval import RetrievalPipeline

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Feature slug extraction: "feature:081-foo-bar" → "foo-bar".
_FEATURE_SLUG_RE = re.compile(r"^feature:\d+-(.+)$")

# Next-phase mapping per spec FR-2.  ``finish → ""`` is intentional
# (``.strip()`` removes trailing space for the terminal case).  Do NOT
# import ``_derive_next_phase`` from entity_registry — that helper returns
# ``'finish'`` for the terminal phase which is semantically wrong here.
_NEXT_PHASE: dict[str, str] = {
    "brainstorm": "specify",
    "specify": "design",
    "design": "create-plan",
    "create-plan": "implement",
    "implement": "finish",
    "finish": "",
}

# Oversample factor for refresh retrieval: we pull ``limit * FACTOR``
# candidates so the post-confidence-filter still has enough rows to fill
# the requested ``limit`` in typical cases.
REFRESH_OVERSAMPLE_FACTOR: int = 3

# Destination for per-refresh diagnostics (opt-in via memory_influence_debug
# config).  Duplicated from memory_server.py per design TD-4 (see design.md)
# to avoid cross-subprocess import side effects.  Tests monkeypatch this
# constant on the ``refresh`` module; integration tests that share a log
# file with memory_server must monkeypatch both constants.
INFLUENCE_DEBUG_LOG_PATH: Path = (
    Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"
)

# ---------------------------------------------------------------------------
# Module-level dedup state (per-process — each MCP subprocess has its own)
# ---------------------------------------------------------------------------

# One-shot-per-key warning guard for malformed int config values.
_refresh_warned_fields: set[str] = set()

# One-shot flag: warn once per process if retrieval exceeds the 500ms budget
# (spec FR-7 — observability-only, not pre-emption).  Set in Phase 3's
# ``refresh_memory_digest``.
_slow_refresh_warned: bool = False

# One-shot flag: warn once per process if diagnostic log write fails.
_refresh_error_warned: bool = False


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


def build_refresh_query(
    feature_type_id: str, completed_phase: str
) -> str | None:
    """Build the ``'<slug> <next_phase>'`` query string for refresh retrieval.

    Returns ``None`` when ``feature_type_id`` does not match the regex
    ``^feature:\\d+-(.+)$`` — caller omits the ``memory_refresh`` field.

    Examples
    --------
    >>> build_refresh_query("feature:081-mid-session-memory-refresh-hoo", "specify")
    'mid-session-memory-refresh-hoo design'
    >>> build_refresh_query("feature:081-mid-session-memory-refresh-hoo", "finish")
    'mid-session-memory-refresh-hoo'
    >>> build_refresh_query("feature:weird-id", "specify") is None
    True
    """
    match = _FEATURE_SLUG_RE.match(feature_type_id)
    if match is None:
        return None
    slug = match.group(1)
    next_phase = _NEXT_PHASE.get(completed_phase, "")
    return f"{slug} {next_phase}".strip()


# ---------------------------------------------------------------------------
# Config helpers (int-variant; float-variant now lives in config_utils.py)
# ---------------------------------------------------------------------------


# Shared config helpers bound with the refresh caller's prefix + clamp
# policy (feature 088 FR-6.7).  Implementation lives in ``_config_utils.py``;
# ``functools.partial`` preserves the caller-visible signatures
# (``_warn_and_default(key, raw, default, warned)`` and
# ``_resolve_int_config(config, key, default, *, clamp=None, warned)``) so
# tests that reference ``refresh._warn_and_default`` /
# ``refresh._resolve_int_config`` continue to work unchanged.
#
# Divergence from ``maintenance.py`` preserved: stderr prefix ``[refresh]``
# and ``warn_on_clamp=False`` (clamp is silent — operator-tuned values get
# corrected without noise).
_warn_and_default = functools.partial(
    _warn_and_default_core, prefix="[refresh]"
)
_resolve_int_config = functools.partial(
    _resolve_int_config_core, prefix="[refresh]", warn_on_clamp=False
)


# ---------------------------------------------------------------------------
# Diagnostic emission (reuses 080's debug log; duplicate path constant)
# ---------------------------------------------------------------------------


def _emit_refresh_diagnostic(
    *,
    feature_type_id: str,
    completed_phase: str,
    query: str,
    entry_count: int,
    elapsed_ms: int,
) -> None:
    """Append one JSON line describing a refresh to ``INFLUENCE_DEBUG_LOG_PATH``.

    Line format matches spec FR-6.  Parent directory is created lazily.
    On first IO failure (permission denied, disk full, target-is-a-directory,
    etc.) emit one stderr warning and set ``_refresh_error_warned`` to
    suppress subsequent warnings for the remainder of the process lifetime.
    """
    global _refresh_error_warned
    try:
        INFLUENCE_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": "memory_refresh",
            "feature_type_id": feature_type_id,
            "completed_phase": completed_phase,
            "query": query,
            "entry_count": entry_count,
            "elapsed_ms": elapsed_ms,
        })
        with INFLUENCE_DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except (OSError, IOError) as exc:
        if not _refresh_error_warned:
            sys.stderr.write(
                f"[refresh] memory-refresh diagnostic log write failed "
                f"({exc}); suppressing further diagnostic write errors "
                f"this session\n"
            )
            _refresh_error_warned = True


# ---------------------------------------------------------------------------
# Entry serialization with byte-cap enforcement
# ---------------------------------------------------------------------------


def _serialize_entries(entries: list[dict]) -> list[dict]:
    """Project entries to the 3-key shape, truncate descriptions, cap bytes.

    Per spec FR-4:
    - Each output entry has exactly ``{"name", "category", "description"}``.
    - ``description`` is truncated to 240 characters.
    - ``json.dumps(entries, separators=(",", ":"))`` UTF-8 byte length must
      be ≤2000 bytes; if it exceeds, drop entries from the END until the
      budget is met.
    """
    projected: list[dict] = [
        {
            "name": e["name"],
            "category": e["category"],
            "description": (e.get("description") or "")[:240],
        }
        for e in entries
    ]

    if not projected:
        return projected

    def _byte_len(items: list[dict]) -> int:
        return len(
            json.dumps(items, separators=(",", ":")).encode("utf-8")
        )

    while projected and _byte_len(projected) > 2000:
        projected.pop()  # drop from end (lowest-ranked)

    return projected


# ---------------------------------------------------------------------------
# Hybrid retrieve — extracted for structural parity (design TD-1)
# ---------------------------------------------------------------------------


def refresh_memory_digest(
    db: MemoryDatabase,
    provider: EmbeddingProvider | None,
    query: str,
    limit: int,
    *,
    config: dict,
    feature_type_id: str | None = None,
    completed_phase: str | None = None,
) -> dict | None:
    """Return a compact memory digest for the given query, or ``None``.

    Public entry used by ``workflow_state_server._process_complete_phase``
    to inject a ``memory_refresh`` field into ``complete_phase`` responses
    (Phase 4 caller).

    Returns ``None`` when:
    - ``provider is None`` (deterministic; no BM25 fallback — spec AC-3).
    - ``hybrid_retrieve`` raises (error path; one-shot stderr warning).
    - The post-confidence-filter + byte-cap list is empty.

    On success: returns a dict of shape
    ``{"query": str, "count": int, "entries": [{"name", "category", "description"}, ...]}``.

    Side effects:
    - Emits a one-shot stderr latency warning when retrieval exceeds 500ms
      (observability-only — field is still delivered; spec FR-7).
    - Appends one JSON line to ``INFLUENCE_DEBUG_LOG_PATH`` when the
      ``memory_influence_debug`` config flag is True (spec FR-6).

    Parameters
    ----------
    feature_type_id, completed_phase:
        Forwarded to ``_emit_refresh_diagnostic`` for debug-log context.
        Not used in retrieval.
    """
    global _slow_refresh_warned, _refresh_error_warned

    clock_start = time.perf_counter()

    # AC-3 / FR-8: no provider → omit field (deterministic, no fallback).
    if provider is None:
        return None

    # Retrieval + ranking (delegated to hybrid_retrieve for structural
    # parity with memory_server._process_search_memory).  Oversample so the
    # post-confidence-filter still has enough rows to fill ``limit``.
    try:
        ranked = hybrid_retrieve(
            db, provider, config, query, limit * REFRESH_OVERSAMPLE_FACTOR
        )
    except Exception as exc:
        if not _refresh_error_warned:
            sys.stderr.write(
                f"[workflow-state] memory_refresh retrieval failed: {exc}\n"
            )
            _refresh_error_warned = True
        return None

    # Post-filter: medium/high confidence only (spec FR-3 step 2).
    filtered = [
        e for e in ranked
        if e.get("confidence") in ("medium", "high")
    ]

    # Truncate to requested limit (spec FR-3 step 4).
    truncated = filtered[:limit]

    # Serialize to {name, category, description} with byte cap.
    entries = _serialize_entries(truncated)

    if not entries:
        return None

    # Latency observation (spec FR-7) — observability-only, not pre-emption.
    elapsed_ms = int((time.perf_counter() - clock_start) * 1000)
    if elapsed_ms > 500 and not _slow_refresh_warned:
        # EXACT prefix mandated by spec FR-7 (asserted verbatim in
        # test_ac10_slow_retrieval_warns_once_field_still_present).
        print(
            f"[workflow-state] memory_refresh took {elapsed_ms}ms "
            f"(>500ms budget)",
            file=sys.stderr,
        )
        _slow_refresh_warned = True

    # Optional debug diagnostic line (spec FR-6).
    if config.get("memory_influence_debug", False):
        _emit_refresh_diagnostic(
            feature_type_id=feature_type_id or "",
            completed_phase=completed_phase or "",
            query=query,
            entry_count=len(entries),
            elapsed_ms=elapsed_ms,
        )

    return {"query": query, "count": len(entries), "entries": entries}


def hybrid_retrieve(
    db: MemoryDatabase,
    provider: EmbeddingProvider | None,
    config: dict,
    query: str,
    limit: int,
    *,
    project: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """Run the standard retrieval + ranking pipeline and return ranked entries.

    Thin wrapper so both ``memory_server._process_search_memory`` (Phase 2)
    and ``refresh_memory_digest`` (Phase 3) share the same retrieval shape —
    makes ranking parity structural rather than coincidental (design TD-1).

    Parameters
    ----------
    project:
        Optional project filter passed through to ``RetrievalPipeline.retrieve``
        for two-tier project-scoped blending.  Defaults to ``None`` (no
        project filtering) — the default path used by ``refresh_memory_digest``.
    category:
        Optional category filter applied BEFORE ranking (narrows the
        ``entries_by_id`` candidates).  Defaults to ``None`` (all categories
        considered).  When set, only entries with matching ``category`` field
        are passed to ``RankingEngine.rank``.

    Returns entries ordered by ``final_score`` descending, with all original
    entry fields preserved (including ``confidence`` — the caller can
    post-filter if needed).
    """
    pipeline = RetrievalPipeline(db, provider, config)
    result = pipeline.retrieve(query, project=project)
    all_entries = db.get_all_entries()
    # Category filter BEFORE ranking — preserves pre-rank-narrowing semantics
    # that the deepened category test in ``test_memory_server.py`` asserts.
    if category:
        all_entries = [e for e in all_entries if e.get("category") == category]
    entries_by_id = {e["id"]: e for e in all_entries}
    ranker = RankingEngine(config)
    return ranker.rank(result, entries_by_id, limit)
