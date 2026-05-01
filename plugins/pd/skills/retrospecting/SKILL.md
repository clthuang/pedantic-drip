---
name: retrospecting
description: Runs data-driven AORTA retrospective using retro-facilitator agent with full intermediate context. Use when the user says 'run retro', 'capture learnings', 'reflect on feature', or 'update knowledge bank'.
---

# Retrospective

## Static Reference
Data-driven AORTA retrospective using retro-facilitator agent.

## Process

### Step 0: Recovery Check for Interrupted Retros

Before assembling context, check if a previous retro run was interrupted after writing `retro.md` but before completing knowledge bank updates.

1. Check if `{pd_artifacts_root}/features/{id}-{slug}/retro.md` exists
2. If it does NOT exist → skip to Step 1 (fresh run)
3. If it exists, check for completed KB updates:
   - Grep each KB markdown file (`patterns.md`, `anti-patterns.md`, `heuristics.md`) for `Last observed: Feature #{id}`
   - Call `search_memory` MCP with `query: "Feature {id}"`, `limit: 20` — check for DB entries referencing this feature
4. If retro.md exists AND both KB markdown entries AND DB entries are present → retro already completed, skip to Step 5 (commit)
5. If retro.md exists but KB markdown OR DB entries are missing → recovery needed:
   - Parse the "Act (Knowledge Bank Updates)" section from retro.md
   - Extract patterns, anti-patterns, and heuristics entries with their metadata

**YOLO mode:** Auto-select "Resume" without prompting.

**Normal mode:**
```
AskUserQuestion:
  questions: [{
    "question": "retro.md exists but knowledge bank updates are incomplete. How should we proceed?",
    "header": "Retro Recovery",
    "options": [
      {"label": "Resume", "description": "Persist missing KB/DB entries from existing retro.md"},
      {"label": "Re-run", "description": "Discard existing retro.md and run full retrospective"},
      {"label": "Skip", "description": "Leave retro as-is, proceed to commit"}
    ],
    "multiSelect": false
  }]
```

- **Resume**: Jump to Step 3a using parsed entries, then continue through Steps 3b, 4, 4c, 5
- **Re-run**: Continue to Step 1 (overwrite retro.md)
- **Skip**: Jump to Step 5

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
    plus retro_md content.
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

If using fallback, generate retro.md in the legacy format (What Went Well / What Could Improve / Learnings Captured).

**Fallback learning persistence:** After writing retro.md, also execute Steps 3a, 4, and 4c
using the investigation-agent's JSON output. Map fields:
- `patterns` array → Step 4 patterns entries
- `anti_patterns` array → Step 4 anti-patterns entries
- `heuristics` array → Step 4 heuristics entries

For each entry, set defaults for fields the investigation-agent doesn't produce:
- `text`: the string from the array
- `name`: derive from text (first ~60 chars)
- `confidence`: "low"
- `keywords`: []
- `reasoning`: ""
- `provenance`: "Feature #{id} (investigation-agent fallback)"

Skip Step 4b (validation of pre-existing entries) during fallback.

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

### Act (Knowledge Bank Updates)
**Patterns added:**
- {pattern text} (from: {provenance})

**Anti-patterns added:**
- {anti-pattern text} (from: {provenance})

**Heuristics added:**
- {heuristic text} (from: {provenance})

## Raw Data
- Feature: {id}-{slug}
- Mode: {mode}
- Branch lifetime: {days or N/A}
- Total review iterations: {count}
```

### Step 3a: Persist Learnings to DB via store_memory MCP

For each entry in `act.patterns`, `act.anti_patterns`, `act.heuristics` from the retro-facilitator response:

Call `store_memory` MCP tool with:
- `name` — entry name
- `description` — the learning text
- `reasoning` — reasoning from agent (or empty string)
- `category` — one of `patterns`, `anti-patterns`, `heuristics`
- `references` — `["{provenance}"]`
- `confidence` — confidence from agent (or `"medium"`)
- `source` — `"retro"`

Track each entry's name in a local list for verification in Step 3b.

**Fallback** if `store_memory` MCP is unavailable:
```bash
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs dirname)
if [[ -n "$PLUGIN_ROOT" ]] && [[ -x "$PLUGIN_ROOT/.venv/bin/python" ]]; then
  PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -m semantic_memory.writer \
    --action upsert --global-store ~/.claude/pd/memory \
    --entry-json '{"name":"...","description":"...","reasoning":"...","category":"...","source":"retro","confidence":"...","references":"[...]"}'
