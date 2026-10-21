# Design: Workflow Hardening — Backward Travel, Pre-Implementation Gate, Taskify

## Prior Art Research

### Research Conducted
| Question | Source | Finding |
|----------|--------|---------|
| Where does backward travel logic live? | workflow-transitions/SKILL.md:37-53 | validateAndSetup Step 1 already has a backward branch (re-run prompt). This is the insertion point. |
| Does backward_transition_reason exist in DB? | entity_registry/database.py:2677 | Yes — TEXT column already in workflow_phases table. No new column needed. |
| How do phases auto-chain? | All phase commands' completion sections | AskUserQuestion → "Continue to /pd:{next} (Recommended)". YOLO bypasses and invokes directly. |
| What maps need updating for phase merge? | transition_gate/constants.py, frontmatter_inject.py | PHASE_SEQUENCE, ARTIFACT_PHASE_MAP (both files), HARD_PREREQUISITES, GUARD_METADATA (14 guards), PHASE_GUARD_MAP |
| How does LangGraph handle backtracking? | LangGraph docs | Fork pattern: create new checkpoint from past state, don't rollback. as_node controls which node re-runs. |
| How to detect review ping-pong? | Yang et al. EMNLP 2025 | Track findings count per round — should strictly decrease. Plateau or increase = oscillation. Better than artifact hashing. |
| Pre-implementation readiness gates? | McKinsey QuantumBlack | Two-layer: (1) deterministic structural checks, (2) critic agent for judgment calls. Both must pass. |
| Context injection for rework? | QuantumBlack, DVC | The artifact IS the context (DVC pattern). Upstream change propagates via artifact checksums. No prompt injection needed — reviewers re-read updated files. |

### Existing Solutions Evaluated
| Solution | Source | Why Used/Not Used |
|----------|--------|-------------------|
| .backward-context.json file | Spec AC-A2 proposal | **Rejected** — no precedent in codebase for per-feature JSON sidecar. Simpler approach: store backward context in entity metadata (existing pattern) and let the upstream phase read it via MCP tool call. |
| LangGraph checkpoint fork | LangGraph docs | **Adopted conceptually** — backward travel creates a "new execution branch" from the upstream phase, not a rollback. Git history accumulates (new commits, no amends). |
| SHA-256 artifact hash for ping-pong | Spec AC-A5 | **Replaced** — findings-count-decrease rule is more reliable. Track issue count per reviewer iteration; if count doesn't decrease between backward travels on the same pair, that's ping-pong. |
| Merged phase as single reviewer | — | **Rejected** — keep plan-reviewer and task-reviewer as separate dispatches within the combined phase. Sequential, not merged into one agent. |

### Novel Work Justified
1. **Forward re-run orchestrator** — new logic in workflow-transitions skill that advances one phase at a time after a backward fix, using `backward_return_target` in entity metadata
2. **Relevance-verifier agent** — new agent reading full artifact chain for coherence
3. **Standalone taskify command** — thin wrapper around existing breaking-down-tasks skill + task-reviewer cycle

## Architecture Overview

### Proposed Workflow

```
brainstorm → specify → design → create-plan → RELEVANCE → implement → 360 QA → finish
                                (plan+tasks)     GATE
     ▲           ▲         ▲        ▲                                    │
     │           │         │        │                                    │
     └───────────┴─────────┴────────┘                                    │
         backward travel                                                 │
         (any reviewer can send to any earlier phase)                    │
         (re-runs forward one phase at a time after fix)                │
                                                         ┌───────┴───────┐
                                                       PASS             FAIL
                                                         │               │
                                                      finish          backward or halt
```

