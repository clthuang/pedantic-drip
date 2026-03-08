# Design: Enforced State Machine (Phase 1)

## Prior Art Research

### Codebase Patterns

- **PreToolUse deny pattern:** `pre-commit-guard.sh` reads stdin JSON, extracts tool_input via python3, defines `output_block()`/`output_allow()` as **local functions** (lines 89-135, NOT in `common.sh`). The `yolo-guard.sh` hook inlines its own deny JSON via `cat <<EOF`. Apply the inline pattern — no shared deny helper exists.
- **MCP tool registration:** `workflow_state_server.py` uses `@mcp.tool()` decorator + `_process_*()` functions + `@_with_error_handling` + `@_catch_value_error` decorator stack. Module globals `_db`, `_engine`, `_artifacts_root` set during `lifespan()`.
- **Atomic file writes:** `_write_meta_json_fallback()` uses `NamedTemporaryFile` + `os.replace()` for crash safety. Reuse this pattern for `_project_meta_json()`.
- **Path validation:** `_validate_feature_type_id()` defends against path traversal (null bytes, realpath check). All new tools accepting `feature_type_id` must call this.
- **Entity metadata storage:** `db.update_entity(type_id, metadata={...})` shallow-merges metadata dict. Phase timing stored under `metadata.phase_timing` key.

### External Research

- **Hook exit semantics:** exit 0 + `permissionDecision: "deny"` is the canonical block path. Exit 2 is a hard-block alternative (stderr shown to Claude). Stick with exit 0 + deny JSON for consistency with existing hooks.
- **Known issue #4362:** `approve: false` was ignored in some CC versions — use `permissionDecision` field, not `approve`. Our existing hooks already use the correct field.
- **CQRS synchronous projection:** Update both write model and read model within the same operation. Projection called inline after DB commit, before returning to caller. No eventual consistency concerns.

## Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    LLM Agent Layer                       │
│  (skills, commands — 9 write sites updated)             │
│                                                         │
│  create-feature.md ──┐                                  │
│  decomposing/SKILL ──┤  Call MCP tools                  │
│  workflow-state/SKILL─┤  instead of                     │
│  workflow-trans/SKILL─┤  Write/Edit                     │
│  finish-feature.md ──┤                                  │
│  create-project.md ──┘                                  │
└────────┬────────────────────────┬───────────────────────┘
         │ MCP tool calls         │ Write/Edit tool calls
         │                        │
         ▼                        ▼
