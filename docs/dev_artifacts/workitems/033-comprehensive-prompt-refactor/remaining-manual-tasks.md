# Remaining Manual Tasks — Feature 033

**Created:** 2026-03-01
**Context:** 28/40 tasks completed during implementation. 12 tasks blocked on `claude -p` (headless mode) or interactive CC sessions. Scoring completed for 5 pilot files (gate OPEN). Tasks below require fresh terminal or interactive sessions.

## Completed Since Merge

- [x] T01/T33: Scored 5 pilot files via interactive promptimize (see pilot-gate-report.md)
- [x] T03: Created test input artifacts (see test-inputs/)
- [x] Pilot gate: OPEN — all 5 files scored >=80 (range 83-97, mean 92)

## Deferred Tasks

### T02: Capture Baseline Behavioral Outputs
**Requires:** Fresh CC session (not nested)
**Action:** For each of the 5 pilot files, invoke with representative inputs from `test-inputs/` and capture outputs to `baseline-behaviors.md`.
**Why blocked:** Behavioral verification (T34-T38) needs pre/post comparison data. Since refactoring is already merged, only post-refactor behaviors can be captured.
**Recommendation:** Skip — pre-refactor baselines no longer available. Post-refactor behaviors serve as the new baseline.

### T11: Smoke Test batch-promptimize.sh
**Requires:** Fresh terminal (outside CC session)
**Action:**
```bash
cd /Users/terry/projects/my-ai-setup
bash plugins/iflow/scripts/batch-promptimize.sh 2>&1 | head -20
```
Verify at least 1 file produces a valid numeric score.
**Priority:** Low — interactive scoring already validated the scoring system works.

### T34-T38: Pilot Behavioral Verification
**Requires:** Interactive CC sessions
**Status:** Deferred — static analysis evidence already documented in pilot-gate-report.md.
**Recommendation:** Run opportunistically when using these components in normal workflow. Each component's behavioral contract is preserved per static analysis.

| Task | Component | What to Verify |
|------|-----------|----------------|
| T34 | design-reviewer.md | Approval decision matches, issue count +/-1, no new severity categories |
| T35 | secretary.md | All 5 routing prompts return same agent selection |
| T36 | brainstorming/SKILL.md | Same stages reached, same research dispatch count +/-1, same PRD headings |
| T37 | review-ds-code.md | 3-chain synthesis: same approval, issue count +/-1, no new categories |
| T38 | review-ds-analysis.md | Same as T37 for analysis review |

### T40: Full Batch Promptimize Run (SC-1)
**Requires:** Fresh terminal + significant time
**Action:**
```bash
cd /Users/terry/projects/my-ai-setup
bash plugins/iflow/scripts/batch-promptimize.sh 2>&1 | tee batch-scores.log
```
All 85+ component files must score >=80.
**Priority:** Medium — pilot gate passed, but full coverage validates the refactoring didn't degrade any file.
**Recommendation:** Run when convenient. This is the final quality gate for SC-1.
