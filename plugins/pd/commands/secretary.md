---
description: Intelligent task routing - discover agents and delegate work
argument-hint: [help|orchestrate <desc>|<request>]
---

# /pd:secretary Command

Route requests to the best-matching specialist agent.

## Codex Reviewer Routing

Before any reviewer dispatch in this command (secretary-reviewer), follow the codex-routing reference (primary: `~/.claude/plugins/cache/*/pd*/*/references/codex-routing.md`; fallback for dev workspace: `plugins/pd/references/codex-routing.md`). If codex is installed (per the path-integrity-checked detection helper in the reference doc), route via Codex `task --prompt-file` (foreground). Reuse the reviewer's prompt body verbatim via temp-file delivery (single-quoted heredoc — never argv interpolation). Translate the response per the field-mapping table in the reference doc. Falls back to pd reviewer Task on detection failure or malformed codex output.

**Security exclusion:** This command does NOT dispatch `pd:security-reviewer`, so the codex-routing exclusion does not need to be enforced here. The exclusion is enforced wherever `pd:security-reviewer` IS dispatched (implement, finish-feature). Note: Dynamic agent dispatch at Step 7 DELEGATE is a runtime-templated routing, not a static reviewer dispatch; codex routing is not applied at that delegation site.

## Static Reference Tables

All static routing tables, rules, and reference data are collected here for prompt cache efficiency. Procedural steps below reference these tables by name.

### Routing Boundary Directive

> During steps 1-6, you are ROUTING, not executing. Do not use Edit, Write, or Bash.
> Only use Read, Glob, Grep for discovery, AskUserQuestion for clarification,
> and Task for secretary-reviewer. Step 7 (DELEGATE) lifts this restriction.

### YOLO Mode Overrides

Apply when `[YOLO_MODE]` is active:
- Step 2 (CLARIFY): Skip — infer intent from request text
- Step 5 (REVIEW): Skip reviewer gate
- Step 6 (RECOMMEND): Auto-select highest-confidence match in Standard mode
- Step 7 (DELEGATE): If workflow pattern detected, redirect to orchestrate subcommand handler directly. Otherwise proceed immediately.

### Specialist Fast-Path Table

Before running semantic matching, check against known specialist patterns:

| Pattern (case-insensitive) | Agent | Confidence |
|---|---|---|
| "review" + ("security" / "vulnerability" / "owasp") | pd:security-reviewer | 95% |
| "review" + ("code quality" / "clean code" / "best practice") | pd:code-quality-reviewer | 95% |
| "review" + ("implementation" / "against spec" / "against requirements") | pd:implementation-reviewer | 95% |
| "review" + ("design" / "architecture") | pd:design-reviewer | 95% |
| "review" + ("spec" / "requirements" / "acceptance criteria") | pd:spec-reviewer | 95% |
| "review" + ("plan" / "implementation plan") | pd:plan-reviewer | 95% |
| "review" + ("data" / "analysis" / "statistical" / "methodology") | pd:ds-analysis-reviewer | 95% |
| "review" + ("notebook" / "pandas" / "sklearn" / "DS code") | pd:ds-code-reviewer | 95% |
| "simplify" / "reduce complexity" / "clean up code" | Skill: `simplify` (native CC) | 95% |
| "explore" + ("codebase" / "code" / "patterns" / "how does") | pd:codebase-explorer | 95% |
| "deepen tests" / "add edge case tests" / "test deepening" | pd:test-deepener | 95% |

### Skill Fast-Path Table

Routes to skills via `Skill()` instead of agents via `Task()`:

| Pattern (case-insensitive) | Skill | Confidence |
|---|---|---|
| "debug" / "root cause" / "why is this broken" | pd:systematic-debugging | 95% |
| "TDD" / "test-driven" / "red-green-refactor" | pd:implementing-with-tdd | 95% |
| "retrospective" / "retro" / "what went well" | pd:retrospecting | 95% |
| "update docs" / "sync documentation" | pd:updating-docs | 95% |

### Fast-Path Rules

1. Match is keyword overlap, not semantic — must hit the exact pattern
2. If fast-path matches → skip Discovery, skip semantic matching, skip reviewer gate
3. Go directly to Step 6 (Recommender) with the matched agent/skill at 95% confidence
4. User still confirms via AskUserQuestion before delegation (unless YOLO)
5. Tag whether match is agent or skill — affects delegation method in Step 7

### Workflow Pattern Recognition Table

| Pattern Keywords | Workflow |
|-----------------|----------|
| "new feature", "add capability", "create feature" | pd:brainstorm |
| "brainstorm", "explore", "ideate", "what if", "think about" | pd:brainstorm |
| "add command", "add hook", "add agent", "add skill", "create component", "modify plugin", "new command", "new hook", "new agent", "new skill", "extend plugin" | pd:brainstorm |
| "design", "architecture" | pd:design |
| "specify", "spec", "requirements" | pd:specify |

