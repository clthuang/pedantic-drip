# Design: Memory Feedback Loop

## Prior Art Research

### Codebase Patterns
- **Memory enrichment pattern:** `search_memory` is called before each dispatch, results placed INSIDE `prompt: |` as `## Relevant Engineering Memory`. Only on fresh dispatches (I1-R4), not resumed (I2). Category varies by agent role.
- **Post-dispatch processing:** Only existing hook is I9 `Files read:` fallback detection. No influence tracking exists post-dispatch.
- **merge_duplicate() SQL:** Hardcoded single UPDATE incrementing `observation_count` and unioning keywords. No dynamic builder or confidence mutation.
- **Config propagation:** `_process_store_memory()` receives `config: dict | None` as kwarg. `MemoryDatabase` class itself takes no config — config-driven behavior lives in `memory_server.py`.
- **Legacy path:** `build_memory_context()` branches on `memory_semantic_enabled`. No deprecation warning pattern exists — CLAUDE.md says "delete old code, don't maintain compatibility shims."

### External Research
- **Influence tracking:** Production systems store (query, context, response) triples and attach downstream outcome signals. Kernel SHAP and ContextCite provide per-document attribution. Our v1 substring match is a pragmatic simplification.
- **Confidence evolution:** MemOS/SAGE use lifecycle states (Generated → Activated → Merged → Archived). Temporal validity research (ACL 2024) formalizes that confidence must account for when a fact was true.
- **Cold start:** Two-phase approach — Phase 1 ranks on semantic similarity only, Phase 2 blends with learned utility via configurable alpha that ramps as data accumulates. Our system is in Phase 1.
- **Legacy deprecation:** Strangler Fig pattern (Azure/Fowler) — facade routes traffic based on config, migrate incrementally, decommission when parity confirmed.

## Architecture Overview

### Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                    Command Files (5)                          │
│  specify.md, design.md, create-plan.md,                      │
│  create-tasks.md, implement.md                               │
│                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │ Pre-dispatch │───>│ Task dispatch │───>│ Post-dispatch  │  │
│  │ search_memory│    │ (prompt incl │    │ influence scan │  │
│  │ + store names│    │  memory sect)│    │ + record_influ │  │
│  └─────────────┘    └──────────────┘    └────────────────┘  │
└──────────┬───────────────────────────────────────┬───────────┘
           │                                       │
           v                                       v
┌─────────────────────────┐         ┌─────────────────────────┐
│   Memory MCP Server     │         │   Memory MCP Server     │
│   search_memory()       │         │   record_influence()    │
└─────────┬───────────────┘         └─────────┬───────────────┘
          │                                   │
          v                                   v
┌────────────────────────────────────────────────────────────┐
│              MemoryDatabase (SQLite)                        │
│                                                            │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐    │
│  │ entries   │  │ entries_fts  │  │ influence_log     │    │
│  │ (774 rows)│  │ (FTS5 index) │  │ (new data here)   │    │
│  └──────────┘  └──────────────┘  └───────────────────┘    │
│                                                            │
│  merge_duplicate() ── [NEW] confidence promotion logic     │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Session Start:
   injector.py → retrieve → rank → inject top-N → session context
   (update recall_count for injected entries)

2. Command Dispatch (per subagent):
   a. search_memory(query, limit=5, brief=true, category=...)
   b. Store returned entry names in working context
   c. Build Task prompt WITH ## Relevant Engineering Memory section
   d. Dispatch subagent
   e. Receive subagent output
   f. Scan output for stored entry names (exact substring match)
   g. For each match: record_influence(entry_name, agent_role, feature_type_id)

3. Memory Capture (existing, unchanged):
   store_memory → extract_keywords → compute_embedding → dedup_check
   └── if duplicate: merge_duplicate() → [NEW] check promotion thresholds
   └── if new: insert_new_entry()

4. Ranking (existing, no code change):
   prominence = 0.25*obs + 0.15*conf + 0.25*recency + 0.15*recall + 0.20*influence
   (recall and influence will now have non-zero values)
```

## Components

### C1: Command File Memory Pattern (REQ-1 + REQ-2)

**Responsibility:** Ensure every eligible subagent receives memory context and influence is tracked post-dispatch.

**Pattern template (added to each eligible dispatch block):**

```markdown
**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
limit=5, brief=true, and category="{category}".
Store the returned entry names for post-dispatch influence tracking.
Include non-empty results as:

Task tool call:
  ...
  prompt: |
    {existing prompt content}

    ## Relevant Engineering Memory
    {search_memory results from the pre-dispatch call above}

