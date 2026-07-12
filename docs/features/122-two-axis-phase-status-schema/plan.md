# Implementation Plan: Two-Axis Phase/Status Schema (feature 122)

## Objective

Land design D1-D7 in three serial steps: the dark axes module (constants, register-on-demand vocab triggers, named view) with its deterministic pins; the exhaustive trigger-teeth battery; the ships-dark guard extension folded into integration QA.

## Prerequisites

Branch `feature/122-two-axis-phase-status-schema` (active). Design D1-D7 binding, including: EXECUTION_STATUSES = SEVEN values (`ready` after `prioritised`, PRD FR-8 — 124's cascade target); expression-RAISE trigger messages carrying axis AND `quote(NEW.to_value)` (≥3.47.0 asserted at register time; empirically probed on this venv's 3.53.2); trigger DDL register-on-demand ONLY (never at import — snapshot/RESTORE + collection-time imports would leak into 119/120/126's suites); the view self-registers at import under owner `"axes"`, triggers under `"axes_vocab_triggers"`; module-top `from entity_registry import views` is LOAD-BEARING (registration chain events → views → axes). The D6 spec touch-up already landed with the design commit (138a3d82) — implement's inventory is three code files + feature docs.

## Step Ordering Rationale

Step 1 ships the module + its shape/registration/view pins as one vertical slice (a module without its pins is unreviewable). Step 2 appends the trigger-teeth battery to the same test file (needs step 1's `register_vocab_ddl`; separated because the 13-probe acceptance matrix + rejection semantics + leak-detection deserve their own review context). Step 3 widens the dark-guard needles + teeth (test_schema_v2.py; the membership line lands in step 1, atomic with axes.py's creation — the every-run scan would otherwise flag the new file) and runs full integration QA — last so the suite-baseline delta (FR122-5) is measured once, over the complete feature.

## Step 1 — axes.py + shape/view pins (D1, D2 build+registration, D3, D4; SC1, SC4)

**Do:**
1. NEW `plugins/pd/hooks/lib/entity_registry/axes.py`: dark-module preamble (views.py's shape); module-top `from entity_registry import views` + load-bearing chain comment (D4); `PIPELINE_PHASES`/`EXECUTION_STATUSES` tuples EXACTLY per D1 + exported frozenset views; module-load apostrophe assertion; `_VOCAB_TRIGGER_DDL` built from the constants via the D2-pinned interpolation with BOTH triggers verbatim (pipeline + execution, expression-RAISE messages naming axis + quoted value + axes.py pointer); `entity_phase_status` view DDL per D3 + `register_ddl("axes", ...)` at import; `register_vocab_ddl()` (asserts `sqlite3.sqlite_version_info >= (3, 47, 0)` FIRST, then `register_ddl("axes_vocab_triggers", _VOCAB_TRIGGER_DDL)`); `is_vocab_registered()` LATCH-FREE (scans the live DDL registry for owner `"axes_vocab_triggers"`, never a module flag — the suites' snapshot/restore idiom deregisters between tests, so a sticky latch would skip re-registration and make the teeth vacuous); PLUS the one-line `_V2_DARK_MODULES` += `"axes.py"` in test_schema_v2.py, atomic with the file's creation (the every-run ships-dark scan would otherwise flag axes.py's own views import as an offender between steps 1 and 3 — needle widening + teeth remain step 3); docstring carries the #067 inheritance note (per-entity reads → entity_axis_state) and the vocab-free-lifecycle statement.
2. NEW `test_axes.py`: define its OWN snapshot/restore registry fixture (the package deliberately has no conftest fixtures — each test module carries a local copy, test_views.py precedent) + bootstrapped-DB/connect_v2/seeded-entity idioms (test_views.py); D5 group 1 — tuple-equality pins for both vocabularies (order pinned); registration semantics — `is_vocab_registered()` False→True across `register_vocab_ddl()`, second call raises `ValueError` (duplicate owner); D5 group 5 — `PRAGMA table_info(entity_phase_status)` column list == the five FR-6 names; round-trip seed with DISTINCT in-vocab values AND DISTINCT timestamps on both axes, ALL FOUR axis columns asserted against their `entity_axis_state` counterparts; write-rejection (INSERT/UPDATE/DELETE → OperationalError, 120's pin pattern).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_axes.py -q` green.

## Step 2 — trigger-teeth battery (D2 semantics; SC2, SC3, SC6-structural)

**Do:** Append to `test_axes.py`: an OPT-IN (non-autouse) fixture registering `register_vocab_ddl()` ONCE per snapshot — MUST NOT be autouse, or the leak-detection pin (which bootstraps WITHOUT triggers) fails or goes vacuous; D5 group 2 — ALL 13 acceptance probes as raw INSERTs (6 pipeline + 7 execution); rejections per axis (out-of-vocab; cross-axis `'wip'` on pipeline + `'design'` on execution; wrong-case `'WIP'`) asserting `sqlite3.IntegrityError` EXACTLY with BOTH axis and offending value in the message; NULL to_value accepted on all three axes; lifecycle free-text + type_id-shaped + legacy `completed` accepted (no trigger); D5 group 3 — leak-detection pin: bootstrap WITHOUT `register_vocab_ddl()` accepts an out-of-vocab pipeline INSERT (SC6's structural guarantee); D5 group 4 — `from workflow_engine.kanban import derive_kanban, PHASE_TO_KANBAN` (the LIVE module, plugins/pd/hooks/lib/workflow_engine/kanban.py — importable via hooks/lib/conftest.py), enumerate reachable outputs as `set(PHASE_TO_KANBAN.values())` ∪ the terminal-branch literals ({completed, blocked, backlog} — string literals inside the function body, not module constants), assert STRICT subset (six ⊂ seven); D5 group 7 — rejection probes are raw `conn.execute` INSERTs (FR122-3 structural proof, noted in a comment).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_axes.py -q` green; rejection-message asserts demonstrated against the real trigger output (axis + quoted value present).

## Step 3 — dark-guard teeth + integration QA (D5 group 6; SC5, SC6, SC7)

**Do:**
1. `test_schema_v2.py` (membership already landed in step 1): needles += the three spellings (`entity_registry.axes` / `from entity_registry import axes` / `from .axes import`); 3 seeded-offender teeth tests written RED first against the un-extended needle set (121's exact pattern).
2. Full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q` — FR122-5 baseline re-derived at the merge-base in a scratch worktree with the identical command (the 3631 literal is NOT authoritative), then diffed against the feature-branch total; confirm ZERO 119/120/126 test-file modifications (`git diff --stat` shows no test_events/test_views/test_meta_projection lines); `./validate.sh` (0 errors); `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor pin unchanged; repo-wide grep zero live importers of axes; `git diff develop...HEAD --stat` vs D7 inventory BY NAME: axes.py (NEW), test_axes.py (NEW), test_schema_v2.py, spec.md (design commit) + feature docs.

**Verify:** all green; teeth demonstrated red pre-needles; no unsanctioned files.

## Risks & Mitigations

- **Trigger leakage into sibling suites:** the register-on-demand mechanism + step 2's leak-detection pin make isolation structural, not conventional.
- **RAISE expression portability:** version assert in `register_vocab_ddl()` fails loud pre-3.47; venv probed at 3.53.2.
- **FK failures in raw-INSERT probes:** events.entity_uuid REFERENCES entities — reuse the seeded-entity idiom; a probe failing on FK (not the vocab trigger) is a fixture bug, distinguish via the exception message assert.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per step; dark module reverts clean (guard-enforced unimported; triggers exist only where a test registered them).

## Success Check (spec SCs)

SC1/SC4 → step 1; SC2/SC3 → step 2; SC5 → step 3 (teeth); SC6 → step 2 (structural leak pin) + step 3 (suite, zero sibling edits); SC7 → step 3 (validate/doctor; roadmap edits landed at specify, 903f3964).
