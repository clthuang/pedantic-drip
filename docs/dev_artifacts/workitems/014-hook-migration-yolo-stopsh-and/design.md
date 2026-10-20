# Design: Hook Migration — yolo-stop.sh

## Prior Art Research

### Codebase Findings

1. **PHASE_SEQUENCE** (`hooks/lib/transition_gate/constants.py:12-20`): Canonical 7-phase tuple — `(brainstorm, specify, design, create-plan, create-tasks, implement, finish)`. Precomputed `_PHASE_VALUES` tuple already exists in `engine.py:28`.

2. **Phase enum** (`hooks/lib/transition_gate/models.py:13-22`): Hyphenated `.value` attributes — `Phase.create_plan.value == "create-plan"`.

3. **WorkflowStateEngine.get_state()** (`hooks/lib/workflow_engine/engine.py:54-75`): Returns `FeatureWorkflowState | None`. Falls back to `.meta.json` if DB unhealthy. The `current_phase` field is already the _next_ phase to enter (derived internally via `_next_phase_value`). However, the spec uses `last_completed_phase` and manually derives next phase for consistency with the fallback path.

4. **EntityDatabase constructor** (`hooks/lib/entity_registry/database.py:414-434`): Eager `sqlite3.connect(db_path, timeout=5.0)` + `_set_pragmas()` + `_migrate()`. Can throw `sqlite3.Error` or `OSError`.

5. **session-start.sh PYTHONPATH pattern** (`hooks/session-start.sh:320`): `PYTHONPATH="${SCRIPT_DIR}/lib"` — the only existing hook using this pattern for Python module imports.

6. **Existing try/except in hooks**: Bare `except:` with `print('')` or `pass` — established convention for hooks to fail silently.

7. **yolo-stop.sh migration targets**: Lines 110-130 (inline `.meta.json` parsing), lines 172-184 (hardcoded `phase_map` dict).

### External Findings

1. **Claude Code hook semantics**: Exit 0 = allow, exit 2 = block. stdout = JSON `{decision, reason}`. stderr must be suppressed to avoid corrupting JSON.

2. **Python try/except ImportError**: Standard pattern for graceful module degradation — try import, except ImportError with fallback.

3. **Fallback-open pattern**: Hooks should fail open (allow stop) rather than crash. Aligns with NFR-3.

## Architecture Overview

This is a targeted migration within a single file (`yolo-stop.sh`). No new files, no new modules, no architectural changes.

### Change Scope

The hook has 5 logical sections. Only section 3 (feature state reading) and section 4 (next-phase derivation) are modified:

| Section | Lines | Change |
|---------|-------|--------|
| 1. YOLO checks (mode, paused, usage) | 20-69 | None |
| 2. Active feature scanning | 75-107 | None |
| 3. Feature state reading | 110-130 | Retained (supplemented by engine call in section 4) |
| 4. Next-phase derivation | 172-184 | **Replace** with `PHASE_SEQUENCE` lookup |
| 5. Controls (completion, stuck, max blocks, message) | 132-200 | None (except input source changes) |

Sections 3 and 4 are merged into a single combined Python invocation per the spec's Structural Note.

### Data Flow (After Migration)

```
Active feature scanning (unchanged)
  → FEATURE_ID, FEATURE_SLUG, FEATURE_STATUS, LAST_COMPLETED_PHASE (from .meta.json)
  → Combined Python invocation:
       try:
         EntityDatabase → WorkflowStateEngine → get_state()
         → state.last_completed_phase (or fallback to $LAST_COMPLETED_PHASE)
         → PHASE_SEQUENCE index lookup → next_phase
       except:
         → inline phase_map fallback → next_phase
  → NEXT_PHASE (stdout capture)
  → Existing controls use NEXT_PHASE, FEATURE_STATUS, LAST_COMPLETED_PHASE
```

## Components

### C1: Combined Python Invocation

**Purpose:** Replace sections 3-4 (lines 110-184) with a single `python3 -c` call that imports engine modules, retrieves state, and derives next phase.

**Location:** `yolo-stop.sh`, replacing lines 172-184 (phase_map block). Lines 110-130 (feature state reading) are retained because `FEATURE_STATUS` and `LAST_COMPLETED_PHASE` are still needed by other controls (completion check on line 133, stuck detection on line 150).

