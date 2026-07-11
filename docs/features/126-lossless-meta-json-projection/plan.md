# Implementation Plan: Lossless .meta.json Projection (feature 126)

## Objective

Land design D1-D9 in four serial steps: the dark projection module with its golden fixtures, guards, canary, registry edit, and dark-guard teeth; the replay property test; the two-component NFR-3 harness; the baseline capture + integration QA.

## Prerequisites

Branch `feature/126-lossless-meta-json-projection` (active). Design D1-D9 binding, including: the D1 event grammar table (init REQUIRED; renamed excluded from status); D2 DENYLIST status fold (`_NON_STATUS_EVENT_TYPES`, forward rule as test-level comment); D3 derivation table (completed = finish-phase ts PRIMARY / terminal-lifecycle FALLBACK; falsy-backward→absent; skippedPhases shape-preserving passthrough — string AND array both live, NO normalization); D4 `PRAGMA query_only` canary + its own teeth; D5 fixture provenance table (real files: 120/130/131/122 + writer-test array expectation + 073 fixture shapes); D6 property discipline (MASTER_SEED=0x126, N_cases=200, per-case Random, diverging completed-ts cases); D7 three needles + teeth red-first; D8 two sentinel pairs + self-guarding bench + recorded-N constant.

## Step Ordering Rationale

Step 1 ships the module + every deterministic pin as one vertical slice (module without pins is unreviewable; teeth must land with the dark module). Step 2 appends the property test to the same test file (needs step 1's module; its generator mechanics deserve separate review context). Step 3 is file-disjoint from 1-2 (hook sentinels + bench + seeder + their smoke tests) but runs after so the projection the seeder smoke round-trips against is already committed (serialized for reviewer clarity; the raw scripts are independent). Step 4 runs the harness at recorded scale and full integration QA (steps 1-3 committed first — the artifact records the commit it measured).

## Step 1 — meta_projection.py + fixtures + guards + canary + registry + teeth (D1-D5, D7)

**Do:**
1. NEW `plugins/pd/hooks/lib/entity_registry/meta_projection.py`: dark preamble (views.py's shape); module-top `from entity_registry import events` (load-bearing: registry order AND `read_events` consumer — comment states both roles); `project_meta(conn, entity_uuid)` per D1-D3 EXACTLY (kind guard first after row fetch; D2 denylist fold with the forward-rule comment; D3 table incl. completed PRIMARY/FALLBACK, falsy-backward→absent, shape-preserving skippedPhases, phase_summaries accumulation); ZERO writes (SELECTs via `read_events` + one entities-row SELECT — no `entity_state` reads, #067).
2. `plugins/pd/hooks/lib/entity_registry/events.py`: registry docstring only — three new keys (`phaseSummaryEntry`, `backwardContext`, `backwardReturnTarget`, with the file-side snake_case mapping documented) + consumer attribution corrected to `entity_registry.meta_projection` (126, not 120).
3. NEW `plugins/pd/hooks/lib/entity_registry/test_meta_projection.py`: the SEVEN D5 golden fixtures with pinned provenance — (a) frozen copy of 120's real completed file — ALL real-file fixtures are INLINED as self-contained Python constants with provenance comments; NEVER open() the source paths at runtime (they are gitignored, absent on fresh clones/CI); (b) BOTH skippedPhases shapes (130's string + the writer-test array `[{"phase": ..., "reason": ...}]` from test_workflow_state_server.py:4380-4439); (c) 131's 2-entry phase_summaries (multi-entry fold non-vacuity); (d) backward_context value-shape from 073's fixture (test_workflow_state_server.py:4600); backward_return_target value from 073's documented payload shape (073's design.md:163, `"create-plan"`); backlog_source synthetic (no exemplar in any documented shape — acknowledged in-test); (e) 122's planned minimal-init skeleton (lastCompletedPhase null-PRESENT); (f) renamed (id/slug = new tail; status before==after; phases unperturbed); (g) in-flight + cross-axis `status_changed` interleave. TWO registry-pin tests (SC4/FR126-4): unknown-key-ignored (a payload carries an undocumented key alongside real ones — silently dropped, no error) and per-key WRONG-SPELLING (e.g. `reviewer_notes`, `backward_context` in a payload must NOT populate the output fields). ALL nine guard tests (kind, orphan, zero-init, malformed payload JSON via raw INSERT, duplicate-init latest-wins, terminal-no-finish fallback, same-timestamp tie, null-status-verbatim, re-entered-phase last-entry-wins). D4 canary: `PRAGMA query_only=ON` conn → `project_meta` succeeds; companion test proves the canary rejects a probe INSERT (canary demonstrated red).
4. `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py`: `_V2_DARK_MODULES` += `"meta_projection.py"`; needles += the three spellings; 3 seeded-offender teeth demonstrated RED first against the un-extended needle set.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_meta_projection.py plugins/pd/hooks/lib/entity_registry/test_schema_v2.py -q` green; teeth red-first evidence; canary red-first evidence (probe INSERT rejected).

## Step 2 — replay property test (D6, SC2)

**Do:** Append to `test_meta_projection.py`: `MASTER_SEED = 0x126`, `N_CASES = 200`; per-case `random.Random(case_seed)` for EVERY draw (phase sequences incl. re-entries/backwards/skips in both shapes, status changes on both axes, renames, payload presence/absence, falsy backward values, timestamp jitter incl. ties, diverging finish-completed vs terminal-lifecycle timestamps — the D3 primary/fallback non-vacuity requirement); global `random` untouched; ONE bootstrapped DB, per-case entity uuids, no cleanup; oracle = independent pure-Python fold built from the GENERATED SPECS (not by re-reading the DB); field-by-field assert; failure message carries seed + full sequence; <5s wall-clock with elapsed in the assert message.

**Verify:** `pytest .../test_meta_projection.py -q` green; run TWICE — identical pass/fail outcome and case structure (uuid7 values legitimately differ; do NOT seed uuid minting); elapsed printed in the assert message.

## Step 3 — NFR-3 harness (D8; sentinels + bench + seeder + smokes)

**Do:**
1. `plugins/pd/hooks/session-start.sh`: TWO sentinel pairs, comment-only — `# BENCH-WALK-START/END` bracketing the `latest_meta=$(python3 -c '…')` assignment (EXCLUDING line 74's `local`; the single-quoted python string is byte-untouched) and `# BENCH-GLOB-START/END` bracketing the projects-glob snippet (:409-427).
2. NEW `plugins/pd/hooks/tests/bench-populated-read.sh`: extracts both snippets between sentinels at run time (exits 3 with a named message if either extraction is empty or missing its load-bearing lines — walk: `os.walk`+`json.load`; glob: `glob.glob`+`json.load`); seeds a synthetic tree under `mktemp -d` (`random.Random(0x126)`; realistic .meta.json sizes; features tree + projects tree); glob eval's THREE-variable setup documented in-script: `PROJECT_ROOT` + `artifacts_root_val` pointed at the seeded tree, `feature_workspace_uuid` set to a non-matching sentinel so the :424 first-match break never fires (NO-MATCH full-scan posture); takes the feature-scale count as an EXPLICIT ARGUMENT (first-capture default: `find docs/features -name .meta.json | wc -l` — the PARSE-cost driver, ~22 on this repo vs ~137 dirs; the seeded tree carries one .meta.json per dir so seeded N = parsed N, recorded); measures each component as its own process, `N_ITERATIONS = 120` per scale (live-recorded + 10×); emits p50/p95 + full sorted distribution per component per scale.
3. NEW `scripts/seed-census-db.py`: deterministic census-scale v2 DB seeder (~533 entities / 7 workspaces; `random.Random(0x126)`; all-synthetic strings; scale parameterized). Write API: raw INSERTs on a connect_v2 conn (v2 has no registration API until 122/123; v2 entities has NO type_id uniqueness constraint by design — FR-4) with SEQUENTIAL deterministic type_ids (`feature:{i:04d}-{slug}`) so counts are exact and collision-free by construction; events via `append_event`.
4. NEW `plugins/pd/hooks/lib/entity_registry/test_census_seeder.py`: seeder smoke at REDUCED scale (20 entities / 2 workspaces — EXACT expected row counts asserted, not >0, so silent drops surface at reduced scale + ONE seeded feature entity round-trips through `project_meta`); sentinel-existence pytest (all four markers present in session-start.sh).

