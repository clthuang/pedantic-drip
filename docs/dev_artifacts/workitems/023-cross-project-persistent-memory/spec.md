# Spec: Cross-Project Persistent Memory System

## Overview
Make iflow's knowledge bank consumable by injecting entries into session context at startup, and enable cross-project knowledge transfer by promoting universal entries to a global store during retrospectives.

Covers PRD Phases 1 (intra-project consumption + global store bootstrap) and Phase 2 (cross-project injection).

## Components

### Component 1: Session-Start Memory Injection

**File:** `plugins/iflow-dev/hooks/session-start.sh`

**What changes:**
- New function `build_memory_context()` reads knowledge bank entries and returns formatted markdown for injection
- `build_context()` calls `build_memory_context()` and **prepends** the result before the workflow state context. This places memory at the beginning of additionalContext, maximizing recall per "Lost in the Middle" research. The workflow state (active feature, branch, phase) follows after.
- Respects `iflow-dev.local.md` config fields `memory_injection_enabled` (default: `true`) and `memory_injection_limit` (default: `20`)

**Injection source priority (Phase 1):**
1. Project-local `docs/dev_artifacts/knowledge-bank/anti-patterns.md` — highest priority (prevent known mistakes)
2. Project-local `docs/dev_artifacts/knowledge-bank/heuristics.md` — second priority (apply known shortcuts)
3. Project-local `docs/dev_artifacts/knowledge-bank/patterns.md` — third priority (reinforce good practices)

**Injection source priority (Phase 2 — added when global store exists):**
4. Global store `~/.claude/iflow/memory/anti-patterns.md` — universal anti-patterns from other projects
5. Global store `~/.claude/iflow/memory/heuristics.md` — universal heuristics from other projects
6. Global store `~/.claude/iflow/memory/patterns.md` — universal patterns from other projects

**Deduplication:** If an entry exists in both project-local and global, deduplicate by computing an ephemeral content hash for local entries and matching against global store hashes. Include only the version with higher observation count.

**Entry parsing:**

The knowledge bank files have varying formats that the parser must handle:

| File | Header format | Metadata fields |
|------|--------------|-----------------|
| `anti-patterns.md` | `### Anti-Pattern: {Name}` | `Observed in:`, `Cost:`, `Instead:`, `Last observed:`, `Observation count:` |
| `patterns.md` | `### Pattern: {Name}` | `Used in:`, `Benefit:`, `Example:` |
| `heuristics.md` | `### {Name}` (no type prefix) | `Source:`, `Confidence:` (sometimes absent) |

Parser rules:
- Entry boundary: any line starting with `### ` (three hashes + space)
- Entry name: text after `### ` with optional `{Type}: ` prefix stripped
- Description text: all lines between the `###` header and the first `- ` metadata line. Example: for `### Anti-Pattern: Working in Wrong Worktree\nMaking changes in main worktree when a feature worktree exists.\n- Observed in: Feature #002`, the description is `Making changes in main worktree when a feature worktree exists.`
- Extract `Observation count: {N}` (default 1 if field missing)
- Extract `Confidence: {level}` (default "medium" if field missing)

Sort order: observation count desc, then confidence (high > medium > low), tiebreak by file position descending (later/newer entries first — newer entries are appended at the end of files, so higher file position = more recent). Global store entries have `Last observed: {ISO date}` for proper recency sorting instead of file position.

**Injection format:**
```markdown
## Engineering Memory (from knowledge bank)

### Anti-Patterns to Avoid
{top anti-pattern entries, formatted as-is from source file}

### Heuristics
{top heuristic entries}

### Patterns to Follow
{top pattern entries}

---
```

**Ordering:** Per "Lost in the Middle" research — anti-patterns (highest priority) at the beginning of the memory block, patterns at the end, heuristics in the middle. The entire memory block is prepended before workflow state. Splitting memory around workflow state would fragment both, reducing coherence.

**Token budget:** The limit is applied globally across all categories and sources. Fill strategy:
1. Collect all entries from all sources (local + global), deduplicated by content hash
2. Sort entries into their category buckets (anti-patterns, heuristics, patterns)
3. Allocate a minimum of 3 entries per non-empty category (ensuring breadth)
4. Fill remaining budget by category priority: anti-patterns first, then heuristics, then patterns
5. Within each category, entries are sorted by observation count desc, confidence desc, then recency

This ensures that even with 15 high-observation-count anti-patterns, the user still sees at least 3 heuristics and 3 patterns (if available). If the global limit is less than 3 * (number of non-empty categories), skip the minimum guarantee and fall back to pure priority-based allocation.

