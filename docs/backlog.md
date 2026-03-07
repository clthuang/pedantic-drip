# Backlog

| ID | Timestamp | Description |
|----|-----------|-------------|
| 00008 | 2026-01-31T12:05:00Z | add product manager, product owner team (agents, skills) |
| 00012 | 2026-02-17T12:00:00Z | fix the secretary AskUserQuestion formatting. The user should be able to select the options directly and also continue to chat if desired. |
| 00014 | 2026-02-24T12:01:00Z | Security Scanning — static rule-based security scanning alongside the agent-based security-reviewer (inspired by ECC's AgentShield with 102 rules). See ecc-comparison-improvements.md Item 10. |
| 00015 | 2026-02-24T12:02:00Z | Cross-Platform Hooks — port Bash hooks to Node.js for Windows compatibility. See ecc-comparison-improvements.md Item 11. |
| 00016 | 2026-02-24T12:03:00Z | Multi-Model Orchestration — route to multiple AI providers (Codex, Gemini) alongside Claude for cost optimization or specialized tasks. See ecc-comparison-improvements.md Item 12. |
| 00017 | 2026-02-27T12:00:00Z | Unified Central Context Management — expand the knowledge bank DB into a unified central context management service. All agents retrieve required context from the DB. The main orchestration agent sends background context as DB indices to subagents rather than full text. |
| 00018 | 2026-02-27T12:01:00Z | Knowledge Bank Auto-Logging — upgrade knowledge bank to automatically and asynchronously log all session conversations via subagents. Capture every prompt and response, index after each turn. Rethink DB schema to include enriched metadata: session_id, raw prompt/response, categories, timestamps, and other appropriate fields. |
| 00020 | 2026-02-27T13:53:55Z | Consider renaming the plugin/repository to `pedantic-drips` for the public MIT open-source release to highlight the adversarial reviewing nature of the workflow. |
| 00024 | 2026-02-27T22:26:00+08:00 | Add `remove_entry` method to the entity registry and ensure each entity has a status attribute. Currently there is no delete/remove API on `EntityDatabase`, and the `status` field is optional with no default — consider enforcing a default status on registration. |
| 00026 | 2026-02-27T22:51:54+0800 | Add feature subfiles into the entity DB to facilitate referencing entry IDs for future lazy-loading designs. |
| 00027 | 2026-03-01T12:00:00+08:00 | Simplify secretary by removing aware and orchestrate mode. Autonomy is fully controlled by yolo config. |
| 00028 | 2026-03-01T15:00:00+08:00 | Add software-architect, product-manager, devops-infrastructure advisors and add restructuring-a-system archetype to brainstorming references. |
| 00029 | 2026-03-01T16:00:00+08:00 | Remove project lifetime soft constraint from create-project and decomposing skill. It provides weak signal — decomposition quality should be driven by PRD scope and requirements, not a vague time horizon. |
| 00030 | 2026-03-01T08:36:34Z | Fix register_entity MCP tool to correctly process metadata parameter with JSON objects (e.g. `{"depends_on_features": []}`) — currently rejects dict input due to Pydantic string_type validation. |
| 00031 | 2026-03-01T15:00:00+08:00 | Handle DB write lock and concurrent write — ensure entity registry handles SQLite busy/locked errors gracefully under concurrent access. |
| 00032 | 2026-03-01T12:49:31Z | Fix the workflow progression such that if a PRD is missing then go to the PRD creation step |
| 00033 | 2026-03-02T23:15:00+08:00 | Reduce diff comparison for deploying reviewers. Phase-specific reviewers should handle diff operations themselves and reuse the same reviewer for the same type of review, unless the subagent ID is lost then spin up a new instance. Ensure maximum caching possibility for token efficiency. |
| 00034 | 2026-03-02T23:45:00+08:00 | Update code simplifier to use Claude Code's native simplify command instead of custom agent dispatch. |
| 00035 | 2026-03-04T00:35:00+08:00 | Enrich secretary problem solving frameworks and brainstorm frameworks. |
| 00036 | 2026-03-04T00:35:00+08:00 | Add system design architect and solution architect skills/references for design executor and design reviewer. |
| 00037 | 2026-03-04T00:35:00+08:00 | Add product manager skills and references for create-feature executor and reviewer. |
| 00038 | 2026-03-08T02:30:00+08:00 | Knowledge bank markdown-to-DB sync gap — markdown KB (docs/knowledge-bank/) has 169 entries from retrospectives but semantic memory DB (~/.claude/iflow/memory/memory.db) has 417 entries from automated store_memory calls. Neither is a superset of the other: DB misses retro-sourced entries (hook development, markdown migrations, entity registry patterns), markdown misses review-loop-captured entries. Need a bidirectional sync mechanism or single source of truth. Queries for "markdown migration", "hook development bash stderr", "entity registry" return 0 DB hits despite being well-documented in markdown files. |
