# Specification: Enforced State Machine (Phase 1)

## Overview

Phase 1 of the enforced state machine deploys a PreToolUse hook that blocks all direct `.meta.json` writes, updates 9 LLM-driven write sites to use MCP tools (3 new + 2 extended), adds a `.meta.json` projection function, and instruments blocked attempts for 2-week measurement.

**Scope:** Phase 1 covers FR-7, FR-8, FR-11 from the PRD, plus FR-4 (extend `complete_phase`) and FR-5 (`_project_meta_json` projection) which are necessary dependencies — the hook blocks all `.meta.json` writes and existing MCP tools don't write `.meta.json`, so the projection function is required for Phase 1 to work.

**Scope delta from PRD:** FR-8 says "use existing MCP tools" but existing tools lack creation and activation capabilities. Phase 1 adds 3 minimal MCP tools (`init_feature_state`, `init_project_state`, `activate_feature`) to cover these gaps. These are lightweight precursors to the full `create_feature` CQRS tool planned for Phase 2 (FR-3).

## Requirements Addressed

| Req | Description | Phase | Notes |
|-----|-------------|-------|-------|
| FR-7 | PreToolUse hook `meta-json-guard.sh` blocking ALL Write/Edit to `*/.meta.json` | 1 | |
| FR-8 | Update 9 LLM-driven `.meta.json` write sites to use MCP tools | 1 | 3 new + 2 extended tools |
| FR-11 | Instrumentation — log every blocked write with feature ID, tool name, timestamp | 1 | Calling command not available in hook context |
| FR-4 | Extended `complete_phase` with timing metadata | 1 (pulled forward) | Hook blocks all writes; MCP write path requires projection |
| FR-5 | `.meta.json` projection function `_project_meta_json` | 1 (pulled forward) | Hook blocks all writes; existing MCP tools don't write `.meta.json` |

## Enforcement Boundary

**Critical architectural distinction:** PreToolUse hooks intercept **LLM tool calls** (Write, Edit, Bash) — they run in the Claude Code host process before the tool executes. MCP server Python code writes to the filesystem directly via `open()` / `pathlib.Path.write_text()` **without hook interception**. This is why the MCP-only write path works: MCP tools bypass the hook by design.

```
LLM → Write(.meta.json) → PreToolUse hook → BLOCKED
LLM → transition_phase() → MCP server → Python open() → .meta.json written ✓
```

**Two `.meta.json` write paths in Phase 1 (mutually exclusive):**

1. **Normal path (new):** MCP tool mutates DB → calls `_project_meta_json()` → writes `.meta.json` as synchronous projection. This is the designed path for all 9 write sites.
2. **Degraded path (existing, unchanged):** When DB is unavailable, `_write_meta_json_fallback()` (engine.py:442-512) writes `.meta.json` directly from in-memory state. This runs in Python (not via LLM tool calls), so the hook does NOT block it.

These paths are **mutually exclusive**: `_project_meta_json()` only runs after a successful DB mutation; `_write_meta_json_fallback()` only runs when DB mutation fails. They cannot both write `.meta.json` for the same operation. Phase 2 removes the degraded path when read-only degradation replaces it. **Accepted Phase 1 limitation:** the fallback can create state that the hook would have blocked if done by LLM.

## Functional Specification

### 1. PreToolUse Hook: `meta-json-guard.sh`

**Trigger:** PreToolUse event for `Write` and `Edit` tool calls.

**Behavior:**
1. Read JSON-RPC input from stdin (same pattern as `pre-commit-guard.sh`)
2. Extract `tool_name` and `tool_input` from the input
3. If `tool_name` is not `Write` and not `Edit` → output empty JSON, exit (allow)
4. Extract file path from `tool_input.file_path`
5. If file path does not end with `.meta.json` → allow
6. If file path ends with `.meta.json` → **deny** with:
   ```json
   {
     "hookSpecificOutput": {
       "hookEventName": "PreToolUse",
       "permissionDecision": "deny",
       "permissionDecisionReason": "Direct .meta.json writes are blocked. Use MCP workflow tools instead: transition_phase() to enter a phase, complete_phase() to finish a phase, or init_feature_state() to create a new feature."
     }
   }
   ```
7. Log the blocked attempt (FR-11 instrumentation — see section 3)

**Registration in `hooks/hooks.json`:**

Insert a new entry in the `PreToolUse` array, after the `Bash` matcher (pre-commit-guard) and before the `.*` matcher (yolo-guard):

```json
{
  "matcher": "Write|Edit",
  "hooks": [
    {
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/meta-json-guard.sh"
    }
  ]
}
```

