---
name: verifying
description: The Verify stage's playbook — launch the verify-change workflow (the code review beside QA, then bounded fix cycles), record its review and qa entries, and settle rejections and risk tags with the user. Use when a feature is in phase verify, or when reviewing a feature's whole branch diff.
---

# Verifying

The Verify stage (`phase: verify`) asks: does the merged branch do what the criteria say, as a whole? One review call over the whole branch diff runs beside QA, then up to three cycles of a separate fixer plus a QA re-run, all inside the `verify-change` workflow. The conductor records the result and owns every ruling. Shared mechanics: the `workflow-transitions` skill.

## Steps

1. **Phase entry** per `workflow-transitions`, on the feature branch with a clean tree.
2. **Derive the args** for `verify-change` from the committed files:
   - `feature_id`; `shape` and `plan` (the files' paths); `base`: `git merge-base HEAD <base_branch>`;
   - `checklist`: this skill's `## Review checklist` section, verbatim;
   - `qa_battery` from `.claude/pd.local.md` (none set: stop and ask the user to set it; `phase-gate.sh verify` fails without it), plus the migration's up-and-down commands on a fixture database when the feature has `risk: migration`;
   - `task_proofs`: each task's `case_map`, `greens` and `skipped`, from the `run` entries' task lines and their `case_map:` lines;
   - `assumptions`: this feature's open assumptions from `pd-status`;
   - `codex`: `false` when the user's CLAUDE.md says `**Codex reviewer: DISABLED**`; `codex_flags`: the `--model <m> --effort <e>` its `**Codex reviewer model:**` line names (`references/review-call.md`);
   - `workflow_output_cap` from the config, raised by any `decision` entry that raised it for this feature.
3. **Launch `verify-change`** per `workflow-transitions` "Workflow runs". Its first QA run also runs the risk scan and the isolation check over `<base>..HEAD` (`pd-lint --risk`, `pd-lint --isolation`), once; their errors and unmatched risk signals come back as `qa` issues. Don't run them again.
4. **Record the result** (`references/workflow-results.md`, `verify-change`) in the shapes of `references/log-entries.md`, then clear `run in flight:` and commit:
   - **`run`:** the launch, with `Agents:`, `Tokens:` and the fix `cycles`;
   - **`review`:** heading `review verify — <reviewed_by, or none>`; `Verdict:` and the reviewed commit; one issue line per `review.issues` item; one `Rejects: review@<this entry>#<id> — <evidence>` line per rejection of an `R` issue;
   - **`qa`:** `Commit: <qa.commit>`; one `` Ran: `<command>` -> pass|fail `` line per battery command; `Criteria gaps:` from `qa.gaps`; one issue line per `qa.issues` item; one `Rejects: qa@<this entry>#<id> — <evidence>` line per rejection of a `Q` issue; one `Fixed: <id> by <commit> — <test>` line per `fixes` item, and a `Closes:` line naming the fixed review issues (`review@<the review entry>#R<n>`; a `Q` issue QA no longer reports was never logged);
   - **`note`:** one per flake.
5. **Settle what is still open:**
   - **Rejections:** put them to the user through AskUserQuestion, at most four per call, blockers first. Each answer is a `decision` entry, `A (user, verbatim)`; an accepted one adds `Closes:` for its issue, naming the entry that raised it (`review@…#R<n>` or `qa@…#Q<n>`).
   - **Blockers left after the third cycle, or a failing battery:** a `capped verify` entry (four lists), then ask the user; the answer is a `decision` with `answers: capped@<date> <time>`.
   - **A judgement finding with no testable check:** a hard stop: ask.
   - **No usable review** (`reviewed_by: null`, an `R0` blocker): a hard stop. Ask through AskUserQuestion: re-run the review call, or waive it, a `decision` entry with `Closes: review@<this entry>#R0`. The open `R0` blocks `phase-gate.sh verify` until then.
6. **Risk tags.** A risk signal with no matching tag: decide the tag with the user (a `decision` entry), then set `risk:` in the README.
   - **`security`:** the security review at finish becomes mandatory (`finishing-branch`).
   - **`migration`:** re-run this stage with the migration's up and down in the battery.
   - **On a small or express feature,** a tag set here moves the feature back: express to `specify`, small to `design`, each then at standard depth (`phase verify -> <stage> (back)`).
   - **Only the user clears a tag,** with a `decision` entry.
7. **Exit check:** `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh verify <feature dir>`: every `qa_battery` command passing in the latest `qa` entry, no source, test or fixture change since its commit, no open blocker. Then phase exit per `workflow-transitions` (`phase verify -> finish`).

**Entries this stage writes:** `run`, `review`, `qa`, `note` (flakes), `decision` (rulings, accepted rejections, tags), `capped` (at the cap), `phase`.

**Express's lighter Verify:** the proving command and the QA battery. The code review is the conductor's call. Skipping it is a `decision` entry with its reason; then run the proving command and each battery command yourself, unchanged, and write the `qa` entry from their exit codes at HEAD. Otherwise run `verify-change` as above.

## Review checklist

The code review's bar, over the whole branch diff (`<base>..HEAD`), not one task's:
- **Each criterion is met:** every `B<n>` in `shape.md` `## Requirements` has a test that encodes it, and the code does what the expectation says for its input, edge cases included.
- **Each mapped test asserts its case's stated outcome,** not a weaker one: check every `case_map` entry at file:line. A test that would also pass on a fallback or no-op path proves nothing. Tests already green at their first commit (`greens`) get a closer look.
- **The contracts hold:** signatures, errors and invariants match `shape.md` `### Contracts`; no test imports a module outside a contract's `modules:` line, or a private name.
- **Integration seams:** what crosses tasks (shared types, call order, config, error propagation) works end to end, since each task was proven alone.
- **Minimum code:** no abstraction, option, wrapper or "for later" code the contract doesn't need. Over-engineering is a finding.
- **Safety:** input validated at trust boundaries, no data loss on error paths, no secret in code or logs.
- **The executors' reports are claims, not evidence:** check each at file:line before relying on it.

A blocker is wrong behaviour a user would hit, or a criterion with no test that would catch its breaking. Style and preference are notes. Every finding cites file:line.
