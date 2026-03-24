# Design: Memory Feedback Loop — Phase 1 (Delivery & Simplification)

## Prior Art Research

### Codebase Patterns
- **17 fresh subagent dispatches** across 5 command files match spec AC-1 counts (specify:2, design:4, create-plan:2, create-tasks:2, implement:7). Each uses `Task tool call:` blocks with `subagent_type:` for fresh dispatches and `resume:` for continued dispatches.
- `search_memory` MCP tool already accepts `query`, `limit`, `brief` parameters — `brief=true` returns compact one-line-per-entry format ideal for dispatch injection.
- The `retrospecting/SKILL.md` already calls `search_memory` from workflow instructions — this is the only existing precedent for prompt-instructed MCP calls in the workflow.
- Injector pipeline (`injector.py:main()`) has a clear insertion point for threshold filtering between `engine.rank()` (line 215) and `format_output()` (line 226).
- `collect_context()` gathers 6 signal types; signals 1-3, 5, 6 are work-specific (feature slug, description, phase, branch, changed files). Signal 4 (project description) is always present.
- Keywords system is a pure no-op stub — `TieredKeywordGenerator` delegates to `SkipKeywordGenerator` which returns `[]`.
- Three unused embedding providers (OpenAI, Ollama, Voyage) account for ~370 lines in `embedding.py` plus SDK imports.

### External Research
- Industry standard for multi-agent memory: inject retrieved memories per-agent in dispatch prompts, not broadcast full history. Each subagent gets its own filtered context (LangGraph, Amazon Bedrock AgentCore patterns).
- Production relevance thresholds typically range 0.3-0.5; our default of 0.3 is conservative and appropriate for Phase 1.
- Standard RAG pattern: retrieve → re-rank → threshold filter → inject. Our pipeline already does retrieve → rank; this design adds threshold filtering.

## Architecture Overview

Five independent workstreams, each modifying a disjoint set of files:

```
Workstream A: Command File Enrichment (FR-1)
  5 command .md files → add pre-dispatch instruction blocks

Workstream B: Dead Keyword Removal (FR-2)
  keywords.py (delete) → test_keywords.py (delete) →
  memory_server.py (remove imports/usage) →
  writer.py (remove _merge_keywords) →
  config.py (remove memory_keyword_provider)

Workstream C: Dead Provider Removal (FR-3)
  embedding.py (remove 3 providers, simplify create_provider) →
  test_embedding.py (remove 3 provider test classes)

Workstream D: Relevance Threshold (FR-4)
  injector.py (add filtering + has_work_context check) →
  retrieval.py (add has_work_context method) →
  config.py (add memory_relevance_threshold default)

Workstream E: Config Defaults (FR-5)
  config.py (change injection limit default) →
  .claude/pd.local.md (change repo override)
```

### Component Interaction

```
Session Start:
  injector.py → retrieval.py → ranking.py → [NEW: threshold filter] → format_output()
                                                                          ↓
                                                                   orchestrator context

Subagent Dispatch (NEW):
  command file instruction → orchestrator calls search_memory MCP →
  results injected into Task dispatch prompt → subagent sees memories
```

## Components

### C1: Pre-dispatch Memory Enrichment Instruction Block

A markdown instruction block inserted before each fresh `Task tool call:` in the 5 workflow command files.

**Template:**
```markdown
**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
limit=5, brief=true, and category={role-appropriate category filter}.
Include non-empty results as:

## Relevant Engineering Memory
{search_memory results}
```

**limit=5 rationale:** Upper bound of spec's 3-5 range; `brief=true` format is compact (~70 tokens per entry = ~350 tokens total, well within acceptable dispatch overhead).

**Category filtering by agent role (scope improvement):**
The `search_memory` MCP tool's `category` parameter filters results to a single knowledge bank category. Using it narrows retrieval scope to the most relevant entry type for each agent:

| Agent Role | Category Filter | Rationale |
|---|---|---|
| Reviewers (spec, design, plan, task, impl, quality) | `"anti-patterns"` | Reviewers benefit most from known pitfalls |
| Security reviewer | `"anti-patterns"` | Security issues are documented as anti-patterns |
| Implementer | None (all categories) | Needs patterns, anti-patterns, and heuristics |
| Code simplifier | `"patterns"` | Looking for established patterns to follow |
| Test deepener | `"anti-patterns"` | Edge cases and failure modes |
| Research agents (codebase-explorer, internet-researcher) | None (all categories) | Broad exploration benefits from full context |
| Phase reviewers | None (all categories) | Holistic review needs all categories |

When the category filter is `None`, the `category` parameter is omitted from the `search_memory` call, returning results across all categories. This scoping improves retrieval precision — a reviewer seeing anti-patterns is more actionable than seeing a mix of patterns and heuristics.