┌─────────────────┐    ┌─────────────────────────┐
│  workflow_state  │    │  meta-json-guard.sh     │
│  _server.py     │    │  (PreToolUse hook)       │
│                  │    │                          │
│  New tools:      │    │  *.meta.json? → DENY    │
│  • init_feature  │    │  + log to JSONL          │
│  • init_project  │    │  other files? → ALLOW    │
│  • activate      │    └─────────────────────────┘
│                  │
│  Extended:       │
│  • transition    │
│  • complete      │
│                  │
│  Shared:         │
│  • _project_     │
│    meta_json()   │
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────────┐
│ SQLite │ │ .meta.json   │
│ DB     │ │ (projection) │
│(write) │ │ (read model) │
└────────┘ └──────────────┘
```

### Data Flow

**Normal path (all 9 write sites):**
```
LLM → MCP tool call → _process_*() → engine/db mutation → _project_meta_json() → .meta.json written → response to LLM
```

**Blocked path (any residual direct write):**
```
LLM → Write/Edit(.meta.json) → meta-json-guard.sh → DENY + log entry → LLM receives deny reason
```

**Degraded path (DB unavailable, unchanged):**
```
engine.transition_phase() → DB fails → _write_meta_json_fallback() → .meta.json written directly
```

## Components

### C1: `meta-json-guard.sh` (New File)

**Location:** `plugins/iflow/hooks/meta-json-guard.sh`

**Responsibility:** Block all LLM Write/Edit tool calls targeting `*.meta.json` files. Log blocked attempts.

**Design decisions:**
- **Fast-path optimization:** Check `*".meta.json"*` via bash string match before any JSON parsing. ~99% of Write/Edit calls don't target `.meta.json`, so this avoids the python3/jq overhead. Borrowed from `yolo-guard.sh` pattern. **Accepted trade-off:** Write calls whose *content* mentions `.meta.json` (e.g., writing a skill file that references it) trigger a false-positive python3 call (~30ms), but correctness is maintained because python3 checks `file_path`, not content. Still under NFR-3's 50ms threshold.
- **Path extraction:** Use python3 inline (same as `pre-commit-guard.sh`) to parse `tool_input.file_path` from stdin JSON. Suppress stderr (`2>/dev/null`) per hook safety convention.
- **Logging:** Append JSONL to `~/.claude/iflow/meta-json-guard.log` before returning deny. Use `date -u +%Y-%m-%dT%H:%M:%SZ` for timestamp. Extract feature_id via bash regex on path.
- **Source common.sh:** For `escape_json()`, `detect_project_root()`, `install_err_trap()`. Deny JSON is inlined (no shared `output_block()` exists — it's local to `pre-commit-guard.sh`).

**Internal structure:**
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap

# Read all stdin once
INPUT=$(cat)

# Fast path: skip JSON parse if no .meta.json reference
if [[ "$INPUT" != *".meta.json"* ]]; then
    echo '{}'
    exit 0
fi

# Extract file_path AND tool_name in a single python3 call
# Use tab delimiter to handle paths with spaces
IFS=$'\t' read -r FILE_PATH TOOL_NAME < <(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    fp = data.get('tool_input', {}).get('file_path', '')
    tn = data.get('tool_name', 'unknown')
    print(fp + '\t' + tn)
except:
    print('\tunknown')
" 2>/dev/null)

# Check if target is .meta.json
if [[ "$FILE_PATH" != *".meta.json" ]]; then
    echo '{}'
    exit 0
fi

# Log blocked attempt (FR-11)
log_blocked_attempt "$FILE_PATH" "$TOOL_NAME"

# Deny (inline JSON — no shared output_block helper exists)
REASON="Direct .meta.json writes are blocked. Use MCP workflow tools instead: transition_phase() to enter a phase, complete_phase() to finish a phase, or init_feature_state() to create a new feature."
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "$(escape_json "$REASON")"
  }
}
EOF
exit 0
```

**`log_blocked_attempt` function (single python3 call — both fields extracted above):**
```bash
log_blocked_attempt() {
    local file_path="$1"
    local tool_name="$2"
    local log_dir="$HOME/.claude/iflow"
    local log_file="$log_dir/meta-json-guard.log"
    local timestamp feature_id

    mkdir -p "$log_dir"
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Extract feature_id from path
    if [[ "$file_path" =~ features/([^/]+)/\.meta\.json ]]; then
        feature_id="${BASH_REMATCH[1]}"
    elif [[ "$file_path" =~ projects/([^/]+)/\.meta\.json ]]; then
        feature_id="${BASH_REMATCH[1]}"
    else
        feature_id="unknown"
    fi

    # Append JSONL (>> is atomic for lines < PIPE_BUF on POSIX)
    echo "{\"timestamp\":\"$timestamp\",\"tool\":\"$tool_name\",\"path\":\"$(escape_json "$file_path")\",\"feature_id\":\"$feature_id\"}" >> "$log_file"
}
```

**Registration in `hooks.json`:** Insert at index 2 in `PreToolUse` array (after `Bash`/pre-commit-guard at index 1, before `.*`/yolo-guard at index 2).

### C2: `_project_meta_json()` (New Function)

**Location:** `plugins/iflow/mcp/workflow_state_server.py` (module-level function)

**Responsibility:** Regenerate `.meta.json` from current DB + entity state after every successful mutation.

**Design decisions:**
- **Placed in MCP server, not engine.** The engine is a state machine; file projection is a server-layer concern. Keeps engine testable without filesystem coupling.
- **Atomic write:** Reuse `NamedTemporaryFile` + `os.replace()` pattern from `_write_meta_json_fallback()`.
- **Fail-open for projection:** If projection fails (disk full, permissions), DB state is preserved. MCP tool returns success with a warning field. The LLM can still proceed; `.meta.json` will be stale until next successful projection.
- **Uses `_db` and `_engine` globals** — same as all other MCP server processing functions.

