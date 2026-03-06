# Design: Graceful Degradation to .meta.json

## Prior Art Research

### Codebase Patterns

1. **Existing `.meta.json` hydration** (`engine.py:233-310`): `_hydrate_from_meta_json()` already reads `.meta.json`, derives `FeatureWorkflowState`, and backfills DB. Key limitation: calls `self.db.get_entity()` at line 238 as precondition — unusable when DB is down. The phase derivation logic (lines 255-283) and `_derive_completed_phases`/`_next_phase_value` helpers are reusable.

2. **Graceful degradation in frontmatter_inject.py** (lines 143-148): Catches `sqlite3.Error` and `OSError`, logs warning to stderr, then `sys.exit(0)` — non-blocking pattern for hooks. Validates the approach of catching `sqlite3.Error` broadly rather than specific subclasses.

3. **Atomic file write in frontmatter.py** (lines 296-322): `NamedTemporaryFile` in same directory + `os.rename()`. Includes proper cleanup in `finally` block. This exact pattern applies to `.meta.json` write fallback.

4. **Semantic memory fallback** (`semantic_memory/database.py:398-400`): Catches `sqlite3.OperationalError`, returns empty list. Simple fallback-to-empty pattern for list operations.

5. **EntityDatabase._conn** (`database.py:352-356`): `sqlite3.Connection` with `PRAGMA busy_timeout=5000`. Health probe via `_conn.execute("SELECT 1")` is viable but must account for 5s timeout on locked DBs.

6. **_extract_slug()** (`engine.py:189-200`): Already extracts slug from `feature_type_id` without DB access. Enables filesystem path derivation in fallback.

7. **Existing MCP error handling** (`workflow_state_server.py:105-166`): Catches `ValueError` and generic `Exception`, returns string messages. No structured format, no degradation signal.

### External Solutions

1. **SQLite health probe**: Standard pattern is `SELECT 1` via cursor, catch `sqlite3.OperationalError`. Simple, sub-millisecond on healthy DBs.

2. **Atomic file write (POSIX)**: `tempfile` + `flush()` + `fsync()` + `os.replace()`. The `os.replace()` is preferred over `os.rename()` for guaranteed atomicity. Existing codebase uses `os.rename()` which is equivalent on POSIX.

3. **MCP error signaling**: The MCP spec supports an `isError` flag in tool results. Industry practice leans toward structured JSON error bodies with type, message, and recovery hints.

4. **Circuit breaker pattern** (Closed -> Open -> Half-Open): Considered but rejected — adds complexity with no benefit for a single-request-per-session model (MCP stdio transport). The health probe at method entry is the simpler equivalent.

5. **Defense-in-depth**: Proactive health probe (primary) + reactive try/except (secondary) is a well-established reliability pattern. Both paths share the same fallback code.

---

## Architecture Overview

### Design Philosophy

The degradation layer wraps the existing engine with try/except guards at each public method boundary. It does NOT create a separate "degraded engine" or strategy pattern — the existing engine methods gain fallback paths inline. This keeps the change minimal, avoids doubling the API surface, and ensures the happy path is unchanged.

### Component Topology

```
┌─────────────────────────────────────┐
│        MCP Server Layer             │
│  workflow_state_server.py           │
│  ┌───────────────────────────────┐  │
│  │ _serialize_state() ──────────►│──┼── adds `degraded` field
│  │ _serialize_result()           │  │
│  │ _process_* functions ─────────│──┼── structured JSON errors
│  │ TransitionResponse handling   │  │
│  └───────────────────────────────┘  │
└──────────────┬──────────────────────┘
               │ calls
┌──────────────▼──────────────────────┐
│    WorkflowStateEngine              │
│    engine.py                        │
│  ┌───────────────────────────────┐  │
│  │ _check_db_health() ──────────►│──┼── SELECT 1 probe (primary)
│  │                               │  │
│  │ get_state() ──────────────────│──┼── try DB → catch → _read_state_from_meta_json
│  │ transition_phase() ───────────│──┼── try DB write → catch → TransitionResponse(degraded=True)
│  │ complete_phase() ─────────────│──┼── try DB write → catch → _write_meta_json_fallback
│  │ list_by_phase/status() ───────│──┼── try DB → catch → _scan_features_filesystem
│  │ validate_prerequisites() ─────│──┼── transitive via get_state (no change)
│  │                               │  │
│  │ _read_state_from_meta_json()  │  │   NEW: pure-filesystem reader
│  │ _write_meta_json_fallback()   │  │   NEW: atomic .meta.json writer
│  │ _scan_features_filesystem()   │  │   NEW: directory scanner for lists
│  └───────────────────────────────┘  │
└──────────────┬──────────────────────┘
               │ reads/writes
┌──────────────▼──────────────────────┐
│    Data Layer                        │
│  ┌─────────────┐  ┌───────────────┐ │
│  │ EntityDB     │  │ .meta.json    │ │
│  │ (primary)    │  │ (fallback)    │ │
│  └─────────────┘  └───────────────┘ │
└──────────────────────────────────────┘
```

