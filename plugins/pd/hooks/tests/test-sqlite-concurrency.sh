#!/usr/bin/env bash
# test-sqlite-concurrency.sh — Phase 0 spike for FR-0 / REQ-1 (feature 078)
#
# Sets up a temp git repo with 3 worktrees and spawns 3 parallel background
# processes, each writing 10 entity rows to a single shared entity_registry
# SQLite DB under WAL mode + busy_timeout=15000. Asserts that all 30 rows
# land in the DB and reports wall-clock time, retry count, and success rate.
#
# Task 0.1 added the harness; Task 0.2 adds the parallel-write test. Metrics
# are printed to stdout only — writing a structured results file is T0.3.
#
# Usage: bash plugins/pd/hooks/tests/test-sqlite-concurrency.sh

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

NUM_WORKTREES=3
ENTITIES_PER_PROC=10
TOTAL_EXPECTED=$((NUM_WORKTREES * ENTITIES_PER_PROC))

# Plugin Python environment. Prefer the plugin venv (installed deps); fall
# back to system python3. entity_registry lives in hooks/lib and is imported
# by adding it to PYTHONPATH.
PLUGIN_VENV_PYTHON="${PLUGIN_ROOT}/.venv/bin/python"
if [[ -x "$PLUGIN_VENV_PYTHON" ]]; then
    PD_PYTHON="$PLUGIN_VENV_PYTHON"
else
    PD_PYTHON="$(command -v python3)"
fi
PD_PYTHONPATH="${HOOKS_DIR}/lib"

# --- Setup ---
# TMPDIR_TEST: scratch root for the whole test run.
# REPO_DIR:    bare-enough main repo we initialize with an initial commit.
# WORKTREE_DIRS: array of absolute paths to the created worktrees.
TMPDIR_TEST=$(mktemp -d -t pd-sqlite-concurrency-XXXXXX)
REPO_DIR="${TMPDIR_TEST}/repo"
WORKTREES_ROOT="${TMPDIR_TEST}/worktrees"
WORKTREE_DIRS=()

cleanup() {
    local exit_code=$?
    # Best-effort teardown: remove worktrees first (git needs repo present),
    # then nuke the whole temp dir. Never let cleanup fail the script.
    if [[ -d "$REPO_DIR/.git" ]]; then
        for wt in "${WORKTREE_DIRS[@]:-}"; do
            if [[ -n "$wt" && -d "$wt" ]]; then
                git -C "$REPO_DIR" worktree remove --force "$wt" >/dev/null 2>&1 || true
            fi
        done
        git -C "$REPO_DIR" worktree prune >/dev/null 2>&1 || true
    fi
    rm -rf "$TMPDIR_TEST" 2>/dev/null || true
    exit "$exit_code"
}
# Cleans up on normal exit AND on interrupt (Ctrl-C, SIGTERM, etc.).
trap cleanup EXIT INT TERM HUP

setup_repo_and_worktrees() {
    log_info "Setting up temp repo at: $REPO_DIR"
    mkdir -p "$REPO_DIR"
    git -C "$REPO_DIR" init --quiet --initial-branch=main
    git -C "$REPO_DIR" config user.email "spike@pd.test"
    git -C "$REPO_DIR" config user.name "pd spike"
    git -C "$REPO_DIR" config commit.gpgsign false

    # Need at least one commit so `git worktree add -b` can branch off HEAD.
    echo "# spike" > "$REPO_DIR/README.md"
    git -C "$REPO_DIR" add README.md
    git -C "$REPO_DIR" commit --quiet -m "initial commit"

    mkdir -p "$WORKTREES_ROOT"
    for i in $(seq 1 "$NUM_WORKTREES"); do
        local wt="${WORKTREES_ROOT}/wt-${i}"
        local branch="spike-wt-${i}"
        git -C "$REPO_DIR" worktree add --quiet -b "$branch" "$wt" >/dev/null
        WORKTREE_DIRS+=("$wt")
    done

    log_info "Created ${#WORKTREE_DIRS[@]} worktrees under: $WORKTREES_ROOT"
}

