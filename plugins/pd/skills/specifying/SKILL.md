---
name: specifying
description: Creates precise specifications. Use when the user says 'write the spec', 'document requirements', 'define acceptance criteria', or 'create spec.md'.
---

# Specification Phase

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Create precise, testable requirements.

## YOLO Mode Overrides

If `[YOLO_MODE]` is active:

- **"No PRD found" prompt:** Auto-select "Describe feature now" — use the YOLO description
  from the original user request as the feature description
- **"Review this spec" loop (both PRD and no-PRD paths):** Auto-select "Looks good" on first draft.
  The spec-reviewer and phase-reviewer stages (in specify.md) provide quality assurance.
- **No-PRD path requirement gathering:** Infer problem, success criteria, scope, and acceptance
  criteria from user description + any available context. Do not ask interactive questions.

## Prerequisites

Check for feature context:
- Look for feature folder in `{pd_artifacts_root}/features/`
- If not found:
  - "No active feature. Would you like to /pd:brainstorm first to explore ideas?"
  - Do NOT proceed without user confirmation
- If found:
  - Check for `{pd_artifacts_root}/features/{id}-{slug}/prd.md`
  - If `prd.md` exists: Read for context, use as input for spec
  - If `prd.md` not found:
    ```
    AskUserQuestion:
      questions: [{
        "question": "No PRD found. How to proceed?",
        "header": "PRD Missing",
        "options": [
          {"label": "Run /pd:brainstorm", "description": "Create PRD through brainstorming first"},
          {"label": "Describe feature now", "description": "Provide requirements directly"}
        ],
        "multiSelect": false
      }]
    ```
    - If "Run /pd:brainstorm": Invoke `/pd:brainstorm` → STOP
    - If "Describe feature now": Proceed to gather requirements directly

## Read Feature Context

1. Find active feature folder in `{pd_artifacts_root}/features/`
2. Read `.meta.json` for mode and context
3. Adjust behavior based on mode:
   - Standard: Full process with optional verification
   - Full: Full process with required verification

## Process

### If PRD exists:

1. **Draft spec.md from PRD content:**
   - Problem Statement: from PRD "Problem Statement" section
   - Success Criteria: from PRD "Goals" or "Success Metrics"
   - Scope: from PRD "Scope" section (In Scope / Out of Scope)
   - Acceptance Criteria: derive from PRD, deliberately mapping both Happy Paths and Error & Boundary Cases. Output Truth Tables if complex branching exists.

2. **Present draft to user:**
   ```
   AskUserQuestion:
     questions: [{
       "question": "Review this spec. What needs to change?",
       "header": "Review",
       "options": [
         {"label": "Looks good", "description": "Save and complete"},
         {"label": "Edit problem", "description": "Revise problem statement"},
         {"label": "Edit criteria", "description": "Revise success/acceptance criteria"},
         {"label": "Edit scope", "description": "Revise scope boundaries"}
       ],
       "multiSelect": false
     }]
   ```

3. Repeat until user selects "Looks good"

### If no PRD (user chose "Describe feature"):

1. **Define the Problem**
   From user input, distill:
   - One-sentence problem statement
   - Who it affects
   - Why it matters

2. **Define Success Criteria**
   Ask: "How will we know this is done?"
   Each criterion must be:
   - Specific (not vague)
   - Measurable (can verify)
   - Testable (can write test for)

3. **Define Scope**
   **In scope:** What we WILL build
   **Out of scope:** What we WON'T build (explicit)
   Apply YAGNI: Remove anything not essential.

4. **Define Acceptance Criteria**
   For each feature aspect systematically define:
   - **Happy Path:** Standard execution flow.
   - **Error & Boundary Cases:** Invalid input, lack of connectivity, concurrent states.
   - **Token Efficiency:** Keep scenarios concise. Group similar `Given` setups. If logic contains complex branching, output a markdown Truth Table instead of linear ACs.
   - Given [context]
   - When [action]
   - Then [result]

5. **Draft spec, present for review** (same AskUserQuestion as above)

## Output: spec.md

Write to `{pd_artifacts_root}/features/{id}-{slug}/spec.md`:

```markdown
# Specification: {Feature Name}

## Problem Statement
{One sentence}

## Success Criteria
- [ ] {Criterion 1 — measurable}
- [ ] {Criterion 2 — measurable}

## Scope

### In Scope
- {What we will build}

### Out of Scope
- {What we explicitly won't build}

## Acceptance Criteria

### Happy Paths
- Given {context}
- When {action}
- Then {result}

### Error & Boundary Cases
- Given {failure condition or edge case}
- When {action}
- Then {safe failure or resulting state}

### State Transitions (Optional)
{Include markdown truth table ONLY if feature logic has complex branching or overlapping states}

## Feasibility Assessment

Evaluate whether requirements are achievable. Focus on POSSIBILITY, not difficulty.

### Assessment Approach
1. **First Principles** - What fundamental constraints apply?
2. **Codebase Evidence** - Existing patterns that support this? Location: {file:line}
3. **External Evidence** (if needed) - Documentation confirming approach? Source: {URL}

### Feasibility Scale
| Level | Meaning | Evidence Required |
|-------|---------|-------------------|
| Confirmed | Verified working approach | Code reference or documentation |
| Likely | No blockers, standard patterns | First principles reasoning |
| Uncertain | Assumptions need validation | List assumptions to verify |
| Unlikely | Significant obstacles | Document obstacles |
| Impossible | Violates constraints | State the constraint |

### Assessment
**Overall:** {Confirmed | Likely | Uncertain | Unlikely | Impossible}
**Reasoning:** {WHY, based on evidence}
**Key Assumptions:**
- {Assumption} — Status: {Verified at {location} | Needs verification}
**Open Risks:** {Risks if assumptions wrong}

## Dependencies
- {External dependency, if any}

## Open Questions
- {Resolved during spec or deferred}
```

## Self-Check Before Completing

- [ ] Each criterion is testable?
- [ ] Critical failure modes and boundary edge-cases explicitly covered?
- [ ] No implementation details (what, not how)?
- [ ] No unnecessary features (YAGNI)?
- [ ] Concise (fits one screen)?
- [ ] Feasibility assessment uses evidence, not opinion?
- [ ] Assumptions explicitly listed?
- [ ] If any FR or AC names symbols used in test bodies (e.g. `inspect.getsource`, `re.ASCII`, `pytest.mark.parametrize`), **all** required stdlib imports are enumerated in the FR — not just the most prominent one. Closes #00288 traceability gap.

If any check fails, revise before saving.

## Completion

"Spec complete. Saved to spec.md."
"Run /pd:show-status to check, or /pd:design to continue."
