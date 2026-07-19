# Plan: 133-doctor-check-retirement

Contract chain: spec.md (FR133-1..4, SC1-SC8) → design.md (D1-D9), both as absorbed through their full review loops (11 blockers / 8 rounds; see .review-history.md). Serial ×4; every task ends suite-green with a confined diff measured INCREMENTALLY vs the previous task's tip (plan-i1 W1: cumulative measurement misfires for double-owned files). Baseline: pinned in tasks.md (3947/3/0 at the develop merge-base; re-derived live at each dispatch) with per-task test-count deltas reported per-file (plan-i1 W2: for a deletion-heavy feature, pass-count accounting is what distinguishes green from silently-uncollected).

## Task order & rationale

1. **Task 1 — Carry-forwards (D4 + D5).** Additive-only, zero coupling to the retirement: reconcile_check's three-layer workspace threading (additive-optional default-None at every layer; the two untouched drift callers stay byte-identical) and export_entities_json's workspace filter (DB method only; MCP tool unchanged). First because it is the smallest independently-verifiable slice and its SC4 tests pin behavior the later big diff must not disturb.
2. **Task 2 — check_v2_cutover_window (D3).** The additive marker check + its four-state test file + CHECK_ORDER append. `EXPECTED_CHECK_COUNT` and test_doctor.py membership bump 19→20 TEMPORARILY. Add-before-retire is the deliberate optimum (plan-i1 S1): with the marker check already present, task 3's H3-atomic count/doc sweep reconciles straight to the FINAL 10 in one shot — retire-first would churn docs through a never-shipped 9 or split the atomic sweep. Lazy in-function import of the writer's path fns; NOT in `_ENTITY_DB_CHECKS`; tmp-marker-dir isolation in every test.
3. **Task 3 — The retirement (D1 + D2 + D7 + D8).** The big atomic sweep: ten checks + eleven fix fns + three production helpers + orphaned test helpers + import-block entries + CHECK_ORDER/_ENTITY_DB_CHECKS pruning + the FULL test-surface partition (every top-level class AND def classified; the two SQL count-guard floors re-derived; the name-trap class deleted) + count sweep 20→10 across code+docs (D7's widened gate grep) + SC3's cross-package sweeps (database.py:5361 m15 docstring + :7942-7943 comment, check_severity_vocab.py docstrings, test_meta_projection.py:282, test_cleanup_suffix_parsers.py:202, test_audit_writes.py allowlist 4→2 + TD-11/_fix_meta_json_via_mcp/_DRIFT_* dispositions, test_fix_actions.py/test_fixer.py deletions + survivor-fix ordering regression) + SC1's hermetic healthy-workspace fixture + referential-fault control. Ends with SC3's full-token greps (all retired names exit 1) and SC7's reconciliation grep.
4. **Task 4 — Ships-dark re-scope (D6).** test_schema_v2.py premise-text rewrite + class rename; SC8's pinned needle gate. Last because it is independent and tiny — a clean tail.

## Risks

- Task 3's size is intrinsic (H3: the content-equality pin makes partial retirement red) — the partition contract + D8's named class/def lists bound it; the implementer STOPS on any surface not in D8/D9 rather than widening.
- The two SQL count-guard floors are re-derived EMPIRICALLY at task 3 (design pins direction, not the exact number — the honest form).
- SC6 needs NO edit: the two named chain-replay tests re-run green unedited (the m15 sweep is docstring-only).
- Live DB untouched throughout; the marker check reads real ~/.claude/pd only in production (all tests isolate PD_REBUILD_MARKER_DIR).

## Rollback

Each task is an independently-revertible commit set (no data/schema changes anywhere in the feature; the only production-behavior deltas are additive-optional params + the additive check). Reverting task N alone leaves tasks <N shippable; the feature-level story is D9's single-branch revert.

## Gates

Per task: full standard-scope suite + confined-diff check vs the task's file list. Feature end (task 4): hooks 67/67 + validate 0 errors + SC7's widened reconciliation grep (deliberate RE-RUN of task 3's gate — task 4's rename edit could reintroduce a count-shaped string; re-verification, not duplicate ownership — tasks-i2 S1) + diff-vs-develop ⊆ D9.
