# Retrospective — Feature 105 Codex Routing Coverage Extension

**Branch:** `feature/105-codex-routing-coverage-extension`
**Closes:** Feature 103 coverage gap — codex routing now applies at 11 dispatch sites (existing 6 + new 5).

## Outcome

Shipped a 5-preamble + 1-validate.sh patch as a tightly-scoped follow-up to feature 103. validate.sh now exits non-zero on (a) any file referencing codex-routing.md missing the no-security-review indicator (FR-2a), or (b) the discovered file set drifting from the 11-file allowlist (FR-2b). All 4 implement reviewers approved on iter 1. Pre-merge validate.sh PASS.

## A — Achievements

- **Direct-orchestrator implement, single-pass review.** All 12 tasks (T1-T12) executed inline with no per-task implementer dispatch. All 4 reviewers (implementation, relevance, code-quality, security) approved iter 1 with only suggestion-level findings. Continues the pattern from features 101, 102, 104: heavy upstream review (specify 3 iters + design 4 iters + create-plan 3 iters = 10 reviewer iterations) buys single-pass implementation.
- **Override-pattern not needed.** Unlike feature 104, no test-deepener override was required. The user-direction filter ("primary feature + primary/secondary defense") aligned naturally with this feature's small scope; reviewers found no recursive test-hardening accumulation to override.
- **FR-2b allowlist-drift detection works in both directions.** Manual-checklist tests T11 (a)+(b) confirmed validate.sh fires non-zero for both drift +1 (extra file) AND drift -1 path-substitution (file renamed). Sanity-check (`grep -rl ... | grep "taskify.md.disabled"`) verified the discovery loop sees the rename, preventing a silent-pass mode where validate.sh errored on something else.

## O — Obstacles

- **Plan-reviewer iter 2 detected fixes-in-tasks.md-only.** Iter 1 plan-reviewer required clarifications in plan.md anchor text + cwd-handling. I applied the fixes to tasks.md (the operational layer) but missed propagating them to plan.md (the description layer). Iter 2 plan-reviewer caught this. Lesson: when a reviewer flags issues in plan.md, the fixes need to land in plan.md too — not just downstream operational artifacts.
- **Task-reviewer iter 1 found 3 self-containment blockers.** T4/T5/T6 had `using the same extract_codex_section pattern as T3` — fine for human readers but invalid for isolated subagent execution. Fix: inline the full snippet in each task. Lesson: when authoring tasks for potential parallel/isolated dispatch, every task must be self-contained (no cross-task references for code).
- **Design's evidence-file commit-stance was wrong.** Design I-5 prescribed "Evidence files ARE committed at agent_sandbox/2026-05-06/feature-105-evidence/...". Implementation discovered `agent_sandbox/` is gitignored at the repo root. Resolved via implementation-log.md + local-only evidence. Same precedent as feature 102 (.qa-gate-low-findings.md gitignored). Lesson: design phase should verify gitignore status of any path it prescribes for committed artifacts.
- **R-8 line number drift (cosmetic).** Design fixed "line 726" verbatim into the secretary.md preamble's R-8 note. After preamble insertion, the actual `subagent_type: "{plugin}:{agent}"` shifted to line 732. Implementation-reviewer flagged as suggestion. Mitigation: anchor text "Step 7 DELEGATE" is content-stable; line number is a soft reference. Acceptable tradeoff.

## R — Risks Surfaced

- **Pattern-discovery scope of validate.sh:** the FR-2b grep scope is `plugins/pd/commands plugins/pd/skills`. If pd ever adds a third dispatch directory (e.g., `plugins/pd/agents/dispatchers/`), the allowlist won't auto-pick it up. Manual update needed. Documented but not fixed.
- **Codex companion CLI surface inherited from feature 103:** if `node codex-companion.mjs task --prompt-file` flag changes in a future codex plugin release, all 11 preambles propagate the bug at once. Not new — same scope-shared risk feature 103 inherited. Future feature could add a CI smoke test running `node codex-companion.mjs task --help` and asserting the flag.
- **decomposing/SKILL.md preamble placement** — code-quality-reviewer suggested moving the preamble to immediately after H1 (currently after Config Variables). Cosmetic only; validate.sh-compliant either way.

## T — Themes / Trends

- **Heavy-upstream / cheap-downstream pattern is now load-bearing across 5 consecutive features (101, 102, 103, 104, 105).** The investment moves work upstream where it's cheapest and produces binary-checkable DoDs. When all 4 reviewers approve iter 1 with only suggestion-level findings (zero blockers, zero warnings), final validation can be skipped without risk.
- **Skipping Step 0 research is appropriate when prior art is direct.** Feature 105 is literally an extension of feature 103; the research dispatch would have been a pure no-op. YOLO mode "domain expert" path saved 2 agent dispatches with zero information loss.
- **Plan-reviewer's "fixes-in-plan.md-too" expectation.** When a reviewer flags issues anchored to plan.md, the operator should propagate fixes to plan.md as well — not assume the operational tasks.md layer is sufficient. This is now the third feature where this distinction surfaced (102, 104, 105).

## A — Actions

1. **CLAUDE.md sync** — Add a line to the Knowledge & Memory section noting that codex routing now covers 11 sites (was 6). Defer to claude-md-management plugin if installed, else log skip.
2. **Document agent_sandbox/ gitignore convention** — Add a one-liner to docs/dev_guides explaining that evidence files in agent_sandbox/ are local-only by design (per CLAUDE.md tracked-non-workflow convention). Future features that need committed artifacts must use docs/features/{id}/.evidence-*.txt instead. Defer to a follow-up — not in scope here.
3. **Propose follow-up backlog item:** consider promoting `references/codex-routing.md` discovery scope from `plugins/pd/commands plugins/pd/skills` to a reusable `discover_codex_dispatch_sites.sh` helper that the FR-2b allowlist can reuse, so future scope expansions (new dispatch directories) don't require per-site validate.sh edits. Low priority.
4. **Knowledge bank entries to capture:**
   - Pattern: "Plan-reviewer flags require fixes in plan.md too, not just tasks.md" (process category, link to features 102/104/105).
   - Pattern: "FR-2b-style allowlist diff catches both adds-and-removes; count-only checks miss path substitutions" (engineering category, link to feature 105 spec-reviewer iter 1 warning #5).
   - Anti-pattern: "Cross-task references for code (using the same X as Tn) break parallel/isolated subagent dispatch" (test-engineering category, link to feature 105 task-reviewer iter 1).

## Workarounds Captured

None this feature. The evidence-file gitignore mismatch was resolved via implementation-log.md substitution; not a persistent workaround.

## Iteration Counts

| Phase | Reviewer iterations |
|-------|---------------------|
| specify | 3 (spec-reviewer iter 1+2+3 → APPROVED; phase-reviewer iter 1+2 → APPROVED) |
| design | 4 (design-reviewer iter 1+2 → APPROVED; phase-reviewer iter 1+2 → APPROVED) |
| create-plan | 3 (plan-reviewer iter 1+2+3 → APPROVED; task-reviewer iter 1+2 → APPROVED; phase-reviewer iter 1 → APPROVED) |
| implement | 1 (all 4 reviewers approved iter 1) |
| **Total** | **11 reviewer iterations across 4 phases** |

The 11-iteration upstream investment paid off in the 1-iteration implement convergence — same heavy-upstream/cheap-downstream pattern as features 101, 102, 104.
