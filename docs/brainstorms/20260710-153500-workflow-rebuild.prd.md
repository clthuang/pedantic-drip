# PRD: Workflow Rebuild — Lean Canonical Workflow + Express Mode

**Status:** draft
**Source:** critical design review 2026-07-10 (evidence: two exploration sweeps over commands/skills + repo's own friction artifacts)
**Track:** 1 of 2 (companion: `20260710-153600-entity-db-redesign.prd.md`)

## Problem

The workflow's implementation is a 2024-era exoskeleton built for weaker models. Evidence:

- **~74,000 words** of orchestration prose (8,181 command lines + 5,616 skill lines). In the four artifact-producing commands (`implement`, `create-plan`, `design`, `specify`), **75–80% is defensive scaffolding + duplicated boilerplate**, not intent. `implement.md` review phase spans lines 210–1095.
- **Duplication:** the reviewer JSON schema restated 62× across 23 files (3× per reviewer per command); `resume_state` machinery 239 occurrences; codex-routing preamble copy-pasted in 11 files; 58 per-command YOLO override blocks.
- **Dispatch cost:** 33 subagent dispatches minimum (~85 at caps) per small feature. `implement` happy path alone ≥8 reviewer dispatches (mandatory full 4-reviewer re-validation even when all passed).
- **The loops don't earn their cost:** `docs/pd-audit-findings.md:13-39` (Severity: Critical) cites self-correction research (DeepMind: 7.6% of wrong fixed, 8.8% of right broken; Self-Refine: diminishing returns after 1-2 iterations). Feature 006: 38 review iterations for a docs-only feature (`heuristics.md:293`). Reviewer finds one nitpick per iteration until circuit breaker (`anti-patterns.md:419`). Final-validation counts against the iteration cap — the legitimate completion path can trip the circuit breaker (`anti-patterns.md:645`).
- **Complexity managing complexity:** resume_state / delta-size guards / context-compaction detection exist to manage the token cost of the loop design itself, not to guard any model failure.

## Requirements (user-stated, binding)

- **R1.1 — Single triaging entry.** Secretary remains the unified entry point.
- **R1.2 — Canonical workflow preserved in spirit.** Ground decisions on well-researched information; each step reduces uncertainty; narrow-purpose agents for specific tasks (avoid context pollution and blindspots); each step plots boundaries then gradually hones in to details; implementation coupled with independent QA and review agents to complete the task cycle.
- **R1.3 — Dual intensity.** Full deep-work pipeline OR shallow express mode for small / low-uncertainty tasks, selectable per task.

## Design Direction

### Keep (the essence per R1.2)
- The 6-phase spine as **deep mode**: brainstorm → specify → design → create-plan → implement → finish. Phases stay as uncertainty-reduction gates producing artifacts.
- Narrow-purpose research agents (codebase-explorer, internet-researcher, etc.) dispatched with scoped context — this is the anti-context-pollution mechanism and it works.
- Independent review/QA at each phase boundary and independent QA + review paired with implementation.
- Files-as-artifacts, resumability, bounded autonomy (a circuit breaker stays — final validation must NOT count against it).
- Model-independent guards: data-file single-writer, prompt-injection hardening in dispatches, MCP degradation ladders, prerequisite fail-fast (one line each, not 4-level message ladders).

### Change
- **Commands become contracts, not scripts.** Each phase command: inputs, output artifact, definition of done, constraints — target 200–500 words (from 1,000+ lines). Skills carry knowledge, not step-by-step procedure.
- **One review moment per phase, not two.** Replace skeptic + gatekeeper pairs with a single independent reviewer per phase whose contract covers both artifact quality and handoff readiness. Single pass + one fix round; escalate to user after that instead of iterating to a cap.
- **Implement QA shifts from prose-review loops to execution-based verification.** Independent QA agent runs the change (tests + drive the affected flow); the code reviewer does one adversarial pass. No mandatory second full-review round.
- **Reviewer schemas defined once** in each agent file; dispatching commands reference the agent, never restate the schema.
- **Secretary slims to triage-that-selects-mode** (satisfies R1.1 + R1.3 together): assess uncertainty/risk/blast-radius → route to deep mode (full pipeline), express mode, or a specialist. The 8-step DISCOVER→DELEGATE pipeline with 11 lookup tables is replaced by a short routing contract; the model routes natively.
- **One global YOLO rule** in workflow-transitions, replacing 15 per-command override blocks.

### Delete
- `resume_state` machinery (239 refs), delta-size guards (16), context-compaction detection (12), `Files read:` confirmation ritual (38), LAZY-LOAD warnings (13), JSON parse/retry ladders and per-command schema restatements, the mandatory post-pass full re-validation round.

### Express mode (new)
- For small / low-uncertainty tasks (triage decides; user can force either mode).
- Shape: inline mini-spec (a few sentences, recorded as an event) → implement → one combined QA+review pass → finish. Uses the same entity/DB state model (companion track) with skipped phases recorded, so tracking and auditability are uniform across modes.

## Non-goals
- No new phases, no new reviewer roles, no new state vocabulary (the DB track owns state modeling).
- Not rewriting agents' domain knowledge (DS/game/crypto packs untouched).

## Success criteria
- Orchestration prose ≤ ~10k words total across commands+skills (from ~74k).
- Small-feature deep-mode run ≤ 12 subagent dispatches (from 33–85); express run ≤ 4.
- Reviewer iterations: 1 pass + ≤1 fix round per phase; zero circuit-breaker trips on happy paths.
- All existing model-independent guards still in place (validate.sh + doc-drift gate green).

## Sequencing
Depends on the entity-db-redesign track for state writes (all workflow management goes through the DB there). Recommended order: **DB track first**, workflow rebuild second. The canonical phase vocabulary does not change, so the DB track can model phases now without waiting.

## Open questions
1. Express-mode audit trail: which artifacts are mandatory (mini-spec event only, or also a one-paragraph design note)?
2. Triage rubric for deep vs express: what signals (diff size estimate, novelty, blast radius, security surface) and can the user override mid-flight (escalate express → deep)?
3. Do brainstorm and specify merge into one "shape" phase in deep mode, or stay separate? (R1.2 says preserve the spirit — merging may still satisfy it; decide at design.)
4. Codex-routing preamble: factor into workflow-transitions once, or drop entirely while the toggle is disabled?
