# pd Plugin

> A Claude Code plugin that turns ideas into shipped features through structured phases — brainstorm, spec, design, plan, implement — with built-in quality gates, semantic memory, and autonomous operation.

## What It Does

pd guides features from idea to merge through proven phases. Every phase has AI reviewers that catch issues before they compound. The plugin learns from retrospectives — memory persists across sessions and projects. It can run fully autonomously (YOLO mode) or step-by-step with user confirmation at each gate. Domain knowledge modules cover game design, crypto/DeFi, and data science.

## Installation

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Claude Code | latest | The CLI tool from Anthropic |
| Python | 3.10+ | Required for semantic memory. Linux: also install `python3-venv` |
| git | any | Required |

Optional: `rsync` and `gtimeout` (macOS: `brew install coreutils`).

### Install

```bash
/plugin marketplace add clthuang/pedantic-drip
/plugin install pd@my-local-plugins
```

Core dependencies auto-install on first session.

### Setup semantic memory (recommended)

The plugin auto-installs core dependencies on first launch. For semantic search, configure an embedding provider:

```bash
# Find your plugin root and run the interactive setup
bash "$(ls -d ~/.claude/plugins/cache/*/pd/*/scripts/setup.sh 2>/dev/null | head -1)"
```

The setup walks through provider selection, API key configuration, and project initialization.

| Provider | API Key | Notes |
|----------|---------|-------|
| gemini | `GEMINI_API_KEY` | Free tier available (default) |
| none | — | Disable semantic search |

### Troubleshooting

```bash
bash "$(ls -d ~/.claude/plugins/cache/*/pd/*/scripts/doctor.sh 2>/dev/null | head -1)"
```

Read-only health check across 5 categories (system prerequisites, plugin environment, embedding provider, memory system, project context) with OS-specific fix commands.

## Quick Start

**Just describe what you need:**
```bash
/pd:secretary "add email validation to the signup form"
```
Secretary routes your request to the right workflow phase or specialist automatically.

**Or start directly:**
```bash
/pd:brainstorm "your idea here"       # Explore an idea
/pd:create-feature "add user auth"    # Build something
```

Then follow the phases:
```
/pd:specify → /pd:design → /pd:create-plan → /pd:create-tasks → /pd:implement → /pd:finish-feature
```

## Key Features

### Autonomous Operation (YOLO Mode)

```bash
/pd:secretary mode yolo              # Enable autonomous mode
/pd:secretary orchestrate <desc>     # Build end-to-end without pausing
/pd:secretary continue               # Resume from last completed phase
```

All quality gates (reviewers, phase validators) still run — YOLO mode only bypasses user confirmation at phase transitions. Safety boundaries stop execution on review failures, merge conflicts, or missing prerequisites.

**Modes:** `manual` (default) | `aware` (session hints) | `yolo` (fully autonomous)

### Semantic Memory

Three MCP tools persist and leverage learnings across sessions:

| Tool | Purpose |
|------|---------|
| `store_memory` | Save a pattern, anti-pattern, or heuristic to long-term memory |
| `search_memory` | Search past learnings by topic using semantic similarity |
| `record_influence` | Record that a retrieved memory influenced a subagent dispatch, improving future ranking |

Memory entries are injected automatically at session start. Duplicate entries are suppressed at capture time using cosine similarity (configurable via `memory_dedup_threshold`). The global store (`~/.claude/pd/memory/`) accumulates knowledge across all projects. See [README_FOR_DEV.md](./README_FOR_DEV.md) for configuration.

### Domain Knowledge

Built-in specialist knowledge for brainstorming and code review:
- **Game design** — core loop analysis, engagement strategy, aesthetic direction, feasibility
- **Crypto/DeFi** — protocol comparison, tokenomics, market strategy, risk assessment
- **Data science** — methodology assessment, pitfall analysis, modeling approach, DS code review

### Kanban Board (UI Server)

The plugin auto-starts a local Kanban board at `http://localhost:8718/` on every session start. The board shows all features, brainstorms, backlog items, and projects with their workflow phases and lineage in real time. No manual setup required.