**Placement rules:**
- Inserted before every `Task tool call:` block containing `subagent_type:` (fresh dispatches only)
- NOT inserted before `resume:` blocks (resumed dispatches already have memory from initial dispatch)
- The query is derived from the agent's role + the dispatch context that follows
- **For loop-based dispatches** (implementer in implement.md): the instruction explicitly references the current task iteration's description and file list from the task definition, not a global query. The template for these reads: `call search_memory with query derived from the current task's description and its file paths`
- **Out of scope:** Non-workflow command files (secretary.md, wrap-up.md, finish-feature.md, review-ds-code.md, review-ds-analysis.md, etc.) are excluded per spec FR-1 which scopes to the 5 workflow command files only

**Query construction guidance:**
The query should include the agent's role and the task-specific context. General rule: `{agent role} + {task/feature context} + {relevant file paths}`. Examples:

| Context | Example Query |
|---|---|
| Reviewer dispatch (fixed context) | "spec review {feature slug} {spec.md path}" |
| Research dispatch (feature-scoped) | "{feature description from spec}" |
| Implementer dispatch (per-task loop) | "implement {current task description} {current task file list}" |
| Post-implementation reviewer | "code quality {changed files from implementation}" |

The orchestrator derives the query naturally from the dispatch prompt that follows — the instruction provides the pattern, not a literal string.

### C2: Keyword System Removal

Delete `keywords.py` and `test_keywords.py` entirely. Remove all references from:

**Note:** Line numbers below are approximate references at design time. The authoritative targets are the function/import names — use grep to locate them during implementation.

**memory_server.py changes:**
- Remove `from semantic_memory.keywords import ...` (near line 25-28)
- Remove `keyword_gen` parameter from `_process_store_memory()` signature (near line 44)
- Remove keyword generation block inside `_process_store_memory()` (near lines 82-91)
- Hardcode `keywords_json = "[]"` (replaces the generation block)
- Remove `_keyword_gen` global variable (near line 231)
- Remove keyword generator initialization in `lifespan()` (near lines 266-270)
- Remove `keyword_gen=_keyword_gen` from the call site (near line 325)

**writer.py changes:**
- Remove `_merge_keywords()` function entirely (lines 76-103)
- Remove keyword merge call in `main()` (lines 293-296)
- Keep `_build_db_entry()`'s handling of `keywords` field (it defaults to `"[]"` — safe)

**config.py changes:**
- Remove `"memory_keyword_provider": "auto"` from DEFAULTS (line 27)

### C3: Unused Provider Removal

Delete from `embedding.py`:
- `OpenAIProvider` class (lines 301-379)
- `OllamaProvider` class (lines 476-554)
- `VoyageProvider` class (lines 557-643)
- `openai_sdk` import try/except block (lines 25-28)
- `ollama_sdk` import try/except block (lines 30-33)
- `voyageai_sdk` import try/except block (lines 35-38)

Simplify `create_provider()`:
- Remove `_PROVIDER_ENV_KEYS` dict (replace with inline check for `"gemini"`)
- Remove `elif` branches for openai/ollama/voyage
- Keep `_load_dotenv_once()` (still needed for GEMINI_API_KEY)
- Simplify `known_keys` in `_load_dotenv_once()` to just `("GEMINI_API_KEY",)`

Delete from `test_embedding.py`: All test classes/functions for OpenAI, Ollama, and Voyage providers.

**What remains in embedding.py:**
- `EmbeddingProvider` protocol
- `GeminiProvider` class
- `NormalizingWrapper` class
- `_load_dotenv_once()` (simplified)
- `create_provider()` (simplified to gemini-only + None)

### C4: Relevance Threshold Filtering

**retrieval.py — new method on `RetrievalPipeline`:**

```python
def has_work_context(self, project_root: str) -> bool:
    """Check whether work-specific context signals are present.

    Returns True when any of signals 1-3, 5, or 6 from
    collect_context() are present (anything beyond the
    always-present project description).

    Mirrors collect_context()'s signal checks for consistency.
    Duplicates some subprocess calls (git branch, git diff) that
    collect_context() will also make — accepted tradeoff since
    these are lightweight (~50-100ms total) and only run in the
    injector path.
    """
    meta, feature_dir = self._find_active_feature(project_root)
    if meta is not None and feature_dir is not None:
        return True  # Signal 1 (feature slug) present — matches collect_context line 86

    branch = self._git_branch_name(project_root)
    base_branch = self._config.get("base_branch", "auto")
    skip_branches = {"main", "master", "develop", "HEAD"}
    if base_branch not in ("auto", ""):
        skip_branches.add(base_branch)
    if branch and branch not in skip_branches:
        return True  # Signal 5 (non-default branch) present

    committed = self._git_changed_files(project_root)
    if committed:
        return True  # Signal 6a present

    working = self._git_working_tree_files(project_root)
    if working:
        return True  # Signal 6b present

    return False
