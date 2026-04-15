#!/usr/bin/env bash
# test-worktree-dispatch.sh — Pins down raw git worktree primitives used by parallel dispatch.
#
# Scenarios:
#   1. Worktree creation + cleanup roundtrip
#   2. Sequential merge of 2 worktree branches (both changes land on main)
#   3. SHA-based stray-commit detection (TD-2 post-agent validation)
#   4. Fallback on worktree add failure (collision / invalid branch)
#
# Usage: bash plugins/pd/hooks/tests/test-worktree-dispatch.sh

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

# Plugin venv Python: used for any JSON / structured assertions (mirrors
# test-sqlite-concurrency.sh + test-workflow-regression.sh). Git mechanics
# are driven by the git CLI directly; Python is here only for precise
# assertions on structured data if a test needs it.
PLUGIN_VENV_PYTHON="${PLUGIN_ROOT}/.venv/bin/python"
if [[ -x "$PLUGIN_VENV_PYTHON" ]]; then
    PD_PYTHON="$PLUGIN_VENV_PYTHON"
else
    PD_PYTHON="$(command -v python3)"
fi

# --- Setup ---
# TMPDIR_TEST:    scratch root for the whole test run.
# REPO_DIR:       temp repo under TMPDIR_TEST — never reuse the project repo,
#                 every test must be hermetic (see `CLAUDE.md`: no polluting
#                 real state, use temp repos).
# WORKTREES_ROOT: where .pd-worktrees/ would live in a real project; we keep
#                 a parallel tree here so tests match the production layout.
# WORKTREE_DIRS:  tracked for cleanup; `trap cleanup` removes them forcefully.
TMPDIR_TEST=$(mktemp -d -t pd-worktree-dispatch-XXXXXX)
# Resolve symlinks up-front. On macOS, `mktemp -d` returns a path under
# /var/folders/..., but git internally resolves that to /private/var/folders/
# when it records worktree paths. If we don't normalize, `git worktree list`
# output won't match our un-resolved REPO_DIR and path-based assertions fail.
if command -v realpath >/dev/null 2>&1; then
    TMPDIR_TEST=$(realpath "$TMPDIR_TEST")
else
    TMPDIR_TEST=$(cd "$TMPDIR_TEST" && pwd -P)
fi
REPO_DIR="${TMPDIR_TEST}/repo"
WORKTREES_ROOT="${REPO_DIR}/.pd-worktrees"
WORKTREE_DIRS=()

cleanup() {
    local exit_code=$?
    # Best-effort teardown: force-remove any worktrees git still knows about,
    # prune dangling entries, then nuke the temp dir. Cleanup must never
    # fail the script (trap on EXIT INT TERM HUP).
    if [[ -d "$REPO_DIR/.git" ]]; then
        # Use `git worktree list --porcelain` to discover EVERY worktree the
        # repo thinks it owns — including ones a test added but didn't push
        # into WORKTREE_DIRS (e.g., an add that succeeded unexpectedly).
        while IFS= read -r wt_path; do
            [[ -z "$wt_path" ]] && continue
            # Skip the main worktree (git worktree list includes it first).
            [[ "$wt_path" == "$REPO_DIR" ]] && continue
            git -C "$REPO_DIR" worktree remove --force "$wt_path" >/dev/null 2>&1 || true
        done < <(git -C "$REPO_DIR" worktree list --porcelain 2>/dev/null | awk '/^worktree / { print $2 }')
        git -C "$REPO_DIR" worktree prune >/dev/null 2>&1 || true
    fi
    rm -rf "$TMPDIR_TEST" 2>/dev/null || true
    exit "$exit_code"
}
# Cleans up on normal exit AND on interrupt (Ctrl-C, SIGTERM, etc.).
trap cleanup EXIT INT TERM HUP

# --- Shared repo setup ---
#
# Initialize a fresh temp repo with a single commit on `main`. Each test
# resets the repo state (checks out main, removes any extra worktrees) so
# scenarios don't bleed into each other. Using `--initial-branch=main` is
# deliberate — the feature 078 design uses `main` as the base branch for
# worktree creation; tests should mirror that convention.
setup_repo() {
    log_info "Setting up temp repo at: $REPO_DIR"
    mkdir -p "$REPO_DIR"
    git -C "$REPO_DIR" init --quiet --initial-branch=main
    git -C "$REPO_DIR" config user.email "worktree-test@pd.test"
    git -C "$REPO_DIR" config user.name "pd worktree test"
    git -C "$REPO_DIR" config commit.gpgsign false

    # Seed commit so `git worktree add -b` has a HEAD to branch off. Content
    # deliberately trivial — tests care about commit topology, not content.
    echo "# worktree dispatch test repo" > "$REPO_DIR/README.md"
    git -C "$REPO_DIR" add README.md
    git -C "$REPO_DIR" commit --quiet -m "initial commit"

    mkdir -p "$WORKTREES_ROOT"
}

