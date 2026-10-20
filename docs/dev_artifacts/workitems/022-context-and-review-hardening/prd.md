# PRD: Implementation Context Scoping, Strategic Awareness, and Review Pipeline Hardening

## Status
- Created: 2026-02-13
- Last updated: 2026-02-13
- Status: Draft
- Problem Type: Technical/Architecture

## Problem Statement

iflow-dev's multi-phase pipeline already passes each phase's output as input to the next: prd.md -> spec.md -> design.md -> plan.md -> tasks.md -> code. Traceability is enforced by reviewers at each transition. The artifacts ARE the lineage graph.

But seven concrete problems remain — three in implementation context, three in the review pipeline, and one in context window management:

**Implementation context:**
1. **Token overload at implementation:** The implement command loads ALL prior artifacts (prd + spec + design + plan + tasks) into every reviewer and fix-iteration prompt — regardless of which task is being worked on. For large features, this wastes context window on irrelevant sections.
2. **Implementation decisions vanish:** The implementer agent makes trade-off decisions and deviates from the plan, but these are not recorded. The retro phase has only git diffs and reviewer findings — no structured record of *why* the agent chose approach X over Y, or what it changed from the original design.
3. **Strategic context lost by implementation time:** The project PRD and priorities are injected during `/specify` and `/design` (via workflow-transitions Step 5), but by the time an agent is coding task 5 of 8, the strategic "why" has been compressed into a task description and a "Why" field. The agent has no sense of where this task fits in the bigger picture.

**Review pipeline:**
4. **Phase-reviewer blind to domain reviewer failures:** When a domain reviewer (spec-reviewer, design-reviewer, plan-reviewer, task-reviewer) exhausts its 5-iteration cap without approval, the command proceeds to the phase-reviewer "with warning." But the phase-reviewer's prompt only receives the artifact content — it gets no signal that the domain reviewer failed, how many iterations it took, or what issues remain unresolved. It can approve an artifact the domain reviewer explicitly rejected.
5. **Post-planning reviewers have no external verification:** The spec-reviewer, design-reviewer, and plan-reviewer all have WebSearch and Context7 tools to verify library/API claims against reality. But the security-reviewer and implementation-reviewer — which validate code against design — only have Read/Glob/Grep. If the artifact chain has a shared incorrect assumption (e.g., wrong API behavior), no downstream reviewer can catch it.
6. **Knowledge bank entries have no validation or expiry:** Anti-patterns and heuristics are written once by retrospectives and trusted forever. No creation date, no observation count, no process to challenge or retire stale entries. A wrong heuristic compounds across every future feature.

**Context window management:**
7. **Compact failure during multi-subagent orchestration:** When multiple parallel subagents complete near-simultaneously, their results all land in the main context at once. Combined with a large system prompt (CLAUDE.md @ references, 40+ skill descriptions, 25+ agent types), the context hits its limit. Compaction fires — but all 4 SessionStart hooks match the `compact` event and re-inject context (workflow state, secretary awareness), partially defeating the compaction. The sequence: system prompt ~35% of window → conversation grows during orchestration → agent results arrive → context limit → compact fires → hooks re-inject → compact struggles or fails.

### Evidence
- Implementation receives ALL prior artifacts wholesale — Evidence: `plugins/iflow-dev/commands/implement.md:98-245`
- No structured decision/deviation recording — Evidence: No `decisions` or `deviations` fields anywhere in iflow-dev plugin (grep confirmed)
- Project context injected at phase level, not task level — Evidence: `plugins/iflow-dev/skills/workflow-transitions/SKILL.md:115-148` (Step 5 runs during phase startup, not per-task)
- JetBrains Research: simple context reduction achieved 2.6% higher solve rates, 52% cheaper — Evidence: https://blog.jetbrains.com/research/2025/12/efficient-context-management/
- Progressive disclosure (metadata first, detail on demand): 70% token reduction, 35% accuracy improvement — Evidence: https://lethain.com/agents-large-files/
- Phase-reviewer receives no domain reviewer outcome — Evidence: `plugins/iflow-dev/commands/specify.md:107-128` (prompt has artifact content and next-phase expectations only; no domain reviewer result)
- When domain reviewer fails at cap, command "proceeds to Stage 2 with warning" but warning is not forwarded to phase-reviewer — Evidence: `specify.md:92-94`, `design.md:252`, `create-plan.md:59`, `create-tasks.md:85-87` (note: create-tasks.md uniquely omits "with warning" — it silently proceeds)
- Post-planning reviewers lack external tools — Evidence: `security-reviewer.md:5` (tools: Read, Glob, Grep), `implementation-reviewer.md:5` (tools: Read, Glob, Grep) vs `spec-reviewer.md:5` (has WebSearch, Context7)
- Knowledge bank has no dates, counts, or challenge process — Evidence: `docs/dev_artifacts/knowledge-bank/anti-patterns.md` (8 entries, none with dates or validation metadata)
- All 4 SessionStart hooks match `compact` event, re-injecting context during compaction — Evidence: `plugins/iflow-dev/hooks/hooks.json:5,14,23,32` (matcher: `startup|resume|clear|compact`)
- session-start.sh injects workflow state (active feature, command list) on every compact — Evidence: `plugins/iflow-dev/hooks/session-start.sh` (finds active feature, outputs available commands)
- Parallel subagent results cause context spikes — Evidence: Brainstorming Stage 2 dispatches 3 agents simultaneously; implementing skill may dispatch multiple task agents; each result lands in main context at full size

## Goals

1. **Reduce implementation context** by loading only the design/plan sections relevant to the current task, using references already present in the task "Why" field
2. **Record implementation decisions and deviations** per task in a structured format the retro phase can consume
3. **Inject strategic context during task implementation** so the coding agent knows where this task fits in the project/feature priorities
4. **Signal domain reviewer outcome to phase-reviewer** so handoff decisions are informed by prior review results, not blind to them
5. **Give post-planning reviewers external verification** so security and implementation claims can be checked against reality, not just the internal artifact chain
6. **Add validation lifecycle to knowledge bank entries** so stale or incorrect heuristics are challenged rather than compounding silently
7. **Stop SessionStart hooks from firing on compact events** so compaction can actually reclaim context instead of being defeated by re-injection

