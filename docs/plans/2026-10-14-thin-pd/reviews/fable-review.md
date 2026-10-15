# Independent review of `docs/workflow-principles.md` and the 2026-10-14 rulings

Reviewer: Fable 5.1, read-only, 2026-10-14. Sources re-verified against fetched text; quotes are verbatim and under 15 words.

## 1. Verdict

- **The structural half of the method is sound and well-argued; the quantitative half is asserted.** Runnable criteria, contracts before parallel work, one home per fact, proof outside the author, run-the-thing: keep all of it. "Wide margin", "comparable rate", "negative expected value", "three is about the ceiling" (§11) have no source and the nearest evidence is 2023-model self-correction on QA benchmarks, not independent review of code.
- **One ruling rests on a cap that does not exist.** D7's "/goal + layered caps" names a per-workflow-run token "hard ceiling" (plan §A5 cap 1). Claude Code's workflow runtime has no such option; its large-run warning "is advisory: it doesn't pause or limit the run", and `--max-budget-usd` is "(print mode only)". The only real spend cap for an interactive run is the Stop-hook port, and it fires between turns, after a fan-out has spent.
- **§7 over-generalises a model-specific fact, and the generalisation bites the model D7 chose.** "Current models do that unprompted" is Anthropic's Opus 5 guidance. The Fable 5 guide says the opposite ("Make self-verification explicit in long-run prompts"), and the Sonnet 5.5 guide says it "sometimes reports a change as done without running a check that exercises it". S6 would prune the one instruction Anthropic says Sonnet needs.
- **The three-fix-cycle rule (D10) cannot judge judgement-shaped findings.** "Judge each one by running the checks again, never by asking the reviewer" is vacuous when the finding was "this criterion is unfaithful" or "this contract returns the wrong error": no existing check tests it. Your own CLAUDE.md non-vacuity guard names this failure. The fix is one sentence: a judgement finding is fixed only when the fixer has turned it into a check.
- **Nothing in the essay or the plan measures whether the method pays.** METR found developers who were 19% slower believed they were 20% faster. The essay's confidence is exactly the kind of self-estimate that study shows is unreliable, and the repository's own record (229 of 504 commits on machinery, 32 on method) says the pipeline, not the method, consumed the effort. D9 is the most important ruling of the day and it is right.

## 2. Findings, ranked by severity

### F1. The token cap D7 relies on is not a platform feature (plan §A5; essay §13)

