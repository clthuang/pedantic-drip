# Thin pd on Claude Code's native features (design)

**Status:** calvin'd twice on 2026-10-14 (D16, D17), then reviewed by Codex for implementation readiness in three cycles, ending READY (annex `reviews/`); ready for the build (§16), which `build-tasks.md` breaks into tasks.
**The direction ("thin pd"):**
- Claude Code's native workflows, skills, subagents, hooks and `/goal` run the process;
- the SQLite entity registry and the MCP servers retire;
- durable state moves into files committed with each project.

**This document has two parts:**
- **Part A, the workflow topology:** pd's problem-solving method, mapped onto Claude Code's native features. Added at the user's request (2026-10-14): "Focus on recreating my problem solving workflow topology using CC's native feature."
- **Part B, the artifact SOP:** the files that hold durable state, and the rules that keep them consistent across every project pd is installed in.

**Scope guard (the user's challenge, 2026-10-14: "are we rebuilding CC's internal long running agent harness?"):**
- **No.** Claude Code ships no long-running harness. Anthropic's is a recipe built "to enable the Claude Agent SDK to work effectively across many context windows": a feature list, a progress file and git (anthropic.com/engineering/effective-harnesses-for-long-running-agents).
- **Part B is that recipe's file layer, plus the scripts that keep it honest:** the feature list is the roadmaps and the backlog (§7), the progress file is `## Now` and `log.md` (§5, §6), and git is git. Part A runs the process on Claude Code's own features. Both use the built-ins wherever they fit (§2, principle 6), and neither builds an issue tracker. Tracker-like extras are listed in §14 and deferred until a project needs them.

**Glossary:**
- **Dn:** a decision in §15. A letter suffix (D1b, D7c) marks a sub-decision.
- **Fn and Kn:** findings in the Fable reviews: Fn in the first, Kn in the fourth.
- **#074:** a pd backlog item.
- **Phase R:** the abandoned registry re-key (§A8.1). **M1** is one of its milestones.
- **"The existing integration script":** `followups-phase-integration-generic.js` (§A4).
- **"This session":** the agent session that wrote this plan, on 2026-10-14.

**Provenance:** the annex `docs/dev_artifacts/plans/2026-10-14-thin-pd/`, committed with this plan before the build (§16 step 2) and moved with it at adopt (§16 step 7).
- **`reviews/`:** the four Fable reviews (`fable-review.md`, `fable-review-2.md`, `fable-review-3.md`, `fable-review-4.md`); calvin's first ledger (`calvin-ledger.md`), the author's answers to it (`calvin-adjudication.md`) and the record of how each answer was applied (`calvin-applied.md`); calvin's second ledger (`calvin-ledger-2.md`), the author's answers to it (`calvin-adjudication-2.md`) and the record of applying them (`calvin-applied-2.md`); and Codex's implementation-readiness review of this plan and the task breakdown in three cycles: `codex-readiness-review.json` (21 findings), `-2.json` (6 left) and `-3.json` (READY, 2026-10-14). §15 cites the reviews and ledgers.
- **`build-tasks.md`:** §16 broken into tasks, each with a runnable proof.
- **`workflow-scripts/`:** the two scripts §A4's workflows are built from.

---

# Part A: the workflow topology on native features

## A1. What pd is for, and what it can drop

**pd exists to run one problem-solving method.** The user's two principles, verbatim (2026-10-14):
- "different phases reduce different types of uncertainties."
- "keeping the scope and responsibility of each agent narrow and well defined, review agents should have large context and free from historical conversation of the execution agent"

**The long form is the essay `docs/workflow-principles.md`,** committed with this plan before the build (§16 step 2). The plan is the home of mechanisms; the essay is the home of principles. Its sections are cited below by number and title, as "principles §N, *title*", so a citation survives a renumbering.

**Everything else pd built is machinery for running that method:** the SQLite state machine, the MCP servers, the Kanban UI, cross-workspace queries, the reconciler and the doctor.
- **Its size, measured on develop at `97b3470a` (the commands are in §A8.1):** 35,565 lines of production Python and 97,653 lines of Python tests under `plugins/pd/hooks/lib`, `plugins/pd/mcp` and `plugins/pd/ui`. The method itself lives in 8,023 lines of skill, command and agent markdown.
- **The user's ruling, verbatim (2026-10-14):** "I am happy to lose the Kanban UI, cross workspace querying (somewhat replaced by claud-mem)."

**Why rebuild pd at all,** when it has been off since 2026-09-24 (§A8.1)? It makes the method mechanical across four projects:
- **committed state** any session can resume;
- **gates** that caught every recorded occurrence of the half-sweep defect (§A8.1);
- **one vocabulary.**

Without it, the user keeps handover documents by hand, as Phase R did.

**So each pd component faces one test:** does it carry the method (keep it, rewritten onto native features) or only the machinery (retire it)? §A6 applies the test; a component it doesn't name gets its verdict from the build's inventory (§A6).

## A2. The topology: one stage per class of unknown

Each stage names the unknown it removes, what it hands down, the mechanical gate (its exit check, Part B §5), and an independent check only where being wrong is expensive (principles §11, *More review is not better; every loop gets a budget*).

**The diagram:** `docs/workflow-canonical.mmd` draws this section and §A3 to §A5, which are its source.
- **Change the text first,** then redraw the diagram by hand. Nothing checks it for drift; that is an accepted risk.
- **Its PNG is regenerated by the author** after each edit to the `.mmd`, with `mmdc -i docs/workflow-canonical.mmd -o docs/workflow-canonical.png -s 3 -b white`, and never committed (Part B §3.1, rule 4).
- **The essay's decks carry their own images.** They are human-doc assets, outside this plan's scope.

| Stage (`phase` value) | The unknown it removes | Hands down | Mechanical gate | Independent check | Runs as |
|---|---|---|---|---|---|
| **0. Triage** (none) | What kind of work is this, and how deep must it go? | First, `pd-new` creates the item for the way the work arrived (Part B §4.1): a request gets `pd-new feature`, which makes the feature directory with its README and `log.md`; an idea gets `pd-new brainstorm`, and a bug `pd-new rca`, each one file. Then: the item's `type`; for a feature, its `mode` (`standard`, `small` or `express`) and `risk:` tags; each skipped stage as a `phase` entry in `log.md`, with the reason. Work entering at Clarify gets its `mode` and `risk:` later, when `pd-new feature --from` promotes it at Criteria: the conductor applies `/pd:secretary`'s depth rules then (D16) | none | none | Main session: `/pd:secretary` |
| **1. Clarify** (none: the work lives in its brainstorm or `rca` item, Part B §3) | Is this the right problem, and what would success look like? | A brainstorm PRD or an RCA report, in its single-file item. The feature directory first exists when `pd-new feature` runs: at Triage for a request, and at Criteria for work promoted by `pd-new feature --from <brainstorm or rca>`. An RCA's fix may instead run express straight after the RCA, through the same command with `mode: express`. A direct request skips to stage 2, where the conductor first asks this stage's two questions | none | A refuter against each surviving RCA cause, inside the `rca-fanout` workflow. A PRD gets none; calvin covers it at Criteria (§A8.3 S2) | Main session asks (the user owns the answers); the `research-fanout` or `rca-fanout` workflow fans out |
| **2. Criteria** (`specify`) | How will anyone know it is done? | `shape.md` `## Requirements`. The success criteria are the behaviour expectations: each has an id and an outcome anyone can observe (`B1: <input or action> -> <observable outcome>`). Goals, non-goals and user stories give them context. Also: what is in scope and out of scope, edge cases, must-nots. These are expectations, not tests: Plan turns them into test cases (D14) | `phase-gate.sh specify`, which also requires the user's sign-off entry, plus `pd-lint`'s expectation format (Part B §9) | Calvin, for faithfulness and sufficiency, which no script can check (principles §3, *Behaviour before architecture*), in up to three review-revise cycles (below). Then the user signs off the criteria, recorded as a `decision` entry: "Q: criteria signed off? A (user, verbatim): …" | Main session; calvin as a fresh `calvin-runner` agent writing its ledger to a file (§A3) |
| **3. Contracts** (`design`) | What crosses each boundary? | `shape.md` `## Design`: an `### Architecture` diagram (mermaid) of the modules, the data flowing between them and the contract on each edge (D12); per module, its schema and interface contract in one code block, which carries a `modules:` line (Part B §9), the files it owns, its invariants; and `### Test strategy`: where fixtures live, each fake and what it stands in for, and which real resources tests may touch (none unless named) (D15). Documents only: the scaffold is semantic and contract-level, and no code is written here (D14) | `phase-gate.sh design`, which also requires the diagram and `### Test strategy` | Design review: fresh context, Codex first, in up to three review-revise cycles. It checks that every edge carries a contract and every contract sits on an edge | Main session writes it, grounded by `codebase-explorer`; one review call reviews it (§A4) |
| **4. Plan** (`create-plan`) | In what order, and how is each step proven? | `plan.md`: tasks grouped into waves (§A4). Per task: its contract pointer, the files it may touch, a `uses:` list of the modules its tests or code import, its test cases and the command that will run them. The test cases are semantic, in plain words or pseudo code, not test code: each cites the expectation ids it covers and names the fixture or fake it uses ("none" when it uses neither), edge cases included, and each tests the contract surface, never internals. All written by the conductor, never the executor (principles §7, *A task is dispatchable only when it is objectively verifiable*). The conductor marks a task `[parallel-safe]` only when it is big enough for running in parallel to pay (§A8.3 S5) | `phase-gate.sh create-plan`, plus `pd-lint`: every expectation id is covered by a test case, and every `uses:` module of a `[parallel-safe]` task will exist at its wave's base (Part B §9) | Test-case review: fresh context, Codex first. Are the cases faithful to the expectations, and do they cover the edges? Up to three review-revise cycles (D14) | Main session. `plan.md`'s tasks become the `implement-tasks` workflow's args |
| **5. Execute** (`implement`) | Does the code meet each task's contract? | Per task, the tests first, then the change in as many commits as it has meaningful steps (D14, D15). The first commit holds only the test code, transcribed from the plan's test cases; it may add source, as new files or as new lines in existing ones, such as signatures that raise, but no existing line may change or go (§A4). Each test in it must fail as a test, not as code that won't load; any test already green there is named for the Verify reviewer. Each later commit says what changed and why, so reviewers, fixers and a resumed run can follow the trajectory. "Meaningful step" is a reading aid that nothing checks: a commit mixing unrelated steps is a code-review note, never a blocker. At HEAD every test passes, and the executor never changes its tests after the first commit (§A4). Merged onto the feature branch wave by wave, in plan order | The merger's per-task check (§A4) | None per task. The cadence ruling of 2026-10-13 set one review and one QA per milestone; here the milestone is Verify, so each feature gets one of each | The `implement-tasks` workflow |
| **6. Verify** (`verify`, new) | Does the whole change hold together, including what no criterion named? | `review`, `qa` and `gate` entries in `log.md` | `phase-gate.sh verify`: a `qa` entry recording every `qa_battery` command (Part B §12) passing, and the commit it ran against, with no file under `source_paths`, `test_paths` or `fixture_paths` changed since. Later commits may change anything else, such as `log.md`, the README or `retro.md`; a change to source, tests or fixtures needs a new `qa` entry (codex review C4). And no open blockers | Code review (Codex first) beside QA, flagging only what affects correctness or the criteria, over-engineering included. QA also says, for each criterion, what passing it would still allow (D14), in the `qa` entry: a gap that affects a criterion is a blocker finding, otherwise a note. Then up to three fix cycles by a separate fixer, each re-checked by a QA re-run, never by a second review | The `verify-change` workflow, started by the `verifying` skill |
| **7. Finish** (`finish`) | What did this teach, and should the method change? | A `metrics` entry in `log.md` (Part B §6). On a trigger (§A8.3 S4): `retro.md`, with each lesson turned into a check, a CLAUDE.md line or a skill edit. Otherwise one `note` entry | `phase-gate.sh finish` | The security review, for a feature tagged `risk: security`; a blocker from it sends the feature back to Verify (below). When a retro runs, `retro-facilitator` re-derives every figure from `log.md` and git | A fresh `retro-facilitator` agent, on a trigger; then the main session merges and closes |

**Why `verify` becomes its own phase:** today's `implement` phase holds both execution and verification. The user lists verification as its own stage ("code review, QA, simplification"). Splitting it gives verification its own gate and its own `log.md` record. The user ruled for it (D7).

**Review and fix budgets.** The user's rulings, 2026-10-14: "each phase should allow up to three cycles"; then, after the third Fable review (D14), "Criteria clarification, spec writing, design and contracts should have higher review-revise cycle allowance as they have more uncertainties."
- **Before code (Criteria, Contracts, Plan): up to three review-revise cycles.** Nothing can be run yet, so a reviewer is the only judge.
  - **A re-review is scoped:** it checks only the earlier findings and the edit that answered them, never the whole artifact again.
  - **The loop ends at the first pass with no blocker.** Whatever is still open after the third cycle goes to the user.
  - **One Criteria cycle:** calvin runs in report mode on the criteria, with the PRD or RCA report they derive from, and writes a ledger. The conductor answers each row, asking the user any question that is theirs, and revises. The next cycle re-runs calvin scoped to the earlier ledger's rows and the edit that answered them.
    - **Whose question it is:** questions about intent, scope, priorities or a ruling are the user's; questions about wording or consistency are the conductor's. The conductor decides which is which, and the ledger records whom each went to.
    - **A Criteria pass has no blocker** when calvin's ledger has no blocker-severity row.
- **After code, checks judge the fixes, never a second review** (K5 of the fourth Fable review):
  - **Execute:** up to three fix cycles per task against the merger's check. A task's first run is not a cycle; the fix cycles start after a failed check;
  - **Verify:** one review pass, then up to three fix cycles against the QA battery;
  - **A security blocker at finish** sends the feature back to Verify, as a backward move. The fixer handles it under Verify's rules: a fresh budget of three fix cycles, and each fix brings its test. The security reviewer re-checks only its own findings, scoped like a re-review before code.
  - **That move is the one exception to the backward-move rule (below):** only Verify's fix loop, the QA battery and the security reviewer's scoped re-check run again. The code review doesn't run again.
- **A judgement finding** says that behaviour is missing or wrong while the existing suite passes before and after its fix (a missing case, a wrong error, an untested edge). So it counts as fixed only with a new test. In practice it shows when a QA re-run sees no new test go red and then green: the fix needs one. The QA re-run rejects such a fix, its cycle counts as spent, and the next cycle must bring the test.
  - **The finder states the case** in words; the fixer commits its test before the fix; the QA re-run checks it red on that commit and green after. So no agent chooses its own proof (principles §7, *A task is dispatchable only when it is objectively verifiable*; the test-author split, D14).
  - **In Verify, the fixer commits new tests first,** and changes an existing test only when a finding says that test is wrong. The rule that tests never change after the first commit (§A4) binds Execute's tasks only.
  - **If no such test can be written,** the finding goes to the user. (The Fable review's F4, adopted 2026-10-14.)
- **A removal finding** (over-engineering, §A8.3 S3) is fixed by deleting code. It is judged by the suite staying green, plus the diff removing the code at the finding's file:line. It never needs a new test, and doesn't go to the user for want of one.
- **An unexpected result triggers a re-run** (D14, D15). Expected means red at the first commit, and green at HEAD, after merges and in the QA battery. If the two runs disagree, a third run decides. A flake costs no cycle: a `note` entry in `log.md` names the test, written by the conductor from the workflow result's `flakes[]` (§A4), and it becomes a QA finding in Verify.
- **A rejected finding costs no cycle** (D15). The rejection is proposed with file:line evidence, by the fixer after code and by the conductor before it; the conductor records it and puts it to the user. Only the user accepts a rejection, before code as after it, in the batch (§A4); it is never argued in a re-review.
- **When a loop reaches its cap, the conductor writes a `capped` entry in `log.md` before it asks the user** (D15, the user: "after review cycle cap is reached, we need to document any deferred items, followup items, decisions made, assumptions made"). It has four lists, each allowed to say "none":
  - **Deferred:** what is left open, and why;
  - **Follow-ups:** each also gets a line in `backlog.md`, with `from: features/<id>`;
  - **Decisions:** each made during the loop, pointing at its `decision` entry (Part B §6 gives the answer line's forms);
  - **Assumptions:** each one the work now rests on. The next stage that has a reviewer receives the open assumptions as claims to check (after Execute, that is Verify's code review); at Finish, the open ones are listed for the user in the finish summary. One stays open until a later `review` or `qa` entry cites it as confirmed, or the user rules; `pd-status` lists open assumptions, and they don't block.
- **A `capped` entry closes the loop's open blockers.** The cap stop is an AskUserQuestion. The user's answer is a `decision` entry, written after the question, that names the `capped` entry it answers (`answers: capped@<date> <HH:MM±hh:mm>`, Part B §6), and `pd-status` links the two (Part B §11).
- **A failed executor task escalates once:** fix cycle 1 runs on `sonnet`, and fix cycles 2 and 3 on the strongest model (D7c; D14: "Escalation is cycle 2"). The escalated cycles reuse the `implementer` definition with its model overridden (§A3), and keep its verification paragraph; the extra checking costs one cycle, which is accepted. Verify's fixer follows the same ladder.
- **Still failing after fix cycle 3:** the work stops and goes to the user.
- **Principles §11, *More review is not better; every loop gets a budget*, now says the same** (updated 2026-10-14).

**The entry picks the depth, not just the start** (principles §2, *Entry depth matches the uncertainty that arrived*):
- **A brainstorm** enters at Clarify.
- **An RCA** arrives with a diagnosis and evidence, which answers most of Clarify. Its fix enters at Criteria, or runs express when it is one known pattern (row 1 above).
- **A direct feature request** enters at Criteria.
- **Express** (`mode: express`) is for a small diff on a known pattern, provable by one command. Known means the codebase already holds the same change shape, and the mini-spec cites that example's path.
  - **It skips the Criteria, Contracts and Plan phases,** and each skip is recorded.
  - **A mini-spec stands in for the criteria and the plan:** one task block in `shape.md` `## Requirements`, with the expectation, its test cases, the file set, `uses:` and the proving command. The `implement-tasks` args derive from it, and the executor's tests-first rule still applies.
  - **Then Execute and a lighter Verify run:** the proving command and the QA battery. The code review is the conductor's call, and skipping it is a `decision` entry (D15).
- **A small feature may write Contracts and Plan in one sitting** (the user's ruling on S1, 2026-10-14).
  - **Decided at Triage, as an estimate** (D13): the task count is known only once the plan exists, so Triage records `mode: small`, with its reason in Triage's own `phase` entry (`phase triage -> <first stage>`), for example "one module, one proving command". The cap is `small_feature_tasks` (Part B §12, default 3).
  - **A plan that outgrows the estimate is not a failure.** `pd-lint` reports it without blocking, and the conductor records the overrun as a `note` entry in `log.md`. The feature keeps small's single review call; nothing else changes.
  - **Both phases are still recorded.** One review call covers the contracts and the test cases together (D15), in up to three review-revise cycles, counted once for the joint review; `pd-lint` checks the plan as usual.
  - **`plan.md` stays a separate file,** so each executor receives only its own task, and `from_shape:` still applies.
  - **Never for work that needs standard depth** (next item).
- **Always standard depth, never small or express:** a security surface, a schema or data migration, more than `many_files` files (Part B §12, default 10), an area unfamiliar to the codebase (no existing module or earlier feature covers it; Triage judges, and records why), or criteria that look hard to state as observable outcomes. This is `/pd:secretary`'s existing rule. If Criteria still can't state one, that is a hard stop (§A5).
- **Risk tags make two of these stick** (D14). Triage records `risk: security` or `risk: migration` in the frontmatter (Part B §5), and a risk scan at `verify` warns when the branch diff shows a signal with no matching tag (Part B §9; D15 moved it from commit time, where a task worktree has no feature to tag).
  - **`security`:** the security review at finish is mandatory.
  - **`migration`:** QA runs the migration up and down against a fixture database, recorded as a `qa` entry.
  - **A tag set at Verify on a small or express feature** is a backward move: an express feature goes back to its earliest skipped stage, and a small one to Contracts. Either then runs at standard depth, so Contracts and Plan get separate review calls. A `phase` entry records it.
  - **Only the user clears a tag,** with a `decision` entry.

**Going back is cheap, and it invalidates what sits below** (principles §12, *Going back should be normal*):
- **Any stage may send the work back.** The frontmatter `phase` moves back, and a `phase` entry in `log.md`, marked `(back)`, records the reason and names what the move invalidates (Part B §6). One backward move costs nothing more: it is not a retro trigger (§A8.3 S4).
- **What a move invalidates:** every stage from the one moved back to runs again; a security blocker's move back to Verify is the one exception (above). Review blockers about a replaced artifact close with the backward entry. The plan regenerates, unless it may be re-confirmed (below), and tasks whose contract or test cases changed re-run. Code and merged branches are not marked stale mechanically.
- **A stale plan is caught mechanically.** `plan.md` records, in a `from_shape:` frontmatter field, the git blob hash of the `shape.md` it was derived from.
  - **While `phase` is `create-plan` or later,** `pd-lint` fails when `shape.md` has changed since. After a move back to `specify` or `design`, the stale plan is expected.
  - **Re-entering `create-plan`** means regenerating the plan, or re-confirming it by updating the hash. Re-confirming is allowed only when the backward move changed nothing the plan cites (no contract or expectation it names), and only after a scoped test-case review re-checks the plan, or the user does; a `review` or `decision` entry records it. Otherwise the plan regenerates.

## A3. The two agent rules, made mechanical

**Rule 1: narrow scope.** The agent definitions enforce it, not the prompts.
- **Tools:** every agent in pd's `agents/` gets a `tools` allowlist.
  - Executors and the fixer get the edit tools.
  - **Reviewers** (the design, test-case, code and security reviewers) get `tools: Read, Grep, Glob`, with no Bash, Edit or Write, so a reviewer can't repair what it finds (principles §10, *Verification is objective execution, not opinion*: keep "the finding and the fix in different hands"). The diff and the gate output arrive as inputs.
  - **Calvin runs as `calvin-runner`,** an agent pd ships (§A6). It runs the user's `calvin` skill and writes the ledger to a file, with `tools: Read, Glob, Skill, Write`. Its `Write` reaches only its ledger path, `agent_sandbox/<date>/<feature id>/calvin-cycle-<n>.md`, which the conductor names in its prompt and, before the dispatch, records as `calvin_ledger` in the session's gate state file (`~/.claude/pd/gate/<session id>.json`, §A5). A `PreToolUse` hook allows `calvin-runner` to write that exact path and nothing else (Part B §9, codex review C5). Whether a subagent's hook input carries the parent session's `session_id` is checked in the bake-off (§A7 item 2). The ledger is raw output: its findings and answers are summarized in a `review` entry (§2, principle 7). `/pd:init` checks that the skill is installed (Part B §12).
  - **QA isn't a reviewer for this rule.** It keeps Bash, since it runs the suites. It may write throwaway probes only under `agent_sandbox/`, enforced by the same `PreToolUse` hook (Part B §9).
  - **The merger** has no `Write` or `Edit`. Its git runs through Bash, which can't be limited by pattern; that is an accepted risk.
- **Inputs:** an executor's prompt carries the contract, its test cases, the proving command and the file set (principles §7, *A task is dispatchable only when it is objectively verifiable*), plus pointers into `shape.md` and `plan.md`. After its test commit it may not touch the test files, meaning the files under `test_paths` that the first commit added or changed; the merger checks. Its result maps each test case to the test that encodes it (`case_map`, D15).
- **Every task runs as a narrow agent, in its own worktree and on its own branch** (§A4), including the small and sequential ones. "Sequential" only means one at a time, after the wave's parallel tasks land; it never means the main session (D15; today's `implementing` skill has the main session do it, `plugins/pd/skills/implementing/SKILL.md:9`). It asks for the minimum code that meets the contract (§A8.3 S3). It never carries file dumps or conversation.
- **Quality bars live in one place:** an agent's `skills` frontmatter preloads its stage's skill ("The full skill content is injected, not only the description"). For example, `design-reviewer` preloads `designing`. Codex can't preload a Claude skill, so the review call's prompt carries the stage's checklist inline: the stage skill reads its own checklist section when it builds the review prompt, at dispatch, so the bar still lives only in the skill (§A4).
- **Integration has an owner** (principles §8, *Executors take a narrow scope; the smartest owns the seams*): in `verify`, the code reviewer's scope is the whole branch diff, and QA drives the flows that cross tasks.

**Rule 2: reviewers have large context and none of the executor's history.**
- **No history, by construction:** "Each subagent starts with a fresh, isolated context window. It doesn't see your conversation history" (code.claude.com/docs/en/sub-agents). Workflow agents are subagents.
  - **The one exception is a fork,** which "inherits the entire conversation so far". A review never runs as a fork.
  - **A skill with `context: fork` is not a fork** of the conversation, despite the name. It runs as a fresh subagent.
- **What a reviewer receives:**
  - **Given, after code:** the artifact set (`shape.md`, `plan.md`), the full branch diff, the gate output, and the executor's report labeled "claims, not evidence: check each at file:line". In Verify, also every task's `case_map` and the merger's list of tests already green at their test commit. The code reviewer checks that each mapped test asserts its case's stated outcome, not a weaker one (D15).
  - **Given, before code:** the design and test-case reviewers receive `shape.md` and `plan.md`, read access to the code, and any prior findings; there is no diff yet.
  - **Never given:** the executor's transcript, or the main session's reasoning.
- **Large context:** "a subagent's context window is sized by its own model, not the parent's". Every model pd pins has a 1M-token window (§A8.4; §A7 item 3 confirms it for a subagent), so the reviewer, QA and retro agents only pin the strongest model and high effort in their `model` and `effort` frontmatter.
  - **"The strongest model"** is the `opus` alias in agent frontmatter, which follows the latest Opus. Changing it to another model is a one-line frontmatter edit.
  - **The Codex reviewer's model and effort** live in the user's CLAUDE.md, which is their home.
- **A reviewer's findings are claims too** (principles §9, *Every claim about the system needs grounding*). The fixer checks each against source before acting. For a wrong one it proposes a rejection with file:line evidence; the conductor records it and puts it to the user. The existing integration script already does the checking.
  - **A rejection is not the last word,** because the fixer works for the author's side. It stays open in `pd-status` until the user accepts it (D13), so the `Stop` gate holds the goal run on it.

**Strength follows consequence** (principles §6, *Thinking goes where being wrong is expensive*: "execution can run on a weaker model, verification cannot"):
- **Executors** run on `sonnet` (the user's ruling, D7), at `effort: medium`. Fix cycles 2 and 3, of executors and of Verify's fixer, run on the strongest model (§A2): the `implement-tasks` and `verify-change` workflows pass `model:` to `agent()` for them.
- **The executor's agent definition keeps a short verification paragraph.** Sonnet 5.5 at low effort "can skip verifying a change" (https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5). The escalated cycles keep it too (§A2). Opus-class agents otherwise get no such instruction, because asking them causes "over-verification". Pruning instructions is per model (§A8.3 S6).
- **Reviewers, QA and retro** run on the strongest model.
- **Set in each agent's frontmatter,** so no prompt has to remember it. The one exception is the escalated fix cycles' model, passed by the workflow (above).

## A4. Who runs what: the conductor and the workflows

**The main session is the conductor.**
- **It owns every decision that needs the user:** the clarifying questions, confirming the criteria, and rulings on escalated blockers. It asks with AskUserQuestion.
- **It writes the files:** frontmatter, `## Now` and `log.md` entries, from each workflow's structured result and the user's rulings (D3).
- **Why not one workflow per feature:**
  - workflows take "No mid-run user input", and the docs' advice is "For sign-off between stages, run each stage as its own workflow" (code.claude.com/docs/en/workflows);
  - a workflow script has "No direct filesystem or shell access"; only its agents do.

**The workflows are the fan-outs.** Each one:
- is a saved plugin workflow in pd's `workflows/`, named so it can't collide with a command (`/pd:implement` exists);
- is started by its stage's skill, never typed by the user: the commands stay the user's entry points;
- takes its args from committed files (Part B §8): `research-fanout` and `rca-fanout` take the question and the brainstorm or rca file; `verify-change` takes the branch, `shape.md` and `plan.md`; only `implement-tasks` derives its args from `plan.md`'s tasks;
- returns structured output only, in a `schema` pinned in its script and restated in one place, `plugins/pd/references/workflow-results.md`:
  - **every result:** `stopped` (null, or `"budget"` when the workflow cap ended the run early, §A5 cap 1), its results so far, which are partial when stopped, `agents_used` and `tokens`;
  - **`implement-tasks`:** `tasks[{id, branch, head, case_map, proof:{first, head, greens, skipped}, cycles, flakes[], status}]`;
  - **`verify-change`:** `review`, `qa`, `fixes[]`, `rejections[]`;
  - **`research-fanout` and `rca-fanout`:** `findings[{claim, evidence, source}]`; each `rca-fanout` finding also carries `verdict: survived | refuted`.

The conductor writes `log.md` from that result; the `run` entry carries each task's fix cycles and the result's `agents_used` (Part B §6).

| Workflow | Stage | Shape | Built from |
|---|---|---|---|
| `research-fanout` | Clarify | Narrow researchers in parallel (`codebase-explorer`, `internet-researcher`, `skill-searcher`, one `advisor` per lens: the `brainstorming` skill's existing advisors), then one synthesizer. Runs only when the conductor judges that a question spans many independent sources, and records why in the `run` entry (§A8.3 S5) | The `brainstorming` skill's research step |
| `rca-fanout` | Clarify, for a bug | One investigator per hypothesis, then a refuter per surviving cause (`rca-investigator` with a refute brief). The report lists every cause with its evidence and verdict. Runs for every bug that reaches Clarify; a bug whose cause is already known goes to express or Criteria instead | `rca-investigator` |
| `implement-tasks` | Execute | Wave by wave, in plan order. Every task runs as one `implementer` in worktree isolation, on its own branch. A wave's `[parallel-safe]` tasks run at the same time, from the feature branch's HEAD at the wave's start ("the base"), and the `merger` agent lands them in plan order. Then the wave's other tasks run one at a time, each from the feature branch's HEAD once the task before it has landed, under the same check (§A3, §A8.3 S5). Then the next wave. Each implementer renames its worktree branch to `pd/<feature id>/task-<n>` before committing, commits tests first and then each meaningful step (§A2), and reports its branch, HEAD and `case_map`. Before a fix cycle, the workflow removes the failed attempt's worktree and keeps its branch; the fix cycle's agent starts in its own worktree and first checks out that branch, named in its prompt. Resume, fix cycles and the merger treat every task alike. Before launching, the conductor checks out the feature branch in the main session's checkout, which `worktree.baseRef: "head"` makes the base. **The merger's check, per task**, is listed below the table | `followups-tasks-capped.js` (the annex's `workflow-scripts/`), with `implement_only` |
| `verify-change` | Verify | The review call beside QA; then up to three cycles of a separate fixer (the `implementer` definition with a fixer brief, as a separate instance) plus a QA re-run, until QA passes and every review blocker is fixed or has a rejection proposed with evidence. The QA re-run checks each new test red on its test commit and green after (§A2). The risk scan and the test-isolation check run once here, over the branch diff (Part B §9). A rejection is a file:line refutation recorded as a `review` entry, and it stays open in `pd-status` until the user accepts it (D13). After code there is no second review, so the conductor puts the open rejections to the user in AskUserQuestion batches of four, the most one call takes, blockers first. Remaining blockers go back to the conductor | `followups-phase-integration-generic.js` (the annex's `workflow-scripts/`) |

**The merger's check, per task** (D13, revised by D14 and D15). It runs through `pd-proof`, which reads only the proving command's JUnit XML, never the test run's console output:
1. **The first commit holds only test files,** plus source additions: new source files, or lines added to existing ones (such as new signatures that raise). On an existing source file the diff is additions only: no existing line changes or goes. The task's paths respect the test-isolation rules (Part B §9).
2. **At the first commit, per test:** each test fails as a test, with no load or collection errors. A test already green there, or skipped, is listed by name: `pd-proof` lists them in its JSON result, and the merger passes the list on to the Verify reviewer.
3. **At HEAD:** every test passes, no test is newly skipped since the first commit, and no commit after the first touches the test files (the files under `test_paths` that the first commit added or changed).
4. **After each merge:** the proofs of every task merged so far are re-run on the feature branch, and `pd-lint` runs (Part B §4.1). A break is a fix cycle in Execute for the task just merged, not a finding in Verify; that cycle gets both its own proof and the earlier proof it broke.

A task the conductor marks `proof: green-only` at Plan, with a reason (`refactor`, `infra` or `fixture`), skips step 2. The test-case review sees the mark.

- **An unexpected result is re-run** before it counts (§A2).
- **A lazy stub is caught by step 2, not by reading it.** No check can tell, across languages, that added source lines are only signatures that raise; so that stays a rule in the brief, and any test the stub makes green is named.
- **A wrong test:** the executor never changes its tests after the first commit; it reports which kind of error it found.
  - **A transcription error** (the case is right, its test code is wrong) restarts the task with a corrected first commit, and the merger re-checks red.
  - **A wrong test case** sends the task back to Plan: `phase` moves back to `create-plan`. Merged tasks stay merged, and tasks not yet run wait; after the plan regenerates, tasks whose contract or cases changed run again.
- **The cycle rule becomes control flow.** One reviewer pass, then up to three fix cycles against runnable checks, then the user (§A2): today that is a prompt rule plus a three-cycle circuit breaker in `implement.md`. In `verify-change` it is the script's shape: a loop bounded at three.
- **Review is one agent call, not a workflow** (D14): Codex first (`codex:codex-rescue`), then one Claude reviewer if Codex fails.
  - **Codex fails** when, per the user's CLAUDE.md, the agent errors, the CLI is unavailable, it times out, or it returns no usable review. It gets one retry at most.
  - **When the user's CLAUDE.md has the Codex reviewer toggled off,** the call goes straight to the Claude reviewer.
  - **The stage's checklist travels in the prompt,** because Codex can't preload a Claude skill (§A3).
  - **Findings** come in the `{approved, issues[], summary}` schema. Each issue carries `{id, severity: blocker | warning | note, category, file, line, claim, evidence}`, pinned in `references/workflow-results.md`.
  - **A scoped re-review** gets the prior findings and the diff since, and returns `{findings: [{id, status: resolved | open | regressed, evidence}], new_in_diff: [...]}`. New findings are allowed only inside the diff's hunks: the conductor mechanically drops any whose file and line fall outside one, so it can't turn into a full review (D15).
  - **Before code, a pass with no blocker ends the stage,** whatever its warnings say. Verify ends only when the review has no open blocker and QA passes. Warnings and optional findings are recorded as notes in the `review` entry; nobody must act on them, and the retro may read them.
  - **Who dispatches it:** the conductor at Contracts and Plan; `verify-change` inside its script. A workflow around one agent would add a launch, an approval and an args file for no fan-out.
- **The security review at finish is not that call.** The `finishing-branch` skill dispatches `pd:security-reviewer` directly, on Anthropic models and never Codex, per the user's CLAUDE.md.
- **There is no separate simplifier step** (the user's ruling, S3). The executor's brief asks for minimum code, and over-engineering is a code-review finding, fixed inside the cycles.
- **The retro needs no workflow.** When a trigger fires (§A8.3 S4), it is one agent, `retro-facilitator`, dispatched by the `retrospecting` skill.

## A5. Long runs: `/goal`, `/loop` and hooks

**`/goal` drives; a script gate decides** (the user's rulings, D7, and "Script gate + real caps" after the Fable review).
- **The gate is a `Stop` hook script, ported from `yolo-stop.sh`.** It reads files for state, and transcripts only to sum usage.
  - **When it acts:** it counts usage on every stop, whether or not a goal runs (cap 3). It blocks only while the feature's `## Now` has a `goal: <feature id> target <phase> session <session id>` line (Part B §5) whose session id matches the hook input's `session_id`. The target defaults to `finish`.
  - **Reaching the target:** for `finish`, the feature is `done`; for any other phase, that phase's exit check has passed and `phase` has moved past it.
  - **Who writes the line:** the conductor, when a goal run starts. It clears the line, and commits, only when the user answers "stop" at any stop, or in the turn where `pd-status` shows the target reached with no open blockers. A hard stop alone doesn't clear it: "continue" keeps the line, and the gate stays armed.
  - **What it checks:** it runs `pd-lint` and `pd-status` itself. It blocks the stop (exit 2) while the feature hasn't reached its target phase, has open blockers, or fails `pd-lint` on its files.
  - **When it lets the goal run end:** the `goal:` line is gone.
  - **At the token cap it blocks, with a question** (D13). Letting the stop through would not end the goal run: `/goal`'s own hook fires beside the gate ("All matching hooks run in parallel") and would start another turn. So the gate blocks (exit 2) with a reason telling the conductor to ask, through AskUserQuestion, "budget spent: continue or stop?". The goal's "or the user has said to stop" clause then ends it. "Continue" writes a `decision` entry raising the feature's budget by `budget_increment` (Part B §12); the gate reads the latest raise.
  - **It yields to background work** (D14). The `Stop` hook's input carries `background_tasks`, whose entries include the types `workflow` and `subagent`; the docs say the array lets hooks "distinguish 'session is done' from 'session is paused waiting for background work to wake it back up'" (code.claude.com/docs/en/hooks). While a `workflow` or `subagent` entry is running, the gate lets the stop through, and the finished workflow run wakes the session. A `shell` or `monitor` entry (a dev server left running) doesn't count, or the gate would yield forever (D15). If the array is absent, the `## Now` line `run in flight:` stands in (Part B §5, §8); the gate ignores one whose session id isn't the current session's.
  - **Why it must yield:** "after stop hooks have continued the turn eight times in a row, Claude Code overrides the next block and ends the turn", and the count "resets each time Claude calls a tool" (same page; `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises it). A gate that blocks while a workflow runs either burns turns polling or gets overridden.
  - **It honours `stop_hook_active`,** as `yolo-stop.sh` does (`plugins/pd/hooks/yolo-stop.sh:185`): when it blocked last time and nothing has moved since, it stops repeating the same block on a condition that will never resolve (code.claude.com/docs/en/hooks). Instead it blocks once more, with the instruction to ask the user "no progress since the last check: continue or stop?" (D15). Letting the stop through would not end a `/goal` run (above), and AskUserQuestion is a tool call, which resets the 8-block count.
  - **"Moved"** means a new commit on the feature branch, or a change to `log.md` or the README, since the previous check. The gate keeps that check's state in `~/.claude/pd/gate/<session id>.json`.
- **`/goal` keeps the session going and shows the spend.** Its "met" verdict no longer ends a goal run on its own. Its evaluator "doesn't run commands or read files independently", so a sentence claiming that `pd-lint` printed 0 errors would satisfy it. The docs name the split: a Stop hook "can run a script for deterministic checks" (code.claude.com/docs/en/goal).
- **What it is:** "a wrapper around a session-scoped prompt-based Stop hook". After each turn, a small model judges the condition: not yet met (keep working), met, or impossible (code.claude.com/docs/en/goal). pd's `yolo-stop.sh` is a hand-built version of the same thing.
- **A goal names the same target as the gate,** so the two agree. For example: `/goal pd-status prints feature 2026-10-15-pd-html as done with no open blockers, or the user has said to stop`.
- **Its hazard, seen in this session:** a goal keeps pushing after a turn that ends in a question. Here, the goal hook kept re-firing after the user chose "Stay paused". So under a goal:
  - **every hard stop is an AskUserQuestion call,** which holds the turn open for the user, never a question in prose at the end of a turn;
  - **every condition ends with "or the user has said to stop",** so the evaluator can see the ruling.
- **Every stop that asks the user falls in one of two groups.**
  - **Hard stops stay hard in every mode** (principles §13, *Stop rather than guess and carry on*). In print mode, a hard stop ends the run with a `handoff` entry:
    - a merge conflict;
    - a cap reached, after its `capped` entry (§A2);
    - a judgement finding with no testable check (§A2);
    - the token cap (above);
    - the stuck path: no progress since the last check (above);
    - a criterion nobody can state as an observable outcome;
    - the criteria sign-off, which is the user's own judgement (§A2 row 2).
  - **Decisions:** in print mode, the conductor makes these on the user's behalf and logs each one (D16). At the workflow cap, that decision is "stop":
    - the rejection batches (§A4);
    - the workflow cap's "continue" (cap 1 below).
- **pd's conductor runs interactively** (D16, the user: "interactive only, when in print mode, any decisions made on user behalf should be logged"). An unattended goal run is an interactive session left running under `/goal`, and a hard stop waits for the user.
  - **In print mode (`claude -p`) nothing can be asked.** Every decision the conductor makes on the user's behalf is a `decision` entry marked "A (conductor, on the user's behalf)" (Part B §6). A hard stop ends the run as above, and `--max-budget-usd` caps it (cap 6 below).
  - **`pd-status` lists the on-behalf decisions** for the user to review (Part B §11).
- **Permissions:** a goal "doesn't change your permission mode". Unattended goal runs use auto mode.
- **`yolo-guard.sh` retires.** Outside hard stops, the conductor asks only about decisions the user owns, so there is nothing to auto-answer.

**Caps on fan-out and spend.** The user's concern, verbatim (2026-10-14): "if we use goal to replace yolo, how do we control the fan out and resources effectively? I find goal tends to use a lot more tokens and agents".
- **Why a goal spends more** (inferred, not measured; the bake-off records the spend, §A7):
  - each "not yet met" verdict starts another turn, with nobody watching in between;
  - the model's defaults take over: Opus 5 "delegates subagents more readily" (https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5);
  - `/goal` shows its spend but has no budget of its own.
- **The caps, strongest first:**
  1. **Fan-out only inside pd's workflows** (§A4), each with a fixed shape. Their token limits:
     - **The turn's target, when the user sets one** ("+500k"): the workflow runtime's `budget` is then a hard ceiling, and further agent calls throw. This comes from the workflow-authoring reference bundled with Claude Code; the public workflows page doesn't document it.
     - **Always, each script's own check, mandatory in every pd workflow** (D13): before starting each agent, the script compares `budget.spent()` with `workflow_output_cap` (Part B §12), passed in its args. When the cap is reached, the workflow run stops early and returns `stopped: "budget"` with its partial results (§A4); for `implement-tasks`, the completed tasks and the unstarted ones. The conductor writes a `run` entry and asks the user: continue, or stop. "Continue" relaunches with the cap raised by `workflow_output_cap` again, recorded in a `decision` entry; the committed config doesn't change.
     - **For goal runs, that check is the only per-workflow-run bound.** Under `/goal`, turns after the first are started by the hook, not the user, and no doc says whether a "+Nk" target carries into them (§A7).
     - **The limits:** both count output tokens only, and an agent that is already running can overshoot. The runtime's "Large workflow" warning doesn't help: it "is advisory: it doesn't pause or limit the run" (code.claude.com/docs/en/workflows).
  2. **Environment caps,** in the project's `.claude/settings.json` `env` block, proposed by `/pd:init` (Part B §12):
     - `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`, so no agent spawns agents;
     - `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` and `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`, which cap how many run at once, not the total (code.claude.com/docs/en/env-vars). They keep their defaults unless the user sets them.
     - **No native cap limits the total number of agents:** `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION` was "Removed in v2.1.224 and now a no-op". So the conductor dispatches only two kinds of agent work: pd's workflows, whose fixed shapes set the count, and the single named agents a playbook names (`calvin-runner`, `codebase-explorer`, `internet-researcher`, the review call, `security-reviewer` and `retro-facilitator`). Any other delegation breaks a conductor rule; no mechanism blocks it. (D14 cut the agent-spawn counter hook: workflow agents may not pass through the `Agent` tool it would watch.)
  3. **A token cap in the gate:** the `Stop` gate totals usage over every transcript in the session, not just the main one: workflow and subagent transcripts are separate files (D14). Past `feature_token_budget` (Part B §12), it blocks with the "budget spent: continue or stop?" instruction above. It is ported from `yolo-stop.sh`'s `yolo_usage_limit`, with two corrections (D15):
     - **The measure:** `input_tokens + output_tokens + cache_creation_input_tokens` from each entry's `message.usage`, cache reads excluded. It stands for the work processed fresh in each call; cache reads re-read the same context and would swamp it. `yolo-stop.sh:44-55` sums a top-level `usage` that today's transcripts don't have (this session's main transcript: 0 top-level, 8,346 under `message`), so a straight port counts zero; and counting cache reads would multiply the total roughly a hundredfold.
     - **Per feature, not per session:** on every stop, whether or not a goal runs, the gate charges the session's usage since its previous count to the feature whose branch is checked out (the README's `branch:`). It blocks only while a matching `goal:` line exists (above).
     - **Carried across sessions in a file:** no step reliably runs at session end, so each time it fires, the gate writes the running per-feature total to `~/.claude/pd/gate/<repo key>/<feature id>.json`, where the repo key is a hash of the repository's `origin` URL, or of its path when it has none, since feature ids are unique only within one repository (codex review C14), beside the feature's original budget (Part B §9). The next session continues it, and finish copies it into the `metrics` entry. Whether a `SessionEnd` hook could do this is on the bake-off list (§A7).
     - **Between turns only:** the gate fires between turns, so one turn's workflow run can overshoot it; cap 1 bounds that turn.
  4. **Model and effort per agent:** executors on `sonnet`; the strongest model runs the verifiers, the retro, and cycles 2 and 3 of executors and fixers (§A3).
  5. **One goal per feature,** never one for a whole roadmap.
  6. **For print-mode runs:** `claude -p --max-budget-usd` is the only cap on all spend, because "Spend from subagents counts toward the cap". It works in print mode only (code.claude.com/docs/en/cli-reference).
- **Where the budgets live:** `.claude/pd.local.md`'s `workflow_output_cap`, `feature_token_budget` and `budget_increment`, with their defaults (Part B §12).

**`/loop` is for polling, not for driving stages.**
- **Use it to watch outside state:** a CI run, or a long workflow running in the background.
- **Don't drive stages with it:** scheduled prompts stop when the session ends ("Closing the terminal or letting the session exit stops them firing"), and recurring ones "automatically expire 7 days after creation" (code.claude.com/docs/en/scheduled-tasks).
- **A roadmap runs one goal per feature,** so each goal run's spend stays bounded. Between features, the conductor reads `pd-status`'s next ready item and prints the next `/goal` command, and the user starts it. Whether Claude can start a goal itself is on the bake-off list (§A7). Across sessions, `## Now` and that next ready item are the resume point (Part B §8 and §7.1).

**Hooks hold the mechanical checks and the session-start summary.** `PreToolUse` on `git commit` runs `pd-lint`, and exit 2 blocks (Part B §9).

**Considered, and not used:**
- **Agent teams:** "experimental and disabled by default", with "No session resumption with in-process teammates". Teammates also message each other directly, which works against reviewer independence (code.claude.com/docs/en/agent-teams).
- **`SubagentStop` and `TaskCompleted` gates:** both can block with exit 2. The workflows' output schemas, and the merger running each proving command, already cover what they would check.

## A6. Every pd component: kept, replaced or retired

**Kept, rewritten onto native features:**
- **The phase skills** (`brainstorming`, `specifying`, `designing`, `planning`, `implementing`, `finishing-branch`, `retrospecting`, `root-cause-analysis`, `workflow-transitions`): they become the conductor's playbooks. Their MCP calls become file reads and writes (Part B), and `implementing` loses its hand-run worktree steps.
  - **Plus one new phase skill, `verifying`:** it starts `verify-change` and writes the stage's entries.
- **The `updating-docs` skill,** which publishes artifacts to the human docs (Part B §3, §3.1).
- **The commands this section names or a kept playbook calls,** `/pd:secretary`'s triage among them: thin entry points, as they are now. The §16 inventory lists them. They stay the user's entry points; the stage skills start the workflows, which users don't type (§A4).
- **19 of the 24 agents:** the same roles, with `tools`, `model`, `effort` and `skills` frontmatter per §A3. S2 retires `prd-reviewer`, `relevance-verifier` and `test-deepener`; D18 deletes `project-decomposer` and `project-decomposition-reviewer`, with the `decomposing` skill and `/pd:create-project`. `plan-reviewer` stays, as the Claude fallback for the Plan stage's test-case review (D14).
  - **Two kept agents take a second brief:** `implementer` plays the fixer, as a separate instance, and `rca-investigator` the refuter.
  - **Plus two new agents:** `merger`, which runs git and `pd-proof`, and `calvin-runner`, which runs calvin at Criteria; §A3 sets their tools. So: 19 kept plus 2 new.
- **The backlog:** a file (Part B §7). The knowledge bank is frozen as a read-only archive (§A8.3 S4).

**Replaced by a native feature:**

| pd today | Native replacement |
|---|---|
| `/pd:yolo`, `yolo-stop.sh`, `yolo-guard.sh` | `/goal` to drive, a script `Stop` gate to decide, auto mode and the caps (§A5). The gate and its token cap are ported from `yolo-stop.sh` |
| Hand-run worktrees in `.pd-worktrees/`, the workaround for CC Issue #33045 | The workflow's `isolation: 'worktree'`, with the `worktree.baseRef: "head"` setting. Without it, a subagent's worktree branches "from your repository's default branch", not the feature branch (code.claude.com/docs/en/worktrees) |
| The review gate and the three-cycle circuit breaker in `implement.md` | `verify-change`'s bounded loop (§A4) |
| Codex routing, `plugins/pd/references/codex-routing.md` (its per-command preambles were dropped in 2026-07, `validate.sh` FR-2b) | One review call, Codex first (§A4) |
| Resuming through the engine | `claude --resume` in the same session; otherwise `## Now`, with the workflow's args re-derived from the committed files (Part B §8) |

**Replaced by files and scripts (Part B):**

| pd today | Replacement |
|---|---|
| The workflow engine, the entity registry and the MCP servers (`transition_phase`, `complete_phase`, phase events) | Frontmatter, `log.md`, `phase-gate.sh` and `pd-lint` |
| The reconciliation orchestrator and the doctor | `pd-lint`, which takes over the doctor's role (a health check at every commit), but none of its database checks |
| `session-start.sh` | A short `SessionStart` summary (Part B §9) |
| `/pd:show-status`, `/pd:list-features`, `/pd:show-lineage` | `pd-status` |
| `allocate_entity_id` | `pd-new` |

**Retired, by the user's ruling:**
- **The Kanban UI** (`plugins/pd/ui`, `start-ui-server.sh`).
- **Cross-workspace queries.** claude-mem covers recall across projects.

**`pre-exit-plan-review.sh` retires** (`plan-reviewer` itself stays, D14). The hook and CLAUDE.md's "Plans from any source" rule are covered by the user's global rule: calvin any agent-written plan before executing it.
- **Not covered:** a plan the user writes by hand.
- **Where that global file is absent,** nothing replaces the hook. Both are accepted risks.

**Everything this section doesn't name is settled by an inventory,** at the start of the build (§16 step 3). It lists every skill, command, agent and hook with its verdict.
- **The rule (D17):** a component is kept if the new design uses it. Everything else is deleted straight away, in one commit the user reviews (§16 step 3), and git history keeps it.
- **The remaining hooks are decided there the same way,** each on its own. Those that may stay include the commit, push and unicode guards.

## A7. What the bake-off must prove

These rest on documentation, not on a run. The bake-off (§16, step 6) settles each one.
- **Two kinds of item:** most are checks, which pass or fail. Those marked **Question** record an answer; their stated fallback applies until then. Passing means every check passes and every question is answered.
- **A check whose event doesn't occur naturally** (a hard stop, re-runs that disagree, the token cap) is provoked by a probe, and recorded as such: a scripted AskUserQuestion hard stop, a deliberately flaky fixture, or a small `feature_token_budget` for one probe run (item 6).
- **If an item fails,** the rollout stops there: its plan section is revised and calvin'd, and the user decides.

1. **Worktree isolation works on the feature branch:** with `worktree.baseRef: "head"`, an `implement-tasks` task's worktree starts from the feature branch's HEAD, and the merger can merge its commits. The docs don't name a subagent worktree's branch, so the implementer renames it and reports it with its HEAD (§A4).
2. **A plugin agent's frontmatter holds:** `tools`, `model`, `effort` and `skills` apply when a workflow names the agent through `agentType`. Also: a subagent's hook input carries the parent session's `session_id`, which the agent write hook relies on (§A3). (Plugin agents ignore `hooks`, `mcpServers` and `permissionMode`, per the docs.)
3. **A pinned reviewer model really gets the 1M-token window:** every model pd pins has one, and the docs say "For every model with a 1M-token context window, 1M is the default" (§A8.4); the bake-off confirms it holds for a subagent.
4. **A `/goal` run stops at a hard stop:** an AskUserQuestion holds it, and "the user has said to stop" ends it.
5. **The task list is available:** the docs provide it by default only on "Opus 4.7, Sonnet 4.6, Haiku 4.5, and earlier models"; any other model needs `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` (code.claude.com/docs/en/interactive-mode). This session runs Opus 5.5 and has no task tools. What pd loses without it is in Part B §8.
6. **Spend stays inside the caps** (§A5):
   - the bake-off feature's tokens and agent count are recorded, the count summed from its `run` entries' `agents_used` (§A4). They decide nothing (D17);
   - **Question:** whether a `SessionEnd` hook could write the session's total, beside the gate's per-feature file (§A5, cap 3);
   - the gate's token total includes the workflow agents' transcripts. The `subagents/` directory is documented ("`~/.claude/projects/{project}/{sessionId}/subagents/`", code.claude.com/docs/en/sub-agents); its `workflows/<run id>/` sub-layout, seen on this machine on 2026-10-14, is not;
   - the gate yields while a workflow runs in the background, so it neither polls nor hits the 8-block override (§A5);
   - the `Stop` gate blocks a stop while `pd-status` shows open blockers, even after `/goal` judges the condition met;
   - **the gate ends a goal-driven run at the cap:** at the token cap, its AskUserQuestion instruction stops the run while `/goal` still judges the condition unmet. One probe run with a small `feature_token_budget` shows it; the main bake-off run keeps no feature budget;
   - **Question:** whether a "+Nk" turn target carries into turns the `/goal` hook starts (§A5, cap 1). Fallback: each workflow's own `budget.spent()` check.
7. **The merger's per-task check holds** (§A4), through `pd-proof` on the project's runner: the first commit fails per test with no load errors; HEAD passes; no later commit touches the tests; merged proofs re-run after each merge; an unexpected result is re-run, with a third run deciding a disagreement, and logged. Also check that `agentType: codex:codex-rescue` works inside a workflow script, for `verify-change`'s review call (unverified).
8. **Auto mode lets workflow agents work unattended:** "the prompt your script passes to `agent()` doesn't count as a request from you when the classifier reviews that subagent's actions" (code.claude.com/docs/en/workflows). The allow rules `/pd:init` proposes (Part B §12) must let the merger merge, remove worktrees and run the tests in a goal run nobody watches.
9. **Question, who starts the next goal:** whether Claude can start a `/goal` itself. Until that is shown, the conductor prints the command and the user starts it (§A5).
10. **Resume and escalation work** (codex review C13), shown by a probe:
    - **resume:** a run with one task finished and one interrupted, its worktrees removed, then resumed in a fresh session, merges the finished task once and runs only the remaining one;
    - **escalation:** a task that fails its check twice reuses its branch, and its cycle 2 runs on the strongest model.

## A8. The method, reviewed against today's models

**The user asked (2026-10-14):** "objectively review my problem solving workflow and review it against the latest model capabilities and see if there is anything that can be simplified or consolidated."

**How it was reviewed:** each principle is sorted by why it holds.
- **Structural:** it holds whatever the model, because it follows from how agents and documents work.
- **Compensating:** it makes up for a model weakness, so it should relax as models improve.
- **Where each lands:**
  - **Structural:** §1, *Every stage kills a named class of unknown*; §2, *Entry depth matches the uncertainty that arrived*; §3, *Behaviour before architecture*; §14, *Lessons become checks, not prose*; and §8, *Executors take a narrow scope; the smartest owns the seams*, because parallel agents can't share context.
  - **Compensating:** §6, *Thinking goes where being wrong is expensive*. It exists because weaker models are cheaper, and weaker.
  - **About the method itself:** §15, *Some rules are scaffolding*.
  - **The rest:** placed by the tables below.

The evidence is this repository's own record, plus the sources cited inline.

### A8.1 This repository's record (measured 2026-10-14 on develop at `97b3470a`)

**How to re-run the figures:** line counts are `wc -l` over the named paths; commit counts are `git log --oneline 97b3470a --since=2026-07-01 -- <paths>`.

- **The gates caught every recorded occurrence; whether the rules prevented others can't be seen.** CLAUDE.md's record of the half-sweep defect class reads "100% gate-caught / 0% prevented", over seven occurrences. Each was a fact restated in several places with one copy left stale; feature 126's crossed from `plan.md` back into `design.md`. A prevented defect leaves no record, so the figure can't show prevention.
- **The machinery took most of the commits.** Of 504 commits on develop since 2026-07-01, 229 touched the state machine's code (`plugins/pd/hooks/lib`, `mcp`, `ui`), and 32 touched skills, commands or agents. Commit count is a proxy for effort.
- **Planning documents ran to about a third of the lines written.** Phase R's design, inventory and playbook run to 6,053 lines, and its task briefs to 1,671 more, against a change of +15,020/−9,093 lines across 155 files and 95 commits. It was still unfinished after three weeks. This is context for S1, which the user rejected.
- **The user cut the review cadence mid-campaign:** from a review and QA per task, to one per milestone (2026-10-13).
- **Retro output in the knowledge bank goes unread; the part that reached CLAUDE.md is read.**
  - **The knowledge bank:** about 2,500 lines, described in CLAUDE.md as "inert reference markdown (no tooling reads/writes it)". It has had one commit since 2026-07-01.
  - **CLAUDE.md, which is read:** 2,961 words loaded into every session. Of those, 1,114 are retro-derived guardrails and 709 are registry gotchas.
- **pd has been switched off since 2026-09-24.** This campaign ran on native workflows and hand-kept files the whole time. What it missed was resuming across sessions, which the handover documents covered by hand. That is Part B's job.

### A8.2 What holds whatever the model

| Principle | Why it is structural |
|---|---|
| **§4, *Contracts are the hand-off boundary between agents*** | Parallel agents can't talk to each other, however capable. What they agree on has to be written down first |
| **§5, *One fact, one home*** | Restatement drift is a property of documents, not of models. The half-sweep record above is this repository's proof |
| **§7, *A task is dispatchable only when it is objectively verifiable*; §11, *More review is not better; every loop gets a budget*** | The executor doesn't author its proof, and review is independent: a model judges its own output less reliably than someone else's (sources in §A8.4) |
| **§10, *Verification is objective execution, not opinion*** | A run is evidence whatever the model's confidence |
| **§12, *Going back should be normal*; §13, *Stop rather than guess and carry on*** | These are properties of the process, not of the model |
| **§9, *Every claim about the system needs grounding*** | Still needed. It has become cheap: CodeGraph and LSP answer "does this exist?" in one call |

### A8.3 What compensates, and can be simplified

**S1. Merge Criteria, Contracts and Plan into one Shape phase.** **Rejected** by the user, 2026-10-14: "separate out planning from the design stage. I think they are two distinct angles to solving the problem." Then "Keep all three" (later amended by D11: a small feature may write Contracts and Plan in one sitting, §A2): Criteria, Contracts and Plan stay three phases, and `plan.md` keeps its `from_shape:` check. The proposal is kept below as a record.
- **Today:** three phases (`specify`, `design`, `create-plan`), two files (`shape.md`, `plan.md`), and a staleness check between them (§A2).
- **Proposed:** one `shape` phase writing one `shape.md` with three sections: `## Criteria`, `## Contracts` and `## Tasks`.
  - **Every class of unknown still gets resolved before execution,** each with its own section check in `phase-gate.sh`. Principle §1, *Every stage kills a named class of unknown*, names a stage by the unknown it kills; three unknowns can be killed in one stage.
  - **The user's sign-off on the criteria stays a stop** inside the phase, before any contract is written. So the order behind principle §3, *Behaviour before architecture*, holds.
- **Why it's safe now:** the plan is derived from the contracts; the `planning` skill already says it is "regenerated whenever the design moves". A model with a 1M-token window writes all three in one pass with the code in view.
- **What it removes:**
  - the `create-plan` phase, `plan.md` and the `from_shape:` check;
  - the second artifact that the half-sweep defects kept crossing.
- **The phase list becomes:** `brainstorm | shape | implement | verify | finish`.

**S2. Independent reviews only at fixed moments (three; four since D14)** (principle §11, *More review is not better; every loop gets a budget*: "review where being wrong is most expensive"). **Adopted:** "Three, plan by lint".
- **Amended by D14:** Plan now holds the test cases, which take judgement, so it gets a review again; its Claude fallback is `plan-reviewer`. A standard-depth feature meets four review moments: calvin at Criteria, the design review, the test-case review and the code review. Security at finish is added when the feature is tagged. The three before code each get up to three scoped review-revise cycles (§A2).
- **Today:** a standard-depth feature can meet the PRD reviewer, calvin, the design reviewer, the plan reviewer (through the plan-mode hook), the relevance verifier, the code reviewer, the test deepener and the security reviewer.
- **Proposed:**
  1. **Before build:** calvin in report mode on the criteria, with the PRD or RCA report they derive from, in the Criteria phase, and the design reviewer (Codex first) on the contracts, in the Contracts phase. Since S1 was rejected, they run in separate phases. They catch different failures: calvin finds what an implementer would have to guess, and the design reviewer finds decisions that are wrong against the code.
  2. **After build:** the code review, beside QA, in `verify`.
  3. **At finish, only for a security surface:** the security reviewer.
- **Reviewers flag only what affects correctness or the stated criteria, plus over-engineering (S3).** The rest is optional, never enters the fix cycles, and is recorded as notes in the `review` entry (§A4). Claude Code's docs warn that a gap-hunting reviewer "will usually report some, even when the work is sound", and that "Chasing every finding leads to over-engineering" (§A8.4).
- **No ad hoc double-checks inside execution.** Independent review happens at these moments only (four since D14). Anthropic's Opus 5 guidance says "do not use subagents to verify or double-check your own work", while its Fable 5 guidance says fresh-context verifiers "tend to outperform self-critique". On our reading, both hold when review is placed deliberately rather than scattered.
- **What it drops:**
  - ~~**the plan reviewer**~~ (superseded by D14: it stays as the test-case review's fallback). `pd-lint` still checks the plan mechanically: each task's proving command and file set, disjoint `[parallel-safe]` sets, and `from_shape:` (Part B §9);
  - **the relevance verifier,** covered in part twice over: the `from_shape:` check catches a design that changed after the plan was derived, and the test-case review catches a plan that never matched it;
  - **the PRD reviewer on promoted brainstorms:** calvin covers it;
  - **the test deepener:** hunting for what no criterion named is QA's job (principle §10, *Verification is objective execution, not opinion*).

**S3. Simplification becomes a brief and a review lens, not a separate step.** **Adopted:** "Brief + review lens".
- **Before:** an earlier pd design had a simplifier agent edit the finished change, then re-ran the gates. Today's `implement` has no such step (`plugins/pd/commands/implement.md`); the proposal keeps it out.
- **Proposed:**
  - **the executor's brief asks for the minimum code** that meets the contract;
  - **over-engineering becomes a finding category** in the code review, fixed inside the fix cycles (§A2).
- **Why:** a separate simplifier makes an unreviewed behavior change, and costs another agent and another gate run. Preventing the excess in the brief is cheaper than removing it afterwards.

**S4. Retros by trigger, with lessons landing where they are read.** **Adopted:** "On trigger, lessons routed".
- **A full retro runs only on a trigger:** a second backward move in the feature, a defect found after merge, fix cycles exhausted, or a cost overrun (the feature's tokens pass its budget). Part B §9 names the entry `pd-lint` reads for each. One backward move is not a trigger: principles §12, *Going back should be normal*, says going back must be cheap. (Revised after the Fable review, 2026-10-14.)
- **Otherwise** the feature gets one `note` entry in `log.md`.
- **A lesson lands where it acts:** a `pd-lint` or hook check if it can be checked, otherwise one line in the CLAUDE.md of the project where the feature ran, or an edit to the skill. A lesson about pd itself goes into pd's skill. It never goes to the knowledge bank, which is frozen as an archive.

**S5. Fan out only when it pays.** **Adopted:** "Only when it pays".
- **Research:** Clarify runs in the main session with at most one researcher, `internet-researcher` or `codebase-explorer`. The `research-fanout` workflow, with its advisor lenses, runs only when a question spans many independent sources. A bug's `rca-fanout` is not bounded this way (§A4).
- **Execution:** the `implement-tasks` workflow runs tasks at the same time only when the conductor marked them `[parallel-safe]`, which it does only for a task big enough for running in parallel to pay. Everything else runs one task at a time, each in its own worktree, never in the main session (§A3, §A4, D15).
- **Why:** multi-agent systems "use about 15× more tokens than chats" (a direction, not a measure for pd; the bake-off measures), and "most coding tasks involve fewer truly parallelizable tasks than research". Opus 5's guidance: delegation "multiplies cost and time when applied to small tasks" (§A8.4).

**S6. Prune CLAUDE.md and the skills.** **Adopted:** "Staged prune". The user reviews the prune diff before it lands.
- **The 709-word registry section** goes with the registry.
- **Each remaining guardrail** either becomes a `pd-lint` check or a line in a reviewer's checklist, or stays in at most two lines.
- **The skills lose prescriptive steps** the model now does unprompted. This is per model: Opus-class agents lose self-verification instructions, while the Sonnet executor keeps one in its agent definition, which its escalated cycles keep too (§A3). Either way, the proof that counts runs outside the executor, in the merger.
- **Why:**
  - instructions are context, "not enforced configuration" (Part B §2), and in the record above the gates caught every recorded occurrence, while whether these rules prevented others can't be seen;
  - "Skills developed for prior models are often too prescriptive" (Fable 5 guidance), and asking Opus 5 for verification steps causes "over-verification" (§A8.4).

**The rulings (D8, 2026-10-14):** S1 rejected; S2 to S6 adopted, and §A2 to §A6 now reflect them. Asked about S3, the user also ruled on fix cycles (§A2).

### A8.4 Sources on today's models

Gathered 2026-10-14. Every quote was matched against the fetched page text. The downloads were session scratch and are not kept, so each source is cited by its full URL (the author's call, D16).

**What changed, and what it relaxes:**

| Capability | Evidence | What it relaxes |
|---|---|---|
| **1M-token context is the default** | "For every model with a 1M-token context window, 1M is the default" (platform.claude.com/docs/en/build-with-claude/context-windows) | Splitting reviews to fit a window: reviewers read the whole artifact set and the diff in one pass |
| **Long autonomous runs** | Opus 5.5 "sustains long-running autonomous work better than Claude Opus 5" (https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5). METR's 50% time horizon doubled about every 7 months over six years, and every 89 days since 2024 under its TH1.1 measure (metr.org/blog/2026-1-29-time-horizon-1-1) | Hand-holding inside a stage. Each stage may be one long run; untested for Claude 5 |
| **Self-verification built in** | "Claude Opus 5 verifies its own work without being told to"; verification prompts "cause over-verification" (https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5) | Verification instructions for Opus-class agents (S6). The Sonnet executor keeps its paragraph, because Sonnet 5.5 "can skip verifying a change" (§A3) |
| **Better instruction following** | Fable 5 "can steer most behaviors with a brief instruction"; "Skills developed for prior models are often too prescriptive" (https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5) | Long prescriptive skills (S6) |

**What hasn't changed, and still needs the method:**

| Weakness | Evidence | Principle it keeps |
|---|---|---|
| **Unrequested scope** | Sonnet 5.5 "tends to add tests, documentation, and small supporting files"; Fable 5.1 "may fix nearby code, extend behavior the task didn't mention" (https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1) | §7, *A task is dispatchable only when it is objectively verifiable*: its bounded file set; S3's minimum-code brief |
| **Claiming done without running a check** | Sonnet 5.5 "sometimes reports a change as done without running a check that exercises it" (https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5) | §10, *Verification is objective execution, not opinion*: the proving command runs outside the executor |
| **Self-judgment** | "an LLM evaluator scores its own outputs higher than others'" (Panickssery et al. 2024, arxiv.org/abs/2404.13076); "LLMs struggle to self-correct their responses without external feedback" (Huang et al. 2023, arxiv.org/abs/2310.01798) | §7, *A task is dispatchable only when it is objectively verifiable*, and §11, *More review is not better; every loop gets a budget*: independent review |
| **Feedback quality bounds repair** | Self-Debug with unit tests "improves the baseline accuracy by up to 12%", and without them by 2–3% (arxiv.org/abs/2304.05128) | §10, *Verification is objective execution, not opinion* |
| **Iteration** | Self-Refine reports "diminishing returns" as iterations increase (arxiv.org/abs/2303.17651) | §11, *More review is not better; every loop gets a budget*: budgeted loops: scoped re-review before code, one pass after; fixes bounded at three cycles, checked by runs (§A2) |

**What the guidance says about process weight:**
- **Planning:** "If you could describe the diff in one sentence, skip the plan." Planning "is most useful when you're uncertain about the approach" (code.claude.com/docs/en/best-practices). That is the entry-depth rule of principle §2, *Entry depth matches the uncertainty that arrived*.
- **Simplicity:** "finding the simplest solution possible, and only increasing complexity when needed" (anthropic.com/engineering/building-effective-agents).
- **Verification:** "Give Claude a check it can run"; "If you can't verify it, don't ship it" (code.claude.com/docs/en/best-practices).
- **Fan-out cost:** "multi-agent systems use about 15× more tokens than chats", and "most coding tasks involve fewer truly parallelizable tasks than research" (anthropic.com/engineering/multi-agent-research-system).

**Limits of this evidence:**
- **METR has published no time horizon for any Claude 5 model.** Its tracker "is no longer actively updated", and it rates measurements above 16 hours as "unreliable".
- **The self-correction and iteration papers predate 2025.** Applying them to Claude 5 is an extrapolation.
- **No published figure measures the gain from planning first.** The guidance is qualitative.

## A9. What pd can do that the native tools can't, and whether to keep it

**The user asked (2026-10-14):** identify what pd built that Claude Code's native tools can't easily preserve, and assess whether any of it must be kept: "I suspect most of them not."

**The finding: nothing needs to be kept as machinery.** Three small behaviors are worth keeping, each a script or a short hook: `phase-gate.sh`, `pd-status`'s blocker flag, and the `Stop` gate with its token cap, ported from `yolo-stop.sh` (D7). The user ruled "Retire all" (D9). The evidence, gathered on develop at `97b3470a`, is below.

**What the new machinery should weigh:** the new scripts are expected at roughly 1–2k lines. The build records the lines it adds and stops for a review with the user past 5k (§16 step 4), so it can't quietly re-grow what §A1 retires.

**Already unused: 22 of the 43 MCP tools have no caller.** No pd command, skill, agent, hook script or reference names them:
- **Entity extras:** `issue_spawn`, `export_lineage_markdown`, `delete_entity`, `add_entity_tag`, `get_entity_tags`, `add_dependency`, `remove_dependency`, `search_entities`, `list_projects`;
- **OKRs:** `add_okr_alignment`, `get_okr_alignments`, `create_key_result`, `update_kr_score`;
- **Workflow extras:** `reconcile_frontmatter`, `reconcile_status`, `init_feature_state`, `transition_entity_phase`, `get_notifications`, `promote_task`, `query_ready_tasks`, `get_progress_view`, `query_phase_analytics`.

**Exists only because state lived in a shared database:** these retire with it, and nothing replaces them.
- **Workspace identity and the uuid re-key** (Phase R);
- **Migrations, SQLite lock recovery** (`cleanup-locks.sh`) **and the migration lock**;
- **Reconciliation** between the database and `.meta.json`;
- **The doctor's checks** that guard the database's single write path;
- **The data-file guards,** which stop direct writes to `.meta.json` and `docs/backlog.md` because those were projections. Under Part B, the files are the truth, and `pd-lint` guards them.

**Real capabilities with no exact native equivalent:**

| Capability | What native gives instead | The loss | Keep? |
|---|---|---|---|
| **Transition-time enforcement:** the engine refused to enter a phase whose prerequisites were missing (`transition_gate`: 43 guards) | `phase-gate.sh` run by the skill before it moves `phase:` past a phase, and by `pd-lint` at every commit for the phases already passed (Part B §9). Each of the 43 guards is mapped to one of them, or dropped, at build time (§16 step 4) | Work done out of order is caught at commit, not at the moment the phase starts; and any guard the mapping drops | **No.** Nothing is done until it is committed, so the commit is the moment that matters. Keep `phase-gate.sh` (3 KB, already a script) |
| **Queryable history:** phase timings, iteration counts and reviewer notes as rows, with `query_phase_analytics` | `log.md` and git timestamps | No SQL across features | **No.** The analytics tool has no caller, and the retro reads `log.md` |
| **Autonomy that checks real state:** `yolo-stop.sh` read the feature's recorded state, and sent Claude back while reviews were unapproved | `/goal`, whose evaluator sees only what the session printed | The evaluator could be fooled by a claim in prose | **Keep it,** as the script `Stop` gate (§A5). It runs `pd-lint` and `pd-status` itself; `/goal` only drives |
| **A token budget for autonomous runs** (`yolo_usage_limit` in `yolo-stop.sh`) | `/goal` shows the token spend, and pauses on a usage limit or rate limit; it has no budget of its own | No hard cap on spend for an unattended goal run | **Yes, as a hook** (the user's ruling, D7): a `Stop` hook reading the transcript's usage, ported from `yolo_usage_limit` (§A5) |
| **Dependency-aware picking of the next feature** (`yolo_deps.py`) | A plan's `roadmap:` with `after:`, and `pd-status`'s next ready item (Part B §7.1) | None | Replaced in this design by the roadmap and `pd-status` |
| **Cross-project views, lineage and roll-ups** (across every workspace: `get_lineage`, `rollup.py`) and **the Kanban UI** | claude-mem for recall across projects | The views themselves | **No:** the user's ruling (§A1) |
| **Asking the user mid-pipeline:** pd's commands ran in the main session, so any step could ask | Workflows take no mid-run input, so the conductor asks between workflows (§A4) | None, by that design | Replaced in this design by the conductor asking between workflows |
| **Session-start orientation:** `session-start.sh` (670 lines) printed the active feature, its phase and the next command, ran the doctor and started the UI | A `SessionStart` hook printing `## Now` and each plan's next ready item (Part B §9) | The doctor run and the UI | **No:** both retire |
| **Triage logic in Python** (`secretary_intelligence.py`) | The `/pd:secretary` rules, judged by the model | Deterministic mode detection | **No.** The rules are a short list for the model to apply. How reliably it does is not measured; the bake-off and the `metrics` entries will show misroutes |
| **Referential integrity:** foreign keys, cascades, and parents that block deletion | `pd-lint`'s link checks | Integrity is checked at commit, not enforced on every write | **No** |

**Not in scope here:** the domain skills (data science, crypto analysis, game design, promptimize, specialist teams). They don't depend on the registry, so they port as they are, or are pruned by the user at S6's prune, using session-history usage counts.

---

# Part B: the artifact SOP

## 1. Why the SOP is needed

**Measured on 2026-10-14,** in pd's four active projects (pedantic-drip, fractorg, project_illium, cast-below). Only these four adopt the SOP; the registry's other workspaces stay in its read-only archive (D5).

| Finding | Evidence |
|---|---|
| **pedantic-drip keeps no state in git** | `.meta.json` and `docs/backlog.md` are gitignored projections of the database (`.gitignore:68-69`). Only 23 of its 153 feature directories even have a `.meta.json` on disk. Without the database, its state is gone. |
| **The other projects track `.meta.json`, but it disagrees with the database** | fractorg: 56 `.meta.json` say completed, while the database has 0 completed. project_illium uses 11 different status words (memory note, 2026-09-18). |
| **The artifact sets have drifted** | The old set is `spec.md`, `design.md`, `plan.md`, `tasks.md` (145/138/137/139 of pedantic-drip's dirs). The gate now checks `shape.md` and `plan.md` (`scripts/phase-gate.sh`). Some dirs also hold `prd.md`, `verdict.md`, `review.md`, `.review-history.md`, `.qa-gate.json` or `implementation-log.md`. |
| **Project tracking goes stale, project planning doesn't** | Registry, read-only: 16 projects, and 114 of 271 features belong to one. But 13 projects still say `active`, only 2 were ever completed, and 5 "active" ones have no features. pedantic-drip has two folders for the same initiative under two id schemes (`005-iflow-arch-evolution` and `P001-iflow-arch-evolution`). Meanwhile its four roadmaps hold about 420 lines of real planning. |
| **Native workflows can't resume across sessions** | "In a session you start fresh, Claude has no earlier run to relaunch and starts the workflow over as a new run" (code.claude.com/docs/en/workflows). The resume point has to live in files. |

**What this SOP has to make true:**
- **Comprehensive:** every fact a session needs to resume lives in git, and so do the audit facts from finish on, when the `metrics` entry copies the gate's token total in (§6). The task list, scratch args, the gate's state files and `init-declined` are conveniences, and can be lost.
- **Consistent:** one layout, one schema and closed vocabularies in every project, all checked by a script.
- **Easy to manage:** two control files per feature (`README.md` and `log.md`) and one per single-file item (the file itself), one lint command and one status command.

---

## 2. Principles

1. **Committed files are the only source of truth.** Every view (the status table, plan progress, counts) is computed from the files and is disposable.
2. **One fact, one place.** Status lives only in the item's frontmatter. History lives only in its `log.md` (a single-file item's `## Log`) and in git. A plan's membership and order live only in its `roadmap:`. Nothing restates any of them. pd's #074 restatement class is the reason.
3. **Derive, don't sync.** Progress, "what's next" and a plan's completion are computed, never stored. That is how trackers do it: GitHub shows "sub-issue progress" in Projects. With nothing stored, agents can't forget to update it.
4. **Closed vocabularies,** checked by the linter. A word outside the list fails the commit.
5. **Artifact and state rules are enforced by scripts and hooks, not by prompts.** Claude Code's docs say instructions are context, "not enforced configuration"; a `PreToolUse` hook blocks with exit code 2. The one stated exception is the conductor's delegation rule, which no mechanism blocks (§A5, cap 2).
6. **Use Claude Code's built-ins before building anything:**

   | Need | Built-in used |
   |---|---|
   | Step-by-step progress within and across sessions | The task list. Launch with `CLAUDE_CODE_TASK_LIST_ID=<item id>` to share it across sessions; it is stored in `~/.claude/tasks/`. On models newer than those the docs list, it also needs `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` (§A7). |
   | Continuing an interrupted workflow run | `claude --resume` of the same session, which replays the run's saved results |
   | Running unattended to a stated end | `/goal` under pd's caps, which replaces YOLO mode (§A5) |
   | Orchestration | Saved plugin workflows, skills, subagents (§A4) |

   **pd adds only what these don't provide:** state that is per repo, committed, reviewable and the same on every machine.
7. **Keep scratch separate.** Bulky raw output (gate logs, agent transcripts, probes) goes in gitignored `agent_sandbox/` and is disposable. What resume or audit needs is summarized into the item's `log.md`.

---

## 3. The layout

**Two audiences, two places:**
- **Agent-centric development artifacts** live under `{artifacts_root}`, which defaults to **`docs/dev_artifacts/`** in pd's scripts (a project that hasn't adopted is told so, §12). Agents write them and read them back to plan, resume and audit.
- **Human-centric docs** stay at the top of `docs/`. People read them to use or develop the project. Their tiers are already set by `doc_tiers` in `.claude/pd.local.md`.

```text
docs/
├── user-guide/                    # HUMAN: how to install and use the project      (doc_tiers)
├── dev-guide/                     # HUMAN: how to develop it                         (doc_tiers)
├── technical/                     # HUMAN: architecture, API reference               (doc_tiers)
│   └── decisions/<id>.md          # HUMAN: lasting architecture decisions (ADRs)
├── _html/                         # gitignored: HTML generated by pd-html (§3.1)
└── dev_artifacts/                 # AGENT: everything pd's workflow produces = {artifacts_root}
    ├── backlog.md                 # committed; one line per idea (§7)
    ├── features/<id>/             # one directory per feature
    │   ├── README.md              # CONTROL: frontmatter state + "## Now"
    │   ├── log.md                 # CONTROL: append-only history (§6)
    │   ├── shape.md               # Requirements + Design, with its Architecture diagram (specify, design)
    │   ├── plan.md                # Plan with each task's test cases (create-plan); from_shape: records the shape.md it came from (§A2)
    │   └── retro.md               # finish, only when a retro trigger fired (§A8.3 S4)
    ├── plans/<id>.md              # cross-cutting plans and designs; a plan with a roadmap: groups features (§7.1)
    ├── plans/<id>/                # optional: that plan's annex (reviews, scripts); pd-lint checks nothing inside
    ├── brainstorms/<id>.md        # single file: frontmatter, body, "## Now" and "## Log"
    ├── rca/<id>.md                # single file, the same shape
    └── knowledge-bank/{patterns,anti-patterns,heuristics}.md   # frozen, read-only archive (§A8.3 S4)
agent_sandbox/<YYYY-MM-DD>/<topic>/   # gitignored scratch, workflow args included (§8, §10)
```

- **Features get their own directory,** because they hold several artifacts.
- **Single-file items** (plans, brainstorms, rca) are one markdown file with the same frontmatter. Each carries its own `## Now` and `## Log` sections, with the same entry shapes as a feature's README and `log.md` (§5, §6).
- **A plan's annex:** a plan may have a sibling directory with the same id, `plans/<id>/` beside `plans/<id>.md`, holding its annex. `pd-lint` accepts it and checks nothing inside it.
- **There is no separate "project" type.**
  - **Multi-feature work is a plan with a `roadmap:`** (§7.1).
  - **"Project" means only the repository** again. In pd it had meant both the repository (`project_id`) and a multi-feature initiative.
- **Decisions split by audience:**
  - **A ruling made during a feature** is a `decision` entry in that feature's `log.md`.
  - **A lasting architecture decision** a person should find later is an ADR in `docs/technical/decisions/`. That directory already exists.
- **Publishing to the human docs:** when a development artifact becomes reference material (for example a design that settles how a subsystem works), the `updating-docs` skill writes the human doc in `docs/technical/`. The artifact is never moved.

### 3.1 Documentation format: markdown source, HTML for reading

**The clause, added to pd** as `plugins/pd/references/doc-format.md`. The `updating-docs` skill and every template cite it.

1. **Write markdown.** Every artifact and every doc is authored as `.md`.
   - **It is the cheaper output:** on 2026-10-14, the same document (this one) measured about 6.3k tokens as markdown and about 10.1k as bare semantic HTML. That's **1.6× more for HTML, before any styling.** The measure was a words-plus-punctuation proxy; the HTML came from markdown-it with no CSS.
   - **Agents read markdown back cheaply,** and git diffs stay clean.
2. **Read as HTML, generated, never hand-written.** `pd-html <file.md | dir>` converts markdown to HTML with one standard stylesheet, so the model spends zero tokens on formatting.
   - **The stylesheet:** `plugins/pd/templates/doc.css`.
   - **Where output goes:** `docs/_html/` (gitignored), mirroring the source paths.
   - **Each page is standalone:** the stylesheet is inlined, so a page opens anywhere and can be shared as one file. The exception is mermaid diagrams, which need the network; offline they show as code.
3. **Hand-written HTML is the exception,** for content markdown can't express, such as a laid-out dashboard or an interactive page. It lives in `docs/`, beside its topic, is committed, and links `doc.css` by relative path. Even then: use only `doc.css`'s classes, with no inline styles and no `<style>` blocks of its own.
4. **Generated HTML is never committed and never edited.** The `.md` is the one source. This is the same rule as committed renders: delete them and regenerate.

**`doc.css`, the standard template** (about 60 lines, written once):
- **Typography:** a readable measure (about 72ch), system fonts, and a clear heading scale;
- **Content:** tables with borders and zebra rows, code blocks, blockquotes, `<details>`;
- **Theme:** light and dark through `prefers-color-scheme`;
- **Print:** a print style;
- **Status words:** classes for `draft`, `done`, `active`, `blocked` and `abandoned`, which `pd-status` uses.

**`pd-html`, the converter:**
- **A single script** with PEP 723 inline dependencies (`markdown-it-py` and its table plugin), run as `uv run pd-html.py`. uv fetches and caches the dependency, so pd keeps no venv for it. pd already requires uv (its Python rule), and `/pd:init` checks for it.
- **What it renders:**
  - frontmatter becomes a small header box (id, status, phase, issue link);
  - relative `.md` links are rewritten to their `.html` twins;
  - a plan's `roadmap:` becomes a table with each item's live status;
  - a `mermaid` block (such as a design's architecture diagram) is left for mermaid.js, loaded from a CDN, to draw in the browser.
- **Options:** `--open` opens the result in the browser; `--all` renders every human-centric doc plus the active items.
- **Its check:** an assert-based self-test renders a fixture with a table, code, frontmatter, a roadmap and a relative link, and checks the output.

---

## 4. Identity, naming, and the optional issue tracker

**Two separate things:**
- **The id:** always generated locally, the same way in every project, and never changed.
- **The issue link:** an optional attribute, set only in projects connected to a tracker.

A project can connect to GitHub, disconnect, or never have it, and no id ever changes.

### 4.1 The id: always local

**A new item's id is `YYYY-MM-DD-<slug>`,** and it is the directory or file name. For example: `features/2026-10-14-artifact-sop/`.

- **Generated by:** `pd-new <type> "<title>"`, which takes today's date, on the local clock of the machine running it, plus `slugify(title)`. It needs no network and no coordinator.
- **A backlog item isn't a frontmatter item:** `pd-new backlog "<title>"` appends a dated line to `backlog.md`, with an id made the same way, and `pd-lint` checks the line's format (§7).
- **The slug:** lowercase, hyphens, at most 5 words, no dates, no sequence numbers. `slugify` drops stopwords and keeps the first five remaining words.
- **Why not a sequence number:** `NNN` needs a coordinator, because two branches, worktrees or machines can take the same next number. That coordinator was the registry's `allocate_entity_id`. A date plus a slug is unique without one, sorts by time, and matches what `plans/` and `rca/` already do.
- **Why not the issue number:**
  - a project without GitHub would need a second scheme;
  - an item created offline would have to be renamed once its issue exists, breaking links;
  - issue numbers are per repository, so `#12` is ambiguous across projects.
- **Collisions** (the same slug on the same day) are refused by `pd-new`, which sees only its own checkout. A duplicate made on another branch is caught by `pd-lint` after the merge, which checks ids within each type directory: the merger runs it after each task merge (step 4 of the merger's check, §A4), and `/pd:finish-feature` after the final merge.
- **Legacy ids** (`134-workflow-rebuild`) stay as they are, and are never renamed. They sort before dated ids. A legacy item's created date is its first commit in `git log`.
- **Links** between items are paths relative to `{artifacts_root}` (`features/2026-10-14-artifact-sop`), never a bare number or a title. Inside a roadmap, items are keyed by slug (§7.1).
- **Short references in commands:** pd's commands accept any unique part of an id (`/pd:implement artifact-sop`).

### 4.2 The issue link: optional, minimal

`.claude/pd.local.md` gains one field (listed with the rest in §12):

```yaml
tracker: none        # none | github   (later: one adapter per tracker)
```

| `tracker` | On `pd-new` | At done or abandoned |
|---|---|---|
| `none` (the default) | Nothing | Nothing |
| `github` | For features and plans only: runs `gh issue create` (the body is one line plus the item's path), then writes `issue: <its URL>` into the frontmatter. Offline, it creates the item without `issue:` and notes that in `## Now`. Inside a goal run, it records `issue: pending`, and the next command the user invokes creates the issue. | `gh issue close --reason completed` (or `"not planned"`) |

**That is all pd does with a tracker for now.** Labels, boards, sync and drift checks are deferred (§14).

**The rules:**
- **One direction only: item → issue.** The files own status, phase and history; the issue owns its discussion. pd never reads status back from the issue, so `pd-lint` and the commit hook run offline.
- **`issue:` holds a full URL,** not a number, so it works for any tracker and any repository. Its one other value is `pending`, set inside a goal run (above).
- **Closing keywords can't do the closing.** GitHub interprets them "only when the pull request targets the repository's default branch". pd features merge into `develop`, and often locally with no PR. So `/pd:finish-feature` closes the issue itself.
  - Source: https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue
- **Artifacts, rulings and logs never go into an issue.** The reason is one fact, one place, not secrecy: an issue would hold a second copy. `/pd:init` still warns before setting `tracker: github` on a public repo. pedantic-drip is public; the other three are private (checked 2026-10-14).
- **Creating an issue publishes something,** so pd creates one only inside a command the user invokes. A `pd-new` the conductor runs inside a goal run doesn't count; it records `issue: pending` (above).

**Measured 2026-10-14:**
- All four projects have a GitHub `origin`, issues enabled, and `main` as the default branch.
- `gh` is logged in as `clthuang`.
- Issues are barely used yet: the latest are pedantic-drip #8 and fractorg #6. Issues and PRs share one counter, and project_illium's PRs reach #165.

---

## 5. State: the frontmatter

Every item carries the same frontmatter block. A feature's lives in `features/<id>/README.md`; a single-file item's sits at the top of its file.

```yaml
---
id: 2026-10-14-artifact-sop          # equals the directory or file name
type: feature                        # feature | plan | brainstorm | rca
title: Artifact management SOP
status: active                       # draft | active | blocked | done | abandoned
phase: design                        # features only: specify | design | create-plan | implement | verify | finish
mode: standard                       # features only: standard | small | express (set at Triage, or at promotion for work that entered at Clarify)
origin: backlog#2026-10-10-foo       # optional: what it was promoted from
branch: feature/2026-10-14-artifact-sop   # features only: always feature/<id>; removed at done
risk: [security]                     # features only, optional: security | migration (§A2)
issue: https://github.com/clthuang/pedantic-drip/issues/12   # only when tracker ≠ none (§4.2)
---
```

**What the fields mean:**

| Field | Rule |
|---|---|
| `status` | **draft:** written down, not started. **active:** being worked. **blocked:** waiting; the reason is in `## Now`. **done:** finished. **abandoned:** stopped; the reason is in `log.md` (a single-file item's `## Log`). |
| `status` (a plan with a `roadmap:`) | Only `draft`, `active` or `abandoned`. pd computes "done" from the roadmap (§7.1); nobody writes it. |
| `phase` | The phase being worked. A feature's Clarify stage has no phase: it lives in the brainstorm or rca item the feature is created from (§A2). `phase-gate.sh <phase>` is a phase's exit check: what that phase must hand down. The skill runs it before moving `phase:` past the phase, and `pd-lint` re-runs it at every commit for each phase before the current one, never the current one, so a mid-phase commit passes (§9). |
| `risk` | Set at Triage (or at promotion for work that entered at Clarify, §A2), or by the conductor after the risk scan at `verify` warns (§9); on a small or express feature, a tag set at `verify` moves the feature back (§A2). `security` makes the security review at finish mandatory; `migration` makes QA run the migration up and down on a fixture database. Only a `decision` entry from the user removes a tag. |
| `mode` | Set at Triage, or at promotion for work that entered at Clarify (§A2). `small` writes Contracts and Plan in one sitting, still as two phases. `express` skips specify, design and create-plan; its mini-spec, one task block, lives in `shape.md` under `## Requirements` only. |

- **Deliberately absent:**
  - **created, updated and completed dates:** the id and `git log` already hold them;
  - **reviewer notes and phase timestamps:** they go in `log.md`;
  - **which plan a feature belongs to:** the plan's `roadmap:` says it; the feature doesn't restate it, and `pd-status` looks it up.
- **The README body,** below the frontmatter, has exactly these sections:
  1. `## Now`: optional fixed key lines first, then free text: the next step, blockers, and any workflow run in flight. It is overwritten, not appended, and an overwrite re-emits the key lines. `pd-lint` checks their format:
     - `goal: <feature id> target <phase> session <session id>`, while a goal run is active (§A5);
     - `run in flight: <run-name> session <session id>`, plus `(args: <path>)` when an args file was saved, while a workflow run is (§8).
  2. `## Links`: the artifacts and related items.

---

## 6. History: `log.md`

**Append-only.** Each entry is one `##` heading, `## <date> <HH:MM±hh:mm> <kind>`: the local time with its UTC offset, so entries made in different time zones still compare. Each has a fixed shape:

```markdown
## 2026-10-14 09:12+08:00 decision
Q: Reduce the review cadence?
A (user, verbatim): "Keep Code review and QA after each phase milestone implementation."

## 2026-10-14 11:30+08:00 review M1 — codex (fallback: no)
Verdict: changes requested. Blockers: 2 (listed). Commit: 6ccfa3a5.

## 2026-10-14 12:05+08:00 gate implement — pass
G1 4920/2, G2 51/1, G3 0/0, G4 67/67, G5 121. Raw logs: agent_sandbox/2026-10-14/m1/.

## 2026-10-14 15:40+08:00 phase verify -> design (back)
Reason: the contract named no error for an empty input. Invalidates: plan.md.
```

- **Shapes live in one place:** `plugins/pd/references/log-entries.md` holds one block per entry kind.
- **Two entries of the same kind in the same minute:** the second's heading gets a `-2` suffix on its kind (`review-2`), and references to it use the suffix.
- **A `phase` entry's heading** is `## <date> <HH:MM±hh:mm> phase <from> -> <to>`, with `(back)` when it moves back; a backward entry names what it invalidates (§A2).
- **A `decision` entry's answer line** reads "A (user, verbatim)", or "A (conductor)" for a call the conductor made, or "A (conductor, on the user's behalf)" in a print-mode run (§A5). A decision answering a cap stop names the `capped` entry it answers, as `answers: capped@<date> <HH:MM±hh:mm>` (§A2).
- **A `qa` entry records the commit its battery ran against** (§A2 row 6).
- **A later entry names a blocker it closes** as `review@<date> <HH:MM±hh:mm>#<issue id>` (§11).
- **An entry converted from a legacy file** (§12, adopt step 4) carries a `Status: closed (legacy)` line, and `pd-status` treats its blockers as closed.
- **Entry kinds** (closed list): `decision`, `phase` (a phase transition), `review`, `qa`, `gate`, `run` (a workflow launched or finished), `handoff`, `replan` (§7.1), `metrics`, `defect`, `note`, `capped` (a loop reached its cap: deferred items, follow-ups, decisions, assumptions; §A2, D15).
- **Measuring the method** (F7, adopted 2026-10-14). Without it, "trim the scaffolding" is taste, not evidence.
  - **At finish, the conductor writes one `metrics` entry,** holding only what no other entry records (D13):
    - the depth taken: the mode;
    - tokens: the `Stop` gate's running total for the feature, over every transcript in its sessions (§A5, cap 3).
  - **Derived, never written:** the phases skipped (from Triage's `phase` entries), the stops that went to the user (from the `decision` entries), the fix cycles per phase (from the `run`, `review`, `qa` and `gate` entries; the `run` entry carries Execute's cycles per task) and the wall-clock in hours (from the first and last entry headings). Writing them again would restate `log.md` inside itself (§2, principle 2).
  - **A defect found after the merge** appends a `defect` entry to the feature's `log.md`, naming the commit that fixed it. On a done feature it never blocks its commit: `pd-lint` warns, and `pd-status` and the session-start summary show "retro owed" until `retro.md` exists.
  - **`pd-status --compare`** groups done features by depth, and prints the median tokens, cycles, wall-clock and defects for each, deriving the cycles and wall-clock itself. It is deferred until about twenty features are done, when a comparison first means something (D14, §14). The entries are written from the start.
- **The user's rulings are recorded verbatim.** Paraphrased rulings drifted in this campaign; verbatim quotes didn't.
- **Every figure an entry states must come from a primary source,** cited in the entry: a gate log, git, or the workflow run's `journal.jsonl`, in the session's transcript directory. This is the dispatch-briefing rule from CLAUDE.md.
  - **The figures in the entry are the record.** A cited raw log is a pointer, valid until `agent_sandbox/` is cleaned (§10); a journal is valid while its transcript directory exists.

**This replaces** `.review-history.md`, `.qa-gate.json`, `.qa-gate.log`, `implementation-log.md`, `verdict.md`, `review.md` and the database's phase events.

---

## 7. The backlog

**Where it lives** (D1b):
- **By default,** in `{artifacts_root}/backlog.md` (`docs/dev_artifacts/backlog.md`), committed.
- **A project with `tracker: github`** may opt in to `backlog: issues`: its backlog items are issues labeled `backlog`, and promoting one creates the item with `issue:` set to that issue's URL. This is built when the first project opts in (§14).
- **Public repositories keep the file.**

**The file format:** one item per line:

```markdown
- [ ] 2026-10-10-flaky-ui-pid-test — the UI PID-file test fails under load (from: features/2026-10-14-x)
- [x] 2026-10-02-foo — promoted → features/2026-10-14-foo
```

- **Ids:** `pd-new backlog "<title>"` appends the line, with a `YYYY-MM-DD-slug` id (§4.1). A row exported from the registry gets its created date plus a slug (§12).
- **Promoting an item** creates the feature with `origin: backlog#<id>`, and ticks the line with a pointer to the feature. `pd-lint` resolves `backlog#<id>` in `backlog.md` or `backlog-archive.md`.
- **Dropping an item** ticks the line with `— dropped: <reason>`. Lines are never deleted.
- **Archiving:** `pd-lint` warns when the file passes 300 lines, and the conductor then runs `pd-lint --archive`, which moves ticked lines into `backlog-archive.md`.

### 7.1 Multi-feature plans: a roadmap, with computed progress

**A plan groups features by carrying a `roadmap:` list in its frontmatter.** This replaces pd's `projects/<id>/{prd.md, roadmap.md}`. The plan's body holds the PRD and the reasoning; the roadmap holds only membership, order and dependencies.

```yaml
---
id: 2026-10-14-thin-pd
type: plan
title: Thin pd on native workflows
status: active
roadmap:
  - feature: features/2026-10-15-pd-html
  - feature: features/2026-10-16-pd-lint
    after: [pd-html]
  - planned: pd-adopt                 # not created yet; becomes a feature: line when created
    after: [pd-lint]
  - dropped: pd-board                 # never deleted; a reason is required
    reason: "a tracker covers it"
---
```

**Items are keyed by slug,** the id without its date, unique within the roadmap. `planned: <slug>` becomes `feature: features/<date>-<slug>` with the same slug; `after:` names slugs, and `pd-lint`'s comparison with HEAD matches items by slug.

**Why it can't drift** (the user's concern: "how do we ensure that agents keep the progress in sync?"):

| What could drift | How it's prevented |
|---|---|
| **Progress, "what's next", done-ness** | **Never stored, so nothing to sync.** `pd-status` computes them from each listed feature's own frontmatter, which the gates and lint already keep honest. "Next ready" is the first item whose `after:` items are all done or dropped; `pd-status` flags the dependents of a dropped item for a replan. The plan is done once every item is done or dropped. |
| **Scope: items added, dropped, reordered** | **Structured and checked at every commit.** Anthropic's harness found that "the model is less likely to inappropriately change or overwrite JSON files compared to Markdown files", and restricted edits to one field. By analogy, a YAML list checked by `pd-lint` gives the same narrowness; the lint is the real guard (§9). |
| **Silent scope cuts** | **Items are never deleted, only marked `dropped:` with a reason.** `pd-lint` compares the staged roadmap with HEAD's and fails on a removed item. A `feature:` item may be dropped only if its feature is `abandoned`. This is the equivalent of Anthropic's "It is unacceptable to remove or edit tests". |
| **The plan going stale** | **A fixed replan moment.** When a feature listed in a roadmap finishes, `/pd:finish-feature` shows the plan's computed state and appends a `replan` entry to the finishing feature's `log.md`: "plan still holds", or what changed (with the roadmap edit in the same commit). At session start, pd shows each active plan's next ready item. |

- **Creating a planned item:** `pd-new feature --plan <plan> <slug> "<title>"` creates the feature; the slug names which `planned:` line, and the title is given; and turns that line into a `feature:` line, in the same commit.
  - **A planned item that is also promoted** from a brainstorm or rca adds `--from`: `pd-new feature --from <brainstorm or rca> --plan <plan> <slug> "<title>"`. `--from` names the origin, and `--plan` the roadmap whose `planned:` line it fills. Agents may also edit the list by hand; lint judges the result either way, so no extra commands are needed.
- **Timelines, dates and portfolio boards are not pd's job.** When a project needs them, a tracker already computes them from child issues (deferred mirroring, §14).

---

## 8. Workflow runs and resuming across sessions

**Order of preference:**
1. **Same session, or `claude --resume` of it:** relaunch the workflow, and completed agents replay from their saved results. This is a built-in.
2. **A fresh session:** relaunch as a NEW run, with its args re-derived from the committed files.

**The rules for case 2:**
1. **Before launching a workflow run,** the skill derives its args from the committed files: `implement-tasks` from `plan.md`'s tasks (or express's task block, §A2); `verify-change` from the branch, `shape.md` and `plan.md`; `research-fanout` and `rca-fanout` from the question and the brainstorm or rca file (§A4). It may save them to `agent_sandbox/<date>/<feature id>/<run-name>.args.json`, gitignored scratch and a convenience only: the committed files are the source, and a committed copy would restate them (D14). The skill also writes the `## Now` line `run in flight:`, with its session id (§5).
2. **When a workflow run finishes,** the skill appends `run`, `review`, `qa` or `gate` entries to `log.md` with the figures. It clears the `## Now` line and commits.
3. **If a session ends during a workflow run,** a later session reads `## Now`. Native isolation starts every relaunched agent in a fresh worktree, so a relaunch can't start from an earlier attempt's worktree (§A6); resume relies on branches instead. Each implementer names its branch `pd/<feature id>/task-<n>` (§A4), so the conductor finds the earlier workflow run's branches by that prefix. It relaunches `implement-tasks` with them as a resume list: its `merger` first merges every one that passes its check (§A4), and then only the remaining tasks run, with args re-derived from `plan.md`.
4. **Step-level progress inside a long feature** uses Claude Code's task list, not a pd file. Launch with `CLAUDE_CODE_TASK_LIST_ID=<feature id>`, plus `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` where the model needs it (§A7). The user sets these at launch, as `/pd:init`'s output explains. Without them pd loses only step-level progress; `## Now` covers resume.
5. **The run scripts themselves** are saved plugin workflows in pd's `workflows/` directory, not per-feature files. §A4 lists them: `research-fanout`, `rca-fanout`, `implement-tasks` and `verify-change`.

---

## 9. Enforcement

| Check | Where it runs | Blocks? |
|---|---|---|
| **`pd-lint`** (one script) | the `PreToolUse` hook on `Bash(git commit*)`, for staged artifact paths; also by hand, and in CI if a project has it. The hook sees every `git commit` run through Bash, subagents' included (hooks fire for subagent tool calls, verified in the fourth Fable review); a commit made inside a script isn't seen | **Yes** (exit 2) |
| **`phase-gate.sh <phase>`** (existing) | a phase's exit check (§5): in the skill before it moves `phase` past that phase, and inside `pd-lint` for every phase before each feature's current one, never the current one | **Yes** |
| **The agent write hook** | a `PreToolUse` hook on `Write` and `Edit`, keyed on the hook input's `agent_type`: QA may write only under `agent_sandbox/`, and `calvin-runner` only the exact ledger path recorded as `calvin_ledger` in the session's gate state file (§A3) | **Yes** |
| **The `SessionStart` summary** | runs on every matcher (`startup`, `resume`, `clear`, `compact`). It prints the current project's `active` and `blocked` items with their `## Now` lines, each active plan's next ready item, and any done feature that owes a retro (§6); in an unadopted project, "run /pd:adopt" (§12) | No (it can't block) |

**What `pd-lint` checks:**
- **Frontmatter:** it parses, has the required fields for its `type`, and `id` equals the file or directory name.
- **Expectations** (§A2, D14): each one under `shape.md` `## Requirements` is written `B<n>: <input or action> -> <observable outcome>`, with a unique id and a non-empty outcome. This is the mechanical half of principles §3, *Behaviour before architecture*; faithfulness is calvin's.
- **Vocabularies:** `type`, `status`, `phase`, `mode` and the `log.md` entry kinds are each from their closed list. A plan with a `roadmap:` may not say `done`.
- **Ids** are unique within each type directory, which also catches, after a merge, a duplicate made on another branch (§4.1).
- **`issue:`** appears only when `tracker` is not `none`, and holds a URL, or `pending`, which lint accepts with a warning; the user's next command creates the issue (§4.2). Lint checks the format only and never calls the network.
- **Links:** `origin` and `## Links` paths resolve; `backlog#<id>` resolves in `backlog.md` or `backlog-archive.md`.
- **Cited commits:** every commit hash cited in `log.md` exists in the repository. Lint checks form; this is its one link to what happened.
- **`## Now` key lines:** `goal:` and `run in flight:` follow their formats (§5).
- **The backlog:** each line follows §7's format; past 300 lines, a warning to run `pd-lint --archive` (§7).
- **Roadmaps:**
  - every `feature:` path exists;
  - no feature is listed in two roadmaps;
  - every `after:` names an item's slug in the same roadmap, with no cycles;
  - every `dropped:` has a `reason`, and a dropped `feature:` item's feature is `abandoned`;
  - a `planned:` slug that already exists as a feature is an error (it should be a `feature:` line);
  - **no item present in HEAD's roadmap, matched by slug, is missing from the staged one.**
- **Phase artifacts:** `phase-gate.sh` passes for every phase before the feature's current one (§5). For an express feature, read from `mode: express` in the frontmatter, the mini-spec check (one task block in `shape.md` `## Requirements`, §A2) replaces the exit checks of specify, design and create-plan. A `done` feature needs a `metrics` entry. It also needs `retro.md` when its `log.md` records a retro trigger (§A8.3 S4), and otherwise a `note` entry from finish. Each trigger is read from an entry:
  - **a second backward move:** two `phase` entries marked `(back)`;
  - **exhausted fix cycles:** a `capped` entry;
  - **a cost overrun:** `metrics` tokens above the original `feature_token_budget`: its value when the feature's first goal started, which the conductor records in that goal's `run` entry, so it lives in git (§A5, cap 3). If it was unset then, there is no overrun trigger. A "continue" raise doesn't move this line: the raise itself means the budget was overrun;
  - **a defect:** a `defect` entry. Added to a done feature, it never blocks the commit: lint warns, and the retro is owed (§6).
- **Legacy items** (numeric ids):
  - **one that is `done`** is exempt from the phase-artifact, `metrics`, retro and `from_shape:` checks, but still checked for frontmatter vocabulary, ids and links;
  - **one that is neither `done` nor `abandoned`** is listed by `/pd:adopt` and converted to the new artifact set before work on it resumes (§12); abandoned work won't resume.
- **Plans** (§A2):
  - every task in `plan.md` names its test cases, a `uses:` list, a proving command and the files it may touch; each test case names its fixture or fake, or "none"; each proving command names the JUnit XML path it writes, for `pd-proof` (D15);
  - `### Test strategy` names the runner's JUnit option; a runner with none gets a JUnit reporter from an `infra` task before the first feature task;
  - every `uses:` module of a `[parallel-safe]` task exists at its wave's base, or is in the task's own file set (D15). At `create-plan`, `pd-lint` takes wave n's base to be the current HEAD plus the file sets of every task in earlier waves: a `uses:` module must exist at HEAD, or be in the file set of this task or of an earlier wave's task;
  - every expectation id in `shape.md` is cited by at least one test case, and every cited id exists (D14);
  - a wave's `[parallel-safe]` tasks have disjoint file sets;
  - `from_shape:` equals the git blob hash of the current `shape.md`; otherwise the plan is stale. Checked only while `phase` is `create-plan` or later (§A2);
  - a task marked `proof: green-only` gives a reason, `refactor`, `infra` or `fixture` (D15); a `refactor` names a proving command whose test files already exist at HEAD;
  - a `small` feature's plan with more tasks than `small_feature_tasks` is reported, not failed (§A2).
- **One fact, one place:** no `status:` or `phase:` line appears outside the frontmatter, fenced code blocks skipped. It also runs the existing duplicate-contract-block check.
- **Test isolation** (D15, the user: "make sure test fixture locations are methodically defined and enforced so that we don't have test data leaking to proper code and tests access proper code by accident"). The paths come from `source_paths`, `test_paths` and `fixture_paths` in `.claude/pd.local.md` (§12), and the design's `### Test strategy` names the fixtures. Checked by the merger per task and at `verify` over the branch diff:
  - **how it reads code:** per-language regexes for import lines and path strings, for the languages the project declares (`languages`, §12);
  - **no leak into production:** no file under `source_paths` imports from, or names a path under, `test_paths` or `fixture_paths`;
  - **fixtures in their place:** fixture data lives only under `fixture_paths`, and test files only under `test_paths`;
  - **no accidental reach into the real system:** tests import only the modules the design's contracts name, read from each contract block's `modules:` line (a format the `shape.md` template pins, §12), never private ones. "Private" is mechanical only for Python's leading underscore; elsewhere it's the code reviewer's job. A test touching a real resource the test strategy doesn't name is a code-review finding, since no grep can see every network call.
- **`capped` entries:** each has its four lists, and every follow-up has its `backlog.md` line (D15).
- **Risk signals** (a warning, never a failure; D14, moved to `verify` by D15): the branch diff matches a pattern in `plugins/pd/references/risk-patterns.md`, and the feature has no matching `risk:` tag. The list starts with route decorators, migration directories, and identifiers matching auth, permission, token or secret. The conductor sets the tag, or the user clears it with a `decision` entry.
- **No forbidden files:** `.meta.json`, `.review-history.md` and `.qa-gate*` are flagged once a project has adopted the SOP, which `.claude/pd.local.md`'s `sop: 1` records (§12).

---

## 10. Retention and cleanup

| What | Kept | Cleaned |
|---|---|---|
| Items (`done`, `abandoned`) | **Forever, in place.** They are the history; moving them would break links. | Never moved or deleted |
| Workflow args (`agent_sandbox/…/<run-name>.args.json`) | While the run is in flight | With the rest of `agent_sandbox/`; the committed files regenerate them (§8) |
| `agent_sandbox/` | Until the matching `log.md` entry exists | Any time after that; `pd-lint --sweep` lists dirs older than 30 days whose items are `done`, matching each directory name to an item's slug or full id, and lists anything else for the user |
| `docs/_html/` (generated) | Never kept as a source | Any time; `pd-html` regenerates it |
| Task worktrees (made by workflow isolation, under `.claude/worktrees/`) | Until the merge | The merger removes each one after its merge, and the workflow removes a failed attempt's before its fix cycle (§A4); Claude Code's periodic sweep removes leftovers ("a worktree with changes stays on disk until the periodic sweep", code.claude.com/docs/en/worktrees). Resume relies on branches, not worktrees (§8), so a swept worktree loses nothing |
| Task branches | Until the feature is `done` | At `finish`: after the retro if one runs, otherwise at the final merge |

---

## 11. Seeing the state

**`pd-status`** shows the current repository's state without a registry:
- **What it reads:** the repo's frontmatter. It prints a table by status and phase, plus each plan's computed progress and next ready item. `pd-html` can render the same view.
- **It flags open blockers:** a blocker in a `review` or `qa` entry stays open until a later entry names it (`review@<date> <HH:MM±hh:mm>#<issue id>`, §6): a `review` or `qa` entry reporting it fixed, a `decision` or `capped` entry (§A2), or a backward `phase` entry that replaced its artifact (§A2). A converted legacy entry's `Status: closed (legacy)` line closes its own blockers (§6). It also links each `decision` entry to the `capped` entry it answers (§A2). A blocker the fixer proposed to reject stays open until the user accepts the rejection, in a `decision` entry (§A4). The `Stop` gate runs it (§A5).
- **It lists, without blocking:** open assumptions (§A2), on-behalf decisions from print-mode runs (§A5), done features that owe a retro (§6), and the dependents of a dropped roadmap item, for a replan (§7.1).
- **`--compare`** reports the method's cost and outcome by depth, from the `metrics` and `defect` entries plus the cycles and wall-clock it derives from `log.md` (§6). Deferred until about twenty features are done (§14).
- **It is read-only** and caches nothing. The files are the only truth, so the view can never drift from them.
- **It sees one repository only.** The user dropped cross-workspace querying and the Kanban UI (§A1); claude-mem covers recall across projects.

---

## 12. Installing and adopting

**The plugin ships:**
- **skills and commands:** the kept ones (§A6), with their MCP calls rewritten to read and write files, plus the new `verifying` skill;
- **`agents/`:** per §A6, with the new `merger` and `calvin-runner`;
- **`workflows/`:** the four workflows in §A4;
- **`hooks/hooks.json`:** §9's checks;
- **`scripts/`,** in `plugins/pd/scripts/`, which skills and hooks call through `${CLAUDE_PLUGIN_ROOT}/scripts/`: `pd-new`, `pd-lint`, `phase-gate.sh`, `pd-proof`, `pd-status`, `pd-html` and `pd-adopt`.
  - **`pd-proof`** reads only a proving command's JUnit XML. At the first commit: `tests > 0`, `errors == 0`, and each test failed, unless it is green or skipped, in which case `pd-proof` itself lists it in its JSON result. At HEAD: a valid, non-empty report (`tests > 0`), no failures or errors, every test id present at the first commit still present, and no test newly skipped since then (codex review C9).
- **`templates/`:** the feature README, `log.md`, `shape.md` (with the `B<n>:` expectation form under `## Requirements`, and under `## Design` an `### Architecture` mermaid skeleton and a contract block with its `modules:` line in a pinned format, §9), `plan.md` (with a test-cases block per task), `retro.md` and a plan with a roadmap, plus `doc.css` (§3.1);
- **`references/`:**
  - `doc-format.md`, the documentation clause (§3.1);
  - `workflow-results.md`, the workflows' result schemas and the review's issue schema (§A4);
  - `log-entries.md`, one block per `log.md` entry kind (§6);
  - `risk-patterns.md`, the risk scan's patterns (§9).

**A new project: `/pd:init`.** It is optional, and the user runs it once per project. pd works on defaults without it, except at Verify, which needs `qa_battery` (the defaults are in the field list below); today's hooks already fall back when `.claude/pd.local.md` is missing (`plugins/pd/hooks/session-start.sh:33-36`). It gathers the settings the user should approve:
- Checks that uv is installed (§3.1), and that the user's `calvin` skill is installed, which `calvin-runner` runs (§A3).
- Creates the §3 skeleton: `docs/dev_artifacts/` (`{artifacts_root}`) beside the human doc tiers.
- Writes `.claude/pd.local.md` (the field list below). It proposes `source_paths`, `test_paths`, `fixture_paths`, `languages` and `qa_battery` from the project's layout, for the user to confirm (§9, test isolation). It also asks for `tracker`:
  - it offers `github` only when `origin` is a GitHub remote and `gh auth status` passes;
  - it warns when the repository is public.
- Adds `agent_sandbox/`, `.claude/worktrees/` and `docs/_html/` to `.gitignore`.
- Proposes, as a diff the user approves:
  - `worktree.baseRef: "head"`, without which task worktrees start from the default branch (§A6);
  - allow rules for the tools pd's agents run (git merge, git worktree, the project's test commands), so auto mode doesn't block an unattended goal run (§A7.8);
  - the environment caps, in `.claude/settings.json`'s `env` block (§A5, cap 2).
- Explains the task-list variables the user sets at launch (§8).

**`.claude/pd.local.md`, the one field list.** It is committed in every project (D16): `/pd:init` writes it, and it is reviewed like any config.
- **Kept from today:** `artifacts_root` (the scripts' default is `docs/dev_artifacts`), `base_branch`, `release_script` and `doc_tiers` (§3).
- **Triage** (§A2): `small_feature_tasks` (default 3) and `many_files` (default 10).
- **Tests:**
  - `source_paths`, `test_paths` and `fixture_paths`, for the test-isolation checks (§9);
  - `languages`, which selects the per-language regexes those checks use (§9);
  - `qa_battery`, the list of QA commands that `phase-gate.sh verify` requires a passing `qa` entry for (§A2 row 6);
  - **Defaults when `/pd:init` was never run:** `source_paths` and `test_paths` are `src/` and `tests/` when present, and otherwise the isolation checks skip with a warning; `languages` is detected from file extensions. `qa_battery` has no default: `phase-gate.sh verify` fails with "set qa_battery in .claude/pd.local.md".
- **Budgets** (§A5):
  - `workflow_output_cap`: output tokens per workflow run, compared with `budget.spent()`;
  - `feature_token_budget`: the gate's measure, per feature;
  - `budget_increment`: the raise on "continue"; it defaults to the value of `feature_token_budget`.
  - **Their defaults** are set from the bake-off's measured spend. The main bake-off run has `workflow_output_cap` at 2M and no feature budget, and records its spend (§16 step 6; one probe run sets a small budget, §A7).
- **Tracker:** `tracker` (§4.2), and `backlog` once a project opts in to `backlog: issues` (§7).
- **Adoption:** `sop: 1`, written by `/pd:init` or `/pd:adopt`. `pd-lint`'s forbidden-file check keys on it (§9).
- **Retired with this design:** `yolo_mode`, `yolo_max_stop_blocks` and the `yolo_usage_*` fields, with the YOLO hooks; `plan_mode_review`, with `pre-exit-plan-review.sh`; `max_concurrent_agents`, replaced by the concurrency variables (§A5, cap 2); `activation_mode`, which nothing in pd reads today. `/pd:adopt` removes them (step 0 below).

**Detecting a project that hasn't run it** (the user, D14: "make it so that Claude detects if it's been run for a project and then prompt user to run it if missing"):
- **The check:** pd's `SessionStart` hook prints its summary on every matcher (§9); only this check is limited, to `matcher: "startup|resume"`, so it doesn't repeat after every `/clear` or compaction (D15). Inside a git repository only, it looks for `.claude/pd.local.md`. If it's missing, the hook prints one line, which Claude Code adds to Claude's context ("Claude Code adds a SessionStart hook's plain-text stdout to Claude's context", code.claude.com/docs/en/hooks).
- **An unadopted pd project:** detection keys on `sop: 1`, not on the file, since a project that ran today's `/pd:init` already has `.claude/pd.local.md`. When `docs/dev_artifacts/workitems/` exists and the file lacks `sop: 1`, or is missing, the project's items sit outside the scripts' default root: that line, and `pd-status`, say "run /pd:adopt" instead. Otherwise a missing file gets the `/pd:init` offer (below).
- **The prompt:** Claude then offers `/pd:init` through AskUserQuestion: run it now, not now, or never for this repository.
  - **"Not now"** asks again next session.
  - **"Never"** is recorded outside the repository, in `~/.claude/pd/init-declined`, one line per repository, keyed by its `origin` URL when it has one and otherwise by its path. So the repository gains no file, and the question stops even after a move or a fresh clone.

**An existing pd project: `/pd:adopt`.** It is a one-time migration, run as a dry run first, which the user reviews as a diff before committing.
- **It runs on a `pd-adopt` branch,** merged to the base branch after the user's review.
- **Branches open at that time** are listed for their owners. Phase R's branches stay as they are (D9).
- **Only the four active projects adopt** (§1).

0. **First, the config, the registry copy and pedantic-drip's backlog.**
   - **The first change:** remove the retired fields (above) from `.claude/pd.local.md`. `sop: 1` is written last, at step 8 of this list, so the forbidden-file check doesn't block adopt's own commits.
   - **The registry copy:** copy `entities.db` only, with SQLite's backup API from a source opened with `immutable=1`, into `agent_sandbox/`. Every later read of the registry in this migration uses this copy, the read-only export of steps 2 to 4 included (D5).
   - **Pedantic-drip only: export the backlog.** Its `docs/backlog.md` is a gitignored projection, so the backlog is exported from the registry's backlog rows (D5) to `docs/dev_artifacts/backlog.md` before anything moves. Only pedantic-drip's own rows are exported, by its workspace uuid. Open rows stay unticked; closed rows are ticked with their recorded outcome. Each exported row's id is its created date plus a slug (§7).
1. **Move the development artifacts under `docs/dev_artifacts/`** with `git mv`, which moves only tracked files: `features/`, `brainstorms/`, `rca/`, `plans/`, `knowledge-bank/` and `backlog*.md`. Then set `artifacts_root: docs/dev_artifacts`.
   - **The same commit rewrites every relative link** that pointed at the old paths, in both the artifacts and the human docs. **Covered:** markdown links `[..](relative path)`, and backticked relative paths that start with a moved directory, in git-tracked `.md` files. **Not covered:** code, absolute URLs, and anything outside git.
   - **This is the only time items move;** after it, §10's never-move rule holds.
   - **Human docs stay where they are:** `user-guide/`, `dev-guide/`, `technical/` and top-level human pages.
   - **The dry run flags anything it can't classify** (for example pedantic-drip's split `dev-guide/` and `dev_guides/`) for the user to place.
2. **Create each feature's `README.md` frontmatter.** The source is the feature's `.meta.json`, or a read-only export of the registry for pedantic-drip, whose `.meta.json` files are mostly absent.
   - **The fields, for features:**
     - `id`: the directory name;
     - `type`: from the directory;
     - `title`: the first heading, or `.meta.json`;
     - `phase`: from `.meta.json`, or the export's last phase event;
     - `mode`: `standard`, unless the export says express;
     - `branch`: from `.meta.json`, if not done;
     - `origin`: from the parent link.
   - **Legacy single-file items** get only `id`, `type`, `title` and `status`.
   - **The same commit deletes each `.meta.json`** this step read, as step 4 does with the review files.
   - **The status mapping:**
     - `completed`, `complete`, `implemented`, `satisfied` → `done`;
     - `planned`, `preregistered` → `draft`;
     - `in-progress`, `active` → `active`;
     - `promoted`, `analyzed` → `abandoned`: not done, so not `done` (the user's ruling on pedantic-drip's dry run, 2026-10-18);
     - anything else is listed for the user to map by hand.
3. **Convert each `projects/<id>/` into `plans/<id>.md`.**
   - **The body:** the old `prd.md`, followed by the old `roadmap.md`'s prose.
   - **The `roadmap:` list:** built from the execution order and dependency graph, with features resolved by the registry's parent links.
   - **Duplicate projects** (the same initiative under two ids) are merged into one plan.
   - **Projects with no features** become plain plans, with no roadmap.
   - **The user reviews this step closely,** because it needs judgment.
4. **Convert the review and gate files into `log.md` entries:** `.review-history.md`, `.qa-gate.json` and `implementation-log.md`, plus the registry's phase events and reviewer notes from the read-only export (D5). The originals are removed in the same commit.
   - **Why:** the retro and `pd-status --compare` read past features from `log.md`; without the conversion, legacy features drop out.
   - **Converted entries are written closed:** each carries a `Status: closed (legacy)` line (§6), so `pd-status` shows none of their blockers as open.
5. **Leave the content files alone.** `spec.md`, `design.md`, `tasks.md` and `prd.md` stay as they are; new items use `shape.md` and `plan.md`. §9 says what `pd-lint` asks of legacy items. One that is neither `done` nor `abandoned` is listed here and converted to the new artifact set before work on it resumes.
6. **Commit `docs/dev_artifacts/backlog.md`.**
7. **Pedantic-drip only:** remove the `.meta.json` and `docs/backlog.md` lines from `.gitignore`.
8. **Last, write `sop: 1`** into `.claude/pd.local.md`. From here on, `pd-lint` flags the forbidden files (§9).

---

## 13. Where today's files go

| Today | Under this SOP |
|---|---|
| `.meta.json` (gitignored in pedantic-drip, tracked elsewhere) | The `README.md` frontmatter, committed |
| The entity registry, `workflow_phases` and `phase_events` | The frontmatter, `log.md` and git history |
| `projects/<id>/{prd.md, roadmap.md}` and project entities | `plans/<id>.md` with a `roadmap:`; progress computed |
| `.review-history.md`, `.qa-gate*`, `implementation-log.md`, `verdict.md`, `review.md` | `log.md` entries; raw logs in `agent_sandbox/` |
| `docs/backlog.md` (a gitignored database projection) | `docs/dev_artifacts/backlog.md`, committed and the source of truth |
| The Kanban UI and cross-workspace queries | Dropped (the user, 2026-10-14). `pd-status` shows one repository (§11) |
| `allocate_entity_id` | `pd-new`'s date-slug ids, plus an optional `issue:` link (§4) |
| `HANDOFF.md` and handover docs (this campaign's resume files) | `## Now`, `log.md` `handoff` entries and `plan.md` (workflow args are re-derived from it), plus the built-in task list and `--resume` |
| `spec.md`, `design.md`, `tasks.md` (old set) | Kept on legacy items; new items use `shape.md` and `plan.md` |

---

## 14. Deferred until a project needs it

These are tracker features. Build each one only when a real project asks for it; until then, the schema already leaves room (`tracker`, `issue:`), so adding one needs no migration.

| Deferred | What it would do | Build when |
|---|---|---|
| `pd-sync --link` | Create issues for open items in a project that connects a tracker late | A project switches to `tracker: github` with open items |
| `pd-sync --check` | Report items whose issue disagrees with them (report only, never auto-correct) | Issues are actually being edited by hand |
| Status and phase labels | Push `phase:*` and `status:*` labels at each transition | Someone wants to filter issues by phase |
| A GitHub Project board | A board, table or timeline over labeled issues | A portfolio view beyond `pd-status` is needed |
| Roadmap → sub-issues | Mirror a plan's roadmap as a parent issue with sub-issues, so GitHub computes progress | A plan is tracked in GitHub |
| `backlog: issues` | Backlog items as issues labeled `backlog` (D1b) | The first project opts in |
| `pd-plan` commands | Add, drop and move roadmap items by command | Hand edits plus lint prove error-prone |
| `pd-status --compare` | The method's cost and outcome by depth (§6, §11) | About twenty features are done (D14) |

---

## 15. Decisions

- **D1, ids (resolved 2026-10-14):** the user's requirement, verbatim: "it needs to be able to handle both, since not all projects are connected to github". The answer is a local date-slug id everywhere, plus an optional `issue:` link per the project's `tracker` setting (§4).
- **D1b, the backlog (resolved 2026-10-14):** the user chose "File default, issues opt-in".
  - A committed `backlog.md` everywhere.
  - Issues are an opt-in for projects with `tracker: github`, and public repos keep the file.
  - The issues option is built when a project first opts in (§14).
- **D6, multi-feature work (resolved 2026-10-14):** the user chose "Yes, fold it in", then "Trim, then fold roadmaps".
  - A plan with a structured `roadmap:` replaces the project type, and progress is computed (§7.1).
  - The naming question ("project" or "initiative") is gone, because there is no such type.
- **Scope (resolved 2026-10-14):**
  - Use Claude Code's built-ins first (§2, principle 6).
  - Tracker features are deferred (§14).
  - The user, verbatim: "I am happy to lose the Kanban UI, cross workspace querying (somewhat replaced by claud-mem)." Both retire with no replacement (§A6).
- **D7, Part A's topology (resolved 2026-10-14):**
  - **The `verify` phase:** "Own verify phase" (§A2).
  - **Unattended runs:** after asking "how do we control the fan out and resources effectively?", the user chose "/goal + layered caps" (§A5). The YOLO hooks retire. `yolo-stop.sh`'s state check and token cap are ported to a script `Stop` gate (D11).
  - **Executors' model:** "Sonnet, strong verifiers" (§A3).
- **D8, simplifying the method (resolved 2026-10-14):**
  - **S1 is rejected:** "separate out planning from the design stage. I think they are two distinct angles to solving the problem", then "Keep all three". D11 later allows a small feature to write Contracts and Plan in one sitting, still as two phases.
  - **S2 to S6 are adopted:** "Three, plan by lint", "Brief + review lens", "On trigger, lessons routed", "Only when it pays" and "Staged prune" (§A8.3).
- **D9, what pd keeps (resolved 2026-10-14):** "Retire all".
  - **Kept:** `phase-gate.sh`, `pd-status`'s blocker flag, and the `Stop` gate with its token cap (§A9).
  - **Phase R stops for good.** Its branches `followups-r4-f4b`, `followups-r4-g` and `followups-r4-h` stay unmerged, and nothing runs against the live registry.
- **D10, fix cycles (resolved 2026-10-14):** raised by the user while answering S3: "each phase should allow up to three cycles". Clarified as "3 against gates, 1 review" (§A2) (amended by D14: before code, up to three scoped review-revise cycles).
  - **`docs/workflow-principles.md` §11, *More review is not better; every loop gets a budget*,** was updated to match on 2026-10-14.
  - **The repo CLAUDE.md's "Review gate protocol"** is restated at build time, as part of S6's prune.
- **D11, after the Fable review (resolved 2026-10-14):** the review is at `docs/dev_artifacts/plans/2026-10-14-thin-pd/reviews/fable-review.md`. The user adopted:
  - **D7's mechanism:** "Script gate + real caps": a script `Stop` gate decides, `/goal` only drives, and the caps are stated as they really work (§A5);
  - **in the principles:** F3, a model-conditional self-check; F4, judgement findings need a new check; F5, only sourced claims; F8, the proof shown failing first;
  - **ruling changes:** one backward move is not a retro trigger (S4); one escalation to the strongest model (D7c); measuring the method (F7); Contracts and Plan in one sitting for small features (S1).
- **D2, the control file's name (resolved 2026-10-14):** "README.md".
- **D3, who writes `log.md` entries (resolved 2026-10-14):** "The conductor skills" (§A4).
- **D4:** number unused.
- **D5, the old registry's data (resolved 2026-10-14):** "Export, then archive".
  - **Export:** `/pd:adopt` reads a copy of `entities.db`, made from a source opened only with `immutable=1` (§12, adopt step 0), to write each feature's frontmatter, its `log.md` history and the backlog.
  - **Archive:** `entities.db` and its backups are then kept read-only, and stay queryable with `sqlite3`.

- **D12, an architecture diagram in the design phase (resolved 2026-10-14):** the user, verbatim: "update the design phase to include creating a architecture diagram".
  - **What:** `shape.md` `## Design` carries an `### Architecture` mermaid diagram of the modules, the data flowing between them, and the contract on each edge.
  - **One fact, one place:** the diagram names modules and edges and points at the contracts; it never restates a signature. Every edge carries a contract and every contract sits on an edge.
  - **Checked by:** `phase-gate.sh design` requires the diagram; the design reviewer checks the edge-to-contract match. Principles §4, *Contracts are the hand-off boundary between agents*, says the same.

- **D13, after the second Fable review (resolved 2026-10-14):** the review is at `docs/dev_artifacts/plans/2026-10-14-thin-pd/reviews/fable-review-2.md` (verdict: essay publishable, plan ready for calvin). The user adopted, verbatim:
  - **plan fixes:** "Cap ends a /goal run", "Red-first in the merger", "Small decided at Triage", "Lean metrics + rejections" (§A2, §A4, §A5, Part B §6, §9, §11);
  - **essay fixes:** "Sources footer", "Soften weak-model claims", "Unattended per-run bound" (principles §4, *Contracts are the hand-off boundary between agents*; §6, *Thinking goes where being wrong is expensive*; and the new Sources section; §A5 cap 1).
- **D14, after the third Fable review (resolved 2026-10-14):** the review is at `docs/dev_artifacts/plans/2026-10-14-thin-pd/reviews/fable-review-3.md`. The user ruled, verbatim:
  - **Tests (§A2; principles §3, *Behaviour before architecture*, and §7, *A task is dispatchable only when it is objectively verifiable*):** "separate test cases and test code. one is behaviour expectation and is implementing that expectation as a code. The clarification stage and spec stage should generate all the success criterias, goals, non-goals, user stories, behaviour expectations. Design and cotage creates the architecture scaffolds that will help to achieve the spec. The planning stage will fill in the scaffolds with concrete code and turn specs wordy specs into comprehensive test cases and edge cases handling." Then "Design is docs, the scaffolds is at the semantic and contract level", and "plan write test cases semantically, not code. Could be pseudo code. Use 3 cycle cap too". So the executor writes the test code, in a commit before the change (§A2 row 5).
  - **Review budgets (§A2; principles §11, *More review is not better; every loop gets a budget*):** "Criteria clarification, spec writing, design and contracts should have higher review-revise cycle allowance as they have more uncertainties", then "Up to 3, scoped re-review".
  - **Fixes:** "Gate yields, counts all" (§A5); "Sweep contradictions".
  - **Cuts:** "Cut spawn counter + review wf", "Args files to scratch", "Escalation is cycle 2", "Defer compare + deletions".
  - **Risks:** "Flaky-check rule", "Risk tags", "QA questions criteria".
  - **`/pd:init`:** "Go with 1, but after installing the pd plugin, make it so that Claude detects if it's been run for a project and then prompt user to run it if missing. Probably through hooks or something" (Part B §12).
  - **Not adopted:** scoping fix cycles to Verify only, and running a one-week slice before the build.
- **D15, after the fourth Fable review (resolved 2026-10-14):** the review is at `docs/dev_artifacts/plans/2026-10-14-thin-pd/reviews/fable-review-4.md`. The user adopted all twelve proposals: "Stub-only commit 1", "Per-test red/green", "pd-proof via JUnit", "Re-run merged proofs"; "Case map for reviewer", "Gate exits + token measure", "Fixtures home", "Sweep leftovers"; "Re-review schema", "Small: one review call", "Rejections to user batch", "Lighter express Verify". The user added, verbatim:
  - "commit should be as frequent as when meaningful code changes happen which helps to provide the code change trajectory for other agents" (§A2 row 5);
  - "make sure test fixture locations are methodically defined and enforced so that we don't have test data leaking to proper code and tests access proper code by accident." (Part B §9, test isolation);
  - "after review cycle cap is reached, we need to document any deferred items, followup items, decisions made, assumptions made" (§A2, the `capped` entry).
  - **One reviewer claim corrected:** the review says `.claude/pd.local.md` is gitignored; in this repository it is tracked (`git ls-files`).
- **D16, calvin's report (resolved 2026-10-14):** 203 findings, 201 resolved and 2 dismissed. The ledger and the author's adjudication are in `docs/dev_artifacts/plans/2026-10-14-thin-pd/reviews/` (`calvin-ledger.md`, `calvin-adjudication.md`); this revision applies every resolved answer. The user ruled, verbatim:
  - **Print mode (§A5):** "interactive only, when in print mode, any decisions made on user behalf should be logged";
  - **`.claude/pd.local.md` (Part B §12):** "Committed (Recommended)";
  - **The rollout's success test (§16):** "Bake-off + 5 features (Recommended)".
  - **The author's calls while applying it** (flags 1–8 of the annex's `calvin-applied.md`):
    - work entering at Clarify gets its `mode` and `risk:` when its feature is created at Criteria;
    - the field names `languages` and `qa_battery` stand, and `/pd:init` proposes both;
    - today's other `pd.local.md` fields retire (Part B §12);
    - `pd-new feature` takes the `planned:` slug (through `--plan` since D17);
    - a "continue" raise still counts as a cost overrun;
    - §A7 items are checks or marked **Question**s;
    - the canonical diagram gains the security-blocker edge from Finish to Verify;
    - the downloads behind §A8.4 aren't kept, and each source is cited by its full URL (§A8.4).
- **D17, calvin's second report (resolved 2026-10-14):** 89 findings, all resolved. The second ledger and the author's adjudication are in the annex, as `calvin-ledger-2.md` and `calvin-adjudication-2.md`; this revision applies every answer. The user ruled, verbatim:
  - **The rollout's success test (§16):** "Drop the token test". Tokens are recorded and decide nothing.
  - **Deletions (§A6, §16 step 3):** "delete straight away if there is no use for them in the new implementation". This supersedes D14's deferral of deletions ("Defer compare + deletions"); the deferral of `--compare` stands (§14).
  - **The author's calls while applying it** (`calvin-applied-2.md` flags):
    - D17 supersedes D14's deferral of deletions, not D15's;
    - every component with no use goes at §16 step 3, the registry's code, MCP servers, Kanban UI and YOLO hooks included; step 8 only archives `entities.db`;
    - the rest of S6's prune lands with the checks that replace each guardrail;
    - adopt writes `sop: 1` last, so the forbidden-file check doesn't block its own commits;
    - the original token budget is recorded in the goal's `run` entry, in git;
    - a small feature's overrun is a `note`, not a decision;
    - the `goal:` line is also cleared when the target is reached.
- **D18, the build inventory's judgment calls (resolved 2026-10-15):** four verdicts §A6 didn't settle by name (`inventory.md`, judgment calls; `guard-map.md`). The user ruled, verbatim:
  - **Project decomposition:** "delete them for now, and we can recreate them more appropriately if the need arises". `decomposing`, `/pd:create-project`, `project-decomposer` and `project-decomposition-reviewer` go at §16 step 3; a plan's `roadmap:` is written by hand (§7.1) until a need arises.
  - **Components nothing calls:** "implementing-with-tdd, investigation-agent could be called by the secretary". `implementing-with-tdd` goes; `investigation-agent` stays, for `/pd:secretary` to dispatch; `/pd:wrap-up` stays, rewritten to write `## Now` and a `handoff` entry.
  - **The review gate:** "No, as planned". `phase-gate.sh design` and `create-plan` don't require the stage's `review` entry (§A2); guards G-34, G-35, G-38 and G-39 stay dropped.

## 16. Rollout

1. **Calvin this document.** It was written by an agent, so it gets interrogated before anything implements from it, per the user's CLAUDE.md. Done on 2026-10-14 (D16), and a second time the same day (D17).
2. **Commit the plan, with the user's go:** this plan, its annex `docs/dev_artifacts/plans/2026-10-14-thin-pd/` and the essay `docs/workflow-principles.md` are committed before the build starts. Adopt (step 7) later moves the plan and its annex.
3. **Take the inventory, then delete** (D17):
   - **first, the component inventory:** every skill, command, agent and hook, each with its verdict (§A6);
   - **then one commit deletes every component the new design doesn't use:** S2's retirements (`prd-reviewer`, `relevance-verifier`, `test-deepener`, `pre-exit-plan-review.sh`), the YOLO hooks, the workflow engine, the entity registry's code, the MCP servers, the Kanban UI, and the CLAUDE.md text about them. `/pd:adopt` needs none of that code: it reads a copy of `entities.db` with SQLite directly (Part B §12). The user reviews the commit before it lands. Git history keeps them: a failed rollout is fixed forward, or restored from history.
4. **Build the core:**
   - **first, map the 43 `transition_gate` guards** one by one to `phase-gate.sh`, `pd-lint` or "dropped" (§A9), so the scripts are written against that list;
   - the templates, plus `doc.css` and the references in `references/` (Part B §12);
   - `pd-new`, `pd-lint` (including the roadmap checks), `pd-html`, `pd-status` and `pd-adopt`, each with an assert-based self-check;
   - then the commit hook.
   - **`pd-html` can ship first,** on its own: it is useful today, whatever happens to the rest.
   - **A size guard for steps 4 and 5:** the build records the lines it adds under `plugins/pd/scripts`, `plugins/pd/hooks` and `plugins/pd/workflows`, tests and fixtures excluded. They are expected at roughly 1–2k lines; past 5k, the build stops for a review with the user (§A9, codex review C17).
5. **Build Part A:**
   - the agent frontmatter (`tools`, `model`, `effort`, `skills`) per §A3, and the new `merger` and `calvin-runner` agents (§A6);
   - the four workflows in §A4 (`research-fanout`, `rca-fanout`, `implement-tasks`, `verify-change`), starting from the two scripts they generalize (the annex's `workflow-scripts/`), with their result schemas; and the review call;
   - the phase skills rewritten as the conductor's playbooks, with their MCP calls replaced by file reads and writes, plus the new `verifying` skill;
   - the `verify` phase in `phase-gate.sh`, and the `from_shape:` staleness check in `pd-lint`;
   - the `worktree.baseRef: "head"` setting in pd's install instructions;
   - the `Stop` gate with its token cap over every transcript and its yield to background work, and the other caps in §A5: the environment settings, the per-script token check, and the budget fields in `.claude/pd.local.md`;
   - the review budgets: scoped review-revise cycles before code, fix cycles after (§A2);
   - the tests-first rule with a commit per meaningful step, the merger's four-step check and `pd-proof`, the `case_map` and the reviewer's line for it, the test-isolation checks and the `### Test strategy` gate, the scoped re-review schema, the `capped` entry, the flaky-test rule, the judgement-finding rule and the open-rejection rule in `verify`, and the executor's one-time escalation (§A2, §A4);
   - the expectation format and the coverage check in `pd-lint`, the `risk:` tags and their scan at `verify` (Part B §5, §9);
   - the Stop gate's corrections: the stuck path asks, the yield counts only `workflow` and `subagent` entries, the token measure reads `message.usage` and carries across sessions (§A5);
   - **what calvin's report added (D16),** each in the section that owns it: waves and `uses:` lists (§A2, §A4), task branch names (§A4), the session-scoped `## Now` key lines (Part B §5), the print-mode rules (§A5), the QA rule of the agent write hook (Part B §9) and the `pd.local.md` field list (Part B §12);
   - **what calvin's second report added (D17),** each in the section that owns it: every task in its own worktree (§A4), the agent write hook for `calvin-runner` (§A3, Part B §9), the gate's count on every stop (§A5), the shared result fields `stopped`, `agents_used` and `flakes[]` (§A4), the timed entry headings (Part B §6), and `pd-lint`'s express, `modules:` and cited-commit checks (Part B §9);
   - `phase-gate.sh`: `implement`'s exit check becomes a `run` entry recording every plan task merged with its proof passing, and its old entry-time dirty-tree check goes, since `pd-lint` re-runs exit checks at commit time with changes staged (codex review C6); `finish` requires `retro.md` only when `log.md` records a trigger, since today it always does; the `--express` branch checks the mini-spec in `shape.md` `## Requirements`, where today it trusts a database event;
   - the `metrics` and `defect` entries (Part B §6); `pd-status --compare` waits (§14);
   - `/pd:init` and its `SessionStart` detection (Part B §12);
   - the design's architecture diagram (D12): the `designing` skill, `/pd:design`, the design reviewer's checklist and `phase-gate.sh design` were updated on 2026-10-14; the `shape.md` template carries the skeleton;
   - **the rest of S6's prune lands with the checks that replace it:** each CLAUDE.md guardrail that becomes a `pd-lint` check or a checklist line is removed in the commit that adds its replacement, as a diff the user reviews.
6. **Run the bake-off:** one new feature of modest size, run in standard mode, end to end through every stage in §A2, on the native features plus this SOP, with `workflow_output_cap` at 2M and no feature budget (Part B §12), plus the probe runs §A7 names. It must settle each item in §A7; if one fails, the rollout stops there (§A7).
   - **Left for first real use:** express, `rca-fanout` and `research-fanout` are proven by their first real use, each logged. A failure there is fixed forward and logged as a `defect` entry.
7. **Dry-run `/pd:adopt`** on pedantic-drip (153 feature dirs moving under `docs/dev_artifacts/`, links rewritten, projects converted to plans), and review the diff. This design doc moves too, to `docs/dev_artifacts/plans/`, with its annex `docs/dev_artifacts/plans/2026-10-14-thin-pd/`; the essay `docs/workflow-principles.md`, committed with them at step 2, stays in `docs/` as a human doc. Then do the same for fractorg, project_illium and cast-below; their checkouts are read-only until the user approves each one.
8. **Archive the registry** once all four active projects have adopted: `entities.db` and its backups, every `~/.claude/pd/entities/entities.db*` file, are kept read-only (D5, codex review C21). Its code went at step 3 (D17); the registry's other workspaces stay in the archive, and don't adopt.

**How the rollout is judged** (D16, the user: "Bake-off + 5 features (Recommended)"; D17, the user: "Drop the token test"):
- **Thin pd works** if, in the bake-off, every §A7 check passes and every question is answered, and then the next five real features run with `pd-lint` clean and no registry. Tokens are recorded and decide nothing.
- **It fails** if a §A7 item can't be fixed. A failed rollout is fixed forward, or restored from git history (step 3).
