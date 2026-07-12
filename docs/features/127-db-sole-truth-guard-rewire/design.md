# Design: DB Sole-Truth Guard Rewire (feature 127)

Implements spec FR127-1..7. All probes below were run against the live tree at design time; every file:line cited was read, not recalled.

## D1 — meta_json_decision.py rewrite (FR127-1, FR127-2)

**Deletions (content-anchored):** `_find_sentinel` (:39-50), `_sentinel_is_valid` (:53-75), and the imports that die with them (`glob`, `pathlib.Path`). `_is_truthy` (:32-36) survives unchanged. The module's `decide()` becomes two branches:

```python
def decide(file_path: str, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Deny .meta.json writes unless the break-glass env permits."""
    if _is_truthy(os.environ.get("PD_META_JSON_WRITE_ALLOWED")):
        return {"permissionDecision": "allow"}
    return {"permissionDecision": "deny", "permissionDecisionReason": _DENY_REASON}
```

**New `_DENY_REASON` (exact text — SC1's three grep needles are `_project_meta_json`, `PD_META_JSON_WRITE_ALLOWED`, `doctor`):**

```python
_DENY_REASON = (
    ".meta.json is a read-only projection written only by the DB layer "
    "(_project_meta_json, invoked inside MCP mutations: complete_phase / "
    "transition_phase / init_feature_state / activate_feature). Direct "
    "writes are always denied — post-128, mutations fail loud "
    "(WorkflowDBUnavailableError) and recovery is /pd:doctor, never a "
    "hand-edit. Break-glass (manual emergency ONLY): set "
    "PD_META_JSON_WRITE_ALLOWED=1."
)
```

**New module docstring** states: (a) the sole-truth rationale and that feature 128 SUPERSEDED the 2026-03-18 RCA's degradation-path recommendation (dated); (b) the policy-vs-infra distinction — this module's unconditional deny is POLICY; data-file-guard.sh's `{}`-on-error emission (AC-7.8, data-file-guard.sh:8) is INFRA fail-open and is untouched; (c) **OQ-1 resolved: deny applies to CREATION too** — `decide()` is path-keyed and never consults file existence (structurally true in the two-branch form; a Claude-created orphan `.meta.json` is the reconciler-archival hazard).

## D2 — deny-matrix tests (FR127-5, SC1)

All in `plugins/pd/hooks/lib/data_file_guards/test_dispatcher.py` beside the surviving bypass test (:174). Each test constructs its sentinel world via `monkeypatch.setenv("HOME", tmp_path)` (plus bypass env unset):

1. `test_meta_json_deny_no_sentinel` — empty HOME (no sentinel anywhere) → deny. **RED-FIRST** (today :86-88 allows).
2. `test_meta_json_deny_stale_sentinel` — sentinel file whose content names a non-executable interpreter path → deny. **RED-FIRST** (today :96-97 allows).
3. `test_meta_json_deny_valid_sentinel` — sentinel naming a real executable (`sys.executable`) → deny. Regression pin (already denies today; cannot be red-first — post-127 all three worlds share one branch; the test proves the deletion left no state-dependence).
4. Every deny test asserts `permissionDecisionReason` contains all three FR127-2 elements: `"_project_meta_json"`, `"PD_META_JSON_WRITE_ALLOWED"`, `"doctor"`.
5. `test_meta_json_decision_env_bypass_allows` (:174) unchanged-green.

Red-first evidence: run tests 1-2 against the pre-D1 module and record the failures in the task report.

## D3 — allowlist made structural (FR127-3, SC2)

In `plugins/pd/hooks/lib/doctor/test_audit_writes.py`:

- **Per-entry rationale comments** on `META_JSON_WRITER_ALLOWLIST` (:60-65), one line each: `_project_meta_json` (sole FEATURE-meta projection writer — the sole-truth entry), `init_project_state` (PROJECT-meta creation writer, feature_lifecycle.py:305-306 — project meta out of 127 scope), `_fix_last_completed_phase` / `_fix_completed_timestamp` (MCP-routing symbol continuity; no direct writes today per the existing comment).
- **New test `test_meta_json_allowlist_exact_membership`:** asserts `set(META_JSON_WRITER_ALLOWLIST) == {the four names}` — the allowlist is a TUPLE (:60-65), so the set() coercion is required (a literal tuple==set is always False; pinned at design iteration 2); set equality (not subset) means any new writer symbol added to an audited tree goes red without an explicit allowlist edit.
- **Red-first for SC2's teeth:** reuse 128's scratch-offender idiom (test_audit_writes.py already carries an AST-walker probe writing a synthetic offender into a scratch tree) — demonstrate a seeded non-allowlisted `.meta.json` writer is flagged; record in the task report.

## D4 — abandon-feature rewire (FR127-7) — probe result and chosen route

**Probe (all run at design time):** NO standalone MCP tool re-projects `.meta.json`. `_project_meta_json` fires at exactly four sites — `_process_transition_phase` (:1014), `_process_complete_phase` (:1371), `_process_init_feature_state` (:1672), `_process_activate_feature` (:1723) — all wrong semantics for abandonment. entity_server.py contains ZERO `.meta.json` references (`update_entity` does not project). `reconcile_apply` syncs meta→DB (the wrong direction, :1571); `reconcile_status` is a read-only drift report (:1756-1817). BUT: `_project_meta_json` itself reads `entities.status` (:442) and already treats `abandoned` as terminal (:450 writes the `completed` timestamp) — and doctor drift-class #3 establishes the in-process invocation precedent (fix_actions/__init__.py:111-112: `from workflow_state_server import _project_meta_json; _project_meta_json(ctx.db, ctx.engine, feature_type_id)`).

**Chosen route — a thin PUBLIC re-projection MCP tool (design iteration-1 decision, superseding both spec FR127-7 branches — recorded per the skeptic's B1):** the probe's two spec-sanctioned options both fail a 127-internal principle: the inline-bypass hand-writes a file that can diverge from the DB (the split-brain 127 exists to kill), and the iteration-0 idea (a command-embedded `python -c` calling `_project_meta_json` in-process) reaches past the MCP boundary into a leading-underscore internal from an UNAUDITED markdown file — undercutting FR127-3/SC2's structural-audit intent and resting on three fragile operational assumptions (shared DB-path resolution, cold-import side-effect-freedom, CWD-relative sys.path). The superior third route is spec candidate B realized properly:

**New MCP tool `reproject_meta_json` on workflow_state_server.py** (~15 lines + tests):
- Async tool `reproject_meta_json(feature_type_id: str | None = None, ref: str | None = None)` — the `str | None = None` default is LOAD-BEARING (design iteration 2 blocker): `_resolve_ref_to_feature_type_id` treats any non-None feature_type_id as authoritative (:1851 returns it verbatim), so a `str = ""` default would make every ref-only call resolve to `""` → `db.get_entity("")` → None → warning-return WITHOUT writing (:396-398) — a silent no-op reintroducing the split-brain. Siblings use the same None default (get_phase :1877, complete_phase :1918, validate_prerequisites :1950). Ref-resolution happens in the ASYNC TOOL BODY mirroring get_phase (:1884-1887: explicit try/except ValueError → `_make_error("invalid_ref", ...)`) — NOT inside the decorated handler, where `@_catch_value_error` would mislabel an unknown ref as `invalid_transition` (its "not found" substring key at :768 misses the resolver's "No entity found" text; pinned at design iteration 3). Handler `_process_reproject_meta_json(engine, db, artifacts_root, feature_type_id)` receives the resolved ftid, call `_project_meta_json(db, engine, ftid)` (the existing allowlisted writer — a FIFTH call site beside :1014/:1371/:1672/:1723), `return json.dumps({"projected": True, "feature_type_id": ..., "warning": <str|None>})` — a JSON STRING like every sibling `_process_*` (:1749/:1787/:1803), never a raw dict. A non-None warning from `_project_meta_json` means NO file was written (entity missing, artifact_path unset :400-403) — the handler surfaces it as `{"projected": False, "warning": ...}` so the caller's fail-loud check has a signal.
- Decorator stack mirrors the READ handlers (`@_with_error_handling` + `@_catch_value_error`, no `@_with_retry`): its DB access is read-only; the file write is not a SQLite mutation. DB-down rides the 128 contract → `db_unavailable` envelope for free.
- Audit posture: the writer SYMBOL is the already-allowlisted `_project_meta_json`, invoked from inside an AUDIT_TREES file — the AST write-audit sees exactly what it sees for the existing four sites. The exact-4-member allowlist test (D3) is untouched.
- Cross-server consistency (dissolves the DB-path assumption): `update_entity` (entity-registry server) and this tool (workflow server) open the SAME cross-project entities.db via the same standard resolution (`ENTITY_DB_PATH` → default), as every existing projection already does (e.g. `complete_phase` projects registry-written metadata today); WAL guarantees a committed registry write is visible to the workflow server's connection.
- Tests in test_workflow_state_server.py: (1) happy path — seeded feature WITH artifact_path set (the projection depends on it, :400-403), `db.update_entity(status="abandoned")` (status kwarg verified, database.py:7351), then the tool called VIA `ref=` — the exact shape abandon-feature uses; a feature_type_id= call would green while the ref path no-ops (vacuous, design iteration 2) — asserting `.meta.json` regenerated with `status: abandoned` AND the terminal `completed` timestamp (:450) AND `projected: true`; (2) unknown ref → error envelope; (3) DB-down fault injection MUST raise a `sqlite3.Error` at the DB read (rides `@_with_error_handling` → `error_type: db_unavailable`, :739-744) — NOT toggle the module-global `_db_unavailable`, which yields a different bare envelope with no error_type (:166-170).

**abandon-feature.md Steps 4+5 collapse:**
- **New Step 4 (DB truth, sole status mutation):** `update_entity(type_id="feature:{folder-name}", status="abandoned")` (the old Step 5's call, now primary; old Step 4's direct Write DELETED — no dual-write).
- **New Step 5 (projection):** `reproject_meta_json(ref="feature:{folder-name}")` — the DB-rendered file, via the sanctioned tool boundary.
- **Failure text (replaces :59's "`.meta.json` change persists"):** if either call fails, STOP and report the error (fail loud; recovery is /pd:doctor) — the command never hand-writes the file.
- **Shape change (flagged for implement review):** abandoned features now get the top-level `completed` timestamp (:447-452 treats `abandoned` as terminal) which the old "preserve all other fields" direct write did not add — more correct (DB projection is canonical), noted so it surprises no one.
- **132 handoff (dated 2026-07-12):** the rebuild tool may subsume this tool's job (bulk regeneration); keep the single-feature tool — it is the API 132's bulk path can iterate.

**Spec sweep (upward, same revision):** FR127-7's fallback branch and Scope In updated to name the chosen chain (recorded in spec.md + .review-history.md); FR127-2's zero-consumers claim UNCHANGED — route D never touches the bypass env, the caveat stays un-triggered.

**Docs-sync (DEFINITE deliverable — plan review B1; count verified live):** plugins/pd/README.md:231 renders "exposes 21 tools" + a tool table (:235-247) for workflow_state_server; the live `@mcp.tool()` count IS 21 (re-counted at plan review per the 131/129 drift lesson, not assumed) → task 3 edits it to 22 AND adds a `reproject_meta_json` table row. Top-level README.md renders no MCP-tool enumeration (verified). entity-server's "20 tools" (:202) untouched.

## D5 — NFR-3 measurement (FR127-4, SC3; OQ-2 resolved)

**Baseline reproduction (UNCHANGED harness):** ONE invocation — `bash plugins/pd/hooks/tests/bench-populated-read.sh --features 22` — which already emits BOTH scales (SCALES=[N, 10N], bench-populated-read.sh:63: N=22 AND N=220; a second `--features 220` run would only re-measure 220 and add an unused 2200 — dropped at design iteration 2). Seed 0x126 and N_ITERATIONS=120 are internal to the script. Verdicts compare against the FRESH reproduction (spec boundary case).

**Census substrate (corrected at design iteration 1 — the script's scale is a DEFAULT, not fixed: `--entities N` / `--workspaces N` exist):** three seeded DBs via `scripts/seed-census-db.py --target-dir <mktemp -d>` at seed 0x126: `--entities 22` (like-for-like vs the N=22 file baseline, BINDING verdicts), `--entities 220` (trend, vs the N=220 file figures), and the 533/7 default census (realistic-population FYI — mirroring 126's component 5b). Workspace count stays 7 across all three (the workspace-lookup scans the workspaces table; its row count is the relevant scale and is stated in the artifact). This satisfies SC3's both-scales criterion literally.

**View materialization (design iteration 2 blocker — the seeded DB lacks `entity_axis_state`):** seed-census-db.py imports only `events`+`schema_v2` (:39-40) and `bootstrap_v2` replays ONLY DDL registered at call time (schema_v2.py:130-135), so the seeded v2.db has NO views. FR127-4 forbids touching the 126 harness, so bench-db-direct-read.sh materializes the view itself as a ONE-TIME setup step after seeding: `plugins/pd/.venv/bin/python -c "import sys; sys.path setup; import entity_registry.views; from entity_registry.schema_v2 import bootstrap_v2; bootstrap_v2('<seeded>/v2.db')"` — `CREATE VIEW IF NOT EXISTS` persists in sqlite_master, so the per-sample spawn processes just query it (no per-sample DDL). `entity_registry.axes` is NOT imported (entity_phase_status/entity_state are unused by the pinned queries; the walk-equivalent reads `entity_axis_state` only).

**Query shapes (OQ-2 resolved, honoring #067 — per-entity `entity_axis_state`, never per-entity `entity_state`):**

- **walk-equivalent** ("find active feature + its phase" — what 132's session-start would run), two statements per sample:
  1. `SELECT e.uuid FROM entities e JOIN entity_axis_state s ON s.entity_uuid = e.uuid AND s.axis = 'execution' WHERE e.workspace_uuid = ? AND e.type = 'feature' AND s.to_value = 'active'`
  2. per returned uuid (or a fixed probe uuid when none match): `SELECT to_value FROM entity_axis_state WHERE entity_uuid = ? AND axis = 'pipeline'`
  Worst-case posture mirrors the baseline — and the no-match is GUARANTEED by the seed itself (corrected at design iteration 3): seed-census-db.py emits only `lifecycle` + `pipeline` axis events (:124/:138/:145/:155), never `execution`, so query #1's `s.axis = 'execution' AND s.to_value = 'active'` filter matches zero rows by construction and query #2 always takes the fixed-probe-uuid fallback. The artifact states plainly that the walk-equivalent measures pure no-match GROUP-BY scan cost (the analogue of 126's no-match glob) — its p95 must not be misread as a real active-feature-resolution latency (reinforces the 132 semantics handoff). LABEL (design iteration 1): this is a LATENCY analogue, not a correctness-faithful resolver — `entity_axis_state.to_value` comes from the `MAX(uuid)` row and uuids sort lexicographically, not temporally (views.py:79), so "latest phase" semantics are approximate; 132 must pin correct latest-event semantics before cutover (stated in the artifact + 132 handoff). The artifact records `EXPLAIN QUERY PLAN` for both statements (feeds #067's 132 mandate).
- **workspace-lookup** (glob-equivalent): `SELECT uuid FROM workspaces WHERE project_root = ?` with a non-matching root (no-match posture, same as the baseline's glob component).

**Process basis (spec-pinned):** each sample = one spawn of `plugins/pd/.venv/bin/python -c "<connect, query, close>"` — 120 samples per query per posture, mirroring the baseline's per-sample spawn shape. The in-process amortized figures (one process, 120-iteration loop) are reported FYI-only.

**New committed script:** `plugins/pd/hooks/tests/bench-db-direct-read.sh` — mirrors bench-populated-read.sh's output format (sorted distributions, p50/p95 lines) so the artifact can quote both harnesses uniformly.

**Artifact:** `docs/features/127-db-sole-truth-guard-rewire/db-read-latency-verification.md` — both measurement sets verbatim (both file-side scales), machine context, EXPLAIN QUERY PLAN output, reproduction commands, verdicts (i) walk-equivalent p95 ≤ 31 ms binding at N=22, (ii) workspace-lookup p95 ≤ 32 ms, (iii) census FYI-only, 220 as trend evidence, and the explicit 132 go/no-go statement.

## D6 — test-world note

The deny-matrix tests set up sentinel worlds that `decide()` no longer probes — deliberately: they prove behavior is world-INDEPENDENT (the deletion's contract), and tests 1-2 double as the red-first evidence against the pre-D1 module.

## D7 — file inventory (complete)

1. `plugins/pd/hooks/lib/data_file_guards/meta_json_decision.py` — rewrite (D1)
2. `plugins/pd/hooks/lib/data_file_guards/test_dispatcher.py` — +3 deny-matrix tests (D2 items 1-3; item 4 is a shared assertion across them, item 5 the pre-existing bypass test unchanged — count corrected at gate)
3. `plugins/pd/hooks/lib/doctor/test_audit_writes.py` — rationale comments + exact-membership test (D3)
4. `plugins/pd/commands/abandon-feature.md` — Steps 4+5 rewire (D4)
5. `plugins/pd/hooks/tests/bench-db-direct-read.sh` — NEW (D5)
6. `docs/features/127-db-sole-truth-guard-rewire/db-read-latency-verification.md` — NEW artifact (D5)
7. Feature docs (spec/design/plan/tasks/.review-history)

Plus (route D): `plugins/pd/mcp/workflow_state_server.py` (+`reproject_meta_json` tool + handler), `plugins/pd/mcp/test_workflow_state_server.py` (+3 tests), and `plugins/pd/README.md` (21→22 tools + table row — plan review B1).

No command/skill/agent/hook add/remove → README COMPONENT counts unchanged; the MCP-tool count line IS touched (D4 docs-sync, definite). No doctor check changes → pin unchanged.

**QA deliverables (assigned here per design iteration 1):** (a) FR127-6's suite baseline re-derived at merge-base in a scratch worktree (the 122/128 pattern) before the feature-branch run, deltas fully accounted; (b) SC4's checks named explicitly: dispatcher fail-open infra tests green unchanged AND backlog_decision.py zero-diff AND the function-scoped check that `test_backlog_decision_always_denies` (test_dispatcher.py:160-171 — it lives in the file task 1 edits, whole-file zero-diff impossible) has no overlapping diff hunks (wording synced to spec SC4 at relevance round 1 — the task-review W3 sweep had missed this restatement); (c) SC6's repo-wide direct-write sweep executed with the disposition table in the task report (grep instructed `.meta.json` writes across plugins/pd/{commands,skills,agents}; known hit abandon-feature.md:50 → fixed by D4; design-time sweep found no second offender — the task-phase re-run confirms on the final tree).

## D8 — 133 handoff check (spec Dependencies)

Design confirms: no doctor check probes the degraded-permit behavior (the write-audit tests assert writer inventory, not guard policy; the guard's own tests live in test_dispatcher.py) — nothing for 133 to retire from this feature.
