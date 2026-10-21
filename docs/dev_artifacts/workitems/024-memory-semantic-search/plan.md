# Plan: Semantic Memory System

**Commit strategy:** Each phase is committed separately (e.g., `git commit -m "feat(024): Phase 1 - foundation modules"`) to enable incremental review and targeted rollback.

**Import path strategy:** All verification commands and tests run from `plugins/iflow-dev/hooks/lib/` as working directory, making `from semantic_memory import ...` resolve naturally. All three entry points (`injector.py`, `writer.py`, `memory-server.py`) are invoked by absolute path from bash (session-start.sh, SKILL.md, .mcp.json) and need `sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))` at the top of their `if __name__ == "__main__"` block to resolve `from semantic_memory import ...`. Test files use the same `sys.path.insert` pattern. Note: the design mentions "relative imports" for injector.py — use absolute imports with sys.path instead.

## Implementation Order

### Phase 0: Environment Setup (prerequisite for all code)

#### 0.1 Dependency Management and Venv

- **Why this item:** TD10, TD11 — numpy and provider SDKs must be importable before any Python module can be written or tested. Without `pyproject.toml` and `uv sync`, no verification step from Phase 1 onward can actually run.
- **Why this order:** Zero dependencies. Everything else depends on having a working venv.
- **Deliverable:** `pyproject.toml` with numpy core dependency, optional extras for mcp/gemini/voyage/openai. `uv sync` creates working venv at `plugins/iflow-dev/.venv/`.
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/pyproject.toml`
- **Verification:** `cd plugins/iflow-dev && uv sync && .venv/bin/python -c "import numpy; print(numpy.__version__)"` succeeds. `uv sync --extra mcp --extra gemini` installs MCP and Gemini SDK. Verify Gemini SDK API: `.venv/bin/python -c "from google.genai import types; types.EmbedContentConfig(task_type='RETRIEVAL_QUERY', output_dimensionality=768)"`. Verify MCP import: `.venv/bin/python -c "from mcp.server.fastmcp import FastMCP"`.

---

### Phase 1: Foundation (no code dependencies)

#### 1.1 Package Structure, Shared Utilities, and Types

- **Why this item:** TD1 defines the package layout. `content_hash()` is used by every component that creates or deduplicates entries. Shared dataclasses (`CandidateScores`, `RetrievalResult`) are defined here to avoid circular dependencies between retrieval.py and ranking.py.
- **Why this order:** Zero dependencies. Every subsequent module imports from this package.
- **Deliverable:** `semantic_memory/` package directory with `__init__.py` exporting `content_hash()`, version string, and `EmbeddingError` exception. `types.py` exporting `CandidateScores` and `RetrievalResult` dataclasses.
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/__init__.py`, `plugins/iflow-dev/hooks/lib/semantic_memory/types.py`
- **Verification:** `cd plugins/iflow-dev/hooks/lib && ../.venv/bin/python -c "from semantic_memory import content_hash; print(content_hash('test description'))"` returns a 16-char hex string. `from semantic_memory.types import RetrievalResult, CandidateScores` succeeds.

#### 1.2 Configuration Reader

- **Why this item:** TD5 — every component reads config for provider settings, weights, and toggles. Must match bash `read_local_md_field` behavior exactly.
- **Why this order:** Zero dependencies beyond __init__.py.
- **Deliverable:** `config.py` with `read_config(project_root) -> dict` returning merged defaults + parsed values. No YAML library — line-by-line scanning matching bash behavior.
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/config.py`
- **Verification:** Unit test: given a mock `iflow-dev.local.md` with `memory_semantic_enabled: true` and `memory_vector_weight: 0.5`, `read_config()` returns correct types (bool, float). Given missing file, returns all defaults. Space stripping matches bash `tr -d ' '`.

#### 1.3a Database Schema and Basic CRUD

- **Why this item:** C1 — the SQLite database is the central persistence layer. Schema creation, connection setup (WAL, PRAGMAs), migration framework, and basic CRUD must exist before anything reads or writes.
- **Why this order:** Depends only on __init__.py (for content_hash).
- **Deliverable:** `database.py` with `MemoryDatabase` class: `__init__` (schema creation, PRAGMAs), `close`, `upsert_entry`, `get_entry`, `get_all_entries`, `count_entries`, `get_metadata`, `set_metadata`. Migration framework (TD8) with `MIGRATIONS` dict.
- **Complexity:** Medium (schema, PRAGMAs, migration framework, 8 methods)
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/database.py`
- **Verification:** Unit test: create in-memory DB, upsert entry, retrieve by ID, verify all fields. Migration from version 0 to 1 creates tables. `get_metadata`/`set_metadata` round-trips.