**Event filtering:**
- `startup` event: inject memory (fresh session)
- `resume` event: inject memory (returning to session)
- `clear` event: skip memory injection (post-compact, avoid re-inflating context)

**Detection:** Claude Code passes the event type via stdin JSON with a `source` field (values: `startup`, `resume`, `clear`, `compact`). The current session-start.sh does not read stdin. The new `build_memory_context()` function must read stdin early in `main()` and pass the source value through. Implementation:
```bash
# Read stdin JSON and extract source (at top of main(), before build_context)
EVENT_SOURCE=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('source','startup'))" 2>/dev/null || echo "startup")
```
Skip memory injection when `EVENT_SOURCE` is `clear` or `compact`. Note: stdin can only be read once, so this must happen before any other stdin reading. Each SessionStart hook is invoked as a separate process receiving its own copy of stdin, so consuming stdin here does not affect other hooks.

**Fallback approach (if stdin `source` field is unavailable or unverified during design):** Split the hooks.json SessionStart entry for session-start.sh into two matchers:
- `"matcher": "startup|resume"` → runs session-start.sh with memory injection
- `"matcher": "clear"` → runs session-start.sh with `SKIP_MEMORY=1` environment variable (or a separate lightweight script)
This avoids stdin parsing entirely and is a proven pattern since hooks.json already supports matcher-based routing. Design phase should verify which approach is used.

**Acceptance criteria:**
- [ ] AC-1.1: Session starts with knowledge bank entries visible in additionalContext
- [ ] AC-1.2: `memory_injection_enabled: false` in `iflow-dev.local.md` suppresses injection entirely
- [ ] AC-1.3: Entry count does not exceed `memory_injection_limit` value
- [ ] AC-1.4: Anti-patterns appear before heuristics in injected content
- [ ] AC-1.5: Entries are sorted by observation count descending, then confidence (high > medium > low), within each category
- [ ] AC-1.6: No injection occurs on `clear` events (post-compact)
- [ ] AC-1.7: Empty knowledge bank (no files or empty files) produces no injection and no errors
- [ ] AC-1.8: Memory injection function (`build_memory_context()`) completes in <3s with 500 synthetic entries. Measurement: `python3 -c "import time; print(time.monotonic())"` before/after (macOS-compatible — BSD `date` does not support `%N` nanoseconds). The 3s budget is for memory injection alone, not total session-start hook time.

### Component 2: Global Memory Store

**Path:** `~/.claude/iflow/memory/`

**Files:**
- `~/.claude/iflow/memory/patterns.md`
- `~/.claude/iflow/memory/anti-patterns.md`
- `~/.claude/iflow/memory/heuristics.md`

**Entry format (richer than project-local):**
```markdown
### {Type}: {Name}
{Description text}
- Content-Hash: sha256:{first 16 chars of hash}
- Source: {project-name}, Feature #{NNN}
- Observation count: {N}
- Last observed: {ISO date}
- Tags: universal
- Confidence: {high|medium|low}
```

**File header:**
```markdown
# Global {Patterns|Anti-Patterns|Heuristics}

Cross-project learnings promoted from retrospectives. Automatically managed by iflow.
Do not edit manually — entries are updated during /finish.
```

**Content hash:** SHA-256 of the entry description text, normalized by: lowercasing, stripping leading/trailing whitespace, collapsing multiple spaces to single space. Store first 16 hex characters.

Description text extraction: all lines between the `###` header line and the first line starting with `- ` (metadata). Example:
```
### Anti-Pattern: Working in Wrong Worktree     ← header (not hashed)
Making changes in main worktree when a feature   ← description (hashed)
worktree exists.                                  ← description (hashed)
- Observed in: Feature #002                       ← metadata (not hashed)
```
For entries where description is on the same line as header (rare), the description is empty and the hash is computed from an empty string — these entries will not match anything, which is correct (they are malformed).

**Bootstrapping:** Directory and files created on first promotion (Step 4c of retrospecting skill). No pre-creation needed. If `~/.claude/iflow/` doesn't exist, `mkdir -p` before writing.

**Acceptance criteria:**
- [ ] AC-2.1: Global store files follow the entry format above
- [ ] AC-2.2: Content hash is consistent — same text always produces same hash
- [ ] AC-2.3: Store is human-readable markdown (can be opened and understood in any editor)
- [ ] AC-2.4: Missing directory/files are created on first write without errors