### Component Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Phase Command (specify, design, create-plan, implement) │
│                                                          │
│  1. validateAndSetup() ← EXTENDED for backward travel    │
│     - reads backward_context from entity metadata        │
│     - injects into phase prompt as additional context     │
│     - checks backward_return_target for forward re-run   │
│                                                          │
│  2. Phase skill execution (existing, unchanged)          │
│                                                          │
│  3. Reviewer dispatch (existing pattern)                 │
│     - reviewer response NOW may include backward_to      │
│                                                          │
│  4. handleReviewerResponse() ← NEW                       │
│     - if backward_to: trigger backward travel            │
│     - else: proceed as today (iterate or approve)        │
│                                                          │
│  5. commitAndComplete() ← EXTENDED                       │
│     - clears backward_context from metadata after use    │
│     - checks backward_return_target for forward re-run   │
│     - if return target not reached: invoke next phase     │
│     - if return target reached: clear target, resume      │
│       normal flow                                        │
└──────────────────────────────────────────────────────────┘
```

## Components

### C1: Backward Travel Orchestration
- **Purpose:** Enable reviewers to send work back to upstream phases with context
- **Location:** Extends `workflow-transitions/SKILL.md` (validateAndSetup + new handleReviewerResponse + commitAndComplete)
- **Inputs:** Reviewer response with `backward_to` field, current feature metadata
- **Outputs:** Phase transition to upstream phase with backward context injected

### C2: Pre-Implementation Relevance Gate
- **Purpose:** Verify full artifact chain coherence before implementation
- **Location:** New dispatch point in `create-plan` command's completion section (after commitAndComplete, before auto-chain to implement)
- **Agent:** New `relevance-verifier.md` agent
- **Inputs:** spec.md, design.md, plan.md, tasks.md
- **Outputs:** Structured pass/fail per check with gap identification

### C3: Merged Create-Plan
- **Purpose:** Produce plan.md + tasks.md in a single phase
- **Location:** Modified `create-plan.md` command
- **Skills used:** planning skill → breaking-down-tasks skill (sequential)
- **Review:** plan-reviewer → task-reviewer → phase-reviewer (combined max 5 iterations)

### C4: Standalone Taskify
- **Purpose:** Break down any plan into atomic tasks with quality verification
- **Location:** New `taskify.md` command (no new skill — directly invokes existing breaking-down-tasks skill)
- **Inputs:** Plan file path, optional --spec and --design paths
- **Outputs:** tasks.md alongside input file
- **Review:** Built-in task-reviewer cycle (max 3 iterations, automatic)

### C5: Post-Implementation 360 QA
- **Purpose:** Layered verification at task, spec, and standards levels
- **Location:** Modified `implement.md` command (restructured review section)
- **Agents:** implementation-reviewer (task-level), relevance-verifier (spec-level), code-quality-reviewer + security-reviewer (standards-level)

## Interfaces

### I1: Extended Reviewer Response Schema

All phase reviewers (spec-reviewer, design-reviewer, plan-reviewer, task-reviewer, phase-reviewer) gain optional backward travel fields:

```json
{
  "approved": false,
  "issues": [...],
  "summary": "...",
  "backward_to": "specify",
  "backward_reason": "AC-2 in spec is not testable — task T3's DoD inherits this vagueness",
  "backward_context": {
    "source_phase": "create-plan",
    "target_phase": "specify",
    "findings": [
      {"artifact": "spec.md", "section": "AC-2", "issue": "Not testable", "suggestion": "Define measurable threshold"}
    ],
    "downstream_impact": "Task T3 DoD cannot be verified without clearer spec AC-2"
  }
}
```

**Rules:**
- `backward_to` is optional. If absent, normal approve/iterate flow.
- `backward_to` must name a phase earlier than the current phase in PHASE_SEQUENCE.
- `backward_context` is required when `backward_to` is present.

### I2: handleReviewerResponse() — NEW shared procedure

Added to `workflow-transitions/SKILL.md` after the reviewer dispatch parse step:

```
Input: reviewer_response (parsed JSON), feature_type_id, current_phase
Output: action = "approve" | "iterate" | "backward"

