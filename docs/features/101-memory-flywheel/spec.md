# Feature 101 — Memory Flywheel Loop Closure (Specification)

> Source: `docs/features/101-memory-flywheel/prd.md` · Backlog #00053
> Mode: standard · Branch: `feature/101-memory-flywheel`

## Scope

Six FRs across three stages closing the four flow gaps that prevent pd's
memory subsystem from compounding feedback. The infrastructure
(`record_influence_by_content` MCP, `_influence_score` in `ranking.py`,
FTS5 schema + triggers, `recall_count` column, `_project_blend`,
`/pd:promote-pattern` skill) already exists; this feature wires the
existing pieces together and self-heals the broken FTS5 backfill.

**Out of scope (non-goals from PRD):** new decay mechanism (existing
`maintenance --decay` is canonical), parallel promote-pattern path
(existing skill is canonical), PostToolUse hook on `complete_phase` MCP
(existing `memory_refresh` digest is sufficient until proven otherwise),
edge-case mutation tests beyond integration-floor coverage,
backwards-compatibility shims (private tooling).

## Stage Boundaries

| Stage | FRs | File domain |
|-------|-----|-------------|
| 1 — Foundations | FR-2, FR-3, FR-5 | `database.py`, `maintenance.py`, `memory_server.py`, `session-start.sh` |
| 2 — Influence Wiring + Lifecycle | FR-1, FR-4 | `commands/{specify,design,create-plan,implement}.md`, `maintenance.py`, new `audit.py`, new `scripts/check_block_ordering.py` |
| 3 — Adoption Trigger | FR-6 | `skills/retrospecting/SKILL.md` |

Stages MAY ship as one PR or three sequential PRs at implementer
discretion. Per PRD OQ-4 resolution, default: single PR with three
internal commit boundaries.

---

## Functional Requirements

### FR-1: Mechanize Influence Recording at Reviewer Return Points

Restructure the existing 14 post-dispatch influence-tracking prose blocks
in orchestrator commands so the LLM cannot skip them under load.

**Sites (verified):**
- `commands/specify.md:166, 326`
- `commands/design.md:368, 564`
- `commands/create-plan.md:162, 319, 473`
- `commands/implement.md:127, 192, 505, 666, 844, 1015, 1178`

**Restructuring rules (apply to all 14 sites):**
1. **Unconditional invocation:** Drop the `if search_memory returned entries`
   conditional gate. Pass `injected_entry_names = []` if no prior search
   occurred (the MCP function short-circuits cheaply at memory_server.py:824).
2. **Reposition:** Move the block BEFORE the "Branch on result" / "Decide
   pass-or-fail" step in each command. Currently buried mid-step (between
   parse-response and branch-on-result), which structurally invites the
   "lost in the middle" attention failure.
3. **Numbered as own step:** Each site receives its own numbered step (e.g.,
   `c.0` or new explicit step letter). Not "Post-dispatch tracking" prose
   — a literal step in the orchestrator's checklist.
4. **Observable output line:** Each block requires the orchestrator to emit
   `Influence recorded: N matches` to its output (visible in conversation
   transcript). Provides an LLM self-correction signal — if the line is
   absent, the orchestrator can detect skip on next turn.

**Audit script (NEW):** `plugins/pd/hooks/lib/semantic_memory/audit.py` with
CLI `python -m semantic_memory.audit --feature {id}`. Reads
the **influence-log sidecar** (see below) to identify which entries were
injected during the feature's reviewer dispatches, then queries the DB
for current `influence_count` and `recall_count` per entry. Emits a
markdown table.

**Influence-log sidecar (NEW, capture mechanism for AC-1.5 ground truth):**
Each restructured post-dispatch block writes one JSON line to
`docs/features/{id}-{slug}/.influence-log.jsonl` immediately before the
`record_influence_by_content` MCP call:

```json
{"timestamp": "<iso>", "agent_role": "<role>", "injected_entry_names": [...], "feature_type_id": "feature:{id}-{slug}"}
```

