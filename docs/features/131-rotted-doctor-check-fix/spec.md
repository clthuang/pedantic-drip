# Specification: Rotted Doctor-Check Fix

## Problem Statement

Four doctor checks query columns dropped from the live entity DB schema (`entity_type` dropped by feature 109, `project_id` dropped by feature 108/109), and their `except sqlite3.Error: pass` blocks swallow the failures — so `check_feature_status`, `check_brainstorm_status`, and `check_project_attribution` silently report nothing (false negatives), while `check_entity_orphans` mass-flags every on-disk feature as "no entity in DB" (false positives), making doctor output untrustworthy.

## Evidence

EXPLAIN harness run against the live DB (2026-07-10, schema v17: `entities` columns are `uuid, workspace_uuid, type_id, entity_id, name, status, parent_uuid, artifact_path, created_at, updated_at, metadata, type, kind, lifecycle_class`) — 7 of 31 SQL sites in `plugins/pd/hooks/lib/doctor/checks.py` fail:

Line numbers as of HEAD at authoring (d92354e9); the EXPLAIN harness is the authoritative broken-site check, not these numbers.

| Line | Check | Dead column |
|------|-------|-------------|
| 709  | `check_feature_status` | `entity_type` |
| 988  | `check_brainstorm_status` | `entity_type` |
| 1083 | `check_brainstorm_status` | `entity_type` |
| 1391 | `check_entity_orphans` | `entity_type` + `project_id` |
| 1398 | `check_entity_orphans` | `entity_type` |
| 1488 | `check_entity_orphans` | `entity_type` |
| 1558 | `check_project_attribution` | `project_id` |

Additionally, the check's fixer `_fix_project_attribution` (`fix_actions/__init__.py:348-359`) is dead-by-unreachability once its trigger check is deleted, and is a duplicate of the workspace-claim path: `backfill_project_ids` was already migrated by feature 108 and writes `entities.workspace_uuid` (`database.py:7818-7824`), the same claim `check_unknown_workspace_orphans`'s fix action performs — it does NOT write dropped columns.

P004 PRD census: ~320 of 601 doctor warnings stem from these swallowed schema errors.

## Success Criteria