**Internal structure:**
```python
def _project_meta_json(
    db: EntityDatabase,
    engine: WorkflowStateEngine,
    feature_type_id: str,
    feature_dir: str | None = None,
) -> str | None:
    """Regenerate .meta.json from DB + engine state. Returns warning string or None.

    Uses engine.get_state() as authoritative source for last_completed_phase
    and current_phase. Falls back to entity metadata if engine state unavailable.
    Phase timing details (iterations, reviewerNotes) come from entity metadata
    only (engine doesn't track these).
    """
    entity = db.get_entity(feature_type_id)
    if entity is None:
        return f"entity not found: {feature_type_id}"

    if feature_dir is None:
        feature_dir = entity.artifact_path
        if not feature_dir:
            # Fallback: derive from entity_id convention
            slug = feature_type_id.split(":", 1)[1] if ":" in feature_type_id else feature_type_id
            feature_dir = os.path.join(_artifacts_root, "features", slug)
            if not os.path.isdir(feature_dir):
                return f"artifact_path not set and fallback dir not found: {feature_type_id}"

    meta_path = os.path.join(feature_dir, ".meta.json")
    metadata = entity.metadata or {}
    phase_timing = metadata.get("phase_timing", {})

    # Get authoritative state from engine (handles migration from existing features).
    # Note: _project_meta_json is only called after successful DB mutation, so
    # engine.get_state() reads from DB (not .meta.json). If DB degrades between
    # mutation and this call (extremely unlikely), engine falls back to .meta.json
    # which is stale but acceptable — projection will use stale last_completed_phase.
    engine_state = engine.get_state(feature_type_id)
    last_completed = (
        engine_state.last_completed_phase if engine_state
        else metadata.get("last_completed_phase")
    )

    # Build .meta.json structure
    meta = {
        "id": metadata.get("id", ""),
        "slug": metadata.get("slug", ""),
        "mode": metadata.get("mode", "standard"),
        "status": entity.status or "active",
        "created": entity.created_at or _iso_now(),
        "branch": metadata.get("branch", ""),
    }

    # Optional fields
    if metadata.get("brainstorm_source"):
        meta["brainstorm_source"] = metadata["brainstorm_source"]
    if metadata.get("backlog_source"):
        meta["backlog_source"] = metadata["backlog_source"]

    # Workflow state (engine is authoritative)
    meta["lastCompletedPhase"] = last_completed

    # Phases from phase_timing metadata
    phases = {}
    for phase_name, timing in phase_timing.items():
        phase_entry = {}
        if timing.get("started"):
            phase_entry["started"] = timing["started"]
        if timing.get("completed"):
            phase_entry["completed"] = timing["completed"]
        if timing.get("iterations") is not None:
            phase_entry["iterations"] = timing["iterations"]
        if timing.get("reviewerNotes"):
            phase_entry["reviewerNotes"] = timing["reviewerNotes"]
        if phase_entry:
            phases[phase_name] = phase_entry
    meta["phases"] = phases

    # Skipped phases
    if metadata.get("skipped_phases"):
        meta["skippedPhases"] = metadata["skipped_phases"]

    # Atomic write (fail-open: catch Exception, let BaseException propagate)
    try:
        _atomic_json_write(meta_path, meta)
        return None  # success
    except Exception as exc:
        return f"projection failed: {exc}"
```

**Caller integration:** Each `_process_*()` function calls `_project_meta_json(db, engine, ...)` after DB mutation succeeds, using `_engine` module global. If it returns a warning, include it in the MCP response JSON as `"projection_warning": "..."`. For `init_feature_state`, pass `_engine` (may be None if engine not needed for new features — the function handles this gracefully).

### C3: `init_feature_state` (New MCP Tool)

**Location:** `plugins/iflow/mcp/workflow_state_server.py`

**Responsibility:** Create initial feature state in DB + entity registry, then project `.meta.json`.

