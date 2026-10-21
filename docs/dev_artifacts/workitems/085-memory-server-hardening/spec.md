# Specification: Memory Server Hardening (Feature 080 QA Bundle)

## Problem Statement
Feature 080 (`/pd:promote-pattern` + memory influence logging) left 8 post-QA residuals (#00067–#00074) that together create security risk (log permissions, HTML comment injection), unbounded log growth, ~80 LOC of near-duplicate float-config resolution, and missing CI guards for docs-sync invariants; this feature closes all 8 in one coherent PR.

## Success Criteria

- [ ] **SC-1**: All 8 backlog items annotated in `docs/backlog.md`. Verified by TWO distinct shell checks:
  - (a) Per-item completeness: `missing=$(for n in 00067 00068 00069 00070 00071 00072 00073 00074; do grep -q "| $n .*(fixed in feature:085-memory-server-hardening)" docs/backlog.md || echo $n; done); [ -z "$missing" ]` — exits 0 only when every target row has the annotation.
  - (b) Total count: `[ "$(grep -c 'fixed in feature:085-memory-server-hardening' docs/backlog.md)" -ge 8 ]` — guards against duplicate IDs or re-annotation oddities.

- [ ] **SC-2**: `_render_block` raises `ValueError` for `entry_name` containing `-->`, `<!--`, or triple-backtick — proven by 3 pytest cases in new `plugins/pd/hooks/tests/test_md_insert.py`, each asserting `pytest.raises(ValueError, match=<substring>)`.

- [ ] **SC-3**: `influence-debug.log` created with mode `0o600` atomically under ambient umask `0o022` — pytest sets `os.umask(0o022)` in setup, then calls `_emit_influence_diagnostic` on a fresh tmp_path log, asserts `os.stat(path).st_mode & 0o777 == 0o600`.

- [ ] **SC-4**: `_emit_influence_diagnostic` rotates to `.1` at size ≥ 10 MB — pytest pre-seeds tmp_path log with 10.5 MB content under umask `0o022`, invokes diagnostic, asserts: (a) `.1` exists with size ≈ 10.5 MB, (b) primary log size ≈ 1 line, (c) `os.stat(log_path).st_mode & 0o777 == 0o600` on the newly created primary log (FR-2's 0o600 invariant applies post-rotation too, since rotation triggers a fresh creation).

- [ ] **SC-5**: `plugins/pd/hooks/lib/semantic_memory/config_utils.py` exists and exports `resolve_float_config`; local duplicates deleted; no dangling references. Verified by TWO shell assertions:
  - (a) `grep -rE 'def (_resolve_float_config|_resolve_weight|_warn_and_default|_ranker_warn_and_default)\b' plugins/pd/mcp/memory_server.py plugins/pd/hooks/lib/semantic_memory/ranking.py | wc -l` → `0`
  - (b) `grep -rE '\b(_resolve_float_config|_resolve_weight|_ranker_warn_and_default)\b' plugins/pd/ --include='*.py' | wc -l` → `0` (catches indirect/import references anywhere in the tree). `_warn_and_default` is intentionally excluded from (b) because an int-variant survives in `refresh.py`/`maintenance.py` (see Scope → Out of Scope).

- [ ] **SC-6**: `resolve_float_config(config={"k": True}, key="k", default=0.05, ...)` returns `0.05` (NOT `1.0`); same for `False` → `0.05` (NOT `0.0`). Bool-handling pytest case in `test_config_utils.py` (new file).

- [ ] **SC-7**: Circular-import smoke test passes as an automated step in `validate.sh`: `PYTHONPATH=plugins/pd/hooks/lib python3 -c 'from semantic_memory import config_utils; from semantic_memory import ranking'` exits 0. (Automated CI check, runs on every validate.sh invocation.)

- [ ] **SC-8**: `"recorded"` key absent from `_emit_influence_diagnostic` JSON output — pytest asserts `"recorded" not in json.loads(log_line)`.

- [ ] **SC-9**: `record_influence_by_content` resolves `memory_influence_threshold` exactly once per invocation. Verified by TWO mechanisms:
  - (a) Source grep (static): `grep -n 'resolve_float_config' plugins/pd/mcp/memory_server.py | grep 'memory_influence_threshold' | wc -l` → `1` (single canonical call site).
  - (b) Runtime spy (dynamic): existing test file `plugins/pd/mcp/test_memory_server.py` inserts its parent directory into `sys.path` (see current test setup, lines 22-24), then imports via `import memory_server`. Therefore the pytest patch target MUST be the bound-import name at the consumer site: `unittest.mock.patch('memory_server.resolve_float_config', wraps=<reference to the real helper>)`. Rationale: Python's `from X import Y` binds `Y` into the importer's namespace at import time; patching `semantic_memory.config_utils.resolve_float_config` would NOT intercept calls made from within `memory_server`. Assertion: compute `matching = [c for c in spy.call_args_list if (c.kwargs.get("key") == "memory_influence_threshold") or (len(c.args) >= 2 and c.args[1] == "memory_influence_threshold")]; assert len(matching) == 1`.

- [ ] **SC-10**: Test stubs for `file_path_regex` / `content_regex` embed the actual `check_expression` for simple regexes and fall back with a comment for complex — proven by 5 pytest cases: (i) simple literal `\.env$` matches POSITIVE; (ii) alternation `foo|bar` matches first branch; (iii) character class `[a-z]+` matches; (iv) complex `(?i)secret` falls back with comment; (v) backreference `(foo)\1` falls back with comment.

- [ ] **SC-11**: `validate.sh` contains two automated regression guards running every CI invocation:
  - (a) `threshold=0.70` literal absent from non-test `.py` files under `plugins/pd/` — grep uses `--include='*.py' --exclude='test_*.py'` (the correct pattern for pd's inline-test convention, since `plugins/pd/mcp/test_memory_server.py` and `plugins/pd/hooks/lib/semantic_memory/test_dedup.py` are NOT under a `tests/` subdir).
  - (b) `memory_influence_` appears ≥ 3 times in `README_FOR_DEV.md`.
  Both automated, not manual. Additionally, a one-time implementation-phase sandbox test (PR description note, not ongoing) deliberately introduces `threshold=0.70` in a `.py` file and confirms `./validate.sh` fails with the expected message — documents that the guard works at PR time.

- [ ] **SC-12**: `./validate.sh` exits 0 on final PR.

- [ ] **SC-13**: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ plugins/pd/mcp/` exits 0.

- [ ] **SC-14**: No user-facing change to `/pd:promote-pattern`. Verified by golden-file snapshot tests stored at `plugins/pd/hooks/tests/fixtures/feature_085_snapshots/`:
  - **Input fixture**: `plugins/pd/hooks/tests/fixtures/feature_085_snapshots/input_kb.md` — a checked-in KB fragment with 3 promotable entries (none containing `-->`, `<!--`, or triple-backtick per FR-1 sanitizer; these snapshots verify unchanged happy-path output, not FR-1 rejection behavior).
  - **Snapshot targets**: (i) classifier output via `promote_pattern.classifier.classify_entries(input_kb)` serialized to deterministic JSON (sorted keys); (ii) `_render_block(...)` output for one entry; (iii) full `_md_insert.insert_block(...)` output against a target markdown fixture.
  - **Storage**: expected outputs at `plugins/pd/hooks/tests/fixtures/feature_085_snapshots/{classifier.json, render_block.md, md_insert.md}`, generated at start of implementation by running against the PRE-PR codebase.
  - **Test mechanism**: pytest cases in new `plugins/pd/hooks/tests/test_feature_085_snapshots.py` call the current code and assert `actual == Path(snapshot).read_text()`. Fixtures committed to the PR.
  - **Gating**: only FR-1 (sanitization) and FR-4 (helper extraction used indirectly by classifier via ranking) could plausibly change these outputs; FR-2, FR-3, FR-5, FR-6, FR-8 do not affect them. Snapshots MUST match exactly post-PR; any drift requires explicit update-in-PR with justification in commit message.

## Scope

### In Scope
- 3 security hardening items: `entry_name` sanitization (#00067), log permission bits (#00068), log rotation (#00069).
- 3 code quality items: shared `config_utils.py` extraction (#00070), drop redundant `recorded` field (#00071), eliminate double threshold resolution (#00072).
- 2 testability items: test stub regex embedding (#00073), `validate.sh` docs-sync guards (#00074).
- New pytest files: `test_md_insert.py` (pattern_promotion generator tests), `test_hook.py` (generator hook stub tests), `test_config_utils.py` (shared helper tests). None currently exist.
- Test migration in existing files — see **Test Migration** subsection below.
- New smoke test step in `validate.sh` for circular-import detection.

### Out of Scope
- Groups B (#00075–#00079) and C (#00080–#00084) QA follow-ups — separate features.
- Memory flywheel rewiring (#00053), FTS5 backfill, recall tracking — separate project P002.
- Promote-pattern classifier tuning (#00064/#00065/#00066) — separate follow-up.
- Concurrent-writer safety for `influence-debug.log` (single-writer assumption; see AC-E5 for observable failure mode).
- Configurable rotation threshold (hardcoded 10 MB).
- Retroactive mode bits on pre-existing `influence-debug.log` files (see AC-E3).
- Changes to `/pd:promote-pattern` user-facing behavior.
- **Int-variant helpers `_warn_and_default` + `_resolve_int_config`** in `plugins/pd/hooks/lib/semantic_memory/refresh.py` and `maintenance.py`. These are the int-typed counterpart to the float-config helpers being unified. Deliberately out of scope because (a) return type differs (int vs float), (b) the two int-variant call sites do not duplicate — they're a single definition used across two modules via direct import; no dedup opportunity; (c) unifying float+int into one generic helper widens scope beyond the 8 backlog items. If future consolidation is desired, file a follow-up backlog item.
- HTML comment escaping in `description` (only `entry_name` is guarded — see AC-E1 rationale).
- Windows support (pd targets macOS/Linux; AC-H3 and FR-3 rotation are POSIX-only).

### Test Migration

`resolve_float_config` replaces both `_resolve_float_config` (server) and `_resolve_weight` (ranker). All existing test-file call sites must migrate in this PR. Enumeration:

| File | Old Symbol | Line Refs (per Stage 1 review) |
|------|------------|-------------------------------|
| `plugins/pd/mcp/test_memory_server.py` | `_resolve_float_config`, `_warn_and_default` | 123, 128, 141, 150, 161, 171, 185, 199, 200, 201 |
| `plugins/pd/hooks/lib/semantic_memory/test_ranking.py` | `_resolve_weight`, `_ranker_warn_and_default` | 80, 85, 97, 109, 124, 137 |

Migration approach: direct rewrite to import and call `resolve_float_config` from `semantic_memory.config_utils`. NO shim or re-export. Tests that cover the existing warn-and-default behavior migrate to equivalent assertions against the shared helper. Tests that cover `_warn_and_default` internals (the call-when-misconfigured path) migrate to equivalent tests on the shared helper's warned-set side effect.

`refresh.py` and `maintenance.py` int-variant helpers are out of scope (see Out of Scope). Existing tests for those are untouched.

## Acceptance Criteria

### Happy Paths

**AC-H1: Sanitization rejects marker-closing substrings in entry_name**
- **Given** `entry_name = "weird -->"` queued for promotion
- **When** `_render_block(entry_name, description, mode)` is called
- **Then** raises `ValueError` whose message contains the offending substring `-->`; no HTML comment is emitted.

**AC-H2: Log created with 0o600 under nonzero umask**
- **Given** `influence-debug.log` does not yet exist and ambient umask is `0o022` (set explicitly in test setup)
- **When** `_emit_influence_diagnostic(...)` is called
- **Then** file created with `stat.st_mode & 0o777 == 0o600`; diagnostic line is appended.

**AC-H3: Log rotates at 10 MB threshold (POSIX behavior)**
- **Given** `influence-debug.log` exists at size 10.5 MB on POSIX (macOS/Linux — Windows out of scope)
- **When** `_emit_influence_diagnostic(...)` is called
- **Then** existing file is renamed to `influence-debug.log.1` (POSIX `os.rename` overwrites any prior `.1` atomically); new `influence-debug.log` is created with mode `0o600`; the new diagnostic line is the only content.

**AC-H4: Shared helper returns default for bool input**
- **Given** config dict `{"memory_influence_weight": True}` or `{"memory_influence_weight": False}`
- **When** `resolve_float_config(config, "memory_influence_weight", default=0.05, prefix="[ranker]", warned=set())` is called
- **Then** return value is `0.05` (the default — NOT `1.0` for True, NOT `0.0` for False); one-shot warning added to `warned`. Implementation MUST check `isinstance(raw, bool)` BEFORE `isinstance(raw, (int, float))` — verified by explicit pytest cases for both True and False.

**AC-H5: Single-resolution threshold in influence wrapper**
- **Given** `memory_influence_threshold` configured to `0.70`
- **When** `record_influence_by_content(...)` MCP tool is invoked once
- **Then** `resolve_float_config` is invoked exactly once with `key="memory_influence_threshold"` during that MCP call. Verified by `unittest.mock.patch('memory_server.resolve_float_config', wraps=<real helper>)` spy (NOT `plugins.pd.mcp.memory_server.*` — the test harness inserts the `mcp/` dir into sys.path and imports `memory_server` directly; patching must target the bound-import name at the consumer site). Assertion: `matching = [c for c in spy.call_args_list if (c.kwargs.get("key") == "memory_influence_threshold") or (len(c.args) >= 2 and c.args[1] == "memory_influence_threshold")]; assert len(matching) == 1`.

**AC-H6: Regex-aware test stub generation (simple literal regex)**
- **Given** feasibility dict with `check_kind="file_path_regex"` and `check_expression=r"\.env$"`
- **When** `_render_test_sh(...)` runs
- **Then** generated `POSITIVE_INPUT` contains a string matching `r"\.env$"` (e.g., `foo.env`); `NEGATIVE_INPUT` does NOT match; no complex-regex comment.

**AC-H7: Regex-aware test stub generation (alternation — simple)**
- **Given** `check_expression=r"foo|bar"`
- **When** `_render_test_sh(...)` runs
- **Then** `POSITIVE_INPUT` matches the first branch (`foo`); `NEGATIVE_INPUT` matches neither branch; no complex-regex comment. (Alternation is classified as simple.)

**AC-H8: Regex-aware test stub generation (character class + quantifier — simple)**
- **Given** `check_expression=r"[a-z]+@example\.com"`
- **When** `_render_test_sh(...)` runs
- **Then** `POSITIVE_INPUT` matches (e.g., `alice@example.com`); no complex-regex comment.

**AC-H9: Regex-aware test stub generation (inline flag — complex)**
- **Given** `check_expression=r"(?i)secret"`
- **When** `_render_test_sh(...)` runs
- **Then** `POSITIVE_INPUT` falls back to the current generic stub string (which may or may not match the expression — the generated script is NOT asserted to pass for complex regexes; only the presence of the comment is asserted) AND generated script contains the comment `# NOTE: regex too complex for auto-embedded POSITIVE_INPUT — review manually`. This aligns with FR-7's intent to document the limitation without breaking the test.

**AC-H10: docs-sync regression guard active (threshold literal)**
- **Given** a developer reintroduces literal `threshold=0.70` in `plugins/pd/mcp/memory_server.py` (a non-test `.py` file)
- **When** `./validate.sh` runs
- **Then** exits non-zero with message `FAIL: threshold=0.70 literal resurfaced (1 occurrence)`.

**AC-H11: docs-sync regression guard active (README count)**
- **Given** a refactor drops one `memory_influence_*` line from `README_FOR_DEV.md`, leaving 2 references
- **When** `./validate.sh` runs
- **Then** exits non-zero with message `FAIL: memory_influence_* docs in README_FOR_DEV.md dropped below 3 (2)`.

**AC-H12: Circular-import smoke test active**
- **Given** a developer adds `from semantic_memory.ranking import _resolve_weight` (or similar) inside `config_utils.py`
- **When** `./validate.sh` runs
- **Then** the smoke-test step fails, reporting an `ImportError` or `ModuleNotFoundError`.

### Error & Boundary Cases

**AC-E1: Description contains `<!--` — NOT sanitized (intentional scope)**
- **Given** `entry_name = "Normal Entry"` (clean) AND `description = "example: <!-- notes --> details"`
- **When** `_render_block(entry_name, description, mode)` runs
- **Then** call succeeds with NO `ValueError`; the rendered markdown contains the description's literal `<!--` and `-->` characters. Rationale: the `<!-- Promoted: {entry_name} -->` marker interpolates only `entry_name`; `description` is emitted OUTSIDE that marker as body text. Existing `_sanitize_description` (verified at `_md_insert.py:27-74`) handles markdown-structural chars (`#`, `---`, `===`, triple-backticks) and caps length at 500 chars but deliberately does NOT escape `<!--`/`-->` — description is body content, not comment content, so HTML comment injection does not apply here.

**AC-E2: Triple-backtick in entry_name**
- **Given** `entry_name = "Tricky \`\`\` pattern"`
- **When** `_render_block(...)` is called
- **Then** `ValueError` raised with message identifying `` ``` `` as the offending substring.

**AC-E3: Log file pre-exists with permissive mode**
- **Given** `influence-debug.log` exists with mode `0o644` (created before this PR or by another process)
- **When** `_emit_influence_diagnostic(...)` is called
- **Then** mode is NOT retroactively changed (`O_CREAT` is a no-op for existing files); append succeeds. Documented in FR-2 comment that operators wanting 0o600 on pre-existing logs must manually delete and let the next call re-create.

**AC-E4: Rotation rename fails**
- **Given** `influence-debug.log` at 10.5 MB but `.1` target is not writable (permission denied, or parent dir read-only)
- **When** `_emit_influence_diagnostic(...)` is called
- **Then** `os.rename` raises `OSError`; caught by `except (OSError, IOError)` around the rotation+write block; one stderr warning emitted via `_influence_debug_write_failed` (one-shot per process); this diagnostic call skipped; subsequent calls retry rotation and eventually succeed when the condition clears.

**AC-E5: Concurrent writers — best-effort single-writer model**
- **Given** two MCP server processes (e.g., two parallel Claude Code sessions) call `_emit_influence_diagnostic` simultaneously with the log at 10.5 MB
- **When** both reach the rotation block concurrently
- **Then** behavior is best-effort, NOT undefined: `os.rename` is atomic at syscall level on POSIX (Linux/macOS), so at most one rename succeeds per instant; the loser sees the file already rotated on retry. The observable failure mode is that at most one diagnostic line per race may land in `influence-debug.log.1` (the rotated file) rather than the fresh primary log — operators reading the log should consult `.1` for recent-but-rotated lines. This is acceptable because diagnostic LOSS is not a correctness concern (debug-only opt-in path); no guarantee against torn writes across processes.

**AC-E6: Config value is `None`**
- **Given** config dict `{"memory_influence_weight": None}`
- **When** `resolve_float_config(...)` is called
- **Then** return value is default; one-shot warning added.

**AC-E7: Config value is string `"0.25"`**
- **Given** config dict `{"memory_influence_weight": "0.25"}`
- **When** `resolve_float_config(...)` is called with `clamp=(0.0, 1.0)`
- **Then** return value is `0.25` (parsed via `float()`); no warning.

**AC-E8: Config value is string `"invalid"`**
- **Given** config dict `{"memory_influence_weight": "invalid"}`
- **When** `resolve_float_config(...)` is called
- **Then** return value is default; one-shot warning added.

**AC-E9: Rotation of pre-existing `.1` file (POSIX)**
- **Given** `influence-debug.log` at 10.5 MB AND `influence-debug.log.1` already exists with prior rotated content
- **When** `_emit_influence_diagnostic(...)` triggers rotation
- **Then** on POSIX, `os.rename` overwrites `.1` atomically — prior `.1` content is lost; new `.1` contains previous primary content. pd supports only macOS/Linux; Windows is not tested and is out of scope.

**AC-E10: Numpy-bool and bool-subclass inputs (documented acceptance)**
- **Given** config dict containing any subclass of `bool` (e.g., if a future loader introduces `numpy.bool_`)
- **When** `resolve_float_config(...)` is called
- **Then** treated as bool, returns default. This holds because `isinstance(raw, bool)` matches `numpy.bool_` (which inherits from Python `bool`). Note: **the config-loading boundary** — `plugins/pd/hooks/lib/semantic_memory/config.py` — does not import numpy (verified by `grep -n 'numpy\|np\.' plugins/pd/hooks/lib/semantic_memory/config.py` → 0 matches). `memory_server.py` DOES import numpy for embedding math (at `memory_server.py:31`) but config values never flow through that embedding path before reaching `resolve_float_config`; config values are read from the pd config file (stdlib YAML/JSON), then handed to the resolver with no numpy involvement. This AC documents the invariant as static analysis; no runtime numpy test is added (NFR-3: no new deps).

**AC-E11: `_render_test_sh` regex contains backreference `\1` — complex**
- **Given** `check_expression = r"(foo)\1"`
- **When** `_render_test_sh(...)` runs
- **Then** classified as complex (backreference — substring `\1`..`\9` detected in expression); generic POSITIVE_INPUT with complex-regex comment injected.

**AC-E12: `_render_test_sh` regex contains lookahead `(?=...)`  — complex**
- **Given** `check_expression = r"foo(?=bar)"`
- **When** `_render_test_sh(...)` runs
- **Then** classified as complex (substring `(?=` detected); generic POSITIVE_INPUT with complex-regex comment injected.

### State Transitions

No nontrivial state machine — sequential code changes. Rotation state is implicit in filesystem (single file or file + `.1` counterpart).

## Feasibility Assessment

### Assessment Approach
1. **First Principles**: All 8 items are stdlib-only refactors of existing code paths. No new protocols, external services, or unknown technology.
2. **Codebase Evidence**: Stage 2 research + Stage 4 spec-review verified all file:line references and critical claims:
   - `_sanitize_description` handles markdown structure but NOT HTML comment markers (verified at `_md_insert.py:27-74`) — AC-E1 rationale holds because description lands outside the comment marker, not inside.
   - Test files are inline (NOT in `tests/` subdir): `plugins/pd/mcp/test_memory_server.py`, `plugins/pd/hooks/lib/semantic_memory/test_dedup.py`, `plugins/pd/hooks/lib/semantic_memory/test_ranking.py` — FR-8 grep uses `--exclude='test_*.py'` not `--exclude-dir=tests`.
   - `_resolve_float_config` (server) at `mcp/memory_server.py:428-463`; `_resolve_weight` (ranker) at `hooks/lib/semantic_memory/ranking.py:20-63`.
3. **External Evidence**: OpenStack Security Guide confirms `os.open + fdopen + umask=0` pattern. MDN confirms `-->` universally terminates HTML comments. FR-7 complex-regex classifier uses pure substring detection (search for literal `(?=`, `(?!`, `(?<=`, `(?<!`, `(?P`, `(?#`, `(?i)`, `(?s)`, `(?m)`, `\1`..`\9`) — NOT `sre_parse` (deprecated in Python 3.12, scheduled for removal). Substring detection is future-proof and handles every cited complex case correctly; false-negatives are acceptable because the fallback for complex regexes is the safe (non-asserting) generic test stub, not a broken assertion.

### Assessment
**Overall:** Confirmed

**Reasoning:** Every FR maps to a stdlib refactor of already-existing code. Highest-uncertainty item (`config_utils.py` extraction with bool-order invariant) is guarded by SC-6 (dedicated bool test), SC-7 (circular-import smoke), and test-migration enumeration (Scope → Test Migration).

**Key Assumptions:**
- File paths in backlog remain accurate at implementation time — Status: Verified at `plugins/pd/mcp/memory_server.py:418-500`, `plugins/pd/hooks/lib/semantic_memory/ranking.py:20-63`, `plugins/pd/hooks/lib/pattern_promotion/generators/_md_insert.py:27,114-131`, `plugins/pd/hooks/lib/pattern_promotion/generators/hook.py:65,269-337` as of 2026-04-19 Stage 2.
- Existing pytest suite detects behavioral regressions in promote-pattern flow — Status: Verified by SC-14 snapshot tests; implementer captures pre-PR snapshots, re-runs post-PR, asserts equality.
- `os.umask(0)` in FR-2 does not race with unrelated processes — Status: Verified (umask is per-process).
- `config_utils.py` import boundary (stdlib + `config.py` only) is enforced by SC-7 smoke test.
- pd config loading is stdlib-only (no numpy) — Status: Verified by `grep -r "numpy" plugins/pd/hooks/lib/semantic_memory/config.py plugins/pd/mcp/memory_server.py` → 0 matches (AC-E10).

**Open Risks:**
- If a future YAML loader introduces typed values beyond stdlib (via pyyaml C extensions or similar), AC-E10's assumption weakens. Mitigated by `isinstance(raw, bool)` check order.
- If a future developer renames a `memory_influence_*` config key, SC-11 guard remains valid at `>= 3` but false-passes if the new name drops below 3. Acceptable tradeoff (per Feasibility advisor).
- Retroactively changing mode on pre-existing log files explicitly out of scope per AC-E3.

## Dependencies
- Existing pytest infrastructure in `plugins/pd/hooks/tests/`, `plugins/pd/hooks/lib/semantic_memory/`, and `plugins/pd/mcp/` (tests inline with source per pd convention).
- `plugins/pd/.venv` Python virtualenv.
- No new runtime packages; stdlib only (`os`, `sre_parse`, `unittest.mock`).
- `validate.sh` existing framework (~830 lines, adds one section after line 824 + one smoke-test step).

## Open Questions
- None. All scoping questions resolved during brainstorm and Stage 4 spec review. See `prd.md` Review History and this spec's Review History (in `.review-history.md`).
