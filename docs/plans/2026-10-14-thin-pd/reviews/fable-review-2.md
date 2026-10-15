# Fable review 2: the revised essay and plan (2026-10-14)

Reviewer: Fable 5.1, read-only, second pass. Scope: `docs/workflow-principles.md` (revised), `docs/workflow-principles.mmd`, both decks, and `docs/plans/2026-10-14-thin-pd-native-design.md` §A2–§A9, §15, Part B §6/§9/§11. The D12 architecture-diagram edit had landed in both the essay (§4, lines 147–155) and the plan (§A2 row 3, D12) when read; both were read once more before this was written.

## 1 Verdict

- **Essay: yes, publishable as the author's principles**, with one non-blocking repair: it now makes four empirical claims ("has been measured", "research on self-refinement reports", "Anthropic measured", "one controlled study") and carries no reference list. The sources exist (plan §A8.4) but a reader of the essay alone cannot see them. Add a short sources footer (five links) and it is clean.
- **Plan: yes, sound enough for calvin and then build**, with no blocker. The §A5 caps are now described accurately against Claude Code's real behaviour (verified below, including the `budget` hard ceiling). Three gaps calvin should press on are in §5: the token cap cannot end a `/goal` run on its own; red-first as specified is weaker than the essay claims; the small-feature trigger is circular.

## 2 The adopted fixes

| Item | Status | Evidence |
|---|---|---|
| F1 token cap that does not exist | **Resolved** | Plan §A5 lines 150–162 restates the caps as they work. Cap 1a (`budget` hard ceiling only when the user sets "+Nk") is VERIFIED against the workflow-authoring reference bundled with Claude Code: "The target is a HARD ceiling, not advisory" and spent() "is shared, not per-workflow". Cap 2 depth/concurrency, cap 3 `PreToolUse` on `Agent` (exit 2 blocks; `SubagentStart` "No"), cap 7 `--max-budget-usd` "(print mode only)" all match the docs |
| F2 `/goal` evaluator reading prose | **Resolved** | §A5 lines 131–136: script `Stop` gate "reads files, not the transcript", runs `pd-lint`/`pd-status`; `/goal` "only drives". Docs quote matches: "It doesn't run commands or read files independently" |
| F3 model-conditional self-check | **Resolved** | Essay §7 lines 221–225 ("depends on the model... others, run cheaply, skip it"); plan §A3 line 98 keeps Sonnet's verification paragraph, S6 line 304. One stale restatement remains: §A8.4 line 321 still says the capability "relaxes: Verification instructions in executor briefs", but executors are Sonnet (D7) and keep theirs |
| F4 judgement findings need a new check | **Resolved** | Essay §11 lines 299–303; plan §A2 line 55; §16 line 869 |
| F5 only sourced claims | **Resolved in substance, partly in form** | "wide margin", "comparable rate", "negative expected value", "about the ceiling" are gone; §11 now says "Three is a budget I chose, not a measured ceiling" (line 294–295). Each remaining empirical claim has a source in plan §A8.4, none in the essay itself. Two unsourced claims survive unchanged: §4 line 144 "A small model reliably satisfies a pinned signature"; §6 line 164 "a smaller, faster model does it well" |
| F6 backward move cost | **Resolved** | Essay §12 lines 328–329; plan §A2 line 72, S4 line 292, Part B §9 line 709 (trigger list says "two backward moves") |
| F7 measure the method | **Resolved** | Essay §15 lines 383–387 (METR study, unnamed); plan Part B §6 `metrics` entry, `pd-status --compare` (§11 line 737), §A2 row 7, §16 line 870 |
| F8 proof shown failing first | **Resolved, with a limit (§3 item 2)** | Essay §7 lines 186–189 incl. refactor exception; plan §A2 row 4, §A4 `implement` row (line 121) with the "behavior unchanged" exemption; §16 line 869; `.mmd` gate G3 |
| S4 one backward move is not a trigger | **Resolved** | Plan line 292 "One backward move is not a trigger"; essay §14 line 359 "a second step back" |
| D7c one escalation to the strongest model | **Resolved, ambiguous** | Plan §A2 line 56, §A3 line 97. Essay does not mention it (acceptable: a ruling, not a principle). Ambiguity for calvin: does the strongest-model re-run count as cycle 2, or sit between cycles 1 and 2 making four attempts? |
| S1 Contracts and Plan in one sitting | **Resolved; one stale block** | Essay §1 lines 43–48; plan §A2 lines 65–69. §A8.3 S1 (lines 259–268) and D8 (line 836) still read "Rejected... Keep all three" with no pointer to the D11 amendment |
| Decks | **Faithful to the revised essay and to each other** | Both decks changed by the same 79 lines; EN adds principles 14–15, "one pass, and a budget for fixes", "seen failing before the task starts", the diagram clause, the measurement line; zh-TW carries the same additions (十五條原則, 先親眼看到它失敗, 架構圖). Not checked line by line for translation accuracy |

