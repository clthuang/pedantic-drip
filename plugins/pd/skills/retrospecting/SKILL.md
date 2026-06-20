---
name: retrospecting
description: Runs data-driven AORTA retrospective using retro-facilitator agent with full intermediate context. Use when the user says 'run retro', 'reflect on feature', or 'analyze feature retrospective'.
---

# Retrospective

## Static Reference
Data-driven AORTA retrospective using retro-facilitator agent. Produces a local markdown artifact (`retro.md`).

## Process

### Step 0: Recovery Check for Interrupted Retros

Before assembling context, check if a previous retro run already produced `retro.md`.

1. Check if `{pd_artifacts_root}/features/{id}-{slug}/retro.md` exists
2. If it does NOT exist → continue to Step 1 (fresh run)
3. If it exists → recovery needed:

**YOLO mode:** Auto-select "Skip" without prompting.

**Normal mode:**
```
AskUserQuestion:
  questions: [{
    "question": "retro.md already exists. How should we proceed?",
    "header": "Retro Recovery",
    "options": [
      {"label": "Re-run", "description": "Discard existing retro.md and run full retrospective"},
      {"label": "Skip", "description": "Leave retro as-is, proceed to commit"}
    ],
    "multiSelect": false
  }]
```

- **Re-run**: Continue to Step 1 (overwrite retro.md)
- **Skip**: Jump to Step 4 (commit)

### Step 1: Assemble Context Bundle

Read and collect all intermediate data:

**a. Phase Metrics** — Read `.meta.json` and extract:
- Phase timings: all `phases.*.started` / `phases.*.completed` timestamps
- Iteration counts: `phases.*.iterations`
- Reviewer notes: `phases.*.reviewerNotes`
- Mode: Standard or Full

**b. Review History** — Read `.review-history.md`:
- If file exists: capture full content
- If file doesn't exist: note "No review history available"

**c. Implementation Log** — Read `implementation-log.md`:
- If file exists: capture full content
- If file doesn't exist: note "No implementation log available"

**c2. Workaround extraction (Feature 102 FR-3) — Run `extract_workarounds.py`:**

The retrospecting skill orchestrator runs the bash snippet below as a shell
command via the Bash tool to extract workaround_candidates from the
implementation log. This is invoked at skill runtime, not test-only.

```bash
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/* 2>/dev/null | head -1)
[[ -z "$PLUGIN_ROOT" ]] && PLUGIN_ROOT="plugins/pd"

workaround_candidates=$("$PLUGIN_ROOT/.venv/bin/python3" \
  "$PLUGIN_ROOT/skills/retrospecting/scripts/extract_workarounds.py" \
  --log-path "{pd_artifacts_root}/features/{id}-{slug}/implementation-log.md" \
  --meta-json-path "{pd_artifacts_root}/features/{id}-{slug}/.meta.json" \
  2>/dev/null || echo "[]")
```

Inject the resulting JSON array under the `### Pre-extracted Workaround
Candidates` section of the retro-facilitator dispatch prompt (above). When
the implementation log is absent or no phase has iterations >= 3, the
extractor returns `[]` and the section displays an empty array. The retro-
facilitator agent may then incorporate any extracted candidates into
`act.heuristics` per the existing AORTA flow.

**d. Git Summary** — Run via Bash:
```bash
git log --oneline {pd_base_branch}..HEAD | wc -l
```
```bash
git diff --stat {pd_base_branch}..HEAD
```

**e. Artifact Stats** — Read and count lines for each artifact:
- `spec.md`, `design.md`, `plan.md`, `tasks.md`
- Note which artifacts exist vs missing

**f. AORTA Framework** — Read `references/aorta-framework.md` from this skill's directory.

### Step 2: Dispatch retro-facilitator

```
Task tool call:
  description: "Run AORTA retrospective"
  subagent_type: pd:retro-facilitator
  model: opus
  prompt: |
    Run AORTA retrospective for feature {id}-{slug}.

    ## Context Bundle

    ### Phase Metrics
    {assembled .meta.json extract — phase timings, iterations, reviewer notes, mode}

    ### Review History
    {.review-history.md content, or "No review history available"}

    ### Implementation Log
    {implementation-log.md content, or "No implementation log available"}

    ### Pre-extracted Workaround Candidates
    {workaround_candidates_json — see "Workaround extraction" below}

    ### Git Summary
    Commits: {commit count}
    Files changed:
    {git diff --stat output}

    ### Artifact Stats
    - spec.md: {line count or "missing"}
    - design.md: {line count or "missing"}
    - plan.md: {line count or "missing"}
    - tasks.md: {line count or "missing"}

    ### AORTA Framework
    {content of references/aorta-framework.md}

    Return structured JSON with observe, review, tune, act sections
    plus retro_md content. The act section and retro_md are written to
    retro.md only — no external persistence.
```