Logic:
  if reviewer_response.backward_to exists:
    1. Validate backward_to is a valid phase earlier than current_phase
    2. Store backward_context in entity metadata:
       - Call update_entity(type_id, metadata={backward_context: reviewer_response.backward_context})
    3. Store backward_return_target = current_phase in entity metadata
    4. Update backward_transition_reason in workflow_phases (existing column)
    5. Log to backward_history array in entity metadata:
       {source_phase, target_phase, reason, timestamp, issue_count: len(issues)}
    6. Expected metadata structure after backward travel:
       ```json
       {
         "phase_timing": { ... },
         "mode": "standard",
         "backward_context": { "source_phase": "create-plan", "target_phase": "specify", "findings": [...], "downstream_impact": "..." },
         "backward_return_target": "create-plan",
         "backward_history": [
           { "source_phase": "create-plan", "target_phase": "specify", "reason": "...", "timestamp": "...", "issue_count": 3 }
         ]
       }
       ```
       All three fields are top-level keys in the entity metadata JSON blob.
    7. Call transition_phase(feature_type_id, backward_to) to move to upstream phase
    7. In YOLO: auto-invoke the target phase command with [YOLO_MODE]
       In interactive: prompt user "Reviewer recommends going back to {phase}. Proceed?"
    return "backward"

  if reviewer_response.approved AND zero blocker/warning:
    return "approve"

  else:
    return "iterate"
```

### I3: Extended validateAndSetup() — backward context injection

Added to `workflow-transitions/SKILL.md` Step 1, after the existing backward-transition prompt:

```
After Step 1 (validate transition):
  Step 1b: Check for backward context
    1. Read .meta.json (already read in Step 1 of validateAndSetup). backward_context is projected into .meta.json by _project_meta_json() — no additional MCP call needed. **Implementation note:** _project_meta_json() must be extended to project `backward_context` and `backward_return_target` fields from entity metadata into .meta.json. `backward_history` should NOT be projected (audit-only, would bloat .meta.json).
    2. If .meta.json contains backward_context:
       a. Read backward_context.findings[]
       b. Format as markdown block:
          ## Backward Travel Context
          This phase is being re-run because a downstream reviewer identified
          issues rooted here.

          **Source:** {source_phase} reviewer
          **Issue:** {backward_reason}
          **Findings:**
          {formatted findings}
          **Downstream Impact:** {downstream_impact}

          Address these findings in this phase's artifact revision.
       c. This block is prepended to the phase's prompt context
       d. After phase completes successfully, clear backward_context from metadata
    3. If metadata.backward_context does NOT exist:
       Normal flow (no injection)
```

### I4: Extended commitAndComplete() — forward re-run orchestration

Added to `workflow-transitions/SKILL.md` after existing Step 3 (phase summary):

```
After Step 3 (Phase Summary):
  Step 3b: Forward re-run check
    1. Read entity metadata for backward_return_target
    2. If backward_return_target exists AND backward_return_target != current_phase:
       a. Determine next_phase = phase after current_phase in PHASE_SEQUENCE
       b. Clear backward_context from metadata (already used by this phase)
       c. Output: "Continue to /pd:{next_phase} [YOLO_MODE]" — the existing YOLO auto-chain mechanism handles invocation (same pattern as current phase completion). This is NOT a new control flow — it reuses the existing "output next command, YOLO auto-chains" pattern.
       d. Log: "Forward re-run: {current_phase} → {next_phase} (returning to {backward_return_target})"
    3. If backward_return_target == current_phase:
       a. Clear backward_return_target from metadata
       b. Log: "Reached backward return target. Resuming normal flow."
       c. Proceed to normal completion (standard auto-chain to next phase)
    4. If backward_return_target does NOT exist:
       Normal flow (standard auto-chain)