**Development Task Heuristic:**
If the request describes modifying, adding to, or extending the plugin system (commands, hooks, agents, skills, workflows), treat it as a feature request → route via Workflow Guardian.

### Investigative Question Detection Table

| Pattern Keywords | Route To |
|-----------------|----------|
| "why", "what caused", "how did this happen", "what went wrong", "how come", "what's causing", "what broke" | investigation-agent |
| "investigate", "debug", "trace", "analyze failure", "diagnose" | investigation-agent |
| Any of the above + "fix", "resolve", "prevent", "stop this from" | rca-investigator |

**Priority rule:** If both investigation and action keywords are present ("why did X break and how do I fix it?"), "fix"/"resolve"/"prevent" takes precedence → route to `rca-investigator`. Default to `investigation-agent` when unclear.

### Maturity Signals Table

| Signal | Well-specified (+1) | Under-specified (-1) |
|--------|--------------------|--------------------|
| Problem statement | Clear, concrete ("add JWT auth to API endpoints") | Vague ("improve auth") |
| Success criteria | Stated or strongly implied ("users can log in via SSO") | Absent |
| Scope | Bounded ("the /api/auth routes") | Unbounded ("the whole system") |
| Approach | Indicated ("using passport.js") | Unknown |
| Unknowns | None stated, problem well-understood | "not sure how", "what's the best way" |

### Maturity Levels Table

| Score | Level | Route |
|-------|-------|-------|
| 3-5 | **Well-specified** | Skip brainstorm → `create-feature` (starts at specify phase) |
| 1-2 | **Partially specified** | Brainstorm with light triage (archetype matching, but flag as "refinement needed" not "exploration") |
| 0 or below | **Exploratory** | Full brainstorm with advisory team (current behavior) |

### Mode Detection Keywords Table

Used by Step 0 (DETECT MODE) for keyword classification:

| Mode | Keywords (first match wins, left-to-right scan) |
|------|------------------------------------------------|
| **CREATE** | create, add, build, implement, start, make, new, need, want, fix, set up |
| **QUERY** | what, how, where, which, list, show, find, status, progress |
| **CONTINUE** | continue, resume, next, finish |

**Feature branch override:** On `feature/*` or `feat/*` branches, default to CONTINUE unless explicit CREATE intent ("add a task", "create a task") or QUERY intent (question words first) detected.

### Scope Signal Keywords Table

Used by Step 4 (weight recommendation) and Weight Escalation Detection:

| Weight | Signal Keywords |
|--------|----------------|
| **light** | quick fix, small, simple, typo, one liner, trivial, minor, tiny, cosmetic |
| **full** | rewrite, refactor, breaking change, complex, cross-team, architecture, migration, security, multi-service |
| **standard** | (default — no signals or mixed) |

**Expansion signals** (upgrade triggers during CONTINUE mode):

| Target | Expansion Keywords |
|--------|-------------------|
| **→ standard** | multiple components, needs design review, needs spec, growing scope, more involved than expected |
| **→ full** | cross-team impact, breaking change, architecture change, rewrite, security review, multi-service |

### OKR Anti-Pattern Checks

On KR creation, check for activity-word anti-patterns and KR count limits:

1. **Activity-word check:** If the KR text contains activity verbs (launch, build, implement, create, deploy, migrate, develop, ship, release), warn: "This looks like an output, not an outcome. Consider reframing as a measurable result."
2. **KR count check:** If the parent objective already has >5 active KRs, warn: "Consider reducing KR count. Recommended max: 5."

These checks use `detect_activity_kr(text)` and `check_kr_count(db, objective_uuid)` from `secretary_intelligence.py`.

### Entity Type Hierarchy Table

Used by Step 3 (TRIAGE) for parent candidate search:

| Entity Type | Plausible Parent Types |
|-------------|----------------------|
| task | feature, project, key_result |
| feature | project, key_result, objective, initiative |
| project | key_result, objective, initiative |
| key_result | objective, initiative |
| objective | initiative |
| initiative | (none — top-level) |

### Confidence Thresholds

- >70%: Strong match, recommend as primary
- 50-70%: Show as alternative option (but if best match is in this range, also show "no strong match" warning)
- <50%: Do not show

**Note:** If the BEST match is <70%, the "No Suitable Match" path in Step 7 applies.

### Complexity Analysis Table

After matching, assess task complexity for mode recommendation:

<!-- Trivial-math exception: 5-signal additive integer counting (SC-5). Addition only, no division/rounding. -->

| Signal | Points |
|--------|--------|
| Multi-file changes likely | +1 |
| Breaking changes / rewrite / migrate | +2 |
| Cross-domain (API + UI + tests) | +1 |
| Unclear scope / many unknowns | +1 |
| Simple / bounded / single file | -1 |

Score ≤ 1 → recommend Standard mode
Score ≥ 2 → recommend Full mode

### No Suitable Match Routing Table