else
  # dev workspace fallback
  PYTHONPATH=plugins/pd/hooks/lib python3 -m semantic_memory.writer \
    --action upsert --global-store ~/.claude/pd/memory \
    --entry-json '{"name":"...","description":"...","reasoning":"...","category":"...","source":"retro","confidence":"...","references":"[...]"}'
fi
```

On failure: log to stderr, continue (do not block retro completion).

### Step 3b: Verify DB Entries

After all `store_memory` calls in Step 3a:

1. Call `search_memory` MCP with `query: "Feature {id} retrospective learnings"`, `limit: 20`
2. For each entry stored in Step 3a, check its name appears in search results
3. Missing entries: retry `store_memory` once per missing entry
4. Output: `"DB persistence: {n}/{total} entries verified"`

### Step 4: Update Knowledge Bank

From the `act` section of the agent response, append entries to knowledge bank files:

0. Ensure directory exists: `mkdir -p {pd_artifacts_root}/knowledge-bank/`

1. For each pattern in `act.patterns`:
   - Append to `{pd_artifacts_root}/knowledge-bank/patterns.md`
2. For each anti-pattern in `act.anti_patterns`:
   - Append to `{pd_artifacts_root}/knowledge-bank/anti-patterns.md`
3. For each heuristic in `act.heuristics`:
   - Append to `{pd_artifacts_root}/knowledge-bank/heuristics.md`

Each entry format:
```markdown
### {Type}: {Name}
{Text}
- Observed in: {provenance}      ← use "Source:" instead for heuristics.md
- Confidence: {confidence}
- Last observed: Feature #{NNN}
- Observation count: 1
```

If a knowledge-bank file doesn't exist, create it with a header:
```markdown
# {Patterns|Anti-Patterns|Heuristics}

Accumulated learnings from feature retrospectives.
```

### Step 4b: Validate Knowledge Bank (Pre-Existing Entries)

Performed by the orchestrating agent inline (not a sub-agent dispatch). Only validates `anti-patterns.md` and `heuristics.md` (not `patterns.md`).

**a. Read all entries** from `{pd_artifacts_root}/knowledge-bank/anti-patterns.md` and `{pd_artifacts_root}/knowledge-bank/heuristics.md` (~15 entries total).

**b. Identify pre-existing entries** — exclude entries just added in Step 4 by comparing entry names against the retro-facilitator's `act.anti_patterns` and `act.heuristics` output. Only pre-existing entries proceed to validation.

**c. Determine relevance** for each pre-existing entry:
- **RELEVANT** if the entry's domain (file patterns, coding practices, workflow steps) overlaps with this feature's git diff files, implementation-log decisions/deviations, or review-history issues (all already in context from Step 1)
- **NOT RELEVANT** if the entry's domain has no overlap — skip, no update needed

**d. Evaluate relevant entries** against this feature's experience:

| Verdict | Condition | Action |
|---------|-----------|--------|
| CONFIRMED | Feature experience aligns with entry's guidance | Update `Last observed: Feature #{id}`, increment `Observation count` |
| CONTRADICTED | Feature experience contradicts the entry | Append `- Challenged: Feature #{id} — {specific contradiction}` to the entry |

**e. Staleness check** (mechanical, not LLM-judgment):

1. For each pre-existing entry, extract the feature number NNN from `Last observed: Feature #{NNN}`
2. Glob `{pd_artifacts_root}/features/` directories, extract numeric prefix (pattern: `/^(\d+)-/`), count directories with numeric ID > NNN
3. If count >= 10: flag entry as STALE
4. Surface all stale entries to user via AskUserQuestion:
   ```
   AskUserQuestion:
     questions: [{
       "question": "The following entries haven't been observed in 10+ features:\n{list with entry names and last-observed feature numbers}\n\nFor each entry, choose an action.",
       "header": "Stale Knowledge Bank Entries",
       "options": [
         {"label": "Keep", "description": "Remove stale marker, update Last observed to current feature"},
         {"label": "Update", "description": "Provide new text, modify in-place, reset Observation count to 1"},
         {"label": "Retire", "description": "Delete entry from file, note in retro.md"}
       ],
       "multiSelect": false
     }]
   ```
