# Spec: Orchestrator Mid-Session Memory Refresh

**Feature:** 081-mid-session-memory-refresh-hoo
**Parent:** project P002-memory-flywheel
**Source:** P002 PRD rescope notes (2026-04-15) — original "memory is push-only at SessionStart" claim was PARTIAL. 65+ `search_memory` call sites across 17 command files in `plugins/pd/commands/*.md` already refresh memory for **sub-agents** before dispatch. The gap is the **orchestrator's own** main-context memory, which only sees the session-start snapshot.

## Problem

Long pd workflow sessions (a 4-phase feature can take hours across multiple `complete_phase` boundaries) run the orchestrator's main Claude context with a stale memory snapshot. When a new entry is stored (via `store_memory` from a retro or `/pd:remember`), sub-agents see it on their next pre-dispatch enrichment — but the orchestrator coordinating them does not, until session restart.

Symptoms this causes:
- Orchestrator schedules a dispatch whose pre-dispatch enrichment pulls a memory entry the orchestrator itself hasn't seen — sub-agent findings reference context the orchestrator can't match.
- New anti-patterns captured during an earlier phase (e.g., specify captures a "don't do X" rule) don't influence orchestrator decisions in a later phase (e.g., implement) until session restart.
- Cumulative learning across the feature is capped at session-start snapshot + whatever the orchestrator picks up from sub-agent return values.

Ship a narrow fix: on `complete_phase` MCP responses, return a compact memory digest the orchestrator can read. Leverage the existing embedding-based ranking by extracting a shared helper module that both MCP servers can import.

## Goals

1. Inject a bounded-size memory digest into `complete_phase` responses so the orchestrator sees fresh entries at phase boundaries.
2. Extract a shared in-process retrieval helper under `plugins/pd/hooks/lib/semantic_memory/` so `workflow_state_server.py` and `memory_server.py` both use it — avoids duplicating the embedding + ranking pipeline.
3. Opt-in with sane default: on by default, config-disableable for regression safety.
4. Measurable via 080's diagnostic framework (feeding back into the flywheel this project is building).
5. **Do NOT** add a new MCP tool, a new hook script, new DB columns, or new embedding infrastructure. A new shared Python helper module is allowed and expected — it is NOT a new MCP tool.

## Non-Goals (explicit)

