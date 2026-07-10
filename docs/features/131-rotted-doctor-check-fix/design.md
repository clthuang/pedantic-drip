# Design: Rotted Doctor-Check Fix

## Prior Art Research

Codebase exploration completed during spec authoring and verified byte-exact across six independent review rounds (see `.review-history.md`); external research skipped — this is an internal-schema repair with in-repo precedents for every mechanism:

- **Workspace resolution + unknown-bucket query pattern**: `check_unknown_workspace_orphans` (`checks.py:532-622`) — resolves project root → `workspaces` rows, branches on `len(root_uuids) == 1`, queries `workspace_uuid = _UNKNOWN_WORKSPACE_UUID`. This is the wheel we reuse, not reinvent.
- **Single-match enforcement precedent**: `_single_root_or_raise` (`database.py:7767-7771`).
- **`error`-severity Issue precedent**: `checks.py:723`; severity vocabulary at `models.py:12`.
- **Tolerate-branch shape**: intentional pre-Migration-11 swallow at `checks.py:579-581`.
- **EXPLAIN-based test precedent**: `EXPLAIN QUERY PLAN` index test at `entity_registry/test_polymorphic_taxonomy.py:332`.

## Architecture Overview

One behavioral module changes (`doctor/checks.py`), one registration surface shrinks (`doctor/__init__.py`, `doctor/fixer.py`, `doctor/fix_actions/__init__.py`), and the test suite gains a durable schema-conformance scan. No new modules, no new dependencies, no schema changes.

```
doctor/checks.py
  ├─ [A] _run_live_schema_query()   ← NEW small helper: execute-or-surface
  ├─ [B] check_feature_status       ← 1 query rewritten, routed through [A]
  ├─ [B] check_brainstorm_status    ← 2 queries rewritten, routed through [A]
  ├─ [B] check_entity_orphans       ← 3 queries rewritten (1 gains two-arm
  │                                    workspace predicate), routed through [A]
  └─ [C] check_project_attribution  ← DELETED (function + module wiring + fixer)

doctor tests
  └─ [D] test_checks.py             ← per-check live-schema regression tests
                                      + committed EXPLAIN scan over all SQL sites
```

## Components

### [A] Error-surfacing query helper (`_run_live_schema_query`)

Private helper in `checks.py` implementing spec SC#4's surface/tolerate discriminator in ONE place instead of six copies. Executes a SQL statement; on `sqlite3.Error`, probes schema and either appends an `error`-severity Issue (rot: target column present, statement still failed — or target column missing FROM the current-schema vocabulary) or returns empty silently (pre-migration DB: current-schema column absent).

### [B] Query rewrites (6 sites, 3 checks)

| Site (HEAD d92354e9) | Rewrite |
|------|---------|
| `check_feature_status` :709 | `entity_type = 'feature'` → `kind = 'feature'` |
| `check_brainstorm_status` :988 | `entity_type = 'brainstorm'` → `kind = 'brainstorm'` |
| `check_brainstorm_status` :1083 | `entity_type = 'feature'` → `kind = 'feature'` |
| `check_entity_orphans` :1391 | `entity_type='feature' AND (project_id=? OR project_id='__unknown__')` → `kind='feature' AND (workspace_uuid = ? OR workspace_uuid = ?)` — both operands bound as params: `(resolved_uuid, _UNKNOWN_WORKSPACE_UUID)`, matching the mirror at `checks.py:576` and the helper's parameterized contract |
| `check_entity_orphans` :1398 | `entity_type = 'feature'` → `kind = 'feature'` (unfiltered; ALWAYS runs — see step-role split below) |
| `check_entity_orphans` :1488 | `entity_type = 'brainstorm'` → `kind = 'brainstorm'` |

**Dead-branch revival, acknowledged**: the old `:1391` scoped branch is DEAD in production — `run_diagnostics` builds ctx without a `project_id` key (`doctor/__init__.py:165-172`), so `kwargs.get("project_id")` is always None and only the unfiltered `:1398` branch ever ran. Routing scoping through `project_root` (which IS in ctx) makes scoping reachable for the first time — a behavior change, not a reconstruction.

**Control flow (the old if/else collapses into two named row-sets):**

