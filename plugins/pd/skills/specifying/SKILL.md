---
name: specifying
description: The Criteria stage's playbook — shape.md ## Requirements as observable expectations, calvin cycles through calvin-runner, and the user's sign-off; also an express work item's mini-spec. Use when a work item is in phase specify, or an express work item needs its mini-spec.
---

# Specifying

The Criteria stage (`phase: specify`) removes one unknown: how will anyone know the work is done? It hands down `shape.md` `## Requirements`. Shared mechanics (state, entry, exit, caps, dispatch): the `workflow-transitions` skill.

## Steps

1. **Phase entry** per `workflow-transitions`. A work item that doesn't exist yet, promoted work included, is created first through `/pd:create-workitem` (`--from <brainstorm or rca>`, or `--plan <plan> <slug>` for a roadmap's `planned:` line), which sets its depth and creates its branch.
2. **A direct request** first gets Clarify's two questions, through AskUserQuestion: is this the right problem, and what would success look like?
3. **Write `## Requirements`** in `{pd_artifacts_root}/workitems/<id>/shape.md` from the PRD, RCA report or request, using `${CLAUDE_PLUGIN_ROOT}/templates/shape.md`. The bar is below. Ask the user only about contradictions and decisions the source can't answer.
4. **Calvin cycles,** up to three (below).
5. **Sign-off:** ask through AskUserQuestion whether the criteria are signed off, showing the expectations (past half a terminal, `shape.md` opens in the browser per `workflow-transitions`). Write the answer as a `decision` entry: `Q: criteria signed off?` and `A (user, verbatim): "<quote>"`. This is a hard stop in every mode: never answered on the user's behalf. A criterion nobody can state as an observable outcome is a hard stop too.
6. **Exit check:** `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh specify <work item dir>` (the expectations' format, and the user's sign-off). Then phase exit per `workflow-transitions` (`phase specify -> design`).

**Entries this stage writes:** `review` (one per calvin cycle), `decision` (the sign-off, and each user ruling), `capped` (at the cap), `phase`.

## Calvin cycles

1. **Name the ledger:** `agent_sandbox/<YYYY-MM-DD>/<id>/calvin-cycle-<n>.md`.
2. **Record it before the dispatch,** in the session's gate state file, keeping its other keys (the agent write hook allows `calvin-runner` that one path and nothing else):

   ```bash
   python3 -c 'import json, os, sys
   p = os.path.expanduser(f"~/.claude/pd/gate/{sys.argv[1]}.json")
   os.makedirs(os.path.dirname(p), exist_ok=True)
   d = json.load(open(p)) if os.path.exists(p) else {}
   d["calvin_ledger"] = sys.argv[2]
   json.dump(d, open(p, "w"))' "${CLAUDE_SESSION_ID}" "<ledger path>"
   ```
3. **Dispatch `calvin-runner`** on `shape.md`, with the PRD or RCA report the criteria derive from, in report mode, naming the ledger path. A later cycle is scoped: the earlier ledger's rows and the edit that answered them.
4. **Answer each row.** Questions about intent, scope, priorities or a ruling are the user's: ask them through AskUserQuestion and quote the answers. Questions about wording or consistency are the conductor's. Revise `## Requirements`.
5. **Write a `review` entry** for the cycle: the ledger path, each row's outcome, and whom each question went to.
6. **The loop ends** at the first cycle whose ledger has no blocker-severity row. Still open after the third: a `capped` entry, then ask the user.

If `calvin-runner` returns `calvin skill not installed`, tell the user (`/pd:init` checks for it) and ask whether to sign off without it; record the answer as a `decision`.

## Express: the mini-spec

For `mode: express` (a small diff on a known pattern, provable by one command), `## Requirements` holds only the mini-spec: one or more expectation lines, and one task block in `plan.md`'s task format (`${CLAUDE_PLUGIN_ROOT}/templates/plan.md`) with `files:`, `uses:`, `command:` (writing its `junit:` path) and test cases. Cite the existing example of the same change shape by path. No calvin and no sign-off: run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh express <work item dir>`, then move `phase:` to `implement` per `workflow-transitions` (Triage has already recorded each skipped stage).

## The bar for `## Requirements`

**Expectations: observable, one per line.** `B<n>: <input or action> -> <observable outcome>`, ids unique. Each names what anyone can see happen: a value, an error, an exit code, a file. "Login works" is not one; `B3: an expired token -> the request gets 401 and no session row` is. An expectation resting on stdlib or library runtime behavior carries the verifying REPL line inline (`>>> expr → result`). These are expectations, not tests: the Plan stage turns them into test cases.

**Goals, non-goals and user stories** give the expectations their context.

**Scope boundaries, both sides.** What gets built, and the out-of-scope items a reader would otherwise assume are included. YAGNI applies to both lists. A criterion that keeps old behaviour working (compatibility) cites its evidence of external consumers: a published package, API or CLI, a route called from outside the repository, a file format other tools read, or a named consumer outside the repository; without it, it's out of scope, and callers inside the repository move with the change.

**Edge cases, named, not gestured at.** Invalid input, absent or empty state, concurrent access, and the failure mode of each external dependency, each with its expected behavior, as an expectation where it is observable. Complex branching goes in a truth table instead of a linear list.

**Must-nots:** what the work item must not do, each with the harm it avoids.

**What, never how.** Anything verifiable only by reading a diff belongs in `## Design`. Where a requirement names test symbols or existing test classes, say whether the scope is production behavior or test-only hardening.