**Fallback:** If retro-facilitator agent fails, fall back to investigation-agent:

```
Task tool call:
  description: "Gather feature learnings"
  subagent_type: pd:investigation-agent
  model: sonnet
  prompt: |
    Gather retrospective data for feature {id}-{slug}.

    Read:
    - Feature folder contents ({pd_artifacts_root}/features/{id}-{slug}/)
    - Git log for this branch
    - .review-history.md if exists

    Identify:
    - What went well
    - What could improve
    - Patterns worth documenting
    - Anti-patterns to avoid

    Return structured findings as JSON:
    {
      "what_went_well": [...],
      "what_could_improve": [...],
      "patterns": [...],
      "anti_patterns": [...],
      "heuristics": []
    }
```

If using fallback, generate retro.md in the legacy format (What Went Well / What Could Improve / Learnings Captured). The fallback output is written to retro.md only.

### Step 2c: Fold Pre-Release QA Sidecars (FR-7b from feature 094)

If `{pd_artifacts_root}/features/{id}-{slug}/.qa-gate-low-findings.md` exists:
1. Read its content.
2. Append under `## Pre-release QA notes` H2 in the planned `retro.md` content (create section if absent), prefixed with sub-heading `### LOW findings`.
3. After successful append, `rm` the sidecar file.

If `{pd_artifacts_root}/features/{id}-{slug}/.qa-gate.log` exists:
1. Read its content (skip lines + count lines per AC-7/AC-17 patterns).
2. Append under `## Pre-release QA notes` H2 in `retro.md` (create section if absent), prefixed with sub-heading `### Audit log`.
3. After successful append, `rm` the sidecar file.

**Note:** Each sidecar may exist independently. A skip-only gate run produces only `.qa-gate.log`; a clean dispatch with no LOW findings also produces only `.qa-gate.log`. The fold step must handle each independently.

If neither sidecar exists: skip silently (no-op).

### Step 3: Write retro.md

Write `{pd_artifacts_root}/features/{id}-{slug}/retro.md` using the `retro_md` field from the retro-facilitator agent response.

The retro_md follows the AORTA format:

```markdown
# Retrospective: {Feature Name}

## AORTA Analysis

### Observe (Quantitative Metrics)
| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| ... | ... | ... | ... |

{Quantitative summary}

### Review (Qualitative Observations)
1. **{Observation}** — {evidence}
2. ...

### Tune (Process Recommendations)
1. **{Recommendation}** (Confidence: {level})
   - Signal: {what was observed}
2. ...

### Act (Reflections)
**Patterns:**
- {pattern text} (from: {provenance})

**Anti-patterns:**
- {anti-pattern text} (from: {provenance})

**Heuristics:**
- {heuristic text} (from: {provenance})

## Raw Data
- Feature: {id}-{slug}
- Mode: {mode}
- Branch lifetime: {days or N/A}
- Total review iterations: {count}
```

The `act` section is part of the retro.md markdown artifact only — pd does not persist these reflections to any external store.

### Step 4: Commit

```bash
git add {pd_artifacts_root}/features/{id}-{slug}/retro.md
git commit -m "docs: AORTA retrospective for feature {id}-{slug}"
git push
```

## Graceful Degradation

| Condition | Behavior |
|-----------|----------|
| `.review-history.md` missing | Agent runs with metrics-only (Observe works, Review limited) |
| `.meta.json` has no phase data | Agent notes "insufficient data", produces minimal retro |
| retro-facilitator agent fails | Fall back to investigation-agent (Step 2 fallback) |
| No git data available | Omit git summary from context bundle |
| `retro.md` already exists | Recovery via Step 0 — prompt to re-run or skip |

## Output

```
Retrospective complete (AORTA framework).
Saved to retro.md.
```

## Automatic Execution

This skill runs automatically during `/pd:finish-feature`:
- No permission prompt required
- User sees summary of the AORTA reflection

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)
- `{pd_base_branch}` — base branch for merges (default: `main`)

## Read Feature Context

1. Find active feature folder in `{pd_artifacts_root}/features/`
2. Read `.meta.json` for mode and context
