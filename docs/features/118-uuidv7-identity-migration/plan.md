# Implementation Plan: UUIDv7 Identity Migration

## Objective

Ship 118's three deliverables per design.md: the 3.14 floor + `uuid7.py` helper, the `_UUID_RE` widening/rename with its full test blast radius, the 4-site mint rewiring, and the dark `schema_v2.py` module — each step independently green.

## Prerequisites

- Branch `feature/118-uuidv7-identity-migration` (active), venv at Python 3.14.6 (verified).
- Design decisions D1-D6 are binding; sibling contracts (121 sequences semantics, DDL registry) ship as documented there.

## Step Ordering Rationale

Steps 1→2→3 are dependency-ordered: the helper needs the floor; the rewiring (3) needs both the helper (1) and the widened validators (2) — between 2 and 3 the system is green because the widened regex accepts v4 AND v7. Step 4 (`schema_v2.py`) is independent (bootstrap mints nothing — callers mint, starting with 119) but runs after 3 to keep the doctor before/after window tight around the only live-behavior change. Steps 2 and 3 both edit `database.py` — serialized, never parallel.

## Step 1 — Python floor + uuid7 helper

**Do:**
- `plugins/pd/pyproject.toml:4` → `requires-python = ">=3.14"`.
- Refresh the lockfile: `cd plugins/pd && uv lock` (uv.lock:3 currently pins `requires-python = ">=3.12"` — pyproject/lock drift otherwise). BEST-EFFORT: `uv lock` needs the package index; if resolution is unavailable (offline/sandbox), edit the single `uv.lock:3` requires-python line directly and note it — tests are unaffected either way (they run via `.venv/bin/python -m pytest`, never `uv run`), so the lock refresh is hygiene, not a greenness gate.
- Create `plugins/pd/hooks/lib/entity_registry/uuid7.py`: `_require_uuid7(mod=uuid)` raising `RuntimeError` naming the 3.14 floor when `uuid7` is absent; module-top call; `generate_uuid7() -> str`.
- Create `test_uuid7.py`: version-nibble-7 + 1000× monotonicity; `_require_uuid7(mod=fake)` raises with "3.14" in the message (design tests #7-8).

**Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_uuid7.py` green; `grep -n "requires-python" plugins/pd/pyproject.toml plugins/pd/uv.lock` both show `>=3.14`.

## Step 2 — Validator widening + full rename sweep

**Do:**
- Widen + rename `_UUID_V4_RE` → `_UUID_RE`, nibble `4` → `[1-7]`, at `database.py:25-27` and `frontmatter.py:57-59`; update the v4/R11 comment above frontmatter's def (`frontmatter.py:56` — database.py's def has no preceding comment; add none).
- Rename at production call sites `database.py:6054`, `:6283`, `frontmatter.py:118`.
- Mechanical rename sweep in tests: `test_database.py` (`:17`, `:178`, `:237` imports + ALL usages incl. variant test `:2113`), `test_server_helpers.py` (`:11`, `:501`, `:1018`), `test_frontmatter.py` (`:25` + usages).
- Re-scope the five reversal tests to version-agnostic acceptance (v1/v3/v5 now MATCH): `test_database.py::TestResolveIdentifierBoundary` ×3, `test_frontmatter.py::TestValidateHeaderUUIDBoundary` ×2 — invert assertions + rename tests/docstrings to say what they now pin (accepts versions 1-7; variant still rejected).
- Sweep ALL lying v4 labels via `grep -n "UUID v4\|v4" test_database.py test_server_helpers.py test_frontmatter.py`: failure messages (`test_database.py:671/:685/:803/:1910`, the DIFFERENT template at `:721` `"Expected UUID v4 for {etype}"`, `:4099` `"does not match UUID v4 pattern"`), test name `test_register_returns_uuid_v4_format` (`:1907`) + its docstring (`:1908`), docstring `:800`, class docstring `test_frontmatter.py:1131`, comments `:220`/`:2179` — version-agnostic wording throughout (messages/names must not claim v4 on v7 values).
- Widen the test-local leak-guard nibble at `test_entity_server.py:19` (name unchanged).

**Verify:** `grep -rn "_UUID_V4_RE" plugins/pd/hooks/lib/` → only the `test_entity_server.py` local def+use; full `entity_registry` test suite green (mints still v4 — widened regex accepts both, so this step is independently green).

## Step 3 — Mint rewiring + round-trip + scan test

**Do:**
- Capture pre-change doctor output — the DB-AWARE doctor, NOT `scripts/doctor.sh` (which is an environmental check that never reads the entities DB; its diff would be vacuously green): `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor --entities-db ~/.claude/pd/entities/entities.db --project-root "$PWD"` WITHOUT `--fix` (read-only) → save to `docs/features/118-uuidv7-identity-migration/.doctor-before.txt`.
- Rewire 4 runtime mints to `generate_uuid7()`: `database.py:6775`, `:7801`, `:9736`, `project_identity.py:685` (+ import per file idiom); update `project_identity.py:563` docstring. Drop `project_identity.py:21` `import uuid as uuid_mod` — `:685` was its sole use (database.py's stays: frozen sites still use it). Frozen sites `:272`/`:1855` untouched.
- Add round-trip test (design #9): `register_entity` → assert minted uuid version nibble == 7 → fetch via `get_entity` by-uuid routing → `resolve_ref` uuid branch → `validate_header` accepts — all positive.
- Add residual-uuid4 source-scan test (design #12): COUNT-BASED — exactly two `uuid4(` occurrences in non-test `entity_registry/` code, both within the frozen migration function bodies. NEVER hardcode line numbers `:272`/`:1855` — this very step's added import shifts them.
- Capture post-change doctor output to `.doctor-after.txt` (same command); diff.

**Verify:** full `entity_registry` suite green; doctor diff shows no new issue classes/crashes; scan test fails if a stray `uuid4(` mint is added (mutation-check it once by reverting one site in the working tree, seeing red, restoring).

## Step 4 — schema_v2 dark module

**Do:**
- Create `plugins/pd/hooks/lib/entity_registry/schema_v2.py` per design D1/D3/D4: `V2_SCHEMA_VERSION = 1`; `_CORE_DDL` (workspaces / entities / entity_relations + CASCADE + dedup unique index / sequences / `_metadata` / non-unique lookup indexes — exact DDL from design D3); `DDL_REGISTRY` + `register_ddl` (duplicate-owner `ValueError`); `bootstrap_v2(db_path)` — fresh autocommit connection, PRAGMAs (WAL, busy_timeout, foreign_keys) BEFORE any transaction, executescript per registry entry, single `INSERT OR IGNORE` version write; docstrings carry the convergent-not-atomic recovery contract and the connection-factory re-issue note.
- Create `test_schema_v2.py` (design tests #1-6): shape sweep keying on UNIQUE-index covered column sets (dedup index expected), same-business-key double insert, extension point + duplicate-owner raise, idempotent re-bootstrap, one-version-write source scan (executable statements only, comments stripped), WAL+FK+busy_timeout asserted on bootstrap's own connection.

**Verify:** `pytest test_schema_v2.py` green; no non-test import of `schema_v2` anywhere (`grep -rn "import schema_v2\|from entity_registry.schema_v2" plugins/pd/hooks/lib/ --include="*.py" | grep -v test_` → empty — ships dark).

## Step 5 — Integration QA

**Do:** full `plugins/pd/hooks/lib/` suite; `./validate.sh`; re-run doctor (stability spot-check); review `git diff develop...HEAD` against the design File Change Inventory (no unsanctioned files).

**Verify:** all green; diff touches exactly the inventory's files (+ the two doctor capture artifacts + workflow docs).

## Risks & Mitigations

- **uv lock churn:** `uv lock` may update unrelated pins. Mitigation: inspect the lock diff; if noise exceeds the requires-python line, use `uv lock --upgrade-package none` semantics (regenerate minimally) or accept-and-note (private tooling).
- **Hidden v4 assertions beyond the enumerated set:** the enumerations came from grep, but step 2's verify is the full suite run, which catches stragglers empirically. Fix-forward within the step.
- **Doctor nondeterminism between captures:** captures are same-session, minutes apart, same DB. If the diff shows drift UNRELATED to uuids (e.g., another session wrote entities), re-capture both sides back-to-back; the criterion is "no NEW ISSUE CLASSES", not byte-equality.
- **3 reviewer-iteration cap** (CLAUDE.md): if any implement-phase reviewer hits 3 rounds, exit the loop, document residuals, delegate to the next gate.

## Rollback

Single feature branch; every step is one commit — `git revert` any step independently. The uuid7 values already minted into the live DB by post-step-3 sessions are valid v17 TEXT uuids either way (both regex generations accept them — v4 regex never validated EXISTING rows, only new-value paths).

## Success Check (maps to spec SCs)

SC1 bootstrap shape → step 4 tests; SC2 one version location → step 4 scan; SC3 extension point → step 4; SC4 helper + 4-site rewiring + frozen-site grep → steps 1/3; SC-regex round-trip → steps 2/3; SC5 floor + suite green → steps 1/5; SC6 migrations untouched + doctor before/after → step 3 + `git diff` in step 5.