**Matcher syntax note:** The `ExitPlanMode` matcher is a literal string. The `.*` matcher uses regex. `Write|Edit` uses regex OR — this is supported by the Claude Code hooks framework (same regex engine). If empirically this fails, fall back to two separate entries with matchers `Write` and `Edit`.

**No allowlist.** Per PRD Decisions: YAGNI — if a legitimate non-state write need emerges during Phase 1 measurement, add an allowlist then.

**Acceptance Criteria:**
- [ ] `Write(file_path="docs/features/XXX/.meta.json", ...)` returns deny
- [ ] `Edit(file_path="docs/features/XXX/.meta.json", ...)` returns deny
- [ ] `Write(file_path="docs/features/XXX/spec.md", ...)` is allowed (not .meta.json)
- [ ] `Write(file_path="docs/projects/XXX/.meta.json", ...)` returns deny (project .meta.json too)
- [ ] Hook latency < 50ms (NFR-3)
- [ ] Blocked attempt logged with feature ID, tool name, and timestamp
- [ ] Skill/command files contain zero Write/Edit instructions targeting `.meta.json` (verifiable: `grep -rn 'Write.*meta.json\|Edit.*meta.json\|\.meta\.json.*content' plugins/iflow/skills/ plugins/iflow/commands/` returns zero matches post-implementation)

### 2. Skill/Command Write Site Updates (FR-8)

Each of the 9 LLM-driven `.meta.json` write sites must be replaced with MCP tool calls. The 10th site (`_write_meta_json_fallback` in Python) is Phase 2 scope (see Enforcement Boundary section).

#### Site 1: `commands/create-feature.md:97-110` — Initial feature creation

**Current:** LLM writes full `.meta.json` via Write tool with all initial fields.

**Change:** Call new `init_feature_state` MCP tool.

**`init_feature_state` tool spec:**
```python
@server.tool()
async def init_feature_state(
    feature_dir: str,      # e.g., "docs/features/034-enforced-state-machine"
    feature_id: str,       # e.g., "034"
    slug: str,             # e.g., "enforced-state-machine"
    mode: str,             # "standard" or "full"
    branch: str,           # e.g., "feature/034-enforced-state-machine"
    brainstorm_source: str | None = None,
    backlog_source: str | None = None,
    status: str = "active",  # "active" or "planned"
) -> str:
```
- Writes `.meta.json` to `{feature_dir}/.meta.json` via Python `open()` (bypasses hook)
- Sets `lastCompletedPhase: null`, `phases: {}`
- Calls `_project_meta_json` internally to ensure consistent format
- Returns confirmation JSON
- This tool is NOT gated — it's a creation operation, not a transition

**Acceptance Criteria:**
- [ ] `create-feature.md` calls `init_feature_state` instead of direct Write
- [ ] Resulting `.meta.json` is identical in structure to current direct writes

#### Site 2: `skills/decomposing/SKILL.md:224-239` — Planned feature .meta.json

**Current:** LLM writes `.meta.json` for each planned feature during project decomposition.

**Change:** Call `init_feature_state(status="planned")`.

**Acceptance Criteria:**
- [ ] Decomposing skill calls `init_feature_state(status="planned")` for each feature
- [ ] Planned features get `.meta.json` with `status: "planned"`

#### Site 3: `skills/decomposing/SKILL.md:282-292` — Project .meta.json

**Current:** LLM writes project `.meta.json` with features and milestones arrays.

**Change:** Call new `init_project_state` MCP tool.

```python
@server.tool()
async def init_project_state(
    project_dir: str,
    project_id: str,
    slug: str,
    features: str,         # JSON array of feature ID strings
    milestones: str,       # JSON array of milestone objects
    brainstorm_source: str | None = None,
) -> str:
```

Writes project `.meta.json` directly via Python `open()` (bypasses hook, same mechanism as `init_feature_state`). Uses its own inline formatting logic (no shared `_project_meta_json` — project schema differs from feature schema).

**Project `.meta.json` fields written:**
- `id`, `slug`, `status` ("active"), `created` (ISO timestamp)
- `brainstorm_source` (optional)
- `features` — JSON array of feature ID strings
- `milestones` — JSON array of milestone objects (`{name, features[], target_date?}`)

No `phases{}`, `lastCompletedPhase`, `branch`, or `mode` fields (these are feature-only).

**Acceptance Criteria:**
- [ ] Decomposing skill calls `init_project_state` instead of direct Write
- [ ] Project `.meta.json` structure matches current format

