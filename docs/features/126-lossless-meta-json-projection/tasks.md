# Tasks: Lossless .meta.json Projection (feature 126)

Execution: STRICTLY SERIAL 1→4 (task 2 appends to task 1's test file; task 3 serialized for reviewer clarity — its seeder smoke round-trips against task 1's committed module; task 4 measures committed state). `pytest` = `plugins/pd/.venv/bin/python -m pytest`.

## Task 1: meta_projection.py + fixtures + guards + canary + registry + teeth

**Why:** spec FR126-1/2/3/4/5 + SC1/SC3/SC4/SC5 / design D1, D2, D3, D4, D5, D7.

**Files:** `plugins/pd/hooks/lib/entity_registry/meta_projection.py` (NEW), `plugins/pd/hooks/lib/entity_registry/test_meta_projection.py` (NEW), `plugins/pd/hooks/lib/entity_registry/events.py` (docstring only), `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py`

**Do:**
1. `meta_projection.py`: dark preamble mirroring views.py (`plugins/pd/hooks/lib/entity_registry/views.py`); module-top `from entity_registry import events` with the dual-role comment (registry replay order + `read_events` consumer); `project_meta(conn, entity_uuid) -> dict` implementing design D1 grammar / D2 denylist fold (`_NON_STATUS_EVENT_TYPES = frozenset({"renamed", "phase_started", "phase_completed", "phase_backward"})` with the forward-rule comment: future non-status event types MUST be added here; 127 asserts its vocabulary against this set) / D3 derivation table EXACTLY (id/slug from type_id tail; created from created_at; completed PRIMARY finish-phase ts, FALLBACK terminal-lifecycle ts; falsy backwardContext/backwardReturnTarget → ABSENT; skippedPhases shape-preserving passthrough — string AND array, NO normalization; phaseSummaryEntry accumulation in uuid order, empty → ABSENT; absent-vs-null per spec FR126-1; phases dict key order = first-entry order, informational only — fixture/property assertions use dict-level `==`, never byte-wise/serialized comparison). Kind guard FIRST after row fetch (row absent → ValueError(uuid); kind != "feature" → ValueError(kind)). Reads: ONE `read_events` call + one entities-row SELECT; no views, no writes.
2. `events.py`: FR-11 registry docstring ONLY — add `phaseSummaryEntry`, `backwardContext`, `backwardReturnTarget` (camelCase payload side; snake_case file side documented per key) and correct the consumer attribution ("feature 120's projection" → `entity_registry.meta_projection`, feature 126).
3. `test_meta_projection.py`: reuse `_reset_ddl_registry` (test_schema_v2.py:90) + bootstrapped-DB/connect_v2 idioms (test_views.py). SEVEN golden fixtures per design D5 with provenance comments: (a) frozen copy of `docs/features/120-state-projection-views/.meta.json` (completed, 5 phases, doubly-encoded reviewerNotes byte-identical); (b) skippedPhases BOTH shapes — string `"[\"brainstorm\"]"` (130's file) AND array `[{"phase": "brainstorm", "reason": "already done"}]` (writer-test expectation, test_workflow_state_server.py:4380-4439); (c) 131's real 2-entry phase_summaries (multi-entry accumulation); (d) backward_context value-shape from 073's fixture (test_workflow_state_server.py:4600, `{"source_phase": "design"}`); backward_return_target value from 073's documented payload shape (docs/features/073-yolo-relevance-gate/design.md:163, `"backward_return_target": "create-plan"`); synthetic backlog_source (no exemplar in any documented shape — acknowledged in-test); (e) 122's planned minimal-init skeleton (status planned-vocab verbatim, mode, branch, `phases {}`, lastCompletedPhase null-PRESENT); (f) renamed — id/slug reproduce the NEW type_id tail, status before==after (denylist pin), phases unperturbed; (g) in-flight (2 completed + 1 started-only) WITH a mid-feature execution-axis `status_changed` interleaved between lifecycle events (cross-axis fold pin). Fixtures (a)/(b)/(c)/(e) INLINE the real files' byte content as self-contained Python constants (provenance path in a comment) and NEVER open() the source paths at runtime — they are gitignored (.gitignore:68), absent on fresh clones. TWO registry-pin tests (FR126-4/SC4): (i) unknown-key-ignored — an event payload carries an undocumented key (e.g. `{"bogus_key": "x"}`) alongside real ones; `project_meta` silently drops it (no error, absent from output); (ii) per-key WRONG-SPELLING — a payload using wrong casing for a registry key (e.g. `reviewer_notes`, `backward_context` on the payload side) must NOT populate the corresponding output field. NINE guard tests: kind (project uuid), orphan uuid, zero-init, malformed payload JSON (raw INSERT on the connect_v2 conn — bypasses append_event), duplicate-init latest-wins, terminal-no-finish (completed = terminal lifecycle ts), same-timestamp tie (uuid7 order), null-status-verbatim, re-entered-phase last-entry-wins (started overwritten). D4 canary pair: `PRAGMA query_only=ON` conn → `project_meta` succeeds; the same conn REJECTS a probe INSERT (`sqlite3.OperationalError`) — the canary's own teeth.
4. `test_schema_v2.py`: `_V2_DARK_MODULES` += `"meta_projection.py"`; `_V2_LIVE_REFERENCE_NEEDLES` += `entity_registry.meta_projection` / `from entity_registry import meta_projection` / `from .meta_projection import`; 3 seeded-offender teeth (one per spelling) — write RED first against the un-extended needle set.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_meta_projection.py plugins/pd/hooks/lib/entity_registry/test_schema_v2.py -q` green; teeth demonstrated red pre-needles (exact failing output); canary probe-INSERT rejection demonstrated.

## Task 2: replay property test

**Why:** spec SC2 / design D6.

**Files:** `plugins/pd/hooks/lib/entity_registry/test_meta_projection.py`

**Do:** Append per design D6 EXACTLY: `MASTER_SEED = 0x126`, `N_CASES = 200` module constants; master `random.Random(MASTER_SEED)` mints per-case seeds; each case's OWN `random.Random(case_seed)` for EVERY draw — phase sequences (incl. re-entries, backwards, skips carried in BOTH shapes), status changes on both axes, renames, payload presence/absence, falsy backward values, timestamp jitter incl. exact ties, and cases where the finish-completed ts DIFFERS from a terminal-lifecycle ts (D3 primary/fallback non-vacuity); global `random` never touched; ONE bootstrapped DB for all cases, per-case fresh entity uuids, no event cleanup (immutability triggers); oracle = pure-Python fold over the GENERATED SPECS (never re-reads the DB); field-by-field assert against `project_meta`; failure message carries case seed + full event sequence; wall-clock assert < 5s around the loop, measured elapsed in the assert message. Do NOT seed or monkeypatch generate_uuid7.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_meta_projection.py -q` green; run TWICE — identical pass/fail outcome and case STRUCTURE (uuid7 values legitimately differ run-to-run); elapsed in the assert message; duration well under 5s.

## Task 3: NFR-3 harness — sentinels + bench + seeder + smokes

**Why:** spec Scope 5a/5b + FR126-6 + SC6 (partial: committed/re-runnable scripts + reduced-scale smoke; the artifact itself is task 4's) / design D8.

**Files:** `plugins/pd/hooks/session-start.sh` (comment-only), `plugins/pd/hooks/tests/bench-populated-read.sh` (NEW), `scripts/seed-census-db.py` (NEW), `plugins/pd/hooks/lib/entity_registry/test_census_seeder.py` (NEW)

**Do:**
1. `session-start.sh`: `# BENCH-WALK-START` / `# BENCH-WALK-END` bracketing the `latest_meta=$(python3 -c '…')` assignment (lines ~75-102; EXCLUDE the `local latest_meta` declaration — top-level eval of `local` errors; the single-quoted python source stays byte-untouched) and `# BENCH-GLOB-START` / `# BENCH-GLOB-END` bracketing the projects-glob snippet (~:409-427). Comments only — `git diff` must show only `#`-prefixed additions in this file.
2. `bench-populated-read.sh`: sentinel extraction for BOTH components at run time; SELF-GUARDING — exit 3 with a named message if either extraction is empty or missing load-bearing lines (walk: `os.walk` + `json.load`; glob: `glob.glob` + `json.load`); seeded tree under `mktemp -d` (`random.Random(0x126)`: features tree with realistic .meta.json payloads + projects tree; glob measured NO-MATCH full-scan); feature-scale count as EXPLICIT argument (`--features N`; first-capture default `find docs/features -name .meta.json | wc -l` — the parse-cost driver, ~22 on this repo vs ~137 dirs; seeded tree = one .meta.json per dir so seeded N = parsed N); glob eval sets THREE vars (`PROJECT_ROOT`/`artifacts_root_val` → seeded tree; `feature_workspace_uuid` → non-matching sentinel, NO-MATCH full-scan); `--smoke` flag caps BOTH iterations AND tree scale; measures each component as its own process; `N_ITERATIONS = 120` per scale (live-recorded + 10×); emits p50/p95 + full sorted distribution per component per scale.
3. `seed-census-db.py`: bootstraps schema_v2 + events + registered DDL into a target dir; seeds ~533 entities across 7 workspaces (`--entities/--workspaces` parameterized; `random.Random(0x126)`; kinds/phases/payload sizes at census proportions; ALL synthetic strings — no live data). Write API: raw INSERTs on a connect_v2 conn (v2 has no registration API until 122/123; v2 entities deliberately has NO type_id uniqueness — FR-4) with SEQUENTIAL type_ids (`feature:{i:04d}-{slug}`) — exact counts, collision-free by construction; events through `append_event`.
4. `test_census_seeder.py`: (i) seeder smoke at 20 entities / 2 workspaces — asserts EXACT expected row counts (entities AND events; not >0 — silent drops must surface at reduced scale) AND one seeded feature entity round-trips through `project_meta`; (ii) sentinel-existence test — all FOUR markers present in session-start.sh.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_census_seeder.py -q` green; `bash plugins/pd/hooks/tests/bench-populated-read.sh --smoke` end-to-end with drift-guard passing; `bash plugins/pd/hooks/tests/test-hooks.sh` green (comment-only edit proven behavior-neutral).

## Task 4: baseline capture + integration QA

**Why:** spec SC6 + SC7 / design D8 artifact + Testing strategy #8.

**Files:** `docs/features/126-lossless-meta-json-projection/populated-latency-baseline.md` (NEW)

**Do:**
1. Confirm tasks 1-3 COMMITTED and tree clean; capture the live feature-dir count (RECORDED constant); run the bench at both scales (full N_ITERATIONS=120); run `seed-census-db.py` at FULL scale into a scratch dir (record runtime + row counts, discard dir); write `populated-latency-baseline.md`: p50/p95 + full sorted distribution per component per scale, recorded feature count + seeds (0x126 all three consumers, independent instances), machine context (`sw_vers`, `uname -m`, `sysctl -n machdep.cpu.brand_string`), reproduction commands with the recorded N explicit, the 127 clause (re-run BOTH components at these seeds + this N; compare DB-direct reads to 5a), and the synthetic-proxy residual note (payload sizes vary in the wild).
2. Full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh` (0 errors); `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor pin unchanged (suite); `git diff develop...HEAD --stat` vs design D9's 8-row inventory BY NAME + feature docs; nothing unsanctioned.

**Verify:** all green; artifact carries every FR126-6 element; no unsanctioned files.

## Summary

| Task | Depends on | Collides with |
|------|-----------|---------------|
| 1 | — | — |
| 2 | 1 (same test file) | — |
| 3 | 1 committed (seeder smoke round-trips project_meta; otherwise file-disjoint — serialized for reviewer clarity) | — |
| 4 | 1-3 committed | — |

Order: 1 → 2 → 3 → 4. Concurrency: NONE.