### Data Flow: Normal vs Degraded

**Normal path** (DB available):
```
get_state() → db.get_workflow_phase() → _row_to_state() → FeatureWorkflowState(source="db")
```

**Degraded path** (DB unavailable):
```
get_state() → _check_db_health() returns False
           → skip DB call entirely
           → _read_state_from_meta_json() → FeatureWorkflowState(source="meta_json_fallback")
```

**Secondary defense** (probe passes, DB fails mid-operation):
```
get_state() → _check_db_health() returns True
           → db.get_workflow_phase() raises sqlite3.Error
           → catch → _read_state_from_meta_json() → FeatureWorkflowState(source="meta_json_fallback")
```

---

## Components

### C1: Health Probe (`_check_db_health`)

**Location:** `engine.py`, new private method on `WorkflowStateEngine`

**Responsibility:** Lightweight DB availability check before each public method call.

**Behavior:**
- Guard: if `self.db._conn is None` → return `False` (defensive — while `EntityDatabase.close()` does not currently set `_conn` to `None`, this guards against future changes or direct `_conn` manipulation)
- Execute `self.db._conn.execute("SELECT 1")`
- Return `True` on success, `False` on any `sqlite3.Error`
- Result stored as local variable `db_available`, passed through call chain

**NFR-1 interaction:** `EntityDatabase` sets `PRAGMA busy_timeout=5000`. In worst case (locked DB), `SELECT 1` may block up to 5s before failing. This violates the `<5ms` single-operation target. **Trade-off accepted:** This is a rare edge case (locked DB with contention), and the health probe correctly reports DB unavailable afterward. NFR-1 `<5ms` applies to the fallback path execution, not the probe on a blocked DB.

**Design decision:** Local variable, not instance attribute. Preserves stateless design (NFR-4). Each public method call gets its own probe result.

### C2: Pure-Filesystem Reader (`_read_state_from_meta_json`)

**Location:** `engine.py`, new private method on `WorkflowStateEngine`

**Responsibility:** Derive `FeatureWorkflowState` from `.meta.json` without any DB calls.

**Behavior:**
1. Extract slug via `_extract_slug(feature_type_id)`
2. Construct path: `{artifacts_root}/features/{slug}/.meta.json`
3. Read and parse JSON (return `None` on `FileNotFoundError` or `json.JSONDecodeError`)
4. Extract `status`, `mode`, `lastCompletedPhase`
5. Derive `workflow_phase` using same logic as `_hydrate_from_meta_json` lines 255-283
6. Build `FeatureWorkflowState(source="meta_json_fallback")`

**Reuse:** Phase derivation logic (status → workflow_phase mapping) is identical to `_hydrate_from_meta_json`. To avoid duplication, extract the shared derivation into `_derive_state_from_meta(meta: dict, feature_type_id: str) -> FeatureWorkflowState | None`. Both `_hydrate_from_meta_json` and `_read_state_from_meta_json` call it.

### C3: Atomic `.meta.json` Writer (`_write_meta_json_fallback`)

**Location:** `engine.py`, new private method on `WorkflowStateEngine`

**Responsibility:** Write state changes to `.meta.json` when DB is unavailable during `complete_phase()`.

