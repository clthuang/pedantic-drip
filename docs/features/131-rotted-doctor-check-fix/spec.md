# Specification: Rotted Doctor-Check Fix

## Problem Statement

Four doctor checks query columns dropped from the live entity DB schema (`entity_type` dropped by feature 109, `project_id` dropped by feature 108/109), and their `except sqlite3.Error: pass` blocks swallow the failures — so `check_feature_status`, `check_brainstorm_status`, and `check_project_attribution` silently report nothing (false negatives), while `check_entity_orphans` mass-flags every on-disk feature as "no entity in DB" (false positives), making doctor output untrustworthy.

## Evidence

EXPLAIN harness run against the live DB (2026-07-10, schema v17: `entities` columns are `uuid, workspace_uuid, type_id, entity_id, name, status, parent_uuid, artifact_path, created_at, updated_at, metadata, type, kind, lifecycle_class`) — 7 of 31 SQL sites in `plugins/pd/hooks/lib/doctor/checks.py` fail:

| Line | Check | Dead column |
|------|-------|-------------|
| 708  | `check_feature_status` | `entity_type` |
| 986  | `check_brainstorm_status` | `entity_type` |
| 1081 | `check_brainstorm_status` | `entity_type` |
| 1389 | `check_entity_orphans` | `entity_type` + `project_id` |
| 1396 | `check_entity_orphans` | `entity_type` |
| 1487 | `check_entity_orphans` | `entity_type` |
| 1556 | `check_project_attribution` | `project_id` |

P004 PRD census: ~320 of 601 doctor warnings stem from these swallowed schema errors.

## Success Criteria

- [ ] Zero SQL statements in `doctor/checks.py` reference the DROPPED `entities.entity_type` or `entities.project_id` columns — the live `workspaces.project_id_legacy` column (`checks.py:391`) and message-text mentions of `project_id='__unknown__'` are excluded (verify: the EXPLAIN harness reports 0 broken sites out of all SQL sites — authoritative check).
- [ ] `check_entity_orphans` run against the live DB no longer flags features that exist in both DB and filesystem (the ~one-warning-per-feature false-positive class disappears).
- [ ] The fixed queries in `check_feature_status` and `check_brainstorm_status` execute against the live schema without `sqlite3.Error` and return whatever `kind='feature'` / `kind='brainstorm'` rows exist (query liveness, not data presence — an all-promoted brainstorm set legitimately yields zero candidates). Smoke check: `check_feature_status`'s candidate set is non-empty on this repo's live DB (features guaranteed present per census).
- [ ] A schema-level `sqlite3.Error` at any of the 6 REWRITTEN sites (broken site 7, `checks.py:1556`, is deleted with its check) surfaces as an `error`-severity doctor Issue naming the check and the SQL error — never a silent `pass` (per CLAUDE.md "Do not silently swallow database exceptions"). The EXPLAIN-clean SQL sites inside these checks (e.g., the `artifact_path` sweep at `checks.py:1457-1481`) retain their existing handling per Out of Scope. Exception: absence of a column that only exists post-migration (e.g., `workspace_uuid` on a pre-Migration-11 DB) is tolerated silently, mirroring the intentional-swallow precedent at `checks.py:579-581` — only failures against the CURRENT schema vocabulary (`kind`, `workspace_uuid` present) are rot and must surface.
- [ ] All existing doctor tests pass; each of the three retained checks gains a regression test that fails if its query references a column absent from the live schema. `check_project_attribution` and its tests are removed, and a doctor run emits zero `project_attribution` issues.

## Scope

### In Scope

- Rewrite the broken queries in the three retained checks to live schema: `entity_type = 'X'` → `kind = 'X'` (exact semantic successor per feature 109). For the `project_id` scoping filter in `check_entity_orphans`: the old bucket IS faithfully reconstructible — Migration 11 maps every legacy `project_id='__unknown__'` entity 1:1 onto `workspace_uuid = _UNKNOWN_WORKSPACE_UUID` (`checks.py:539-546`, `database.py:118`). What actually changed is the SCOPING INPUT (the `project_id` kwarg has no column to match; workspace resolves via project root → `workspaces.uuid`) and the SENTINEL VALUE (`'__unknown__'` string → computed UUID). Policy: scope the feature-directory sweep to the current `workspace_uuid` when resolvable (pattern at `checks.py:564-576`); fall back to unfiltered when no workspace context resolves.
- DELETE `check_project_attribution` (and its tests): its defended surface — entities in the unknown bucket — is already covered by the LIVE sibling `check_unknown_workspace_orphans` (`checks.py:532-581`), which queries `workspace_uuid = _UNKNOWN_WORKSPACE_UUID` and carries a fix action (`claim_unknown_entities`). Fixing it would duplicate that check, contradicting the PRD's doctor-shrink goal (Goal 4 / FR-12).
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
- Given `check_project_attribution` is deleted, when doctor runs, then zero `project_attribution` issues are emitted, and the unknown-workspace bucket remains covered by `check_unknown_workspace_orphans` (no coverage gap, no duplicate).

### Error & Boundary Cases

- Given a DB whose CURRENT schema is missing a column one of the 6 rewritten queries references, when that check runs, then it emits one `error`-severity Issue containing the check name and the sqlite error message, and does not raise or silently pass.
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
