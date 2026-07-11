#!/usr/bin/env bash
# NFR-3 harness (feature 126, design D8, spec 5a): measures the two
# spec-named per-session state reads session-start.sh performs against a
# populated tree — (i) the feature walk (find_active_feature's python3
# snippet) and (ii) the projects glob (build_context's workspace-slug
# lookup) — each as its own process, against a seeded tree under mktemp -d.
# No repo state is mutated; doctor/reconcile are nowhere in this harness.
#
# Extraction is drift-proof: both components are pulled OUT of
# session-start.sh at run time via the BENCH-WALK-START/END and
# BENCH-GLOB-START/END sentinel comments (comment-only edits in that
# file). If session-start.sh drifts (markers removed, load-bearing lines
# missing), this script exits loud with status 3 rather than silently
# measuring something else.
#
# Usage:
#   bash bench-populated-read.sh [--smoke] [--features N]
#
#   --smoke      Cap iterations AND tree scale for a fast end-to-end check
#                (not a real measurement — task 4 runs the full scale).
#   --features N Feature-.meta.json count to seed at the "recorded" scale
#                (default: first-capture `find docs/features -name
#                .meta.json | wc -l` — the parse-cost driver). The 10x
#                scale is always 10 * N. 127 must pass 126's RECORDED N
#                explicitly on every re-run rather than re-deriving it.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

SESSION_START_SH="plugins/pd/hooks/session-start.sh"
SEED=0x126
N_ITERATIONS=120
SMOKE=0
FEATURES_N=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --smoke) SMOKE=1; shift ;;
        --features) FEATURES_N="$2"; shift 2 ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v perl >/dev/null 2>&1 || {
    echo "ERROR: perl required for nanosecond timing (Time::HiRes)" >&2
    exit 2
}

if [[ -z "$FEATURES_N" ]]; then
    FEATURES_N=$(find docs/features -name .meta.json | wc -l | tr -d ' ')
fi

if [[ "$SMOKE" -eq 1 ]]; then
    N_ITERATIONS=3
    FEATURES_N=5
fi

SCALES=("$FEATURES_N" "$((FEATURES_N * 10))")

# ---------------------------------------------------------------------------
# Sentinel extraction (design D8 EXTRACTION MECHANISM) + self-guard.
# ---------------------------------------------------------------------------
extract_sentinel() {
    local start_marker="$1" end_marker="$2"
    # Marker must be the whole line OR be followed by whitespace (annotations
    # like "(feature 126, design D8)" are legitimate). A FUSED suffix (e.g.
    # "# BENCH-WALK-START-DISABLED") must read as a MISSING sentinel — the
    # original substring index() matcher silently accepted it.
    awk -v s="$start_marker" -v e="$end_marker" '
        function is_marker(m,  line) {
            line=$0; sub(/^[[:space:]]+/, "", line)
            return line == m || index(line, m " ") == 1
        }
        is_marker(s) { found=1; next }
        is_marker(e) { found=0 }
        found { print }
    ' "$SESSION_START_SH"
}

walk_block=$(extract_sentinel "# BENCH-WALK-START" "# BENCH-WALK-END")
glob_block=$(extract_sentinel "# BENCH-GLOB-START" "# BENCH-GLOB-END")

if [[ -z "$walk_block" ]] || [[ "$walk_block" != *"os.walk"* ]] || [[ "$walk_block" != *"json.load"* ]]; then
    echo "ERROR: BENCH-WALK sentinel extraction from ${SESSION_START_SH} is empty" \
         "or missing a load-bearing line (os.walk / json.load) — session-start.sh" \
         "has drifted from this harness's expectations." >&2
    exit 3
fi

if [[ -z "$glob_block" ]] || [[ "$glob_block" != *"glob.glob"* ]] || [[ "$glob_block" != *"json.load"* ]]; then
    echo "ERROR: BENCH-GLOB sentinel extraction from ${SESSION_START_SH} is empty" \
         "or missing a load-bearing line (glob.glob / json.load) — session-start.sh" \
         "has drifted from this harness's expectations." >&2
    exit 3
fi