#### Site 4: `skills/workflow-state/SKILL.md:41-46` — Planned→active transition

**Current:** LLM edits `.meta.json` to change `status` from `"planned"` to `"active"`.

**Change:** Call new `activate_feature` MCP tool.

```python
@server.tool()
async def activate_feature(
    feature_type_id: str,  # e.g., "feature:034-enforced-state-machine"
) -> str:
```
1. Validates current entity status is `"planned"` (via `get_entity`)
2. Updates entity status to `"active"` (via `update_entity` — uses existing `entities.status` column, no schema change)
3. Calls `_project_meta_json()` to update `.meta.json`
4. Returns confirmation JSON

**Acceptance Criteria:**
- [ ] `workflow-state/SKILL.md` calls `activate_feature` instead of direct Edit
- [ ] Status changes from "planned" to "active" via MCP
- [ ] Uses existing `entities.status` column (confirmed: `update_entity(feature_type_id, status="active")` already supported)

#### Site 5: `skills/workflow-state/SKILL.md:117-120` — SkippedPhases write

**Current:** LLM edits `.meta.json` to add entry to `skippedPhases[]` array.

**Change:** Extend `transition_phase` to accept `skipped_phases` parameter.

```python
async def transition_phase(
    feature_type_id: str,
    target_phase: str,
    yolo_active: bool = False,
    skipped_phases: str | None = None,  # JSON array of {"phase": "...", "reason": "..."}
) -> str:
```

When `skipped_phases` is provided, stores in entity metadata and includes in `.meta.json` projection.

**Acceptance Criteria:**
- [ ] `workflow-state/SKILL.md` passes skip info to `transition_phase` instead of direct Edit
- [ ] `skippedPhases` array in `.meta.json` populated by MCP tool projection

#### Site 6: `skills/workflow-transitions/SKILL.md:109-118` — Mark phase started

**Current:** LLM edits `.meta.json` to add `phases.{name}.started` timestamp.

**Change:** `transition_phase` already handles phase entry in DB. Extend it to call `_project_meta_json()` after DB update, which writes `phases.{name}.started` to `.meta.json`.

**Acceptance Criteria:**
- [ ] `workflow-transitions/SKILL.md` `validateAndSetup` Step 4 no longer writes `.meta.json` directly
- [ ] `transition_phase` returns the started timestamp in its response so the LLM can reference it
- [ ] `.meta.json` updated by `_project_meta_json()`, not by LLM

#### Site 7: `skills/workflow-transitions/SKILL.md:206-217` — Mark phase completed

**Current:** LLM edits `.meta.json` to add `phases.{name}.completed`, `iterations`, `reviewerNotes`, and update `lastCompletedPhase`.

**Change:** Extend `complete_phase` to accept timing metadata and call `_project_meta_json()`.

```python
async def complete_phase(
    feature_type_id: str,
    phase: str,
    iterations: int | None = None,
    reviewer_notes: str | None = None,  # JSON array of strings
) -> str:
```

**Implementation layer:** The MCP server wrapper `_process_complete_phase` stores `iterations` and `reviewer_notes` in entity metadata via `db.update_entity(feature_type_id, metadata=...)` after calling `engine.complete_phase()`, then calls `_project_meta_json()`.

**Acceptance Criteria:**
- [ ] `workflow-transitions/SKILL.md` `commitAndComplete` Step 2 no longer writes `.meta.json`
- [ ] `complete_phase` projects `phases.{name}.completed`, `iterations`, `reviewerNotes`, `lastCompletedPhase`
- [ ] Timestamps generated server-side (Python `datetime.now(UTC).isoformat()`)

#### Site 8: `commands/finish-feature.md:415-429` — Terminal status update

**Current:** LLM edits `.meta.json` to set `status: "completed"` (or `"merged"`).

**Change:** `complete_phase("finish")` already sets `entities.status = "completed"` in DB. Extend to also call `_project_meta_json()` which includes status in projection.

**Acceptance Criteria:**
- [ ] `finish-feature.md` calls `complete_phase("finish")` instead of direct Edit
- [ ] `.meta.json` `status` field updated to "completed" by projection

#### Site 9: `commands/create-project.md:60-75` — Project .meta.json creation

**Current:** LLM writes project `.meta.json` via Write tool.

**Change:** Call `init_project_state` MCP tool (same as Site 3).

**Acceptance Criteria:**
- [ ] `create-project.md` calls `init_project_state` instead of direct Write

### 3. Instrumentation (FR-11)

**Log file:** `~/.claude/iflow/meta-json-guard.log`