When no existing agent scores above 50%, run scoping research then route:

| Finding | Route |
|---------|-------|
| Simple: ≤2 files affected, single domain, bounded task | Call `EnterPlanMode` directly — "This task is straightforward. Switching to plan mode." |
| Complex: 3+ files, multiple domains, or unfamiliar technology | Invoke `Skill({ skill: "pd:create-specialist-team", args: "{clarified_intent}" })` |

### Review Skip/Invoke Criteria

**Skip reviewer when:**
- Best match confidence >85% AND match is a direct agent (not a workflow pattern)
- `[YOLO_MODE]` is active

**Invoke reviewer when:**
- Best match confidence <=85%
- Multiple matches within 15 points of each other (ambiguous ranking)
- Match is a workflow route (brainstorm/specify/design) — workflow misroutes are costlier

### Error Handling Templates

**Agent Parse Failure:**
- Log warning internally, skip the problematic file, continue with remaining agents

**Delegation Failure:**
```
AskUserQuestion:
  questions: [{
    question: "Delegation to {agent} failed: {error}. What would you like to do?",
    header: "Error",
    options: [
      { label: "Retry", description: "Try again with same agent" },
      { label: "Choose different agent", description: "Pick an alternative" },
      { label: "Cancel", description: "Abort request" }
    ],
    multiSelect: false
  }]
```

### Rules

1. **Always confirm before delegating** — Never auto-delegate without user approval (unless YOLO)
2. **Show reasoning** — Always explain why an agent was recommended
3. **Respect cancellation** — If user cancels, stop immediately
4. **Minimal context** — Pass only task-relevant information to subagents
5. **Handle errors gracefully** — Offer recovery options, don't crash
6. **Skip self** — Never recommend secretary as a match for tasks
7. **Prefer specialists** — Match to most specific agent, not generic workers
8. When no specialist matches (best <50%), run scoping research and auto-resolve (plan mode for simple, specialist team for complex)
9. **Never execute work** — Discover, interpret, match, delegate. Never investigate the user's problem, design solutions, or produce artifacts.

---

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)
- `{pd_reviewer_model}` — model to use for the secretary reviewer gate (default: `opus`, overridable for local proxy users)

## Subcommand Routing

Parse the first word of the argument:
- `help` → Help subcommand
- `orchestrate` or `continue` → Orchestrate subcommand
- anything else → Request handler (performs routing inline)
- no argument → Brief usage

## Subcommand: help

If argument is `help`:

Display usage instructions:

```
Secretary - Intelligent Task Routing

Usage:
  /pd:secretary help              Show this help
  /pd:secretary orchestrate <desc> Run full workflow autonomously (YOLO only)
  /pd:secretary <request>         Route request to best agent

Orchestration (YOLO mode only):
  /pd:secretary orchestrate build a login system
  /pd:secretary continue          Resume from last completed phase

Examples:
  /pd:secretary review auth for security issues
  /pd:secretary help me improve test coverage
  /pd:secretary find and fix performance problems

The secretary will:
1. Discover available agents and skills across all plugins
2. Interpret your request (ask structured clarifying questions if needed)
3. Assess problem maturity and match to the best specialist agent or skill
4. Validate routing via reviewer (for uncertain matches)
5. Confirm with you before delegating
6. Execute the delegation and report results
```

## Subcommand: orchestrate

If argument starts with `orchestrate` or `continue`:

### Prerequisites

1. Read `.claude/pd.local.md`
2. Check if `yolo_mode: true`
3. If `yolo_mode` is NOT `true`:
   - If `activation_mode: yolo` is found in config but `yolo_mode` is not true, show: "You previously used `/pd:secretary mode yolo`. Run `/pd:yolo on` to enable unified YOLO mode."
   - Otherwise show:
   ```
   Orchestration requires YOLO mode. Run /pd:yolo on first.
   ```
   Stop here.

### Detect Workflow State

1. Glob `{pd_artifacts_root}/features/*/.meta.json`
2. Read each file, look for `"status": "active"`
3. If active feature found:
   - Extract `id`, `slug`, and `lastCompletedPhase` from .meta.json as discrete values
   - Report: "Active feature: {id}-{slug}, last phase: {lastCompletedPhase}"
4. If no active feature AND description provided after "orchestrate":
   - This is a new feature request, start from brainstorm
5. If no active feature AND no description (bare `orchestrate` or `continue`):
   ```
   No active feature found and no description provided.

   Usage:
     /pd:secretary orchestrate <description>  Start new feature
     /pd:secretary continue                   Resume active feature
   ```
   Stop here.

### Determine Next Command

Construct `feature_type_id` as `"feature:{id}-{slug}"` from the `id` and `slug` fields
already extracted from `.meta.json`.
Call `get_phase(feature_type_id)`. Parse the JSON response object.
- If `current_phase` is non-null: the feature is mid-phase. Route to `pd:{current_phase}`
  (or `pd:finish-feature` when `current_phase` is `finish`).