The audit script reads the sidecar to construct the "was injected"
ground truth. File is append-only, never truncated. Best-effort —
sidecar write failure is logged but does not block the influence call.

#### Acceptance Criteria

- **AC-1.1:** All 14 post-dispatch blocks have the conditional gate
  removed. Verified by `grep -L 'if search_memory returned entries before' plugins/pd/commands/{specify,design,create-plan,implement}.md`
  returning all four files (i.e., no occurrences left).
- **AC-1.2:** All 14 blocks appear BEFORE the "Branch on result" step.
  Verified by `python plugins/pd/scripts/check_block_ordering.py` (NEW;
  parses each command file, finds the per-dispatch `Post-dispatch
  influence tracking` markers, asserts each occurs before the next
  `**Branch on result**` or `**Branch on (...) result**` marker within
  the same numbered step section). Script lives in `plugins/pd/scripts/`
  and is invoked from validation (e.g., validate.sh integration).
- **AC-1.3:** All 14 blocks include the literal output-line instruction
  `Influence recorded:` in their prose. Verified via `grep -c 'Influence recorded:' plugins/pd/commands/{specify,design,create-plan,implement}.md`
  → 2 / 2 / 3 / 7 (matching site counts).
- **AC-1.4:** New CLI `python -m semantic_memory.audit --feature {id}` runs
  end-to-end and emits a markdown table with columns: `entry_id`,
  `influence_count`, `recall_count`, `was_injected`. Reads
  `.influence-log.jsonl` sidecar for `was_injected` ground truth.
  Test: invoke against feature 101 itself; assert non-empty output and
  rows for each entry that appears in the sidecar.
- **AC-1.5:** **SC-1 validation:** For reviewer dispatches in feature
  101 occurring AFTER FR-1's commit lands on the feature branch (i.e.,
  implement-phase or later dispatches in stages where FR-1 is wired),
  ≥80% of entry IDs in `.influence-log.jsonl` have `influence_count ≥ 1`
  per `audit.py`. Pre-FR-1 dispatches excluded from the dogfood denominator.
- **AC-1.6:** Empty-list short-circuit guard. Microbenchmark in
  `test_memory_server.py`: invoke `_process_record_influence_by_content`
  with `injected_entry_names=[]` 1000 times; assert P95 latency < 5ms.
  Confirms the unconditional-invocation strategy in AC-1.1 has bounded
  cost for the empty case. Verified evidence: short-circuit at
  `memory_server.py:824` (`if not injected_entry_names: return ...`).

### FR-2: FTS5 Integrity Check + On-Demand Backfill

Self-heal the empty `entries_fts` virtual table. Existing migration 5
(`database.py:303-323`) runs `INSERT INTO entries_fts(entries_fts) VALUES('rebuild')`
but the user's DB shows 0 rows — diagnose AND repair.

#### Acceptance Criteria

- **AC-2.1:** New CLI subcommand `python -m semantic_memory.maintenance --rebuild-fts5`
  executes `INSERT INTO entries_fts(entries_fts) VALUES('rebuild')` and
  prints `Rebuilt N rows in entries_fts.` to stdout. Idempotent (re-run
  produces same row count).
- **AC-2.2:** `session-start.sh` invokes a new integrity check inline.
  Pseudocode:
  ```bash
  fts_count=$(python3 -c "import sqlite3; ...")
  entry_count=$(python3 -c "import sqlite3; ...")
  if [ "$fts_count" -eq 0 ] && [ "$entry_count" -gt 0 ]; then
      python3 -m semantic_memory.maintenance --rebuild-fts5 >&2
      # Write diagnostic file
  fi
  ```
- **AC-2.3:** **Unconditional one-time post-rebuild diagnostic file**
  at `~/.claude/pd/memory/.fts5-rebuild-diag.json` capturing:
  `entries_count` (pre-rebuild),
  `fts5_count_before`,
  `fts5_count_after`,
  `schema_user_version` (integer from `PRAGMA user_version` — replaces
  the previously-proposed timestamp; the DB does not store migration
  timestamps),
  `fts5_errors` (any caught exception messages, else `[]`),
  `db_path` (absolute),
  `created_at` (ISO 8601, the `_iso_utc` Z-suffix form).
  Written ONCE on first rebuild; subsequent rebuilds APPEND an entry to
  the JSON's `refires` array (each: `{timestamp, fts5_count_before, fts5_count_after}`).