#### 1.3b Database FTS5 and Embedding Methods

- **Why this item:** FTS5 detection, trigger creation, keyword search, and embedding BLOB operations extend the base database with search capabilities.
- **Why this order:** Depends on 1.3a (base MemoryDatabase class).
- **Deliverable:** Extend `MemoryDatabase` with: `fts5_available` property, FTS5 detection at `__init__()`, FTS5 virtual table and trigger creation (conditional on FTS5 availability), `fts5_search`, `get_all_embeddings`, `update_embedding`, `clear_all_embeddings`, `get_entries_without_embedding`, `update_recall`.
- **Complexity:** Complex (FTS5 detection probe, trigger SQL, BLOB handling, 6 additional methods)
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/database.py` (extends 1.3a)
- **Verification:** Unit test: FTS5 search returns results when available. `get_all_embeddings` returns None when no embeddings stored. `update_recall` increments counts. BLOB round-trip: store float32 tobytes, read back with frombuffer, verify equality.

#### 1.4 Phase 1 Tests

- **Why this item:** Tests for all Phase 1 modules before proceeding to Phase 2. In practice, implementer should write unit tests alongside each module's implementation (test-first where feasible), then consolidate into this test file.
- **Why this order:** After all Phase 1 implementation. Validates foundation before building on it.
- **Deliverable:** Test file covering: content_hash formula, config reader (mock file, missing file, type coercion), database CRUD (in-memory SQLite), FTS5 search, embedding BLOB round-trip, migration framework.
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/tests/test_foundation.py`
- **Verification:** All tests pass: `cd plugins/iflow-dev && .venv/bin/python -m pytest hooks/tests/test_foundation.py -v`

---

### Phase 2: Core Modules (depends on Phase 1)

#### 2.1 Embedding Provider Protocol and Adapters

- **Why this item:** C2 — embedding generation for both write and query paths.
- **Why this order:** Depends on config.py (provider selection, API key env vars).
- **Deliverable:** `embedding.py` with `EmbeddingProvider` Protocol (I2), `GeminiProvider` (full implementation with taskType validation at init, `output_dimensionality=768`, implements both `embed()` and `embed_batch()` using Gemini SDK's batch capability), `OllamaProvider` (raises `NotImplementedError("Ollama provider not yet implemented — use gemini or set memory_semantic_enabled: false")`), `NormalizingWrapper` (L2 normalization, zero-vector detection raising `EmbeddingError`), `create_provider()` factory (returns None for missing API key, None for Voyage/OpenAI — not implemented in this feature), `EmbeddingError` exception. Note: if Phase 0.1 SDK verification fails for `task_type`, check actual SDK source for correct parameter name (could differ between `google-genai` versions).
- **Complexity:** Complex
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/embedding.py`
- **Verification:** Unit test with mock provider: NormalizingWrapper normalizes to unit length. Zero vector raises EmbeddingError. `create_provider()` returns None when API key missing. OllamaProvider raises NotImplementedError. SDK verification: `from google.genai import types; types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=768)`.

#### 2.2 Keyword Generator

- **Why this item:** C3 — keyword labels for FTS5 indexing at write time.
- **Why this order:** Depends on config.py (provider selection).
- **Deliverable:** `keywords.py` with `KeywordGenerator` Protocol (I3), `TieredKeywordGenerator` (tier order based on config, 5s timeout per tier, per-keyword validation against `^[a-z0-9][a-z0-9-]*$`), keyword prompt template, stopword list matching AC5.
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/keywords.py`
- **Verification:** Unit test: mock tier returns `["fts5", "sqlite", "INVALID!", "parser-error"]` → validator keeps 3 valid keywords, filters 1 invalid. Stopword list rejects generic terms. Empty result when all fail.

#### 2.3 Ranking Engine

