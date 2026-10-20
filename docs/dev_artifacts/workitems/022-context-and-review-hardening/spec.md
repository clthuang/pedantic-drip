# Specification: Context and Review Hardening

## Problem Statement

iflow-dev's implementation phase wastes context on irrelevant artifacts, loses decision rationale, lacks strategic awareness, has blind spots in the review pipeline (phase-reviewer blind to domain reviewer failures, post-planning reviewers can't verify external claims, knowledge bank entries never challenged), and SessionStart hooks defeat context compaction.

## Success Criteria

- [ ] SC-1: Per-task dispatch loop in implementing skill constructs distinct Task calls per task
- [ ] SC-2: Tasks with Why/Source traceability fields receive scoped design.md/plan.md sections (not full artifacts); spec.md always loaded in full
- [ ] SC-3: Tasks without traceability fields fall back to full artifact loading without error
- [ ] SC-4: Each completed task produces an implementation-log.md entry with decisions, deviations, files changed, and concerns
- [ ] SC-5: Retro skill reads implementation-log.md as context bundle Step 1c
- [ ] SC-6: /finish deletes implementation-log.md after retro
- [ ] SC-7: Project-linked features have code paths to receive project context block (~200-500 tokens: ~200 base for goals+priority, ~100 per dependency feature) per task; verified via code review per AC-9. Design phase decides whether to cap at ~500 tokens for large dependency lists.
- [ ] SC-8: Non-project features skip project context injection without error
- [ ] SC-9: Phase-reviewer prompts in all 4 two-stage commands include Domain Reviewer Outcome block
- [ ] SC-10: Security-reviewer has WebSearch + Context7 with "verify at least 1 claim if present" instruction
- [ ] SC-11: Implementation-reviewer has WebSearch + Context7 with "verify at least 1 claim if present" instruction
- [ ] SC-12: Knowledge bank entries have "Last observed" and "Observation count" metadata
- [ ] SC-13: Retro skill validates knowledge bank entries against feature experience (brute-force scan of all entries; first retro run calibration: feature author confirms no false positives, no obvious false negatives, challenge text is specific and actionable)
- [ ] SC-14: Entries not re-observed for 10+ actual features flagged as stale and surfaced to user
- [ ] SC-15: SessionStart hooks match `startup|resume|clear` only (not `compact`)
- [ ] SC-16: `./validate.sh` passes with zero errors

## Scope

### In Scope

**Prerequisite + Changes 1-3 (Implementation Context):**
- Restructure implementing skill into explicit per-task Task tool dispatch loop
- Tasks processed sequentially in document order (top to bottom in tasks.md); each gets its own Task tool dispatch
- Parse Why/Source field from tasks.md to extract design/plan section references
- Extract referenced sections from design.md and plan.md via heading matching (rules below)
- Load spec.md in full (always), PRD Problem Statement + Goals sections only (extract by exact heading text match: `## Problem Statement` and `## Goals`, each through next same-level heading)

**Traceability Field Parsing:**
- Split the Why/Source field value on comma (`,`) to produce individual reference strings. Apply the Plan/Design/Spec regex to each trimmed reference independently. Collect all matched sections.
- Regex per reference: `Plan (?:Step )?(\w+\.\w+)` for plan refs, `Design (?:Component )?(\w+[-\w]*)` for design refs (matches C9, Auth-Module, R-1, I-4), `Spec (\w+\.\w+)` for spec refs (informational — spec always loaded in full).

**Heading Extraction Rules (design.md and plan.md):**
- **Plan reference** (e.g., "Plan 3.2" or "Plan Step 1A.1"): Find the first heading (any level) whose text contains the reference identifier (e.g., "3.2" or "1A.1") as a substring. Plan headings vary across features: `### Step 3.2:`, `#### 3.2:`, `### 3.2 Title`.
- **Prefix fallback**: If the exact identifier (e.g., "1A.1") is not found in any heading, try matching the prefix before the last dot (e.g., "1A"). This handles features where sub-items are bold text (`**1A.1: filename**`) under a parent heading (`### 1A: Group`). The parent heading's section (including all bold sub-items within it) is extracted.
- **Design reference** (e.g., "Design Component Auth-Module" or "Design C9"): Find the first heading whose text contains the component identifier (e.g., "Auth-Module" or "C9") as a substring.
- **Spec reference** (e.g., "Spec C4.1"): Spec is always loaded in full; spec references in Source fields are informational only.
- **Section boundary**: Extract from the matched heading through the next heading at the same level (or end of file). Include all nested subheadings within the section.
- **No match**: If neither exact identifier nor prefix matches any heading, log a warning and fall back to loading the full artifact.
- Implementer agent report format extended with decisions and deviations fields
- Implementer agent appends structured entry to implementation-log.md per task
- Retro skill reads implementation-log.md (Step 1c, between Review History and Git Summary); retro-facilitator dispatch prompt (Step 2) also updated to include implementation-log section in context bundle
- /finish deletes implementation-log.md (same lifecycle as .review-history.md)
- Project context block (goals, dependencies, priority signal) prepended to project-linked task prompts