**Design decisions:**
- **Registers entity first**, then creates workflow phase, then projects. If entity already exists, update metadata only (idempotent for retries).
- **No gate validation** — creation is not a transition.
- **Reuses `_validate_feature_type_id`** pattern for path safety, but relaxes the "directory must exist" check (directory is being created).

**Internal structure:**
```python
@_with_error_handling
@_catch_value_error
def _process_init_feature_state(
    db: EntityDatabase,
    feature_dir: str,
    feature_id: str,
    slug: str,
    mode: str,
    branch: str,
    brainstorm_source: str | None,
    backlog_source: str | None,
    status: str,
) -> str:
    feature_type_id = f"feature:{feature_id}-{slug}"

    # Register or update entity
    metadata = {
        "id": feature_id,
        "slug": slug,
        "mode": mode,
        "branch": branch,
        "phase_timing": {"brainstorm": {"started": _iso_now()}} if status == "active" else {},
    }
    if brainstorm_source:
        metadata["brainstorm_source"] = brainstorm_source
    if backlog_source:
        metadata["backlog_source"] = backlog_source

    existing = db.get_entity(feature_type_id)
    if existing is None:
        db.register_entity(
            entity_type="feature",
            entity_id=f"{feature_id}-{slug}",
            name=slug,
            artifact_path=feature_dir,
            status=status,
            metadata=metadata,
        )
    else:
        # Retry path: preserve existing phase_timing to avoid clobbering
        # progress data. Only update status and non-timing metadata.
        existing_meta = existing.metadata or {}
        metadata["phase_timing"] = existing_meta.get("phase_timing", metadata["phase_timing"])
        if existing_meta.get("last_completed_phase"):
            metadata["last_completed_phase"] = existing_meta["last_completed_phase"]
        if existing_meta.get("skipped_phases"):
            metadata["skipped_phases"] = existing_meta["skipped_phases"]
        db.update_entity(feature_type_id, status=status, metadata=metadata)

    # Project .meta.json
    warning = _project_meta_json(db, _engine, feature_type_id, feature_dir)

    result = {
        "created": True,
        "feature_type_id": feature_type_id,
        "status": status,
        "meta_json_path": os.path.join(feature_dir, ".meta.json"),
    }
    if warning:
        result["projection_warning"] = warning
    return json.dumps(result)
```

### C4: `init_project_state` (New MCP Tool)

**Location:** `plugins/iflow/mcp/workflow_state_server.py`

**Responsibility:** Create initial project `.meta.json` with project-specific schema (features array, milestones).

**Design decisions:**
- **Does NOT use `_project_meta_json()`** — projects have a different schema (no `phases{}`, `lastCompletedPhase`, `branch`, `mode`). Writes directly.
- **Registers entity** in entity registry for lineage tracking.
- **Atomic write** via same `NamedTemporaryFile` + `os.replace()` pattern.

**Internal structure:**
```python
@_with_error_handling
@_catch_value_error
def _process_init_project_state(
    db: EntityDatabase,
    project_dir: str,
    project_id: str,
    slug: str,
    features: str,  # JSON string
    milestones: str,  # JSON string
    brainstorm_source: str | None,
) -> str:
    project_type_id = f"project:{project_id}-{slug}"

    # Parse JSON params
    features_list = json.loads(features)
    milestones_list = json.loads(milestones)

    # Register entity
    existing = db.get_entity(project_type_id)
    if existing is None:
        db.register_entity(
            entity_type="project",
            entity_id=f"{project_id}-{slug}",
            name=slug,
            artifact_path=project_dir,
            status="active",
        )

    # Build project .meta.json
    meta = {
        "id": project_id,
        "slug": slug,
        "status": "active",
        "created": _iso_now(),
        "features": features_list,
        "milestones": milestones_list,
    }
    if brainstorm_source:
        meta["brainstorm_source"] = brainstorm_source

    # Atomic write
    meta_path = os.path.join(project_dir, ".meta.json")
    _atomic_json_write(meta_path, meta)

    return json.dumps({
        "created": True,
        "project_type_id": project_type_id,
        "meta_json_path": meta_path,
    })
```

### C5: `activate_feature` (New MCP Tool)

