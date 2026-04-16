# Design: Orchestrator Mid-Session Memory Refresh

**Feature:** 081-mid-session-memory-refresh-hoo
**Spec:** [spec.md](spec.md)

## Prior Art Research

**Cross-subprocess memory.db access (WAL mode compatibility):** Both `memory_server.py` (existing) and `workflow_state_server.py` (new, via this feature) will hold independent connections to `~/.claude/pd/memory/memory.db`. SQLite WAL mode (enabled by 079's migration) supports multi-connection readers with one active writer. `memory_server.py` is the primary writer (store/update/delete); `workflow_state_server.py` is read-only via `RetrievalPipeline`. No additional locking concerns. CLAUDE.md `SQLite lock recovery` + `Hook subprocess safety` guidance remain in effect; `cleanup-locks.sh` hook continues to handle stale-lock edge cases.

**Skipped research agent dispatch** — this is a narrow refactor + additive MCP response field touching code exercised heavily by 080 (just shipped v4.15.1). Existing in-process components to reuse:

- `RetrievalPipeline` (`hooks/lib/semantic_memory/retrieval.py:35`) — public hybrid-retrieval class. `retrieve(context_query, project)` returns `RetrievalResult`. Already used by `_process_search_memory` in `memory_server.py`. Thin wrapper is sufficient.
- `RankingEngine` (`hooks/lib/semantic_memory/ranking.py:10`) — applies prominence/influence weights, already config-tuned per 080.
- `_resolve_float_config` pattern (`memory_server.py:445`) — template for the new int helper.
- `INFLUENCE_DEBUG_LOG_PATH` (`memory_server.py:424`) — reused as-is for diagnostic writes.

No external libraries needed. No new embedding infrastructure.

## Architecture Overview

**Pattern:** Extract a thin shared helper module that wraps `RetrievalPipeline + RankingEngine + confidence filter`. Inject the helper call at the top of `_process_complete_phase`'s response assembly (before the return at line 778 of `workflow_state_server.py`).

**Touched files:**

| File | Change |
|---|---|
| `plugins/pd/hooks/lib/semantic_memory/refresh.py` | **NEW.** Shared helper module. `refresh_memory_digest()`, `build_refresh_query()`, `hybrid_retrieve()` (extracted, see TD-1 revised), `_resolve_int_config()`, `_emit_refresh_diagnostic()`. Module-level dedup flags + constants. |
| `plugins/pd/mcp/workflow_state_server.py` | **Lifespan gains:** open `MemoryDatabase` at `~/.claude/pd/memory/memory.db` → `_memory_db`; create embedding provider via `create_provider(config)` → `_provider`; store config dict → `_config` (module globals mirroring memory_server.py pattern). **In `_process_complete_phase`:** call `refresh_memory_digest(_memory_db, _provider, query, limit, config=_config)` just before return (gated on config); attach `memory_refresh` field to `result` dict. **Note:** the `db` parameter of `_process_complete_phase` remains `EntityDatabase` (operates on entities.db); refresh uses the separate `_memory_db` module global (operates on memory.db). |
| `plugins/pd/mcp/memory_server.py` | **Small refactor.** Extract the retrieval-pipeline-build block of `_process_search_memory` (lines 311-340 equivalent) into a new `hybrid_retrieve()` function in `refresh.py`. `_process_search_memory` is modified to call the extracted function — this makes AC-13 ranking parity structural rather than coincidental (see TD-1 revised). |
| `plugins/pd/templates/config.local.md` | Append 2 fields. |
| `.claude/pd.local.md` | Append same 2 fields. |
| `README_FOR_DEV.md` | Append 2 bullets to memory config table. |
| `plugins/pd/hooks/lib/semantic_memory/test_refresh.py` | **NEW.** Unit tests for AC-1 through AC-14. |
| `plugins/pd/mcp/test_workflow_state_server.py` | Extend with integration tests (field present/absent in complete_phase response; AC-9 regression). |

**No changes to** `retrieval.py`, `ranking.py` (reused as-is). `memory_server.py` receives a **small surgical refactor** per TD-1 (extract `_process_search_memory` retrieval block into `hybrid_retrieve()` in refresh.py; update the caller to invoke it) — NOT unchanged. This is reflected in the Touched Files table.

**Dataflow:**
```
complete_phase MCP call
    ↓
_process_complete_phase (workflow_state_server.py)
    ↓ (existing phase-transition logic unchanged; uses EntityDatabase `db`)
result dict assembled
    ↓
[NEW] if _memory_db is not None and _config.get("memory_refresh_enabled", True):
    ↓
    refresh_memory_digest(_memory_db, _provider, query, limit, config=_config)  ── refresh.py
        ↓
        hybrid_retrieve(_memory_db, _provider, _config, query, limit*REFRESH_OVERSAMPLE_FACTOR)
        │   (same extracted function called by memory_server's _process_search_memory — parity structural)
        ↓
        [hybrid_retrieve internals, identical across both callers:]
        RetrievalPipeline(_memory_db, _provider, _config).retrieve(query, project=None)  ── retrieval.py (existing)
        ↓
        RankingEngine(_config).rank(retrieval_result, entries_by_id, limit*REFRESH_OVERSAMPLE_FACTOR)  ── ranking.py (existing, returns entries with confidence field preserved per ranking.py docstring)
        ↓
        returns list[dict] with full entry fields including "confidence"
    ↓
    post-filter: [e for e in ranked if e["confidence"] in ("medium", "high")]
        ↓
    truncate to limit
        ↓
    serialize to list[{name, category, description}]
        ↓
    byte-cap enforcement (≤2000 bytes UTF-8, per-entry description 240 chars)
    ↓
result["memory_refresh"] = {query, count, entries}
    ↓
return json.dumps(result)
```

**Two databases in workflow_state_server.py:**
- `db: EntityDatabase` — existing, `~/.claude/pd/entities/entities.db`, phase-transition tracking.
- `_memory_db: MemoryDatabase` — **NEW**, `~/.claude/pd/memory/memory.db`, read-only-for-this-feature access via `RetrievalPipeline`.

These are distinct SQLite files; no lock contention. `memory_server.py` also opens memory.db in its own subprocess — SQLite WAL mode (already enabled per 079 migration) supports multi-connection readers with a single writer. Each MCP subprocess maintains its own connection.

**Subprocess topology (why a shared helper, not an import from memory_server):**
- `workflow_state_server.py` and `memory_server.py` are two **separate** stdio MCP subprocesses. They do not share Python module state at runtime.
- A new `refresh.py` under `hooks/lib/semantic_memory/` is importable by BOTH at Python import time without cross-subprocess coupling — each subprocess loads its own copy of the module and its own module-level dedup flags.
- Verified state today (by repo inspection):
  - `workflow_state_server.py` does NOT have `_config`, `_provider`, or `_memory_db` module globals today. Config is read locally inside `lifespan` (around line 176 via `read_config(project_root)`) and only `artifacts_root` is extracted — the rest of the dict is discarded.
  - `workflow_state_server.py` does NOT import `create_provider`, `EmbeddingProvider`, or `MemoryDatabase`.
- Implementation REQUIRES adding three module globals and three lifespan initializations (see TD-3 revised). This is mandatory, not conditional.

## Components

### C-1: `refresh.py` module (new)

**Responsibility:** All refresh-specific logic in one place. Imports only from `semantic_memory` (retrieval/ranking/config), `pathlib`, `datetime`, `json`, `sys`, `time`, `re`. No MCP dependencies.

**Public surface:**
- `refresh_memory_digest(db, provider, query, limit, *, config) -> dict | None` — returns `{"query": ..., "count": ..., "entries": [...]}` or `None`. Internal pseudocode:
  ```python
  if provider is None:
      return None  # AC-3 / FR-8: provider absent → field absent (deterministic, no BM25 fallback)
  ranked = hybrid_retrieve(db, provider, config, query, limit * REFRESH_OVERSAMPLE_FACTOR)
  filtered = [e for e in ranked if e["confidence"] in ("medium", "high")]
  truncated = filtered[:limit]
  entries = _serialize_entries(truncated)  # applies 240-char + byte-cap
  if not entries:
      return None
  return {"query": query, "count": len(entries), "entries": entries}
  ```
- `hybrid_retrieve(db, provider, config, query, limit) -> list[dict]` — extracted from `_process_search_memory` per TD-1 revised. Both MCP servers call it.
- `build_refresh_query(feature_type_id: str, completed_phase: str) -> str | None` — returns query string or `None` on regex mismatch.

**Internal helpers:**
- `_resolve_int_config(config, key, default, *, clamp, warned) -> int` — mirrors `_resolve_float_config` from 080 (bool rejection, dedup warning, optional clamp tuple).
- `_emit_refresh_diagnostic(*, feature_type_id, completed_phase, query, entry_count, elapsed_ms)` — appends JSON line to `INFLUENCE_DEBUG_LOG_PATH`. Reuses same try/except pattern and one-shot stderr warning as `_emit_influence_diagnostic` (copy the pattern; do NOT import from memory_server to avoid cross-subprocess coupling risk).
- `_serialize_entries(entries, limit) -> list[dict]` — applies 240-char description truncation + byte-cap enforcement.

**Module-level state (per-process, each MCP subprocess gets its own copy):**
- `_slow_refresh_warned: bool = False`
- `_refresh_error_warned: bool = False`
- `_refresh_warned_fields: set[str] = set()`
- `INFLUENCE_DEBUG_LOG_PATH = Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"` (same path as 080; duplicated here to avoid cross-subprocess import).

### C-2: `workflow_state_server.py` integration

**Responsibility:** Gate on config, invoke the helper, attach the result field. Minimal changes.

**Shape (sketch, not final code):**
```python
# At module top (new imports)
from semantic_memory.refresh import refresh_memory_digest, build_refresh_query

# Existing lifespan already creates db; add provider creation mirroring memory_server's.
# (Design phase verifies whether lifespan needs augmentation — see TD-3.)

# In _process_complete_phase, just before `return json.dumps(result)`:
if db is not None and _config.get("memory_refresh_enabled", True):
    query = build_refresh_query(feature_type_id, phase)
    if query:
        digest = refresh_memory_digest(db, _provider, query, _refresh_limit, config=_config)
        if digest:
            result["memory_refresh"] = digest
return json.dumps(result)
```

### C-3: workflow-state server module globals + lifespan additions

**Responsibility:** Make `_config`, `_provider`, `_memory_db` available at module scope so `_process_complete_phase` can read them. See TD-3 for the full list of additions.

Verified today (by repo inspection, not deferred): `workflow_state_server.py` has none of these. Implementation adds all three definitively. Lifespan shutdown closes `_memory_db`.

### C-4: Config template + docs

**plugins/pd/templates/config.local.md** (append after existing memory_influence_* fields):
```yaml
# inject memory digest into complete_phase responses so orchestrator sees fresh
# entries at phase boundaries; disable to revert to session-start-only memory
memory_refresh_enabled: true
# max memory entries in per-phase refresh digest; clamped to [1, 20]; each
# entry description capped at 240 chars
memory_refresh_limit: 5
```

**.claude/pd.local.md** (append same 2 fields).

**README_FOR_DEV.md** (append after line 530 — the last `memory_influence_debug` bullet from 080):
```
- `memory_refresh_enabled` — Inject memory digest into complete_phase MCP response at phase boundaries (default: true)
- `memory_refresh_limit` — Max entries in per-phase refresh digest (default: 5; clamped to [1, 20])
```

### C-5: Tests

**`plugins/pd/hooks/lib/semantic_memory/test_refresh.py` (NEW):**
- `TestBuildRefreshQuery` — AC-4a/b/c/d (normal, finish, 3-digit-id, regex-mismatch).
- `TestResolveIntConfig` — bool rejection, string parse, clamp, dedup. Mirrors 080's `TestResolveFloatConfig`.
- `TestRefreshMemoryDigest` — AC-1 (field shape), AC-3 (no provider), AC-6 (entry key set), AC-7 (confidence filter), AC-11 (byte cap), AC-13 (ranking parity vs `_process_search_memory`).
- `TestEmitRefreshDiagnostic` — AC-8 (log line format). Monkeypatches `semantic_memory.refresh.INFLUENCE_DEBUG_LOG_PATH` (NOT `memory_server.INFLUENCE_DEBUG_LOG_PATH`). If a future integration test wants both servers' diagnostics to share a tmp file, it must monkeypatch both constants.
- `TestLatencyGuard` — AC-10 (slow retrieval → one warning, field still present, 2nd call silent).
- `TestErrorHandling` — AC-14 dedup, FR-8 error paths.
- **Autouse reset fixture** resets 3 module globals (`_slow_refresh_warned`, `_refresh_error_warned`, `_refresh_warned_fields`) — mirrors 080's pattern.

**`plugins/pd/mcp/test_workflow_state_server.py` (extend):**
- `TestCompletePhaseMemoryRefresh` — AC-1/AC-2/AC-5/AC-9 at the integration layer.
- AC-9 regression: confirm all existing `complete_phase` tests pass unchanged (no new assertions needed; the sheer existence and passing of the suite is the check).

### C-6: Byte-cap serialization

**Responsibility:** Enforce ≤2000 bytes deterministically.

**Algorithm** (in `_serialize_entries`):
```
1. Build list of {name, category, description[:240]} dicts.
2. serialized = json.dumps(entries, separators=(',', ':'))
3. If len(serialized.encode('utf-8')) > 2000:
       while len(entries) > 0:
           entries = entries[:-1]  # drop last
           serialized = json.dumps(entries, separators=(',', ':'))
           if len(serialized.encode('utf-8')) <= 2000:
               break
4. Return entries.
```

Uses compact JSON separators so byte count is predictable. UTF-8 byte length (not str length) — guards against multi-byte chars in descriptions.

## Technical Decisions

### TD-1: Small extracted `hybrid_retrieve()` function for structural parity (REVISED)

**Decision:** Extract the retrieval-pipeline-build block from `_process_search_memory` into a new `hybrid_retrieve(db, provider, config, query, limit) -> list[dict]` function in `refresh.py`. Both `_process_search_memory` (memory_server.py) and `refresh_memory_digest` (refresh.py) call it. `memory_server.py` is modified — a small, surgical change.

**Why the revision from iter-1:** Iter-1 TD-1 claimed parity was automatic because both paths instantiate `RetrievalPipeline + RankingEngine` "the same way." Design-reviewer correctly caught that parity depends on caller-discipline (same `project=` arg, same `entries_by_id` dict-build, same `limit` to `rank()`) — a regression could silently diverge the two orderings. Extracting the common function makes parity structural. The extraction is ~20 LOC and touches only `_process_search_memory` at line 311-340.

**What `hybrid_retrieve` does:**
1. `pipeline = RetrievalPipeline(db, provider, config); result = pipeline.retrieve(query, project=None)`
2. `all_entries = db.get_all_entries(); entries_by_id = {e["id"]: e for e in all_entries}`
3. `ranker = RankingEngine(config); ranked = ranker.rank(result, entries_by_id, limit)`
4. Returns `ranked` (list of entry dicts with `final_score` and all original fields including `confidence`).

Both callers now invoke the same function with their own `limit` — `_process_search_memory` uses its caller-provided limit; `refresh_memory_digest` uses `limit * REFRESH_OVERSAMPLE_FACTOR`.

**AC-13 test strategy after this revision:** Unit test calls `hybrid_retrieve(..., limit=N)` directly and asserts a deterministic ranking given seeded embeddings. Both callers inherit this correctness; no separate parity harness needed.

### TD-1b: `REFRESH_OVERSAMPLE_FACTOR = 3` module constant

**Decision:** Define `REFRESH_OVERSAMPLE_FACTOR: int = 3` at `refresh.py` module scope. AC-13 expression `min(K, search_memory_limit, limit * REFRESH_OVERSAMPLE_FACTOR)` now references this named constant.

**Why:** Spec FR-3 step 1 says "oversample by 3x"; a named constant makes the test expression deterministic and the oversample tunable in one place if future tuning needs it.

### TD-2: Query construction via inline mapping, not imported helper

**Decision:** `build_refresh_query` uses a local `_NEXT_PHASE` dict mapping per spec FR-2. Does NOT import `_derive_next_phase` from `entity_registry`.

**Why:** `_derive_next_phase('finish')` returns `'finish'` per existing tests — that's a legitimate registry semantic for entity state machines ("finish is terminal, stays finish") but semantically wrong here (the orchestrator has no further phase to refresh memory for after finish; query should be just the feature slug). A local mapping makes the `finish → ""` terminal behavior explicit and localized.

### TD-3: workflow-state server lifespan additions (REVISED — now definitive)

**Decision:** `workflow_state_server.py` requires THREE module-level additions:

1. **`_config: dict = {}`** — populated in lifespan via `global _config; _config = config` (mirrors `memory_server.py:409`). Used by integration sketch to gate on `memory_refresh_enabled` and pass through to `refresh_memory_digest`.
2. **`_provider: EmbeddingProvider | None = None`** — populated in lifespan via `global _provider; _provider = create_provider(config)` (mirrors `memory_server.py:520-523`). Wrapped in try/except — on failure `_provider` stays `None` and refresh silently omits the field.
3. **`_memory_db: MemoryDatabase | None = None`** — populated in lifespan by opening `~/.claude/pd/memory/memory.db` (same path `memory_server.py` uses). Wrapped in try/except — on failure `_memory_db` stays `None` and refresh silently omits the field.

New imports at the top of `workflow_state_server.py`:
```python
from semantic_memory.database import MemoryDatabase
from semantic_memory.embedding import EmbeddingProvider, create_provider
from semantic_memory.refresh import (
    refresh_memory_digest, build_refresh_query,
    _resolve_int_config, _refresh_warned_fields,
)
```

**Subtlety — import `_refresh_warned_fields` by reference, not by copy:** Python imports of module-level mutable objects return references to the live object. The integration sketch passes `_refresh_warned_fields` directly to `_resolve_int_config(..., warned=_refresh_warned_fields)` — this mutates the set in refresh.py's module scope, preserving per-process dedup semantics. An implementer must NOT do `warned = set()` or re-assign `_refresh_warned_fields = set()` in workflow_state_server.py; either would silently break dedup.

**Why mandatory:** Verified via repo inspection that none of these exist today. Iter-1 hedging ("verify during implementation") was incorrect.

**Why no crash on failure:** `RetrievalPipeline` accepts `provider=None` and degrades gracefully (vector skipped, BM25 still works if FTS5 available). `MemoryDatabase` failure (unlikely — file is present, WAL mode) is handled by the outer gate `if _memory_db is not None`. Either failure mode → `memory_refresh` absent; no impact on phase transition.

**Cleanup:** Lifespan shutdown closes `_memory_db` alongside the existing `_db` close.

### TD-4: Duplicate `INFLUENCE_DEBUG_LOG_PATH` constant vs. import from memory_server

**Decision:** Duplicate the constant definition in `refresh.py`. Do NOT import from `memory_server.py`.

**Why:** `memory_server.py` runs in a separate MCP subprocess; importing its module-level constant into `refresh.py` (which is imported by workflow_state_server.py) would cause memory_server's module code (including lifespan decorators, MCP tool registrations) to execute at import time in a context that isn't the memory_server's own subprocess. Risk of side effects, circular imports, or worse. A duplicate `Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"` is two lines. Cheap, safe, and the two always point to the same file.

**Trade-off:** If 080's backlog item #00068 (`chmod 0o600` on log file) lands, both constants need updating. Minor maintenance burden vs. cross-subprocess coupling risk.

### TD-5: Confidence filter as post-filter, not DB query filter

**Decision:** Filter on `entry["confidence"] in ("medium", "high")` AFTER `RankingEngine.rank()`, not as an argument to the retrieval pipeline.

**Why:** `RetrievalPipeline.retrieve()` and `RankingEngine.rank()` have no confidence parameter today. Adding one would be a cross-cutting change touching the existing `_process_search_memory` signature. Post-filter keeps the change scoped to `refresh.py`. Slight retrieval waste (we fetch low-confidence candidates only to discard) but negligible at `limit*3` oversample.

### TD-6: Byte-cap via drop-from-end, not re-rank

**Decision:** When serialized bytes exceed 2000, drop entries from the **end** of the ranked list. Do NOT re-rank or score-weight.

**Why:** The ranked list is already ordered by relevance (RankingEngine output). Dropping the lowest-ranked entries first is exactly what we want. Simpler than alternative weighting schemes.

### TD-7: Observability-only latency guard

**Decision:** `time.perf_counter()` measures elapsed; if >500ms, emit one-shot stderr warning. Do NOT attempt pre-emption.

**Why:** Synchronous retrieval cannot be interrupted. The honest solution is to measure, warn, and let the operator investigate or disable. Matches spec FR-7.

### TD-8: Digest payload is MCP-result-visible; orchestrator reads it as tool result

**Decision:** The `memory_refresh` field appears in the JSON string returned by `complete_phase` — visible to the orchestrator as part of the MCP tool result content. No separate "injection" mechanism.

**Why:** MCP tool results go directly into the calling LLM's context. The orchestrator naturally sees the field and can incorporate it. This is simpler than a hook-based injection and requires no new infrastructure.

### TD-9: `_resolve_int_config` takes config as parameter (divergence from 080)

**Decision:** The new `_resolve_int_config` in `refresh.py` takes `config: dict` as a positional argument. This diverges from 080's `_resolve_float_config` (in `memory_server.py`) which reads module-global `_config` directly.

**Why:** `refresh.py` is a shared helper imported by both MCP servers; each server has its own `_config`. Parameterizing config keeps the helper agnostic. Retrofitting 080's helper to this pattern is backlog item (#00070 covers the shared-helper refactor; not this feature).

### TD-10: RankingEngine.rank() preserves full entry fields including `confidence`

**Decision:** Post-filter relies on `entry["confidence"]` being present in `RankingEngine.rank()` output.

**Why safe:** `ranking.py` docstring confirms `rank()` returns entry dicts ordered by `final_score` descending, with the `final_score` key added — all original fields (including `confidence`) preserved. Verified by inspection. No field re-join needed in the post-filter path.

## Interfaces

### I-1: `refresh_memory_digest`

**NOTE:** Tasks.md Task 3.2 defines the authoritative signature for this function, including `feature_type_id: str | None = None` and `completed_phase: str | None = None` kwargs required for FR-6 diagnostic forwarding. The signature below predates that decision; refer to tasks.md for the canonical form.

```python
def refresh_memory_digest(
    db: MemoryDatabase,
    provider: EmbeddingProvider | None,
    query: str,
    limit: int,
    *,
    config: dict,
    feature_type_id: str | None = None,  # per tasks.md Task 3.2
    completed_phase: str | None = None,   # per tasks.md Task 3.2
) -> dict | None:
    """Return a compact memory digest for the given query.

    Returns None if no results, no provider (when vector retrieval is
    required), or any helper error path is hit. Returns a dict with
    keys {"query", "count", "entries"} on success.  Each entry has
    exactly 3 keys: {"name", "category", "description"}.

    Applies a medium/high confidence post-filter and truncates to
    ``limit`` entries, further capped at 2000 bytes total JSON.
    """
```

### I-2: `build_refresh_query`

```python
_FEATURE_SLUG_RE = re.compile(r"^feature:\d+-(.+)$")

_NEXT_PHASE = {
    "brainstorm": "specify",
    "specify": "design",
    "design": "create-plan",
    "create-plan": "implement",
    "implement": "finish",
    "finish": "",
}

def build_refresh_query(feature_type_id: str, completed_phase: str) -> str | None:
    """Build 'slug next_phase' query string, or return None on malformed input.

    Examples
    --------
    >>> build_refresh_query("feature:081-mid-session-memory-refresh-hoo", "specify")
    "mid-session-memory-refresh-hoo design"
    >>> build_refresh_query("feature:081-mid-session-memory-refresh-hoo", "finish")
    "mid-session-memory-refresh-hoo"
    >>> build_refresh_query("feature:weird", "specify") is None
    True
    """
```

### I-3: `_resolve_int_config` (new, mirrors 080)

```python
def _resolve_int_config(
    config: dict,
    key: str,
    default: int,
    *,
    clamp: tuple[int, int] | None = None,
    warned: set[str],
) -> int:
    """Resolve an int config field with bool rejection + dedup warning.

    - bool rejected (Python bool subclasses int; must reject before int branch)
    - string-parseable via int(raw)
    - invalid value → default + one-shot stderr warning per key
    - optional clamp to [min, max] (silent, no warning)
    """
```

### I-4: `_emit_refresh_diagnostic`

```python
def _emit_refresh_diagnostic(
    *,
    feature_type_id: str,
    completed_phase: str,
    query: str,
    entry_count: int,
    elapsed_ms: int,
) -> None:
    """Append one JSON line to INFLUENCE_DEBUG_LOG_PATH.  Returns silently
    on IOError (with one-shot stderr warning).

    Line format:
    {"ts": "<iso Z>", "event": "memory_refresh", "feature_type_id": "...",
     "completed_phase": "...", "query": "...", "entry_count": N,
     "elapsed_ms": M}
    """
```

### I-5: `workflow_state_server.py` integration point

**Before (line 776 area):**
```python
    # Artifact completeness warning on finish (AC-5)
    if phase == "finish":
        artifact_warnings = _check_artifact_completeness(db, feature_type_id)
        if artifact_warnings:
            result["artifact_warnings"] = artifact_warnings

return json.dumps(result)
```

**After:**
```python
    # Artifact completeness warning on finish (AC-5)
    if phase == "finish":
        artifact_warnings = _check_artifact_completeness(db, feature_type_id)
        if artifact_warnings:
            result["artifact_warnings"] = artifact_warnings

# Feature 081: memory refresh digest (additive).
# Three gates: entity DB present (no project context without it), memory DB
# present (no digest source without it), config enables. _memory_db is
# MemoryDatabase (memory.db), distinct from `db: EntityDatabase` (entities.db).
if (
    db is not None
    and _memory_db is not None
    and result.get("last_completed_phase")  # None on degraded engine-fallback paths
    and _config.get("memory_refresh_enabled", True)
):
    query = build_refresh_query(feature_type_id, phase)
    if query:
        limit = _resolve_int_config(
            _config, "memory_refresh_limit", 5,
            clamp=(1, 20), warned=_refresh_warned_fields,
        )
        digest = refresh_memory_digest(
            _memory_db, _provider, query, limit, config=_config,
        )
        if digest:
            result["memory_refresh"] = digest

return json.dumps(result)
```

Notes: `_memory_db`, `_provider`, `_config` all become module globals per TD-3. `_refresh_warned_fields` is imported from `refresh` module for the int-config warning (set lives in refresh.py module scope per C-1).

## Risks

### R-1: Provider not available in workflow-state server

**Risk:** Provider creation in lifespan fails (missing API key, network at startup).

**Mitigation:** `refresh_memory_digest` early-returns `None` when `provider is None`, deterministically — no fallback to BM25-only retrieval. This matches spec AC-3 precisely (`memory_refresh` absent; no exception; no stderr warning). Update C-1 pseudocode and implementation:
```python
def refresh_memory_digest(db, provider, query, limit, *, config):
    if provider is None:
        return None  # AC-3 / FR-8
    ...
```
Rationale: mixing provider-absent BM25-only results into the digest would make behavior opaque (operator can't tell whether the embedding model is working). Cleaner to fail silent and let the operator notice missing diagnostics.

### R-2: MCP subprocess cold-start latency

**Risk:** First `complete_phase` call per MCP subprocess restart pays embedding-model init cost (can be 1-2s for Gemini). Triggers FR-7 latency warning noisily on every restart.

**Mitigation:** Warm the provider in lifespan (existing pattern for memory_server). FR-7 warning is one-shot per process, so even if cold-start trips it, subsequent calls are silent.

### R-3: Duplicate INFLUENCE_DEBUG_LOG_PATH constants drift

**Risk:** If someone changes the path in memory_server.py but forgets refresh.py (or vice versa), diagnostics split into two files.

**Mitigation:** Document the duplication in TD-4. Add a grep-check to validate.sh (deferred to backlog if not included in this feature).

### R-4: Orchestrator confused by refresh content

**Risk:** Injecting memory entries into complete_phase response could confuse the orchestrator if entries are irrelevant to the current decision context (e.g., general-repo patterns vs. feature-specific guidance).

**Mitigation:** Query construction is feature-specific (`{slug} {next_phase}`), which narrows retrieval. 080's config-driven threshold/weight lets operators tune relevance. Regression lever: `memory_refresh_enabled: false` disables entirely (HP-3).

### R-5: Token budget exceeded by edge-case entries

**Risk:** A KB entry with an unusually long description + name + category could push a single entry over ~500 bytes, making the 5-entry digest exceed 2000 bytes.

**Mitigation:** FR-4 enforces per-entry description truncation at 240 chars BEFORE byte-cap measurement. AC-11 exercises this explicitly with 500-char fixture descriptions.

### R-6: Existing complete_phase tests break from response-shape change

**Risk:** Tests that assert `result == {exact_dict}` on complete_phase output will break because `memory_refresh` is a new key.

**Mitigation:** Implementation phase audits existing tests; any exact-dict equality assertions either (a) get updated to ignore the new key, or (b) explicitly set `memory_refresh_enabled: false` in their test config. Phase 0 baseline measurement (following 080's pattern) captures pre-change test count.

## Dependencies

- `semantic_memory.retrieval.RetrievalPipeline` (no change)
- `semantic_memory.ranking.RankingEngine` (no change; uses 080's config-driven weights)
- `semantic_memory.database.MemoryDatabase` (no change)
- `semantic_memory.embedding.EmbeddingProvider` + `create_provider` (no change)
- No new Python packages. All stdlib: `pathlib`, `datetime`, `json`, `sys`, `time`, `re`.

## Phase Gates

Implementation must verify (in order):
1. **Existing-test audit:** `grep -n 'complete_phase\|last_completed_phase' plugins/pd/mcp/test_workflow_state_server.py` enumerates tests that may assert on exact `complete_phase` response shape. Audit each; update exact-dict equality assertions to ignore `memory_refresh`, OR set `memory_refresh_enabled: false` in those test configs. Record count of impacted tests in Phase 0 baseline.
2. `workflow_state_server.py` gains three module-level globals per TD-3 (`_config`, `_provider`, `_memory_db`) populated during lifespan.
3. `refresh.py` helper compiles and imports cleanly in both MCP subprocesses (verified by running each MCP server's lifespan).
4. `hybrid_retrieve()` function extracted; `_process_search_memory` updated to call it; existing `search_memory` tests pass unchanged.
5. Ranking parity assertion (AC-13) passes before any production integration.
6. `complete_phase` unit tests pass unchanged (AC-9) — all assertions updated per step 1.
7. `validate.sh` 0 errors, warning count ≤ baseline (Phase 0 of implementation captures this).
