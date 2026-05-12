# Feature 113 — Feature 112 QA-Gate Followups: Design

## Status
- Phase: design
- Mode: standard
- Spec: `docs/features/113-feature-112-qa-followups/spec.md`

## Prior Art Research

Findings from codebase-explorer (2026-05-12). Internet-researcher skipped — no external prior art for internal MCP workspace-identity refactoring.

| Pattern | Established at | Reuse in feature 113 |
|---------|----------------|----------------------|
| `workspace_uuid: str \| None = None` keyword-only kwarg | `engine.py:84,120` (`transition_phase`, `complete_phase`) | Apply to `update_workflow_phase` (FR-4.1) using `_UNSET` sentinel pattern of database.py:4866-4944 |
| `_workspace_uuid or None` MCP-boundary normalization | `workflow_state_server.py:99-104` (idiom comment) | Pin lines 657 and 1280 (FR-6) |
| Conditional kwarg pattern (`project_id=project_id if workspace_uuid is None else None`) | `entity_status.py:175, 316` | Apply to 4 sites: lines 47, 72, 189, 320 (FR-10) |
| Narrow `except sqlite3.OperationalError` with stderr warning, re-raise non-DB | `engine.py:105-113, 178-186`; `server_helpers.py:279-282` | Apply to `_filter_states_by_workspace` and `parent_resolution` (FR-7, FR-8) |
| `monkeypatch.setattr` mock + `capsys.readouterr()` stderr capture | `test_engine.py:2900-2948, 4014-4078` | Use for FR-7.2, FR-8.2, FR-11.5 boundary tests |
| Pre/post `db.get_*` direct SELECT mutation pin | `test_frontmatter_sync.py:1768-1795` | Use for FR-4.3 column-immutability test |
| Module-level `frozenset` enum + `ValueError`-raising validator | `semantic_memory/__init__.py:8-10`, `semantic_memory/writer.py:27-44` | Model for `qa_gate/emitter.py::emit_qa_gate` (FR-1) |
| `bootstrap_test_workspace()` / `get_test_workspace_uuid()` | `test_helpers.py:11-52` | Use for multi-workspace tests (FR-4.3, FR-5.2, FR-11.5 scope-scan) |
| `read+write` MCP handler classification | `docs/features/112-workspace-identity-cleanup/handler-audit.md:1-39` | Authority for FR-11 scope (reconcile_apply #8, reconcile_frontmatter #9, reconcile_status #10) |
| `warnings.catch_warnings()` / `simplefilter('error', DeprecationWarning)` | NONE in codebase | FR-10.2 introduces this pattern (no prior art) |

**Notable absences:** No prior `qa_gate/` subpackage exists — FR-1 creates new ground modeled on `semantic_memory/`. No existing test uses `simplefilter('error', DeprecationWarning)` — FR-10.2 is first.

## Architecture Overview

Feature 113 is **surgical**: it threads existing patterns through gaps, narrows over-broad exception handlers, and pins behaviors with mutation tests. No new architectural components, no schema migration, no public API breakage.

**Change shape by file count:**
- Source modifications: 7 files (`database.py`, `engine.py`, `entity_lifecycle.py`, `entity_status.py`, `workflow_state_server.py`, `server_helpers.py`, `entity_server.py`)
- Source additions: 2 new modules (`qa_gate/__init__.py`, `qa_gate/emitter.py`) + 1 new helper script (`bash-version-capture.sh`)
- Test modifications/additions: 5 test files (`test_database.py`, `test_engine.py`, `test_entity_lifecycle.py`, `test_workflow_state_server.py`, `test_server_helpers.py`) + 3 new test files (`test_emitter.py`, `test_reconciliation.py` extension, `test_frontmatter_sync.py` extension, `test_entity_status.py` extension)
- Total: ~150-250 LOC + ~16 new tests

**Single architectural axis:** the workspace_uuid identity thread. Feature 112 introduced the column and pass-through patterns; feature 113 closes the asymmetries (FR-4/5/11), removes the silent fallbacks (FR-3/7/8/9), and adds defensive coverage (FR-6/10).

## Components

### C1 — `qa_gate/` package (new)

**Files:**
- `plugins/pd/hooks/lib/qa_gate/__init__.py` — package marker + `STATUS_ENUM` export
- `plugins/pd/hooks/lib/qa_gate/emitter.py` — `emit_qa_gate(...)` function
- `plugins/pd/hooks/lib/qa_gate/test_emitter.py` — unit tests

**Responsibility:** Canonical `.qa-gate.json` schema + write path. Validates status enum, per-entry keys, head_sha idempotency. Replaces inline JSON construction in `/pd:finish-feature` Step 5b.

**Modeled on:** `semantic_memory/__init__.py` (frozenset enum + module-level validator).

**Consumers:** `/pd:finish-feature` command (now and future). One consumer today, designed for many.

### C2 — `bash-version-capture.sh` (new)

**File:** `plugins/pd/hooks/tests/bash-version-capture.sh`

**Responsibility:** Produce AC-12 evidence in exactly the 3-section format (host bash, /bin/bash, /bin/bash test-hooks.sh exit code). Called from `/pd:finish-feature` Step 5b.

**Exit semantics:** Exits 0 only when the test-hooks.sh invocation under /bin/bash exits 0; otherwise propagates the test-hooks.sh exit code.

### C3 — `update_workflow_phase` extension (modified)

**File:** `plugins/pd/hooks/lib/entity_registry/database.py:4866-4944`

**Change:** Add `workspace_uuid: str | None = None` to the signature using the existing `_UNSET` sentinel idiom. When non-None, the method:
1. SELECTs the existing `workspace_uuid` from `workflow_phases` WHERE `type_id = ?`
2. Raises `ValueError(f"workspace_uuid mismatch for {type_id}: stored={existing!r}, provided={workspace_uuid!r}")` on mismatch
3. Does NOT add `workspace_uuid` to the UPDATE SET clause (column is immutable post-Migration-11)

**Why mismatch-check rather than resolve-via-update_entity-style:** `workflow_phases` rows are keyed by `type_id` (the entity's). The workspace_uuid is fixed at row-creation by the autofill trigger `wp_autofill_workspace_uuid`. A mismatch indicates the caller has the wrong workspace context for the operation — silent acceptance would let cross-workspace writes proceed. The mismatch ValueError is the read-side workspace assertion.

### C4 — Engine + lifecycle forwarding (modified)

**Files:**
- `plugins/pd/hooks/lib/workflow_engine/engine.py:100-103, 166-170` — `WorkflowStateEngine.transition_phase` and `complete_phase` non-terminal paths add `workspace_uuid=workspace_uuid` to `db.update_workflow_phase` calls
- `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:193` — `transition_entity_phase` adds `workspace_uuid=workspace_uuid` to the kwargs dict consumed by `db.update_workflow_phase`

**Effect:** Once C3 lands, the mismatch check becomes load-bearing for every transition_phase and complete_phase call — preventing cross-workspace writes via misrouted type_ids.

**Test contract for FR-4.3 mismatch tests:** The engine.py `transition_phase` (line 105) and `complete_phase` (line 178) wrap `db.update_workflow_phase` calls in `except sqlite3.Error:`. FR-4.1's ValueError is NOT a sqlite3.Error subclass, so it WILL propagate. Tests MUST use the explicit shape `with pytest.raises(ValueError, match="workspace_uuid mismatch"):` to pin both the error TYPE and the message fragment. Relying on "test raises something" is insufficient — a future refactor that adds `except (sqlite3.Error, ValueError):` would silently invalidate the pin. Pre-implementation verification: temporarily widen the except to `(sqlite3.Error, ValueError)` and confirm the test fails BEFORE landing the FR-4 commit.

### C5 — workspace filter narrow-fail (modified)

**File:** `plugins/pd/mcp/workflow_state_server.py:1563-1665`

**Changes:**
- FR-3.0: Entry-point normalization `if project_id == "": project_id = None` at the top of `_resolve_list_handler_workspace_filter`
- FR-3.1: Retain `_db is None → return None`; add comment documenting it as intentional degraded mode
- FR-3.2: Replace silent `None` return on invalid hex with `raise ValueError(...)`; both `list_features_by_phase` (line 1619) and `list_features_by_status` (line 1643) wrap with `try/except ValueError` and return `_make_error(error_type="invalid_project_id", ...)`

### C6 — Narrow exception handlers (modified)

**Files:**
- `plugins/pd/mcp/workflow_state_server.py:1614-1615` — `_filter_states_by_workspace`: split into `except json.JSONDecodeError` (return as-is) + `except sqlite3.OperationalError` (return `_make_error`). RuntimeError + others propagate.
- `plugins/pd/hooks/lib/entity_registry/server_helpers.py:248-255` — Parent resolution: narrow bare-except to `except sqlite3.OperationalError`. Other exceptions propagate. Add stderr warning before falling through with `parent_uuid=None`.

### C7 — `_process_create_key_result` explicit check (modified)

**File:** `plugins/pd/mcp/entity_server.py:449-450`

**Change:** Add `if parent_entity is None: raise ValueError(f"Parent entity not found: {parent_type_id!r}")` after the `db.get_entity(parent_type_id)` call. Caught by existing `except Exception` decorator at entity_server.py:1129-1130 (returns error JSON to MCP caller).

### C8 — `entity_status.py` conditional-kwarg sweep (modified)

**File:** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`

**Change:** At lines 47, 72, 189, 320, change `project_id=project_id, workspace_uuid=workspace_uuid` → `project_id=project_id if workspace_uuid is None else None, workspace_uuid=workspace_uuid`. Pattern matches lines 175 and 316 (already correct).

**Effect:** Eliminates the post-FR-2 happy-path `DeprecationWarning` emitted by `_resolve_workspace_uuid_kwargs` (database.py:2813-2819) when both kwargs are non-None.

### C9 — Reconcile workspace_uuid threading (modified)

**Files:**
- `plugins/pd/hooks/lib/workflow_engine/reconciliation.py:756` — `apply_workflow_reconciliation` gains `workspace_uuid` kwarg; merges into the dict at lines 367-373 (NOT via `**kwargs, workspace_uuid=` syntax — avoids future duplicate-kwarg TypeError), and adds as separate kwarg at line 462 (single-kwarg call). See I9 for the exact shape.
- `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py:543` — `scan_all` gains `workspace_uuid` kwarg; forwards to `db.list_entities` at line 570 (workspace-scoped scan)
- `plugins/pd/mcp/workflow_state_server.py:1189, 1223, 1366` — `_process_reconcile_apply`, `_process_reconcile_frontmatter`, `_process_reconcile_status` accept and forward `workspace_uuid`
- `plugins/pd/mcp/workflow_state_server.py:1678, 1694, 1705` — Async MCP handlers pass `workspace_uuid=_workspace_uuid or None`

**Explicit non-action:** `check_workflow_drift` at reconciliation.py:634 is read-only — no threading needed (verified during phase-review iter 2).

## Technical Decisions

### TD-1 — `update_workflow_phase` workspace_uuid is a read-side assertion, not a write

**Decision:** Mismatch check on read; column never appears in UPDATE SET.

**Rationale:** Migration 11's `wp_autofill_workspace_uuid` trigger populates the column at INSERT time from `entities.workspace_uuid`. Once set, the value is immutable — changing it would mean an entity moved between workspaces, which is not a supported operation. The kwarg's purpose is to assert "caller is operating on the workspace it thinks it is" — a defensive check against type_id collision across workspaces.

**Alternative considered:** Resolve workspace via the kwarg (like `update_entity` does). Rejected because workflow_phases is keyed by type_id directly, not by a resolution that can differ by workspace.

### TD-2 — Mismatch ValueError shape

**Decision:** `raise ValueError(f"workspace_uuid mismatch for {type_id}: stored={existing!r}, provided={workspace_uuid!r}")`

**Rationale:**
- Includes both stored and provided UUIDs in the message for debuggability
- Uses `!r` for explicit string-vs-None vs empty-string distinction
- Caught by existing `_catch_value_error` decorator at MCP boundaries
- Does NOT include type_id-implied workspace_uuid (no defense-in-depth lookup) — the stored value IS the type_id-implied workspace_uuid

### TD-3 — `qa_gate/emitter.py` enum representation

**Decision:** Module-level `STATUS_ENUM = frozenset({"passed", "deferred", "n_a", "conditional_skipped"})`. Validator: `if status not in STATUS_ENUM: raise ValueError(...)`.

**Rationale:** Direct copy of `semantic_memory/__init__.py:8-10` pattern. frozenset is immutable, set-membership is O(1), and the module-level location makes the enum the canonical source for both the emitter and any future validator (e.g., a JSON schema generator).

### TD-4 — Reconcile workspace_uuid kwarg shape

**Decision:** Add `workspace_uuid` as a separate kwarg (not folded into the existing kwargs dict) at every signature extension.

**Rationale (per phase-reviewer iter 2 suggestion S2):** Separate kwarg matches FR-4.2's pattern at engine.py:103. Grep-ability: `grep -n 'workspace_uuid=' reconciliation.py` returns each forwarding site. Folded-into-dict would obscure the threading.

**Applies to:**
- `apply_workflow_reconciliation(..., workspace_uuid: str | None = None)`
- `scan_all(db, artifacts_root, workspace_uuid: str | None = None)`
- `_process_reconcile_apply(..., workspace_uuid: str | None = None)`
- `_process_reconcile_frontmatter(..., workspace_uuid: str | None = None)`
- `_process_reconcile_status(..., workspace_uuid: str | None = None)`

### TD-5 — `scan_all` workspace-scoping via list_entities

**Decision:** Forward `workspace_uuid` to `db.list_entities(entity_type="feature", workspace_uuid=workspace_uuid)` at frontmatter_sync.py:570. Do NOT thread to `detect_drift` at line 581 (read-only function operating on a specific path; workspace is already implied by the path lookup).

**Rationale:** `scan_all`'s only DB interaction is the list_entities filter. Scoping there limits which entities the drift scan considers, which is the entire effective workspace-scoping the function needs.

### TD-6 — `_make_error` shape for FR-3.2

**Decision:** Caller wrappers in `list_features_by_phase` and `list_features_by_status` return:
```json
{
  "error": true,
  "error_type": "invalid_project_id",
  "message": "{str(exc)}",
  "recovery_hint": "Pass project_id='*' for cross-workspace OR omit for current-workspace default"
}
```

**Rationale:** Matches existing `_make_error` pattern at workflow_state_server.py:485. The recovery_hint guides the caller toward valid project_id values without exposing internal hex format requirements.

### TD-7 — Mutation-pin test patterns by category

**Decision (per codebase-explorer findings):**
- **Pre/post DB SELECT** for column-immutability pins (FR-4.3 `test_update_workflow_phase_does_not_mutate_workspace_uuid_column`) — pattern from `test_frontmatter_sync.py:1768-1795`
- **`monkeypatch.setattr` tracking wrapper** for kwarg-forwarding pins (FR-4.3 mismatch tests, FR-5.2, FR-11.5 boundary tests) — pattern from `test_engine.py:4014-4078`
- **`capsys.readouterr()` stderr capture** for warning-text pins (FR-8.2) — pattern from `test_engine.py:2900-2948`
- **Multi-workspace bootstrap via `bootstrap_test_workspace()`** for cross-workspace isolation tests (FR-4.3 mismatch, FR-5.2, FR-11.5 scope-scan) — pattern from `test_helpers.py:11-52`
- **`warnings.catch_warnings()` + `simplefilter('error', DeprecationWarning)`** for FR-10.2 — new pattern (no codebase prior art)

### TD-8 — qa_gate `.qa-gate.json` canonical schema

**Decision:** The canonical schema differs from both existing samples (feature 096, feature 112). FR-1.2 establishes:
```json
{
  "feature": "{id}-{slug}",
  "head_sha": "{git rev-parse HEAD output}",
  "gate_run_at": "{ISO 8601 UTC timestamp}",
  "ac_results": [
    {
      "id": "AC-N",
      "status": "passed" | "deferred" | "n_a" | "conditional_skipped",
      "evidence": "<free-text test path or grep result, ≤500 chars>",
      "condition": "<non-empty when status == 'conditional_skipped', else ''>",
      "backlog_ref": "<5-digit backlog ID> | null"
    },
    ...
  ],
  "decision": "approved" | "deferred",
  "reviewers": [<list of reviewer agent names>]
}
```

**Rationale:** Replaces freeform schemas in features 096 and 112 with a canonical per-AC array. The flat array makes it greppable, diffable, and consumable by future tools (e.g., AC coverage dashboard).

**Migration of existing files:** NOT in scope for FR-1. Existing feature 096/112 `.qa-gate.json` files retain their legacy shape (informational only). Feature 113 and onward use the canonical schema.

### TD-9 — `bash-version-capture.sh` portability

**Decision:** Script uses POSIX `[[:space:]]` patterns, `${!varname:-default}` indirect expansion, no eval. Targets macOS bash 3.2 (per CLAUDE.md "Bash 3.2 / macOS BSD portability").

**Rationale:** AC-12 evidence depends on the script working under both host bash (which may be 5.x via Homebrew) and `/bin/bash` (which is 3.2 on macOS). The portability constraints are inherited from the rest of the hooks codebase.

## Interfaces

### I1 — `qa_gate.emitter.emit_qa_gate`

```python
# plugins/pd/hooks/lib/qa_gate/emitter.py

from __future__ import annotations
import json
import os
import subprocess
from typing import TypedDict

STATUS_ENUM = frozenset({"passed", "deferred", "n_a", "conditional_skipped"})


class AcResult(TypedDict, total=False):
    id: str            # required, e.g., "AC-1"
    status: str        # required, must be in STATUS_ENUM
    evidence: str      # required, ≤500 chars
    condition: str     # default ""
    backlog_ref: str | None  # default None


def emit_qa_gate(
    *,
    feature: str,
    feature_dir: str,
    ac_results: list[AcResult],
    decision: str,
    reviewers: list[str],
    head_sha: str | None = None,
) -> str:
    """Validate and write .qa-gate.json. Returns the absolute path written.

    Raises
    ------
    ValueError
        - status outside STATUS_ENUM for any entry
        - missing required key (id, status, evidence)
        - evidence > 500 chars
        - status == "conditional_skipped" but condition is empty

    Idempotency
    -----------
    If `head_sha` is None, computed from `git rev-parse HEAD`. If the file
    already exists with the same head_sha, this is a no-op (returns existing
    path without rewriting).
    """
```

### I2 — `update_workflow_phase` extended signature

```python
# plugins/pd/hooks/lib/entity_registry/database.py

class EntityDatabase:
    def update_workflow_phase(
        self,
        type_id: str,
        *,
        kanban_column: str | object = _UNSET,
        workflow_phase: str | object = _UNSET,
        last_completed_phase: str | object = _UNSET,
        mode: str | object = _UNSET,
        backward_transition_reason: str | None | object = _UNSET,
        workspace_uuid: str | None = None,  # NEW (FR-4.1)
    ) -> None:
        """Update workflow_phases row by type_id.

        Args (workspace_uuid):
            Optional read-side workspace assertion. When non-None, SELECTs the
            stored workspace_uuid and raises ValueError on mismatch BEFORE the
            UPDATE proceeds. Does NOT appear in the UPDATE SET clause (column
            is immutable post-Migration-11; autofill at INSERT only).

        Raises:
            ValueError: workspace_uuid != stored value for this type_id.
        """
```

### I3 — Engine method signatures (unchanged, but with new forwarding)

```python
# plugins/pd/hooks/lib/workflow_engine/engine.py — call sites only

# transition_phase, line ~100-103
self.db.update_workflow_phase(
    feature_type_id,
    workflow_phase=target_phase,
    workspace_uuid=workspace_uuid,  # NEW (FR-4.2)
)

# complete_phase, line ~166-170 (non-terminal)
self.db.update_workflow_phase(
    feature_type_id,
    last_completed_phase=phase,
    workflow_phase=next_phase,
    workspace_uuid=workspace_uuid,  # NEW (FR-4.2)
)
```

### I4 — `transition_entity_phase` kwarg-dict extension

```python
# plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:185-193

update_kwargs: dict = {
    "workflow_phase": target_phase,
    "kanban_column": kanban_column,
    "workspace_uuid": workspace_uuid,  # NEW (FR-5.1) — unconditional, None is no-op per FR-4.1
}
if is_forward:
    update_kwargs["last_completed_phase"] = current_phase

db.update_workflow_phase(type_id, **update_kwargs)
```

**Locked at iter 2:** Unconditional pass. FR-4.1 makes None a no-op (the mismatch check is skipped when workspace_uuid is None), so unconditional inclusion is functionally identical to conditional + simpler. Matches spec FR-5.1 verbatim ("forwards the kwarg to BOTH").

### I5 — `_resolve_list_handler_workspace_filter` extension

```python
# plugins/pd/mcp/workflow_state_server.py:1563-1594

def _resolve_list_handler_workspace_filter(project_id: str | None) -> str | None:
    """..."""

    # FR-3.0: empty string → None at entry (treated as default-workspace)
    if project_id == "":
        project_id = None

    if project_id == "*":
        return None  # cross-workspace

    if _db is None:
        # Degraded-mode: no DB → cross-workspace fallback is intentional,
        # surfaced via _check_db_available upstream
        return None

    # ... legacy hex resolution ...

    # FR-3.2: invalid hex → raise (was: return None)
    raise ValueError(f"No workspace found for project_id={project_id!r}")
```

```python
# Caller wrappers (workflow_state_server.py:1619 and :1643)

async def list_features_by_phase(phase: str, project_id: str | None = None) -> str:
    try:
        ws_filter = _resolve_list_handler_workspace_filter(project_id)
    except ValueError as exc:
        return _make_error(
            error_type="invalid_project_id",
            message=str(exc),
            recovery_hint="Pass project_id='*' for cross-workspace OR omit for current-workspace default",
        )
    # ... rest unchanged ...
```

Same shape for `list_features_by_status`.

### I6 — Narrow exception handlers

```python
# plugins/pd/mcp/workflow_state_server.py:1614-1615 (FR-7)
# OLD:
#   except (json.JSONDecodeError, Exception):
#       return results_json
# NEW:
except json.JSONDecodeError:
    return results_json  # malformed JSON from engine — return as-is
except sqlite3.OperationalError as exc:
    return _make_error("db_unavailable", str(exc),
                       "Database temporarily unavailable; retry shortly")
# Other exceptions PROPAGATE (no except Exception clause)
```

```python
# plugins/pd/hooks/lib/entity_registry/server_helpers.py:248-255 (FR-8)
# OLD:
#   except Exception:
#       pass  # parent_uuid stays None
# NEW:
except sqlite3.OperationalError as exc:
    print(
        f"server_helpers: parent resolution failed under DB error: {exc} "
        f"— registering as orphan",
        file=sys.stderr,
    )
    # Fall through with parent_uuid=None
# Other exceptions PROPAGATE
```

### I7 — `_process_create_key_result` missing-parent check

```python
# plugins/pd/mcp/entity_server.py:449-450 (FR-9)
parent_entity = db.get_entity(parent_type_id)
if parent_entity is None:
    raise ValueError(f"Parent entity not found: {parent_type_id!r}")
parent_uuid = parent_entity["uuid"]
```

### I8 — `entity_status.py` conditional-kwarg sweep (4 sites)

```python
# Pattern applied at lines 47, 72, 189, 320 (FR-10.1):
# OLD:
#   db.update_entity(type_id, status=..., project_id=project_id, workspace_uuid=workspace_uuid)
# NEW:
db.update_entity(
    type_id,
    status=...,
    project_id=project_id if workspace_uuid is None else None,
    workspace_uuid=workspace_uuid,
)
```

### I9 — Reconcile workspace_uuid threading

```python
# plugins/pd/hooks/lib/workflow_engine/reconciliation.py:756 (FR-11.1)
def apply_workflow_reconciliation(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None = None,
    dry_run: bool = False,
    *,
    workspace_uuid: str | None = None,  # NEW
) -> ReconciliationResult:
    ...
    # At reconciliation.py:367-374 — merge into the kwargs dict before unpacking.
    # Avoids the `**kwargs, workspace_uuid=...` syntax which would TypeError if
    # a future maintainer adds 'workspace_uuid' to the dict literal at lines 367-373.
    kwargs = dict(
        workflow_phase=meta["workflow_phase"],
        last_completed_phase=meta["last_completed_phase"],
        mode=meta["mode"],
    )
    if expected_kanban is not None:
        kwargs["kanban_column"] = expected_kanban
    kwargs["workspace_uuid"] = workspace_uuid  # NEW (FR-11.1) — None is no-op per FR-4.1
    db.update_workflow_phase(feature_type_id, **kwargs)

    # At reconciliation.py:462 — single-kwarg call, no dict; safe to add directly
    db.update_workflow_phase(
        feature_type_id,
        kanban_column=expected_kanban,
        workspace_uuid=workspace_uuid,
    )
```

```python
# plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py:543 (FR-11.2)
def scan_all(
    db: EntityDatabase,
    artifacts_root: str,
    *,
    workspace_uuid: str | None = None,  # NEW
) -> list[DriftReport]:
    ...
    features = db.list_entities(entity_type="feature", workspace_uuid=workspace_uuid)
    ...
```

```python
# plugins/pd/mcp/workflow_state_server.py:1189, 1223, 1366 (FR-11.3 + 11.4)
def _process_reconcile_apply(..., workspace_uuid: str | None = None) -> str:
    result = apply_workflow_reconciliation(
        engine, db, artifacts_root, feature_type_id, dry_run,
        workspace_uuid=workspace_uuid,
    )
    ...

def _process_reconcile_frontmatter(..., workspace_uuid: str | None = None) -> str:
    if feature_type_id is None:
        reports = scan_all(db, artifacts_root, workspace_uuid=workspace_uuid)
    ...

def _process_reconcile_status(..., workspace_uuid: str | None = None) -> str:
    frontmatter_reports = scan_all(db, artifacts_root, workspace_uuid=workspace_uuid)
    ...
```

```python
# Async handlers — workflow_state_server.py:1678, 1694, 1705 (FR-11.4)
async def reconcile_apply(...) -> str:
    return _process_reconcile_apply(..., workspace_uuid=_workspace_uuid or None)

async def reconcile_frontmatter(...) -> str:
    return _process_reconcile_frontmatter(..., workspace_uuid=_workspace_uuid or None)

async def reconcile_status(...) -> str:
    return _process_reconcile_status(..., workspace_uuid=_workspace_uuid or None)
```

### I10 — `bash-version-capture.sh` contract

```bash
#!/usr/bin/env bash
# plugins/pd/hooks/tests/bash-version-capture.sh
#
# Produce AC-12 evidence in canonical 3-section format.
#
# Usage: bash plugins/pd/hooks/tests/bash-version-capture.sh > docs/features/{id}-{slug}/bash-version.log
# Exit code: 0 if /bin/bash test-hooks.sh exits 0; otherwise propagates that exit code.

# Intentional: no 'set -e' — emit each section even if a prior section command fails,
# so partial evidence is captured. Only the test-hooks.sh exit code (section 3) propagates.
set -u
# Section 1: host bash
echo "=== Host bash --version ==="
bash --version

# Section 2: /bin/bash
echo "=== /bin/bash --version ==="
/bin/bash --version

# Section 3: /bin/bash test-hooks.sh
TEST_OUTPUT=$(/bin/bash plugins/pd/hooks/tests/test-hooks.sh 2>&1)
RC=$?
echo "=== /bin/bash plugins/pd/hooks/tests/test-hooks.sh (exit=${RC}) ==="
echo "${TEST_OUTPUT}" | tail -20

exit ${RC}
```

## Risks

### R1 — `update_workflow_phase` mismatch ValueError breaks existing call sites

**Risk:** If any existing caller passes a stale `workspace_uuid` (e.g., from a misrouted CLI argument), the new mismatch check raises ValueError where the prior version silently succeeded.

**Mitigation:** Audit-grep at NFR-3 confirms zero current callers pass `workspace_uuid` to `update_workflow_phase`. The new behavior is activated only by FR-4.2/FR-5.1 forwarding (which are new) or future opt-in callers. No existing test fixture relies on the old (no-kwarg) behavior.

**Verification:** `grep -rn 'update_workflow_phase' plugins/pd/ --include='*.py' | grep -v test_` returns 12 sites; none currently pass workspace_uuid (verified at iter 3 of spec-review).

### R2 — FR-6 mutation pin may pass vacuously

**Risk:** If empty-string `workspace_uuid` flows through to `db.update_entity` and the FK constraint catches it (as expected), the mutation pin is real. But if upstream normalization re-coerces empty→None elsewhere (e.g., in `_resolve_workspace_uuid_kwargs`), the mutation tests would silently succeed when removing `or None`.

**Mitigation:** Per AC-6 fallback clause: implementation verifies the actual failure mode (FK or equivalent observable error) before merging; AC-6 text is updated in the same commit if the mode differs.

**Verification:** During implementation, manually test the mutation by removing `or None` at line 1280, running the test, and confirming a non-trivial assertion error fires.

### R3 — `scan_all` workspace-scoping changes drift-report set

**Risk:** Today `scan_all` returns drift reports for ALL features regardless of workspace. After FR-11.2, callers must pass `workspace_uuid` to get workspace-scoped reports — the default behavior change could surprise downstream consumers.

**Mitigation:** Default `workspace_uuid=None` retains existing cross-workspace behavior. Only FR-11.3 + FR-11.4 MCP handlers opt into scoping by passing `_workspace_uuid or None`. Non-MCP callers (if any) keep their current behavior unchanged.

**Verification:** `grep -rn 'scan_all' plugins/pd/` shows callers: `_process_reconcile_frontmatter` (line 1230), `_process_reconcile_status` (line 1381). Both are FR-11.3/11.4 targets. No external callers.

### R4 — `qa_gate/emitter.py` schema breaks if reused for older features

**Risk:** FR-1.2's canonical schema differs from feature 096 and feature 112's `.qa-gate.json` shapes. If someone re-emits an older feature's gate via the new emitter, the output structure changes (no backward read of old shape).

**Mitigation:** TD-8 explicitly scopes migration as out-of-scope. Older `.qa-gate.json` files are informational artifacts; their shape is frozen and the emitter does not attempt to migrate. AC-13 dogfoods only against feature 113's own gate.

### R5 — Per-method incremental rollout introduces transient inconsistency

**Risk:** Between commits in the NFR-5 sequence, the codebase has partial workspace_uuid threading. For example, after FR-4.1 lands but before FR-4.2, `update_workflow_phase` accepts workspace_uuid but no caller passes it. After FR-4.2 lands but before FR-5, engine.py passes it but entity_lifecycle.py doesn't.

**Mitigation:** Each FR ships with its own tests, and the regression baseline (NFR-2) is captured at the feature branch root. AC-12 verifies no test regresses pass→fail at any commit. The transient inconsistency is contained within the feature branch.

### R6 — DeprecationWarning suppression test (FR-10.2) introduces new pattern

**Risk:** No prior code uses `warnings.catch_warnings()` + `simplefilter('error', DeprecationWarning)`. The pattern could conflict with pytest's global warning filters or pytest plugins.

**Mitigation:** If the primary pattern fails, fall back to the `recwarn` pytest fixture:
```python
def test_sync_entity_statuses_no_deprecation_warning_on_happy_path(recwarn):
    sync_entity_statuses(...)
    deprecations = [w for w in recwarn if issubclass(w.category, DeprecationWarning)]
    assert deprecations == [], f"Unexpected DeprecationWarnings: {deprecations}"
```
The project pins pytest >=9.0.2,<10 (pyproject.toml:24); `pytest.warns(None)` was removed in pytest 8 and is NOT available. The `recwarn` fixture is the supported fallback. Verify locally before committing FR-10.2.

**Verification:** Run the new test in isolation: `pytest -k 'no_deprecation_warning' -W error::DeprecationWarning`.

### R7 — Test count drift (residual from spec iters)

**Risk:** Spec test counts (in AC summaries and FR bodies) may drift again during implementation if the test author splits or merges tests.

**Mitigation:** The Verification Plan Summary table is the single source of truth. Any test count divergence during implementation requires a spec patch in the same commit.

## Out of Scope

- Migration 12 (no schema change needed)
- Migration of older `.qa-gate.json` files to the canonical schema
- `_project_id` lazy global removal (#00389)
- FR-4 alias drop + 30-test migration (#00390)
- F6 uuid7 adoption (#00359 — gated on Python 3.14+)
- Documentation tier scaffolding (YOLO Skip remains the norm)

## Cross-References

- Spec: `docs/features/113-feature-112-qa-followups/spec.md`
- Migration 11 schema: `plugins/pd/hooks/lib/entity_registry/database.py:2041-2092`
- Handler audit classification: `docs/features/112-workspace-identity-cleanup/handler-audit.md`
- `_UNSET` sentinel idiom: `plugins/pd/hooks/lib/entity_registry/database.py:4866-4944`
- `_resolve_workspace_uuid_kwargs` DeprecationWarning source: `plugins/pd/hooks/lib/entity_registry/database.py:2813-2819`
- `semantic_memory` enum/validator prior art: `plugins/pd/hooks/lib/semantic_memory/__init__.py:8-10`, `writer.py:27-44`
- Multi-workspace test bootstrap: `plugins/pd/hooks/lib/entity_registry/test_helpers.py:11-52`