- **Why this item:** C5 — scoring and selection logic independent of retrieval strategy.
- **Why this order:** Depends on types.py (RetrievalResult, CandidateScores from Phase 1). No dependency on retrieval.py.
- **Deliverable:** `ranking.py` with `RankingEngine` class (I5): `rank(result, entries, limit)` implementing min-max normalization, weight redistribution when signals unavailable (using `result.vector_candidate_count` and `result.fts5_candidate_count`), prominence sub-scoring (obs_count 0.3, confidence 0.2, recency 0.3, recall 0.2), category-balanced selection (min-3 per non-empty category when limit >= 9).
- **Complexity:** Complex
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/ranking.py`
- **Verification:** Unit test: known score inputs → verify ordering. Weight redistribution when `vector_candidate_count=0`. Category balance with 3 categories and limit=20. Prominence scoring with known inputs produces expected values.

#### 2.4 Phase 2 Tests

- **Why this item:** Tests for all Phase 2 modules.
- **Why this order:** After Phase 2 implementation. Validates core modules before building pipelines.
- **Deliverable:** Test file covering: NormalizingWrapper, create_provider with mock env, keyword validation/filtering/stopwords, ranking formula with known inputs, weight redistribution, category balancing.
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/tests/test_core_modules.py`
- **Verification:** All tests pass.

---

### Phase 3: Pipelines (depends on Phase 1 + 2)

#### 3.1 Retrieval Pipeline

- **Why this item:** C4 — orchestrates context collection, vector + FTS5 retrieval, and merging into RetrievalResult.
- **Why this order:** Depends on database.py (queries), embedding.py (query embedding generation), types.py (dataclasses).
- **Deliverable:** `retrieval.py` with `RetrievalPipeline` class (I4): `collect_context(project_root)` (feature name/description/phase/git diff signals), `retrieve(context_query)` (vector + FTS5, merge, populate diagnostic metadata). Handles all degradation paths (no provider, no FTS5, no context, no numpy).
- **Complexity:** Complex
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/retrieval.py`
- **Verification:** Unit test: mock database with pre-computed embeddings. `collect_context` with mock .meta.json and git output. `retrieve` with both signals, vector-only, FTS5-only, and neither. RetrievalResult carries correct candidate counts.

#### 3.2 Markdown Importer

- **Why this item:** C7 — first-run import of existing knowledge bank entries.
- **Why this order:** Depends on database.py (upsert), embedding.py (Phase 2 deferred), keywords.py (generation).
- **Deliverable:** `importer.py` with `MarkdownImporter` class (I8, note: `keyword_gen` parameter typed as `KeywordGenerator | None` to support skip mode — design I8 shows non-optional but plan requires None support): `import_all(project_root, global_store)` returns count. `_parse_markdown_entries(filepath, category)` matches `memory.py` parsing exactly (heading format `### Category: Name`, body until next heading, metadata lines). Phase 1 inserts without embeddings AND without keywords — both are deferred to Phase 2 processing via write-path invocations. FTS5 indexes name/description directly, which is sufficient for the first session. Note: heuristics.md entries do NOT use a "Heuristic:" prefix in practice — follow memory.py's actual parsing, not design doc heading examples.
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/importer.py`
- **Verification:** Unit test: mock anti-patterns.md with 3 entries → 3 DB rows with correct fields. Re-import is idempotent. Embeddings AND keywords NULL after Phase 1 import.

#### 3.3 Phase 3 Tests

- **Why this item:** Tests for pipeline modules.
- **Why this order:** After Phase 3 implementation.
- **Deliverable:** Test file covering: retrieval with all degradation paths, context signal collection, importer markdown parsing matching memory.py, dedup idempotency.
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/tests/test_pipelines.py`
- **Verification:** All tests pass.

---

### Phase 4: Entry Points (depends on Phase 1 + 2 + 3)

#### 4.1 Injector CLI (Query Path)

