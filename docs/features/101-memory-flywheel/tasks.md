# Feature 101 — Memory Flywheel Loop Closure (Tasks)

> Plan: `plan.md` · Spec: `spec.md` · Design: `design.md` · Backlog #00053

## Format

Each task: 5–15 minutes. Done criterion is binary. TDD ordering enforced
(RED before GREEN). `Depends:` lists task IDs that must complete first.

---

## Stage 1 — Foundations

### P1.1 — FR-2: FTS5 self-heal

- [ ] **T1.1.1** Write `test_rebuild_fts5_basic` — drop `entries_fts`, populate `entries`, call rebuild_fts5, assert `entries_fts` count > 0. (TDD: RED) | File: `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` | Done: pytest --collect-only shows the test; running it FAILS because rebuild_fts5 not yet implemented | Depends: —
- [ ] **T1.1.2** Write `test_rebuild_fts5_diagnostic_file` — assert `.fts5-rebuild-diag.json` created with all 8 fields (entries_count, fts5_count_before, fts5_count_after, schema_user_version, fts5_errors, db_path, created_at, refires=[]). (TDD: RED) | Same file | Done: test FAILS (expected) | Depends: T1.1.1
- [ ] **T1.1.3** Write `test_rebuild_fts5_refire` — second call appends entry to `refires` array with timestamp + before/after counts. (TDD: RED) | Same | Done: test FAILS | Depends: T1.1.2
- [ ] **T1.1.4** Write `test_rebuild_fts5_user_version_classification` — refire across user_version increment classified as "expected post-migration"; refire on same user_version classified as "defect refire". (TDD: RED) | Same | Done: test FAILS | Depends: T1.1.3
- [ ] **T1.1.5** Implement `rebuild_fts5(db_path) -> dict` in `plugins/pd/hooks/lib/semantic_memory/maintenance.py`: set `conn.isolation_level = None`, run integrity-check + rebuild + integrity-check inside `BEGIN IMMEDIATE` retry loop (max_attempts=2, backoff=0.05s on locked-DB), return diagnostic dict. (TDD: GREEN) | maintenance.py | Done: T1.1.1 + T1.1.2 + T1.1.3 + T1.1.4 all PASS | Depends: T1.1.4
- [ ] **T1.1.6** Implement diagnostic JSON read-modify-write at `~/.claude/pd/memory/.fts5-rebuild-diag.json`: first call writes initial dict with `refires: []`; subsequent calls read existing JSON, append refire entry, write back. (TDD: GREEN) | maintenance.py | Done: T1.1.3 PASS | Depends: T1.1.5
- [ ] **T1.1.7** Add `--rebuild-fts5` CLI subcommand to `maintenance.py` argparse: invokes `rebuild_fts5(db_path)`, prints `Rebuilt N rows in entries_fts.`, exits 0. (TDD: GREEN) | maintenance.py | Done: `python -m semantic_memory.maintenance --rebuild-fts5` runs end-to-end on a populated test DB | Depends: T1.1.6
- [ ] **T1.1.8** Add `check_fts5_integrity()` bash function to `plugins/pd/hooks/session-start.sh`: query entries.count and entries_fts.count via inline `python3 -c`; if entries > 0 AND fts5 == 0, run `--rebuild-fts5` subprocess and log `[memory] FTS5 empty; rebuilt N rows.` to stderr. Invoke from main session-start flow. (TDD: GREEN) | session-start.sh | Done: dropping entries_fts on a test DB then invoking session-start rebuilds it | Depends: T1.1.7
- [ ] **T1.1.9** Run all FR-2 tests: `pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py -k rebuild_fts5 -v`. Verify 4 tests pass. (TDD: VERIFY) | — | Done: 4 PASS, 0 FAIL | Depends: T1.1.8

### P1.2 — FR-3: Mid-session recall tracking