```python
db_features_all, features_tolerated = _run_live_schema_query(
    entities_conn,                          # ALWAYS runs (was the :1398 else-branch)
    "SELECT type_id, entity_id, artifact_path FROM entities "
    "WHERE kind = 'feature'", (), "entity_orphans", issues, ("kind",))
db_feature_ids = {row[1] for row in db_features_all}      # step-2 membership, UNSCOPED

if scoped:                                   # exactly one workspaces row matched
    db_features_step1, _ = _run_live_schema_query(   # two-arm predicate (was :1391)
        entities_conn, "... WHERE kind = 'feature' AND "
        "(workspace_uuid = ? OR workspace_uuid = ?)",
        (root_uuids[0], _UNKNOWN_WORKSPACE_UUID), "entity_orphans", issues,
        ("kind", "workspace_uuid"))
else:
    db_features_step1 = db_features_all

# Steps 2 and 4 are gated on the tolerated flags (docstring MUST clause):
#   step 2 (checks.py:1438-1454) runs ONLY if not features_tolerated
#   step 4 (:1494-1522) runs ONLY if not brainstorms_tolerated
#     where: db_brainstorms, brainstorms_tolerated = _run_live_schema_query(
#                ..., "... WHERE kind = 'brainstorm'", ..., ("kind",))  # was :1488
# Tolerated membership is UNKNOWN, not empty -- flagging would violate the
# spec tolerate AC.
```

