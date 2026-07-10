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

**Dead-branch revival, acknowledged**: the old `:1391` scoped branch is DEAD in production — `run_diagnostics` builds ctx without a `project_id` key (`doctor/__init__.py:165-172`), so `kwargs.get("project_id")` is always None and only the unfiltered `:1398` branch ever ran. Routing scoping through `project_root` (which IS in ctx) makes scoping reachable for the first time — a behavior change, not a reconstruction. To avoid the new false-positive class this could create (an on-disk dir whose entity carries a different REAL workspace_uuid getting step-2-flagged "no entity in DB"), the two queries take distinct roles:

- **Step-2 membership** (`db_feature_ids`, consumed at `checks.py:1444`) is built from the UNFILTERED `:1398` query, always — a dir whose entity exists under ANY workspace is never flagged "has .meta.json but no entity in DB" (spec SC#2 holds for every exists-in-both case, foreign-real-workspace included; matches today's only-reachable behavior).
- **Step-1 reporting** (DB→disk orphan sweep, `checks.py:1405-1421`) iterates the two-arm scoped row-set (`:1391`) when exactly one `workspaces` row matches the project root; 0 or >1 matches → step 1 iterates the unfiltered set (current behavior). Foreign-workspace entities are thus excluded from step-1 reporting; unknown-bucket entities are treated as local (spec's unknown-bucket AC holds a fortiori since step-2 membership is unscoped).

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

- Fork the helpers: `_make_live_db()` builds fixtures via the real `EntityDatabase(tmp_path)` bootstrap (live schema, as `test_polymorphic_taxonomy.py` does); a live `_register_feature` inserts `kind='feature'` rows. The legacy `_make_db`/`_register_feature` are RETAINED only for tests that legitimately exercise pre-Migration-11 schemas (per `_make_db`'s own docstring, `test_checks.py:25-29`) — including the new tolerate-branch test.
- Repoint the three rewritten checks' behavioral suites (`test_check7_*`, `check_feature_status`, `check_brainstorm_status` tests) onto the live fixtures.

1. Per-check regression: for each retained check, build a live-schema DB via `_make_live_db()` and assert the check's queries execute (no schema `sqlite3.Error` surfaces, no tolerate-branch engagement — assert via returned candidate sets being non-vacuous where the fixture registers rows).
2. Committed EXPLAIN scan: AST-walk `checks.py` for constant SQL in `execute()` calls (same technique as the authoring harness), `EXPLAIN` each against a live-schema connection, assert zero failures. Durable form of spec SC#1.
3. Surface-branch test: live-schema DB, monkeypatch/corrupt a query to fail while `kind` exists → assert one `error` Issue naming the check.
4. Tolerate-branch test: LEGACY fixture (`_make_db`, genuinely no `kind` column) → assert clean completion, zero Issues from the rewritten sites — the legacy fixture guards against vacuous green by construction.
5. Scoping tests: foreign-workspace entity excluded from step-1 reporting; unknown-bucket entity treated local (step 1) and never step-2-flagged; foreign-real-workspace ON-DISK dir NOT step-2-flagged (unscoped membership); 0/>1 workspace-match → unfiltered step-1 fallback.
6. Deletion tests: doctor run emits zero `project_attribution` issues; `test_doctor.py` `expected_names` updated and its `CHECK_ORDER` assertion passes.

## Interfaces

```python
def _run_live_schema_query(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple,
    check_name: str,
    issues: list[Issue],
    required_columns: tuple[str, ...],   # e.g. ("kind",) or ("kind", "workspace_uuid")
) -> list[tuple]:
    """Execute sql; return rows.

    On sqlite3.Error:
      - If every column in required_columns exists in entities' current schema
        (PRAGMA table_info probe, run on the failure path only — no cache;
        failures are rare and the probe is one PRAGMA) -> append one
        error-severity Issue(check=check_name, message=f"{check_name}: schema
        query failed: {exc}") and return [].
      - If any required column is absent (pre-Migration-11 DB) -> return []
        silently (tolerate branch, spec SC#4).
    """
```

Call-site contract: every rewritten site passes its `required_columns`; sites keep their existing downstream logic operating on returned rows (`db_features`, candidate sets). The helper NEVER raises. `:1083`'s `.fetchone()` usage adapts to the list return (`rows[0] if rows else None`), and its enclosing `try/except sqlite3.Error` at `checks.py:1066-1099` STAYS — it also guards EXPLAIN-clean sibling queries (`:1068`, `:1074`) that are out of scope.

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
