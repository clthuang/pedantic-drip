---
description: Review data analysis for statistical pitfalls and methodology issues
argument-hint: <notebook or script path>
---

# Review Analysis Command

Dispatch the ds-analysis-reviewer agent via 3 chained calls to review analysis for statistical pitfalls, methodology issues, and conclusion validity.

## Codex Reviewer Routing

Before any reviewer dispatch in this command (ds-analysis-reviewer), follow the codex-routing reference (primary: `~/.claude/plugins/cache/*/pd*/*/references/codex-routing.md`; fallback for dev workspace: `plugins/pd/references/codex-routing.md`). If codex is installed (per the path-integrity-checked detection helper in the reference doc), route via Codex `task --prompt-file` (foreground). Reuse the reviewer's prompt body verbatim via temp-file delivery (single-quoted heredoc — never argv interpolation). Translate the response per the field-mapping table in the reference doc. Falls back to pd reviewer Task on detection failure or malformed codex output.

**Security exclusion:** This command does NOT dispatch `pd:security-reviewer`, so the codex-routing exclusion does not need to be enforced here. The exclusion is enforced wherever `pd:security-reviewer` IS dispatched (implement, finish-feature).

## Get Target File

If $ARGUMENTS is provided, use it as the target file path.

If $ARGUMENTS is empty, prompt the user:

```
AskUserQuestion:
  questions: [{
    "question": "What would you like to review?",
    "header": "Target",
    "options": [
      {"label": "Notebook", "description": "Review a Jupyter notebook (.ipynb)"},
      {"label": "Script", "description": "Review a Python script (.py)"},
      {"label": "Directory", "description": "Review all analysis files in a directory"}
    ],
    "multiSelect": false
  }]
```

After selection, ask for the path: "Please provide the file or directory path."

## Load Skill

Read the analysis pitfalls skill: Glob `~/.claude/plugins/cache/*/pd*/*/skills/spotting-ds-analysis-pitfalls/SKILL.md` — read first match.
Fallback: Read `plugins/pd/skills/spotting-ds-analysis-pitfalls/SKILL.md` (dev workspace).
If not found: proceed with general analysis pitfall methodology.

## Chain 1: Methodology, Statistical Validity, Data Quality

Dispatch the ds-analysis-reviewer agent for the first set of review axes.

```
Task tool call:
  description: "Review analysis — Chain 1: methodology, statistical validity, data quality"
  subagent_type: pd:ds-analysis-reviewer
  model: opus
  prompt: |
    SCOPE RESTRICTION: Evaluate ONLY the following axes: [methodology, statistical validity, data quality].
    Ignore all other review sections in your system prompt.
    Do not evaluate, comment on, or report findings for axes outside this list.
    Your response JSON must contain axis_results entries ONLY for the listed axes.
    Any axis_results entry for an unlisted axis will be discarded by the caller.

    Review this data analysis for the axes listed above:

    Target: {file path from $ARGUMENTS or user input}

    Read the target file(s) and evaluate:
    - Methodology: analysis type fit, statistical method correctness, documented assumptions, sample size, confidence intervals
    - Statistical validity: walk through the pitfall diagnostic tree (sampling & selection, statistical traps, temporal & leakage, inference errors)
    - Data quality: population representativeness, missing value handling, outlier treatment, train/test leakage

    Verify at least 1 statistical claim using external tools.

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
              "axis": { "type": "string", "description": "Name of the review axis evaluated" },
              "approved": { "type": "boolean", "description": "True if no blockers found for this axis" },
              "issues": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "severity": { "type": "string", "enum": ["blocker", "warning", "suggestion"] },
                    "description": { "type": "string", "description": "What the issue is" },
                    "location": { "type": "string", "description": "file:line or section reference" },
                    "suggestion": { "type": "string", "description": "How to fix it" }
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

**Chain 1 error handling:** If Chain 1 fails (Task returns error or invalid JSON), do NOT proceed to Chain 2 or Chain 3. Return immediately:
```json
{"approved": false, "issues": [{"severity": "blocker", "description": "Chain 1 failed: {error}"}], "summary": "Review incomplete due to chain failure — halt before remaining chains"}
```

Capture Chain 1's JSON output for use in Chain 3.

## Chain 2: Conclusion Validity, Reproducibility

Dispatch the ds-analysis-reviewer agent for the second set of review axes.

```
Task tool call:
  description: "Review analysis — Chain 2: conclusion validity, reproducibility"
  subagent_type: pd:ds-analysis-reviewer
  model: opus
  prompt: |
    SCOPE RESTRICTION: Evaluate ONLY the following axes: [conclusion validity, reproducibility].
    Ignore all other review sections in your system prompt.
    Do not evaluate, comment on, or report findings for axes outside this list.
    Your response JSON must contain axis_results entries ONLY for the listed axes.
    Any axis_results entry for an unlisted axis will be discarded by the caller.

    Review this data analysis for the axes listed above:

    Target: {file path from $ARGUMENTS or user input}

    Read the target file(s) and evaluate:
    - Conclusion validity: conclusions supported by analysis, causal claims backed by causal methods, limitations stated, alternative explanations considered
    - Reproducibility: random seeds set, environment documented, data pipeline deterministic, results reproducible from raw data

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
              "axis": { "type": "string", "description": "Name of the review axis evaluated" },
              "approved": { "type": "boolean", "description": "True if no blockers found for this axis" },
              "issues": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "severity": { "type": "string", "enum": ["blocker", "warning", "suggestion"] },
                    "description": { "type": "string", "description": "What the issue is" },
                    "location": { "type": "string", "description": "file:line or section reference" },
                    "suggestion": { "type": "string", "description": "How to fix it" }
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

