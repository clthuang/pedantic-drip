# Design: State Projection Views (feature 120)

## Overview

One new dark module `views.py` registering two VIEW DDL statements (per-axis primitive + pivoted face) through 118's registry; a stdlib seeded replay property test; the #061 PRAGMA guard inside 119's `append_event`; guard-allowlist extension; and a committed latency-baseline artifact from one benchmark run. No new tables, no MCP changes, no live code paths.

## Key Decisions

### D1: two views — per-axis primitive + pivoted face (resolves spec D-1, lean (c) confirmed)
`views.py` registers ONE DDL script (`register_ddl("views", _VIEWS_DDL)`) containing both:
```sql
CREATE VIEW IF NOT EXISTS entity_axis_state AS
SELECT entity_uuid, axis, to_value, MAX(uuid) AS event_uuid, timestamp
FROM events
GROUP BY entity_uuid, axis;

CREATE VIEW IF NOT EXISTS entity_state AS
SELECT
  ent.uuid AS entity_uuid,
  (SELECT to_value  FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'pipeline')  AS pipeline_value,
  (SELECT timestamp FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'pipeline')  AS pipeline_at,
  (SELECT to_value  FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'execution') AS execution_value,
  (SELECT timestamp FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'execution') AS execution_at,
  (SELECT to_value  FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'lifecycle') AS lifecycle_value,
  (SELECT timestamp FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'lifecycle') AS lifecycle_at
FROM entities ent;
```
- **Bare-columns-with-MAX is the documented SQLite idiom, not the arbitrary-row hazard:** when a query uses the `max()` aggregate, SQLite takes bare output columns FROM THE ROW holding the maximum (documented "Bare columns in an aggregate query", sqlite.org lang_select §2.4; verified empirically on the venv's sqlite 3.51.0: larger-uuid-inserted-FIRST still yields the larger-uuid row's `to_value`). CONTRACT — the idiom is well-defined ONLY under two preconditions that both hold here and are load-bearing: (1) EXACTLY ONE min/max aggregate in the select (two-or-more → bare-column source row is arbitrary per the same doc section); (2) NO ties on the aggregated column (events.uuid is the PRIMARY KEY — MAX(uuid) is never tied), which is also why `to_value` AND `timestamp` provably come from the SAME winning row. Any future view adding a second min/max must materialize the winning uuid first (join/subquery), not rely on bare-column provenance. The spec's rowid-confound fixture guards the DIFFERENT, genuinely-arbitrary case (bare columns with NO min/max aggregate) and any rewrite away from this idiom — it stays mandatory.
- **Column names are axis-generic** (`pipeline_value`, not `pipeline_phase`): feature 122 owns the two-axis VALUE vocabularies and their live names; naming the pivoted columns after 122's future CHECK-constrained fields would let 120 pre-empt 122's naming decision. 122/125 may add renamed convenience views; this module owns latest-wins only.
- **Pivoted view selects FROM `entities`** — zero-event entities appear as an all-NULL-state row (SC1); orphan events (raw-INSERT residual surface) appear in `entity_axis_state` but NOT in `entity_state` (no entities row to hang them on) — the D-1 orphan-semantics call: the primitive is exhaustive over events, the face is exhaustive over entities; documented, not defended.
- `timestamp` rides along in the per-axis view so consumers answer "current value + when" without a second query (spec item 1's minimum).

### D2: views.py module shape + registration-order dependency (resolves the bootstrap-ordering seam)
`views.py` mirrors events.py's dark-module preamble and IMPORTS `entity_registry.events` at module top — not for symbols, but because `register_ddl` replays IN REGISTRATION ORDER (schema_v2.py:96-98/:134) and both views reference the `events` table: importing events.py first guarantees its DDL precedes the views' in the registry. (`entities` is core DDL, always first.) The factory-requirement docstring (119 precedent) restates: consumers must import DDL owners before `bootstrap_v2`; 132 owns the canonical import-all. A module-top comment pins the import as load-bearing so a linter/reviewer doesn't strip the "unused" import.

### D3: #061 guard — PRAGMA probe at append_event entry (resolves spec D-3, binding lean confirmed)
In events.py, first statement of `append_event` (BEFORE the `conn.in_transaction` branch — both compose and standalone paths covered by construction):
```python
row = conn.execute("PRAGMA foreign_keys").fetchone()
if row is None or row[0] != 1:
    raise ValueError(
        "append_event requires a connect_v2 connection "
        "(PRAGMA foreign_keys=ON is per-connection; a bare sqlite3.connect "
        "would write orphan-capable rows into the immutable events table — backlog #061)"
    )
```
- One PRAGMA read per append — negligible vs the transaction cost; catches ANY foreign_keys=OFF connection regardless of provenance.
- Forwards through the retry-wrapper test doubles (they proxy `.execute` to a real connect_v2 conn — spec's binding constraint verified at test_events.py:371/:409).
- `read_events` is NOT guarded — reads can't create orphans; guarding reads would break the property test's ad-hoc read connections for zero safety gain.
- events.py's FR-11/factory docstrings gain one line naming the guard; #061 is closed by this feature (backlog entry updated at finish).

### D4: replay property test mechanics (resolves spec D-2)
In new `test_views.py`:
- **One bootstrapped file DB for the whole property run** (spec's <5s steer): `bootstrap_v2` once; cases NEVER delete events — the immutability triggers forbid `DELETE` (events.py DDL), so cleanup is impossible by design. Isolation instead comes from per-case entity namespaces: each case seeds fresh entity uuids and the assertion compares ONLY that case's entities (view queried `WHERE entity_uuid IN (case uuids)`).
- **Generator:** `random.Random(MASTER_SEED)` (module constant, e.g. `0x120`) mints a per-case seed; each case builds its OWN `random.Random(case_seed)` and EVERY stochastic draw — entity/event counts, axis, value, actor, out-of-order timestamps, the shuffled-insert coin flip, AND the uuid shuffle — comes from that instance; the global `random` module is never touched (a stray global draw would break SC3's fixed-master-seed determinism run-to-run).
- **Shuffled-insert constraint (rowid confound):** for ~half the cases (per-case coin flip), the case pre-mints ALL its event uuids via `generate_uuid7()`, SHUFFLES them, and writes via raw `INSERT` on the connect_v2 conn binding the shuffled uuid explicitly — insertion/rowid order diverges from uuid order. The other half writes through `append_event` (API-path realism). Both halves feed the same replay.
- **Replay:** pure-Python fold — `dict[(entity_uuid, axis)] = max(events, key=lambda e: e.uuid)`; compare `to_value`, `event_uuid`, `timestamp` field-by-field against `entity_axis_state`, and the pivoted row against the folded triple.
- **Failure output:** `pytest.fail(f"seed={case_seed}: {sequence!r} ...")` — seed + full sequence printed; no shrinker (YAGNI, sequences ≤ 96 events).
- **Budget:** N=200 cases, one DB, no per-case bootstrap → well under the 5s non-regression guard.

### D5: fixture-level SC1/SC2 tests (deterministic complements to the property test)
- SC1 pins as explicit fixtures (not property cases): three-axis latest; out-of-order-timestamp (later uuid, earlier timestamp wins); rowid-confound with DISTINCT to_values (larger uuid inserted first; assert the larger-uuid row's value — kills both a no-aggregate bare-column view and any rowid-latest rewrite); single-axis entity (other pivoted columns NULL, per-axis has one row); zero-event entity (absent from per-axis; all-NULL pivoted row); NULL to_value latest (latest-wins even when NULL — "latest non-null" is the rejected semantic, pinned).
- SC2: `INSERT`/`UPDATE`/`DELETE` against BOTH views → `sqlite3.OperationalError` (six pins, parametrized); `PRAGMA table_info(entities)` column set == 118's DDL list (no state columns crept in).
- #061 (SC4): bare-conn standalone → raise + zero rows; bare-conn with open transaction (compose path) → same; connect_v2 → unchanged (existing suite is the regression net); `test_bare_connection_inserts_the_same_orphan_successfully` PRESERVED byte-unchanged.

### D6: ships-dark guard extension (resolves spec item 4)
`_V2_DARK_MODULES` += `"views.py"`; `_V2_LIVE_REFERENCE_NEEDLES` += three spellings (`entity_registry.views`, `from entity_registry import views`, `from .views import`); three seeded-offender teeth tests (one per spelling, relative included) — 121's exact pattern.

### D7: latency baseline artifact (resolves spec D-4)
Run `bash plugins/pd/hooks/tests/bench-session-start.sh` at a clean committed point during implement; write `docs/features/120-state-projection-views/latency-baseline.md` containing: both medians (baseline_sha=merge-base and HEAD — on this branch both estimate the same quantity; say so), raw script output pasted verbatim, machine context (`sw_vers`/`uname -m`/CPU), reproduction command, and the SCOPE STATEMENT verbatim-mirroring spec item 5 (empty-HOME fixed overhead, median-only; NOT NFR-3's populated p50/p95 — capture assigned to 126, verification to 127, roadmap.md:42). The existing `bench-results.txt` convention ("generated at PR open; do not re-commit") stays untouched — this artifact is feature-docs, not the hook-test fixture.

## Data Flow

Post-132 shape (nothing live now): state readers query `entity_state`/`entity_axis_state`; writers call `append_event` (guarded); the views recompute latest-per-axis on read. Dark until then; the property test is the only consumer.

## Error Handling

- Guard raise (#061): `ValueError` naming the contract + backlog id, before any write, both transaction modes.
- View queries on an un-bootstrapped DB: "no such table/view" propagates — same posture as every v2 surface pre-bootstrap.
- Property-test failure: seed + sequence in the failure message (reproducible).

## File Change Inventory

| File | Change |
|------|--------|
| `plugins/pd/hooks/lib/entity_registry/views.py` | NEW dark module — `_VIEWS_DDL` (two views), `register_ddl("views", ...)`, load-bearing events import (D1/D2) |
| `plugins/pd/hooks/lib/entity_registry/events.py` | + #061 PRAGMA guard at append_event entry + docstring line (D3) |
| `plugins/pd/hooks/lib/entity_registry/test_views.py` | NEW — fixture pins (D5 SC1/SC2) + replay property test (D4) |
| `plugins/pd/hooks/lib/entity_registry/test_events.py` | + SC4 guard tests (standalone + compose bare-conn); :506 raw-INSERT pin untouched (D5) |
| `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py` | `_V2_DARK_MODULES` + 3 needles + 3 teeth for views.py (D6) |
| `docs/features/120-state-projection-views/latency-baseline.md` | NEW artifact (D7) |
| `docs/backlog-manual.md` | #061 marked closed-by-120 (at finish) |

## Testing Strategy

- **#1 (SC1, `test_views.py`):** the six deterministic fixtures of D5 — three-axis latest, out-of-order timestamp, rowid-confound (distinct values, larger-uuid-first), single-axis NULLs, zero-event all-NULL pivoted row + per-axis absence, NULL-to_value latest-wins.
- **#2 (SC2):** parametrized INSERT/UPDATE/DELETE × both views → OperationalError; `PRAGMA table_info(entities)` pin.
- **#3 (SC3, property):** D4's generator — N=200, master seed pinned, ~half shuffled-insert cases, field-by-field equality per-axis AND pivoted, <5s guard (a plain duration assert around the loop).
- **#4 (SC4, `test_events.py`):** bare-conn standalone raise + zero rows; bare-conn compose raise + zero rows; connect_v2 pass; :506 preserved — verification is diff-level (not modified) and STRUCTURAL: :506 exercises the raw-INSERT surface (`bare_conn.execute("INSERT INTO events…")`, :519-527) and never enters `append_event`, so the guard is orthogonal to it by construction; caller audit: every existing `append_event` call site in the suite uses an FK-ON connection (connect_v2 directly, or retry wrappers forwarding `.execute` to one, :389-394/:419-423), so the guard raises for none of them — "unchanged AND green" is self-evident, not asserted.
- **#5 (SC6 guard):** three teeth + needle-set extension; full-suite/validate/doctor neutrality at integration QA.
- **#6 (SC5):** artifact existence + required sections (gate-level read at finish QA, no pytest).

## Risks

- **Bare-column idiom misread as a bug:** the D1 note cites the documented behavior + the empirical check; the rowid-confound fixture keeps any rewrite honest.
- **Property-test flake via shared DB:** per-case entity namespaces + append-only table = no cross-case interference by construction.
- **Bench run variance:** the artifact records both medians + raw output; it is a snapshot, not a gate.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.
