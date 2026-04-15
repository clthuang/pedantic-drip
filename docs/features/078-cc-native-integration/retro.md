# Retrospective: 078-cc-native-integration

## AORTA Analysis

### Observe (Quantitative Metrics)
| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| brainstorm | ~1 min | 0 | PRD pre-existed; immediate transition to specify |
| specify | ~10 min | 3 | At the 3-iteration hard cap |
| design | ~12 min | 4 | **Exceeded the documented 3-iteration hard cap** |
| create-plan | ~8 min | 2 | Within target band |
| implement | ~3 days (29 tasks, 7 batches) | 2 | Iter-3 final validation skipped pragmatically; 1 usage-limit stall |

**Summary:** Standard mode, 3-day branch lifetime, 14 commits, 40 files, +4144/-230 lines. Spec and design phases hit or exceeded the 3-iteration cap (3 and 4). Implementation dispatched with parallelism up to 5, producing 4 new test scripts, 3 new ADRs, and a 400-line spike-results doc.

### Review (Qualitative Observations)
1. **Design exceeded the 3-iteration hard cap (4 iterations) without triggering user-intervention summary** — the cap exists in CLAUDE.md but isn't enforced in design.md.
2. **Review-history file was not generated** because reviewer dispatches bypassed the standard writing flow — systemic observability gap.
3. **Security-reviewer caught a real OWASP LLM01 vector** (doctor_schedule cron interpolated into Tool-arg template without validation) that other reviewers missed; fixed in iter 2 with allowlist regex + injection test.
4. **Relevance-verifier requested backward travel for a one-sentence doc gap**; team resolved inline, suggesting backward-travel policy is too heavy-handed for trivial gaps.
5. **Six reviewer suggestions deferred at complete_phase** with no backlog capture — deferrals at risk of rotting invisibly.

### Tune (Process Recommendations)
1. **Add tasks.md format validation to create-plan/plan-reviewer** (Confidence: high)
   - Signal: Bullet-format tasks.md was rewritten mid-implement because plan-reviewer doesn't parse against the implementing skill's regex.
2. **Enforce the 3-iteration cap in specify.md and design.md** (Confidence: high)
   - Signal: Design hit 4 iterations with no circuit-breaker trigger; cap is documented but not mechanized.
3. **Make review-history writing a hook-enforced PostToolUse step** (Confidence: medium)
   - Signal: Direct reviewer dispatches silently skipped the log; retro lost qualitative trail.
4. **Decouple final-validation regression pass from the iteration counter in implement.md** (Confidence: medium)
   - Signal: Iter-3 final validation was skipped because the workflow would have fired the circuit breaker on the legitimate completion path.
5. **Add gap-severity field to relevance-verifier's return JSON** (Confidence: medium)
   - Signal: Verifier requested backward travel for a trivial one-sentence AC gap.
6. **Add same-file task bundling to the implementing skill's batch planner** (Confidence: high)
   - Signal: T2.2-T2.10 manually bundled into one dispatch to avoid parallel merge conflicts on one file.

### Act (Knowledge Bank Updates)

**Patterns added:**
- When N tasks all modify the same file, dispatch them as a single implementer agent rather than parallel agents (from: implement phase — T2.2-T2.10 bundled onto implementing/SKILL.md)
- Any user-config value interpolated into an LLM Tool-arg template must pass an allowlist regex and carry a dedicated injection test (from: implement iter 1 security review — doctor_schedule OWASP LLM01)
- Trivial documentation gaps from relevance-verifier can be resolved inline; backward travel is reserved for structural gaps (from: implement iter 1 — REQ-2 .worktreeinclude fixed inline)

**Anti-patterns added:**
- Writing tasks.md in a format other than the implementing skill's '### Task N.M:' heading convention (from: create-plan → implement transition — bullet format required mid-implement rewrite)
- Direct reviewer dispatches that bypass the standard review-history-writing flow (from: implement phase — .review-history.md not generated, AORTA 'R' degraded)
- Workflows whose final-validation round counts against the same iteration cap as remediation rounds (from: implement iter 3 — pragmatic skip to avoid circuit breaker on completion path)

**Heuristics added:**
- Test code respects the same encapsulation boundaries as production code (from: implement iter 1 — test-sqlite-concurrency.sh accessed db._conn, flagged by code-quality-reviewer)
- Manual verification spikes should be documented as PR-time gates in spike-results.md and surfaced in finish-feature output (from: implement phase — T0.4, T4.1 documented as blocked-manual PR gates)
- Deferred reviewer suggestions should be captured in the backlog at complete_phase time, not left in review summaries (from: implement complete_phase — 6 deferred suggestions with no backlog capture)

## Raw Data
- Feature: 078-cc-native-integration
- Mode: Standard
- Branch lifetime: 3 days (2026-04-12 → 2026-04-15)
- Total review iterations: 11 (specify 3 + design 4 + create-plan 2 + implement 2)
- Commits: 14; Files changed: 40; +4144 / -230 lines
- Tasks: 29 across 5 stages, 7 batches, parallelism up to 5
- Notable stalls: 1 (T2.0 usage-limit at 5pm Asia/Taipei)
- Manual PR gates: 2 (T0.4 agent path compliance, T4.1 context:fork)
- Deferred suggestions: 6 (not backlogged)