Configure via `.claude/pd.local.md`:
- `ui_server_enabled: false` — disable auto-start
- `ui_server_port: 8718` — change the port

### Specialist Teams

`/pd:create-specialist-team` assembles ephemeral multi-perspective teams for complex tasks that need diverse expertise.

## Commands

### Core Workflow

| Command | Purpose |
|---------|---------|
| `/pd:brainstorm [topic]` | Explore ideas, produce evidence-backed PRD |
| `/pd:create-feature <desc>` | Skip brainstorming, create feature directly |
| `/pd:create-project <prd>` | Create project from PRD with AI-driven decomposition into features |
| `/pd:specify` | Write requirements (spec.md) |
| `/pd:design` | Define architecture (design.md) |
| `/pd:create-plan` | Plan implementation (plan.md) |
| `/pd:create-tasks` | Break into tasks (tasks.md) |
| `/pd:implement` | Write code with TDD and review |
| `/pd:abandon-feature` | Transition a feature to abandoned status |
| `/pd:finish-feature` | Merge, run retro, cleanup branch (pd features) |
| `/pd:wrap-up` | Wrap up implementation - review, retro, merge or PR |

### Utilities

| Command | Purpose |
|---------|---------|
| `/pd:show-lineage` | Display entity lineage tree for the current feature branch or a specified entity |
| `/pd:show-status` | See current feature progress |
| `/pd:list-features` | List active features and branches |
| `/pd:retrospect` | Run retrospective on a feature |
| `/pd:add-to-backlog` | Capture ad-hoc ideas and todos |
| `/pd:remember` | Capture a learning to long-term memory |
| `/pd:cleanup-brainstorms` | Delete old brainstorm scratch files |
| `/pd:doctor` | Run diagnostic checks on pd workspace health |
| `/pd:secretary` | Intelligent task routing to agents and skills (supports YOLO mode with orchestrate subcommand) |
| `/pd:create-specialist-team` | Create ephemeral specialist teams for complex tasks |
| `/pd:root-cause-analysis` | Investigate bugs systematically |
| `/pd:promptimize [file-path or inline text]` | Review a prompt against best practices and return an improved version |
| `/pd:refresh-prompt-guidelines` | Scout latest prompt engineering best practices and update the guidelines document |
| `/pd:review-ds-analysis <file>` | Review data analysis for statistical pitfalls |
| `/pd:review-ds-code <file>` | Review DS Python code for anti-patterns |
| `/pd:init-ds-project <name>` | Scaffold a new data science project |
| `/pd:generate-docs` | Generate three-tier documentation scaffold or update existing docs |
| `/pd:sync-cache` | Sync plugin source files to cache |
| `/pd:yolo [on\|off]` | Toggle YOLO autonomous mode on or off |

## How It Works

### Workflow

```mermaid
flowchart TD
    SEC["/secretary<br/>Unified Entry Point"] -->|Explore| BS["/brainstorm<br/>Explore & Research"]
    SEC -->|Build| CF["/create-feature<br/>Direct Start"]
    SEC -->|Debug| RCA["/root-cause-analysis<br/>Debug & Investigate"]
    SEC -->|Specialist| AGENT["Agent / Skill<br/>Direct Dispatch"]

    BS -->|PRD| SPEC
    CF --> SPEC
    RCA -->|Fix| SPEC

    subgraph SPEC["SPECIFY"]
        SE[Executor] <-->|Fix| SR{{"Reviewer<br/>Clear?"}}
    end
    SPEC -->|Fix| SG{Spec Gate}
    SG -->|Pass| DES

    subgraph DES["DESIGN"]
        DE[Executor] <-->|Fix| DR{{"Reviewer<br/>Robust?"}}
    end
    DES -->|Fix| DG{Design Gate}
    DG -->|Pass| PLN

    subgraph PLN["PLAN"]
        PE[Executor] <-->|Fix| PR{{"Reviewer<br/>Practical?"}}
    end
    PLN -->|Fix| PG{Plan Gate}
    PG -->|Pass| TSK

    subgraph TSK["TASKS"]
        TE[Executor] <-->|Fix| TR{{"Reviewer<br/>Executable?"}}
    end
    TSK -->|Fix| TG{Task Gate}
    TG -->|Pass| IMP

    subgraph IMP["IMPLEMENT"]
        IE["Spec to Interface TDD"] <-->|Fix| IR{{"Reviewer<br/>Complete?"}}
    end
    IMP -->|Fix| CG{Code Gate}
    CG -->|All Pass| FIN

    FIN["FINISH<br/>Docs / PR / Merge"] --> RET
    RET["RETROSPECTIVE<br/>Capture Learnings"] --> MEM[("Long-Term<br/>Memory")]
    RET --> DONE([Complete])
```

