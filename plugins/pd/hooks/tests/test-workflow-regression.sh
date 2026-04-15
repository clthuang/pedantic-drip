#!/usr/bin/env bash
# test-workflow-regression.sh — Behavioral regression tests for workflow phases (feature 078, FR-5 / REQ-4)
#
# Skeleton: sets up a temp dir with a mock feature folder + minimal .meta.json
# and a temp entity DB path for use by later test cases. Tears down the whole
# temp dir on any exit path.
#
# Task 1.1: harness (setup, teardown, placeholder test).
# Task 1.2: entity DB registration baseline.
# Task 1.3: complete_phase -> .meta.json projection assertion.
#
# Usage: bash plugins/pd/hooks/tests/test-workflow-regression.sh

set -euo pipefail

# --- Colors / logging helpers ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

log_test() {
    echo -e "TEST: $1"
    ((TESTS_RUN++)) || true
}

log_pass() {
    echo -e "${GREEN}  PASS${NC}"
    ((TESTS_PASSED++)) || true
}

log_fail() {
    echo -e "${RED}  FAIL: $1${NC}"
    ((TESTS_FAILED++)) || true
}

log_info() {
    echo -e "${YELLOW}  INFO: $1${NC}"
}

# --- Paths ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_ROOT="$(cd "${HOOKS_DIR}/.." && pwd)"

# Plugin venv Python + PYTHONPATH for entity_registry imports. Tests invoke
# the library directly (no MCP) against an isolated temp DB (ENTITY_DB_PATH).
PLUGIN_PY="${PLUGIN_ROOT}/.venv/bin/python"
PLUGIN_PYPATH="${HOOKS_DIR}/lib"

# Mock feature identity — a fake feature outside the real docs/features tree.
MOCK_FEATURE_ID="999"
MOCK_FEATURE_SLUG="mock-feature"
MOCK_FEATURE_DIRNAME="${MOCK_FEATURE_ID}-${MOCK_FEATURE_SLUG}"

# --- Setup ---
# TMPDIR_TEST:   scratch root for the whole test run.
# FEATURES_ROOT: mock `features/` dir housing the mock feature folder.
# MOCK_FEATURE_DIR: the mock feature folder (contains .meta.json).
# ENTITY_DB_PATH:   temp SQLite path for an isolated entity registry DB.
TMPDIR_TEST=$(mktemp -d -t pd-workflow-regression-XXXXXX)
FEATURES_ROOT="${TMPDIR_TEST}/features"
MOCK_FEATURE_DIR="${FEATURES_ROOT}/${MOCK_FEATURE_DIRNAME}"
MOCK_META_JSON="${MOCK_FEATURE_DIR}/.meta.json"
ENTITY_DB_PATH="${TMPDIR_TEST}/entities.db"

cleanup() {
    local exit_code=$?
    # Best-effort teardown: remove the entire temp dir. Never let cleanup fail.
    rm -rf "$TMPDIR_TEST" 2>/dev/null || true
    exit "$exit_code"
}
# Cleans up on normal exit AND on interrupt (Ctrl-C, SIGTERM, etc.).
trap cleanup EXIT INT TERM HUP

setup_mock_feature() {
    log_info "Setting up mock feature at: $MOCK_FEATURE_DIR"
    mkdir -p "$MOCK_FEATURE_DIR"

    # Minimal .meta.json modeled after real feature .meta.json files:
    # id, slug, status=active, lastCompletedPhase=specify. Timestamps are
    # stable strings (tests assert on structure, not exact times).
    cat > "$MOCK_META_JSON" <<EOF
{
  "id": "${MOCK_FEATURE_ID}",
  "slug": "${MOCK_FEATURE_SLUG}",
  "mode": "Standard",
  "status": "active",
  "created": "2026-04-15T00:00:00+00:00",
  "branch": "feature/${MOCK_FEATURE_DIRNAME}",
  "lastCompletedPhase": "specify",
  "phases": {
    "specify": {
      "started": "2026-04-15T00:00:00+00:00",
      "completed": "2026-04-15T00:10:00+00:00",
      "iterations": 1
    }
  }
}
EOF

    log_info "Mock entity DB path (not yet created): $ENTITY_DB_PATH"
}

# --- Tests ---