```

### I5: Relevance Gate Dispatch (C2)

Inserted in `create-plan.md` completion section, after commitAndComplete but before auto-chain to implement:

```
After commitAndComplete("create-plan", ["plan.md", "tasks.md"], ...):

  # Relevance gate (pre-implementation coherence check)
  Task tool call:
    description: "Pre-implementation relevance verification"
    subagent_type: pd:relevance-verifier
    model: opus
    prompt: |
      Verify the full artifact chain is coherent before implementation begins.

      ## Required Artifacts
      Read these files:
      - Spec: {feature_path}/spec.md
      - Design: {feature_path}/design.md
      - Plan: {feature_path}/plan.md
      - Tasks: {feature_path}/tasks.md

      ## Verification Checks
      1. COVERAGE: Every spec AC has ≥1 task with traceable DoD
      2. COMPLETENESS: Every design component has ≥1 task
      3. TESTABILITY: Every task DoD is binary and verifiable
      4. COHERENCE: Task approaches reflect design decisions

      Return JSON:
      {
        "pass": true/false,
        "checks": [
          {"name": "coverage", "pass": true/false, "details": "...", "gaps": [...]},
          {"name": "completeness", "pass": true/false, "details": "...", "gaps": [...]},
          {"name": "testability", "pass": true/false, "details": "...", "gaps": [...]},
          {"name": "coherence", "pass": true/false, "details": "...", "gaps": [...]}
        ],
        "backward_to": "specify",          // optional: if gap traces to upstream
        "backward_context": { ... },        // optional: structured findings
        "summary": "..."
      }

  If gate.pass == true:
    Proceed to /pd:implement (or next phase per normal chain)

  If gate.pass == false AND gate.backward_to exists:
    Invoke handleReviewerResponse() with the gate's response (triggers backward travel)

  If gate.pass == false AND no backward_to:
    In YOLO: emit "relevance verification failed" safety keyword → halt
    In interactive: present results, user decides
```

### I6: Merged Create-Plan Command (C3)

Modified `create-plan.md`:

```
Step 4: Execute with Combined Review Loop

  a. Produce plan artifact:
     Invoke planning skill → writes plan.md

  b. Produce tasks artifact:
     Invoke breaking-down-tasks skill → reads plan.md, writes tasks.md

  c. Combined review loop (max 5 iterations):
     Iteration N:
       1. Dispatch plan-reviewer (validates plan quality)
          - If plan-reviewer.backward_to: invoke handleReviewerResponse() → exit
          - If plan-reviewer fails: fix plan.md, re-run breaking-down-tasks, loop
          - If plan-reviewer passes: proceed to task-reviewer

       2. Dispatch task-reviewer (validates task breakdown)
          - If task-reviewer.backward_to: invoke handleReviewerResponse() → exit
          - If task-reviewer fails: fix tasks.md, loop
          - If task-reviewer passes: proceed to phase-reviewer

       3. Dispatch phase-reviewer (validates handoff readiness)
          - If phase-reviewer.backward_to: invoke handleReviewerResponse() → exit
          - If phase-reviewer fails: fix plan.md and/or tasks.md, loop
          - If phase-reviewer passes: APPROVED

  d. commitAndComplete("create-plan", ["plan.md", "tasks.md"], iterations, ...)

  e. Relevance gate (I5) — runs after commit, before auto-chain to implement
```

### I7: Standalone Taskify Command (C4)

New `taskify.md` command:

```
/pd:taskify <plan-path> [--spec=<path>] [--design=<path>] [--output=<path>]

Step 1: Resolve input
  - plan_path = first argument (required)
  - spec_path = --spec argument (optional)
  - design_path = --design argument (optional)
  - output_path = --output argument (optional, default: {plan_dir}/tasks.md)

Step 2: Validate
  - Read plan file, verify it exists and has content
  - If --spec: verify spec file exists
  - If --design: verify design file exists
  - NO .meta.json check, NO MCP calls, NO entity registry

Step 3: Produce tasks
  - Invoke breaking-down-tasks skill with plan content
  - If --spec/--design provided, include as additional context
  - Write tasks.md to output_path

Step 4: Quality review cycle (automatic, up to 3 iterations)
  - Dispatch task-reviewer agent with:
    - tasks.md (required)
    - plan file (required)
    - spec/design files (if provided)
  - If reviewer finds blockers/warnings: auto-correct, re-run
  - If approved or 3 iterations: output final tasks.md

Step 5: Output
  "Tasks created: {n} tasks across {m} parallel groups."
  "Output: {output_path}"
```

### I8: Post-Implementation 360 QA (C5)

Restructured review section in `implement.md`:

```
Current: 3-reviewer parallel dispatch (implementation, quality, security)

