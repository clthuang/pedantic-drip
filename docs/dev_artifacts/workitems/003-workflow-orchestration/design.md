# Design: Workflow Orchestration & Iterative Review

## Architecture Overview

The system introduces centralized workflow state management via a skill, iterative quality review via a reviewer agent, and enhanced hooks for context awareness.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SessionStart Hook                           │
│  • Load active feature from .meta.json                              │
│  • Warn if cwd ≠ worktree                                           │
│  • Show current phase and next command                              │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Phase Command                                 │
│  (e.g., /specify, /design, /create-plan)                            │
│                                                                      │
│  1. Call workflow-state skill: validate transition                   │
│  2. Check for partial phase (started but not completed)              │
│  3. Execute phase with reviewer loop                                 │
│  4. Update .meta.json state                                          │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
         ┌──────────────────┐           ┌──────────────────┐
         │  Phase Skill     │           │  Chain Reviewer  │
         │  (executor)      │◄─────────►│  Agent           │
         │                  │  iterate  │  (read-only)     │
         │  Produces        │           │  Critiques       │
         │  artifact        │           │  artifact        │
         └──────────────────┘           └──────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │  .meta.json      │
         │  .review-history │
         └──────────────────┘
```

## Components

### 1. Workflow State Skill

**Purpose:** Central state management and transition validation

**Location:** `skills/workflow-state/SKILL.md`

**Responsibilities:**
- Define phase sequence
- Validate phase transitions (hard/soft prerequisites)
- Provide state read/update patterns
- Track worktree location

**Inputs:**
- Current `.meta.json` state
- Requested phase transition

**Outputs:**
- Validation result (allowed/blocked/warning)
- Updated state instructions

### 2. Chain Reviewer Agent

**Purpose:** Validate artifact quality and chain sufficiency

**Location:** `agents/chain-reviewer.md`

**Responsibilities:**
- Receive previous phase output + current output
- Validate current output is self-sufficient for next phase
- Return structured feedback (approved/issues)
- NEVER suggest scope expansion

**Inputs:**
- Previous phase artifact (if exists)
- Current phase artifact
- Next phase expectations (from skill)

**Outputs:**
- Structured feedback:
  ```json
  {
    "approved": boolean,
    "issues": [
      {"severity": "blocker|warning|note", "description": "..."}
    ]
  }
  ```

### 3. Final Reviewer Agent

**Purpose:** Validate implementation matches original spec

**Location:** `agents/final-reviewer.md`

**Responsibilities:**
- Compare implementation against spec.md
- Flag unimplemented requirements
- Flag extra work not in spec

**Inputs:**
- spec.md
- Implementation files (code changes)

**Outputs:**
- Structured feedback (same format as chain reviewer)

### 4. Enhanced SessionStart Hook

**Purpose:** Context injection and worktree warning

**Location:** `hooks/session-start.sh` (modify existing)

**Responsibilities:**
- Find active feature
- Check cwd vs worktree
- Show current phase and suggested next command
- Only show active features (status = active)

**Inputs:**
- Feature folder structure
- Current working directory

**Outputs:**
- Context message with warnings if applicable

### 5. Phase Command Template

**Purpose:** Standard structure for all phase commands

**Pattern applied to:** All phase commands (specify, design, create-plan, create-tasks, implement)

**Reviewer Loop Pattern (implemented in commands, not skills):**

```
Phase Command (e.g., /design)
│
├─ 1. Validate transition (workflow-state skill)
│      - If blocked: Show error, stop
│      - If warning: Show warning, ask to proceed
│
├─ 2. Check for partial phase
│      - If started but not completed: Ask user (continue/fresh/review)
│
├─ 3. Get mode from .meta.json → determine max_iterations
│      - Hotfix=1, Quick=2, Standard=3, Full=5
│
├─ 4. Mark phase started in .meta.json
│
└─ 5. REVIEWER LOOP:
       │
       iteration = 1
       │
       WHILE iteration <= max_iterations:
       │
       ├─ a. Execute phase skill → produce/revise artifact
       │
       ├─ b. Spawn chain-reviewer agent with:
       │      - Previous phase artifact (if exists)
       │      - Current artifact just produced
       │      - Next phase expectations (see table below)
       │
       ├─ c. Reviewer returns: {approved, issues, summary}
       │
       ├─ d. IF approved:
       │      - Mark phase completed with iterations count
       │      - Present to user: "Phase complete (N iterations)"
       │      - BREAK
       │
       ├─ e. IF NOT approved AND iteration < max:
       │      - Append iteration details to .review-history.md
       │      - iteration++
       │      - CONTINUE (executor revises based on feedback)
       │
       └─ f. IF NOT approved AND iteration == max:
              - Mark phase completed with iterations count + reviewerNotes
              - Present to user: "Phase complete. Reviewer concerns: [issues]"
              - BREAK
```

**Key principle:** Skills produce artifacts; commands manage the loop. Skills remain unchanged.

### 6. Review History Writer

**Purpose:** Record iteration details during development

**Location:** Inline in phase commands (uses workflow-state skill patterns)

**Responsibilities:**
- Append to `.review-history.md` after each iteration
- Store summary in `.meta.json` on phase completion
- Delete `.review-history.md` on /finish

## Interfaces

### Interface 1: Workflow State Validation

```
Function: validateTransition(currentPhase, targetPhase, artifacts)

Input:
  currentPhase: string | null
  targetPhase: string
  artifacts: { spec: boolean, design: boolean, plan: boolean, tasks: boolean }

Output:
  {
    allowed: boolean,
    type: "proceed" | "warning" | "blocked",
    message: string | null
  }