# --- Worker script ---
# Python worker that writes ENTITIES_PER_PROC rows into the shared DB.
#
# Takes three CLI args:
#   argv[1]  db_path       absolute path to the shared entity DB
#   argv[2]  proc_index    1-based index of this worker (used in type_id)
#   argv[3]  count         number of entities to write
#
# Writes a JSON summary to stdout (single line) with:
#   {"proc": N, "written": K, "retries": R, "errors": [...], "elapsed_s": T}
# and exits 0 even on partial failure — the harness aggregates and decides.
#
# Uses entity_registry.database.EntityDatabase directly (bypassing MCP) to
# mirror the worktree-agent topology where multiple processes share one DB
# but each opens its own connection. WAL + busy_timeout=15000 are set by
# EntityDatabase._set_pragmas(); explicit retry-on-OperationalError catches
# the rare case where the 15s timeout is still exhausted.
WORKER_SCRIPT="${TMPDIR_TEST}/worker.py"
cat > "$WORKER_SCRIPT" <<'PYEOF'
import json
import sqlite3
import sys
import time

db_path = sys.argv[1]
proc_index = int(sys.argv[2])
count = int(sys.argv[3])

# Import entity_registry from hooks/lib (set via PYTHONPATH by caller).
from entity_registry.database import EntityDatabase

db = EntityDatabase(db_path)

written = 0
retries = 0
errors = []
start = time.monotonic()

for m in range(1, count + 1):
    entity_id = f"t02-proc{proc_index}-entity{m}"
    attempts = 0
    while True:
        attempts += 1
        try:
            db.register_entity(
                "feature",
                entity_id,
                f"T0.2 spike entity proc={proc_index} m={m}",
                project_id="test-078-sqlite-concurrency",
                metadata={"proc": proc_index, "m": m},
            )
            written += 1
            break
        except sqlite3.OperationalError as e:
            # busy_timeout=15000 should absorb most contention internally.
            # If we still see "database is locked" here, retry with short
            # backoff. Cap at 3 attempts per entity to bound worst case.
            msg = str(e)
            if "locked" in msg.lower() or "busy" in msg.lower():
                retries += 1
                if attempts >= 3:
                    errors.append({"entity_id": entity_id, "error": msg})
                    break
                time.sleep(0.1 * (2 ** (attempts - 1)))
                continue
            errors.append({"entity_id": entity_id, "error": msg})
            break
        except Exception as e:  # noqa: BLE001 - surface any unexpected failure
            errors.append({"entity_id": entity_id, "error": f"{type(e).__name__}: {e}"})
            break

elapsed = time.monotonic() - start
db.close()

summary = {
    "proc": proc_index,
    "written": written,
    "retries": retries,
    "errors": errors,
    "elapsed_s": round(elapsed, 3),
}
print(json.dumps(summary))
PYEOF

# --- Tests ---