# ---------------------------------------------------------------------------
# Seeded tree builder (random.Random(0x126)) — one .meta.json per feature
# dir (seeded N == parsed N) plus a projects/ tree for the glob component.
# ---------------------------------------------------------------------------
build_seeded_tree() {
    local target_dir="$1" scale_n="$2"
    python3 - "$target_dir" "$scale_n" <<'PY'
import json
import os
import random
import sys

target_dir, scale_n = sys.argv[1], int(sys.argv[2])
rng = random.Random(0x126)

features_dir = os.path.join(target_dir, "docs", "features")
projects_dir = os.path.join(target_dir, "docs", "projects")
os.makedirs(features_dir, exist_ok=True)
os.makedirs(projects_dir, exist_ok=True)

PHASES = ["brainstorm", "spec", "design", "plan", "implement", "finish"]


def realistic_meta(slug, workspace_uuid=None):
    phase_count = rng.randint(1, len(PHASES))
    phases = {}
    for phase in PHASES[:phase_count]:
        phases[phase] = {
            "started": "2026-01-01T00:00:00Z",
            "completed": "2026-01-01T01:00:00Z",
            "iterations": rng.randint(1, 3),
            "reviewerNotes": "x" * rng.randint(80, 400),
        }
    meta = {
        "id": slug.split("-")[0],
        "slug": slug,
        "mode": rng.choice(["standard", "full"]),
        "status": "active",
        "created": "2026-01-01T00:00:00Z",
        "branch": f"feature/{slug}",
        "phases": phases,
        "lastCompletedPhase": PHASES[phase_count - 1],
    }
    if workspace_uuid is not None:
        meta["workspace_uuid"] = workspace_uuid
    return meta


for i in range(scale_n):
    slug = f"{i:04d}-seeded-feature-{rng.randint(1000, 9999)}"
    feature_dir = os.path.join(features_dir, slug)
    os.makedirs(feature_dir, exist_ok=True)
    with open(os.path.join(feature_dir, ".meta.json"), "w") as fh:
        json.dump(realistic_meta(slug), fh)

for i in range(scale_n):
    slug = f"seeded-project-{i:04d}"
    project_dir = os.path.join(projects_dir, slug)
    os.makedirs(project_dir, exist_ok=True)
    # Never equal to the harness's NO-MATCH sentinel — forces the glob
    # snippet's for/else full scan every iteration (design D8: worst case).
    workspace_uuid = f"seeded-ws-{rng.randint(100000, 999999)}-{i:04d}"
    with open(os.path.join(project_dir, ".meta.json"), "w") as fh:
        json.dump(realistic_meta(slug, workspace_uuid=workspace_uuid), fh)
PY
}

# ---------------------------------------------------------------------------
# Per-iteration timers (perl Time::HiRes — mirrors bench-session-start.sh
# house style; macOS `date` lacks nanosecond precision).
# ---------------------------------------------------------------------------
_now_ns() {
    perl -MTime::HiRes -e 'printf "%d", Time::HiRes::time()*1e9'
}

measure_walk_once() {
    local features_dir="$1"
    local start_ns end_ns latest_meta
    start_ns=$(_now_ns)
    eval "$walk_block"
    end_ns=$(_now_ns)
    echo $(( (end_ns - start_ns) / 1000000 ))
}

measure_glob_once() {
    local PROJECT_ROOT="$1" artifacts_root_val="$2" feature_workspace_uuid="$3"
    local start_ns end_ns project_slug
    start_ns=$(_now_ns)
    eval "$glob_block"
    end_ns=$(_now_ns)
    echo $(( (end_ns - start_ns) / 1000000 ))
}

# ---------------------------------------------------------------------------
# p50/p95 + full sorted distribution (order-stat index = ceil(p/100 * n)).
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

echo "bench-populated-read.sh: seed=${SEED} features_n=${FEATURES_N} iterations=${N_ITERATIONS} smoke=${SMOKE}"

tree_dir=""
trap 'rm -rf "${tree_dir:-}"' EXIT

for scale in "${SCALES[@]}"; do
    tree_dir=$(mktemp -d)
    build_seeded_tree "$tree_dir" "$scale"

    walk_timings=()
    for ((i = 0; i < N_ITERATIONS; i++)); do
        walk_timings+=("$(measure_walk_once "${tree_dir}/docs/features")")
    done
    print_stats "walk (find_active_feature)" "$scale" "${walk_timings[@]}"

    glob_timings=()
    for ((i = 0; i < N_ITERATIONS; i++)); do
        glob_timings+=("$(measure_glob_once "$tree_dir" "docs" "NO-MATCH-SENTINEL-${scale}")")
    done
    print_stats "glob (build_context workspace lookup, NO-MATCH)" "$scale" "${glob_timings[@]}"

    rm -rf "$tree_dir"
done

echo "PASS: bench-populated-read.sh completed"
exit 0
