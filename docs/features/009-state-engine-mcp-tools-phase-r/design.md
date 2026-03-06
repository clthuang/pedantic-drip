# Design: State Engine MCP Tools — Phase Read/Write

## Prior Art Research

### Codebase Patterns

- **entity_server.py** (274 lines): Primary template. FastMCP with `@asynccontextmanager` lifespan, module-level globals (`_db`, `_config`, `_project_root`, `_artifacts_root`), `@mcp.tool()` async functions delegating to `_process_*()` helpers, stdio transport entry point.
- **server_helpers.py** (329 lines): Processing functions extracted to separate module for testability. Accept `db` as first arg plus primitives, return `str`, never raise.
- **run-entity-server.sh** (41 lines): Bootstrap script with 4-step resolution: venv fast-path → system python3 → uv bootstrap → pip fallback. Sets `PYTHONPATH` and `PYTHONUNBUFFERED=1`.
- **plugin.json**: Two existing MCP servers (`memory-server`, `entity-registry`). Third entry follows same pattern.
- **test_entity_server.py**: `monkeypatch.setattr` to inject in-memory `EntityDatabase`, `await` tool handlers directly.

### External Research

- FastMCP auto-extracts function name, docstring, and type annotations for MCP schema generation.
- Sync tool functions run in thread pool automatically; async functions run on event loop.
- `ToolError` for expected/domain errors; standard exceptions forwarded by default.
- Known Claude Code client bug: JSON object params sometimes serialized as strings — mitigated by using scalar types for all tool inputs.

## Architecture Overview

### Component Diagram

```
┌────────────────────────────────────┐
│  Claude / MCP Client               │
│  (tool-use protocol via stdio)     │
└──────────────┬─────────────────────┘
               │ JSON-RPC/stdio
┌──────────────▼─────────────────────┐
│  workflow_state_server.py          │
│  ┌──────────────────────────────┐  │
│  │ FastMCP("workflow-engine")   │  │
│  │                              │  │
│  │ @mcp.tool() get_phase        │  │
│  │ @mcp.tool() transition_phase │  │
│  │ @mcp.tool() complete_phase   │  │
│  │ @mcp.tool() validate_prereqs │  │
│  │ @mcp.tool() list_by_phase    │  │
│  │ @mcp.tool() list_by_status   │  │
│  └──────────┬───────────────────┘  │
│             │ delegates            │
│  ┌──────────▼───────────────────┐  │
│  │ _process_*() functions       │  │
│  │ (inline in server module)    │  │
│  └──────────┬───────────────────┘  │
└─────────────┼──────────────────────┘
              │ calls
┌─────────────▼──────────────────────┐
│  WorkflowStateEngine (feature 008) │
│  (stateless orchestrator)          │
├────────────────────────────────────┤
│  EntityDatabase (shared WAL)       │
└────────────────────────────────────┘
```

### Components

#### C1: `workflow_state_server.py`

The MCP server module. Lives at `plugins/iflow/mcp/workflow_state_server.py`.

**Responsibilities:**
- FastMCP server initialization with lifespan
- 6 `@mcp.tool()` async handler functions (thin wrappers)
- 6 `_process_*()` processing functions (error handling + serialization)
- Module-level globals: `_db`, `_engine`, `_artifacts_root`

**Decision: Inline processing functions vs separate module.**
Processing functions are defined inline in the server module (like `memory_server.py`), not extracted to a separate `server_helpers.py` module (like `entity_registry`). Rationale: The processing functions are server-specific (they serialize engine results to JSON strings), not reusable library code. The entity_registry extracted helpers because they're shared across multiple consumers. For 6 small functions, a single-file approach is simpler and adequate. Testing uses `monkeypatch.setattr` on the module globals, same pattern as `test_entity_server.py`.

#### C2: `run-workflow-server.sh`

Bootstrap shell script at `plugins/iflow/mcp/run-workflow-server.sh`. Identical structure to `run-entity-server.sh` with only the diagnostic prefix and `SERVER_SCRIPT` variable changed.

#### C3: Plugin registration

Entry in `.claude-plugin/plugin.json` under `mcpServers`.

### Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Processing function location | Inline in server module | Server-specific serialization logic, not reusable. Simpler than separate module for 6 functions. |
| Serialization approach | Manual dict construction with `.value` for enums | Spec R4 requires explicit `.value` for `Severity(str, Enum)`. `dataclasses.asdict()` returns enum objects, not string values. |
| Module-level globals | `_db`, `_engine`, `_artifacts_root` | Matches `entity_server.py` pattern. `_engine` is new (holds `WorkflowStateEngine` instance). |
| Tool function style | Async (matching entity_server pattern) | Consistency with existing servers. FastMCP handles sync→async conversion automatically, but async is the established convention. |
| Phase validation | Delegated to engine/gates | Spec R4 explicitly states MCP tools do NOT validate `target_phase`. |
| Error format | Dual: `"Error: ..."` for ValueError, `"Internal error: ..."` for unexpected | Spec R3. Processing functions catch both and return strings. |

### Risks

| Risk | Mitigation |
|------|-----------|
| DB contention with entity-registry server | WAL mode (already enabled by EntityDatabase constructor) supports concurrent readers. Both servers are primarily read-heavy. |
| Bootstrap script fails silently | Bootstrap tests (bash script tests) verify PYTHONPATH, PYTHONUNBUFFERED, and no-stdout-before-exec. |
| `WorkflowStateEngine` constructor does I/O | Constructor stores references only (no DB calls, no I/O per docstring). Safe for lifespan initialization. |
| Filesystem I/O in `validate_prerequisites` | `_get_existing_artifacts()` does `os.path.exists()` checks. Bounded by `_ALL_HARD_ARTIFACTS` set size (small constant). Within 100ms budget per SC-6. |

## Interfaces

### I0: Module Imports

```python
"""MCP workflow-engine server for phase read/write operations.

Runs as a subprocess via stdio transport.  Never print to stdout
(corrupts JSON-RPC protocol) -- all logging goes to stderr.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager

# Make workflow_engine, transition_gate, entity_registry, semantic_memory
# importable from hooks/lib/ — safety net for direct invocation and tests.
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import EntityDatabase
from semantic_memory.config import read_config
from transition_gate.models import Severity, TransitionResult
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.models import FeatureWorkflowState

from mcp.server.fastmcp import FastMCP
```

### I1: Module-Level Globals

```python
_db: EntityDatabase | None = None
_engine: WorkflowStateEngine | None = None
_artifacts_root: str = ""
```

### I2: Lifespan

```python
@asynccontextmanager
async def lifespan(server):
    """Manage DB connection and engine lifecycle."""
    global _db, _engine, _artifacts_root

    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/iflow/entities/entities.db"),
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    _db = EntityDatabase(db_path)

    project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
    config = read_config(project_root)
    _artifacts_root = os.path.join(project_root, str(config.get("artifacts_root", "docs")))

    _engine = WorkflowStateEngine(_db, _artifacts_root)

    print(f"workflow-engine: started (db={db_path}, artifacts={_artifacts_root})", file=sys.stderr)

    try:
        yield {}
    finally:
        if _db is not None:
            _db.close()
            _db = None
        _engine = None
```

### I3: MCP Tool Handlers

Each handler follows the pattern: None guard → delegate to `_process_*()`.

```python
mcp = FastMCP("workflow-engine", lifespan=lifespan)

@mcp.tool()
async def get_phase(feature_type_id: str) -> str:
    """Read the current workflow state for a feature."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_get_phase(_engine, feature_type_id)

@mcp.tool()
async def transition_phase(
    feature_type_id: str,
    target_phase: str,
    yolo_active: bool = False,
) -> str:
    """Validate and enter a target phase."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_transition_phase(_engine, feature_type_id, target_phase, yolo_active)

@mcp.tool()
async def complete_phase(feature_type_id: str, phase: str) -> str:
    """Record a phase as completed and advance to next phase."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_complete_phase(_engine, feature_type_id, phase)

@mcp.tool()
async def validate_prerequisites(feature_type_id: str, target_phase: str) -> str:
    """Dry-run gate evaluation without executing the transition."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_validate_prerequisites(_engine, feature_type_id, target_phase)

@mcp.tool()
async def list_features_by_phase(phase: str) -> str:
    """All features currently in a given workflow phase."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_list_features_by_phase(_engine, phase)

@mcp.tool()
async def list_features_by_status(status: str) -> str:
    """All features with a given entity status."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_list_features_by_status(_engine, status)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### I4: Processing Functions

Each function accepts the engine instance (not globals), catches exceptions, returns `str`.

```python
def _serialize_state(state: FeatureWorkflowState) -> dict:
    """Convert FeatureWorkflowState to JSON-serializable dict."""
    return {
        "feature_type_id": state.feature_type_id,
        "current_phase": state.current_phase,
        "last_completed_phase": state.last_completed_phase,
        "completed_phases": list(state.completed_phases),
        "mode": state.mode,
        "source": state.source,
    }