**Post-dispatch influence tracking:**
If search_memory returned entries before this dispatch:
  For each entry name in the stored list:
    If entry name appears as a case-insensitive exact substring in the subagent's output:
      call record_influence(entry_name=<name>, agent_role=<subagent_type>,
        feature_type_id=<current feature type_id from .meta.json>)
  If no entries matched: no action (valid — not all memories will be referenced)
  If record_influence fails: warn "Influence tracking failed: {error}", continue
  If .meta.json missing or type_id unresolvable: skip influence recording with warning
```

**Affected dispatch blocks (15 total):**

| Command | Agent | Line | Category |
|---------|-------|------|----------|
| specify.md | spec-reviewer | 57 | anti-patterns |
| specify.md | phase-reviewer | 198 | (none) |
| design.md | design-reviewer | 246 | anti-patterns |
| design.md | phase-reviewer | 435 | (none) |
| create-plan.md | plan-reviewer | 63 | anti-patterns |
| create-plan.md | phase-reviewer | 188 | (none) |
| create-tasks.md | task-reviewer | 63 | anti-patterns |
| create-tasks.md | phase-reviewer | 223 | (none) |
| implement.md | code-simplifier | 74 | patterns |
| implement.md | test-deepener | 131 | anti-patterns |
| implement.md | test-deepener | 187 | anti-patterns |
| implement.md | implementation-reviewer | 306 | anti-patterns |
| implement.md | code-quality-reviewer | 482 | anti-patterns |
| implement.md | security-reviewer | 635 | anti-patterns |
| implement.md | implementer | 845 | (none) |

**Category "(none)" note:** Phase-reviewer and implementer dispatches use no category filter — `search_memory` is called without a category, returning results across all categories. This is intentional: these agents benefit from broad memory context rather than a specific category.

**Excluded (research agents):** codebase-explorer (design.md:65), internet-researcher (design.md:88) — these gather raw data, not act on engineering judgments.

**Prompt block clarification:** Command files like implement.md have many `prompt: |` blocks (14 in implement.md). Only the FRESH (I1-R4) dispatch for each eligible agent gets memory enrichment — resumed dispatches (I2, I2-FV, I7) do not include the memory section, matching the existing pattern. The 7 eligible dispatches in implement.md correspond to 7 distinct agents (code-simplifier, test-deepener x2, implementation-reviewer, code-quality-reviewer, security-reviewer, implementer), each with their first/fresh prompt block.

### C2: Confidence Auto-Promotion (REQ-3)

**Responsibility:** Evolve confidence based on accumulated evidence when dedup merges occur.

**Integration point:** `database.py:merge_duplicate()`

**Call chain:**
```
memory_server.py:_process_store_memory(config=_config)
  → check_duplicate(embedding, db, threshold)
    → if duplicate: db.merge_duplicate(existing_id, keywords, config=cfg)
```

**Config propagation (full lifecycle trace):**
1. `session-start.sh` reads `pd.local.md` → injects config values into session context
2. `memory_server.py:lifespan()` calls `read_config(project_root)` → stores as module-level `_config` dict
3. `memory_server.py:store_memory()` MCP handler calls `_process_store_memory(config=_config)` (line 375)
4. `_process_store_memory()` sets `cfg = config or {}` (line 105)
5. On dedup: `db.merge_duplicate(existing_id, keywords, config=cfg)` → config reaches promotion logic

`read_config()` (config.py) merges `pd.local.md` overrides on top of `DEFAULTS`. New keys added to DEFAULTS are guaranteed to be in `cfg` even when not set in `pd.local.md`.

**Changes:**
1. `merge_duplicate()` signature: add `config: dict | None = None` parameter
2. `_process_store_memory()`: pass `config=cfg` kwarg to `db.merge_duplicate()` call
3. `config.py` DEFAULTS: add 3 new keys (single source of truth for defaults):
   - `memory_auto_promote`: `False`
   - `memory_promote_low_threshold`: `3`
   - `memory_promote_medium_threshold`: `5`
4. Promotion code uses `config.get()` with fallback defaults matching DEFAULTS for defense-in-depth

**Promotion logic — transaction-aware placement:**

The existing `merge_duplicate()` transaction structure (database.py:453-489) is:
```python
self._conn.execute("BEGIN IMMEDIATE")  # line 453
try:
    row = self._conn.execute("SELECT * ...").fetchone()  # line 455
    # ... keyword merging ...
    self._conn.execute("UPDATE entries SET observation_count = observation_count + 1, ...")  # line 481
    # >>> PROMOTION UPDATE GOES HERE (before COMMIT) <<<
    self._conn.commit()  # line 486
except Exception:
    self._conn.rollback()
    raise
