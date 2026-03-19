---
description: Generate three-tier documentation scaffold or update existing docs
argument-hint: ""
---

# /pd:generate-docs Command

Generate or update structured project documentation across all enabled tiers.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)
- `pd_doc_tiers` — comma-separated list of enabled documentation tiers (default: `user-guide,dev-guide,technical`)

## YOLO Mode Overrides

If `[YOLO_MODE]` is active:
- Scaffold confirmation gate -> auto-select "Scaffold" (generate-docs is explicit user invocation, safe to auto-proceed)

---

## Step 1: Parse and Validate Tiers

<!-- SYNC: tier-resolution -->
1. Read `pd_doc_tiers` from session context
2. Split on comma, trim whitespace from each value
3. Filter to only recognized values: `user-guide`, `dev-guide`, `technical`
4. If no recognized tier names remain after filtering, output:
   ```
   No valid documentation tiers configured. Check doc_tiers in .claude/pd.local.md.
   ```
   Stop execution. Do not invoke updating-docs skill.

## Step 2: Resolve Mode

<!-- NOTE: Doc tier directories (docs/user-guide/, docs/dev-guide/, docs/technical/) are always
     at the project root, NOT under {pd_artifacts_root}. This is intentional: doc tiers are
     project-facing public documentation; {pd_artifacts_root} controls pd workflow artifacts
     (features/, brainstorms/, projects/). They may live in separate directory trees when
     {pd_artifacts_root} is not "docs". -->

For each recognized tier from Step 1, check if `docs/{tier}/` exists relative to the project root (cwd).

- If **any** enabled tier directory is missing -> `mode=scaffold`
- If **all** enabled tier directories exist -> `mode=incremental`

## Step 3: Pre-Compute Git Timestamps

<!-- SYNC: enriched-doc-dispatch -->
For each enabled tier, compute the timestamp of the most recent source change using the tier-to-source monitored directories from doc-schema:

- **user-guide:** `git log -1 --format=%aI -- README.md package.json setup.py pyproject.toml bin/`
- **dev-guide:** `git log -1 --format=%aI -- src/ test/ Makefile .github/ CONTRIBUTING.md docker-compose.yml`
- **technical:** `git log -1 --format=%aI -- src/ docs/technical/`

If any command returns empty output (no commits for those paths), use the literal string `"no-source-commits"` for that tier. Store results as a map:

```json
{ "user-guide": "2024-01-15T10:30:00+00:00", "dev-guide": "no-source-commits", "technical": "2024-01-20T14:00:00+00:00" }
```

## Step 4: Scaffold Confirmation (scaffold mode only)

If `mode=scaffold`:

1. Build a file summary by looking up each missing tier's files from doc-schema. Display:
   ```
   Will create: docs/{tier1}/overview.md, docs/{tier1}/installation.md, ... ({N} files total)
   ```
   Where `{N}` is the total count of files across all missing tiers.

2. Ask for confirmation:

```
AskUserQuestion:
  questions: [{
    "question": "Documentation scaffolding will create new directories and starter files.",
    "header": "Scaffold",
    "options": [
      {"label": "Scaffold", "description": "Create docs/{tier}/ directories with starter content for all missing tiers"},
      {"label": "Skip", "description": "Exit without writing"}
    ],
    "multiSelect": false
  }]
```

If "Skip": Output "Scaffolding skipped." and stop execution.

If `[YOLO_MODE]` is active: auto-select "Scaffold" without prompting.

## Step 5: ADR Extraction Scanning

Glob `{pd_artifacts_root}/features/*/design.md` to discover design files for ADR context.

1. Sort matched files by directory number descending (e.g., `028-*` before `027-*`)
2. Cap at 10 most recent files
3. If more than 10 files matched, log: `"Skipping {N} older features for ADR scan"` where `{N}` is the number of skipped files
4. Collect the capped list as `design_md_paths`

If no design.md files found, set `design_md_paths` to an empty array (ADR context injection will be skipped by the skill).

## Step 6: Invoke Updating-Docs Skill

Invoke the `updating-docs` skill with:
- `mode`: resolved mode from Step 2 (scaffold or incremental)
- `design_md_paths`: array from Step 5
- Enabled tiers from Step 1
- Pre-computed `tier_timestamps` from Step 3

The skill handles doc-schema resolution, researcher/writer dispatch, and result reporting.

## Output

After skill completion, display the summary returned by the skill.

```
Documentation generation complete.
Mode: {scaffold|incremental}
Tiers: {comma-separated list of enabled tiers}
```
