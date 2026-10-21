# Retrospective: 018 — iflow UI Server + Kanban Board

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 30 min | 5 (phase-reviewer) | All warnings, no blockers. SC-6/PRD reconciliation flagged; no change required. |
| design | 75 min | 7 (3 design + 4 handoff) | 2 blockers iter 1: Jinja2 "already in venv" false claim, CDN URL mismatch. Handoff capped on PoC gate formalization. |
| create-plan | 165 min | 10 (5 plan + 5 chain) | Both stages hit cap. Three concurrent blocker categories: TDD order inverted, dependency graph contradictions, shell wrapper invocation mechanics. |
| create-tasks | 75 min | 7 (5 task + 2 chain) | Task-reviewer capped. Blockers: import paths, missing conftest.py, circular dependency (stub board.py required), PYTHONPATH in wrapper. |
| implement | 230 min | 5 (force-approved) | uvicorn missing from base deps caught at iter 4 final validation. Quality + security passed iter 4; implementation passed iter 5 after trivial pyproject.toml fix. Circuit breaker — force-approved. |

**Quantitative summary:** 575 total minutes (~9.6 hours wall-clock), 34 review iterations across 5 phases. create-plan was the costliest phase (165 min, 10 iterations) — the only phase in project history with simultaneous double cap across both review stages. Implementation produced 48 passing tests, 25 files changed, 3,394 insertions, 30 commits. Only 1 meaningful blocker (uvicorn missing from base deps) reached implementation.

---

### Review (Qualitative Observations)

1. **Spec accuracy gaps in dependency and CDN claims drove 2+ design iterations and cascaded to plan.** Design iter 1 caught two blockers from unverified spec claims: "Jinja2 not in venv — design falsely claims Already in venv" and "Tailwind CSS CDN URL mismatch — cdn.tailwindcss.com vs DaisyUI v5's @tailwindcss/browser@4". Design iter 2 continued: "Spec Dependencies (line 112) claims Jinja2 already available — incorrect". Required an explicit "Spec inaccuracies addressed by this design" section and a spec correction task in the plan.

2. **Python import path and PYTHONPATH specification recurred as a blocker across 4 separate phase boundaries.** Plan iter 1: "Package import validation unreliable — python -c import may fail without PYTHONPATH." Task iter 2 blocker: "Import path `from plugins.iflow.ui.routes.board` is wrong — plugins/ has no \_\_init\_\_.py. Should be `from ui.routes.board`." Task iter 5 blocker: "No pytest invocation includes PYTHONPATH → all runs fail ImportError — added conftest.py task (1.2.3) with sys.path inserts." Same root cause independently re-discovered at design, plan iter 1, task iter 2, and task iter 5.

3. **create-plan double cap (10/10) was driven by three independent blocker categories requiring simultaneous convergence.** Plan iter 2 blocker: "TDD order still inverted — tests come AFTER implementation." Plan iter 3 blocker: "Shell wrapper module invocation fails from plugin cache — `$PLUGIN_DIR/../..` won't resolve to project root." Chain iters 1–4: dependency graph redrawn each iteration for 4.1/4.3 relationship (parallel vs sequential, which phases need 4.3). All three required simultaneous resolution before either reviewer stage would approve.

4. **Quality review improvement (uv sync --no-dev) revealed missing runtime dep (uvicorn) three iterations later.** Iter 1 quality: "Step 3 uses uv pip install instead of uv sync — drift risk from hand-maintained package list." Changed to `uv sync --no-dev`. Iter 4 final validation blocker: "uvicorn not in pyproject.toml base dependencies — uv sync --no-dev won't install it, causing ModuleNotFoundError." Switching install commands without auditing pyproject.toml base deps created a gap invisible until end-to-end execution.

---

### Tune (Process Recommendations)

1. **Add Dependency Verification Checklist to Spec Skill** (Confidence: high)
   - Signal: Spec claimed Jinja2 "already in venv" and used incorrect CDN URL — both caught at design iter 1, drove 2+ design iterations and a plan correction task.
   - Recommendation: For each external library listed as "available" in spec, verify presence in `plugins/iflow/.venv/lib`. For each CDN URL, verify by reading an actual sibling server file or dependency feature design.md. Annotate as "verified against: \<file\>:\<line\>".