**Accepted deviation from spec FR-2:** The spec says "Replace steps 2-3 with a call to `WorkflowStateEngine.get_state()`." However, the existing `.meta.json` parsing (lines 110-130) must remain because:
- `FEATURE_STATUS` is used by the completion check (line 133) and is not available from `FeatureWorkflowState`
- `LAST_COMPLETED_PHASE` is used as fallback input to the combined invocation when `get_state()` returns None
- Removing it would break sections that depend on these variables

The engine call _supplements_ the existing parsing — it provides a more authoritative `last_completed_phase` when available, but does not replace the `.meta.json` read entirely.

**Structure:** Per spec Structural Note skeleton:

```
NEXT_PHASE=$(PYTHONPATH="${SCRIPT_DIR}/lib" python3 -c "
try:
    from transition_gate.constants import PHASE_SEQUENCE
    from workflow_engine.engine import WorkflowStateEngine
    from entity_registry.database import EntityDatabase
    import os

    _PHASE_VALUES = tuple(p.value for p in PHASE_SEQUENCE)
    db_path = os.environ.get('ENTITY_DB_PATH',
        os.path.expanduser('~/.claude/iflow/entities/entities.db'))
    db = EntityDatabase(db_path)
    engine = WorkflowStateEngine(db, '${PROJECT_ROOT}/${ARTIFACTS_ROOT}')
    state = engine.get_state('feature:${FEATURE_ID}-${FEATURE_SLUG}')

    if state is not None:
        last = state.last_completed_phase or ''
    else:
        last = '${LAST_COMPLETED_PHASE}'

    # Both null representations converge here:
    # Engine path: None -> '' (via 'or' fallback above)
    # Fallback path: string 'null' (from .meta.json parsing)
    if last in ('null', ''):
        print(PHASE_SEQUENCE[1].value)  # specify — first command phase
    elif last in _PHASE_VALUES:
        idx = _PHASE_VALUES.index(last)
        print(_PHASE_VALUES[idx + 1] if idx < len(_PHASE_VALUES) - 1 else '')
    else:
        print('')
except Exception:
    phase_map = {
        'null': 'specify', 'brainstorm': 'specify', 'specify': 'design',
        'design': 'create-plan', 'create-plan': 'create-tasks',
        'create-tasks': 'implement', 'implement': 'finish',
    }
    last = '${LAST_COMPLETED_PHASE}'
    print(phase_map.get(last, ''))
" 2>/dev/null)
```

### C2: PYTHONPATH Setup

**Purpose:** Make `transition_gate`, `workflow_engine`, and `entity_registry` packages importable from the hook's `lib/` directory.

**Mechanism:** Inline `PYTHONPATH="${SCRIPT_DIR}/lib"` prefix on the `python3 -c` command. The hook's `SCRIPT_DIR` resolves to the hooks directory (`plugins/iflow/hooks/`), so `${SCRIPT_DIR}/lib` points to `plugins/iflow/hooks/lib/` where all three packages reside.

**Pattern source:** `session-start.sh:320` uses identical pattern.

## Technical Decisions

### TD-1: Use `last_completed_phase` instead of `current_phase`

**Decision:** The combined invocation reads `state.last_completed_phase` and derives next phase via PHASE_SEQUENCE index lookup, rather than using `state.current_phase` directly.

**Rationale:** `current_phase` is already the next phase (computed by `_next_phase_value` inside the engine). Using it would be simpler. However:
- The fallback path must derive next phase from `LAST_COMPLETED_PHASE` using the inline `phase_map`
- Both paths must produce identical output for the same input
- Using the same derivation algorithm (last_completed → next via sequence lookup) in both paths makes correctness verification straightforward

**Key divergence example:** For a new feature with `lastCompletedPhase=null`:
- Engine's `current_phase` = `"brainstorm"` (first phase in sequence, via `_next_phase_value` with no prior phase)
- Combined invocation's output = `"specify"` (via `PHASE_SEQUENCE[1].value`, preserving null→specify mapping from original `phase_map`)

