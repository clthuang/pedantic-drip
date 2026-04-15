---
last-updated: 2026-04-16
feature: 083-promote-pattern-command
---

# Plan: /pd:promote-pattern

## Implementation Order

```
Phase 1: Python scaffolding (kb_parser, classifier, inventory)
    ↓
Phase 2: Generators (hook, skill, agent, command)
    ↓
Phase 3: Apply orchestrator + KB marker (Stage 5)
    ↓ (independent, can parallel with Phase 2)
Phase 4: CLI entrypoint + skill markdown + command file
    ↓
Phase 5: End-to-end verification (3 manual promotions)
```

## Phase 1: Python Scaffolding (C-3, C-4, C-5, C-8 package init)

**Why:** Pure-deterministic helpers must land first — they are dependencies for Phase 2 generators. TDD: test each in isolation before using.
**Why this order:** Zero external dependencies (other than stdlib + repo files). Parallel-safe within the phase.
**Complexity:** Low

### Steps (TDD first):
1. `plugins/pd/hooks/lib/pattern_promotion/__init__.py` + `__main__.py` package skeleton.
2. `pattern_promotion/kb_parser.py` + `test_kb_parser.py` — `KBEntry` dataclass, `enumerate_qualifying_entries`. Tests for marker-exclusion, observation-count normalization, line-range capture.
3. `pattern_promotion/classifier.py` + `test_classifier.py` — `KEYWORD_PATTERNS`, `classify_keywords`, `decide_target`. Tests per FR-2a row (positive + negative), tie-break logic, all-zero case.
4. `pattern_promotion/inventory.py` + `test_inventory.py` — `list_skills`, `list_agents`, `list_commands`. Simple directory scans against fixture dirs.

**Done when:** All Phase 1 pytest files green; `plugins/pd/.venv/bin/python -m pattern_promotion --help` prints usage (even if subcommands not implemented yet).

**Key files:**
- `plugins/pd/hooks/lib/pattern_promotion/__init__.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/__main__.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/classifier.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/inventory.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/test_*.py` (new)

## Phase 2: Per-Target Generators (C-6)

**Why:** Each target requires its own DiffPlan generator with validation. Isolated from apply orchestration; testable end-to-end via DiffPlan output.
**Why this order:** Depends on Phase 1 (KBEntry, DiffPlan dataclasses). Independent of Phase 3 (apply is downstream consumer).
**Complexity:** Medium

### Steps (TDD per generator):
1. `pattern_promotion/generators/__init__.py` + `DiffPlan`/`FileEdit` dataclasses in a shared types module (e.g., `pattern_promotion/types.py`).
2. `generators/hook.py` + `test_hook.py` — `generate(entry, target_meta)`, `validate_feasibility(feasibility)`, slug collision handling, positive/negative test-script generation per TD-7. `write_order` field on FileEdits (sh=0, test=1, hooks.json=2).
3. `generators/skill.py` + `test_skill.py` — `generate`, `validate_target_meta` (heading existence check), section insertion.
4. `generators/agent.py` + `test_agent.py` — same shape as skill.
5. `generators/command.py` + `test_command.py` — same shape, step_id targeting.

**Done when:** Each generator produces deterministic DiffPlan for canonical fixture inputs; validators reject malformed target_meta with clear reasons.

**Key files:**
- `plugins/pd/hooks/lib/pattern_promotion/types.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/generators/__init__.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/generators/hook.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/generators/skill.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/generators/agent.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/generators/command.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/generators/test_*.py` (new)

## Phase 3: Apply Orchestrator + KB Marker (C-7)

**Why:** Coordinates the 5-stage atomic write. Must handle rollback correctly — the trickiest part of the whole feature.
**Why this order:** Consumes DiffPlan (Phase 2). Independent of CLI wiring (Phase 4), so can start in parallel with Phase 2 second half.
**Complexity:** Medium