![Workflow Overview](./docs/workflow-overview.png)

### Review System

Every phase has a skeptic reviewer that challenges assumptions and a gatekeeper that validates completeness. Quality gates prevent issues from compounding across phases.

### File Structure

```
docs/
├── brainstorms/           # From /pd:brainstorm
├── features/{id}-{name}/  # From /pd:create-feature
│   ├── spec.md, design.md, plan.md, tasks.md
│   └── .meta.json         # Phase tracking
├── projects/{id}-{name}/  # From /pd:create-project
│   ├── prd.md             # Project PRD
│   └── roadmap.md         # Dependency graph, milestones
├── retrospectives/        # From /pd:retrospect
└── knowledge-bank/        # Accumulated learnings
```

### Task Output Format

Tasks are organized for parallel execution:

- **Dependency Graph**: Mermaid diagram showing task relationships
- **Execution Strategy**: Groups tasks by parallel executability
- **Task Details**: Each task includes:
  - Dependencies and blocking relationships
  - Exact file paths and step-by-step instructions
  - Test commands or verification steps
  - Binary "done when" criteria
  - Time estimates (5-15 min each)

## Reference

pd includes 29 skills and 28 agents that run automatically during the workflow. You don't invoke them directly.

### Skills

#### Workflow Phases

| Skill | Purpose |
|-------|---------|
| brainstorming | Guides 6-stage process producing evidence-backed PRDs with advisory team analysis and structured problem-solving |
| structured-problem-solving | Applies SCQA framing and type-specific decomposition to problems during brainstorming |
| specifying | Creates precise specifications with acceptance criteria |
| designing | Creates design.md with architecture and contracts |
| decomposing | Orchestrates project decomposition pipeline (AI decomposition, review, feature creation) |
| planning | Produces plan.md with dependencies and ordering |
| breaking-down-tasks | Breaks plans into small, actionable tasks with dependency tracking |
| implementing | Guides phased TDD implementation (Interface → RED-GREEN → REFACTOR) |
| finishing-branch | Guides branch completion with PR or merge options |

#### Quality & Review

| Skill | Purpose |
|-------|---------|
| promptimize | Reviews prompts against best practices guidelines and returns scored assessment with improved version |
| reviewing-artifacts | Comprehensive quality criteria for PRD, spec, design, plan, and tasks |
| implementing-with-tdd | Enforces RED-GREEN-REFACTOR cycle with rationalization prevention |
| workflow-state | Defines phase sequence and validates transitions |
| workflow-transitions | Shared workflow boilerplate for phase commands (validation, branch check, commit, state update) |

#### Investigation

| Skill | Purpose |
|-------|---------|
| systematic-debugging | Guides four-phase root cause investigation |
| root-cause-analysis | Structured 6-phase process for finding ALL contributing causes |

#### Domain Knowledge

