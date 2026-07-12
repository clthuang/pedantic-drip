#!/usr/bin/env bash
# NFR-3 DB-direct read-latency harness (feature 127, design D5, spec
# FR127-4): measures the DB-direct SQLite equivalents of
# bench-populated-read.sh's file-based walk/glob components, against
# seeded v2 entity-registry databases built by the UNTOUCHED
# scripts/seed-census-db.py.
#
# Two postures, each measured at three census scales (--entities 22 / 220
# / 533, --workspaces 7, seed 0x126 — pinned by design D5):
#
#   - walk-equivalent  — "find active feature + its phase" (what 132's
#     session-start would run), two statements per sample against the
#     dark entity_axis_state view: (1) entities JOIN entity_axis_state ON
#     axis='execution', filtered to a real seeded workspace_uuid — the
#     seed emits NO execution-axis events, so this is a GUARANTEED
#     no-match by construction, worst-case full GROUP-BY scan cost, not a
#     correctness-faithful "find the active feature" resolver; (2) a
#     fixed real seeded entity uuid's pipeline-axis state (statement 1
#     never returns a uuid to chain into statement 2, so the fixed probe
#     uuid is always what statement 2 queries).
#   - workspace-lookup — the glob-equivalent: workspaces.project_root
#     lookup in the same NO-MATCH posture as the baseline's glob
#     component.
#
# Each seeded DB gets a ONE-TIME view-materialization step
# (entity_registry.views + schema_v2.bootstrap_v2 — entity_registry.axes
# is deliberately NOT imported, design D5) before any sample runs;
# CREATE VIEW IF NOT EXISTS persists in sqlite_master, so the per-sample
# spawns below query it directly via plain sqlite3.connect (no
# entity_registry import, no per-sample DDL).
#
# Process basis (spec FR127-4, apples-to-apples with the baseline): each
# OWN-PROCESS sample is one spawn of `plugins/pd/.venv/bin/python -c
# "<connect, query, close>"`, timed from bash (perl Time::HiRes,
# mirroring bench-populated-read.sh's _now_ns) so python startup is
# INCLUDED in every sample, same as the baseline. A second, IN-PROCESS
# amortized measurement (one process, one connection, N_ITERATIONS
# queries in a loop, timed internally in microseconds) is reported
# FYI-only — it informs 132's long-lived-server case but carries no
# verdict.
#
# EXPLAIN QUERY PLAN is captured once per census for both walk-equivalent
# statements (feeds backlog #067's 132 mandate).
#
# No repo state is mutated: seeding writes into mktemp -d directories
# only; scripts/seed-census-db.py is read-only from this script's
# perspective.
#
# Usage:
#   bash bench-db-direct-read.sh [--smoke]
#
#   --smoke   Cap iterations AND census scales for a fast end-to-end check
#             (not a real measurement — task 4's artifact runs the full
#             scale).

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

PY="plugins/pd/.venv/bin/python"
SEED_SCRIPT="scripts/seed-census-db.py"

# 0x126 is the seed pinned by 126/127 design (populated-latency-baseline.md,
# design D5) across every artifact that cites "seed 0x126". argparse's
# `type=int` cannot parse a "0x"-prefixed STRING via plain int(), so the
# value actually passed to seed-census-db.py's --seed is the bash-arithmetic
# decimal expansion of the SAME literal (0x126 == 294) — not a re-derived or
# approximated number.
SEED_HEX="0x126"
SEED_DECIMAL=$((SEED_HEX))
WORKSPACES=7
N_ITERATIONS=120
SMOKE=0
# N=22 (like-for-like vs the 126 file baseline, BINDING verdicts), N=220
# (trend vs the baseline's 220 figures), N=533 (the seeder's own default —
# realistic-population FYI, mirrors 126's component 5b). Workspace count
# stays 7 across all three (design D5).
SCALES=(22 220 533)