## Success Criteria

- [ ] Implementation phase loads only the referenced design/plan sections for each task (not full artifacts)
- [ ] Falls back to full artifact loading when references are missing or unparseable
- [ ] Every completed task has a structured record of decisions made, deviations from design, and files changed
- [ ] Retro phase reads the implementation log as a data source
- [ ] Features within a project receive a project priority summary during implementation
- [ ] No regression in existing workflows — features without project context or without "Why" references continue to work identically
- [ ] Phase-reviewer prompt includes domain reviewer outcome (approved/failed, iteration count, unresolved issues)
- [ ] Security-reviewer and implementation-reviewer have WebSearch and Context7 tools, with at least 1 external verification required
- [ ] Knowledge bank entries have "Last observed" metadata; retro skill validates cited entries; entries unfreshened for 10+ features flagged as stale
- [ ] SessionStart hooks do not fire on compact events — compaction reclaims context without re-injection
- [ ] `./validate.sh` passes with zero errors

## Solution: Seven Targeted Changes

### Prerequisite: Explicit Per-Task Dispatch in Implementing Skill

**Current state:** The implementing skill (`implementing/SKILL.md`) is a high-level guide: it describes Phase 1 (deploy subagents by domain), Task Selection (pick next incomplete task), and Phase 2/3 (RED-GREEN/REFACTOR). But it does not have an explicit per-task dispatch loop that constructs a distinct prompt per task. Tasks are worked on sequentially by the implementer agent within a single session — the context is the entire implementing skill prompt, not a per-task injection.

**Required change:** Make the implementing skill's task loop explicit: for each task in tasks.md, construct a Task tool dispatch to the implementer agent with task-specific context (scoped artifacts, project context, etc.), collect the agent's report (including implementation log entry), then proceed to the next task. Each per-task dispatch includes the full TDD cycle (Interface, RED-GREEN, REFACTOR) — the current skill's phases become the implementer agent's internal workflow per task, not the orchestrating skill's phases. This structural change is the foundation all three changes below depend on.

**Where to change:** `plugins/iflow-dev/skills/implementing/SKILL.md` — restructure the task selection and execution flow into an explicit per-task dispatch pattern.

### Change 1: Parse "Why" Field for Selective Context Loading

**Current state:** tasks.md may contain per-task traceability references in two known formats:
```
**Why:** Implements Plan 3.2 / Design Component Auth-Module    (features 017+)
**Source:** Spec C4.1, Plan 1A.1                                (feature 019)
```
Only features created after feature 017 (which added the Why field to the task template) use this pattern. Older features (002-016) have no traceability field. The implement command ignores any traceability fields and loads ALL of design.md and plan.md into every prompt.

