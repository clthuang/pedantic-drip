---
name: planning
description: The Plan stage's playbook — plan.md's waves of tasks, each with its contract, files, uses:, proving command and test cases, reviewed by the test-case review. Use when a feature is in phase create-plan, or when writing or reviewing `## Plan`.
---

# Planning

The Plan stage (`phase: create-plan`) removes one unknown: in what order, and how is each step proven? It hands down `plan.md`, whose tasks become the `implement-tasks` workflow's args. The conductor writes every test case; executors never do. Shared mechanics: the `workflow-transitions` skill.

## Steps

1. **Phase entry** per `workflow-transitions`.
2. **Write `plan.md`** beside `shape.md`, using `${CLAUDE_PLUGIN_ROOT}/templates/plan.md`, with `from_shape:` set to `git hash-object shape.md`. The bar is the checklist below.
3. **Check it mechanically:** `pd-lint <feature dir>` (expectation coverage, task fields, JUnit paths, wave bases, disjoint `[parallel-safe]` file sets, `from_shape:`). Fix every error before the review.
4. **The test-case review:** the review call per `${CLAUDE_PLUGIN_ROOT}/references/review-call.md`, with this skill's `## Review checklist` inline, given `shape.md`, `plan.md` and read access to the code. Up to three review-revise cycles:
   - **revise** for each blocker; a finding you can refute at file:line gets a `Rejects:` line instead, and only the user accepts it;
   - **re-review scoped** to the earlier findings and the edit that answered them (`pd-review-filter --range <reviewed commit>..HEAD`);
   - **the loop ends** at the first pass with no blocker. Still open after the third: a `capped` entry, then ask the user.
5. **Exit check:** `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh create-plan <feature dir>`, and `pd-lint` clean. Then phase exit per `workflow-transitions` (`phase create-plan -> implement`).

**Entries this stage writes:** `review` (one per review call), `decision` (each user ruling, each accepted rejection, a re-confirmed plan), `capped` (at the cap), `note` (a small feature's overrun), `phase`.

**Small mode:** the joint review made at the end of the `designing` skill covers this plan too; don't make a second call. When the plan has more tasks than `small_feature_tasks`, `pd-lint` warns: record the overrun as a `note` entry and carry on with the single review.

**Re-entering after a backward move:** `shape.md` has changed, so `from_shape:` is stale and `pd-lint` fails. Regenerate the plan, or re-confirm it by updating `from_shape:` only when the move changed nothing the plan cites (no contract or expectation it names), and only after a scoped test-case review or the user's ruling, recorded as a `review` or `decision` entry. Tasks whose contract or test cases changed re-run.

## The task block

```markdown
### Wave 1

#### Task 1: <what it delivers> [parallel-safe]
- contract: shape.md ## Design, <module>
- files: <every path the task may touch, tests included>
- uses: <modules its tests or code import, or none>
- command: `<runner> <test files> --junitxml=agent_sandbox/junit/task-1.xml`
- junit: agent_sandbox/junit/task-1.xml
- test cases:
  - C1 [B1, B2] (fixture: <path> | fake: <name> | fixture: none): given <input>, expect <outcome>.
```

Add `- proof: green-only (refactor|infra|fixture)` only for a task whose tests can't be red first; the merger then skips the red check, and the review sees the mark.

## Review checklist

- **Faithful cases:** each test case cites the expectation ids it covers, and expects that expectation's stated outcome, not a weaker one ("raises" where the expectation names the error; "returns a list" where it names the list).
- **Coverage:** every `B<n>` is covered by at least one case; edge cases and must-nots from `## Requirements` have their cases.
- **The contract surface, never internals:** cases call what the contract block exposes; none reaches into private names or implementation details. Each names its fixture or fake, or `fixture: none`.
- **Semantic, not code:** cases are plain words or pseudo code, specific enough that two executors would write equivalent tests.
- **Non-vacuity:** a case for a new path beside an existing fallback asserts a fact true only on the new path.
- **Dispatchable tasks:** each has its contract pointer, file set, `uses:`, and a proving command that writes its `junit:` path; a task no command can prove is split or sharpened.
- **Order:** waves in dependency order; a task's `uses:` modules exist at its wave's base. `[parallel-safe]` only when the task's file set is disjoint from every other parallel task in its wave, and it is big enough for running in parallel to pay.
- **`green-only` is earned:** the reason is `refactor` (existing tests prove it), `infra` or `fixture`, and true of the task.
