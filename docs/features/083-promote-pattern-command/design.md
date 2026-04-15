---
last-updated: 2026-04-16
feature: 083-promote-pattern-command
project: P002-memory-flywheel
---

# Design: /pd:promote-pattern

## Prior Art (Step 0 — abbreviated, YOLO)

Skipped formal research dispatch — the codebase was mapped during prior P002 investigations:
- **KB markdown parser exists** at `plugins/pd/hooks/lib/semantic_memory/importer.py:117` as `_parse_markdown_entries` — **private method, returns upsert-shaped dicts (no line ranges, no Promoted-marker handling)**. Cannot be cleanly reused without refactor; this design instead introduces a separate parser tailored to FR-1's needs.
- **Hook registration pattern** is in `plugins/pd/hooks/hooks.json` + `.sh` files following established conventions.
- **Slash-command pattern** is markdown files under `plugins/pd/commands/{name}.md`.
- **Skill-backed command precedent** is `/pd:retrospect` → `pd:retrospecting` (multi-stage stateful workflow with LLM calls + approval). Counter-example `/pd:remember` is single-shot inline.
- **Subprocess Python precedent** is `retrospecting/SKILL.md:231` — but only for write-only stores; this design extends the pattern to structured returns.

## Architecture Overview

A **slash command** (`/pd:promote-pattern`) backed by a **supporting skill** (`pd:promoting-patterns`) that holds the multi-stage workflow logic. Command file is the entrypoint per pd convention; skill carries reusable steps. Python helpers under `plugins/pd/hooks/lib/pattern_promotion/` provide deterministic operations.

```
User → /pd:promote-pattern [name?]
         ↓
       commands/promote-pattern.md  (entrypoint, ~50 lines)
         ↓ (Skill dispatch)
       skills/promoting-patterns/SKILL.md  (logic core, ~250 lines)
         ↓
       ┌─ Step 1: Enumerate KB        → pattern_promotion/kb_parser.py
       ├─ Step 2: Classify target     → classifier.py + (optional) inline LLM
       ├─ Step 3: Generate diff       → generators/{hook,skill,agent,command}.py
       ├─ Step 4: Approval gate       → AskUserQuestion + edit-content path
       └─ Step 5: Apply (5-stage)     → apply.py
```

## Pipeline Stage Ownership

Maps every spec FR-1..FR-6 sub-step to its executor (resolves design-reviewer Blocker 1):

| Spec sub-step | Owner | Notes |
|---|---|---|
| FR-1 enumeration | `pattern_promotion/kb_parser.py::enumerate_qualifying_entries` | Pure Python; tests independent of skill |
| FR-1 listing UX (AskUserQuestion / substring match / disambiguation) | **skill markdown** | Reads enumerator's JSON; chooses display path |
| FR-2a keyword scoring | `pattern_promotion/classifier.py::classify_keywords` | Pure Python; deterministic |
| FR-2b tie-break decision | `pattern_promotion/classifier.py::decide_target` | Pure Python; returns winner-or-None |
| FR-2c LLM fallback | **skill markdown** (inline orchestrator reasoning) | Constrained prompt; output validated against closed enum (FR-2c) |
| FR-2d user override | **skill markdown** (AskUserQuestion) | CLAUDE.md never offered |
| FR-3-hook step 1 (feasibility gate) | **skill markdown** (inline LLM call) | Output validated by `pattern_promotion/generators/hook.py::validate_feasibility` |
| FR-3-hook step 2 (skeleton generation) | `pattern_promotion/generators/hook.py::generate` | Pure Python templates |
| FR-3-hook step 3 (slug collision) | `pattern_promotion/generators/hook.py::generate` | Auto-suffix |
| FR-3-{skill,agent,command} step 1 (Top-3 LLM) | **skill markdown** (inline LLM) | Pool list provided by `pattern_promotion/inventory.py::list_targets(target_type)` |
| FR-3-{skill,agent,command} step 2 (AskUserQuestion select) | **skill markdown** | Top-3 + Other + cancel |
| FR-3-{skill,agent,command} step 3 (section/step ID + re-ask) | **skill markdown** (inline LLM, max 1 re-ask) | Output validated by `generators/{skill,agent,command}.py::validate_target_meta` (heading/step exists) |
| FR-3-{skill,agent,command} step 4 (patch generation) | `pattern_promotion/generators/{skill,agent,command}.py::generate` | Pure Python |
| FR-4 approval gate | **skill markdown** (AskUserQuestion + edit-content capture) | DiffPlan rendered for preview |
| FR-5 stages 1-5 | `pattern_promotion/apply.py::apply` | Single Python entrypoint; all 5 stages atomic; emits stage progress |
| FR-6 CLAUDE.md exclusion | LLM prompts (FR-2c) + AskUserQuestion options (FR-2d) | Never reaches generator |

