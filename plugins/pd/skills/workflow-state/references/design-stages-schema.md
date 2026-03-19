# Design Phase Stages Schema

The design phase uses a 4-stage workflow with detailed tracking:

```json
{
  "phases": {
    "design": {
      "started": "2026-01-30T01:00:00Z",
      "completed": "2026-01-30T02:00:00Z",
      "stages": {
        "architecture": {
          "started": "2026-01-30T01:00:00Z",
          "completed": "2026-01-30T01:15:00Z"
        },
        "interface": {
          "started": "2026-01-30T01:15:00Z",
          "completed": "2026-01-30T01:30:00Z"
        },
        "designReview": {
          "started": "2026-01-30T01:30:00Z",
          "completed": "2026-01-30T01:45:00Z",
          "iterations": 2,
          "reviewerNotes": []
        },
        "handoffReview": {
          "started": "2026-01-30T01:45:00Z",
          "completed": "2026-01-30T01:50:00Z",
          "approved": true,
          "reviewerNotes": []
        }
      }
    }
  }
}
```

## Stage Descriptions

| Stage | Purpose | Reviewer |
|-------|---------|----------|
| architecture | High-level structure, components, decisions, risks | None (validated in designReview) |
| interface | Precise contracts between components | None (validated in designReview) |
| designReview | Challenge assumptions, find gaps, ensure robustness | design-reviewer (skeptic) |
| handoffReview | Ensure plan phase has everything it needs | phase-reviewer (gatekeeper) |

## Stage Object Fields

**architecture / interface:**
| Field | Type | Description |
|-------|------|-------------|
| started | ISO8601 | When stage began |
| completed | ISO8601/null | When stage completed |

**designReview:**
| Field | Type | Description |
|-------|------|-------------|
| started | ISO8601 | When stage began |
| completed | ISO8601/null | When stage completed |
| iterations | number | Review iterations (1-3 based on mode) |
| reviewerNotes | array | Unresolved concerns from design-reviewer |

**handoffReview:**
| Field | Type | Description |
|-------|------|-------------|
| started | ISO8601 | When stage began |
| completed | ISO8601/null | When stage completed |
| approved | boolean | Whether phase-reviewer approved |
| reviewerNotes | array | Concerns noted by phase-reviewer |

## Recovery from Partial Design Phase

When recovering from interrupted design phase, detect the incomplete stage:

1. Check which stages have `started` but not `completed`
2. The first incomplete stage is the current stage
3. Offer user options: Continue from current stage, Start fresh, or Review first
