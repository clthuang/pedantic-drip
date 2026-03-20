# PRD: Fractal Work Management for Agent-Native Development

**Date:** 2026-03-20
**Status:** Draft (research complete, not yet promoted)
**Source:** Deep research session analyzing three pillars of organizational engineering for AI-agent-centered development.

---

## Problem Statement

The pd plugin operates at a single level — tactical feature development. But software organizations need management at three levels simultaneously:

1. **Strategic** (months): What to build and why — initiatives, projects, roadmaps
2. **Tactical** (weeks): How to build a specific capability — features with quality gates
3. **Operational** (hours-days): Execute specific tasks — implementation, testing, review

pd excels at level 2 but has no lifecycle at levels 1 or 3. The result:
- Strategic work (project decomposition) is write-once — roadmaps, milestones, and dependencies are never maintained after creation
- Operational work (tasks.md) is a flat checklist — no lifecycle, no quality gates, no dependency tracking
- Cross-level feedback doesn't flow — operational learnings don't trigger strategic reassessment

## Core Insight: Fractal Self-Similarity

Every successful multi-level framework uses the same lifecycle at every level:
- **Military**: MDMP at strategic, operational, and tactical echelons — structurally identical planning cycles at different scopes
- **SAFe**: PI Planning is the same ceremony at Team, ART, Solution, and Portfolio levels
- **Sociocracy 3.0**: Same governance pattern at every nested circle level
- **OKRs**: A Key Result at level N becomes an Objective at level N+1

The lifecycle is structurally identical. Only scope, cadence, and gate stringency change.

## Proposed Universal Lifecycle: 5D

```
DISCOVER → DEFINE → DESIGN → DELIVER → DEBRIEF
```

| Phase | Strategic | Tactical | Operational |
|-------|-----------|----------|-------------|
| **Discover** | Market research, user interviews, competitive analysis | Brainstorm, PRD, evidence gathering | Read context, understand task |
| **Define** | Shape the bet, scope boundaries, success criteria | Specify, acceptance criteria | Task definition, done-when criteria |
| **Design** | Architecture, system design, decomposition into tactical items | Component design, interfaces, decomposition into operational tasks | Implementation approach |
| **Deliver** | Execute via tactical work items | Implement via operational tasks | Write code, run tests |
| **Debrief** | Strategy review, project retrospective | Feature retro, knowledge bank | Code review, lessons learned |

pd's current 7-phase sequence maps to 5D at the tactical level:
- `brainstorm` → Discover
- `specify` → Define
- `design` + `create-plan` + `create-tasks` → Design (with decomposition)
- `implement` → Deliver
- `finish` (retro) → Debrief

## Proposed Data Model: Universal Work Item

```
Work Item:
  level: strategic | tactical | operational
  lifecycle: 5D phases with level-appropriate gates
  parent: reference to parent work item (or null)
  children: list of child work items (created during Design phase)
  dependencies: sibling work items this is blocked by
  status: active | blocked | completed | abandoned
  artifacts: level-appropriate documents
```

**Decomposition as a lifecycle phase:** "Design" at level N produces child work items at level N+1. This is not a separate "decomposition" step — it's what design means at higher levels.

**Kanban per level:** Each level tracks its own work-in-progress. Strategic kanban tracks initiatives. Tactical kanban tracks features. Operational kanban tracks tasks.