If the invocation used `state.current_phase` directly, it would output `"brainstorm"` — breaking the existing behavior. The `last_completed_phase` approach avoids this by applying the same null→specify mapping in both engine and fallback paths.

**Trade-off:** Slight redundancy (engine already computed this internally) for consistency and verifiability.

### TD-2: Retain existing `.meta.json` parsing (lines 110-130)

**Decision:** Keep the existing `python3 -c` block that reads `.meta.json` for `FEATURE_ID`, `FEATURE_SLUG`, `FEATURE_STATUS`, and `LAST_COMPLETED_PHASE`.

**Rationale:**
- `FEATURE_STATUS` has no equivalent in `FeatureWorkflowState` — needed for completion check (line 133)
- `LAST_COMPLETED_PHASE` is the fallback input when `get_state()` returns None
- Removing this block would require moving all state extraction into the combined invocation and restructuring the subsequent shell logic

### TD-3: Broad `except Exception` is intentional

**Decision:** The combined invocation uses `except Exception:` (not targeted exceptions).

**Rationale:** Per NFR-3 fallback mechanism. The hook must never crash — any failure in the engine path (import error, DB error, key error, type error) must fall through to the inline `phase_map`. This is a temporary safety net.

### TD-4: Use `python3` (not venv binary)

**Decision:** Use system `python3` in the combined invocation, not `${PLUGIN_ROOT}/.venv/bin/python`.

**Rationale:** yolo-stop.sh currently uses `python3` for all its Python calls (lines 35, 44, 86, 110, 138, 172). The transition_gate and workflow_engine modules have no external dependencies beyond stdlib + each other — they don't need the venv. Using the venv would require resolving `PLUGIN_ROOT` (yolo-stop.sh uses `SCRIPT_DIR` which is the hooks dir, not plugin root) and would diverge from the hook's existing convention.

## Risks

### R-1: Import chain and EntityDatabase construction latency (Low)

**Import chain analysis:** The combined invocation imports three packages:
1. `transition_gate.constants` — imports `Phase` enum and `PHASE_SEQUENCE` tuple. Only loads `transition_gate.models` (enum definitions). Does NOT load gate functions. This import is lightweight.
2. `workflow_engine.engine` — imports `WorkflowStateEngine`. Triggers `transition_gate.__init__` which loads all 26 gate functions via the `.gate` module, plus `entity_registry.database`. The gate function loading is the dominant import cost, but consists only of bytecode loading (no I/O, no execution).
3. `entity_registry.database` — imports `EntityDatabase`. Uses only stdlib (`sqlite3`, `os`, `json`).

All three packages use only stdlib dependencies. No external packages, no network calls during import. The 26 gate functions are Python function definitions — their import cost is bytecode loading, not execution.

**Estimated cold-start budget:** Module loading for all three packages: ~30-80ms (Python bytecode loading for ~20 files). `EntityDatabase` constructor (`sqlite3.connect()` + `_set_pragmas()` + `_migrate()`): ~5-20ms on warm filesystem. Total estimated: ~35-100ms — well within 500ms NFR-2 budget. Network-mounted home directory could add latency to the DB connection, but the fallback path catches this via the broad `except Exception`.

**Connection cleanup:** The `EntityDatabase` opens a `sqlite3` connection in its constructor. The combined invocation does not explicitly close it. This is acceptable because the entire `python3 -c` subprocess exits immediately after `print()` — Python's interpreter shutdown closes all open file descriptors and sqlite3 connections. There is no persistent process or connection pool. The connection exists for ~50-100ms total.

### R-2: PYTHONPATH collision (Low)

Setting `PYTHONPATH` inline affects only the `python3 -c` subprocess, not the parent shell or other processes. No collision risk.

### R-3: Phase sequence drift in fallback (Accepted)

If `PHASE_SEQUENCE` changes and the fallback `phase_map` is not updated, behavior diverges. Per spec NFR-3 drift risk: accepted trade-off — fallback is temporary.

### R-4: Shell variable interpolation in Python string (Low)

Shell variables (`${LAST_COMPLETED_PHASE}`, `${FEATURE_ID}`, `${FEATURE_SLUG}`) are interpolated by bash into the Python code string before Python executes. If a `.meta.json` value contains single quotes or Python-significant characters, it could break the string literal or (theoretically) inject Python code.

