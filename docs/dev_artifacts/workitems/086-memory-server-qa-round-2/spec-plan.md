# Feature 086: Memory Server QA Round 2 (PRD + Spec + Design + Plan)

Consolidates 10 post-release QA findings (#00085–#00094) from feature 085 into one coherent hardening bundle. Source = backlog items (no fresh brainstorm needed; findings are concrete).

## Problem Statement
Feature 085 shipped with 10 post-release QA findings from 5 parallel adversarial subagents. 3 HIGH (ReDoS, async umask race, untested FR-6 caller path), 6 MED (correctness/quality gaps), 1 LOW (cosmetic).

Investigation confirmed:
- **#00090 pytest global pollution is ALREADY mitigated** — both `test_memory_server.py:119-120` and `test_ranking.py:68-75` have autouse fixtures resetting module globals. Mark this finding as verified-false-alarm (document in retro; no code change).
- The remaining 9 items are real and fixable in-scope.

## Scope

### In scope (fix)
- **#00085** ReDoS detection + timeout in `_construct_matching_sample`
- **#00086** Async umask race serialization via `asyncio.Lock`
- **#00087** Caller-passed threshold zero-call test
- **#00088** JSON escape via `json.dumps` in `_render_test_sh`
- **#00089** Rotation-failure isolation (separate try/except from write path)
- **#00091** Migrate `memory_dedup_threshold` to `resolve_float_config`
- **#00092** 10 MB boundary off-by-one tests (2 cases)
- **#00093** End-to-end shell execution test for regex stub
- **#00094** Documentation of SC-9(a) cosmetic limitation (no code; retro-level)

### Closed as verified-already-fixed
- **#00090** pytest global pollution — autouse fixtures present

### Out of scope
- Low-severity security-reviewer suggestions (bidi chars, mkdir mode, symlink chmod on .1) — accepted risk for single-user pd
- `refresh.py`/`maintenance.py` `.open()` patterns — confirmed pre-existing out-of-scope per feature 085 TD-5

## Design

### Bundle A — Generator hardening (hook.py)

**#00085 ReDoS**: Extend `_COMPLEX_REGEX_MARKERS` detection OR add nested-quantifier regex check. Approach: add a pre-flight `_has_nested_quantifier(expr)` helper that looks for patterns like `(...+)+`, `(...*)+`, `(...+)*` using a regex over the regex. Simpler: extend `_is_complex_regex` to detect `[+*]\)[+*?]` or `\)[+*?]` after a capture group with inner quantifier.

**Implementation sketch:**
```python
_NESTED_QUANTIFIER_RE = re.compile(r"\([^)]*[+*?][^)]*\)[+*?]")

def _is_complex_regex(expr: str) -> bool:
    # existing substring checks...
    if _INLINE_FLAG_RE.search(expr):
        return True
    # NEW: catch nested quantifiers (ReDoS)
    if _NESTED_QUANTIFIER_RE.search(expr):
        return True
    return False
```

**Timeout guard for re.search**: Python stdlib `re` has no timeout kwarg. Options:
- Use `signal.SIGALRM` (POSIX only; sync-thread only; breaks asyncio).
- Use `threading` with timeout.
- Use short-input-only: `_construct_matching_sample` candidates are bounded-length strings constructed from the regex, so catastrophic backtracking on a SHORT input is unlikely. The real ReDoS risk is when an operator-authored regex runs against untrusted long input, which is not what this generator does.

**Pragmatic decision**: classifier check is sufficient. Candidates in `_construct_matching_sample` are ≤2× the regex length; ReDoS on those is practically bounded. Add the classifier pre-flight; skip threading-based timeout as over-engineering.

**#00088 JSON escape**: Replace f-string interpolation at `hook.py:434` and `:444` with `json.dumps`:
```python
import json
# before:
positive = f'{{"tool_input":{{"file_path":"{sample}"}}}}'
# after:
positive = json.dumps({"tool_input": {"file_path": sample}})
```

This breaks the shell single-quote protection pattern because `json.dumps` output contains `"` which collides with shell double-quotes. Solution: use `printf %s` or escape single quotes via `'\''` pattern. Simplest: keep POSITIVE_INPUT as a bash var with single-quote-escaped body via `${var//\'/\'\\\'\'}` — but this gets complex. Alternative: write POSITIVE_INPUT via base64 encoding, decode in test script. Simpler: do the json.dumps, then `'"'.join(json_str.split("'"))` to produce a shell-single-quote-safe string by replacing `'` inside with `'\''`.

**Cleanest fix**: use python's `shlex.quote` on the JSON string so the shell value is properly escaped regardless of JSON content.
```python
import json, shlex
positive_json = json.dumps({"tool_input": {"file_path": sample}})
positive_quoted = shlex.quote(positive_json)  # produces 'json-body' with single-quote safety
# in generated bash:
f"POSITIVE_INPUT={positive_quoted}\n"  # NO surrounding single quotes — shlex.quote adds them
```

### Bundle B — Memory server polish (memory_server.py)

**#00086 async umask race**: Serialize access to the umask critical section with an `asyncio.Lock` scoped to the MCP module. Since `_emit_influence_diagnostic` is called from async wrapper `record_influence_by_content`, we can grab the lock before entering the critical section.

But `_emit_influence_diagnostic` is currently SYNC. Two options:
1. Make it async and hold the lock across umask.
2. Keep it sync; wrap the umask section in `os.umask(0o600)` using a POSIX-idiomatic alternative: `os.open` + `os.fchmod(fd, 0o600)` after `os.fdopen`. This sidesteps umask entirely — create with O_CREAT inheriting umask (typically 0o644), then fchmod to 0o600 on the fd. TOCTOU window is 1 syscall (the open-then-fchmod gap) but during that window only the creator process holds the fd; no observer can act.

**Cleanest fix**: switch to `os.open` + `os.fchmod`. No umask manipulation, no async race.

```python
fd = os.open(
    str(INFLUENCE_DEBUG_LOG_PATH),
    os.O_APPEND | os.O_CREAT | os.O_WRONLY,
    0o600,  # mode arg is still masked by umask
)
try:
    # Defensive: enforce 0o600 regardless of umask.
    # os.fchmod acts on the fd, not the path — no race even if a symlink
    # was swapped mid-operation.
    os.fchmod(fd, 0o600)
except (OSError, NotImplementedError):
    pass  # Windows/platforms without fchmod — fall back to mode arg + umask
```

**#00089 rotation-failure isolation**: Split the outer try/except into two:
```python
# Rotation attempt — isolated so a transient rename failure doesn't silence writes.
try:
    current_size = INFLUENCE_DEBUG_LOG_PATH.stat().st_size
    if current_size >= _INFLUENCE_DEBUG_ROTATE_BYTES:
        os.rename(str(INFLUENCE_DEBUG_LOG_PATH), str(INFLUENCE_DEBUG_LOG_PATH) + ".1")
except FileNotFoundError:
    pass  # log doesn't exist yet
except OSError as exc:
    # Rotation failed — emit one-shot warning, continue to write (still appends to oversized log).
    if not _rotation_failure_warned:
        sys.stderr.write(f"[memory-server] rotation failed ({exc}); continuing to append\n")
        _rotation_failure_warned = True

# Write attempt — separate guard, separate failure flag.
try:
    line = json.dumps({...})
    # fchmod-based atomic 0o600 creation...
except (OSError, IOError) as exc:
    if not _influence_debug_write_failed:
        ...
```

**#00091 migrate `memory_dedup_threshold`**: At `memory_server.py:132`, change:
```python
# before:
threshold = cfg.get("memory_dedup_threshold", 0.90)
# after:
threshold = resolve_float_config(
    cfg, "memory_dedup_threshold", 0.90,
    prefix="[memory-server]", warned=_warned_fields, clamp=(0.0, 1.0),
)
```

### Bundle C — Test coverage additions

**#00087 caller-passed threshold**: Add pytest case to `TestSingleResolutionThresholdFR6`:
```python
def test_record_influence_by_content_skips_resolve_when_threshold_passed(
    self, db, monkeypatch
):
    # ... same setup as existing test ...
    asyncio.run(memory_server.record_influence_by_content(
        ..., threshold=0.8,  # caller-passed, non-None
    ))
    matching = [c for c in spy.call_args_list if ...]
    assert len(matching) == 0, "caller-passed threshold should bypass resolve_float_config"
```

**#00092 boundary tests**: Add 2 cases:
- `test_no_rotation_at_one_byte_below_threshold`: seed exactly `10 * 1024 * 1024 - 1` bytes → no rotation.
- `test_rotation_at_exact_threshold`: seed exactly `10 * 1024 * 1024` bytes → rotation occurs.

**#00093 end-to-end shell execution**: Add a pytest case that constructs a hook+test pair via `_render_test_sh`, writes to tmp_path, runs the test script via `subprocess`, asserts exit 0. Test only the simple-regex happy path (AC-H6); complex cases already have the fallback safety net.

**#00094 SC-9(a) doc note**: Add a comment in `test_memory_server.py` near the SC-9(b) spy test referencing the heuristic "SC assertions using single-line grep are fragile to multiline code" and explaining why the runtime spy (SC-9(b)) is the authoritative check.

## Plan (execution order)

Sequential with per-bundle commits. TDD RED-then-GREEN for new invariants.

1. **Bundle C.1**: Add RED tests for #00087 caller-passed-threshold and #00092 boundary cases. Verify they fail.
2. **Bundle B.1**: Implement #00089 rotation isolation (decouple rotation try/except from write try/except).
3. **Bundle B.2**: Implement #00086 async umask race fix via `os.fchmod` on fd (removes umask manipulation entirely).
4. **Bundle B.3**: Implement #00091 migrate `memory_dedup_threshold` to shared helper.
5. **Bundle A.1**: Implement #00085 ReDoS classifier extension — add `_NESTED_QUANTIFIER_RE`.
6. **Bundle A.2**: Implement #00088 JSON escape via `shlex.quote` in `_render_test_sh`.
7. **Bundle C.2**: Verify RED tests from step 1 now GREEN. Add #00093 end-to-end subprocess test. Add #00094 doc note.
8. **Gate**: Run `./validate.sh` + full pytest. Confirm green.
9. **Backlog annotation**: Mark #00085–#00094 as `(fixed in feature:086-memory-server-qa-round-2)` except #00090 (already-mitigated) which gets `(verified already mitigated in feature:086-memory-server-qa-round-2)`.
10. **CHANGELOG**: Add entries.
11. **Merge + release**.

## Tasks (compact)

### Task 1.1: RED — caller-passed threshold test (#00087)
Append to `TestSingleResolutionThresholdFR6` in `test_memory_server.py`: `test_caller_passed_threshold_bypasses_resolve`. Assert `len(matching) == 0` when `threshold=0.8`. DoD: test fails against current code.

### Task 1.2: RED — boundary rotation tests (#00092)
Add `test_no_rotation_just_below_threshold` (seed 10MB-1) and `test_rotation_at_exact_threshold` (seed exactly 10MB). Test the >= boundary. DoD: both pass against current `>=` code, but one would fail against a hypothetical `>` regression.

### Task 2: Rotation isolation (#00089)
In `_emit_influence_diagnostic`: split outer try into (a) rotation try/except with `_rotation_failure_warned` one-shot + `continue-to-write`, (b) write try/except with existing `_influence_debug_write_failed`. Add module-level `_rotation_failure_warned: bool = False`. Update autouse fixture in test_memory_server.py to reset the new global. DoD: rotation OSError no longer silences subsequent writes; existing `test_rotation_failure_skips_write_with_warning` may need revision to match new behavior.

### Task 3: Async race fix via fchmod (#00086)
Replace `os.umask(0); try: os.open; finally: os.umask(old)` block with `os.open` + `os.fchmod(fd, 0o600)` (wrapped in try/except for Windows). Update FR-2 comment to reflect the new pattern. DoD: existing SC-3 test still passes; no umask manipulation remains.

### Task 4: FR-4 completion (#00091)
`memory_server.py:132`: swap raw `cfg.get` for `resolve_float_config` with `clamp=(0.0, 1.0)`, `prefix="[memory-server]"`, `warned=_warned_fields`. DoD: grep verifies the dedup path now flows through the shared helper.

### Task 5: ReDoS classifier (#00085)
Add `_NESTED_QUANTIFIER_RE = re.compile(r"\([^)]*[+*?][^)]*\)[+*?]")` and integrate into `_is_complex_regex`. Add pytest cases: `test_nested_quantifier_classified_complex` for `(a+)+b`, `(x+x+)+y`. DoD: existing AC tests still pass; new ReDoS cases flagged as complex.

### Task 6: JSON escape via shlex.quote (#00088)
Update `_render_test_sh`:
- Replace f-string JSON construction (lines 434, 444) with `json.dumps(dict)`.
- Wrap the JSON body with `shlex.quote` so it works as a bash variable value without escaping mismatches.
- The generated script becomes `POSITIVE_INPUT={shlex_quoted}` with no surrounding single quotes (shlex.quote adds them).
DoD: existing tests pass; new test verifies `"` inside `sample` (if injected) is preserved through to the shell.

### Task 7: Verify Bundle C RED → GREEN
Re-run the 3 RED tests from Tasks 1.1 + 1.2 against HEAD after Tasks 2-6. All 3 should pass. DoD: pytest exit 0 for the feature 086 test subset.

### Task 8: End-to-end shell execution (#00093)
Add pytest case `test_render_test_sh_roundtrips_to_bash`: construct a minimal hook script that greps for the regex, construct POSITIVE_INPUT via `_render_test_sh`, write both to tmp_path, `chmod +x`, invoke via `subprocess.run(["bash", test_sh])`, assert exit 0. DoD: subprocess test green; catches Python re.search / grep -E divergence.

### Task 9: SC-9(a) doc note (#00094)
Add a 2-line comment near `TestSingleResolutionThresholdFR6` in `test_memory_server.py` explaining: SC-9(a) source grep is cosmetic (fails on multiline calls); SC-9(b) runtime spy (this class) is authoritative. Reference the memory heuristic name. DoD: comment present, no functional change.

### Task 10: Full validation + commits + backlog annotations
- Run `./validate.sh` → exit 0.
- Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ plugins/pd/mcp/` → exit 0 for feature tests.
- Annotate backlog items #00085-#00094 with `(fixed in feature:086-memory-server-qa-round-2)`; special annotation for #00090 (verified-already-mitigated).
- Update CHANGELOG.md.
- Bump `plugins/pd/plugin.json` dev version.

## Success Criteria

- [ ] SC-1: Backlog items #00085, #00086, #00087, #00088, #00089, #00091, #00092, #00093, #00094 annotated `(fixed in feature:086-memory-server-qa-round-2)`; #00090 annotated as verified-already-mitigated.
- [ ] SC-2: `_is_complex_regex` returns True for `(a+)+b`, `(x+x+)+y`, `(ab*)+c`. Pytest verifies.
- [ ] SC-3: `record_influence_by_content(threshold=0.8)` causes zero calls to `resolve_float_config` for `memory_influence_threshold`. Pytest spy verifies.
- [ ] SC-4: Rotation at exact 10 MB boundary works; 10MB-1 byte does not rotate. Two pytest cases.
- [ ] SC-5: `_emit_influence_diagnostic` uses `os.fchmod(fd, 0o600)` after `os.open`; no `os.umask(0)` manipulation in the function. Visual + grep.
- [ ] SC-6: Rotation OSError no longer silences subsequent writes. Revised rotation-failure test verifies.
- [ ] SC-7: `memory_server.py:132` (or current line) calls `resolve_float_config` for `memory_dedup_threshold`. Grep verifies.
- [ ] SC-8: `_render_test_sh` generates `POSITIVE_INPUT` via `json.dumps` + `shlex.quote`. Integration test via subprocess green.
- [ ] SC-9: `./validate.sh` green; full pytest green.
- [ ] SC-10: CHANGELOG updated with Unreleased entries.