- **AC-2.4:** If diagnostic file already exists when rebuild fires, log
  stronger warning: `[memory] FTS5 rebuild fired again (refire #N); see
  ~/.claude/pd/memory/.fts5-rebuild-diag.json`.
- **AC-2.5:** Integration test (`test_database.py` or new `test_maintenance.py`):
  - Drop `entries_fts`, populate `entries`, run integrity check, assert
    `entries_fts.count > 0` post-check.
  - Assert diagnostic JSON file created with all 6 required fields.
  - Assert second rebuild produces `refires` array entry.
- **AC-2.6:** Stdlib-only constraint: integrity check uses `python3` (pd
  venv) + bash; no external libraries.

### FR-3: Mid-Session Recall Tracking

`search_memory` MCP MUST increment `recall_count` for returned entries.

#### Acceptance Criteria

- **AC-3.1:** `_process_search_memory` in `memory_server.py` (the function
  backing the MCP tool) calls `db.update_recall(returned_ids, now_iso)`
  after computing `returned_ids` but before returning the response.
  **Dependency confirmed:** `update_recall` exists at
  `database.py:809` (`def update_recall(self, ids, now_iso)`). No new
  helper required.
- **AC-3.2:** Within-call dedup: `returned_ids = list(set([e.id for e in returned_entries]))`
  before the update_recall call. Same entry returned twice in one query
  result counts once.
- **AC-3.3:** Across calls: same entry retrieved by two separate
  `search_memory` invocations within one session has `recall_count`
  incremented by 2 (once per invocation).
- **AC-3.4:** `update_recall` UPDATE failure (locked DB, etc.) is caught;
  the response is returned to the caller anyway; warning logged to stderr
  per existing log-and-continue convention.
- **AC-3.5:** Integration test: call `search_memory` returning known
  entry X; assert `recall_count` incremented by 1 vs pre-call. Call again;
  assert incremented by 2.
- **AC-3.6:** **SC-7 validation:** Synthetic-1000-entries benchmark
  (`test_search_memory_benchmark.py`) measures `_process_search_memory`
  P50 latency before vs after FR-3. Pass when:
  `delta_p50_absolute_ms < max(5, 0.05 * baseline_p50_ms)`. Either bound
  satisfies (use the larger). Rationale: 5ms is the hard floor for
  near-zero baselines; 5% protects against scaling regressions on slower
  baselines.
  **Baseline capture:** the benchmark fixture runs the same query path
  twice — once with the FR-3 `update_recall` call monkeypatched to a no-op
  (baseline), once unpatched (post-FR-3). Both measured in the same test
  invocation; no separately-pinned baseline file required.

### FR-4: Confidence Upgrade Path

Add `_recompute_confidence` in `maintenance.py` with two-gate OR semantics
plus outcome-validation floor on the use gate.

**Gate definitions:**
- **Observation gate:** `observation_count >= K_OBS` (default 3, key
  `memory_promote_min_observations` — reused).
- **Use gate:** `influence_count >= 1 AND influence_count + recall_count >= K_USE`
  (default `K_USE=5`, new key `memory_promote_use_signal`).

Either gate triggers `low → medium`. Both gates' values doubled trigger
`medium → high` (`K_OBS_HIGH=6` reuses doubled-default convention,
`K_USE_HIGH=10`).

#### Acceptance Criteria

- **AC-4.1:** New function `_recompute_confidence(entry: dict) -> str | None`
  in `plugins/pd/hooks/lib/semantic_memory/maintenance.py`. Returns
  the new confidence value if upgrade applied, else `None`.
- **AC-4.2:** Called from `decay_confidence()` after the demotion check
  AND from `merge_duplicate()` after observation_count++.