# Placeholder test: confirms the harness produced the expected mock feature
# artifacts. T1.2+ will add real regression tests against the entity DB,
# complete_phase, and phase transition guards.
test_skeleton_ok() {
    log_test "skeleton: mock feature dir and .meta.json exist; entity DB path is set"

    if [[ ! -d "$MOCK_FEATURE_DIR" ]]; then
        log_fail "mock feature dir missing: $MOCK_FEATURE_DIR"
        return
    fi

    if [[ ! -f "$MOCK_META_JSON" ]]; then
        log_fail ".meta.json missing: $MOCK_META_JSON"
        return
    fi

    # Validate .meta.json is well-formed and carries expected fields.
    if ! python3 -c "
import json, sys
with open('$MOCK_META_JSON') as f:
    meta = json.load(f)
assert meta.get('id') == '${MOCK_FEATURE_ID}', 'id mismatch: %r' % meta.get('id')
assert meta.get('slug') == '${MOCK_FEATURE_SLUG}', 'slug mismatch: %r' % meta.get('slug')
assert meta.get('status') == 'active', 'status mismatch: %r' % meta.get('status')
assert meta.get('lastCompletedPhase') == 'specify', 'lastCompletedPhase mismatch: %r' % meta.get('lastCompletedPhase')
" 2>/dev/null; then
        log_fail ".meta.json content did not match expected schema"
        return
    fi

    if [[ -z "${ENTITY_DB_PATH:-}" ]]; then
        log_fail "ENTITY_DB_PATH not set"
        return
    fi

    log_pass
}

# Regression test (T1.2): exercise the entity_registry Python library against
# an isolated temp DB. Registers a task entity, then re-opens the DB and
# asserts the row exists with the expected status. This is the baseline for
# FR-5: "after task registration, entity DB contains task entity with
# expected status".
test_entity_db_registration() {
    log_test "entity DB: register task entity via Python library, assert row exists with correct status"

    # Guard: venv python must be present. If the plugin hasn't been bootstrapped,
    # fail loudly rather than silently skipping — this test is a baseline that
    # must run on any dev machine.
    if [[ ! -x "$PLUGIN_PY" ]]; then
        log_fail "plugin venv python not found at: $PLUGIN_PY (run: uv sync in plugins/pd/)"
        return
    fi

    # Step 1: register the task entity. Uses register_entity() (public API).
    # Exports ENTITY_DB_PATH so the child process targets the isolated DB.
    # Stderr captured so failures surface in log_fail.
    local register_err
    if ! register_err=$(
        ENTITY_DB_PATH="$ENTITY_DB_PATH" \
        PYTHONPATH="$PLUGIN_PYPATH" \
        "$PLUGIN_PY" - <<'PY' 2>&1
import os, sys
from entity_registry.database import EntityDatabase

db = EntityDatabase(os.environ["ENTITY_DB_PATH"])
uuid = db.register_entity(
    entity_type="task",
    entity_id="regression-t1-2",
    name="regression test",
    project_id="test-regression",
    status="active",
)
if not uuid:
    print("register_entity returned empty UUID", file=sys.stderr)
    sys.exit(1)
PY
    ); then
        log_fail "register_entity failed: $register_err"
        return
    fi

    # Step 2: re-open the DB in a fresh process and query the row. Asserts
    # the entity exists AND its fields match what we registered. We print
    # a simple "OK" sentinel on success; anything else is a failure.
    local query_out
    if ! query_out=$(
        ENTITY_DB_PATH="$ENTITY_DB_PATH" \
        PYTHONPATH="$PLUGIN_PYPATH" \
        "$PLUGIN_PY" - <<'PY' 2>&1
import os, sys
from entity_registry.database import EntityDatabase

db = EntityDatabase(os.environ["ENTITY_DB_PATH"])
ent = db.get_entity("task:regression-t1-2")
if ent is None:
    print("entity not found for type_id=task:regression-t1-2", file=sys.stderr)
    sys.exit(1)

# Assert on the fields we set. status is the key acceptance criterion;
# the other three guard against silent schema drift.
checks = {
    "entity_type": "task",
    "entity_id": "regression-t1-2",
    "name": "regression test",
    "status": "active",
    "project_id": "test-regression",
    "type_id": "task:regression-t1-2",
}
for field, expected in checks.items():
    actual = ent.get(field)
    if actual != expected:
        print(f"field {field}: expected {expected!r}, got {actual!r}", file=sys.stderr)
        sys.exit(1)
print("OK")
PY
    ); then
        log_fail "entity query/assertions failed: $query_out"
        return
    fi

    if [[ "$query_out" != *"OK"* ]]; then
        log_fail "unexpected output from query step: $query_out"
        return
    fi

    log_pass
}