- [ ] **T1.2.1** Write `test_search_memory_increments_recall_count` — populate entry X, call `_process_search_memory` returning X, assert `recall_count` incremented by 1. (TDD: RED) | `plugins/pd/mcp/test_memory_server.py` | Done: test FAILS | Depends: —
- [ ] **T1.2.2** Write `test_search_memory_within_call_dedup` — fixture causes ranker to return same entry twice in one query; assert recall_count incremented exactly once (set-based dedup). (TDD: RED) | Same | Done: test FAILS | Depends: T1.2.1
- [ ] **T1.2.3** Write `test_search_memory_across_calls_increments_per_call` — call _process_search_memory twice with same query; assert recall_count == 2. (TDD: RED) | Same | Done: test FAILS | Depends: T1.2.2
- [ ] **T1.2.4** Write `test_search_memory_recall_failure_logs_warn_returns_entries` — monkeypatch `db.update_recall` to raise OperationalError; assert returned entries are still populated AND `[memory-server] update_recall failed:` warning emitted to stderr. (TDD: RED) | Same | Done: test FAILS | Depends: T1.2.3
- [ ] **T1.2.5** Modify `_process_search_memory` in `plugins/pd/mcp/memory_server.py`: after computing returned_entries, compute `returned_ids = list({e['id'] for e in returned_entries})`; call `db.update_recall(returned_ids, _iso_utc(now()))` if non-empty. (TDD: GREEN) | memory_server.py | Done: T1.2.1 + T1.2.2 + T1.2.3 PASS | Depends: T1.2.4
- [ ] **T1.2.6** Wrap update_recall call in try/except sqlite3.OperationalError; log `[memory-server] update_recall failed: {e}` to stderr; do NOT re-raise (NFR-1 best-effort). (TDD: GREEN) | memory_server.py | Done: T1.2.4 PASS | Depends: T1.2.5
- [ ] **T1.2.7** Write `test_search_memory_benchmark.py`: synthetic 1000-entry DB, run baseline (monkeypatch update_recall to no-op) + post-FR-3 (real); assert `delta_p50_absolute_ms < max(5, 0.05 * baseline_p50_ms)` per AC-3.6; print P95 informationally. (TDD: GREEN) | new file `plugins/pd/mcp/test_search_memory_benchmark.py` | Done: benchmark PASSES P50 bound | Depends: T1.2.6
- [ ] **T1.2.8** Run all FR-3 tests: `pytest plugins/pd/mcp/ -k search_memory -v`. Verify 4 unit + 1 benchmark pass. (TDD: VERIFY) | — | Done: 5 PASS | Depends: T1.2.7

### P1.3 — FR-5: source_project filter

- [ ] **T1.3.1** Write `test_record_influence_filters_cross_project` — insert entry with source_project='proj-A'; patch _project_root='proj-B' module state; call `_process_record_influence_by_content` with content that would substring-match; assert entry A's influence_count UNCHANGED. (TDD: RED) | `plugins/pd/mcp/test_memory_server.py` | Done: test FAILS | Depends: —
- [ ] **T1.3.2** Write `test_record_influence_same_project_passes` — same fixture but _project_root='proj-A'; assert influence_count incremented. (TDD: RED) | Same | Done: test FAILS | Depends: T1.3.1
- [ ] **T1.3.3** Write `test_record_influence_null_project_root_bypass_with_warn` — patch _project_root=None; assert filter bypassed (update applies) AND stderr contains `[memory] record_influence: no project context`. (TDD: RED) | Same (use capsys) | Done: test FAILS | Depends: T1.3.2
- [ ] **T1.3.4** Modify `_process_record_influence_by_content` in `plugins/pd/mcp/memory_server.py`: after fetching candidate entries, if `_project_root is not None`, filter `candidates = [c for c in candidates if c.get('source_project') == _project_root]`; apply BEFORE threshold-similarity comparison. (TDD: GREEN) | memory_server.py | Done: T1.3.1 + T1.3.2 PASS | Depends: T1.3.3
- [ ] **T1.3.5** Add null-`_project_root` bypass branch: if None, log `[memory] record_influence: no project context; skipping project filter` to stderr and skip the filter. (TDD: GREEN) | memory_server.py | Done: T1.3.3 PASS | Depends: T1.3.4
- [ ] **T1.3.6** Run all FR-5 tests: `pytest plugins/pd/mcp/ -k record_influence -v`. Verify 3 PASS. (TDD: VERIFY) | — | Done: 3 PASS | Depends: T1.3.5