def _serialize_result(result: TransitionResult) -> dict:
    """Convert TransitionResult to JSON-serializable dict.

    Assumes guard_id is always non-None — engine._evaluate_gates()
    always passes an explicit guard_id string ('G-18', 'G-08', etc.).
    """
    return {
        "allowed": result.allowed,
        "reason": result.reason,
        "severity": result.severity.value,
        "guard_id": result.guard_id,
    }

def _process_get_phase(engine: WorkflowStateEngine, feature_type_id: str) -> str:
    try:
        state = engine.get_state(feature_type_id)
        if state is None:
            return f"Feature not found: {feature_type_id}"
        return json.dumps(_serialize_state(state))
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"

def _process_transition_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    target_phase: str,
    yolo_active: bool,
) -> str:
    try:
        results = engine.transition_phase(feature_type_id, target_phase, yolo_active)
        # Coupling: mirrors engine.py line 63 — engine updates DB iff all gates pass.
        # If engine semantics change, update this derivation in sync.
        transitioned = all(r.allowed for r in results)
        return json.dumps({
            "allowed": transitioned,
            "results": [_serialize_result(r) for r in results],
            "transitioned": transitioned,
        })
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"

def _process_complete_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    phase: str,
) -> str:
    try:
        state = engine.complete_phase(feature_type_id, phase)
        return json.dumps(_serialize_state(state))
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"

def _process_validate_prerequisites(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    target_phase: str,
) -> str:
    try:
        results = engine.validate_prerequisites(feature_type_id, target_phase)
        all_passed = all(r.allowed for r in results)
        return json.dumps({
            "all_passed": all_passed,
            "results": [_serialize_result(r) for r in results],
        })
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"

def _process_list_features_by_phase(engine: WorkflowStateEngine, phase: str) -> str:
    # ValueError from _row_to_state on corrupt DB data is intentionally caught
    # by Exception and reported as "Internal error:" (not user input error).
    try:
        states = engine.list_by_phase(phase)
        return json.dumps([_serialize_state(s) for s in states])
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"

def _process_list_features_by_status(engine: WorkflowStateEngine, status: str) -> str:
    # ValueError from _row_to_state on corrupt DB data is intentionally caught
    # by Exception and reported as "Internal error:" (not user input error).
    try:
        states = engine.list_by_status(status)
        return json.dumps([_serialize_state(s) for s in states])
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"
```

**Key design notes:**
- `_serialize_state()` and `_serialize_result()` are shared helpers, not processing functions. They don't catch exceptions.
- `_process_get_phase` does NOT catch `ValueError` separately because `get_state()` returns `None` (not raises) for missing features. This is guaranteed by the `WorkflowStateEngine` public API contract (spec Dependency API): `get_state() -> FeatureWorkflowState | None`. Any future engine change that breaks this contract would be a breaking API change requiring coordinated updates.
- `_process_list_*` functions do NOT catch `ValueError` separately because `list_by_phase()` and `list_by_status()` don't raise `ValueError`.
- `_process_transition_phase` and `_process_complete_phase` catch `ValueError` because the engine raises it for "Feature not found", invalid phases, etc.

### I5: Bootstrap Script

```bash
#!/bin/bash
# Bootstrap and run the MCP workflow-engine server.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER_SCRIPT="$SCRIPT_DIR/workflow_state_server.py"

export PYTHONPATH="$PLUGIN_DIR/hooks/lib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# Step 1: Fast path -- existing venv
if [[ -x "$VENV_DIR/bin/python" ]]; then
    exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"
fi

# Step 2: System python3 with required deps already available
if python3 -c "import mcp.server.fastmcp" 2>/dev/null; then
    exec python3 "$SERVER_SCRIPT"
