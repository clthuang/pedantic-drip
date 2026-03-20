# PRD: pd as Fractal Organisational Management Hub

**Date:** 2026-03-20
**Status:** Draft
**Source:** Deep research across 60+ sources on organisational management, OKR frameworks, cross-level coordination, and AI-native development patterns.

---

## Problem Statement

pd is a tactical feature development engine. It excels at guiding one feature through brainstorm-to-finish with AI-reviewed quality gates. But organisations operate at multiple levels simultaneously, and pd has no presence above or below the feature level.

**Executive/Strategic layer (absent):** No way to capture vision, set OKRs, manage initiative portfolios, or make strategic bets. C-suite decisions happen outside pd — context is lost, intent never reaches execution.

**Program/Management layer (partial):** Projects exist but are write-once containers. Roadmaps, milestones, and dependencies are stored at decomposition time and never maintained. No risk tracking, no milestone progress, no cross-project coordination. 67% of strategies fail not because strategy was wrong but because daily behaviours don't align with strategic intent (Kaplan-Norton/HBR).

**Operational layer (weak):** tasks.md is a flat checklist. No lifecycle, no quality gates, no dependency tracking between tasks. In the AI-native era, tasks are the unit that agents execute — they deserve first-class treatment.

**Cross-level coordination (absent):** No mechanism for strategic intent to flow down to execution or for operational learnings to flow back up.

---

## Core Insight: Fractal Self-Similarity

Every successful multi-level management framework uses the **same lifecycle at every level** — only scope and gate stringency change:

- **Military Mission Command (Auftragstaktik):** Same planning cycle at every echelon. Give objective + resources, not how-to. (von Moltke/Clausewitz)
- **Hoshin Kanri:** Three-layer planning with bidirectional "catchball" — iterative alignment where each level refines and adjusts. (Toyota)
- **OKRs:** A Key Result at level N becomes an Objective at level N+1. Same structure, different scope. (Intel/Google)
- **Sociocracy 3.0:** Same governance pattern at every nested circle level, repeating fractally.

pd already has the lifecycle engine, entity registry, AI-reviewed quality gates, and knowledge bank. **Don't build four different systems — apply the same engine at every level with level-appropriate configuration.**

### Theoretical Foundation: Viable System Model (VSM)

Stafford Beer's Viable System Model (1972) is pd's theoretical foundation. VSM models organisations as recursive fractal structures where every viable system contains the same five subsystems at every level — the principle of recursion means "all viable systems look the same" regardless of scale.

**VSM mapping to pd:**

| VSM System | pd Equivalent | Function |
|-----------|---------------|----------|
| **S1: Operations** | L3/L4 features + tasks | Primary value-producing units (teams/agents executing work) |
| **S2: Coordination** | Secretary + entity engine | Prevents conflict between S1 units (routing, dedup, dependency tracking) |
| **S3: Optimisation** | Quality gates + reviewers | Optimises current operations (AI reviewers, transition guards) |
| **S3*: Audit** | Reconciliation + anomaly detection | Sporadic direct investigation bypassing normal reporting |
| **S4: Intelligence** | L1 strategic layer + advisors | Scans external environment, models future (brainstorming, research agents) |
| **S5: Policy** | OKRs + initiative governance | Defines identity, balances S3-S4 tension, ultimate authority |

**Algedonic signals** — VSM's pain/pleasure alerts that escalate through recursion levels with timeouts — are exactly pd's "anomaly propagation." When operational reality deviates from capability, feedback escalates through levels until resolved.

**Critical design constraint from VSM:** S2-S5 must NOT become viable systems themselves (Kerr, 2022). When coordination/governance functions prioritise self-preservation over serving S1 operations, organisational health deteriorates. pd must ensure the secretary, quality gates, and OKR framework serve feature execution, not the other way around.

**Implementations:** Open-source Elixir implementation (github.com/viable-systems) with Actor Model and Event Sourcing. Project Cybersyn (Chile, 1971-73) demonstrated VSM viability at national scale. Academic VSMod tool (University of Valladolid, since 2003).

### Architectural Precedents

**OpenProject's "work package" model** is the closest existing software to pd's unified entity approach — all work items (tasks, features, bugs, milestones, epics) are the same entity type with different "types" as configuration, each with its own workflow (status transitions based on type + role). This validates pd's "same lifecycle engine, different gate stringency per type."

**C2SIM (SISO-STD-019-2020)** — NATO-standard ontology for hierarchical command and control. Intent flows down through orders that decompose at each echelon while preserving commander's intent. Status flows up through reporting. Both share the same data model — exactly pd's bidirectional feedback pattern.

**Magentic-One (Microsoft, 2024)** — dual-ledger architecture: Task Ledger (strategic plan + facts) and Progress Ledger (execution monitoring with stall detection and re-planning triggers). The closest published model to pd's "decompose → execute → feedback" loop.

### Agent Decomposition Principles

From AOP (ICLR 2025) — three principles for multi-agent task decomposition that pd's Design phase must satisfy:
1. **Solvability** — each sub-task must be independently solvable by at least one agent
2. **Completeness** — decomposition must include all relevant information from the parent
3. **Non-redundancy** — sub-tasks must be unique and necessary

From Anthropic's multi-agent research: encode "good heuristics rather than rigid rules" for decomposition. Rigid task specs are counterproductive due to emergent behaviours. Token usage explains 80% of performance variance.

### What's Novel in pd (No Existing Precedent)

1. **Multi-level decomposition in one system** — no framework handles Strategic → Program → Feature → Task → Agent as a first-class hierarchy. Existing tools operate at 1-2 levels.
2. **OKRs as first-class work items** sharing the same entity registry as features and tasks — every existing tool (WorkBoard, Viva Goals) treats OKRs and execution as separate systems connected by integrations.
3. **Purely event-driven organisational governance** — no existing tool eliminates scheduled ceremonies entirely. All Hoshin Kanri/OKR tools use scheduled reviews.
4. **Persistent entity lineage across sessions and projects** — most agent frameworks treat each run as stateless.

### Design Risks the Literature Warns About

1. **Event-driven-only is uncharted** — every real implementation uses some scheduled forcing functions. pd's optional `target_date` metadata partially addresses this.
2. **VSM criticism: variety is hard to measure** — the framework is more interpretive than testable. pd should focus on structural patterns (recursion, algedonic signals), not measurement theory.
3. **S2 (coordination) is most commonly under-specified** in VSM implementations — pd's secretary needs extra design attention.
4. **Double-loop learning blockers** (Argyris) — organisations resist changing governing variables even when operational feedback demands it. pd can surface anomalies but can't force strategic reassessment.

---

## The 5D Fractal Lifecycle

Every work item at every organisational level follows five phases:

```
DISCOVER → DEFINE → DESIGN → DELIVER → DEBRIEF
```

pd's existing 7-phase tactical sequence is a **specialisation** of 5D at the tactical level. The mapping is loose, not structural — L3 features keep their existing 7-phase names and gates unchanged:
- `brainstorm` ≈ **Discover**
- `specify` ≈ **Define**
- `design` + `create-plan` + `create-tasks` ≈ **Design** (three sub-phases for architecture, planning, and decomposition)
- `implement` ≈ **Deliver**
- `finish` ≈ **Debrief**

L1, L2, and L4 work items use the 5D phase names directly. L3 features use the existing 7-phase names. The lifecycle engine is parameterised by entity type, not forced into uniform naming.

### Four Work Levels

