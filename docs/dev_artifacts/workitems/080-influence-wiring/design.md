# Design: Influence Tuning + Diagnostics

**Feature:** 080-influence-wiring
**Spec:** [spec.md](spec.md)

## Prior Art Research

Skipped — feature is pure internal refactoring of existing memory system. No external solutions to research; pattern precedents (config-field → instance-attribute) already established at `ranking.py:32-35` (`_prominence_weight` pattern).

## Architecture Overview

Six surgical edits across five files. No new modules, no new interfaces to external consumers. The Subprocess Serialization Contract is unchanged (no CLI additions). The MCP tool signature on the stdio boundary is unchanged (the wrapper delegates to helper, same externally-visible contract).

**Touched files:**
1. `plugins/pd/mcp/memory_server.py` — threshold default becomes `None`; helper resolves from module-level `_config`; add `INFLUENCE_DEBUG_LOG_PATH` constant; add diagnostics emitter; add `_warned_fields` set.
2. `plugins/pd/hooks/lib/semantic_memory/ranking.py` — add `self._influence_weight` in `__init__`; replace hardcoded `0.05` in `_prominence`.
3. `plugins/pd/templates/config.local.md` — append 3 memory_influence_* fields with explanatory comments.
4. `.claude/pd.local.md` — append same 3 fields (debug: true for baseline collection).
5. `README_FOR_DEV.md` — append 3 fields to the existing 11-field memory config enumeration at lines 517-527.
6. `plugins/pd/commands/{specify,design,create-plan,implement}.md` — mechanical substitution: 14 occurrences of `threshold=0.70)` (multi-line call form — argument on its own line with trailing `)`). For each, remove the `threshold=0.70` line and move the `)` to the end of the previous argument. Resulting calls use the function's new default (`None`), which resolves to the config value 0.55. See C-5 for before/after examples.

**Dataflow:** No change to inbound/outbound data. Diagnostics are a side-effect appended to a local log file; influence recording returns the same JSON payload as before.

## Components

### C-1: Config-driven threshold (memory_server.py)

**Responsibility:** Read `memory_influence_threshold` from module-level `_config` at the single canonical resolution point (inside `_process_record_influence_by_content`, immediately after argument coercion). Preserve existing clamp at `[0.01, 1.0]`.

**Shape:**
- `record_influence_by_content(..., threshold: float | None = None)` — signature change only.
- `_process_record_influence_by_content(..., threshold: float | None = None)` — same signature change.
- Inside helper, before any use: `if threshold is None: threshold = _resolve_float_config("memory_influence_threshold", 0.55)`.
- Existing `threshold = max(0.01, min(1.0, threshold))` line (currently line 313) stays as-is.

### C-2: Config-driven influence weight (ranking.py)

**Responsibility:** Expose the hardcoded `0.05` coefficient in `_prominence` as config-driven. Follow existing pattern from `_prominence_weight` (line 35).

**Shape:**
- Add to `RankingEngine.__init__`: `self._influence_weight: float = _resolve_float_config_in_ranker(config, "memory_influence_weight", 0.05, clamp=(0.0, 1.0))`.
- Replace `_prominence` line 252 last term: `0.05 * influence` → `self._influence_weight * influence`.

### C-3: Diagnostics emitter (memory_server.py)

**Responsibility:** When `memory_influence_debug` is true, append one JSON line per **outer-call** invocation of `record_influence_by_content` to `INFLUENCE_DEBUG_LOG_PATH`. Zero overhead when disabled. Emitted from the MCP wrapper (outside `@with_retry`) so retries don't double-log, AND so every terminal path of the inner helper (happy path + 5 early-return paths) produces exactly one diagnostic.

**Shape:**
- Module-level (grouped in one block immediately after `_project_root` at line 401):
  - `INFLUENCE_DEBUG_LOG_PATH = Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"`.
  - `_influence_debug_write_failed: bool = False` (one-shot warning flag).
  - `_warned_fields: set[str] = set()` (C-4).