- If `current_phase` is null: the feature is between phases. Use `last_completed_phase`
  to determine the next phase from the canonical sequence:
  brainstorm → specify → design → create-plan → implement → finish.
  Route to the command for that next phase.
If MCP unavailable, fall back to `.meta.json` `lastCompletedPhase` (camelCase)
and apply the same canonical-sequence logic.

### Execute in Main Session

Invoke the next command via Skill (NOT Task) so it runs in the main session and the user sees all output:

```
Skill({
  skill: "pd:{next-command}",
  args: "[YOLO_MODE] {description or feature context}"
})
```

The existing command chaining and YOLO overrides handle everything from here. Each phase:
- Auto-selects at AskUserQuestion prompts (YOLO overrides in workflow-transitions)
- Runs full executor-reviewer cycles (all reviewer agents still execute)
- Auto-invokes the next command at completion

### Hard Stops

The chain breaks and reports to user when:
- **Circuit breaker**: 5 review iterations without approval in implementation
- **Git merge conflict**: Cannot auto-resolve in /finish-feature
- **Hard prerequisite failure**: Missing design.md (blocks create-plan), spec.md or tasks.md (blocks implement)
- **Pre-merge validation failure**: 3 fix attempts exhausted

These are handled by the individual commands. The orchestrator does NOT need to catch them — the Skill invocation naturally surfaces them.

## Subcommand: <request>

If argument is anything other than `help`, `orchestrate`, or `continue`:

Apply the Routing Boundary Directive above.

**Check YOLO mode** — Check if `[YOLO_MODE]` is active in session context. Fallback: read `.claude/pd.local.md` and check `yolo_mode: true`. Apply YOLO Mode Overrides above when active.

---

### Step 0: DETECT MODE

Before routing, determine the user's operating mode: **CREATE**, **CONTINUE**, or **QUERY**. This controls which downstream steps activate.

#### Resolution Order

1. **Context check** — Detect current git branch via `git branch --show-current`.
   - If on a feature branch (matches `feature/*` or `feat/*`):
     - Check for explicit CREATE intent: patterns like "add a task", "create a task to track", "new entity" → **CREATE**
     - Check for explicit QUERY intent: question words (how, what, where, which, list, show, find, status, progress) appearing first → **QUERY**
     - Otherwise → **CONTINUE** (default when on feature branch)
   - If NOT on a feature branch → proceed to keyword classification

2. **Keyword classification** — Scan request text left-to-right for first keyword match:
   - Action verbs: create, add, build, implement, start, make, new, need, want, fix, set up → **CREATE**
   - Question/status words: what, how, where, which, list, show, find, status, progress → **QUERY**
   - Continuation words: continue, resume, next, finish → **CONTINUE**

3. **Ambiguous** — If no keywords match after context check, default to **CREATE** (safe default — creation flow includes clarification steps).

#### Mode-Specific Behaviour

| Mode | Effect on Pipeline |
|------|-------------------|
| **CREATE** | Run full pipeline. After MATCH, enter Universal Work Creation Flow (identify → link → register → activate). |
| **CONTINUE** | If on feature branch: extract feature context from `.meta.json`, call `get_phase()` to determine current phase, propose: "Feature {id} is in {phase} phase. Continue?" If not on feature branch: call `search_entities(query="status:active")` to list available work. |
| **QUERY** | Search entity registry via `search_entities(query="{extracted terms}")`. Present topology-aware results: entity status, lifecycle phase, children progress, blockers. If no results: "No matching entities found." If multiple results: present ranked list with type and status. |

**CONTINUE shortcut:** When mode is CONTINUE and on a feature branch, skip Steps 1-6 and go directly to Step 7 (DELEGATE) with the detected phase command. Present confirmation first (unless YOLO).

**QUERY shortcut:** When mode is QUERY, skip Steps 1-6. Query the entity registry directly:
1. Extract search terms from the request
2. Call `search_entities(query="{terms}")` — if entity_type is inferrable from request, pass it as filter
3. For each result, optionally call `get_entity(ref="{type_id}")` for full detail (phase, children, blockers)
4. Present results to user. If pending notifications exist (call `get_notifications()`), append them.
5. Stop (no delegation needed).

---

### Step 1: DISCOVER

Build an index of available agents and skills:

```
Agent discovery:
1. Primary: Glob ~/.claude/plugins/cache/*/*/agents/*.md
   - For each file: extract plugin name from path, read frontmatter (including `model` field), build agent record

2. Fallback (if step 1 found 0 agents): Glob plugins/*/agents/*.md
   - Process same as step 1

3. Merge and deduplicate agents by plugin:name

Skill discovery:
4. Primary: Glob ~/.claude/plugins/cache/*/pd*/*/skills/*/SKILL.md
   - For each file: extract skill name from path, read frontmatter (name, description), build skill record

5. Fallback (if step 4 found 0 skills): Glob plugins/*/skills/*/SKILL.md
   - Process same as step 4

6. Merge and deduplicate skills by plugin:name

7. If still 0 agents AND 0 skills: proceed to Step 4 — do NOT error out.
   Keyword matching (Specialist Fast-Path + Workflow Pattern Recognition)
   provides routing even without discovery of either agents or skills.
```