**Implementation-log.md Entry Template:**
```markdown
## Task N: {task title}
- **Files changed:** {list of files}
- **Decisions:** {decision + rationale, or "none"}
- **Deviations:** {deviation from plan/design + reason, or "none"}
- **Concerns:** {concerns for future attention, or "none"}
```

**Primary Modification Targets:**
- `plugins/iflow-dev/skills/implementing/SKILL.md` — per-task dispatch loop, context scoping, decision log appendage
- `plugins/iflow-dev/agents/implementer.md` — report format extension, project context block in prompt
- `plugins/iflow-dev/commands/implement.md` — implementer prompt template changes (NOT review templates)
- `plugins/iflow-dev/skills/retrospecting/SKILL.md` — implementation-log.md consumption (Step 1c), knowledge bank validation
- `plugins/iflow-dev/commands/finish.md` — implementation-log.md cleanup
- `plugins/iflow-dev/commands/specify.md`, `design.md`, `create-plan.md`, `create-tasks.md` — Domain Reviewer Outcome block in phase-reviewer prompts
- `plugins/iflow-dev/agents/security-reviewer.md`, `implementation-reviewer.md` — WebSearch + Context7 tools, verification instructions
- `docs/dev_artifacts/knowledge-bank/anti-patterns.md`, `heuristics.md` — metadata backfill
- `plugins/iflow-dev/hooks/hooks.json` — remove `compact` from SessionStart matchers

**Changes 4-6 (Review Pipeline Hardening):**
- Domain Reviewer Outcome block added to phase-reviewer prompts in specify.md, design.md, create-plan.md, create-tasks.md
- WebSearch + Context7 tools added to security-reviewer and implementation-reviewer agents
- Verification instruction section added to both agents (matching spec-reviewer pattern)
- Knowledge bank entry template updated with Last observed and Observation count metadata
- Existing entries in anti-patterns.md and heuristics.md backfilled with metadata
- Retro skill validation sub-step: read all entries, check against feature artifacts, confirm/challenge/flag stale

**Change 7 (Context Window):**
- Remove `compact` from all 4 SessionStart hook matchers in hooks.json

### Out of Scope

