---
last-updated: 2026-04-29T00:00:00Z
source-feature: 078-cc-native-integration
audit-feature: 098-tier-doc-frontmatter-sweep
---

<!-- AUTO-GENERATED: START - source: 078-cc-native-integration -->
# Usage

## Quick Start

The easiest entry point is `/pd:secretary`. Describe what you want to do and it routes to the right workflow automatically:

```bash
/pd:secretary "add email validation to the signup form"
```

Or start a phase directly:

```bash
/pd:brainstorm "your idea here"    # Explore an idea, produce a PRD
/pd:create-feature "add user auth" # Skip brainstorming, start a feature directly
```

## The Feature Workflow

Features move through phases in sequence. After creating a feature, advance phase by phase:

```bash
/pd:specify        # Write requirements (spec.md)
/pd:design         # Define architecture (design.md)
/pd:create-plan    # Plan implementation (plan.md + tasks.md)
/pd:implement      # Write code with TDD
/pd:finish-feature # Merge, retrospective, branch cleanup
```

Each phase runs a reviewer before closing. If the reviewer finds issues, it sends the feature back with referral notes.

**`/pd:implement` — parallel task execution:** Tasks are dispatched in parallel using git worktrees (created under `.pd-worktrees/`, gitignored). If worktree creation fails for a specific task, that task runs without isolation. If SQLite contention is detected, remaining tasks fall back to serial execution. Merge conflicts halt the process and surface details for manual resolution.

**`/pd:finish-feature` — security review:** After pre-merge checks pass, pd runs `/security-review` if the command is available in `.claude/commands/`. Critical or high-severity findings block the merge. If the command is not installed, this step is skipped with a warning.

### Phase Context on Rework

When a reviewer sends a feature backward, pd automatically injects a `## Phase Context` block at the start of the re-entered phase. This block contains:

- **Reviewer Referral** — the specific issues flagged by the reviewer that triggered rework
- **Prior Phase Summaries** — key decisions, artifacts produced, and reviewer notes from earlier passes through each phase (up to the 2 most recent per phase)

This means re-entering a phase is never a blank slate. Prior decisions are visible so you don't re-litigate resolved issues.

Example of what gets injected:

```markdown
## Phase Context
### Reviewer Referral
**Source phase:** design
- [spec.md > AC-3] Gap in acceptance criteria — add edge case for empty input

### Prior Phase Summaries
**specify** (2026-04-02T08:00:00Z): Specification complete (3 iterations).
  Key decisions: Chose append-list storage over keyed dict for rework history.
  Artifacts: spec.md
```

## Common Workflows

### Explore Before Building

```bash
/pd:brainstorm "topic or problem"
# Review the PRD produced, then:
/pd:create-feature "feature description"
```

### Build Directly

```bash
/pd:create-feature "add user auth"
/pd:specify
/pd:design
/pd:create-plan
/pd:implement
/pd:finish-feature
```

### Check Progress

```bash
/pd:show-status      # Current phase and feature state
/pd:list-features    # All active features and branches
```

### Capture a Learning

```bash
/pd:remember "always validate empty inputs before processing"
```

### Promote a Pattern to an Enforceable Rule

Once a knowledge-bank entry accumulates enough observations (default threshold: 3), `/pd:promote-pattern` converts it into a hook, skill, agent, or command so the rule is enforced automatically on the next session:

```bash
/pd:promote-pattern                    # Interactive — lists qualifying entries
/pd:promote-pattern "relative paths"   # Filter to entries matching the substring
```

The command dispatches the `promoting-patterns` skill, which orchestrates an enumerate → classify → generate-diff → approve → atomic-apply flow. Classification uses deterministic keyword scoring with an LLM fallback when keywords tie or miss; the user can always override the target. CLAUDE.md is never offered as a target. On apply, writes are atomic with rollback on any validation failure, and the KB entry gains a `- Promoted: ...` line so re-runs skip it.

Configure the qualifying threshold via `memory_promote_min_observations` in `.claude/pd.local.md` (default: `3`).

## Autonomous Mode (YOLO)

To run the workflow without manual confirmation at each phase gate:

```bash
/pd:yolo on                                    # Enable YOLO mode
/pd:secretary orchestrate "add user auth"      # Build end-to-end
/pd:secretary continue                         # Resume from last phase
/pd:yolo off                                   # Return to manual mode
```

Quality reviewers still run in YOLO mode. Autonomous operation pauses automatically on review failures, merge conflicts, or missing prerequisites.

## Project-Level Work

For larger initiatives with multiple features:

```bash
/pd:create-project "prd description"   # AI decomposes PRD into features
```

## Utilities

| Command | What it does |
|---------|-------------|
| `/pd:add-to-backlog <idea>` | Capture an idea without starting a feature |
| `/pd:retrospect` | Run a retrospective on a completed feature |
| `/pd:promote-pattern [<substring>]` | Promote a high-confidence KB entry to an enforceable hook, skill, agent, or command |
| `/pd:show-lineage` | Display entity relationships for the current feature |
| `/pd:doctor` | Check workspace health |
| `/pd:cleanup-brainstorms` | Delete old brainstorm scratch files |

## File Layout

pd creates files under your project's `docs/` directory (configurable via `artifacts_root`):

```
docs/
├── brainstorms/           # Brainstorm PRDs
├── features/{id}-{name}/  # Feature artifacts
│   ├── spec.md
│   ├── design.md
│   ├── plan.md
│   ├── tasks.md
│   └── .meta.json         # Phase state and summaries
├── projects/{id}-{name}/  # Project PRDs and roadmaps
├── retrospectives/        # Retrospective outputs
└── knowledge-bank/        # Accumulated learnings
```

The `.meta.json` file tracks phase state and stores accumulated phase summaries. These summaries are what pd injects as context when a phase is re-entered during rework.
<!-- AUTO-GENERATED: END -->
