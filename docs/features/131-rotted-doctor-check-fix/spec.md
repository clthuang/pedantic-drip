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

- [ ] Zero SQL statements in `doctor/checks.py` reference `entity_type` or `project_id` entity columns (verify: the EXPLAIN harness reports 0 broken sites out of all SQL sites).
- [ ] `check_entity_orphans` run against the live DB no longer flags features that exist in both DB and filesystem (the ~one-warning-per-feature false-positive class disappears).
- [ ] `check_feature_status` and `check_brainstorm_status` produce non-empty candidate sets from the live DB again (queries return rows; checks are no longer dead).
- [ ] A schema-level `sqlite3.Error` inside any of the four checks surfaces as an `error`-severity doctor Issue naming the check and the SQL error — never a silent `pass` (per CLAUDE.md "Do not silently swallow database exceptions"). Exception: absence of a column that only exists post-migration (e.g., `workspace_uuid` on a pre-Migration-11 DB) is tolerated silently, mirroring the intentional-swallow precedent at `checks.py:579-581` — only failures against the CURRENT schema vocabulary (`kind`, `workspace_uuid` present) are rot and must surface.
- [ ] All existing doctor tests pass; each RETAINED check gains a regression test that fails if its query references a column absent from the live schema. If `check_project_attribution` is deleted (see Open Questions), its tests are removed instead and doctor emits zero `project_attribution` issues.

## Scope

### In Scope

- Rewrite the 7 broken queries to live schema: `entity_type = 'X'` → `kind = 'X'` (exact semantic successor per feature 109). For the `project_id` filters: the old `project_id = '__unknown__'` string-literal scoping is UNREPRODUCIBLE (column dropped; its row-set cannot be reconstructed) — this is a new semantic, not a port. Replacement policy: scope to the current `workspace_uuid` when resolvable (unknown-bucket = the computed `_UNKNOWN_WORKSPACE_UUID` at `database.py:118`, pattern already used at `checks.py:564-576`); fall back to unfiltered when no workspace context resolves.
- `check_project_attribution`: fix to the workspace-based equivalent (entities in the `_UNKNOWN_WORKSPACE_UUID` bucket) or delete with rationale if its defended surface is judged gone — decision at design.
- Replace the blanket `except sqlite3.Error: pass` at the affected sites with error-surfacing (emit `error`-severity Issue).
- Regression tests pinning live-schema compatibility for the four checks.

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
- Given a resolvable workspace context and features registered under a DIFFERENT workspace, when `check_entity_orphans` runs, then those foreign-workspace entities are excluded from the orphan sweep (workspace-scoped branch preserved).
- Given `check_project_attribution` is RETAINED (fix branch): given entities in the `_UNKNOWN_WORKSPACE_UUID` bucket, when it runs, then those claimable entities are reported. Given it is DELETED instead: the check function and its tests are removed, and a doctor run emits zero `project_attribution` issues.

### Error & Boundary Cases

- Given a DB whose schema is missing a column one of the four checks queries, when that check runs, then it emits one `error`-severity Issue containing the check name and the sqlite error message, and does not raise or silently pass.
- Given an empty DB (no entities), when the four checks run, then no false positives are emitted and no exception escapes.
- Given no resolvable workspace context, when `check_entity_orphans` runs, then it falls back to an unscoped live-schema query (current unfiltered behavior preserved).

## Feasibility Assessment

### Assessment
**Overall:** Confirmed
**Reasoning:** `kind` is the drop-in successor of `entity_type` (feature 109 migration 12; result dicts already alias both keys). Workspace scoping via `_UNKNOWN_WORKSPACE_UUID` is already used by a neighboring live check at `checks.py:564-576`. The EXPLAIN harness demonstrates the exact failing set; rewrites are column renames plus one scoping-semantics port.
**Key Assumptions:**
- `kind` values use the same vocabulary as old `entity_type` (`feature`, `brainstorm`) — Status: Verified (live DB query during P004 census; `database.py` FTS5 indexes `kind`).
- Doctor Issue model supports `error` severity — Status: Verified (`models.py:12` types severity as `"error" | "warning" | "info"`; `severity="error"` already used at `checks.py:723`).
**Open Risks:** None identified beyond the check_project_attribution fix-vs-delete decision (Open Questions).

## Dependencies

- None (independent pre-work; no dependency on features 118-133).

## Open Questions

- `check_project_attribution`: fix to workspace-bucket semantics or delete outright — resolved at design after inspecting what its warnings drive.
