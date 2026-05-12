# Retrospective: 112-workspace-identity-cleanup

## AORTA Analysis

### Observe (Quantitative Metrics)
| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| brainstorm | skipped | 0 | Promoted directly from /pd:secretary routing |
| specify | 9.5 min | 2 | Iter 1: 5 blockers + 5 warnings + 2 suggestions. Iter 2: APPROVED |
| design | ~12 min | 3 | Iter 1: 4 blockers (I-3 factual error, TD-7 invalid pytest.ini, C4b mechanism wrong) |
| create-plan | ~22 min | 3 | Heaviest cycle — 10 blockers iter 1, 4 NEW blockers iter 2 from fix regression. Iter 3: zero blockers |
| implement | ~62 min | 0 | Per-method incremental commits served as audit trail (pattern from feature 108) |

**Summary:** ~105 min total across 4 active phases. 8 cumulative review iterations (2+3+3+0). Create-plan was heaviest by both duration and iteration count, with iter 2 introducing fresh blockers from incomplete fix propagation. Regression score: +4 pass, -1 pre-existing fix repaired, zero new regressions vs baseline. Implement contributed largest absolute duration but zero review cycles via incremental commit pattern.

### Review (Qualitative Observations)

1. **Factual errors in design and plan artifacts were the dominant blocker category** — claims about code location (I-3), scope size (Phase D _project_id), and tool mechanics (TE.10b) all proved wrong when empirically grepped. All three were reviewer-caught, requiring artifact rewrites rather than minor tweaks.
   - Evidence: Design iter 1 'I-3 claimed parent_type_id resolution lived in the _resolve_workspace_uuid_kwargs shim; empirical grep showed it actually lives in register_entity body at database.py:3343-3445.' Plan iter 1: 'scope was originally budgeted 3 lines but actual count was 48 occurrences.'

2. **Fix propagation regressions in plan iter 2** — applying iter 1's C.2 fix without scanning siblings caused G.1's db._conn to re-emerge as a NEW blocker. Iteration cycles can introduce as much risk as they resolve when revisions are mechanical rather than principled.
   - Evidence: 'Plan iter 2 introduced NEW blockers: G.1 still used db._conn (missed re-applying C.2 fix when consolidating). Task-reviewer iter 2 caught 4 new blockers I introduced.'

3. **Phase ordering bugs from non-adjacent splits** — Phase A's import drop preceded Phase D's call-site removal, creating an intermediate NameError state. The fix reorganized phase boundaries rather than tasks within phases.
   - Evidence: 'original plan dropped detect_project_id import in Phase A but the call site lived in Phase D's MCP files — NameError until Phase D ran.'

### Tune (Process Recommendations)

1. **Add empirical-claims checklist to specifying and designing skills** (Confidence: high)
   - Signal: Three distinct factual-error blockers across design and plan, all caught by reviewers, none at authoring time
   - Action: Require grep/test citation for claims about code location, scope size, or tool behavior. Reviewer prompts should fail blocks lacking verification citations.

2. **Add regression-check step to plan-reviewer and task-reviewer revision passes** (Confidence: high)
   - Signal: Plan iter 2 introduced 4 new blockers by failing to propagate iter 1 fixes
   - Action: When re-reviewing after revisions, explicitly diff iter N against iter N-1 and flag any previously-fixed issue that re-emerged. Editors should grep for sibling instances before declaring resolution.

3. **Codify per-method incremental rollout pattern in implementing skill** (Confidence: high)
   - Signal: 62 min implement with zero review iterations, regression score improved, pattern reused successfully from feature 108
   - Action: Document the pattern as preferred strategy for refactors touching many call sites where each commit can be independently verified.

4. **Optional iter-N findings sidecar for reviewer commands** (Confidence: medium)
   - Signal: Saving .plan-review-iter1.md mid-session enabled successful fresh-session resume after user overrode conservative budget
   - Action: Reviewer commands write .{command}-review-iter{N}.md when iterations >= 2, enabling cross-session continuity.

5. **File backlog item for complete_phase reviewer_notes string-vs-dict mismatch** (Confidence: high)
   - Signal: Tool description claims 'JSON-serializable payload' but only strings work; three attempts wasted on dict variants
   - Action: Either accept dicts with auto-coercion (mirror entity_registry pattern at database.py:627) or update tool description to 'string only'.

### Act (Knowledge Bank Updates)

**Patterns added:**
- Per-method incremental commits for many-call-site refactors — granular audit trail supplants post-hoc review (from: Feature #112 implement, 62 min, 0 iterations, +4 regression score)
- Save iter-N reviewer findings to sidecar markdown mid-session — enables fresh-session resume; context budgets often less constrained than they appear (from: Feature #112 create-plan, .plan-review-iter1.md at 56% context)

**Anti-patterns added:**
- Citing code locations, scope sizes, or API behaviors without empirical verification — factual errors compound into wrong phase boundaries and task budgets (from: Feature #112 design I-3, plan Phase D scope, design TE.10b)
- Applying review fixes as point-fixes without sibling-scan — guarantees regression in next iteration (from: Feature #112 plan iter 2, 4 NEW blockers from incomplete consolidation)
- Splitting producer/consumer of an identifier across non-adjacent phases — creates intermediate NameError state, violates phase-checkpoint invariant (from: Feature #112 plan iter 1, detect_project_id import vs call site)

**Heuristics added:**
- Repeated point-fixes during revision mean the original wasn't class-fixed — stop and re-scan before publishing (from: Feature #112 db._conn regression)
- Code citations in specs/designs need exact file:line references — vague refs hide factual errors (from: Feature #112 I-3 wrong by 100+ lines)
- User pushback on conservative context budget is often correct — save sidecars and continue (from: Feature #112 user override at 56% context)
- MCP tool contract mismatches are bugs, not usage errors — file backlog, don't memorize workarounds (from: Feature #112 complete_phase string-vs-dict)

## Raw Data
- Feature: 112-workspace-identity-cleanup
- Mode: standard
- Branch lifetime: same session (~2 hours active)
- Total review iterations: 8 (2 specify + 3 design + 3 create-plan + 0 implement)
- Commits: 19 (15 reviewer-cycle + 7 implementation + 2 cleanup)
- Diff: 35 files, +3088 / -265
- Regression: 79/4193/3 vs baseline 80/4189/3 (+4 pass, -1 pre-existing repaired, 0 new regressions)
- AC-32 timing: 0.0063s vs 2s budget (~300× headroom)
