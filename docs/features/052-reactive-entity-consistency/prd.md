# PRD: pd as Fractal Organisational Management Hub

**Date:** 2026-03-20
**Status:** Draft
**Source:** Deep research across 60+ sources on organisational management, OKR frameworks, cross-level coordination, and AI-native development patterns.

---

## Problem Statement

pd is a tactical feature development engine. It excels at guiding one feature through brainstorm-to-finish with AI-reviewed quality gates. But organisations operate at multiple levels simultaneously, and pd has no presence above or below the feature level.

### What's Missing

**Executive/Strategic layer:** No way to capture vision, set OKRs, manage initiative portfolios, or make strategic bets. C-suite decisions happen outside pd — context is lost, intent never reaches execution.

**Program/Management layer:** Projects exist but are write-once containers. Roadmaps, milestones, and dependencies are stored at decomposition time and never maintained. No risk tracking, no milestone progress, no cross-project coordination. 67% of strategies fail not because strategy was wrong but because daily behaviours don't align with strategic intent (Kaplan-Norton/HBR).

**Operational layer:** tasks.md is a flat checklist. No lifecycle, no quality gates, no dependency tracking between tasks. In the AI-native era, tasks are the unit that agents execute — they deserve first-class treatment.

**Cross-level coordination:** No mechanism for strategic intent to flow down to execution or for operational learnings to flow back up. This is the hardest problem in organisational management, and pd doesn't even attempt it.

---

## Core Insight: Fractal Self-Similarity

Every successful multi-level management framework uses the **same lifecycle at every level** — only scope, cadence, and gate stringency change:

- **Military Mission Command (Auftragstaktik):** Same planning cycle at strategic, operational, and tactical echelons. Give objective + resources, not how-to. (von Moltke/Clausewitz)
- **Hoshin Kanri:** Three-layer planning with bidirectional "catchball" — not top-down cascade but iterative alignment where each level refines and adjusts. (Toyota)
- **OKRs:** A Key Result at level N becomes an Objective at level N+1. Same structure, different scope. (Intel/Google)
- **Sociocracy 3.0:** Same governance pattern at every nested circle level, repeating fractally.
- **SAFe:** PI Planning is the same ceremony at Team, ART, Solution, and Portfolio levels.

pd already has the lifecycle engine, entity registry, AI-reviewed quality gates, and knowledge bank. **Don't build four different systems — apply the same engine at every level with level-appropriate configuration.**

---

## Solution: The 5D Fractal Lifecycle

### Universal Lifecycle

Every work item at every organisational level follows the same five phases:

```
DISCOVER → DEFINE → DESIGN → DELIVER → DEBRIEF
```

pd's existing 7-phase tactical sequence maps naturally:
- `brainstorm` → **Discover** (research, evidence gathering, problem framing)
- `specify` → **Define** (scope, success criteria, acceptance criteria)
- `design` + `create-plan` + `create-tasks` → **Design** (architecture, decomposition into children)
- `implement` → **Deliver** (execute, track, manage dependencies)
- `finish` (retro) → **Debrief** (review outcomes, capture learnings, propagate feedback)

### Four Organisational Levels

| Level | Who | Cadence | Work Items | pd Today |
|-------|-----|---------|-----------|----------|
| **L1: Strategic** | CEO, CTO, VP, Founders | Quarterly / Annual | Initiatives, Objectives, Key Results | None |
| **L2: Program** | Directors, EMs, PMs | Monthly / 6-week cycles | Projects, Milestones | Partial (write-once) |
| **L3: Tactical** | Senior Engineers, Tech Leads | Weekly / Biweekly | Features | Well-served |
| **L4: Operational** | Engineers, ICs, AI Agents | Daily / Hourly | Tasks | Flat checklist |

### What Each Level Actually Does (Research-Grounded)

#### L1: Strategic — "What to build and why"

**Real-world patterns (Amazon, Google, Stripe, Netflix, Basecamp):**
- **Amazon:** Written 6-page narratives for strategy reviews, PR/FAQ documents for new initiatives (mock press release + 5 pages of FAQs, written from customer perspective). PowerPoint banned. Meetings start with 20-25 minutes of silent reading.
- **Google:** OKRs with committed vs aspirational distinction. Committed must score 1.0; aspirational target 0.6-0.7. 3-5 objectives, ~3 KRs each.
- **Stripe:** Foundational documents (values, operating principles, long-term goals), quarterly goals, weekly metrics reviews. Claire Hughes Johnson's "stable, consistent foundation of practices."
- **Netflix:** "Highly aligned, loosely coupled." Leadership provides context (strategy, metrics, assumptions), not control (approvals, committees). Every decision has an "informed captain."
- **Basecamp:** "Betting table" picks shaped pitches each 6-week cycle. No backlog — unshaped ideas that aren't bet on are discarded.
- **David Sacks:** CEO Dashboard uses "3x5 rule" — 5 headline numbers + 3 charts. Red metrics for 2 consecutive weeks trigger root-cause analysis. Maximum 3 objectives per team with 3 KRs each.

**Decision framework:** Bezos Type 1/Type 2 — irreversible decisions (one-way doors) require slow deliberation; reversible decisions (two-way doors) should be made fast with ~70% information. Most decisions are Type 2 but organisations mistakenly treat them as Type 1.

**Cadence:** Annual strategic direction → quarterly OKR setting → monthly business reviews → weekly metrics check-ins.