**Location:** `plugins/iflow/mcp/workflow_state_server.py`

**Responsibility:** Transition a planned feature to active status.

**Design decisions:**
- **Pre-condition check:** Must be in `"planned"` status. Reject otherwise.
- **Uses existing `db.update_entity(status="active")`** — no schema change needed.
- **Projects `.meta.json`** via `_project_meta_json()` after status update.

**Internal structure:**
```python
@_with_error_handling
@_catch_value_error
def _process_activate_feature(
    db: EntityDatabase,
    feature_type_id: str,
) -> str:
    entity = db.get_entity(feature_type_id)
    if entity is None:
        raise ValueError(f"feature_not_found: {feature_type_id}")
    if entity.status != "planned":
        raise ValueError(
            f"invalid_transition: feature status is '{entity.status}', "
            f"expected 'planned' for activation"
        )

    db.update_entity(feature_type_id, status="active")

    warning = _project_meta_json(db, _engine, feature_type_id)

    result = {
        "activated": True,
        "feature_type_id": feature_type_id,
        "previous_status": "planned",
        "new_status": "active",
    }
    if warning:
        result["projection_warning"] = warning
    return json.dumps(result)
```

### C6: Extended `transition_phase` (Modified)

**Location:** `plugins/iflow/mcp/workflow_state_server.py` — modify `_process_transition_phase` and `transition_phase` tool.

**Changes:**
1. Add `skipped_phases: str | None = None` parameter
2. If `skipped_phases` provided, parse JSON and store in entity metadata
3. Store phase started timestamp in `metadata.phase_timing`
4. Call `_project_meta_json()` after successful transition

**Modified `_process_transition_phase`:**
```python
@_with_error_handling
@_catch_value_error
def _process_transition_phase(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    feature_type_id: str,
    target_phase: str,
    yolo_active: bool,
    skipped_phases: str | None,
) -> str:
    response = engine.transition_phase(feature_type_id, target_phase, yolo_active)
    transitioned = all(r.allowed for r in response.results)

    if transitioned:
        # Store phase timing
        entity = db.get_entity(feature_type_id)
        metadata = (entity.metadata if entity else {}) or {}
        phase_timing = metadata.get("phase_timing", {})
        phase_timing.setdefault(target_phase, {})
        phase_timing[target_phase]["started"] = _iso_now()
        metadata["phase_timing"] = phase_timing

        # Store skipped phases if provided
        if skipped_phases:
            metadata["skipped_phases"] = json.loads(skipped_phases)

        # Store last_completed_phase for projection
        # (transition doesn't complete, but we need to track current state)
        db.update_entity(feature_type_id, metadata=metadata)

        # Project .meta.json
        warning = _project_meta_json(db, _engine, feature_type_id)

    result = {
        "transitioned": transitioned,
        "results": [_serialize_result(r) for r in response.results],
        "degraded": response.degraded,
    }
    if transitioned:
        result["started_at"] = phase_timing[target_phase]["started"]
        if skipped_phases:
            result["skipped_phases_stored"] = True
        if warning:
            result["projection_warning"] = warning
    return json.dumps(result)
```

### C7: Extended `complete_phase` (Modified)

**Location:** `plugins/iflow/mcp/workflow_state_server.py` — modify `_process_complete_phase` and `complete_phase` tool.

**Changes:**
1. Add `iterations: int | None = None` and `reviewer_notes: str | None = None` parameters
2. Store timing metadata in entity after engine completes phase
3. Call `_project_meta_json()` after successful completion

