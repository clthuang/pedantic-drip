---
description: Review data science Python code for anti-patterns and best practices
argument-hint: <file or directory path>
---

# Review DS Code Command

Dispatch the ds-code-reviewer agent to check DS Python code quality.

## Codex Reviewer Routing

Before any reviewer dispatch in this command (ds-code-reviewer), follow the codex-routing reference (primary: `~/.claude/plugins/cache/*/pd*/*/references/codex-routing.md`; fallback for dev workspace: `plugins/pd/references/codex-routing.md`). If codex is installed (per the path-integrity-checked detection helper in the reference doc), route via Codex `task --prompt-file` (foreground). Reuse the reviewer's prompt body verbatim via temp-file delivery (single-quoted heredoc — never argv interpolation). Translate the response per the field-mapping table in the reference doc. Falls back to pd reviewer Task on detection failure or malformed codex output.

**Security exclusion:** This command does NOT dispatch `pd:security-reviewer`, so the codex-routing exclusion does not need to be enforced here. The exclusion is enforced wherever `pd:security-reviewer` IS dispatched (implement, finish-feature).

## Get Target File

If $ARGUMENTS is provided, use it as the target file or directory path.

If $ARGUMENTS is empty, prompt the user:

```
AskUserQuestion:
  questions: [{
    "question": "What would you like to review?",
    "header": "Target",
    "options": [
      {"label": "File", "description": "Review a single Python file or notebook"},
      {"label": "Directory", "description": "Review all Python/notebook files in a directory"},
      {"label": "Recent changes", "description": "Review recently modified DS files"}
    ],
    "multiSelect": false
  }]
```

After selection, ask for the path: "Please provide the file or directory path."

**If "Recent changes":** Use `git diff --name-only HEAD~5` to find recently modified `.py` and `.ipynb` files.

## Dispatch Agent — 3-Chain Review

Execute three sequential Task dispatches. Each chain builds on the prior chain's output.
Store `{target}` = the file or directory path from $ARGUMENTS or user input.

### Chain 1: Anti-patterns, Pipeline Quality, Code Standards

```
Task tool call:
  description: "Review DS code — chain 1: anti-patterns, pipeline, standards"
  subagent_type: pd:ds-code-reviewer
  model: sonnet
  prompt: |
    SCOPE RESTRICTION: Evaluate ONLY the following axes: [anti-patterns, pipeline quality, code standards].
    Ignore all other review sections in your system prompt.
    Do not evaluate, comment on, or report findings for axes outside this list.
    Your response JSON must contain axis_results entries ONLY for the listed axes.
    Any axis_results entry for an unlisted axis will be discarded by the caller.

    Target: {target}

    Read the target file(s) and evaluate these three axes:
    1. Anti-patterns — magic numbers, mutation, hardcoded paths, silent data loss, chained indexing, mixed I/O and logic, implicit column deps, data leakage, uncontrolled randomness, memory issues
    2. Pipeline quality — pure functions, I/O at boundaries, .pipe() chains or composition, data validation at boundaries
    3. Code standards — type hints, NumPy-style docstrings, import ordering, logging instead of print, random seeds

    Return your findings as JSON matching this schema:
    ```json
    {
      "type": "object",
      "properties": {
        "axis_results": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "axis": {"type": "string", "description": "Name of the review axis evaluated"},
              "approved": {"type": "boolean", "description": "True if no blockers found for this axis"},
              "issues": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "severity": {"type": "string", "enum": ["blocker", "warning", "suggestion"]},
                    "description": {"type": "string", "description": "What the issue is"},
                    "location": {"type": "string", "description": "file:line or section reference"},
                    "suggestion": {"type": "string", "description": "How to fix it"}
                  },
                  "required": ["severity", "description", "location", "suggestion"]
                }
              }
            },
            "required": ["axis", "approved", "issues"]
          }
        }
      },
      "required": ["axis_results"]
    }
    ```
```

**Chain 1 output handling:** Extract the JSON object from the Task response. If the response does not contain valid JSON with an `axis_results` array, treat this as a chain failure — do NOT proceed to Chain 2. Return immediately:
```json
{"approved": false, "issues": [{"severity": "blocker", "description": "Chain 1 failed: invalid or missing JSON in response"}], "summary": "Review incomplete due to chain failure"}
```

Store the extracted JSON as `{chain_1_result}`.

If the response exceeds 5KB, log a warning: "Chain 1 output exceeds 5KB — review may produce large context for synthesis."

---

### Chain 2: Notebook Quality, API Correctness