```

The promotion UPDATE must be inserted BETWEEN line 484 (existing UPDATE) and line 486 (COMMIT) so both mutations are atomic within the same BEGIN IMMEDIATE transaction. This ensures a crash between the two UPDATEs cannot leave observation_count incremented without confidence promoted.

```python
# After the existing UPDATE (line 484), before self._conn.commit() (line 486):
if config and config.get("memory_auto_promote"):
    # entry dict holds the PRE-UPDATE observation_count (row snapshot from line 455)
    # BEGIN IMMEDIATE serializes writers, so no TOCTOU gap exists for single-connection access
    new_count = entry["observation_count"] + 1
    conf = entry["confidence"]
    src = entry.get("source", "")

    if src != "import":
        low_thresh = config.get("memory_promote_low_threshold", 3)
        med_thresh = config.get("memory_promote_medium_threshold", 5)

        new_conf = None
        if conf == "low" and new_count >= low_thresh:
            new_conf = "medium"
        elif conf == "medium" and new_count >= med_thresh and src == "retro":
            new_conf = "high"

        if new_conf:
            self._conn.execute(
                "UPDATE entries SET confidence = ? WHERE id = ?",
                (new_conf, existing_id)
            )

self._conn.commit()  # existing line 486 — commits both obs_count + confidence atomically
```

**Concurrency note:** `BEGIN IMMEDIATE` acquires a reserved lock, preventing concurrent writers. The `entry["observation_count"]` read is from the row snapshot within the same transaction, so `new_count = entry["observation_count"] + 1` is correct (no TOCTOU gap).

**Design decision:** Separate conditional UPDATE (not refactoring to dynamic builder). Minimal diff, lower regression risk, promotion UPDATE only fires when conditions are met (rare path).

### C3: Keyword Backfill (REQ-4)

**Responsibility:** Populate empty keywords for the existing 774-entry corpus.

**Mechanism:** Use existing `semantic_memory.writer --action backfill-keywords` CLI (writer.py:148).

**Execution:** Run as a one-time migration step during feature delivery:
```bash
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs dirname)
PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" \
  -m semantic_memory.writer --action backfill-keywords --global-store ~/.claude/pd/memory
```

**No code changes needed** — the backfill action already exists and calls `extract_keywords()` (Tier 1 regex) for entries with empty `[]` keywords. Implementation should verify on a 10-entry sample before running against the full corpus (risk accepted given idempotency guarantee).

### C4: Legacy Path Deprecation (REQ-5)

**Responsibility:** Deprecate `memory.py` injection with 1-release escape hatch.

**Change in `session-start.sh:build_memory_context()`:**

```bash
# Current code (line ~425):
if [ "$memory_semantic_enabled" = "true" ]; then
    # semantic injector path
else
    # legacy memory.py path
fi

# New code:
if [ "$memory_semantic_enabled" = "false" ]; then
    # Output deprecation to stdout (not stderr — stderr is suppressed in hooks per CLAUDE.md)
    # This appears in the session context as a warning line
    deprecation_warning="[DEPRECATED] memory_semantic_enabled=false — legacy memory.py injection will be removed next release."
    echo "$deprecation_warning"  # appears in session context output (visible to model + user)
    # legacy memory.py path
else
    # semantic injector path (default)
