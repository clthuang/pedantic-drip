# PRD: Dependency-Aware YOLO Feature Selection

## Status
- Created: 2026-03-17
- Last updated: 2026-03-17
- Status: Draft
- Problem Type: Bug fix

## Problem Statement

YOLO mode gets stuck in an infinite loop when the only `status: "active"` feature has unmet dependencies. The Stop hook (`yolo-stop.sh`) selects features purely by scanning `.meta.json` for `status: "active"` and picking the most-recently-modified one. It has **no dependency awareness** — it doesn't check `depends_on_features` to verify prerequisites are completed.

### Observed Failure (Session Evidence)

In a cast-below session (2026-03-16). Feature IDs reference that external project, not this repo.

1. Features 011 and 013 completed successfully in YOLO mode within project P001
2. After each completion, the Stop hook fired: `[YOLO_MODE] Feature 007-social-economy-launch in progress. Last completed: null. Invoke /iflow:specify --feature=007-social-economy-launch with [YOLO_MODE].`
3. Feature 007 has `status: "active"` but `depends_on_features: ["006-player-identity"]` — and 006 is `status: "blocked"`
4. The model correctly identified 007 as unworkable and disabled YOLO mode
5. The user re-enabled YOLO mode 3 times, each time the same loop occurred
6. Session ended with YOLO disabled, unable to continue autonomous work on P001

### Root Causes

| # | Cause | Component | Impact | This PRD? |
|---|-------|-----------|--------|-----------|
| RC-1 | Stop hook ignores `depends_on_features` | `yolo-stop.sh` lines 75-127 | **Critical** — causes infinite loop | **Yes** |
| RC-2 | No project-scoped YOLO | `yolo.md` command, `yolo-stop.sh` | High — pre-existing design gap | Backlog |
| RC-3 | No automatic next-feature activation | `yolo-stop.sh`, finish-feature flow | High — pre-existing design gap | Backlog |
| RC-4 | Stale `status: "active"` on blocked feature | `.meta.json` data integrity | Medium — contributed to bug | Out of scope (dependency check makes system resilient to stale status) |

## Goals

1. **Break the stuck loop**: YOLO Stop hook must skip features whose dependencies aren't all completed
2. **Diagnostic visibility**: When skipping, output which feature was skipped and why

## Non-Goals

- Project-scoped YOLO (`--project` flag) — separate enhancement, tracked in backlog
- Auto-activation of next planned feature — command-level logic, not hook logic. Tracked in backlog
- Full priority/weight system for features (YAGNI)
- DB reconciliation on new machines (`.meta.json` is source of truth for hooks)
- Changes to `yolo-guard.sh` (works correctly)
- Changes to workflow engine or transition gates
- Data integrity enforcement for stale `status: "active"` on blocked features

## Functional Requirements

### FR-1: Dependency-Aware Feature Selection (RC-1 fix)

**In `yolo-stop.sh` feature selection loop (lines 75-127):**

When evaluating an active feature as a YOLO candidate:
1. Read `depends_on_features` array from `.meta.json`
2. For each dependency reference (e.g., `"006-player-identity"`):
   - Resolve `.meta.json` at `{artifacts_root}/features/{ref}/.meta.json`
   - Check `status` field
