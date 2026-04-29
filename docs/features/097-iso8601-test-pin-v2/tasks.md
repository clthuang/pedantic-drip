# Tasks: Feature 097 — Test-pin v2 bundle for `_ISO8601_Z_PATTERN`

**Direct-orchestrator** with **single-file scope**. Total: 1-file edit + atomic commit + log emission. Net production-touch: 0 LOC. Net test count delta: +14.

**⚠ Co-read requirement:** This file is a compact task index. Full Old/New text quotes + verbatim code blocks live in `plan.md` T1. Direct-orchestrator MUST co-read `plan.md` Implementation Order when running each task.

## Task Index

| ID | Title | File | Depends on |
|----|-------|------|------------|
| **T0** | Capture baselines (PRE_HEAD, PRE_NARROW=224, PRE_WIDE=3208, PRE_SOURCE_PINS=7) + verify FR-7 + FR-6 preconditions | — | none |
| **T1** | Edit `test_database.py`: Edit 1a (3 new stdlib imports) + Edit 1b (replace TestIso8601PatternSourcePins class entirely + add `_UNICODE_DIGIT_SCRIPTS` module constant) | `test_database.py` | T0 |
| **T1.5** | `pytest --collect-only` checkpoint: 21 tests collected, no errors | — | T1 |
| **T2** | Quality gates: validate.sh + pytest narrow + wide + source-pins + scope-guard diff | — | T1.5 |
| **T3** | Atomic commit + emit `implementation-log.md` + call `complete_phase` MCP per NFR-5 | — | T2 |
| **T4** | `/pd:finish-feature` → THIRD production exercise of feature 094 Step 5b gate → release v4.16.7 | — | T3 |

## T0 — Baselines + preconditions

```bash
PRE_HEAD=$(git rev-parse HEAD)
PRE_NARROW=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
PRE_WIDE=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
PRE_SOURCE_PINS=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c "from semantic_memory import database; assert hasattr(database, '_ISO8601_Z_PATTERN')"
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c "import unicodedata; assert all(unicodedata.category(c) == 'Nd' for c in '２٢२২༢២၂೨௨୨൨๒᮲')"
```

**DoD:** PRE_NARROW=224, PRE_WIDE=3208, PRE_SOURCE_PINS=7; both precondition assertions pass.

## T1 — Edit test_database.py

Per plan T1: Edit 1a adds 3 stdlib imports (`ast`, `textwrap`, `unicodedata`); Edit 1b replaces the entire `TestIso8601PatternSourcePins` class (lines 2266-2326) with the v2 body PLUS adds `_UNICODE_DIGIT_SCRIPTS` module-level constant immediately preceding the class.

**Note:** Edit 1a's anchor is `import struct\nimport sqlite3` block. Edit 1b's anchor is the entire feature-095 class verbatim — text-anchored (Edit-tool match by Old text, not line numbers).

**DoD:** All 10 ACs verified via plan T1 DoD grep checks (AC-1, AC-2 [2 cmds], AC-3, AC-4, AC-5 [2 cmds], AC-6, AC-7, AC-8, AC-10 [grep + parametrize count], AC-11 = 12 verification commands covering 10 ACs). AC-9 is manual non-gating.

## T1.5 — Collection checkpoint (fail-fast)

```bash
plugins/pd/.venv/bin/python -m pytest --collect-only \
  plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q | tail -3
```

**DoD:** Output contains `21 tests collected`, no `ERROR` lines.

## T2 — Quality gates

```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q | tail -1   # = "21 passed"
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q | tail -1                                # = "$((PRE_NARROW + 14)) passed"  (expected 238 if no drift)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q | tail -1                                                                # = "$((PRE_WIDE + 14)) passed"   (expected 3222 if no drift)
./validate.sh                                                                                                                            # exit 0
git diff develop...HEAD -- \
  plugins/pd/hooks/lib/semantic_memory/_config_utils.py \
  plugins/pd/hooks/lib/semantic_memory/database.py \
  plugins/pd/hooks/lib/semantic_memory/maintenance.py \
  plugins/pd/hooks/lib/semantic_memory/refresh.py \
  plugins/pd/hooks/lib/semantic_memory/memory_server.py \
  plugins/pd/hooks/lib/semantic_memory/conftest.py | wc -l                                                                               # = 0
```

