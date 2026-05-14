# Design — Feature 110: Markdown Projections and Generalized Guards

- **Project:** P003-entity-system-redesign M3
- **Spec:** docs/features/110-markdown-projections-and-gener/spec.md (rev 4)
- **Schema baseline:** post-migration-12 (entities has type/kind/lifecycle_class, no entity_type)
- **Status:** revision 3 (iter-2: 3 factual blockers + 3 warnings resolved inline; cap-3 reached at design-reviewer)

## §0 Prior Art Research — including AST orthogonality with feature-109

**AST orthogonality with feature-109's `check_status_write_path`:** Feature 109's AST check audits SQL writes against `_PERMITTED_ENCLOSING_DEFS = {append_phase_event, upsert_workflow_phase, update_workflow_phase, create_workflow_phase, update_entity, check_status_write_path}`. Feature 110's `test_audit_writes.py` audits `.meta.json` file writes against `{_project_meta_json, _write_meta_json_fallback, init_project_state}`. **Orthogonality verified:**
- `_project_meta_json` reads entities only (no UPDATE/INSERT to entities/workflow_phases/phase_events) → does NOT trigger feature-109 check.
- `append_phase_event` writes only to `entities` (status update) + `phase_events` (event row) — does NOT write to `.meta.json` → does NOT trigger feature-110 check.
- The two allow-lists are disjoint by construction; no function appears in both, no cross-list conflict.

The two AST walks may be consolidated in a future refactor (parse files once, run two assertion sets) but design 110 keeps them separate for clarity. Plan-phase adds an explicit AC verifying orthogonality is maintained.

**Spec rev-4 corrections re-verification scrutiny:** Spec rev-4 added 3 inline post-iter-3 fixes (fnmatch revert, migration_audit_log, NOT NULL columns) WITHOUT a 4th adversarial spec-review iteration. Design phase applies extra scrutiny:
- (a) fnmatch `*` semantics — verified empirically in TD-1 matrix; probe script `plugins/pd/hooks/tests/probe_fnmatch.py` (new) commits the test cases.
- (b) `phase_events` CHECK constraint — verified at `database.py:3402-3406` per spec-reviewer iter-3 finding; 7 values are `{started, completed, skipped, backward, entity_created, entity_status_changed, entity_promoted}`. Migration 13's `migration_audit_log` table avoids needing to widen this. No further verification needed.
- (c) NOT NULL columns — N/A: migration_audit_log replaces phase_events for forensic logging; the NOT NULL gaps on phase_events are bypassed entirely.



**Codebase precedents (no external research needed — patterns established):**

| Pattern needed | Existing precedent (source-of-truth) |
|---|---|
| SQLite migration with single-tx + FK check | `database.py:2617` `_migration_12_polymorphic_taxonomy_and_events` — model for migration 13 single-tx scaffold + `PRAGMA foreign_key_check` pre/post + idempotency double-check. |
| Down-migration runtime-only restore | `database.py:3506-3939` `_migration_12_polymorphic_taxonomy_and_events_down` — model for `MIGRATIONS_DOWN[13]`. |
| Per-table copy-rename for CHECK/constraint changes | `database.py:3329-3406` migration-12 widened the `phase_events.event_type` CHECK via copy-rename. We do NOT need this in migration 13 (new `entity_display` table is fresh; no existing CHECK to widen). |
| AST-based hook checks | `plugins/pd/hooks/lib/doctor/check_status_write_path.py` (feature 109) — model for AC-1.1 `test_audit_writes.py` AST walk. |
| Bash-from-Python venv loading in hooks | `plugins/pd/hooks/lib/session-start-helpers.sh` — model for FR-7.2 `data-file-guard.sh` venv bootstrap. |
| Hook tests (BATS-like bash) | `plugins/pd/hooks/tests/test-hooks.sh` — model for new `test-data-file-guard.sh`. |
| Doctor check registry | `plugins/pd/hooks/lib/doctor/__init__.py` `CHECK_ORDER` (feature 109 added `check_status_write_path` at position 15) — model for any new doctor checks. |
| Static-grep / projection idempotency tests | Multiple existing patterns in `plugins/pd/hooks/lib/entity_registry/test_*.py`. |

No third-party library research needed: stdlib `fnmatch`, `pathlib`, `ast`, `sqlite3`, `hashlib`, `importlib`, `subprocess` cover all requirements per spec NFR-2.

## §1 Architecture Overview

Feature 110 lands three loosely-coupled sub-features under a single feature directory:

```
┌─────────────────────────────────────────────────────────────┐
│ F4 — Sealed projection write path                            │
│                                                              │
│   DB (entities, phase_events, workflow_phases, backlog rows) │
│           │           │                                      │
│           ▼           ▼                                      │
│   _project_meta_json _project_backlog_md (new)              │
│           │           │                                      │
│           ▼           ▼                                      │
│   {feature}/.meta.json  docs/backlog.md  (gitignored)       │
│                                                              │
│   pd_state_diff.py reads DB at HEAD + base → pd-state.diff.md│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ F7 — Generalized data-file guard                             │
│                                                              │
│   Write/Edit tool call → PreToolUse                          │
│           │                                                  │
│           ▼                                                  │
│   data-file-guard.sh (bash entry)                            │
│     1. source session-start-helpers.sh (load venv)           │
│     2. python3 -m data_file_guards.dispatcher                │
│           │                                                  │
│           ▼                                                  │
│   dispatcher reads data_file_guards.json                     │
│     for each entry: fnmatch(file_path, pattern) &&           │
│                     not any(fnmatch(file_path, excl))        │
│     on match: importlib.import_module(decision_module)       │
│                .decide(file_path, tool_name, payload)        │
│           │                                                  │
│           ▼                                                  │
│   hookSpecificOutput.permissionDecision = deny|allow         │
│                                                              │
│   (replaces plugins/pd/hooks/meta-json-guard.sh)             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ F8 — entity_display table                                    │
│                                                              │
│   entities.uuid (PK)                                         │
│       │                                                      │
│       │ 1:1 FK ON DELETE CASCADE                             │
│       ▼                                                      │
│   entity_display(uuid, seq, slug)                            │
│       + idx_entity_display_seq                               │
│                                                              │
│   Migration 13 backfills from entities.entity_id parse       │
│   after pre-audit confirms entity_id ↔ metadata['slug'] match│
│   or env-gated bypass with migration_audit_log forensic row  │
└─────────────────────────────────────────────────────────────┘
```

## §2 Components

### 2.1 New Python modules

| Path | Purpose | Public API |
|---|---|---|
| `plugins/pd/scripts/pd_state_diff.py` | CLI: emit markdown diff of entity state HEAD vs base. | `python -m pd_state_diff --base <branch>` → stdout markdown |
| `plugins/pd/hooks/lib/data_file_guards/__init__.py` | Package init. | (empty) |
| `plugins/pd/hooks/lib/data_file_guards/dispatcher.py` | Read stdin, iterate config, route to decision module. | `python -m data_file_guards.dispatcher` (reads stdin JSON, writes hook JSON to stdout) |
| `plugins/pd/hooks/lib/data_file_guards/meta_json_decision.py` | Replaces meta-json-guard.sh logic. | `decide(file_path, tool_name, payload) → dict {permissionDecision, reason}` |
| `plugins/pd/hooks/lib/data_file_guards/backlog_decision.py` | New: deny direct backlog.md writes. | Same signature. |
| `plugins/pd/hooks/lib/doctor/test_audit_writes.py` | AST tests for AC-1.1 + AC-1.2. | pytest test file |
| `plugins/pd/hooks/lib/entity_registry/test_entity_display_table.py` | Integration tests for FR-8. | pytest test file |
| `plugins/pd/hooks/lib/entity_registry/test_migration_13_safety.py` | Migration safety tests. | pytest test file |
| `plugins/pd/hooks/lib/entity_registry/test_projection_determinism.py` | AC-4 byte-equality tests. | pytest test file |
| `plugins/pd/hooks/lib/entity_registry/test_pd_state_diff.py` | AC-6 tests. | pytest test file |
| `plugins/pd/hooks/lib/entity_registry/test_gitignore_drift.py` | AC-1.4/1.5 tests. | pytest test file |

### 2.2 New / modified shell scripts

| Path | Change |
|---|---|
| `plugins/pd/hooks/data-file-guard.sh` | **New.** Single dispatch entrypoint per FR-7.2. |
| `plugins/pd/hooks/meta-json-guard.sh` | **Deleted** per FR-7.3. |
| `plugins/pd/hooks/pre-commit-guard.sh` | **Modified** per FR-4.6 — append pd-state.diff.md generation block after existing branch-protection logic. |
| `plugins/pd/hooks/tests/test-data-file-guard.sh` | **New.** Migrates four meta-json-guard tests + adds hot-add fixture tests. |
| `plugins/pd/hooks/tests/test-hooks.sh` | **Modified.** Remove the four meta-json-guard tests (migrated to test-data-file-guard.sh). |
| `plugins/pd/hooks/tests/fixtures/test_data_file_guards.json` | **New.** Hot-add config fixture for AC-7.5. |
| `plugins/pd/hooks/tests/fixtures/fixture_guard.py` | **New.** Test-only decision module. |

### 2.3 Modified Python modules (sealed write path)