- **AC-4.3:** New config key `memory_promote_use_signal` documented in
  `pd.local.md` reference (default 5). High-tier threshold auto-doubled
  (no separate key for K_USE_HIGH).
- **AC-4.4:** Test cases in `test_maintenance.py` (every seed specifies
  starting confidence explicitly):
  - Seed `confidence='low', observation_count=3, influence_count=0, recall_count=0` →
    upgrades to `medium` via observation gate.
  - Seed `confidence='low', observation_count=0, influence_count=2, recall_count=3` →
    upgrades to `medium` via use gate (floor met, sum=5).
  - Seed `confidence='low', observation_count=0, influence_count=0, recall_count=10` →
    does NOT upgrade (floor `influence_count >= 1` unmet despite sum >> K_USE).
  - Seed `confidence='low', observation_count=2, influence_count=1, recall_count=2` →
    does NOT upgrade (observation < 3; sum=3 < K_USE=5).
  - Seed `confidence='medium', observation_count=6, influence_count=0, recall_count=0` →
    upgrades to `high` via observation gate (6 >= K_OBS_HIGH=6).
  - Seed `confidence='medium', observation_count=0, influence_count=4, recall_count=6` →
    upgrades to `high` via use gate (sum=10 >= K_USE_HIGH=10, floor met).
  - Seed `confidence='high', observation_count=999, influence_count=999, recall_count=999` →
    no-op (idempotent at top tier; function returns None).
- **AC-4.5:** Threshold values reachable via config keys (test override
  `memory_promote_min_observations=10` and assert promotion does NOT
  fire at `observation_count=3`).

### FR-5: `source_project` Filter at Influence Recording

`_process_record_influence_by_content` filters candidate entries by
`source_project = current _project_root`.

#### Acceptance Criteria

- **AC-5.1:** Added `source_project = ?` clause (or post-fetch Python
  filter) in the candidate query inside `_process_record_influence_by_content`
  in `memory_server.py`. The current `_project_root` is read from module
  state (already loaded at server startup).
- **AC-5.2:** Default behavior — hard filter: cross-project candidates
  return 0 matches silently.
- **AC-5.3:** **Null-`_project_root` behavior:** If `_project_root` is
  None or unresolvable (e.g., global agent context), the filter is
  bypassed (NO project filter applied) and a one-line stderr warning is
  logged: `[memory] record_influence: no project context; skipping project filter`.
- **AC-5.4:** Test case 1 (cross-project rejection): insert entry with
  `source_project = 'project-A'`; call `_process_record_influence_by_content`
  with `_project_root` patched to `'project-B'` and content that would
  substring-match; assert entry A's `influence_count` unchanged.
- **AC-5.5:** Test case 2 (same-project acceptance): insert entry with
  `source_project = 'project-A'`; call with `_project_root='project-A'`
  and matching content; assert `influence_count++`.
- **AC-5.6:** Test case 3 (null-project bypass): patch `_project_root=None`;
  call with matching content; assert update applied (filter bypassed)
  AND warning emitted to stderr (capture via `capsys`).

### FR-6: Promote-Pattern Post-Retro Adoption Trigger

`retrospecting/SKILL.md` Step 4c (after universal classification) gains
a new sub-step 4c.1 that surfaces `/pd:promote-pattern` when qualifying
entries exist.

#### Acceptance Criteria

- **AC-6.1:** Step 4c.1 added to `plugins/pd/skills/retrospecting/SKILL.md`
  immediately after the existing universal-vs-project-specific
  classification. Invokes `python -m pattern_promotion enumerate --json`
  via subprocess (consistent with existing skill convention).
- **AC-6.2:** Threshold uses existing config key `memory_promote_min_observations`
  (same key as FR-4 observation gate). No new key.
- **AC-6.3:** If the enumerate response indicates `count > 0`, emit
  `AskUserQuestion` with options:
  - "Run /pd:promote-pattern (Recommended)" → invoke
    `Skill({skill: "pd:promoting-patterns"})` (the user-facing pattern;
    the command file `commands/promote-pattern.md` delegates to this
    skill).
  - "Skip" → continue retro.