**DoD:** AC-12 (production diff = 0), AC-13 (narrow = `PRE_NARROW + 14`, expected 238), AC-14 (wide = `PRE_WIDE + 14`, expected 3222), AC-15 (validate.sh exit 0), AC-16 (source-pins = 21). Per NFR-4, the formula `PRE + 14` is the gating assertion; the literal "238/3222" expected values are advisory only and protect against drift between spec and implement.

## T3 — Atomic commit + log + complete_phase

**Sequencing per plan T3:** write `implementation-log.md` FIRST, then atomically commit BOTH files together.

```bash
# Step 1: write implementation-log.md (template below) BEFORE git add
# Step 2: stage both files
git add plugins/pd/hooks/lib/semantic_memory/test_database.py \
        docs/features/097-iso8601-test-pin-v2/implementation-log.md
# Step 3: atomic commit
git commit -m "test(semantic_memory): refactor TestIso8601PatternSourcePins for v2 mutation coverage (#00278)
[full message per plan T3]"
```

The template `docs/features/097-iso8601-test-pin-v2/implementation-log.md` should contain:
```markdown
# Implementation Log — Feature 097

## T0 — Baselines (captured at implement-start)
- PRE_HEAD: {actual_sha}
- PRE_NARROW: {actual_value}  (test_database.py; spec-time estimate: 224)
- PRE_WIDE: {actual_value}     (plugins/pd/hooks/lib/; spec-time estimate: 3208)
- PRE_SOURCE_PINS: {actual_value}  (TestIso8601PatternSourcePins; spec-time estimate: 7)
- FR-7 precondition: database._ISO8601_Z_PATTERN module-accessible — PASS / FAIL
- FR-6 precondition: 13 curated codepoints all category=Nd — PASS / FAIL

## T1 — Edit test_database.py
- Edit 1a (3 imports): test_database.py:9-10 anchor — added ast, textwrap, unicodedata
- Edit 1b (class rewrite): replaced TestIso8601PatternSourcePins (lines 2266-2326) with v2 body + _UNICODE_DIGIT_SCRIPTS constant
- DoD: 10/10 ACs verified via 12 grep/count commands (AC-1..AC-11 minus AC-9 manual)
- Tooling friction: {note any Edit-tool issues, Unicode escape hatches needed, etc.}

## T1.5 — Collection
- pytest --collect-only TestIso8601PatternSourcePins: 21 tests collected, 0 errors

## T2 — Quality gates
- pytest TestIso8601PatternSourcePins: 21 passed (AC-16)
- pytest test_database.py: 238 passed (AC-13, exact T0+14)
- pytest plugins/pd/hooks/lib/: 3222 passed (AC-14, exact T0+14)
- validate.sh: exit 0 (AC-15)
- production scope guard diff: 0 lines (AC-12)

## T3 — Atomic commit
- commit: {sha}
- complete_phase MCP call: {result}
```

Then `complete_phase(feature_type_id="feature:097-iso8601-test-pin-v2", phase="implement", iterations=1)`.

**DoD:** Single atomic commit on feature branch contains BOTH test_database.py AND implementation-log.md; workflow-engine reports `last_completed_phase == "implement"`.

## T4 — `/pd:finish-feature`

Run `/pd:finish-feature` on feature 097. Triggers feature 094 Step 5b gate (THIRD production exercise — first test-only diff vs prior code-touching diffs).

**DoD:**
- Gate dispatches 4 reviewers in parallel against test-only diff
- Verdict: HIGH=0 PASS preferred (qa-override.md fallback per R-6 contingency)
- Auto-fold of any `.qa-gate.log` / `.qa-gate-low-findings.md` sidecars by retrospecting skill
- Merged to develop, pushed, v4.16.7 tagged

## AC Coverage (summary)

All 16 ACs auto-verified per plan AC Coverage Matrix:
- T1 covers: AC-1..AC-8, AC-10, AC-11 (10 ACs via grep)
- T1.5 covers: collection sanity (no AC, but pre-T2 fail-fast)
- T2 covers: AC-12, AC-13, AC-14, AC-15, AC-16 (5 ACs via pytest + diff)
- AC-9 manual non-gating

15 gating + 1 manual = 16 total.