### Steps (TDD first):
1. `pattern_promotion/apply.py` + `test_apply.py` — `apply(entry, diff_plan, target_type) -> Result` running Stages 1-4.
2. Stage 1 pre-flight: file-existence checks, JSON validity for hooks.json, partial-run collision detection (grep for `# Promoted from KB entry:` header per TD-8).
3. Stage 2 snapshot: in-memory dict of path→content for modified files; track created-files list.
4. Stage 3 write: apply edits in `write_order`; on failure invoke rollback closure.
5. Stage 4 baseline-delta validation: run `validate.sh` before and after; compare error counts + categories. For hook target: additionally execute generated test script.
6. Rollback: restore modified files from snapshot; unlink created files.
7. KB marker: separate `mark` CLI subcommand calling `kb_parser.mark_entry(path, entry_name, target_type, target_path)`.

**Done when:** `test_apply.py` covers: happy path (all stages pass), Stage 1 JSON-invalid rejection, Stage 4 baseline-delta rollback, Stage 4 hook-test-fails rollback, created-file rollback (unlink), modify rollback (restore snapshot). `mark` subcommand tested independently.

**Key files:**
- `plugins/pd/hooks/lib/pattern_promotion/apply.py` (new)
- `plugins/pd/hooks/lib/pattern_promotion/test_apply.py` (new)

## Phase 4: CLI Entrypoint + Skill Markdown + Command File (C-1, C-2, C-8)

**Why:** User-visible surface. Depends on all Python helpers working.
**Why this order:** Can't ship without command markdown. Skill markdown is orchestration glue.
**Complexity:** Medium

### Steps:
1. Complete `__main__.py` subcommands: `enumerate`, `classify`, `generate`, `apply`, `mark`. Each writes sandbox artifacts + status JSON on stdout per serialization contract.
2. `plugins/pd/skills/promoting-patterns/SKILL.md` (new) — multi-stage workflow per design Pipeline Ownership table. Uses subprocess invocations of `__main__.py` for deterministic steps; uses inline LLM calls for FR-2c classification, FR-3-* Top-3 selection, FR-3-* section ID, FR-3-hook feasibility gate. AskUserQuestion for listing, selection, approval, edit-content.
3. `plugins/pd/commands/promote-pattern.md` (new) — thin entrypoint; validates arg, dispatches `pd:promoting-patterns` skill, handles `--help`.
4. `.claude/pd.local.md` template update: add `memory_promote_min_observations: 3` with comment.
5. `plugins/pd/README.md` + `README.md` + docs/user-guide: add command reference.

**Done when:** `/pd:promote-pattern --help` displays usage. Skill markdown passes `validate.sh` lint. Subprocess contract works end-to-end with a fixture invocation.

**Key files:**
- `plugins/pd/hooks/lib/pattern_promotion/__main__.py` (extend from Phase 1 skeleton)
- `plugins/pd/skills/promoting-patterns/SKILL.md` (new)
- `plugins/pd/commands/promote-pattern.md` (new)
- `plugins/pd/templates/config.local.md` (modify — add field)
- `plugins/pd/README.md` (modify — add command entry)
- `README.md` (modify — add to CHANGELOG [Unreleased])
- `docs/user-guide/usage.md` (modify — add one section)

## Phase 5: End-to-End Verification (manual per Acceptance Evidence)

**Why:** Spec Acceptance Evidence requires three real promotions (hook, skill, agent). Only end-to-end can verify the LLM steps + AskUserQuestion gates + atomic apply interact correctly.
**Why this order:** Last. All components must work.
**Complexity:** Simple (manual execution)

### Steps:
1. Calibrate threshold: run `enumerate` against current `docs/knowledge-bank/`. Report qualifying count. If 0 or >20, adjust `memory_promote_min_observations` per NFR-5.
2. Promote a hook-class pattern end-to-end. Verify `hooks.json` valid; test script passes positive+negative; KB marker appended.
3. Promote a skill-class pattern. Verify SKILL.md edit grammatical, in correct section; KB marker appended.
4. Promote an agent-class pattern. Verify agent .md edit; KB marker appended.
5. Negative tests: (a) override to CLAUDE.md rejected; (b) re-promote already-promoted entry rejected; (c) LLM-claimed-feasible hook whose test script fails → rollback.
6. Record measurements in spike-results.md or feature-notes.md: LLM token counts per invocation, wall-clock per stage, any rollbacks.

**Done when:** 3 real KB patterns promoted to 3 different target types; all verifications pass; validate.sh + test-hooks.sh green post-merge.

**Key files:** (no code) — manual verification + notes