**YAML Frontmatter Parsing:**
- Find content between first two "---" lines
- For each line: split on first ":" to get key/value
- Handle arrays (lines starting with "- " or bracket notation)
- Skip agents/skills with malformed frontmatter

---

### Step 2: CLARIFY

Analyze the request across 4 dimensions:

| Dimension | What to extract | Example signals |
|-----------|----------------|-----------------|
| **Intent** | What does the user want to achieve? | Action verb: review, create, fix, explore, investigate, design, implement, brainstorm |
| **Scope** | What files/areas/components? | File paths, module names, "the auth system", "all tests" |
| **Constraints** | Approach preferences, patterns to follow? | "using TDD", "keep backward compat", "follow existing patterns" |
| **Maturity** | How well-specified is the problem? | Has success criteria? Bounded scope? Known unknowns? |

**Decision logic:**
- If ALL 4 dimensions are extractable from the request text → proceed (no questions needed)
- If Intent is unclear → ask about intent (informed by discovered agents/skills — present categories the system can actually route to)
- If Intent is clear but Scope is missing → ask about scope
- If multiple dimensions unclear → ask up to 2 questions (combine dimensions where natural)
- Cap at max 3 clarification rounds total

**If Clear:**
- Proceed directly to Step 3

**Example Clarification (Intent unclear):**
```
AskUserQuestion:
  questions: [{
    question: "What would you like to do with the auth module?",
    header: "Intent",
    options: [
      { label: "Review it", description: "Security, code quality, or design review" },
      { label: "Fix something", description: "Debug or investigate a specific issue" },
      { label: "Build on it", description: "Add new functionality or extend it" },
      { label: "Understand it", description: "Explore how it works" }
    ],
    multiSelect: false
  }]
```

**Clarification Timeout/Fallback:**
- Track clarification attempts (max 3)
- If user provides empty/unclear response, re-prompt with simpler options
- After 3 failed attempts or timeout, proceed with best-effort interpretation:
  1. Extract most concrete terms from original request
  2. Match against agent/skill descriptions using keyword overlap
  3. If any candidate scores >50%, recommend it with disclaimer: "Based on limited context, I suggest..."
  4. If no candidate >50%, report "Unable to interpret request. Please try rephrasing or use a specific agent."

---

### Step 3: TRIAGE

When the clarified intent suggests building something new (feature request, new capability, add/create), assess problem maturity. If the intent is NOT a feature/build request (e.g., review, investigate, explore), skip triage entirely and proceed to Step 4.

Score the request against the Maturity Signals Table above, then use the Maturity Levels Table to determine the route.

#### Entity Registry Queries (CREATE mode only)

When Step 0 detected **CREATE** mode, query the entity registry before maturity assessment:

1. **Search for parent candidates:**
   - Infer the entity type from scope signals: company-wide → initiative, multi-feature → project, single deliverable → feature, bounded fix → task (or light feature)
   - Determine plausible parent types: task parents = [feature, project, key_result]; feature parents = [project, key_result, objective, initiative]; project parents = [key_result, objective, initiative]
   - For each plausible parent type, call `search_entities(query="{request keywords}", entity_type="{parent_type}")` to find candidates
   - Present top candidates (max 3) to user: "Found potential parent: {type_id} — {name} ({status})"

2. **Check for duplicates:**
   - Call `search_entities(query="{entity name/description}")` without type filter
   - If results overlap with what user is creating → warn: "Potential duplicate: {type_id} — {name}. Continue creating or link to existing?"
   - Present via AskUserQuestion with options: "Create new", "Link to existing {type_id}", "Cancel"

3. **Propose linkage:**
   - If parent candidates found and no duplicates → propose: "Link as child of {parent_type_id}?"
   - If both parent and duplicates found → present both findings for user decision
   - If neither → proceed as standalone entity (no parent linkage)

Store `parent_candidate`, `entity_type`, and `duplicate_check` results for the Universal Work Creation Flow.

#### When well-specified (skip brainstorm):
- Set `workflow_match = "pd:create-feature"`
- Pass the problem statement as the feature description
- **Continue to Step 4** (MATCH confirms the route, Workflow Guardian validates no active feature conflict)
- Step 5 (REVIEW) still validates this routing
- Step 6 (RECOMMEND) still confirms with user — present as: "Problem is well-specified. Skip brainstorming and create feature directly?"
- Step 7 (DELEGATE) invokes: `Skill({ skill: "pd:create-feature", args: "{description}" })`

#### When partially specified or exploratory:
Run archetype matching:

