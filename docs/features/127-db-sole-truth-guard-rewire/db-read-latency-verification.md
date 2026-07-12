# DB-Direct Read-Latency Verification (feature 127, PRD NFR-3)

Captured 2026-07-12 on branch `feature/127-db-sole-truth-guard-rewire`. This
artifact satisfies FR127-4 / SC3 (design D5): it (1) re-reproduces 126's
populated-state file-based baseline (`docs/features/126-lossless-meta-json-projection/populated-latency-baseline.md`)
at the same seeds, UNCHANGED harness, (2) measures the DB-direct SQLite
equivalents of that same read path against seeded v2 entity-registry
databases, and (3) renders the go/no-go verdict that is a named input to
132's session-start cutover.

**Headline: GO.** DB-direct own-process p95 (29 ms walk-equivalent / 29 ms
workspace-lookup @ N=22) beats both the spec-pinned thresholds (31 ms / 32
ms, 126's RECORDED figures) and this run's FRESH file-based reproduction (35
ms / 36 ms @ N=22) by comfortable margins. See "Verdicts" below for the
arithmetic and "132 handoff" for the caveats that travel with the GO.

## 1. Baseline reproduction (component 5a, harness UNCHANGED)

Command run (verbatim, from a clean tree):

```bash
bash plugins/pd/hooks/tests/bench-populated-read.sh --features 22
```

This single invocation emits both scales the 126 baseline recorded (N=22 and
N=220 = 10×). Seed 0x126 and N_ITERATIONS=120 are internal to the script, per
126's own reproduction contract ("127 MUST re-run this harness with
`--features 22` ... never re-derive N").

### Full output (verbatim)

```
bench-populated-read.sh: seed=0x126 features_n=22 iterations=120 smoke=0
=== walk (find_active_feature) @ N=22 (n=120 iterations) ===
p50: 31 ms
p95: 35 ms
distribution (sorted ms): 29 30 30 30 30 30 30 30 30 30 30 30 30 30 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 33 33 33 33 33 33 33 33 33 33 33 33 34 34 34 34 34 34 34 35 35 35 35 36 36 39
=== glob (build_context workspace lookup, NO-MATCH) @ N=22 (n=120 iterations) ===
p50: 33 ms
p95: 36 ms
distribution (sorted ms): 30 30 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 34 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 36 36 36 37 37 37 38 40
=== walk (find_active_feature) @ N=220 (n=120 iterations) ===
p50: 44 ms
p95: 48 ms
distribution (sorted ms): 41 41 41 41 41 41 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 43 44 44 44 44 44 44 44 44 44 44 44 44 44 44 44 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 45 46 46 46 46 46 46 46 46 46 46 46 47 47 47 47 47 48 48 49 50 51 52 54 56
=== glob (build_context workspace lookup, NO-MATCH) @ N=220 (n=120 iterations) ===
p50: 39 ms
p95: 41 ms
distribution (sorted ms): 37 37 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 38 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 41 41 41 41 41 41 41 41 41 41 42 42 43 43 46
PASS: bench-populated-read.sh completed
```

### Drift vs 126's RECORDED figures

| component | scale | 126 RECORDED p50/p95 | this run's FRESH p50/p95 | drift (p50 / p95) |
|---|---|---|---|---|
| walk | N=22 | 29 / 31 ms | 31 / 35 ms | +2 / +4 ms |
| glob (no-match) | N=22 | 29 / 32 ms | 33 / 36 ms | +4 / +4 ms |
| walk | N=220 | 40 / 42 ms | 44 / 48 ms | +4 / +6 ms |
| glob (no-match) | N=220 | 36 / 38 ms | 39 / 41 ms | +3 / +3 ms |

**Drift observed.** Every figure is 2-6 ms higher than 126's recorded run.
`uptime` at capture time showed `load averages: 4.04 3.96 3.99` on a 28-core
machine — not heavily loaded in steady state, but this repo currently has
multiple parallel feature-127 task agents running concurrent test suites in
sibling worktrees (confirmed via `git status` showing task-3's in-flight
edits at capture time), which plausibly explains bursty scheduler contention
inflating python-spawn latency during this specific measurement window. Per
spec FR127-4's boundary case ("the verdict compares against the FRESH
reproduction, not the stale recorded number"), **the verdicts below are
computed against BOTH** the spec-pinned thresholds (31 ms / 32 ms, which
equal 126's recorded figures) **and** this run's fresh reproduction — DB-direct
beats both, so the drift does not change the outcome.

## 2. DB-direct read latency (feature 127, new harness)

Two postures, per design D5 / OQ-2 (honoring backlog #067's per-entity
`entity_axis_state` guidance):

- **walk-equivalent** — "find active feature + its phase" (what 132's
  session-start would run), two statements per sample against the dark
  `entity_axis_state` view:
  1. `SELECT e.uuid FROM entities e JOIN entity_axis_state s ON s.entity_uuid = e.uuid AND s.axis = 'execution' WHERE e.workspace_uuid = ? AND e.type = 'feature' AND s.to_value = 'active'`
     — bound to a real seeded workspace uuid. **Guaranteed no-match by
     construction:** `scripts/seed-census-db.py` emits only `lifecycle` and
     `pipeline` axis events, never `execution` — so this statement returns
     zero rows regardless of which workspace is queried, and query 2 always
     falls through to the fixed-probe-uuid case below.
  2. `SELECT to_value FROM entity_axis_state WHERE entity_uuid = ? AND axis = 'pipeline'`
     — bound to a fixed real seeded entity uuid (statement 1 never returns a
     uuid to chain from).
- **workspace-lookup** (glob-equivalent): `SELECT uuid FROM workspaces WHERE project_root = ?` bound to the literal `/nonexistent/no-match` — guaranteed no-match against the seeded `/synthetic/census-workspace-NN` roots, mirroring the baseline's glob NO-MATCH posture.

**View materialization:** `scripts/seed-census-db.py` imports only
`events`+`schema_v2`, so the seeded `v2.db` has no views. Per census, a
ONE-TIME setup step (not part of any timed sample) imports
`entity_registry.views` (**not** `entity_registry.axes`) and calls
`bootstrap_v2(db_path)`, which issues `CREATE VIEW IF NOT EXISTS` for
`entity_axis_state` — this persists in `sqlite_master`, so every timed
sample below is a plain `sqlite3.connect()` with no `entity_registry` import
and no per-sample DDL.

**Process basis:** each **own-process** sample is one spawn of
`plugins/pd/.venv/bin/python -c "<connect, query, close>"`, timed from bash
via the same `perl Time::HiRes` `_now_ns` technique bench-populated-read.sh
uses — so python startup (~27-28 ms on this machine) is included in every
sample, exactly mirroring the baseline's per-sample spawn shape (spec
FR127-4's apples-to-apples requirement). A second, **in-process amortized**
measurement (one process, one connection, 120 queries in a loop, timed
internally with `time.perf_counter_ns()` in microseconds) is reported
**FYI-only** — it informs 132's long-lived-server case but carries no
verdict.

Census substrate seeded via the UNTOUCHED `scripts/seed-census-db.py`,
`--workspaces 7 --seed 294` (== `0x126`; argparse's `type=int` cannot parse
a `"0x"`-prefixed string directly, so the CLI value is the bash-arithmetic
decimal expansion of the identical literal, not a re-derived number) at
three `--entities` scales: 22 (like-for-like vs the file baseline, BINDING),
220 (trend), and 533 (the seeder's own default — realistic-population FYI,
mirroring 126's component 5b). The N=533 run's counts — **533 entities,
5,644 events, 7 workspaces** — reproduce 126's component-5b figures
digit-for-digit, confirming the seeder's determinism at this seed.

Command run (verbatim):

```bash
bash plugins/pd/hooks/tests/bench-db-direct-read.sh
```

### Full output (verbatim)

```
bench-db-direct-read.sh: seed=0x126 workspaces=7 scales=22 220 533 iterations=120 smoke=0
seed: seeded 22 entities, 238 events, 7 workspaces -> /var/folders/61/sch8t_rj6hvfjdwcfr4sl_lw0000gn/T/tmp.YCEZwWDhD5/v2.db
=== EXPLAIN QUERY PLAN: walk-equivalent statement 1 @ N=22 ===
(2, 0, 0, 'CO-ROUTINE entity_axis_state')
(9, 2, 216, 'SCAN events USING INDEX idx_events_entity_axis')
(51, 0, 61, 'SEARCH e USING INDEX idx_entities_workspace (workspace_uuid=?)')
(78, 0, 47, 'SEARCH s USING AUTOMATIC PARTIAL COVERING INDEX (to_value=? AND entity_uuid=? AND axis=?)')
=== EXPLAIN QUERY PLAN: walk-equivalent statement 2 @ N=22 ===
(2, 0, 0, 'CO-ROUTINE entity_axis_state')
(9, 2, 61, 'SEARCH events USING INDEX idx_events_entity_axis (entity_uuid=? AND axis=?)')
(51, 0, 82, 'SCAN entity_axis_state')
=== walk-equivalent (DB-direct, NO-MATCH by construction) @ N=22 (n=120 iterations) ===
p50: 28 ms
p95: 29 ms
distribution (sorted ms): 26 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 30 30 30 31 31 31
=== workspace-lookup (DB-direct, NO-MATCH) @ N=22 (n=120 iterations) ===
p50: 28 ms
p95: 29 ms
distribution (sorted ms): 26 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 29 29 29 29 29 29 29 29 29 29 29 29 29 29 30 30 33 33 35
=== walk-equivalent (DB-direct, NO-MATCH by construction) @ N=22 (n=120 iterations, in-process amortized, FYI-only) ===
p50: 14 us
p95: 20 us
distribution (sorted us): 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 15 15 16 16 16 16 16 16 16 17 17 17 18 18 19 19 19 20 20 21 21 21 145 1017
=== workspace-lookup (DB-direct, NO-MATCH) @ N=22 (n=120 iterations, in-process amortized, FYI-only) ===
p50: 1 us
p95: 2 us
distribution (sorted us): 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 2 2 2 2 2 3 3 352
seed: seeded 220 entities, 2377 events, 7 workspaces -> /var/folders/61/sch8t_rj6hvfjdwcfr4sl_lw0000gn/T/tmp.AnSlyze7mx/v2.db
=== EXPLAIN QUERY PLAN: walk-equivalent statement 1 @ N=220 ===
(2, 0, 0, 'CO-ROUTINE entity_axis_state')
(9, 2, 216, 'SCAN events USING INDEX idx_events_entity_axis')
(51, 0, 61, 'SEARCH e USING INDEX idx_entities_workspace (workspace_uuid=?)')
(78, 0, 47, 'SEARCH s USING AUTOMATIC PARTIAL COVERING INDEX (to_value=? AND entity_uuid=? AND axis=?)')
=== EXPLAIN QUERY PLAN: walk-equivalent statement 2 @ N=220 ===
(2, 0, 0, 'CO-ROUTINE entity_axis_state')
(9, 2, 61, 'SEARCH events USING INDEX idx_events_entity_axis (entity_uuid=? AND axis=?)')
(51, 0, 82, 'SCAN entity_axis_state')
=== walk-equivalent (DB-direct, NO-MATCH by construction) @ N=220 (n=120 iterations) ===
p50: 28 ms
p95: 30 ms
distribution (sorted ms): 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 30 30 30 30 30 30 30 30 30 30 30 30 31 31 31 31 34
=== workspace-lookup (DB-direct, NO-MATCH) @ N=220 (n=120 iterations) ===
p50: 28 ms
p95: 30 ms
distribution (sorted ms): 26 26 26 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 30 30 30 30 30 30 31 31 31 33
=== walk-equivalent (DB-direct, NO-MATCH by construction) @ N=220 (n=120 iterations, in-process amortized, FYI-only) ===
p50: 82 us
p95: 100 us
distribution (sorted us): 80 80 80 80 80 80 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 81 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 82 83 83 83 83 83 83 83 83 83 83 83 83 83 83 84 84 84 85 85 85 86 87 87 87 87 90 91 91 92 92 93 93 93 94 94 99 100 100 100 101 148 222 562
=== workspace-lookup (DB-direct, NO-MATCH) @ N=220 (n=120 iterations, in-process amortized, FYI-only) ===
p50: 1 us
p95: 2 us
distribution (sorted us): 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 2 2 2 2 2 3 18 341
seed: seeded 533 entities, 5644 events, 7 workspaces -> /var/folders/61/sch8t_rj6hvfjdwcfr4sl_lw0000gn/T/tmp.oZKHqH1bDO/v2.db
=== EXPLAIN QUERY PLAN: walk-equivalent statement 1 @ N=533 ===
(2, 0, 0, 'CO-ROUTINE entity_axis_state')
(9, 2, 216, 'SCAN events USING INDEX idx_events_entity_axis')
(51, 0, 61, 'SEARCH e USING INDEX idx_entities_workspace (workspace_uuid=?)')
(78, 0, 47, 'SEARCH s USING AUTOMATIC PARTIAL COVERING INDEX (to_value=? AND entity_uuid=? AND axis=?)')
=== EXPLAIN QUERY PLAN: walk-equivalent statement 2 @ N=533 ===
(2, 0, 0, 'CO-ROUTINE entity_axis_state')
(9, 2, 61, 'SEARCH events USING INDEX idx_events_entity_axis (entity_uuid=? AND axis=?)')
(51, 0, 82, 'SCAN entity_axis_state')
=== walk-equivalent (DB-direct, NO-MATCH by construction) @ N=533 (n=120 iterations) ===
p50: 29 ms
p95: 32 ms
distribution (sorted ms): 27 27 27 27 27 27 27 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 31 32 32 32 32 32 32 33 33 33 33 34 35
=== workspace-lookup (DB-direct, NO-MATCH) @ N=533 (n=120 iterations) ===
p50: 28 ms
p95: 31 ms
distribution (sorted ms): 26 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 27 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 30 30 30 30 30 31 31 31 31 31 33 34
=== walk-equivalent (DB-direct, NO-MATCH by construction) @ N=533 (n=120 iterations, in-process amortized, FYI-only) ===
p50: 183 us
p95: 214 us
distribution (sorted us): 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 182 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 183 184 184 184 184 184 184 184 184 186 187 187 187 187 187 187 188 188 188 188 188 188 188 188 188 188 190 190 190 191 191 197 198 199 201 203 204 205 205 205 207 207 208 213 213 214 214 216 227 228 228 337 755
=== workspace-lookup (DB-direct, NO-MATCH) @ N=533 (n=120 iterations, in-process amortized, FYI-only) ===
p50: 1 us
p95: 2 us
distribution (sorted us): 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 2 2 2 2 2 2 3 3 332
PASS: bench-db-direct-read.sh completed
```

### Results summary

| component | scale | own-process p50 / p95 | in-process amortized p50 / p95 (FYI) |
|---|---|---|---|
| walk-equivalent | N=22 | 28 / 29 ms | 14 / 20 us |
| walk-equivalent | N=220 | 28 / 30 ms | 82 / 100 us |
| walk-equivalent | N=533 | 29 / 32 ms | 183 / 214 us |
| workspace-lookup | N=22 | 28 / 29 ms | 1 / 2 us |
| workspace-lookup | N=220 | 28 / 30 ms | 1 / 2 us |
| workspace-lookup | N=533 | 28 / 31 ms | 1 / 2 us |

### EXPLAIN QUERY PLAN

Identical plan shape captured at all three census scales (22, 220, 533) —
SQLite's cost-estimate column (the third element of each row) is the same
default-heuristic number regardless of actual table size, because these
databases have never had `ANALYZE` run against them; the *shape* of the plan
(scan vs. search, which index) is what's informative here, not the estimate
magnitudes:

```
=== EXPLAIN QUERY PLAN: walk-equivalent statement 1 ===
(2, 0, 0, 'CO-ROUTINE entity_axis_state')
(9, 2, 216, 'SCAN events USING INDEX idx_events_entity_axis')
(51, 0, 61, 'SEARCH e USING INDEX idx_entities_workspace (workspace_uuid=?)')
(78, 0, 47, 'SEARCH s USING AUTOMATIC PARTIAL COVERING INDEX (to_value=? AND entity_uuid=? AND axis=?)')
=== EXPLAIN QUERY PLAN: walk-equivalent statement 2 ===
(2, 0, 0, 'CO-ROUTINE entity_axis_state')
(9, 2, 61, 'SEARCH events USING INDEX idx_events_entity_axis (entity_uuid=? AND axis=?)')
(51, 0, 82, 'SCAN entity_axis_state')
```

**Reading (feeds backlog #067's 132 mandate):** both statements materialize
`entity_axis_state` as a CO-ROUTINE (the view is not flattened into the
outer query). Statement 1's `s.axis = 'execution'` predicate lives at the
OUTER join level, so it cannot be pushed into the view's own scan — the
co-routine does a full **`SCAN events`** (O(total events in the census),
using the index only to iterate in `(entity_uuid, axis)` order for the
GROUP BY). Statement 2's `WHERE entity_uuid = ? AND axis = 'pipeline'`
predicate DOES get pushed into the view's underlying query, producing an
efficient **`SEARCH events ... (entity_uuid=? AND axis=?)`**. This asymmetry
is exactly why the in-process amortized FYI figures for the walk-equivalent
grow with N (14 us → 82 us → 183 us, roughly 0.33 us per additional entity,
tracking the ~10.8 events-per-entity ratio the seeder produces) while
workspace-lookup's amortized figures stay flat at 1-2 us regardless of
scale (an indexed `workspaces.project_root` search, no GROUP BY involved).
**A per-entity `entity_axis_state` read (statement 2's shape) is the cheap,
scale-invariant primitive; a join-then-filter-by-axis-value read (statement
1's shape) is not** — the same conclusion 120's own QA probe reached for
`entity_state`, now confirmed at census scale for `entity_axis_state` too.

### Pure no-match GROUP-BY scan cost (label — design D5)

The walk-equivalent's statement 1 is a **LATENCY analogue, not a
correctness-faithful "find the active feature" resolver.** Its p50/p95
figures above measure the cost of a full `events` table scan that is
GUARANTEED to return zero rows (the seed emits no `execution`-axis events by
construction) — they are the worst-case no-match scan cost, structurally
identical in spirit to 126's glob-NO-MATCH component, and must not be read
as "how long it takes to find a real active feature."

**MAX(uuid) semantics caveat (travels to 132):** `entity_axis_state.to_value`
is selected as a bare column alongside a `MAX(uuid)` aggregate
(`entity_registry/views.py:79`). `events.uuid` is a uuid7 (time-ordered by
construction) and the aggregate is well-defined (no ties, exactly one
max-aggregate in the SELECT — see `views.py`'s own bare-columns-with-MAX
contract), but "the row with the lexicographically largest uuid" is a proxy
for "the most recently INSERTED row," not necessarily "the row with the
greatest domain `timestamp`" — those two can diverge (e.g., a future backfill
or event-replay process inserting historical events with old `timestamp`
values but freshly-minted uuids). **132 must pin correct latest-event
semantics before cutover** — this measurement harness exercises the view as
it exists today and takes no position on whether MAX(uuid) is the right
"latest" selector for the live cutover.

## 3. Verdicts

Both binding verdicts are computed at **N=22** (the census scale
like-for-like with 126's recorded file baseline), against **two**
thresholds: the spec-pinned numbers (FR127-4: 31 ms / 32 ms, which equal
126's RECORDED figures) and this run's FRESH file-based reproduction (which
drifted upward — see §1). DB-direct beats both.

### (i) PRIMARY go/no-go — walk-equivalent, BINDING @ N=22

- DB-direct walk-equivalent p95 @ N=22 = **29 ms**
- vs. spec-pinned threshold (126 RECORDED walk p95 @ N=22) = 31 ms → **29 ≤ 31 → PASS**, margin **2 ms**
- vs. this run's FRESH reproduction (walk p95 @ N=22) = 35 ms → **29 ≤ 35 → PASS**, margin **6 ms**

**Verdict: PASS** under both thresholds.

### (ii) workspace-lookup @ N=22

- DB-direct workspace-lookup p95 @ N=22 = **29 ms**
- vs. spec-pinned threshold (126 RECORDED glob p95 @ N=22) = 32 ms → **29 ≤ 32 → PASS**, margin **3 ms**
- vs. this run's FRESH reproduction (glob p95 @ N=22) = 36 ms → **29 ≤ 36 → PASS**, margin **7 ms**

**Verdict: PASS** under both thresholds.

### (iii) census-substrate — FYI-only, no pass/fail

- **N=220 (trend evidence, not binding):** DB-direct walk-equivalent p95 =
  30 ms, workspace-lookup p95 = 30 ms — both still comfortably below the
  N=220 file baseline's fresh figures (walk p95 = 48 ms, glob p95 = 41 ms).
  Notably, the file-based walk p95 grew +13 ms for a 10x entity increase
  (35 ms fresh @ N=22 → 48 ms fresh @ N=220 — the O(N) `.meta.json` parse
  cost), while DB-direct's own-process walk-equivalent p95 moved only +3 ms
  across a 24x entity range (29 ms @ N=22 → 30 ms @ N=220 → 32 ms @ N=533),
  because the ~27-28 ms python-spawn floor dominates and the actual
  query-side marginal cost (visible only in the in-process FYI figures:
  14 us → 82 us → 183 us) is microseconds, not milliseconds — the
  DB-direct advantage does not shrink at higher entity counts; it grows.
- **N=533 (realistic-population FYI, mirrors 126 component 5b):**
  DB-direct walk-equivalent p95 = 32 ms, workspace-lookup p95 = 31 ms.
  **No verdict is defined at this scale.** 126's own component-5b figure for
  this same census (533 entities / 5,644 events / 7 workspaces, 0.113 s
  wall-clock) is a **seeding/write cost**, not a read-latency p95 — it is
  not comparable to, and carries no threshold against, this artifact's read
  figures. This run's own seeding of the identical 533/7 census reproduced
  126's entity/event/workspace counts exactly, confirming the seed is
  still deterministic at 0x126.

## 4. Own-process measurement basis (spec FR127-4)

Every **binding** figure above (§3 (i) and (ii)) is an **own-process**
measurement: each of the 120 samples per query per census is a fresh spawn
of `plugins/pd/.venv/bin/python -c "<connect, query, close>"`, timed from
bash with the identical `perl Time::HiRes`-based `_now_ns` technique
`bench-populated-read.sh` uses for the file-side baseline — so python
interpreter startup (~27-28 ms measured floor on this machine) is included
in every DB-direct sample exactly as it is in every file-side sample. This
is the apples-to-apples basis FR127-4 requires (populated-latency-baseline.md
notes the baseline's own p95 is ~90% python-spawn cost — a basis mismatch
would make any verdict vacuous). The **in-process amortized** figures (one
process, one open connection, 120 queries in a loop, §2's "Results summary"
right column) are reported **FYI-only**: they isolate the pure query cost
for 132's long-lived-server case (e.g., an MCP server holding a persistent
connection) but are explicitly excluded from the verdicts because they are
not on the same basis as the baseline being compared against.

## 5. Machine context

- macOS 26.5.1 (build 25F80); `uname -m`: arm64; CPU: Apple M3 Ultra — same
  machine as 126's baseline capture.
- Python 3.14.6 (`plugins/pd/.venv/bin/python`); bundled `sqlite3` module
  version 3.53.2 (the version the timed queries actually ran against — the
  system `sqlite3` CLI reports 3.51.0, a different build not used by this
  harness).
- `uptime` at capture time: `load averages: 4.04 3.96 3.99` (28 logical
  CPUs); multiple sibling feature-127 task-agent worktrees were running
  concurrent test suites during capture (see §1's drift discussion).

## 6. Reproduction commands

```bash
# from the project root, clean-enough tree (DB-direct harness mutates
# nothing outside mktemp -d; file baseline harness mutates nothing outside
# mktemp -d either)
bash plugins/pd/hooks/tests/bench-populated-read.sh --features 22   # 126's recorded N — do not re-derive
bash plugins/pd/hooks/tests/bench-db-direct-read.sh                 # this feature's harness — fixed 22/220/533 scales, workspaces=7, seed=0x126
```

Residual: DB-direct own-process figures will vary run-to-run with machine
load exactly as the file baseline does (§1's drift is evidence of this,
not a harness defect); `scripts/seed-census-db.py`'s structural output
(entity/event/workspace counts, status/phase distribution) is fully
deterministic at a fixed seed, but the actual uuid7 values differ every run
(uuid7 draws real wall-clock time + OS randomness, not the seeded RNG) — the
probe workspace/entity uuids bound into the timed queries are therefore
always freshly captured from the just-seeded census, never hardcoded.

## 7. 132 handoff — go/no-go statement

**GO.** Both binding verdicts ((i) walk-equivalent, (ii) workspace-lookup,
§3) PASS at N=22 against the spec-pinned thresholds AND against this run's
fresh file-baseline reproduction, with margins of several milliseconds in
every case; N=220 trend evidence shows the margin widening, not narrowing,
as entity count grows. The DB-direct read path measured here is not slower
than the file-based path it would replace, at any scale tested.

Two caveats travel with this GO, both already flagged above and neither of
which changes the verdict:

1. **MAX(uuid) is a proxy for "latest inserted," not "latest by domain
   timestamp"** (§2, "Pure no-match GROUP-BY scan cost" label) — 132 must
   pin the correct latest-event semantics for `entity_axis_state` (or a
   successor view) before wiring session-start to it, particularly if a
   future backfill/replay path can insert events out of temporal order.
2. **Statement 1's shape (join-then-filter-by-axis-value) forces a full
   `events` table scan; statement 2's shape (direct per-entity
   `entity_axis_state` read) is index-efficient** (§2, EXPLAIN QUERY PLAN
   reading). 132's actual "find the active feature" resolver should be
   designed around the cheap per-entity primitive wherever possible, not
   the join-based shape this harness measured as the worst-case latency
   analogue.

This artifact does not change any live code path (FR127-4 is
measurement-only); 132 owns the actual session-start cutover.