| Level | Who | Work Items | pd Today |
|-------|-----|-----------|----------|
| **L1: Strategic** | CEO, CTO, VP, Founders | Initiatives, Objectives, Key Results | None |
| **L2: Program** | Directors, EMs, PMs | Projects, Milestones | Partial (write-once) |
| **L3: Tactical** | Senior Engineers, Tech Leads | Features | Well-served |
| **L4: Operational** | Engineers, ICs, AI Agents | Tasks | Flat checklist |

Levels describe the **type of work** and determine **gate stringency**, not organisational hierarchy. See "Organisational Topology" below.

---

## What Each Level Does (Research-Grounded)

### L1: Strategic — "What to build and why"

**Real-world patterns:**
- **Amazon:** Written 6-page narratives for strategy reviews. PR/FAQ documents for new initiatives (mock press release + 5 pages of FAQs from customer perspective). PowerPoint banned. Meetings start with 20-25 min silent reading.
- **Google:** OKRs with committed vs aspirational distinction. Committed must score 1.0; aspirational target 0.6-0.7.
- **Stripe:** Foundational documents (values, operating principles, long-term goals). Claire Hughes Johnson's "stable, consistent foundation of practices."
- **Netflix:** "Highly aligned, loosely coupled." Leadership provides context (strategy, metrics, assumptions), not control (approvals, committees). Every decision has an "informed captain" who must "farm for dissent."
- **Basecamp:** "Betting table" picks shaped pitches. No backlog — unshaped ideas that aren't bet on are discarded.

**Decision framework:** Bezos Type 1/Type 2 — irreversible decisions require slow deliberation; reversible decisions should be made fast with ~70% information. Most decisions are Type 2 but organisations mistakenly treat them as Type 1.

**Artifacts:**

| Phase | Artifact | Purpose |
|-------|----------|---------|
| Discover | Vision document, market analysis, competitive landscape | Frame the strategic context |
| Define | OKR sheet (objectives + measurable key results), strategic bet thesis | Set measurable direction |
| Design | Initiative portfolio, program decomposition | Break strategy into executable programs |
| Deliver | Portfolio dashboard, OKR progress tracking | Track health across programs |
| Debrief | Strategy review, OKR scoring (0.0-1.0) | Score outcomes, feed learnings back |

**Gate model:** Human-only review. AI assists with research, analysis, and document preparation — humans make every strategic decision.

### L2: Program — "How to organise and coordinate"

**Real-world patterns:**
- **Shopify GSD:** 5-phase project lifecycle (Proposal → Prototype → Build → Release → Results) with OK1 (director-level) and OK2 (senior leadership) review gates. Async by default, sync only for controversial topics.
- **Linear:** 12-month strategic direction, 6-month detailed roadmap, 2-week execution cycles. Projects group related work; roadmaps show strategic view.
- **Shape Up:** Fixed time (6-week cycles), variable scope. Hill charts track uncertainty (unknown → known → done) rather than time estimates.

**Key lesson:** Alignment > cascading. Teams propose their own OKRs that ladder up to company objectives, not receive top-down dictation. "Cascade a few anchors for clarity, align the rest where the work happens." (Wodtke)

**Status communication:** Traffic-light format (GREEN/AMBER/RED + one sentence). 3-5 metrics with Target/Actual/Status. Deliverable verbally in under 2 minutes.

**Artifacts:**

| Phase | Artifact | Purpose |
|-------|----------|---------|
| Discover | Feasibility study, user research, PRD | Validate the opportunity |
| Define | Milestone plan, risk register | Plan the program |
| Design | Feature decomposition, dependency graph, architecture decisions | Break into tactical work |
| Deliver | Milestone tracking, traffic-light status | Track execution |
| Debrief | Project retrospective, milestone review | Capture and propagate learnings |

**Gate model:** Human review with AI-prepared summaries and risk flags. AI does heavy lifting on decomposition, tracking, and analysis — human decides at key gates.

### L3: Tactical — "What to build and how" (pd's current strength)

**Preserved exactly as-is.** pd's existing 7-phase feature lifecycle is the 5D lifecycle at the tactical level. No breaking changes. The 43 transition guards, AI-reviewed quality gates, knowledge bank, and retrospectives remain.