**Behavior:**
1. Read current `.meta.json` content — wrapped in `try/except (FileNotFoundError, json.JSONDecodeError, OSError)` to handle missing or corrupt files. On read failure, raise `ValueError` with descriptive message (caller decides how to handle).
2. Update fields: `lastCompletedPhase`, `phases.{phase}` timestamps, `status` (if finishing)
3. Write atomically: write to `{path}.tmp`, then `os.replace()`
4. Return `FeatureWorkflowState(source="meta_json_fallback")`

**Write pattern:** Follows existing `frontmatter.py` pattern — `NamedTemporaryFile(dir=target_dir)` + write + close + `os.replace()`. Cleanup in `finally`.

### C4: Filesystem Scanner (`_scan_features_filesystem`)

**Location:** `engine.py`, new private method on `WorkflowStateEngine`

**Responsibility:** Enumerate feature states from `.meta.json` files when DB is unavailable for list operations.

**Behavior:**
1. Glob `{artifacts_root}/features/*/.meta.json`
2. For each file, derive `feature_type_id` from directory name (e.g., `features/008-foo/` → `feature:008-foo`)
3. Call `_read_state_from_meta_json()` for each
4. Filter `None` results (unparseable files)
5. Return list of `FeatureWorkflowState`

### C5: TransitionResponse Dataclass

**Location:** `workflow_engine/models.py`

**Responsibility:** Wrap `transition_phase()` return value with degradation signal.

**Fields:**
```python
@dataclass(frozen=True)
class TransitionResponse:
    results: tuple[TransitionResult, ...]
    degraded: bool
```

**Usage:** `transition_phase()` ALWAYS returns `TransitionResponse` (both normal and degraded paths). Normal: `TransitionResponse(results=..., degraded=False)`. Degraded: `TransitionResponse(results=..., degraded=True)`. Other methods signal degradation via `FeatureWorkflowState.source`.

### C6: Structured Error Responses

**Location:** `workflow_state_server.py`, updates to `_process_*` functions

**Responsibility:** Replace string error messages with structured JSON.

**Format:**
```python
def _make_error(error_type: str, message: str, recovery_hint: str) -> str:
    return json.dumps({
        "error": True,
        "error_type": error_type,
        "message": message,
        "recovery_hint": recovery_hint,
    })
```

**Error type mapping** (from spec R4):
- `sqlite3.Error` → `"db_unavailable"`
- `ValueError("Feature not found")` → `"feature_not_found"`
- `ValueError` (other) → `"invalid_transition"`
- `RuntimeError("Engine not initialized")` or similar init errors → `"not_initialized"`
- `Exception` (other) → `"internal"`

### C7: MCP Degradation Signal

**Location:** `workflow_state_server.py`, updates to serialization helpers and `_process_*` functions

**Responsibility:** Add `degraded` boolean to MCP responses where applicable.

**Detection logic:**
- `FeatureWorkflowState` responses: `degraded = (state.source == "meta_json_fallback")`
- `TransitionResponse`: read `response.degraded` directly
- `validate_prerequisites`: exempt per R7 (no `degraded` field — degradation surfaces transitively via `get_state()`)

### C8: `_scan_features_by_status(status)` Variant

**Location:** `engine.py`, new private method on `WorkflowStateEngine`

**Responsibility:** Enumerate features filtered by `.meta.json` `status` field when DB is unavailable for `list_by_status()`.

**Behavior:**
1. Glob `{artifacts_root}/features/*/.meta.json`
2. For each file, read raw JSON and check `meta["status"] == status` BEFORE building `FeatureWorkflowState`
3. Only build `FeatureWorkflowState` for matches (avoids wasted derivation)
4. Return filtered `list[FeatureWorkflowState]`

**Why separate from C4 `_scan_features_filesystem`:** `FeatureWorkflowState` has no `status` field. Filtering must happen at the `.meta.json` level before state derivation. `list_by_phase` can filter on `current_phase` (which IS on the dataclass), but `list_by_status` cannot. This variant reads the raw JSON and filters before deriving.

---

## Technical Decisions

### TD-1: Inline Fallback vs Strategy Pattern

