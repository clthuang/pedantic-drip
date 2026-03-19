#!/usr/bin/env bash
# Cleanup old agent_sandbox directories based on age
#
# Usage: cleanup-sandbox.sh [days]
# Default: removes directories older than 7 days
#
# This script removes dated subdirectories in agent_sandbox/ that are older
# than the specified number of days. Designed to be run manually or via cron.

set -euo pipefail

SANDBOX_DIR="${PWD}/agent_sandbox"
DAYS_OLD="${1:-7}"

# Validate DAYS_OLD is numeric to prevent injection
if [[ ! "$DAYS_OLD" =~ ^[0-9]+$ ]]; then
  echo "Error: days must be a positive integer, got: $DAYS_OLD" >&2
  exit 1
fi

if [[ ! -d "$SANDBOX_DIR" ]]; then
  echo "No agent_sandbox directory found at $SANDBOX_DIR"
  exit 0
fi

# Find and remove directories older than DAYS_OLD
# Uses -mtime +N to find files modified more than N days ago
count=0
while IFS= read -r -d '' dir; do
  if [[ -d "$dir" ]]; then
    echo "Removing: $dir"
    rm -rf "$dir"
    ((count++)) || true
  fi
done < <(find "$SANDBOX_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$DAYS_OLD" -print0 2>/dev/null)

if [[ $count -eq 0 ]]; then
  echo "No directories older than $DAYS_OLD days found in $SANDBOX_DIR"
else
  echo "Removed $count directories"
fi