**Directory creation:** Hook creates `~/.claude/iflow/` directory if it does not exist (`mkdir -p`). This directory is already used by other iflow components (memory, entities) so it typically exists.

**Format:** One JSON line per blocked attempt:
```json
{"timestamp": "2026-03-08T21:30:00Z", "tool": "Write", "path": "docs/features/034-enforced-state-machine/.meta.json", "feature_id": "034-enforced-state-machine"}
```

**Field notes:**
- `tool`: The LLM tool name (`Write` or `Edit`)
- `feature_id`: Extracted from path via regex `features/([^/]+)/\.meta\.json` or `projects/([^/]+)/\.meta\.json`. If no match, `"unknown"`
- **Calling command not logged:** The PreToolUse hook context does not include which iflow command triggered the write. FR-11 from PRD specified "calling command" but this is not available in hook context — partially satisfied

**Implementation:** Append to log file in the hook script before returning deny. Use `>>` append to avoid lock contention.

**Measurement period:** 2 weeks from deployment. After measurement:
- If zero blocked attempts → hook enforcement is working, Phase 2 deferred
- If blocked attempts detected → investigate residual write sites, fix them, decide on Phase 2

**Acceptance Criteria:**
- [ ] Every blocked `.meta.json` write produces a log entry
- [ ] Log file created on first write (no pre-creation needed, `mkdir -p` + `>>` handles it)
- [ ] Log entries are valid JSONL (one JSON object per line)
- [ ] Feature ID extracted from path where possible
- [ ] Calling command NOT logged (unavailable in PreToolUse hook context — documented deviation from FR-11). Path + timestamp is sufficient to identify residual write sites; calling command is not required for Phase 1 go/no-go decision

### 4. New MCP Tools Summary

| Tool | Purpose | Server |
|------|---------|--------|
| `init_feature_state` | Create initial feature `.meta.json` | `workflow_state_server.py` |
| `init_project_state` | Create initial project `.meta.json` | `workflow_state_server.py` |
| `activate_feature` | Transition planned→active + project `.meta.json` | `workflow_state_server.py` |

**Extended existing tools:**

| Tool | Extension |
|------|-----------|
| `transition_phase` | Add `skipped_phases` param; call `_project_meta_json()` after DB update |
| `complete_phase` | Add `iterations`, `reviewer_notes` params; call `_project_meta_json()` after DB update |

### 5. `.meta.json` Projection Function

All MCP tools that mutate state must regenerate `.meta.json` after DB updates. This is a shared utility:

```python
def _project_meta_json(feature_type_id: str, feature_dir: str | None = None) -> None:
    """Regenerate .meta.json from current DB + entity state.

    Reads: entities table (status, metadata.phase_timing — Phase 1), workflow_phases table (Phase 2)
    Writes: {feature_dir}/.meta.json (complete file replacement via Python open())

    If feature_dir is None, resolves it from db.get_entity(feature_type_id).artifact_path.

    Called by: init_feature_state, activate_feature, transition_phase, complete_phase
    NOT called by: init_project_state (projects have different schema)
    """
```

**Directory resolution:** For tools that don't have `feature_dir` as a parameter (e.g., `transition_phase`, `complete_phase`), the MCP server resolves it via `db.get_entity(feature_type_id).artifact_path` (existing field in entity registry, populated during `register_entity`). If `artifact_path` is `None` or empty, `_project_meta_json` logs a warning and returns without writing (DB state is preserved). The MCP tool response includes a warning: `"artifact_path not set for entity"`.

**Fields projected:**
- `id`, `slug` — from entity metadata
- `mode` — from entity metadata
- `status` — from entity status
- `created` — from entity created_at
- `branch` — from entity metadata
- `brainstorm_source`, `backlog_source` — from entity metadata
- `lastCompletedPhase` — from workflow engine state
- `phases` — reconstructed from entity metadata (timing data stored per-phase)
- `skippedPhases` — from entity metadata

**Synchronous:** Called inline after every DB mutation, before MCP tool returns. No staleness window.

**Data source note:** In Phase 1, timing data is stored in entity metadata JSON blob (no new DB columns) with structure: `{"phase_timing": {"specify": {"started": "...", "completed": "...", "iterations": 2, "reviewerNotes": ["..."]}}}`. The projection function reads `metadata.phase_timing` and formats it into the `.meta.json` `phases` object LLM agents expect. Phase 2 may migrate timing data to dedicated `workflow_phases` columns.