- **Why this item:** I6 — main entry point from session-start.sh. Orchestrates full query pipeline.
- **Why this order:** Depends on all core modules. Primary user-facing output.
- **Deliverable:** `injector.py` with `main()` CLI entry point: `--project-root`, `--limit`, `--global-store` args. Produces formatted markdown to stdout matching I10 format. Includes inline RecallTracker logic (C8: batch `update_recall` after injection). Never corrupts stdout on error (stderr only). Diagnostic line composed from RetrievalResult metadata. When triggering first-run import, passes `keyword_gen=None` to the importer to skip keyword generation entirely (avoids API calls within 3-second timeout). Note: uses `sys.path.insert` for absolute imports (not relative imports despite design TD7 mentioning "relative" for injector.py — see import path strategy in preamble).
- **Complexity:** Complex
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/injector.py`
- **Verification:** Integration test: mock DB with entries → verify stdout output matches expected format. Diagnostic line has correct counts. Recall tracking increments. Empty DB triggers import (without keyword generation). Errors produce empty output.

#### 4.2 Writer CLI (Write Path)

- **Why this item:** I9 — CLI entry point for retro dual-writes via Bash tool.
- **Why this order:** Depends on database.py, embedding.py, config.py.
- **Deliverable:** `writer.py` with `main()` CLI: `--action upsert`, `--global-store PATH`, `--entry-json JSON | --entry-file PATH`. Exit codes: 0=success, 1=validation, 2=DB error. Processes up to 50 pending embeddings per invocation (Phase 2). Checks provider migration (TD9).
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/writer.py`
- **Verification:** Unit test: valid entry JSON → DB entry with correct content hash. Invalid JSON exits code 1. Provider unavailable → entry stored without embedding. Pending batch processes up to 50.

#### 4.3 MCP Memory Server

- **Why this item:** C6 — standalone MCP server with `store_memory` tool for mid-session capture.
- **Why this order:** Depends on database.py, embedding.py, keywords.py. Independent of injector/writer.
- **Deliverable:** `memory-server.py` with FastMCP server (I7, import: `from mcp.server.fastmcp import FastMCP` from the `mcp` PyPI package). Business logic extracted into a `_process_store_memory()` plain function that the async tool handler delegates to — enables direct unit testing without MCP transport. sys.path insertion for semantic_memory package. Import smoke test at startup.
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/mcp/memory-server.py`
- **Verification:** Unit test on `_process_store_memory()` directly: creates entry with all fields. Invalid category rejected. Empty name rejected. Duplicate increments observation_count.

#### 4.4 Phase 4 Tests

- **Why this item:** Tests for all entry points.
- **Why this order:** After Phase 4 implementation.
- **Deliverable:** Test file covering: injector output format, diagnostic line, recall tracking, writer exit codes, writer batch processing, MCP business logic (via extracted function).
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/tests/test_entry_points.py`
- **Verification:** All tests pass.

---

### Phase 5: Integration (depends on Phase 4)

#### 5.1 Session-Start Hook Modification

- **Why this item:** TD4 — bash hook branches on `memory_semantic_enabled` to call semantic injector or MD-based fallback.
- **Why this order:** Depends on injector.py being complete.
- **Deliverable:** Modified `session-start.sh` `build_memory_context()` with: semantic/fallback branch, venv Python resolution (`plugins/iflow-dev/.venv/bin/python`), 3-second timeout wrapper, stderr suppression. Both paths produce identical output format.
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/session-start.sh`
- **Verification:** Run existing `test-hooks.sh` tests (Test 6, Test 7) to verify session-start.sh still produces valid output. Manual test: `memory_semantic_enabled: true` → calls injector.py, output contains `semantic: active` in diagnostic line; `false` → calls memory.py, output contains `semantic: disabled`. Missing venv → falls back to bare python3.
- **Rollback:** Keep original `build_memory_context()` function accessible via `git diff` for quick revert if bugs discovered. The toggle `memory_semantic_enabled: false` is itself a runtime rollback path.

#### 5.2 Retrospective Skill Integration

- **Why this item:** TD6 — retrospecting skill Step 4 dual-writes to SQLite.
- **Why this order:** Depends on writer.py CLI.
- **Deliverable:** Modified `retrospecting/SKILL.md` Step 4 with: conditional SQLite write when `memory_semantic_enabled: true`, Bash tool invocation of `writer.py --action upsert`, extraction of keywords/reasoning from agent response with backward-compat defaults (`[]` and `""`). Modified `retro-facilitator.md` agent prompt to produce keywords and reasoning fields in Act section output. Explicit field mapping: agent `text` → writer `description`, agent `provenance` → writer `references` (parsed), agent `confidence` → writer `confidence`, agent `keywords` → writer `keywords`, agent `reasoning` → writer `reasoning`.
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/skills/retrospecting/SKILL.md`, `plugins/iflow-dev/agents/retro-facilitator.md`
- **Verification:** Review: SKILL.md Step 4 includes conditional dual-write block with explicit field mapping. retro-facilitator.md Act section includes keywords and reasoning. Functional test: `writer.py --entry-json '{"name":"test","description":"test","category":"patterns"}'` succeeds with missing keywords/reasoning (defaults applied). This verifies backward-compat: if retro-facilitator omits new fields, writer.py still works.