## 3 New problems, ranked

1. **The token cap cannot end a `/goal` run on its own (plan §A5 cap 4, line 159; "When it lets the run end", line 134).** Two `Stop` hooks fire after every turn: the script gate and `/goal`'s own prompt-based hook ("`/goal` and a Stop hook both fire after every turn"). "All matching hooks run in parallel", and a goal clears only when "the condition is met", judged "impossible", a turn fails, or `/goal clear`. So when the gate "lets the run end past a budget", the goal hook still answers "not yet met" and starts another turn. Cap 4 bounds nothing unless the goal condition also names the budget. Fix: make the gate, on cap reached, block with exit 2 and a reason that instructs the conductor to call AskUserQuestion ("budget spent: continue or stop?"); the goal's "or the user has said to stop" clause then closes it. Also: the gate must honour `stop_hook_active` (docs: "Check this value... to avoid blocking on a condition that will never resolve"); `yolo-stop.sh` line 185 already does, the plan never says the port keeps it.
2. **Red-first, as specified, proves less than the essay says (plan §A4 `implement`, line 121; essay §7 lines 186–189).** The workflow runs "every task's proving command on the base". Task 3's test fails on the base whenever task 1's module does not exist yet: an ImportError is "red" and proves nothing about task 3. The essay's claim that this is "the commonest way a plan hands down a vacuous test" is right about already-green tests and silent about wrong-reason reds. Fix: the merger, which already runs each proving command in plan order, runs task N's command on the branch just before merging task N (expect red) and just after (expect green). Same agent, same loop, no extra stage; and the exemption flag for refactors becomes a `pd-lint` check on `plan.md` (Part B §9 lists no such check).
3. **The small-feature trigger is circular (plan §A2 line 65).** "at most `small_feature_tasks` tasks" is known only after the plan is written, but the choice to write Contracts and Plan together is made before. Fix: the trigger is decided at Triage and recorded in `mode` (an estimate, e.g. "one module, one proving command"); `pd-lint` flags a plan that exceeds the cap after the fact as a `phase` entry, not a failure.
4. **`metrics` restates facts whose home is `log.md` itself (Part B §6, lines 605–609; essay §5).** Wall-clock "from the first and last `log.md` entries" and "fix cycles used per phase" are derivable from the `phase`/`review`/`qa`/`gate` entries in the same file. Writing them again is the restatement §5 forbids and Part B §9's "One fact, one place" check does not cover. Fix: `metrics` holds only what is not elsewhere (depth, tokens, stops); `pd-status --compare` derives cycles and wall-clock.
5. **Stale restatements left by the sweep:** §A8.4 line 321 (executor briefs lose verification instructions; Sonnet executors keep them, §A3); §A8.3 S1 and D8 (no D11 pointer); the `.mmd` puts the independent review after Verification (G4 follows QA) while plan §A2/§A4 say "review beside QA"; the `.mmd` gives Behaviour a reviewer with "≤ 3 cycles" (G1B) while plan §A2 gives Criteria calvin plus the user's confirmation, with no fix loop.
6. **Essay §13 "bound each piece of work separately" is satisfied by the plan only for attended runs.** Cap 1a needs a user-typed "+Nk" on the turn; under `/goal`, turns after the first are started by the hook, not the user, so whether the target persists is UNVERIFIED. The plan says "when the user sets one" but does not draw the consequence: for unattended runs cap 1b (the script's own `budget.spent()` check against an args cap) is the only per-run bound. State that, and make 1b mandatory in every pd workflow.
7. **Minor:** essay §6 "This is not a cost-saving measure" (line 171) sits beside D7's Sonnet ruling and S5's token argument; own it or drop it (open from the first review). Essay §4 line 144 and §6 line 164 (weak-model competence) remain unsourced; soften to "far more reliably than it infers one".

## 4 Still open from the first review

- **Open, not adopted (the user's call, noted without re-arguing):** security-surface lint (F-list "Missing"); human-attention bound; check retirement; S4 periodic sample; cost accounting per model tier.
- **Open, unaddressed:** F10 §6 cost disclaimer; §4 "small model reliably" claim; the essay still states no express criterion of its own (F9 note: "plan has one; essay does not"); "rejected with evidence" in `verify` (§A4 line 122) is still judged by the conductor, the author's own session, which §11 warns against. F4's new-check rule covers the fix side, not the rejection side. Fix: a rejected blocker needs a file:line refutation recorded as a `review` entry, and `pd-status` counts it as open until the user or the next review sees it.
- **Closed:** F1–F8, F9 (via S1 small-feature), F10 items on 15× and "seven times", the subagent-cannot-ask note (essay §13 last paragraph, plan §A5).

## 5 Top three fixes

1. **Make the token cap end the run under `/goal`** (§3.1): gate blocks with exit 2 and an AskUserQuestion instruction on cap reached; keep `stop_hook_active`; add "the gate ends a goal-driven run at the cap" to §A7's bake-off list.
2. **Move red-first to the merger, per task, pre- and post-merge** (§3.2), and lint the refactor exemption. This is the one change that makes F8 deliver what the essay promises.
3. **Add a sources footer to the essay and sweep the five stale restatements** (§3.5, §2 F3/S1 rows). Ten minutes of edits; without them the essay carries unsourced "has been measured" language and the plan contradicts itself in three places a calvin pass will stall on.

## 6 Sources

VERIFIED (quote matched against fetched or bundled text today):
- Workflow authoring reference bundled with Claude Code (loaded via the `workflow-authoring` skill, no public URL): "The target is a HARD ceiling, not advisory"; "the pool is shared, not per-workflow"; "capped at min(16, available CPUs - 2)"; "capped at 1000".
- https://code.claude.com/docs/en/goal : "It doesn't run commands or read files independently"; "can run a script for deterministic checks"; "`/goal` and a Stop hook both fire after every turn"; "A goal doesn't change your permission mode"; clears on met / "impossible" / `/goal clear`.
- https://code.claude.com/docs/en/hooks : "All matching hooks run in parallel"; exit 2 on `Stop` "Prevents Claude from stopping"; `SubagentStart` "No"; `stop_hook_active` "Check this value".
- https://code.claude.com/docs/en/workflows : "The warning is advisory: it doesn't pause or limit the run"; "No mid-run user input".
- https://code.claude.com/docs/en/cli-reference : `--max-budget-usd` "(print mode only)"; "Spend from subagents counts toward the cap".
- https://code.claude.com/docs/en/env-vars : `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` "(default: 3)"; `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION` "Removed in v2.1.224 and now a no-op".
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5 : "can skip verifying a change"; "reports a change as done without running a check".
- https://www.anthropic.com/engineering/multi-agent-research-system : "use about 15× more tokens than chats".
- https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ : "they take 19% longer than without" (matched in saved METR research index).

UNVERIFIED:
- Whether a "+Nk" turn target persists into turns that a `/goal` hook starts (no doc statement found either way).
- Whether `PreToolUse` on `Agent` fires for workflow-script agents (plan §A7.6 already lists it for the bake-off).
- Translation accuracy of the zh-TW deck beyond the spot-checked additions.