# Per-test reset: return the repo to a clean `main` with no extra worktrees.
# Called at the top of every test to guarantee hermetic state. Skipped if
# setup_repo hasn't run yet (defensive — main() orders things correctly).
reset_repo_state() {
    [[ -d "$REPO_DIR/.git" ]] || return 0

    # Force-checkout main (any dangling branch work from a prior test).
    git -C "$REPO_DIR" checkout --quiet --force main 2>/dev/null || true

    # Remove every non-main worktree git knows about.
    while IFS= read -r wt_path; do
        [[ -z "$wt_path" ]] && continue
        [[ "$wt_path" == "$REPO_DIR" ]] && continue
        git -C "$REPO_DIR" worktree remove --force "$wt_path" >/dev/null 2>&1 || true
    done < <(git -C "$REPO_DIR" worktree list --porcelain 2>/dev/null | awk '/^worktree / { print $2 }')
    git -C "$REPO_DIR" worktree prune >/dev/null 2>&1 || true

    # Delete any leftover branches from previous tests (start-of-test isolation).
    while IFS= read -r br; do
        br="${br## }"; br="${br#\* }"
        [[ -z "$br" || "$br" == "main" ]] && continue
        git -C "$REPO_DIR" branch -D "$br" >/dev/null 2>&1 || true
    done < <(git -C "$REPO_DIR" branch --list | sed 's/^[* ]*//')

    # Clear WORKTREE_DIRS tracking for the next test.
    WORKTREE_DIRS=()

    # Also remove any leftover dirs under .pd-worktrees/ that git already
    # forgot (e.g., from a failed `worktree add` that left the path intact).
    rm -rf "${WORKTREES_ROOT:?}"/* 2>/dev/null || true
}

# --- Tests ---

# Test 1: Worktree creation + cleanup roundtrip.
#
# Exercises the simplest primitive the dispatch relies on:
#   git worktree add  →  git worktree remove
# After removal, asserts NO trace remains:
#   - Worktree directory is gone from the filesystem.
#   - `git worktree list` no longer reports the worktree.
#   - The underlying branch may still exist (remove doesn't delete branches),
#     which is fine — branch cleanup is a separate concern handled post-merge.
#
# This pins the contract the design's Phase 1 (create) and Phase 3 (cleanup)
# rely on: a successful add is fully reversible by a successful remove.
test_worktree_roundtrip() {
    log_test "worktree roundtrip: add + remove leaves no trace"
    reset_repo_state

    local wt="${WORKTREES_ROOT}/task-1"
    local branch="worktree-roundtrip-task-1"

    if ! git -C "$REPO_DIR" worktree add --quiet -b "$branch" "$wt" >/dev/null 2>&1; then
        log_fail "git worktree add failed for $wt"
        return
    fi
    WORKTREE_DIRS+=("$wt")

    # Post-add invariants: directory exists, git lists the worktree.
    if [[ ! -d "$wt" ]]; then
        log_fail "worktree directory not created: $wt"
        return
    fi
    if ! git -C "$REPO_DIR" worktree list --porcelain | grep -q "^worktree ${wt}$"; then
        log_fail "git worktree list does not report: $wt"
        return
    fi

    # Remove the worktree. This is the happy-path cleanup invoked by
    # dispatch Phase 3 after a successful merge. Note: `git worktree remove`
    # does NOT accept `--quiet` (git 2.50 on macOS); suppress output via
    # stdout/stderr redirection instead.
    if ! git -C "$REPO_DIR" worktree remove "$wt" >/dev/null 2>&1; then
        log_fail "git worktree remove failed for $wt"
        return
    fi

    # Post-remove invariants: directory is gone, list no longer reports it.
    if [[ -d "$wt" ]]; then
        log_fail "worktree directory still exists after remove: $wt"
        return
    fi
    if git -C "$REPO_DIR" worktree list --porcelain | grep -q "^worktree ${wt}$"; then
        log_fail "git worktree list still reports removed worktree: $wt"
        return
    fi

    log_pass
}

# Test 2: Sequential merge of 2 worktree branches.
#
# Models the Phase 3 merge sequence from design.md (TD-1): after two agents
# complete in parallel worktrees, the orchestrator returns to the feature
# branch and merges each worktree branch in task-document order. Final state
# must contain BOTH changes.
#
# Each worktree edits a DIFFERENT file to avoid merge conflicts — conflict
# handling is a separate concern (design.md TD-1: "halt and surface"). This
# test covers the happy-path merge order guarantee.
test_sequential_merge() {
    log_test "sequential merge: 2 worktrees, both edits land on main"
    reset_repo_state

    local wt1="${WORKTREES_ROOT}/task-1"
    local wt2="${WORKTREES_ROOT}/task-2"
    local branch1="worktree-seqmerge-task-1"
    local branch2="worktree-seqmerge-task-2"

    # Create both worktrees (Phase 1 of dispatch).
    git -C "$REPO_DIR" worktree add --quiet -b "$branch1" "$wt1" >/dev/null
    git -C "$REPO_DIR" worktree add --quiet -b "$branch2" "$wt2" >/dev/null
    WORKTREE_DIRS+=("$wt1" "$wt2")

    # Phase 2 (simulated): each "agent" commits its own file in its worktree.
    echo "content from task 1" > "$wt1/task-1.txt"
    git -C "$wt1" add task-1.txt
    git -C "$wt1" commit --quiet -m "task 1: add task-1.txt"

    echo "content from task 2" > "$wt2/task-2.txt"
    git -C "$wt2" add task-2.txt
    git -C "$wt2" commit --quiet -m "task 2: add task-2.txt"

    # Phase 3: switch to main and merge in task-document order.
    git -C "$REPO_DIR" checkout --quiet main
    if ! git -C "$REPO_DIR" merge --quiet --no-ff "$branch1" -m "merge task 1" >/dev/null; then
        log_fail "merge of $branch1 failed"
        return
    fi
    if ! git -C "$REPO_DIR" merge --quiet --no-ff "$branch2" -m "merge task 2" >/dev/null; then
        log_fail "merge of $branch2 failed"
        return
    fi

    # Final state: both files must exist on main with expected content.
    if [[ ! -f "$REPO_DIR/task-1.txt" ]]; then
        log_fail "task-1.txt missing on main after merge"
        return
    fi
    if [[ ! -f "$REPO_DIR/task-2.txt" ]]; then
        log_fail "task-2.txt missing on main after merge"
        return
    fi
    if [[ "$(cat "$REPO_DIR/task-1.txt")" != "content from task 1" ]]; then
        log_fail "task-1.txt content wrong: $(cat "$REPO_DIR/task-1.txt")"
        return
    fi
    if [[ "$(cat "$REPO_DIR/task-2.txt")" != "content from task 2" ]]; then
        log_fail "task-2.txt content wrong: $(cat "$REPO_DIR/task-2.txt")"
        return
    fi

    # Cleanup — dispatch Phase 3 removes worktrees after successful merge.
    # `git worktree remove` does not accept `--quiet`; redirect to suppress.
    git -C "$REPO_DIR" worktree remove "$wt1" >/dev/null 2>&1
    git -C "$REPO_DIR" worktree remove "$wt2" >/dev/null 2>&1

    log_pass
}

# Test 3: SHA-based stray-commit detection.
#
# Implements the TD-2 post-agent validation: a misbehaved agent could ignore
# the "work only in worktree" directive and commit directly to the feature
# branch. The dispatch detects this by comparing HEAD before dispatch with
# HEAD after — any delta is a stray commit.
#
# Test narrative:
#   1. Record BEFORE SHA on main.
#   2. Simulate a stray commit on main (the "misbehaved agent").
#   3. Record AFTER SHA.
#   4. Assert BEFORE != AFTER (detection fires).
#   5. Also assert the git log between them lists exactly the stray commit,
#      matching the design's "Unexpected commits" surfacing.
#
# Negative check: reset to BEFORE, re-read HEAD, assert equal — confirms the
# detection is symmetric and doesn't false-positive on a clean run.
test_stray_commit_detection() {
    log_test "stray-commit detection: BEFORE/AFTER SHA mismatch flags misbehaved agent"
    reset_repo_state

    # Step 1: record BEFORE. This is what dispatch records in Phase 1 before
    # firing off parallel agents.
    local before
    before=$(git -C "$REPO_DIR" rev-parse HEAD)

    # Step 2: simulate a misbehaved agent committing to the main/feature
    # branch directly (bypassing the worktree). A real agent running with
    # the worktree directive should NEVER do this; the detection exists
    # because we cannot fully trust the agent to honor prose instructions.
    echo "stray content" > "$REPO_DIR/stray.txt"
    git -C "$REPO_DIR" add stray.txt
    git -C "$REPO_DIR" commit --quiet -m "STRAY: agent wrote outside worktree"

    # Step 3: record AFTER. Dispatch reads this in Phase 3 pre-merge validation.
    local after
    after=$(git -C "$REPO_DIR" rev-parse HEAD)

    # Step 4: primary assertion — detection MUST fire.
    if [[ "$before" == "$after" ]]; then
        log_fail "BEFORE/AFTER SHAs are equal ($before); stray commit undetected"
        return
    fi

    # Step 5: the diff range must name exactly the stray commit. This matches
    # the design snippet: `git log --oneline ${MAIN_SHA}..HEAD`. We assert
    # one commit and its subject contains the "STRAY:" marker we used.
    local stray_commits
    stray_commits=$(git -C "$REPO_DIR" log --oneline "${before}..${after}")
    local stray_count
    stray_count=$(printf "%s\n" "$stray_commits" | grep -c . || true)
    if [[ "$stray_count" -ne 1 ]]; then
        log_fail "expected 1 stray commit in range ${before}..${after}, got ${stray_count}: ${stray_commits}"
        return
    fi
    if ! printf "%s" "$stray_commits" | grep -q "STRAY:"; then
        log_fail "stray commit subject missing 'STRAY:' marker: ${stray_commits}"
        return
    fi

    # Negative check: reset hard back to BEFORE, re-read HEAD, assert equal.
    # Guards against the detection being accidentally one-sided (e.g., always
    # reporting a mismatch even on a clean run).
    git -C "$REPO_DIR" reset --hard --quiet "$before"
    local reset_sha
    reset_sha=$(git -C "$REPO_DIR" rev-parse HEAD)
    if [[ "$reset_sha" != "$before" ]]; then
        log_fail "after reset, HEAD ($reset_sha) != BEFORE ($before)"
        return
    fi

    log_pass
}

# Test 4: Fallback on worktree add failure.
#
# Two failure modes the dispatch must handle without polluting repo state
# (TD-2, per-task fallback row):
#   (a) Target path already exists (git refuses).
#   (b) Branch name collides with an existing branch (git refuses -b).
#
# For each: invoke `git worktree add`, assert it returns non-zero, assert
# `git worktree list` does NOT gain a new entry, and assert the repo's HEAD
# is unchanged. A graceful failure is one that leaves the repo pristine so
# the orchestrator can fall back to serial dispatch without side effects.
test_worktree_add_failure_fallback() {
    log_test "fallback: worktree add failures leave repo state clean"
    reset_repo_state

    # Baseline: record current worktree count + HEAD. Any test-induced
    # mutation beyond what we explicitly create = pollution.
    local head_before
    head_before=$(git -C "$REPO_DIR" rev-parse HEAD)
    local wt_count_before
    wt_count_before=$(git -C "$REPO_DIR" worktree list --porcelain | awk '/^worktree / { c++ } END { print c+0 }')

    # --- Failure mode (a): target path already exists. ---
    local collision_path="${WORKTREES_ROOT}/collision"
    mkdir -p "$collision_path"
    echo "pre-existing" > "$collision_path/sentinel.txt"

    # Expect non-zero. `|| true` keeps `set -e` from aborting the test.
    local add_exit_a=0
    git -C "$REPO_DIR" worktree add --quiet -b "worktree-fallback-a" "$collision_path" >/dev/null 2>&1 \
        || add_exit_a=$?

    if [[ "$add_exit_a" -eq 0 ]]; then
        log_fail "(a) worktree add should have failed on existing non-empty path, but succeeded"
        return
    fi

    # Repo state invariants: worktree list count unchanged, HEAD unchanged,
    # the pre-existing sentinel file still intact (git refused, didn't
    # overwrite).
    local wt_count_after_a
    wt_count_after_a=$(git -C "$REPO_DIR" worktree list --porcelain | awk '/^worktree / { c++ } END { print c+0 }')
    if [[ "$wt_count_after_a" -ne "$wt_count_before" ]]; then
        log_fail "(a) worktree count changed: before=${wt_count_before} after=${wt_count_after_a}"
        return
    fi
    local head_after_a
    head_after_a=$(git -C "$REPO_DIR" rev-parse HEAD)
    if [[ "$head_after_a" != "$head_before" ]]; then
        log_fail "(a) HEAD changed after failed worktree add: before=${head_before} after=${head_after_a}"
        return
    fi
    if [[ ! -f "$collision_path/sentinel.txt" ]]; then
        log_fail "(a) pre-existing sentinel was clobbered"
        return
    fi

    # NOTE on branch leak: git (observed on 2.50.1 / Apple Git-155) creates the
    # branch BEFORE validating the target path, so `worktree add -b NAME PATH`
    # against a pre-existing non-empty PATH fails (exit 128) but leaves NAME
    # behind as a dangling branch. This is the pre-existing git behavior the
    # dispatch code MUST handle: on worktree-add failure, the fallback path
    # needs to `git branch -D <branch>` before falling back to serial dispatch,
    # otherwise a subsequent retry of the same task hits failure mode (b)
    # (duplicate-branch) instead.
    #
    # The test pins this contract: if a branch leak occurs, subsequent cleanup
    # succeeds. We delete the leaked branch here (simulating what dispatch
    # Phase 1 fallback must do) so failure mode (b) starts from a clean state.
    if git -C "$REPO_DIR" show-ref --verify --quiet "refs/heads/worktree-fallback-a"; then
        log_info "(a) branch leak observed (git >=2.50 behavior); simulating dispatch cleanup"
        git -C "$REPO_DIR" branch -D "worktree-fallback-a" >/dev/null 2>&1 || {
            log_fail "(a) unable to clean up leaked branch worktree-fallback-a"
            return
        }
    fi

    # Tidy up the sentinel dir so failure mode (b) has a clean slate.
    rm -rf "$collision_path"

    # --- Failure mode (b): branch name already exists. ---
    # Create a branch first, then try to worktree-add with -b using the
    # same name. git refuses because -b insists on creating a fresh branch.
    git -C "$REPO_DIR" branch "worktree-fallback-b" >/dev/null 2>&1
    local wt_count_mid
    wt_count_mid=$(git -C "$REPO_DIR" worktree list --porcelain | awk '/^worktree / { c++ } END { print c+0 }')

    local target_b="${WORKTREES_ROOT}/fallback-b"
    local add_exit_b=0
    git -C "$REPO_DIR" worktree add --quiet -b "worktree-fallback-b" "$target_b" >/dev/null 2>&1 \
        || add_exit_b=$?

    if [[ "$add_exit_b" -eq 0 ]]; then
        log_fail "(b) worktree add -b should have failed on duplicate branch, but succeeded"
        return
    fi

    local wt_count_after_b
    wt_count_after_b=$(git -C "$REPO_DIR" worktree list --porcelain | awk '/^worktree / { c++ } END { print c+0 }')
    if [[ "$wt_count_after_b" -ne "$wt_count_mid" ]]; then
        log_fail "(b) worktree count changed: before=${wt_count_mid} after=${wt_count_after_b}"
        return
    fi
    if [[ -d "$target_b" ]]; then
        log_fail "(b) target path created despite failed add: $target_b"
        return
    fi
    local head_after_b
    head_after_b=$(git -C "$REPO_DIR" rev-parse HEAD)
    if [[ "$head_after_b" != "$head_before" ]]; then
        log_fail "(b) HEAD changed after failed worktree add: before=${head_before} after=${head_after_b}"
        return
    fi

    log_pass
}

# --- Main ---
main() {
    echo "Running test-worktree-dispatch.sh (Task 2.0: git worktree mechanics)"
    echo "Temp dir: $TMPDIR_TEST"
    echo "Python:   $PD_PYTHON"
    echo

    setup_repo
    test_worktree_roundtrip
    test_sequential_merge
    test_stray_commit_detection
    test_worktree_add_failure_fallback

    echo
    echo "Ran: $TESTS_RUN | Passed: $TESTS_PASSED | Failed: $TESTS_FAILED"

    if [[ "$TESTS_FAILED" -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
