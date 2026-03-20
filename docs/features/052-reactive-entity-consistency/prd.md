# PRD: Fractal Organisational Management for Agent-Native Development

**Date:** 2026-03-20
**Status:** Draft
**Source:** Deep research session + organisational management requirements analysis
**Supersedes:** Original fractal-work-management brainstorm (vision/research only)

---

## Problem Statement

pd is a tactical feature development engine. It excels at guiding one feature through brainstorm-to-finish with AI-reviewed quality gates. But real organisations operate at multiple levels simultaneously, and pd has no presence above or below the feature level:

### Level 1: Executive/Strategic (C-Suite) — Currently Absent
- **Vision & mission alignment** — no way to capture or reference strategic direction
- **Initiative portfolio** — no concept of initiatives that span multiple projects
- **OKR cascading** — no objectives/key-results framework at any level
- **Strategic planning horizons** — no quarterly/annual planning cycles
- **Investment decisions** — no way to evaluate competing bets or track resource allocation

### Level 2: Management/Program (Directors, Managers) — Partially Present
- **Roadmapping** — `roadmap.md` exists but is write-once, never maintained
- **OKR ownership** — no mechanism to own and track key results
- **Cross-project coordination** — projects exist but don't interact
- **Milestone tracking** — milestones are stored in `.meta.json` but never checked or updated
- **Dependency management** — `depends_on_features` stored but only consumed by YOLO stop hook; transition gates unaware
- **Risk management** — no risk tracking or escalation

### Level 3: Tactical/Operational (Engineers, ICs) — Well-Served
- Feature lifecycle: brainstorm → specify → design → plan → tasks → implement → finish
- 43 transition guards, AI-reviewed quality gates, knowledge bank, retrospectives
- **Gap:** tasks.md is a flat checklist — no lifecycle, no quality gates, no dependency tracking between tasks

### The Cost of Single-Level Thinking
- Strategic decisions are made outside pd, context is lost
- Projects decompose into features but never track progress against milestones
- Operational learnings (retros) don't propagate to strategic reassessment
- No way to answer: "Are we on track for Q2 objectives?" or "Which initiatives are blocked?"

---

## Core Insight: Fractal Self-Similarity

Every successful multi-level management framework uses the **same lifecycle at every level** — only scope, cadence, and gate stringency change:

- **Military MDMP**: identical planning cycle at strategic, operational, and tactical echelons
- **SAFe**: PI Planning is the same ceremony at Team, ART, Solution, and Portfolio levels
- **OKRs**: a Key Result at level N becomes an Objective at level N+1
- **Hoshin Kanri**: three-layer planning with bidirectional catchball (strategy ↔ tactics ↔ operations)

pd already has the lifecycle engine. The insight is: **don't build three different systems — apply the same engine at every level with level-appropriate configuration.**

---

## Solution: Universal Lifecycle Engine

### The 5D Lifecycle

```
DISCOVER → DEFINE → DESIGN → DELIVER → DEBRIEF
```

pd's current 7-phase sequence maps to 5D at the tactical level:
- `brainstorm` → **Discover**
- `specify` → **Define**
- `design` + `create-plan` + `create-tasks` → **Design** (with decomposition)
- `implement` → **Deliver**
- `finish` (retro) → **Debrief**

The same 5D lifecycle applies at every organisational level:

| Phase | Executive/Strategic | Management/Program | Tactical/Operational |
|-------|--------------------|--------------------|---------------------|
| **Discover** | Market research, competitive analysis, stakeholder interviews, vision setting | User research, feasibility studies, opportunity sizing | Brainstorm, PRD, evidence gathering |
| **Define** | OKRs, strategic bets, investment thesis, success criteria | Roadmap, milestones, resource plan, risk register | Spec, acceptance criteria |
| **Design** | Portfolio architecture, initiative decomposition into programs/projects | Project decomposition into features, dependency graphs, milestone sequencing | Component design, interfaces, task breakdown |
| **Deliver** | Execute via programs/projects, track portfolio health | Execute via features, track milestone progress, manage dependencies | Implement via tasks, write code, run tests |
| **Debrief** | Strategy review, portfolio retrospective, OKR scoring | Project retrospective, milestone review, roadmap adjustment | Feature retro, knowledge bank, code review |

### Organisational Levels