#### 5.3 MCP Server Registration

- **Why this item:** TD7 — register MCP server in `.mcp.json`.
- **Why this order:** Depends on MCP server being complete.
- **Deliverable:** Updated `.mcp.json` with `memory-server` entry.
- **Complexity:** Simple
- **Files:** `.mcp.json`
- **Verification:** `jq '.mcpServers["memory-server"]' .mcp.json` returns correct config.

---

### Phase 6: Validation and Polish

#### 6.1 End-to-End Integration Testing

- **Why this item:** AC1b, AC2, AC9 — semantic relevance, cross-project retrieval, and timeout safety.
- **Why this order:** Depends on all components and integrations being complete.
- **Deliverable:** Integration test script: (1) create test DB with 50 entries across 3 topics with mock embeddings and controlled prominence (obs_count=1, confidence=medium for all entries — ensures ranking differentiation comes from vector/keyword scores, not prominence), (2) run injector.py with context query, (3) verify 18/20 topic-relevant entries in top 25 (AC1b), (4) verify local computation <100ms for 10K entries (AC9a), (5) verify cross-project retrieval: create entry with `source_project="project-a"`, run injector with different project_root, verify entry appears (AC2), (6) verify recall tracking: run 3 injection cycles, assert recall_count=3 and last_recalled_at updated (AC3), (7) verify MCP business logic: call _process_store_memory(), verify entry in DB, run injector, verify retrievable (AC4).
- **Complexity:** Medium
- **Files:** `plugins/iflow-dev/hooks/tests/test_integration.py`
- **Verification:** Test script exits 0. All assertions pass.

#### 6.2 Validate.sh and Final Checks

- **Why this item:** AC13 — `./validate.sh` must pass (no regressions from new files). Python compilation is verified separately by the pytest suite (items 1.4, 2.4, 3.3, 4.4, 6.1) — validate.sh itself does not run Python checks.
- **Why this order:** Final step.
- **Deliverable:** `./validate.sh` passes without regressions. All pytest suites pass (Python compilation and correctness verified).
- **Complexity:** Simple
- **Files:** No new files
- **Verification:** `./validate.sh` exits 0. All pytest items pass.

## Dependency Graph

```
Phase 0 (Environment):
  0.1 pyproject.toml + uv sync ──┐
                                  │
Phase 1 (Foundation):             │
  1.1 __init__.py + types.py ◄────┤
  1.2 config.py ◄─────────────────┤
  1.3a database (basic CRUD) ◄────┤ (depends on 1.1)
  1.3b database (FTS5+embed) ◄────┤ (depends on 1.3a)
  1.4 Phase 1 tests ◄─────────────┤ (depends on 1.1-1.3b)
                                   │
Phase 2 (Core):                    │
  2.1 embedding.py ◄──────────────┤ (depends on 1.2)
  2.2 keywords.py ◄───────────────┤ (depends on 1.2)
  2.3 ranking.py ◄────────────────┤ (depends on 1.1 types.py only)
  2.4 Phase 2 tests ◄─────────────┤ (depends on 2.1-2.3)
                                   │
Phase 3 (Pipelines):               │
  3.1 retrieval.py ◄──────────────┤ (depends on 1.3b, 2.1, 1.1 types)
  3.2 importer.py ◄───────────────┤ (depends on 1.3a, 2.1, 2.2)
  3.3 Phase 3 tests ◄─────────────┤ (depends on 3.1-3.2)
                                   │
Phase 4 (Entry Points):            │
  4.1 injector.py ◄───────────────┤ (depends on 1.2, 1.3b, 2.1, 2.3, 3.1, 3.2)
  4.2 writer.py ◄─────────────────┤ (depends on 1.2, 1.3a, 2.1)
  4.3 memory-server.py ◄──────────┘ (depends on 1.3a, 2.1, 2.2)
  4.4 Phase 4 tests                 (depends on 4.1-4.3)

Phase 5 (Integration):
  5.1 session-start.sh ◄── (depends on 4.1)
  5.2 SKILL.md + agent ◄── (depends on 4.2)
  5.3 .mcp.json ◄───────── (depends on 4.3)

Phase 6 (Validation):
  6.1 Integration tests ◄── (depends on all above)
  6.2 validate.sh ◄──────── (depends on all above)
```

