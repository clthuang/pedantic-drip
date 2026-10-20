# Design: 038 — YOLO Dependency-Aware Feature Selection

## Prior Art Research

### Codebase Patterns
- **PYTHONPATH convention:** `PYTHONPATH="${SCRIPT_DIR}/lib"` for inline Python in hooks; `conftest.py` uses `sys.path.insert(0, "..")` for tests
- **Stderr suppression:** All hook Python calls use `2>/dev/null` per CLAUDE.md safety rules
- **Existing hook lib structure:** `hooks/lib/` contains packages (`transition_gate/`, `workflow_engine/`, `entity_registry/`, `semantic_memory/`) plus standalone modules (`memory.py`). New `yolo_deps.py` follows the standalone module pattern.
- **Python subprocess pattern in yolo-stop.sh:** Two patterns — (1) inline `python3 -c` for simple JSON reads, (2) `PYTHONPATH=... python3 -c` for lib imports with graceful fallback

### External Patterns
- **Leaf-node emission (mise, Turborepo):** Only select tasks with all deps satisfied (in-degree = 0). Our check is simpler: binary per-feature eligibility check, not full graph resolution.
- **Exit code + stdout contract:** Python → shell communication via exit code (gate) + stdout (detail). Matches existing yolo-stop.sh pattern.
- **Fail-safe principle:** Missing/unreadable deps treated as unmet (same as mise's "reject on unknown dependency" pattern).

## Architecture Overview

### Component Diagram

```
yolo-stop.sh
├── [existing] Feature scan loop (lines 84-103)
│   ├── Read status from .meta.json (existing Python call)
│   ├── [NEW] Dependency check (merged into same Python call)
│   │   └── Imports check_feature_deps() from yolo_deps.py
│   └── mtime tiebreak (existing)
├── [NEW] Dep-skip diagnostics collection
├── [NEW] All-skipped early exit (exit 0, no JSON)
└── [existing] Block decision output
```

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| D-1: Merge status + dep check into one Python call | **Yes** | Spec R-1 constraint. Avoids doubling subprocess count per feature. Read status AND deps in one `python3 -c` invocation. |
| D-2: Standalone module vs package | **Standalone `yolo_deps.py`** | Single function, no internal dependencies. No `__init__.py` needed. Follows `memory.py` precedent. |
| D-3: Import mechanism from shell | `PYTHONPATH="${SCRIPT_DIR}/lib"` | Matches existing pattern at line 172 of yolo-stop.sh. Consistent with all hook lib imports. |
| D-4: Diagnostic output channel | stderr via `>&2` | Spec R-2: diagnostics go to stderr, not stdout (which is reserved for JSON block decisions). |
| D-5: Skip tracking | Bash array `SKIP_REASONS` | Collect skip reasons during loop, emit all at once if no eligible feature found. Shell-native, no extra Python. |

### Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Python import fails (yolo_deps.py not found) | Feature treated as having no deps (eligible) | Graceful fallback: if import fails, fall through to existing behavior (no dependency check). Feature still selected — safe default. |
| Performance: extra file reads per dependency | Negligible for <10 deps per feature | Single Python subprocess reads all dep `.meta.json` files in one invocation. O(n) file reads where n = number of deps. |
| Feature selection loop change breaks existing behavior | Features without `depends_on_features` skip dep check | `check_feature_deps` returns `(True, None)` for absent/null/empty deps — zero behavior change for existing features. |

## Components

### C-1: `yolo_deps.py` — Dependency Check Module

**Location:** `plugins/iflow/hooks/lib/yolo_deps.py`

**Responsibility:** Pure function that reads a feature's `.meta.json`, extracts `depends_on_features`, and checks each dependency's status.

**Dependencies:** Python stdlib only (`json`, `os`). No project imports.

**Edge cases:**
- If `meta_path` itself is unreadable or has malformed JSON → return `(True, None)` (treat as no deps, backward-compatible)
- Non-string elements in `depends_on_features` → `isinstance(dep, str)` check; if False, return `(False, f"{dep}:missing")`

**Pseudocode:**
```python
def check_feature_deps(meta_path, features_dir):
    try:
        meta = json.load(open(meta_path))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return (True, None)  # Can't read own meta → no deps assumed
    deps = meta.get("depends_on_features") or []
    for dep in deps:
        if not isinstance(dep, str):
            return (False, f"{dep}:missing")
        dep_meta_path = os.path.join(features_dir, dep, ".meta.json")
        try:
            dep_data = json.load(open(dep_meta_path))
            status = dep_data.get("status", "unknown")
            if status != "completed":
                return (False, f"{dep}:{status}")
        except FileNotFoundError:
            return (False, f"{dep}:missing")
        except (json.JSONDecodeError, OSError):
            return (False, f"{dep}:unreadable")
    return (True, None)
```

### C-2: Modified Feature Selection Loop in `yolo-stop.sh`

**Location:** `plugins/iflow/hooks/yolo-stop.sh` lines 84-103

**Responsibility:** Replace the existing single-purpose status-read Python call with a combined status + dependency check call. Collect skip diagnostics. Handle all-skipped case.

### C-3: Unit Tests — `TestCheckFeatureDeps`

**Location:** `plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py`

**Responsibility:** Test `check_feature_deps()` with `tmp_path` fixtures covering all acceptance criteria.

### C-4: Integration Tests

**Location:** `plugins/iflow/hooks/tests/test-hooks.sh`

**Responsibility:** End-to-end hook invocation with mock features testing AC-8 (skip + select) and AC-9 (all skipped → exit 0).

## Interfaces

### I-1: `check_feature_deps()` Function Signature

```python
def check_feature_deps(meta_path: str, features_dir: str) -> tuple[bool, str | None]:
    """Check if a feature's dependencies are all completed.

    Args:
        meta_path: Absolute path to the feature's .meta.json
        features_dir: Absolute path to the features directory

    Returns:
        (True, None) — all deps met or no deps declared
        (False, "dep_ref:status") — first unmet dep found

    Status labels:
        - Actual status string (e.g., "blocked", "planned", "active") for readable dep .meta.json
        - "missing" for FileNotFoundError
        - "unreadable" for JSONDecodeError or other parse failures
        - "missing" for non-string dep elements (coerced to str for ref)
    """
```

### I-2: Shell Integration — Combined Python Call

The existing Python call at lines 86-94 is replaced with a single call that returns both status and dep-check result. Paths are passed as `sys.argv` (not shell-interpolated strings) to handle special characters safely. Output uses pipe delimiter (matching existing pattern at line 126).

```bash
# Output format: "status|dep_result"
# dep_result is either "ELIGIBLE" or "SKIP:dep_ref:dep_status"
IFS='|' read -r status dep_result <<< "$(PYTHONPATH="${SCRIPT_DIR}/lib" python3 -c "
import json, sys, os
try:
    from yolo_deps import check_feature_deps
except ImportError:
    check_feature_deps = None

meta_path = sys.argv[1]
features_dir = sys.argv[2]

try:
    with open(meta_path) as f:
        d = json.load(f)
    status = d.get('status', '')
except Exception:
    status = ''

# Shell owns the 'active' gate (I-4). Python always returns status + dep result.
if check_feature_deps is None:
    print(f'{status}|ELIGIBLE')
    sys.exit(0)

eligible, reason = check_feature_deps(meta_path, features_dir)
if eligible:
    print(f'{status}|ELIGIBLE')
else:
    print(f'{status}|SKIP:{reason}')
" "$meta_file" "$FEATURES_DIR" 2>/dev/null)"
```

**Design notes:**
- **Safe path handling:** `sys.argv[1]` and `sys.argv[2]` avoid shell interpolation into Python string literals (matches safer pattern at line 55 of yolo-stop.sh).
- **Pipe delimiter:** `IFS='|' read -r` matches the existing pattern at line 126. Status values and feature refs never contain `|`.
- **Fallback:** If `yolo_deps` import fails, `check_feature_deps` is `None`, and the feature is treated as ELIGIBLE (backward-compatible).
- **Layering:** Shell owns control flow (`status == "active"` check in I-4). Python is pure data extraction — always returns status and dep result regardless of status value.

### I-3: Diagnostic Output Format

```bash
# Per-skipped-feature line (to stderr):
echo "[YOLO_MODE] Skipped ${feature_ref}: depends on ${dep_ref} (status: ${dep_status})." >&2

# All-skipped summary (to stderr):
echo "[YOLO_MODE] No eligible active features. Allowing stop." >&2
```

### I-4: Shell Loop Modified Structure

```bash
ACTIVE_META=""
ACTIVE_META_MTIME=0
declare -a SKIP_REASONS=()

for meta_file in "${FEATURES_DIR}"/*/.meta.json; do
    [[ -f "$meta_file" ]] || continue

    # Combined status + dep check (I-2) — pipe-delimited, paths via sys.argv
    # If Python fails entirely, both vars are empty → feature skipped (safe default)
    IFS='|' read -r status dep_result <<< "$(PYTHONPATH="${SCRIPT_DIR}/lib" python3 -c "..." "$meta_file" "$FEATURES_DIR" 2>/dev/null)"

    if [[ "$status" == "active" ]]; then
        if [[ "$dep_result" == SKIP:* ]]; then
            # Extract feature ref from directory name
            feature_dir=$(dirname "$meta_file")
            feature_ref=$(basename "$feature_dir")
            # Parse SKIP:dep_ref:dep_status
            # Colon-safe: feature refs use {id}-{slug} format (no colons),
            # status values are single-word enum members (no colons).
            skip_info="${dep_result#SKIP:}"
            dep_ref="${skip_info%%:*}"
            dep_status="${skip_info#*:}"
            SKIP_REASONS+=("[YOLO_MODE] Skipped ${feature_ref}: depends on ${dep_ref} (status: ${dep_status}).")
            continue
        fi

        mtime=$(stat -f "%m" "$meta_file" 2>/dev/null || stat -c "%Y" "$meta_file" 2>/dev/null || echo "0")
        if [[ "$mtime" -gt "$ACTIVE_META_MTIME" ]]; then
            ACTIVE_META="$meta_file"
            ACTIVE_META_MTIME="$mtime"
        fi
    fi
done

# All-skipped check: if we had active features but none were eligible
if [[ -z "$ACTIVE_META" && ${#SKIP_REASONS[@]} -gt 0 ]]; then
    for reason in "${SKIP_REASONS[@]}"; do
        echo "$reason" >&2
    done
    echo "[YOLO_MODE] No eligible active features. Allowing stop." >&2
    exit 0
fi
```

### I-5: Test Fixture Pattern

```python
class TestCheckFeatureDeps:
    """Tests for check_feature_deps() — AC-1 through AC-7, AC-3b."""

    def _write_meta(self, path: Path, data: dict) -> None:
        """Helper: write .meta.json to a feature directory."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def test_all_deps_completed(self, tmp_path):
        features_dir = tmp_path / "features"
        # Feature A depends on B (completed)
        self._write_meta(features_dir / "A" / ".meta.json",
                        {"status": "active", "depends_on_features": ["B"]})
        self._write_meta(features_dir / "B" / ".meta.json",
                        {"status": "completed"})

        eligible, reason = check_feature_deps(
            str(features_dir / "A" / ".meta.json"),
            str(features_dir))
        assert eligible is True
        assert reason is None
```

## Changed Files

| File | Change | Lines Affected |
|------|--------|---------------|
| `plugins/iflow/hooks/lib/yolo_deps.py` | **New.** ~30 lines. `check_feature_deps()` function | N/A (new file) |
| `plugins/iflow/hooks/yolo-stop.sh` | Replace lines 84-103 with combined status+dep loop | ~84-107 (expanded by ~15 lines) |
| `plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py` | Add `TestCheckFeatureDeps` class (~80 lines, 9 test methods) | Appended |
| `plugins/iflow/hooks/tests/test-hooks.sh` | Add 2 integration test functions (~30 lines) | Appended |