### Component 3: Knowledge Promotion in Retrospecting Skill

**File:** `plugins/iflow-dev/skills/retrospecting/SKILL.md`

**What changes:** Add Step 4c after existing Step 4b (knowledge bank validation).

**Step 4c: Promote to Global Store**

For each entry written in Step 4 (new entries only, not pre-existing entries validated in Step 4b):

1. **Classify:** Determine if entry is universal or project-specific
   - **Universal (default):** Entry describes general engineering wisdom, workflow patterns, tool usage, or coding practices that apply regardless of codebase
   - **Project-specific:** Entry references specific file paths, architecture component names, domain-specific APIs, or project-unique configurations
   - Classification is LLM-judgment-based (performed by Claude during the retro skill) and therefore non-deterministic. The SKILL.md should provide anchoring examples:
     - **Universal example:** "Always read the target file before writing a parser" — no project references
     - **Universal example:** "Break tasks into one-file-per-task granularity" — general workflow wisdom
     - **Project-specific example:** "The secretary agent's routing table must match hooks.json matchers" — references iflow-specific architecture
     - **Project-specific example:** "The session-start.sh Python subprocess adds ~200ms per call" — references a specific file
   - Classification includes reasoning in retro output: e.g., "Universal because: no project-specific references detected"

2. **For universal entries — check for duplicates:**
   - Read the corresponding global store file (`~/.claude/iflow/memory/{category}.md`)
   - Compute content hash of the new entry
   - If a matching content hash exists: increment that entry's observation count, update `Last observed` date, append source provenance. Do NOT create a new entry.
   - If no match: append new entry with content hash, source provenance, observation count 1

3. **For project-specific entries:** Skip promotion. Entry stays in project-local knowledge bank only.

4. **Report:** After promotion, output summary:
   ```
   Memory promotion: {N} universal entries promoted to global store, {M} project-specific entries kept local.
   ```

**Line budget:** Step 4c should be ~20-25 lines in SKILL.md. Total SKILL.md must stay under 500 lines.

**Acceptance criteria:**
- [ ] AC-3.1: Universal entries from retro appear in `~/.claude/iflow/memory/` after /finish
- [ ] AC-3.2: Project-specific entries do NOT appear in global store
- [ ] AC-3.3: Duplicate entries (same content hash) increment observation count instead of creating copies
- [ ] AC-3.4: Provenance includes project name and feature ID
- [ ] AC-3.5: SKILL.md stays under 500 lines after changes
- [ ] AC-3.6: Classification reasoning is included in retro output (e.g., "Universal because: no project-specific references")

### Component 4: Configuration

**File:** `plugins/iflow-dev/templates/iflow-dev.local.md` (template update)

**New fields in YAML frontmatter:**
```yaml
memory_injection_enabled: true
memory_injection_limit: 20
```

**Read via:** `read_local_md_field` from `lib/common.sh` (existing utility, no changes needed)

**Note:** Config fields are added to the EXISTING `iflow-dev.local.md` file (the same file that holds `yolo_mode`). No new config file is created. PRD references to `memory.local.md` are superseded by this spec — all memory config lives in `iflow-dev.local.md`.

**Behavior:**
- Fields are optional. Missing fields use defaults (enabled=true, limit=20).
- `memory_injection_enabled: false` suppresses all memory injection (both local and global)
- `memory_injection_limit: 0` means inject nothing (same as disabled)
- `memory_injection_limit: -1` means inject all (no limit)

**Acceptance criteria:**
- [ ] AC-4.1: Default behavior (no config fields) injects up to 20 entries
- [ ] AC-4.2: `memory_injection_enabled: false` suppresses injection
- [ ] AC-4.3: Custom `memory_injection_limit` value is respected
- [ ] AC-4.4: Template file documents the new fields

### Component 5: Usage Tracking

**Mechanism:** The session-start hook writes a tracking file after injection.

**File:** `~/.claude/iflow/memory/.last-injection.json`

**Content:**
```json
{
  "timestamp": "2026-02-17T02:45:00Z",
  "project": "my-ai-setup",
  "entries_injected": 15,
  "sources": {
    "local": 10,
    "global": 5
  },
  "entry_names": ["Anti-Pattern: Over-Granular Tasks", "Heuristic: Read Before Write", ...]
}
```

**Purpose:** Enables future retro analysis to check which entries were in context during a feature's development.