### P1.4 — Stage 1 integration

- [ ] **T1.4.1** Run combined Stage 1 test suite: `pytest plugins/pd/hooks/lib/semantic_memory/ plugins/pd/mcp/ -v`. (VERIFY) | — | Done: all green; no regressions vs main | Depends: T1.1.9 + T1.2.8 + T1.3.6
- [ ] **T1.4.2** Run `validate.sh`. (VERIFY) | — | Done: 0 errors | Depends: T1.4.1
- [ ] **T1.4.3** Manual smoke test: copy `~/.claude/pd/memory/memory.db` to `/tmp/test.db`, drop entries_fts, run `PLUGIN_ROOT=... python3 -m semantic_memory.maintenance --rebuild-fts5 --db-path /tmp/test.db`, verify entries_fts repopulated AND `.fts5-rebuild-diag.json` written. (VERIFY) | — | Done: rebuild succeeded; diag JSON has all 8 fields | Depends: T1.4.2
- [ ] **T1.4.4** Commit Stage 1: `git add -A && git commit -m "pd(101): Stage 1 — FTS5 self-heal + recall tracking + project filter"`. (COMMIT) | — | Done: commit lands; HEAD on feature branch | Depends: T1.4.3

---

## Stage 2 — Influence Wiring + Lifecycle

### P2.1 — Sidecar + audit + ordering validator

