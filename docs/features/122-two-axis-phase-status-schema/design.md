# Design: Two-Axis Phase/Status Schema (feature 122)

Implements every spec FR; the spec's deferred decisions (EXECUTION_STATUSES exact set, trigger interpolation mechanism, named-view layering, owner names) are pinned in D1-D7. (A design-authoring false premise — "RAISE is static-string only" — briefly weakened spec FR122-3 and was REVERTED after the design skeptic cited SQLite 3.47.0's expression-RAISE and an empirical probe on this venv's 3.53.2 confirmed value interpolation works; the behavior-claims-need-citations class, self-inflicted at the design layer.)

## D1 — Vocabularies (OQ-3 RESOLVED with recorded rationale)

```python
PIPELINE_PHASES = ("brainstorm", "specify", "design", "create-plan", "implement", "finish")
EXECUTION_STATUSES = ("backlog", "prioritised", "ready", "wip", "blocked", "documenting", "completed")
```

Both frozen ordered tuples; membership tests use `frozenset` views derived from them (single objects, exported).

**OQ-3 resolution (PRD prd.md:193):** `EXECUTION_STATUSES` = the six reachable `derive_kanban` outputs (kanban.py:8-40) PLUS `ready` (FR-8) = SEVEN total, in the live board's render order with `ready` inserted after `prioritised` and the dead pair removed (board COLUMN_ORDER is 8 columns, board.py:17-26; `agent_review`/`human_review` have 0 rows EVER and are unreachable from derive_kanban — they STAY DEAD: not in the vocabulary; the dead COLUMNS can be dropped by 125's rewire or any later UI pass — that is a suggestion to 125's specify, NOT an assertion of 125's committed scope (no roadmap entry assigns it; 122's vocabulary excludes the pair regardless — they render empty today)). `ready` IS included (iteration-2 correction — the initial "nothing distinguishes it from backlog" rationale was REFUTED by committed PRD FR-8, prd.md:86: `blocked → ready` is the post-unblock cascade target owned by feature 124; without it, 124's cascade writes would be REJECTED by this very trigger). Order: after `prioritised` (unblocked-and-runnable sits before `wip`); derive_kanban never emits it (predates FR-8) so the SC3 superset holds strictly. HANDOFFS: 124 asserts `ready ∈ EXECUTION_STATUSES` at its cascade implementation; 125's specify must decide the board column for `ready` (no column renders it today — same suggestion-not-scope posture as the dead-pair drop). Spec FR122-2's superset requirement is satisfied with exactly ONE addition beyond the six, rationale = FR-8 (recorded per FR122-2).

## D2 — Vocab triggers: built FROM the constants; EXPRESSION-message RAISE (value in the error)