- manifest.json or any parallel metadata layer
- Cross-feature concept search or tagging
- Formal derived_from graph
- Organizational trade-off encoding
- Effort tracking (planned vs actual)
- Implementation observation masking (SWE-Agent pattern)
- Agent Trace integration
- Changes to the task template in breaking-down-tasks (parse existing format, don't change it)
- Changes to review templates in implement.md (reviewers keep full artifact loading)
- External tools for task-reviewer or code-quality-reviewer (internal consistency validators)

## Acceptance Criteria

### AC-1: Per-Task Dispatch Loop
- Given tasks.md with 3 incomplete tasks
- When implementing skill executes
- Then 3 separate Task tool dispatches to implementer agent are constructed in document order (top to bottom in tasks.md), each with task-specific context, and reports are collected sequentially

### AC-2: Selective Context Loading (With Traceability)
- Given a task with `**Why:** Implements Plan 3.2 / Design Component Auth-Module`
- When the implementing skill prepares context for that task
- Then only the `## Auth-Module` section from design.md and plan item 3.2 from plan.md are included; spec.md is included in full; PRD includes only Problem Statement and Goals sections

### AC-3: Selective Context Loading (Fallback)
- Given a task with no Why/Source field (or unparseable format)
- When the implementing skill prepares context
- Then full design.md, plan.md, spec.md, and PRD are loaded with a logged warning

### AC-4: Source Field Parsing
- Given a task with `**Source:** Spec C4.1, Plan 1A.1`
- When the implementing skill parses traceability
- Then Spec section C4.1 and Plan section 1A.1 (alphanumeric) are extracted correctly

### AC-5: Implementation Decision Log — Creation
- Given a task "Add Redis cache adapter" completed by implementer agent
- When the agent finishes its report
- Then implementation-log.md contains an entry with `## Task N: Add Redis cache adapter`, Files changed, Decisions, Deviations, and Concerns fields

### AC-6: Implementation Decision Log — Retro Consumption
- Given a feature with implementation-log.md containing 5 task entries
- When retro skill runs Step 1 context gathering
- Then implementation-log.md content is included as Step 1c between Review History (b) and Git Summary (d)

### AC-7: Implementation Decision Log — Cleanup
- Given a feature with implementation-log.md after retro has run
- When /finish executes cleanup
- Then implementation-log.md is deleted (same as .review-history.md)

### AC-8: Implementation Decision Log — Graceful Absence
- Given a feature WITHOUT implementation-log.md (pre-existing feature)
- When retro skill runs Step 1 context gathering
- Then retro notes "no implementation log available" and proceeds normally

### AC-9: Strategic Context Injection (Project-Linked)
- Given a feature with project_id in .meta.json and a project with prd.md and roadmap.md
- When implementing skill prepares per-task context
- Then a "## Project Context" block (~200-500 tokens) with project goals, feature dependencies, and priority signal is prepended
- **Verification approach:** Code review confirms the implementing skill contains conditional project context loading logic (reads project prd.md Goals + Problem Statement, roadmap.md, dependency feature .meta.json files) and the implementer prompt template includes a Project Context block placeholder. No live project required — verify the code path exists and AC-10 confirms the no-project path works.
- **Deferred behavioral verification:** First project-linked feature implementation must confirm project context block appears in implementer prompts with correct content (goals, dependencies, priority). Tracked as a follow-up validation, not gating this feature's completion.

### AC-10: Strategic Context Injection (No Project)
- Given a feature without project_id
- When implementing skill prepares context
- Then no project context block is added, no error occurs

### AC-11: Domain Reviewer Outcome — Approved
- Given spec-reviewer approved at iteration 2/5 with zero remaining issues
- When phase-reviewer prompt is constructed in specify.md
- Then prompt includes `## Domain Reviewer Outcome` with `Result: APPROVED at iteration 2/5` and `Unresolved issues: none`

### AC-12: Domain Reviewer Outcome — Failed at Cap
- Given design-reviewer failed at iteration cap 5/5 with 2 remaining blockers
- When phase-reviewer prompt is constructed in design.md
- Then prompt includes `## Domain Reviewer Outcome` with `Result: FAILED at iteration cap (5/5)` and the 2 unresolved blocker descriptions

### AC-13: External Verification — Security Reviewer
- Given code using bcrypt for password hashing
- When security-reviewer reviews implementation
- Then reviewer uses WebSearch or Context7 to verify bcrypt is current best practice, including verification result in output

### AC-14: External Verification — No External Claims
- Given code that is pure internal logic refactoring (no external library usage)
- When implementation-reviewer reviews
- Then reviewer notes "No external claims to verify" and proceeds without forced verification

### AC-15: Knowledge Bank — Entry Metadata
- Given anti-patterns.md entry "Working in Wrong Worktree" observed in Feature #002
- When metadata fields are added
- Then entry includes `- Last observed: Feature #002` and `- Observation count: 1`

### AC-16: Knowledge Bank — Retro Validation (Confirmed)
- Given feature #022 encounters "Over-Granular Tasks" anti-pattern
- When retro runs knowledge bank validation
- Then the entry's Last observed is updated to Feature #022 and Observation count incremented

### AC-17: Knowledge Bank — Retro Validation (Challenged)
- Given feature #022 contradicts a heuristic (e.g., plan completed in 1 iteration despite triggering complexity signals)
- When retro runs knowledge bank validation
- Then entry gets `- Challenged: Feature #022 — {reason}` appended

### AC-18: Knowledge Bank — Staleness
- Given an entry with "Last observed: Feature #005" and 12 actual features created since
- When retro runs staleness check
- Then entry is flagged with staleness marker and surfaced to user via AskUserQuestion for keep/update/retire
- **Retire action**: If user selects "retire", entry is deleted from the knowledge bank file and retro.md notes: "Retired: {entry name} — {user's reason}"
- **Keep action**: Staleness marker removed, Last observed updated to current feature, Observation count unchanged
- **Update action**: User provides updated text, entry is modified in-place, Last observed updated, Observation count reset to 1

### AC-19: Compact-Safe Hooks
- Given hooks.json with SessionStart matchers
- When context compaction fires
- Then no SessionStart hooks execute; hooks still fire on startup, resume, and clear events

### AC-20: Implementer Dispatch Failure
- Given implementer agent Task dispatch fails mid-task
- When the implementing skill detects the failure
- Then error is logged, task is marked as blocked, user is asked whether to retry or skip

### AC-21: Malformed Implementer Report
- Given implementer agent returns a report missing the "decisions" field
- When the implementing skill processes the report
- Then a partial implementation-log.md entry is written with available fields, and the next task proceeds

## Feasibility Assessment

### Assessment Approach
1. **First Principles** — All changes modify LLM prompt text and markdown files; no new infrastructure
2. **Codebase Evidence** — Existing patterns support every change
3. **External Evidence** — Not needed; all changes extend proven internal patterns

### Assessment
**Overall:** Confirmed
**Reasoning:** Every change extends an existing pattern:
- Per-task dispatch: Task tool already used for all reviewer dispatches — same mechanism for implementer
- Why field parsing: Fields exist in tasks.md in features 017, 019, 021 — but NOT feature 020 (no traceability fields) and feature 018 uses `§` separator format (not handled by regex). Both fall back to full loading gracefully. Evidence: `plugins/iflow-dev/skills/breaking-down-tasks/SKILL.md:131-141`
- Implementation log: Follows .review-history.md lifecycle (append/read/delete) — Evidence: `plugins/iflow-dev/commands/implement.md:267-287`
- Project context: workflow-transitions Step 5 already loads project context at phase level — Evidence: `plugins/iflow-dev/skills/workflow-transitions/SKILL.md:115-148`
- Domain reviewer outcome: Commands already parse reviewer JSON response to decide pass/fail — data is in working context
- External tools: spec-reviewer already has WebSearch + Context7 with verification instructions — Evidence: `plugins/iflow-dev/agents/spec-reviewer.md:5,148-151`
- Knowledge bank metadata: Simple markdown field additions to existing entries
- Hook matchers: Single string change per hook entry in hooks.json

**Key Assumptions:**
- Markdown heading extraction is reliable for design.md/plan.md section boundaries — Status: Extraction verified for features 017, 019, 020, 021 (substring + prefix fallback). Feature 018 (§ separator) verified to trigger fallback path correctly. Extraction accuracy: 4/5 features; fallback reliability: 5/5 features.
- Why/Source field regex handles known format variants — Status: Verified at features 017, 019, 021; feature 018 uses unhandled `§` format, feature 020 lacks traceability fields entirely — both confirm fallback path is exercised
- Retro agent can meaningfully validate ~15 knowledge bank entries against feature artifacts in one pass — Status: Likely (bounded input, LLM task)

**Open Risks:**
- Why field format may evolve in future features; parser must be lenient with fallback
- Phase-reviewer behavior on domain reviewer failure is informational-only by default; may need escalation rule if data shows rubber-stamping

## Dependencies

- No external dependencies
- Feature 021 (project-level-workflow) provides project infrastructure used by Change 3 (but Change 3 degrades gracefully without it)
- Feature 017 (evidence-grounded-phases) provides Why field in task template used by Change 1 (but Change 1 falls back for older features)

## Resolved Design Decisions

1. **Traceability field parsing robustness** (resolved — specified in Scope): Parser handles both Why and Source field names. Multi-reference values (e.g., `Spec C4.1, Plan 1A.1`) are split on comma first, then each trimmed reference is matched independently. Regex per reference: `Plan (?:Step )?(\w+\.\w+)` for plan refs (allowing alphanumeric like 1A.1), `Design (?:Component )?(\w+[-\w]*)` for design refs, `Spec (\w+\.\w+)` for spec refs. Falls back to full loading for unrecognized formats. Known non-matching features: feature 018 uses `Design § Component 2 § scqa-framing.md` format (§ separator — not handled by regex, falls back to full loading); feature 020 has no traceability fields at all. Both confirm the fallback path is real, not hypothetical.
2. **Heading extraction accuracy** (resolved — specified in Scope under "Heading Extraction Rules"): Substring match of reference identifier against heading text. Prefix fallback (1A.1 → try 1A) when exact match fails, handling features where sub-items are bold text under parent headings. Extract from matched heading through next same-level heading. Include nested subheadings. Don't follow cross-references. Accommodates all known plan.md heading variants across features 017-021.

3. **Domain Reviewer Outcome block presence** (resolved): The block is only added when a domain reviewer was invoked. All 4 current two-stage commands have domain reviewers. Future commands without domain review skip this block — no error, no empty block. This is a forward-looking edge case only.

## Open Questions

1. **Phase-reviewer behavior on domain reviewer failure**: Informational only for now. Add escalation rule later if data shows need.
2. **Knowledge bank staleness visibility**: Stale markers live in knowledge bank files. Retro surfaces via AskUserQuestion. Retro.md does not duplicate.