# Regression test (T1.3): exercise complete_phase through the MCP handler's
# in-process entrypoint (_process_complete_phase) against an isolated temp DB,
# then assert the on-disk .meta.json was projected with the expected phase
# completion fields.
#
# Why this shape:
#   - The task's Done criterion is "Test invokes complete_phase_impl via venv
#     Python; .meta.json assertions pass". The actual non-async function is
#     named _process_complete_phase in workflow_state_server.py (it's the
#     shared helper the @mcp.tool wrapper delegates to).
#   - We bypass MCP (no FastMCP spin-up) to keep the test hermetic and fast.
#   - We register the feature entity + its workflow_phases row in the SAME
#     isolated DB used by T1.2 (different type_id, no collision), so the
#     baseline assertion remains: mock feature lastCompletedPhase=specify
#     advances to design after complete_phase("design").
test_complete_phase_updates_meta_json() {
    log_test "complete_phase: advances .meta.json to design with non-null ISO timestamp"

    if [[ ! -x "$PLUGIN_PY" ]]; then
        log_fail "plugin venv python not found at: $PLUGIN_PY (run: uv sync in plugins/pd/)"
        return
    fi

    # FEATURES_ROOT is the mock artifacts_root. workflow_state_server doesn't
    # actually need it for this direct _process_complete_phase call (the
    # engine's artifacts_root is used for `_get_existing_artifacts` in gate
    # evaluation, which complete_phase doesn't run), but we pass it for
    # realism so the engine construction matches the real MCP lifespan.
    local mcp_dir="${PLUGIN_ROOT}/mcp"

    local run_out
    if ! run_out=$(
        ENTITY_DB_PATH="$ENTITY_DB_PATH" \
        MOCK_FEATURE_DIR="$MOCK_FEATURE_DIR" \
        FEATURES_ROOT="$FEATURES_ROOT" \
        MCP_DIR="$mcp_dir" \
        PYTHONPATH="$PLUGIN_PYPATH:$mcp_dir" \
        "$PLUGIN_PY" - <<'PY' 2>&1
import json
import os
import sys

from entity_registry.database import EntityDatabase
from workflow_engine.engine import WorkflowStateEngine
from workflow_state_server import _process_complete_phase

db_path = os.environ["ENTITY_DB_PATH"]
feature_dir = os.environ["MOCK_FEATURE_DIR"]
artifacts_root = os.environ["FEATURES_ROOT"]

feature_type_id = "feature:999-mock-feature"

db = EntityDatabase(db_path)

# Seed: entity + workflow_phases row. artifact_path points at the mock dir
# so _project_meta_json writes to MOCK_FEATURE_DIR/.meta.json.
# phase_timing seeds the existing `specify` completion so the .meta.json
# projection carries the prior phase forward (mirrors real-world state).
db.register_entity(
    entity_type="feature",
    entity_id="999-mock-feature",
    name="Mock Feature",
    project_id="test-regression",
    status="active",
    artifact_path=feature_dir,
    metadata={
        "id": "999",
        "slug": "mock-feature",
        "mode": "standard",
        "branch": "feature/999-mock-feature",
        "phase_timing": {
            "specify": {
                "started": "2026-04-15T00:00:00+00:00",
                "completed": "2026-04-15T00:10:00+00:00",
                "iterations": 1,
            },
        },
        "last_completed_phase": "specify",
    },
)

# Current workflow state: specify just completed, design is active.
# (Next phase after "specify" per PHASE_SEQUENCE is "design".)
db.create_workflow_phase(
    feature_type_id,
    workflow_phase="design",
    last_completed_phase="specify",
    mode="standard",
    kanban_column="wip",
)

engine = WorkflowStateEngine(db, artifacts_root)

# Call the in-process shared impl the @mcp.tool("complete_phase") wrapper
# delegates to. This is the closest thing to "complete_phase_impl" in the
# plan — the actual symbol is _process_complete_phase. Note we pass
# entity_engine=None so it falls back to the frozen engine path (simpler;
# we are not exercising cascade here).
result_json = _process_complete_phase(
    engine,
    feature_type_id,
    "design",
    db=db,
    iterations=2,
)
result = json.loads(result_json)
if result.get("error"):
    print(f"complete_phase returned error: {result}", file=sys.stderr)
    sys.exit(1)

# Post-condition: .meta.json on disk has been re-projected.
meta_path = os.path.join(feature_dir, ".meta.json")
if not os.path.exists(meta_path):
    print(f".meta.json missing at: {meta_path}", file=sys.stderr)
    sys.exit(1)

with open(meta_path) as f:
    meta = json.load(f)

# Assertion 1: lastCompletedPhase advanced to "design".
if meta.get("lastCompletedPhase") != "design":
    print(
        f"lastCompletedPhase mismatch: expected 'design', got "
        f"{meta.get('lastCompletedPhase')!r}",
        file=sys.stderr,
    )
    sys.exit(1)

# Assertion 2: phases.design.completed is non-null and ISO-8601 parseable.
design_phase = meta.get("phases", {}).get("design")
if not design_phase:
    print(f"phases.design missing from .meta.json; phases={meta.get('phases')!r}", file=sys.stderr)
    sys.exit(1)

completed_ts = design_phase.get("completed")
if not completed_ts:
    print(f"phases.design.completed is null/empty: {design_phase!r}", file=sys.stderr)
    sys.exit(1)

# Validate ISO-8601. datetime.fromisoformat accepts the "+00:00" offset
# style produced by _iso_now() in workflow_state_server.
from datetime import datetime
try:
    datetime.fromisoformat(completed_ts)
except ValueError as exc:
    print(
        f"phases.design.completed is not a valid ISO timestamp: "
        f"{completed_ts!r} ({exc})",
        file=sys.stderr,
    )
    sys.exit(1)

# Bonus sanity: prior phase's `specify.completed` should still be present
# (we seeded it in phase_timing; projection must preserve it).
specify_phase = meta.get("phases", {}).get("specify")
if not specify_phase or not specify_phase.get("completed"):
    print(
        f"phases.specify.completed missing after projection: "
        f"{specify_phase!r}",
        file=sys.stderr,
    )
    sys.exit(1)

print("OK")
PY
    ); then
        log_fail "complete_phase test failed: $run_out"
        return
    fi

    if [[ "$run_out" != *"OK"* ]]; then
        log_fail "unexpected output: $run_out"
        return
    fi

    log_pass
}

