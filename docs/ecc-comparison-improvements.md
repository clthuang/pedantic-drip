# Improvement Items from ECC Comparison

Source: Holistic comparison of pd vs [everything-claude-code](https://github.com/affaan-m/everything-claude-code)
Date: 2026-02-24

## Implementation Grouping

| Feature | Items | Priority | Status |
|---------|-------|----------|--------|
| **A: Agent Model Selection** | 3 | High | Complete |
| **B: Language Ecosystem** | 1, 7, 9 | High | Not started |
| **C: Code Quality Hooks** | 2 | High (depends on B) | Not started |
| **D: Cross-Cutting Improvements** | 5, 6, 8 | Medium | Not started |
| **Backlog** | 4, 10, 11, 12 | — | Deferred |

## High Priority

### 1. Language-specific skills and agents
**Gap:** ECC covers 6 languages (TypeScript, Python, Go, Java, C++, Swift) with dedicated patterns, testing, and reviewers. pd is entirely language-agnostic.
**ECC examples:** `golang-patterns`, `golang-testing`, `python-patterns`, `python-testing`, `go-reviewer`, `python-reviewer`
**Potential:** Add at minimum: Python patterns, TypeScript/JavaScript patterns, Go patterns.
**Status:** Not started
**Decision:** ACCEPT — extensible architecture with 3 initial language profiles
**Feature:** B (Language Ecosystem)
**Approach:**
- Build an extensible language skill architecture; enable 3 initial profiles
- Initial languages: SQL (`writing-sql`), DS-Python (`writing-ds-python` — exists, extend), Production-Python (`writing-production-python`)
- Each language = a skill SKILL.md + optional rules file in `plugins/pd/rules/`
- Session-start hook detects project type (marker files: `pyproject.toml`, `setup.py`, `*.sql`, `dbt_project.yml`) and injects relevant rules
- Config override in `.claude/pd.local.md`: `language_profiles: [sql, ds-python, production-python]`
- Adding a new language later = create skill + rules file + add marker detection (no architectural changes)

### 2. Code quality hooks (auto-format, type-check)
**Gap:** ECC auto-runs Prettier on JS/TS edits and `tsc --noEmit` on TypeScript changes via PostToolUse hooks. pd has zero code quality hooks.
**ECC examples:** PostToolUse(Edit) -> Prettier format, TypeScript check, console.log warning
**Potential:** Add PostToolUse hooks for auto-formatting and type-checking after file edits.
**Status:** Not started
**Decision:** ACCEPT — project-aware PostToolUse hook
**Feature:** C (Code Quality Hooks) — depends on Feature B for project-type detection
**Approach:**
- PostToolUse(Edit) hook that detects project type and runs appropriate tools
- Python projects: `ruff format` (if installed) or `black`; `ruff check` for linting
- SQL projects: `sqlfluff lint` (if installed)
- Only runs on files matching the project type (not on markdown/config)
- Graceful skip if tooling not installed
- Extensible: adding a new language = adding a detection + formatter case

### 3. Per-agent model selection
**Gap:** ECC specifies `model: haiku` for quick agents and `model: opus` for complex ones. pd dispatches all agents at the same model tier.
**ECC examples:** `architect.md` -> `model: opus`, exploration agents -> `model: haiku`
**Potential:** Add model hints to agent frontmatter. Use haiku for exploration/search, sonnet for implementation, opus for architecture/security review.
**Status:** Complete
**Decision:** ACCEPT — pure prompt edits, highest immediate value
**Feature:** A (Agent Model Selection)
**Approach:**
- Agents already declare model tiers (12 opus, 15 sonnet, 1 haiku) but dispatches don't use them
- Add a general dispatch convention to each dispatching skill/command: "When dispatching via Task, include `model` matching the agent's declared tier"
- Key files: all skills/commands that dispatch agents (brainstorming, implementing, design, create-plan, create-tasks, specify, create-specialist-team, decomposing)

### 4. Lightweight workflow track
**Gap:** The full 7-phase pipeline is overkill for small changes. ECC's independent commands work better for quick fixes.
**Potential:** A "fast track" that combines specify+implement for 1-2 file changes, or makes more phases formally skippable.
**Status:** Not started
**Decision:** BACKLOG — separate feature requiring its own design exploration
**Approach:**
- Define a "Quick" mode alongside Standard and Full
- Quick mode: specify -> implement (skip brainstorm, design, plan, tasks)
- Triggers: `/create-feature --quick` or auto-detection when scope is small
- Still has spec-reviewer gate but skips design/plan phases
- No branch creation for quick mode (works on current branch)
- Needs its own brainstorm/design cycle

## Medium Priority

### 5. Example project configurations
**Gap:** ECC provides 5 production-ready CLAUDE.md examples for different stacks (Next.js SaaS, Django API, Go microservice, Rust API). pd's template is generic.
**Potential:** Stack-specific templates that seed `.claude/pd.local.md` with relevant language skills and rules.
**Status:** Not started
**Decision:** ACCEPT — starter templates for common project types
**Feature:** D (Cross-Cutting Improvements)
**Approach:**
- Create templates in `plugins/pd/templates/` for initially-supported project types
- `config.python-api.local.md` — Production Python API defaults (language_profiles: [production-python])
- `config.data-science.local.md` — Data science project defaults (language_profiles: [ds-python, sql])
- `config.data-engineering.local.md` — Data engineering defaults (language_profiles: [production-python, sql])
- Each template sets: relevant language profiles, domain advisors, review emphasis, project-type-specific settings

### 6. Automatic learning extraction at session end
**Gap:** ECC's SessionEnd hook proposes learnings automatically. pd requires explicit `/remember` or retrospective.
**Potential:** A lightweight SessionEnd hook that captures obvious patterns to complement the existing memory system.
**Status:** Not started
**Decision:** ACCEPT — lightweight SessionEnd reminder
**Feature:** D (Cross-Cutting Improvements)
**Approach:**
- `session-end.sh` hook that outputs a reminder: "Consider capturing learnings with `/remember` if you discovered something useful this session"
- No automatic extraction — just a prompt to the user

### 7. Framework-specific skills
**Gap:** ECC has Django (4 skills), Spring Boot (4 skills). pd has none.
**Potential:** Add reference knowledge skills for commonly-used frameworks.
**Status:** Not started
**Decision:** ACCEPT — aligned with initial language profiles
**Feature:** B (Language Ecosystem) — lower priority than language skills
**Approach:**
- Start with frameworks matching initial profiles:
  - `django-patterns` — Django conventions, middleware, ORM, signals (production-Python)
  - `fastapi-patterns` — FastAPI dependency injection, Pydantic, async (production-Python)
  - `dbt-patterns` — dbt macros, ref/source, testing, documentation (SQL)
- Implement after Item 1's language skills are in place

### 8. Context window management
**Gap:** ECC's "strategic compact" hook suggests `/compact` every ~50 tool calls. pd has no context budget awareness.
**Potential:** A PreToolUse hook that tracks tool call count and suggests compaction.
**Status:** Not started
**Decision:** ACCEPT — simple compaction tip in session-start context
**Feature:** D (Cross-Cutting Improvements)
**Approach:**
- Add compaction tip to session-start context (simple one-liner, no complex hook)
- Lower-effort than ECC's tool-call-counting approach but still provides value

### 9. Dedicated rules directory
**Gap:** ECC separates always-active coding standards (rules/) from skills. pd puts everything in CLAUDE.md, skills, and commands.
**Potential:** A `rules/` directory for always-active standards, reducing token overhead (rules load every session; skills load on demand).
**Status:** Not started
**Decision:** ACCEPT — merged into Item 1's architecture
**Feature:** B (Language Ecosystem) — same implementation
**Approach:**
- Each language profile includes a rules file in `plugins/pd/rules/`
- `rules/common.md` — language-agnostic standards
- `rules/sql.md`, `rules/ds-python.md`, `rules/production-python.md` — language-specific
- Session-start hook detects project language and injects relevant rules into context

## Low Priority

### 10. Security scanning tool
**Gap:** ECC's AgentShield has 102 static analysis rules. pd has a single security-reviewer agent.
**Potential:** Add static rule-based scanning alongside the agent-based approach.
**Status:** Not started
**Decision:** BACKLOG — significant effort, better as own feature with proper design

### 11. Cross-platform hooks (Node.js)
**Gap:** ECC uses Node.js for cross-platform compatibility. pd hooks are Bash-only.
**Potential:** Only matters if pd needs Windows support.
**Status:** Not started
**Decision:** BACKLOG — scope properly as own feature when Windows users adopt the plugin

### 12. Multi-model orchestration
**Gap:** ECC routes to Codex and Gemini alongside Claude. pd is Claude-only.
**Potential:** Multi-model routing adds complexity for marginal benefit.
**Status:** Not started
**Decision:** BACKLOG — significant complexity, needs own design exploration