**Gate model:** AI review with human approval gates (pd's current model).

### L4: Operational — "Execute specific work"

**Real-world patterns:**
- **Spotify Honk agent:** 1,500+ merged AI-generated PRs. 60-90% time savings. LLM Judge vetoes ~25%; agents self-correct ~50% of vetoed attempts.
- **MDTM:** Tasks as files in Git with frontmatter (ID, status, dependencies) + markdown body. Both humans and AI agents can parse/modify.
- **Quality gates as phases:** Requirements → design → development (linting, tests) → review (automated + human) → deployment (integration tests, security scans).

**Autonomy model:** Dual oversight — blocking "human-in-the-loop" for high-stakes decisions, asynchronous "human-on-the-loop" for monitoring. Autonomy scales with seniority and risk.

**Task lifecycle:** define → deliver → debrief (or just deliver for light-weight tasks).

**Gate model:** AI-autonomous with automated verification. Test pass = done. Human review for high-risk changes only.

---

## Organisational Topology

Real organisations are not strict trees. They are **overlapping circles of concern** — a security initiative touches every team, a platform service is consumed by multiple products, an SRE concern spans strategy and operations simultaneously.

### Circles, Not Layers

Instead of rigid L1→L2→L3→L4 hierarchy, pd models the organisation as a **topology of circles**. The entity engine's `parent_type_id` provides the primary tree structure (every entity has one parent). Cross-cutting concerns are modelled via `tags[]` stored in entity metadata — these are queryable labels, not structural relationships. The tree handles decomposition and rollup; tags handle circle membership and cross-cutting queries:

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
    │              COMPANY OKRs (shared context)               │
    └──────────────────────────────────────────────────────────┘
```

### How Circles Map to the Entity Engine

Each circle is a scope — a team, domain, product area, or cross-cutting concern. Work items relate to circles via **tags** and **lineage**, not a single rigid tree:

```
Entity relationships (all via uuid, not type_id):
  parent_uuid     → primary lineage (one parent, tree structure)
  entity_tags     → circle membership (many circles, graph structure)
  entity_deps     → dependencies (lateral, within or across circles)
  okr_alignment   → OKR alignment (many-to-many, work items → key results)
```

- A solo developer has one circle (themselves) operating at L3/L4
- A startup has a few overlapping circles, light L1, active L2/L3/L4
- A large org has many circles at every level, with cross-cutting concerns spanning them
- pd adapts to the topology — it doesn't impose a hierarchy

---

## Secretary as Single Entry Point

The secretary agent is pd's **front door** — the single primary entry point for all interaction.

**Relationship to existing secretary:** The current secretary (`commands/secretary.md`, ~700 lines) is a routing engine with a 7-step pipeline (DISCOVER→CLARIFY→TRIAGE→MATCH→REVIEW→RECOMMEND→DELEGATE), specialist fast-paths, YOLO orchestration, and maturity scoring. The CREATE/QUERY/CONTINUE modes described below are **extensions to the existing pipeline**, not a replacement. They add organisational intelligence (parent search, circle awareness, weight recommendation) to the TRIAGE and MATCH steps. The existing routing, specialist fast-paths, and YOLO orchestration remain. Phase 2 implementation extends the secretary incrementally: 2a adds entity registry queries to TRIAGE, 2b adds proactive notifications to RECOMMEND, 2c adds weight/escalation intelligence to MATCH.

### Three Modes

**Mode 1: CREATE — "I need to..."**

Secretary detects work creation intent, triages level/weight/circle, searches entity registry for parent candidates and duplicates, and proposes a recommendation:

```
User: "We need better observability"
Secretary:
  → Scope: multi-feature program
  → Parent: could link to Objective 'enterprise reliability'
  → Weight: standard
  → "Create as L2 project under KR 'P0 <2/mo'?
     Tags: [platform]. Standard weight."
User: "yes"
Secretary: dispatches create-project, links parent, tags circles
```

**Mode 2: QUERY — "What's happening with..."**

Secretary queries entity engine and presents a topology-aware view:

```
User: "How are we doing on reliability?"
Secretary:
  → Finds objective matching "reliability"
  → Computes OKR score from children
  → Surfaces blockers
  → "Objective 'enterprise reliability': score 0.67 🟡
     ├── KR1 'P0 <2/mo': 0.75 🟢 (2/3 features done)
     ├── KR2 '99.9% uptime': 0.45 🟡 (blocked)
     │     └── ⚠ Feature failover blocked 3 days
     └── KR3 'integration tests': 1.0 🟢 ✓"
```

**Mode 3: CONTINUE — "What's next?" / resume work**

Secretary checks current context (branch, active feature, phase) and proposes next action:

```
User: "What should I work on?"
Secretary:
  → Checks: not on feature branch
  → Queries: ready features (planned, unblocked)
  → Queries: ready tasks (parent in deliver, unblocked)
  → "Ready for work:
     Features: 014-dashboard (unblocked, specify phase)
     Tasks: 3 tasks ready under feature:013-alerting
     Backlog: 2 untriaged items"
```

### Secretary Intelligence

Beyond routing, the secretary provides organisational intelligence:

- **Duplicate detection:** "There's already a feature for structured logging (feature:012). Continue that or create new?"
- **Circle awareness:** "This touches the security circle. Should I tag the security team?"
- **Weight recommendation:** "This started as a bug fix but it touches 3 services. Recommend upgrading to standard weight."
- **Escalation detection:** "This task has been blocked for 5 days. Should I flag it on the parent project?"
- **Progress awareness:** "Objective 'enterprise reliability' score dropped to 0.4 — KR2 is blocked. Want me to investigate?"

### Direct Commands (Power-User Shortcuts)

Direct commands (`/pd:specify`, `/pd:design`, etc.) remain as shortcuts that bypass secretary triage. The entry points, ordered by abstraction:

1. **Natural language** → Secretary (primary, recommended for all users)
2. **`/pd:secretary "..."`** → Secretary with explicit hint
3. **`/pd:specify`, `/pd:create-feature`** → Direct to workflow (power users)
4. **MCP tools** → Raw entity engine access (programmatic/dashboards)

### Proactive Communication (System → User)

The entity engine queues notifications on state changes. **Delivery channels** (pd has no daemon — notifications are surfaced at interaction boundaries):

1. **Session-start summary** — reconciliation (already planned in Phase 1) includes queued notifications
2. **Secretary query responses** — secretary appends relevant notifications when answering queries
3. **MCP tool polling** — external dashboards or the UI server can poll for queued notifications

| Event | Example |
|-------|---------|
| **Threshold crossed** | "KR score dropped to 0.35. Cause: 1 blocked feature. Investigate?" |
| **Completion ripple** | "Feature 012 completed. Project P003: 67%. Feature 013 now unblocked." |
| **Anomaly escalation** | "Feature 013 retro flagged auth middleware as fundamentally broken. Create initiative?" |
| **Stale work** | "Feature 014 in design phase for 12 days with no transitions. Blocked? Abandoned?" |

---

## Universal Work Creation

Work emerges everywhere — not just top-down. pd uses a unified creation flow regardless of source.

### Work Sources

| Source | Description | Example |
|--------|------------|---------|
| **Decomposition** | Design at any level creates children | Project design → features |
| **Emergent** | Discovered during execution | Bug found → new task; retro finds systemic issue → new initiative |
| **Ad-hoc** | External input | Customer feedback → backlog → feature; incident → hotfix |
| **Lateral** | Triggered by sibling events | Feature A completes → Feature B unblocks |

### The 4-Step Creation Flow

Every work item, regardless of source or level:

1. **Identify** — Secretary triages: type (initiative/objective/key_result/project/feature/task), weight (full/standard/light), circle(s)
2. **Link** — Entity engine searches for parent candidates. Secretary proposes linkage. User confirms or creates standalone. If no clear parent: goes to backlog.
3. **Register** — Entity created with type, tags, parent_type_id, status=planned, workflow template from type+weight, blocked_by from sibling dependencies, contributes_to for OKR alignment.
4. **Activate** — Status → active, enters first phase of template. Tasks may auto-activate if parent is in Deliver and no blockers.

### Backlog as Organisational Inbox

pd's existing backlog becomes the universal inbox for untriaged work:
- Any user adds via `/pd:add-to-backlog "description"`
- Secretary triages on demand: identify level, weight, circle, parent → promote to work item
- Untriaged items remain visible but don't block anything

---

## Ceremony Weight

Not everything needs a 6-pager. Work weight determines ceremony level, independent of organisational level.

### Three Weights

| Weight | When | Phases | Gates | Artifacts |
|--------|------|--------|-------|-----------|
| **Full** | High risk, novel, cross-circle, strategic | All phases with full review | AI + human at every transition | All artifacts required, retro mandatory |
| **Standard** | Normal work, clear scope, moderate complexity | Key phases with proportional review | AI at key phases, human at boundaries | Core artifacts (spec, design or plan), retro recommended |
| **Light** | Low risk, small scope, well-understood, bounded blast radius | Minimal viable process | Automated verification only (tests, CI) | Brief description + done-when criteria |

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

    # Tactical (L3) — backward compatible
    ("feature", "full"):        ["brainstorm", "specify", "design", "create-plan",
                                 "create-tasks", "implement", "finish"],
    ("feature", "standard"):    ["brainstorm", "specify", "design", "create-plan",
                                 "create-tasks", "implement", "finish"],
    ("feature", "light"):       ["specify", "implement", "finish"],

    # Operational (L4)
    ("task", "standard"):       ["define", "deliver", "debrief"],
    ("task", "light"):          ["deliver"],
}
```

### Weight Escalation

Weight escalation is **manually triggered** — the user or secretary prompts reassessment based on observed complexity. pd cannot automatically detect file counts or service boundaries. Signals that should prompt a user to upgrade:

| Signal | Recommendation |
|--------|---------------|
| Scope creep: user describes expanding scope | "This is growing — upgrade to standard with spec?" |
| Risk: user mentions auth, payment, or data changes | "Suggest standard weight with design review" |
| Cross-circle: user mentions affecting another team | "Needs coordination — upgrade to standard or project?" |
| Duration: user notes work is taking longer than expected | "Consider upgrading to standard" |

Light ≠ no process. Even light work items are registered as entities (tracked, linked, auditable), linked to parents (show up in rollup), given status lifecycle (planned → active → complete), and verified on completion (tests must pass).

---

## Event-Driven Triggers

All work is event-driven. There are no scheduled ceremonies.

**Execution model:** pd is a CLI tool with no daemon or background process. Triggers fire **synchronously at interaction boundaries**: (a) as post-commit hooks in EntityDatabase when entity state is written, (b) at session start during reconciliation, (c) when secretary evaluates a query. This is on-interaction evaluation, not a real-time event loop.

### Trigger Types

| Trigger | Description | Example |
|---------|------------|---------|
| **Decomposition** | Design at one level creates children | "Project design produces features" |
| **Completion** | Work finishing unblocks dependents and updates parent | "Feature A done → Feature B unblocks, project progress updates" |
| **Anomaly** | Debrief surfaces issue, escalates to parent | "Retro finds systemic auth flaw → flags parent objective" |
| **Threshold** | Derived state crosses a boundary | "KR score drops below 0.4 → flag at-risk to objective owner" |
| **Ad-hoc** | Human or external input | "Customer report → backlog → secretary triages → feature" |

### How Triggers Flow

**Decomposition (Design → children):** When any work item's Design phase decomposes into children, the entity engine registers child entities with `parent_type_id`. Children enter their template's first phase. Intent flows through the topology as structured decomposition that preserves parent context.

**Completion (upward rollup):** When a work item completes, the entity engine:
1. Removes it from siblings' `blocked_by` lists (cascade unblock)
2. Recomputes parent's derived state (progress, OKR score, traffic light)
3. If all siblings complete, parent may advance

**Anomaly (upward propagation):** When a Debrief phase identifies a systemic issue, it's flagged on the parent entity's metadata. The parent's next Discover phase includes child anomalies. Toyota's "andon cord" in organisational form.

**Threshold (derived state monitoring):** Parent state is recomputed when children change (synchronous post-commit) and at session start (reconciliation). When a derived metric crosses a threshold, the notification is queued and surfaced on next secretary interaction or session-start summary. This is poll-on-interaction, not continuous monitoring.

**Ad-hoc (backlog inbox):** Work that doesn't fit the current flow goes to backlog. Secretary triages on demand.

### Time as Performance Measurement

pd records timestamps on every phase transition (it already does this via `phase_timing` in `.meta.json`). Time data serves **retrospective analysis**, not planning:

- **Phase duration:** "Design phases for standard features average 2.3 hours" — understanding capacity
- **Lead time:** "Time from creation to completion" — process improvement
- **Blocked duration:** "This feature was blocked for 4 days" — identifying bottlenecks
- **Value velocity:** "This circle delivered 3 objectives this month" — understanding throughput

Time estimates and deadlines are **not workflow gates** — no phase transition is blocked by a date. However, entities may carry optional `target_date` metadata for teams with external commitments (investor updates, product launches, contractual deadlines). Deadlines are metadata, not gates. Value delivered is the primary metric; time data informs retrospective analysis.

---

## OKR Framework

OKRs are the bridge between strategic intent and tactical execution. pd implements OKRs as first-class work items, not a separate system.

### Structure

```
Objective (L1 work item, type=objective)
  ├── KR1 (type=key_result, metric_type=target)
  │     └── Project A (L2, parent=KR1)
  │           ├── Feature 1 (L3)
  │           └── Feature 2 (L3)
  ├── KR2 (type=key_result, metric_type=baseline)
  │     └── Project B (L2, parent=KR2)
  └── KR3 (type=key_result, metric_type=binary)
        └── Feature 3 (L3, parent=KR3)
```

### Key Result Types

| Type | Description | Scoring |
|------|------------|---------|
| **Target metric** | Move a number from X to Y | (current - baseline) / (target - baseline), clamped 0.0-1.0 |
| **Baseline metric** | Establish a measurement that doesn't exist yet | Binary: measured = 1.0, not measured = 0.0 |
| **Milestone** | Multi-step deliverable | Completed steps / total steps |
| **Binary** | Done or not done | 0.0 or 1.0 |

### Scoring Model (Google-inspired)

- **Committed KRs:** Must score 1.0. Anything less is a planning/execution failure.
- **Aspirational KRs:** Target 0.6-0.7. Scoring 1.0 means the goal wasn't ambitious enough.
- **Objective score:** Weighted average of KR scores. Weights configurable (default: equal).
- **Colour coding:** Green (0.7-1.0), Yellow (0.4-0.6), Red (0.0-0.3).

### Event-Driven OKR Lifecycle

OKRs have no fixed cadence. The entity engine provides continuous, real-time state:

- **OKR state is always current:** Child-completion rollup (binary: done/not-done per child) is the only automated scoring. Milestone KRs: completed_children / total_children. Target-metric KRs require manual score updates (external metrics integration is future work). No check-in meeting needed — the entity engine computes rollup on every child state change.
- **OKRs are created when needed:** When strategic intent crystallises, not at quarter boundaries.
- **OKRs are scored when complete:** When all children finish or when the owner decides to score.
- **Review happens on state change:** When a rollup score drops below threshold, the notification is queued and surfaced at next session start or secretary query. Threshold alerting for target-metric KRs requires manual score updates to trigger.
- **Un-scored KRs:** Target-metric KRs without manual score updates default to 0.0. Objective score is computed as weighted average including defaults. Secretary warns: "Objective includes 2 un-scored KRs — scores may be understated."

### Anti-Patterns pd Must Prevent

1. **Output KRs** — "Launch mobile app" is a task, not a key result. KRs describe outcomes: "Achieve 50K MAU on mobile." pd warns when KR text contains activity words (launch, build, implement, complete).
2. **Too many OKRs** — Default limit: 5 objectives, 5 KRs each. Configurable in `pd.local.md`. Secretary warns when exceeding but doesn't block.
3. **OKRs as performance evaluation** — pd explicitly documents that OKR scores are learning tools, not accountability contracts.
4. **Cascading without autonomy** — pd shows parent context but teams create their own OKRs.

---

## Cross-Level Coordination

### Anti-Patterns to Avoid

1. **Top-down cascade without input** — teams copy-paste OKRs instead of thinking critically (Wodtke, Gothelf)
2. **Status theatre** — metrics that only go up, meetings that produce no action
3. **Metric gaming / Goodhart's Law** — pair every quantity metric with a quality counterbalance
4. **Managing dependencies instead of eliminating them** — "restructure teams and architecture to remove coupling" (Scrum.org)
5. **Copying frameworks without context** — Spotify Model was a snapshot, not a framework

### Patterns pd Implements

**Hoshin Kanri Catchball (Bidirectional Alignment):** Not top-down dictation. Each level receives intent from above (context, constraints, objectives), proposes how to achieve it, and negotiates until aligned. "Ideas shaped by teams are more likely to be executed with care and energy."

**Mission Command (Auftragstaktik):** Give clearly defined objective, timeframe, and resources. Do NOT give how to achieve it. Subordinates interpret intent within their operational context. Requires genuine tolerance for failure.

**Netflix "Highly Aligned, Loosely Coupled":** Provide context (strategy, metrics, assumptions, stakes) rather than control (approvals, committees). Every decision has an "informed captain" who must "farm for dissent."

**Feedback Propagation:**
- **Upward:** L4 task retro → L3 feature retro aggregates → L2 project retro identifies systemic issues → L1 strategy review reassesses assumptions (double-loop learning)
- **Downward:** L1 OKR targets constrain L2 project scope → L2 milestones constrain L3 feature priorities → L3 design constrains L4 task implementation
- **Lateral:** Feature A completes → Feature B unblocks. KR at risk → flag to objective owner for rebalancing.

---

## Data Model

### Entity Hierarchy

```
Initiative (L1) — optional strategic container
  └── Objective (L1) — what we want to achieve
        └── Key Result (L1/L2 bridge) — how we measure success
              └── Project (L2) — coordinated program of work
                    └── Feature (L3) — individual deliverable
                          └── Task (L4) — unit of execution
```

Every node is a **Work Item** in the entity registry — same schema, same workflow engine, different type and level.

### Two-ID System: System Identity vs Human Identity

pd currently has a `uuid` PRIMARY KEY column that's barely used — everything references `type_id` (a human-readable natural key) instead. This conflates identity with display, making entities un-renamable and cross-references fragile. The fix: **uuid is identity, type_id is display.**

**System ID (uuid) — source of truth:**
- Generated: UUIDv4 (already exists in schema, no changes needed; sortability via `created_at`)
- Immutable: never changes after creation
- Carries no meaning: opaque identifier
- Used for: ALL internal references — parent linkage, junction tables (dependencies, tags, OKR alignment), foreign keys, workflow_phases primary key
- Never shown to users unless they explicitly ask for it

**Human ID (type_id / entity_id) — display and search:**
- Format: `{type}:{seq}-{slug}` (standardised across all entity types)
- `seq`: per-type sequential counter, best-effort ordering, gaps OK
- `slug`: max 30 chars, lowercase, hyphens, from name/description at creation
- Mutable: slug can be renamed without breaking any references (uuid is the FK)
- Used for: CLI display, user references, agent/LLM quick searching, conversation
- Partial matching: `feature:052` resolves to `feature:052-structured-logging`

**Standardised human ID format (all types):**

| Type | Current format | New format |
|------|---------------|------------|
| backlog | `backlog:00008` (5-digit) | `backlog:008-webhook-retry` |
| brainstorm | `brainstorm:20260309-160000-brainstorm-backlog-...` (40+ chars) | `brainstorm:002-fractal-work-mgmt` |
| project | `project:P003-observability` (redundant P prefix) | `project:003-observability` |
| feature | `feature:052-structured-logging` (already clean) | `feature:052-structured-logging` (unchanged) |
| initiative | (new) | `initiative:001-enterprise-reliability` |
| objective | (new) | `objective:001-reduce-incidents` |
| key_result | (new) | `key_result:001-p0-under-two` |
| task | (new) | `task:001-add-log-fields` |

**How references work:**
```
USER TYPES:      "depends on feature:052"
MCP/SECRETARY:   resolve "feature:052*" → uuid "01JNQX5K8R..."
ENTITY ENGINE:   stores uuid in entity_dependencies junction table
DISPLAY:         shows "feature:052-structured-logging" to user
```

**Migration:** Existing entities retain their current type_ids (no rename). Internal references (parent, blocked_by) migrate from type_id to uuid. New entities use the standardised format. MCP tools accept both uuid and type_id, resolve to uuid internally.

### Entity Schema Extension

Current entity types: `backlog`, `brainstorm`, `project`, `feature`
New entity types: `initiative`, `objective`, `key_result`, `task`

Each entity carries:
- `uuid` — **system identity**, immutable, all internal references
- `type_id` — **human identity**, `{type}:{seq}-{slug}`, display and search
- `entity_type` — determines lifecycle template and gate stringency
- `level` — L1/L2/L3/L4, derived from entity_type
- `lifecycle_phase` — current 5D phase (or existing 7-phase for L3 features)
- `status` — draft | planned | active | blocked | completed | abandoned
- `parent_uuid` — primary lineage (one parent, references uuid)
- `owner` — person or team responsible
- `metadata` — flexible JSON for type-specific fields (OKR scores, risk registers, etc.)

Relationship tables (all reference uuid, not type_id):
- `entity_tags` (entity_uuid, tag) — circle membership
- `entity_dependencies` (entity_uuid, blocked_by_uuid) — sibling dependencies
- `entity_okr_alignment` (entity_uuid, key_result_uuid) — OKR alignment

### Schema Migration Reality

The PRD's data model changes require **destructive migrations** (table rebuild with data copy), not additive changes:

1. **UUID as primary reference:** Migrate all foreign key references from `type_id` to `uuid`. The `parent_uuid` column already exists in the schema but is underused — make it the canonical parent reference. `parent_type_id` becomes a denormalised display field (updated on rename, not used for joins). `workflow_phases.type_id` gains a companion `workflow_phases.uuid` column as the primary key.

2. **Entity type expansion:** Drop the SQL CHECK constraint on `entity_type` in favour of Python-only validation (`_validate_entity_type`). This makes future type additions non-breaking (no table rebuild). Add `initiative`, `objective`, `key_result`, `task` to `VALID_ENTITY_TYPES`. Trade-off: weaker DB-level integrity (raw SQL bypasses Python validation). Mitigated by migration-time consistency audit.

3. **Workflow phase expansion:** The `workflow_phases` table CHECK constraint only allows the 7 feature phases plus brainstorm/backlog lifecycle phases. The 5D phase names (`discover`, `define`, `design`, `deliver`, `debrief`) must be added — table rebuild. Similarly expand mode CHECK to include `light`. Combine both into a single migration.

4. **Junction tables:** New tables using uuid as foreign keys:
   - `entity_tags` (entity_uuid TEXT, tag TEXT) — indexed on both columns
   - `entity_dependencies` (entity_uuid TEXT, blocked_by_uuid TEXT) — indexed, with cycle detection
   - `entity_okr_alignment` (entity_uuid TEXT, key_result_uuid TEXT) — indexed

   **Rationale:** Dependency enforcement (blocked_by gates at Deliver) and cascade unblock (completion → find dependents) require efficient indexed lookups. Junction tables from the start, not deferred.

5. **Human ID standardisation:** Add a central ID generator that produces `{seq}-{slug}` for all entity types. Per-type sequential counter stored in `_metadata` table (key: `next_seq_{entity_type}`). Existing entities retain their current type_ids. New entities use the standardised format.

6. **Workflow engine generalisation:** The current `WorkflowStateEngine` is deeply coupled to features: `_extract_slug` hardcodes `features/` path, `_get_existing_artifacts` uses feature-specific `HARD_PREREQUISITES`, `_evaluate_gates` uses feature-specific guard IDs, `complete_phase` validates against the 7-phase `_PHASE_VALUES`, `_iter_meta_jsons` globs `features/*/.meta.json`. Requires a new `EntityWorkflowEngine` class (strategy pattern) with type-specific backends. Existing `WorkflowStateEngine` frozen for L3 features. Phased across implementation.

7. **Transition gate compatibility with light weight:** Light-weight features (`["specify", "implement", "finish"]`) skip phases that existing HARD_PREREQUISITES and soft prerequisite guards expect. Gate system parameterised by entity's active template — HARD_PREREQUISITES for a phase filters to only artifacts produced by phases in the active template. Example: for light features, `implement` requires only `spec.md` (from `specify`); `design.md`, `plan.md`, and `tasks.md` are not required because `design`, `create-plan`, and `create-tasks` are not in the template.

8. **Testing strategy for new entity types:** Each new type (initiative, objective, key_result, task) needs: unit tests for registration/lifecycle, integration tests for parent-child across levels, workflow engine tests for 5D phase transitions, gate tests for non-feature phases, and reconciliation tests. Existing 1100+ tests validate L3; new types need proportional coverage. EntityWorkflowEngine design is deferred to the design phase — key open questions: strategy interface, per-type gate configuration, artifact prerequisite model for non-feature entities.

9. **Data backup:** Migration scripts automatically back up the DB file (`entities.db.bak.{timestamp}`) before any destructive operation. Rollback = restore backup file. `.meta.json` files are tracked in git — `git stash` before migration provides filesystem rollback.

### Entity Engine Responsibilities

The entity engine is the **connective tissue** that makes circles coherent:

| Responsibility | Today | Future |
|---------------|-------|--------|
| Store entities | ✓ (4 types) | ✓ (8 types) |
| Parent-child lineage | ✓ | ✓ (deeper: L1→L2→L3→L4) |
| Status tracking | ✓ | ✓ + lifecycle phase tracking |
| Trigger propagation | ✗ | ✓ (completion→unblock, anomaly→parent) |
| State derivation | ✗ | ✓ (rollup, OKR scoring, traffic light) |
| Constraint enforcement | ✗ | ✓ (blocked_by gates at Deliver) |
| Cross-circle queries | ✗ | ✓ (portfolio views, dependency maps) |

---

## What Changes for pd

Each phase is independently shippable with standalone value. Later phases are not required — they are unlocked, not mandated.

### Phase 1a: Depth Fixes (Zero Schema Changes)

**Standalone value:** Existing users get quality fixes immediately — cleaner kanban, honest health checks, session-start summaries.

Fix 6 depth bugs — immediately shippable, no migration risk:
1. **Field validation** — `init_feature_state()` rejects empty identity fields with ValueError
2. **Frontmatter health** — remove dead `reconcile_status` frontmatter check
3. **Maintenance mode** — add `PD_MAINTENANCE=1` bypass to meta-json-guard
4. **Kanban derivation** — implement `derive_kanban()`, replace all independent kanban sets
5. **Artifact completeness** — soft verification warnings on feature finish
6. **Reconciliation reporting** — surface session-start reconciliation summary

### Phase 1b: Schema Foundation

**Standalone value:** Enables all future entity types. UUID-based references make entities renamable. Junction tables enable dependency tracking. Gate parameterisation enables light-weight features (bugfix mode).

Two-ID system:
- Migrate all internal references from `type_id` to `uuid` (parent linkage, workflow_phases FK)
- `parent_uuid` becomes canonical parent reference; `parent_type_id` becomes denormalised display field
- Central ID generator for standardised human IDs (`{seq}-{slug}` per type)
- MCP tools accept both uuid and type_id, resolve to uuid internally

Destructive migrations (combined into single migration to minimise rebuilds):
- Drop entity_type CHECK constraint → Python-only validation (future-proof)
- Expand `VALID_ENTITY_TYPES` to include `initiative`, `objective`, `key_result`, `task`
- Expand workflow_phase CHECK to include 5D phase names
- Expand mode CHECK to include `light`
- Add junction tables (uuid-keyed): `entity_tags`, `entity_dependencies`, `entity_okr_alignment`
- Update FTS sync code for new entity types
- Add workflow templates registry with weight-specific templates
- Parameterise gate evaluation to respect entity's active template (light features skip phases)

### Phase 2: Secretary + Universal Work Creation

**Standalone value:** Users describe what they need in natural language instead of picking commands. Secretary finds parents, detects duplicates, recommends weight.

Transform secretary into organisational router (incremental extension of existing 7-step pipeline):
- Level detection from request scope and user context
- Parent candidate search via entity registry
- Duplicate/overlap detection
- Weight recommendation based on scope, risk, and blast radius
- Weight escalation detection for in-progress work
- Proactive notifications (threshold, completion ripple, anomaly, stale work)

Universal work creation flow:
- 4-step identify → link → register → activate pattern at every level
- Backlog as organisational inbox with on-demand triage

### Phase 3: L4 Operational — Tasks as Work Items

**Standalone value:** AI agents can query ready tasks and execute autonomously. Task dependencies are enforced. Task completion updates feature progress.

Elevate tasks from flat markdown to first-class entities:
- Each task in tasks.md registered as entity with `type=task`, `parent=feature:{id}`
- Mini-lifecycle per weight: light = deliver only; standard = define → deliver → debrief
- Dependencies between tasks tracked and enforced via `blocked_by`
- Agent-executable: AI agents query "ready tasks" and execute autonomously
- Opt-in: simple tasks stay as markdown. Only promoted tasks get entity lifecycle.

### Phase 4: L2 Program — Living Projects

**Standalone value:** Projects track real progress, milestones are checkpoints not metadata, dependencies are enforced, traffic-light status answers "are we on track?"

Make projects living entities instead of write-once containers:
- Projects get their own 5D lifecycle (discover through debrief)
- Milestones become checkpoints within project lifecycle
- Traffic-light status (GREEN/AMBER/RED) derived from child feature progress
- Risk register support in project metadata
- Dependency enforcement: feature can't enter Deliver if `blocked_by` siblings aren't complete
- Cross-circle tagging: projects can span multiple circles

### Phase 5: L1 Strategic — Initiatives & OKRs

**Standalone value:** Strategic intent is captured and linked to execution. OKR scores computed from child completion. "Are we achieving our objectives?" is answerable.

Add the strategic layer:
- **Initiatives** — strategic bets with 5D lifecycle, Amazon-style narrative documents
- **Objectives** — created when strategic intent crystallises
- **Key Results** — measurable outcomes with type (target/baseline/milestone/binary), scoring 0.0-1.0, scored on completion not calendar
- OKR anti-pattern detection (output KRs, too many OKRs, activity words)
- Child-completion rollup as automated scoring; target-metric scoring is manual
- Portfolio view: initiative health, OKR progress, cross-circle dependencies
- Strategic advisors: reuse existing advisory framework at L1

### Phase 6: Cross-Topology Intelligence

**Standalone value:** The full loop — completing work at any level ripples through the topology. Anomalies propagate. The organisation is queryable as one coherent system.

- **Hoshin Kanri catchball** — when creating children, show parent intent; when completing children, update parent progress
- **Cascade unblock** — completing a work item unblocks dependents within and across circles
- **Progress rollup** — parent health derived from children status (OKR scores from child completion)
- **Anomaly propagation** — debrief findings flagged on parent entity for next Discover phase
- **Workspace scoping** — workspace_id column for multi-project isolation
- **Circle-aware queries** — portfolio views filtered by circle, cross-circle dependency maps

---

## What Does NOT Change

- **L3 tactical behaviour** — the existing 7-phase feature lifecycle behaviour is preserved: same phase names, same gates, same artifacts, same test suite passing. Implementation will change (tables rebuilt, engine refactored into `EntityWorkflowEngine` with L3-specific backend), but observable behaviour is identical. "No backward compatibility" (CLAUDE.md) applies to internal implementation; L3 user-facing behaviour is frozen.
- **Entity lineage model** — same parent-child tree concept, migrated from `parent_type_id` to `parent_uuid` as canonical reference, extended with tags for cross-circle membership
- **Agent/reviewer architecture** — same dispatch pattern, extended with level-appropriate reviewers
- **Knowledge bank** — same structure, extended with level and circle tags
- **Plugin portability** — no hardcoded paths, same two-location glob pattern
- **Kanban** — remains a view (UI projection of entity state), not an architectural concern. Can be retrofitted as a dashboard later.

---

## Bootstrapping (Cold-Start)

A new user has zero entities, zero circles, zero OKRs. Secretary's intelligence features (duplicate detection, parent search) depend on a populated registry. The bootstrapping flow:

1. **Zero-entity state:** Secretary works exactly like today's pd — routes to commands without context enrichment. `/pd:create-feature` works standalone with no parent linking. This is the current user experience, unchanged.
2. **First project:** When a user creates their first project, secretary begins offering parent linking for new features. Circles emerge organically from work, not from upfront configuration.
3. **First OKR (opt-in):** Only users who explicitly create objectives/KRs get L1 features. No setup wizard, no mandatory configuration.
4. **Circles are tags, not setup:** Circles don't need to be "created" — they emerge when entities are tagged. Tagging is optional metadata, not a required step.

The principle: **pd works immediately with zero configuration. Intelligence improves as entities accumulate.**

## Migration for Existing Users

Existing pd users have features, projects, brainstorms, and backlog items in their entity DB. The migration path:

1. **Phase 1a (bugfixes):** Zero schema changes. Existing users get quality improvements automatically. No migration needed.
2. **Phase 1b (schema):** Automatic, tested migration. The migration script: (a) backs up the DB file before modifying, (b) runs against a copy first to verify, (c) preserves all existing entity data and type_ids, (d) adds new columns/tables without affecting existing rows. Existing entities retain their current format — no forced rename.
3. **New entity types are invisible:** `initiative`, `objective`, `key_result`, `task` types exist in the schema but no entities of those types appear unless the user explicitly creates them.
4. **Secretary behaves identically** until L2+ entities exist in the registry. With zero initiatives/objectives/KRs, the CREATE/QUERY/CONTINUE modes reduce to current routing behaviour.
5. **All existing commands work unchanged.** No command is removed or renamed.

## L1/L2 Practicality in a CLI Tool

Strategic planning (initiatives, OKRs) is inherently collaborative and often happens in meetings, shared documents, and visual tools. pd is a CLI tool. The target personas and interaction models:

- **Solo developer / small team:** L1/L2 is lightweight personal planning. OKRs are personal goals tracked as entities. Projects coordinate multi-feature efforts. The CLI is the natural interface.
- **Team within a larger org:** L1/L2 OKRs may be imported from external tools (Notion, Linear, Google Docs) or created in pd as a local tracking mirror. pd provides the execution engine; the org may use other tools for collaborative planning.
- **pd UI server:** The existing UI server (`plugins/pd/ui/`) provides a web dashboard for entity and workflow visualisation. L1/L2 portfolio views are natural extensions of this existing web UI, not CLI-only.

L1/L2 value in pd is **execution tracking and cross-level linkage**, not replacing collaborative planning tools. The CLI creates and manages entities; visualisation happens in the UI server or via MCP tool integration with external dashboards.

---

## Risks and Mitigations

### Robustness Concerns

**Dependency cycle detection:** Parent-child lineage uses depth-guarded recursive CTEs (depth < 10) for cycle prevention. `blocked_by` forms a separate DAG that needs its own cycle detection — a `blocked_by` cycle (A blocked by B blocked by C blocked by A) would deadlock. Cycle detection must validate the full `blocked_by` graph on every update, not just the parent chain.

**Cascading rollup fan-out:** Completing one entity triggers parent recalculation up the ancestor chain. For a 6-level hierarchy this is at most 5 recalculations, each a simple aggregate query. This is bounded and fast for CLI-scale entity counts.

**Orphan handling on parent abandonment:** When a parent entity is abandoned, its children need a defined policy. Decision: **guard by default, cascade on explicit request**. Abandoning an entity with active children is blocked unless `--cascade` flag is provided, which cascade-abandons all descendants in a single transaction. This preserves pd's guard philosophy while providing a practical escape hatch for cleanup.

**Concurrency:** SQLite WAL mode with 5s busy timeout handles write serialisation. Cascading triggers (completion → unblock → rollup) involve read-modify-write across rows and must use `BEGIN IMMEDIATE` transactions to prevent stale reads between concurrent sessions.

**Rollup computation model:** Parent state is recomputed **synchronously on child state change** (post-commit in `EntityDatabase`), not via dirty flags. pd is a CLI tool with bounded entity counts — the fan-out concern is premature optimisation. For a 6-level hierarchy with ~100 entities per level, a single completion triggers at most 5 parent recalculations (one per ancestor level). Each recalculation is a simple `SELECT COUNT(*) ... GROUP BY status` query. If performance becomes an issue at scale, dirty-flag batching can be added as an optimisation without changing the API.

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Scope creep — trying to build Jira | High | High | Each phase is independently valuable and shippable. Phase 1 is pure bugfixes. |
| L1/L2 unused — solo devs don't need executive layer | Medium | Low | L1/L2 are opt-in. Solo developers continue using L3/L4 only. Zero overhead if unused. |
| Schema migration breaks existing features | Medium | High | Table-rebuild migrations (not additive). Each migration tested against DB copy before applying. All 1100+ tests must pass after each migration. Rollback via DB backup. |
| OKR scoring noisy without real metrics | Medium | Medium | Start with manual scoring + child-completion rollup. External metrics integration is future work. |
| Task-level lifecycle adds friction | Medium | Medium | L4 is opt-in. Simple tasks stay as markdown. Only promoted tasks get lifecycle. |
| Cross-level coordination becomes status theatre | Medium | High | Follow Netflix: context not control. Catchball not cascade. Event-driven not ceremony-driven. |
| Secretary becomes bottleneck | Low | High | Direct commands remain as bypass. Secretary is recommended, not required. |
| Workflow engine generalisation is massive | High | High | Phase 1 is depth fixes only (no engine changes). Engine generalisation is phased across Phases 3-5 with type-specific parameterisation, not a big-bang rewrite. |
| Cascading rollup creates performance issues | Low | Medium | Synchronous rollup bounded at 5 ancestor levels. Simple aggregate queries. Dirty-flag batching added later if needed. |
| Destructive schema migrations corrupt data | Low | Critical | Each migration tested against DB copy. Backup before applying. Rollback documented. All 1100+ tests must pass. |

---

## Success Metrics

1. **L3 preserved:** All existing tests pass unchanged (710+ entity registry, 309 workflow engine, 118 reconciliation)
2. **L4 operational:** Tasks registered as entities with parent lineage, executed by AI agents, marked complete
3. **L2 living projects:** Milestones track progress, traffic-light computes from features, dependencies enforced
4. **L1 OKRs:** Objectives and Key Results created, scored 0.0-1.0, linked to projects, anti-pattern warnings
5. **Cross-topology:** Completing a feature updates parent project. Completing a project updates parent KR. Retro findings propagate to parent.
6. **Secretary as entry point:** Users can create, query, and continue work through natural language
7. **Backward compatible:** A developer who ignores L1/L2/L4 sees zero change in their L3 workflow
8. **Cold-start:** With zero entities, `/pd:create-feature` works identically to current behaviour (no parent linking offered). After creating one project, next `/pd:create-feature` offers parent linking.
9. **Robustness:** Cycle detection rejects circular `blocked_by` chains. Orphan guard prevents abandoning entity with active children (without `--cascade`). Rollup recomputes within 500ms for graphs up to 1000 entities.

---

## Research Sources

### Executive Operations
- [Amazon PR/FAQ Working Backwards](https://workingbackwards.com/concepts/working-backwards-pr-faq-process/)
- [Amazon Monthly/Quarterly Business Reviews](https://workingbackwards.com/concepts/quarterly-monthly-business-reviews/)
- [Bezos Type 1/Type 2 Decisions](https://fs.blog/reversible-irreversible-decisions/)
- [David Sacks Operating Cadence](https://www.capitaly.vc/blog/david-sacks-operating-cadence-weekly-metrics-okrs-ceo-dashboard)
- [Stripe Operating System](https://www.lennysnewsletter.com/p/lessons-from-scaling-stripe-tactics)
- [Netflix Culture](https://jobs.netflix.com/culture)
- [Shape Up](https://basecamp.com/shapeup)
- [How Linear Builds Product](https://www.lennysnewsletter.com/p/how-linear-builds-product)

### OKR Frameworks
- [Google OKR Playbook](https://www.whatmatters.com/resources/google-okr-playbook)
- [Google re:Work OKR Guide](https://rework.withgoogle.com/intl/en/guides/set-goals-with-okrs)
- [Cascading OKRs at Scale](https://cwodtke.medium.com/cascading-okrs-at-scale-5b1335812a32)
- [OKR Lineage](https://jeffgothelf.com/blog/aligning-not-cascading-okrs-with-an-okr-lineage/)
- [5 Ways Companies Misuse OKRs](https://itamargilad.com/5-ways-your-company-may-be-misusing-okrs/)
- [Key Result Types](https://www.perdoo.com/resources/blog/different-types-of-key-results-and-when-to-use-them)
- [NCT Framework](https://mooncamp.com/blog/nct-vs-okr)
- [V2MOM Framework](https://www.salesforce.com/blog/how-to-create-alignment-within-your-company/)

### Cross-Level Coordination
- [Strategy Execution Gap](https://gwork.io/blog/the-strategy-execution-gap-why-67-of-strategies-fail-and-how-to-close-it/)
- [Hoshin Kanri Catchball](https://businessmap.io/lean-management/hoshin-kanri/what-is-catchball)
- [Mission Command (HBR)](https://hbr.org/2010/11/mission-command-an-organizat)
- [Eliminate Dependencies](https://www.scrum.org/resources/blog/eliminate-dependencies-dont-manage-them)
- [Metric Anti-Patterns](https://kpitree.co/guides/strategy-culture/metric-anti-patterns)
- [Spotify Model Failures](https://www.jeremiahlee.com/posts/failed-squad-goals/)

### Program Management
- [Shopify GSD](https://www.lennysnewsletter.com/p/how-shopify-builds-product)
- [Shopify Engineering Programs](https://shopify.engineering/running-engineering-program-guide)
- [OKR Weekly Check-Ins](https://quantive.com/resources/articles/okr-cycle)
- [Status Update Framework](https://winningpresentations.com/project-status-update-framework/)

### Operational/IC Execution
- [Spotify Honk Agent](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1)
- [Spotify Agent Feedback Loops](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)
- [MDTM Explained](https://github.com/jezweb/roo-commander/wiki/02_Core_Concepts-03_MDTM_Explained)
- [Agentic Manifesto](https://caseywest.com/the-agentic-manifesto/)
- [Pipeline Quality Gates](https://www.infoq.com/articles/pipeline-quality-gates/)
- [Spotify Top Devs](https://techcrunch.com/2026/02/12/spotify-says-its-best-developers-havent-written-a-line-of-code-since-december-thanks-to-ai/)

### Viable System Model & Recursive Governance
- [Stafford Beer, "Brain of the Firm" (1972)](https://metaphorum.org/staffords-work/viable-system-model) — Foundational VSM text, pd's theoretical basis
- [Patrick Hoverstadt, "The Fractal Organization" (2008)](https://onlinelibrary.wiley.com/doi/book/10.1002/9781119208884) — Practical VSM application to organisations
- [Bresser, "Fractal Governance" (2026, SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6011775) — Recent academic validation of fractal governance at scale
- [VSM and Software Teams (Kerr, 2022)](https://jessitron.com/2022/08/28/the-viable-systems-model-and-where-my-team-fits/) — S2-S5 must not become viable systems themselves
- [Agentic Coding VSM (Kellogg, 2026)](https://timkellogg.me/blog/2026/01/20/agentic-coding-vsm) — VSM mapped to AI agent architecture with algedonic signals
- [VSM for Enterprise Agentic Systems](https://medium.com/@magorelkin/stafford-beers-viable-system-model-for-building-enterprise-agentic-systems-81982d6f59c0) — S1-S5 mapped to multi-agent enterprise architectures
- [Viable Systems (Elixir implementation)](https://github.com/viable-systems) — Open-source VSM with Actor Model and Event Sourcing
- [Double-Loop Learning (Argyris)](https://infed.org/dir/welcome/chris-argyris-theories-of-action-double-loop-learning-and-organizational-learning/) — Operational anomalies triggering strategic reassessment
- [Wardley Mapping + VSM](https://www.wardleyleadershipstrategies.com/blog/ai-and-leadership/cybernetic-ai-leadership-with-the-viable-system-model) — Strategy mapping combined with recursive governance

### Organisational Frameworks
- [Sociocracy 3.0 Fractal Organization](https://patterns.sociocracy30.org/fractal-organization.html)
- [SAFe Analysis (PMI)](https://www.pmi.org/disciplined-agile/da-flex-toc/the-good-the-bad-and-the-ugly-of-safe)
- [PMI Strategy-Execution Gap 2025](https://www.pmi.org/about/press-media/2025/new-pmi-research-reveals-strategy-execution-gap-is-undermining-transformation-and-how-to-close-it)
- [Team Topologies](https://teamtopologies.com/key-concepts) — Stream-aligned teams as S1, platform teams as S2
- [OpenProject Work Packages](https://www.openproject.org/docs/user-guide/work-packages/) — Unified entity types with per-type workflows

### Military Command & Control
- [C2SIM Standard (SISO-STD-019-2020)](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-019-2020_c2sim.pdf) — NATO standard for bidirectional intent/status data model
- [US Army C2 Concept 2028](https://api.army.mil/e2/c/downloads/2021/10/06/ffd892d0/afc-concept-for-command-and-control-2028-pursuing-decision-dominance-oct21.pdf) — Decision dominance through standardised data schemas
- [JADC2 and Mission Command](https://www.hudson.org/national-security-defense/do-d-s-jadc2-strategy-should-empower-mission-command) — Adaptive command relationships outperform fixed hierarchy

### Agent Orchestration & Decomposition
- [Anthropic Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) — Orchestrator-worker, 90.2% improvement over single-agent
- [Anthropic Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — 5 composable patterns: chaining, routing, parallelisation, orchestrator-workers, evaluator-optimizer
- [Magentic-One (Microsoft)](https://arxiv.org/html/2411.04468v1) — Dual-ledger task decomposition with stall detection and re-planning
- [Agent-Oriented Planning (ICLR 2025)](https://arxiv.org/abs/2410.02189) — Solvability, completeness, non-redundancy principles
- [TDAG: Dynamic Task Decomposition](https://arxiv.org/abs/2402.10178) — Dynamic agent generation per subtask at runtime
- [Martin Fowler: Humans and Agents](https://martinfowler.com/articles/exploring-gen-ai/humans-and-agents.html) — Human-on-the-loop, agentic flywheel
- [Agent Harness Engineering (2026)](https://aakashgupta.medium.com/2025-was-agents-2026-is-agent-harnesses-heres-why-that-changes-everything-073e9877655e) — "2025 was agents, 2026 is agent harnesses"

### Codebase Analysis (pd current state)
- 4 entity types, 28 skills, 28 agents, 29 commands
- 43 transition guards, 7-phase sequence (standard/full modes only)
- kanban: 8 columns defined, 3 unused (agent_review, human_review, blocked)
- Two competing kanban derivations (STATUS_TO_KANBAN vs FEATURE_PHASE_TO_KANBAN)
- depends_on_features: stored but only consumed by YOLO stop hook
- Project milestones: write-once at decomposition, never read back
- OKR support: non-existent
- Task lifecycle: non-existent (flat markdown checklist)
