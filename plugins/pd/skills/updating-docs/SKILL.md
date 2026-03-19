---
name: updating-docs
description: Automatically updates documentation using agents. Use when the user says 'update docs', 'sync documentation', or when completing a feature.
---

# Updating Documentation

Automatic documentation updates using documentation-researcher and documentation-writer agents.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

## Parameters

- `mode` — **required**, one of `scaffold` or `incremental`. Passed by the invoking command.
  - `scaffold`: Full codebase doc generation. Used for bootstrapping docs.
  - `incremental`: Feature-specific doc updates. Used for ongoing feature work.
- `design_md_paths` — **optional**, array of file paths to design.md files. When provided, the Technical Decisions section from each file is read and injected into the writer dispatch prompt as ADR context. When not provided or empty, ADR context injection is skipped.

## Prerequisites

- Feature folder in `{pd_artifacts_root}/features/` with spec.md for context
- This skill is invoked by `/pd:generate-docs` only. finish-feature and wrap-up implement equivalent doc dispatch inline (per TD7) — they do NOT invoke this skill.

## Dispatch Budget

Dispatch patterns differ by mode to control agent concurrency.

**Incremental mode** (max 3 dispatches):
1. 1 researcher dispatch (documentation-researcher)
2. 1 writer dispatch for the single affected tier (documentation-writer)
3. 1 optional README/CHANGELOG writer dispatch (documentation-writer) — only if researcher findings include user-facing `recommended_updates` or `changelog_state.needs_entry` is true

**Scaffold mode** (max 5 dispatches):
1. 1 researcher dispatch (documentation-researcher)
2. 1 writer dispatch per enabled tier, run sequentially not in parallel (documentation-writer) — up to 3 tiers
3. 1 README/CHANGELOG writer dispatch (documentation-writer)

## Process

### Step 0: Resolve Doc-Schema Reference

<!-- SYNC: enriched-doc-dispatch -->
Glob `~/.claude/plugins/cache/*/pd*/*/references/doc-schema.md` — use first match. Fallback (dev workspace): `plugins/pd/references/doc-schema.md`.

Read the resolved file content. Before injecting into dispatch prompts, replace all occurrences of `{pd_artifacts_root}` in the doc-schema content with the actual session value (e.g., if `{pd_artifacts_root}` is `docs`, replace all `{pd_artifacts_root}` strings in the doc-schema content with `docs`).

The resolved and variable-replaced doc-schema content is injected into BOTH the researcher dispatch prompt AND the writer dispatch prompt as inline context.

### Step 0b: Timestamp Injection

<!-- SYNC: enriched-doc-dispatch -->
The invoking command must pre-compute per-tier git timestamps and inject them into the researcher dispatch prompt. Format:

```json
{ "user-guide": "ISO-timestamp", "dev-guide": "ISO-timestamp", "technical": "ISO-timestamp" }
```

This skill does not run git commands — timestamps are pre-computed by the caller. The skill passes the `tier_timestamps` object through to the researcher dispatch prompt verbatim.

### Step 0c: ADR Context (Optional)

If `design_md_paths` parameter is provided and non-empty:
1. For each path in `design_md_paths`, read the file and extract the Technical Decisions section
2. Collect all extracted Technical Decisions content
3. Inject into the writer dispatch prompt as ADR context (the writer uses this for ADR extraction)

If `design_md_paths` is not provided or is empty, skip this step entirely.

### Step 1: Dispatch Documentation Researcher

<!-- SYNC: enriched-doc-dispatch -->
```
Task tool call:
  description: "Research documentation context"
  subagent_type: pd:documentation-researcher
  model: sonnet
  prompt: |
    Research current documentation state for feature {id}-{slug}.

    Mode: {mode}

    Feature context:
    - spec.md: {content summary}
    - Files changed: {list from git diff}

    Tier timestamps (pre-computed by caller):
    {tier_timestamps JSON object}

    Doc-schema reference:
    ---
    {resolved doc-schema content with {pd_artifacts_root} replaced}
    ---

    Find:
    - Existing docs that may need updates
    - What user-visible changes were made
    - What documentation patterns exist in project
    - Ground truth drift: detect project type and run the matching drift detection strategy

    Return findings as structured JSON.
```

### Step 2: Evaluate Findings

Check researcher output:

**If `no_updates_needed: true`:**

```
AskUserQuestion:
  questions: [{
    "question": "No user-visible changes detected. Skip documentation?",
    "header": "Docs",
    "options": [
      {"label": "Skip", "description": "No documentation updates needed"},
      {"label": "Write anyway", "description": "Force documentation update"}
    ],
    "multiSelect": false
  }]
```

If "Skip": Exit skill - no documentation updates.

### Step 3: Dispatch Documentation Writer

If updates needed, dispatch writer(s) according to the dispatch budget for the current `mode`.

**Incremental mode:** Dispatch a single writer for the affected tier identified by the researcher.

**Scaffold mode:** Dispatch one writer per enabled tier, sequentially (wait for each to complete before dispatching the next).

Each writer dispatch uses this template:

```
Task tool call:
  description: "Update documentation — {tier name or README/CHANGELOG}"
  subagent_type: pd:documentation-writer
  model: sonnet
  prompt: |
    Update documentation based on research findings.

    Mode: {mode}
    Feature: {id}-{slug}
    Research findings: {JSON from researcher agent}

    Doc-schema reference:
    ---
    {resolved doc-schema content with {pd_artifacts_root} replaced}
    ---

    {If ADR context was collected in Step 0c, include:}
    ADR Context:
    ---
    {Technical Decisions content from design.md files}
    ---

    Pay special attention to any `drift_detected` entries — these represent
    documented items that don't match the filesystem (or vice versa).
    Update the affected documentation files. Add missing entries,
    remove stale entries, and correct any count headers.

    Also update CHANGELOG.md:
    - Add entries under the `## [Unreleased]` section
    - Use Keep a Changelog categories: Added, Changed, Fixed, Removed
    - Only include user-visible changes (new commands, skills, config options, behavior changes)
    - Skip internal refactoring, test additions, and code quality changes

    Write necessary documentation updates.
    Return summary of changes made.
```

**README/CHANGELOG dispatch** (applies to both modes when needed):

If the researcher findings include user-facing `recommended_updates` or `changelog_state.needs_entry` is true, dispatch an additional writer focused on README and CHANGELOG updates. In scaffold mode, this is always dispatched as the final writer.

### Step 4: Report Results

Show summary from documentation-writer:

```
Documentation updated:
- README.md: Added /finish command to commands table
- {Other updates...}
```

## What Gets Documented

| Change Type | Documentation Impact |
|-------------|---------------------|
| New command/skill | README commands table, CHANGELOG |
| Changed behavior | README (if documented), CHANGELOG |
| New config option | README, CHANGELOG |
| User-facing output change | CHANGELOG |
| Deprecated/removed feature | README, CHANGELOG (breaking) |

## What Does NOT Get Documented

- Internal refactoring
- Performance improvements (unless >2x)
- Code quality improvements
- Test additions

## Advisory, Not Blocking

This skill suggests but does not require updates:
- User can skip if no user-visible changes
- Agents determine what needs updating
- No enforcement or blocking behavior