**Modified `_process_complete_phase`:**
```python
@_with_error_handling
@_catch_value_error
def _process_complete_phase(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    feature_type_id: str,
    phase: str,
    iterations: int | None,
    reviewer_notes: str | None,
) -> str:
    state = engine.complete_phase(feature_type_id, phase)

    # Store timing metadata
    entity = db.get_entity(feature_type_id)
    metadata = (entity.metadata if entity else {}) or {}
    phase_timing = metadata.get("phase_timing", {})
    phase_timing.setdefault(phase, {})
    phase_timing[phase]["completed"] = _iso_now()
    if iterations is not None:
        phase_timing[phase]["iterations"] = iterations
    if reviewer_notes:
        phase_timing[phase]["reviewerNotes"] = json.loads(reviewer_notes)
    metadata["phase_timing"] = phase_timing
    metadata["last_completed_phase"] = phase

    # Update terminal status
    # engine.complete_phase() for "finish" returns current_phase="finish" (terminal)
    # because _next_phase_value("finish") returns None, and engine sets next_phase=phase
    if phase == "finish":
        db.update_entity(feature_type_id, status="completed", metadata=metadata)
    else:
        db.update_entity(feature_type_id, metadata=metadata)

    # Project .meta.json
    warning = _project_meta_json(db, _engine, feature_type_id)

    result = _serialize_state(state)
    result["completed_at"] = phase_timing[phase]["completed"]
    if warning:
        result["projection_warning"] = warning
    return json.dumps(result)
```

### MCP Tool Wrapper Changes (Required)

The `@mcp.tool()` async wrappers must be updated to pass `_db` to the modified `_process_*` functions:

```python
# Existing wrappers (lines 493-510) — BEFORE:
@mcp.tool()
async def transition_phase(feature_type_id: str, target_phase: str, yolo_active: bool = False) -> str:
    return _process_transition_phase(_engine, feature_type_id, target_phase, yolo_active)

@mcp.tool()
async def complete_phase(feature_type_id: str, phase: str) -> str:
    return _process_complete_phase(_engine, feature_type_id, phase)

# AFTER — add _db param and new params:
@mcp.tool()
async def transition_phase(
    feature_type_id: str, target_phase: str,
    yolo_active: bool = False, skipped_phases: str | None = None,
) -> str:
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_transition_phase(_engine, _db, feature_type_id, target_phase, yolo_active, skipped_phases)

@mcp.tool()
async def complete_phase(
    feature_type_id: str, phase: str,
    iterations: int | None = None, reviewer_notes: str | None = None,
) -> str:
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_complete_phase(_engine, _db, feature_type_id, phase, iterations, reviewer_notes)

# New tool wrappers:
@mcp.tool()
async def init_feature_state(
    feature_dir: str, feature_id: str, slug: str, mode: str, branch: str,
    brainstorm_source: str | None = None, backlog_source: str | None = None,
    status: str = "active",
) -> str:
    if _db is None:
        return _NOT_INITIALIZED
    return _process_init_feature_state(_db, feature_dir, feature_id, slug, mode, branch, brainstorm_source, backlog_source, status)

@mcp.tool()
async def init_project_state(
    project_dir: str, project_id: str, slug: str,
    features: str, milestones: str, brainstorm_source: str | None = None,
) -> str:
    if _db is None:
        return _NOT_INITIALIZED
    return _process_init_project_state(_db, project_dir, project_id, slug, features, milestones, brainstorm_source)

@mcp.tool()
async def activate_feature(feature_type_id: str) -> str:
    if _db is None:
        return _NOT_INITIALIZED
    return _process_activate_feature(_db, feature_type_id)
```

### C8: Shared Utility — `_atomic_json_write()` (New Function)

**Location:** `plugins/iflow/mcp/workflow_state_server.py`

**Responsibility:** Atomic JSON file write via `NamedTemporaryFile` + `os.replace()`.

```python
def _atomic_json_write(path: str, data: dict) -> None:
    """Atomic JSON write: NamedTemporaryFile + os.replace()."""
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=os.path.dirname(path),
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as fd:
            tmp_name = fd.name
            json.dump(data, fd, indent=2)
            fd.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        raise
```

Used by: `_project_meta_json()`, `_process_init_project_state()`.

## Technical Decisions