Skill markdown is the orchestrator; Python is the deterministic core. **Every LLM call is in skill markdown; every deterministic operation is in Python.**

## Subprocess Serialization Contract (resolves design-reviewer Blocker 2)

Skill markdown invokes Python helpers via `Bash` tool subprocess. Contract:

1. **Compact status JSON on stdout** — every helper emits a single JSON object on its last line of stdout. Fields:
   - `status`: `"ok"` | `"error"` | `"need-input"`
   - `data_path`: optional path to a sandbox file containing the bulky artifact (DiffPlan, parsed entries list, etc.)
   - `summary`: human-readable one-line summary
   - `error`: optional error message (when `status="error"`)
2. **Bulky artifacts written to `agent_sandbox/{date}/promote-pattern-{ts}/`** — sandbox dir per command invocation. Files:
   - `entries.json` — output of enumerate
   - `scores.json` — classifier output
   - `diff_plan.json` — generator output (full file contents in JSON-encoded strings)
   - `apply_result.json` — apply orchestrator outcome
3. **Skill reads sandbox files via `Read` tool**, parses JSON, branches on contents.
4. **Exit codes**: 0 on success/need-input, non-zero on error. Stderr captures stack traces and warning logs.
5. **Cleanup**: skill `rm -rf` the sandbox dir on completion (success OR cancel) — not on `error` (leave for debugging).

Example skill markdown step:
```bash
DATE_DIR="agent_sandbox/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"
SANDBOX=$(mktemp -d "$DATE_DIR/promote-pattern-XXXXXX")
plugins/pd/.venv/bin/python -m pattern_promotion enumerate --sandbox "$SANDBOX" --kb-dir docs/knowledge-bank
# → stdout: {"status":"ok","data_path":"<SANDBOX>/entries.json","summary":"7 qualifying entries"}
```
Then skill `Read`s `entries.json` and continues.

**Stale-sandbox opportunistic cleanup:** skill markdown runs `find agent_sandbox -type d -name 'promote-pattern-*' -mtime +7 -exec rm -rf {} +` near invocation start to sweep stale sandboxes from prior runs that failed to clean up. This removes reliance on markdown-level try/finally discipline for the normal cleanup path.

## Components

### C-1: Command entrypoint — `plugins/pd/commands/promote-pattern.md`
~50 lines. Receives optional `<entry-name>` argument. Validates `--help`. Dispatches the `pd:promoting-patterns` skill with parsed args.

### C-2: Logic skill — `plugins/pd/skills/promoting-patterns/SKILL.md`
~250 lines. Markdown-driven orchestrator. Contains step-by-step instructions (FR-1..FR-6) including the LLM-driven steps (Top-3 selection, classification fallback, section identification). All LLM calls in skill markdown follow the **constrained-prompt + validate-output-against-schema** pattern.

