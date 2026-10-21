---
last-invoked: 2026-04-16
feature: 083-promote-pattern-command
---

# Plan: /pd:promote-pattern

## Implementation Order

```
Phase 1: Python scaffolding + shared types (KBEntry, DiffPlan, classifier, inventory)
    ↓
Phase 2: Per-target generators (hook, skill, agent, command)    ←─┐
    ↓                                                              │ (truly parallel
Phase 3: Apply orchestrator + KB marker (Stage 5)      ────────── ─┤  after Phase 1)
                                                                   │
Phase 4a: CLI subcommands + integration tests     ────────────────┘
    ↓
Phase 4b: Skill markdown (split into 3 tasks)
    ↓
Phase 4c: Command file + config + docs sync
    ↓
Phase 5: End-to-end verification (human-driven)
```

Phase 2 and Phase 3 can run in parallel after Phase 1 lands all shared dataclasses (KBEntry lives in kb_parser.py per design; DiffPlan/FileEdit/Result in types.py).

## Phase 1: Python Scaffolding (C-3, C-4, C-5, C-8 package init)

**Why:** Pure-deterministic helpers must land first — they are dependencies for Phase 2 generators AND Phase 3 apply. TDD: test each in isolation.
**Why this order:** Zero external dependencies. All downstream phases consume Phase 1.
**Complexity:** Low

### Task-level breakdown (see tasks.md for per-task details):
- **Task 1.1**: types.py + __init__.py + __main__.py stub tests (TDD red)
- **Task 1.2**: types.py + __init__.py + __main__.py stub implementation (green)
- **Task 1.3**: kb_parser tests (TDD red)
- **Task 1.4**: kb_parser implementation incl. KBEntry dataclass (green)
- **Task 1.5**: classifier tests (TDD red)
- **Task 1.6**: classifier implementation (green)
- **Task 1.7**: inventory tests + implementation
- **Task 1.8**: config wiring for memory_promote_min_observations (CLI + existing common helper)

**Done when:** All Phase 1 pytest files green; `plugins/pd/.venv/bin/python -m pattern_promotion --help` prints usage; config field resolves.

## Phase 2: Per-Target Generators (C-6)

**Why:** Each target requires its own DiffPlan generator with validation.
**Why this order:** Depends on Phase 1 (DiffPlan/FileEdit types). Parallel with Phase 3 after Phase 1 lands.
**Complexity:** Medium

### Task-level breakdown:
- **Task 2.1**: generators/__init__.py package init
- **Task 2.2a**: generators/hook validate_feasibility tests (TDD red)
- **Task 2.2b**: generators/hook generate tests (TDD red) — positive/negative test-script, slug collision, TD-8 marker
- **Task 2.3**: generators/hook implementation (green)
- **Task 2.4**: generators/skill tests + implementation — section locator, **TD-8 marker comment required**
- **Task 2.5**: generators/agent tests + implementation — **TD-8 marker comment required**
- **Task 2.6**: generators/command tests + implementation — step_id targeting, **TD-8 marker comment required**

Tasks 2.3, 2.4, 2.5, 2.6 depend on Task 2.1 + Task 1.4 only — parallelizable to each other.

**Done when:** Each generator produces deterministic DiffPlan; validators reject malformed target_meta; **every generated output (hook, skill, agent, command) contains a TD-8 marker comment scannable by Phase 3 Stage 1 collision detection**.

## Phase 3: Apply Orchestrator + KB Marker (C-7)

**Why:** Coordinates the 5-stage atomic write.
**Why this order:** Depends on Phase 1 types. Parallel with Phase 2.
**Complexity:** Medium

### Task-level breakdown:
- **Task 3.1**: apply.py Stage 1 + happy-path tests (TDD red) — includes all three Stage 1 pre-flight checks: file existence, JSON validity, partial-run collision per TD-8
- **Task 3.2**: apply.py Stages 1-4 happy-path implementation (green)
- **Task 3.3**: apply.py rollback scenario tests (TDD red) — 6 cases incl. baseline-run-failure
- **Task 3.4**: apply.py rollback implementation (green)
- **Task 3.5**: apply.py hook-target test script execution at Stage 4
- **Task 3.6**: mark CLI subcommand **tests + implementation** — cover: (a) insertion after Confidence line, (b) before next sibling heading, (c) at EOF for last entry, (d) repo-relative target path. Wires to `kb_parser.mark_entry` from Task 1.4 — does NOT re-implement insertion logic.