**Acceptance Criteria:**
- [ ] `.meta.json` regenerated after `transition_phase` succeeds
- [ ] `.meta.json` regenerated after `complete_phase` succeeds
- [ ] `.meta.json` regenerated after `init_feature_state` and `activate_feature`
- [ ] Projected file matches the structure LLM agents expect (backward-compatible JSON shape)
- [ ] If projection fails (e.g., disk full), MCP tool returns warning but DB state is preserved

## Non-Functional Requirements

| NFR | Criterion | Verification |
|-----|-----------|-------------|
| NFR-3 | Hook latency < 50ms | Measure with `time` wrapper in test |
| NFR-4 | Existing tests pass | Run full test suite after changes |

## Scope Boundaries

### In Scope (Phase 1)
- PreToolUse hook blocking `.meta.json` writes (FR-7)
- 9 skill/command write site updates (FR-8)
- 3 new MCP tools (`init_feature_state`, `init_project_state`, `activate_feature`)
- 2 MCP tool extensions (`transition_phase`, `complete_phase`) (FR-4)
- `.meta.json` projection function `_project_meta_json` (FR-5)
- Instrumentation logging (FR-11)

### Out of Scope (Phase 2)
- DB schema migration for dedicated timing columns (FR-1, FR-2)
- Full `create_feature` CQRS tool (FR-3) — Phase 1 uses lightweight `init_feature_state`
- Removing `_write_meta_json_fallback()` (requires read-only degradation model — see Enforcement Boundary)
- Reverse reconciliation direction `db_to_meta_json` (FR-6)
- `session-start.sh` reading from MCP (FR-9)
- SQLite WAL mode changes (FR-10 — already configured)

### Explicitly NOT Changed
- `.meta.json` reads — LLM agents can still read `.meta.json` freely
- Entity registry DB schema — no new columns (timing data in metadata JSON blob)
- Reconciliation direction — remains `meta_json_to_db` (but becomes less needed as projection writes `.meta.json`)

## Test Strategy

### Test Impact Assessment

Codebase grep for `meta.json` references in test files found 664 occurrences across 7 files:

| File | Occurrences | Impact |
|------|-------------|--------|
| `test_engine.py` | 299 | HIGH — many mock `.meta.json` reads/writes for engine tests |
| `test_reconciliation.py` | 196 | HIGH — reconciliation tests compare DB vs `.meta.json` state |
| `test_workflow_state_server.py` | 93 | MEDIUM — MCP tool tests, some mock `.meta.json` interactions |
| `test_backfill.py` | 54 | LOW — backfill reads `.meta.json`, no writes |
| `test_retrieval.py` | 16 | NONE — semantic memory, unrelated `.meta.json` references |
| `test_pipelines.py` | 4 | NONE — hook pipeline tests, path-only references |
| `test_server_helpers.py` | 2 | NONE — entity server, path-only references |

**Blast radius:** ~392 test references in 3 files (engine, reconciliation, workflow_state_server) may need updates. Most are read-only assertions that should pass unchanged. Write-mocking tests need to be updated to use the new MCP tool paths.

**Mitigation:** Run full suite after each write-site conversion to catch regressions incrementally.

### Unit Tests
- `meta-json-guard.sh` hook: test deny for Write/Edit to `.meta.json`, allow for other files
- `init_feature_state`: test creates valid `.meta.json` with all fields
- `init_project_state`: test creates valid project `.meta.json`
- `activate_feature`: test planned→active transition, reject non-planned status
- `_project_meta_json`: test projection produces expected JSON structure from DB state
- Extended `transition_phase`: test `.meta.json` written after transition, test `skipped_phases` param
- Extended `complete_phase`: test `.meta.json` written with timing data

### Integration Tests
- End-to-end: create feature → specify → complete — all via MCP, no direct `.meta.json` writes
- Hook blocks direct write attempt, logs it, and returns deny
- Instrumentation log contains expected JSONL entries

### CI Verification
- `grep -rn 'Write.*meta.json\|Edit.*meta.json\|\.meta\.json.*content' plugins/iflow/skills/ plugins/iflow/commands/` returns zero matches (no residual direct write instructions)

### Regression
- Run full existing test suite after changes
- Tests that only read `.meta.json` should pass unchanged
- Tests that mock `.meta.json` writes need update to use MCP tools

## Migration Notes

- **No data migration needed** for Phase 1 — existing `.meta.json` files remain valid
- **Skill/command updates are backward-compatible** — MCP tools produce the same `.meta.json` structure
- **Hook can be disabled** by removing entry from `hooks/hooks.json` if issues arise (reversible)
- **One-shot deployment** — all changes land together (hook + skill updates + MCP tools)