**Verify:** `pytest .../test_census_seeder.py -q` green; `bash plugins/pd/hooks/tests/bench-populated-read.sh --smoke` (caps BOTH iterations AND tree scale — a genuinely fast end-to-end gate) runs with its drift-guard passing; `bash plugins/pd/hooks/tests/test-hooks.sh` green. Neutrality proof for the sentinel edit rests on: comment-only diff (`git diff` shows only `#`-prefixed additions) + the sentinel-existence pytest; test-hooks.sh CORROBORATES (its session-start tests always exercise the walk; the glob path is conditional on workspace_uuid presence).

## Step 4 — baseline capture + integration QA (SC6, SC7)

**Do:**
1. Commit steps 1-3; capture the live feature-dir count as the RECORDED constant; run the bench at both scales (N_ITERATIONS=120); run `scripts/seed-census-db.py` at FULL scale into a scratch dir (runtime + row counts recorded, dir discarded); write `docs/features/126-lossless-meta-json-projection/populated-latency-baseline.md`: p50/p95 + full distribution per component per scale, the recorded feature count + seeds, machine context (`sw_vers`, `uname -m`, `sysctl -n machdep.cpu.brand_string`), reproduction commands (with the recorded N as an explicit argument), the 127 clause (MUST re-run BOTH components at these seeds and this recorded N), and the synthetic-proxy residual note.
2. Full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh` (0 errors); `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor count pin unchanged; `git diff develop...HEAD --stat` vs D9's inventory BY NAME (8 rows + feature docs; backlog untouched this feature — #061 already closed, #067 consumed as input only).

**Verify:** all green; artifact carries every FR126-6 element; no unsanctioned files.

## Risks & Mitigations

- **Two-shape skippedPhases regression:** fixture (b) pins BOTH shapes; the module has no normalization branch to get wrong (passthrough).
- **Sentinel extraction fragility:** self-guarding bench (exit 3) + sentinel-existence pytest; sentinels are comment-only.
- **Property-test time:** one-DB design; 5s guard is the tune-N signal, not a delete-the-assert signal.
- **Seeder scale runtime:** full census run happens ONCE at step 4 (not CI); smoke is reduced-scale.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per step; steps independent (2 appends tests; 3 is hook-comments + new files; 4 is artifact + docs). Dark module reverts clean (guard-enforced unimported); sentinel comments revert trivially.

## Success Check (spec SCs)

SC1/SC3/SC4 → step 1; SC2 → step 2; SC5 → step 1 (teeth); SC6 → steps 3-4; SC7 → step 4.
