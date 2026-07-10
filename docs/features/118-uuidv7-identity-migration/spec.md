# Specification: UUIDv7 Identity Migration

## Problem Statement

The entity DB's identity model is split between `uuid` primary keys and business-key uniqueness (`UNIQUE(workspace_uuid, type_id)`, `workflow_phases` keyed on `type_id`, display slugs doing identity work), which produced the collision/renumber/cross-workspace failure class P004 exists to kill — and the v2 rebuild has no schema foundation to build on: no v2 DDL module exists, ids are generated with random `uuid4` (4 runtime sites + 2 frozen migration-embedded sites), and `requires-python >= 3.12` blocks stdlib `uuid.uuid7` (the exact blocker that deferred UUIDv7 in feature 108 F6 / backlog #00359).

## Evidence

- PRD FR-4: "UUIDv7 is the sole identity, used by every table incl. the workflow-state and events tables. No uniqueness constraint on any human-readable field." NFR-2: `requires-python >= 3.14` (venv verified 3.14.6; `plugins/pd/pyproject.toml:4` currently `>=3.12`).
- Rebuild-not-migrate is settled: "Migrate schema v17 → v18 in place — Rejected (the 114→117 chain demonstrates the repair tax)" (PRD Approaches Considered). The live v17 DB is untouched until feature 132's replay cutover.
- Current identity sprawl: `entities` PK `uuid` but `UNIQUE(workspace_uuid, type_id)` business key; `workflow_phases` PK'd on `type_id` (not uuid); `str(uuid_mod.uuid4())` at 6 sites — 4 RUNTIME generators (`database.py:6775` entity register, `:7801` + `:9736` workspace mint, `project_identity.py:685` workspace mint) and 2 FROZEN migration-embedded sites (`database.py:272` inside the copy-rename entities migration, `:1855` inside Migration 11) that stay uuid4 because editing v17 migration functions is out of bounds; schema version upserted across ~127 migration touch points in `database.py` (PRD FR-12's "ONE version location" targets this sprawl in the v2 module).
- Behavioral constraint (PRD): "No business-key uniqueness constraints. Rationale: reintroduces the collision/renumber class."
- Version-pinned validators (found at spec review iteration 2): `_UUID_V4_RE` (`database.py:25-26`, duplicated `frontmatter.py:57-58`) hardcodes version nibble `4`, gating entity-lookup routing (`database.py:6054`), `resolve_ref` (`:6283`), and frontmatter validation (`frontmatter.py:118`); ~19 test assertions pin v4 format on minted uuids. By contrast `_WORKSPACE_UUID_RE` (`project_identity.py:30-34`) already accepts `[1-7]` by design.

## Success Criteria