- [ ] **T2.1.1** Write `test_append_influence_log_atomic` — spawn 10 subprocess threads each calling `append_influence_log` with a 1KB JSON record; assert all 10 lines present in file AND each line is valid JSON (no interleaving). (TDD: RED) | new `plugins/pd/hooks/lib/semantic_memory/test_influence_log.py` | Done: test FAILS | Depends: T1.4.4
- [ ] **T2.1.2** Write `test_append_influence_log_creates_parent_dir` — call with non-existent feature_path; assert dir created and file written. (TDD: RED) | Same | Done: test FAILS | Depends: T2.1.1
- [ ] **T2.1.3** Write `test_append_influence_log_handles_long_lines` — 5 KB JSON record; assert single uncorrupted line in output. (TDD: RED) | Same | Done: test FAILS | Depends: T2.1.2
- [ ] **T2.1.4** Implement `plugins/pd/hooks/lib/semantic_memory/influence_log.py` with `append_influence_log(feature_path, record)`: mkdir(parents=True, exist_ok=True), os.open with O_APPEND|O_CREAT, fcntl.flock(LOCK_EX), write JSON line, close (flock auto-releases). (TDD: GREEN) | influence_log.py (new) | Done: T2.1.1 + T2.1.2 + T2.1.3 PASS | Depends: T2.1.3
- [ ] **T2.1.5** Write `test_audit_basic` — mock sidecar with 5 lines + DB with 5 entries; invoke `audit.py --feature 101`; assert markdown table with 5 rows + summary. (TDD: RED) | new `plugins/pd/hooks/lib/semantic_memory/test_audit.py` | Done: test FAILS | Depends: T2.1.4
- [ ] **T2.1.6** Write `test_audit_cutover_filter` — sidecar with 3 pre-cutover SHAs + 5 post-cutover SHAs; `.fr1-cutover-sha` set; assert only 5 post-cutover counted. (TDD: RED) | Same | Done: test FAILS | Depends: T2.1.5
- [ ] **T2.1.7** Write `test_audit_source_project_filter` — DB has entries A:proj-A and A:proj-B same name different source_project; assert only current-project entry counted. (TDD: RED) | Same | Done: test FAILS | Depends: T2.1.6
- [ ] **T2.1.8** Write `test_audit_malformed_line_handling` — sidecar with 4 valid lines + 1 corrupt JSON; assert 4 entries counted + skip warning to stderr + summary reports `Skipped lines (malformed): 1`. (TDD: RED) | Same | Done: test FAILS | Depends: T2.1.7
- [ ] **T2.1.9** Write `test_audit_strict_exit_code` — fixture with 50% rate; invoke `audit.py --feature 101 --strict`; assert exit code 2. (TDD: RED) | Same | Done: test FAILS | Depends: T2.1.8
- [ ] **T2.1.10** Implement `plugins/pd/hooks/lib/semantic_memory/audit.py` with full CLI (`--feature`, `--db-path`, `--project-root` cwd-walk-up default, `--json`, `--strict`), sidecar parser (skip+warn on malformed), cutover-SHA filter via `git rev-list <cutover>..<feature-tip>`, source_project DB query filter, markdown/JSON output, exit codes 0/1/2. (TDD: GREEN) | audit.py (new) | Done: T2.1.5–T2.1.9 PASS | Depends: T2.1.9
- [ ] **T2.1.11** Write `test_check_block_ordering_basic` — synthetic md fixture with 14 properly-ordered markers (s1-s14, before Branch); assert exit 0. (TDD: RED) | new `plugins/pd/scripts/test_check_block_ordering.py` | Done: test FAILS | Depends: T2.1.10
- [ ] **T2.1.12** Write `test_check_block_ordering_fails_on_misorder` — fixture with marker AFTER Branch; assert exit 1 with "after Branch" error. (TDD: RED) | Same | Done: test FAILS | Depends: T2.1.11
- [ ] **T2.1.13** Write `test_check_block_ordering_count_mismatch` — fixture with 13 markers (missing s7); assert exit 1 with count error. (TDD: RED) | Same | Done: test FAILS | Depends: T2.1.12
- [ ] **T2.1.14** Implement `plugins/pd/scripts/check_block_ordering.py`: parse 4 command files, find `<!-- influence-tracking-site: s\d+ -->` markers, find `**Branch on` markers, assert each influence-marker line < next Branch line, assert 14 distinct s-ids in 2/2/3/7 distribution per file. Exit 0 pass, 1 fail. (TDD: GREEN) | check_block_ordering.py (new) | Done: T2.1.11 + T2.1.12 + T2.1.13 PASS | Depends: T2.1.13
- [ ] **T2.1.15** Add `docs/features/*/.influence-log.jsonl` to project-root `.gitignore`. (DOCS) | `.gitignore` | Done: `git check-ignore docs/features/test/.influence-log.jsonl` returns 0 | Depends: T2.1.14

### P2.2 — Restructure 14 prose blocks