fi
```

The deprecation warning is output to stdout (appended to the session context output) rather than stderr, because CLAUDE.md mandates `2>/dev/null` for hook subprocesses. This is the definitive approach — stdout is consistent with existing session-start output patterns and immediately visible.

**Design decision:** Invert the conditional to make semantic the default path (matching the existing default=true). The `false` branch becomes the explicit opt-in for legacy.

### C5: Ranking Verification (REQ-6)

**Responsibility:** Verify existing ranking engine works correctly with non-zero feedback signals.

**No code changes.** Add tests that:
1. Create entries with non-zero `influence_count` and verify they rank higher
2. Create entries with non-zero `recall_count` and verify they rank higher
3. Verify both contribute to the prominence sub-score per documented weights

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Influence detection | Exact substring match on entry names | Zero-cost, deterministic, sufficient for v1 data collection. LLM attribution deferred to Phase 3 |
| Confidence promotion trigger | On dedup merge only | merge_duplicate() already fetches full row. Avoids adding logic to _update_existing() which fires on hash collisions (same entry, no new evidence) |
| Confidence promotion SQL | Separate conditional UPDATE | Minimal diff vs. refactoring hardcoded UPDATE to dynamic builder. Lower regression risk |
| Config propagation | Pass config kwarg through call chain | Follows existing pattern: _process_store_memory() already receives config |
| Legacy deprecation | Inverted conditional with warning | Strangler Fig pattern — route default to new, warn on old. No facade needed for this simple branch |
| Research agent exclusion | Skip memory enrichment for codebase-explorer, internet-researcher | These gather raw data, not act on engineering judgments |
| Auto-promote default | Off (memory_auto_promote=false) | Conservative — enable incrementally after verifying corpus quality |

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| False positive influence matches | Noise in influence_log | Medium | Acceptable for v1; entry names are typically multi-word phrases reducing false matches. Phase 3 LLM attribution improves precision |
| Confidence over-promotion | Low-quality entries surface more | Low | Config flag defaults off; retro-source requirement for high prevents spam |
| merge_duplicate() regression | Broken dedup merging | Low | Separate UPDATE keeps existing SQL unchanged; comprehensive unit tests |
| Command file edit errors | Broken agent dispatch | Medium | 15 blocks across 5 files is mechanical but large. Grep-based validation tests catch structural issues |
| Session-start latency | Timeout breach from influence tracking | None | Influence tracking is post-dispatch, not in session-start path. No latency impact on injection |
| recall_count remains unreliable | 15% of prominence sub-score (4.5% of total) reads dead signal | Medium | Known gap deferred to Phase 2 per PRD Migration Path. This feature closes the influence loop; recall loop investigation is Phase 2 step 3 |
| Deprecation warning swallowed | stderr suppressed in session-start.sh | Medium | Output deprecation to stdout (part of injected memory context) rather than stderr, or log to file checked by /pd:doctor |

## Interfaces

### Modified MCP Interface: merge_duplicate()

```python
# BEFORE:
def merge_duplicate(
    self,
    existing_id: str,
    new_keywords: list[str],
) -> dict:

# AFTER:
def merge_duplicate(
    self,
    existing_id: str,
    new_keywords: list[str],
    config: dict | None = None,
) -> dict:
    """Merge a near-duplicate into an existing entry.

    Increments observation_count, updates updated_at, unions keywords.
    If config['memory_auto_promote'] is True, checks promotion thresholds.
    Returns the updated entry dict (includes new confidence if promoted).
    """
```

### Modified MCP Call Chain

```python
# memory_server.py:_process_store_memory()
# BEFORE (line ~110):
merged = db.merge_duplicate(dedup_result.existing_entry_id, keywords)

# AFTER:
merged = db.merge_duplicate(dedup_result.existing_entry_id, keywords, config=cfg)
```

### Command File Pattern Interface

Each eligible dispatch block follows this contract:

**Input:**
- `search_memory` MCP tool (query, limit, brief, category)
- Feature context (`.meta.json` type_id)

**Output:**
- Memory section embedded in Task prompt (or omitted if empty)
- `record_influence` calls for matched entry names (or skipped on failure)

**Error contract:**
- All memory operations are non-blocking
- Failures produce warnings, never block agent dispatch
- Missing `.meta.json` → skip influence recording

### Config Interface

New keys in `pd.local.md`:

```yaml
memory_auto_promote: false          # Enable confidence auto-promotion
memory_promote_low_threshold: 3     # obs_count for low→medium
memory_promote_medium_threshold: 5  # obs_count for medium→high (also requires source=retro)
```

## Traceability

| Spec REQ | Design Component | Key ACs Covered |
|----------|-----------------|-----------------|
| REQ-1 | C1 (Command Pattern) | Memory section inside prompt:, omit when empty |
| REQ-2 | C1 (Command Pattern) | Post-dispatch influence scan, non-blocking |
| REQ-3 | C2 (Confidence Promotion) | Configurable thresholds, import exclusion, retro gate |
| REQ-4 | C3 (Keyword Backfill) | <10% empty post-migration, idempotent |
| REQ-5 | C4 (Legacy Deprecation) | Default true, warning on false, toggle functional |
| REQ-6 | C5 (Ranking Verification) | Non-zero signals rank higher |

**C3 validation step:** After running backfill, execute:
```sql
SELECT COUNT(*) * 100.0 / (SELECT COUNT(*) FROM entries)
FROM entries WHERE keywords = '[]';
```
Result must be < 10.0.

## Dependencies

```
C1 (Command Pattern) ← no dependencies, can start immediately
C2 (Confidence Promotion) ← no dependencies, can start immediately
C3 (Keyword Backfill) ← no technical dependency; sequenced last as a migration step (run after C1/C2 complete)
C4 (Legacy Deprecation) ← no dependencies, can start immediately
C5 (Ranking Verification) ← depends on C2 tests being complete (shared test infrastructure)
```

All 5 components are parallelizable except C5 which shares test infrastructure with C2.