**Change:** When the implementing skill prepares context for each task:
1. Parse the task's "Why" or "Source" field to extract plan section (e.g., "3.2" or "1A.1") and design component (e.g., "Auth-Module" or "C4.1")
2. Extract only the referenced `## Auth-Module` section from design.md and the referenced plan item from plan.md
3. Include spec.md in full (it's the contract), but scope design.md and plan.md to referenced sections only
4. Include the prd.md Problem Statement and Goals sections only (not full PRD)
5. **Fallback:** If the "Why" field is missing, unparseable, or the referenced section isn't found, load the full artifact and log a warning

**Where to change:**
- `plugins/iflow-dev/skills/implementing/SKILL.md` — the task context preparation step where each task is dispatched to the implementer agent
- `plugins/iflow-dev/agents/implementer.md` — the agent's system prompt to reflect scoped context
- **NOT** the review phase (implement.md lines 98-245) — reviewers retain full artifact loading because cross-cutting validation (spec compliance, design alignment, PRD delivery) requires the complete picture

**Fix iterations (implement.md step 6d):** When reviewers find issues and the implementer agent is dispatched for fix iterations, full artifact context is used — same rationale as reviewers. Fix iterations address cross-cutting reviewer findings (e.g., "this code doesn't match the spec"), so they need the complete picture. Only the initial per-task dispatch uses scoped context.

**Coverage note:** Only features created after feature 017 (evidence-grounded-phases) have the Why/Source traceability field. For older features or features with unrecognized formats, the fallback to full artifact loading is the expected and correct behavior. The benefit of Change 1 is forward-looking — all new features use the template that includes the Why field.

**Why not a manifest:** The "Why" field already contains the information needed. Formalizing it into a separate JSON file would duplicate what's already in the artifact, adding maintenance burden with no new information.

### Change 2: Implementation Decision Log

**Current state:** The implementer agent reports "files changed" and "concerns" in freeform text that is not persisted. The review-history.md captures reviewer findings but not implementer reasoning.

**Change:** Add a per-feature `implementation-log.md` (in the feature directory, alongside spec.md, design.md, etc.) that the implementer agent appends to after completing each task:

```markdown
## Task 3: Add Redis cache adapter
- **Files changed:** src/cache/redis.ts, src/cache/interface.ts
- **Decisions:** Used Redis over Memcached because interface contract requires TTL per key
- **Deviations:** Added retry logic not specified in design — needed for connection drops
- **Concerns:** Connection pool sizing may need tuning under load
```

Note: Review iterations are not included per-task because the review phase (implement.md step 6) reviews all tasks at once, not individually. Review data is already captured in .review-history.md.

**Mechanism:**
- The implementer agent's report format already includes "files changed" and "concerns" — extend it with explicit "decisions" and "deviations" fields
- The implementer agent appends a structured markdown entry to `implementation-log.md` after completing each task, as part of its report step (same pattern as how it already reports files changed and concerns — extend, don't add a separate step)
- The retro skill (`plugins/iflow-dev/skills/retrospecting/SKILL.md`) reads this file as a new context bundle sub-step (Step 1c: Implementation Log, inserted between Review History (b) and Git Summary — bumping existing c-e to d-f) — with graceful degradation: "if file doesn't exist, note no implementation log available"
- `/finish` (`plugins/iflow-dev/commands/finish.md`) deletes implementation-log.md after retro reads it (same lifecycle as .review-history.md — requires adding to finish's cleanup list)

**Why markdown, not JSON:** Consistent with .review-history.md pattern. Readable by humans. Appendable without read-modify-write. The retro agent is an LLM — it reads markdown better than JSON.

### Change 3: Strategic Context Injection at Task Level

**Current state:** workflow-transitions Step 5 injects project PRD and dependency feature context at phase startup. This means `/specify` and `/design` get project context, but by implementation time, the strategic "why" is buried in the design artifact, not visible as a distinct signal.

**Change:** When the implementing skill prepares context for a task in a project-linked feature:
1. Read the project PRD's `## Goals` and `## Problem Statement` sections (2-3 paragraphs, not the full PRD)
2. Read the project `roadmap.md` for milestones and feature sequencing
3. Glob feature directories under `docs/dev_artifacts/workitems/` matching `depends_on_features` from this feature's `.meta.json`, read each feature's `.meta.json` to determine completed/active/blocked status (same pattern as workflow-transitions Step 5, but summarized compactly)
4. Prepend a brief "Project Context" block to the implementation prompt:

```
## Project Context
**Project:** {project name} | **This feature:** {feature name} ({module})
**Project goals:** {2-3 bullet summary from project PRD goals}
**Feature dependencies:** {completed: X, Y | in-progress: Z | blocked: W}
**Priority signal:** {milestone this feature belongs to, if any}
```

This gives the implementer agent enough strategic context to make trade-off decisions ("this is the MVP milestone, keep it simple" or "this feature blocks 3 others, be thorough") without flooding the context with the full project PRD.

**Coverage note:** Change 3 builds on project infrastructure from feature 021 (project-level-workflow) which has been implemented but not yet used — no projects exist in the codebase yet. This change is entirely forward-looking. Graceful degradation (skip when no project_id) ensures non-project features are unaffected.

**Where to change:**
- `plugins/iflow-dev/skills/implementing/SKILL.md` — add project context loading when preparing per-task context, similar to workflow-transitions Step 5 but scoped to individual task dispatch
- `plugins/iflow-dev/agents/implementer.md` — update system prompt to reference the project context block

### Change 4: Signal Domain Reviewer Outcome to Phase-Reviewer

**Current state:** Every command with a two-stage review process (specify, design, create-plan, create-tasks) follows the same pattern: domain reviewer runs first (up to 5 iterations), then phase-reviewer validates handoff readiness. When the domain reviewer exhausts its cap without approval, the command "proceeds to Stage 2 with warning" — but that warning is internal to the orchestrating command. The phase-reviewer's prompt receives only the artifact content and "next phase expectations." It has no visibility into whether the domain reviewer approved, failed at cap, or how many iterations occurred.

**Change:** Include a `## Domain Reviewer Outcome` block in every phase-reviewer prompt:

```markdown
## Domain Reviewer Outcome
- Reviewer: {spec-reviewer | design-reviewer | plan-reviewer | task-reviewer}
- Result: {APPROVED at iteration {n}/{max} | FAILED at iteration cap ({max}/{max})}
- Unresolved issues: {list of remaining blocker/warning issues from final iteration, or "none"}
```

This lets the phase-reviewer make informed decisions. An artifact approved at iteration 1 with zero issues is qualitatively different from one that failed at cap with 3 unresolved blockers. The phase-reviewer can factor this into its own approval: e.g., flag a warning like "Domain reviewer did not approve; these unresolved issues may affect the next phase."

**Mechanism:** The orchestrating command retains the domain reviewer's final response in its working context (it already parses the `approved` field and `issues` array to decide pass/fail). When constructing the phase-reviewer prompt, it extracts the reviewer name, iteration count, approval status, and any remaining blocker/warning issues from this response. No additional .meta.json reads needed — the data is already in the command's execution context.

**Where to change:**
- `plugins/iflow-dev/commands/specify.md` — Stage 2 phase-reviewer prompt (lines ~107-128)
- `plugins/iflow-dev/commands/design.md` — Stage 4 phase-reviewer prompt (lines ~295-340)
- `plugins/iflow-dev/commands/create-plan.md` — Stage 2 phase-reviewer prompt (lines ~67-110)
- `plugins/iflow-dev/commands/create-tasks.md` — phase-reviewer prompt (lines ~112-146)

### Change 5: External Verification for Post-Planning Reviewers

**Current state:** Three early-phase reviewers have external verification tools:
- spec-reviewer: WebSearch, Context7 — "MUST verify at least 1 library/API claim"
- design-reviewer: WebSearch, Context7 — "MUST independently verify at least 2 claims"
- plan-reviewer: WebSearch, WebFetch, Context7

But post-planning reviewers that validate code against design have no external tools:
- security-reviewer: Read, Glob, Grep only
- implementation-reviewer: Read, Glob, Grep only
- code-quality-reviewer: Read, Glob, Grep only
- task-reviewer: Read, Glob, Grep only

If the entire artifact chain shares an incorrect assumption (e.g., "library X supports feature Y" verified at spec time but deprecated by implementation time), no downstream reviewer can catch it.

**Change:** Add WebSearch and Context7 to the two reviewers where external verification is most impactful:
1. **security-reviewer** — verify security claims (e.g., "this hashing algorithm is current best practice", "this auth pattern follows OWASP guidelines"). Add instruction: "MUST verify at least 1 security-relevant claim via WebSearch or Context7."
2. **implementation-reviewer** — verify library/API usage against current documentation (e.g., "this API endpoint accepts these parameters"). Add instruction: "MUST verify at least 1 library/API usage claim via Context7."

**Why not all post-planning reviewers:** task-reviewer and code-quality-reviewer validate internal consistency (task ordering, code structure) — external verification adds no value there. Security and implementation are where external reality diverges from internal assumptions.

**Where to change:**
- `plugins/iflow-dev/agents/security-reviewer.md` — Add WebSearch, Context7 to tools list; add verification instruction section (matching spec-reviewer pattern at lines 148-151)
- `plugins/iflow-dev/agents/implementation-reviewer.md` — Add WebSearch, Context7 to tools list; add verification instruction section

### Change 6: Knowledge Bank Validation Lifecycle

**Current state:** `docs/dev_artifacts/knowledge-bank/anti-patterns.md` (8 entries) and `docs/dev_artifacts/knowledge-bank/heuristics.md` (7 entries) are written by retrospectives. Each entry has an "Observed in: Feature #NNN" field referencing the first observation, but no subsequent validation. Entries are trusted indefinitely. The retro skill only adds new entries — it never challenges, updates, or retires existing ones.

**Change:** Add a lightweight validation lifecycle:

1. **Entry metadata:** Add `- Last observed: Feature #NNN` and `- Observation count: N` to each knowledge bank entry template. The first observation sets both. Subsequent observations increment the count and update the feature reference.

2. **Retro validation step:** Add a sub-step to the retro skill's knowledge bank update phase. The retro agent reads ALL knowledge bank entries (currently ~15 total across both files — bounded and grows slowly) and checks each against the feature's git diff, implementation-log.md, and .review-history.md for relevance. For each entry that was relevant to this feature's experience: Was this anti-pattern/heuristic accurate? If confirmed, update 'Last observed' and increment count. If contradicted, add a '- Challenged: Feature #NNN — {reason}' line. Entries not relevant to this feature are skipped (no update needed).

3. **Staleness signal:** Entries not re-observed for 10+ features get a `⚠️ STALE` marker prepended by the retro skill. The count is determined by globbing `docs/dev_artifacts/workitems/` directories with feature numbers higher than the entry's "Last observed" feature number — this counts actual features created, not number arithmetic (avoids false staleness from numbering gaps). Stale entries are not auto-deleted — the retro surfaces them for user review: "The following knowledge bank entries haven't been observed in 10+ features: {list}. Keep, update, or retire?"

**Why feature-count, not time:** Features are the natural clock for this codebase. An entry not re-observed across 10 actual features has had enough opportunity to be tested — enough to question relevance regardless of calendar time.

**Where to change:**
- `docs/dev_artifacts/knowledge-bank/anti-patterns.md` — Add metadata fields to existing entries
- `docs/dev_artifacts/knowledge-bank/heuristics.md` — Add metadata fields to existing entries
- `plugins/iflow-dev/skills/retrospecting/SKILL.md` — Add validation sub-step to the knowledge bank update phase
- Knowledge bank entry template (in retrospecting skill references) — Update template with new metadata fields

### Change 7: Remove `compact` from SessionStart Hook Matchers

**Current state:** All 4 SessionStart hooks in `hooks.json` match `startup|resume|clear|compact`. When context compaction fires, these hooks re-execute: `sync-cache.sh` syncs plugin files, `cleanup-locks.sh` removes stale locks, `session-start.sh` injects workflow state (active feature, available commands), and `inject-secretary-context.sh` injects secretary awareness. This re-injection partially defeats compaction — the system reclaims space from conversation history but immediately fills it with re-injected hook output.

**Root cause analysis:** Three factors compound:
1. **Large system prompt:** CLAUDE.md @ references, 40+ skill descriptions, 25+ agent type descriptions consume ~35% of the context window as a non-compactable baseline.
2. **Parallel subagent results:** Multi-agent dispatches (brainstorming Stage 2 dispatches 3 agents, implementing skill dispatches per-task agents) produce results that all land in the main context, causing sudden spikes.
3. **Hooks defeat compaction:** When the spike triggers compaction, hooks re-inject context that was just compressed. This is the only factor that's a plugin-level bug — the other two are architectural realities.

**Change:** Remove `compact` from the SessionStart hook matchers:

Before: `"matcher": "startup|resume|clear|compact"`
After: `"matcher": "startup|resume|clear"`

**Rationale:** The compacted summary already retains workflow context — the hooks don't need to re-inject it. `sync-cache.sh` and `cleanup-locks.sh` are filesystem operations that don't need to run mid-conversation on compaction. `session-start.sh` workflow state is already in the conversation context (just compacted). `inject-secretary-context.sh` awareness persists through compaction.

The hooks still fire on `startup` (new session), `resume` (continuing session), and `clear` (user reset) — all cases where fresh injection is needed.

**Where to change:**
- `plugins/iflow-dev/hooks/hooks.json` — Change all 4 SessionStart matchers from `startup|resume|clear|compact` to `startup|resume|clear`

## User Stories

### Story 0: Per-Task Dispatch Loop
**As the** implementing skill **I want** an explicit per-task dispatch loop **so that** each task gets its own Task tool call to the implementer agent with task-specific context, and I can collect structured reports per task.
**Acceptance criteria:**
- For each incomplete task in tasks.md, a distinct Task tool dispatch is constructed
- Each dispatch includes task-specific context (scoped artifacts, project context)
- The implementer agent's report is collected and processed (including implementation-log.md entry) before proceeding to the next task
- The TDD cycle (Interface, RED-GREEN, REFACTOR) is the implementer agent's internal workflow per task

### Story 1: Task-Scoped Implementation
**As an** implementation agent **I want** to receive only the design/plan sections relevant to my current task **so that** my context window is focused on what matters.
**Acceptance criteria:**
- "Why" field is parsed to extract design/plan references
- Only referenced sections loaded into prompt
- Fallback to full loading when references are missing

### Story 2: Decision Recording
**As a** retro agent **I want** a structured log of implementation decisions and deviations per task **so that** I can identify where plans broke down and produce specific recommendations.
**Acceptance criteria:**
- implementation-log.md is appended per task with decisions, deviations, files changed
- Retro skill reads the log
- Log is cleaned up by /finish after retro

### Story 3: Strategic Awareness
**As an** implementer agent working on task 5 of a project feature **I want** to know the project's goals and where my feature fits **so that** I can make trade-off decisions aligned with the bigger picture.
**Acceptance criteria:**
- Project context block prepended to implementation prompts for project-linked features
- Non-project features skip this (no error)
- Context is compact (project goals + feature status, not full project PRD)

### Story 4: Informed Handoff Decisions
**As a** phase-reviewer **I want** to know whether the domain reviewer approved or failed at cap **so that** I can factor prior review quality into my handoff decision rather than evaluating the artifact blind.
**Acceptance criteria:**
- Phase-reviewer prompt includes domain reviewer name, result (approved/failed), iteration count, and unresolved issues
- Phase-reviewer can reference unresolved domain issues in its own findings

### Story 5: External Reality Check at Code Review
**As a** security-reviewer **I want** to verify security claims against current best practices **so that** I catch deprecated algorithms or patterns that the internal artifact chain assumed were safe.
**Acceptance criteria:**
- Security-reviewer has WebSearch and Context7 tools
- Security-reviewer must verify at least 1 security claim externally
- Implementation-reviewer has same tools with at least 1 library/API verification

### Story 6: Knowledge Bank Hygiene
**As a** retro agent **I want** to validate knowledge bank entries against this feature's experience **so that** stale or wrong heuristics don't compound across future features.
**Acceptance criteria:**
- Entries have "Last observed" and "Observation count" metadata
- Retro validates relevant entries: confirm, challenge, or flag stale
- Entries not observed for 10+ features flagged with staleness marker
- Stale entries surfaced to user for keep/update/retire decision

### Story 7: Compaction Survives Multi-Agent Sessions
**As a** user running multi-agent workflows (brainstorming, implementing) **I want** compaction to actually reclaim context **so that** long sessions don't fail with context overflow after parallel subagent results arrive.
**Acceptance criteria:**
- SessionStart hooks do not fire on compact events
- Compaction can reclaim conversation context without re-injection
- Hooks still fire on startup, resume, and clear

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Implementer agent dispatch fails mid-task | Log error, mark task as blocked, ask user whether to retry or skip | Don't silently proceed with broken state |
| Implementer agent report is malformed/missing fields | Log warning, write partial implementation-log.md entry with available fields, proceed to next task | Graceful degradation over hard failure |
| tasks.md has no incomplete tasks | Skip implementation, report all tasks already complete | Self-detecting, no error |
| Task has no "Why" field | Load full artifacts | Backward compatibility |
| "Why" references non-existent heading in design.md | Log warning, load full design.md | Don't block implementation |
| Feature has no project_id | Skip project context injection | Non-project features are unchanged |
| Project directory or roadmap.md is missing | Skip project context, log warning | Graceful degradation |
| implementation-log.md doesn't exist yet | Create it on first task completion | Self-initializing |
| Retro runs on feature without implementation-log.md | Fall back to current behavior (git + review-history) | Pre-existing features work fine |
| Domain reviewer not invoked (e.g., future command without domain review) | Phase-reviewer prompt omits Domain Reviewer Outcome block | Graceful absence, not error |
| Domain reviewer fails but phase-reviewer approves anyway | Valid outcome — phase-reviewer assesses handoff sufficiency, not domain correctness | Informed disagreement is acceptable |
| WebSearch/Context7 unavailable for security/implementation reviewer | Flag claims as "Unable to verify — external tools unavailable" | Same pattern as spec-reviewer fallback |
| Implementation has no external library/API claims (pure internal logic) | Reviewer notes "No external claims to verify" and proceeds without external verification | Don't force meaningless verification |
| Knowledge bank entry challenged by retro but user keeps it | Entry retains staleness marker but is not deleted | User has final authority |
| Feature numbering gap (e.g., #008 to #020 with few features between) | Staleness counts actual feature directories created (glob), not number arithmetic | Avoids false staleness from numbering gaps |
| Retro runs on very first feature (#001) | No knowledge bank entries exist to validate; skip validation step | Self-initializing |
| Plugin updated but user has old hooks.json cached | sync-cache.sh (which fires on startup/resume) handles cache refresh; compact exclusion takes effect after next startup | Existing cache mechanism covers this |
| Future hook needs compact event | Add `compact` back to that specific hook's matcher only; don't blanket-match all hooks | Per-hook decision, not global |

## Constraints

### Behavioral
- Must NOT introduce new metadata files that duplicate existing artifact content — Rationale: The artifacts ARE the lineage graph. Don't create a parallel representation.
- Must NOT change the task template in breaking-down-tasks — Rationale: The "Why" field format already works. Just parse what's there.
- Must NOT make project context mandatory — Rationale: Many features are standalone, not part of a project.

### Technical
- Section extraction from markdown relies on heading parsing — headings are frozen post-approval but could vary in format
- implementation-log.md follows .review-history.md lifecycle (append during implementation, read by retro, deleted by finish)
- Project context adds ~200-500 tokens per task prompt — negligible compared to the tokens saved by selective loading

## Requirements

### Functional
- FR-0: Implementing skill restructured with explicit per-task dispatch loop (construct Task call to implementer with task-specific context, collect report, proceed to next)
- FR-1: Implementing skill parses task "Why" or "Source" traceability field to extract design/plan section references when preparing per-task context (other formats or missing fields fall through to full loading)
- FR-2: Context loading extracts only referenced sections from design.md and plan.md using markdown heading matching
- FR-3: Spec.md is always loaded in full (it's the interface contract)
- FR-4: PRD is loaded with Problem Statement and Goals sections only
- FR-5: Fallback to full artifact loading when "Why" parsing fails or section not found
- FR-6: Implementer agent report format extended with "decisions" and "deviations" fields
- FR-7: Implementer agent appends per-task entry to implementation-log.md as part of its completion report
- FR-8: Retro skill reads implementation-log.md as additional data source (added to retrospecting context bundle)
- FR-9: /finish deletes implementation-log.md after retro reads it (added to finish.md cleanup list)
- FR-10: For project-linked features, implementing skill loads project goals and feature status
- FR-11: Project context prepended as compact block (~200-500 tokens) to implementation prompts
- FR-12: Phase-reviewer prompt in all two-stage review commands includes Domain Reviewer Outcome block (reviewer name, result, iteration count, unresolved issues)
- FR-13: Security-reviewer agent has WebSearch and Context7 tools with "MUST verify at least 1 security claim if present; if no external claims exist, note this explicitly" instruction
- FR-14: Implementation-reviewer agent has WebSearch and Context7 tools with "MUST verify at least 1 library/API claim if present; if no external claims exist, note this explicitly" instruction
- FR-15: Knowledge bank entry template includes "Last observed: Feature #NNN" and "Observation count: N" metadata
- FR-16: Retro skill reads ALL knowledge bank entries (brute-force scan, bounded by entry count ~15), checks each against feature artifacts for relevance, and validates relevant entries — confirms, challenges, or updates metadata
- FR-17: Retro skill flags entries not re-observed for 10+ actual features (counted by globbing feature directories, not number arithmetic) as stale and surfaces to user for review
- FR-18: All 4 SessionStart hook matchers in hooks.json changed from `startup|resume|clear|compact` to `startup|resume|clear`

### Non-Functional
- NFR-1: Selective loading reduces design.md/plan.md context to the referenced sections only
- NFR-2: implementation-log.md append is part of the implementer agent's existing report step — extends generation by a few sentences per task, with negligible file I/O overhead
- NFR-3: Project context loading reads project prd.md sections, roadmap.md, and dependency feature .meta.json files — same sources as workflow-transitions Step 5
- NFR-4: All changes are backward-compatible — features without "Why" fields or project context work identically to today
- NFR-5: Domain Reviewer Outcome block adds ~100-200 tokens to phase-reviewer prompt — negligible overhead
- NFR-6: External verification in security/implementation reviewers adds 1-2 tool calls per review — bounded by "at least 1" instruction (not exhaustive)
- NFR-7: Knowledge bank staleness check adds <30 seconds to retro — reads existing entries and compares feature numbers
- NFR-8: Removing `compact` from hook matchers is a single-line change per hook entry — zero risk of behavioral regression for startup/resume/clear events

## Non-Goals

- **manifest.json or parallel metadata layer** — The artifacts themselves carry all lineage information. Adding a JSON metadata file would duplicate existing content.
- **Cross-feature concept search** — Searching across features by topic/concept. Potentially valuable but premature without evidence it's needed.
- **Formal derived_from graph** — The task "Why" field and the sequential artifact chain already encode lineage. Formalizing it adds maintenance without new information.
- **Organizational trade-off encoding** — Agents use project goals and common sense for trade-offs, not encoded decision logic.

## Out of Scope (This Release)

- **Effort tracking (planned vs actual)** — Tracking how long each task/phase takes vs estimates. Would enable budget-aware decision-making. — Future: Could be added to .meta.json phase tracking.
- **Implementation observation masking** — SWE-Agent's pattern of compressing older observations. Orthogonal to these changes. — Future: After measuring implementation context sizes.
- **Agent Trace integration** — Cursor/Cognition's line-level AI attribution spec. — Future: When spec stabilizes.

## Research Summary

### Internet Research
- **JetBrains Research**: Simple observation masking achieved 2.6% higher solve rates, 52% cheaper than unmanaged context. Simpler beats sophisticated. — Source: https://blog.jetbrains.com/research/2025/12/efficient-context-management/
- **Progressive disclosure**: Load metadata first, full content on demand. 80% faster, 70% token reduction, 35% accuracy improvement. — Source: https://lethain.com/agents-large-files/
- **Google ADK artifact handles**: Artifacts tracked by lightweight reference, not embedded. "Ephemeral expansion" for on-demand loading. — Source: https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/
- **Aider repo-map**: Graph ranking to select relevant context from dependency graph. Default 1k tokens, dynamically expanding. — Source: https://aider.chat/docs/repomap.html
- **Traycer spec-driven dev**: All artifacts in epic automatically in context. Executions view tracks every agent handoff. — Source: https://docs.traycer.ai/tasks/epic

### Codebase Analysis
- Implementation receives ALL prior artifacts in every prompt — Location: `plugins/iflow-dev/commands/implement.md:98-245`
- Task "Why" field already contains design/plan references — Location: `plugins/iflow-dev/skills/breaking-down-tasks/SKILL.md:131-141`
- Project context injection exists at phase level (Step 5) but not at task level — Location: `plugins/iflow-dev/skills/workflow-transitions/SKILL.md:115-148`
- .review-history.md lifecycle (append/read/delete) is the model for implementation-log.md — Location: `plugins/iflow-dev/commands/implement.md:267-287`
- Implementer agent already reports files changed and concerns — Location: `plugins/iflow-dev/agents/implementer.md:75-83`
- Phase-reviewer prompt has no domain reviewer signal — Location: `plugins/iflow-dev/commands/specify.md:107-128` (same pattern in design.md, create-plan.md, create-tasks.md)
- Domain reviewer cap bypass is silent — Location: `specify.md:92-94` ("Proceed to Stage 2 with warning" — warning not forwarded)
- External tools split: spec/design/plan reviewers have WebSearch+Context7; task/implementation/code-quality/security reviewers do not — Location: agent frontmatter `tools:` field comparison
- Knowledge bank entries have no dates or validation metadata — Location: `docs/dev_artifacts/knowledge-bank/anti-patterns.md`, `docs/dev_artifacts/knowledge-bank/heuristics.md`
- Retro only adds to knowledge bank, never challenges existing entries — Location: `plugins/iflow-dev/skills/retrospecting/SKILL.md`

### Existing Capabilities
- **workflow-transitions Step 5**: Already loads project PRD and dependency features at phase startup. Change 3 extends this pattern to task-level implementation.
- **breaking-down-tasks "Why" field**: Already contains the section references needed. Change 1 just parses what's there.
- **.review-history.md pattern**: Append during phase, read by retro, delete on finish. Change 2 follows this exact lifecycle.
- **implementer agent report format**: Already structured with sections for files changed, test results, concerns. Change 2 extends with decisions/deviations.

## Structured Analysis

### Problem Type
Technical/Architecture — Context engineering for implementation agents with strategic awareness injection.

### SCQA Framing
- **Situation:** iflow-dev has a mature pipeline where each phase's output feeds the next. Traceability is enforced by reviewers. The artifacts ARE the lineage graph. The infrastructure works.
- **Complication:** Seven gaps span three areas. Implementation context: (1) all artifacts loaded regardless of task relevance, (2) implementation decisions not recorded, (3) strategic project context not visible. Review pipeline: (4) phase-reviewer blind to domain reviewer failures, (5) post-planning reviewers can't verify external claims, (6) knowledge bank entries never challenged. Context window: (7) SessionStart hooks defeat compaction by re-injecting context.
- **Question:** How do we improve implementation context quality, review pipeline reliability, and context window stability without adding a parallel metadata layer?
- **Answer:** Seven targeted changes: parse existing "Why" references for selective loading, add an implementation log, inject project goals at task level, signal domain reviewer outcomes, add external verification to post-planning reviewers, add knowledge bank validation lifecycle, and stop hooks from fighting compaction. Build on what exists rather than creating new infrastructure.

## Comparative Analysis: Original manifest.json Proposal vs This Approach

### What We Adopted
| Proposal Idea | How We Adopted It |
|---------------|-------------------|
| Record implementation decisions/deviations | implementation-log.md with per-task entries (Change 2) |
| Selective context loading | Parse existing "Why" field instead of new derived_from graph (Change 1) |
| Retro reads structured implementation data | Retro reads implementation-log.md (Change 2) |
| Minimal disruption to existing pipeline | All three changes modify implementing skill + implementer agent + retro + finish, no new schema |

### What We Rejected (and Why)
| Proposal Idea | Why Rejected |
|---------------|-------------|
| manifest.json per feature | Duplicates lineage already in artifacts. Maintenance burden without new information. |
| derived_from graph | Task "Why" field already contains these references. Formalizing adds a parallel system. |
| concepts/tagging | No evidence cross-feature concept search is needed yet. Premature abstraction. |
| Per-phase manifest entries | Each phase's output IS its manifest entry. The artifact file is the record. |

### What We Added Beyond the Proposal
| New Idea | Why It Matters |
|----------|---------------|
| Strategic context at task level (Change 3) | The proposal's "global direction" aspiration. Neither the proposal nor the original iflow-dev pipeline delivers this during implementation. |
| Domain reviewer outcome signaling (Change 4) | Discovered during self-confirming loop analysis. Phase-reviewer was blind to domain review failures — a structural gap not addressed by the proposal. |
| External verification for post-planning reviewers (Change 5) | Discovered during blindspot analysis. The proposal's "give retro the manifest" idea assumed good inputs; we found that bad inputs can propagate unchecked past planning. |
| Knowledge bank validation lifecycle (Change 6) | The proposal didn't address organizational learning. We found that iflow-dev's learning mechanism (knowledge bank) has no feedback loop — entries compound without challenge. |
| Compact-safe hook matchers (Change 7) | The proposal didn't address operational stability. We found that SessionStart hooks firing on compact events defeat context reclamation during long multi-agent sessions. |

## Review History

### Review 0 (2026-02-13) — Original manifest.json version
**Findings:** 3 blockers (false certainty on token reduction, scope inflation, abbreviated content), 5 warnings, 2 suggestions.
**Corrections:** Goals reframed, cross-feature search descoped, migration strategy added, schema example added.

### Review 1 (2026-02-13) — manifest.json version approved
**Findings:** 0 blockers, 4 warnings (feature count, FR numbering, concurrency rationale, heading stability), 2 suggestions.
**Outcome:** Approved, but critical discussion revealed the manifest duplicates existing artifact lineage.

### Pivot (2026-02-13) — Simplified to three targeted changes
**Rationale:** The artifacts ARE the lineage graph. A parallel JSON metadata layer duplicates existing information. Instead: parse existing references (Change 1), add a simple log (Change 2), inject strategic context (Change 3). Less infrastructure, more impact.

### Review 2 (2026-02-13) — Simplified version, iteration 0
**Findings:** 2 blockers (Change 1 misidentified insertion point as implement.md review templates; Change 2 assumed per-task callback in implement command), 4 warnings, 2 suggestions.
**Corrections:**
- Change 1: Clarified "Where to change" — implementing skill + implementer agent for task dispatch, reviewers retain full context
- Change 2: Changed mechanism from "implement command appends" to "implementer agent appends as part of its completion report"
- Change 3: Changed "Where to change" from implement.md to implementing skill + implementer agent
- FR-1,7,8,9,10: Updated to reference correct components (implementing skill, implementer agent, retro skill, finish.md)
- Clarified implementation-log.md location (feature directory)
- Noted retro skill and finish.md as explicit change surfaces

### Review 3 (2026-02-13) — Simplified version, iteration 1
**Findings:** 1 blocker (implementing skill lacks explicit per-task dispatch loop — all three changes assume it exists), 4 warnings (Why field not validated against real data, fix-iteration scoping unaddressed, retro bundle slot unspecified, project .meta.json doesn't exist), 2 suggestions.
**Corrections:**
- Added "Prerequisite: Explicit Per-Task Dispatch" section establishing the foundational mechanism all three changes depend on
- Added FR-0 for the dispatch loop prerequisite
- Clarified fix iterations use full context (same rationale as reviewers)
- Specified retro context bundle slot (Step 1f: Implementation Log, between Review History and Git Summary)
- Fixed Change 3 data sources: roadmap.md + feature directory globbing (matching workflow-transitions Step 5 pattern), not a non-existent project .meta.json

### Review 4 (2026-02-13) — Simplified version, iteration 2
**Findings:** 1 blocker (Why field coverage overstated — only 2/19 features use it, Source field variant not mentioned), 4 warnings (retro slot lettering, Change 3 forward-looking, TDD phase mapping, FR-1 scoping), 2 suggestions (review iterations per-task impossible, Source field in Open Questions).
**Corrections:**
- Blocker: Acknowledged Why field is not universal — only features after 017 use it. Added Source field as recognized variant. Added coverage notes for Changes 1 and 3.
- Retro slot: Fixed to Step 1c (between b and c), bumping existing c-e to d-f
- Change 3: Added note that project infrastructure exists but no projects created yet (forward-looking)
- Prerequisite: Clarified TDD phases become implementer agent's internal workflow per task
- FR-1: Expanded to include "Why" or "Source" with explicit fallback for other formats
- Removed review iterations from per-task log template (reviews happen at aggregate level)
- Open Questions: Expanded with Source field, alphanumeric plan refs, and older features without traceability

### Review 5 (2026-02-13) — Post-expansion review, iteration 0
**Findings:** 2 blockers, 4 warnings, 3 suggestions.
**Corrections:**
- Blocker: FR-16 unimplementable — specified concrete mechanism (retro reads ALL entries, brute-force scan bounded by ~15 entries, checks each against feature artifacts)
- Blocker: Change 4 evidence citations wrong (create-tasks.md:159 was phase-reviewer cap, not domain reviewer) — fixed to create-tasks.md:85-87; fixed line range to ~112-146
- Warning: Change 5 missing edge case for pure internal logic — added "no external claims" edge case and adjusted FR-13/14 wording
- Warning: Change 4 mechanism unspecified — added Mechanism section (orchestrating command retains domain reviewer's final response in working context)
- Warning: Prerequisite lacked user story and edge cases — added Story 0 and 3 prerequisite edge cases (dispatch failure, malformed report, no incomplete tasks)
- Warning: Staleness threshold misleading with feature number gaps — changed to actual feature count via globbing, updated FR-17 and edge case
- Suggestion: NFR-2 false precision — reworded to describe actual overhead (report extension, not file I/O timing)
- Suggestion: Added open questions 3-4 for Changes 4-6 (phase-reviewer behavior on failure, staleness visibility)

### Scope Expansion 2 (2026-02-13) — Added compact-safe hooks (Change 7)
**Rationale:** User reported recurring compact failures during multi-subagent sessions. Root cause analysis identified three compounding factors: large system prompt, parallel subagent result spikes, and SessionStart hooks re-injecting context on compact events. The first two are architectural realities; the third is a plugin-level bug fixable with a one-line-per-hook matcher change.
**Additions:**
- Change 7: Remove `compact` from SessionStart hook matchers (FR-18)
- 1 new user story, 2 new edge cases, 1 new NFR

### Scope Expansion 1 (2026-02-13) — Added review pipeline hardening (Changes 4-6)
**Rationale:** Analysis of self-confirming loop risks and agent blindspots revealed three structural gaps in the review pipeline that are independent of implementation context but critical for pipeline reliability. User selected these three from a broader list of eight identified gaps, classifying the rest as operational trade-offs.
**Additions:**
- Change 4: Signal domain reviewer outcome to phase-reviewer (FR-12)
- Change 5: External verification for security-reviewer and implementation-reviewer (FR-13, FR-14)
- Change 6: Knowledge bank validation lifecycle with staleness detection (FR-15, FR-16, FR-17)
- 3 new user stories, 7 new edge cases, 3 new NFRs

## Open Questions

1. **Traceability field parsing robustness**: Validated against real tasks.md files from completed features. Two field names and multiple formats exist:
   - **Why field:** `Implements Plan 1.1 / Design Component 1` (feature 017), `Implements Plan Step 1.1 / Design C9` (feature 021), `Implements Plan 1.1` (no design ref)
   - **Source field:** `Spec C4.1, Plan 1A.1` (feature 019) — note alphanumeric plan reference (1A.1)
   - Some tasks reference "Risk R1" instead of Design
   - Features 002-016 have no traceability field at all
   The parser must handle both field names, be lenient with format variation: extract plan section via regex (`Plan (?:Step )?(\w+\.\w+)` — allowing alphanumeric), extract design reference via regex (`Design (?:Component )?(\w+[-\w]*)` or `Spec (\w+\.\w+)`), and fall back to full artifact loading for unrecognized formats.
2. **Heading extraction accuracy**: Extracting a `## Component Name` section from design.md requires knowing where it ends (next `##` heading). Edge cases: nested `###` subheadings, components that reference other components. The parser should extract the heading and all content until the next same-level heading.
3. **Phase-reviewer behavior on domain reviewer failure**: Should the phase-reviewer treat domain reviewer failure as purely informational (report it in findings but don't change approval threshold) or as a signal to increase scrutiny (e.g., convert warnings to blockers)? The PRD currently frames it as informational — the phase-reviewer "can factor this into its own approval." This seems right for now; an explicit escalation rule can be added if data shows phase-reviewers routinely rubber-stamp failed domain reviews.
4. **Knowledge bank staleness visibility**: Should stale markers appear in the retro.md output (Act section) or only in the knowledge bank files themselves? Current design: retro surfaces stale entries to user via AskUserQuestion during the retro. The staleness markers live in the knowledge bank files. Retro.md could reference them but doesn't need to duplicate.

## Next Steps
Scope expanded to 7 changes across three areas. Ready for promotion to feature via /iflow-dev:create-feature.