Rules:
  - Hard block: /implement without spec.md
  - Hard block: /create-tasks without plan.md
  - Warning: skipping phases (e.g., brainstorm → design)
  - Proceed: correct order
```

### Interface 2: Chain Reviewer Feedback

```
Function: reviewArtifact(previousArtifact, currentArtifact, nextPhaseExpectations)

Input:
  previousArtifact: string | null (content of previous phase file)
  currentArtifact: string (content of current phase file)
  nextPhaseExpectations: string (what next phase needs)

Output:
  {
    approved: boolean,
    issues: [
      {
        severity: "blocker" | "warning" | "note",
        description: string,
        location: string | null (line or section reference)
      }
    ],
    summary: string (brief overall assessment)
  }

Errors:
  - Empty artifact: Return not approved with blocker
  - Missing previous when required: Return not approved with blocker
```

### Next Phase Expectations (for Reviewer)

Each phase reviewer validates that the current artifact contains everything the next phase needs:

| Phase | Produces | Next Phase Needs (Reviewer Validates) |
|-------|----------|---------------------------------------|
| brainstorm | brainstorm.md | **Spec needs:** Clear problem statement, explored options, user intent captured |
| specify | spec.md | **Design needs:** All requirements listed, acceptance criteria defined, scope boundaries clear |
| design | design.md | **Plan needs:** Components defined, interfaces specified, dependencies identified, risks noted |
| create-plan | plan.md | **Tasks needs:** Ordered steps with dependencies, all design items covered, clear sequencing |
| create-tasks | tasks.md | **Implement needs:** Small actionable tasks (<15 min each), clear acceptance criteria per task |
| implement | code | **Verify needs:** All tasks addressed, tests exist/pass, no obvious issues |
| verify | verification | **Finish needs:** Quality confirmed, implementation matches spec, ready to merge |

The reviewer uses this table to assess chain sufficiency: "Can the next phase complete its work using ONLY this artifact?"

### Interface 3: State Update

```
Function: updatePhaseState(featurePath, phaseName, updates)

Input:
  featurePath: string (path to feature folder)
  phaseName: string
  updates: {
    started?: ISO timestamp,
    completed?: ISO timestamp,
    verified?: boolean,
    iterations?: number,
    reviewerNotes?: string[]
  }

Output:
  success: boolean

Pattern:
  1. Read .meta.json
  2. Merge updates into phases[phaseName]
  3. Update currentPhase if completed
  4. Write .meta.json atomically
```

### Interface 4: Review History Entry

```
Format: .review-history.md

## Phase: {phaseName}

### Iteration {n} - {timestamp}

**Reviewer Feedback:**
{feedback summary}

**Issues:**
- [{severity}] {description}

**Changes Made:**
{what executor changed}

---
```

## Technical Decisions

### TD1: Reviewer as Subagent vs Self-Review

- **Choice:** Subagent review (spawn separate agent)
- **Alternatives:** Self-review (same LLM critiques own work), structured prompt
- **Rationale:** Genuine fresh perspective catches blind spots; worth the 3-5 second overhead per iteration

### TD2: State Storage Location

- **Choice:** `.meta.json` in feature folder + `.review-history.md` for details
- **Alternatives:** Central state file, database, session memory only
- **Rationale:** Feature-local state is portable, survives session restarts, easy to inspect

### TD3: Iteration Limit Enforcement

- **Choice:** Mode-based limits (Hotfix=1, Quick=2, Standard=3, Full=5)
- **Alternatives:** Fixed limit, user-configurable, no limit
- **Rationale:** Matches mode philosophy; prevents runaway iterations while allowing rigor when needed

### TD4: Worktree Warning Mechanism

- **Choice:** Warn once per session (SessionStart) + per command (advisory)
- **Alternatives:** Block if wrong directory, auto-switch, no warning
- **Rationale:** Balance between safety and flexibility; user may intentionally work elsewhere
- **State tracking:** SessionStart hook injects warning into session context. Commands check if context already contains worktree warning and don't repeat. No file or env var needed—LLM remembers within session.

### TD5: Review History Cleanup

- **Choice:** Delete `.review-history.md` on /finish
- **Alternatives:** Keep forever, archive to completed folder, compress
- **Rationale:** History served its purpose; git has the record; avoid clutter in completed features

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Reviewer agent scope creeps | Medium - defeats purpose | Hardened persona with explicit constraints in agent prompt |
| State corruption during update | High - lost work | Read-modify-write pattern, atomic file writes |
| Infinite iteration loop | Medium - wasted tokens | Hard ceiling at mode limit, present to user with concerns |
| LLM doesn't follow workflow-state skill | Medium - inconsistent behavior | Clear, explicit instructions; hooks provide backup validation |
| Worktree path changes | Low - confusion | Store relative path, resolve at runtime |

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `skills/workflow-state/SKILL.md` | Central state management skill |
| Create | `agents/chain-reviewer.md` | Phase artifact reviewer |
| Create | `agents/final-reviewer.md` | Implementation vs spec reviewer |
| Modify | `hooks/session-start.sh` | Add worktree warning, show active features only |
| Modify | `commands/specify.md` | Add workflow-state validation, reviewer loop |
| Modify | `commands/design.md` | Add workflow-state validation, reviewer loop |
| Modify | `commands/create-plan.md` | Add workflow-state validation, reviewer loop |
| Modify | `commands/create-tasks.md` | Add workflow-state validation, reviewer loop |
| Modify | `commands/implement.md` | Add workflow-state validation, reviewer loop |
| Modify | `commands/finish.md` | Add status update, history cleanup |

## Dependencies

- Existing plugin infrastructure (commands, skills, hooks, agents)
- Python3 for JSON parsing in hooks (already required)
- Task tool for spawning reviewer subagent
- Git for worktree management (already required)