| Path | Change |
|---|---|
| `plugins/pd/mcp/workflow_state_server.py` | Add `_project_backlog_md(db) → str` (FR-4.2). Modify `_project_meta_json` to query `entity_display` table for `id`/`slug` (FR-8.3). |
| `plugins/pd/hooks/lib/entity_registry/database.py` | Add `_migration_13_entity_display(conn)` and `_migration_13_entity_display_down(conn)`. Register in `MIGRATIONS`/`MIGRATIONS_DOWN`. Modify `scan_entity_ids` to query `entity_display` (FR-8.3). |
| `plugins/pd/hooks/lib/entity_registry/backfill.py` | Replace `entity_id` parsing with `entity_display` queries. |
| `plugins/pd/hooks/lib/workflow_engine/engine.py` | Add `# F4-AUDIT: degraded-mode-only` comment near `_write_meta_json_fallback`. |
| `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py` | Add `# F4-AUDIT: project-type schema; ported to feature 111` near `init_project_state`. |
| `plugins/pd/hooks/lib/doctor/fix_actions.py` | **Corrected (iter-2):** Empirical SUT pin reveals TWO functions write `.meta.json`: `_fix_last_completed_phase` (line 52) AND `_fix_completed_timestamp` (line 87). BOTH replaced with MCP-invoking wrappers per TD-11. The backlog writer is `_fix_backlog_annotation` (line 149) — add `# F4-AUDIT: annotation-only` comment (annotation, not state mutation). FR-4.1 allow-list updated to include both fix-action symbol names. |
| `plugins/pd/skills/add-to-backlog.md` (command) | Replace direct `Write` call with: `register_entity(entity_type='backlog', ...)` then call to projection. |
| `plugins/pd/commands/finish-feature.md` Step 5b MED-finding emission | Same pattern: register backlog entries via DB then re-project. |
| `plugins/pd/scripts/cleanup_backlog.py` | **Modified, NOT removed.** (Design overrides spec FR-4.3 REMOVED directive — routes through `update_entity` MCP instead; spec to be updated at retro.) Continues to perform archival but ROUTES THROUGH existing `update_entity(type_id, status='archived')` MCP (precedent at `cleanup-brainstorms.md:78`). NO new MCP tool added. After archival, calls `_project_backlog_md` to regenerate `docs/backlog.md` (excludes `status='archived'` rows). |
| `plugins/pd/hooks/lib/entity_registry/database.py register_entity` | **Modified.** ALSO inserts into `entity_display(uuid, seq, slug)` parsing seq/slug from entity_id. Same transaction as the existing entities INSERT. Maintains AC-8.2 1:1 invariant for NEW entities post-migration-13. **Fail-fast precondition:** If `entity_id` does not match `^\d+-.+` regex (e.g., test fixtures with `entity_id='test-fixture'`), `register_entity` raises `EntityIdFormatError` BEFORE the entities INSERT (no partial state). `register_entities_batch` similarly modified. Plan-phase adds AC for this contract. Existing test fixtures with non-standard entity_ids must be migrated to the `{seq}-{slug}` format OR explicitly skip entity_display creation via a `_register_entity_no_display` test-only helper. |
| `plugins/pd/commands/show-status.md` | Update prose to reference `entity_display` (FR-8.3 skill update). |

### 2.4 Configuration files

| Path | Change |
|---|---|
| `plugins/pd/hooks/data_file_guards.json` | **New.** Two-entry config (`*.meta.json` with exclude_patterns, `docs/backlog.md`). |
| `plugins/pd/hooks/hooks.json` | **Modified.** Unregister `meta-json-guard.sh`, register `data-file-guard.sh`. |
| `.gitignore` | **Modified.** Append `**/.meta.json`, `docs/backlog.md`, `pd-state.diff.md`. |

## §3 Technical Decisions

### TD-1 — fnmatch over pathlib.match (Python 3.12 floor)

**Decision:** Use `fnmatch.fnmatch(file_path, pattern)` for pattern matching in dispatcher.