Proposed: 3-level sequential verification

Level 1: Task-Level Verification
  - Agent: implementation-reviewer (existing)
  - Input: tasks.md DoDs + git diff of implementation
  - Check: each task's DoD criteria met
  - If fail: fix implementation, re-run (existing iterate pattern)
  - If fail with backward_to: invoke handleReviewerResponse()

Level 2: Spec-Level Verification
  - Agent: relevance-verifier (same as pre-impl gate)
  - Input: spec.md ACs + implementation
  - Check: each spec AC satisfied
  - Deterministic where possible (run tests if configured)
  - If fail: may recommend backward travel to upstream phase
  - If fail without backward_to: fix implementation, re-run

Level 3: Standards-Level Verification
  - Agents: code-quality-reviewer + security-reviewer (existing, unchanged)
  - Input: implementation diff
  - Check: engineering standards
  - If fail: fix in-place (no backward travel for style issues)

All 3 levels must pass. Max 5 total iterations across all levels.
Existing YOLO circuit breaker (5 iterations) preserved.
```

### I9: Ping-Pong Detection

**Mechanism:** Findings-count-decrease rule (replaces SHA-256 hashing from spec).

```
In handleReviewerResponse(), when backward_to is present:

  1. Read backward_history from entity metadata
  2. Find previous entries with same (source_phase, target_phase) pair
  3. If ≥2 previous entries exist for this pair:
     a. Compare issue_count: current vs previous
     b. Compare current issue_count against the most recent previous entry's issue_count for the same (source_phase, target_phase) pair. If current >= previous (plateau or increase):
        - This is a ping-pong signal
        - In YOLO: force approve with warnings (log "ping-pong detected, forcing forward")
        - In interactive: prompt user "Same issues recurring. Force approve or continue fixing?"
  4. If issue_count decreased: legitimate progress, allow backward travel