**Chain 2 error handling:** If Chain 2 fails (Task returns error or invalid JSON), do NOT proceed to Chain 3. Return immediately:
```json
{"approved": false, "issues": [{"severity": "blocker", "description": "Chain 2 failed: {error}"}], "summary": "Review incomplete due to chain failure — halt before synthesis"}
```

Capture Chain 2's JSON output for use in Chain 3.

## Scope Leakage Filter

Before constructing Chain 3's prompt, verify that Chain 1 and Chain 2 `axis_results` contain only the assigned axes:
- Chain 1 allowed axes: methodology, statistical validity, data quality
- Chain 2 allowed axes: conclusion validity, reproducibility

Remove any `axis_results` entries for unassigned axes. Log removed entries as warnings in the review output.

## Chain 3: Synthesis

Construct Chain 3's prompt with both prior JSON results embedded.

```
Task tool call:
  description: "Review analysis — Chain 3: synthesis of all findings"
  subagent_type: pd:ds-analysis-reviewer
  model: opus
  prompt: |
    Synthesize the following chain results into a single consolidated analysis review.
    Do not re-read the original files.

    ## Prior Chain Results

    ### Chain 1 Results (methodology, statistical validity, data quality)
    {Chain 1 JSON output}

    ### Chain 2 Results (conclusion validity, reproducibility)
    {Chain 2 JSON output}

    Merge all axis results into a unified review. Deduplicate overlapping issues.
    Determine overall approval: approved is true only when zero blockers across all axes.

    Return your synthesis as JSON matching this schema:

    ```json
    {
      "type": "object",
      "properties": {
        "approved": { "type": "boolean", "description": "True if no blockers across all axes" },
        "pitfalls_detected": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string", "description": "Pitfall category name" },
              "severity": { "type": "string", "enum": ["blocker", "warning", "suggestion"] },
              "description": { "type": "string", "description": "What the pitfall is" },
              "evidence": { "type": "string", "description": "How it was detected" }
            }
          }
        },
        "code_issues": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "severity": { "type": "string", "enum": ["blocker", "warning", "suggestion"] },
              "description": { "type": "string", "description": "Code-level issue" },
              "location": { "type": "string", "description": "file:line reference" }
            }
          }
        },
        "methodology_concerns": {
          "type": "array",
          "items": { "type": "string", "description": "Methodology observation" }
        },
        "verification": {
          "type": "object",
          "properties": {
            "claim_checked": { "type": "boolean", "description": "Whether at least 1 statistical claim was verified" },
            "claim_details": { "type": "string", "description": "What was checked and result" }
          }
        },
        "recommendations": {
          "type": "array",
          "items": { "type": "string", "description": "Actionable recommendation" }
        },
        "summary": { "type": "string", "description": "2-3 sentence overall assessment" }
      }
    }
    ```
```

**Chain 3 error handling:** If Chain 3 fails, return the raw Chain 1 and Chain 2 results concatenated as a degraded response:
```
WARNING: Synthesis chain failed. Returning raw chain results in degraded mode.

Chain 1 (methodology, statistical validity, data quality):
{Chain 1 JSON output}

Chain 2 (conclusion validity, reproducibility):
{Chain 2 JSON output}
```

## On Completion

After the synthesis completes, present findings and offer follow-up:

1. Display summary
2. List blockers (if any) -- must fix
3. List warnings -- should fix
4. List suggestions -- consider fixing
5. Display pitfalls detected with evidence
6. Display methodology concerns
7. Display verification results

```
AskUserQuestion:
  questions: [{
    "question": "Analysis review complete. What would you like to do?",
    "header": "Next Step",
    "options": [
      {"label": "Review DS code quality", "description": "Also check code anti-patterns with /review-ds-code"},
      {"label": "Address issues", "description": "Fix the identified pitfalls and issues"},
      {"label": "Done", "description": "Review complete, no further action"}
    ],
    "multiSelect": false
  }]
```

**If "Review DS code quality":**
1. Invoke: `/pd:review-ds-code {target file path}`

**If "Address issues":**
1. Display the issues list with suggested fixes
2. Offer to apply fixes automatically where possible

**If "Done":**
1. Display: "Analysis review complete."
2. End the workflow
