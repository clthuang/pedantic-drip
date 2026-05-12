#!/usr/bin/env bash
# plugins/pd/hooks/tests/bash-version-capture.sh
#
# Feature 113 FR-2 / AC-12: produce AC-12 evidence in canonical 3-section format.
#
# Usage:
#   bash plugins/pd/hooks/tests/bash-version-capture.sh > docs/features/{id}-{slug}/bash-version.log
#
# Exit code: 0 if /bin/bash test-hooks.sh exits 0; otherwise propagates the
# test-hooks.sh exit code.

# EPIPE safety (CLAUDE.md / feature 107): the trap is co-load-bearing with the
# `|| true` guards below. Without the trap, the bash process is SIGPIPE-killed
# before `|| true` can run when a downstream consumer closes the pipe early.
trap '' PIPE

# Intentional: NO 'set -e' — we want each section emitted even if a prior
# section command fails, so partial evidence is captured. Only the test-hooks.sh
# exit code (section 3) propagates.
set -u

# Each write is wrapped to swallow EPIPE-induced failures (the trap prevents
# kill; the `|| true` prevents `set -u` (or a transient write error) from
# terminating the script mid-emit).
{ echo "=== Host bash --version ==="; } 2>/dev/null || true
{ bash --version; } 2>/dev/null || true

{ echo "=== /bin/bash --version ==="; } 2>/dev/null || true
{ /bin/bash --version; } 2>/dev/null || true

# Recursion guard: test-hooks.sh contains a test that invokes THIS script
# (test_bash_version_capture_script_emits_three_sections). Set the sentinel so
# that test skips itself when we re-invoke test-hooks.sh from within the
# capture script. Without this, test-hooks.sh would call bash-version-capture.sh
# which calls test-hooks.sh which calls bash-version-capture.sh → infinite loop.
TEST_OUTPUT=$(BASH_VERSION_CAPTURE_RUNNING=1 /bin/bash plugins/pd/hooks/tests/test-hooks.sh 2>&1)
RC=$?
{ echo "=== /bin/bash plugins/pd/hooks/tests/test-hooks.sh (exit=${RC}) ==="; } 2>/dev/null || true
{ echo "${TEST_OUTPUT}" | tail -20; } 2>/dev/null || true

exit ${RC}