### C-3: KB parser — new `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py`
**Standalone parser** — does not extend `semantic_memory/importer.py` (private method, wrong return shape, no line ranges). Implements:
- `enumerate_qualifying_entries(kb_dir, min_observations) -> list[KBEntry]`
- `KBEntry` dataclass: `name, description, confidence, effective_observation_count, category, file_path, line_range`
- Marker detection: skips entries containing `- Promoted: ` line.
- `effective_observation_count` per FR-1 normalization (Observation count field OR distinct Feature # count OR 0).

The existing `importer._parse_markdown_entries` is unchanged. **No coupling between import flow and promote-pattern flow** — both can evolve independently.

### C-4: Classifier — new `plugins/pd/hooks/lib/pattern_promotion/classifier.py`
- `KEYWORD_PATTERNS: dict[str, list[re.Pattern]]` — single source of truth for FR-2a regex tables; compiled at module load with `re.IGNORECASE`.
- `classify_keywords(entry: KBEntry) -> dict[str, int]`
- `decide_target(scores: dict) -> Optional[str]` — strict-highest winner or None.

### C-5: Inventory helper — new `plugins/pd/hooks/lib/pattern_promotion/inventory.py`
Provides candidate pools for FR-3-{skill,agent,command} Top-3 selection:
- `list_skills() -> list[str]` — skill directory names under `plugins/pd/skills/`
- `list_agents() -> list[str]` — agent file basenames under `plugins/pd/agents/`
- `list_commands() -> list[str]` — command file basenames under `plugins/pd/commands/`

Skill markdown reads these and feeds Top-3 LLM prompt with the appropriate pool. Output bounded (~30 names → ~500 tokens).

### C-6: Per-target generators — new `plugins/pd/hooks/lib/pattern_promotion/generators/`
Four modules, each exposing `generate(entry, target_meta) -> DiffPlan`:
- `hook.py` — `target_meta = {feasibility: {event, tools[], check_kind, check_expression}}`. Generates `.sh` + `hooks.json` patch + test stub. Plus `validate_feasibility(feasibility) -> bool` for FR-3-hook step 1 schema check (rejects empty `tools`, unknown enums).
- `skill.py` — `target_meta = {skill_name, section_heading, insertion_mode}`. Plus `validate_target_meta(target_meta) -> bool` (heading exists in target file).
- `agent.py` — `target_meta = {agent_name, section_heading, insertion_mode}`. Same validator.
- `command.py` — `target_meta = {command_name, step_id, insertion_mode}`. Same validator.

### C-7: Apply orchestrator — new `plugins/pd/hooks/lib/pattern_promotion/apply.py`
Single function `apply(entry, diff_plan, target_type) -> Result` running 5 stages with stage-boundary progress logs to stderr (visible to skill via stderr capture in Bash). Handles snapshot/rollback/baseline-delta-validate.

### C-8: CLI entrypoint — new `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
Subcommands: `enumerate`, `classify`, `generate`, `apply`, `mark`. Each takes `--sandbox <dir>` and optional flags. Used by skill markdown via subprocess; also enables direct unit/integration testing without the skill layer.

### C-9: Config field — `.claude/pd.local.md` template
`memory_promote_min_observations: 3` under `# Memory` block.

## Technical Decisions

### TD-1: Skill-as-logic, command-as-entry — **criterion explicit**
**Criterion:** A pd command warrants a backing skill when the workflow has (a) >1 LLM call in sequence, (b) stateful approval loops, OR (c) rollback semantics. `/pd:promote-pattern` has all three; `/pd:remember` has none.

### TD-2: New parser, not importer reuse
Original plan to extend `semantic_memory/importer.py` was rejected after design review: the existing parser is private (`_parse_markdown_entries`), returns DB-upsert-shaped dicts without line ranges, and has no Promoted-marker awareness. Standalone `pattern_promotion/kb_parser.py` is cleaner. **Acknowledged tradeoff:** small parsing-logic duplication. **Mitigation:** if a future feature needs a unified parser, extract a shared module then; YAGNI now.

### TD-3: Subprocess Python via sandbox-file artifacts + stdout status JSON
Per the Subprocess Serialization Contract above. Helpers emit compact status JSON on stdout; bulky outputs go to `agent_sandbox/.../promote-pattern-{ts}/`. Skill `Read`s sandbox files. Exit code 0 = success or need-input; non-zero = error. Stderr for diagnostics.

### TD-4: Inline LLM for classification + Top-3 + section ID
Skill markdown invokes the orchestrating LLM directly for FR-2c, FR-3-* Top-3, and FR-3-* section identification. **Mitigation against context pollution (per design-reviewer warning):** every LLM step has (a) a constrained prompt enumerating valid output schema, (b) validation of LLM output against closed enum or file-existence check, (c) at most one re-ask, (d) **FR-2d user override is the explicit safety net** — user always sees and can override classification before any write.

### TD-5: Baseline-delta validation via validate.sh
Captures `validate.sh` output immediately after Stage 2 (snapshot) and again after Stage 3 (write). Rollback only on NEW errors.

### TD-6: KB marker is line-level
`- Promoted: {target_type}:{repo-relative path}` markdown bullet. Survives re-parsing.

### TD-7: Hook feasibility gate is LLM + post-generation positive/negative test execution
**Strengthened per design-reviewer warning:** the generated `test-{slug}.sh` contains two invocations internally — one positive (input that should be blocked by the hook) and one negative (input that should pass). The script exits non-zero if either case produces the wrong verdict. Stage 4 runs the test script once; non-zero exit → rollback. This forces feasibility honesty: an LLM-claimed-feasible hook that doesn't distinguish must fail its own test.

### TD-8: In-memory snapshot rollback (no transaction wrapper)
Documented limitation: SIGINT between Stage 3 and Stage 5 leaves target files written without KB marker.

**Hook-target partial-run detection:** every generated hook `.sh` emits a leading comment header `# Promoted from KB entry: {entry_name}` (added by `hook.py::generate`). Stage 1 pre-flight scans `plugins/pd/hooks/*.sh` for this exact comment line matching the current entry's name; if any file contains the marker comment, abort with "possible prior partial run from {file}, manual check required". This resolves the slug auto-suffix drift concern.

Skill/agent/command targets are file-modify (not file-create). SIGINT after Stage 3 leaves the file modified; re-run re-enumerates the entry (no KB marker yet) and on re-apply the diff may produce a conflicting insertion. Mitigation: skill/agent/command generators include a `# Promoted: <entry-name>` marker comment in the appended block; Stage 1 pre-flight detects the marker and aborts. Documented in error table.

## Risks

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| LLM classification drift across sessions | Medium | Low | FR-2d user override always available (TD-4) |
| `hooks.json` schema evolves | Low | Medium | Validate JSON post-patch (Stage 4); use existing JSON tooling |
| Mid-flight SIGINT (Stage 3-5) | Low | Low | Stage 1 collision check (TD-8); user re-runs |
| `validate.sh` baseline-delta false positive (timing-sensitive checks) | Low | Medium | Compare error count + categories |
| Skill discovery list bloat (>30 skills) | Low | Low | Cap at 30; pre-filter by keyword overlap |
| User edit-content corrupts markdown structure | Medium | Low | Stage 4 catches; rollback restores |
| LLM-claimed-feasible hook that doesn't fire | Medium | Medium | TD-7: positive/negative test execution at Stage 4 |
| Sandbox dir not cleaned after error | Low | Low | Documented; leaves debugging artifacts intentionally |

## Interfaces

### I-1: `enumerate_qualifying_entries(kb_dir: Path, min_observations: int) -> list[KBEntry]`
**Module:** `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py`
```python
def enumerate_qualifying_entries(
    kb_dir: Path,
    min_observations: int = 3,
) -> list[KBEntry]:
    """Return KB entries meeting promotion criteria. Excludes constitution.md
    and entries already containing '- Promoted:' marker."""
```

### I-2: `classify_keywords(entry: KBEntry) -> dict[str, int]`
**Module:** `plugins/pd/hooks/lib/pattern_promotion/classifier.py`

### I-3: `decide_target(scores: dict) -> Optional[Literal['hook','skill','agent','command']]`
**Module:** Same as I-2.

### I-4: `list_targets(target_type) -> list[str]` (and per-type variants)
**Module:** `plugins/pd/hooks/lib/pattern_promotion/inventory.py`

### I-5: `generate(entry: KBEntry, target_meta: dict) -> DiffPlan` (per generator)
**Modules:** `plugins/pd/hooks/lib/pattern_promotion/generators/{hook,skill,agent,command}.py`

`target_meta` schemas:
- **hook:** `{feasibility: {event: str, tools: list[str], check_kind: str, check_expression: str}}`
- **skill:** `{skill_name: str, section_heading: str, insertion_mode: Literal['append-to-list','new-paragraph-after-heading']}`
- **agent:** Same as skill but `agent_name`.
- **command:** `{command_name: str, step_id: str, insertion_mode: ...}`

Each generator also exports `validate_target_meta(target_meta) -> bool` for FR-3 step 3 validation.

### I-6: `DiffPlan` and `FileEdit` dataclasses (with ordering contract)
```python
@dataclass
class FileEdit:
    path: Path                   # absolute
    action: Literal['create', 'modify']
    before: Optional[str]        # None for create
    after: str
    write_order: int             # lower = earlier; ties broken by path

@dataclass
class DiffPlan:
    edits: list[FileEdit]        # sorted by write_order ascending
    target_type: Literal['hook', 'skill', 'agent', 'command']
    target_path: Path            # primary target file (for KB marker); for hook=the .sh, for skill/agent/command=the modified file

# Hook target write_order: .sh=0, test-.sh=1, hooks.json=2 (must be last)
# Single-file targets: write_order=0
```
Rollback per FileEdit: `modify` → restore `before`; `create` → unlink.

### I-7: `apply(entry, diff_plan, target_type) -> Result`
**Module:** `plugins/pd/hooks/lib/pattern_promotion/apply.py`
```python
@dataclass
class Result:
    success: bool
    target_path: Optional[Path]  # repo-relative
    reason: Optional[str]
    rolled_back: bool
    stage_completed: int         # 0-5; for diagnostics
```
Emits stage-boundary log lines to stderr: `[promote-pattern] Stage N: <name>` so skill can show progress.

### I-8: CLI subcommands
**Module:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
- `enumerate --sandbox <dir> --kb-dir <path> [--min-observations N]`
- `classify --sandbox <dir> --entry-name <name>`
- `generate --sandbox <dir> --entry-name <name> --target-type <type> --target-meta-file <path>` — pre-checks target_meta schema via the generator's `validate_target_meta` / `validate_feasibility`; returns `status="need-input"` with explanation if malformed (avoids separate validate-feasibility subcommand)
- `apply --sandbox <dir> --entry-name <name>`
- `mark --kb-file <path> --entry-name <name> --target-type <type> --target-path <path>`

All subcommands write JSON status to stdout per Subprocess Serialization Contract.

### I-9: Config field
`.claude/pd.local.md` template gains `memory_promote_min_observations: 3`.

### I-10: Command argument shape
`/pd:promote-pattern [<entry-name-substring>]` or `/pd:promote-pattern --help`.

## Out of Scope (Design)

- **Backporting promotion for constitution.md entries** — already hard rules.
- **Cross-project promotion** — only current `docs/knowledge-bank/`.
- **Reverse promotion (un-promote)** — manual KB edit.
- **Auto-promotion daemon** — explicit per spec.
- **Refactoring `_parse_markdown_entries` to public API** (TD-2) — separate cleanup if/when needed.
- **Sandbox cleanup on error** — leave for debugging.

## Component Dependencies

```
promote-pattern.md (command)
  └── promoting-patterns/SKILL.md (skill)
        ├── pattern_promotion/__main__ enumerate → kb_parser.py
        ├── pattern_promotion/__main__ classify  → classifier.py
        ├── pattern_promotion/__main__ generate  → generators/{hook,skill,agent,command}.py
        ├── pattern_promotion/__main__ apply     → apply.py
        │     ├── (Stage 4) ./validate.sh
        │     └── (TD-7 hook target) test-{slug}.sh execution
        └── pattern_promotion/__main__ mark      → kb_parser.py marker append
```

## Testing Strategy

- **Unit (pytest, direct import — no skill layer):**
  - `kb_parser.py`: marker exclusion, observation_count normalization, line range capture
  - `classifier.py`: regex scoring (positive + negative cases per FR-2a row), tie-break logic
  - `inventory.py`: directory scan correctness
  - Each `generators/*.py`: deterministic output for canonical inputs; `validate_*` helpers
  - `apply.py`: 5-stage flow with synthetic DiffPlan; mock validate.sh for baseline-delta; SIGINT simulation
- **Integration (pytest with `__main__.py` CLI):**
  - End-to-end CLI invocations against fixture KB dirs
  - Sandbox file roundtrip
- **Manual end-to-end (Acceptance Evidence, per spec):**
  - Promote real KB pattern to each of {hook, skill, agent}; confirm marker, target file, validate.sh
  - TD-7 verification: feasible hook actually fires; infeasible hook is rejected
