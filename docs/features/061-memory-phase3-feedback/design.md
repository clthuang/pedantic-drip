# Design: Memory Phase 3 — Feedback Loop Closure

## Prior Art Research

Existing infrastructure reused:
- `RankingEngine._recall_frequency()` at `ranking.py:145` — modification target for recall dampening
- `RankingEngine._prominence()` at `ranking.py:210` — caller of _recall_frequency, needs updated call
- `RetrievalPipeline.retrieve()` at `retrieval.py:175` — modification target for project filtering
- `MemoryDatabase.get_all_entries()` at `database.py:557` — returns entries with `source_project` column
- `injector.py:main()` at line 169 — runs the injection pipeline, passes project_root
- Capture Review Learnings sections in 5 command files — modification target for notable catches

---

## Architecture Overview

```
FR-1 (Notable Catches):
  commands/{specify,design,create-plan,create-tasks,implement}.md
    └── Extend "Capture Review Learnings" section with single-iteration blocker logic

FR-2 (Project Filtering):
  injector.py → RetrievalPipeline.retrieve(query, project=...) → DB WHERE filter
    └── Two-tier blend: project-scoped + universal, deduplicated

FR-3 (Recall Dampening):
  RankingEngine._recall_frequency(recall_count, last_recalled_at, now)
    └── Time decay: 14-day half-life on recall advantage
  RankingEngine._prominence() → updated call site
```

All changes are backward-compatible. Existing callers without `project` parameter get unchanged behavior.

---

## Components

### C1: Notable Catch Extension (5 command files)

Add a new sub-section to each command file's "Capture Review Learnings" section:

```markdown
**Notable catches (single-iteration blockers):**
If the review loop completed in 1 iteration AND the reviewer found issues with severity "blocker":
1. For each blocker issue (max 2):
   - Store via store_memory MCP tool:
     - name: derived from issue description (max 60 chars)
     - description: issue description + suggestion
     - reasoning: "Single-iteration blocker catch in feature {id} {phase} phase"
     - category: inferred from issue type (same mapping as recurring patterns)
     - confidence: "medium"
     - references: ["feature/{id}-{slug}"]
```

This is a **prompt instruction change only** — no Python code involved.

### C2: Project-Scoped Retrieval (`retrieval.py`)

Modify `RetrievalPipeline.retrieve()` to accept `project: str | None = None`:

```python
def retrieve(self, context_query: str | None, project: str | None = None) -> RetrievalResult:
```

**When `project` is None:** Existing behavior unchanged.

**When `project` is set:**
1. Run existing vector + FTS5 retrieval as normal (full candidate set)
2. After building `candidates` dict, tag each candidate with its `source_project` from the entries table
3. Split candidates into `project_candidates` (matching source_project) and `universal_candidates` (all)
4. Return a `RetrievalResult` with an additional `project` field for the ranker to use

**Alternative considered:** Filter at the DB query level (WHERE source_project = ?). Rejected because vector similarity search operates on the full embedding matrix — filtering before cosine similarity would require a second matrix build. Post-retrieval splitting is simpler and the candidate counts are small (< 1000).

### C3: Two-Tier Blend in Ranker (`ranking.py`)

Modify `RankingEngine.rank()` to handle project-scoped results:

```python
def rank(self, result: RetrievalResult, entries: dict, limit: int) -> list[dict]:
```

**When `result.project` is None:** Existing behavior (single-tier selection).

**When `result.project` is set:**
1. Score all candidates as normal (vector + BM25 + prominence)
2. Split scored entries: `project_scored` (source_project matches) and `all_scored` (everything)
3. Select top `limit // 2` from `project_scored`
4. Select top `limit - len(project_selected)` from `all_scored`, excluding already-selected IDs
5. Merge, sort by final_score descending
6. Apply `_balanced_select()` on the merged set

**Underfill handling:** If project tier has fewer than `limit // 2` entries, fill remainder from universal tier.

### C4: Recall Dampening (`ranking.py`)

Modify `RankingEngine._recall_frequency()`:

```python
def _recall_frequency(self, recall_count: int, last_recalled_at: str | None = None, now: datetime | None = None) -> float:
    base = min(recall_count / 10.0, 1.0)
    if now is None:
        return base  # backward compat for tests calling without time args
    if last_recalled_at is None:
        return base * 0.5  # legacy entries without timestamp
    recalled = datetime.fromisoformat(last_recalled_at)
    if recalled.tzinfo is None:
        recalled = recalled.replace(tzinfo=timezone.utc)
    days_since = max((now - recalled).total_seconds() / 86400.0, 0.0)
    decay = 1.0 / (1.0 + days_since / 14.0)
    return base * decay
```

**Caller update:** `_prominence()` passes `entry.get("last_recalled_at")` and `now` to `_recall_frequency()`.

### C5: Injector Project Resolution (`injector.py`)

Add project name resolution to `main()`:

```python
def _resolve_project_name(project_root: str) -> str | None:
    """Resolve project name from git remote or directory name."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=project_root
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Extract repo name from URL (handles https and ssh)
            name = url.rstrip("/").rsplit("/", 1)[-1]
            return name.removesuffix(".git")
    except Exception:
        pass
    return os.path.basename(os.path.abspath(project_root))
```

Pass to `pipeline.retrieve(context_query, project=project_name)`.

---

## Technical Decisions

### TD-1: Post-retrieval project split, not DB-level filter
**Decision:** Split candidates after retrieval, not during DB queries.
**Rationale:** Vector similarity requires the full embedding matrix. Filtering before cosine would need a project-specific matrix rebuild. Post-retrieval splitting adds a dict lookup per candidate but avoids matrix management complexity.

### TD-2: Two-tier blend in ranker, not retrieval
**Decision:** The blend logic (N/2 project + N/2 universal) lives in `rank()`, not `retrieve()`.
**Rationale:** Retrieval is signal-agnostic (it produces candidate scores). Ranking is where selection decisions belong. This keeps retrieval clean and the blend logic testable.

### TD-3: Backward-compatible _recall_frequency signature
**Decision:** Add `last_recalled_at` and `now` as optional kwargs with defaults.
**Rationale:** Existing tests call `_recall_frequency(5)` without time args. Making them optional avoids breaking 20+ test calls while the new behavior only activates when both args are provided.

### TD-4: Prompt-only change for notable catches
**Decision:** FR-1 is implemented entirely as command file prompt changes, not Python code.
**Rationale:** The review learning capture is already a prompt instruction executed by Claude. Adding the notable catch logic is a prompt extension, not a code change. This is the simplest possible implementation.

---

## Interfaces

### I1: `RetrievalPipeline.retrieve()` — updated signature

```python
def retrieve(self, context_query: str | None, project: str | None = None) -> RetrievalResult:
    """Perform hybrid retrieval with optional project scoping."""
```

`RetrievalResult` gains an optional `project: str | None = None` field.

### I2: `RankingEngine._recall_frequency()` — updated signature

```python
def _recall_frequency(self, recall_count: int, last_recalled_at: str | None = None, now: datetime | None = None) -> float:
```

### I3: `RankingEngine.rank()` — unchanged signature, new project-blend behavior

```python
def rank(self, result: RetrievalResult, entries: dict, limit: int) -> list[dict]:
    # If result.project is set, apply two-tier blend
```

### I4: `_resolve_project_name()` — new helper in `injector.py`

```python
def _resolve_project_name(project_root: str) -> str | None:
    """Resolve project name from git remote origin or directory basename."""
```

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Project name mismatch between resolution and stored source_project | Medium | Medium | Use same git-remote-then-basename logic as store_memory |
| Two-tier blend returns fewer than limit when project has few entries | Medium | Low | Fill remainder from universal tier |
| Backward-compat break in _recall_frequency tests | Low | Low | Optional params with defaults preserve existing call sites |
| Notable catch prompt instruction ignored by Claude | Medium | Medium | Budget cap (2) limits damage; verify in retro |

---

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `plugins/pd/hooks/lib/semantic_memory/retrieval.py` | **Modified** | Add `project` param to `retrieve()` |
| `plugins/pd/hooks/lib/semantic_memory/retrieval_types.py` | **Modified** | Add `project` field to `RetrievalResult` |
| `plugins/pd/hooks/lib/semantic_memory/ranking.py` | **Modified** | Update `_recall_frequency()`, `_prominence()`, `rank()` |
| `plugins/pd/hooks/lib/semantic_memory/injector.py` | **Modified** | Add `_resolve_project_name()`, pass project to retrieve |
| `plugins/pd/commands/specify.md` | **Modified** | Add notable catch sub-section |
| `plugins/pd/commands/design.md` | **Modified** | Add notable catch sub-section |
| `plugins/pd/commands/create-plan.md` | **Modified** | Add notable catch sub-section |
| `plugins/pd/commands/create-tasks.md` | **Modified** | Add notable catch sub-section |
| `plugins/pd/commands/implement.md` | **Modified** | Add notable catch sub-section |
| `plugins/pd/hooks/lib/semantic_memory/test_ranking.py` | **Modified** | Tests for dampening |
| `plugins/pd/hooks/lib/semantic_memory/test_retrieval.py` | **Modified** | Tests for project filtering |
| `plugins/pd/hooks/lib/semantic_memory/test_injector.py` | **Modified** | Tests for project resolution |

## Test Strategy

1. **Ranking tests:** _recall_frequency with/without last_recalled_at, decay at 14/30/60 days, backward compat (no time args)
2. **Retrieval tests:** retrieve with project=None (unchanged), project="test" (two-tier split)
3. **Injector tests:** _resolve_project_name with git remote, without remote, fallback to dirname
4. **Integration test:** full pipeline with project filtering produces blended results
5. **Command file:** manual verification that notable catch prompt appears in all 5 files
