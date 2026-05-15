# Plan — Feature 111: Issue Lifecycle Closure

- **Spec:** spec.md rev 3.5 (Pin G trigger — 5th parser site added to scope)
- **Design:** design.md rev 2.5 (C8.b + IF-8 target_files = 3 paths; C11 corrected to note get_entity_by_uuid exists)
- **Status:** revision 3 (addresses plan-reviewer iter 2: 2 blockers + 4 warnings + 2 suggestions)
- **Mode:** standard

## §1 Strategy

5 implementation groups with **strict A → B → {C ∥ D ∥ E}** ordering. Group A is DDL-only (atomic-commit-discipline per NFR-1). Group B ships all Python constants + exception classes + helper methods + tests; this is what C/D/E depend on. Groups C, D, E run in parallel worktrees once B is merged.

### §1.1 Precedence resolutions (per plan-reviewer iter 1)

- **TDD red-first vs atomic-DDL-only.** Atomic-DDL wins for Group A — migration commit ships DDL only (no test file in the same commit) per features 109/110 precedent. **Red-first compensation:** Task A.8 runs a local Python REPL smoke test (NOT committed) against a tmpfs DB that asserts the post-migration schema state. This is the red-equivalent gate before Group A commits. Group B's `test_migration_14_safety.py` is the full red test (runs after Group B's exception/helper symbols exist).
- **Closure transaction boundary (RESOLVED — design IF-2 patched to rev 2.4).** Feature 088 FR-5.1 mandates caller's `completed` phase_event STAYS OUTSIDE the existing `with db.transaction():` block (current `workflow_state_server.py:1202-1229` post-commit dual-write — "MUST NOT roll back" comment). For F10, **closure writes go INSIDE** the existing transaction block (alongside `update_entity` for metadata at ~line 1195 / before transaction-close at ~line 1199); **caller's `completed` event stays OUTSIDE** (preserves FR-5.1). Mixed semantics: closure side atomic, caller side best-effort dual-write. Implementer inserts closure block between `db.update_workflow_phase(...)` (line ~1195) and end of with-block (line ~1199).
- **Group E parallel-with-D safety (RESOLVED).** AC-CL.3's doctor synthetic test uses HAND-CRAFTED DB fixtures (direct INSERT into entities + entity_relations rows; NO call to `complete_phase(closes=)`). E remains parallelizable with D. Integration coverage of F10→doctor lives in Group D's own tests (AC-10.x).
- **Same-PR enforcement.** Group A and Group B MUST land in the same PR. Implementer **creates both commits locally and pushes as a single `git push` invocation** — no intermediate push between commits. PR description must list both commit SHAs. **Verification gate:** at PR-merge time, assert `git log --oneline GROUP_A_SHA..GROUP_B_SHA | wc -l == 1` (B is the immediate successor of A, no interleaved commits). PR template or merge checklist line: "Confirm Group A → Group B commits are immediately adjacent (no interleaved commits)." Group A's commit message captures the local-smoke-test output (Task A.8) so the commit is self-witnessed.

### §1.2 TDD ordering per Group

Each Group's task list below is split into RED-first (tests) then GREEN (production code). Implementer-skill enforces red-first regardless of bullet ordering.

### §1.3 Complexity levels

| Group | Complexity | Rationale |
|---|---|---|
| A | Complex | Two CHECK-widening copy-renames + down-migration safety; ceremony per migration-12 precedent is non-trivial |
| B | Medium | Constants, exception classes, helper methods — mostly mechanical; test files comprehensive |
| C | Medium | New MCP tool, well-pinned to design IF-1 step-by-step |
| D | Complex | Transaction-ordering refactor inside an existing block with feature-088 FR-5.1 invariants to preserve |
| E | Medium | Bounded cleanup pending pre-Group-E inventory (Task E.0); ≈780 lines reviewed, expected delete-rate <30% |

## §2 Dependency Graph

```
       ┌─────────────────────────────────────────────┐
       │  Group A — Migration 14 (DDL only)          │
       │  database.py:                               │
       │   • _migration_14_issue_lifecycle_closure   │
       │   • MIGRATIONS[14], MIGRATIONS_DOWN[14]     │
       │   • _copy_rename helpers (up + down)        │
       └─────────────────────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────┐
       │  Group B — Discriminator/constants/helpers  │
       │   • _KIND_TO_TYPE_LIFECYCLE += {bug, task}  │
       │   • _VALID_PARAMS += {spawned_child}        │
       │   • _CLOSES_TERMINAL = {...}                │
       │   • VALID_ENTITY_TYPES += 'bug'             │
       │   • Exception classes (IF-9)                │
       │   • 4 new EntityDatabase helpers (C11)      │
       │   • transition_entity_phase defensive raise │
       │   • test_migration_14_safety.py +           │
       │     test_status_only_lifecycle.py +         │
       │     test_entity_lifecycle.py extensions     │
       └─────────────────────────────────────────────┘
            │              │              │
            ▼              ▼              ▼
       ┌───────────┐  ┌───────────┐  ┌───────────┐
       │ Group C   │  │ Group D   │  │ Group E   │
       │ issue_    │  │ complete_ │  │ Cleanup + │
       │ spawn MCP │  │ phase     │  │ new       │
       │           │  │ closes=   │  │ doctor    │
       │           │  │           │  │ check     │
       └───────────┘  └───────────┘  └───────────┘
```