5. Apply user's choice per entry:
   - **Keep**: Remove stale marker, update `Last observed` to current feature, `Observation count` unchanged
   - **Update**: User provides new text, modify entry in-place, update `Last observed`, reset `Observation count` to 1
   - **Retire**: Delete entry from file, append to `retro.md`: `Retired: {entry name} — {user's reason}`

### Step 4c: Promote to Global Store

For each NEW entry written in Step 4 (not pre-existing entries from 4b):

1. Classify as `universal` or `project-specific` with reasoning:
   - Universal: "Always read target file before editing" (no project refs), "Break tasks into one-file-per-task" (general workflow)
   - Project-specific: "Secretary routing table must match hooks.json" (pd architecture), "session-start.sh Python subprocess adds ~200ms" (specific file)
   - Default to `universal` — over-sharing is better than under-sharing

2. For universal entries:
   - Compute content hash: `echo "DESCRIPTION" | python3 -c "import sys,hashlib; print(hashlib.sha256(' '.join(sys.stdin.read().lower().strip().split()).encode()).hexdigest()[:16])"`
   - Read global store file at `~/.claude/pd/memory/{category}.md` (create dir with `mkdir -p` if needed)
   - If hash match: increment `Observation count`, update `Last observed`, append project to `Source`
   - If no match: append entry with full schema (Content-Hash, Source, Observation count: 1, Last observed, Tags: universal, Confidence)

3. For project-specific entries: skip, log reason

4. Output: "Memory promotion: N universal promoted, M project-specific kept local"

### Step 4c.1: Promote-Pattern Adoption Trigger (Feature 101 FR-6)

After universal classification + global-store promotion in Step 4c,
surface `/pd:promote-pattern` to the user when the KB has qualifying
entries. This converts the deferred-value adoption barrier (the command
exists but is rarely invoked) into a moment of immediate trigger.

1. **Enumerate qualifying entries** via subprocess CLI (matches the
   `promoting-patterns` skill's invocation convention):
   ```bash
   PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs -r dirname)
   [ -z "$PLUGIN_ROOT" ] && PLUGIN_ROOT="plugins/pd"  # fallback (dev workspace)
   result=$(PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -m pattern_promotion enumerate --json 2>/dev/null) || result='{"count":0}'
   count=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('count',0))" 2>/dev/null) || count=0
   ```
   Threshold uses existing config key `memory_promote_min_observations`
   (same key reused by FR-4's observation gate; eligibility for
   confidence upgrade and pattern-promotion are aligned).

2. **If `count > 0`:**
   - **YOLO mode** (`[YOLO_MODE]` substring in args, per
     `specifying/SKILL.md:16` precedent): skip the prompt, directly
     invoke `Skill({skill: "pd:promoting-patterns"})`.
   - **Non-YOLO:** AskUserQuestion with options:
     - `"Run /pd:promote-pattern (Recommended)"` →
       `Skill({skill: "pd:promoting-patterns"})`
     - `"Skip"` → continue retro

3. **If `count == 0`:** emit nothing (silent skip).

4. **Subprocess error isolation:** if the enumerate subprocess errors
   (MCP unavailable, missing venv, etc.), log
   `[retrospect] promote-pattern enumerate failed: {error}; skipping trigger`
   to stderr and continue retro. Never block on this step.

### Step 5: Commit

```bash
git add {pd_artifacts_root}/features/{id}-{slug}/retro.md {pd_artifacts_root}/knowledge-bank/
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
| `retro.md` exists but KB not updated | Recovery via Step 0 — parse Act section, persist missing entries |

## Output

```
Retrospective complete (AORTA framework).
Updated: {list of knowledge-bank files updated}
Saved to retro.md.
```

## Automatic Execution

This skill runs automatically during `/pd:finish-feature`:
- No permission prompt required
- Findings drive knowledge bank updates
- User sees summary of learnings captured

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)
- `{pd_base_branch}` — base branch for merges (default: `main`)

## Read Feature Context

1. Find active feature folder in `{pd_artifacts_root}/features/`
2. Read `.meta.json` for mode and context