# Regression test (T1.4): exercise the workflow engine's phase transition
# guards. Verifies the valid/invalid contract from FR-5:
#   - transition_phase(target="design") SUCCEEDS when feature is in specify
#     and spec.md exists (G-08 hard prerequisite satisfied).
#   - transition_phase(target="implement") FAILS when feature is in specify
#     and implement-phase artifacts (design.md / plan.md / tasks.md) are
#     absent (G-08 blocks with allowed=False).
#
# Uses an isolated mock feature (998-mock-transition) with its own in-memory
# DB so this test does not depend on, or mutate, state from T1.2/T1.3.
T14_MOCK_FEATURE_ID="998"
T14_MOCK_FEATURE_SLUG="mock-transition"
T14_MOCK_FEATURE_DIRNAME="${T14_MOCK_FEATURE_ID}-${T14_MOCK_FEATURE_SLUG}"

setup_t14_mock_feature() {
    # Create the feature dir under the shared features root and write a
    # spec.md that satisfies the 4 levels of artifact validation for design:
    #   G-02 exists, G-03 size, G-04 headers, G-05/G-06 required sections.
    # Deliberately DO NOT create design.md / plan.md / tasks.md — their
    # absence is the precondition for the invalid-transition assertion.
    local feat_dir="${FEATURES_ROOT}/${T14_MOCK_FEATURE_DIRNAME}"
    mkdir -p "$feat_dir"
    cat > "${feat_dir}/spec.md" <<'EOF'
# Spec: Mock Transition Feature

## Overview
Mock content for phase transition guard testing.

## Scope
In scope: guard verification.

## Requirements
- REQ-1: guards fire correctly.

## Acceptance Criteria
- Tests pass.
EOF
}