**Artifacts:**
| Phase | Artifact | Purpose |
|-------|----------|---------|
| Discover | Vision document, market analysis, competitive landscape | Frame the strategic context |
| Define | OKR sheet (objectives + measurable key results), strategic bet thesis | Set measurable direction |
| Design | Initiative portfolio, program decomposition | Break strategy into executable programs |
| Deliver | Portfolio dashboard, OKR progress tracking | Track health across programs |
| Debrief | Strategy review, OKR scoring (0.0-1.0) | Score outcomes, feed next cycle |

**Gate model:** Human-only review. AI assists with research, analysis, and document preparation — but humans make every strategic decision.

#### L2: Program — "How to organise and coordinate"

**Real-world patterns (Shopify, Linear, Shape Up):**
- **Shopify GSD:** 5-phase project lifecycle (Proposal → Prototype → Build → Release → Results) with OK1 (director-level) and OK2 (senior leadership) review gates. Async by default, sync only for controversial topics. Weekly: Monday company updates, program lead check-ins, escalation triage, Friday demos.
- **Linear:** 12-month strategic direction, 6-month detailed roadmap, 2-week execution cycles. Projects group related work across cycles; roadmaps sit above projects for strategic view.
- **Shape Up:** Fixed 6-week cycles with variable scope (not fixed scope with variable time). 2-week cooldown between cycles. Hill charts track uncertainty (unknown → known → done) rather than time estimates.
- **Spotify:** Squad-based autonomous teams with shared OKRs. The model eventually failed at scale due to accountability gaps — Spotify moved toward traditional management with clearer engineering leadership.

**Key lesson from research:** Alignment > cascading. Teams should propose their own OKRs that ladder up to company objectives, not receive top-down dictation. "Cascade a few anchors for clarity, align the rest where the work happens." (Christina Wodtke)

**Status communication:** Traffic-light format (GREEN/AMBER/RED + one sentence). 3-5 metrics with Target/Actual/Status. Must be deliverable verbally in under 2 minutes. Weekly for active projects, biweekly for steady-state.

**Risk management:** Practical risk register with top 5-10 risks. Each entry: Description, Likelihood (1-5), Impact (1-5), Owner, Mitigation Actions, Status. Reviewed weekly during active projects.

**Cadence:** 6-week cycles (Shape Up pattern) or quarterly roadmap refresh → weekly status + risk triage → daily standups.

**Artifacts:**
| Phase | Artifact | Purpose |
|-------|----------|---------|
| Discover | Feasibility study, user research, PRD | Validate the opportunity |
| Define | Roadmap, milestone plan, risk register | Plan the program |
| Design | Feature decomposition, dependency graph, architecture decisions | Break into tactical work |
| Deliver | Milestone tracking, burndown, dependency status, traffic-light updates | Track execution |
| Debrief | Project retrospective, milestone review, roadmap adjustment | Capture and propagate learnings |

**Gate model:** Human review with AI-prepared summaries and risk flags. AI does the heavy lifting on decomposition, tracking, and analysis — human decides at key gates.

#### L3: Tactical — "What to build and how" (pd's current strength)

**Preserved exactly as-is.** pd's existing 7-phase feature lifecycle is the 5D lifecycle at the tactical level. No breaking changes.

The 7 phases map to 5D:
- brainstorm → Discover
- specify → Define
- design + create-plan + create-tasks → Design (with decomposition into L4)
- implement → Deliver
- finish → Debrief