| # | Decision | Rationale | Alternative Considered |
|---|----------|-----------|----------------------|
| D1 | Place `_project_meta_json()` in MCP server, not engine | Engine is a state machine; file I/O is server concern. Keeps engine unit-testable without filesystem. | In engine.py — rejected: couples engine to file format |
| D2 | Fast-path string check before JSON parse in hook | ~99% of Write/Edit calls don't target `.meta.json`. Avoids python3 subprocess for the common case. NFR-3 (< 50ms) requires this. | Always parse — rejected: adds ~30ms latency per non-.meta.json write |
| D3 | Store phase timing in entity metadata blob, not new DB columns | Phase 1 YAGNI — avoids schema migration. Metadata blob is flexible and already supports shallow merge. | New columns — deferred to Phase 2 |
| D4 | Atomic write via `NamedTemporaryFile` + `os.replace()` | Proven pattern from `_write_meta_json_fallback()`. Crash-safe on POSIX. | Direct `open().write()` — rejected: not atomic |
| D5 | `init_project_state` uses inline write, not `_project_meta_json()` | Project schema (features[], milestones[]) differs from feature schema (phases{}, lastCompletedPhase). Shared function would need branching that negates the benefit. | Shared function with mode param — rejected: adds complexity |
| D6 | No allowlist in hook | YAGNI per PRD. If legitimate `.meta.json` writes appear in instrumentation log, add allowlist then. | Pre-built allowlist — rejected: speculative |
| D7 | `_process_*` functions accept `db` param explicitly | Enables testing with mock DB. Consistent with existing pattern for `engine` param. | Use global `_db` directly — rejected: harder to test |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Hook latency > 50ms on slow machines | Low | Medium — slows every Write/Edit | Fast-path string check avoids python3 for 99% of calls |
| `artifact_path` not populated for some entities | Medium | Low — projection silently skips, DB state preserved | Warning in MCP response; backfill migration can fix existing entities |
| Stale `.meta.json` if projection fails | Low | Low — LLM reads stale data, next successful operation fixes it | Warning in MCP response; reconcile_check detects drift |
| Test suite disruption from 392 test references | High | Medium — many tests mock `.meta.json` writes | Incremental migration: convert one write site at a time, run suite after each |
| `_write_meta_json_fallback` creates unguarded state | Low | Low — only fires during DB degradation (rare) | Accepted Phase 1 limitation; Phase 2 removes fallback |

## Interfaces

### Hook Interface: `meta-json-guard.sh`

**Input (stdin):**
```json
{"tool_name": "Write", "tool_input": {"file_path": "/path/to/.meta.json", "content": "..."}}
```

**Output (stdout) — deny:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Direct .meta.json writes are blocked. Use MCP workflow tools instead: transition_phase() to enter a phase, complete_phase() to finish a phase, or init_feature_state() to create a new feature."
  }
}
```

**Output (stdout) — allow (non-.meta.json files):**
```json
{}
```

**Side effect:** Appends JSONL to `~/.claude/iflow/meta-json-guard.log`

### MCP Tool Interface: `init_feature_state`

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `feature_dir` | `str` | Yes | Absolute or project-relative path to feature dir |
| `feature_id` | `str` | Yes | Numeric feature ID (e.g., "034") |
| `slug` | `str` | Yes | Feature slug (e.g., "enforced-state-machine") |
| `mode` | `str` | Yes | "standard" or "full" |
| `branch` | `str` | Yes | Git branch name |
| `brainstorm_source` | `str` | No | Path to source brainstorm PRD |
| `backlog_source` | `str` | No | Backlog item reference |
| `status` | `str` | No | "active" (default) or "planned" |

**Response:**
```json
{
  "created": true,
  "feature_type_id": "feature:034-enforced-state-machine",
  "status": "active",
  "meta_json_path": "docs/features/034-enforced-state-machine/.meta.json",
  "projection_warning": null
}
```

### MCP Tool Interface: `init_project_state`

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `project_dir` | `str` | Yes | Absolute or project-relative path to project dir |
| `project_id` | `str` | Yes | Project ID |
| `slug` | `str` | Yes | Project slug |
| `features` | `str` | Yes | JSON array of feature ID strings |
| `milestones` | `str` | Yes | JSON array of milestone objects |
| `brainstorm_source` | `str` | No | Path to source brainstorm PRD |

**Response:**
```json
{
  "created": true,
  "project_type_id": "project:001-my-project",
  "meta_json_path": "docs/projects/001-my-project/.meta.json"
}
```

### MCP Tool Interface: `activate_feature`

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `feature_type_id` | `str` | Yes | e.g., "feature:034-enforced-state-machine" |

**Pre-condition:** Entity status must be "planned".

**Response:**
```json
{
  "activated": true,
  "feature_type_id": "feature:034-enforced-state-machine",
  "previous_status": "planned",
  "new_status": "active",
  "projection_warning": null
}
```

### Extended MCP Tool: `transition_phase`

**New parameter:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `skipped_phases` | `str` | No | JSON array of `{"phase": "...", "reason": "..."}` |

**Response additions:**
```json
{
  "transitioned": true,
  "results": [...],
  "degraded": false,
  "started_at": "2026-03-08T22:46:00Z",
  "skipped_phases_stored": true,
  "projection_warning": null
}
```

### Extended MCP Tool: `complete_phase`

**New parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `iterations` | `int` | No | Number of review iterations for this phase |
| `reviewer_notes` | `str` | No | JSON array of reviewer note strings |

**Response additions:**
```json
{
  "feature_type_id": "...",
  "current_phase": "design",
  "last_completed_phase": "specify",
  "completed_at": "2026-03-08T22:45:00Z",
  "projection_warning": null
}
```

### Internal Interface: `_project_meta_json()`

```python
def _project_meta_json(
    db: EntityDatabase,
    engine: WorkflowStateEngine,
    feature_type_id: str,
    feature_dir: str | None = None,
) -> str | None:
    """Returns None on success, warning string on failure.

    Uses engine.get_state() for authoritative last_completed_phase.
    Uses entity metadata for timing details (iterations, reviewerNotes).
    Falls back to metadata-only if engine state unavailable.
    """