test_phase_transition_guards() {
    log_test "phase transition guards: valid (specify -> design) succeeds; invalid (specify -> implement) blocks"

    setup_t14_mock_feature

    # Venv guard — same posture as sibling tests.
    if [[ ! -x "$PLUGIN_PY" ]]; then
        log_fail "plugin venv python not found at: $PLUGIN_PY (run: uv sync in plugins/pd/)"
        return
    fi

    # Drive the workflow engine via the plugin venv against an in-memory DB
    # (fully isolated from the shared ENTITY_DB_PATH used by T1.2/T1.3). The
    # engine root is TMPDIR_TEST because the engine expects "features/<slug>/"
    # beneath its root; our harness already created FEATURES_ROOT at
    # "${TMPDIR_TEST}/features".
    local mcp_dir="${PLUGIN_ROOT}/mcp"
    local py_output
    if ! py_output=$(
        PLUGIN_ROOT="$PLUGIN_ROOT" \
        ENGINE_ROOT="$TMPDIR_TEST" \
        FEATURE_SLUG="$T14_MOCK_FEATURE_DIRNAME" \
        FEATURE_TYPE_ID="feature:${T14_MOCK_FEATURE_DIRNAME}" \
        PYTHONPATH="$PLUGIN_PYPATH:$mcp_dir" \
        "$PLUGIN_PY" - <<'PY' 2>&1
import json
import os
import sys

from entity_registry.database import EntityDatabase
from workflow_engine.engine import WorkflowStateEngine
from workflow_state_server import _process_transition_phase

engine_root = os.environ["ENGINE_ROOT"]
feature_slug = os.environ["FEATURE_SLUG"]
feature_type_id = os.environ["FEATURE_TYPE_ID"]

db = EntityDatabase(":memory:")
db.register_entity(
    "feature", feature_slug, "Mock Transition Feature",
    status="active", project_id="__unknown__",
)
db.create_workflow_phase(feature_type_id, workflow_phase="specify")

engine = WorkflowStateEngine(db, engine_root)

# --- Valid transition: specify -> design (spec.md exists). ---
valid_raw = _process_transition_phase(
    engine, feature_type_id, "design", False, db=db,
)
valid_data = json.loads(valid_raw)

# Reset back to 'specify' so the second call starts from the same precondition
# (the first call, on success, advanced workflow_phase to 'design').
db.update_workflow_phase(feature_type_id, workflow_phase="specify")

# --- Invalid transition: specify -> implement (design/plan/tasks absent). ---
invalid_raw = _process_transition_phase(
    engine, feature_type_id, "implement", False, db=db,
)
invalid_data = json.loads(invalid_raw)

summary = {
    "valid": {
        "transitioned": valid_data.get("transitioned"),
        "degraded": valid_data.get("degraded"),
        "error": valid_data.get("error", False),
        "guard_ids": [r.get("guard_id") for r in valid_data.get("results", [])],
    },
    "invalid": {
        "transitioned": invalid_data.get("transitioned"),
        "degraded": invalid_data.get("degraded"),
        "error": invalid_data.get("error", False),
        "guard_ids": [r.get("guard_id") for r in invalid_data.get("results", [])],
        "blocking_guards": [
            r.get("guard_id") for r in invalid_data.get("results", [])
            if r.get("allowed") is False
        ],
    },
}
print(json.dumps(summary))
PY
    ); then
        log_fail "python driver crashed: $py_output"
        return
    fi

    # Parse + assert. Use an env var to pass the JSON into python3 — stdin
    # is consumed by the heredoc, so piping via stdin would silently fail.
    local parse_result
    if ! parse_result=$(PD_TEST_JSON="$py_output" python3 - <<'PY' 2>&1
import json, os, sys
data = json.loads(os.environ["PD_TEST_JSON"])
valid = data["valid"]
invalid = data["invalid"]

errors = []

# Valid-transition expectations
if valid.get("error"):
    errors.append(f"valid transition returned error payload: {valid}")
if valid.get("transitioned") is not True:
    errors.append(f"expected valid specify->design transitioned=True, got {valid}")
if valid.get("degraded") is True:
    errors.append(f"expected valid transition degraded=False, got {valid}")

# Invalid-transition expectations
if invalid.get("transitioned") is not False:
    errors.append(f"expected invalid specify->implement transitioned=False, got {invalid}")
if not invalid.get("blocking_guards"):
    errors.append(f"expected at least one blocking guard on invalid transition, got {invalid}")
# G-08 is the authoritative blocker: implement requires design.md / plan.md /
# tasks.md, none of which exist in the mock feature dir.
if "G-08" not in invalid.get("guard_ids", []):
    errors.append(f"expected G-08 to fire for missing implement prereqs, got {invalid}")

if errors:
    for e in errors:
        print(e)
    sys.exit(1)
PY
    ); then
        log_fail "assertions failed: ${parse_result} | raw: ${py_output}"
        return
    fi

    log_pass
}

# --- Main ---
main() {
    echo "Running test-workflow-regression.sh"
    echo "Temp dir: $TMPDIR_TEST"
    echo

    setup_mock_feature
    test_skeleton_ok
    test_entity_db_registration
    test_complete_phase_updates_meta_json
    test_phase_transition_guards

    echo
    echo "Ran: $TESTS_RUN | Passed: $TESTS_PASSED | Failed: $TESTS_FAILED"

    if [[ "$TESTS_FAILED" -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