- **Step-2 membership** (`db_feature_ids`, consumed at `checks.py:1444`) always comes from `db_features_all` — a dir whose entity exists under ANY workspace is never flagged "has .meta.json but no entity in DB" (spec SC#2 holds for every exists-in-both case, foreign-real-workspace included; matches today's only-reachable behavior).
- **Step-1 reporting** (DB→disk orphan sweep, `checks.py:1405-1421`) iterates `db_features_step1`.

**Reconciliation with the pre-existing `local_entity_ids` heuristic**: step 1 already discriminates cross-project rows via `local_entity_ids` (`checks.py:1407` warning branch vs `:1419` `cross_project_count` info bucket; built by `_build_local_entity_set`, injected at `doctor/__init__.py:171`). That heuristic is the pre-workspace-era PROXY for "belongs to this project" — directory presence approximating ownership. `workspace_uuid` is the fact the proxy approximated. Resolution:

- **When scoped** (exactly one workspace match): the two-arm row-set IS the ownership discriminator. Step 1 iterates `db_features_step1` and flags every missing dir as a warning — the `local_entity_ids` branching is bypassed (every scoped row is "ours" by workspace fact). Rows in `db_features_all` but NOT in `db_features_step1` whose dirs are missing feed `cross_project_count`, preserving the existing info Issue ("may belong to other projects").
- **When not scoped** (0 or >1 matches): current behavior preserved verbatim — `db_features_step1 == db_features_all`, `local_entity_ids` branching untouched.
- The spec's deleted-dir warning AC holds in both modes: scoped → warning via workspace fact; unscoped → warning via the legacy branch (`entity_id in local_entity_ids or not local_entity_ids`).
- **Why this is testable non-vacuously**: with `local_entity_ids` EMPTY (empty features dir), the legacy branch warns for EVERY missing-dir row including foreign ones (`not local_entity_ids` → warning arm); the scoped path routes foreign rows to the info bucket instead. Distinct outcomes ⇒ [D].5's foreign-workspace test fails if the workspace predicate is removed. (This is also a live false-positive class the scoping genuinely fixes.)

Workspace resolution mirrors `check_unknown_workspace_orphans` (`checks.py:582-592`) EXACTLY: `os.path.abspath(project_root)`, predicate `project_root IS NOT NULL AND project_root = ?`, and the whole lookup wrapped in `try/except sqlite3.Error → root_uuids = []` (missing `workspaces` table → unfiltered fallback, never a raise). The `project_id` kwarg is no longer read by this check (dead input; the runner's kwarg plumbing is untouched).

### [C] check_project_attribution deletion surface

- `checks.py`: `check_project_attribution` function (+ its `__all__`/docstring mentions if any)
- `doctor/__init__.py`: import (:32), `CHECK_ORDER` entry (:55), `_ENTITY_DB_CHECKS` entry (:97)
- `doctor/fixer.py`: `_fix_project_attribution` import (:21), `_SAFE_PATTERNS` "Backfill project_id for" entry (:52)
- `doctor/fix_actions/__init__.py`: `_fix_project_attribution` (:348-359)
- `test_doctor.py`: remove `'check_project_attribution'` from the hard-coded `expected_names` (`test_doctor.py:24`; the `actual_names == expected_names` assertion at :38 enforces the deletion)
- `test_checks.py` / `test_fix_actions.py` / `test_fixer.py`: its test cases
- KEEP: `EntityDatabase.backfill_project_ids` (live `workspace_uuid` writer, reachable via `entity_server.py`); `check_unknown_workspace_orphans` (absorbs the surface)

### [D] Tests

**Fixture-migration plan (resolves the legacy-fixture conflict):** the existing behavioral tests for the three rewritten checks are built on LEGACY hand-rolled fixtures — `_make_db()` (`test_checks.py:22-59`) creates `entities` with `entity_type`/`project_id` but NO `kind`, NO `workspace_uuid`, and no `workspaces` table; `_register_feature` (`test_checks.py:113-131`) inserts `entity_type='feature'`. After the rewrite those fixtures would silently route every query down the tolerate branch (vacuous green) or false-fail (e.g., `test_check7_all_matched` at `:1340-1358`, `test_check7_orphaned_local_entity` at `:1364-1382`, cross-project suite at `:1431-1489`, plus the `check_feature_status`/`check_brainstorm_status` suites). Plan:

- Fork the helpers: `_make_live_db()` builds fixtures via the real `EntityDatabase(tmp_path)` bootstrap (live schema, as `test_polymorphic_taxonomy.py` does); a live `_register_feature(..., workspace_uuid=...)` inserts `kind='feature'` rows under a caller-chosen workspace; `_insert_workspace(conn, project_root, uuid)` inserts `workspaces` rows so [D].5 can construct exactly-one / zero / multiple project-root matches and local / foreign-real / unknown-bucket entity placements directly. The legacy `_make_db`/`_register_feature` are RETAINED only for tests that legitimately exercise pre-Migration-11 schemas (per `_make_db`'s own docstring, `test_checks.py:25-29`) — including the new tolerate-branch test.
- Repoint the three rewritten checks' behavioral suites (`test_check7_*`, `check_feature_status`, `check_brainstorm_status` tests) onto the live fixtures.

1. Per-check regression: for each retained check, build a live-schema DB via `_make_live_db()` and assert the check's queries execute (no schema `sqlite3.Error` surfaces, no tolerate-branch engagement — assert via returned candidate sets being non-vacuous where the fixture registers rows).
2. Committed EXPLAIN scan: AST-walk `checks.py` for constant SQL in `execute()` calls (same technique as the authoring harness), `EXPLAIN` each against a live-schema connection, assert zero failures. Durable form of spec SC#1.
3. Surface-branch test: live-schema DB, monkeypatch/corrupt a query to fail while `kind` exists → assert one `error` Issue naming the check.
4. Tolerate-branch test: LEGACY fixture (`_make_db`, genuinely no `kind` column) with a registered feature AND its on-disk directory created → assert the WHOLE check emits zero Issues (spec's tolerate AC — proves the tolerated-membership skip of steps 2/4, not merely quiet SQL sites). `check_feature_status`/`check_brainstorm_status` need no separate tolerate assertion: as candidate-set consumers they no-op on tolerated `rows=[]` by construction (shared helper validated once here and in [D].3) — the asymmetry is deliberate, not a gap.
5. Scoping tests (non-vacuous by construction — each controls `local_entity_ids` via the on-disk features dir AND workspace placement via `_insert_workspace` + per-entity `workspace_uuid`, and fails if the two-arm predicate is removed): (a) foreign-workspace entity, missing dir, EMPTY features dir → info bucket, not warning (legacy branch would warn — proves the predicate discriminates); (b) unknown-bucket entity, missing dir, scoped → warning (treated local); (c) foreign-real-workspace ON-DISK dir → not step-2-flagged (unscoped membership); (d) zero and multiple workspace matches → legacy `local_entity_ids` branching verbatim.
6. Deletion tests: doctor run emits zero `project_attribution` issues; `test_doctor.py` `expected_names` updated and its `CHECK_ORDER` assertion passes.
7. Empty-DB boundary: `_make_live_db()` with zero registered rows → all three retained checks run clean, zero Issues, no exception (spec's empty-DB AC).

## Interfaces

```python
def _run_live_schema_query(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple,
    check_name: str,
    issues: list[Issue],
    required_columns: tuple[str, ...],   # e.g. ("kind",) or ("kind", "workspace_uuid")
) -> tuple[list[tuple], bool]:
    """Execute sql; return (rows, tolerated).

    On sqlite3.Error:
      - If every column in required_columns exists in entities' current schema
        (PRAGMA table_info probe, run on the failure path only — no cache;
        failures are rare and the probe is one PRAGMA) -> append one
        error-severity Issue(check=check_name, message=f"{check_name}: schema
        query failed: {exc}") and return []. EMIT-ONCE: skip the append if an
        identical (check, message) Issue is already in `issues` — call sites
        inside loops (:1083 runs per-dependency-edge, checks.py:1049/:1078)
        must not multiply one persistent failure into dozens of Issues
        (spec SC#4 / error-AC say ONE Issue).
      - If any required column is absent (pre-Migration-11 DB) -> return []
        silently (tolerate branch, spec SC#4).

    RETURN SHAPE: returns (rows, tolerated: bool) so callers can distinguish
    "schema too old, could not read" from "genuinely zero rows". Membership
    consumers MUST honor it: when db_features_all or the brainstorm set
    (:1488) is tolerated, check_entity_orphans SKIPS step-2 (checks.py:
    1438-1454) and step-4 (:1494-1522) disk->DB flagging entirely --
    membership is UNKNOWN, not empty, and flagging every on-disk dir would
    violate the spec's tolerate AC ("no Issue is emitted, check completes
    cleanly"). Candidate-set consumers (feature_status, brainstorm_status,
    step-1) just use rows and need no branch: empty rows = nothing to report.
    """
```

Call-site contract: every rewritten site passes its `required_columns`; sites keep their existing downstream logic operating on returned rows (`db_features`, candidate sets). The helper NEVER raises. `:1083`'s `.fetchone()` usage adapts to the list return (`rows[0] if rows else None`), and its enclosing `try/except sqlite3.Error` at `checks.py:1066-1099` STAYS — it also guards EXPLAIN-clean sibling queries (`:1068`, `:1074`) that are out of scope. `:988`'s own enclosing `try/except sqlite3.Error: pass` (`checks.py:985-993`) is likewise RETAINED as a harmless dead guard (the helper never raises; consistent treatment with :1083, no wrapper surgery in this feature).

Merged step-1 loop (pins the disjoint warn-vs-count partition and the bypass-`local_entity_ids`-when-scoped rule):

```python
step1_ids = {row[1] for row in db_features_step1}
# (db_features_all / db_features_step1 unpacked from the helper's
#  (rows, tolerated) return above; step-1 iteration needs no tolerate gate --
#  tolerated sets are empty, so the loop is a no-op by construction)
for type_id, entity_id, artifact_path in db_features_all:
    feature_dir = os.path.join(artifacts_root, "features", entity_id)
    if os.path.isdir(feature_dir):
        continue
    if scoped:
        if entity_id in step1_ids:      # ours by workspace fact -> warning
            issues.append(Issue(...))   # "in DB but feature directory not found"
        else:                           # foreign workspace -> info bucket
            cross_project_count += 1
    else:                               # legacy branching, verbatim
        if entity_id in local_entity_ids or not local_entity_ids:
            issues.append(Issue(...))
        else:
            cross_project_count += 1
```

Workspace resolution (mirrors `checks.py:582-592` exactly — abspath, NULL-guard, tolerated failure):

```python
try:
    root_uuids = [r[0] for r in entities_conn.execute(
        "SELECT uuid FROM workspaces "
        "WHERE project_root IS NOT NULL AND project_root = ?",
        (os.path.abspath(project_root),),
    )]
except sqlite3.Error:
    root_uuids = []          # missing workspaces table -> unfiltered fallback
scoped = len(root_uuids) == 1   # step-1 two-arm scoping iff exactly one match
```

## Technical Decisions

1. **One helper, six call sites** — the discriminator logic (PRAGMA probe + severity routing) exists once; copies would drift exactly like the original rot did.
2. **PRAGMA probe only on the failure path, uncached** — zero happy-path cost; a failure re-runs one `PRAGMA table_info`, which is cheaper than getting cross-connection cache invalidation right (`sqlite3.Connection` accepts no attributes; `id(conn)` keys risk address-reuse staleness).
3. **Column-presence = "current schema" test** — matches spec SC#4: `kind`/`workspace_uuid` present-but-failing surfaces; absent tolerates. No version-number sniffing.
4. **`check_entity_orphans` drops its `project_id` kwarg consumption** — resolution moves to project-root → `workspaces` lookup (the kwarg's column is gone; keeping a dead parameter invites the next rot). The doctor runner's kwarg plumbing is untouched; the check simply stops reading it.
5. **AST-based scan test over grep** — mirrors the proven `check_status_write_path` AST approach (CLAUDE.md) and the authoring harness; grep would false-positive on comments and message text (spec SC#1's carve-outs).
6. **Deletion over parity** — no replacement check for `check_project_attribution`; `check_unknown_workspace_orphans` + its `claim_unknown_entities` fix action already own the surface (PRD Goal 4 / FR-12 doctor-shrink).

## Risks

- **Fixture drift in tests**: the existing suites DO create the old schema (verified: `_make_db`, `test_checks.py:22-59`) — handled by Component [D]'s fixture-migration plan (`_make_live_db` fork; legacy fixture retained only for pre-Migration-11 tests including the tolerate branch).
- **Hidden callers of check_project_attribution**: mitigated by grep-zero verification at implementation (`grep -rn check_project_attribution plugins/` → only deletions remain) plus the existing `CHECK_ORDER` consistency tests.
- **PRAGMA probe on foreign connections**: `entities_conn` in doctor checks may point at a copy/read-only DB; PRAGMA table_info is read-only and safe there.

## Dependencies

- None beyond stdlib (`ast`, `sqlite3`) and existing doctor/test infrastructure.