- Refreshing on every tool call (cost explosion; `complete_phase` only).
- Refreshing on `get_phase` / `transition_phase` (read-only queries don't warrant a refresh cost).
- Refreshing into sub-agent contexts (already handled by 65+ pre-dispatch enrichment sites across 17 commands).
- PostToolUse hook-based refresh — MCP response injection is simpler and doesn't require hook infrastructure changes. A hook-based variant remains a viable follow-up if MCP-response-based refresh proves insufficient in practice (not rejected; deferred).
- Long-lived orchestrator memory cache (stateless per-call refresh is sufficient).
- Automatic memory de-duplication against what orchestrator already saw (orchestrator reads the digest freshly each time; dedup is the orchestrator's problem).

## Scoping Decisions Made During Spec Authoring

- **Integration point:** MCP response injection chosen over PostToolUse hook because (a) simpler — no new hook script, no hook-dispatch ordering concerns; (b) payload is synchronously visible to the orchestrator as tool result content; (c) easier to disable (config flag vs hook removal). Hook-based path remains a viable follow-up.
- **Shared helper module:** Required because `workflow_state_server.py` and `memory_server.py` run as separate stdio MCP subprocesses today and do not share module-level state. A new `plugins/pd/hooks/lib/semantic_memory/refresh.py` extracts the retrieval logic so both can import it. This does NOT count as "new infrastructure" — it is a pure refactor of existing logic into a reusable shape.
- **Confidence filter:** `search_memory` has no confidence-filter parameter today. Rather than modifying the public MCP tool, the new helper module applies the confidence filter post-retrieval. Keeps the MCP surface unchanged.

## Functional Requirements

### FR-1: `complete_phase` emits `memory_refresh` field
The `_process_complete_phase` function in `plugins/pd/mcp/workflow_state_server.py` MUST append an optional `memory_refresh` field to the JSON response when ALL of:
- `memory_refresh_enabled: true` in config (default true), AND
- `db is not None` (the MCP server has a live database connection; see existing line 754 guard), AND
- The call succeeded (`result` contains `last_completed_phase`), AND
- The shared refresh helper returns a non-empty digest.

Field shape:
```json
"memory_refresh": {
  "query": "<feature_slug> <next_phase>",
  "count": N,
  "entries": [
    {"name": "...", "category": "patterns|anti-patterns|heuristics", "description": "..."},
    ...
  ]
}
```

If any precondition fails (disabled, no db, error path, empty digest), the field is OMITTED from the response (not null, not empty — absent). Callers must tolerate absence. Warnings (`cascade_warning`, `projection_warning`, `artifact_warnings`) DO NOT suppress refresh — the call is still considered "successful" for refresh purposes as long as `last_completed_phase` is set.

### FR-2: Query construction
The query string is built by a new helper `_build_refresh_query(feature_type_id: str, completed_phase: str) -> str` in the shared refresh module:

1. **Feature slug extraction:** Apply regex `r"^feature:\d+-(.+)$"` to `feature_type_id`; capture group 1 is the slug. Example: `"feature:081-mid-session-memory-refresh-hoo"` → slug `"mid-session-memory-refresh-hoo"`. Example: `"feature:100-foo-bar"` → slug `"foo-bar"`. If the regex doesn't match, return empty string — caller omits field.
2. **Next phase lookup:** Use an inline mapping local to the helper:
   ```python
   _NEXT_PHASE = {
       "brainstorm": "specify", "specify": "design", "design": "create-plan",
       "create-plan": "implement", "implement": "finish", "finish": "",
   }
   ```
   `finish → ""` is intentional (deviates from `entity_registry._derive_next_phase('finish') == 'finish'` because "what comes next after finish?" is semantically empty, not a repeat of the completed phase). Do NOT import `_derive_next_phase`.
3. **Assembly:** `f"{slug} {_NEXT_PHASE.get(completed_phase, '')}".strip()`. Trailing space handled by `.strip()`.

### FR-3: Entry selection — behavioral contract

**Refactoring constraint (structural, not optional):** `_process_search_memory` at `memory_server.py:311-340` MUST be refactored to call the same extracted retrieval function that `refresh_memory_digest` calls. This makes ranking-parity (AC-13) structural, not coincidental. Direct invocation of `_process_search_memory` from `refresh_memory_digest` is NOT acceptable because the two live in separate MCP subprocesses.

The new helper `refresh_memory_digest(db, provider, query: str, limit: int) -> list[dict] | None` MUST produce the following behavior (design phase identifies the exact extracted-callable name; spec constrains only the observable contract):

1. **Retrieve candidates** via the extracted embedding + vector-search function. Oversample by requesting `limit * 3` candidates (ceiling, not floor — if DB has fewer matching rows, use whatever is returned; no error).
2. **Apply confidence filter** as a post-filter: `filtered = [e for e in results if e["confidence"] in ("medium", "high")]`.
3. **Apply ranking** by passing `filtered` through the existing `RankingEngine.rank(...)` — reuses 080-tuned weights including `_influence_weight`.
4. **Truncate** to `limit` entries.
5. **Return** the list (or `None` on no embedding provider, DB error, or empty result).

### FR-4: Entry serialization (deterministic byte budget)
Each entry in the response contains ONLY three string fields: `name`, `category`, `description`. Do NOT include `observation_count`, `influence_count`, `references`, embeddings, metadata, or timestamps.

**Size enforcement:** After building the list, serialize via `json.dumps(entries)`; if the result exceeds 2000 bytes (~500 tokens at 4 bytes/token), truncate each entry's `description` field to 240 chars and re-serialize. If still >2000 bytes, drop entries from the end until ≤2000 bytes. The final list may contain fewer than `limit` entries — this is acceptable; `count` reflects the actual post-trim count.

### FR-5: Config fields
Add two new fields to `plugins/pd/templates/config.local.md` (comments preserved):
- `memory_refresh_enabled: true` — "inject memory digest into complete_phase responses so orchestrator sees fresh entries at phase boundaries; disable to revert to session-start-only memory"
- `memory_refresh_limit: 5` — "max memory entries in per-phase refresh digest; clamped to [1, 20]; each entry description capped at 240 chars"

Also add to `.claude/pd.local.md` (repo config) as `memory_refresh_enabled: true` + `memory_refresh_limit: 5` (no special debug-collection value; unlike 080, this feature is not under active measurement).

Add 2 bullet lines to `README_FOR_DEV.md` memory config table (append after `memory_influence_debug` from 080).

**Precedence:** Project-local `.claude/pd.local.md` overrides template defaults at config-read time. This matches existing config resolution in `plugins/pd/hooks/lib/semantic_memory/config.py` — no new precedence logic.

### FR-6: Diagnostics reuse
When `memory_influence_debug: true` (the 080 config flag), append a JSON line per refresh to `INFLUENCE_DEBUG_LOG_PATH` via a new helper `_emit_refresh_diagnostic(...)` in `refresh.py`:

```json
{"ts": "2026-04-16T...Z", "event": "memory_refresh", "feature_type_id": "...", "completed_phase": "...", "query": "...", "entry_count": N, "elapsed_ms": M}
```

Writes to the **same** `INFLUENCE_DEBUG_LOG_PATH` used by 080 (at `~/.claude/pd/memory/influence-debug.log`) — not stderr. Operators already tail this file; no new log to manage. The `elapsed_ms` field is measured wall-clock time of the retrieval call (see FR-7).

**Dedup flags required** (avoids drift vs 080's pattern; all per-process — each MCP subprocess gets its own copy, which is the intended semantic since each subprocess reads config/env independently):
- `_slow_refresh_warned: bool` in `refresh.py` (FR-7 latency warning) — one-shot per process.
- `_refresh_error_warned: bool` in `refresh.py` (FR-8 helper errors) — one-shot per process.
- For malformed-config warnings (FR-8 int helper), declare a new `_refresh_warned_fields: set[str]` in `refresh.py`. Do NOT import `_warned_fields` from `memory_server.py` — that module lives in a different MCP subprocess at runtime, so the import would either create a circular-dependency risk or (if the import succeeds) each subprocess would still get its own copy, adding coupling for no deduplication benefit. The new set in `refresh.py` follows the same bool-rejection + dedup pattern as 080's `_warned_fields` but is owned by the shared helper module.

### FR-7: Latency observation (not pre-emption)
Measure wall-clock time around the retrieval call using `time.perf_counter()`. If the elapsed time exceeds 500ms, emit ONE stderr warning with the prefix `[workflow-state] memory_refresh took {ms}ms (>500ms budget)`. Use a module-level `_slow_refresh_warned: bool` flag so the warning fires once per process (deduped, matching 080's pattern).

**Important honest limitation:** The guard CANNOT pre-empt a single slow call — synchronous retrieval has already completed by the time we measure. The guard only warns the operator so they can investigate or disable. The field is INCLUDED in the response even if slow (we already paid the cost).

This is a deliberate deviation from the original spec iter-1 AC-10 ("omit the field if slow"). Spec iter-1 was infeasible without a timeout refactor that breaks NFR-1. Honest observation > infeasible pre-emption.

### FR-8: Error handling
- Embedding provider unavailable → omit field, no error.
- Shared helper raises → catch in `_process_complete_phase`, log one warning via `_refresh_error_warned` flag, omit field.
- Config malformed (`memory_refresh_limit: "five"`) → fall back to default 5, emit one-shot stderr warning via a new `_resolve_int_config(key, default, clamp=(min, max))` helper analogous to 080's `_resolve_float_config`. Bool rejection required (as in 080 — `isinstance(raw, bool)` check before `isinstance(raw, int)`).
- Feature slug regex mismatch (FR-2 step 1) → omit field silently.
- `db is None` branch at `workflow_state_server.py:754` → omit field silently (no project context to refresh against).

### FR-9: No regression of existing complete_phase callers
Existing MCP callers receive the same response shape PLUS the new optional field. JSON parsers that don't know about `memory_refresh` still work. Existing tests for `complete_phase` MUST pass unchanged — verified by running the current test suite after the change.

## Non-Functional Requirements

- **NFR-1 Additive only**: No new MCP tools, no DB migration, no new log files, no new embedding pipeline. Allowed: one new shared Python helper module under `plugins/pd/hooks/lib/semantic_memory/refresh.py` imported by both MCP servers.
- **NFR-2 Token budget**: refresh digest ≤2000 bytes (~500 tokens). Enforced deterministically by FR-4 byte cap.
- **NFR-3 Latency observability (not pre-emption)**: >500ms retrieval time triggers one-shot stderr warning; does not block the response.
- **NFR-4 Backward compatible**: MCP contract unchanged — new field is strictly additive.
- **NFR-5 Zero-overhead when disabled**: When `memory_refresh_enabled: false`, no embedding call or DB query is performed. Short-circuit happens before the retrieval call site.

## Out of Scope

- Refresh on `get_phase`, `transition_phase`, or any other MCP tool.
- Orchestrator-side de-duplication (orchestrator reads the digest; dedup is its problem).
- PostToolUse hook-based refresh — deferred to a future feature if MCP-response-based refresh proves insufficient.
- Cross-project filtering — inherit whatever behavior the existing retrieval path has (currently: no project-scoped filtering in `search_memory`).
- Digest caching across phases within a session (each complete_phase call gets a fresh search — K queries per feature is negligible).
- Measuring "did the refresh change orchestrator behavior?" — that's a 080 follow-up (082 + future instrumentation).
- Modifying the public `search_memory` MCP tool signature — confidence filter lives in the new helper only.

## Acceptance Criteria

- [ ] **AC-1 field presence**: Call `complete_phase` on a feature with a non-null `last_completed_phase`. With `memory_refresh_enabled: true`, a working provider, and a fixture DB containing 3 medium/high confidence entries matching the query, response JSON contains `memory_refresh` with shape per FR-1. Verified by unit test.
- [ ] **AC-2 field absence when disabled**: With `memory_refresh_enabled: false`, call `complete_phase`. Assert `memory_refresh` key NOT in response. Mock the retrieval helper and assert call count == 0 (NFR-5 zero-overhead).
- [ ] **AC-3 field absence when no provider**: Provider = None. Assert `memory_refresh` absent. No exception. No stderr warning (silent expected-omit).
- [ ] **AC-4a query construction (normal)**: For `feature_type_id: "feature:081-mid-session-memory-refresh-hoo"`, completing `"specify"` → query = `"mid-session-memory-refresh-hoo design"`.
- [ ] **AC-4b query construction (finish)**: Completing `"finish"` → query = `"mid-session-memory-refresh-hoo"` (no trailing space via `.strip()`).
- [ ] **AC-4c query construction (3-digit ID)**: For `feature_type_id: "feature:100-foo-bar"`, completing `"design"` → query = `"foo-bar create-plan"`.
- [ ] **AC-4d query construction (regex mismatch)**: For `feature_type_id: "feature:weird-id"` (no digit prefix), the helper returns empty string → `memory_refresh` absent from response.
- [ ] **AC-5 limit clamping**: `memory_refresh_limit: 0` → clamped to 1. `memory_refresh_limit: 100` → clamped to 20. `memory_refresh_limit: "bad"` → default 5 + warning. `memory_refresh_limit: True` → default 5 + warning (bool rejection).
- [ ] **AC-6 entry shape**: Each entry in `entries` has exactly 3 keys: `{"name", "category", "description"}`. No extra fields.
- [ ] **AC-7 low-confidence filter**: Seed DB with 3 entries: one low, one medium, one high confidence, all matching the query. Refresh with limit=10. Assert only medium and high appear (count == 2 in response).
- [ ] **AC-8 diagnostic emission**: With `memory_influence_debug: true`, one line appended to `INFLUENCE_DEBUG_LOG_PATH` per refresh with `"event": "memory_refresh"` and an `elapsed_ms` field. Matches 080's log format.
- [ ] **AC-9 no regression**: All existing tests in `plugins/pd/mcp/test_workflow_state_server.py` pass unchanged. Additionally: `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v` reports ≥N_before passing (N_before captured in implementation phase baseline).
- [ ] **AC-10 latency observability**: Mock the retrieval helper to take 600ms. Call `complete_phase`. Assert (a) `memory_refresh` field IS present (not pre-empted), (b) one stderr warning emitted matching regex `\[workflow-state\] memory_refresh took \d+ms`, (c) second slow call emits NO additional warning (deduped via `_slow_refresh_warned` flag), (d) phase transition itself succeeds normally.
- [ ] **AC-11 byte cap**: Construct fixture with 10 entries each having a 500-char description. Refresh with limit=10. Assert serialized `entries` JSON is ≤2000 bytes AND descriptions in the response are each ≤240 chars AND entries may be fewer than 10 (byte cap truncates).
- [ ] **AC-12 docs sync**: `grep -c "^memory_refresh_" .claude/pd.local.md` returns 2. `grep -c "^memory_refresh_" plugins/pd/templates/config.local.md` returns 2. `grep -c "memory_refresh_" README_FOR_DEV.md` returns ≥2 (allows prose references).
- [ ] **AC-13 existing search_memory path unchanged**: For a fixed query Q and a DB containing K entries with seeded deterministic embeddings (via `_FixedSimilarityProvider` pattern from 080's `test_memory_server.py`; if that class is not yet in a shared test helper, define it locally in the new test file), the first `min(K, search_memory_limit, refresh_pre_filter_limit)` entries returned by `search_memory` MUST appear in the SAME RELATIVE ORDER in the pre-confidence-filter intermediate list of `refresh_memory_digest`. Verified by unit test asserting list-slice equality on entry names. Confirms the shared refactor doesn't regress existing retrieval.
- [ ] **AC-14 warning dedup**: Provoke 3 consecutive config-malformed warnings across test cases (use monkeypatch on `_warned_fields` or equivalent). Assert stderr contains exactly 1 warning line (dedup working). Reuses 080's dedup pattern.

## Happy Paths

**HP-1 (default session):** User upgrades. No config change. Phase transitions during a 4-phase feature emit compact memory digests. The orchestrator naturally incorporates the digest content into its next-phase planning. Nothing new to configure.

**HP-2 (operator measures impact):** Operator sets `memory_influence_debug: true`. Runs a feature through all 4 phases. Greps `~/.claude/pd/memory/influence-debug.log` for `"event": "memory_refresh"` — sees 4 refresh lines (one per complete_phase). Computes avg `elapsed_ms` across calls; confirms within budget. Samples a few entries from responses to verify relevance to the feature slug.

**HP-3 (regression safety):** Operator suspects the refresh is confusing orchestrator decisions on a specific feature. Sets `memory_refresh_enabled: false`. `complete_phase` responses revert to pre-081 shape. Feature completes without incident. Config flag documented as a rollback lever.

**HP-4 (provider outage):** The Gemini embedding provider is temporarily unavailable mid-session. `complete_phase` still succeeds; `memory_refresh` field is silently absent for the affected calls. Orchestrator falls back to its existing session-start snapshot. No hard failure.

**HP-5 (slow retrieval):** DB on slow disk causes a 700ms retrieval. First complete_phase call emits one stderr warning about latency; field is still delivered. Subsequent slow calls same session do NOT emit new warnings. Operator investigates disk state when convenient; no session disruption.

## Rollback

Revert the single feature commit. The two config fields are additive and silently default to absent. Zero data migration. Zero downstream caller breakage (response field is optional).

## References

- P002 PRD: `docs/projects/P002-memory-flywheel/prd.md` (Rescope Notes, 2026-04-15, item 4 "Orchestrator Mid-Session Refresh")
- 080 (completed, v4.15.1): `docs/features/080-influence-wiring/spec.md` — this feature reuses 080's `INFLUENCE_DEBUG_LOG_PATH`, debug-flag pattern, bool-rejection pattern, and dedup-warning pattern
- Existing enrichment precedent: 65+ call sites across 17 commands in `plugins/pd/commands/*.md` calling `search_memory` before Task dispatches
- `plugins/pd/mcp/workflow_state_server.py:665-778` (`_process_complete_phase`) — injection point
- `plugins/pd/mcp/memory_server.py:311-340` (`_process_search_memory`) — retrieval callable to extract into `refresh.py`
- `plugins/pd/hooks/lib/semantic_memory/ranking.py` — `RankingEngine.rank()` reused unchanged