```

**injector.py — changes to `main()`:**

**Insertion point 1 — threshold filtering:** Insert between `engine.rank()` (current line 215) and `if selected:` recall tracking block (current line 218). This is inside the existing `try` block, so the `finally: db.close()` handles cleanup.

```python
# Relevance threshold filtering (FR-4)
threshold = float(config.get("memory_relevance_threshold", 0.3))
selected = [e for e in selected if e["final_score"] > threshold]
```

**Insertion point 2 — no-context early return:** Insert after pipeline construction (current line 207) and before `context_query = pipeline.collect_context(project_root)` (current line 208). This is inside the existing `try` block, so `db`, `config`, `model`, and `global_store` are all in scope, and the `finally: db.close()` handles cleanup on return. `RetrievalResult(candidates={})` is valid — all fields have defaults (verified: `retrieval_types.py` uses `@dataclass` with `field(default_factory=dict)` and `int = 0`).

```python
# Skip injection when no work context (FR-4)
if not pipeline.has_work_context(project_root):
    sys.stdout.write('Memory: skipped (no context signals)\n')
    # Write tracking with skipped_reason to distinguish from "ran but found zero"
    total_count = db.count_entries()
    tracking = {
        "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "semantic",
        "entries_injected": 0,
        "total_entries": total_count,
        "model": model,
        "skipped_reason": "no_work_context",
    }
    tracking_path = os.path.join(global_store, ".last-injection.json")
    try:
        with open(tracking_path, "w") as fh:
            json.dump(tracking, fh, indent=2)
            fh.write("\n")
    except OSError:
        pass
    return
```

**config.py — add to DEFAULTS:**
```python
"memory_relevance_threshold": 0.3,
```

**Test impact:** Existing `test_injector.py` tests `format_output()` — these are unaffected since the threshold filter runs before `format_output()` is called. New tests needed for: (1) threshold filtering behavior (AC-4), (2) no-context skip behavior (AC-5), (3) `has_work_context()` method. Existing `test_retrieval.py` tests are unaffected since `has_work_context()` is a new additive method.

### C5: Default Config Changes

**config.py:** Change `"memory_injection_limit": 20` → `"memory_injection_limit": 15`

**.claude/pd.local.md:** Change `memory_injection_limit: 50` → `memory_injection_limit: 20`

## Technical Decisions

### TD-1: Prompt Instruction vs. Hook-based Injection

**Decision:** Prompt instruction in command files (not a hook).

**Rationale:** Command files are markdown templates interpreted by Claude. Adding a pre-dispatch instruction block is the simplest mechanism — no new code, no new hooks, no new MCP calls from hooks. The orchestrator already interprets similar instructions (e.g., "Read the following files before beginning your review").

**Tradeoff:** Prompt instructions are not deterministic. The orchestrator may skip the `search_memory` call under context pressure. This is accepted for Phase 1 per spec risk table. Phase 3 (influence tracking) will measure actual delivery rates.

### TD-2: Keyword Removal — Keep DB Schema, Remove Code

**Decision:** Delete all keyword Python code; keep the `keywords` TEXT column and FTS5 triggers in the DB.

**Rationale:** Removing the DB column requires a migration (ALTER TABLE + FTS5 rebuild). The column will always contain `"[]"` after this change — it contributes zero signal to FTS5 ranking but costs nothing to retain. Phase 2 (LLM keyword generation) will reuse the column. The `memory_keyword_weight` config key stays for the same reason — the weight distributes across all FTS5-indexed columns (name, description, reasoning, keywords), and removing it would change ranking math.

### TD-3: has_work_context() — Separate Method vs. Modifying collect_context()

**Decision:** New `has_work_context()` method on `RetrievalPipeline`, not modifying `collect_context()`.

**Rationale:** `collect_context()` returns `str | None` — adding a boolean signal would require changing the return type to a tuple or dataclass, which cascades to all callers. A separate boolean method is cheaper and aligns with the spec's design.

**Duplication concern:** `has_work_context()` partially duplicates `collect_context()`'s signal detection (feature detection, branch check, changed files). This is acceptable because: (1) the method is a fast boolean check that short-circuits early, (2) it runs only in the injector path, and (3) refactoring to share logic with `collect_context()` would require changing that method's structure for no functional benefit.

### TD-4: Threshold Position — After Ranking, Before Recall

**Decision:** Apply `final_score > threshold` filter after `engine.rank()` returns, before `db.update_recall()`.

**Rationale:** Filtering before recall tracking means low-scoring entries don't get their recall_count incremented. This prevents the prominence signal from being inflated by irrelevant injections. The threshold is applied to the already category-balanced selection, so it may reduce below the balanced minimum per category — this is intentional (a low-relevance entry from a well-represented category should still be filtered).

### TD-5: create_provider() Simplification Strategy

**Decision:** Replace the `_PROVIDER_ENV_KEYS` dict and multi-provider `elif` chain with a simple gemini-only branch.

**Rationale:** After removing OpenAI, Ollama, and Voyage, only Gemini remains. The factory pattern is unnecessary for a single provider. If providers are added in the future, the factory can be re-introduced from git history.

**Simplified create_provider():**
```python
def create_provider(config: dict) -> EmbeddingProvider | None:
    if np is None:
        return None
    _load_dotenv_once()
    provider_name = config.get("memory_embedding_provider", "")
    if provider_name != "gemini":
        return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    model = config.get("memory_embedding_model", "")
    try:
        return NormalizingWrapper(GeminiProvider(api_key=api_key, model=model))
    except Exception as exc:
        print(f"memory-server: create_provider failed: {exc}", file=sys.stderr)
        return None