**Parallelism within phases:**
- Phase 1: items 1.1, 1.2 in parallel; then 1.3a; then 1.3b; then 1.4
- Phase 2: items 2.1, 2.2, 2.3 in parallel; then 2.4
- Phase 3: items 3.1, 3.2 in parallel; then 3.3
- Phase 4: items 4.1, 4.2, 4.3 in parallel; then 4.4
- Phase 5: items 5.1, 5.2, 5.3 in parallel

## Risk Areas

| Risk | Phase | Mitigation |
|------|-------|------------|
| Gemini SDK `taskType` parameter may not be supported in installed version | 0.1, 2.1 | Phase 0.1 verification validates SDK API surface at venv creation. GeminiProvider validates at `__init__()` with fail-fast RuntimeError. |
| `memory.py` markdown parsing has undocumented edge cases | 3.2 | Read `memory.py:parse_entries()` source before implementing importer. Use same regex patterns. Test with real knowledge bank files. |
| session-start.sh modification breaks existing memory injection | 5.1 | Fallback path (`memory_semantic_enabled: false`) calls existing `memory.py` unchanged. Run test-hooks.sh. Git revert available. |
| FTS5 trigger REPLACE chain doesn't handle all JSON edge cases | 1.3b | Per-keyword validation (C3) ensures keywords match `^[a-z0-9][a-z0-9-]*$` before storage. |
| numpy import adds latency to session start | 4.1 | Module-level import with flag check. ImportError → skip vector retrieval. ~20ms typical. |
| retro-facilitator agent ignores new prompt fields | 5.2 | writer.py defaults to `[]` and `""` when fields missing. Functional test verifies this. |
| MCP `mcp` package API changes between versions | 0.1, 4.3 | Phase 0.1 verifies `from mcp.server.fastmcp import FastMCP`. Pin version in pyproject.toml. |

## Testing Strategy

| Level | What | How | Plan Item |
|-------|------|-----|-----------|
| Unit | Each module in isolation | Python pytest with mock dependencies, in-memory SQLite | 1.4, 2.4, 3.3, 4.4 |
| Integration | Full pipeline end-to-end | Real SQLite DB, mock embeddings, verify ranking output | 6.1 |
| Integration | Cross-project retrieval (AC2) | Entry from project-a retrievable in project-b | 6.1 |
| Integration | Timeout safety (AC9a) | 10K entries with mock embeddings, <100ms assertion | 6.1 |
| Manual | Session-start hook | Run session-start.sh with semantic on/off | 5.1 |
| Manual | MCP capture | Call store_memory via Claude Code | After 5.3 |
| Regression | MD fallback | `memory_semantic_enabled: false` → identical to memory.py | 5.1 |

## Definition of Done

- [ ] pyproject.toml created, `uv sync` produces working venv with numpy (0.1)
- [ ] All 11 Python modules created and syntactically valid (1.1-4.3)
- [ ] Shared types in types.py (CandidateScores, RetrievalResult) — no circular imports
- [ ] MemoryDatabase handles schema creation, FTS5 detection, all 14 I1 methods (1.3a+1.3b)
- [ ] EmbeddingProvider protocol with GeminiProvider (full) and NormalizingWrapper (2.1)
- [ ] OllamaProvider raises NotImplementedError; Voyage/OpenAI not implemented (2.1)
- [ ] TieredKeywordGenerator with per-keyword validation (2.2)
- [ ] RankingEngine with weight redistribution and category-balanced selection (2.3)
- [ ] RetrievalPipeline with all degradation paths (3.1)
- [ ] Injector CLI produces output matching I10 format with diagnostic line (4.1)
- [ ] Writer CLI handles upsert, embedding generation, Phase 2 batch processing (4.2)
- [ ] MCP server with extracted business logic for testability (4.3)
- [ ] Unit tests for each phase pass (1.4, 2.4, 3.3, 4.4)
- [ ] session-start.sh branches on `memory_semantic_enabled` (5.1)
- [ ] Retrospecting SKILL.md Step 4 dual-writes to SQLite with backward-compat (5.2)
- [ ] retro-facilitator.md produces keywords and reasoning (5.2)
- [ ] `.mcp.json` includes memory-server entry (5.3)
- [ ] Integration tests pass: AC1b, AC2, AC3, AC4, AC9a (6.1)
- [ ] `./validate.sh` passes (6.2)