fi

# Step 3: Bootstrap with uv (preferred)
if command -v uv >/dev/null 2>&1; then
    echo "workflow-engine: bootstrapping venv with uv at $VENV_DIR..." >&2
    uv venv "$VENV_DIR" >&2
    uv pip install --python "$VENV_DIR/bin/python" "mcp>=1.0,<2" >&2
    exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"
fi

# Step 4: Bootstrap with pip (fallback)
echo "workflow-engine: bootstrapping venv with pip at $VENV_DIR..." >&2
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q "mcp>=1.0,<2" >&2
exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"
```

### I6: Plugin Registration

Addition to `.claude-plugin/plugin.json`:

```json
{
  "mcpServers": {
    "memory-server": { ... },
    "entity-registry": { ... },
    "workflow-engine": {
      "command": "${CLAUDE_PLUGIN_ROOT}/mcp/run-workflow-server.sh",
      "args": []
    }
  }
}
```

### I7: Test Structure

```
plugins/iflow/mcp/
├── workflow_state_server.py          # Server + processing functions
├── run-workflow-server.sh            # Bootstrap script
├── test_workflow_state_server.py     # Processing function unit tests
└── test_run_workflow_server.sh       # Bootstrap script tests
```

**Test approach for processing functions** (`test_workflow_state_server.py`):
- Fixtures: in-memory `EntityDatabase`, real `WorkflowStateEngine` instance
- Seed data: create entity + workflow phase rows for test features
- Test categories per SC-2: (a) success, (b) not-found/empty, (c) ValueError, (d) unexpected exception via mock/patch

**Fixture setup example:**
```python
import pytest
from entity_registry.database import EntityDatabase
from workflow_engine.engine import WorkflowStateEngine

@pytest.fixture
def db():
    """In-memory database with schema."""
    return EntityDatabase(":memory:")

@pytest.fixture
def engine(db, tmp_path):
    """Engine backed by in-memory DB."""
    return WorkflowStateEngine(db, str(tmp_path))

@pytest.fixture
def seeded_engine(engine, db):
    """Engine with a test feature seeded in DB."""
    db.register_entity("feature", "009-test", "Test Feature", status="active")
    db.create_workflow_phase("feature:009-test", workflow_phase="specify")
    return engine
```

**Sample test pattern:**
```python
def test_get_phase_success(seeded_engine):
    result = _process_get_phase(seeded_engine, "feature:009-test")
    data = json.loads(result)
    assert data["feature_type_id"] == "feature:009-test"
    assert data["current_phase"] == "specify"

def test_get_phase_not_found(engine):
    result = _process_get_phase(engine, "feature:nonexistent")
    assert result == "Feature not found: feature:nonexistent"

def test_unexpected_exception(seeded_engine, monkeypatch):
    monkeypatch.setattr(seeded_engine, "get_state", lambda *a: 1/0)
    result = _process_get_phase(seeded_engine, "feature:009-test")
    assert result.startswith("Internal error: ZeroDivisionError:")
```

**Test approach for bootstrap** (`test_run_workflow_server.sh`):
- Bash syntax check (`bash -n`)
- Executable permission check
- PYTHONPATH verification
- PYTHONUNBUFFERED verification
- No stdout before exec

## File Inventory

| File | Action | Purpose |
|------|--------|---------|
| `plugins/iflow/mcp/workflow_state_server.py` | Create | MCP server with tools and processing functions |
| `plugins/iflow/mcp/run-workflow-server.sh` | Create | Bootstrap shell script |
| `plugins/iflow/.claude-plugin/plugin.json` | Modify | Add workflow-engine server entry |
| `plugins/iflow/mcp/test_workflow_state_server.py` | Create | Processing function tests |
| `plugins/iflow/mcp/test_run_workflow_server.sh` | Create | Bootstrap script tests |

## Dependencies

- `WorkflowStateEngine` from `workflow_engine` (feature 008) — import via `hooks/lib/` PYTHONPATH
- `FeatureWorkflowState` from `workflow_engine.models`
- `TransitionResult`, `Severity` from `transition_gate.models`
- `EntityDatabase` from `entity_registry.database`
- `read_config` from `semantic_memory.config`
- `FastMCP` from `mcp.server.fastmcp`
