# Retrospective: 041-meta-json-guard-degradation

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 7 min 9 sec | 2 | Well-bounded bug fix from RCA; clean convergence |
| design | 11 min 44 sec | 3 | Reviewers pushed on sentinel placement, function rename atomicity, and set -e interaction |
| create-plan | 10 min 4 sec | 3 | Plan-reviewer required explicit task ordering and atomic refactor constraint |
| create-tasks | ~10 min 46 sec | 5 | Highest friction — driven by missing dependency annotations and parallelism markers, not correctness |
| implement | 19 min 17 sec | 2 | All 3 reviewers approved first functional iteration; iteration 2 was final validation only |

Feature completed in ~59 minutes on 2026-03-17 (Standard mode, single day). Total review iterations: 15 across 5 phases. create-tasks was the highest-friction phase (5 iterations) driven entirely by task structure quality. implement was the smoothest (1 functional iteration, 3/3 reviewer approval, 0 blockers). 17 commits, 10 files, +1446/-11 lines — dominated by 620 lines of new test coverage vs 32 lines of production code change (19:1 ratio).

---

### Review (Qualitative Observations)

1. **Task dependency annotation quality was the primary source of rework** — All 5 create-tasks iterations were driven by missing explicit `> Depends on:` annotations and parallelism markers, not task correctness. Evidence: final tasks.md shows explicit depends-on on Task 1.4 (on 1.1-1.3), Task 2.3 (on 2.2), and a parallel marker on Task 2.4 — all added under review pressure.

2. **Implementation converged in one functional iteration with only suggestions** — All 3 reviewers approved on first pass. The 8 suggestions were exclusively in JSONL injection safety (4 security) and readability (4 quality). The same injection pattern — unescaped variable in JSONL echo — appeared across 3 separate fields (timestamp, feature_id, tool_name). Evidence: `.review-history.md` Iteration 1: "Implementation Review: Approved", "Quality Review: Approved (4 suggestions)", "Security Review: Approved (4 suggestions)".

3. **A code simplification step introduced a preventable bug** — A `replace_all` operation matched inside a helper function body during implementation, causing infinite recursion and a segfault. Fixed quickly via targeted refactor (commit 4a3030d). Evidence: Key Events: "Code simplification step caused a bug (replace_all matched inside helper function body, causing infinite recursion / segfault). Fixed quickly."

---

### Tune (Process Recommendations)

1. **Elevate dependency annotations to a blocker-level task-reviewer check** (Confidence: high)
   - Signal: create-tasks reached 5 iterations — highest of any phase — driven entirely by missing `> Depends on:` and parallelism markers. All other phases required 2-3 iterations.
   - Recommendation: Add to task-reviewer prompt as a blocker: every task with a prerequisite must include `> Depends on: Task X.Y`; tasks with no blockers must be annotated parallelizable. Currently this is enforced through review pressure, causing unnecessary iterations.

2. **Add escape_json requirement to hook authoring checklist** (Confidence: high)
   - Signal: Security reviewer flagged 4 JSONL injection issues across 3 distinct variables in meta-json-guard.sh. All were caught post-implementation rather than prevented at authoring time.
   - Recommendation: Add to the hook development guide and security reviewer prompt: all variables interpolated into JSONL echo statements must use escape_json. Include as an explicit checklist item.

3. **Add replace_all scoping caution to hook development guide** (Confidence: medium)
   - Signal: Unscoped replace_all caused infinite recursion by matching inside a helper function body. Fixed quickly but was a preventable defect.
   - Recommendation: Add to hook development guide: "Bulk find-replace in bash hook files must be scoped to specific line ranges or use word-boundary anchors. Never apply replace_all to a function name that appears in its own body."

4. **Add atomic-edit heuristic for bash function refactors to plan-reviewer** (Confidence: medium)
   - Signal: Design required 3 iterations to surface the Task 2.2 atomicity constraint (rename + call-site update = single edit). The constraint was obvious in retrospect but not anticipated.
   - Recommendation: Add a plan-reviewer heuristic: refactor tasks that rename a function must explicitly state that the rename and all call site updates are a single atomic edit.

5. **Reinforce red-green task sequencing as a recommended pattern for hook changes** (Confidence: high)
   - Signal: 620 lines of tests written before 32 lines of production code (19:1 ratio). All 3 reviewers approved implement on first functional pass — the cleanest implement convergence observed.
   - Recommendation: Capture red-green task sequencing (Phase 1: failing tests with red-phase notes; Phase 2: implement to green) as a high-confidence pattern in the knowledge bank for hook changes.

---

### Act (Knowledge Bank Updates)

**Patterns added:**

- **Red-green task sequencing for hook changes:** Structure tasks so Phase 1 writes all failing tests (with explicit red-phase notes) before Phase 2 makes any production code changes. Yields single-iteration implement convergence. (from: Feature 041, create-tasks + implement phases)

- **Atomic rename+call-site update for bash function refactors:** When renaming a function in a bash file, the rename and all call site updates must be performed in a single edit. Splitting them creates a broken intermediate state that fails silently at runtime. (from: Feature 041, design phase — Task 2.2 atomicity constraint)

**Anti-patterns added:**

- **Unscoped bulk text substitution in bash hook files:** Using replace_all or sed without line-range or word-boundary scoping risks matching inside function bodies, causing infinite recursion or logic corruption. (from: Feature 041, implement phase — replace_all caused segfault)

- **JSONL log construction with unescaped bash variables:** Constructing JSONL in bash hooks without escape_json on every interpolated variable creates injection vectors. Fields that appear safe (timestamp, tool_name) must also be escaped. (from: Feature 041, implement phase — 4 security review findings)

**Heuristics added:**

- **Dependency annotation is a task-author responsibility, not a reviewer catch:** Every task with a prerequisite needs an explicit `> Depends on:` annotation. Tasks with no blockers should be marked parallelizable. (from: Feature 041, create-tasks — 5 iterations driven by missing annotations)

- **Escape all JSONL variables in hook files uniformly via escape_json.** Escaping all fields requires less judgment than deciding which are safe, and eliminates an entire class of security review findings at authoring time. (from: Feature 041, implement phase — security review suggestions)

---

## Raw Data

- Feature: 041-meta-json-guard-degradation
- Mode: Standard
- Branch: feature/041-meta-json-guard-degradation
- Branch lifetime: single day (2026-03-17)
- Total review iterations: 15
- Commits: 17
- Files changed: 10 (+1446 / -11)
- Production code delta: ~32 lines (meta-json-guard.sh)
- Test coverage delta: ~620 lines (test-hooks.sh)
- Source: RCA for fresh-install deadlock (meta-json-guard unconditional deny with no degradation path)
