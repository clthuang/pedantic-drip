# Brainstorm: Update Command References

## Problem Statement

Command references throughout documentation use `/command` format instead of the namespaced `/iflow:command` format required by the plugin system.

## Goals

- Update all command references to use `/iflow:` prefix
- Maintain consistency across user-facing documentation

## Scope Analysis

Grep found 695 occurrences across 67 files.

**File categories:**
| Category | Files | Priority |
|----------|-------|----------|
| README.md | 1 | High - user-facing |
| CLAUDE.md | 1 | High - AI instructions |
| plugins/iflow/ | ~20 | High - defines the commands |
| docs/features/ | ~40 | Medium - historical records |
| docs/plans/ | ~5 | Low - historical |

## Options Considered

1. **Full update** - Change all 695 occurrences across all files
2. **User-facing only** - README.md, CLAUDE.md, plugins/iflow/ (active docs)
3. **Exclude historical features** - Skip completed feature folders (002-007)

## Chosen Direction

Option 2: User-facing + active plugin docs only.

Rationale: Historical feature docs are records of what was done at the time. Updating them would be revisionist and adds no value.

## Next Steps

Mechanical search-and-replace across target files.