**Done when:** test_apply covers happy + 6 rollback scenarios; mark subcommand appends marker at correct insertion point per FR-5 Stage 5.

## Phase 4a: CLI Subcommands + Integration Tests (C-8)

**Why:** Subprocess Serialization Contract must work before skill markdown can consume it.
**Why this order:** Depends on Phases 1-3. Blocks Phase 4b.
**Complexity:** Medium

### Task-level breakdown:
- **Task 4a.1**: enumerate subcommand
- **Task 4a.2**: classify subcommand
- **Task 4a.3**: generate subcommand (routes to per-target generator with validate_* pre-check)
- **Task 4a.4**: apply subcommand (reads diff_plan.json; invokes apply.apply())
- **Task 4a.5**: test_cli_integration.py — end-to-end subprocess contract validation

**Done when:** 5 subcommand integration tests green; subprocess contract round-trip verified.

## Phase 4b: Skill Markdown (C-2 — split into 3 tasks per reviewer feedback)

**Why:** Orchestrator glue. Largest markdown artifact in this feature.
**Why this order:** Depends on Phase 4a (CLI subcommands must work).
**Complexity:** Medium (split across 3 tasks prevents monolithic implementation)

### Task-level breakdown:
- **Task 4b.1**: SKILL.md skeleton + Steps 1-2 (enumerate + classify + user-override)
- **Task 4b.2**: SKILL.md Step 3 (per-target generation with Top-3 LLM, section-ID LLM, generate dispatch)
- **Task 4b.3**: SKILL.md Steps 4-5 (approval gate with edit-content, apply + mark sequential invocation, stale-sandbox cleanup)

**Done when:** Skill runs end-to-end on fixture KB; `validate.sh` passes; `grep -c AskUserQuestion plugins/pd/skills/promoting-patterns/SKILL.md` returns ≥4.

## Phase 4c: Command File + Config + Docs Sync (C-1, C-9, CLAUDE.md sync)

**Why:** User-visible surface + documentation sync per CLAUDE.md Documentation sync.
**Why this order:** Depends on Phase 4b (skill must exist).
**Complexity:** Low

### Task-level breakdown:
- **Task 4c.1**: commands/promote-pattern.md thin entrypoint
- **Task 4c.2**: config template — add `memory_promote_min_observations: 3`
- **Task 4c.3**: docs sync across README.md, README_FOR_DEV.md, plugins/pd/README.md, CHANGELOG.md, docs/user-guide/usage.md (per CLAUDE.md Documentation sync + spec FR audience)
- **Task 4c.4**: validate.sh audit — **if pattern_promotion/ is not covered by existing python health checks, extend validate.sh**; document result

**Done when:** `/pd:promote-pattern --help` works; 5 docs-sync files updated with consistent counts; validate.sh reports 0 python errors against pattern_promotion/ package.

## Phase 5: End-to-End Verification (HUMAN-DRIVEN)

**Why:** Spec Acceptance Evidence requires 3 real promotions. AskUserQuestion gates require a human in interactive CC session.
**Why this order:** Last. All components must work.
**Complexity:** Medium (not Simple — requires KB pattern diversity + interactive session + negative cases)

**⚠️ Executor: HUMAN OPERATOR — tasks in this phase cannot be performed by an automated agent** (AskUserQuestion flows require interactive response).

### Steps:
1. Threshold calibration + KB-diversity check: run `enumerate` against current KB. Confirm ≥1 hook-eligible + ≥1 skill-eligible + ≥1 agent-eligible pattern exists. If not, raise a blocker in spike-results.md.
2-4. Promote one pattern to each of hook/skill/agent target end-to-end in interactive CC session.
5. Negative tests: (a) attempt CLAUDE.md override → verify rejection; (b) re-promote already-promoted entry → verify rejection; (c) **direct apply subcommand with hand-crafted diff_plan.json whose hook test script is designed to fail** (deterministic — not reliant on LLM claiming feasibility).
6. Token cost measurement for one representative invocation; confirm ≤2000 tokens per attempt per NFR-3.

**Done when:** 3 real KB patterns promoted; 3 negative scenarios pass; `validate.sh` + `test-hooks.sh` green.
