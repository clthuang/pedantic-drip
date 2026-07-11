# Design: Lossless .meta.json Projection (feature 126)

Implements every spec FR; every design-decision point the spec deferred is pinned here (D1-D9). All file:line cites verified at authoring time.

## D1 — Event grammar CONTRACT (the registry's validating grammar)

Feature-kind entities. Event rows are `append_event(conn, entity_uuid, event_type, axis, from_value, to_value, actor, timestamp, payload)` (119's single writer; #061 guard applies). The grammar:

| event_type | axis | to_value | payload keys (registry) | projects into |
|---|---|---|---|---|
| `initialized` | `lifecycle` | initial status VERBATIM (writer's business, e.g. `planned`/`active`) | `mode`, `branch`, optional `brainstorm_source`, `backlog_source` | `status`, `mode`, `branch`, sources |
| `status_changed` | `execution` | new status VERBATIM | — | `status` |
| `completed` \| `abandoned` \| `archived` \| `activated` | `lifecycle` | terminal/lifecycle status VERBATIM | — | `status`; FALLBACK-only source for top-level `completed` (see D3) |
| `phase_started` | `pipeline` | phase name | optional `skippedPhases` (VERBATIM stored shape — string OR native array, both live; see D3) | `phases[p].started` (event ts), `skippedPhases` |
| `phase_completed` | `pipeline` | phase name | `iterations`, `reviewerNotes`, optional `phaseSummaryEntry` (ONE dict) | `phases[p].completed` (event ts), `iterations`, `reviewerNotes`, `phase_summaries[]` accumulation |
| `phase_backward` | `pipeline` | target phase name | `backwardContext` (dict), `backwardReturnTarget` (str) | `backward_context`, `backward_return_target` (+ `phases[target].started` per re-entry rule) |
| `renamed` | `lifecycle` | new type_id (121's existing grammar, display.py:210-223) | `nameFrom`, `nameTo` | NOTHING (excluded from status fold; id/slug come from the row) |

Registry docstring (events.py:18-34) gains: `phaseSummaryEntry`, `backwardContext`, `backwardReturnTarget` (camelCase, matching the registry's FR-11 convention; the projected FILE keys stay snake_case `phase_summaries`/`backward_context`/`backward_return_target` — the registry documents both spellings and which side each lives on), and the consumer attribution is corrected from "feature 120's projection" to `entity_registry.meta_projection` (126).

**Grammar scope — live writer only:** the grammar reproduces the CURRENT writer's output (workflow_state_server.py:437-499). Legacy pre-current-writer files on disk (114/116: `completed_clusters`, `deferral_reasoning`, `files_changed`, `notes`, phase-level `status`, `stages{...}`) have NO grammar slot BY DESIGN — the current writer does not emit them; they are 132's historical-backfill concern, and the projection-as-oracle will correctly FLAG them non-round-trippable rather than silently reproduce them (the no-silent-lossiness contract, made explicit). `skippedPhases` note: TWO shapes are live (gate-verified) — 119/130's files carry the STRING `"[\"brainstorm\"]"`, while the writer's tests prove a NATIVE ARRAY for the documented skip mechanisms (test_workflow_state_server.py:4380-4439; transition_phase json.loads the param into a list at :948-950 and `_project_meta_json`:480-481 passes whatever shape through untouched). The event payload carries the stored value VERBATIM in EITHER shape and the projection is a shape-preserving passthrough — 127/132 emit whatever shape they recorded; round-trip is byte-identical per shape.

**Init required:** projection of an entity with zero `initialized` events raises `ValueError` naming the missing event class (spec boundary). Duplicate `initialized` events: latest-wins by uuid (MAX(uuid) discipline, 120's CONTRACT).

## D2 — Status fold: enumerated event_type filter, single MAX(uuid) across both axes

DENYLIST framing (forward-compatible with 127's status vocabulary): `_NON_STATUS_EVENT_TYPES = frozenset({"renamed", "phase_started", "phase_completed", "phase_backward"})`. `status` = `to_value` of the MAX(uuid) event with `event_type NOT IN _NON_STATUS_EVENT_TYPES` (both `lifecycle` and `execution` axes participate in ONE fold — the spec's "axis precedence" question dissolves: latest status-bearing event wins regardless of axis, matching v1's single-field last-write-wins). A future status-bearing event_type 127 mints participates BY DEFAULT (an allowlist would silently exclude it — the triple-blind hazard: generator/oracle/projection all sharing one enumeration); the forward rule is the inverse: any future NON-status event type MUST be added to the denylist, and 127's integration asserts its event vocabulary against this set — 126 carries the obligation as an explicit test-level comment/assertion beside `_NON_STATUS_EVENT_TYPES` (127 inherits it in code, not prose alone; `events.event_type` has no CHECK enumeration to assert against structurally). `renamed` is structurally excluded — the load-bearing filter (rename's to_value is a type_id; test_views.py:181-186 proves status tokens and rename share the lifecycle axis). A fixture interleaves a mid-feature execution-axis `status_changed` between lifecycle events to pin the cross-axis fold. NULL to_value among status-bearing events projects verbatim as null (120 semantics).

## D3 — Field derivation table (the whole shape)

| field | source | fold / absence rule |
|---|---|---|
| `id`, `slug` | entities row `type_id` tail: after first `:`, split at first `-` | current row (post-rename = new tail) |
| `created` | `entities.created_at` | v1's `_iso_now()` fallback (workflow_state_server.py:443) dropped under invents-nothing — created_at is NOT NULL on the entities row |
| `status` | D2 fold | — |
| `mode`, `branch` | payload of latest event carrying the key | last-carrying-event wins (MAX uuid among carriers) |
| `phases[p].started` | `phase_started`/`phase_backward`-into-p event timestamp | last-entry-wins per phase (re-entry OVERWRITES started — matches the live write site workflow_state_server.py:941-945 `setdefault` + `["started"] = ts`) |
| `phases[p].completed`, `.iterations`, `.reviewerNotes` | `phase_completed` for p: its timestamp / payload keys | last completion per phase wins; started-only phase carries `started` ONLY (keys absent) |
| `lastCompletedPhase` | phase of MAX(uuid) `phase_completed` event | null-PRESENT when init exists but zero completions |
| top-level `completed` | PRIMARY: the finish-phase `phase_completed` event's timestamp (spec FR126-2; the live writer sources it from `phase_timing["finish"]["completed"]`, workflow_state_server.py:450-452 — 120's real file is byte-identical finish.completed == completed). FALLBACK: terminal-but-no-finish (abandoned-pre-finish, spec boundary) = the terminal lifecycle event's timestamp | ABSENT if neither exists; NEVER wall-clock (v1's `_iso_now()` fallback deliberately dropped). The D6 generator MUST produce cases where the lifecycle-terminal ts differs from finish.completed so the primary/fallback rule is non-vacuous. PRIMARY fires whenever a finish `phase_completed` event exists, independent of terminal status (faithful to spec FR126-2); the finish-then-backward-without-terminal seam vs the live writer's `status in (completed, abandoned) OR last_completed == "finish"` condition (workflow_state_server.py:450) is consciously deferred to 127's writer-equivalence integration |
| `skippedPhases` | payload key — shape-preserving passthrough (string AND native-array shapes both live) | last-carrying wins; absent if never carried; NO shape normalization ever |
| `brainstorm_source`, `backlog_source` | payload keys | last-carrying wins; absent if never carried |
| `backward_context`, `backward_return_target` | `backwardContext`/`backwardReturnTarget` payload keys | last-carrying wins; a FALSY carried value (None/`{}`/`""`) projects ABSENT — matches the writer's conditional emission (workflow_state_server.py:484-487 `if metadata.get(...)`) and 075's own test ("Empty phase_summaries list is not projected (matches backward_context pattern)", test_workflow_state_server.py:4539) |
| `phase_summaries` | ACCUMULATE `phaseSummaryEntry` dicts in uuid order across `phase_completed` events | each event carries ONE self-contained entry (lossless-by-construction; matches v1's append-per-completion, 131's real file: 2 entries of 5 phases); empty accumulation → field ABSENT (075 pattern) |

`phases` dict key order = first-entry order (uuid order of first `phase_started` per phase) — dict-level equality is the contract; key order is not asserted byte-wise except where a fixture derives from a real file and trivially matches.

**Kind guard:** first statement after the row fetch: row absent → `ValueError(uuid)`; `row["kind"] != "feature"` → `ValueError(kind)` (spec boundary; project shape belongs to 123).

**Read path:** ONE `read_events(conn, entity_uuid)` call (full ordered stream, index-covered) + one entities-row SELECT. NO per-entity `entity_state` reads (#067's O(total-events) trap); 120's views are not used at all — per-phase history needs the full stream anyway.

## D4 — FR126-5 read-only structural pin: `PRAGMA query_only` canary

The read-only test opens a connect_v2 connection, sets `PRAGMA query_only=ON`, and runs `project_meta` over a seeded entity — ANY write attempt raises `sqlite3.OperationalError` at the engine level (structural, not grep). One companion test proves the canary's teeth: the same conn REJECTS a probe INSERT (the canary itself demonstrated red). This is SQLite-enforced zero-write proof, stronger than source-scanning.

## D5 — Golden fixtures (spec FR126-3 (a)-(g), provenance pinned)

| fixture | expected dict byte-derived from | exercises |
|---|---|---|
| (a) full standard run | `docs/features/120-state-projection-views/.meta.json` (completed, 5 phases, doubly-encoded reviewerNotes) — frozen copy in-test, provenance comment | the clean whole shape |
| (b) skipped phases — BOTH shapes | string form: 130's real file (`"[\"brainstorm\"]"`); array form: the writer's own test expectation (test_workflow_state_server.py:4380-4439, `[{"phase": ..., "reason": ...}]`) | shape-preserving passthrough, byte identity per shape |
| (c) phase_summaries | 131's real file (2-entry array of 5 phases) | MULTI-entry accumulation (non-vacuous fold) |
| (d) backward + backlog-sourced | `backward_context` value-shape from 073's fixture (test_workflow_state_server.py:4600, `{"source_phase": "design"}`); `backward_return_target` value from 073's own documented payload shape (docs/features/073-yolo-relevance-gate/design.md:163, `"backward_return_target": "create-plan"` — spec FR126-3(d)'s preference order honored; absent from the live-writer test suite itself); `backlog_source` synthetic (no exemplar in any documented shape — acknowledged in-test) | backward pair + sources |
| (e) minimal-init skeleton | 122's real planned file (`status` planned, `phases {}`, `lastCompletedPhase` null PRESENT, `mode`, `branch`) | init-only projection |
| (f) renamed entity | synthetic: init → phase run → `renamed` (new type_id) | id/slug = NEW tail; `status` before==after (filter pin); phases unperturbed |
| (g) in-flight + cross-axis fold | synthetic: init + 2 completed + 1 started-not-completed, WITH a mid-feature execution-axis `status_changed` interleaved between lifecycle events | absent-vs-started-only semantics + the D2 cross-axis status pin (folded here, not an extra fixture) |

Each fixture: synthesize the D1 event stream, run `project_meta`, assert field-by-field against the frozen expected dict (for (a)/(b)/(c)/(e): the REAL file's parsed content, minus fields the grammar owner didn't write — none expected; any true residual must be enumerated in-test, not silently dropped).

## D6 — Property test (spec SC2, 120's D4 discipline verbatim)

`MASTER_SEED = 0x126`, `N_CASES = 200`, per-case `random.Random(case_seed)` for EVERY draw (phase sequences incl. re-entries and backwards, skips, status changes, renames, payload presence/absence, falsy backward values, timestamp jitter incl. ties, per-case entity), global `random` untouched, ONE bootstrapped DB, isolation by per-case entity uuids, no cleanup. Oracle = independent pure-Python fold over the generated event specs (built from the SPECS, not by re-reading the DB — kills a projection that misreads storage). Field-by-field assert vs `project_meta`. Failure message: seed + full event sequence. Wall-clock < 5s with elapsed in the message.

## D7 — Ships-dark teeth (spec SC5)

`_V2_DARK_MODULES` += `"meta_projection.py"`; `_V2_LIVE_REFERENCE_NEEDLES` += `entity_registry.meta_projection` / `from entity_registry import meta_projection` / `from .meta_projection import`; 3 seeded-offender teeth (one per spelling), red-first against the un-extended needle set. Module preamble mirrors views.py; module-top `from entity_registry import events` (registry order, D2-of-120 pattern) — meta_projection reads `events` via `read_events` so the import is live-load-bearing, comment states both roles.

## D8 — NFR-3 two-component harness (spec 5a/5b)

**Script:** `plugins/pd/hooks/tests/bench-populated-read.sh` (new; committed; no repo state mutated — everything under `mktemp -d`).

- **(5a) measured:** the boundary is BOTH spec-named per-session state reads — (i) the feature walk (`python3 -c` snippet, session-start.sh:76-101) and (ii) the projects glob (:409-427, globs `projects/*/` and json-loads each `.meta.json`) — each timed as its own process against a seeded tree; doctor/reconcile nowhere in the harness. EXTRACTION MECHANISM (drift-proof, SYMMETRIC — both components): TWO sentinel pairs in session-start.sh (comment-only edits, zero behavior change) — `# BENCH-WALK-START/END` bracketing the `latest_meta=$(python3 -c '…')` ASSIGNMENT (lines 75-102, EXCLUDING line 74's `local` declaration — eval-ing `local` at top level errors; the harness evals the extracted assignment with `features_dir` repointed at the seeded tree; sentinels are BASH comments outside the single-quoted python string, which stays byte-untouched per FR-1.1) and `# BENCH-GLOB-START/END` bracketing the projects-glob snippet (:409-427). Drift-guards live in TWO layers: the bench script itself exits loud (status 3, named message) if either extraction is empty or missing its load-bearing lines (walk: `os.walk` + `json.load`; glob: `glob.glob` + `json.load`) — a self-guarding harness; and `test_census_seeder.py` carries a cheap pytest asserting all four sentinel markers exist in session-start.sh (suite-visible drift signal). Neither component can silently diverge from the hook. Glob measurement pins the NO-MATCH full-scan case (the snippet breaks on first workspace_uuid match at :424, so latency is match-position-dependent; the worst case matches the walk's always-full-scan posture and gives 127 a defensible number). Seeded tree generator (`random.Random(0x126)`): feature dirs (+ a projects/ tree for (ii)) with realistic `.meta.json` (sizes drawn from the real repo's distribution — phases populated, reviewerNotes-scale strings), at TWO scales: the live-repo feature-`.meta.json` COUNT captured ONCE at 126 task time as a RECORDED constant (`find docs/features -name .meta.json | wc -l` — the PARSE-cost driver; ~22 on this repo vs ~137 dirs, .meta.json being gitignored; the seeded tree carries one .meta.json per dir so seeded N = parsed N; passed as an explicit harness argument on every re-run — 127 consumes 126's recorded N, never re-derives; a fresh `find`-derived count is only the first-capture default) and 10× that. `N_ITERATIONS = 120` per scale (>100, honest p95 = ~114th order stat). Artifact `populated-latency-baseline.md`: p50, p95, full sorted ms distribution per scale, seed + parameters, machine context (`sw_vers`, `uname -m`, `sysctl -n machdep.cpu.brand_string`), reproduction command, and the 127 clause (MUST re-run both components at these seeds; compare DB-direct reads vs 5a).
- **(5b) seeded only:** `scripts/seed-census-db.py` — bootstraps a v2 DB (`schema_v2` + `events` + registered DDL) in a target dir and seeds ~533 entities across 7 workspaces (deterministic `random.Random(0x126)`; kinds/phases/payload sizes drawn to census proportions; ALL synthetic strings). Write API: raw INSERTs on a connect_v2 conn (v2 has no registration API until 122/123; v2 entities deliberately has NO type_id uniqueness — FR-4, schema_v2.py:49) with SEQUENTIAL deterministic type_ids (`feature:{i:04d}-{slug}`) — exact counts, collision-free by construction; events through `append_event`. Smoke: pytest test runs it at REDUCED scale (20 entities/2 workspaces) and asserts row counts + one projected entity round-trips. Full-scale run happens at task time; its runtime + row counts recorded in the artifact.

**Seed note:** D6, 5a, and 5b each construct an INDEPENDENT `random.Random(0x126)` for disjoint artifacts — no draw stream is shared, so the common literal is a convention, not a coupling.

## D9 — File inventory

| file | change |
|---|---|
| `plugins/pd/hooks/lib/entity_registry/meta_projection.py` | NEW (dark) |
| `plugins/pd/hooks/lib/entity_registry/test_meta_projection.py` | NEW (fixtures, property test, canary, kind/orphan/init guards) |
| `plugins/pd/hooks/lib/entity_registry/events.py` | registry docstring: +3 keys, consumer attribution fix |
| `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py` | dark-module guard: +1 module, +3 needles, +3 teeth |
| `plugins/pd/hooks/tests/bench-populated-read.sh` | NEW (5a harness) |
| `plugins/pd/hooks/session-start.sh` | sentinel comments only (BOTH pairs: BENCH-WALK-START/END + BENCH-GLOB-START/END, zero behavior change) |
| `scripts/seed-census-db.py` | NEW (5b seeder) |
| `plugins/pd/hooks/lib/entity_registry/test_census_seeder.py` | NEW (5b smoke, reduced scale) |
| `docs/features/126-lossless-meta-json-projection/populated-latency-baseline.md` | NEW (artifact, task time) |

No live writer, no MCP, no UI, no doctor changes. `.meta.json` writer untouched (127). Backlog #061 already closed; #067 consumed as input only.

## Testing strategy

1. The 7 golden fixtures (D5) — real-file byte-derivation per field-class.
2. Property test (D6) — grammar-conditional losslessness, 200 cases.
3. Guards: kind (project uuid → ValueError), orphan uuid, zero-init, malformed payload JSON (raw-INSERT seeded) → loud JSONDecodeError, duplicate init latest-wins, terminal-no-finish (completed = terminal event ts), same-timestamp tie (uuid7 order wins), null-status-verbatim (NULL to_value among status-bearing events never resurrects an earlier non-null), re-entered-phase last-entry-wins (backward-then-forward overwrites phases[p].started per workflow_state_server.py:941-945).
4. D4 query_only canary (+ its own teeth).
5. Registry pins: unknown-key ignored; per-key spelling (camelCase payload vs snake_case file keys).
6. Ships-dark teeth red-first (D7).
7. 5b smoke at reduced scale; 5a runs at task time (artifact, not CI).
8. Full-suite regression + validate + doctor pin (spec SC7).