- New helper: `_emit_influence_diagnostic(agent_role, injected, matched, threshold, feature_type_id)`.
- Call site: in the **MCP wrapper** `record_influence_by_content` (line 614) after the helper returns. Parse the helper's JSON return value to extract `matched` count. Gate: `if _config.get("memory_influence_debug", False)` — first check, zero overhead when disabled. Uses the outer call's `threshold` argument (already resolved by helper via config fallback, so we need to either re-resolve here OR have the helper return the effective threshold in a new internal-only JSON field). **Chosen:** helper returns the same JSON shape as before (no contract change); wrapper re-calls `_resolve_float_config("memory_influence_threshold", 0.55)` if `threshold is None` to get the effective value for logging. Tiny double-resolution cost, zero contract change.
- Writes JSON line: `{"ts": "<iso>", "event": "influence_dispatch", "agent_role": ..., "injected": len(injected_entry_names), "matched": <from helper return>, "recorded": <same as matched>, "threshold": <effective value>, "feature_type_id": feature_type_id}`.
- On IOError/OSError: if not `_influence_debug_write_failed`: emit one stderr warning, set flag to True. Subsequent failures silent.
- **Early-return semantics:** the helper's 5 early-return paths (empty injected_entry_names, np unavailable, provider unavailable, no valid chunks, all chunk embeddings failed) each return a well-formed JSON with `matched=[]`. The wrapper logs those as `matched=0, injected=len(injected_entry_names)` — giving operators visibility into degraded dispatches, which is exactly when debug is most useful.

### C-4: Warning emitter (shared helpers)

**Responsibility:** One-shot-per-field warnings when config values can't be coerced to float.

**Shape:**
- Module-level in `memory_server.py`: `_warned_fields: set[str] = set()` (grouped with other new module globals per C-3).
- New helper `_resolve_float_config(key: str, default: float) -> float`:
  - Read `raw = _config.get(key, default)`.
  - **Reject bool explicitly**: `if isinstance(raw, bool): treat as invalid`. (Python `bool` is `int` subclass, so `float(True) = 1.0` would silently succeed — must intercept before the int/float branch.)
  - If `isinstance(raw, (int, float))` (after bool rejection): return `float(raw)`.
  - If `isinstance(raw, str)`: try `float(raw)`; on ValueError fall through to invalid path.
  - Invalid path: if `key not in _warned_fields`: emit stderr warning `[memory-server] config field '{key}' value {raw!r} is not a float; using default {default}`; add to set. Return default.
- Analogous helper `_resolve_weight(config, key, default, *, warned)` in `ranking.py` (per I-5). Same bool rejection. Separate warning-set per module (acceptable — these are separate process contexts anyway in common usage since RankingEngine runs in the hook process, memory_server in its own MCP subprocess).
- **Test reset strategy:** Add an `autouse=True` pytest fixture in `plugins/pd/mcp/test_memory_server.py` (and analogously in the ranking.py test file) that resets **three pieces of module state** before each test:
  1. `monkeypatch.setattr(memory_server, '_warned_fields', set())` — fresh warning set per test.
  2. `monkeypatch.setattr(memory_server, '_influence_debug_write_failed', False)` — fresh write-failed flag.
  3. `monkeypatch.setattr(memory_server, '_config', {})` — fresh config dict. Tests set their specific values via `monkeypatch.setitem(memory_server._config, "memory_influence_threshold", 0.8)` rather than direct assignment, so the fixture teardown restores automatically.
  AC-10 tests MUST include this fixture as a dependency. Parallel/reordered tests produce stable results under this regime.

### C-5: 14-caller mechanical migration

**Responsibility:** Remove the explicit `threshold=0.70` argument from all 14 call sites so the new internal default can take effect.

**Shape:** For each of the 14 occurrences across `plugins/pd/commands/{specify,design,create-plan,implement}.md`, rewrite.

**Canonical form for multi-line calls** (the predominant pattern — e.g., `implement.md:134`):

