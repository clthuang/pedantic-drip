# Plan: 133-doctor-check-retirement

Contract chain: spec.md (FR133-1..4, SC1-SC8) → design.md (D1-D9), both as absorbed through their full review loops (11 blockers / 8 rounds; see .review-history.md). Serial ×4; every task ends suite-green with a confined diff. Baseline at dispatch: recorded in tasks.md from the live develop merge-base figure.

## Task order & rationale

1. **Task 1 — Carry-forwards (D4 + D5).** Additive-only, zero coupling to the retirement: reconcile_check's three-layer workspace threading (additive-optional default-None at every layer; the two untouched drift callers stay byte-identical) and export_entities_json's workspace filter (DB method only; MCP tool unchanged). First because it is the smallest independently-verifiable slice and its SC4 tests pin behavior the later big diff must not disturb.
2. **Task 2 — check_v2_cutover_window (D3).** The additive marker check + its four-state test file + CHECK_ORDER append. `EXPECTED_CHECK_COUNT` and test_doctor.py membership bump 19→20 TEMPORARILY (each membership change is code+test coupled per H3; the final 10 lands at task 3). Lazy in-function import of the writer's path fns; NOT in `_ENTITY_DB_CHECKS`; tmp-marker-dir isolation in every test.
3. **Task 3 — The retirement (D1 + D2 + D7 + D8).** The big atomic sweep: ten checks + eleven fix fns + three production helpers + orphaned test helpers + import-block entries + CHECK_ORDER/_ENTITY_DB_CHECKS pruning + the FULL test-surface partition (every top-level class AND def classified; the two SQL count-guard floors re-derived; the name-trap class deleted) + count sweep 20→10 across code+docs (D7's widened gate grep) + SC3's cross-package sweeps (database.py:5361 m15 docstring + :7942-7943 comment, check_severity_vocab.py docstrings, test_meta_projection.py:282, test_cleanup_suffix_parsers.py:202, test_audit_writes.py allowlist 4→2 + TD-11/_fix_meta_json_via_mcp/_DRIFT_* dispositions, test_fix_actions.py/test_fixer.py deletions + survivor-fix ordering regression) + SC1's hermetic healthy-workspace fixture + referential-fault control. Ends with SC3's full-token greps (all retired names exit 1) and SC7's reconciliation grep.
4. **Task 4 — Ships-dark re-scope (D6).** test_schema_v2.py premise-text rewrite + class rename; SC8's pinned needle gate. Last because it is independent and tiny — a clean tail.

## Risks

- Task 3's size is intrinsic (H3: the content-equality pin makes partial retirement red) — the partition contract + D8's named class/def lists bound it; the implementer STOPS on any surface not in D8/D9 rather than widening.
- The two SQL count-guard floors are re-derived EMPIRICALLY at task 3 (design pins direction, not the exact number — the honest form).
- SC6 needs NO edit: the two named chain-replay tests re-run green unedited (the m15 sweep is docstring-only).
- Live DB untouched throughout; the marker check reads real ~/.claude/pd only in production (all tests isolate PD_REBUILD_MARKER_DIR).

## Gates

Per task: full standard-scope suite + confined-diff check vs the task's file list. Feature end (task 4): hooks 67/67 + validate 0 errors + SC7's widened reconciliation grep + diff-vs-develop ⊆ D9.