- [ ] **T2.2.1** Capture FR-1 cutover SHA: `git rev-parse HEAD > docs/features/101-memory-flywheel/.fr1-cutover-sha` (one-line text file). (SETUP) | feature dir | Done: file exists, single line, 40-char SHA | Depends: T2.1.15
- [ ] **T2.2.2** Restructure s1 (specify.md spec-reviewer block, 1st): replace existing post-dispatch block with C-1 canonical template; insert `<!-- influence-tracking-site: s1 -->` marker; verify position before `**Branch on`. (GREEN) | `plugins/pd/commands/specify.md` | Done: marker present, block before Branch, contains "Influence recorded:" | Depends: T2.2.1
- [ ] **T2.2.3** Restructure s2 (specify.md phase-reviewer, 2nd). (GREEN) | Same | Done: marker s2 present | Depends: T2.2.2
- [ ] **T2.2.4** Restructure s3, s4 (design.md ×2). (GREEN) | `plugins/pd/commands/design.md` | Done: markers s3, s4 present; both before Branch | Depends: T2.2.3
- [ ] **T2.2.5** Restructure s5, s6, s7 (create-plan.md ×3). (GREEN) | `plugins/pd/commands/create-plan.md` | Done: markers s5, s6, s7 present; all before Branch | Depends: T2.2.4
- [ ] **T2.2.6** Restructure s8, s9 (implement.md test-deepener Phase A + B). (GREEN) | `plugins/pd/commands/implement.md` | Done: markers s8, s9 present | Depends: T2.2.5
- [ ] **T2.2.7** Restructure s10–s14 (implement.md remaining 5 sites). For each, read the dispatch's `subagent_type:` field to determine the role; substitute into canonical template. (GREEN) | Same | Done: markers s10–s14 present, 7 total in implement.md | Depends: T2.2.6
- [ ] **T2.2.8** Run `python plugins/pd/scripts/check_block_ordering.py`; assert exit 0. (VERIFY) | — | Done: stdout shows "OK: 14 blocks correctly positioned (2/2/3/7)" | Depends: T2.2.7
- [ ] **T2.2.9** Run `grep -c 'Influence recorded:' plugins/pd/commands/{specify,design,create-plan,implement}.md`; assert 2/2/3/7. (VERIFY) | — | Done: counts match | Depends: T2.2.8
- [ ] **T2.2.10** Add `python plugins/pd/scripts/check_block_ordering.py` invocation to `validate.sh` component-check loop. (DOCS) | `validate.sh` | Done: validate.sh runs the check; failure surfaces as validation failure | Depends: T2.2.9

### P2.3 — FR-4 confidence upgrade

