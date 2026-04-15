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

### Steps (TDD first):
1. Package skeleton (`__init__.py`, `__main__.py` stub, `types.py` with DiffPlan/FileEdit/Result dataclasses — NOT KBEntry, which belongs to kb_parser.py per design C-3).
2. `kb_parser.py` tests + implementation — `KBEntry` dataclass + `enumerate_qualifying_entries` + `mark_entry` helper.
3. `classifier.py` tests + implementation.
4. `inventory.py` tests + implementation.
5. Config wiring: load `memory_promote_min_observations` in `__main__.py`'s `enumerate` subcommand default (reads `.claude/pd.local.md` via common helper pattern from existing hooks).

**Done when:** All Phase 1 pytest files green; `plugins/pd/.venv/bin/python -m pattern_promotion --help` prints usage; config field resolves.

## Phase 2: Per-Target Generators (C-6)

**Why:** Each target requires its own DiffPlan generator with validation.
**Why this order:** Depends on Phase 1 (DiffPlan/FileEdit types). Parallel with Phase 3 after Phase 1 lands.
**Complexity:** Medium

### Steps (TDD per generator):
1. `generators/__init__.py` package init.
2. `generators/hook.py` tests + implementation — includes TD-7 positive/negative test-script generation, slug collision auto-suffix, TD-8 `# Promoted from KB entry:` header comment.
3. `generators/skill.py` tests + implementation — section locator, TD-8 marker comment.
4. `generators/agent.py` tests + implementation — parallel to skill.py, different target pool.
5. `generators/command.py` tests + implementation — step_id targeting.

Tasks 2.3, 2.4, 2.5, 2.6 (hook/skill/agent/command) depend only on `generators/__init__.py` (2.1) + `kb_parser.KBEntry` (Phase 1). They are parallelizable to each other.

**Done when:** Each generator produces deterministic DiffPlan for canonical fixture inputs; validators reject malformed target_meta with clear reasons; every generated output contains the TD-8 marker comment.

## Phase 3: Apply Orchestrator + KB Marker (C-7)

**Why:** Coordinates the 5-stage atomic write.
**Why this order:** Depends on Phase 1 types. Parallel with Phase 2.
**Complexity:** Medium

### Steps (TDD first):
1. `apply.py` happy-path tests + implementation covering Stages 1-4 as a unified flow. Stage 1 includes **all three pre-flight checks**: file existence, JSON validity, partial-run collision detection per TD-8 (merged — not split across tasks).
2. `apply.py` rollback scenario tests + implementation (snapshot restore, created-file unlink, baseline-delta rollback, hook-test rollback, baseline-run-failure abort-before-write).
3. Hook-target test script execution in Stage 4.
4. `mark` subcommand for Stage 5 KB marker — delegated per design C-7 so `apply.py` can be unit-tested independently of KB writes.

**Done when:** `test_apply.py` covers happy + 5 rollback scenarios; `mark` subcommand appends marker at correct insertion point per FR-5 Stage 5.

## Phase 4a: CLI Subcommands + Integration Tests (C-8)

**Why:** Subprocess Serialization Contract must work before skill markdown can consume it.
**Why this order:** Depends on Phases 1-3. Blocks Phase 4b.
**Complexity:** Medium

### Steps:
1. Complete `__main__.py` subcommands: `enumerate`, `classify`, `generate`, `apply`, `mark`. Each writes sandbox artifacts + status JSON on stdout per contract.
2. `test_cli_integration.py` — end-to-end subprocess invocations against fixture KB dirs. Asserts: status JSON schema, sandbox file contents, exit codes (0=ok/need-input; non-zero=error), `--min-observations` wiring from config.

**Done when:** 5 subcommand integration tests green; subprocess contract round-trip verified.

## Phase 4b: Skill Markdown (C-2 — split into 3 tasks per reviewer feedback)

**Why:** Orchestrator glue. Largest markdown artifact in this feature.
**Why this order:** Depends on Phase 4a (CLI subcommands must work).
**Complexity:** Medium (split across 3 tasks prevents monolithic implementation)

### Steps:
1. Skeleton + Steps 1-2 (enumerate + classify + AskUserQuestion flows).
2. Step 3 (per-target generation with Top-3 LLM, section-ID LLM, generate subcommand dispatch).
3. Step 4-5 (approval gate with edit-content, apply + mark sequential invocation, stale-sandbox cleanup).

**Done when:** Skill runs end-to-end on a fixture KB with a pre-classified entry; `validate.sh` passes.

## Phase 4c: Command File + Config + Docs Sync (C-1, C-9, CLAUDE.md sync)

**Why:** User-visible surface + documentation sync per CLAUDE.md Documentation sync.
**Why this order:** Depends on Phase 4b (skill must exist).
**Complexity:** Low

### Steps:
1. `plugins/pd/commands/promote-pattern.md` — thin entrypoint.
2. `plugins/pd/templates/config.local.md` — add `memory_promote_min_observations: 3`.
3. Documentation sync across all CLAUDE.md-mandated touchpoints: `README.md`, `README_FOR_DEV.md`, `plugins/pd/README.md` (component counts + command table + skill table), `CHANGELOG.md` [Unreleased].
4. `validate.sh` audit: confirm new `pattern_promotion/` package gets covered by existing python syntax/import health checks (or add if missing).

**Done when:** `/pd:promote-pattern --help` works; all docs-sync touchpoints updated; counts consistent across files.

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