```

### TD-6: Category-Scoped Retrieval for Subagent Dispatches

**Decision:** Use `search_memory`'s existing `category` parameter to scope retrieval per agent role.

**Rationale:** Without scoping, all 17 dispatch sites retrieve from the full knowledge bank. Reviewers seeing "Pattern: Thin Orchestrator" is noise — they need anti-patterns (things to catch). Implementers need all categories. Category filtering is zero-cost (already supported by `search_memory`) and significantly improves retrieval precision by matching the agent's purpose to the entry type. This is a pre-retrieval filter that reduces the candidate set before semantic ranking, complementing the post-ranking threshold filter (TD-4).

**Tradeoff:** Category filtering may miss cross-category insights (e.g., a pattern that prevents an anti-pattern). Accepted because: (1) the implementer and phase-reviewer dispatches use no filter (full breadth), (2) the session-start injection still provides full-category context to the orchestrator.

### TD-7: No-Context Skip Output Format

**Decision:** Output `"Memory: skipped (no context signals)\n"` as a single-line diagnostic when work context is absent.

**Rationale:** The session-start hook that runs the injector expects either formatted markdown output or empty string. A single diagnostic line is parseable by the hook (it checks `if output:`) and provides visibility in the session transcript. The spec defines this exact string.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Orchestrator skips search_memory call under context pressure | Medium | Medium | Accepted for Phase 1. Influence tracking in Phase 3 will measure delivery rates. |
| Removing keyword code breaks memory_server store path | Low | High | Keywords are a no-op. Existing tests will verify store/search still work after removal. |
| Relevance threshold 0.3 too aggressive for low-context sessions | Low | Medium | Configurable via `memory_relevance_threshold`. Low-context sessions get the `has_work_context()` skip anyway. |
| Removing 3 embedding providers breaks config for users who set memory_embedding_provider to openai/ollama/voyage | Very Low | Low | No external users; this is private tooling. `create_provider()` returns None for unknown providers (graceful degradation). |
| Pre-dispatch instruction adds ~100 tokens per dispatch site × 17 sites | Low | Low | One-time prompt overhead, not runtime. Command files are loaded once per phase invocation. |

## Interfaces

### I1: Pre-dispatch Instruction Block (C1)

**Input:** None (static markdown template inserted into command files)

**Output effect:** Orchestrator calls `search_memory(query=..., limit=5, brief=true)` MCP tool and includes results in the subsequent Task dispatch prompt.

**Contract with search_memory MCP:**
```
search_memory(
  query: str,              # agent role + task context + file list
  limit: int = 5,          # top 5 results
  brief: bool = true,      # compact one-line format
  category: str | None     # role-scoped filter (see TD-6 table)
) -> str                   # formatted results or empty string
```

### I2: has_work_context() (C4)

```python
class RetrievalPipeline:
    def has_work_context(self, project_root: str) -> bool:
        """Returns True if any work-specific signal is present.

        Signals checked (short-circuit on first True):
        1. Active feature exists (from .meta.json scan)
        2. Non-default branch name
        3. Recently changed files (committed or working tree)
        """
```

### I3: Threshold Filtering (C4)

Applied inline in `injector.py:main()` — no new function. The filter is a single list comprehension:

```python
selected = [e for e in selected if e["final_score"] > threshold]
```

Where `threshold` comes from `config.get("memory_relevance_threshold", 0.3)`.

### I4: Simplified create_provider() (C3/TD-5)

```python
def create_provider(config: dict) -> EmbeddingProvider | None:
    """Create a Gemini embedding provider from configuration.

    Returns None if: numpy unavailable, provider not 'gemini',
    GEMINI_API_KEY not set, or construction fails.
    """
```

### I5: Config DEFAULTS Changes (C5)

```python
DEFAULTS = {
    ...
    "memory_injection_limit": 15,        # was 20
    "memory_relevance_threshold": 0.3,   # new
    # "memory_keyword_provider" removed
    ...
}
```