**Gate model:** AI review with human approval gates (pd's current model). 43 transition guards, AI-reviewed quality gates, knowledge bank, retrospectives.

#### L4: Operational — "Execute specific work"

**Real-world patterns (Spotify Honk agent, MDTM, Shape Up):**
- **Spotify Honk agent:** 1,500+ merged AI-generated PRs. 60-90% time savings on migrations. Engineers trigger from Slack/GitHub, AI produces PR. LLM Judge vetoes ~25% of sessions; agents self-correct ~50% of vetoed attempts.
- **MDTM (Markdown-Driven Task Management):** Tasks as files in Git with TOML frontmatter (ID, status, priority, assignee, dependencies) + markdown body. Status: To Do → In Progress → Review → Done. Both humans and AI agents can parse/modify.
- **AI-native execution:** 57% of organisations have deployed multi-step agent workflows. Spotify's top devs reportedly haven't written code since December 2025 — they review, orchestrate, and direct AI agents.
- **Quality gates as lightweight phases:** Requirements gate → Design gate → Development gate (linting, tests on every commit) → Review gate (automated + human) → Deployment gate (integration tests, security scans).

**Autonomy model:** Dual oversight — blocking "human-in-the-loop" for high-stakes decisions, asynchronous "human-on-the-loop" for continuous monitoring. Autonomy scales with seniority and risk: implementation details = full autonomy; architecture changes = proposal + approval.

**Task lifecycle:**
- **Define** — task spec with done-when criteria (from tasks.md or created ad-hoc)
- **Deliver** — implement, test, verify (AI-autonomous with automated gates)
- **Debrief** — review feedback, learnings (lightweight, often implicit in code review)

**Gate model:** AI-autonomous with automated verification. Test pass = done. Human review for high-risk changes only.

---

## Cross-Level Coordination: The Hard Problem

Research shows 67% of strategies fail at execution, not formulation. The failure modes are well-documented:

### Anti-Patterns to Avoid
1. **Top-down cascade without input** — teams copy-paste OKRs instead of thinking critically; any change to top OKRs forces entire departments to rebuild (Wodtke, Gothelf)
2. **Status theatre** — metrics that only go up, meetings that produce no action, process for process' sake
3. **Metric gaming / Goodhart's Law** — call center agents hanging up difficult calls to reduce handle time. Fix: pair every quantity metric with a quality counterbalance
4. **Set-and-forget** — OKRs/roadmaps checked only at quarter-end. Fix: weekly check-ins are "the single most important thing" (Quantive)
5. **Managing dependencies instead of eliminating them** — "the right approach is to restructure teams and architecture to remove coupling rather than building process to coordinate it" (Scrum.org)
6. **Copying frameworks without context** — Spotify Model was never a framework; it was a snapshot. Companies that copied it failed.

### Patterns That Work

**1. Hoshin Kanri Catchball (Bidirectional Alignment)**
Not top-down dictation. Each level:
- Receives intent from above (context, constraints, objectives)
- Proposes how to achieve it (plans, OKRs, decomposition)
- Negotiates back up until aligned
- "Ideas shaped by teams are more likely to be executed with care and energy"

**2. Mission Command (Auftragstaktik)**
Commander gives: clearly defined objective, timeframe, and resources.
Commander does NOT give: how to achieve it.
Subordinates interpret intent within their operational context. This requires genuine tolerance for failure — adding more process does not produce mission command.

**3. Netflix "Highly Aligned, Loosely Coupled"**
Leadership provides context (strategy, metrics, assumptions, objectives, stakes, transparency) rather than control (approvals, committees). Every decision has an "informed captain" who must "farm for dissent."

**4. Feedback Propagation**
- **Upward:** L4 task retro → L3 feature retro aggregates patterns → L2 project retro identifies systemic issues → L1 strategy review reassesses assumptions (double-loop learning)
- **Downward:** L1 OKR targets constrain L2 project scope → L2 milestones constrain L3 feature priorities → L3 design decisions constrain L4 task implementation
- **Lateral:** Feature A completes → Feature B unblocked (cascade unblock). KR1 at risk → flag to Objective owner for rebalancing.

### How pd Implements Cross-Level Coordination

**Alignment, not cascading:** When creating an L2 project under an L1 objective, pd shows the parent's intent and constraints but the team defines their own approach. The parent-child lineage tracks alignment without dictating content.

**Progress rollup:** Parent work item health is derived from children status. An L1 objective's OKR score is computed from its L2 children's completion. An L2 project's milestone progress is computed from its L3 features' phase status.

**Anomaly propagation:** When an L3 feature retro (Debrief) identifies a systemic issue, it's flagged on the parent L2 project and surfaces in the next L1 strategy review. Toyota's "andon cord" principle — operational reality reaches decision-makers directly.

**Dependency enforcement:** A work item can't enter Deliver if its `blocked_by` siblings aren't complete. This applies at every level — L3 feature blocked by another L3 feature, L2 project blocked by another L2 project.

---

## OKR Framework

OKRs are the bridge between strategic intent and tactical execution. pd implements OKRs as first-class work items, not a separate system.

### Structure

```
Objective (L1 work item, type=objective)
  ├── KR1 (L1/L2 bridge, type=key_result, metric_type=target)
  │     └── Project A (L2, parent=KR1)
  │           ├── Feature 1 (L3, parent=Project A)
  │           └── Feature 2 (L3, parent=Project A)
  ├── KR2 (type=key_result, metric_type=baseline)
  │     └── Project B (L2, parent=KR2)
  └── KR3 (type=key_result, metric_type=binary)
        └── Feature 3 (L3, parent=KR3)
```

### Key Result Types (from Perdoo/SimpleOKR research)

| Type | Description | Scoring |
|------|------------|---------|
| **Target metric** | Move a number from X to Y (e.g., "Reduce P1 incidents from 8/mo to <2/mo") | (current - baseline) / (target - baseline), clamped 0.0-1.0 |
| **Baseline metric** | Establish a measurement that doesn't exist yet (e.g., "Measure monthly deploy frequency") | Binary: measured = 1.0, not measured = 0.0 |
| **Milestone** | Multi-step deliverable (e.g., "Ship observability platform: logging, tracing, alerting") | Completed steps / total steps |
| **Binary** | Done or not done (e.g., "Achieve SOC2 certification") | 0.0 or 1.0 |

### Scoring Model (Google-inspired)

- **Committed KRs:** Must score 1.0. Anything less is a planning/execution failure.
- **Aspirational KRs:** Target 0.6-0.7 average. Scoring 1.0 means the goal wasn't ambitious enough.
- **Objective score:** Weighted average of KR scores. Weights configurable (default: equal).
- **Colour coding:** Green (0.7-1.0), Yellow (0.4-0.6), Red (0.0-0.3).

### Cadence

| Ceremony | Frequency | Duration | Purpose |
|----------|-----------|----------|---------|
| OKR setting | Quarterly | 1-2 weeks | Set objectives and measurable key results |
| OKR check-in | Weekly | 20 min | Update KR progress, surface blockers |
| OKR review | Monthly | 45 min | Assess objective health, rebalance |
| OKR scoring | End of quarter | 1 hour | Score KRs 0.0-1.0, retrospect on cycle |

### Anti-Patterns pd Must Prevent

1. **Output KRs** — "Launch mobile app" is a task, not a key result. KRs must describe outcomes: "Achieve 50K MAU on mobile." pd should warn when KR text contains activity words (launch, build, implement, complete).
2. **Too many OKRs** — Maximum 3 objectives, 3 KRs each (David Sacks "3x3 rule"). pd enforces this as a soft limit with override.
3. **OKRs as performance evaluation** — pd explicitly documents that OKR scores are learning tools, not accountability contracts.
4. **Cascading without autonomy** — pd shows parent context but teams create their own OKRs.

---

## Data Model: Universal Work Item

### Entity Hierarchy

```
Initiative (L1) — optional strategic container
  └── Objective (L1) — what we want to achieve
        └── Key Result (L1/L2 bridge) — how we measure success
              └── Project (L2) — coordinated program of work
                    └── Feature (L3) — individual deliverable
                          └── Task (L4) — unit of execution
```

Every node is a **Work Item** — same entity registry, same workflow engine, different `level` and `type`.

### Entity Schema Extension

Current entity types: `backlog`, `brainstorm`, `project`, `feature`

New entity types: `initiative`, `objective`, `key_result`, `task`

Each entity carries:
- `type` — determines lifecycle template and gate stringency
- `level` — L1/L2/L3/L4, derived from type
- `lifecycle_phase` — current 5D phase (or existing 7-phase for L3 features)
- `status` — draft | planned | active | blocked | completed | abandoned
- `parent` — reference to parent work item (existing `parent_type_id`)
- `blocked_by` — list of sibling type_ids this depends on (in `metadata`)
- `cadence` — planning cycle this belongs to (Q1-2026, H1-2026, etc.)
- `owner` — person or team responsible
- `metadata` — flexible JSON for type-specific fields (OKR scores, risk registers, etc.)

### Workflow Templates

```python
WORKFLOW_TEMPLATES = {
    # L1: Strategic (5D, human-gated)
    "initiative": ["discover", "define", "design", "deliver", "debrief"],
    "objective":  ["discover", "define", "design", "deliver", "debrief"],
    "key_result": ["define", "deliver", "debrief"],

    # L2: Program (5D, human+AI-gated)
    "project":    ["discover", "define", "design", "deliver", "debrief"],

    # L3: Tactical (existing 7-phase, AI+human-gated, backward compatible)
    "standard":   ["brainstorm", "specify", "design", "create-plan", "create-tasks", "implement", "finish"],
    "full":       ["brainstorm", "specify", "design", "create-plan", "create-tasks", "implement", "finish"],
    "bugfix":     ["specify", "create-tasks", "implement", "finish"],
    "hotfix":     ["implement", "finish"],

    # L4: Operational (mini-lifecycle, AI-autonomous)
    "task":       ["define", "deliver", "debrief"],
}
```

### Gate Stringency by Level

| Level | Gate Type | Who Reviews | Pass Criteria |
|-------|-----------|------------|---------------|
| L1 | Human-only | Executives, informed captains | Explicit human approval at every transition |
| L2 | Human + AI | AI prepares analysis, human decides at key gates (OK1/OK2 pattern) | AI-reviewed with human sign-off |
| L3 | AI + Human | AI reviews, human approves at key gates (pd's current model) | AI approval + human override at phase boundaries |
| L4 | AI-autonomous | Automated verification (tests, linting, CI) | Tests pass = done. Human review for high-risk only |

---

## Organisational Topology (Not Hierarchy)

Real organisations are not strict trees. They are **overlapping circles of concern** — a security initiative touches every team, a platform service is consumed by multiple products, an SRE concern spans strategy and operations simultaneously.

### Circles, Not Layers

Instead of rigid L1→L2→L3→L4 hierarchy, pd models the organisation as a **topology of circles**:

```
    ┌──────────────────────────────────────────────────────────┐
    │                                                          │
    │    ┌─────────────┐                                       │
    │    │  SECURITY   │──────────────────────┐                │
    │    │  concern    │                      │                │
    │    └──────┬──────┘                      │                │
    │           │ spans                       │                │
    │    ┌──────┴──────────────────┐    ┌─────┴──────────┐     │
    │    │     PLATFORM           │    │   PRODUCT A     │     │
    │    │     circle             │    │   circle        │     │
    │    │  ┌──────────────┐      │    │  ┌───────────┐  │     │
    │    │  │ Observability│      │    │  │ Auth      │  │     │
    │    │  │ project      │◄─────┼────┼──│ feature   │  │     │
    │    │  │              │ used │    │  │           │  │     │
    │    │  └──────────────┘ by   │    │  └───────────┘  │     │
    │    │  ┌──────────────┐      │    │  ┌───────────┐  │     │
    │    │  │ HA Infra     │      │    │  │ Dashboard │  │     │
    │    │  │ project      │      │    │  │ feature   │  │     │
    │    │  └──────────────┘      │    │  └───────────┘  │     │
    │    └────────────────────────┘    └────────────────┘      │
    │                                                          │
    │    ┌────────────────┐   ┌────────────────┐               │
    │    │  PRODUCT B     │   │  DATA TEAM     │               │
    │    │  circle        │   │  circle        │               │
    │    │  ┌───────────┐ │   │  ┌───────────┐ │               │
    │    │  │ Payments  │ │   │  │ Pipeline  │ │               │
    │    │  │ feature   │ │   │  │ project   │ │               │
    │    │  └───────────┘ │   │  └───────────┘ │               │
    │    └────────────────┘   └────────────────┘               │
    │                                                          │
    │              COMPANY OKRs (shared context)               │
    └──────────────────────────────────────────────────────────┘
```

### How Circles Map to the Entity Engine

Each **circle** is a scope — a team, domain, product area, or cross-cutting concern. Work items belong to circles via **tags** and **lineage**, not a single rigid tree:

- A **feature** has one parent (project or standalone) but can be **tagged** with multiple circles (security, platform, product-a)
- An **initiative** can span multiple circles — its children (projects, features) live in different circles
- A **cross-cutting concern** (security audit, accessibility, performance) is an entity that links to work items across circles
- The entity engine's **lineage** provides the primary structure; **tags** provide the cross-cutting dimension

```
Entity relationships:
  parent_type_id  → primary lineage (one parent, tree structure)
  tags[]          → circle membership (many circles, graph structure)
  blocked_by[]    → dependencies (lateral, within or across circles)
  contributes_to  → OKR alignment (many-to-many, work → KRs)
```

### Why This Matters for pd

The L1/L2/L3/L4 levels still describe the **type of work** (strategic/program/tactical/operational) and determine **gate stringency** and **cadence**. But the organisational structure is a topology:

- A solo developer has one circle (themselves) operating at L3/L4
- A startup has a few overlapping circles, light L1, active L2/L3/L4
- A large org has many circles at every level, with cross-cutting concerns spanning them
- pd adapts to the topology — it doesn't impose a hierarchy

The entity engine is the **connective tissue** that makes circles coherent. Work items are linked through lineage, tagged with circles, and the engine handles state derivation, dependency enforcement, and progress rollup across the topology.

---

## Secretary as Organisational Router

The secretary agent is pd's **front door** — the universal entry point that triages requests to the right circle, level, and workflow:

### Triage Model

```
USER REQUEST (natural language)
  │
  ▼
SECRETARY analyses:
  ├── WHO: User's role/circle (from config/memory)
  ├── SCOPE: Company-wide? Team? Individual task?
  ├── ACTION: Plan? Coordinate? Execute? Query?
  └── WEIGHT: How much ceremony does this need?
  │
  ▼
CONTEXT ENRICHMENT:
  ├── Search entity registry for related work
  │   "structured logging" → finds project:P003-observability
  ├── Check for duplicates/overlaps
  │   "Is someone already working on this?"
  ├── Identify parent candidates
  │   "This fits under KR: P0 incidents <2/mo"
  └── Detect circle membership
      "Touches auth service (Product A) + logging (Platform)"
  │
  ▼
RECOMMENDATION:
  "This looks like a standard-weight tactical feature.
   I found Project P003 (Observability) under KR 'P0 <2/mo'.
   It touches both Platform and Product A circles.

   Create as feature under project:P003?
   Weight: standard (spec + design + implement)
   Tags: [platform, product-a]"
```

### Routing Examples

| Request | Secretary Analysis | Route |
|---------|-------------------|-------|
| "We need to improve platform reliability" | Company-wide scope, strategic intent | L1: `/pd:create-objective` |
| "Set up the observability project" | Multi-feature program, clear scope | L2: `/pd:create-project` |
| "Build structured logging for auth" | Single deliverable, clear parent | L3: `/pd:create-feature` under project |
| "Fix the NPE in login handler" | Small, bounded, low risk | Light L3 or L4 task |
| "Where are we on Q2 OKRs?" | Status query, not work creation | Entity engine portfolio query |
| "The auth migration is blocked by infra" | Dependency/blocker report | Update `blocked_by`, flag risk |

### Secretary Intelligence

The secretary doesn't just route — it provides **organisational intelligence**:

- **Duplicate detection:** "There's already a feature for structured logging (feature:012). Continue that or create new?"
- **Circle awareness:** "This touches the security circle. Should I tag the security team?"
- **Weight recommendation:** "This started as a bug fix but it touches 3 services. Recommend upgrading to standard weight with design review."
- **Escalation detection:** "This task has been blocked for 5 days. Should I flag it on the parent project?"
- **Cadence awareness:** "Q2 OKR check-in is next week. Want me to prepare a progress summary?"

---

## Universal Work Creation

Work emerges everywhere in an organisation — not just top-down. pd needs a unified creation flow that works regardless of source:

### Work Sources

```
DECOMPOSITION:  Design at any level creates children
                Initiative design → projects
                Project design → features (pd already does this)
                Feature design → tasks

EMERGENT:       Work discovered during execution
                Bug found during implementation → new task or feature
                Retro surfaces systemic issue → new initiative
                Scope change → new dependency or feature

AD-HOC:         Work created from outside the current flow
                Customer feedback → backlog → feature
                Incident → hotfix feature or task
                Idea → brainstorm → feature
                Tech debt → backlog → feature

LATERAL:        Work triggered by sibling events
                Feature A completes → Feature B unblocks
                KR at risk → rebalancing work created
```

### The 4-Step Creation Flow

Every work item, regardless of source or level, follows the same pattern:

**Step 1: Identify** — Secretary triages the request:
- What type? (initiative / objective / key_result / project / feature / task)
- What weight? (full / standard / light)
- What circle(s)? (platform, product-a, security, etc.)

**Step 2: Link** — Entity engine finds where it fits:
- Search for parent candidates in the topology
- Secretary proposes linkage: "Link to project:P003?"
- User confirms, or creates standalone
- If no clear parent: goes to backlog as organisational inbox

**Step 3: Register** — Entity created in registry:
- Type, tags, parent_type_id, status=planned
- Workflow template assigned based on type + weight
- blocked_by computed from sibling dependencies
- OKR alignment recorded via `contributes_to` if applicable

**Step 4: Activate** — When ready to start:
- Status → active, enters first phase of template
- For tasks: may auto-activate if parent is in Deliver phase and no blockers
- For features: activation may wait for capacity or dependency resolution

### The Backlog as Organisational Inbox

pd's existing backlog becomes the **universal inbox** for work that hasn't been triaged into the topology:

- Any circle member can add to backlog: `/pd:add-to-backlog "description"`
- Secretary triages backlog items at cadence boundaries (weekly, per-cycle)
- Triage = identify level, weight, circle, and parent → promote to work item
- Untriaged items remain visible but don't block anything

---

## Ceremony Weight

Not everything needs a 6-pager. Work weight determines ceremony level, independent of organisational level:

### Three Weights

| Weight | When | Phases | Gates | Artifacts |
|--------|------|--------|-------|-----------|
| **Full** | High risk, novel, cross-circle, strategic | All 5D phases with full review | AI review + human approval at every transition | All artifacts required, retro mandatory |
| **Standard** | Normal work, clear scope, moderate complexity | Key phases with proportional review | AI review at key phases, human at boundaries | Core artifacts (spec, design or plan), retro recommended |
| **Light** | Low risk, small scope, well-understood, bounded blast radius | Minimal viable process | Automated verification only (tests, CI) | Brief description + done-when criteria, retro captured in parent |

### Weight-Specific Templates

```python
WEIGHT_TEMPLATES = {
    # Strategic (L1)
    ("initiative", "full"):     ["discover", "define", "design", "deliver", "debrief"],
    ("initiative", "standard"): ["discover", "define", "design", "deliver", "debrief"],
    ("objective", "standard"):  ["define", "design", "deliver", "debrief"],
    ("key_result", "standard"): ["define", "deliver", "debrief"],

    # Program (L2)
    ("project", "full"):        ["discover", "define", "design", "deliver", "debrief"],
    ("project", "standard"):    ["discover", "define", "design", "deliver", "debrief"],
    ("project", "light"):       ["define", "design", "deliver", "debrief"],

    # Tactical (L3) — backward compatible with existing templates
    ("feature", "full"):        ["brainstorm", "specify", "design", "create-plan",
                                 "create-tasks", "implement", "finish"],
    ("feature", "standard"):    ["brainstorm", "specify", "design", "create-plan",
                                 "create-tasks", "implement", "finish"],
    ("feature", "light"):       ["specify", "implement", "finish"],

    # Operational (L4)
    ("task", "standard"):       ["define", "deliver", "debrief"],
    ("task", "light"):          ["deliver"],  # just do it — tests are the gate
}
```

### Gate Stringency by Weight

| Weight | Review Model | Pass Criteria |
|--------|-------------|---------------|
| **Full** | AI + human at every phase boundary | Explicit human approval required |
| **Standard** | AI reviews, human approves at key boundaries | AI approval + human override available |
| **Light** | Automated only (tests, linting, CI) | Tests pass = done |

### Weight Escalation

Secretary detects when light work outgrows its weight class:

| Signal | Recommendation |
|--------|---------------|
| Scope creep: "fix" touches >3 files or >2 services | "Consider upgrading to standard with spec" |
| Risk: changes auth, payment, or data code | "Suggest standard weight with design review" |
| Cross-circle: affects another team's service | "Needs coordination — consider standard or project" |
| Duration: light task active >2 days | "Consider upgrading to standard" |
| Blast radius: changes shared API contract | "This needs design review — upgrade to standard" |

Light ≠ no process. Even light work items are:
- Registered as entities (tracked, linked, auditable)
- Linked to parents (show up in progress rollup)
- Given status lifecycle (planned → active → complete)
- Verified on completion (tests must pass)

---

## Work Trigger Model

How work gets initiated at each level and flows through the topology:

### Trigger Types

| Trigger | Description | Example |
|---------|------------|---------|
| **Cadence** | Time-based: planning cycle begins | "Q2 starts — set OKRs" |
| **Decomposition** | Design at one level creates children | "Project design produces features" |
| **Completion** | Work finishing unblocks dependents | "Feature A done → Feature B unblocks" |
| **Anomaly** | Debrief surfaces issue, escalates to parent | "Retro finds systemic auth flaw → initiative" |
| **Ad-hoc** | External input or new discovery | "Customer report → backlog → feature" |

### How Triggers Flow

**Decomposition (Design → children):** When any work item's Design phase decomposes into children, the entity engine registers child entities with `parent_type_id` pointing to the decomposing item. Children enter their template's first phase. This is how intent flows through the topology — not as top-down commands but as structured decomposition that preserves parent context.

**Completion (upward rollup):** When a work item completes, the entity engine:
1. Removes it from siblings' `blocked_by` lists (cascade unblock)
2. Recomputes parent's derived state (progress, OKR score, traffic light)
3. If all siblings complete, parent may advance (e.g., all features done → project's Deliver phase can complete)

**Anomaly (upward propagation):** When a Debrief phase identifies a systemic issue, it's flagged on the parent entity's metadata. The parent's next Discover phase includes child anomalies. This is Toyota's "andon cord" in organisational form.

**Cadence (time-based):** Strategic and program work is triggered by planning cycles (quarterly OKR setting, 6-week cycle boundaries). pd supports this via `/pd:start-cycle` commands and cadence tags on entities.

**Ad-hoc (backlog inbox):** Work that doesn't fit the current flow goes to backlog. Secretary triages at cadence boundaries or on-demand.

---

## What Changes for pd

### Phase 1: Foundation — Depth Fixes + Core Extensions

Fix 6 depth bugs (no architectural change, immediate value):
1. **Field validation** — `init_feature_state()` rejects empty identity fields with ValueError
2. **Frontmatter health** — remove dead `reconcile_status` frontmatter check
3. **Maintenance mode** — add `PD_MAINTENANCE=1` bypass to meta-json-guard
4. **Kanban derivation** — implement `derive_kanban()`, replace all independent kanban sets
5. **Artifact completeness** — soft verification warnings on feature finish
6. **Reconciliation reporting** — surface session-start reconciliation summary

Core extensions:
- Extend entity type CHECK constraint: add `initiative`, `objective`, `key_result`, `task`
- Add `tags` and `contributes_to` fields to entity metadata schema
- Add workflow templates registry with weight-specific templates (from Ceremony Weight section)
- Add ceremony weight system (full/standard/light) to entity creation flow

### Phase 2: Secretary + Universal Work Creation

Transform secretary into organisational router:
- Level detection from request scope and user context
- Parent candidate search via entity registry
- Duplicate/overlap detection
- Weight recommendation based on scope, risk, and blast radius
- Weight escalation detection for in-progress work

Universal work creation flow:
- 4-step identify → link → register → activate pattern at every level
- Backlog as organisational inbox with triage at cadence boundaries

### Phase 3: L4 Operational — Tasks as Work Items

Elevate tasks from flat markdown to first-class entities:
- Each task in tasks.md registered as entity with `type=task`, `parent=feature:{id}`
- Mini-lifecycle per weight: light = deliver only; standard = define → deliver → debrief
- Dependencies between tasks tracked and enforced via `blocked_by`
- Agent-executable: AI agents query "ready tasks" and execute autonomously
- Opt-in: simple tasks stay as markdown. Only promoted tasks get entity lifecycle.

### Phase 4: L2 Program — Living Projects

Make projects living entities instead of write-once containers:
- Projects get their own 5D lifecycle (discover through debrief)
- Milestones become checkpoints within project lifecycle, not just metadata
- Roadmap regenerated when project state changes
- Traffic-light status (GREEN/AMBER/RED) derived from child feature progress
- Risk register support in project metadata
- Dependency enforcement: feature can't enter Deliver if `blocked_by` siblings aren't complete
- Cross-circle tagging: projects can span multiple circles

### Phase 5: L1 Strategic — Initiatives & OKRs

Add the strategic layer:
- **Initiatives** — strategic bets with 5D lifecycle, Amazon-style narrative documents
- **Objectives** — what we want to achieve this cycle, with cadence tags (Q2-2026)
- **Key Results** — measurable outcomes with type (target/baseline/milestone/binary), scoring 0.0-1.0
- OKR cadence management (quarterly by default, configurable)
- OKR anti-pattern detection (output KRs, too many OKRs, activity words)
- Portfolio view: initiative health, OKR progress, cross-circle dependencies
- Strategic advisors: reuse existing advisory framework at L1

### Phase 6: Cross-Topology Intelligence

- **Hoshin Kanri catchball** — when creating children, show parent intent; when completing children, update parent progress
- **Cascade unblock** — completing a work item unblocks dependents within and across circles
- **Progress rollup** — parent health derived from children status (OKR scores from child completion)
- **Anomaly propagation** — debrief findings flagged on parent entity for next Discover phase
- **Workspace scoping** — workspace_id column for multi-project isolation
- **Circle-aware queries** — portfolio views filtered by circle, cross-circle dependency maps

---

## What Does NOT Change

- **L3 tactical workflow** — the existing 7-phase feature lifecycle is preserved exactly as-is. The phase names, gates, and artifacts remain. No breaking changes to existing features.
- **Entity lineage model** — same `parent_type_id` mechanism, extended with tags for cross-circle membership
- **Agent/reviewer architecture** — same dispatch pattern, extended with level-appropriate reviewers
- **Knowledge bank** — same structure, extended with level and circle tags for filtering
- **Plugin portability** — no hardcoded paths, same two-location glob pattern

---

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Scope creep — trying to build Jira | High | High | Each phase is independently valuable and shippable. Phase 1 is pure bugfixes. |
| L1/L2 unused — solo devs don't need executive layer | Medium | Low | L1/L2 are opt-in. Solo developers continue using L3/L4 only. Zero overhead if unused. |
| Schema migration breaks existing features | Medium | High | Entity type extension is additive (new CHECK values). L3 templates are backward-compatible. |
| OKR scoring is noisy without real metrics | Medium | Medium | Start with manual scoring + child-completion rollup. External metrics integration is future work. |
| Task-level lifecycle adds friction | Medium | Medium | L4 is opt-in. Simple tasks stay as markdown. Only promoted tasks get lifecycle. |
| Cross-level coordination becomes status theatre | Medium | High | Follow Netflix model: provide context not control. Catchball not cascade. Weekly check-ins not quarterly reviews. |

---

## Success Metrics

1. **L3 preserved:** All existing tests pass unchanged (710+ entity registry, 309 workflow engine, 118 reconciliation)
2. **L4 operational:** Tasks from tasks.md can be registered as entities with parent lineage, executed by AI agents, and marked complete
3. **L2 living projects:** Project milestones track progress, roadmap regenerates, traffic-light status computes from features
4. **L1 OKRs:** Objectives and Key Results created, scored 0.0-1.0, linked to projects, with anti-pattern warnings
5. **Cross-level:** Completing a feature updates parent project progress. Completing a project updates parent KR score. Retro findings propagate to parent.
6. **Backward compatible:** A developer who ignores L1/L2/L4 sees zero change in their L3 workflow

---

## Research Sources

### Executive Operations
- [Amazon PR/FAQ Working Backwards](https://workingbackwards.com/concepts/working-backwards-pr-faq-process/) — Written narratives for strategic decisions
- [Amazon Monthly/Quarterly Business Reviews](https://workingbackwards.com/concepts/quarterly-monthly-business-reviews/) — Input metrics focus, narrative-driven
- [Bezos Type 1/Type 2 Decisions](https://fs.blog/reversible-irreversible-decisions/) — Reversible vs irreversible decision framework
- [David Sacks Operating Cadence](https://www.capitaly.vc/blog/david-sacks-operating-cadence-weekly-metrics-okrs-ceo-dashboard) — 3x5 rule, weekly metrics, 30-day implementation
- [Stripe Operating System](https://www.lennysnewsletter.com/p/lessons-from-scaling-stripe-tactics) — Foundational documents, operating principles
- [Netflix Culture](https://jobs.netflix.com/culture) — Highly aligned, loosely coupled; informed captains
- [Shape Up](https://basecamp.com/shapeup) — Betting table, 6-week cycles, variable scope
- [How Linear Builds Product](https://www.lennysnewsletter.com/p/how-linear-builds-product) — 12-month direction, 2-week cycles

### OKR Frameworks
- [Google OKR Playbook](https://www.whatmatters.com/resources/google-okr-playbook) — Committed vs aspirational, scoring rules, KR writing guidelines
- [Google re:Work OKR Guide](https://rework.withgoogle.com/intl/en/guides/set-goals-with-okrs) — 0.6-0.7 sweet spot
- [Cascading OKRs at Scale](https://cwodtke.medium.com/cascading-okrs-at-scale-5b1335812a32) — Alignment > cascading
- [OKR Lineage](https://jeffgothelf.com/blog/aligning-not-cascading-okrs-with-an-okr-lineage/) — Family tree not waterfall
- [5 Ways Companies Misuse OKRs](https://itamargilad.com/5-ways-your-company-may-be-misusing-okrs/) — Output KRs, too many, top-down, performance eval
- [Key Result Types](https://www.perdoo.com/resources/blog/different-types-of-key-results-and-when-to-use-them) — Target, baseline, milestone, binary
- [NCT Framework](https://mooncamp.com/blog/nct-vs-okr) — Narratives + Commitments + Tasks (Netflix-attributed)
- [V2MOM Framework](https://www.salesforce.com/blog/how-to-create-alignment-within-your-company/) — Salesforce: Vision, Values, Methods, Obstacles, Measures

### Cross-Level Coordination
- [Strategy Execution Gap](https://gwork.io/blog/the-strategy-execution-gap-why-67-of-strategies-fail-and-how-to-close-it/) — 67% fail at execution, not strategy
- [Hoshin Kanri Catchball](https://businessmap.io/lean-management/hoshin-kanri/what-is-catchball) — Bidirectional alignment
- [Mission Command](https://hbr.org/2010/11/mission-command-an-organizat) — Objective + resources, not how-to (HBR)
- [Eliminate Dependencies](https://www.scrum.org/resources/blog/eliminate-dependencies-dont-manage-them) — Restructure, don't manage
- [Metric Anti-Patterns](https://kpitree.co/guides/strategy-culture/metric-anti-patterns) — Goodhart's Law, vanity metrics, set-and-forget
- [Spotify Model Failures](https://www.jeremiahlee.com/posts/failed-squad-goals/) — Why copying frameworks fails

### Program Management
- [Shopify GSD](https://www.lennysnewsletter.com/p/how-shopify-builds-product) — 5-phase lifecycle, OK1/OK2 gates
- [Shopify Engineering Programs](https://shopify.engineering/running-engineering-program-guide) — Cadences, artifacts, templates
- [OKR Weekly Check-Ins](https://quantive.com/resources/articles/okr-cycle) — "The single most important thing"
- [Status Update Framework](https://winningpresentations.com/project-status-update-framework/) — Traffic-light, 5 elements, 2-minute rule

### Operational/IC Execution
- [Spotify Honk Agent](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1) — 1,500+ AI-generated PRs
- [Spotify Agent Feedback Loops](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3) — LLM Judge, self-correction
- [MDTM Explained](https://github.com/jezweb/roo-commander/wiki/02_Core_Concepts-03_MDTM_Explained) — Markdown-driven task management
- [Agentic Manifesto](https://caseywest.com/the-agentic-manifesto/) — Human-in/on-the-loop dual oversight
- [Pipeline Quality Gates](https://www.infoq.com/articles/pipeline-quality-gates/) — Lightweight lifecycle phases
- [Spotify Top Devs](https://techcrunch.com/2026/02/12/spotify-says-its-best-developers-havent-written-a-line-of-code-since-december-thanks-to-ai/) — Engineers as agent orchestrators

### Organisational Frameworks
- [Sociocracy 3.0 Fractal Organization](https://patterns.sociocracy30.org/fractal-organization.html) — Same governance at every level
- [SAFe Analysis](https://www.pmi.org/disciplined-agile/da-flex-toc/the-good-the-bad-and-the-ugly-of-safe) — PI Planning works; centralisation doesn't
- [PMI Strategy-Execution Gap 2025](https://www.pmi.org/about/press-media/2025/new-pmi-research-reveals-strategy-execution-gap-is-undermining-transformation-and-how-to-close-it) — Dedicated organisational capacity needed

### Codebase Analysis (pd current state)
- 4 entity types, 28 skills, 28 agents, 29 commands
- 43 transition guards, 7-phase sequence (standard/full modes only)
- kanban: 8 columns defined, 3 unused (agent_review, human_review, blocked)
- Two competing kanban derivations (STATUS_TO_KANBAN vs FEATURE_PHASE_TO_KANBAN)
- depends_on_features: stored but only consumed by YOLO stop hook
- Project milestones: write-once at decomposition, never read back
- OKR support: non-existent
- Task lifecycle: non-existent (flat markdown checklist)