```
Task tool call:
  description: "Review DS code — chain 2: notebook quality, API correctness"
  subagent_type: pd:ds-code-reviewer
  model: sonnet
  prompt: |
    SCOPE RESTRICTION: Evaluate ONLY the following axes: [notebook quality, API correctness].
    Ignore all other review sections in your system prompt.
    Do not evaluate, comment on, or report findings for axes outside this list.
    Your response JSON must contain axis_results entries ONLY for the listed axes.
    Any axis_results entry for an unlisted axis will be discarded by the caller.

    Target: {target}

    Read the target file(s) and evaluate these two axes:
    1. Notebook quality (if .ipynb) — header with title/author/date/purpose, imports in single top cell, markdown narrative between code cells, focused cells, executable top-to-bottom, clean outputs. If the target is not a notebook, return axis approved with no issues.
    2. API correctness — verify at least 1 pandas/numpy/sklearn API usage via Context7. Check for deprecated APIs, correct parameters, expected return types.

    Return your findings as JSON matching this schema:
    ```json
    {
      "type": "object",
      "properties": {
        "axis_results": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "axis": {"type": "string", "description": "Name of the review axis evaluated"},
              "approved": {"type": "boolean", "description": "True if no blockers found for this axis"},
              "issues": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "severity": {"type": "string", "enum": ["blocker", "warning", "suggestion"]},
                    "description": {"type": "string", "description": "What the issue is"},
                    "location": {"type": "string", "description": "file:line or section reference"},
                    "suggestion": {"type": "string", "description": "How to fix it"}
                  },
                  "required": ["severity", "description", "location", "suggestion"]
                }
              }
            },
            "required": ["axis", "approved", "issues"]
          }
        }
      },
      "required": ["axis_results"]
    }
    ```
```

**Chain 2 output handling:** Extract the JSON object from the Task response. If the response does not contain valid JSON with an `axis_results` array, treat this as a chain failure — do NOT proceed to Chain 3. Return immediately:
```json
{"approved": false, "issues": [{"severity": "blocker", "description": "Chain 2 failed: invalid or missing JSON in response"}], "summary": "Review incomplete due to chain failure"}
```

Store the extracted JSON as `{chain_2_result}`.

If the response exceeds 5KB, log a warning: "Chain 2 output exceeds 5KB — review may produce large context for synthesis."

**Scope leakage filtering:** Before constructing Chain 3's prompt, verify that `{chain_1_result}` contains only entries for axes: anti-patterns, pipeline quality, code standards. Verify that `{chain_2_result}` contains only entries for axes: notebook quality, API correctness. Remove any `axis_results` entries for unassigned axes. Log removed entries as warnings in the review output.

---

### Chain 3: Synthesis

```
Task tool call:
  description: "Synthesize DS code review from chain results"
  subagent_type: pd:ds-code-reviewer
  model: sonnet
  prompt: |
    Synthesize the results from two prior review chains into a single consolidated review.
    Do not re-read the original source files.

    ## Prior Chain Results

    ### Chain 1 (anti-patterns, pipeline quality, code standards):
    {chain_1_result}

    ### Chain 2 (notebook quality, API correctness):
    {chain_2_result}

    ## Instructions

    Merge all axis_results from both chains into a unified review. Consolidate:
    - Set approved to false if ANY axis has approved=false
    - Collect all issues across axes, preserving severity and location
    - Identify 2-5 strengths based on axes with few or no issues
    - Include verification details from the API correctness axis
    - Write a 2-3 sentence summary covering all axes

    Return your synthesis as JSON matching this schema:
    ```json
    {
      "type": "object",
      "properties": {
        "approved": {"type": "boolean", "description": "True if no blockers across all axes"},
        "strengths": {
          "type": "array",
          "items": {"type": "string", "description": "Positive observation"}
        },
        "issues": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "severity": {"type": "string", "enum": ["blocker", "warning", "suggestion"]},
              "axis": {"type": "string", "description": "Which review axis flagged this"},
              "description": {"type": "string", "description": "What the issue is"},
              "location": {"type": "string", "description": "file:line or section reference"},
              "suggestion": {"type": "string", "description": "How to fix it"}
            },
            "required": ["severity", "axis", "description", "location", "suggestion"]
          }
        },
        "verification": {
          "type": "object",
          "properties": {
            "api_checked": {"type": "boolean", "description": "Whether at least 1 API usage was verified"},
            "api_details": {"type": "string", "description": "What was checked and result"}
          },
          "required": ["api_checked", "api_details"]
        },
        "summary": {"type": "string", "description": "2-3 sentence overall assessment"}
      },
      "required": ["approved", "strengths", "issues", "verification", "summary"]
    }
    ```
```

**Chain 3 output handling:** Extract the JSON object from the Task response. If Chain 3 fails (invalid JSON or Task error), return a degraded response by concatenating Chain 1 and Chain 2 results with a warning header:
```json
{"approved": false, "strengths": [], "issues": [], "verification": {"api_checked": false, "api_details": "Synthesis chain failed"}, "summary": "Chain 3 synthesis failed. Raw chain results returned as degraded output. Review Chain 1 and Chain 2 results below.", "degraded": true, "chain_1": {chain_1_result}, "chain_2": {chain_2_result}}
```

---

## On Completion

Present findings from the final synthesis (or degraded output) with severity levels:

1. Display summary
2. List blockers (if any) — must fix
3. List warnings — should fix
4. List suggestions — consider fixing
5. Display strengths — what was done well

Then offer follow-up:

```
AskUserQuestion:
  questions: [{
    "question": "Code review complete. What would you like to do?",
    "header": "Next Step",
    "options": [
      {"label": "Review analysis", "description": "Also check for statistical pitfalls with /review-ds-analysis"},
      {"label": "Address issues", "description": "Fix the identified code issues"},
      {"label": "Done", "description": "Review complete, no further action"}
    ],
    "multiSelect": false
  }]
```

**If "Review analysis":**
1. Invoke: `/pd:review-ds-analysis {target file path}`

**If "Address issues":**
1. Display the issues list with suggested fixes
2. Offer to apply fixes automatically where possible

**If "Done":**
1. Display: "DS code review complete."
2. End the workflow
