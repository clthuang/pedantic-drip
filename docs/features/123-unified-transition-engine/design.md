# Design: Unified Transition Engine (feature 123)

Binding upstream: spec.md (FR123-1..6, SC1-6, hazard table) at 20d5a7b9. Every D-section pins a contract; code blocks are VERBATIM where marked.

## D1 — Router module: `plugins/pd/hooks/lib/workflow_engine/router.py` (OQ-1 RESOLVED)

New module in workflow_engine. Rationale (import-graph verified): the router composes the frozen engine (workflow_engine.engine), the 5D ordering rules (workflow_engine.entity_engine), templates (workflow_engine.templates), transition_gate, AND the lifecycle graphs — workflow_engine already imports entity_registry (engine.py:12, entity_engine.py:22-23); placing the router in entity_registry would invert that for the whole engine stack (today's only reverse edge is backfill.py:17's derive_kanban import, which 132 deletes — do not widen it).

Public surface:
- `MACHINE_REGISTRY: dict[str, Machine]` — kind → machine instance; keys exactly the 8 machine-bearing kinds (spec FR123-1 table). `bug` deliberately absent (status-only).
- `get_machine(kind) -> Machine` — raises `ValueError(f"no transition machine for kind: {kind}")` for bug/workspace/unknown (callers that today special-case bug keep doing so BEFORE routing; the router never silently no-ops).
- `Machine` protocol (Python `Protocol`, no ABC ceremony): `validate(current: str | None, target: str, *, weight: str = "standard") -> TransitionDecision`; `is_forward(current, target) -> bool`; `column_for(phase) -> str | None` (lifecycle kinds return their column; feature/5D return None — kanban derivation stays derive_kanban's until 132); `phases(weight) -> tuple[str, ...]`.
- `TransitionDecision` — frozen dataclass: `allowed: bool`, `reason: str`, `severity: "info"|"warn"|"error"`, `guard_id: str | None`. Mirrors the existing gate-result dict shape (engine.py `_run_gate`) so MCP serialization is unchanged.

## D2 — The three machine classes (OQ-3 RESOLVED: strategy objects, NOT one flattened schema)

The three shapes are irreducibly different (spec i2-B1/i3-W-A established the data-vs-enforcement splits); one declarative schema would re-flatten what the skeptic rounds un-flattened.

1. **`FeatureMachine`** — weight-AGNOSTIC. Wraps `transition_gate.PHASE_SEQUENCE` (the ONLY enforced feature graph) + delegates gate evaluation to the existing 4-gate chain (G-18/G-08/G-23/G-22) exactly as engine.py:560-600 runs them today. It does NOT consume templates.py (runtime-dead for features; FEATURE_7_PHASE is a 6-entry misnomer). `phases(weight)` returns the full 6-tuple for every weight; express variance = skipped-events overlay (spec FR123-6).
2. **`FiveDMachine(kind)`** — one instance per 5D kind (initiative/objective/key_result/project/task). `phases(weight)` = `get_template(kind, weight)` verbatim. `validate` implements the :508-546 ordering rules EXTRACTED (moved, not rewritten): same-phase and +1 → allowed; earlier → allowed-with-warn (`guard_id="G-18"`, matching today's backward-warn shape); > +1 → blocked (skip). The hand-rolled block in `_fived_transition` is then DELETED — the machine is its only home.
3. **`LifecycleMachine(kind)`** — brainstorm/backlog. Carries the graph data currently in ENTITY_MACHINES: `transitions` dict, `forward` set, `columns` map **with the FR123-4 change applied: brainstorm `reviewing` → `"wip"`** (was agent_review — the last live producer retires; wip is CHECK-legal, database.py:411-415). `validate` = graph membership (current in transitions, target in transitions[current]) with the same error strings transition_entity_phase raises today (`invalid_transition: cannot transition {kind} from {current} to {target}`).

Machine definitions live IN router.py. `ENTITY_MACHINES` as a name survives ONLY as the LifecycleMachine construction data inside router.py (SC1's grep then resolves to the router definition site alone).

## D3 — entity_engine.py rewire (FR123-3 + FR123-5)

- `_is_phase_sequence_kind` (:44-46) survives as the backend selector, but BOTH backends delegate validation to `get_machine(kind).validate(...)`:
  - FeatureBackend: unchanged flow — the frozen engine already runs the gate chain; FeatureMachine IS that chain behind the protocol (no double-evaluation: the backend calls the machine, the machine calls the gates).
  - FiveDBackend: `_fived_transition`'s :508-546 hand-rolled block DELETED, replaced by one `machine.validate(...)` call; the decision maps to the same TransitionResponse results shape.
- **Fail-loud (both shapes):** `_fived_transition`'s `except sqlite3.Error → TransitionResponse(degraded=True)` (:552-567) and `_fived_complete`'s `except sqlite3.Error → print+None` (:452-457) BOTH become `raise db_unavailable_error(operation=..., feature_ref=...) from e` (models.py:49-61 — the no-'locked' message contract is the builder's, models.py:40-45). Transaction rollback rides the existing per-request transaction (workflow_state_server's `db.transaction()`), same as 128's feature path.
- **Kind-key collapse (H3):** the five `entity["entity_type"]` reads (:281/:404/:475 + two others verified at implement) become `entity["kind"]`; outward result dicts keep carrying both keys (DB alias unchanged).
- `TransitionResponse.degraded` field AND its :27-31 adjacent explanatory comment REMOVED from models.py (spec FR123-3 + gate W1). Every construction site loses the kwarg (call-site-forced).

## D4 — workflow_state_server.py changes

- `:925-929` guard block DELETED (last producer gone with D3).
- `:1007` envelope key `"degraded": response.degraded` DELETED → transition envelope = `{transitioned, results}` (2-key); the pinned test :1328-1345 updates. READ-side `_serialize_state` :246 UNTOUCHED (the kept FR-10 signal; its 5-key pin :1364-1380 unchanged).
- Imports :43-44 update to the router module path (D6 decides entity_lifecycle.py's fate; tool contracts unchanged).

## D5 — `_project_meta_json` kind-dispatch (OQ-2 RESOLVED: root-level, name preserved)

Inside `_project_meta_json` (workflow_state_server.py:383-499), the FIRST act after resolving the entity: branch on `entity["kind"]`:
- `feature` → the existing body, byte-identical output (SC2's no-other-kind-changes half).
- `project` → build PROJECT shape: `{id, slug, status, created, features, milestones, brainstorm_source}` — `features`/`milestones`/`brainstorm_source` recovered from the DB entity metadata (init_project_state stores them there, feature_lifecycle.py:257-262; NOT a read-merge of the existing file), `status` from the entity row, `id`/`slug` split from type_id. Write via the same `_atomic_json_write` path the function already uses.
- any other kind → return without writing (structured no-op log line) — bug/brainstorm/backlog/5D-non-project entities have no `.meta.json` contract; today they'd have been clobber victims too if any carried an artifact_path + workflow row.
Function NAME preserved → the 127 exact-4 writer allowlist (test_audit_writes.py:313-327) untouched. All SIX call sites (3 clobber vectors :1014/:1371/:1442 + 3 feature-only :1705/:1756/fix_actions:112) route through the branch — feature ids byte-unchanged.

## D6 — entity_lifecycle.py disposition (no-backcompat: MOVE and DELETE)

`init_entity_workflow` + `transition_entity_phase` MOVE into router.py (they become the lifecycle-kind entry points calling LifecycleMachine); entity_lifecycle.py is DELETED. Import updates (the complete set, grep-verified): workflow_state_server.py:43-44 (aliased imports → router), test_entity_lifecycle.py, test_status_only_lifecycle.py, test_workflow_state_server.py:32, ui test_deepened_app.py:1012 (spec FR123-4's import-coupling clause). The moved `transition_entity_phase` keeps its exact ValueError strings and dict returns (MCP contract stable per FR123-5); its `db.update_entity`/`db.update_workflow_phase` write calls are unchanged (sanctioned CRUD, doctor surface untouched).

## D7 — test plan (GOVERNING list; every touched assert cited)

**Red-first (before any production edit):**
1. SC2 ×3: seeded project (with features/milestones metadata + a real .meta.json) through `transition_phase`, `complete_phase`, `reproject_meta_json` — each TODAY overwrites with feature shape (assert features/milestones ABSENT post-call = the red); post-D5 all three preserve them (byte-compare the two arrays) + status updated.
2. SC3 fault-injection ×2: monkeypatched `update_workflow_phase` raising `sqlite3.OperationalError` inside (a) a 5D transition and (b) a 5D complete — TODAY (a) returns degraded=True response, (b) returns None + stderr; post-D3 BOTH raise WorkflowDBUnavailableError with pre-state intact (re-read the row: unchanged).
3. SC4: brainstorm draft→reviewing — TODAY writes kanban_column=agent_review; post-D2 writes wip (row asserted).

**The SC1 graph-diff union test (non-vacuity core):** a new test module enumerates `MACHINE_REGISTRY` and asserts each kind's effective graph — (phase set per weight where applicable, valid-targets per phase, forward/backward classification) — against literals DERIVED at authoring time from the old code's enforced structures (ENTITY_MACHINES dicts; get_template lists + the :508-546 rules; PHASE_SEQUENCE), each literal carrying a derivation comment naming its source. Weight-subset dimension asserted for 5D kinds only (feature N/A). Brainstorm's reviewing→wip is the ONE deliberate delta — asserted as such (the test names FR123-4, proving the diff harness sees exactly one intentional change and zero accidental ones).

**Updates (enumerated):** test_workflow_state_server.py :1328-1345 3-key→2-key; :6583 agent_review→wip literal; :32 import path; test_entity_lifecycle.py + test_status_only_lifecycle.py: import paths + re-label "not a lifecycle-GRAPH kind" (:49-50 assertions keep passing — task/bug still absent from lifecycle machines; docstrings/names updated to the new meaning); test_deepened_app.py :1012 import path + :1008-1010 stale comment refresh; test_engine.py TransitionResponse dataclass tests lose the degraded field cases (:1910-1959 region, exact sites at implement); test_entity_engine.py's 5 `assert not response.degraded` sites DELETED with the field.

**New (beyond red-first + graph-diff):** router registry completeness (get_machine raises for bug/workspace/unknown); D5's other-kind no-op branch; kind-collapse regression pin (an entity dict lacking `entity_type` but carrying `kind` flows through both backends — H3's regression guard).

## D8 — file inventory + QA deliverables

1. plugins/pd/hooks/lib/workflow_engine/router.py (NEW — registry + 3 machine classes + moved lifecycle entry points)
2. plugins/pd/hooks/lib/workflow_engine/entity_engine.py (D3)
3. plugins/pd/hooks/lib/workflow_engine/models.py (degraded field + :27-31 comment out)
4. plugins/pd/hooks/lib/workflow_engine/engine.py (FeatureMachine wiring ONLY if needed — expected ZERO or import-only; the gate chain stays in place)
5. plugins/pd/mcp/workflow_state_server.py (D4 + D5)
6. plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py (DELETED)
7. Tests per D7 (test_workflow_state_server.py, test_entity_lifecycle.py→relocated/renamed alongside router, test_status_only_lifecycle.py, test_engine.py, test_entity_engine.py, ui/tests/test_deepened_app.py, + the new router test module)
8. Feature docs (spec/design/plan/tasks/.review-history + reports)

**QA deliverables:** merge-base baseline (scratch worktree, account the known 2-doctor-test worktree artifact); full suite hooks/lib+mcp+ui; validate.sh; hooks suite; doctor pin unchanged (check_status_write_path's permitted-writers list untouched — router writes via the same CRUD names); SC1 grep + SC3 mutation-layer grep + SC4 production grep (scoped per spec); diff gate vs THIS inventory.

## Open items deliberately left to create-plan

Task split (router+machines first vs single-task), the test_entity_lifecycle.py relocation naming, and the exact entity_engine.py additional `entity_type`-read sites (two beyond the three cited — enumerate at plan time with line numbers from the live tree).