**Rationale:** Spec rev-4 corrected the iter-2/3 confusion. Python 3.12 (pd's `requires-python` floor per `pyproject.toml`) does NOT support `**` recursive globs in `pathlib.PurePath.match()` (`full_match()` is 3.13+). `fnmatch` treats `*` as any-char including `/`, so `*.meta.json` correctly matches `docs/features/043/.meta.json`. Excludes use the same semantics (`docs/projects/*/.meta.json` excludes project paths).

**Verified Behavior matrix** (per memory pattern "Inline Verified Behavior matrix"):

| Call | Returns | Notes |
|---|---|---|
| `fnmatch.fnmatch("docs/features/043/.meta.json", "*.meta.json")` | `True` | `*` matches the leading path component |
| `fnmatch.fnmatch("docs/projects/P003/.meta.json", "*.meta.json")` | `True` | Same — `*` is greedy |
| `fnmatch.fnmatch("docs/projects/P003/.meta.json", "docs/projects/*/.meta.json")` | `True` | Exclude triggers — guard skips this entry |
| `fnmatch.fnmatch("docs/backlog.md", "docs/backlog.md")` | `True` | Literal match |
| `fnmatch.fnmatch("docs/projects/P003/.meta.json", "docs/projects/*/*.meta.json")` | `False` | `*` does not span the leading `docs/projects/` prefix when `docs/projects/` is literal at start |

A probe script `plugins/pd/hooks/tests/probe_fnmatch.py` lives alongside `test-data-file-guard.sh` to allow future implementers to verify behavior empirically.

### TD-2 — Dedicated `migration_audit_log` table (not phase_events)

**Decision:** Migration 13 creates a dedicated table `migration_audit_log` for forensic events (mismatch_row, bypass_acknowledged).

**Rationale:** Spec rev-4 caught that `phase_events.event_type` CHECK only permits 7 values post-migration-12. Widening the CHECK in migration 13 would add scope and risk. A dedicated audit table keeps migration concerns contained.

**Schema:**
```sql
CREATE TABLE migration_audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  migration_version INTEGER NOT NULL,
  event_type TEXT NOT NULL,        -- 'mismatch_row' | 'bypass_acknowledged'
  payload TEXT NOT NULL,           -- JSON
  created_at TEXT NOT NULL         -- ISO 8601
);
```

No indexes (low-traffic table). No FK to entities (forensic survives entity deletion).

### TD-3 — sys.path.insert(0, ...) for decision module imports

**Decision:** Dispatcher prepends `PD_DATA_FILE_GUARDS_LIB` to `sys.path` (using `insert(0, ...)`, NOT `sys.path[0] = ...`), imports the module, then pops the inserted entry.

**Rationale:** Per spec FR-7.2 clarification. Prepend ensures override modules are found first; insert-not-overwrite preserves existing path semantics.

**Pseudocode:**
```python
import sys, importlib
from contextlib import contextmanager

@contextmanager
def prepended_path(p):
    sys.path.insert(0, p)
    try:
        yield
    finally:
        # Remove the first occurrence we inserted (safe: insert-then-pop[0])
        sys.path.pop(0)

def import_decision(module_name: str, lib_dir: str):
    with prepended_path(lib_dir):
        return importlib.import_module(module_name)
```

### TD-4 — Projection timestamps source from DB columns only

**Decision:** `_project_meta_json` and `_project_backlog_md` MUST source all timestamp fields from `entities.updated_at` / `entities.created_at`. No `datetime.utcnow()` / `datetime.now()` at projection time.

**Rationale:** Per spec FR-4.4 byte-determinism requirement. AC-4.1/4.2 enforces via static-check grep within the projection function bodies.

**Implementation pattern (existing `_project_meta_json`):** already sources `updated_at` from DB row — feature 110 verifies (does not change behavior here). The new `_project_backlog_md` follows the same pattern.

### TD-5 — pre-commit-guard.sh modification: append-after-existing pattern

**Decision:** Append the pd_state_diff.py invocation block AFTER the existing branch-protection logic in `pre-commit-guard.sh`. Failure of the diff script does NOT block the commit (exit 0 fail-open).

**Git edge cases enumerated** (per memory pattern "Enumerate Git Edge Cases in Design Technical Decisions"):

| Edge case | Handler |
|---|---|
| Base branch ref missing (fresh clone, no `develop` ref) | `pd_state_diff.py` exits 0 with stdout text `pd-state diff unavailable: base ref '{base}' not found`. AC-6.6 enforces. |
| First commit on a new repo (no `HEAD`) | `git diff` returns the entire tree; script handles by treating empty-base as empty entity-state. Emit `No entity state changes vs {base}`. |
| Merge commit with two parents | Diff against `merge-base(HEAD, base)`, not `HEAD~`. Use `git merge-base HEAD <base>` to resolve. |
| Detached HEAD | Resolve via `git rev-parse HEAD` (works in detached state). |
| Pre-commit hook fired during rebase / cherry-pick | Detect via `git rev-parse --git-dir`/`/REBASE_*` markers; skip diff generation (exit 0). |
| Symlinked `.git` directory (worktrees) | `git rev-parse --git-common-dir` resolves real .git. |
| DB connection failure | Print error to stderr, write `pd-state diff unavailable: DB connection failed` to file, exit 0. |
| Concurrent commit invocation (CI matrix) | File write uses `os.replace(tmp, final)` atomic rename to avoid torn writes. |

### TD-6 — Migration 13 pre-flight gate (3-check sequence)

**Decision:** Migration 13's pre-flight asserts all 3 conditions IN ORDER before any DDL:

1. `PRAGMA user_version` returns 12.
2. `SELECT MAX(version) FROM schema_version` returns 12 AND equals `user_version`.
3. `PRAGMA table_info(entities)` returns expected 14 columns with `entity_type` ABSENT, `type`/`kind`/`lifecycle_class` PRESENT.

**Distinct error messages per failed assertion:**

| Assertion failed | Error message |
|---|---|
| #1: `user_version != 12` | `Migration 13 aborted: user_version={N}, expected 12. Run feature-109 deferred remediation first.` |
| #2: `schema_version table / user_version pragma disagree` | `Migration 13 aborted: schema_version table version={M} disagrees with PRAGMA user_version={N}. Manual reconciliation required.` |
| #3: column layout mismatch | `Migration 13 aborted: entities table schema mismatch. Expected post-migration-12 layout. Detected entity_type={present/absent}, type={present/absent}. Run feature-109 deferred remediation first.` |

### TD-7 — Backfill SQL uses runtime PRAGMA table_info

**Decision:** Migration 13 backfill SQL begins with `PRAGMA table_info(entities)` and asserts presence of `uuid`, `entity_id`, `metadata` columns before any SELECT. No hardcoded column-list assumptions.

**Rationale:** Per memory KB anti-pattern "Hardcoded Schema Column Lists in Migration Steps" (feature 109).

### TD-7b — entity_id parsing audit (class-fix grep)

**Decision:** FR-8.3's 4-caller enumeration is the design-time identified scope; plan-phase MUST add an audit-task to grep for ALL `entity_id`-suffix-parsing call sites and classify each as (a) port to entity_display, (b) confirms out-of-scope (type_id parsing only, not seq/slug semantics), or (c) test fixture.

**Audit grep pattern** (for plan-phase task):
```bash
grep -rnE '\.split\(":"\)|\.partition\(":"\)|substr\(.*entity_id|instr\(.*entity_id|re\.match.*entity_id' \
  plugins/pd/hooks/lib/ plugins/pd/mcp/ \
  | grep -v 'test_' | grep -v 'migration_13'
```

**Known sites beyond the spec FR-8.3 enumeration** (from design-reviewer iter-1):
- `entity_status.py:229, :249` — splits on `:` separator (type_id parsing, NOT seq/slug semantics) → out-of-scope (b).
- `frontmatter_inject.py:101` — partition on `:` → out-of-scope (b).
- `database.py:5210` (rename path) — split for rename → in-scope, port to entity_display (a).

**Lint AC (new, added to spec FR-8.3 via design):** post-feature, the above grep returns hits ONLY in (i) `_migration_13_*` functions and (ii) test files. Any other hit is a regression.

### TD-8 — Down-migration is runtime-only

**Decision:** `MIGRATIONS_DOWN[13]` only drops runtime artifacts (`entity_display`, `idx_entity_display_seq`, `migration_audit_log` if present). Source-code restore of removed callers (e.g., `cleanup_backlog.py`) is via git history.

**Rationale:** Established precedent from feature 109 retro: "down-migration is runtime-only restore; source-code state pre-migration is reachable via git history alone".

### TD-9 — pd-state.diff.md output format

**Decision:** Markdown table with 5 columns: `uuid`, `type_id`, `status`, `workflow_phase`, `parent_uuid`. Status-change marker column (`(added)` | `(removed)` | `(changed: <field>)`).

**Output template:**
```markdown
# pd-state diff vs {base}

| uuid (short) | type_id | status | workflow_phase | parent_uuid | change |
|---|---|---|---|---|---|
| 6c4a... | feature:043-foo | active | implement | project:P002-bar | (changed: workflow_phase) |
| 2bd1... | backlog:00400 | open | — | feature:108-baz | (added) |

Total: 2 changed, 1 added, 0 removed.
```

If no changes: `No entity state changes vs {base}`. uuid truncated to first 8 chars for readability.

### TD-10 — Backlog projection deterministic ordering (matches existing flat-table shape)

**Decision:** `_project_backlog_md` emits a flat top-level table matching the EXISTING `docs/backlog.md` shape byte-for-byte (verified against current file: single `| ID | Timestamp | Description |` table sorted by ID ascending; per-feature `## From Feature N ...` sections appear lower as additional sections AFTER the main table, with rows in that section also in ID order).

**Section structure (v1 — matches existing file format families):**

The existing `docs/backlog.md` uses TWO distinct item formats:
1. **Flat top-level table** (lines ~5-50): `| ID | Timestamp | Description |` pipe-table rows for general backlog items.
2. **Per-feature bullet sections** (lines ~70+): `## From Feature N ...` headers with bullet-list items (`- **#00367** [SEVERITY/category] description`) — usually with introductory prose paragraphs and sometimes `### HIGH-cluster deferrals` / `### MED findings` sub-headers.

`_project_backlog_md` v1 emits BOTH formats, controlled by `entities.metadata.format` JSON field:
- `metadata.format = "table_row"` (default for general backlog): emitted as pipe-table row in the flat top table.
- `metadata.format = "bullet_item"`: emitted as bullet item under the `## From Feature N ...` section identified by `metadata.section`.
- `metadata.section_intro` (optional): prose paragraph(s) emitted between `## From Feature N` header and the first item in that section.
- `metadata.subsection` (optional): `### HIGH-cluster deferrals` / `### MED findings` grouping header.

**Backfill rule for `metadata.format` / `metadata.section_intro` / `metadata.subsection`:** A one-shot parser reads existing `docs/backlog.md` during migration 13. For each row found:
- Top-table rows: `format="table_row"`, `section=null`.
- Per-feature section bullets: `format="bullet_item"`, `section="<section heading text>"`, `section_intro=<intro paragraph if any>`, `subsection=<sub-heading if any>`.

**No `## Archived` separate section in v1.** Archive logic deferred to per-row `(closed: ...)` annotation in description text (matches existing convention). The `status='archived'` flag (FR-4.3 `cleanup_backlog.py` archival behavior) controls whether the row appears in the main table; archived rows are EXCLUDED from the main table output (matching existing cleanup behavior where archived rows are moved to `docs/backlog-archive.md`).

**Source fields:**
- `id` column: `entities.entity_id` numeric prefix (5-digit zero-padded).
- `timestamp` column: `entities.created_at` (ISO 8601).
- `description` column: `entities.name` (which carries the free-text description, including any `(closed: ...)` annotations).
- Section grouping: `entities.metadata.section` JSON field (NULL = flat top table). Backfilled during migration 13 by parsing the current `docs/backlog.md` once and assigning section context.

**Backfill rule for `metadata.section`:** A one-shot parser reads existing `docs/backlog.md`. For each row found:
- If the row appears under a `## From Feature N ...` header, set `metadata.section` to that header text.
- Otherwise (top-level table), set `metadata.section = null`.
Parser runs as part of migration 13 (or as a separate Group 0 task — plan-phase decides Group placement, NOT algorithm choice).

**Byte-equality verification (relaxed):** AC-4.2a (added to spec via design phase) requires that `_project_backlog_md` against the post-migration DB produces a file whose `diff -u` against the current `docs/backlog.md` shows only WHITESPACE-LEVEL differences (no semantic content drift). EXACT byte-equality is NOT required because the existing file has minor irregularities (variable bullet indentation, trailing whitespace) that the projection normalizes deterministically. Plan-phase delivers a `compare_backlog_projection.py` script that diff-compares projection output against current `docs/backlog.md` with whitespace-normalized comparison; a failing diff blocks the migration commit.

### TD-11 — Doctor autofix replacement strategy (drift classes enumerated)

**Decision:** `_fix_update_meta_json` is replaced by `_fix_meta_json_via_mcp(drift_type, feature_dir)`. The existing `_fix_update_meta_json` (per SUT-explorer survey: `plugins/pd/hooks/lib/doctor/fix_actions.py:53-95`) handles drift cases by direct `.meta.json` write. Audited drift classes (enumerated in design rev-2, NOT punted to plan):

| Drift class | Detection trigger | New autofix action |
|---|---|---|
| `lastCompletedPhase mismatch` | `entities.metadata.lastCompletedPhase != entity.last_completed_phase` (from DB) | Invoke `complete_phase(feature_type_id, <DB phase>)` MCP — triggers projection that overwrites `.meta.json`. |
| `status mismatch (DB completed, file active)` | DB entity status='completed' AND file says 'active' | Invoke `complete_phase(..., phase='finish')` (canonical finish transition). |
| `branch field stale` | `entities.metadata.branch != git current branch for this feature` | Re-project via `_project_meta_json` (triggers branch-field refresh from DB). No state change. |
| `unknown drift class` (any other discrepancy) | Anything not in the above 3 classes | Doctor emits WARN-only finding pointing user to the appropriate MCP. Does NOT autofix. |

Plan-phase will add one AC per row of this table (4 ACs under AC-1.x or new AC-9.x). The unknown-drift case is the safety net — when in doubt, surface to user rather than guess.

## §4 Interfaces

### 4.1 `pd_state_diff.py` CLI — algorithm committed

```
$ python -m pd_state_diff --base develop
[stdout: markdown content per TD-9]
[exit 0 on success; exit 0 on any failure with stderr warning]
```

**Algorithm (committed in design, NOT punted to plan):**

The DB is the source of truth. `.meta.json` is gitignored so file-diff is impossible. The algorithm is **phase_events replay against a base-commit-timestamp horizon**:

1. Resolve `base_commit_ts` = output of `git log -1 --format=%aI <base>` (ISO 8601 timestamp of HEAD on base branch).
2. Query current entity state from DB:
   ```sql
   SELECT e.uuid, e.type_id, e.status, e.parent_uuid,
          wp.workflow_phase, e.updated_at
   FROM entities e
   LEFT JOIN workflow_phases wp ON wp.type_id = e.type_id
   ORDER BY e.uuid
   ```
3. **Backfilled-entity defense (new):** If `entities.created_at <= base_commit_ts` AND no `phase_events` row exists for entity_uuid where `event_type='entity_created'`, treat base-time state as the CURRENT entity row (assume no change since base — entity was backfilled, has no synthetic creation event). Skip replay for these rows.
4. For all other entities, compute base-time state by replaying `phase_events`:
   ```sql
   SELECT event_type, payload, phase, timestamp
   FROM phase_events
   WHERE entity_uuid = ? AND timestamp <= ?
   ORDER BY timestamp ASC
   ```
   Apply events in order: `entity_created` → set base-existed=True, status='active'; `entity_status_changed` → update status; `started`/`completed` → update workflow_phase; `entity_promoted` → update type_id.
4. Compare base-time state against current state. Emit row per entity with change marker per TD-9.
5. Entities with `created_at > base_commit_ts` are `(added)`; entities whose base-time state existed but current state has them at terminal `archived` are `(removed)` from active view.

**Performance bound:** Per AC-6.5 median-of-5 < 500ms on a 500-row DB. Replay cost is O(events_per_entity × 500). Empirically: post-feature-109, average events_per_entity is ~5-15 for feature-type entities. Total query count: 1 (current state) + 500 (replay queries) = 501 prepared SQL executions. Plan-phase MUST add a benchmark task using fixture DB.

**Failure path:** If `git log -1 <base>` returns nonzero (base ref missing), script writes `pd-state diff unavailable: base ref '{base}' not found` to output AND exits 0 (AC-6.6).

**Concurrent commit safety:** Output file write uses `os.replace(tmp_path, final_path)` atomic rename (TD-5 row "Concurrent commit invocation").

### 4.2 `data-file-guard.sh` contract

**stdin:** Standard Claude Code PreToolUse hook JSON: `{tool_name, tool_input}`.

**stdout:** Standard hook JSON: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow|deny", "permissionDecisionReason": "..."}}` or `{}` (empty allow).

**Exit code:** 0 always (per FR-7.2 fail-open semantics under venv-load failure).

### 4.3 `dispatcher.py` (data_file_guards package)

```python
def main():
    """Entry point: read stdin JSON, dispatch via config, emit hook JSON to stdout."""
    payload = json.load(sys.stdin)
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if tool_name not in {"Write", "Edit", "NotebookEdit"}:
        emit_allow()
        return

    config = load_config(os.environ.get("PD_DATA_FILE_GUARDS_CONFIG", DEFAULT_CONFIG))
    lib_dir = os.environ.get("PD_DATA_FILE_GUARDS_LIB", DEFAULT_LIB)

    for entry in config:
        if fnmatch.fnmatch(file_path, entry["pattern"]):
            excludes = entry.get("exclude_patterns", [])
            if any(fnmatch.fnmatch(file_path, ex) for ex in excludes):
                continue
            decision = invoke_decision(entry["decision_module"], lib_dir, file_path, tool_name, tool_input)
            emit(decision)
            return

    emit_allow()
```

### 4.4 Decision module contract

```python
def decide(file_path: str, tool_name: str, payload: dict) -> dict:
    """
    Returns:
        {"permissionDecision": "allow"} OR
        {"permissionDecision": "deny", "permissionDecisionReason": "<message>"}
    """
```

### 4.5 `_project_backlog_md(db) → str` signature

```python
def _project_backlog_md(db: EntityDatabase) -> str:
    """
    Build deterministic markdown representation of backlog from DB state.

    Reads:
      - All entities WHERE entity_type='backlog' (status IN active|open|archived)
      - Their entity_display (for {seq}-{slug} formatting)
      - entity.metadata.section (for per-section grouping)

    Returns: markdown string with header + table + section structure per TD-10.
    """
```

### 4.6 Migration 13 + DOWN signatures

```python
def _migration_13_entity_display(conn: sqlite3.Connection) -> None:
    """Add entity_display table + migration_audit_log + backfill from entity_id."""

def _migration_13_entity_display_down(conn: sqlite3.Connection) -> None:
    """Drop entity_display, idx_entity_display_seq, migration_audit_log."""
```

Both wrapped in `BEGIN IMMEDIATE` + `PRAGMA foreign_key_check` per feature-109 precedent.

## §5 Cross-File Invariants

| Invariant | Verification |
|---|---|
| `.meta.json` content is deterministic function of DB | AC-4.1 — hash-equality two consecutive projections |
| entity_id parsing audit | `grep -rnE '\.split\(":"\)\|substr\(.*entity_id\|instr\(.*entity_id'` against `plugins/pd/hooks/lib/`, `plugins/pd/mcp/` hits ONLY in `_migration_13_*` functions AND `test_*.py` files. TD-7b lint AC (plan-phase to add). |
| `docs/backlog.md` content is deterministic function of DB | AC-4.2 |
| `data_file_guards.json` schema matches dispatcher expectations | AC-7.1 — dispatcher fails fast on schema violation |
| `entity_display` row count == entities row count | AC-8.2 — `NOT IN` subquery returns 0 |
| `migration_audit_log` rows only created when mismatch detected | AC-8.0 — clean fixture DB has 0 rows; mismatch fixture has N rows |
| `pd-state.diff.md` never blocks commit | AC-6.6 — script always exits 0 |
| `meta-json-guard.sh` is absent | AC-7.6 — `test -f` returns nonzero |
| All `.meta.json` writers have F4-AUDIT comment within 5 lines | AC-1.1b — comment proximity check |

## §6 Risks

| Risk | Mitigation | Plan-phase AC |
|---|---|---|
| R3 — Backfill mismatch (env-gated bypass) | Pre-audit + forensic migration_audit_log row | AC-8.0 |
| R4 — pd-state.diff.md performance flaky on CI | Median-of-5 with warm-up + 1500ms outlier cap | AC-6.5 |
| R5 — Doctor autofix regression (drift modes not covered) | Per-drift-class AC; WARN-only fallback for unknown classes | Plan to enumerate drift modes |
| R6 — venv bootstrap failure under hook context | Fail-open: dispatcher exits 0 with allow | AC-7.8 |
| R7 — `pd_state_diff.py` algorithm complexity (gitignored .meta.json removes simple file-diff path) | **Algorithm committed in §4.1 (phase_events-replay + backfilled-entity defense).** Plan-phase verifies benchmark task is included per AC-6.5. | AC-6.5 perf budget verified at plan |
| R8 — Backlog projection vs add-to-backlog command flow | Plan must thread new register-then-project pattern through the existing command MD | Plan task with explicit sequence |
| R9 — Live DB stale schema (pre-12) intercepts migration 13 | Pre-flight gate with explicit error pointing at feature-109 remediation | AC-5.6, AC-5.6b, AC-5.6c |

## §7 Open Questions Resolved by Spec Rev 4

- pd-state.diff.md gitignored vs committed → **gitignored**, never committed. Local PR-prep only.
- pre-commit-guard.sh existing vs new → **existing**; modified by append-after-existing pattern.
- Fnmatch vs pathlib.match → **fnmatch** (Python 3.12 floor); no `**` glob.
- phase_events forensic row vs dedicated table → **dedicated `migration_audit_log` table**.
- init_project_state port → **deferred to feature 111**; retained with F4-AUDIT comment.
- _fix_update_meta_json → **replaced** with MCP-invoking wrapper + WARN-only fallback.
- `meta-json-guard.sh` shim retained → **deleted**; 4 existing tests migrated.

## §8 Plan-Phase Inputs

Plan-phase will produce ~12-15 Groups:

- Group 0: scaffolding (`.gitignore` entries, empty package init files)
- Group 1: pre-flight gate tests + migration 13 stub
- Group 2: `entity_display` table + index + backfill (FR-8.1, FR-8.2)
- Group 3: pre-audit + migration_audit_log (FR-8.2-pre)
- Group 4: scan_entity_ids port (FR-8.3a)
- Group 5: `_project_meta_json` entity_display read (FR-8.3b)
- Group 6: backfill.py port (FR-8.3c)
- Group 7: rename test + AC-8.6 (FR-8.4)
- Group 8: `_project_backlog_md` function (FR-4.2)
- Group 9: data_file_guards package + dispatcher (FR-7.1, FR-7.2, FR-7.3)
- Group 10: `data-file-guard.sh` + hooks.json registration (FR-7.4)
- Group 11: AST audit tests + F4-AUDIT comments (AC-1.1, AC-1.2, FR-4.1)
- Group 12: backlog writer port + cleanup_backlog removal (FR-4.3)
- Group 13: `.gitignore` + tracked-copy removal (FR-4.5)
- Group 14: `pd_state_diff.py` + pre-commit-guard.sh modification (FR-4.6)
- Group 15: down-migration + AC-5.5 round-trip test
