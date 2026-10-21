# Specification: Backlog to Feature Link

## Problem Statement

When a brainstorm originates from a backlog item and gets promoted to a feature, the backlog item remains, causing duplicate tracking and requiring manual cleanup.

## Success Criteria

- [ ] `/create-feature` detects backlog source from brainstorm header
- [ ] Backlog ID is stored in `.meta.json` as `backlog_source`
- [ ] Matching backlog row is removed from `docs/backlog.md`
- [ ] Features without backlog origin work unchanged

## Scope

### In Scope

- Update `/create-feature` command to parse brainstorm for backlog source
- Store backlog ID in `.meta.json`
- Remove backlog row when feature is created

### Out of Scope

- Changes to `/brainstorm` command (already captures source)
- Backlog status tracking (just remove, don't mark as "in progress")
- Bidirectional linking (feature → backlog is enough)

## Technical Details

### Brainstorm Header Pattern

The backlog source is captured in brainstorm files using this exact format:
```
*Source: Backlog #XXXXX*
```

Where `XXXXX` is a 5-digit zero-padded ID (e.g., `00001`, `00042`).

**Regex pattern:** `\*Source: Backlog #(\d{5})\*`

The pattern appears on its own line, typically near the top of the brainstorm file after the title.

## Acceptance Criteria

### Detect Backlog Source

- Given a brainstorm.md containing line `*Source: Backlog #00001*`
- When `/create-feature` is invoked
- Then the backlog ID "00001" is extracted using regex `\*Source: Backlog #(\d{5})\*`

### Store in Meta

- Given a detected backlog source "00001"
- When `.meta.json` is created
- Then it includes `"backlog_source": "00001"`

### Remove from Backlog

- Given a detected backlog source "00001"
- When `.meta.json` is created
- Then the row with ID "00001" is removed from `docs/backlog.md`

### No Backlog Source

- Given a brainstorm.md without backlog source header
- When `/create-feature` is invoked
- Then no `backlog_source` field is added and `docs/backlog.md` is unchanged

### Backlog Not Found

- Given a backlog source "99999" that doesn't exist in backlog.md
- When `/create-feature` is invoked
- Then display console warning: `⚠️ Backlog item #99999 not found in docs/backlog.md`
- And continue with feature creation (non-blocking warning)
- And still store `"backlog_source": "99999"` in `.meta.json` for traceability

## Dependencies

- `/create-feature` command exists
- `docs/backlog.md` follows table format with ID column

## Open Questions

- None
