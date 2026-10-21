# Brainstorm: Link Backlog Items to Features

*Started: 2026-01-31*

## Problem Statement

When a brainstorm originates from a backlog item and gets promoted to a feature, there's no automatic linkage:

1. **Duplicate tracking** — Same item exists in backlog AND as a feature
2. **Lost traceability** — No record linking the feature back to its backlog origin
3. **Manual cleanup** — User must remember to update backlog after `/create-feature`

## Goals

1. **Auto-remove from backlog** — When `/create-feature` runs with a backlog item context, automatically delete that item from `docs/backlog.md`
2. **Maintain traceability** — Store backlog ID in `.meta.json` so origin is documented even after removal

## Approaches Considered

### Approach A: Parse from brainstorm.md header

- Brainstorm already captures "Source: Backlog #00001" in header
- `/create-feature` parses this to detect backlog origin
- **Pros:** No changes to brainstorming skill, uses existing data
- **Cons:** Relies on consistent header format

### Approach B: Explicit argument to /create-feature

- User passes `--from-backlog 00001` to create-feature
- **Pros:** Explicit, no parsing needed
- **Cons:** Extra user effort, easy to forget

### Approach C: Store in scratch file metadata

- Brainstorming skill writes a metadata section with backlog ID
- **Pros:** Structured data
- **Cons:** More changes needed

## Chosen Direction

**Approach A: Parse from brainstorm.md header**

The brainstorm already includes `*Source: Backlog #00001*` when started from a backlog item. The `/create-feature` command will:

1. Read the brainstorm content
2. Parse for pattern `Source: Backlog #(\d+)`
3. If found:
   - Store `backlog_source: "00001"` in `.meta.json`
   - Remove the matching row from `docs/backlog.md`
4. If not found: proceed normally (no backlog linkage)

## Open Questions

None - approach is straightforward.

## Next Steps

1. Update `/create-feature` command to:
   - Parse brainstorm for backlog source
   - Store in `.meta.json`
   - Remove from `docs/backlog.md`