3. **Skip the feature if ANY dependency has status != "completed"**
4. If no eligible active feature found after filtering, **allow stop** (don't block) — immediately, without waiting for stuck-detection

**Edge cases:**
- `depends_on_features` is `null` or empty array → no blocking, feature is eligible
- Dependency `.meta.json` can't be read (missing file) → treat as unmet (fail-safe)
- Multiple active features: apply dependency filter to each, select most-recent mtime among eligible ones

### FR-2: Dependency Warning in Stop Hook Output

When the Stop hook skips a feature due to unmet dependencies, include diagnostic lines in the reason:

```
[YOLO_MODE] Skipped feature {id}-{slug}: depends on {unmet_dep} (status: {dep_status}).
[YOLO_MODE] No eligible active features. Allowing stop.
```

When a feature passes dependency check, no extra output (existing behavior).

## Technical Approach

### Changed Files

| File | Change | Complexity |
|------|--------|------------|
| `plugins/iflow/hooks/yolo-stop.sh` | Add dependency check in feature selection loop | Low-Medium |
| `plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py` | Add dep-check unit tests | Low |

### Implementation Strategy

**Option A (preferred): Single batched Python call**

Instead of spawning one Python subprocess per dependency, batch the entire check into one call:

```bash
# Read meta, check all deps in one Python invocation
dep_check=$(python3 -c "
import json, os, sys
meta = json.load(open('$meta_file'))
deps = meta.get('depends_on_features') or []
if not deps:
    print('ELIGIBLE')
    sys.exit(0)
features_dir = '$FEATURES_DIR'
for dep in deps:
    dep_meta = os.path.join(features_dir, dep, '.meta.json')
    try:
        dep_data = json.load(open(dep_meta))
        if dep_data.get('status') != 'completed':
            print(f'SKIP:{dep}:{dep_data.get(\"status\", \"unknown\")}')
            sys.exit(0)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f'SKIP:{dep}:missing')
        sys.exit(0)
print('ELIGIBLE')
" 2>/dev/null)
```

This keeps the subprocess count at 1 per active feature (existing pattern already spawns Python for JSON parsing).

**Stderr suppression:** All Python calls must use `2>/dev/null` per CLAUDE.md hook safety rules.

**Interaction with stuck-detection:** The existing stuck-detection (lines 148-154) checks if `stop_hook_active=true` and phase hasn't changed. With the dependency check, if all active features have unmet deps, the hook allows stop on first attempt (no block issued). Stuck-detection only applies when a feature IS selected but no progress occurs.

### Testability

Extract the dependency-check logic into a testable Python function (following the existing pattern where `compute_next_phase` is extracted and tested in `test_yolo_stop_phase_logic.py`). The function signature:

```python
def check_feature_deps(meta_path: str, features_dir: str) -> tuple[bool, str | None]:
    """Returns (eligible, skip_reason). eligible=True if all deps met."""
```

## Acceptance Criteria

### AC-1: Dependency Check Breaks Stuck Loop
- Given feature 007 has `status: "active"` and `depends_on_features: ["006-player-identity"]`
- And feature 006 has `status: "blocked"`
- When the YOLO Stop hook fires
- Then feature 007 is skipped (not selected as YOLO target)
- And stop is allowed on first attempt (no stuck-detection delay)

### AC-2: Eligible Active Feature Still Selected
- Given feature 014 has `status: "active"` and `depends_on_features: ["012-signal-resolver"]`
- And feature 012 has `status: "completed"`
- When the YOLO Stop hook fires
- Then feature 014 is selected as the YOLO target (existing behavior preserved)

### AC-3: No-Deps Feature Still Selected
- Given feature 009 has `status: "active"` and `depends_on_features: null`
- When the YOLO Stop hook fires
- Then feature 009 is selected (null/empty deps = no blocking)

### AC-4: Empty Array Deps Feature Still Selected
- Given feature 010 has `status: "active"` and `depends_on_features: []`
- When the YOLO Stop hook fires
- Then feature 010 is selected (empty array = no blocking)

### AC-5: Missing Dependency File Treated as Unmet
- Given feature 020 has `status: "active"` and `depends_on_features: ["999-nonexistent"]`
- And no directory `features/999-nonexistent/` exists
- When the YOLO Stop hook fires
- Then feature 020 is skipped (fail-safe)

### AC-6: Multiple Active Features, One Eligible
- Given features 007 and 014 both have `status: "active"`
- And 007 has unmet deps, 014 has all deps met
- When the YOLO Stop hook fires
- Then feature 014 is selected (007 skipped)

### AC-7: All Active Features Have Unmet Deps — Graceful Stop
- Given all active features have at least one unmet dependency
- When the YOLO Stop hook fires
- Then stop is allowed immediately
- And output includes diagnostic lines for each skipped feature

### AC-8: Diagnostic Output for Skipped Features
- Given feature 007 is skipped due to unmet dependency on 006
- When the Stop hook outputs its reason
- Then it includes: `Skipped feature 007-...: depends on 006-... (status: blocked)`

### AC-9: Existing Tests Still Pass
- Given the existing test suite in `test_yolo_stop_phase_logic.py`
- When tests run after changes
- Then all existing tests pass (no regressions)

## Test Strategy

### Unit Tests (new, in test_yolo_stop_phase_logic.py)

Extract `check_feature_deps()` into a Python function and test:
- All deps completed → eligible
- One dep not completed → skip with reason
- `depends_on_features: null` → eligible
- `depends_on_features: []` → eligible
- Missing dependency `.meta.json` → skip (fail-safe)
- Multiple deps, first met, second unmet → skip
- Malformed dependency `.meta.json` (invalid JSON) → skip (fail-safe)

### Integration Tests (in test-hooks.sh)
- YOLO stop with blocked dependency → stop allowed
- YOLO stop with eligible active feature → feature selected (existing behavior preserved)

## Risks

| Risk | Mitigation |
|------|-----------|
| Python subprocess overhead | Batched into single call per feature (existing pattern) |
| Missing `.meta.json` for dependency | Fail-safe: treat as unmet |
| Race condition: `.meta.json` updated mid-check | Acceptable: next hook invocation picks up changes |
| Breaking existing YOLO behavior | No change when `depends_on_features` is null/empty — backward compatible |

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| Fix at activation time (prevent stale active+blocked state) | Addresses RC-4 but doesn't fix RC-1 — a feature can legitimately be active when its dependency becomes un-completed (e.g., rollback). Hook-level resilience is the right layer. |
| Bash-native JSON parsing (jq/grep) | jq is not guaranteed installed. Python is already used throughout hooks. No benefit over batched Python call. |
| Pre-filter at feature creation | Would require changes to decomposition flow. Over-engineering for a hook bug fix. |

## Open Questions

1. **Stuck-detection interaction:** When no eligible feature is found and stop is allowed, should the hook reset `stop_count` in state file? Current design: yes (clean slate for next YOLO session).
2. **Multiple unmet deps:** When a feature has multiple unmet deps, should the diagnostic list all of them or just the first? Current design: first (fail-fast, less output noise).

## Future Enhancements (Backlog)

- **RC-2: Project-scoped YOLO** — `/yolo on --project P001` to restrict feature selection
- **RC-3: Auto-activate next planned feature** — Command-level (not hook) logic to find and activate next unblocked planned feature in a project after completing one