- [ ] A v2 schema module exists (new file under `plugins/pd/hooks/lib/entity_registry/`) that bootstraps a FRESH SQLite DB (WAL mode) with the v2 core tables — `workspaces`, `entities`, `entity_relations`, `sequences` — where every table's primary key is a UUID string column and every inter-table reference is by uuid (verify: `PRAGMA table_info`/`index_list` on a bootstrapped DB shows uuid PKs and ZERO UNIQUE constraints on any human-readable column: `type_id`, `slug`, `name`, display fields).
- [ ] The module exposes ONE version location: a single `V2_SCHEMA_VERSION` constant written once at bootstrap into a `_metadata` table row keyed `schema_version` (verify: exactly ONE SQL write statement — INSERT/UPDATE/REPLACE targeting `_metadata`'s `schema_version` row — exists in the v2 module; the constant SYMBOL may appear multiple times, the write site may not. No per-migration upsert chain).
- [ ] The module is additively extensible by the sibling features: registering additional DDL statements (feature 119 `events`, 120 views, 122 axis CHECKs) requires appending to one declared DDL registry, not editing bootstrap logic (verify: a test registers a dummy table through the extension point and bootstrap creates it).
- [ ] A `generate_uuid7()` helper (scope-neutral name — 3 of the 4 runtime sites mint WORKSPACE uuids, not entity uuids) returns stdlib `uuid.uuid7()` strings, and the 4 RUNTIME `uuid4` generation sites (`database.py:6775,7801,9736`, `project_identity.py:685`; the `:563` docstring mention updated to match) route through it. The 2 migration-embedded sites (`database.py:272`, `:1855` — inside the copy-rename entities migration and Migration 11 respectively, marker `[migration-11]` at `:1866`) are explicitly EXCLUDED — they live inside frozen v17 migration functions whose entire chain is discarded at feature-132 replay (verify: grep `uuid4(` in non-test `entity_registry/` code returns EXACTLY the two frozen sites, nothing else; helper unit test asserts version nibble == 7 and intra-process monotonic sort order).
- [ ] Every uuid validator accepts uuid7: `_UUID_V4_RE` widened to version nibble `[1-7]` and renamed `_UUID_RE` at BOTH definition sites (`database.py:25-26`, `frontmatter.py:57-58`), and a minted uuid7 entity ROUND-TRIPS the three gated paths — `get_entity`-by-uuid routing (`database.py:6054`), `resolve_ref` uuid branch (`database.py:6283`), frontmatter `entity_uuid` validation (`frontmatter.py:118`) — via positive assertions (verify: a test registers an entity whose uuid is version 7, resolves it by uuid through both DB paths, and validates a frontmatter header carrying it; the grep battery alone is NOT sufficient — it stays green while misrouting ships).
- [ ] `plugins/pd/pyproject.toml` declares `requires-python = ">=3.14"`, and the full test suite passes under the venv Python 3.14.6 AFTER the in-scope test updates (v4-pinned minted-uuid format assertions in `test_database.py`/`test_server_helpers.py` made version-agnostic; the five version-boundary rejection tests across `test_frontmatter.py`/`test_database.py` re-scoped per In Scope; all other tests unchanged) (verify: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/` green; no `uuid.uuid7` AttributeError anywhere).
- [ ] The LIVE v17 database file and its migration chain in `database.py` are untouched — no in-place migration, no v17 DDL edits, no edits inside migration function bodies (the frozen `:272`/`:1855` uuid4 sites stay; verify: `git diff` shows no changes to existing migration functions). Doctor regression check is same-session before/after: capture doctor output against the live DB immediately before and immediately after the rewiring commit; the diff shows no new issue classes and no check crashes (a frozen historical snapshot is NOT the baseline — live entity state drifts between sessions).

## Scope

### In Scope

- New v2 schema module: core-table DDL (uuid PKs, uuid FKs, no business-key uniqueness), fresh-DB bootstrap (WAL, busy_timeout, `V2_SCHEMA_VERSION` written once), and a declared DDL-registry extension point for sibling features.
- 118/121 boundary on `sequences`: 118 owns the `sequences` TABLE DDL (ships empty in core bootstrap); feature 121 owns only the allocation logic on top and does NOT re-create the table. Minimal column contract 121 depends on: `uuid` TEXT PK, `workspace_uuid` TEXT FK → `workspaces(uuid)`, `kind` TEXT, `current_value` INTEGER — an allocator `kind` column carries no business-key UNIQUE constraint (not in the forbidden set: `type_id`/`slug`/`name`/display fields).
- `generate_uuid7()` helper + rewiring the 4 RUNTIME `uuid4` generation sites to it. uuid7 strings are drop-in values for the v17 TEXT uuid COLUMNS, but NOT for the v4-pinned validators (next bullet) — the two must ship together. The 2 migration-embedded uuid4 sites are frozen (see Success Criteria).
- Version-agnostic uuid validation: widen `_UUID_V4_RE` (`database.py:25-26`, `frontmatter.py:57-58` — version nibble pinned to `4`, so uuid7 values would misroute entity lookup at `database.py:6054`, `resolve_ref` at `:6283`, and FAIL frontmatter validation at `frontmatter.py:118`) to accept version nibble `[1-7]`, mirroring `_WORKSPACE_UUID_RE`'s forward-compatible design (`project_identity.py:30-34`); rename to `_UUID_RE` so the name stops lying. Update the affected tests — the complete version-nibble-reversal set (every test asserting a v1/v3/v5 uuid is REJECTED, which flips under `[1-7]`): (a) `test_frontmatter.py::TestValidateHeaderUUIDBoundary` — `test_validate_header_uuid_wrong_version_digit_3` (~`:1159`), `test_validate_header_uuid_version_digit_exactly_4_not_5` (~`:1187`); (b) `test_database.py::TestResolveIdentifierBoundary` (~`:2033`) — `test_uuid_v1_format_not_matched_as_uuid` (~`:2074`), `test_uuid_v5_format_not_matched_as_uuid` (~`:2086`), `test_uuid_v3_format_not_matched_as_uuid` (~`:2096`) — re-scope all five to version-agnostic acceptance; plus v4-pinned FORMAT assertions on minted uuids in `test_database.py` / `test_server_helpers.py`. The variant-nibble `[89ab]` boundary tests in both files stay as-is (variant unchanged by uuid7).
- `requires-python >= 3.14` bump in `plugins/pd/pyproject.toml`.
- Unit tests: bootstrap shape (PKs, no human-key UNIQUEs), extension point, uuid7 version/monotonicity, one-version-location check, uuid7 entity round-trip through the three formerly-v4-gated paths.

### Out of Scope

- `events` table DDL and append path (feature 119); state projection views (feature 120); `pipeline_phase`/`execution_status` columns (feature 122); display-id ALLOCATION logic (feature 121 — the `sequences` table itself ships in 118, empty).
- Any change to the LIVE v17 schema, its migrations, or `workflow_phases` (the v17 table keeps working until cutover).
- Backfill/cutover of existing data (feature 132); doctor changes (131 done / 133 later).
- Consumer rewiring: nothing reads the v2 DB in this feature — the module ships dark, exercised only by its tests.

## Acceptance Criteria

### Happy Paths

- Given a temp path, when the v2 bootstrap runs, then a WAL-mode SQLite file exists containing `workspaces`, `entities`, `entity_relations`, `sequences`, each with a uuid TEXT PRIMARY KEY, and the `_metadata` table's `schema_version` row holds `V2_SCHEMA_VERSION`, written by exactly one code site.
- Given the bootstrapped v2 DB, when `PRAGMA index_list` is inspected per table, then no UNIQUE index covers `type_id`, `slug`, `name`, or any display field.
- Given two entities registered in the v2 `entities` table with the SAME `type_id` and workspace, when both inserts run, then both rows exist (no constraint violation) — business keys are non-unique by design.
- Given `generate_uuid7()` called 1000× in-process, when the results are compared, then all are version-7 UUIDs and their string sort order equals their generation order (uuid7 time-ordering; empirically demonstrated in the venv at spec authoring: 10,000 consecutive `uuid.uuid7()` strings were already sorted and all version-7 — CPython 3.14 maintains a per-process timestamp+counter for intra-millisecond monotonicity).
- Given a sibling feature registers `CREATE TABLE events (...)` via the DDL registry, when bootstrap runs, then the table exists — no bootstrap-logic edit needed.
- Given an entity registered after the rewiring (uuid version 7), when it is fetched by uuid via `get_entity` routing (`database.py:6054`), resolved via `resolve_ref` (`:6283`), and its uuid is validated in a frontmatter header (`frontmatter.py:118`), then all three paths succeed — positive round-trip assertions, not grep absence.

### Error & Boundary Cases

- Given a v2 DB already bootstrapped at the target path, when bootstrap runs again, then it is idempotent (no error, no duplicate DDL application, version unchanged).
- Given Python < 3.14 (no `uuid.uuid7`), when the helper module imports, then the failure is immediate and names the 3.14 floor (no lazy AttributeError deep in a write path) — verify with a monkeypatched absence.
- Given the live v17 DB, when the full existing test suite and a live doctor run execute after the uuid7 rewiring, then the test suite is green and the doctor diff against the same-session pre-change capture shows no new issue classes (uuid7 strings are valid TEXT uuids; the workspace-uuid regex at `project_identity.py:30-34` already accepts version nibble `[1-7]`).

## Feasibility Assessment

### Assessment
**Overall:** Confirmed
**Reasoning:** `uuid.uuid7` exists in the venv (3.14.6, re-verified at spec authoring: `python -c "import uuid; uuid.uuid7()"` succeeds per NFR-2). The v2 module is additive new code with no live consumers. The uuid4→uuid7 swap changes the VALUE generated into existing TEXT columns AND requires widening the two v4-pinned validator regexes (in scope) — with both shipped together, all consumers accept the new values.
**Key Assumptions:**
- ALL version-aware uuid consumers in non-test `hooks/lib` code are enumerated — Status: Verified at spec review iteration 2 by full grep for `_UUID_V4_RE` and version-nibble regex patterns. The complete set: `_WORKSPACE_UUID_RE` (`project_identity.py:30-34`, already accepts `[1-7]`, no change needed) and `_UUID_V4_RE` (`database.py:25-26` used at `:6054`/`:6283`; `frontmatter.py:57-58` used at `:118` — all v4-pinned, widened in scope). Iteration-1's claim that `_WORKSPACE_UUID_RE` was the ONLY such consumer was false (grep searched `.version`/`[1-7]` and missed regex-encoded nibbles); iteration 2's sweep searched the regex pattern space itself.
- uuid7's variant field matches the existing `[89ab]` variant nibble in both regexes (RFC 9562: uuid7 uses the same IETF variant) — Status: Verified (venv-generated uuid7 samples match `-[89ab]` at position 20).
- `uv`-managed venv already at 3.14.6, so the `requires-python` bump breaks no local tooling — Status: Verified (PRD NFR-2 evidence + spec-authoring re-check).
**Open Risks:** If any external script pins an older Python against `plugins/pd`, the floor bump surfaces it loudly at resolve time — acceptable (private tooling, single user).

## Dependencies

- None among P004 features (this is the foundation; 119/120/121/122/129 build on it).

## Open Questions

- None. The v17-untouched boundary and the ships-dark posture are settled by the PRD's rebuild-not-migrate decision.
