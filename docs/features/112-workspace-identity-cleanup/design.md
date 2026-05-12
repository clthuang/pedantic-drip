# Feature 112 — Workspace Identity Cleanup — Design

**Spec:** [`spec.md`](spec.md)
**Parent:** project P003-entity-system-redesign
**Reference feature:** 108-workspace-identity-foundation (this feature
completes 108's deferred Phase F + Phase H).

---

## Prior Art Research

Skipped explicit codebase-explorer / internet-researcher dispatches.
Prior-art context already available from:

1. **Feature 108 artifacts** (parent feature): the
   `_resolve_workspace_uuid_kwargs` deprecation shim
   (`database.py:2780`), the `_resolve_optional_workspace_filter` read
   counterpart (`database.py:2843`), and the per-method incremental
   rollout pattern proven across commits `88e85f4` → `dd7f91e`.

2. **Memory-bank patterns relevant to this feature** (from
   complete_phase memory_refresh):

   | Pattern | Application here |
   |---|---|
   | "Grep-first scope discovery for component maps" | Spec FR-1, FR-4, FR-5 each lock the file:line set via live grep at spec-time; design preserves these enumerations and refuses to drift. |
   | "Inline Verified Behavior matrix in design for language-semantics fixes" | FR-6 session-start.sh shell expansion semantics (`${WORKSPACE_UUID:0:8}`) gets a behavior matrix below. |
   | "MCP server peer parity check prevents design blockers" | FR-2 wiring mirrors entity_server.py:151,530 — we explicitly cross-reference. |
   | "Design must prescribe shared utility location for library extractions" | `_resolve_optional_workspace_filter` already lives at `entity_registry/database.py:2843`; no new module needed. |
   | "Enumerate Git Edge Cases in Design Technical Decisions" | This feature touches no git operations; not applicable. |

3. **Adversarial QA gate findings** for feature 108: 9 HIGH items, of
   which 6 deferred to this feature. The `qa-override.md` documents
   the deferral rationale + each cluster's verification AC.

---

## Architecture Overview

This is a cleanup feature, not a redesign. The architecture is:

- **No new components.** The 7 FR clusters each modify existing
  surfaces.
- **The transition shim (`_resolve_workspace_uuid_kwargs`) is the
  primary integration point.** FR-4 removes its `parent_type_id`
  resolution branch and drops the `register_entity` /
  `register_entities_batch` `parent_type_id` kwarg signature. All
  other FRs feed into this final shim deletion.
- **The `_workspace_uuid` lazy global is canonicalised** as the
  write-scope source in both MCP servers (`entity_server.py` already
  does this; `workflow_state_server.py` is wired in FR-2).

### Dependency graph (FR ordering)

```
FR-1 (delete detect_project_id) ──┐
                                  ├──> FR-6 (project_id render cleanup) ──> FR-7 (validation)
FR-3 (drop ENTITY_PROJECT_ID) ────┘                                            │
                                                                               │
FR-2 (wire _workspace_uuid in WSS) ───┐                                        │
                                      ├──> FR-4 (drop parent_type_id kwarg) ──┤
FR-5 (markdown sweep) ───────────────────┘ (FR-5 is parallel-safe with FR-2/4)│
                                                                               ▼
                                                                          ./validate.sh
                                                                          + pytest suite
                                                                          + .qa-gate.json
```

**Ordering rationale:**
- FR-1 and FR-3 are independent — they delete unused surfaces.
- FR-1 must land BEFORE FR-6 because FR-6 deletes the `_project_id`
  lazy global which is currently populated by `detect_project_id`. If
  FR-6 lands first, `_project_id` references blow up.
- FR-2 must land BEFORE FR-4 because FR-4 deletes the
  `parent_type_id` resolution path through the shim; if FR-2 hasn't
  wired `_workspace_uuid` through workflow_state_server, writes that
  previously routed via the legacy `project_id` JOIN will fail.
- FR-5 is parallel-safe — markdown-only changes don't affect runtime.
- FR-7 (validation artifacts) is last by definition — it audits
  what's landed.

---

## Components

### Component C1 — `project_identity.py` cleanup (FR-1, FR-3)

**File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py`

**Pre-state:** Contains both `detect_project_id` (the legacy 12-char
hex resolver, deprecated by feature 108 but never deleted) and the
`ENTITY_PROJECT_ID` env-var override branch.

**Post-state:**
- `detect_project_id` function deleted.
- `os.environ.get("ENTITY_PROJECT_ID")` block deleted.
- `_compute_legacy_project_id(working_dir)` retained as
  migration-only helper — still used by Migration 11 forward steps
  that read `workspaces.project_id_legacy`.
- The module docstring is updated to note the migration completion.

**Imports affected:** 9 files (see FR-1 file table in spec.md). The
3 test files (`test_project_identity.py`,
`test_entity_server.py`, `test_task_promotion.py`) get their
monkeypatch + assertion logic rewritten to target
`resolve_workspace_uuid`.

### Component C2 — MCP server canonical scoping (FR-2, FR-6)

**Files:** `plugins/pd/mcp/workflow_state_server.py`,
`plugins/pd/mcp/entity_server.py`.

**FR-2 wiring deliverable:** `handler-audit.md` (design-phase artifact;
sequencing per spec FR-2 Post-state). Classifies every `@mcp.tool()`
in `workflow_state_server.py` as `write` / `read` / `read+write`.
Each write call gets `workspace_uuid=_workspace_uuid or None`. Read
calls preserve cross-workspace semantics via
`_resolve_optional_workspace_filter`.

**Current read-handler state (verified at design-time):**
`list_features_by_phase` (1533) and `list_features_by_status` (1566)
do NOT currently route through `_resolve_optional_workspace_filter`.
The `_resolve_optional_workspace_filter` helper is invoked only from
within database.py methods (e.g. `list_entities`, `search_entities`).
The MCP tools call these underlying methods with default args. FR-2
must:
1. Extend `list_features_by_phase` and `list_features_by_status` to
   accept a `workspace_uuid` filter argument when `project_id != "*"`.
2. Forward to the engine, which passes through to `db.list_entities` /
   `db.search_entities` with the workspace_uuid filter.
3. When `project_id == "*"`, the handler passes `workspace_uuid=None`
   to the underlying DB call, which causes the helper to return None
   (no filter) — cross-workspace query preserved.

This is a behavioral change: today the handlers query
cross-workspace by default. Post-FR-2 they query single-workspace by
default and require explicit `project_id="*"` for cross-workspace.
Documented in CHANGELOG per NFR-5.

**FR-6 deletion deliverable:** `entity_server.py` `_project_id` lazy
global removed; the `detect_project_id` import (handled in FR-1) is
removed in the same commit. `session-start.sh:129,463-485` switches to
`workspace_uuid_short=${WORKSPACE_UUID:0:8}` rendering.

### Component C2b — Engine-layer signature propagation (FR-2)

The MCP handler `workspace_uuid` kwarg must propagate through the
engine layer. Per `handler-audit.md`, 12 engine functions need a new
`workspace_uuid` kwarg added.

**Engine functions (live grep at design-time):**

| # | Module | Function | Signature change |
|---|---|---|---|
| 1 | `workflow_engine/feature_lifecycle.py` | `init_feature_state` | add `workspace_uuid: str \| None = None` |
| 2 | `workflow_engine/feature_lifecycle.py` | `activate_feature` | same |
| 3 | `workflow_engine/project_lifecycle.py` | `init_project_state` | same |
| 4 | `workflow_engine/entity_engine.py` | `init_entity` | same |
| 5 | `workflow_engine/entity_engine.py` | `transition_phase` | same |
| 6 | `workflow_engine/engine.py` | `complete_phase` | same |
| 7 | `workflow_engine/engine.py` | `transition` | same |
| 8 | `workflow_engine/task_promotion.py` | `promote_task` | same |
| 9 | `workflow_engine/phase_events.py` | `record_backward_event` | same |
| 10 | `workflow_engine/reconciliation.py` | `reconcile_apply` | same |
| 11 | `entity_registry/frontmatter_sync.py` | `sync_frontmatter` | same |
| 12 | `reconciliation_orchestrator/entity_status.py` | `reconcile_status` | same |

**Non-MCP caller enumeration:** Each engine function may have non-MCP
callers (CLI tools, hook scripts, other engine functions, tests).
The FR-2 implementer MUST grep each function name across plugins/pd/
at FR-time and either:
- (a) Pass `workspace_uuid=None` from non-MCP callers (degrading to
  legacy resolution via `_resolve_workspace_uuid_kwargs`), OR
- (b) Migrate the non-MCP caller to obtain a workspace_uuid (e.g.
  via `resolve_workspace_uuid(PROJECT_ROOT)`).

**Decision per non-MCP caller** is the engineer's judgment call at
FR-time, documented in the commit message. The general guidance:
short-lived CLI tools and test fixtures get `workspace_uuid=None`
(the deprecation shim handles them); long-lived production callers
get explicit resolution.

**Verification:** `grep -rn '<func_name>\b' plugins/pd/ --include='*.py'`
per function. Match list documented in commit body per AC-15.

### Component C3 — `register_entity` parent_type_id alias removal (FR-4)

**Pre-state (verified against live code at design-time):** The
`parent_type_id` resolution lives inside `register_entity` itself at
`database.py:3426-3445`, NOT inside `_resolve_workspace_uuid_kwargs`
(which only handles `workspace_uuid` / `project_id` resolution).
`_resolve_workspace_uuid_kwargs` signature at `database.py:2780-2786`:
`(self, workspace_uuid, project_id, *, _caller)` — no parent kwargs.

The body of `register_entity` (lines 3343-3445) currently:
1. Accepts `parent_type_id: str | None = None` (line 3354) and
   `parent_uuid: str | None = None` (line 3353) kwargs.
2. After `_resolve_workspace_uuid_kwargs(...)` resolves the
   workspace, branches on `parent_type_id` at line 3426: if both
   `parent_uuid` and `parent_type_id` supplied, emit
   `DeprecationWarning`; otherwise call `_resolve_identifier(
   parent_type_id, workspace_uuid=ws_uuid)` to resolve to a UUID,
   silently falling back to `parent_uuid=None` on ValueError.

`register_entities_batch` has the equivalent block (per-entity dict
schema accepts `parent_type_id` keys).

**Post-state:**
- The `parent_type_id` kwarg is deleted from `register_entity`
  signature; the `parent_type_id` resolution block at lines
  3420-3445 is deleted along with the local `warnings.warn(...)`
  emitter (the `import warnings` may remain if used elsewhere).
- Same shape change applied to `register_entities_batch`: the
  per-entity dict schema drops `parent_type_id` key; the body code
  that read it is deleted.
- Each production caller is updated to pass a pre-resolved
  `parent_uuid` (resolved via `db.resolve_ref(parent_type_id_string)`
  at the call site — see Component C5 for the resolution-batching
  pattern).
- `_resolve_workspace_uuid_kwargs` is UNTOUCHED (it never had
  parent kwargs — the design previously misrepresented this).

### Component C3b — Synthesized JOIN column elimination (FR-4 AC-3b)

**Pre-state:** Three SELECT statements emit `p.type_id AS parent_type_id`
as a JOIN-derived column for legacy-compat:
- `database.py:2995` (`get_entity_by_uuid`)
- `database.py:3595` (`get_entity`)
- `database.py:3647` (alternative get path)
- `database.py:4567` (`export_lineage_markdown` envelope)

Downstream readers consume the synthesized column:
- `plugins/pd/hooks/lib/entity_registry/test_database.py` —
  15+ assertions on `entity["parent_type_id"]` (test code; gets
  rewritten alongside production callers per AC-3 exclusion language).
- `plugins/pd/hooks/lib/entity_registry/test_server_helpers.py` —
  2+ assertions (same treatment).

**Production downstream readers (verified at design-time):**
- `entity_registry/frontmatter_sync.py` (multiple lines per spec
  FR-4 file list, especially lines reading `entity.get('parent_type_id')`).
- `workflow_engine/reconciliation.py:314` reads
  `entity.get('parent_type_id')`.
- The export envelope in `database.py:4611`
  (`entity['parent_type_id'] = row['parent_type_id']`).

**Post-state — per-call-site decision:**

| SELECT site | Decision | Rationale |
|---|---|---|
| `database.py:2995` (`get_entity_by_uuid`) | Drop the `p.type_id AS parent_type_id` alias; readers switch to `parent_uuid` + 1 follow-up `get_entity_by_uuid(parent_uuid)` lookup when the type_id string is needed | Lookups are infrequent; latency cost minimal |
| `database.py:3595` (`get_entity` primary) | Drop the alias | Same |
| `database.py:3647` (`get_entity` alternative path) | Drop the alias | Same |
| `database.py:4567` (export envelope) | Drop the alias from the envelope schema; export consumers learn to JOIN parent_uuid themselves | Export is consumed by markdown projection (feature 110); 112 ships the schema change without breaking 110's plan |

**Downstream reader updates:**
- `frontmatter_sync.py` — replace `entity.get('parent_type_id')` with
  `entity.get('parent_uuid')` lookups; resolve to type_id via a
  one-shot `db.resolve_ref()` if the prose ID is needed.
- `reconciliation.py:314` — same pattern.
- `database.py:4611` — drop the export-envelope key.

**AC-3b verification (sharpened):** After FR-4 lands,
`grep -rnE "['\"]parent_type_id['\"]" plugins/pd/ --include='*.py' |
grep -vE '^[^:]+:[^:]+:\s*#' | grep -vE 'plugins/pd/hooks/lib/entity_registry/(database\.py:1[01][0-9]|database\.py:2[01][0-9]|database\.py:6[023][0-9])'`
returns 0 production hits. (The Migration-8/10/11 historical bodies
are explicitly excluded by the file:line range carve-out.)

### Component C4 — Markdown sweep (FR-5)

**Files (17 hits across 5 files):**
- `plugins/pd/commands/create-feature.md` (6 hits)
- `plugins/pd/commands/secretary.md` (6 hits)
- `plugins/pd/commands/create-project.md` (2 hits)
- `plugins/pd/skills/brainstorming/SKILL.md` (2 hits)
- `plugins/pd/skills/decomposing/SKILL.md` (1 hit)

**Replacement pattern:**
- `parent_type_id="<typed-id-string>"` (kwarg form in code blocks) →
  `parent_uuid=<uuid-resolved-via-db.resolve_ref()>` (kwarg form) plus
  a one-line preamble "resolve the parent type_id to a uuid via
  `db.resolve_ref(...)` first".
- Prose references like "set the parent_type_id to X" → "set the
  parent_uuid (resolve from `X` via `db.resolve_ref()`) to Y".
- Avoid mechanical sed — the prose context determines whether the
  replacement is a kwarg or a value reference.

### Component C4b — `.meta.json` schema bump (FR-4 R-6)

**Pre-state:** `.meta.json` files in `docs/features/*` and
`docs/projects/*` historically carry frontmatter / top-level keys
that may include `parent_type_id:` (string form of the parent
reference). FR-4's removal of the `parent_type_id` kwarg surface
requires a corresponding rewrite of any persisted `parent_type_id`
on disk.

**Audit at design-time:**
- `grep -rn 'parent_type_id' docs/features/ docs/projects/ docs/brainstorms/`
  to enumerate existing on-disk hits. Many `.meta.json` files
  generated by feature 108 and earlier may carry the key.
- The runtime behavior reading these files
  (`frontmatter_sync.py`, `_project_meta_json()`) is the affected
  surface.

**Post-state:**
- A one-shot rewrite at the start of FR-4 implementation walks
  `docs/features/*/.meta.json` and `docs/projects/*/.meta.json`
  files. For each file containing `parent_type_id`:
  - Resolve the value (a type_id string) to a UUID via
    `db.resolve_ref(value)`.
  - Replace the key/value with `parent_uuid: <resolved-uuid>`.
  - Write the file in-place via the `meta-json-guard.sh` fallback
    path (the guard permits writes when MCP is busy with this exact
    migration — alternatively, the rewrite is performed by a
    dedicated MCP tool that the guard recognises).
- Header schema is updated in `entity_registry/header.py` (or
  equivalent) to accept ONLY `parent_uuid:` going forward; an old
  `parent_type_id:` is treated as a parse error (per NFR-1, no
  backward compat).
- The script lives at
  `agent_sandbox/{today}/112-validation/meta-json-rewrite.py` and is
  invoked once. Its output is logged. After invocation, AC-3b's grep
  passes against on-disk state.

**Verification (extension to AC-3b):** After FR-4 lands AND the
rewrite script has run, `grep -rn 'parent_type_id' docs/features/
docs/projects/ docs/brainstorms/ --include='*.json'` returns 0
hits. (Historical artifacts under `docs/features/108-*/` retain
their references as legacy migration history — these are .md
artifacts, not .json, so the grep above naturally excludes them.)

### Component C5 — Resolution batching (cross-cluster, R-1 mitigation)

**Risk R-1** in the spec flagged the potential resolve_ref() call
explosion. Mitigation:

- `reconciliation.py` and `task_promotion.py` loop over many entities;
  each iteration would otherwise resolve the same parent type_id
  redundantly. **Batch-resolve at function entry** using
  `db.scan_entity_ids(prefix="...")` or
  `_resolve_identifier(parent_ref)` to get a dict
  `{type_id: uuid}` before the loop, then look up in-memory per row.
- For single-call sites (e.g., one register_entity per MCP request),
  no batching needed — resolve inline.
- Frontmatter sync/inject paths read parent_type_id from `.meta.json`
  and write to entity rows; the resolution becomes a one-shot
  `db.resolve_ref(parent_type_id)` at the start of the sync function.

### Component C6 — Validation artifact pipeline (FR-7)

**Files (new):**
- `agent_sandbox/{today}/112-validation/` directory with 10 log
  files (per AC-10) + `migration-timing-baseline.log` (TD-6
  design-time measurement) + `meta-json-rewrite.py` + log
  (C4b rewrite script).
- `docs/features/112-workspace-identity-cleanup/.qa-gate.json`
  walking the 41 feature 108 ACs.
- `plugins/pd/hooks/lib/entity_registry/test_database.py` gains
  `test_migration_11_runtime` (500-row synthetic dataset, asserts
  wall clock < 30s, warns > 2s) AND
  `test_migration_11_stress_benchmark` (10k-row, marked
  `@pytest.mark.benchmark`, not gated).

**Test fixture seed:** Both new tests share a
`_seed_v10_entities(db, count)` helper added to `test_database.py`.
The helper inserts `count` rows into the pre-Migration-11 entities
schema (project_id + parent_type_id columns present) with
deterministic UUIDs (e.g. `f"test-uuid-{i:06d}"`) and pseudo-random
parent edges (every 5th entity gets `parent_type_id="feature:001-test"`
where feature:001-test is the first row). Deterministic seeding
ensures the benchmark is reproducible across runs.

**`.qa-gate.json` walker construction:**

- **Artifact type:** One-shot manually-authored JSON file. No
  generator script (per design-phase decision — the 41 ACs don't
  drift frequently enough to justify a script).
- **Input source:** Feature 108 `spec.md` AC table at
  `docs/features/108-workspace-identity-foundation/spec.md` Block A-E
  ACs.
- **Output path:** `docs/features/112-workspace-identity-cleanup/.qa-gate.json`.
- **Schema enforcement:** AC-9 validator command (inlined in spec).
- **Authoring sequence:** The implementer reads feature 108 spec's
  41 ACs, then for each:
  1. Check if status is determined by this feature's commits — if so,
     wait until the cluster lands and record the verification command
     + observed output.
  2. Check if AC is F6-gated → mark `conditional_skipped` with
     `condition="F6_gate_failed"`, `backlog_ref="00359"`.
  3. Check if AC is bash-3.2-gated → run the AC-12 capture; record
     status per outcome.
  4. Check if AC was verified during feature 108's pre-release gate
     (see `.qa-gate.log` and the implementation-reviewer evidence at
     `qa-override.md`) → mark `passed` with evidence pointing to the
     historical record.
- **Evidence source for non-this-feature ACs:** Feature 108
  `qa-override.md` enumerates which ACs were verified during 108's
  pre-release gate. The walker copies the evidence from there. If
  the historical evidence is absent, the entry uses
  `status="deferred"` with `backlog_ref` pointing to the appropriate
  follow-up entry.

---

## Technical Decisions

### TD-1 — Per-method incremental rollout (NFR-3, R-1 mitigation)

Each FR cluster ships as 1–2 commits. Within a cluster, individual
file migrations are sequenced one at a time. After each commit:
1. Run `./validate.sh` — must be green.
2. Run the scoped pytest package suite — must be green vs baseline.
3. Run `git diff HEAD~1 HEAD --stat` to confirm no unintended drift.

**Why:** Proven in feature 108 (commits `88e85f4` → `dd7f91e`). Each
commit is independently revertible; bisect remains useful; review
load stays manageable.

### TD-2 — Production-caller migration BEFORE shim deletion (FR-4)

The deprecation shim deletion (`parent_type_id` branch in
`_resolve_workspace_uuid_kwargs`) is the LAST commit of FR-4. The
preceding commits migrate one caller at a time, with each commit
running pytest scoped to the touched package.

**Why:** If the shim is deleted before all callers migrate, any
missed call site raises `TypeError` at runtime. Per-caller migration
catches incomplete coverage before the shim removal.

### TD-3 — handler-audit.md as a design-phase deliverable (spec FR-2)

The `handler-audit.md` deliverable is produced during the design
phase, not implementation. The audit:
1. Enumerate every `@mcp.tool()` in `workflow_state_server.py`.
2. For each, classify the body as write / read / read+write.
3. List each `db.register_entity` / `db.upsert_workflow_phase` /
   `db.update_entity` / `db.list_*` / `db.search_*` call with the
   expected post-FR-2 form.

**Why:** Per spec FR-2 sequencing — the AC-8 pre-test (TDD red) needs
the classification in hand BEFORE FR-2 code changes land. Producing
the audit at design time lets the implementer write the test first.

**Re-verification at FR-time:** Before FR-2 implementation commits
begin, the implementer re-runs the audit grep:
```bash
grep -nE 'db\.(register_entity|upsert_workflow_phase|update_entity|list_entities|search_entities|get_entity|search_by_type_id_prefix|set_parent|get_lineage|claim_unknown_entities|next_sequence_value)' plugins/pd/mcp/workflow_state_server.py
```
If the call-site count drifts from the design-time table, the
implementer updates `handler-audit.md` accordingly in the FR-2 commit.
This prevents stale audits from leaking unchecked surface.

### TD-4 — `_compute_legacy_project_id` retention (FR-1, NFR-1)

Despite NFR-1 ("no backward compatibility"), `_compute_legacy_project_id`
is retained. Justification:

- Migration 11 forward uses it to compute legacy project_ids when
  building the `workspaces.project_id_legacy` column.
- Migration 11 reverse needs it to reconstruct the dropped
  `entities.project_id` column.
- The MIGRATIONS / MIGRATIONS_DOWN dispatcher invariant is "migrations
  are reversible". Removing the helper would break Migration 11
  reverse byte-identical round-trip (feature 108 AC-13).

**Conclusion:** `_compute_legacy_project_id` is migration-only legacy
infrastructure, not a transition shim. It stays.

### TD-5 — Verified Behavior matrix for `${WORKSPACE_UUID:0:8}` (FR-6, memory pattern)

`session-start.sh:463-485` switches the context render path from
`${project_id}-${project_slug}` to
`${workspace_uuid_short}-${project_slug}` where
`workspace_uuid_short=${WORKSPACE_UUID:0:8}`. Bash 3.2 (macOS system
bash) and bash 5+ have subtle behavior differences in parameter
expansion. The Verified Behavior matrix:

| Input | Bash 3.2 / 5+ behavior | Expected output |
|-------|------------------------|-----------------|
| `WORKSPACE_UUID=6250c8a6-5306-443f-b225-477a040016ea`, `${WORKSPACE_UUID:0:8}` | Both versions return first 8 chars | `6250c8a6` |
| `WORKSPACE_UUID=""`, `${WORKSPACE_UUID:0:8}` | Both versions return empty string | `` (empty) |
| `WORKSPACE_UUID unset`, `${WORKSPACE_UUID:0:8}` | Both versions return empty string (no error under `set +u`) | `` |
| `WORKSPACE_UUID="abc"`, `${WORKSPACE_UUID:0:8}` | Both versions return the full 3-char string (no padding) | `abc` |

**Implementation:** The render path is robust to WORKSPACE_UUID being
empty/short (degrades to short string + slug). No `set -u` is in
effect for `session-start.sh` (verified at FR-time via `grep -n 'set
-' plugins/pd/hooks/session-start.sh`).

### TD-6 — Migration timing test threshold (AC-11)

The test asserts wall clock < 30 s and warns at > 2 s on a 500-row
synthetic dataset (matching feature 108 AC-32 baseline). Threshold
choice:

- 2 s warning level: Feature 108 NFR-6 target.
- 30 s fail level: Feature 108 AC-32 explicit upper bound. Wide
  enough to absorb CI variability without false-failures.
- No skip carve-out (per spec R-5 resolution): if the test fails on
  the dev machine, that's a real performance regression to surface.

**Design-time measurement (R-5 surfacing):** Before FR-7
implementation begins, the implementer runs a one-shot timing
measurement against the current develop tip:

```bash
# Hand-rolled 500-row v10 fixture + invoke Migration 11
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c '
import time, tempfile, sqlite3, os
from entity_registry.database import EntityDatabase
# ... seed 500 v10 rows ... then invoke MIGRATIONS[11](conn) ...
print(f"wall_clock_seconds={t1-t0:.3f}")'
```

Record the result in `agent_sandbox/{today}/112-validation/migration-timing-baseline.log`.

**Conditional sub-task:** If the measured wall clock > 5 s,
performance work becomes a sub-task in this feature (or a follow-up
backlog entry, decided by the implementer per the magnitude). If
wall clock <= 5 s, FR-7 ships the test as-is.

This satisfies R-5's surfacing requirement at design-phase rather
than deferring to implementation discovery.

### TD-7 — Stress benchmark gating via `./validate.sh`, not pytest.ini (AC-11)

`test_migration_11_stress_benchmark` (10k-row dataset) uses
`@pytest.mark.benchmark`. It is NOT invoked by `./validate.sh` (the
validation script doesn't run this test module's benchmark tests).
**No global `pytest.ini` change.** Existing pytest invocations across
the repo retain their current behavior; the benchmark only runs when
explicitly invoked via `pytest -m benchmark` or by file:test
selection.

**Why:** Adding `addopts = -m "not benchmark"` to `pytest.ini` is a
global config change that could suppress other benchmark-marked tests
elsewhere. Spec AC-11 only requires "not gated on in ./validate.sh"
— that's satisfied by validate.sh not invoking the benchmark.

**Verification at FR-7 implementation time:** Run
`grep -rn '@pytest.mark.benchmark' plugins/pd/` to confirm no
existing benchmark tests need consideration. Run
`grep -n 'pytest_runtest\|benchmark' plugins/pd/.../pytest.ini` and
the validate.sh body to verify the gating logic.

---

## Risks

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| RD-1 | FR-4 commit-ordering mistake leaves orphan kwargs (caller migrated, shim still accepts) | Wasted CI run + extra commit | TD-2: shim deletion is the LAST commit of FR-4 |
| RD-2 | `handler-audit.md` classification miss (write path classified as read) | AC-8 pre-test passes but AC-7 fails post-impl | Spec AC-7b makes the audit a hard deliverable; design-phase production gives time for review |
| RD-3 | Frontmatter dict-key `'parent_type_id': ...` writes (FR-4 R-6) leak into post-migration markdown frontmatter | Silent data drift in `.meta.json` files | AC-3b explicit dict-key grep; schema bump in same commit as kwarg removal |
| RD-4 | Migration 11 reverse breaks because `_compute_legacy_project_id` deleted by mistake | Loss of Migration 11 byte-identical round-trip (feature 108 AC-13 regression) | TD-4 explicit retention; design-phase decision documented |
| RD-5 | Bash 3.2 / 5+ parameter expansion divergence breaks session-start.sh on dev machines | Hook fails silently on macOS / Linux mix | TD-5 Verified Behavior matrix; AC-12 bash-version log captures the actual environment |
| RD-6 | Phase H `.qa-gate.json` walker misses an AC | Coverage gap reproduces feature 108's Phase H deferral | C6 walker contract is exhaustive — 41 entries enforced by AC-9; auto-fail if entry count != 41 |
| RD-7 | NFR-2 baseline drifts during implementation if develop receives unrelated commits | Net-new-failure accounting corrupted | Baseline captured at FR-7 start, BEFORE any FR-cluster commit (spec NFR-2 protocol) |

---

## Interfaces

### I-1 — `EntityDatabase.register_entity` signature change (FR-4)

**Before:**
```python
def register_entity(
    self,
    entity_type: str,
    entity_id: str,
    name: str = "",
    *,
    artifact_path: str | None = None,
    status: str | None = None,
    parent_type_id: str | None = None,  # ← DELETED in FR-4
    parent_uuid: str | None = None,
    metadata: dict | str | None = None,
    workspace_uuid: str | None = None,
    project_id: str | None = None,
    auto_id: bool = False,
) -> str:
    ...
```

**After:**
```python
def register_entity(
    self,
    entity_type: str,
    entity_id: str,
    name: str = "",
    *,
    artifact_path: str | None = None,
    status: str | None = None,
    parent_uuid: str | None = None,
    metadata: dict | str | None = None,
    workspace_uuid: str | None = None,
    project_id: str | None = None,  # legacy alias retained for now
    auto_id: bool = False,
) -> str:
    ...
```

**Breaking change:** Callers passing `parent_type_id=` will hit
`TypeError: register_entity() got an unexpected keyword argument
'parent_type_id'`. CHANGELOG entry per NFR-5.

### I-2 — `register_entities_batch` signature change (FR-4)

Same shape as I-1: `parent_type_id` removed from each entity dict
schema; callers must pre-resolve to `parent_uuid`. The
`db.register_entities_batch([{type_id, name, parent_uuid, ...}, ...])`
form is canonical.

### I-3 — `register_entity` `parent_type_id` alias block deletion (FR-4)

**Note:** Earlier drafts of this design wrongly placed the
parent_type_id resolution in `_resolve_workspace_uuid_kwargs`. The
live code at `database.py:2780-2841` has signature
`(self, workspace_uuid, project_id, *, _caller)` — no parent kwargs.
`_resolve_workspace_uuid_kwargs` is UNTOUCHED by this feature.

The parent_type_id alias resolution lives inside `register_entity`
itself at `database.py:3343-3445`. FR-4 cuts the alias surface here:

**Before** (current state at `database.py:3343-3445`):
```python
def register_entity(
    self,
    entity_type: str,
    entity_id: str,
    name: str,
    *,
    workspace_uuid: str | None = None,
    project_id: str | None = None,
    artifact_path: str | None = None,
    status: str | None = None,
    parent_uuid: str | None = None,
    parent_type_id: str | None = None,  # ← DELETED in FR-4
    metadata: dict | None = None,
) -> str:
    ...
    ws_uuid = self._resolve_workspace_uuid_kwargs(
        workspace_uuid, project_id, _caller="register_entity"
    )

    # Compat shim (Feature 108 transition):
    # parent_type_id alias resolution at lines 3420-3445
    if parent_type_id is not None:                              # ← DELETED
        if parent_uuid is not None:                              # ← DELETED
            warnings.warn(..., DeprecationWarning, ...)         # ← DELETED
        else:                                                    # ← DELETED
            try:                                                 # ← DELETED
                resolved_parent_uuid, _ = self._resolve_identifier(
                    parent_type_id,
                    workspace_uuid=ws_uuid,
                )                                                # ← DELETED
                parent_uuid = resolved_parent_uuid              # ← DELETED
            except ValueError:                                   # ← DELETED
                parent_uuid = None                               # ← DELETED
    ...
```

**After:**
```python
def register_entity(
    self,
    entity_type: str,
    entity_id: str,
    name: str,
    *,
    workspace_uuid: str | None = None,
    project_id: str | None = None,
    artifact_path: str | None = None,
    status: str | None = None,
    parent_uuid: str | None = None,
    metadata: dict | None = None,
) -> str:
    ...
    ws_uuid = self._resolve_workspace_uuid_kwargs(
        workspace_uuid, project_id, _caller="register_entity"
    )
    # parent_type_id alias block removed — callers pre-resolve to parent_uuid.
    ...
```

The docstring (lines 3357-3403) is updated to drop the
`parent_type_id` parameter description.

`register_entities_batch` has the equivalent alias block in the same
file (per-entity dict schema reads `parent_type_id` keys). FR-4
removes that block too.

**Breaking change:** Callers passing `parent_type_id=` will hit
`TypeError: register_entity() got an unexpected keyword argument
'parent_type_id'`. CHANGELOG entry per NFR-5.

### I-4 — Session-start context render contract (FR-6)

**Before** (session-start.sh:463-485):
```bash
context+="\n${pd_root_prefix}\n"
context+="- Project: ${project_id}-${project_slug}\n"
context+="- Artifacts root: ${artifacts_root_val}\n"
```

**After:**
```bash
workspace_uuid_short="${WORKSPACE_UUID:0:8}"
context+="\n${pd_root_prefix}\n"
context+="- Project: ${workspace_uuid_short}-${project_slug}\n"
context+="- Artifacts root: ${artifacts_root_val}\n"
```

**Behavior:** When `WORKSPACE_UUID` is unset/empty, the render
degrades to `-${project_slug}` (leading hyphen + slug). Acceptable
fallback per TD-5.

### I-5 — `.qa-gate.json` schema (AC-9, formal definition)

```typescript
type QAGateEntry = {
  ac_id: string;  // "AC-1" through "AC-41" (feature 108 numbering)
  status: "passed" | "deferred" | "n_a" | "conditional_skipped";
  evidence?: {
    command: string;
    output_excerpt: string;
    file_ref?: string;  // optional "path:line"
  };
  condition: "F6_gate_failed" | "bash_4plus_host" | null;
  backlog_ref: string | null;  // "NNNNN" 5-digit ID
};

type QAGateFile = QAGateEntry[];  // length === 41 (enforced)
```

Validator (informal): `python3 -c 'import json,sys; d =
json.load(open(sys.argv[1])); assert len(d) == 41; assert all((e.get("evidence")
or e.get("backlog_ref") or e.get("condition")) for e in d)'`.

---

## Out-of-Scope Reaffirmation

(Mirroring spec.md Out-of-Scope.)

- Features 109/110/111.
- Migration 12+ schema changes.
- F6 (UUIDv7) adoption — backlog #00359, blocked on pyproject floor
  bump.
- 14 LOW QA-gate findings in
  `.qa-gate-low-findings.md` sidecar — retained as-is.

## Open Questions

Tracked during design review iteration 1; revisit at iteration 2 or
during implementation if any reopen:

1. **`list_features_by_*` cross-workspace default behavior** —
   Resolved: FR-2 changes the default from cross-workspace to
   single-workspace; `project_id="*"` becomes explicit. Documented
   in C2 + CHANGELOG entry.
2. **`.meta.json` schema bump migration** — Resolved: one-shot rewrite
   script at FR-4 implementation time per C4b. Audit at design time.
3. **Engine-layer non-MCP callers** — Resolved: per-caller decision
   in C2b; default to `workspace_uuid=None` (deprecation shim handles)
   for short-lived contexts, explicit resolution for long-lived
   production callers. Documented in commit body per AC-15.
4. **Migration timing** — Resolved: design-time measurement
   prescribed in TD-6; if > 5 s on dev machine, perf work surfaces
   as sub-task. Otherwise FR-7 ships as-is.
5. **`.qa-gate.json` walker** — Resolved: manually-authored one-shot
   JSON (per C6). No generator script.
