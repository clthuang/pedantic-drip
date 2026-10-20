# Design: Update Documentation Step

## Architecture Overview

A lightweight addition to the `/finish` workflow that prompts for documentation review and provides a dedicated `/update-docs` skill for guided updates.

```
                    ┌─────────────┐
                    │  /finish    │
                    └──────┬──────┘
                           │
    ┌──────────────────────┼──────────────────────┐
    │                      │                      │
    ▼                      ▼                      ▼
┌────────────┐     ┌────────────────┐     ┌────────────┐
│ Uncommitted│     │ Tasks Complete │     │ Quality    │
│ Changes?   │     │ Check          │     │ Review?    │
└────────────┘     └────────────────┘     └────────────┘
                                                │
                                                ▼
                                         ┌────────────────┐
                                         │ Documentation  │ ← NEW
                                         │ Review?        │
                                         └───────┬────────┘
                                                 │ (if yes)
                                                 ▼
                                         ┌────────────────┐
                                         │ /update-docs   │
                                         │ skill          │
                                         └────────────────┘
```

## Components

### Component 1: Documentation Detector

**Purpose:** Identify which documentation files exist in the project

**Inputs:** Project root path

**Outputs:** List of detected doc files with metadata

```
Detected files:
- README.md (exists: true, path: /README.md)
- CHANGELOG.md (exists: false)
- HISTORY.md (exists: false)
- API.md (exists: false)
- docs/*.md (exists: true, count: 3)
```

**Detection targets:**
| File Pattern | Description |
|-------------|-------------|
| `README.md` | Primary project readme |
| `CHANGELOG.md` | Version history |
| `HISTORY.md` | Alternative changelog |
| `docs/*.md` | Documentation folder (top-level only) |
| `API.md` | API documentation |

**Note:** Does NOT recurse into `docs/` subdirectories (KISS principle - avoids feature folders, knowledge-bank, etc.)

### Component 2: /update-docs Skill

**Purpose:** Guide user through documentation updates based on feature context

**Inputs:**
- Feature context (spec.md, brainstorm.md if available)
- Detected documentation files

**Outputs:**
- Suggestions for which docs need updating
- Context extracted from feature to assist updates

**Behavior:**
1. Detect available doc files
2. Read feature context (spec.md → success criteria, scope)
3. Present suggestions with reasoning
4. User decides what to update
5. Provide context when user edits each file

### Component 3: /finish Integration

**Purpose:** Add documentation check to pre-completion flow

**Inputs:** Feature state, detected doc files

**Outputs:** Prompt to run /update-docs (skippable)

**Position in flow:** After quality review, before completion options

## Interfaces

### Documentation Detector (internal helper)

```
Input:  project_root (string)
Output: {
  readme: { exists: boolean, path: string },
  changelog: { exists: boolean, path: string },  // CHANGELOG.md
  history: { exists: boolean, path: string },    // HISTORY.md (alt changelog)
  api: { exists: boolean, path: string },        // API.md
  docs: { exists: boolean, files: string[] }     // docs/*.md (top-level only)
}
Errors: None (returns empty/false for missing files)
```

### /update-docs Skill Interaction

```
Input:  User invokes /update-docs
Output: Interactive session:
        1. "Detected documentation files: {list}"
        2. "Based on feature spec, these might need updates:"
           - README: {reason or "No user-visible changes detected"}
           - CHANGELOG: "New feature - entry recommended"
        3. "Would you like to update any of these? (select)"
        4. For each selected: Open for editing with context
```

### /finish Pre-Completion Check

```
Input:  Feature context, doc detection result
Output:
  - If docs exist: "Documentation review? Run /update-docs (y/n)"
  - If no docs: Skip silently
  - User choice "n": Continue to completion options
  - User choice "y": Invoke /update-docs skill
```

**Note:** Single y/n choice (KISS). No separate "skip" option—declining IS skipping.

## Technical Decisions

### Decision 1: No Auto-Generation

- **Choice:** Suggest updates, don't auto-write
- **Alternatives:** Generate draft content, fully automate
- **Rationale:** Documentation requires human judgment on tone, audience, detail level. Auto-generated docs often need heavy editing anyway.

### Decision 2: Top-Level docs/ Only

- **Choice:** Only scan `docs/*.md`, not subdirectories
- **Alternatives:** Recursive scan, configurable depth
- **Rationale:** Subdirectories often contain feature docs, knowledge-bank, or other structured content that shouldn't be treated as user documentation.

### Decision 3: Advisory, Not Blocking

- **Choice:** Documentation check is skippable
- **Alternatives:** Require docs update, block merge without docs
- **Rationale:** Some changes don't need doc updates (refactors, internal fixes). Forcing it would create friction and possibly lead to trivial doc changes.

### Decision 4: Feature Context for Suggestions

- **Choice:** Read spec.md to determine if changes are user-visible
- **Alternatives:** Analyze code changes, commit messages
- **Rationale:** spec.md already captures user-visible changes. Code analysis would be complex and prone to false positives.

#### User-Visible Changes Heuristics

Extract from spec.md's **In Scope** section. A change is user-visible if it:

| Indicator | Example | Doc Impact |
|-----------|---------|------------|
| Adds new command/skill | "Create `/update-docs` skill" | README (usage), CHANGELOG |
| Changes existing command behavior | "Modify `/finish` to offer..." | README (if behavior documented), CHANGELOG |
| Adds configuration option | "Add `--no-review` flag" | README (options), CHANGELOG |
| Changes user-facing output | "Show documentation suggestions" | CHANGELOG |
| Deprecates/removes feature | "Remove legacy mode" | README, CHANGELOG (breaking) |

**NOT user-visible** (no doc update needed):
- Internal refactoring ("Restructure helper functions")
- Performance improvements (unless >2x change)
- Code quality ("Add error handling", "Fix type errors")
- Test additions ("Add unit tests for...")

**Extraction algorithm:**
1. Read spec.md "In Scope" section
2. For each bullet, check against indicator table
3. If ANY match → suggest README/CHANGELOG update
4. If NONE match → report "No user-visible changes detected"

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Users always skip doc check | Docs still drift | Make suggestions helpful enough to be worth reviewing |
| False positives (suggest update when not needed) | Annoyance | Keep suggestions high-level; user decides |
| Missing doc files in unusual locations | Incomplete detection | Accept limitation; document supported patterns |

## Dependencies

- Existing `/finish` command (commands/finish.md)
- Feature context files (spec.md, brainstorm.md)
- Glob tool for file detection
