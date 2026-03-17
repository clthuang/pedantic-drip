# Specification: 038 — YOLO Dependency-Aware Feature Selection

## Problem Statement

The YOLO Stop hook (`yolo-stop.sh`) selects the most-recently-modified active feature without checking whether its declared dependencies (`depends_on_features` in `.meta.json`) are completed. When the only active feature has unmet dependencies, this causes an infinite block loop — the hook keeps instructing the model to work on a feature it can't progress.

## Scope

**In scope:**
- Add dependency checking to the feature selection loop in `yolo-stop.sh` (lines 84-103)
- Extract dependency-check logic into a testable Python function
- Add diagnostic output when features are skipped due to unmet dependencies
- Unit tests for the new function

**Out of scope:**
- Project-scoped YOLO, auto-activation of planned features, data integrity enforcement (see PRD Non-Goals)
- Changes to `yolo-guard.sh`, workflow engine, or transition gates

## Requirements

### R-1: Dependency Filter in Feature Selection Loop

After confirming a feature has `status: "active"` (existing check, line 95), add a dependency check before considering it as a YOLO candidate:

1. Read `depends_on_features` from the feature's `.meta.json`
2. If key is absent, `null`, or `[]` → feature is eligible (skip dependency check)
3. For each dependency string (e.g., `"006-player-identity"`):
   - Resolve path: `{FEATURES_DIR}/{dep}/.meta.json` (dependency strings are expected to match feature directory names exactly, format: `{id}-{slug}`. If the directory does not exist, fail-safe handling applies per step 5.)
   - Read and parse the dependency's `.meta.json`
   - Check `status` field
4. If ANY dependency has `status != "completed"` → skip this feature
5. If dependency `.meta.json` is missing or unparseable → treat as unmet (fail-safe)
6. If any element in `depends_on_features` is not a string → treat as unmet (fail-safe)

Dependencies are checked in array order; the first unmet dependency encountered (by array position) is reported.

**Implementation constraint:** Use a single batched Python subprocess per feature (not one per dependency). The existing loop already spawns Python to read status; extend that call to also check dependencies.

### R-2: Diagnostic Output for Skipped Features

When a feature is skipped due to unmet dependencies, collect a diagnostic line:
```
[YOLO_MODE] Skipped {id}-{slug}: depends on {first_unmet_dep} (status: {dep_status}).
```

If ALL active features are skipped (no eligible candidate found), the hook must:
1. Output all collected diagnostic lines to stderr (informational, not part of any JSON block decision)
2. Allow stop (`exit 0`) — do NOT issue a block decision, no JSON output

**Design choice (OQ-2):** Report only the first unmet dependency per feature (fail-fast, reduces output noise).

### R-3: Testable Python Function

Extract the dependency-check logic into a standalone Python function importable from tests:

```python
def check_feature_deps(meta_path: str, features_dir: str) -> tuple[bool, str | None]:
    """Check if a feature's dependencies are all completed.

    Args:
        meta_path: Path to the feature's .meta.json
        features_dir: Path to the features directory

    Returns:
        (True, None) if all deps met or no deps declared.
        (False, "dep_ref:status") if any dep is unmet.
    """
```

**Location:** New file `plugins/iflow/hooks/lib/yolo_deps.py` — keeps hook lib modular and avoids growing `common.sh`. The function is called from `yolo-stop.sh` via inline Python that imports it.

### R-4: Interaction with Existing Controls

- **Stuck-detection (lines 147-154):** No change. Stuck-detection only fires when `stop_hook_active=true` (i.e., the hook previously issued a block). When all features are skipped by dependency check, no block is issued, so stuck-detection never activates for this case.
- **Max iterations (lines 159-169):** No change. `stop_count` is only incremented when a block IS issued. Skipped features that lead to `exit 0` don't increment the counter.
- **Usage limit (lines 31-70):** No change. Runs before feature selection.
- **stop_count (OQ-1 resolved):** When all active features are skipped (no eligible candidate), `stop_count` is neither incremented nor reset — the hook exits via `exit 0` before reaching counter logic. This deviates from the PRD's suggestion to reset, but is simpler and achieves the same effect (no false stuck-detection since no block is issued).

## Acceptance Criteria