| Level | Typical Roles | Cadence | Work Items | Current pd Support |
|-------|--------------|---------|------------|-------------------|
| **L1: Strategic** | CEO, CTO, VP, Founders | Quarterly/Annual | Initiatives, OKRs | None |
| **L2: Program** | Directors, Engineering Managers, Product Managers | Monthly/Quarterly | Projects, Epics, Milestones | Partial (projects exist but write-once) |
| **L3: Tactical** | Senior Engineers, Tech Leads | Weekly/Biweekly | Features | Well-served |
| **L4: Operational** | Engineers, ICs | Daily/Hourly | Tasks, Subtasks | Flat checklist (tasks.md) |

### Gate Stringency by Level

| Level | Review Model | Gate Rigour | Autonomy |
|-------|-------------|-------------|----------|
| **L1: Strategic** | Human-only review, written narratives (Amazon 6-pager pattern) | Highest — every transition requires explicit human approval | Human-driven, AI assists with research and analysis |
| **L2: Program** | Human review with AI-prepared summaries, risk flags | High — AI prepares but human decides | Human-driven, AI does heavy lifting on decomposition and tracking |
| **L3: Tactical** | AI review with human approval gates (pd's current model) | Medium — AI reviews, human approves at key gates | AI-driven with human oversight |
| **L4: Operational** | AI-autonomous with automated verification | Lowest — test pass = done | AI-autonomous |

---

## Data Model: Universal Work Item

### Entity Hierarchy

```
Initiative (L1)
  └── Objective (L1)
        └── Key Result (L1/L2 bridge)
              └── Project (L2)
                    └── Feature (L3)
                          └── Task (L4)
```

Each node is a **Work Item** — same schema, same lifecycle engine, different `level` and `type`:

```
Work Item:
  id: unique identifier
  type: initiative | objective | key_result | project | feature | task
  level: L1 | L2 | L3 | L4
  lifecycle_phase: discover | define | design | deliver | debrief
  status: draft | planned | active | blocked | completed | abandoned
  parent: reference to parent work item
  children: derived from parent references
  blocked_by: list of sibling work items this depends on
  owner: person or team responsible
  cadence: planning cycle this belongs to (Q1-2026, H1-2026, Sprint-42, etc.)
  artifacts: level-appropriate documents
  metadata: flexible JSON for level-specific fields
```

### What's New vs What Exists

| Concept | Current State | New State |
|---------|--------------|-----------|
| Entity types | 4 fixed: backlog, brainstorm, project, feature | Extended: + initiative, objective, key_result, task |
| Lifecycle | 7 phases, tactical only | 5D phases at every level via workflow templates |
| Lineage | parent_type_id (single parent) | Same mechanism, deeper hierarchy (L1→L2→L3→L4) |
| Milestones | Array in project .meta.json, never updated | First-class work items with own lifecycle |
| OKRs | Non-existent | Objective + Key Result entity types with scoring |
| Tasks | Flat markdown checklist | L4 work items with mini-lifecycle |
| Dependencies | Stored, mostly ignored | Enforced at Deliver gates |
| Kanban | Single board, 8 columns (3 unused) | Per-level boards, derived from (status, phase) |

### Level-Specific Artifacts

| Level | Discover | Define | Design | Deliver | Debrief |
|-------|----------|--------|--------|---------|---------|
| **L1** | Vision doc, market analysis, competitive landscape | OKR sheet, strategic bet thesis, investment memo | Initiative portfolio, program decomposition | Portfolio dashboard, OKR tracking | Strategy review, OKR scoring |
| **L2** | Feasibility study, user research, PRD | Roadmap, milestone plan, risk register, resource plan | Feature decomposition, dependency graph, architecture decisions | Milestone tracking, burndown, dependency status | Project retro, milestone review |
| **L3** | Brainstorm PRD | spec.md | design.md, plan.md, tasks.md | implementation-log.md | retro.md |
| **L4** | Context read | Task definition (from tasks.md) | Implementation approach | Code + tests | Review feedback |

### OKR Integration

OKRs are the **bridge between strategic intent and tactical execution**:

```
Initiative: "Become the leading AI development platform"
  └── Objective: "Ship enterprise-grade reliability" (Q2-2026)
        ├── KR1: "Reduce P0 incidents to <2/month" → measured, scored 0.0-1.0
        │     └── Project: "Observability overhaul"
        │           ├── Feature: "Structured logging"
        │           └── Feature: "Alert pipeline"
        ├── KR2: "99.9% API uptime" → measured, scored 0.0-1.0
        │     └── Project: "HA infrastructure"
        └── KR3: "All critical paths have integration tests" → measured, scored 0.0-1.0
              └── Project: "Test coverage initiative"
```

**OKR lifecycle:**
- **Discover:** Research what matters, gather evidence
- **Define:** Set measurable KRs with baselines and targets
- **Design:** Decompose KRs into projects/features
- **Deliver:** Track KR progress as children complete
- **Debrief:** Score KRs (0.0-1.0), assess objective health, feed into next cycle

**Key Result scoring** is computed from child work item completion:
- Percentage-based KRs: derived from completed children / total children
- Metric-based KRs: manually updated or pulled from external data
- Binary KRs: completed when all children complete

### Cross-Level Feedback Loops

**Upward propagation (Debrief → parent's Discover):**
- L4 task retro surfaces issues → L3 feature retro aggregates → L2 project retro identifies systemic patterns → L1 strategy review reassesses assumptions
- Operational anomalies trigger re-evaluation of parent assumptions (double-loop learning)

**Downward propagation (Define → children's constraints):**
- L1 OKR targets constrain L2 project scope
- L2 milestones constrain L3 feature deadlines
- L3 design decisions constrain L4 task implementation

**Lateral propagation (sibling dependencies):**
- Feature A completes → Feature B unblocked (cascade unblock)
- KR1 at risk → flag to Objective owner for rebalancing

---

## What Changes for pd

### Phase 1: Foundation — Depth Fixes + Entity Model Extension

Fix the 6 depth bugs identified in feature 050 analysis (no architectural change needed):
1. **Field validation** — `init_feature_state()` rejects empty identity fields
2. **Frontmatter health** — remove dead `reconcile_status` frontmatter check
3. **Maintenance mode** — add `PD_MAINTENANCE=1` bypass to meta-json-guard
4. **Kanban derivation** — implement `derive_kanban()`, replace all independent kanban sets
5. **Artifact completeness** — soft verification warnings on feature finish
6. **Reconciliation reporting** — surface session-start reconciliation summary

Extend entity type CHECK constraint: add `initiative`, `objective`, `key_result`, `task`.

### Phase 2: Workflow Templates + Operational Level (L4)

**Workflow templates** replace the single hardcoded phase sequence:

```python
WORKFLOW_TEMPLATES = {
    # L1: Strategic
    "initiative": ["discover", "define", "design", "deliver", "debrief"],
    "objective":  ["discover", "define", "design", "deliver", "debrief"],
    "key_result": ["define", "deliver", "debrief"],
    # L2: Program
    "project":    ["discover", "define", "design", "deliver", "debrief"],
    # L3: Tactical (backward compatible with existing 7 phases)
    "standard":   ["brainstorm", "specify", "design", "create-plan", "create-tasks", "implement", "finish"],
    "full":       ["brainstorm", "specify", "design", "create-plan", "create-tasks", "implement", "finish"],
    "bugfix":     ["specify", "create-tasks", "implement", "finish"],
    "hotfix":     ["implement", "finish"],
    # L4: Operational
    "task":       ["define", "deliver", "debrief"],
}
```

**L4 tasks become work items:**
- Each task in tasks.md gets registered as an entity with `type=task`, `parent=feature:{id}`
- Mini-lifecycle: define (task spec) → deliver (implement) → debrief (review)
- AI-autonomous execution with automated verification (test pass = done)

### Phase 3: Program Level (L2) — Project Lifecycle

Make projects living entities instead of write-once containers:
- Projects get their own 5D lifecycle (currently they're created and forgotten)
- Milestones become checkpoints within the project lifecycle, not just metadata
- Roadmap.md is regenerated when project state changes
- Dependency enforcement: feature can't enter Deliver if its `blocked_by` siblings aren't complete
- Project dashboard: progress against milestones, feature status rollup, risk flags

### Phase 4: Strategic Level (L1) — Initiatives & OKRs

Add the executive layer:
- **Initiatives** — top-level strategic bets with 5D lifecycle
- **Objectives** — what we want to achieve this cycle, decompose into Key Results
- **Key Results** — measurable outcomes, scored 0.0-1.0, decompose into projects/features
- OKR cadence management (quarterly by default)
- Portfolio dashboard: initiative health, OKR progress, cross-project dependencies
- Strategic advisors: reuse existing advisory framework (pre-mortem, opportunity-cost, working-backwards) at L1

### Phase 5: Cross-Level Intelligence

- **Cascade unblock** — completing a work item at any level unblocks dependents
- **Progress rollup** — parent work item health derived from children status
- **Anomaly propagation** — debrief findings at level N surface to level N-1
- **Workspace scoping** — workspace_id column for multi-project isolation
- **Context-aware secretary** — secretary routes requests to appropriate level based on scope

---

## What Does NOT Change

- **L3 tactical workflow** — the existing 7-phase feature lifecycle is preserved exactly as-is (it maps to 5D but the phase names and gates remain). No breaking changes to existing features.
- **Entity lineage model** — same parent_type_id mechanism, just deeper hierarchy
- **Agent/reviewer architecture** — same dispatch pattern, extended with level-appropriate reviewers
- **Knowledge bank** — same structure, extended with level tags
- **Plugin portability** — no hardcoded paths, same two-location glob pattern

---

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Scope creep — trying to build Jira | High | High | Each phase is independently valuable. Phase 1 is pure bugfixes. Phase 2 adds templates. Ship incrementally. |
| L1/L2 levels unused — solo developer doesn't need executive layer | Medium | Low | L1/L2 are opt-in. Solo developers continue using L3/L4 only. No overhead if unused. |
| Schema migration breaks existing features | Medium | High | Entity type extension is additive (new CHECK values). L3 workflow templates are backward-compatible. |
| OKR scoring is noisy without real metrics integration | Medium | Medium | Start with manual scoring + child-completion rollup. External metrics integration is a future phase. |
| Task-level lifecycle adds friction to simple tasks | Medium | Medium | L4 lifecycle is opt-in. Simple tasks stay as markdown checkboxes. Only promoted tasks get full lifecycle. |

---

## Success Metrics

1. **L3 preserved:** All existing 710+ entity registry, 309 workflow engine, 118 reconciliation tests pass unchanged
2. **L4 operational:** Tasks from tasks.md can be registered as entities with parent lineage to their feature
3. **L2 living projects:** Project milestones can be marked complete, roadmap regenerated, feature progress tracked
4. **L1 OKRs:** Objectives and Key Results can be created, scored, and linked to projects
5. **Cross-level:** Completing a feature updates its parent project's progress. Completing a project updates its parent KR's score.
6. **Backward compatible:** A developer who ignores L1/L2/L4 sees zero change in their L3 workflow

---

## Research Sources

### Organisational Models
- [Linear Conceptual Model](https://linear.app/docs/conceptual-model) — Initiative → Project → Issue hierarchy
- [Shape Up](https://basecamp.com/shapeup/1.1-chapter-02) — Shaping as strategic deep work
- [Amazon Working Backwards](https://workingbackwards.com/concepts/working-backwards-pr-faq-process/) — PR/FAQ as strategic artifact
- [Shopify GSD](https://www.lennysnewsletter.com/p/how-shopify-builds-product) — Gate reviews as layer boundaries
- [Hoshin Kanri](https://www.6sigma.us/process-improvement/essential-guide-to-hoshin-kanri/) — Three-layer planning with bidirectional catchball
- [Sociocracy 3.0](https://patterns.sociocracy30.org/fractal-organization.html) — Same governance at every level

### Fractal/Recursive Patterns
- [Military MDMP](https://garmonttactical.com/post/military-decision-making-process-mdmp-7-steps-from-intel-to-action.html) — Same planning cycle at every echelon
- [SAFe Hierarchy](https://www.enov8.com/blog/the-hierarchy-of-safe-scaled-agile-framework-explained/) — PI Planning at every level
- [OKR Hierarchy](https://techdocs.broadcom.com/us/en/ca-enterprise-software/valueops/rally/rally-help/planning/objectives-and-key-results-okrs/create-an-okr-hierarchy-in-rally/examples-of-okr-hierarchies.html) — Key Result becomes Objective at next level
- [Double Diamond](https://www.designcouncil.org.uk/our-resources/the-double-diamond/) — Inherently recursive design process

### Agent/Harness Engineering
- [Anthropic: Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — Dual-agent architecture, artifact-first state
- [Addy Osmani: Agentic Engineering](https://addyosmani.com/blog/agentic-engineering/) — Engineers as composers orchestrating agent ensembles
- [Gene Kim: Three Developer Loops](https://itrevolution.com/articles/the-three-developer-loops-a-new-framework-for-ai-assisted-coding/) — Inner/Middle/Outer loop framework

### Codebase Analysis (pd current state)
- 4 entity types, 28 skills, 28 agents, 29 commands
- 43 transition guards, 7-phase sequence (standard/full modes only)
- kanban: 8 columns defined, 3 unused (agent_review, human_review, blocked)
- Two competing kanban derivations (STATUS_TO_KANBAN vs FEATURE_PHASE_TO_KANBAN)
- depends_on_features: stored but only consumed by YOLO stop hook
- Project milestones: write-once at decomposition, never read back
- OKR support: non-existent
- Task lifecycle: non-existent (flat markdown checklist)