**No conflicts between C/D/E:** C touches `entity_server.py`; D touches `workflow_state_server.py`; E touches `entity_registry/backfill.py` + `doctor/checks.py` + `doctor/__init__.py`. Each Group creates distinct test files.

## §3 Group-Level Plan

### Group A — Migration 14 (DDL only)

**Why this item:** Implements design C7 (Migration 14) — spec FR-MR.1/2/3/4/5/6/7/8/9 + AC-MR.1-11. Mandatory schema foundation before Python constants in Group B reference `'bug'` kind, `'spawned_child'` event_type, or `entity_relations` table.

**Why this order (first, alone):** All subsequent Groups depend on the schema (Group B's tests load synthetic v14 DB fixtures; C/D/E exercise the new constraint surface). Atomic-DDL discipline per NFR-1 forbids bundling Python logic — Group A is the cleanest standalone migration commit.

**Goal:** Schema migration adding `entity_relations` table, widening `entities` (type, kind) CHECK to admit `'bug'`, widening `phase_events` event_type CHECK to admit `'spawned_child'`, remapping any kind='task' rows to `lifecycle_class='task_flow'`. Down-migration with pre-flight refuses on bug entities or relation rows.

**Files:** `plugins/pd/hooks/lib/entity_registry/database.py` only.

**Functions added:**
- `_migration_14_issue_lifecycle_closure(conn)` — main up-migration body.
- `_copy_rename_entities_for_v14(conn)` — entities CHECK widening copy-rename helper.
- `_copy_rename_phase_events_for_v14(conn)` — phase_events CHECK widening copy-rename helper.
- `_migration_14_down(conn)` — down-migration with pre-flight refuse.
- `_copy_rename_entities_to_v13(conn)` — entities CHECK narrowing helper.
- `_copy_rename_phase_events_to_v13(conn)` — phase_events CHECK narrowing helper.
- `MIGRATIONS[14] = _migration_14_issue_lifecycle_closure`.
- `MIGRATIONS_DOWN[14] = _migration_14_down`.

**Note:** NO test file in this commit (test_migration_14_safety.py lives in Group B per atomic-DDL-only rule).

**Acceptance:** Migration runs on a v13 DB → schema_version=14, entity_relations table exists with 3 indices, (type, kind) CHECK admits `'bug'`, phase_events event_type CHECK admits `'spawned_child'`, kind='task' rows have lifecycle_class='task_flow'. Down-migration on v14 DB with 0 bugs + 0 relations → schema_version=13. Down with bugs → MigrationError.

### Group B — Discriminator + constants + helpers + tests

**Why this item:** Implements design C2/C3/C6/C10/C11 + status-only model (C4). Spec FR-9.2 mapping rows, FR-BL.1-4, FR-EX.1-3, FR-MR.4/5 Python-side, AC-BL.x, AC-EX.x. Group A's tests live here because they reference Group B symbols (exception classes, _CLOSES_TERMINAL).

**Why this order (after A, before C/D/E):** C and D both import `EntityNotFoundError` / `InvalidCloseTargetError`; both call new helpers `resolve_entity_uuid`, `get_entity_by_uuid`, `get_prior_closer`, `insert_entity_relation`. C also relies on `_KIND_TO_TYPE_LIFECYCLE` mapping for `'bug'`. Without B's symbols, C and D fail to import.

**Goal:** All Python application logic + new exception classes + 4 new EntityDatabase helpers + transition_entity_phase defensive raise + the migration safety tests.

**TDD sequence:** Test files (B.1-B.5) written FIRST (red). Production code (B.6-B.15) makes them green.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` — add constants + helpers + exceptions.
- `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py` — add defensive raise.
- `plugins/pd/hooks/lib/entity_registry/test_migration_14_safety.py` (NEW) — verifies Group A migration.
- `plugins/pd/hooks/lib/entity_registry/test_status_only_lifecycle.py` (NEW) — verifies AC-BL.x.
- `plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py` — extend with AC-BL.7 defensive raise tests.
- `plugins/pd/mcp/test_workflow_state_server.py` — audit + extend if needed for ENTITY_MACHINES introspection assertions impacted by defensive raise.

**Additions:**
- `_KIND_TO_TYPE_LIFECYCLE` at database.py:48: add `'bug': ('work', 'bug_flow')`; remap `'task': ('work', 'task_flow')`.
- `_VALID_PARAMS` at database.py:4442: add `'spawned_child': {'metadata'}`. **Also `_REQUIRED_PARAMS` at database.py:4452: add `'spawned_child': {'metadata'}`** (per plan-reviewer iter 2 W4 — preserves audit-trail guarantee that spawned_child events carry the required metadata payload).
- `_CLOSES_TERMINAL` (NEW module-level dict at database.py near `_KIND_TO_TYPE_LIFECYCLE`): `{'bug_flow': 'closed', 'task_flow': 'closed', 'work_flow': 'dropped'}`.
- `VALID_ENTITY_TYPES` tuple at database.py:4534: add `'bug'` (9 values total).
- `EntityNotFoundError(ValueError)` + `InvalidCloseTargetError(ValueError)` near EntityExistsError at :4484.
- 3 new EntityDatabase methods: `get_prior_closer`, `insert_entity_relation`, `resolve_entity_uuid`. **REUSE existing `db.get_entity_by_uuid` at database.py:4788** (per plan-reviewer iter 2 B2 — verified existing method covers IF-1 step 5 + IF-2 step 2 use cases).
- `transition_entity_phase`: AC-BL.7 satisfied by existing code at `entity_lifecycle.py:148-150` (raises `ValueError("invalid_entity_type: ... — only brainstorm and backlog supported")` when entity_type not in ENTITY_MACHINES). NO new defensive raise needed.

**Acceptance:** All AC-BL.x + AC-EX.x + AC-MR.x pass. `pytest plugins/pd/hooks/lib/entity_registry/test_status_only_lifecycle.py test_migration_14_safety.py test_entity_lifecycle.py -v` green.

### Group C — F9 `issue_spawn` MCP

**Why this item:** Implements design C1 (issue_spawn MCP). Spec FR-9.1-9.9, AC-9.1-9.9.

**Why this order (after B; parallel with D, E):** Depends on Group B symbols (helpers, exception classes, _KIND_TO_TYPE_LIFECYCLE['bug']). Independent of Groups D (different file: entity_server.py vs workflow_state_server.py) and E (different file).

**TDD sequence:** test_issue_spawn.py written FIRST (red); issue_spawn implementation makes it green.

**Goal:** New MCP tool that spawns bug/task issue entities linked to a parent, appends `spawned_child` event on parent without modifying parent's `workflow_phase` or `kanban_column`.

**Files:**
- `plugins/pd/mcp/entity_server.py` — add `@mcp.tool() async def issue_spawn(...)`.
- `plugins/pd/mcp/test_issue_spawn.py` (NEW) — verifies AC-9.x.

**Implementation** (per IF-1 + IF-9 mapping): see design IF-1 step-by-step.

**Acceptance:** All AC-9.x pass. `pytest plugins/pd/mcp/test_issue_spawn.py -v` green.

### Group D — F10 `complete_phase` closes= extension

**Why this item:** Implements design C5 (closes= extension). Spec FR-10.1-10.6, AC-10.1-10.11.

**Why this order (after B; parallel with C, E):** Depends on Group B helpers (`resolve_entity_uuid`, `get_entity_by_uuid`, `get_prior_closer`, `insert_entity_relation`) + exception classes (`EntityNotFoundError`, `InvalidCloseTargetError`) + `_CLOSES_TERMINAL` dict. Independent of C (different file) and E (different file).

**TDD sequence:** Task D.1 (transaction-boundary audit, pre-resolved per §1.1 — closure writes INSIDE existing with-block at line ~1195, caller's `completed` STAYS OUTSIDE). Test file D.2 written FIRST (red). Production code D.3 + D.4 makes them green.

**Goal:** Extend existing `complete_phase` MCP to accept `closes: list[str] | None` kwarg; atomic transaction writes `entity_relations(kind='fixes')` rows + transitions closed entities to terminal status; idempotent on same-closer replay; cross-workspace closure forbidden.

**Files:**
- `plugins/pd/mcp/workflow_state_server.py:1086` (`_process_complete_phase`) and `:1809` (MCP signature) — add `closes` kwarg + closure block per IF-2.
- `plugins/pd/mcp/test_complete_phase_closes.py` (NEW) — verifies AC-10.x.

**Implementation pin (RESOLVED in design rev 2.5 + plan §1.1):** Closure writes (FR-10.3 steps 6, 7) land INSIDE the existing `with db.transaction():` block (between `db.update_workflow_phase(...)` at line ~1198 and the close of the with-block at line ~1199). **Sibling, NOT nested:** the closure block is a sibling of (NOT inside) the `if feature_type_id.startswith("feature:")` block at line 1195 — closure writes fire for ANY caller kind when `closes` is non-empty, not just features. Mis-nesting would silently skip closure transitions for non-feature callers despite `closes=` being passed. The caller's `completed` phase_event dual-write at lines 1202-1229 (feature 088 FR-5.1) STAYS OUTSIDE the transaction. Mixed semantics — closure side atomic, caller side best-effort — is the deliberate boundary.

**Acceptance:** All AC-10.x (10.1 through 10.11) pass. `pytest plugins/pd/mcp/test_complete_phase_closes.py -v` green.

### Group E — Cleanup + new doctor check

**Why this item:** Implements design C8 (parser removal) + C9 (new doctor check). Spec FR-CL.1-4, AC-CL.1-4.

**Why this order (after B; parallel with C, D):** Independent of C/D — touches different files (`entity_registry/backfill.py`, `doctor/checks.py`, `doctor/__init__.py`). AC-CL.3's test uses hand-crafted DB fixtures (no F10 invocation) — does NOT depend on Group D output (resolution per §1.1).

**TDD sequence:** Inventory (E.0) first to bound scope. Tests (E.1, E.2) written FIRST (red). Production changes (E.3-E.8) make them green.

**Goal:** Remove free-text suffix parsers from production code, add `check_no_free_text_status_parsers` doctor check.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/backfill.py:418-444` — DELETE derived_status block.
- `plugins/pd/hooks/lib/doctor/checks.py:983-1015` — DELETE regex compilation + line-loop; preserve entities_conn cross-ref infra.
- `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py:14-18` — DELETE `CLOSED_RE`, `PROMOTED_RE`, `FIXED_RE`, `NAME_STRIP_RE` regex compilations. Migrate consumers at `:320-329` to read from DB (entities.status + entity_relations). Per spec FR-CL.1b (added per Pin G trigger).
- `plugins/pd/hooks/lib/doctor/checks.py` (bottom) — add `check_no_free_text_status_parsers` per IF-8 (3 target paths).
- `plugins/pd/hooks/lib/doctor/__init__.py:12-31` (import block) + `:33` (CHECK_ORDER list start) — register new check.
- `plugins/pd/hooks/lib/entity_registry/test_backfill.py:981, 992, 1037` — migrate fixtures to DB-state inputs OR delete parser-exercise-only tests.
- `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py:385-1168` — same triage (path correction: file lives in reconciliation_orchestrator/, not entity_registry/).
- `plugins/pd/hooks/lib/entity_registry/test_cleanup_suffix_parsers.py` (NEW) — verifies AC-CL.x.
- `plugins/pd/hooks/lib/doctor/test_doctor.py` — extend with `check_no_free_text_status_parsers` smoke tests + 2-CWD assertion.

**Acceptance:** All AC-CL.x pass (1 grep returns 0; 2 backfill behavior documented as changed; 3 doctor reads from DB; 4 new check passes from project root AND from a subdirectory).

## §4 Risks (carry-forward from spec/design)

- **R1–R8** (see spec.md §7 + design.md §3) — all addressed.
- **Implementer must verify:**
  - IF-2 step 5 transaction COMMIT-ordering at `workflow_state_server.py:1127-1234` (design notes critical verification).
  - test_workflow_state_server.py impact from defensive raise in transition_entity_phase (Group B sub-task).
  - Same-PR constraint for Groups A + B (must merge together).
- **Accepted out-of-scope:** orphan detection (entities whose parent has no `spawned_child` audit row) — explicit design decision; no compensating code.

## §5 Acceptance Map

| Spec AC | Group | Test file |
|---|---|---|
| AC-9.1 – 9.9 | C | `test_issue_spawn.py` |
| AC-10.1 – 10.11 | D | `test_complete_phase_closes.py` |
| AC-MR.1 – 11 | A (DDL) + B (tests) | `test_migration_14_safety.py` |
| AC-BL.1 – 7 | B | `test_status_only_lifecycle.py` + `test_entity_lifecycle.py` |
| AC-CL.1 – 4 | E | `test_cleanup_suffix_parsers.py` + `test_doctor.py` |
| AC-EX.1 – 2 | B | `test_status_only_lifecycle.py::test_exception_classes_*` |
