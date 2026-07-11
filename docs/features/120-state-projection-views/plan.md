# Implementation Plan: State Projection Views (feature 120)

## Objective

Land design D1-D7 in four serial steps: the dark views module with its deterministic pins and guard extension; the replay property test; the #061 guard; the latency-baseline artifact folded into integration QA.

## Prerequisites

Branch `feature/120-state-projection-views` (active). Design D1-D7 binding, including: the bare-column two-precondition CONTRACT (exactly-one-MAX + PK-no-ties); axis-generic pivoted column names (`pipeline_value`, not 122's future `pipeline_phase`); the load-bearing `events` import for registry order; PRAGMA-probe guard BEFORE the in_transaction branch; per-case-Random-only stochastic draws; `test_events.py:506` preserved byte-unchanged.

## Step Ordering Rationale

Step 1 ships the module + its deterministic fixtures + the ships-dark teeth as one vertical slice (a view without its pins is unreviewable; the teeth must land with the module or the dark guard has a gap). Step 2 appends the property test to the same test file (needs step 1's module; separated because its generator mechanics deserve their own review context). Step 3 (#061 guard) is file-disjoint from 1-2 (events.py + test_events.py) but runs after so the property test's raw-INSERT half is written against the PRE-guard semantics it actually uses (raw INSERT is unguarded — order only matters for reviewer clarity). Step 4 runs the benchmark (requires a CLEAN COMMITTED tree — the script exits 2 on dirty; steps 1-3 must be committed first) and the full integration QA.

## Step 1 — views.py + deterministic pins + guard teeth (D1, D2, D5-SC1/SC2, D6)

**Do:**
1. NEW `plugins/pd/hooks/lib/entity_registry/views.py`: dark-module preamble (events.py's shape); module-top `import entity_registry.events` with the load-bearing comment (registry order — D2); `_VIEWS_DDL` exactly per D1 (both views, axis-generic names); `register_ddl("views", _VIEWS_DDL)`; the D1 CONTRACT text lives in the module docstring beside the DDL.
2. NEW `test_views.py`: `_reset_ddl_registry` reuse; bootstrapped-DB + connect_v2 fixtures (test_display.py idioms); the SIX D5 fixtures — three-axis latest; out-of-order timestamp; rowid-confound (pre-minted uuids, larger inserted FIRST, DISTINCT to_values, assert larger-uuid value); single-axis (pivoted others NULL; per-axis one row); zero-event (per-axis absent; pivoted all-NULL row); NULL-to_value latest-wins. SC2: parametrized INSERT/UPDATE/DELETE × both views → OperationalError (6 pins); `PRAGMA table_info(entities)` column-set pin.
3. `test_schema_v2.py`: `_V2_DARK_MODULES` += `"views.py"`; needles += 3 spellings; 3 seeded-offender teeth (121's exact pattern incl. relative form).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_views.py plugins/pd/hooks/lib/entity_registry/test_schema_v2.py -q` green; teeth red-then-green demonstrated (seeded offender flagged pre-needle).

## Step 2 — replay property test (D4, SC3)

**Do:** Append to `test_views.py`: `MASTER_SEED` constant; generator per D4 (1-8 entities × 0-12 events; ALL draws from the per-case `random.Random(case_seed)`; ~half shuffled-insert cases via pre-minted+shuffled uuids and raw INSERT on the connect_v2 conn, other half through `append_event`; NULL values in the alphabet); ONE bootstrapped DB for the run, per-case entity namespaces, NO cleanup (immutability forbids DELETE — isolation via `WHERE entity_uuid IN (...)`); pure-Python max-uuid fold; field-by-field equality per-axis AND pivoted; failure prints seed + sequence; N=200; duration assert < 5s around the loop (non-regression guard; assert message includes the measured elapsed so a trip reads as "tune N", not a mystery flake).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_views.py -q` green; run twice — identical pass/fail outcome AND case structure (both derive from MASTER_SEED; raw uuid7 values legitimately differ run-to-run — wall-clock-encoded, expected); duration comfortably under the guard.

## Step 3 — #061 guard (D3, SC4)

**Do:**
1. `events.py`: PRAGMA probe as the FIRST statement of `append_event` (D3's exact code + message naming #061); one docstring line in the factory-requirement block naming the guard.
2. `test_events.py`: NEW tests — bare-conn standalone → ValueError + zero rows; bare-conn with open transaction (compose path) → same; `test_bare_connection_inserts_the_same_orphan_successfully` (:506) untouched. The existing suite is the connect_v2-unchanged regression net (every append_event call site is FK-ON — design's audit; the property is what holds, not any exact count).

**Verify:** guard tests demonstrated red before the probe lands, green after; `pytest plugins/pd/hooks/lib/entity_registry/test_events.py -q` green; `git diff` shows :506's test body untouched.

## Step 4 — latency baseline + integration QA (D7, SC5, SC6)

**Do:**
1. Commit steps 1-3; confirm clean tree; run `bash plugins/pd/hooks/tests/bench-session-start.sh` — NOTE: the script's own NFR2 gate (delta>50ms → exit 1) is NOT this feature's gate (medians are echoed BEFORE that check; capture stdout regardless of exit code — the committed artifact is the deliverable, D7's snapshot-not-gate posture), and the script OVERWRITES the tracked `plugins/pd/hooks/tests/bench-results.txt` ("do not re-commit" convention) — `git restore plugins/pd/hooks/tests/bench-results.txt` after capturing stdout so the tree ends clean; write `docs/features/120-state-projection-views/latency-baseline.md` per D7 (both medians + raw output verbatim + machine context + reproduction command + the scope statement mirroring spec item 5: empty-HOME overhead, median-only; NFR-3 populated p50/p95 capture = 126, verification = 127, roadmap.md:42).
2. Full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh`; `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor count unchanged; `git diff develop...HEAD --stat` vs the 7-row inventory BY NAME (views.py NEW, events.py, test_views.py NEW, test_events.py, test_schema_v2.py, latency-baseline.md NEW, backlog-manual.md #061-closure at finish) + feature docs.

**Verify:** all green; artifact contains every D7-required section; no unsanctioned files.

## Risks & Mitigations

- **Bench variance / dirty-tree exit:** step 4 runs at a committed point; artifact records raw output — snapshot, not gate.
- **Property-test time on slow disks:** one-DB design; if the 5s guard trips on CI-class hardware, the guard is the signal to tune N — not to delete the assert.
- **Bare-column idiom misread:** D1 CONTRACT in module docstring + rowid-confound fixture.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per step; steps independent (step 2 appends tests only; step 3 is file-disjoint; step 4 is docs+artifact). Dark module reverts clean (guard-enforced unimported).

## Success Check (spec SCs)

SC1/SC2 → step 1; SC3 → step 2; SC4 → step 3; SC5 → step 4; SC6 → steps 1 (teeth) + 4 (suites/validate/doctor).
