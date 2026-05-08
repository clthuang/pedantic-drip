#!/usr/bin/env bash
# Verifies: bash with set -e + trap '' PIPE + EPIPE-safe write exits 0
# under closed-stdout. Run: bash probe-a1-exit0-under-broken-pipe.sh
# Verify exit 0:
#   bash probe-a1-exit0-under-broken-pipe.sh | dd of=/dev/null bs=1 count=0 ; echo "rc=$?"
set -euo pipefail
trap '' PIPE
{ printf '{}\n' 2>/dev/null; } || true
exit 0