1. Read the archetypes reference file:
   - Glob `~/.claude/plugins/cache/*/pd*/*/skills/brainstorming/references/archetypes.md` — use first match
   - Fallback: Glob `plugins/*/skills/brainstorming/references/archetypes.md`
   - If not found: skip archetype matching, proceed to Step 4 with no archetype context
2. Extract keywords from the clarified user intent
3. Match against each archetype's signal words — count hits per archetype
4. Select archetype with highest overlap (ties: prefer domain-specific archetype)
5. If zero matches: default to "exploring-an-idea"
6. Load the archetype's default advisory team from the reference
7. Optionally override team if model judgment warrants it (explain reasoning)
8. Store `archetype` and `advisory_team` for Step 7
9. Set `workflow_match = "pd:brainstorm"`

Triage results are only used when Step 7 routes to brainstorming. Otherwise discarded.

---

### Step 4: MATCH

Match clarified intent to discovered agents and skills. Check patterns in this priority order:

#### Specialist Fast-Path

Check the request against the Specialist Fast-Path Table and Skill Fast-Path Table above. Apply Fast-Path Rules above.

**If no fast-path match** → proceed to remaining matching below.

#### Workflow Pattern Recognition

Check the request against the Workflow Pattern Recognition Table above.

If workflow_match or investigative match detected (see Investigative Question Detection Table above), set in output and skip semantic agent matching.

#### Workflow Guardian

When a workflow pattern is detected (feature request, "build X", "implement X", "plan X", "code X"), determine the correct phase:

1. Glob `{pd_artifacts_root}/features/*/.meta.json`
2. Read each file, look for `"status": "active"`
3. If NO active feature:
   - If triage set `workflow_match = "pd:create-feature"` → preserve that route. Explain: "Problem is well-specified. Creating feature directly (skipping brainstorm)."
   - If triage set `workflow_match = "pd:brainstorm"` → preserve that route. Explain: "No active feature. Starting from brainstorm to ensure research and planning phases are complete."
   - If no triage ran (safety default) → route to `pd:brainstorm`
4. If active feature found:
   - Extract `id`, `slug`, and `lastCompletedPhase` from the `.meta.json` already read above
   - Construct `feature_type_id` as `"feature:{id}-{slug}"` from the `id` and `slug` fields
     already extracted from `.meta.json`.
     Call `get_phase(feature_type_id)`. Parse the JSON response object.
     - If `current_phase` is non-null: the feature is mid-phase. Route to `pd:{current_phase}`
       (or `pd:finish-feature` when `current_phase` is `finish`).
     - If `current_phase` is null: the feature is between phases. Use `last_completed_phase`
       to determine the next phase from the canonical sequence:
       brainstorm → specify → design → create-plan → implement → finish.
       Route to the command for that next phase.
     If MCP unavailable, fall back to `.meta.json` `lastCompletedPhase` (camelCase)
     and apply the same canonical-sequence logic.
   - If the next phase matches what the user asked for → route with: "All prerequisite phases complete. Proceeding to {phase}."
   - If the next phase is earlier than what the user asked for → route to the next phase with: "You asked to {user request}, but {next phase} hasn't been completed yet. Routing to {next phase} to ensure planning phase is complete."

Note: Workflow Guardian applies ONLY to workflow pattern matches. Specialist agent routing (reviews, investigations, debugging) bypasses this entirely.

#### Semantic Matching (Agents and Skills)

If no fast-path, workflow, or investigative match:

```
1. If candidate count (agents + skills) <= 20:
   - Consider all candidates for semantic matching

2. If candidate count > 20:
   - Extract keywords from user intent (nouns, verbs, domain terms)
   - Pre-filter to top 10 candidates by keyword overlap with description
   - Consider these 10 for semantic matching

3. For each candidate (agent OR skill):
   - Evaluate semantic fit between intent and candidate description
   - For agents: consider tools vs task requirements
   - For skills: consider if the skill's triggering patterns match
   - Assign confidence score (0-100)
   - Document reasoning
   - Tag whether match is agent or skill (affects delegation method)

4. Return matches sorted by confidence
```

Apply Confidence Thresholds above to filter results.

#### Weight Recommendation (CREATE mode)

When Step 0 detected **CREATE** mode, recommend a workflow weight based on scope signals extracted from the request and triage context:

**Scope signal extraction:** Collect descriptors from the user's request that indicate scope/complexity:
- "quick fix", "small", "simple", "typo", "trivial", "minor", "cosmetic" → light signals
- "rewrite", "refactor", "breaking change", "complex", "cross-team", "architecture", "migration", "security", "multi-service" → full signals
- No clear signals → standard (default)

**Weight resolution:**
- Any full signal present → recommend **full** weight
- Only light signals → recommend **light** weight
- No signals or mixed → recommend **standard** weight

Store `recommended_weight` for the Universal Work Creation Flow. Present in Step 6 (RECOMMEND): "Recommended weight: {weight} based on scope signals: {list of matched signals}."

#### Complexity Analysis