### AC-1: Unmet Dependency Causes Skip
- Given: Feature A has `status: "active"`, `depends_on_features: ["B"]`
- And: Feature B has `status: "blocked"` (or any non-"completed" status)
- When: `check_feature_deps()` is called with Feature A's meta path
- Then: Returns `(False, "B:blocked")`

### AC-2: All Deps Met Allows Selection
- Given: Feature A has `status: "active"`, `depends_on_features: ["B"]`
- And: Feature B has `status: "completed"`
- When: `check_feature_deps()` is called
- Then: Returns `(True, None)`

### AC-3: Null Deps Allows Selection
- Given: Feature A has `depends_on_features: null`
- When: `check_feature_deps()` is called
- Then: Returns `(True, None)`

### AC-3b: Missing Key Allows Selection
- Given: Feature A's `.meta.json` has no `depends_on_features` key at all
- When: `check_feature_deps()` is called
- Then: Returns `(True, None)`

### AC-4: Empty Array Deps Allows Selection
- Given: Feature A has `depends_on_features: []`
- When: `check_feature_deps()` is called
- Then: Returns `(True, None)`

### AC-5: Missing Dep Meta Treated as Unmet (Fail-Safe)
- Given: Feature A has `depends_on_features: ["999-nonexistent"]`
- And: No file exists at `features/999-nonexistent/.meta.json`
- When: `check_feature_deps()` is called
- Then: Returns `(False, "999-nonexistent:missing")`

### AC-6: Malformed Dep Meta Treated as Unmet (Fail-Safe)
- Given: Feature A has `depends_on_features: ["B"]`
- And: `features/B/.meta.json` contains invalid JSON
- When: `check_feature_deps()` is called
- Then: Returns `(False, "B:missing")`

### AC-7: Multiple Deps — First Unmet Causes Skip
- Given: Feature A has `depends_on_features: ["B", "C"]`
- And: Feature B has `status: "completed"`, Feature C has `status: "planned"`
- When: `check_feature_deps()` is called
- Then: Returns `(False, "C:planned")`

### AC-8: Hook Skips Blocked Feature, Selects Eligible One
- Given: Features X (unmet deps) and Y (all deps met) both `status: "active"`
- When: The YOLO Stop hook's feature selection loop runs
- Then: Y is selected as the YOLO target (X skipped)

### AC-9: Hook Allows Stop When All Features Have Unmet Deps
- Given: All active features have at least one unmet dependency
- When: The YOLO Stop hook fires
- Then: Hook exits with code 0 (allow stop), no block decision issued
- And: Diagnostic lines are output for visibility

### AC-10: Existing Tests Pass
- Given: The existing `test_yolo_stop_phase_logic.py` test suite
- When: Tests run after changes
- Then: All existing tests pass without modification

## Test Strategy

### Unit Tests (in `test_yolo_stop_phase_logic.py`)

New test class `TestCheckFeatureDeps`:
- `test_all_deps_completed` → AC-2
- `test_null_deps` → AC-3
- `test_empty_deps` → AC-4
- `test_unmet_dep` → AC-1
- `test_missing_dep_meta` → AC-5
- `test_malformed_dep_meta` → AC-6
- `test_multiple_deps_first_unmet` → AC-7
- `test_multiple_deps_second_unmet` → AC-7 variant (first met, second unmet)
- `test_no_depends_on_features_key` → key missing entirely from JSON

Tests use `tmp_path` fixture to create mock `.meta.json` files. No database or engine dependency — the function is pure filesystem I/O.

### Integration Tests (in `test-hooks.sh`)

Add two integration test cases to the existing hook test suite:
- `test_yolo_stop_skips_blocked_dep` → AC-8: Set up two active features (one with unmet dep, one eligible), verify eligible one is selected
- `test_yolo_stop_all_deps_unmet_allows_stop` → AC-9: All active features have unmet deps, verify hook exits 0

These use mock `.meta.json` directories created in the test setup, following existing `test-hooks.sh` patterns.

## Changed Files

| File | Change |
|------|--------|
| `plugins/iflow/hooks/lib/yolo_deps.py` | **New.** `check_feature_deps()` function |
| `plugins/iflow/hooks/yolo-stop.sh` | Import and call `check_feature_deps()` in feature selection loop |
| `plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py` | New `TestCheckFeatureDeps` test class |
| `plugins/iflow/hooks/tests/test-hooks.sh` | Two integration test cases for AC-8, AC-9 |
