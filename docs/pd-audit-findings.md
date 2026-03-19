# pd Plugin Audit Findings

> **Audit Date:** 2026-01-31
> **Health Score:** 6/10
> **Status:** Documentation only (no code changes)

This document captures findings from a thorough review of the pd plugin against research findings, best practices, and official Claude Code architecture.

---

## Critical Issues

### 1. Executor-Reviewer Loops Violate Research Findings

**Severity:** Critical

The workflow implements multi-stage reviewer loops that research proves ineffective.

| Command | Reviewer Chain | Problem |
|---------|---------------|---------|
| `/implement` | chain-reviewer → final-reviewer | LLMs cannot reliably self-correct |
| `/specify`, `/design`, `/create-plan`, `/create-tasks` | chain-reviewer loop (up to 5 iterations) | Diminishing returns after 1-2 iterations |

**Current flow in `/implement`:**
```
implementer → chain-reviewer (loop up to 5x) → final-reviewer → human decision
```

**Research Evidence:**

1. **DeepMind Study:** "7.6% of incorrect responses corrected; 8.8% of correct responses made incorrect" - showing self-review can actually degrade quality.

2. **Self-Refine (NeurIPS 2023):** Demonstrates diminishing returns after 1-2 iterations of self-refinement.

3. **Debugging Decay Index (arXiv 2025):** "Debugging effectiveness exhausted by 3rd iteration" - further iterations waste compute.

4. **Scaling Agent Systems (arXiv 2025):** "Coordination overhead becomes net cost when baseline performance already high."

**Recommendation:** Remove reviewer loops entirely. Use single verification step with external feedback (tests, linting).

---

### 2. Redundant Reviewer Agents

**Severity:** Critical

Five reviewer agents create confusion, decision paralysis, and wasted compute:

| Agent | Purpose | Overlaps With |
|-------|---------|---------------|
| `chain-reviewer` | Validates artifact ready for next phase | - |
| `final-reviewer` | Validates implementation matches spec | spec-reviewer |
| `spec-reviewer` | Verifies implementation matches spec | final-reviewer |
| `code-quality-reviewer` | Reviews code quality | quality-reviewer |
| `quality-reviewer` | Verifies code quality | code-quality-reviewer |

**Recommendation:** Consolidate to 2 agents maximum:
1. `chain-reviewer` - Keep for artifact sufficiency (single-pass, no loop)
2. `implementation-reviewer` - Merge final-reviewer + spec-reviewer + quality reviewers

---

### 3. Orphaned Components (Dead Code)

**Severity:** Critical

#### Unused Agents (Never Referenced)

| Agent | Location | Status |
|-------|----------|--------|
| `generic-worker` | `plugins/pd/agents/generic-worker.md` | Never invoked by any command or skill |
| `investigation-agent` | `plugins/pd/agents/investigation-agent.md` | Never invoked by any command or skill |

#### Unused Skills (Never Referenced)

| Skill | Location | Lines | Status |
|-------|----------|-------|--------|
| `detecting-kanban` | `plugins/pd/skills/detecting-kanban.md` | 36 | Trivial utility, never called |
| `dispatching-parallel-agents` | `plugins/pd/skills/dispatching-parallel-agents.md` | 74 | Documented but never integrated |
| `systematic-debugging` | `plugins/pd/skills/systematic-debugging.md` | 101 | No `/debug` command exists |
| `writing-skills` | `plugins/pd/skills/writing-skills.md` | 158 | Meta skill, self-referential only |

**Recommendation:** Delete orphaned components or integrate them properly.

---

## High Priority Issues

### 4. Complex Commands (Entry Points Should Be Simple)

**Severity:** High

| Command | Lines | Embedded Logic |
|---------|-------|----------------|
| `/implement` | 173 | 2 reviewer loops, 7 workflow steps |
| `/finish` | 100+ | Quality review, retro, merge, cleanup |

Commands should be simple entry points that delegate to skills/agents. These commands contain entire workflows inline.

**Recommendation:** Simplify commands to invoke skills, move logic to skills.

---

### 5. Native Plan Mode Duplication

**Severity:** High

pd's `/create-plan` command duplicates Claude Code's native `EnterPlanMode` functionality:

| Capability | Native Plan Mode | pd /create-plan |
|------------|------------------|-------------------|
| Codebase exploration | Yes | Yes (via skills) |
| Plan file output | Yes | Yes (plan.md) |
| User approval gate | Yes (ExitPlanMode) | No (reviewer loop instead) |
| Implementation | After approval | After reviewer approval |

**Added overhead from pd:**
- chain-reviewer loop (up to 5 iterations)
- .meta.json state tracking
- Phase validation logic

**Recommendation:** Consider using native plan mode instead, or simplify to complement rather than replace.

---

## Medium Priority Issues

### 6. Weak Skill Trigger Descriptions

**Severity:** Medium

| Skill | Current Trigger | Problem |
|-------|-----------------|---------|
| `detecting-kanban` | "Use when checking Kanban availability" | Vague - never auto-triggers |
| `verifying-before-completion` | "Use when about to claim work is complete" | Should be automatic guard |
| `systematic-debugging` | "Use when encountering any bug" | Should be automatic on test failure |

**Recommendation:** Make triggers specific or make skills automatic guards.

---

### 7. Inconsistent Naming

**Severity:** Medium

| Skill | Issue |
|-------|-------|
| `verifying-before-completion` | Should be `completion-guarding` (gerund form) |
| `dispatching-parallel-agents` | Inconsistent with other names |

**Standard per CLAUDE.md:** Gerund form (`creating-tests`, `reviewing-code`)

---

## Low Priority Issues

### 8. Hook Efficiency

**Severity:** Low

`pre-commit-guard.sh` runs 12+ find patterns on every `git commit`:
```bash
find . -type f \( -name "*_test.go" -o -name "*.test.ts" ... \)
```

**Recommendation:** Optimize with single find or cache results.

---

## Component Health Summary

| Type | Total | Active | Orphaned | Health |
|------|-------|--------|----------|--------|
| Skills | 18 | 14 | 4 | 78% |
| Agents | 8 | 6 | 2 | 75% |
| Commands | 14 | 14 | 0 | 100% |
| Hooks | 2 | 2 | 0 | 100% |

**Overall Health Score:** 6/10 - Good intent, poor execution due to executor-reviewer anti-patterns.

---

## Research Sources

1. **Large Language Models Cannot Self-Correct Reasoning Yet**
   https://arxiv.org/abs/2310.01798 - ICLR 2024

2. **Self-Refine: Iterative Refinement with Self-Feedback**
   https://arxiv.org/abs/2303.17651 - NeurIPS 2023

3. **Debugging Decay Index**
   https://arxiv.org/html/2506.18403 - arXiv 2025

4. **Towards a Science of Scaling Agent Systems**
   https://arxiv.org/html/2512.08296v1 - arXiv 2025

5. **Benchmarking LLM-based Code Review**
   https://arxiv.org/html/2509.01494v1 - arXiv 2025

---

## Future Actions (If Desired)

If cleanup is undertaken in the future, prioritize in this order:

1. **Remove reviewer loops** - Replace with single-pass verification + external feedback
2. **Consolidate reviewers** - Merge 5 reviewer agents into 2
3. **Delete orphaned code** - Remove unused agents and skills
4. **Simplify commands** - Extract workflow logic to skills
5. **Fix naming** - Apply consistent gerund form to all skills