while [[ $# -gt 0 ]]; do
    case "$1" in
        --smoke) SMOKE=1; shift ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v perl >/dev/null 2>&1 || {
    echo "ERROR: perl required for nanosecond timing (Time::HiRes)" >&2
    exit 2
}
[[ -x "$PY" ]] || {
    echo "ERROR: $PY not found or not executable (plugins/pd/.venv missing?)" >&2
    exit 2
}

if [[ "$SMOKE" -eq 1 ]]; then
    N_ITERATIONS=3
    SCALES=(5 10)
fi

# ---------------------------------------------------------------------------
# Per-iteration timers (perl Time::HiRes — mirrors bench-populated-read.sh's
# house style; macOS `date` lacks nanosecond precision).
# ---------------------------------------------------------------------------
_now_ns() {
    perl -MTime::HiRes -e 'printf "%d", Time::HiRes::time()*1e9'
}

# ---------------------------------------------------------------------------
# Python source blocks (built once, reused across every spawn/census).
# Dynamic values cross the bash/python boundary via sys.argv — never via
# string interpolation into the source text — so uuids/paths need no shell
# escaping.
# ---------------------------------------------------------------------------

# One-time per-census setup: bootstrap the seeded DB's dark views (design D5
# view-materialization step) and capture a real seeded workspace uuid + a
# real seeded entity uuid to use as query parameters (both statements need a
# LIVE uuid from this specific census, not a literal, so the query plan
# reflects a plausible real lookup rather than an empty-workspace shortcut).
_SETUP_PY=$(cat <<'PYEOF'
import sys

sys.path.insert(0, "plugins/pd/hooks/lib")
import entity_registry.views  # noqa: F401 -- registers "views" DDL (entity_registry.axes NOT imported, design D5)
from entity_registry.schema_v2 import bootstrap_v2

db_path = sys.argv[1]
conn = bootstrap_v2(db_path)
ws_uuid = conn.execute("SELECT uuid FROM workspaces ORDER BY uuid LIMIT 1").fetchone()[0]
entity_uuid = conn.execute("SELECT uuid FROM entities ORDER BY uuid LIMIT 1").fetchone()[0]
conn.close()
print(f"{ws_uuid} {entity_uuid}")
PYEOF
)

# EXPLAIN QUERY PLAN for both walk-equivalent statements, captured once per
# census (not timed) against the real probe uuids.
_EXPLAIN_PY=$(cat <<'PYEOF'
import sqlite3
import sys

db_path, ws_uuid, probe_uuid, scale = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
conn = sqlite3.connect(db_path)
print(f"=== EXPLAIN QUERY PLAN: walk-equivalent statement 1 @ N={scale} ===")
for row in conn.execute(
    "EXPLAIN QUERY PLAN SELECT e.uuid FROM entities e JOIN entity_axis_state s ON s.entity_uuid = e.uuid AND s.axis = 'execution' WHERE e.workspace_uuid = ? AND e.type = 'feature' AND s.to_value = 'active'",
    (ws_uuid,),
):
    print(row)
print(f"=== EXPLAIN QUERY PLAN: walk-equivalent statement 2 @ N={scale} ===")
for row in conn.execute(
    "EXPLAIN QUERY PLAN SELECT to_value FROM entity_axis_state WHERE entity_uuid = ? AND axis = 'pipeline'",
    (probe_uuid,),
):
    print(row)
conn.close()
PYEOF
)

# walk-equivalent, ONE own-process sample: statement 1 (guaranteed
# no-match), then statement 2 against the fixed probe uuid, then close.
_WALK_EQUIV_PY=$(cat <<'PYEOF'
import sqlite3
import sys

db_path, ws_uuid, probe_uuid = sys.argv[1], sys.argv[2], sys.argv[3]
conn = sqlite3.connect(db_path)
conn.execute(
    "SELECT e.uuid FROM entities e JOIN entity_axis_state s ON s.entity_uuid = e.uuid AND s.axis = 'execution' WHERE e.workspace_uuid = ? AND e.type = 'feature' AND s.to_value = 'active'",
    (ws_uuid,),
).fetchall()
conn.execute(
    "SELECT to_value FROM entity_axis_state WHERE entity_uuid = ? AND axis = 'pipeline'",
    (probe_uuid,),
).fetchall()
conn.close()
PYEOF
)

# workspace-lookup, ONE own-process sample: glob-equivalent NO-MATCH.
_WORKSPACE_LOOKUP_PY=$(cat <<'PYEOF'
import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
conn.execute(
    "SELECT uuid FROM workspaces WHERE project_root = ?",
    ("/nonexistent/no-match",),
).fetchall()
conn.close()
PYEOF
)

# walk-equivalent, IN-PROCESS amortized loop (FYI-only): one connection,
# N_ITERATIONS timed iterations, microsecond resolution (own-process
# spawn overhead dominates the binding measurement — amortized queries are
# sub-millisecond, so ms-rounding here would degenerate to all-zero).
_WALK_EQUIV_AMORTIZED_PY=$(cat <<'PYEOF'
import sqlite3
import sys
import time

db_path, ws_uuid, probe_uuid, n_iterations = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
conn = sqlite3.connect(db_path)
timings_us = []
for _ in range(n_iterations):
    start_ns = time.perf_counter_ns()
    conn.execute(
        "SELECT e.uuid FROM entities e JOIN entity_axis_state s ON s.entity_uuid = e.uuid AND s.axis = 'execution' WHERE e.workspace_uuid = ? AND e.type = 'feature' AND s.to_value = 'active'",
        (ws_uuid,),
    ).fetchall()
    conn.execute(
        "SELECT to_value FROM entity_axis_state WHERE entity_uuid = ? AND axis = 'pipeline'",
        (probe_uuid,),
    ).fetchall()
    end_ns = time.perf_counter_ns()
    timings_us.append((end_ns - start_ns) // 1000)
conn.close()
print(" ".join(str(t) for t in timings_us))
PYEOF
)

# workspace-lookup, IN-PROCESS amortized loop (FYI-only).
_WORKSPACE_LOOKUP_AMORTIZED_PY=$(cat <<'PYEOF'
import sqlite3
import sys
import time

db_path, n_iterations = sys.argv[1], int(sys.argv[2])
conn = sqlite3.connect(db_path)
timings_us = []
for _ in range(n_iterations):
    start_ns = time.perf_counter_ns()
    conn.execute(
        "SELECT uuid FROM workspaces WHERE project_root = ?",
        ("/nonexistent/no-match",),
    ).fetchall()
    end_ns = time.perf_counter_ns()
    timings_us.append((end_ns - start_ns) // 1000)
conn.close()
print(" ".join(str(t) for t in timings_us))
PYEOF
)

measure_walk_equiv_once() {
    local db_path="$1" ws_uuid="$2" probe_uuid="$3"
    local start_ns end_ns
    start_ns=$(_now_ns)
    "$PY" -c "$_WALK_EQUIV_PY" "$db_path" "$ws_uuid" "$probe_uuid"
    end_ns=$(_now_ns)
    echo $(( (end_ns - start_ns) / 1000000 ))
}

measure_workspace_lookup_once() {
    local db_path="$1"
    local start_ns end_ns
    start_ns=$(_now_ns)
    "$PY" -c "$_WORKSPACE_LOOKUP_PY" "$db_path"
    end_ns=$(_now_ns)
    echo $(( (end_ns - start_ns) / 1000000 ))
}

# ---------------------------------------------------------------------------
# p50/p95 + full sorted distribution (order-stat index = ceil(p/100 * n)) —
# same formula as bench-populated-read.sh's print_stats.
# ---------------------------------------------------------------------------
print_stats() {
    local component="$1" scale="$2"
    shift 2
    local sorted=()
    while IFS= read -r value; do sorted+=("$value"); done < <(printf '%s\n' "$@" | sort -n)
    local n=${#sorted[@]}
    local p50_idx=$(( (50 * n + 99) / 100 ))
    local p95_idx=$(( (95 * n + 99) / 100 ))
    (( p50_idx < 1 )) && p50_idx=1
    (( p95_idx < 1 )) && p95_idx=1
    (( p50_idx > n )) && p50_idx=n
    (( p95_idx > n )) && p95_idx=n
    echo "=== ${component} @ N=${scale} (n=${n} iterations) ==="
    echo "p50: ${sorted[$((p50_idx - 1))]} ms"
    echo "p95: ${sorted[$((p95_idx - 1))]} ms"
    echo "distribution (sorted ms): ${sorted[*]}"
}

# Same order-stat formula, microsecond unit, labeled FYI-only — for the
# in-process amortized loops.
print_stats_us() {
    local component="$1" scale="$2"
    shift 2
    local sorted=()
    while IFS= read -r value; do sorted+=("$value"); done < <(printf '%s\n' "$@" | sort -n)
    local n=${#sorted[@]}
    local p50_idx=$(( (50 * n + 99) / 100 ))
    local p95_idx=$(( (95 * n + 99) / 100 ))
    (( p50_idx < 1 )) && p50_idx=1
    (( p95_idx < 1 )) && p95_idx=1
    (( p50_idx > n )) && p50_idx=n
    (( p95_idx > n )) && p95_idx=n
    echo "=== ${component} @ N=${scale} (n=${n} iterations, in-process amortized, FYI-only) ==="
    echo "p50: ${sorted[$((p50_idx - 1))]} us"
    echo "p95: ${sorted[$((p95_idx - 1))]} us"
    echo "distribution (sorted us): ${sorted[*]}"
}

echo "bench-db-direct-read.sh: seed=${SEED_HEX} workspaces=${WORKSPACES} scales=${SCALES[*]} iterations=${N_ITERATIONS} smoke=${SMOKE}"

census_dir=""
trap 'rm -rf "${census_dir:-}"' EXIT

for scale in "${SCALES[@]}"; do
    census_dir=$(mktemp -d)

    seed_output=$("$PY" "$SEED_SCRIPT" \
        --target-dir "$census_dir" \
        --entities "$scale" \
        --workspaces "$WORKSPACES" \
        --seed "$SEED_DECIMAL")
    echo "seed: ${seed_output}"

    db_path="${census_dir}/v2.db"

    setup_output=$("$PY" -c "$_SETUP_PY" "$db_path")
    read -r ws_uuid probe_uuid <<< "$setup_output"

    "$PY" -c "$_EXPLAIN_PY" "$db_path" "$ws_uuid" "$probe_uuid" "$scale"

    walk_timings=()
    for ((i = 0; i < N_ITERATIONS; i++)); do
        walk_timings+=("$(measure_walk_equiv_once "$db_path" "$ws_uuid" "$probe_uuid")")
    done
    print_stats "walk-equivalent (DB-direct, NO-MATCH by construction)" "$scale" "${walk_timings[@]}"

    lookup_timings=()
    for ((i = 0; i < N_ITERATIONS; i++)); do
        lookup_timings+=("$(measure_workspace_lookup_once "$db_path")")
    done
    print_stats "workspace-lookup (DB-direct, NO-MATCH)" "$scale" "${lookup_timings[@]}"

    walk_amortized=$("$PY" -c "$_WALK_EQUIV_AMORTIZED_PY" "$db_path" "$ws_uuid" "$probe_uuid" "$N_ITERATIONS")
    print_stats_us "walk-equivalent (DB-direct, NO-MATCH by construction)" "$scale" $walk_amortized

    lookup_amortized=$("$PY" -c "$_WORKSPACE_LOOKUP_AMORTIZED_PY" "$db_path" "$N_ITERATIONS")
    print_stats_us "workspace-lookup (DB-direct, NO-MATCH)" "$scale" $lookup_amortized

    rm -rf "$census_dir"
done

echo "PASS: bench-db-direct-read.sh completed"
exit 0