Before:
```
record_influence_by_content(
    subagent_output_text=<output>,
    injected_entry_names=<names>,
    agent_role=<role>,
    feature_type_id=<id>,
    threshold=0.70)
```

After (remove the entire `threshold=0.70)` line; move the `)` onto the previous argument's line, preserving the trailing comma→no-trailing-comma transition):
```
record_influence_by_content(
    subagent_output_text=<output>,
    injected_entry_names=<names>,
    agent_role=<role>,
    feature_type_id=<id>)
```

**Canonical form for single-line calls** (if any — audit during implementation):

Before: `record_influence_by_content(..., feature_type_id=<id>, threshold=0.70)`

After: `record_influence_by_content(..., feature_type_id=<id>)` (remove `, threshold=0.70` in one slice).

**Implementer guidance:** Use Edit tool per-occurrence; avoid sed because markdown surrounding prose (comments, bullet levels) may vary per call site. Verification: AC-7 grep `threshold=0.70` across `plugins/pd/commands/*.md` must return 0 lines; additionally AC-7b: grep `threshold=0\.` returns 0 (catches typos like `threshold=0.7` or `threshold=0.75`).

### C-6: Config templates

**Responsibility:** Document the 3 new fields in the two config files that define/ship them, and in the README_FOR_DEV.md reference table.

**Shape (plugins/pd/templates/config.local.md, append after existing memory_* fields):**
```yaml
# cosine similarity threshold for influence matching; lower = more permissive; range [0.0, 1.0] clamped
memory_influence_threshold: 0.55
# contribution of influence to ranking prominence; coefficient in _prominence formula; NOT auto-renormalized — raise only by subtracting from other weights so sum stays ≤1.0
memory_influence_weight: 0.05
# emit per-dispatch hit-rate diagnostics to ~/.claude/pd/memory/influence-debug.log
memory_influence_debug: false
```

**.claude/pd.local.md:** Same fields, but `memory_influence_debug: true` (baseline collection per Success Criteria).

**README_FOR_DEV.md (append after line 527, preserving indentation):**
```
- `memory_influence_threshold` — Cosine similarity threshold for influence matching (default: 0.55)
- `memory_influence_weight` — Coefficient for influence in ranking prominence (default: 0.05)
- `memory_influence_debug` — Emit per-dispatch hit-rate diagnostics to `~/.claude/pd/memory/influence-debug.log` (default: false)
```

## Technical Decisions

### TD-1: Signature-default-None vs inner-config-resolution
**Decision:** Set `threshold: float | None = None` and resolve inside the helper, not as `threshold: float = 0.55`.
**Why:** A literal default at the signature level (like `0.55`) conflicts with explicit caller-passed values — Python evaluates the default at function-definition time, not per-call. If a future config change wants to re-tune, changing the signature default won't affect the 14 migrated callers that pass `None`. Resolving at the call site from a module-level `_config` lets the config file drive behavior without code edits. This is the same pattern used by `RankingEngine` instance attributes today.

### TD-2: Dedicated log file over stderr for diagnostics
**Decision:** Diagnostics go to `~/.claude/pd/memory/influence-debug.log`, not stderr.
**Why:** The MCP server runs as a stdio subprocess of Claude Code. Its stderr is captured by Claude Code's MCP harness — on macOS that lands in a rotating client-side log the operator can't easily tail. A dedicated file gives the operator a deterministic `tail -f` target. Also avoids polluting the existing server startup stderr (`memory-server: embedding provider=...`) with per-dispatch telemetry.

### TD-3: Don't modify config.py
**Decision:** Keep `read_config()` / `_coerce()` untouched. Add per-field float coercion + warning at the point of consumption.
**Why:** `config.py` is shared by all memory components (injector, ranker, memory_server). Adding per-field validation there has a blast radius beyond this feature. Point-of-consumption validation (in the MCP server helper and `RankingEngine.__init__`) scopes the change to the three new fields only. Each consumer is already the authoritative source for its own config interpretation — ranking.py already does `float(config.get("memory_prominence_weight", ...))` inline at line 35, and this matches that pattern.

### TD-4: `recorded == matched` invariant
**Decision:** Write `recorded: len(matched)` in the diagnostic line. Never differs from `matched` under current semantics.
**Why:** The existing `db.record_influence(...)` call at line 372 is wrapped in no try/except; if it raises, the exception propagates. There is no recorded-but-not-matched path and no matched-but-not-recorded path. Including `recorded` as a field future-proofs the log schema for a future retry/queue layer without committing to implementation now.

### TD-5: No log rotation
**Decision:** `influence-debug.log` grows unbounded; operator prunes manually.
**Why:** YAGNI. Expected usage is "enable for a week, capture baseline, disable." Files produced in that window are <1MB. Rotation adds a maintenance surface this feature doesn't need.

### TD-6: One-shot warning guards in two places
**Decision:** Separate `_warned_fields` sets in `memory_server.py` and `ranking.py`.
**Why:** The two modules run in separate process contexts in production — `ranking.py` lives in the SessionStart hook process; `memory_server.py` lives in the MCP subprocess. A shared module-level set would have no shared memory across those processes anyway. Per-module sets are simpler and match runtime topology.

### TD-7: Leave existing threshold clamp at `[0.01, 1.0]`
**Decision:** Don't widen clamp bounds for the new config-driven path. Same clamp applies whether threshold came from config, explicit override, or default.
**Why:** The existing clamp is a sanity rail for the existing literal-threshold path. New config-driven path inherits the same sanity rail for free. `<0.01` threshold is nonsensical (would match everything); `>1.0` is invalid (cosine similarity max is 1.0).

### TD-8: Retain `RankingEngine` construction semantics
**Decision:** `RankingEngine.__init__` reads the new `memory_influence_weight` at construction time. It's not re-read per `rank()` call.
**Why:** Matches the existing pattern for `_prominence_weight` (line 35). If the operator changes the config mid-session, they need a new session to pick it up — same behavior as every other memory config field. Consistent mental model.

## Risks

### R-1: 14-caller migration misses a spot
**Risk:** If any of the 14 `threshold=0.70` occurrences is missed in the migration, Success Criteria (30% hit rate) won't be met and the baseline measurement is polluted.
**Mitigation:** AC-7 is an explicit grep check with a `wc -l | 0` gate. Commit won't pass the AC suite if any caller remains. Grep pattern is exact-string — no false negatives.

### R-2: Config coercion blast radius larger than planned
**Risk:** If an implementer mistakenly adds per-field validation to `config.py`, existing memory tests may break.
**Mitigation:** TD-3 explicitly rules out modifying `config.py`. FR-5 phrasing ("point of consumption") is now unambiguous in spec.md iter 3.

### R-3: Log directory creation race
**Risk:** Two concurrent MCP calls both see missing `~/.claude/pd/memory/` and race to `mkdir`.
**Mitigation:** `Path.mkdir(parents=True, exist_ok=True)` is idempotent by design — the `exist_ok=True` flag handles the race. No further locking needed.

### R-4: Disk full during diagnostic write
**Risk:** Appending to the log file fails with ENOSPC. Breaks influence recording.
**Mitigation:** FR-3 mandates try/except IOError wrapping; first failure logs one stderr warning via `_influence_debug_write_failed` flag; subsequent failures are silent. Influence recording path itself (the return value) is never in the try/except — it's never blocked by diagnostic failures.

### R-5: Baseline measurement integrity
**Risk:** Operator forgets to capture pre-merge baseline → Success Criteria comparison is meaningless.
**Mitigation:** Success Criteria now includes explicit procedure step 1 (capture baseline on reverted branch). Retro template should include a "baseline captured: yes/no" field to make skips visible.

## Interfaces

### I-1: record_influence_by_content (MCP tool surface)

**Before:**
```python
async def record_influence_by_content(
    subagent_output_text: str,
    injected_entry_names: list[str],
    agent_role: str,
    feature_type_id: str | None = None,
    threshold: float = 0.70,
) -> str
```

**After:**
```python
async def record_influence_by_content(
    subagent_output_text: str,
    injected_entry_names: list[str],
    agent_role: str,
    feature_type_id: str | None = None,
    threshold: float | None = None,  # resolves from memory_influence_threshold config
) -> str
```

Return value unchanged (same JSON with `matched` list + `skipped` count).

### I-2: _process_record_influence_by_content (internal helper)

Same signature change as I-1. Inside the helper, resolution block at the top:

```python
if threshold is None:
    threshold = _resolve_float_config("memory_influence_threshold", 0.55)
threshold = max(0.01, min(1.0, threshold))  # existing clamp, unchanged
```

**No diagnostic emission inside the helper.** The helper is decorated with `@with_retry("memory")`; emitting here would double-log on retry. Also, the helper has 5 early-return paths (empty injected, numpy unavailable, provider unavailable, no valid chunks, all embeddings failed) — none of which reach a helper-bottom emission site. Diagnostic emission moves to the wrapper (I-2b) where it runs exactly once per outer call, covering all return paths.

### I-2b: record_influence_by_content (MCP wrapper) — diagnostic integration

The wrapper at line 614 already delegates to the helper. After the helper returns, before the wrapper returns, insert the diagnostic block:

```python
async def record_influence_by_content(
    subagent_output_text: str,
    injected_entry_names: list[str],
    agent_role: str,
    feature_type_id: str | None = None,
    threshold: float | None = None,
) -> str:
    result_json = await asyncio.to_thread(
        _process_record_influence_by_content,
        subagent_output_text,
        injected_entry_names,
        agent_role,
        feature_type_id,
        threshold,
    )
    # New: diagnostic emission (outside @with_retry boundary)
    if _config.get("memory_influence_debug", False):
        try:
            result = json.loads(result_json)
            matched_count = len(result.get("matched", []))
        except (json.JSONDecodeError, TypeError):
            matched_count = 0
        effective = threshold if threshold is not None else _resolve_float_config(
            "memory_influence_threshold", 0.55
        )
        effective = max(0.01, min(1.0, effective))  # clamp-parity with helper
        _emit_influence_diagnostic(
            agent_role=agent_role,
            injected=len(injected_entry_names),
            matched=matched_count,
            threshold=effective,
            feature_type_id=feature_type_id,
        )
    return result_json
```

**Clamp parity:** The wrapper applies the same `max(0.01, min(1.0, ...))` clamp as the helper (line 313) so the logged `threshold` field equals the value the helper used. Without this, a config value like `0.005` would log as `0.005` while the helper clamped to `0.01` — diagnostic fidelity broken.

**Return JSON parsing cost:** One `json.loads` per debug-enabled dispatch is negligible (microseconds). Keeping the helper's return contract unchanged (plain JSON string) avoids a tuple-return refactor across existing callers.

### I-3: _resolve_float_config (new helper, memory_server.py)

```python
_warned_fields: set[str] = set()

def _resolve_float_config(key: str, default: float) -> float:
    raw = _config.get(key, default)
    # Reject bool explicitly — bool is an int subclass in Python, so float(True)=1.0
    # would otherwise silently coerce. Invalid-path fall-through guarantees AC-10(e).
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return _warn_and_default(key, raw, default)
    if isinstance(raw, (int, float)):
        return float(raw)
    # raw is str
    try:
        return float(raw)
    except ValueError:
        return _warn_and_default(key, raw, default)


def _warn_and_default(key: str, raw, default: float) -> float:
    if key not in _warned_fields:
        sys.stderr.write(
            f"[memory-server] config field {key!r} value {raw!r} "
            f"is not a float; using default {default}\n"
        )
        _warned_fields.add(key)
    return default
```

### I-4: _emit_influence_diagnostic (new helper, memory_server.py)

```python
_influence_debug_write_failed: bool = False

def _emit_influence_diagnostic(*, agent_role, injected, matched, threshold, feature_type_id) -> None:
    global _influence_debug_write_failed
    try:
        INFLUENCE_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": "influence_dispatch",
            "agent_role": agent_role,
            "injected": injected,
            "matched": matched,
            "recorded": matched,
            "threshold": threshold,
            "feature_type_id": feature_type_id,
        })
        with INFLUENCE_DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except (OSError, IOError) as e:
        if not _influence_debug_write_failed:
            sys.stderr.write(
                f"[memory-server] influence-debug log write failed ({e}); "
                f"suppressing further diagnostic write errors this session\n"
            )
            _influence_debug_write_failed = True
```

### I-5: RankingEngine.__init__ delta (ranking.py)

**Before (line 32-35):**
```python
self._vector_weight: float = float(config.get("memory_vector_weight", 0.5))
self._keyword_weight: float = float(config.get("memory_keyword_weight", 0.2))
self._prominence_weight: float = float(config.get("memory_prominence_weight", 0.3))
```

**After (append one line with clamp + warn):**
```python
self._vector_weight: float = float(config.get("memory_vector_weight", 0.5))
self._keyword_weight: float = float(config.get("memory_keyword_weight", 0.2))
self._prominence_weight: float = float(config.get("memory_prominence_weight", 0.3))
self._influence_weight: float = _resolve_weight(
    config, "memory_influence_weight", 0.05, warned=_ranker_warned_fields
)  # clamped to [0.0, 1.0]
```

Module-level helper in ranking.py (separate from memory_server.py's `_resolve_float_config` to preserve module isolation per TD-6):

```python
_ranker_warned_fields: set[str] = set()

def _resolve_weight(config: dict, key: str, default: float, *, warned: set[str]) -> float:
    raw = config.get(key, default)
    # Reject bool explicitly — bool is an int subclass, float(True)=1.0 would silently coerce.
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        val = _ranker_warn_and_default(key, raw, default, warned)
    elif isinstance(raw, (int, float)):
        val = float(raw)
    else:  # str
        try:
            val = float(raw)
        except ValueError:
            val = _ranker_warn_and_default(key, raw, default, warned)
    return max(0.0, min(1.0, val))  # clamp silently


def _ranker_warn_and_default(key: str, raw, default: float, warned: set[str]) -> float:
    if key not in warned:
        sys.stderr.write(
            f"[ranker] config field {key!r} value {raw!r} "
            f"is not a float; using default {default}\n"
        )
        warned.add(key)
    return default
```

### I-6: _prominence delta (ranking.py:252)

**Before:** `return 0.30 * norm_obs + 0.15 * confidence + 0.35 * recency + 0.15 * recall + 0.05 * influence`

**After:** `return 0.30 * norm_obs + 0.15 * confidence + 0.35 * recency + 0.15 * recall + self._influence_weight * influence`

### I-7: Config file surface (config.local.md + .claude/pd.local.md)

See C-6 for exact field additions with comments.

### I-8: README_FOR_DEV.md surface

Append 3 new bullet-list entries after line 527 (`memory_promote_min_observations`). Format matches existing table entries (hyphen, backtick-wrapped field name, em-dash separator, prose description, default value in parens).

## Dependencies

- Spec provides AC-1 through AC-11 as testable binary criteria.
- No new Python dependencies. Uses existing stdlib: `pathlib.Path`, `datetime`, `json`, `sys`.
- No migration required (pure config-additive, no schema change).
- Test infrastructure:
  - AC-2, AC-3, AC-10(b): existing `plugins/pd/hooks/lib/semantic_memory/test_ranking.py` (or the nearest existing ranking test file — identify during plan).
  - AC-1, AC-4, AC-5, AC-6, AC-10(a,c,d,e): existing `plugins/pd/mcp/test_memory_server.py` (verified to exist, 60+ lines — extend with new test classes).
  - AC-7, AC-7b, AC-11: validate.sh extension (grep assertions) OR a new pytest node `test_docs_sync.py`. Pick one during plan; validate.sh is the simpler path.