- **AC-6.4:** YOLO mode override: skip the AskUserQuestion, invoke
  `Skill({skill: "pd:promoting-patterns"})` directly.
  **YOLO detection mechanism:** the parent skill (`retrospecting/SKILL.md`)
  receives `[YOLO_MODE]` as a substring token in its `args` per existing
  pd convention (matches `specifying/SKILL.md:16` "If `[YOLO_MODE]` is
  active in the execution context"). Step 4c.1's YOLO branch is
  triggered by the same token check. Document this convention in the
  SKILL.md addition. **Existing precedent for `Skill()` dispatch:**
  `retrospecting/SKILL.md` (this same file) already invokes other
  skills via `Skill({skill: "..."})` — match that pattern verbatim.
- **AC-6.5:** Zero-qualifying-entries case: no prompt emitted, no log
  noise; retro continues silently.
- **AC-6.6:** Subprocess CLI invocation isolation — the enumerate
  subprocess MUST NOT block retro completion if it errors (e.g., MCP
  unavailable, missing venv). On error: log `[retrospect] promote-pattern
  enumerate failed: {error}; skipping trigger` to stderr; continue.
- **AC-6.7:** Dogfood validation: this feature's own retro (when it
  ships) MUST exercise the trigger end-to-end at least once. Recorded
  in retro.md.

---

## Non-Functional Requirements

- **NFR-1: Zero blocking on memory ops.** All FRs degrade gracefully —
  failed MCP, locked DB, missing FTS5 module, subprocess errors — never
  block primary path. Logged per existing stderr discipline.
- **NFR-2: Stdlib-only for hooks.** FR-2 session-start integrity check
  uses bash + `python3` (pd venv) only.
- **NFR-3: Migration idempotency.** FR-2 rebuild idempotent; partial
  state on crash safe to re-run.
- **NFR-4: MCP request/response schema unchanged.** FR-3 and FR-5 do not
  change MCP-level public schemas. Side-effect changes intentional and
  documented per FR.
- **NFR-5: Test coverage at primary defense.** Each FR has at least one
  integration test exercising end-to-end. No mutation pin source-tests
  beyond what spec-driven tests already produce.
- **NFR-6: Within-call dedup on FR-3.** Set-based; no per-entry list-scan.
- **NFR-7: No backwards-compat shims.** Per CLAUDE.md private-tooling
  principle, all FRs ship as straight replacements; no config flags or
  feature toggles to gate new behavior.

---

## Out of Scope

Per PRD non-goals (re-iterated for spec discipline):

- Replacing `docs/knowledge-bank/` markdown stores with the semantic-memory DB.
- Real-time mistake monitoring / auto-detect user corrections.
- Multi-model orchestration.
- Reviewer diff token-efficiency.
- Per-feature retroactive influence backfill.
- A second decay mechanism alongside `maintenance --decay`.
- New PostToolUse hook on `complete_phase` MCP duplicating the existing
  `memory_refresh` digest in `_process_complete_phase`.
- Build-out of `/pd:promote-pattern` (already complete).
- Recall-count time-series, LLM-judged influence, confidence downgrades,
  `/pd:demote-pattern`, cross-session pattern push.

---

## Dependencies

- `record_influence_by_content` MCP tool (`memory_server.py:816`) — exists,
  reused by FR-1 and FR-5.
- `_influence_score`, `_recall_frequency` in `ranking.py` — exist, no
  changes.
- `entries_fts` virtual table + triggers — exist, no schema changes
  (FR-2 only repopulates).
- `update_recall` in `database.py` — exists, reused by FR-3.
- `decay_confidence`, `merge_duplicate`, `_select_candidates` in
  `maintenance.py` — exist, FR-4 inserts `_recompute_confidence` call.
- `_project_root` module state in `memory_server.py` — exists, read by
  FR-5.