```

**Rationale:** Findings count decrease is a better convergence signal than artifact hashing. If the reviewer keeps finding the same number (or more) issues after a fix attempt, the fix isn't working. This is the Yang et al. EMNLP 2025 convergence formula applied practically.

## Technical Decisions

### TD-1: Backward context in entity metadata, not .backward-context.json
- **Choice:** Store backward_context in entity metadata (existing JSON blob in entities.metadata) rather than a separate file
- **Alternatives:** .backward-context.json file per feature — no precedent in codebase, adds file lifecycle management
- **Rationale:** Entity metadata is the established pattern for per-feature state. All phase commands already have access via MCP. _project_meta_json() already projects metadata to .meta.json. No new file patterns needed.
- **Engineering Principle:** Don't invent new persistence patterns when existing ones work
- **Evidence:** Codebase: entity metadata stores phase_timing, brainstorm_source, mode, skipped_phases — backward_context fits the same pattern

### TD-2: Findings-count-decrease for ping-pong detection
- **Choice:** Track issue count per backward travel event; if count doesn't decrease on same pair, that's ping-pong
- **Alternatives:** SHA-256 artifact hashing (spec proposal), semantic similarity threshold (research finding)
- **Rationale:** Issue count is already available in reviewer response. Hash comparison requires computing and storing hashes. Findings count decrease is mathematically grounded (Yang et al. convergence formula) and simpler to implement.
- **Engineering Principle:** KISS — use data already in hand
- **Evidence:** Web research: Yang et al. EMNLP 2025 convergence model

### TD-3: Sequential reviewer dispatch in merged create-plan (not parallel)
- **Choice:** plan-reviewer → task-reviewer → phase-reviewer sequentially within each iteration
- **Alternatives:** Parallel dispatch of all 3, merge results
- **Rationale:** Plan-reviewer may find issues that require plan.md changes, which invalidate tasks.md. Running task-reviewer on stale tasks.md wastes tokens. Sequential ensures each reviewer sees the latest artifact.
- **Engineering Principle:** Don't review stale artifacts
- **Evidence:** Current two-phase pattern is already sequential (plan approved before tasks started)

### TD-4: Relevance gate as separate dispatch point, not a new phase
- **Choice:** Gate runs inside create-plan command's completion section, not as a distinct workflow phase
- **Alternatives:** Add "relevance-gate" as a new phase in PHASE_SEQUENCE
- **Rationale:** Adding a phase means new ENTITY_MACHINES entries, transition gates, and HARD_PREREQUISITES — significant infrastructure for what is functionally a single agent dispatch. Running it as a post-commit check in create-plan keeps the phase count minimal.
- **Engineering Principle:** YAGNI — don't create infrastructure for a single dispatch
- **Evidence:** The gate produces no artifact of its own; it validates existing artifacts

### TD-5: Standalone taskify as a command wrapper, not a new skill
- **Choice:** New `taskify.md` command that wraps existing breaking-down-tasks skill + task-reviewer dispatch
- **Alternatives:** New `taskify/SKILL.md` skill
- **Rationale:** The skill already exists (breaking-down-tasks). The new command is orchestration (read file, invoke skill, dispatch reviewer, write output) — that's command-level work, not skill-level.
- **Engineering Principle:** Skills define behavior; commands orchestrate
- **Evidence:** Pattern: every pd command wraps a skill with validation + review + state management

### TD-6: ARTIFACT_PHASE_MAP restructured to list values
- **Choice:** Change `ARTIFACT_PHASE_MAP: dict[str, str]` to `dict[str, list[str]]` in constants.py — create-plan maps to ["plan.md", "tasks.md"]. Reverse lookup at gate.py:160 changes from `{v: k for k, v in ARTIFACT_PHASE_MAP.items()}` to `{a: k for k, artifacts in ARTIFACT_PHASE_MAP.items() for a in artifacts}` (flatten lists to individual artifact→phase mappings). frontmatter_inject.py's ARTIFACT_PHASE_MAP stays dict[str, str] (different schema) but updates 'tasks' → 'create-plan'.
- **Alternatives:** Keep 1:1 map with duplicate entries for create-plan
- **Rationale:** The 1:1 map breaks when one phase produces two artifacts. The reverse lookup needs updating regardless. A list value is the natural representation.
- **Engineering Principle:** Data structure should match the domain (1:many relationship)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Forward re-run orchestration is novel | May have edge cases in phase chaining | Prototype in workflow-transitions skill first; test with a 2-phase backward jump |
| Backward travel bloats entity metadata | JSON blob grows with backward_history entries | Keep only essential fields (source, target, reason, timestamp, issue_count). Trim context details. |
| Merged create-plan is more complex than two separate phases | More failure modes in one command | Keep plan-reviewer and task-reviewer as separate dispatches (familiar pattern). Only the orchestration is merged. |
| Relevance gate adds latency before implementation | Extra agent dispatch (~30-60s) | Only runs once per feature (not per iteration). Cost is small vs potential implementation rework. |
| Standalone taskify quality without spec/design context | Task reviewer can't check traceability | Optional --spec/--design args for richer validation. Without them, reviewer checks plan-to-task coverage only. |
| Entity metadata blob grows with backward_history | Large JSON affects read/write performance | Cap backward_history at last 10 entries (FIFO eviction). Cap backward_context.findings text at 2000 chars. |
| .review-history.md ambiguity on backward re-run | Same phase appears twice in review history | Re-run phases append with "## {Phase} (backward travel re-run)" header to distinguish from original run. |

## Dependencies

- Existing workflow-transitions skill (validateAndSetup + commitAndComplete)
- Existing planning skill + breaking-down-tasks skill
- Existing reviewer agents (plan-reviewer, task-reviewer, phase-reviewer, implementation-reviewer, code-quality-reviewer, security-reviewer)
- `backward_transition_reason` column in workflow_phases table (already exists)
- Entity metadata JSON blob (existing, stores phase_timing)
- PHASE_SEQUENCE, ARTIFACT_PHASE_MAP, HARD_PREREQUISITES, GUARD_METADATA in constants.py
- frontmatter_inject.py ARTIFACT_PHASE_MAP
