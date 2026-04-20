# Feature 088 Retrospective — Features 082 & 084 QA Hardening

Completed 2026-04-19. Full mode. Branch: `feature/088-082-084-qa-hardening`. 12 bundles, 47 ACs, 43 findings closed (14 HIGH, 22 MED, 7 LOW), +41 new tests (baseline 416 → 457).

## Aims

Feature 088 set out to close the full set of 43 NEW findings surfaced by 8 parallel adversarial reviewers on completed features 082 (recall-tracking-and-confidence) and 084 (structured-execution-data) beyond the already-known post-release QA backlog (#00075–#00084). The scope spanned 9 subsystems: session-start hook security, semantic-memory correctness, entity-registry migration safety, MCP tool cross-project isolation, transaction safety for dual-write, analytics pairing correctness, code quality cleanup, test hardening, spec patches, skill-layer fix, and retroactive retro for 084.

Explicit non-goals: no new features, no backward-compatibility shims, no rewrites — only surgical hardening.

## Outcomes

**Delivered** (all 12 bundles, ordered per TD-I dependency graph):

- **Bundle A — Shared config utility** (SHA `20aa2e4`): extracted `_warn_and_default` + `_resolve_int_config` from `maintenance.py`/`refresh.py` into `_config_utils.py`. Dropped 77 LOC across the two callers via `functools.partial` binding per-caller prefix and clamp-policy.
- **Bundle B — Correctness fixes** (`5259b87`): unified timestamp format via `_iso_utc` helper (eliminated mixed `isoformat()` + strftime), added `_DAYS_MIN`/`_DAYS_MAX` constants + overflow guard, removed dead `now_iso` parameter, added `scan_limit` with LIMIT clause and yield-based streaming.
- **Bundle G — Input validation** (`aa75ec3`): DEFAULTS expansion for all `memory_decay_*` keys, strict boolean coercion rejecting capital `'False'`/`'True'`, unknown-key warning pass, foreign-uid project_root refusal.
- **Bundle I — Skill-layer fix** (`21facbc`): `workflow-transitions/SKILL.md` now resolves `project_id` server-side via `.meta.json` → `get_entity()` → None fallback before `record_backward_event`. MUST land before D.3 (ordering constraint satisfied).
- **Bundle D — Cross-project isolation + migration hardening** (`c6f29bf`): `query_phase_analytics` defaults to current project (explicit `"*"` opt-in required), partial UNIQUE index on `source='backfill'` rows, `INSERT OR IGNORE` backfill, `PHASE_EVENTS_COLS` explicit column list replacing `SELECT *`, schema_version re-check inside BEGIN IMMEDIATE, `record_backward_event` server-side validation + `_make_error` shape.
- **Bundle E — Transaction safety** (`f1dcdff`): `insert_phase_event` moved OUTSIDE main transaction in both `_process_transition_phase` and `_process_complete_phase` (ordering swap for complete_phase), `phase_events_write_failed: true` response flag, 10KB `reviewer_notes` guard at both MCP entry-point AND DB layer, single-parse JSON with malformed-JSON rejection, transaction-participation pin test for #00134 verified-false-alarm.
- **Bundle F — Analytics pairing + filter-then-limit** (`4c00d4f`): `_compute_durations` rewritten to iterate union of started/completed keys with `zip_longest` for imbalanced pairs, `_ANALYTICS_EVENT_SCAN_LIMIT=500` module-level constant, iteration_summary filter-then-limit, module-level imports (`defaultdict`, `datetime`, `zip_longest`).
- **Bundle C — Session-start security** (`55f7a77`): 6 `python3 -c` blocks converted from double-quoted (bash-expandable) to single-quoted with `sys.argv`, symlink-safe log open via `O_NOFOLLOW` + `fchmod`, PATH pinning + venv hard-fail + `gtimeout`/`timeout`/Python-subprocess-timeout fallback.
- **Bundle H — Test hardening** (`c7da544`): autouse fixture for `_db` globals, 25+ `db._conn` call sites migrated to `_for_testing` public API, `NOW` → `_TEST_EPOCH` rename, 14 new tests spanning concurrency, integration, boundary, error-path, and CHECK-constraint negative tests.
- **Bundle L — Reconcile drift detection** (`fa90c50`): `_detect_phase_events_drift` helper + integration into `_process_reconcile_check` / `_process_reconcile_apply` as sibling JSON key (additive, preserves frozen `WorkflowDriftResult` dataclass). `reconcile_apply` warns but does NOT auto-insert (analytics is additive).
- **Bundle J — Spec patches** (`9872eee` for J.1; `474df3f` for J.2/J.3): 082 spec `## Amendments (2026-04-19 — feature 088)` section with 3 amendments (AC-10 skipped_floor value, FR-2 NULL-branch text, AC-11 capsys assertion requirement), docstring I-3 correction, EQP regeneration (`scanned=10000 skipped_import=0 elapsed_ms=34`).
- **Bundle K — Process backfill** (`9872eee`): retroactive 084 `retro.md` (85 lines, AORTA format, #00134 verified-false-alarm documented), backlog #00138 entry for deferred #00116/#00136 sub-items.

**Not delivered** (explicitly deferred to #00138): sub-items from #00116 (feature 082 test gaps) and #00136 (feature 084 test gaps) beyond the minimums in FR-10.7/FR-10.10. None are correctness blockers — all are mutation-resistance improvements to be addressed in future test-hardening features.

## Reflections

**What went well:**

- **Adversarial parallel review is 10×-productive for QA.** Dispatching 8 parallel reviewers (2 per class × 2 features) surfaced 43 distinct findings in ~15 minutes of wall time — individual review passes would likely have caught 5–10 of these across multiple sequential rounds. The cost was one large context hit and one orchestration session.
- **Feature 086 pattern replicated cleanly.** Modeling this hardening bundle after feature 086 (the QA-round-2 predecessor) gave us a ready-made structure: bundled fixes, explicit file-change map, AC→test mapping, TD notes for implementation choices, and staged commits per bundle. The design phase completed in 4 iterations (vs. 3–5 typical) because the template was known-good.
- **Verified-false-alarm pattern.** Two findings (#00090 from feature 085, #00134 from feature 084) were confirmed as already-mitigated during investigation. Feature 086 coined the pattern ("verified-already-fixed"); feature 088 extended it to #00134 (`insert_phase_event` unconditional commit — actually already guarded by `self._in_transaction`). Capturing these as pin tests preserves the verification work without wasted code changes.
- **Ordering constraint caught early.** The I-before-D.3 ordering constraint (SKILL.md must stop passing `project_id=` before MCP removes the parameter) was surfaced by plan-reviewer iter 1 and explicitly encoded in TD-I + the task dependency table. No mid-implementation breakage.
- **Upstream quality drives implementation correctness.** Security-reviewer feedback, code-quality fixes, and test coverage all passed on iteration 1 or 2 per bundle because spec/design/plan phases were exhaustive. All 12 bundle implementer dispatches succeeded without needing review rework.

**What went wrong:**

- **Four review-cycle blockers on spec iteration 1.** Spec-reviewer found 7 blockers in iter 1: finding #00096 was silently split between FR-3.2 and FR-10.1 without cross-reference; AC-15 "logs an error" was untestable; AC-5 simulated concurrency sequentially; truthiness-coercion half of #00096 had no AC; NFR-2 baseline capture was underspecified; FR-9 patch governance was unstated; FR-2.4 `MAY` created a defense-in-depth gap. All were fixable in iter 2, but the triage quality of the initial spec was below bar.
- **Design-reviewer iter 1 caught three material bugs in sketches.** Bundle E.2 referenced `self._conn.in_transaction` (pysqlite3 Connection attribute) when the codebase uses `self._in_transaction` (instance attribute); Bundle D.4 changed `record_backward_event` parameter names (`phase`/`backward_target` vs actual `source_phase`/`target_phase`); Bundle C.1 targeted `python3 <<EOF` heredocs that don't exist (actual vulnerability is `python3 -c`). All fixed in iter 2. These would have caused implementation failures if shipped to agents.
- **Plan-reviewer iter 1 caught silent scope drift.** Four plan blockers: Bundle D.1 unintentionally renamed `feature_type_id` → `type_id` (spec didn't mandate); Bundle A signature mismatch (old vs new); Bundle C dependency table said `0` when C.2 modifies shared files; AC-38 (FR-10.5) had no task.
- **Bundle L initial sketch referenced wrong data structures.** Design iter 2 had `reconcile_check` building a plain dict `report` and appending `report['phase_events_drift']` — but actual code uses a frozen `WorkflowDriftResult` dataclass. Design iter 3 corrected to add drift as a sibling top-level JSON key. This is the same class of bug as the `in_transaction` attribute mix-up — specification referencing imagined APIs rather than reading the actual codebase.
- **Session-start security vulnerability pattern identification was wrong in iter 1.** The design referenced `python3 <<EOF` heredoc patterns that don't exist in the file. The actual pattern (six `python3 -c "..."` blocks with bash-variable interpolation inside the double-quoted Python source) is subtly different — and the AC-1 grep would have passed trivially pre-fix if not for iter-2 correction. Better upfront grep-verification of the vulnerable surface would have caught this.

**Unexpected discoveries:**

- **Drive-by `query_phase_events` limit=0 clamp fix.** Bundle D's implementer found that `min(max(limit, 1), 500)` silently bumps `limit=0` to 1, breaking a pre-existing test. Fixed inline per `leave-ground-tidier` memory. Reduced overall project-test regression count.
- **45 pre-existing hook test failures surface during Bundle E.** Investigation showed these are pre-existing `source_hash` schema failures from prior bundles (unrelated to 088's scope). Documented in Bundle E report; explicitly out of scope.
- **Deferred sub-items require explicit backlog entry at spec time.** Plan-reviewer correctly flagged that TD-6's "optional per project judgment" language allowed silent scope reduction. Bundle K's #00138 entry now pre-commits deferred sub-items to backlog before implement starts.

## Tune (What to change)

These corrections are encoded into the knowledge bank so future features avoid the same pitfalls.

- **Anti-pattern: specs that reference imagined APIs.** When writing a design sketch that calls into existing code, ALWAYS verify the function signature and return shape by reading the actual source. Do not assume names, parameter shapes, or data-structure types. Three separate iter-1 blockers (E.2 `self._conn.in_transaction`, D.4 param names, L.1 plain dict vs frozen dataclass) traced to this root cause.
- **Anti-pattern: grep-verifiable ACs that pass trivially pre-fix.** When an AC uses `grep` as its verification method, confirm the baseline (pre-fix) grep count. AC-1 (`grep -nE 'python3 <<EOF'` returns 0) would have passed before any code change because the vulnerable pattern was not heredocs. Grep ACs must include both a negative baseline and a positive target.
- **Anti-pattern: "MAY" language in hardening specs.** FR-2.4 initially allowed "migration 10 MAY add CHECK constraint — optional — entry-point check is authoritative." The optionality created a defense-in-depth gap: a caller bypassing the MCP tool and calling `insert_phase_event` directly would skip the size check. Hardening specs should not use MAY — either require defense at both layers or explicitly document that the second layer is accepted risk.
- **Anti-pattern: split findings without explicit cross-reference.** Finding #00096 had two distinct defects (OverflowError + bool coercion). Spec iter 1 split them between FR-3.2 and FR-10.1 but did not cross-reference, so AC-11 alone did not cover #00096's full scope. When splitting findings across FRs, every FR that addresses a sub-issue must explicitly note the parent finding and which sub-issue it covers.
- **Heuristic: 8-parallel adversarial review beats 4-sequential.** For post-release QA on completed features, dispatch reviewers in parallel across security/code-quality/implementation/test-depth dimensions. Two reviewers per class (one per feature under review) with explicit "DO NOT resurface these known findings" lists produced 43 NEW findings in ~15 minutes.
- **Heuristic: verified-false-alarm is a valid outcome.** When a finding investigates an existing guard that already works, document the verification and add a pin test rather than making a no-op change. Feature 086's #00090 and feature 088's #00134 both fit this pattern. The pin test prevents future regression without inflating the diff.
- **Heuristic: bundle dependency graphs are load-bearing.** When three bundles touch the same file (e.g., A/B/G on `maintenance.py`), sequential landing is required — parallel worktree dispatch would conflict. The plan MUST state this explicitly in the dependency table; TD-I was the correct format.
- **Heuristic: ordering constraints between bundles are worth an explicit call-out.** I-before-D.3 was flagged early because SKILL.md must stop passing `project_id=` before MCP removes the parameter. Without explicit ordering, a naive implementer could have broken workflow-transitions for one commit cycle.

## Adopt (What to keep doing)

- **Adversarial parallel review for post-release QA.** 8 reviewers × ~15 min surfaced more findings than would a week of sequential review. Will remain the default approach for hardening features after any mode=full feature ships.
- **Model after prior hardening features.** Feature 086 provided the template that made 088 efficient. Future QA-round features should explicitly reference the chain (088 → 086 → 085 post-release) to inherit the pattern.
- **Bundle design with explicit file-change map.** The `File Change Map` table in design.md made dependency conflicts visible before implementation. Keep this as a mandatory design artifact for multi-subsystem features.
- **AC→test mapping table.** The 1:1 table at the end of design.md caught AC-38 orphaning in plan-review and made test coverage audit trivial. Keep as standard.
- **Verified-false-alarm pattern in retros.** Document findings that investigation confirms as already-handled. Future debuggers reading the KB see that the pattern was considered and rejected with evidence.
- **Spec patch via Amendments section (not in-place edits).** Preserves historical spec text, makes git blame useful, surfaces post-release corrections without rewriting shipped docs. Used for 082 spec patches; keep as standard for all retrospective spec corrections.
- **TD notes resolving every non-trivial implementation choice.** 10 TDs (TD-A through TD-J) in design.md pre-answered every reviewer question about implementation approach. Reduced iter-1 review surface significantly.
- **Dual-write OUTSIDE transaction commit boundary.** When adding analytics/audit writes, keep the primary write in its own transaction, commit, then fire analytics in a separate try/except with a `*_write_failed: true` response flag. Never place additive analytics inside the main commit — an analytics failure will silently roll back the primary write.
- **Column-explicit SELECT in runtime queries.** The `SELECT *` regression in 084 (caught again in 088 as finding #00121) is a recurring anti-pattern. Use a module-level `*_COLS` constant imported at call sites. Matches 085's pattern.
- **`_check_db_available()` as first statement of every new MCP handler.** Consistency with existing handlers produces consistent degraded-mode response shapes across the MCP surface.

## Summary Metrics

- **Total wall-clock:** ~11 hours (feature 088 start 2026-04-19 07:54 → finish complete ~17:30).
- **Phases:** spec (3 iter), design (4 iter), plan (2 iter), tasks, implement (12 bundles), finish.
- **Total reviewer iterations:** 14 across all phases.
- **New tests:** +41 (416 → 457 in NFR-1 suite); +2 in test-hooks.sh (103 → 106).
- **Total files touched:** 16 across `plugins/pd/hooks/`, `plugins/pd/mcp/`, `plugins/pd/skills/`, `docs/features/082,084,088/`, `docs/backlog.md`, `agent_sandbox/`.
- **LOC delta:** +~1,400 LOC net (majority in new tests + retro.md + spec/design/plan/tasks artifacts), -100 LOC via shared helper extraction.
- **Findings closed:** 43 (14 HIGH / 22 MED / 7 LOW). Verified-false-alarm: 1 (#00134).
- **Findings deferred:** 24 sub-items to backlog #00138 (all low-priority mutation-resistance tests).

## Knowledge Bank Entries Captured

Will be stored via `/pd:remember` invocations (or semantic_memory.writer CLI) by the retrospecting skill that dispatches this retro. Candidate entries:

1. **Anti-pattern**: Spec references imagined APIs — verify function signatures and data shapes before writing design sketches.
2. **Anti-pattern**: Grep-verifiable ACs that pass trivially pre-fix — include positive and negative baseline.
3. **Anti-pattern**: MAY language in hardening specs creates defense-in-depth gaps.
4. **Anti-pattern**: Split findings across FRs without cross-reference.
5. **Heuristic**: 8-parallel adversarial review is 10×-productive vs. sequential.
6. **Heuristic**: Verified-false-alarm is a valid outcome — add pin test, document in retro.
7. **Heuristic**: Bundle dependency graphs are load-bearing; parallel dispatch requires file-isolation verification.
8. **Heuristic**: Ordering constraints between bundles (I-before-D.3 pattern) must be explicit in plan.
9. **Pattern**: Spec patch via Amendments section preserves historical auditability.
10. **Pattern**: Dual-write outside primary transaction commit boundary; `*_write_failed: true` response flag; never place analytics inside main commit.