**Limitation:** Only the most recent injection is tracked (overwritten each session). Historical tracking across sessions is out of scope for this feature. Retro analysis of injection effectiveness (correlating injected entries with feature outcomes, per PRD SC-4) is deferred — the retrospecting skill does not yet read this file. This tracking file provides the data foundation for future correlation.

**Acceptance criteria:**
- [ ] AC-5.1: Tracking file is written after each successful injection
- [ ] AC-5.2: Tracking file contains project name, entry count, and entry names
- [ ] AC-5.3: Previous tracking file is overwritten (only last injection tracked)

## PRD Success Criteria Traceability

| PRD Criterion | Spec Coverage | Status |
|---------------|---------------|--------|
| SC-1: Knowledge bank entries injected at session start | Component 1 (Phase 1 sources) | Fully covered |
| SC-2: Learning from Project A visible in Project B | Component 1 (Phase 2 sources) + Component 3 (promotion) | Fully covered |
| SC-3: Token cost bounded with configurable limit | Component 4 (`memory_injection_limit`) + Component 1 (fill strategy) | Fully covered |
| SC-4: Anti-pattern recurrence tracking via observation counts + retro analysis | Observation counts: Component 2 entry format. Retro correlation: **deferred** — tracking file written (Component 5) but retro skill does not consume it yet | Partially covered |
| SC-5: Usage tracking shows which entries were in context | Component 5 (`.last-injection.json`) — overwrite-only, no history | Partially covered |

## Scope Boundaries

**In scope:**
- session-start.sh: add `build_memory_context()` function and integrate with `build_context()`
- retrospecting SKILL.md: add Step 4c (~20-25 lines)
- Global store directory structure and entry format
- `iflow-dev.local.md` template: add memory config fields
- Usage tracking file write

**Out of scope:**
- SQLite/FTS5 indexing (Phase 3)
- MCP memory server (Phase 4)
- Semantic search or embeddings
- Stop hook capture
- Memory consolidation/compression
- Modifying the constitution.md file (not part of injection)

## Interface Contracts

### session-start.sh → Claude Code
The existing contract is maintained: hook outputs JSON with `hookSpecificOutput.additionalContext`. Memory content is prepended before workflow state in the context string. No new JSON fields introduced. Memory injection adds approximately 2,100 tokens (20 entries x ~105 tokens/entry) to the session-start additionalContext. Combined with secretary context and workflow state, total SessionStart context injection should be monitored — if total exceeds ~5,000 tokens, reduce the default `memory_injection_limit`.

### retrospecting skill → global store
Write path only. The skill uses Write/Edit tools to create/update markdown files at `~/.claude/iflow/memory/`. No new tool types required.

### config → hook
`read_local_md_field` reads `iflow-dev.local.md` from `${PROJECT_ROOT}/.claude/`. No changes to the utility function. New field names: `memory_injection_enabled`, `memory_injection_limit`.

## Error Handling

| Error | Handling | Rationale |
|-------|----------|-----------|
| Knowledge bank files missing | Skip injection, no error | New projects won't have knowledge bank yet |
| Global store directory missing | Skip global entries in injection; create on first promotion | Bootstraps on first retro |
| `iflow-dev.local.md` missing | Use defaults (enabled, limit 20) | Zero-config experience |
| Malformed entry (no observation count) | Default to observation count 1 | Backward compatibility with older entries |
| Content hash collision (different text, same hash) | Extremely unlikely with SHA-256; if it occurs, append as new entry | Correctness over dedup |
| Global store file has write permission error | Log warning to stderr, skip promotion, don't fail retro | Retro is more valuable than promotion |
| Hook timeout (>3s) | session-start.sh already has implicit timeout from Claude Code | No additional timeout handling needed |

## Migration

No migration needed. The system operates on new files:
- Global store is created fresh on first promotion
- session-start.sh changes are additive (new function, called from existing build_context)
- Existing knowledge bank entries are read as-is (backward compatible entry format)
- Config fields are optional with defaults

## Testing Strategy

**Manual validation:**
1. Start a session with knowledge bank populated → verify entries appear in context
2. Set `memory_injection_enabled: false` → verify no entries appear
3. Run a retro that produces a universal entry → verify it appears in `~/.claude/iflow/memory/`
4. Run a retro that produces a project-specific entry → verify it does NOT appear in global store
5. Start a session in a different project → verify global store entries appear
6. Run a retro that produces a duplicate → verify observation count increments

**Automated checks (via validate.sh):**
- SKILL.md line count < 500
- hooks.json still valid JSON
- No syntax errors in session-start.sh (bash -n)