**Decision:** Inline try/except fallback in each public method.

**Rationale:** Strategy pattern (e.g., `DBEngine` vs `FilesystemEngine`) would double the API surface and require a factory/selector. The degradation is a thin wrapper around existing logic, not a full alternative implementation. Inline guards keep the code localized and easy to follow.

**Trade-off:** Slightly more complex individual methods vs. much simpler overall architecture.

### TD-2: Health Probe as Local Variable

**Decision:** `db_available` is a local variable passed through the call chain, not an instance attribute.

**Rationale:** Preserves stateless design. Each request gets fresh probe results. No race conditions, no stale state, no need for TTL/invalidation.

**Trade-off:** Every public method has a `db_available` parameter threaded to internal calls. Acceptable — only 3-4 internal methods need it.

### TD-3: Shared Phase Derivation via Extract Method

**Decision:** Extract `_derive_state_from_meta(meta, feature_type_id)` from `_hydrate_from_meta_json` to share with `_read_state_from_meta_json`.

**Rationale:** The phase derivation logic (lines 255-283) is non-trivial and must stay consistent between the two paths. Duplication risks divergence.

**Trade-off:** Refactoring existing method, but the extraction is mechanical and testable.

### TD-4: `TransitionResponse` Always Returned from `transition_phase()`

**Decision:** `transition_phase()` ALWAYS returns `TransitionResponse`, both in normal and degraded paths. No union type. Other methods use `FeatureWorkflowState.source` for degradation signal.

**Rationale:** Eliminates the `list[TransitionResult] | TransitionResponse` union type that complicated MCP handler logic. Normal path wraps results in `TransitionResponse(results=..., degraded=False)`. Degraded path uses `TransitionResponse(results=..., degraded=True)`. The MCP handler always receives the same type. `validate_prerequisites()` is exempt per R7.

**Trade-off:** Minor overhead wrapping normal-path results in a dataclass. Justified by much simpler handler code — no type-checking branch needed.

### TD-5: `os.replace()` Over `os.rename()`

**Decision:** Use `os.replace()` for atomic `.meta.json` writes.

**Rationale:** `os.replace()` guarantees atomic replacement on POSIX (explicitly documented). `os.rename()` may raise `FileExistsError` on Windows (not relevant here but cleaner semantics). Existing codebase uses `os.rename()` — we follow the explicit `os.replace()` recommendation from research.

### TD-6: Broad `sqlite3.Error` Catch

**Decision:** Catch `sqlite3.Error` (base class) rather than specific subclasses.

**Rationale:** `sqlite3.OperationalError`, `sqlite3.DatabaseError`, `sqlite3.InterfaceError` all indicate DB unavailability. Catching the base class covers corruption, locking, and connection errors uniformly.

**Trade-off:** May catch programming errors (e.g., `sqlite3.ProgrammingError` from bad SQL). Acceptable — the fallback behavior is safe and the error is logged.

---

## Risks

### Risk 1: Stale `.meta.json` State

**Severity:** Medium
**Description:** In degraded mode, `.meta.json` may not reflect the latest DB state (e.g., a `transition_phase` wrote to DB but `.meta.json` has no `workflow_phase` field).
**Mitigation:** Acknowledged in spec R2. The DB is unavailable anyway, so `.meta.json` is the best available source. NFR-6 designates `.meta.json` as authoritative fallback. Feature 011 reconciliation resolves divergence when DB recovers.

### Risk 2: Health Probe False Positive

**Severity:** Low
**Description:** `SELECT 1` succeeds but subsequent complex queries fail (e.g., table corruption, disk full during write).
**Mitigation:** Defense-in-depth — R1/R2 catch handlers serve as secondary defense. The probe catches the common cases (locked, closed, permission denied); the try/except catches the rest.

### Risk 3: `_conn` Private Attribute Access

**Severity:** Low
**Description:** Accessing `EntityDatabase._conn` breaks encapsulation. Future `EntityDatabase` changes could break the probe.
**Mitigation:** Both classes are in the same package. The constraint explicitly prohibits modifying `EntityDatabase`, so private access is the only option. A comment documents the dependency.

### Risk 4: `.meta.json` Write Concurrency

