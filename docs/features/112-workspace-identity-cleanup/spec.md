# Feature 112 — Workspace Identity Cleanup — Specification

**Parent:** project P003-entity-system-redesign (foundation-completion before
features 109, 110, 111).

**Trigger:** Feature 108 pre-release QA gate (Step 5b) identified 9 HIGH
findings. 3 runtime-breakers fixed in 108; 6 spec-completeness HIGH
deferrals (#00360–#00366) plus 22 MED items (#00367–#00388) deferred to
this feature. The deferral rationale lives at
`docs/features/108-workspace-identity-foundation/qa-override.md`.

**Approach:** Per-method incremental rollout (pattern proven in feature
108). Each cluster ships as 1–2 commits; `./validate.sh` and the scoped
pytest package suite are green at every commit.

---

## Problem Statement

After feature 108 shipped Migration 11 (`workspace_uuid` identity
foundation) and v4.17.0, the production surface still carries the
legacy transition shim:

1. `detect_project_id` function still resolves project IDs for 9
   files (1 definition + 5 production callers + 3 test callers). Spec
   FR-3 required 0 hits.
2. `_workspace_uuid` lazy global in `workflow_state_server.py` is
   populated at startup but never threaded through tool handlers — all
   workflow_state_server writes route via the deprecation shim instead
   of the canonical workspace_uuid path.
3. `ENTITY_PROJECT_ID` env-var override is still read; a corresponding
   test still exercises it.
4. `parent_type_id` kwarg is still accepted by 9+ production files and
   shipped via the `_resolve_workspace_uuid_kwargs` deprecation alias.
   Spec FR-9 AC-18 required 0 hits.
5. `parent_type_id` appears in **17 prose locations across 5 markdown
   files** — 3 commands + 2 skills (Task 6.12 markdown sweep not run).
6. `session-start.sh` and `mcp/entity_server.py` still render
   `${project_id}-${project_slug}` in user-visible context paths
   instead of the spec-mandated `${workspace_uuid_short}-${project_slug}`
   form.
7. Phase H validation artifacts were never produced — no
   `.qa-gate.json` walking the 41 ACs, no migration-timing test
   (AC-32), no bash 3.2 verification log (AC-34).

Until this cleanup ships, the deprecation alias path is the canonical
write path for workflow_state_server (acceptable but slow — JOINs
`workspaces.project_id_legacy` on every write); legacy env-var and SQL
column surfaces remain reachable; features 109/110/111 inherit broken
documentation.

---

## Success Criteria

- **SC-1** Backlog entries #00360–#00366 are closed with evidence
  (verification command + observed output) recorded in this feature's
  `.qa-gate.json` evidence column. AC-16 (annotation in `backlog.md`)
  is the surface marker; SC-1 is the evidence trail.
- **SC-2** Net production-code removal: `detect_project_id`,
  `ENTITY_PROJECT_ID`, `parent_type_id` kwarg path, `_project_id`
  lazy global from `entity_server.py`.
- **SC-3** `_workspace_uuid` is the canonical scoping field for every
  WRITE invocation (`register_entity` / `upsert_workflow_phase` /
  `update_entity`) from `workflow_state_server.py` and
  `entity_server.py`. Read handlers retain the cross-workspace
  semantics (see FR-2 audit table).
- **SC-4** `./validate.sh` and `entity_registry/` pytest both green at
  every commit (per-method incremental rollout).
- **SC-5** `docs/features/112-workspace-identity-cleanup/.qa-gate.json`
  walks all 41 ACs from feature 108 spec with `{ac_id, status,
  evidence, condition, backlog_ref}` per AC; status values restricted
  to the documented enum (see AC-9).

---

## Functional Requirements

### FR-1 — Delete `detect_project_id` and migrate 9 files (#00360)

**Pre-state file enumeration** (live grep verified at spec-time):

| # | File | Role | Migration target |
|---|------|------|------------------|
| 1 | `plugins/pd/hooks/lib/entity_registry/project_identity.py:499` | definition | DELETE function |
| 2 | `plugins/pd/mcp/entity_server.py:28,218` | import + caller | drop import; `_project_id` removal handled in FR-6 |
| 3 | `plugins/pd/mcp/workflow_state_server.py:36,213` | import + caller | drop import; replace caller per FR-2 wiring |
| 4 | `plugins/pd/hooks/lib/workflow_engine/task_promotion.py:18,335` | import + caller | replace with `resolve_workspace_uuid` |
| 5 | `plugins/pd/hooks/lib/doctor/fix_actions.py:332,334` | lazy import + caller | replace with `resolve_workspace_uuid` |
| 6 | `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py:23,112` | import + caller | replace with `resolve_workspace_uuid` |
| 7 | `plugins/pd/hooks/lib/entity_registry/test_project_identity.py` — `TestDetectProjectId` class spanning lines 68+ (full grep at FR-time; current hits at lines 68, 73, 77, 79, 83, 86, 89, 90, 97, 120, 132, 141, 144, 149+) | tests | rename to target `resolve_workspace_uuid`; delete removed-function tests |
| 8 | `plugins/pd/hooks/lib/entity_registry/test_entity_server.py:294,297,316` | tests | monkeypatch `resolve_workspace_uuid` instead |
| 9 | `plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py:30,31,33` | test fixture | monkeypatch `resolve_workspace_uuid` instead |

**Post-state:** Function deleted from `project_identity.py`.
`_compute_legacy_project_id` retained as a migration-only legacy helper
(callers that specifically need the pre-Migration-11 12-char hex form,
e.g. backfill paths reading `workspaces.project_id_legacy`).

**Verification (AC-1):** `grep -rn 'detect_project_id' plugins/pd/
--include='*.py'` returns 0 hits.

### FR-2 — Wire `_workspace_uuid` through `workflow_state_server` (#00361)

**Pre-state:** `plugins/pd/mcp/workflow_state_server.py:102` defines
`_workspace_uuid: str = ""` populated at lifespan. The value is never
read elsewhere in the file. All `register_entity` / `upsert_workflow_phase`
calls from this server pass `project_id` only.

**Per-handler audit table** (operationalises R-2 read/write asymmetry).
At FR-time, re-grep `@mcp.tool()` decorated functions in
`workflow_state_server.py` and classify each per this contract:

| Classification | Behaviour at write call | Behaviour at read call |
|---|---|---|
| `write` | MUST pass `workspace_uuid=_workspace_uuid or None` | N/A |
| `read` (single-workspace default, `*` = all) | N/A | MUST NOT pass `workspace_uuid` when `project_id == "*"`; otherwise pass it |
| `read+write` | Apply both rules per call site | Apply both rules per call site |

**FR sub-item — Promote `_resolve_optional_workspace_filter`.**
Verify `_resolve_optional_workspace_filter` is currently defined in
`entity_registry/database.py:2843` (it is — feature 108 introduced it
as the read-path counterpart to `_resolve_workspace_uuid_kwargs`).
Read handlers route their workspace filter through this helper,
which already returns `None` (no filter) when `project_id == "*"`.

**Post-state deliverable:** A handler classification table committed
to `docs/features/112-workspace-identity-cleanup/handler-audit.md`
listing every `@mcp.tool()` in `workflow_state_server.py` with its
classification, and per-call-site verification of the rules above.
**Sequencing:** `handler-audit.md` MUST be produced during the design
phase (or at minimum before FR-2 code changes begin), so the engineer
has the classification in hand when authoring the AC-8 pre-test (TDD
red phase).

**Pattern reference:** `plugins/pd/mcp/entity_server.py:151,530`
(`_upsert_project` and `register_entity`) demonstrate the write-path
forwarding.

**Verification (AC-7, AC-8):** Per AC-7 manual grep + AC-8 integration
test (see Acceptance Criteria).

### FR-3 — Remove `ENTITY_PROJECT_ID` env-var (#00362)

**Pre-state:** `plugins/pd/hooks/lib/entity_registry/project_identity.py:512`
reads `os.environ.get("ENTITY_PROJECT_ID")` as a project_id override.
`test_project_identity.py:140` exercises it.

**Post-state:** Env-var read deleted. The legacy test is converted to
`test_resolve_workspace_uuid_env_override` and exercises
`ENTITY_WORKSPACE_UUID` (already supported by `resolve_workspace_uuid`
step 1).

**Verification (AC-2):** `grep -r 'ENTITY_PROJECT_ID' plugins/pd/`
returns 0 hits.

**Verification (AC-2b):** `test_resolve_workspace_uuid_env_override`
exists in `test_project_identity.py`, asserts that setting
`ENTITY_WORKSPACE_UUID=<uuid>` overrides the resolution path, and
passes (`PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python
-m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py
-k test_resolve_workspace_uuid_env_override`).

### FR-4 — Drop `parent_type_id` kwarg from production callers (#00363)

**Pre-state:** Production files pass `parent_type_id=` kwarg to
`register_entity` / `register_entities_batch`. The
`_resolve_workspace_uuid_kwargs` shim in
`entity_registry/database.py` accepts both `parent_type_id` and
`parent_uuid`.

**Files to migrate (live grep at spec-time):**
- `plugins/pd/mcp/entity_server.py:435,449,561,1119,1126`
- `plugins/pd/hooks/lib/workflow_engine/task_promotion.py:346`
- `plugins/pd/hooks/lib/entity_registry/server_helpers.py:262,439,457`
- `plugins/pd/hooks/lib/entity_registry/frontmatter_inject.py:227,236`
- `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py:501,545,548,553,556,658,668,746,756,800`
- `plugins/pd/hooks/lib/workflow_engine/reconciliation.py:50,314,331`

**Post-state:** Every call resolves the parent reference to a UUID at
the call site (via `db.resolve_ref(parent_type_id_string)` or a
pre-resolved uuid from the caller).

**Implementation note:** `frontmatter_sync.py` and
`frontmatter_inject.py` use `parent_type_id` in MULTIPLE forms — kwarg
calls, dict-key writes (`{'parent_type_id': value}` in markdown
frontmatter payloads), and dict-key reads. The FR-time engineer audits
ALL forms per file and replaces with `parent_uuid` analogues; markdown
frontmatter payloads that historically carried `parent_type_id` keys
are rewritten to `parent_uuid` keys with a one-line schema bump (no
backward compat per NFR-1).

**Verification (AC-3 strict):** `grep -nE 'parent_type_id\s*=' plugins/pd/
--include='*.py' | grep -vE '^[^:]+:[^:]+:\s*#'` returns 0 hits in
production code (test fixtures using legacy schemas excluded).

**Verification (AC-3b dict-key):** `grep -rnE "['\"]parent_type_id['\"]"
plugins/pd/ --include='*.py' | grep -vE '^[^:]+:[^:]+:\s*#'` returns 0
hits in production code.

**Verification (AC-3c shim removal):** The
`_resolve_workspace_uuid_kwargs` shim in `database.py` drops its
`parent_type_id` resolution branch; the kwarg signature is removed
from `register_entity` and `register_entities_batch`; the
`DeprecationWarning` emitter path for the parent_type_id alias is
deleted. Verified via `grep -n 'parent_type_id'
plugins/pd/hooks/lib/entity_registry/database.py` returning 0 hits
outside of historical Migration-8/9/10/11 migration bodies (which
retain references for SQL DDL backward-time accuracy).

### FR-5 — Markdown sweep of `parent_type_id` (#00364) — **17 hits / 5 files**

**Pre-state (live grep at spec-time):**

| File | Lines |
|------|-------|
| `plugins/pd/commands/create-feature.md` | 194, 211, 212, 213, 214, 224 (6 hits) |
| `plugins/pd/commands/secretary.md` | 517, 796, 797, 798, 820, 830 (6 hits) |
| `plugins/pd/commands/create-project.md` | 95, 121 (2 hits) |
| `plugins/pd/skills/brainstorming/SKILL.md` | 281, 291 (2 hits) |
| `plugins/pd/skills/decomposing/SKILL.md` | 248 (1 hit) |

**Total:** 17 hits across 5 markdown files.

**Post-state:** All 17 prose hits replaced with `parent_uuid` +
type_id-resolution prose, matching post-Mig-11 semantics. Each
replacement reads naturally — instructions to set a parent now read
"resolve the parent type_id via `db.resolve_ref()`, then pass
`parent_uuid=<resolved-uuid>`" or equivalent for prose contexts.

**Out-of-scope retention:** `CHANGELOG.md`, `docs/backlog.md` historical
entries, `docs/features/108-*/` artifacts, and `docs/features/112-*/`
itself retain their references (legacy migration history is permitted).

**Verification (AC-4):** `grep -rn 'parent_type_id'
plugins/pd/commands/ plugins/pd/skills/ --include='*.md'` returns 0
hits.

### FR-6 — FR-10 (project_id rendering) cleanup (#00365)

**Scope narrowing (post-iter-1 plan review):** Live grep
(`grep -c _project_id plugins/pd/mcp/entity_server.py`) returns 48
occurrences across read filters, `_effective_project_id()`, all
`_resolve_ref_param` call sites, all read handlers, etc. Removing the
`_project_id` lazy global from `entity_server.py` is its own
multi-day refactor and exceeds this feature's per-method incremental
budget. **Deferred to follow-up feature 113 (or later) and filed as
backlog #00389**.

This feature's FR-6 narrows to the session-start render change
+ removing the `detect_project_id`-based assignment in
`entity_server.py:218` (the line itself stays; the call switches to
`_compute_legacy_project_id` for value parity).

**Pre-state (narrowed):**
- `plugins/pd/hooks/session-start.sh:129` reads
  `meta.get('project_id', '')`.
- `session-start.sh:463-485` renders `${project_id}-${project_slug}` in
  the user-visible context string.
- `plugins/pd/mcp/entity_server.py:218` populates `_project_id` via
  `detect_project_id(_project_root)` — this is the line FR-1 cannot
  remove without breaking 48 callers.

**Post-state (narrowed):**
- `session-start.sh:129` reads `meta.get('workspace_uuid', '')`.
- `session-start.sh:463-485` renders
  `workspace_uuid_short=${WORKSPACE_UUID:0:8}` then
  `${workspace_uuid_short}-${project_slug}`.
- `entity_server.py:218` `_project_id = detect_project_id(_project_root)`
  → `_project_id = _compute_legacy_project_id(_project_root)`
  (same value, drops the `detect_project_id` dependency, retains
  the 48 read-path callers unchanged for follow-up feature).
- `entity_server.py:55` declaration UNCHANGED (deferred to backlog
  #00389).
- `entity_server.py:531` `_project_id` usage UNCHANGED (deferred).

**Out of scope (this feature):** Removing the `_project_id` lazy
global from `entity_server.py:55,531` and migrating all 48 read-path
callers to use `_workspace_uuid` directly. Filed as backlog #00389.

**Verification (AC-5):** `grep -nE '\bproject_id\b'
plugins/pd/hooks/session-start.sh` returns hits only inside the
migration step (Migration 11 source comments) and the legacy
projects-table operations; no live read paths reference `project_id`.

**Verification (AC-6, narrowed):**
`grep -nE '^_project_id\s*[:=]|\b_project_id\s*=\s*detect_project_id|\b_project_id\s*=\s*resolve_workspace_uuid' plugins/pd/mcp/entity_server.py`
returns 0 hits (the lazy-global declaration AND assignment patterns
are gone). Prose mentions inside docstrings and comments are
permitted residuals.

### FR-7 — Phase H validation artifacts (#00366)

**Pre-state:** Feature 108's Phase H (Tasks 8.1–8.10) was deferred. No
`agent_sandbox/2026-05-10/108-validation/` directory; no
`.qa-gate.json` walking all 41 ACs; no `test_migration_11_runtime`
timing test; no `bash --version` verification log.

**Post-state:**
- `agent_sandbox/{today}/112-validation/` contains per-package pytest
  logs (entity-registry, doctor, recon-orch, workflow-engine, mcp,
  ui), `hooks-tests.log`, `validate.log`, `bash-version.log`,
  `baseline.log` (pinned baseline per NFR-2).
- `docs/features/112-workspace-identity-cleanup/.qa-gate.json` walks
  all 41 ACs from feature 108 spec.md per the schema in AC-9.
- A new test `test_migration_11_runtime` runs Migration 11 against a
  **500-row** synthetic dataset (matching feature 108 AC-32 baseline)
  and asserts wall clock < 30 s; LOGS a WARNING via `pytest.warns(...)`
  if > 2 s. **No CI flakiness carve-out.** A separate documented
  stress benchmark (NOT gated on) runs N=10000 entities for
  performance characterisation only.
- `bash-version.log` captures (a) `bash --version`, (b) `/bin/bash
  --version`, AND (c) the result of `bash plugins/pd/hooks/tests/test-hooks.sh`
  run with `/bin/bash` explicitly. If the host shell is bash 4+
  (common on macOS via Homebrew), the log states the skip-then-rerun
  rationale and confirms `/bin/bash` is 3.2 (macOS system bash).

**Verification (AC-9, AC-10, AC-11, AC-12):** see Acceptance Criteria.

---

## Acceptance Criteria

### Block A — Code removal (verification by grep)

- **AC-1** `grep -rn 'detect_project_id' plugins/pd/ --include='*.py'`
  returns 0 hits after FR-1.
- **AC-2** `grep -rn 'ENTITY_PROJECT_ID' plugins/pd/ --include='*.py'`
  returns 0 hits after FR-3. (CHANGELOG/historical markdown references
  outside `plugins/pd/` are out of scope; CHANGELOG retains the
  removal note.)
- **AC-2b** `test_resolve_workspace_uuid_env_override` exists in
  `plugins/pd/hooks/lib/entity_registry/test_project_identity.py`,
  asserts that setting `ENTITY_WORKSPACE_UUID=<uuid>` overrides the
  resolution path, and passes via the scoped pytest invocation in
  FR-3 verification.
- **AC-3** `grep -nE 'parent_type_id\s*=' plugins/pd/ --include='*.py' |
  grep -vE '^[^:]+:[^:]+:\s*#'` returns 0 hits in production code
  (test fixtures using legacy schemas excluded).
- **AC-3b** `grep -rnE "['\"]parent_type_id['\"]" plugins/pd/
  --include='*.py' | grep -vE '^[^:]+:[^:]+:\s*#'` returns 0 hits in
  production code.
- **AC-3c** `grep -n 'parent_type_id'
  plugins/pd/hooks/lib/entity_registry/database.py` returns hits only
  inside historical Migration-8/9/10/11 migration bodies (no
  references in the live shim path).
- **AC-4** `grep -rn 'parent_type_id' plugins/pd/commands/
  plugins/pd/skills/ --include='*.md'` returns 0 hits after FR-5.
- **AC-5** `grep -nE '\bproject_id\b'
  plugins/pd/mcp/entity_server.py plugins/pd/hooks/session-start.sh`
  returns hits only inside Migration 11 source / legacy projects-table
  operations after FR-6.
- **AC-5b** `grep -n 'workspace_uuid_short' plugins/pd/hooks/session-start.sh`
  returns at least one hit in the 460–490 line range (the renamed
  context-string render path).
- **AC-6 (narrowed)** `grep -nE '\b_project_id\s*=\s*detect_project_id' plugins/pd/mcp/entity_server.py`
  returns 0 hits after FR-6. The `_project_id` declaration at line 55
  is RETAINED (scope deferred to feature 113 / backlog #00389). The
  detect_project_id-based assignment is replaced with
  `_project_id = _compute_legacy_project_id(_project_root)`.

### Block B — `_workspace_uuid` canonical scoping (FR-2)

- **AC-7** Every `db.register_entity` /
  `db.upsert_workflow_phase` / `db.update_entity` (WRITE) call from
  `plugins/pd/mcp/workflow_state_server.py` passes
  `workspace_uuid=_workspace_uuid or None` as kwarg. Read handlers in
  the same file route their workspace filter through
  `_resolve_optional_workspace_filter` and do NOT pass
  `workspace_uuid` when `project_id == "*"`.
- **AC-7b** The handler-audit deliverable
  `docs/features/112-workspace-identity-cleanup/handler-audit.md`
  exists and lists every `@mcp.tool()` in
  `workflow_state_server.py` with its classification (write / read /
  read+write) and the matching FR-2 rule applied per call site.
- **AC-8** A new integration test in
  `plugins/pd/mcp/test_workflow_state_server.py` asserts that an
  entity registered via the MCP tool ends up scoped to the active
  workspace (`SELECT workspace_uuid FROM entities WHERE type_id = '...'`
  returns `_workspace_uuid` after bootstrap). Test is added in the
  same commit as FR-2's wiring changes; pre-test FAILS, post-fix
  PASSES (TDD).

### Block C — Validation artifacts (FR-7)

- **AC-9** `docs/features/112-workspace-identity-cleanup/.qa-gate.json`
  exists, parses as valid JSON, contains exactly 41 entries (one per
  feature 108 AC). Each entry conforms to the schema:
  ```json
  {
    "ac_id": "AC-{N}",
    "status": "passed" | "deferred" | "n_a" | "conditional_skipped",
    "evidence": {
      "command": "<verification command>",
      "output_excerpt": "<observed result>",
      "file_ref": "<path:line>"  // optional
    },
    "condition": "F6_gate_failed" | "bash_4plus_host" | null,
    "backlog_ref": "NNNNN" | null
  }
  ```
  Constraints:
  - Every entry has non-empty `evidence` OR a non-null `backlog_ref`
    OR a non-null `condition` from the documented enum.
  - F6-gated ACs (AC-24, AC-25, AC-33 per feature 108 spec) MUST
    have `status="conditional_skipped"` and `condition="F6_gate_failed"`
    while backlog #00359 is open.
  - `bash_4plus_host`-conditional ACs MUST have
    `status="conditional_skipped"` and `condition="bash_4plus_host"`
    on dev machines where `/bin/bash` is not 3.2.
- **AC-10** `agent_sandbox/{today}/112-validation/` contains
  `entity-registry-pytest.log`, `doctor-pytest.log`,
  `mcp-pytest.log`, `workflow-engine-pytest.log`,
  `recon-orch-pytest.log`, `ui-pytest.log`, `hooks-tests.log`,
  `validate.log`, `bash-version.log`, `baseline.log`. All files
  non-empty.
- **AC-11** `test_migration_11_runtime` (with this exact name) exists
  in `plugins/pd/hooks/lib/entity_registry/test_database.py`, runs
  Migration 11 against a 500-row
  synthetic dataset (matching feature 108 AC-32 baseline), and
  asserts wall clock < 30 s. It emits a `pytest.warns(...)` or
  equivalent warning when > 2 s. There is **no CI-flakiness
  skip mechanism**; the assertion is the hard gate. A separate
  stress benchmark (`test_migration_11_stress_benchmark`) running
  N=10000 is included but uses `@pytest.mark.benchmark` (not gated on
  in `./validate.sh`).
- **AC-12** `bash-version.log` captures all three lines:
  1. Host shell `bash --version`.
  2. System `/bin/bash --version`.
  3. The exit code and tail-output of `/bin/bash
     plugins/pd/hooks/tests/test-hooks.sh` (run explicitly with
     `/bin/bash`).
  If the host shell is bash 4+ AND `/bin/bash` is bash 3.2, the log
  documents this with the explicit rerun result. AC-12 is satisfied
  only when line 3 exits 0 against bash 3.2 (macOS system bash) —
  evidence-of-conformance, not evidence-of-existence.

### Block D — Per-method rollout discipline

- **AC-13** Every commit in this feature passes `./validate.sh`
  (Errors: 0).
- **AC-14** Every commit in this feature passes the scoped pytest
  package suite for the package(s) touched by that commit. Cross-cutting
  commits run the full plugin suite (`plugins/pd/.venv/bin/python -m
  pytest plugins/pd/`) and the result is checked against `baseline.log`
  (per NFR-2) for net-new failures.
- **AC-15** Each FR's commits document the file:line mapping for the
  migration in the commit message body (per feature 108 retro's
  per-method rollout pattern).

### Block E — Backlog reconciliation

- **AC-16** Backlog entries #00360–#00366 are closed (annotated with
  `(fixed in feature:112-workspace-identity-cleanup)` in the
  Description column of `docs/backlog.md`).
- **AC-17** MED findings #00367–#00388 are each evaluated against this
  feature's commits. For each entry, exactly one of:
  - (a) closes with a commit reference in this feature's diff (commit
    SHA + brief diff hunk), OR
  - (b) closes with a verification command showing the issue is
    already resolved (command + observed-output that demonstrates the
    pre-condition no longer holds), OR
  - (c) remains open with rationale ≥2 sentences AND a target feature
    number where it WILL be closed (e.g. "deferred to feature 113
    because [reason]; closure path is [path]").

  Bare "deferred" or "not in scope" is NOT acceptable; option (c)
  requires both a rationale and a target.

---

## Non-Functional Requirements

- **NFR-1 (No backward compatibility):** This feature deletes legacy
  surface. No deprecation aliases, no shims, no compat flags. The
  `_resolve_workspace_uuid_kwargs` `parent_type_id` branch is deleted
  outright in FR-4.

- **NFR-2 (Test parity, pinned baseline):** Before any FR-cluster
  commit lands, run `PYTHONPATH=plugins/pd/hooks/lib
  plugins/pd/.venv/bin/python -m pytest plugins/pd/` at the feature
  112 branch root commit. Capture pass/fail count + failing test_ids
  into `agent_sandbox/{today}/112-validation/baseline.log`. NFR-2 is
  satisfied iff post-implementation run shows no test_id transitioning
  from pass→fail vs `baseline.log`. New test_ids added by this feature
  must pass.

- **NFR-3 (Per-method rollout):** Commits are sequenced one FR cluster
  at a time. Cross-cluster changes are explicitly identified and
  rationalised in commit messages.

- **NFR-4 (Migration 11 invariants intact):** Migration 11's reverse
  migration and byte-identical round-trip artifact remain unchanged.
  This feature does not touch Migration 11 forward or reverse logic.

- **NFR-5 (Doc sync):** README, README_FOR_DEV, and CHANGELOG entries
  are updated for every user-visible surface change. Expected
  CHANGELOG entries (Keep-a-Changelog format under `[Unreleased]`):
  1. **Removed:** `ENTITY_PROJECT_ID` env-var override (FR-3).
  2. **Removed:** `parent_type_id` kwarg from
     `EntityDatabase.register_entity` and `register_entities_batch`
     (FR-4).
  3. **Changed:** session-start context path format from
     `${project_id}-${project_slug}` to
     `${workspace_uuid_short}-${project_slug}` (FR-6).
  4. **Changed:** `list_features_by_phase` and
     `list_features_by_status` MCP tools default to single-workspace
     queries (post-FR-2). Pass `project_id="*"` to opt into the
     legacy cross-workspace behavior.

---

## Out of Scope

- Feature 109 polymorphic taxonomy + event sourcing.
- Feature 110 markdown projections from DB.
- Feature 111 issue lifecycle closure.
- Migration 12+ schema changes.
- The 14 LOW QA-gate findings in
  `docs/features/108-workspace-identity-foundation/.qa-gate-low-findings.md`
  beyond what overlaps with the 7 clusters above. (LOW items stay in
  sidecar; this feature does NOT explicitly close them.)
- F6 (UUIDv7) adoption (backlog #00359 — blocked on pyproject floor
  bump, separate feature). F6-conditional ACs (AC-24, AC-25, AC-33
  per feature 108 spec) inherit `status="conditional_skipped"` in
  the AC-9 schema while #00359 remains open.
- **`_project_id` lazy global removal** from
  `plugins/pd/mcp/entity_server.py:55,531` and the 48 read-path
  callers (`_effective_project_id()`, `_resolve_ref_param` call
  sites, read handlers, `_backfill_project_ids`). Filed as backlog
  **#00389** — post-iter-1 plan-review scope narrowing. This
  feature's FR-6 narrows to: (a) `session-start.sh` render change,
  (b) `entity_server.py:218` switch from `detect_project_id` to
  `_compute_legacy_project_id` (drops the dependency, retains the
  value semantics).

---

## Risks and Mitigations

- **R-1: parent_uuid resolution explosion at call sites.** Callers
  currently pass `parent_type_id="feature:..."` and the shim resolves
  via JOIN. Pushing resolution to the call site multiplies the number
  of resolve_ref() calls in hot paths (e.g., `reconciliation.py`
  loops). **Mitigation:** Batch-resolve at function entry, not per-row,
  using `_resolve_identifier` or `db.scan_entity_ids`. Document in
  design phase.

- **R-2: workflow_state_server read/write asymmetry mishandling.**
  Tool handlers that legitimately query across workspaces (e.g.,
  `list_features_by_phase` with `project_id="*"`) must NOT pass
  `_workspace_uuid` as a filter. **Mitigation:** FR-2's per-handler
  audit table (deliverable `handler-audit.md`) operationalises the
  classification. Read handlers route through
  `_resolve_optional_workspace_filter`; write handlers through
  `_resolve_workspace_uuid_kwargs`.

- **R-3: `parent_type_id` markdown sweep changes user-facing
  workflow command behavior.** If `create-feature.md` instructs
  callers to use `parent_type_id`, those callers must be updated too.
  **Mitigation:** Audit who reads these command files (claude-code +
  agents) and update Task tool prompts in lockstep. The 17-hit list
  in FR-5 includes the skill files (`brainstorming/SKILL.md`,
  `decomposing/SKILL.md`) which are the upstream prose definitions.

- **R-4: Phase H validation may surface pre-existing test failures
  unrelated to this feature.** The wider plugin suite has 4
  pre-existing failures in `semantic_memory::TestMergeDuplicatePromotion`.
  **Mitigation:** NFR-2 pinned baseline (AC-14) makes net-new-failure
  accounting deterministic regardless of develop drift.

- **R-5: AC-11 migration timing gate.** Per the resolved spec, AC-11
  is the hard gate (500-row dataset, fail >30s, warn >2s — mirrors
  feature 108 AC-32). No skip carve-out. If timing exceeds 30s on
  the dev machine, the design phase MUST surface migration
  performance work as a sub-task. The 10k-row stress benchmark is
  separately tagged `@pytest.mark.benchmark` and not gated.

- **R-6: FR-4 frontmatter_sync.py / frontmatter_inject.py dict-key
  payloads.** These files use `parent_type_id` in markdown frontmatter
  payloads, not just kwargs. **Mitigation:** AC-3b explicitly checks
  dict-key form. Schema bump (no backward compat per NFR-1) requires
  consumer audit — design phase enumerates frontmatter consumers and
  updates them in lockstep.

---

## Validation Plan

After all 7 FRs land:

1. Run `./validate.sh` — expect: Errors: 0.
2. Run `bash plugins/pd/hooks/tests/test-hooks.sh` — expect: 114/114
   passed (or current baseline at FR-7 start).
3. Run scoped pytest per package, capturing logs into
   `agent_sandbox/{today}/112-validation/` (FR-7 / AC-10).
4. Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/` → diff
   pass/fail set against `baseline.log` (NFR-2 / AC-14).
5. Generate `.qa-gate.json` walking all 41 ACs per AC-9 schema (FR-7 /
   AC-9).
6. Run the new migration-timing test (FR-7 / AC-11). Run the
   benchmark separately for documentation.
7. Capture `bash-version.log` per AC-12 (FR-7 / AC-12).
8. Manual grep verification per AC-1, AC-2, AC-3, AC-3b, AC-3c, AC-4,
   AC-5, AC-6.
9. Update `docs/backlog.md` annotating #00360–#00366 per AC-16; record
   MED evaluations per AC-17 in `retro.md`.