**Gate stringency by level:**
- Strategic: heavy human review, written narratives (Amazon 6-pager pattern)
- Tactical: AI review with human approval gates (pd's current model)
- Operational: AI-autonomous with automated verification

**Dependency enforcement by level:** Gate checks at the Deliver phase verify prerequisite work items are complete before allowing entry.

**Feedback propagation:** Debrief at level N triggers re-evaluation of assumptions at level N-1. Operational anomalies surface tactical/strategic assumption failures (double-loop learning).

## Terminology

| Old Term | New Term | Why |
|----------|----------|-----|
| Project | Strategic Work Item | "Project" overloaded; level makes scope explicit |
| Feature | Tactical Work Item | "Feature" overloaded; avoids confusion with product features |
| Task (tasks.md) | Operational Work Item | Elevated from checklist item to first-class lifecycle entity |
| Phase | Lifecycle Phase | Same 5D phases at every level |
| Kanban column | Work State | Per-level flow tracking, not a single board |

Or simply: **"Work Item"** at every level, distinguished by `level` attribute. This is the Azure DevOps / Jira convention — generic but clear.

## What Changes for pd

1. **pd's phase-gated workflow becomes the template** — applied at every level with level-appropriate gates
2. **Decomposition becomes part of Design** — not a separate skill, but what Design means at higher levels
3. **tasks.md entries become first-class work items** — with their own mini-lifecycle (discover→define→design→deliver→debrief), not just checkboxes
4. **Dependencies are enforced at Deliver gates** — not just stored and ignored
5. **Debrief propagates up** — retrospective findings flow to parent work item's Discover phase

## Relationship to Feature 050

Feature 050 (Reactive Entity Consistency Engine) attempted to solve 12 gaps by adding breadth capabilities to pd's core. This analysis reveals those gaps split into:

**Depth bugs (fix now, no architectural change):**
- Gap 2: Field validation in `init_feature_state()` — add ValueError for empty identity fields
- Gap 5: Permanent frontmatter unhealthy — remove dead check from `reconcile_status`
- Gap 7: Guard blocks maintenance — add `PD_MAINTENANCE=1` bypass
- Gap 8: Three competing "done" signals — implement `derive_kanban()` consolidation
- Gap 11: Artifact completeness — add soft verification warnings on finish
- Gap 12: Silent reconciliation — surface session-start summary

**Breadth concerns (addressed by fractal model, not by patching pd):**
- Gaps 1, 3, 4, 6, 9, 10 — workspace isolation, cascading, ghost entities, workflow templates, memory scoping

## Research Sources

### Organizational Models
- [Linear Conceptual Model](https://linear.app/docs/conceptual-model) — Initiative → Project → Issue hierarchy
- [Shape Up](https://basecamp.com/shapeup/1.1-chapter-02) — Shaping as strategic deep work
- [Amazon Working Backwards](https://workingbackwards.com/concepts/working-backwards-pr-faq-process/) — PR/FAQ as strategic artifact
- [Shopify GSD](https://www.lennysnewsletter.com/p/how-shopify-builds-product) — Gate reviews as layer boundaries
- [Hoshin Kanri](https://www.6sigma.us/process-improvement/essential-guide-to-hoshin-kanri/) — Three-layer planning with bidirectional catchball
- [Sociocracy 3.0 Fractal Organization](https://patterns.sociocracy30.org/fractal-organization.html) — Same governance at every level
- [Holacracy](https://www.holacracy.org/how-it-works/organizational-structure/) — Nested circles with double-linking

### Fractal/Recursive Patterns
- [Military MDMP](https://garmonttactical.com/post/military-decision-making-process-mdmp-7-steps-from-intel-to-action.html) — Same planning cycle at every echelon
- [SAFe Hierarchy](https://www.enov8.com/blog/the-hierarchy-of-safe-scaled-agile-framework-explained/) — PI Planning at every level
- [OODA Loop](https://en.wikipedia.org/wiki/OODA_loop) — Recursive, not sequential
- [Double Diamond](https://www.designcouncil.org.uk/our-resources/the-double-diamond/) — Inherently recursive design process
- [OKR Hierarchy](https://techdocs.broadcom.com/us/en/ca-enterprise-software/valueops/rally/rally-help/planning/objectives-and-key-results-okrs/create-an-okr-hierarchy-in-rally/examples-of-okr-hierarchies.html) — Key Result becomes Objective at next level

### Agent/Harness Engineering
- [Anthropic: Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) — Orchestrator-worker pattern
- [Anthropic: Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — Dual-agent architecture, artifact-first state
- [Martin Fowler: Humans and Agents](https://martinfowler.com/articles/exploring-gen-ai/humans-and-agents.html) — Humans on the loop, agentic flywheel
- [Gene Kim: Three Developer Loops](https://itrevolution.com/articles/the-three-developer-loops-a-new-framework-for-ai-assisted-coding/) — Inner/Middle/Outer loop framework
- [Two Agentic Loops](https://planoai.dev/blog/the-two-agentic-loops-how-to-design-and-scale-agentic-apps) — Goal-directed systems cannot constrain themselves
- [Harness Engineering Guide](https://www.nxcode.io/resources/news/harness-engineering-complete-guide-ai-agent-codex-2026) — Context + Constraints + Entropy management
- [Addy Osmani: Agentic Engineering](https://addyosmani.com/blog/agentic-engineering/) — Engineers as composers orchestrating agent ensembles
- [Devin Performance Review 2025](https://cognition.ai/blog/devin-annual-performance-review-2025) — Bounded tasks with clear specs, parallelization

### Codebase Analysis (pd current state)
- kanban_column: 8 possible values, 5 ever used, 3 dead columns (agent_review, human_review, blocked)
- Two competing kanban derivation strategies (STATUS_TO_KANBAN vs FEATURE_PHASE_TO_KANBAN) producing contradictory values
- depends_on_features: stored but only consumed by YOLO stop hook — transition gates unaware
- Project milestones, roadmap.md: write-once at decomposition, never read back
- Phase-gated workflow (43 transition guards): load-bearing — everything else is peripheral