- [ ] **T2.3.1** Write `test_recompute_confidence_observation_gate` — seed `confidence='low', observation_count=3, influence_count=0, recall_count=0`; assert `_recompute_confidence` returns `'medium'`. (TDD: RED) | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` | Done: test FAILS | Depends: T1.4.4
- [ ] **T2.3.2** Write `test_recompute_confidence_use_gate_with_floor` — seed `confidence='low', observation_count=0, influence_count=2, recall_count=3`; assert returns `'medium'`. (TDD: RED) | Same | Done: test FAILS | Depends: T2.3.1
- [ ] **T2.3.3** Write `test_recompute_confidence_recall_only_no_promotion` — seed `confidence='low', observation_count=0, influence_count=0, recall_count=10`; assert returns `None` (floor blocks). (TDD: RED) | Same | Done: test FAILS | Depends: T2.3.2
- [ ] **T2.3.4** Write `test_recompute_confidence_neither_gate_no_op` — seed `confidence='low', observation_count=2, influence_count=1, recall_count=2`; assert returns `None`. (TDD: RED) | Same | Done: test FAILS | Depends: T2.3.3
- [ ] **T2.3.5** Write `test_recompute_confidence_medium_to_high_obs` — seed `confidence='medium', observation_count=6`; assert returns `'high'`. (TDD: RED) | Same | Done: test FAILS | Depends: T2.3.4
- [ ] **T2.3.6** Write `test_recompute_confidence_medium_to_high_use` — seed `confidence='medium', observation_count=0, influence_count=4, recall_count=6`; assert returns `'high'`. (TDD: RED) | Same | Done: test FAILS | Depends: T2.3.5
- [ ] **T2.3.7** Write `test_recompute_confidence_high_idempotent` — seed `confidence='high'`; assert returns `None`. (TDD: RED) | Same | Done: test FAILS | Depends: T2.3.6
- [ ] **T2.3.8** Write `test_select_upgrade_candidates_query` — populate DB with 3 hot entries (obs >= 3, NOT stale per decay) + 2 stale entries; call `_select_upgrade_candidates`; assert only the 3 hot entries returned. (TDD: RED) | Same | Done: test FAILS | Depends: T2.3.7
- [ ] **T2.3.9** Write `test_upgrade_confidence_wrapper` — populate DB with mixed entries; call `upgrade_confidence(db, scan_limit=100)`; assert returns dict with non-empty `low_to_medium` list AND DB rows updated. (TDD: RED) | Same | Done: test FAILS | Depends: T2.3.8
- [ ] **T2.3.10** Write `test_batch_promote_basic` parallel to existing `test_batch_demote_basic`: seed 3 'low' entries; call `db.batch_promote(ids, 'medium', now_iso)`; assert all 3 confidence updated AND last_promoted_at populated; second call no-ops (idempotent). (TDD: RED) | `plugins/pd/hooks/lib/semantic_memory/test_database.py` | Done: test FAILS | Depends: T2.3.9
- [ ] **T2.3.11** Implement `_recompute_confidence(entry: dict) -> str | None` in `plugins/pd/hooks/lib/semantic_memory/maintenance.py`: read K_OBS = `_resolve_int_config('memory_promote_min_observations', 3)`; K_USE = `_resolve_int_config('memory_promote_use_signal', 5)`; K_OBS_HIGH = K_OBS*2; K_USE_HIGH = K_USE*2; apply OR-semantics with floor per spec FR-4. (TDD: GREEN) | maintenance.py | Done: T2.3.1–T2.3.7 PASS | Depends: T2.3.10
- [ ] **T2.3.12** Implement `_select_upgrade_candidates(db, scan_limit) -> list[dict]` SQL helper in maintenance.py: SELECT id, confidence, observation_count, influence_count, recall_count FROM entries WHERE confidence != 'high' AND (observation_count >= ? OR (influence_count >= 1 AND influence_count + recall_count >= ?)) LIMIT ?. (TDD: GREEN) | maintenance.py | Done: T2.3.8 PASS | Depends: T2.3.11
- [ ] **T2.3.13** Implement `upgrade_confidence(db, scan_limit) -> dict` wrapper: iterate `_select_upgrade_candidates`, call `_recompute_confidence` per row, collect upgrades, call `db.batch_promote(ids, new_tier, now_iso)`, return summary dict. (TDD: GREEN) | maintenance.py | Done: T2.3.9 PASS | Depends: T2.3.12
- [ ] **T2.3.14** Implement `db.batch_promote(ids, new_confidence, now_iso)` in `plugins/pd/hooks/lib/semantic_memory/database.py` mirroring `batch_demote` shape: `UPDATE entries SET confidence=?, last_promoted_at=? WHERE id IN (?,...) AND confidence != ?` (idempotency guard). (TDD: GREEN) | database.py | Done: T2.3.10 PASS | Depends: T2.3.13
- [ ] **T2.3.15** Wire `upgrade_confidence(db, scan_limit)` into `run_memory_decay()` AFTER `decay_confidence()` returns. Add the result to the diagnostic dict under `upgraded`. (TDD: GREEN) | maintenance.py | Done: end-to-end run shows both decay AND upgrade in diagnostic | Depends: T2.3.14
- [ ] **T2.3.16** Wire `_recompute_confidence` into `merge_duplicate()` in database.py: after `observation_count++`, call `_recompute_confidence` on the merged entry; if returns non-None, UPDATE confidence inline. (TDD: GREEN) | database.py | Done: integration test (merge two duplicates that cross K_OBS threshold; assert upgrade applied) PASS | Depends: T2.3.15
- [ ] **T2.3.17** Document `memory_promote_use_signal` (default 5) in pd config-key reference. K_OBS_HIGH and K_USE_HIGH NOT separately documented (auto-derived). (DOCS) | `plugins/pd/references/memory-config.md` (or equivalent — find the right file via grep on existing config keys) | Done: new key documented with default + behavior | Depends: T2.3.16
- [ ] **T2.3.18** Run all FR-4 tests: `pytest plugins/pd/hooks/lib/semantic_memory/ -k 'recompute_confidence or upgrade_candidates or batch_promote' -v`. Verify ≥10 PASS. (TDD: VERIFY) | — | Done: all PASS | Depends: T2.3.17

### P2.4 — Stage 2 integration

- [ ] **T2.4.1** Run combined Stage 2 test suite: full pytest run on changed modules. (VERIFY) | — | Done: green | Depends: T2.2.10 + T2.3.18
- [ ] **T2.4.2** Run `python -m semantic_memory.audit --feature 101` (no --strict; expect output even if rate < 80% pre-cutover). (VERIFY) | — | Done: command produces a markdown table; summary line printed | Depends: T2.4.1
- [ ] **T2.4.3** Run `validate.sh`. (VERIFY) | — | Done: 0 errors; check_block_ordering passes | Depends: T2.4.2
- [ ] **T2.4.4** Commit Stage 2: `git add -A && git commit -m "pd(101): Stage 2 — Influence wiring (14 sites) + confidence upgrade"`. (COMMIT) | — | Done: commit lands | Depends: T2.4.3

---

## Stage 3 — Adoption Trigger

### P3.1 — Retrospecting Step 4c.1

- [ ] **T3.1.1** Write `test_retrospecting_promote_trigger_zero_qualifying_silent` — bash test sourcing skill prose; mock enumerate to return `count=0`; assert no AskUserQuestion emitted, no skill chained. (TDD: RED) | new `plugins/pd/skills/retrospecting/test_promote_trigger.sh` | Done: test FAILS (Step 4c.1 not yet inserted) | Depends: T2.4.4
- [ ] **T3.1.2** Write `test_retrospecting_promote_trigger_with_qualifying_emits_question` — mock enumerate `count=2`, non-YOLO; assert AskUserQuestion text "qualify for promotion" present. (TDD: RED) | Same | Done: test FAILS | Depends: T3.1.1
- [ ] **T3.1.3** Write `test_retrospecting_promote_trigger_yolo_chains_skill` — `[YOLO_MODE]` arg + `count=2`; assert `Skill({skill: "pd:promoting-patterns"})` invocation, no AskUserQuestion. (TDD: RED) | Same | Done: test FAILS | Depends: T3.1.2
- [ ] **T3.1.4** Write `test_retrospecting_promote_trigger_subprocess_failure_isolated` — enumerate subprocess returns non-zero; assert log warn + retro continues. (TDD: RED) | Same | Done: test FAILS | Depends: T3.1.3
- [ ] **T3.1.5** Insert Step 4c.1 prose into `plugins/pd/skills/retrospecting/SKILL.md` per design C-10 template: subprocess `pattern_promotion enumerate --json`, count check, YOLO branch (auto-Skill chain on `[YOLO_MODE]` token), non-YOLO branch (AskUserQuestion), error isolation. (GREEN) | retrospecting/SKILL.md | Done: T3.1.1–T3.1.4 PASS | Depends: T3.1.4
- [ ] **T3.1.6** Verify YOLO detection mechanism: `grep -E '\[YOLO_MODE\]' plugins/pd/skills/retrospecting/SKILL.md`; assert match within Step 4c.1 prose. (VERIFY) | — | Done: 1 match in 4c.1 region | Depends: T3.1.5
- [ ] **T3.1.7** Run all FR-6 tests: `bash plugins/pd/skills/retrospecting/test_promote_trigger.sh`. (TDD: VERIFY) | — | Done: 4 PASS | Depends: T3.1.6

### P3.2 — Dogfood + final validation

- [ ] **T3.2.1** Run final SC-1 audit: `python -m semantic_memory.audit --feature 101 --strict`. Verify rate ≥ 80% on post-cutover dispatches OR diagnose via `mcp_status` breakdown. (VERIFY) | — | Done: exit 0 (rate ≥ 80%) OR diagnosis recorded for retro | Depends: T2.4.4 + all reviewer dispatches in implement phase
- [ ] **T3.2.2** Smoke-test FR-6 trigger: manually invoke retrospecting Step 4c.1 logic against a deliberately seeded test KB (≥1 qualifying entry); verify trigger fires + AskUserQuestion / YOLO chain works. (VERIFY) | — | Done: trigger demonstrably fires | Depends: T3.2.1
- [ ] **T3.2.3** Run `validate.sh` end-to-end. (VERIFY) | — | Done: 0 errors | Depends: T3.2.2
- [ ] **T3.2.4** Commit Stage 3: `git add -A && git commit -m "pd(101): Stage 3 — Promote-pattern adoption trigger"`. (COMMIT) | — | Done: commit lands | Depends: T3.2.3

---

## Parallel Execution Plan

Per `.worktreeinclude` worktree-parallel pattern:

**Within Stage 1 (after T1.4.4 prerequisites are clear, but conceptually
parallelizable since each P1.x is a different file):**
- Worktree 1: P1.1 (FR-2)
- Worktree 2: P1.2 (FR-3)
- Worktree 3: P1.3 (FR-5)
- Then sequentially: T1.4.1–T1.4.4

**Within Stage 2:**
- After P2.1 (helpers) completes, P2.2 (prose) and P2.3 (FR-4) can
  parallelize across 2 worktrees.
- Then sequentially: P2.4 integration.

**Stage 3:** sequential single-file change.

## Acceptance Criteria → Task Mapping

| AC | Task(s) verifying it |
|----|----------------------|
| AC-1.1 | T2.2.2–T2.2.7 (all 14 sites unconditional) + T2.2.9 (grep verification) |
| AC-1.2 | T2.1.11–T2.1.14, T2.2.8 (check_block_ordering passes) |
| AC-1.3 | T2.2.9 (grep count 2/2/3/7) |
| AC-1.4 | T2.1.5–T2.1.10, T2.4.2 (audit runs end-to-end) |
| AC-1.5 | T3.2.1 (final SC-1 audit ≥ 80%) |
| AC-1.6 | T1.2.7 (microbenchmark fixture) — bound at < 5ms P95 baseline (synthetic; FR-1 reuses existing short-circuit) |
| AC-2.1 | T1.1.5–T1.1.7 (--rebuild-fts5 CLI) |
| AC-2.2 | T1.1.8 (session-start integrity check) |
| AC-2.3 | T1.1.5–T1.1.6 (8-field diagnostic JSON) |
| AC-2.4 | T1.1.4 (refire stronger warning); T1.1.5 (user_version classification) |
| AC-2.5 | T1.1.1–T1.1.4 (integration tests) |
| AC-2.6 | T1.1.8 (stdlib-only constraint) |
| AC-3.1 | T1.2.5 (update_recall call site) |
| AC-3.2 | T1.2.2 (within-call dedup) |
| AC-3.3 | T1.2.3 (across-call increment) |
| AC-3.4 | T1.2.4, T1.2.6 (UPDATE failure handling) |
| AC-3.5 | T1.2.1 (integration) |
| AC-3.6 | T1.2.7 (synthetic benchmark) |
| AC-4.1 | T2.3.11 (_recompute_confidence) |
| AC-4.2 | T2.3.15, T2.3.16 (call sites) |
| AC-4.3 | T2.3.17 (config key documented) |
| AC-4.4 | T2.3.1–T2.3.7 (7 seed cases) |
| AC-4.5 | (config override test — added inline within T2.3.18 verification) |
| AC-5.1 | T1.3.4 (filter clause) |
| AC-5.2 | T1.3.1 (cross-project test) |
| AC-5.3 | T1.3.5 (null-project bypass + warn) |
| AC-5.4 | T1.3.1 |
| AC-5.5 | T1.3.2 |
| AC-5.6 | T1.3.3 |
| AC-6.1 | T3.1.5 (Step 4c.1 inserted) |
| AC-6.2 | T3.1.5 (reuses memory_promote_min_observations) |
| AC-6.3 | T3.1.2 (AskUserQuestion options) |
| AC-6.4 | T3.1.3 (YOLO branch) + T3.1.6 (mechanism verification) |
| AC-6.5 | T3.1.1 (zero-qualifying silent) |
| AC-6.6 | T3.1.4 (subprocess error isolation) |
| AC-6.7 | T3.2.2 (dogfood) |

Total tasks: **63**. Estimated total time: **~9.5 hours** with the
parallelism plan above.