- **Claim:** "Fan-out only inside pd's workflows ... Each run is launched with a token budget, a hard ceiling: once it's spent, further agent calls fail."
- **What is wrong:** No such option exists. The workflows reference lists the run constraints: 16 concurrent agents, 1,000 agents per run, 4,096 items per call, and a `Large workflow` warning when projected tokens pass 1.5M. "The warning is advisory: it doesn't pause or limit the run." The size guideline is "advice, not a cap". The budget flags that exist are `--max-budget-usd`, "(print mode only)", and the SDK's query-level `maxBudgetUsd`. There is also "no limit on the total number of subagents Claude can spawn over a session" (`CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION` was removed in v2.1.224).
- **Evidence:** https://code.claude.com/docs/en/workflows ; https://code.claude.com/docs/en/cli-reference ; https://code.claude.com/docs/en/sub-agents
- **Why it matters:** §13 says "A limit the run can talk itself past is not a limit." Under D7 the only hard limits are depth (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`) and concurrency; both bound rate, not total. A single turn that launches a workflow can spend the whole budget before the Stop hook sees the transcript.
- **Recommendation:** Either run unattended work only through `claude -p --max-budget-usd` (where the cap is real and "Spend from subagents counts toward the cap"), or keep the PreToolUse spawn counter and the Stop-hook token cap AND make the `Workflow` tool deny-listed under `/goal`, so the per-turn spend stays bounded by one agent. Correct §A5 so it no longer claims a ceiling the runtime lacks.

### F2. `/goal`'s evaluator judges prose, and the plan's mitigation does not close the gap (plan §A5, §A9)

- **Claim:** goal conditions "name the output of `pd-status` and `pd-lint`, real command runs".
- **What is wrong:** the evaluator "doesn't run commands or read files independently"; it reads what Claude printed. A condition phrased as "pd-lint printed 0 errors" is satisfied by Claude printing that sentence. Your old `yolo-stop.sh` read state from disk; the replacement reads transcript text. That is a regression in exactly the §10 sense ("verification is execution, not opinion").
- **Evidence:** https://code.claude.com/docs/en/goal
- **Recommendation:** Keep the deterministic Stop hook (a script that runs `pd-lint` and `pd-status` itself) as the gate; use `/goal` only as the "keep going" driver. The goal doc says this split is the intended design: a Stop hook "can run a script for deterministic checks".

### F3. §7's self-verification claim is model-specific and contradicts §15 (essay §7; ruling S6)

- **Claim:** "What the brief no longer needs is an instruction to check its own work. Current models do that unprompted, and telling them to buys more checking, not better checking."
- **What is wrong:** true for Opus 5 ("instructions like these cause over-verification on Claude Opus 5"), false as a universal. Anthropic's Fable 5 guide: "Make self-verification explicit in long-run prompts." Sonnet 5.5 guide: at low effort it "sometimes reports a change as done without running a check that exercises it", and the documented fix is a verification paragraph in the system prompt. D7 puts executors on Sonnet. The essay's own §15 says instructions that compensate for model weakness "should be revisited each time the models change"; §7 states one as permanent.
- **Evidence:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5 ; .../prompting-claude-fable-5 ; .../prompting-claude-sonnet-5-5
- **Recommendation:** Keep the structural sentence ("The proof that counts is the one that runs outside the executor"). Replace the universal claim with: "Whether the brief also asks the executor to run its check depends on the executor model and effort; check the model's guide." Pin the verification paragraph in the Sonnet executor's agent definition, not in a skill.

### F4. D10's "checks, never the reviewer" cannot judge judgement findings (essay §11; plan §A2, §A4)

- **Claim:** "allow up to three fix cycles, and judge each one by running the checks again, never by asking the reviewer again."
- **What is wrong:** Three classes of review finding exist: (a) a failing check, (b) a missing check (test gap, unfaithful criterion), (c) a wrong decision (contract shape, error type). Re-running existing checks judges only (a). For (b) and (c) the existing suite is green before and after the fix; the rule declares the fix done on evidence that never tested it. The plan's `verify` workflow says blockers are "fixed or rejected with evidence", and the conductor judges that evidence; the conductor is the author's own session, which is the self-judging §11 warns against.
- **Evidence:** your CLAUDE.md "Non-vacuity test guard"; Huang et al. show self-judged correction degrades (GPT-4 GSM8K 95.5 to 91.5 to 89.0 over two rounds), https://arxiv.org/abs/2310.01798 (2023 models, reasoning QA, so transfer is uncertain).
- **Recommendation:** Add one rule: a judgement finding counts as fixed only when the fixer adds a check that fails on the pre-fix code and passes after. If no such check can be written, that finding is a hard stop (it belongs in §13's list), or it gets exactly one targeted re-judgement by the reviewer scoped to that finding. That keeps "no confirmatory re-review" for the whole change while closing the hole.

### F5. §11's quantitative language has no source (essay §11)

- **Claims:** "by a wide margin", "at a rate comparable to the rate at which they fix", "negative expected value", "three is about the ceiling".
- **What the evidence supports:** direction, not magnitude. Self-preference bias exists (Panickssery et al., "self-preference"), self-repair "performance gains are often modest" and "self-repair is bottlenecked by the model's ability to provide feedback on its own code" (Olausson et al.), Self-Refine reports "diminishing returns" across iterations, intrinsic self-correction can degrade (Huang et al.). All are 2023-24 results on GPT-3.5/GPT-4-class models. None measures an independent reviewer iterating on code with 2026 models, and Anthropic reports Opus 5.5 reviewers show "more bugs caught than on Claude Opus 5 and fewer false alarms", so the breakage rate is moving. "Three" appears nowhere; it is your heuristic.
- **Evidence:** https://arxiv.org/abs/2404.13076 ; https://arxiv.org/abs/2306.09896 ; https://arxiv.org/abs/2303.17651 ; https://arxiv.org/abs/2310.01798 ; https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5
- **Recommendation:** Say what you can defend: "Independent review beats self-review; iteration has diminishing returns; in my own record confirmatory passes found nothing N of N times." Drop "comparable rate" unless you measure it from `log.md`. Reframe "three" as a budget, not a ceiling ("I stop at three because the fourth has never paid for itself here").

### F6. §12 says going back should be cheap; S4 and the plan make it expensive

- **Claim:** "Discovering an earlier stage was wrong is the process working... when going back is expensive or reads as failure, both agents and people fudge forward."
- **What is wrong:** S4 lists "a backward move" as a retro trigger, and §A2 invalidates `plan.md` on any `shape.md` change. So one backward step costs a regenerated plan plus a full retrospective. That is the incentive §12 warns against, built into the rules beside it.
- **Recommendation:** A backward move writes one `log.md` line. The retro trigger is the second backward move in a feature, or a post-merge defect. Keep the `from_shape` invalidation (it is the §5 sweep made mechanical) but let the conductor re-confirm the hash when the change is local.

### F7. The method has no measurement of itself (missing)

- **What is wrong:** Nothing records whether a full-depth feature ships with fewer post-merge defects, or at what token and wall-clock cost, than an express one. METR's 2025 RCT: developers "take 19% longer than without" yet "still believed AI had sped them up by 20%". Their 2026 follow-up calls its own data "an unreliable signal". The point is not that your method slows you down; it is that nobody can tell from belief, and §14 asks for lessons as checks while the method itself has none.
- **Evidence:** https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ ; https://metr.org/blog/2026-02-24-uplift-update/ (early-2025 Cursor/Claude 3.5-3.7 setting; may not transfer)
- **Recommendation:** `log.md` already exists. Record per feature: depth taken, tokens, wall-clock, human turns, fix cycles used, defects found after merge. After twenty features, compare express against full. That is one `pd-status` column and the only way §15's "trim the scaffolding" gets evidence instead of taste.

### F8. Test quality is argued, never checked (essay §3, §7, §10)

- **What is wrong:** "Faithfulness" and "sufficiency" are left to judgement, and the proving command is a test the planner wrote. Coverage is a poor proxy: one 2025 study found "some test suites achieve 100% coverage but only 4% mutation score". A mechanical check for vacuous tests exists (mutation testing, or at minimum: the proving test must fail on the pre-change tree) and the essay does not use it.
- **Evidence:** https://arxiv.org/abs/2506.02954
- **Recommendation:** Add to §7's task shape a fourth clause: the proving command must be shown red before the task starts (the planner or merger runs it against base). That is cheaper than mutation testing and kills the commonest vacuity.

### F9. S1's rejection is right in principle and too absolute in practice (ruling D8/S1; essay §1)

See §4 below. The strongest case against three fixed phases is your own record: design, inventory and playbook ran 6,053 lines against a 15k-line change, and the half-sweep defect class that `from_shape` exists to catch recurred seven times across exactly the artifact boundary a merge would remove. The essay already owns the resolution: §2 says entry picks depth. Make the Contracts/Plan split collapsible under §2 for features below a size, rather than universal.

### F10. Minor factual and consistency notes

- §6 "This is not a cost-saving measure" sits beside D7, which chose Sonnet as a cost measure. Either own the cost argument or drop the disclaimer.
- §8 "a fan-out multiplies tokens many times over" is supported: "multi-agent systems use about 15× more tokens than chats" (Anthropic). Cite it.
- §11 "A reviewer told to find gaps will find some" is supported almost verbatim by Claude Code's docs ("will usually report some, even when the work is sound"; "Chasing every finding leads to over-engineering"). Cite it.
- §14's "seven times" is your repository's record (CLAUDE.md "100% gate-caught / 0% prevented"). Say so; it is the best evidence in the essay.
- Plan §A4: subagents cannot call `AskUserQuestion` (stripped from every subagent) and workflows take "No mid-run user input". The conductor design handles this; the essay's §13 "stop and ask" should say the stop must surface in the main session, since a stopped subagent is just a returned result.

## 3. Per-principle table

| § | Verdict | Reason |
|---|---|---|
| 1 Every stage kills a named unknown | Keep | Exit-on-resolved-unknowns, not document-exists, is the essay's best idea. The new "converse" paragraph is a defence of S1's rejection; it belongs in §2 as a depth rule. |
| 2 Entry depth matches uncertainty | Keep, extend | Also list the collapse of Contracts+Plan as a depth choice (F9). Add an express criterion the essay itself states (plan has one; essay does not). |
| 3 Behaviour before architecture | Keep, revise | Add the mechanical half of faithfulness: show the predicate red before build (F8). |
| 4 Contracts are the hand-off | Keep | Sound and well-exampled. "A small model reliably satisfies a pinned signature" is plausible but unsourced; soften to "satisfies far more reliably than it infers". |
| 5 One fact, one home | Keep | Your seven-occurrence record is the proof; cite it here, not only in §14. |
| 6 Thinking goes where wrong is expensive | Revise | Direction supported (Olausson: feedback quality is the bottleneck). Drop "not a cost-saving measure"; add executor-model escalation after a failed cycle (§4 below). |
| 7 Dispatchable only if verifiable | Revise | Keep contract/proof/files and "least code". Replace the universal self-check claim with a model-conditional one (F3). Add "proof shown red first". |
| 8 Narrow scope, smartest owns seams | Keep | Fan-out cost paragraph is right and citable. |
| 9 Every claim needs grounding | Keep | Note that CodeGraph/LSP make it cheap now (plan §A8.2 says this; essay should). |
| 10 Verification is execution | Keep | Simplification-as-lens paragraph is correct; a post-review rewrite is an unreviewed change. |
| 11 Three is the ceiling | Revise | Keep one-pass-per-moment; remove unsourced magnitudes; add the judgement-finding rule (F4, F5). |
| 12 Going back is normal | Keep, reconcile | Reconcile with S4's backward-move trigger (F6). |
| 13 Stop rather than guess | Revise | Budget paragraph is right in intent; the mechanism D7 names does not exist (F1). "Stop" from a subagent must surface in the conductor. |
| 14 Lessons become checks | Keep, extend | Add a retirement rule for checks (§15 applies to `pd-lint` too) and a cost trigger for retros. |
| 15 Some rules are scaffolding | Keep | Apply it to §7 and §11, which currently state scaffolding as structure. |

## 4. The rulings

**S1 (keep Criteria, Contracts, Plan separate): partly disagree.** The user's principle is right: sequencing-and-proof is a different question from what-crosses-each-boundary, and the plan's proving commands must be written by the stronger model before any executor sees them (§7). But "two distinct angles" does not require two documents and two gates for every feature. The record says the artifact boundary is where facts rot (seven half-sweep occurrences, the `from_shape` hash exists only to police it), and the plan phase has no independent check at all under S2, so it is the cheapest phase to fold. I would overturn "always three" to "three by default; Contracts and Plan may be written in one sitting under §2 when the plan is under N tasks, with `plan.md` still a separate file so the executor receives only its task." That keeps the angle and loses a gate where the gate caught nothing.

**S2 (three reviews, plan by lint): agree.** Placement by expected cost of being wrong is correct, and dropping the plan reviewer is justified by the mechanical nature of the plan's checks. One caveat: the plan is where the proving commands live, and a vacuous proving command is a judgement defect lint cannot see. F8's "red first" rule is the mechanical substitute.

**D10 (one review, three fix cycles by checks): agree with the F4 carve-out.** Without it the rule is a vacuous-green machine for exactly the findings that matter most.

**S3 (no simplifier step): agree.** The Sonnet 5.5 and Fable 5.1 guides both document that the minimum-code instruction works ("it may fix nearby code, extend behavior the task didn't mention" responds to an explicit leave-out instruction). A post-review rewrite is an unreviewed change. Correct.

**S4 (retros by trigger): agree, with two additions.** All four triggers are failure signals; a feature that passed every gate at three times the budget never triggers one. Add a cost-overrun trigger and a periodic sample (every tenth feature). And F6: a single backward move should not be a trigger, or §12 is fiction.

**S5 (fan out only when it pays): agree.** Supported by Anthropic's 15× figure and the Opus 5 guidance to "cap delegation".

**S6 (prune instructions for older models): agree in principle, disagree with §7's execution.** The Fable 5 guide says prior-model skills are "often too prescriptive"; true. But the same page says to make self-verification explicit, and the Sonnet 5.5 guide gives a verification paragraph because the model skips checks at low effort. Pruning is per model, and the executor is the model with the documented gap.

**D7 verify phase: agree.** Execution and verification are different unknowns; §1 demands the split.

**D7 Sonnet executors: agree as a default, not a rule.** The guide says "For the hardest long-horizon work, an Opus model is the better choice." Add: a task that fails its first fix cycle is re-run on the strongest model before it costs a second cycle or a human. That is cheaper than the human stop §13 reaches for.

**D7 `/goal` with caps: disagree as specified.** F1 and F2. The intent is right; the named mechanism is partly imaginary. Use `-p --max-budget-usd` for truly unattended runs, and a script Stop hook as the gate.

**D9 (retire the state machine): agree, strongly.** 35k lines of production Python and 97k of tests to run 8k lines of method, 229 commits on machinery versus 32 on method, and the plugin switched off since September while the work continued by hand. The method survived without the machinery for three weeks; that is the bake-off.

## 5. Missing

- **Measurement of the method** (F7). One `log.md` record per feature, compared across depths.
- **Test quality beyond "faithfulness"** (F8). Red-before-green on proving tests; mutation testing for the security and migration cases that §2 already sends to full depth.
- **Security as a standing obligation, not a finish-time trigger.** "Security surface" is self-declared by the planner; nothing checks the declaration. A one-line lint (new route, auth, shell, SQL, file write in the diff) should force the trigger rather than trust it.
- **Human attention as the bottleneck.** The conductor stops at criteria confirmation, escalations, and hard stops. Nothing bounds how many stops a day you can absorb, and unattended runs under F1 will produce them in bursts. Say what the human's queue is and what waits.
- **Cost accounting.** Tokens per phase and per model tier, so §6's "cost follows consequence" is a measurement rather than a slogan.
- **When the method is overkill.** The plan has an express path; the essay does not state one. Claude Code's own guidance: "If you could describe the diff in one sentence, skip the plan."
- **Check retirement.** §14 turns lessons into checks; §15 prunes instructions. Nothing prunes checks, and `pd-lint` will grow the way CLAUDE.md did (2,961 words, 1,114 of them retro-derived).

## 6. The case against the whole approach

**The argument.** Frontier time horizons double every 89 to 131 days under METR's TH1.1; Anthropic describes Opus 5.5 running "multi-hour audits and migrations" with "little oversight" and tells Opus 5 users to remove verification scaffolding. If one model can carry a change through a repository until tests pass, then criteria documents, contract documents, plan documents, hashes between them and seven gates are a 2024 harness strapped to a 2026 model. The essay's own record supports the charge: planning weighed a third of the change, machinery took 229 commits, and Phase R was still unfinished after three weeks.

**My verdict.** The charge lands on the pipeline and misses the principles. METR's predeployment evaluation of Opus 5.5 says it "still has qualitative weaknesses that an expert human is unlikely to exhibit" on hard long-horizon tasks; Anthropic's harness post found Claude verified end-to-end only "once explicitly prompted to use browser automation tools"; the Sonnet 5.5 guide documents claiming done without a run; the Fable 5.1 guide documents unrequested scope. Every one of those is a failure the structural principles (§3, §4, §5, §7's proof-outside-author, §10) exist to catch, and none of them is a document. What the models are outgrowing is the ceremony: three artifacts where one would do for a small feature, prescriptive skill steps, self-check instructions for models that self-check. The essay already says this in §15. The honest position is that the method is a verification discipline that costs almost nothing when the work is small (one runnable criterion, one proof, one file set) and earns its documents only when §2 says the uncertainty is large. Written that way, no model generation makes it obsolete, because it never depended on the model being weak; it depended on the author not being the judge.

The real risk is not that the models outgrow the method. It is the one the record already shows: that the tooling grows until it is the work. D9 addresses that. Keep it.

## 7. Sources

Anthropic documentation and engineering

- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5 — VERIFIED (saved copy; "over-verification", "do not use subagents to verify or double-check your own work", "cap delegation")
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5 — VERIFIED (saved copy; "Make self-verification explicit in long-run prompts", "often too prescriptive")
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1 — VERIFIED (saved copy; "fix nearby code, extend behavior the task didn't mention")
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5 — VERIFIED (fetched today; "reports a change as done without running a check", "Opus model is the better choice", "tends to add tests, documentation")
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5 — VERIFIED (saved copy; "fewer false alarms", "multi-hour audits and migrations")
- https://code.claude.com/docs/en/goal — VERIFIED (fetched today; "doesn't run commands or read files independently")
- https://code.claude.com/docs/en/workflows — VERIFIED (fetched today; "The warning is advisory", "No mid-run user input", "advice, not a cap")
- https://code.claude.com/docs/en/cli-reference — VERIFIED (fetched today; `--max-budget-usd` "(print mode only)")
- https://code.claude.com/docs/en/env-vars — VERIFIED (fetched today; `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION` removed)
- https://code.claude.com/docs/en/sub-agents — VERIFIED (fetched today; no total spawn limit; `AskUserQuestion` stripped)
- https://code.claude.com/docs/en/agent-sdk/typescript — VERIFIED (fetched today; `maxBudgetUsd` is query-level; no per-workflow budget found in first 100k chars; remainder UNREAD)
- https://code.claude.com/docs/en/best-practices — VERIFIED (saved copy; "will usually report some, even when the work is sound", "skip the plan", "biased toward code it just wrote")
- https://www.anthropic.com/engineering/multi-agent-research-system — VERIFIED (saved copy; "about 15× more tokens")
- https://www.anthropic.com/engineering/building-effective-agents — VERIFIED (saved copy; "simplest solution possible")
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents — VERIFIED (saved copy; "once explicitly prompted to use browser automation tools")

METR

- https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ — VERIFIED (fetched today; "19% longer", "sped them up by 20%"; early-2025 models)
- https://metr.org/blog/2026-02-24-uplift-update/ — VERIFIED (fetched today; "unreliable signal", "-18% ... -38% and +9%")
- https://metr.org/blog/2026-1-29-time-horizon-1-1/ — VERIFIED (saved copy; "89 days under TH1.1")
- https://metr.org/blog/2026-09-22-claude-opus-5-5/ — VERIFIED (fetched today; "qualitative weaknesses that an expert human is unlikely to exhibit")

Papers (all pre-2025 models unless noted; transfer to 2026 models is uncertain)

- https://arxiv.org/abs/2310.01798 Huang et al., ICLR 2024 — VERIFIED (saved full text; Table 3 figures; "struggle to self-correct ... without external feedback")
- https://arxiv.org/abs/2306.09896 Olausson et al., ICLR 2024 — VERIFIED (abstract; "gains are often modest", "bottlenecked by the model's ability to provide feedback")
- https://arxiv.org/abs/2303.17651 Madaan et al., Self-Refine — VERIFIED (saved full text; "diminishing returns")
- https://arxiv.org/abs/2404.13076 Panickssery et al. — VERIFIED (abstract; "self-preference")
- https://arxiv.org/abs/2506.02954 MutGen, 2025 — VERIFIED (abstract; "100% coverage but only 4% mutation score")
- https://arxiv.org/abs/2412.18531 Cihan et al., ICSE SEIP 2025 — VERIFIED (abstract; "73.8% of automated comments were resolved"; PR closure time rose)
- https://www.uber.com/blog/ureview/ — VERIFIED (fetched today; "tune out and ignore them", "75% of its comments as useful"; practitioner evidence, not peer-reviewed)

Not verified

- Any figure for "three" review or fix cycles — UNVERIFIED (no source found; appears to be the author's heuristic)
- "reviewers break correct work at a rate comparable to the rate at which they fix incorrect work" — UNVERIFIED as stated; nearest evidence is Huang et al. self-correction on QA, which is a different setting
- A published measurement of planning-first gain for coding agents — UNVERIFIED (none found; the plan doc already notes this)