- [ ] Zero SQL statements in `doctor/checks.py` reference the DROPPED `entities.entity_type` or `entities.project_id` columns — the live `workspaces.project_id_legacy` column (`checks.py:391`) and message-text mentions of `project_id='__unknown__'` are excluded. Durable verification: SC#5's committed per-check regression tests plus a committed static/EXPLAIN scan over checks.py's SQL sites. (The authoring-time EXPLAIN harness that found the 7 sites is labelled evidence, not a committed check — commit an equivalent as part of SC#5's test work.)
- [ ] `check_entity_orphans` run against the live DB no longer flags features that exist in both DB and filesystem (the ~one-warning-per-feature false-positive class disappears).
- [ ] The fixed queries in `check_feature_status` and `check_brainstorm_status` execute against the live schema without `sqlite3.Error` and return whatever `kind='feature'` / `kind='brainstorm'` rows exist (query liveness, not data presence — an all-promoted brainstorm set legitimately yields zero candidates). Smoke check: `check_feature_status`'s candidate set is non-empty on this repo's live DB (features guaranteed present per census).
- [ ] A schema-level `sqlite3.Error` at any of the 6 REWRITTEN sites (broken site 7, `checks.py:1558`, is deleted with its check) surfaces as an `error`-severity doctor Issue naming the check and the SQL error — never an unconditional silent `pass` (per CLAUDE.md "Do not silently swallow database exceptions"; the one verified exception is the tolerate branch below). The EXPLAIN-clean SQL sites inside these checks (e.g., the `artifact_path` sweep at `checks.py:1457-1481`) retain their existing handling per Out of Scope. Runtime discriminator (the tolerate-vs-surface rule): when a rewritten query fails, probe the target column's presence (e.g., `PRAGMA table_info`); if the current-schema column (`kind`, `workspace_uuid`) IS present yet the statement failed → surface the `error` Issue; if the column is absent (pre-Migration-11 DB) → tolerate silently. `checks.py:579-581` is a shape reference for the TOLERATE branch only — it swallows all `sqlite3.Error` indiscriminately and must not be copied wholesale for the surface branch.
- [ ] All existing doctor tests pass; each of the three retained checks gains a regression test that fails if its query references a column absent from the live schema, AND a committed scan test (the EXPLAIN-equivalent SC#1 promises) EXPLAIN-validates ALL SQL sites in `checks.py` against the live schema — this scan is the durable form of the authoring harness. `check_project_attribution` and its tests are removed, and a doctor run emits zero `project_attribution` issues.
- [ ] No retained doctor check OR fixer reads or writes the dropped `entities.entity_type` / `entities.project_id` columns — a defensive net over `fix_actions/` and `fixer.py` with zero currently-known write-path violators (`backfill_project_ids` writes the live `workspace_uuid`, `database.py:7818-7824`); the only known read violator is `check_project_attribution`'s query at `checks.py:1558`, removed by the deletion.

## Scope

### In Scope

- Rewrite the broken queries in the three retained checks to live schema: `entity_type = 'X'` → `kind = 'X'` (exact semantic successor per feature 109). For the `project_id` scoping filter in `check_entity_orphans`: the old bucket IS faithfully reconstructible — Migration 11 maps every legacy `project_id='__unknown__'` entity 1:1 onto `workspace_uuid = _UNKNOWN_WORKSPACE_UUID` (`checks.py:539-546`, `database.py:118`). What actually changed is the SCOPING INPUT (the `project_id` kwarg has no column to match; workspace resolves via project root → `workspaces.uuid`) and the SENTINEL VALUE (`'__unknown__'` string → computed UUID). Policy — the rewritten predicate is the faithful reconstruction of the old two-arm filter: `WHERE kind='feature' AND (workspace_uuid = ? OR workspace_uuid = '{_UNKNOWN_WORKSPACE_UUID}')`, applied ONLY when exactly one `workspaces` row matches the project root (mirroring `check_unknown_workspace_orphans`'s `len(root_uuids) == 1` branch at `checks.py:608-622` and `_single_root_or_raise`, `database.py:7767-7771`); 0 or >1 matching rows count as "no resolvable workspace" → unfiltered fallback (`WHERE kind='feature'`). The unknown-bucket arm keeps unknown-workspace entities inside `db_feature_ids`, so step 2 (`checks.py:1444`) does not false-flag their on-disk directories.
- DELETE `check_project_attribution` and its FULL deregistration surface: the check function and its tests; the `doctor/__init__.py` wiring (import at :32, `CHECK_ORDER` entry at :55, `_ENTITY_DB_CHECKS` entry at :97); the fixer `_fix_project_attribution` (`fix_actions/__init__.py:348-359` — dead once its trigger check goes, and a duplicate of the workspace-claim path); and its `fixer.py` registrations (import at :21, `_SAFE_PATTERNS` "Backfill project_id for" entry at :52). `backfill_project_ids` itself stays (live `workspace_uuid` writer, also reachable via `entity_server.py`). Rationale: its defended surface — entities in the unknown bucket — is already covered by the LIVE sibling `check_unknown_workspace_orphans` (`checks.py:532-581`), which queries `workspace_uuid = _UNKNOWN_WORKSPACE_UUID` and carries a fix action (`claim_unknown_entities`). Fixing it would duplicate that check, contradicting the PRD's doctor-shrink goal (Goal 4 / FR-12).
- Replace the blanket `except sqlite3.Error: pass` at the 6 rewritten sites with error-surfacing (emit `error`-severity Issue).
- Regression tests pinning live-schema compatibility for the three retained checks.

### Out of Scope

- The 12-check retirement of checks whose surfaces vanish AFTER the redesign (feature 133).
- Any schema change, event log, or new-DB work (features 118+).
- Doctor architecture changes (runner, fixer, severity model).
- The other 16 `except sqlite3.Error` sites whose queries EXPLAIN clean.

## Acceptance Criteria

### Happy Paths

- Given a live DB with `kind` column and N registered features that all have on-disk directories, when `check_entity_orphans` runs, then it emits zero "no entity in DB" warnings for those features.
- Given a feature registered in the DB whose directory was deleted, when `check_entity_orphans` runs, then exactly that entity is flagged "in DB but feature directory not found".
- Given features whose DB `status` diverges from their `.meta.json` status, when `check_feature_status` runs, then the divergent features are reported (check is alive again).
- Given a brainstorm entity with a stale status, when `check_brainstorm_status` runs, then it is reported.
- Given a resolvable workspace context and features registered under a DIFFERENT workspace, when `check_entity_orphans` runs, then those foreign-workspace entities are excluded from the feature-directory orphan check (sections 1-2; section 3's `artifact_path` path-prefix scoping at `checks.py:1466-1468` is unchanged and out of scope).
- Given an on-disk feature directory whose entity sits in the unknown-workspace bucket (`workspace_uuid = _UNKNOWN_WORKSPACE_UUID`), when `check_entity_orphans` runs with a resolvable workspace, then that entity is INCLUDED in `db_feature_ids` (two-arm predicate) and its directory is NOT flagged "has .meta.json but no entity in DB" — SC#2 holds for the unknown-bucket class; its claimability remains `check_unknown_workspace_orphans`'s job.
- Given `check_project_attribution` is deleted, when doctor runs, then zero `project_attribution` issues are emitted, and the unknown-workspace bucket remains covered by `check_unknown_workspace_orphans` (no coverage gap, no duplicate).

### Error & Boundary Cases

- Given a DB where a rewritten query's target current-schema column (`kind`, `workspace_uuid`) IS present but the statement still raises `sqlite3.Error` (e.g., corrupted index, malformed DB), when that check runs, then it emits one `error`-severity Issue containing the check name and the sqlite error message, and does not raise or silently pass (SC#4 surface branch).
- Given a pre-Migration-11 DB where the target column (`kind` or `workspace_uuid`) is ABSENT entirely, when that check runs, then no Issue is emitted and the check completes cleanly (SC#4 tolerate branch).
- Given an empty DB (no entities), when the three retained checks run, then no false positives are emitted and no exception escapes.
- Given no resolvable workspace context, when `check_entity_orphans` runs, then it falls back to an unscoped live-schema query (current unfiltered behavior preserved).

## Feasibility Assessment

### Assessment
**Overall:** Confirmed
**Reasoning:** `kind` is the drop-in successor of `entity_type` (feature 109 migration 12; result dicts already alias both keys). Workspace scoping via `_UNKNOWN_WORKSPACE_UUID` is already used by a neighboring live check at `checks.py:564-576`. The EXPLAIN harness demonstrates the exact failing set; the work is column renames in three retained checks, one workspace-scoping replacement, and one check deletion whose surface is already covered live.
**Key Assumptions:**
- `kind` values use the same vocabulary as old `entity_type` (`feature`, `brainstorm`) — Status: Verified (live DB query during P004 census; `database.py` FTS5 indexes `kind`).
- Doctor Issue model supports `error` severity — Status: Verified (`models.py:12` types severity as `"error" | "warning" | "info"`; `severity="error"` already used at `checks.py:723`).
**Open Risks:** None identified.

## Dependencies

- None (independent pre-work; no dependency on features 118-133).

## Open Questions

- None. The check_project_attribution fix-vs-delete question was resolved at spec review iteration 2: DELETE — fixing it to workspace-bucket semantics would duplicate the live `check_unknown_workspace_orphans` (`checks.py:532-581`).