**Mitigation:** All interpolated values come from `.meta.json` fields parsed by the hook's own Python code (lines 110-130). The `lastCompletedPhase` field is validated by the engine as a known phase string (e.g., `"specify"`, `"design"`) — no user-controlled free text. `FEATURE_ID` is numeric, `FEATURE_SLUG` is a sanitized slug. The risk of malicious injection is effectively zero in this controlled context. This matches the existing convention — the current `phase_map` invocation (lines 172-184) already interpolates `${LAST_COMPLETED_PHASE}` identically.

### R-5: Plugin cache package completeness (Low)

The combined invocation assumes `${SCRIPT_DIR}/lib` contains `transition_gate/`, `workflow_engine/`, and `entity_registry/` packages. In the dev workspace, these always exist. In the installed plugin cache (`~/.claude/plugins/cache/*/iflow*/*/hooks/lib/`), completeness depends on the plugin sync mechanism.

**Mitigation:** If any package is missing, the `from ... import` statement raises `ImportError`, caught by the broad `except Exception`, and the fallback `phase_map` is used. This is exactly the NFR-3 graceful degradation working as designed.

## Interfaces

### I-1: Combined Invocation → Shell

**Input:** Shell variables interpolated by bash before Python executes:
- `${PROJECT_ROOT}` — absolute project root path
- `${ARTIFACTS_ROOT}` — relative artifacts directory (e.g., `docs`)
- `${FEATURE_ID}` — feature ID string (e.g., `014`)
- `${FEATURE_SLUG}` — feature slug (e.g., `hook-migration-yolo-stopsh-and`)
- `${LAST_COMPLETED_PHASE}` — fallback phase string from `.meta.json`

**Output:** Single line to stdout — the next phase name (e.g., `design`) or empty string if no next phase. Captured by shell into `$NEXT_PHASE`.

**Error handling:** stderr suppressed via `2>/dev/null`. Any exception falls to inline `phase_map` fallback within the same subprocess.

### I-2: Engine API Usage

```python
# Construction
db = EntityDatabase(db_path)  # Can throw sqlite3.Error, OSError
engine = WorkflowStateEngine(db, artifacts_root)  # No I/O

# State retrieval
state = engine.get_state(feature_type_id)
# Returns: FeatureWorkflowState | None
# Fields used: state.last_completed_phase (str | None)
# Fields NOT used: current_phase, completed_phases, mode, source
```

### I-3: PHASE_SEQUENCE API Usage

```python
from transition_gate.constants import PHASE_SEQUENCE

# Index access
PHASE_SEQUENCE[1].value  # "specify" — used for null→specify mapping

# Sequence derivation
_PHASE_VALUES = tuple(p.value for p in PHASE_SEQUENCE)
idx = _PHASE_VALUES.index(last)
next = _PHASE_VALUES[idx + 1]  # bounds-checked: idx < len - 1
```

## File Change Summary

| File | Action | Lines Changed |
|------|--------|--------------|
| `plugins/iflow/hooks/yolo-stop.sh` | Modify | Replace lines 172-184 (phase_map block) with combined invocation (~25 lines net) |

No new files. No deleted files. No test changes needed (AC-6: existing tests pass without modification).

**Test coverage note:** After migration, existing hook tests exercise the **fallback path only** (no database present in test environment). The engine primary path is covered by `workflow_engine` unit tests (184 tests) and the manual verification checkpoint (AC-8). Both paths produce identical output by design — the fallback `phase_map` is a static copy of the same mapping that `PHASE_SEQUENCE` encodes.

## Manual Verification Checkpoint (AC-8)

Per spec AC-8: After implementation, with `ENTITY_DB_PATH` pointing to a valid DB containing the active feature entity, run the hook and confirm the block message reads `"Invoke /iflow:design"` for a feature with `lastCompletedPhase="specify"`.

**This is a required gate task in the implementation plan** — not an optional afterthought. The plan must include an explicit task for this checkpoint, and it must pass before the feature can be marked complete. This compensates for the zero automated hook-level coverage of the primary engine path.