**Severity:** Low
**Description:** Multiple agent sessions could write `.meta.json` simultaneously in degraded mode.
**Mitigation:** MCP server is stdio transport (one instance per agent session). Concurrent writes are unlikely. Atomic write (`os.replace`) ensures no partial writes. Last-write-wins is acceptable per spec.

### Risk 5: PRAGMA busy_timeout Interaction

**Severity:** Low
**Description:** `EntityDatabase` sets `PRAGMA busy_timeout=5000`. If the DB is locked, `SELECT 1` may block for up to 5 seconds before failing. This violates NFR-1 (`<5ms` single-operation target).
**Mitigation:** This is a worst-case scenario. In practice, locked DBs are rare in single-user CLI tools (MCP stdio = one session). The 5s delay only occurs on the first call to a locked DB — subsequent calls within the same method are skipped via the `db_available` flag. **NFR-1 exception:** The `<5ms` target applies to fallback path execution after probe completes, not to the probe itself when DB is contended. Once probe returns `False`, all fallback operations are sub-millisecond filesystem reads.

---

## Interfaces

### I1: `_check_db_health() -> bool`

```python
def _check_db_health(self) -> bool:
    """Lightweight DB availability check. Returns False if DB is unusable."""
    if self.db._conn is None:
        return False
    try:
        self.db._conn.execute("SELECT 1")
        return True
    except sqlite3.Error:
        return False
```

### I2: `_read_state_from_meta_json(feature_type_id: str) -> FeatureWorkflowState | None`

```python
def _read_state_from_meta_json(
    self, feature_type_id: str
) -> FeatureWorkflowState | None:
    """Pure-filesystem state reader. No DB calls."""
    slug = self._extract_slug(feature_type_id)
    meta_path = os.path.join(self.artifacts_root, "features", slug, ".meta.json")
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return self._derive_state_from_meta(meta, feature_type_id, source="meta_json_fallback")
```

### I3: `_derive_state_from_meta(meta: dict, feature_type_id: str, source: str) -> FeatureWorkflowState | None`

```python
def _derive_state_from_meta(
    self, meta: dict, feature_type_id: str, source: str = "meta_json"
) -> FeatureWorkflowState | None:
    """Shared phase derivation from .meta.json dict. Used by both hydration paths."""
    status = meta.get("status")
    mode = meta.get("mode")
    last_completed = meta.get("lastCompletedPhase")

    if status == "active":
        if last_completed is not None:
            try:
                next_phase = self._next_phase_value(last_completed)
            except ValueError:
                return None
            workflow_phase = next_phase if next_phase is not None else last_completed
        else:
            workflow_phase = PHASE_SEQUENCE[0].value
        completed_phases = self._derive_completed_phases(last_completed)
    elif status == "completed":
        workflow_phase = "finish"
        last_completed = last_completed or "finish"
        try:
            completed_phases = self._derive_completed_phases(last_completed)
        except ValueError:
            return None
    else:
        workflow_phase = None
        last_completed = None
        completed_phases = ()

    return FeatureWorkflowState(
        feature_type_id=feature_type_id,
        current_phase=workflow_phase,
        last_completed_phase=last_completed,
        completed_phases=completed_phases,
        mode=mode,
        source=source,
    )
```

### I4: `_write_meta_json_fallback(feature_type_id: str, phase: str) -> FeatureWorkflowState`