2. **Annotate Python Import Root at Spec Time for New Packages** (Confidence: high)
   - Signal: Python import path recurred as a blocker at design, plan iter 1, task iter 2, and task iter 5 — four phase boundaries, same root cause.
   - Recommendation: At spec time, confirm PYTHONPATH root (`plugins/iflow/`, not its parent) and annotate all FR import examples with the verified root. Add conftest.py with sys.path insertion as a mandatory task 1.x for every new package that includes tests.

3. **create-plan Pre-Submission Three-Check Fast-Fail** (Confidence: high)
   - Signal: create-plan double cap (165 min, 10 iterations) was driven by TDD ordering, dependency graph contradictions, and shell wrapper invocation — all three active simultaneously.
   - Recommendation: Before plan submission: (1) verify all test steps precede implementation steps in every phase; (2) verify every dependency edge in the graph appears as prose and vice versa; (3) for shell wrapper tasks, state exact invocation pattern and verify it matches an existing sibling script (e.g., run-workflow-server.sh). These three checks would have prevented 6–7 of 10 iterations.

4. **Audit pyproject.toml Base Deps When Switching Install Command** (Confidence: high)
   - Signal: uv sync --no-dev improvement at iter 1 exposed missing uvicorn only at iter 4 final validation — a 3-iteration gap between the change and its consequence.
   - Recommendation: When any script switches from `uv pip install <list>` to `uv sync --no-dev`, immediately audit `[project]` dependencies in pyproject.toml to confirm every runtime-path package is listed there. Make this a required done-when step in any task that modifies a bootstrap wrapper's install step.

5. **PoC Gate Requires Four Elements Before Design Handoff** (Confidence: medium)
   - Signal: Design handoff took 4 iterations to specify PoC gate mechanics — iter 1 added failure contingency, iter 2 pass/fail criteria and file location, iter 3 task sequencing, iter 4 approved.
   - Recommendation: Write PoC gate atomically before handoff submission: (1) exact pass/fail criteria with commands and expected output, (2) named failure contingency with alternative approach, (3) conditional task branching sequence, (4) artifact file location. Missing any one causes the handoff reviewer to extract it in a separate iteration.

---

### Act (Knowledge Bank Updates)

**Patterns added:**
- `uv sync --no-dev Requires Complete Base Dependency Audit` — when upgrading bootstrap wrapper from hand-maintained install to lockfile-driven sync, immediately audit [project] deps (from: Feature 018, implement phase)
- `Establish Python Import Root at Spec Time for New Packages` — annotate verified PYTHONPATH root in all FR import examples; add mandatory conftest.py task for new packages (from: Feature 018, multi-phase recurring import blocker)

**Anti-patterns added:**
- `Spec Dependency Claims Without Venv Verification` — false-certainty dep claims in spec propagate as design blockers requiring explicit correction sections downstream (from: Feature 018, design iter 1)
- `Switching Install Command Without Auditing Dependency Manifest` — changing uv pip install to uv sync --no-dev without reconciling pyproject.toml creates invisible runtime gaps (from: Feature 018, implement iters 1 and 4)

**Heuristics added:**
- `create-plan Double Cap Predicts Three Simultaneous Blocker Categories` — budget 150–180 min when feature combines TDD methodology, shell wrapper invocation, and multi-phase dependency graph (from: Feature 018, create-plan 165 min double cap)
- `Recurring Cross-Phase Blocker in Same Category Signals Missing Spec-Level Annotation` — same issue across 3+ phase boundaries means the spec is missing a foundational annotation each reviewer is independently re-discovering (from: Feature 018, import path across 4 phases)
- `PoC Gate Requires Four Elements Before Design Handoff` — pass/fail criteria, failure contingency, task branching, artifact location — all four must be written atomically (from: Feature 018, design handoff 4 iterations)

---

## Raw Data

- Feature: 018-unified-iflow-ui-server-with-s
- Mode: full
- Branch lifetime: 2026-03-08 to 2026-03-09 (1 day)
- Total review iterations: 34
- Circuit breaker hits: 3 (plan-reviewer 5/5, chain-reviewer 5/5, implement force-approve at 5/5)
- Implementation: 48 tests, 25 files changed, 3,394 insertions, 30 commits
- Artifact sizes: spec.md 115 lines, design.md 406 lines, plan.md 232 lines, tasks.md 278 lines (total: 1,031 lines)
- Learnings captured during implement: "uv sync --no-dev requires all runtime deps in base [project]", "Use call_args.kwargs not positional indexing for mocks"