- `pattern_promotion enumerate` CLI in `pattern_promotion/__init__.py` —
  exists, called by FR-6 subprocess.
- `Skill` dispatch tool — built-in, used by FR-6 YOLO chaining.

## Test Strategy

- **Per-FR integration tests** in `plugins/pd/hooks/lib/semantic_memory/test_*.py`
  and `plugins/pd/skills/retrospecting/test_*.py` (new file if needed).
- **Cross-FR dogfood:** Feature 101's own reviewer dispatches exercise
  FR-1 (influence wiring) and FR-3 (recall tracking) live; the post-feature
  audit (AC-1.5) confirms ≥80% influence rate.
- **Synthetic benchmark** for FR-3 latency (AC-3.6).
- **No mutation-pin source tests** — explicitly excluded per user filter.

## Open Questions

- **OQ-S1:** Should AC-1.4's audit CLI also support `--all-features` mode
  for retro-time aggregation? Default: no — single-feature is enough for
  SC-1; aggregation is a future enhancement.
- **OQ-S2:** FR-2 diagnostic JSON path is `~/.claude/pd/memory/.fts5-rebuild-diag.json`.
  Should this co-locate with the DB (which is at `~/.claude/pd/memory/memory.db`)?
  Default: yes — per the path proposed in AC-2.3.

## Acceptance Criteria Index

| AC | FR | Type | Verification |
|----|-----|------|--------------|
| AC-1.1 | FR-1 | grep | `grep -L 'if search_memory'` |
| AC-1.2 | FR-1 | grep | block-before-branch ordering |
| AC-1.3 | FR-1 | grep | `grep -c 'Influence recorded:'` 2/2/3/7 |
| AC-1.4 | FR-1 | CLI | `audit.py` runs end-to-end |
| AC-1.5 | FR-1 | DB | ≥80% influence_count ≥1 (post-FR-1 dispatches) |
| AC-1.6 | FR-1 | bench | empty-list short-circuit P95 < 5ms |
| AC-2.1 | FR-2 | CLI | `--rebuild-fts5` idempotent |
| AC-2.2 | FR-2 | bash | session-start integrity check |
| AC-2.3 | FR-2 | file | `.fts5-rebuild-diag.json` 6 fields |
| AC-2.4 | FR-2 | log | refire stronger warning |
| AC-2.5 | FR-2 | test | `test_maintenance.py` integration |
| AC-2.6 | FR-2 | constraint | stdlib-only |
| AC-3.1 | FR-3 | code | `update_recall` call site |
| AC-3.2 | FR-3 | test | within-call dedup |
| AC-3.3 | FR-3 | test | across-call increment |
| AC-3.4 | FR-3 | test | UPDATE failure handling |
| AC-3.5 | FR-3 | test | integration `search_memory` |
| AC-3.6 | FR-3 | bench | <5% P50 regression |
| AC-4.1 | FR-4 | code | `_recompute_confidence` defined |
| AC-4.2 | FR-4 | code | call sites in decay + merge |
| AC-4.3 | FR-4 | doc | config key documented |
| AC-4.4 | FR-4 | test | 7 seed cases |
| AC-4.5 | FR-4 | test | config-override |
| AC-5.1 | FR-5 | code | filter clause added |
| AC-5.2 | FR-5 | test | cross-project hard filter |
| AC-5.3 | FR-5 | code | null-project bypass + warn |
| AC-5.4 | FR-5 | test | cross-project rejection |
| AC-5.5 | FR-5 | test | same-project acceptance |
| AC-5.6 | FR-5 | test | null-project bypass |
| AC-6.1 | FR-6 | doc | Step 4c.1 added |
| AC-6.2 | FR-6 | code | reuses existing key |
| AC-6.3 | FR-6 | doc | AskUserQuestion options |
| AC-6.4 | FR-6 | doc | YOLO override documented |
| AC-6.5 | FR-6 | test | zero-qualifying silent |
| AC-6.6 | FR-6 | test | subprocess error isolation |
| AC-6.7 | FR-6 | retro | dogfood exercise |