```python
def _write_meta_json_fallback(
    self, feature_type_id: str, phase: str, state: FeatureWorkflowState
) -> FeatureWorkflowState:
    """Write complete_phase state to .meta.json when DB is unavailable."""
    slug = self._extract_slug(feature_type_id)
    meta_path = os.path.join(self.artifacts_root, "features", slug, ".meta.json")

    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        raise ValueError(
            f"Cannot write fallback: .meta.json unreadable at {meta_path}: {exc}"
        ) from exc

    # Update fields (only those that already exist in .meta.json schema)
    meta["lastCompletedPhase"] = phase
    phases = meta.setdefault("phases", {})
    phase_obj = phases.setdefault(phase, {})
    if "started" not in phase_obj:
        phase_obj["started"] = _iso_now()
    phase_obj["completed"] = _iso_now()

    next_phase = self._next_phase_value(phase)
    if next_phase is None:
        meta["status"] = "completed"

    # Atomic write
    target_dir = os.path.dirname(os.path.abspath(meta_path))
    tmp_path = None
    try:
        fd = tempfile.NamedTemporaryFile(
            mode="w", dir=target_dir, delete=False, suffix=".tmp", encoding="utf-8"
        )
        tmp_path = fd.name
        json.dump(meta, fd, indent=2)
        fd.write("\n")
        fd.close()
        fd = None
        os.replace(tmp_path, meta_path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return FeatureWorkflowState(
        feature_type_id=feature_type_id,
        current_phase=next_phase if next_phase is not None else phase,
        last_completed_phase=phase,
        completed_phases=self._derive_completed_phases(phase),
        mode=state.mode,
        source="meta_json_fallback",
    )
```

### I5: `_scan_features_filesystem() -> list[FeatureWorkflowState]`

```python
def _scan_features_filesystem(self) -> list[FeatureWorkflowState]:
    """Scan features directory for .meta.json files. Used when DB is unavailable for list ops."""
    import glob as glob_mod
    pattern = os.path.join(self.artifacts_root, "features", "*", ".meta.json")
    results: list[FeatureWorkflowState] = []
    for meta_path in glob_mod.glob(pattern):
        feature_dir = os.path.basename(os.path.dirname(meta_path))
        feature_type_id = f"feature:{feature_dir}"
        state = self._read_state_from_meta_json(feature_type_id)
        if state is not None:
            results.append(state)
    return results
```

### I6: `TransitionResponse` Dataclass

```python
@dataclass(frozen=True)
class TransitionResponse:
    """Wraps transition_phase results with degradation signal."""
    results: tuple[TransitionResult, ...]
    degraded: bool
```

### I7: Updated `get_state()` Signature (Unchanged)

```python
def get_state(self, feature_type_id: str) -> FeatureWorkflowState | None:
    """Read feature workflow state. Falls back to .meta.json if DB unavailable."""
    db_available = self._check_db_health()
    if not db_available:
        print(f"[degraded] get_state({feature_type_id}): DB unavailable, "
              "falling back to .meta.json", file=sys.stderr)
        return self._read_state_from_meta_json(feature_type_id)
    try:
        row = self.db.get_workflow_phase(feature_type_id)
        if row is not None:
            return self._row_to_state(row)
        return self._hydrate_from_meta_json(feature_type_id)
    except sqlite3.Error as exc:
        print(f"[degraded] get_state({feature_type_id}): {exc}, "
              "falling back to .meta.json", file=sys.stderr)
        return self._read_state_from_meta_json(feature_type_id)
```

### I8: Updated `transition_phase()` Return Type

```python
def transition_phase(
    self, feature_type_id: str, target_phase: str, yolo_active: bool = False
) -> TransitionResponse:
    """Validate and enter a target phase. Always returns TransitionResponse."""
```

**Note on return type:** The return type changes from `list[TransitionResult]` to `TransitionResponse`. Both normal and degraded paths return `TransitionResponse`. Normal: `TransitionResponse(results=tuple(results), degraded=False)`. Degraded: `TransitionResponse(results=tuple(results), degraded=True)`. The MCP handler always receives the same type — no branching needed.

### I9: `_make_error()` Helper

```python
def _make_error(error_type: str, message: str, recovery_hint: str) -> str:
    """Create structured JSON error response for MCP tools."""
    return json.dumps({
        "error": True,
        "error_type": error_type,
        "message": message,
        "recovery_hint": recovery_hint,
    })
```

### I10: Updated `_serialize_state()` with Degradation

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
        "degraded": state.source == "meta_json_fallback",
    }
