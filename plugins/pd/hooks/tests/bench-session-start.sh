#!/usr/bin/env bash
# NFR2 benchmark for feature 107 (per design TD7 + C7).
# Compares median wall-clock time of session-start.sh on this branch vs
# its merge-base against develop. Asserts patched_median - baseline_median <= 50 ms.
#
# Pre-flight: requires clean working tree (no uncommitted changes) so
# `git worktree add` is safe. Uses `.pd-worktrees/bench-<sha>/` per
# CLAUDE.md convention.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Pre-flight check
if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: working tree dirty; commit or stash before running benchmark." >&2
    exit 2
fi

baseline_sha=$(git merge-base HEAD develop)
worktree_dir=".pd-worktrees/bench-${baseline_sha:0:8}"

# Cleanup if a previous run left state behind
if [[ -d "$worktree_dir" ]]; then
    git worktree remove --force "$worktree_dir" 2>/dev/null || rm -rf "$worktree_dir"
fi

trap 'git worktree remove --force "$worktree_dir" 2>/dev/null || true' EXIT

git worktree add "$worktree_dir" "$baseline_sha" >/dev/null

# measure_median <hook_path>
# 11 timed runs; drop fastest+slowest; median of 9 in milliseconds.
# Runs each invocation under HOME=$(mktemp -d) to isolate from workspace
# state (otherwise build_context's output differs based on active feature
# / pd state, which conflates state-driven workload with hook code changes).
measure_median() {
    local hook="$1"
    local times=()
    for _ in $(seq 1 11); do
        local fresh_home; fresh_home=$(mktemp -d)
        local start_ns end_ns
        start_ns=$(perl -MTime::HiRes -e 'printf "%d", Time::HiRes::time()*1e9' 2>/dev/null)
        HOME="$fresh_home" bash "$hook" </dev/null >/dev/null 2>&1 || true
        end_ns=$(perl -MTime::HiRes -e 'printf "%d", Time::HiRes::time()*1e9' 2>/dev/null)
        rm -rf "$fresh_home"
        local elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))
        times+=("$elapsed_ms")
    done
    # sort ascending, drop first and last, take middle of 9 (index 4 zero-based)
    printf '%s\n' "${times[@]}" | sort -n | sed '1d;$d' | awk 'NR==5'
}

baseline_ms=$(measure_median "$worktree_dir/plugins/pd/hooks/session-start.sh")
patched_ms=$(measure_median "plugins/pd/hooks/session-start.sh")

git worktree remove --force "$worktree_dir"

delta=$(( patched_ms - baseline_ms ))

cat > plugins/pd/hooks/tests/bench-results.txt <<RESULTS
# Generated at PR open; re-run locally to re-verify but do not re-commit.
baseline_sha=$baseline_sha
baseline_median_ms=$baseline_ms
patched_median_ms=$patched_ms
delta_ms=$delta
threshold_ms=50
RESULTS

echo "baseline median: ${baseline_ms} ms"
echo "patched  median: ${patched_ms} ms"
echo "delta:           ${delta} ms (threshold +50)"

if (( delta > 50 )); then
    echo "FAIL: NFR2 delta exceeded 50 ms" >&2
    exit 1
fi

echo "PASS: NFR2 within budget"
exit 0