Apply the Complexity Analysis Table above to assess task complexity for mode recommendation.

---

### Step 5: REVIEW

Before presenting the recommendation, evaluate whether independent validation is needed using the Review Skip/Invoke Criteria above.

When invoking the reviewer:
```
Task({
  subagent_type: "pd:secretary-reviewer",
  model: "{pd_reviewer_model}",
  description: "Validate routing recommendation",
  prompt: "Discovered agents: {agent list with descriptions}\n
           User intent: {clarified intent}\n
           Routing: {recommended agent} ({confidence}% match)\n
           Mode recommendation: {Standard or Full}\n
           Validate agent fit, confidence calibration, missed specialists, and mode appropriateness."
})
```

**Handle reviewer response:**
- If reviewer approves → present original recommendation
- If reviewer objects (has blockers) → adjust recommendation per reviewer suggestions, note "adjusted after review"
- If reviewer fails or times out → proceed with original recommendation (note the failure internally)

---

### Step 6: RECOMMEND

Present recommendation to user for confirmation:

```
AskUserQuestion:
  questions: [{
    question: "Route to {agent} ({confidence}% match)?",
    header: "Routing",
    options: [
      { label: "Accept - Standard", description: "{reason} (recommended for this scope)" },
      { label: "Accept - Full", description: "{reason} (extra verification for complex tasks)" },
      // Include alternatives >50% (max 2):
      { label: "Use {alt-agent}", description: "Alternative: {alt-confidence}% match" },
      { label: "Cancel", description: "Abort request" }
    ],
    multiSelect: false
  }]
```

Pre-select the recommended mode based on complexity analysis (Standard or Full first in list).

**Notification append:** Before presenting the recommendation, check for pending notifications by calling `get_notifications()`. If notifications exist, append them below the routing recommendation: "Pending notifications: {count} — {summary of first 3}." This ensures the user sees relevant state changes when making routing decisions.

**User Response Handling:**
- "Accept - Standard" → Proceed with Standard mode delegation
- "Accept - Full" → Proceed with Full mode delegation
- "Use {alt-agent}" → Proceed to delegation with selected alternative
- "Cancel" → Report "Request cancelled" and stop
- Custom text (via Other) → Parse as "plugin:agent" format, validate, delegate if valid

---

### Step 7: DELEGATE

Execute the delegation:

**If workflow_match:**
```
Skill({
  skill: "{workflow_match}",
  args: "{user_context}"
})
```

**When workflow_match is "pd:brainstorm" AND triage completed:**
```
Skill({
  skill: "pd:brainstorm",
  args: "{user_context} [ARCHETYPE: {archetype}] [ADVISORY_TEAM: {comma-separated advisor names}]"
})
```

**If skill match (from semantic matching or fast-path):**
```
Skill({
  skill: "{plugin}:{skill-name}",
  args: "{clarified_intent}"
})
```

**If agent match:**
```
Task({
  subagent_type: "{plugin}:{agent}",
  model: "{agent_record.model}",
  description: "Brief task summary",
  prompt: `
    Task: {clarified_intent}

    Context:
    {context_summary}

    Requirements:
    {specific_requirements}

    Return your findings in structured format.
  `
})
```

**After Delegation:**
- Present subagent results to user
- Offer follow-up options if relevant

#### No Suitable Match (best match <50%)

When no existing agent scores above 50%, run scoping research:

1. Extract key terms from the clarified intent
2. Glob for files matching those terms — count results and identify directories
3. Grep for pattern spread — identify how many domains are involved

Route based on the No Suitable Match Routing Table above.

**Fallback:** If specialist team creation fails, offer retry/rephrase/cancel via AskUserQuestion.

---

### CREATE Mode: Universal Work Creation Flow

When Step 0 detected **CREATE** mode and the user has confirmed the routing recommendation, execute this 4-step creation flow. This replaces the default delegation for work creation requests.

#### Step C1: IDENTIFY

Determine the entity attributes:

1. **Entity type** — Infer from scope (already determined in Triage):
   - Company-wide impact → `initiative`
   - Multi-feature effort → `project`
   - Single deliverable → `feature`
   - Bounded fix / sub-item → `task` (or light `feature`)

2. **Weight** — Use `recommended_weight` from MATCH step (light / standard / full).

3. **Name** — Extract or ask:
   - If request contains a clear name/title → use it
   - Otherwise → ask: "What should this be called? (short, descriptive name)"

4. **Tags** — Extract domain/circle tags from context:
   - Infer from keywords: "auth" → tag `auth`, "frontend" → tag `frontend`
   - Present inferred tags for confirmation

#### Step C2: LINK

Propose parent linkage using Triage results:

1. If `parent_candidate` was found in Triage:
   - Call `get_entity(ref="{parent_type_id}")` to confirm parent still exists and is active
   - Present: "Link as child of {parent_name} ({parent_type_id})?"
   - Before confirming parent linkage, fetch parent context using `get_parent_context(db, parent_type_id)` from `secretary_intelligence.py`. If context is returned, display: "Parent: {type_id} ({phase}, {progress}%)" with traffic light indicator ({traffic_light}). This is the Catchball pattern (AC-35a) — showing parent intent on creation so the user understands what they're linking into.
   - User confirms or selects different parent or standalone

2. If no parent found:
   - Proceed as standalone (no parent linkage)
   - Note: "No parent entity found. Creating as standalone {entity_type}."

3. **Backlog triage** — If the request references backlog:
   - Call `search_entities(query="{description}", entity_type="feature")` filtered to status=open
   - If backlog item found → propose: "Promote backlog item {type_id} to {entity_type}? This will update its status from open to active."
   - On confirmation: use `update_entity(type_id="{backlog_type_id}", status="active")` then continue with registration

#### Step C3: REGISTER

Create the entity in the registry:

```
Call register_entity with:
  entity_type: "{entity_type}"
  entity_id: "{generated_id}"  (or let the system generate via central ID generator)
  name: "{name}"
  status: "planned"
  parent_type_id: "{parent_type_id}"  (if linked in C2, otherwise omit)
  metadata: {
    "weight": "{recommended_weight}",
    "tags": ["{tag1}", "{tag2}"],
    "source": "secretary"
  }
```

If tags were identified, call `add_entity_tag(entity_ref="{type_id}", tag="{tag}")` for each.

Report to user: "Registered: {entity_type}:{entity_id} — {name} (weight: {weight}, parent: {parent_type_id or 'none'})"

#### Step C4: ACTIVATE

Transition the entity from planned to active:

1. Call `update_entity(type_id="{type_id}", status="active")`
2. The workflow engine assigns the template phase sequence based on entity_type and weight
3. Report: "{entity_type}:{entity_id} activated. First phase: {first_phase}."
4. Offer to continue: "Start working on {first_phase} now?"
   - If yes → delegate to the matching phase command (same as CONTINUE mode routing)
   - If no → stop. Entity is registered and active for later resumption.

**Confirmation gate:** Before C3 (REGISTER), present a summary for user confirmation (unless YOLO):

```
AskUserQuestion:
  questions: [{
    question: "Create this work item?",
    header: "New {entity_type}",
    options: [
      { label: "Create", description: "{name} | weight: {weight} | parent: {parent_or_none}" },
      { label: "Edit", description: "Change type, weight, parent, or name" },
      { label: "Cancel", description: "Abort creation" }
    ],
    multiSelect: false
  }]
```

---

### Weight Escalation Detection

Weight escalation applies during **CONTINUE** mode when the user describes scope expansion. Check for escalation signals whenever processing a CONTINUE request.

#### Detection

Extract scope signals from the user's current request and conversation context. Check for expansion indicators:

**Standard-level signals** (upgrade light → standard):
- "multiple components", "needs design review", "needs spec", "growing scope", "more involved than expected"

**Full-level signals** (upgrade light/standard → full):
- "cross-team impact", "breaking change", "architecture change", "rewrite", "security review", "multi-service"

#### Evaluation

1. Determine current weight: call `get_entity(ref="{current_feature_type_id}")` → read `metadata.weight` (or `workflow_phases.mode`)
2. If current weight is already `full` → no escalation possible, skip
3. Match signals against the expansion patterns above
4. If escalation detected → recommend upgrade

#### Recommendation

Present to user:

```
AskUserQuestion:
  questions: [{
    question: "This work is growing beyond {current_weight} weight. Upgrade to {recommended_weight}?",
    header: "Weight Escalation",
    options: [
      { label: "Upgrade to {recommended_weight}", description: "Template expands. Phases before current position marked as skipped." },
      { label: "Keep {current_weight}", description: "Continue with current template" }
    ],
    multiSelect: false
  }]
```

#### Execution (on confirmation)

1. Update the entity's mode: call `update_entity(type_id="{type_id}", metadata={"weight": "{new_weight}"})`
2. Record skipped phases: the phases present in the new template but absent from the original template AND before the current phase position are recorded as `skipped_phases` in metadata:
   ```
   update_entity(type_id="{type_id}", metadata={
     "weight": "{new_weight}",
     "skipped_phases": ["brainstorm", "design"]  // phases in new template before current position that were not in original
   })
   ```
3. Report: "Weight upgraded from {old} to {new}. Phases {skipped_list} marked as skipped. Continuing from {current_phase}."
4. The entity continues from its current phase — no new entity created, same uuid.

---

### Error Handling

Apply the Error Handling Templates above.

## No Arguments

If no argument provided:

Display brief usage:
```
Usage: /pd:secretary [help|mode|orchestrate|<request>]

Quick examples:
  /pd:secretary help
  /pd:secretary review auth module
  /pd:secretary mode yolo
  /pd:secretary orchestrate build a login system

Run /pd:secretary help for full documentation.
```