```

Called by: `_process_init_feature_state`, `_process_activate_feature`, `_process_transition_phase`, `_process_complete_phase`.

### Internal Interface: `_atomic_json_write()`

```python
def _atomic_json_write(path: str, data: dict) -> None:
    """Raises on failure (caller handles)."""
```

Called by: `_project_meta_json`, `_process_init_project_state`.

## Dependencies

### Build Order

```
1. _atomic_json_write()           — no dependencies
2. _project_meta_json()           — depends on _atomic_json_write, EntityDatabase, WorkflowStateEngine
3. meta-json-guard.sh             — depends on lib/common.sh (existing)
4. init_feature_state             — depends on _project_meta_json
5. init_project_state             — depends on _atomic_json_write
6. activate_feature               — depends on _project_meta_json
7. Extended transition_phase      — depends on _project_meta_json
8. Extended complete_phase        — depends on _project_meta_json
9. Skill/command write site edits — depends on all MCP tools being deployed
10. hooks.json registration       — last: enables enforcement after all sites updated
```

**Critical ordering constraint:** Hook registration (step 10) must be LAST. If the hook is enabled before all 9 write sites are updated, legitimate `.meta.json` writes will be blocked. Deploy atomically in a single commit.

### External Dependencies

- No new pip packages required
- `common.sh` helper functions (existing)
- `EntityDatabase` API (existing, no schema changes)
- `WorkflowStateEngine` API (existing)
- `tempfile`, `os` stdlib (existing imports in workflow_state_server.py)

### Test File Mapping

| Component | Test File | Action |
|-----------|-----------|--------|
| `meta-json-guard.sh` | `hooks/tests/test-hooks.sh` | Extend with deny/allow/log test cases |
| `_atomic_json_write()` | `mcp/test_workflow_state_server.py` | Add unit tests |
| `_project_meta_json()` | `mcp/test_workflow_state_server.py` | Add unit tests (mock DB + engine) |
| `init_feature_state` | `mcp/test_workflow_state_server.py` | Add MCP tool tests |
| `init_project_state` | `mcp/test_workflow_state_server.py` | Add MCP tool tests |
| `activate_feature` | `mcp/test_workflow_state_server.py` | Add MCP tool tests |
| Extended `transition_phase` | `mcp/test_workflow_state_server.py` | Extend existing tests |
| Extended `complete_phase` | `mcp/test_workflow_state_server.py` | Extend existing tests |