`_VOCAB_TRIGGER_DDL` interpolates the tuples into SQL `IN (...)` lists at module load — PINNED MECHANISM: `"(" + ", ".join(f"'{v}'" for v in PIPELINE_PHASES) + ")"`, guarded by a module-load assertion that no vocabulary value contains `'` (a future apostrophe-bearing value fails LOUD at import, never emits malformed DDL; today's thirteen values are all quote-free identifier tokens). Two BEFORE INSERT triggers on `events`:

```sql
CREATE TRIGGER IF NOT EXISTS events_vocab_pipeline BEFORE INSERT ON events
WHEN NEW.axis = 'pipeline' AND NEW.to_value IS NOT NULL
     AND NEW.to_value NOT IN ({pipeline_list})
BEGIN SELECT RAISE(ABORT, 'out-of-vocabulary to_value ' || quote(NEW.to_value) || ' on pipeline axis (feature 122 — see entity_registry/axes.py PIPELINE_PHASES)'); END;

CREATE TRIGGER IF NOT EXISTS events_vocab_execution BEFORE INSERT ON events
WHEN NEW.axis = 'execution' AND NEW.to_value IS NOT NULL
     AND NEW.to_value NOT IN ({execution_list})
BEGIN SELECT RAISE(ABORT, 'out-of-vocabulary to_value ' || quote(NEW.to_value) || ' on execution axis (feature 122 — see entity_registry/axes.py EXECUTION_STATUSES)'); END;
```

(Both triggers spelled verbatim per events.py's stated-DDL convention, events.py:86-89.)

(Dated note 2026-07-12, battery absorption: BOTH D2 guards — the module-load apostrophe check and register_vocab_ddl's version check — ship as TYPED raises (ValueError / RuntimeError), not bare `assert`: two independent battery reviewers (security + quality) flagged that `python -O` strips asserts, and the sibling idiom (events.py, schema_v2.py) is typed raises. Same trigger points, same messages, strictly louder.)

(Dated note 2026-07-12, implement task 1: `{pipeline_list}`/`{execution_list}` denote the ALREADY-PARENTHESIZED product of the pinned interpolation above — reading this block's literal `NOT IN ({...})` as adding its own parens double-parenthesizes, a SQLite "row value misused" error, empirically probed on 3.53.2. Shipped DDL is `NOT IN {list}` with the mechanism's own parens; trigger names, WHEN shape, and RAISE message text are verbatim. Design-internal inconsistency resolved in favor of the pinned mechanism.)

Expression messages in RAISE require SQLite ≥ 3.47.0 (2024-10-21); this venv runs 3.53.2 and the form was EMPIRICALLY PROBED here (in-vocab accepted; out-of-vocab rejected with `out-of-vocabulary to_value 'bogus-value' on pipeline axis (feature 122)`). `register_vocab_ddl()` asserts `sqlite3.sqlite_version_info >= (3, 47, 0)` before registering — a pre-3.47 runtime fails loud at registration, never with malformed-DDL confusion. SC2's rejection tests assert BOTH the axis and the offending value appear in the message text. Lifecycle has NO trigger (spec: vocab-free, renames carry type_ids).

**Registration:** `register_vocab_ddl()` calls `schema_v2.register_ddl("axes_vocab_triggers", _VOCAB_TRIGGER_DDL)` — NEVER at import (spec's register-on-demand mechanism, verified rationale: snapshot/RESTORE registry + collection-time imports would leak into 120/126's suites). Idempotence: a second call raises register_ddl's duplicate-owner ValueError — callers guard via the exported `is_vocab_registered()` (canonical name — D4's export list governs); the 122 test fixture registers once per snapshot scope.

## D3 — Named view: a thin rename over 120's `entity_state` (zero new MAX)

```sql
CREATE VIEW IF NOT EXISTS entity_phase_status AS
SELECT entity_uuid,
       pipeline_value  AS pipeline_phase,  pipeline_at,
       execution_value AS execution_status, execution_at
FROM entity_state;
```

Inherits 120's bare-column CONTRACT wholesale (no new aggregate — the winning-row semantics live entirely in 120's shipped primitives); values verbatim (FR122-4); lifecycle columns intentionally not exposed (FR-6 names two axes). **#067 inheritance note (in the module docstring):** per-entity reads through this view inherit entity_state's O(total-events) correlated-subquery cost — consumers follow #067's guidance (per-entity → entity_axis_state; full-table → fine).

## D4 — Module shape & registration order

`entity_registry/axes.py` (dark; preamble mirrors views.py): module-top `from entity_registry import views` — LOAD-BEARING for registration ORDER (axes' view SELECTs FROM entity_state, so views' DDL must replay first; views itself imports events — the chain gives events → views → axes; comment states the chain). The named view self-registers at import under owner `"axes"` (the events.py/views.py precedent); ONLY the trigger DDL is register-on-demand under owner `"axes_vocab_triggers"` (distinct owners — register_ddl raises on duplicates; phase-gate suggestion honored). Constants + `register_vocab_ddl()` + `is_vocab_registered()` exported.

## D5 — Tests (`test_axes.py`, all inside the snapshot/restore fixture idiom)

1. **Exact-membership pins:** `PIPELINE_PHASES == (...)` and `EXECUTION_STATUSES == (...)` — tuple equality (order pinned too). The 126 precedent (downstream features assert against these).
2. **Trigger teeth, exhaustive:** with `register_vocab_ddl()` in fixture scope — EVERY member of both tuples accepted on its axis (raw INSERT, 13 acceptance probes: 6 pipeline + 7 execution); out-of-vocab rejected per axis (incl. cross-axis vocabulary: `'wip'` on pipeline rejected, `'design'` on execution rejected; wrong case `'WIP'` rejected); NULL accepted on all three axes; lifecycle free-text + type_id-shaped + legacy `completed` accepted. Rejection asserts `sqlite3.IntegrityError` EXACTLY (RAISE(ABORT) in a trigger = SQLITE_CONSTRAINT_TRIGGER → IntegrityError; 119's immutability-trigger precedent) with BOTH the axis and the offending value present in the message text (expression-RAISE, D2).
3. **Leak-detection pin (spec SC6's structural guarantee):** a bootstrap WITHOUT `register_vocab_ddl()` accepts an out-of-vocab pipeline INSERT — proving sibling suites can never be affected.
4. **Compatibility pin (SC3):** every reachable `derive_kanban` output (import the LIVE kanban module from the test — tests importing live code is unrestricted; the dark guard polices the reverse) is a member of `EXECUTION_STATUSES`; reachability enumerated from kanban.py's map values + terminal branches, asserted a STRICT SUBSET (the six ⊂ the seven — `ready` is FR-8's, unreachable from derive_kanban by design).
5. **View pins (SC4):** names exact (`PRAGMA table_info` column list == the five FR-6 names); the round-trip seed uses DISTINCT in-vocab values AND DISTINCT timestamps on the two axes, and asserts ALL FOUR axis columns (pipeline_phase, execution_status, pipeline_at, execution_at) against their `entity_axis_state` counterparts — a swapped column alias OR a swapped `*_at` source is red, never green (non-vacuity pin); write-rejection (view read-only, 120's pin pattern).
6. **Ships-dark teeth (SC5):** `_V2_DARK_MODULES` += `"axes.py"`; three needle spellings; 3 seeded-offender teeth red-first.
7. **Raw-INSERT enforcement (FR122-3):** the rejection probes in (2) use raw `conn.execute` INSERTs (not append_event) — structural proof.

## D6 — Spec touch-up inventory (same commit as design approval)

REVERT of the transient static-RAISE weakening: FR122-3 + SC2 + boundary case 1 restored to "names the axis AND the offending value", with a dated note recording the false premise and the empirical probe. (The original touch-up and its revert both live in this feature's git history; the spec's final text carries the revert.)

## D7 — File inventory

| file | change |
|---|---|
| `plugins/pd/hooks/lib/entity_registry/axes.py` | NEW (dark) |
| `plugins/pd/hooks/lib/entity_registry/test_axes.py` | NEW |
| `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py` | dark-guard: +1 module, +3 needles, +3 teeth |
| `docs/features/122-two-axis-phase-status-schema/spec.md` | D6 touch-up (dated) |

No live code, no UI, no MCP; roadmap edits already landed at specify (903f3964). Suite baseline re-derived at implement (FR122-5).

## Testing strategy

1. D5 items 1-7 (exact pins, exhaustive teeth, leak-detection, compatibility, view pins, dark teeth, raw-INSERT proof).
2. Regression: full suite green with ZERO 119/120/126 test edits (structural isolation); 119's immutability tests unchanged (different trigger verbs, no interaction).
3. validate.sh 0 errors; doctor pin unchanged.