```

### I11: `_iso_now()` Helper

```python
def _iso_now() -> str:
    """Return current time as ISO 8601 string with local timezone offset.
    Matches existing .meta.json convention (e.g., '2026-03-06T18:30:00+08:00')."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).astimezone().isoformat()
```

### I12: Full `transition_phase()` with Degraded Path

```python
def transition_phase(
    self, feature_type_id: str, target_phase: str, yolo_active: bool = False
) -> TransitionResponse:
    """Validate and enter a target phase. Always returns TransitionResponse."""
    db_available = self._check_db_health()

    # Step 1: Get current state (uses fallback if DB unavailable)
    state = self.get_state(feature_type_id)
    if state is None:
        raise ValueError(f"Feature not found: {feature_type_id}")

    degraded = not db_available or state.source == "meta_json_fallback"

    # Step 2: Evaluate gates (pure logic — no DB dependency)
    # Gate evaluation works identically on both DB and meta_json_fallback state.
    # It reads FeatureWorkflowState fields + filesystem artifacts only.
    results = self._evaluate_gates(state, target_phase, yolo_active)

    # Step 3: Determine if transition is allowed
    all_passed = all(r.passed for r in results)

    # Step 4: If allowed AND DB available, write transition to DB
    if all_passed and db_available:
        try:
            self.db.set_workflow_phase(feature_type_id, target_phase)
        except sqlite3.Error as exc:
            # Secondary defense: DB write failed after probe passed
            print(f"[degraded] transition_phase: DB write failed: {exc}",
                  file=sys.stderr)
            degraded = True
            # No .meta.json write for transition_phase (per spec R2).
            # transition_phase records gate results, not state changes.
            # State is advanced by complete_phase later.

    # Step 5: If allowed but DB unavailable, skip DB write (spec R2)
    # Gate results are still valid — they don't depend on DB writes.
    # The transition is "logically valid" even without persistence.

    return TransitionResponse(
        results=tuple(results),
        degraded=degraded,
    )
```

### I13: Full `complete_phase()` with Degraded Path

```python
def complete_phase(
    self, feature_type_id: str, phase: str
) -> FeatureWorkflowState:
    """Mark a phase as completed. Falls back to .meta.json write if DB unavailable."""
    db_available = self._check_db_health()

    # Step 1: Get current state (uses fallback if DB unavailable)
    state = self.get_state(feature_type_id)
    if state is None:
        raise ValueError(f"Feature not found: {feature_type_id}")

    # Step 2: Validate phase completion is allowed (pure logic)
    # Full validation executes normally on both DB and meta_json_fallback state.
    # Only the final write triggers fallback behavior.
    self._validate_complete_phase(state, phase)

    # Step 3: Attempt DB write
    if db_available:
        try:
            self.db.complete_workflow_phase(feature_type_id, phase)
            # Read back updated state from DB
            row = self.db.get_workflow_phase(feature_type_id)
            if row is not None:
                return self._row_to_state(row)
            # DB write succeeded but read-back failed — fall through to meta.json
        except sqlite3.Error as exc:
            # Secondary defense: DB write failed after probe passed
            print(f"[degraded] complete_phase: DB write failed: {exc}",
                  file=sys.stderr)

    # Step 4: Fallback — write to .meta.json
    print(f"[degraded] complete_phase({feature_type_id}, {phase}): "
          "writing to .meta.json", file=sys.stderr)
    return self._write_meta_json_fallback(feature_type_id, phase, state)
```

### I14: MCP Handler `_process_transition_phase` (Updated)

```python
async def _process_transition_phase(
    feature: str, target_phase: str, yolo: bool = False
) -> str:
    """MCP handler for transition_phase. Always receives TransitionResponse."""
    try:
        response = engine.transition_phase(feature, target_phase, yolo)
    except ValueError as exc:
        if "not found" in str(exc).lower():
            return _make_error("feature_not_found", str(exc),
                             "Verify feature_type_id exists")
        return _make_error("invalid_transition", str(exc),
                         "Check phase name and current state")
    except sqlite3.Error as exc:
        return _make_error("db_unavailable", str(exc),
                         "Check DB file permissions and integrity")
    except Exception as exc:
        return _make_error("internal", str(exc), "Check server logs")

    # TransitionResponse always has .results and .degraded
    transitioned = all(r.passed for r in response.results)
    result = {
        "transitioned": transitioned,
        "results": [_serialize_result(r) for r in response.results],
        "degraded": response.degraded,
    }
    return json.dumps(result)
```

### I15: Full `list_by_phase()` with Degraded Path

```python
def list_by_phase(
    self, phase: str, entity_type: str = "feature"
) -> list[FeatureWorkflowState]:
    """List features in a given workflow phase. Falls back to filesystem scan."""
    db_available = self._check_db_health()

    if db_available:
        try:
            rows = self.db.list_by_workflow_phase(phase, entity_type)
            return [self._row_to_state(r) for r in rows]
        except sqlite3.Error as exc:
            print(f"[degraded] list_by_phase: {exc}", file=sys.stderr)

    # Fallback: scan filesystem, filter by current_phase
    all_states = self._scan_features_filesystem()
    return [s for s in all_states if s.current_phase == phase]
```

### I16: Full `list_by_status()` with Degraded Path

```python
def list_by_status(
    self, status: str, entity_type: str = "feature"
) -> list[FeatureWorkflowState]:
    """List features by status. Falls back to filesystem scan filtered by .meta.json status."""
    db_available = self._check_db_health()

    if db_available:
        try:
            rows = self.db.list_by_status(status, entity_type)
            return [self._row_to_state(r) for r in rows]
        except sqlite3.Error as exc:
            print(f"[degraded] list_by_status: {exc}", file=sys.stderr)

    # Fallback: scan filesystem, filter by .meta.json status field
    # Cannot use _scan_features_filesystem() because FeatureWorkflowState
    # has no 'status' field. Must filter at the .meta.json level.
    return self._scan_features_by_status(status)
```

### I17: `_scan_features_by_status(status: str) -> list[FeatureWorkflowState]`

```python
def _scan_features_by_status(self, status: str) -> list[FeatureWorkflowState]:
    """Scan features directory, filtering by .meta.json status field."""
    import glob as glob_mod
    pattern = os.path.join(self.artifacts_root, "features", "*", ".meta.json")
    results: list[FeatureWorkflowState] = []
    for meta_path in glob_mod.glob(pattern):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if meta.get("status") != status:
            continue
        feature_dir = os.path.basename(os.path.dirname(meta_path))
        feature_type_id = f"feature:{feature_dir}"
        state = self._derive_state_from_meta(
            meta, feature_type_id, source="meta_json_fallback"
        )
        if state is not None:
            results.append(state)
    return results
```

---

## Dependency Graph

```
C1: _check_db_health
  └── used by: all public methods (get_state, transition_phase, complete_phase,
      validate_prerequisites, list_by_phase, list_by_status)

C2: _read_state_from_meta_json
  ├── depends on: C3 (_derive_state_from_meta via TD-3)
  └── used by: get_state fallback, C4 scanner

C3: _derive_state_from_meta (extracted from _hydrate_from_meta_json)
  └── used by: C2, C8, _hydrate_from_meta_json (refactored)

C4: _write_meta_json_fallback
  └── used by: complete_phase write fallback

C5: TransitionResponse
  └── used by: transition_phase (always returned, normal + degraded)

C6: _scan_features_filesystem
  ├── depends on: C2 (_read_state_from_meta_json)
  └── used by: list_by_phase fallback

C7: _make_error
  └── used by: all _process_* functions in MCP server

C8: _scan_features_by_status
  ├── depends on: C3 (_derive_state_from_meta)
  └── used by: list_by_status fallback

C9: _serialize_state update (degraded field)
  └── used by: all MCP responses involving FeatureWorkflowState
```

## Change Impact Summary

| File | Change Type | Scope |
|------|------------|-------|
| `workflow_engine/models.py` | Add `TransitionResponse` dataclass, update `source` comment | Small |
| `workflow_engine/engine.py` | Add C1-C4, C6, C8 methods; wrap public methods with fallback; extract C3; add imports (`sqlite3`, `tempfile`, `glob`) | Large (primary change) |
| `mcp/workflow_state_server.py` | Add C7, C9; update `_process_*` for structured errors and degradation; add `import sqlite3` | Medium |
| `workflow_engine/test_engine.py` | New tests for all degradation paths | Medium |
| `mcp/test_workflow_state_server.py` | Update error-path assertions, add degradation tests | Medium |