# Parallel entity write test (T0.2).
#
# Spawns NUM_WORKTREES background Python workers. Each worker opens its own
# connection to the SHARED entity DB and writes ENTITIES_PER_PROC entities.
# Asserts total row count equals NUM_WORKTREES * ENTITIES_PER_PROC and
# reports aggregated retry count, per-proc wall-clock, and success rate.
#
# Entity IDs are unique across processes (proc{N}-entity{M}) so that row
# count is a genuine concurrency signal — a collision-driven INSERT OR
# IGNORE would mask write failures.
test_parallel_entity_writes() {
    log_test "parallel: ${NUM_WORKTREES} procs x ${ENTITIES_PER_PROC} writes -> ${TOTAL_EXPECTED} rows"

    local shared_db="${TMPDIR_TEST}/entities.db"

    # Pre-create the DB (also warms up schema migration) so workers race on
    # INSERTs, not on first-open migrations.
    "$PD_PYTHON" - <<PYINIT
import os, sys
sys.path.insert(0, "${PD_PYTHONPATH}")
from entity_registry.database import EntityDatabase
db = EntityDatabase("${shared_db}")
db.close()
PYINIT

    if [[ ! -f "$shared_db" ]]; then
        log_fail "failed to pre-create shared DB at ${shared_db}"
        return
    fi

    # Spawn workers, one per worktree, in parallel. Each worker's stdout
    # (single-line JSON summary) is captured to its own file. `cd` into the
    # worktree first to mirror the real topology where an agent would run
    # from inside a worktree directory but write to the global DB.
    local -a worker_pids=()
    local -a worker_out=()
    local wall_start wall_end wall_elapsed
    wall_start=$(date +%s)

    for i in $(seq 1 "$NUM_WORKTREES"); do
        local wt="${WORKTREE_DIRS[$((i-1))]}"
        local out="${TMPDIR_TEST}/worker-${i}.json"
        worker_out+=("$out")
        (
            cd "$wt"
            PYTHONPATH="$PD_PYTHONPATH" "$PD_PYTHON" "$WORKER_SCRIPT" \
                "$shared_db" "$i" "$ENTITIES_PER_PROC" >"$out" 2>"${out}.err"
        ) &
        worker_pids+=($!)
    done

    # Wait for all workers; record any non-zero exits but don't abort —
    # we want to see full results.
    local failed_procs=0
    for pid in "${worker_pids[@]}"; do
        if ! wait "$pid"; then
            ((failed_procs++)) || true
        fi
    done

    wall_end=$(date +%s)
    wall_elapsed=$((wall_end - wall_start))

    # Aggregate per-proc summaries.
    local total_written=0 total_retries=0 total_errors=0
    for out in "${worker_out[@]}"; do
        if [[ ! -s "$out" ]]; then
            log_info "missing worker output: $out (stderr: $(cat "${out}.err" 2>/dev/null || true))"
            continue
        fi
        local line written retries errs
        line=$(cat "$out")
        written=$("$PD_PYTHON" -c "import json,sys; print(json.loads(sys.argv[1])['written'])" "$line")
        retries=$("$PD_PYTHON" -c "import json,sys; print(json.loads(sys.argv[1])['retries'])" "$line")
        errs=$("$PD_PYTHON" -c "import json,sys; print(len(json.loads(sys.argv[1])['errors']))" "$line")
        total_written=$((total_written + written))
        total_retries=$((total_retries + retries))
        total_errors=$((total_errors + errs))
        log_info "worker output: $line"
    done

    # Authoritative check: query the DB directly for row count.
    local db_count
    db_count=$("$PD_PYTHON" - <<PYCOUNT
import sys
sys.path.insert(0, "${PD_PYTHONPATH}")
from entity_registry.database import EntityDatabase
db = EntityDatabase("${shared_db}")
row = db._conn.execute(
    "SELECT COUNT(*) FROM entities WHERE project_id = ?",
    ("test-078-sqlite-concurrency",),
).fetchone()
print(row[0])
db.close()
PYCOUNT
)

    local success_rate
    if [[ "$TOTAL_EXPECTED" -gt 0 ]]; then
        success_rate=$(awk "BEGIN { printf \"%.1f\", (${db_count} / ${TOTAL_EXPECTED}) * 100 }")
    else
        success_rate="0.0"
    fi

    echo "  metrics: rows_in_db=${db_count} expected=${TOTAL_EXPECTED} retries=${total_retries} " \
         "worker_errors=${total_errors} failed_procs=${failed_procs} wall_clock=${wall_elapsed}s " \
         "success_rate=${success_rate}%"

    if [[ "$db_count" -ne "$TOTAL_EXPECTED" ]]; then
        log_fail "expected ${TOTAL_EXPECTED} rows in DB, got ${db_count} (retries=${total_retries}, errors=${total_errors})"
        return
    fi
    if [[ "$failed_procs" -ne 0 ]]; then
        log_fail "${failed_procs} worker process(es) exited non-zero"
        return
    fi
    if [[ "$total_errors" -ne 0 ]]; then
        log_fail "workers reported ${total_errors} error(s) despite row count match"
        return
    fi

    log_pass
}

# --- Main ---
main() {
    echo "Running test-sqlite-concurrency.sh (T0.2: parallel entity writes)"
    echo "Temp dir:  $TMPDIR_TEST"
    echo "Python:    $PD_PYTHON"
    echo "PYTHONPATH: $PD_PYTHONPATH"
    echo

    setup_repo_and_worktrees
    test_parallel_entity_writes

    echo
    echo "Ran: $TESTS_RUN | Passed: $TESTS_PASSED | Failed: $TESTS_FAILED"

    if [[ "$TESTS_FAILED" -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