| Skill | Purpose |
|-------|---------|
| game-design | Game design frameworks, engagement/retention analysis, aesthetic direction, and feasibility evaluation |
| crypto-analysis | Crypto/Web3 frameworks for protocol comparison, DeFi taxonomy, tokenomics, trading strategies, MEV classification, market structure, and risk assessment |
| data-science-analysis | Data science frameworks for methodology assessment, pitfall analysis, and modeling approach recommendations (brainstorming domain) |
| writing-ds-python | Clean DS Python code: anti-patterns, pipeline rules, type hints, testing strategy, dependency management |
| structuring-ds-projects | Cookiecutter v2 project layout, notebook conventions, data immutability, the 3-use rule |
| spotting-ds-analysis-pitfalls | 15 common statistical pitfalls with diagnostic decision tree and mitigation checklists |
| choosing-ds-modeling-approach | Predictive vs causal modeling, method selection flowchart, Rubin/Pearl frameworks, hybrid approaches |

#### Specialist Teams

| Skill | Purpose |
|-------|---------|
| creating-specialist-teams | Creates ephemeral specialist teams via template injection into generic-worker |

#### Maintenance

| Skill | Purpose |
|-------|---------|
| retrospecting | Runs data-driven AORTA retrospective using retro-facilitator agent |
| updating-docs | Automatically updates documentation using agents |
| writing-skills | Applies TDD approach to skill documentation |
| detecting-kanban | Detects Vibe-Kanban and provides TodoWrite fallback |
| capturing-learnings | Guides model-initiated learning capture with configurable modes |

### Agents

#### Reviewers

| Agent | Purpose |
|-------|---------|
| brainstorm-reviewer | Reviews brainstorm artifacts with universal + type-specific criteria before promotion |
| code-quality-reviewer | Reviews implementation quality after spec compliance is confirmed |
| design-reviewer | Challenges design assumptions and finds gaps |
| implementation-reviewer | Validates implementation against full requirements chain |
| phase-reviewer | Validates artifact completeness for next phase transition |
| plan-reviewer | Skeptically reviews plans for failure modes and feasibility |
| prd-reviewer | Critically reviews PRD drafts for quality and completeness |
| project-decomposition-reviewer | Validates project decomposition quality (coverage, sizing, dependencies) |
| spec-reviewer | Reviews spec.md for testability, assumptions, and scope discipline |
| security-reviewer | Reviews implementation for security vulnerabilities |
| task-reviewer | Validates task breakdown quality for immediate executability |
| ds-analysis-reviewer | Reviews data analysis for statistical pitfalls, methodology issues, and conclusion validity |
| ds-code-reviewer | Reviews DS Python code for anti-patterns, pipeline quality, and best practices |

#### Workers

| Agent | Purpose |
|-------|---------|
| implementer | Implements tasks with TDD and self-review discipline |
| project-decomposer | Decomposes project PRD into ordered features with dependencies and milestones |
| generic-worker | General-purpose implementation agent for mixed-domain tasks |
| documentation-writer | Writes and updates documentation based on research findings |
| code-simplifier | Identifies unnecessary complexity and suggests simplifications |
| test-deepener | Systematically deepens test coverage after TDD scaffolding with spec-driven adversarial testing |

#### Advisory

| Agent | Purpose |
|-------|---------|
| advisor | Applies strategic or domain advisory lens to brainstorm problems via template injection |

#### Researchers

| Agent | Purpose |
|-------|---------|
| codebase-explorer | Analyzes codebase to find relevant patterns and constraints |
| documentation-researcher | Researches documentation state and identifies update needs |
| internet-researcher | Searches web for best practices, standards, and prior art |
| investigation-agent | Read-only research agent for context gathering |
| skill-searcher | Finds relevant existing skills for a given topic |

#### Orchestration

| Agent | Purpose |
|-------|---------|
| secretary-reviewer | Validates secretary routing recommendations before presenting to user |
| rca-investigator | Finds all root causes through 6-phase systematic investigation |
| retro-facilitator | Runs data-driven AORTA retrospective with full intermediate context |

## For Developers

See [README_FOR_DEV.md](./README_FOR_DEV.md) for:
- Component authoring (skills, agents, hooks)
- Architecture and design principles
- Release workflow
- Validation

Each project uses `.claude/pd.local.md` for local settings (artifacts path, merge branch, memory config). See [README_FOR_DEV.md](./README_FOR_DEV.md) for the full configuration reference.
