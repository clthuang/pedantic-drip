#!/usr/bin/env bash
# The one version is plugin.json's: X.Y.Z, at least the highest v* tag, and a new one has its CHANGELOG section.
# marketplace.json's pd entry carries none (Claude Code reads plugin.json's first).
# Usage: scripts/check-version.sh   (run by validate.sh, from the repository root)
set -euo pipefail

MANIFEST=plugins/pd/.claude-plugin/plugin.json
die() { echo "check-version: $*" >&2; exit 1; }
by_version() { sort -t. -k1,1n -k2,2n -k3,3n; }

version=$(jq -r '.version // empty' "$MANIFEST")
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "$MANIFEST version '$version' must be X.Y.Z"
! jq -e '.plugins[] | select(.name == "pd") | has("version")' .claude-plugin/marketplace.json >/dev/null \
    || die ".claude-plugin/marketplace.json sets the pd entry's version; plugin.json holds the only one"
last=$(git tag --list 'v*' | sed -n 's/^v\([0-9]*\.[0-9]*\.[0-9]*\)$/\1/p' | by_version | tail -1)
[[ -n "$last" ]] || die "no v* release tags here: run git fetch --tags"
[[ "$(printf '%s\n%s\n' "$last" "$version" | by_version | tail -1)" == "$version" ]] \
    || die "$MANIFEST version $version is below the last release, v$last"
[[ "$version" == "$last" ]] || grep -qF "## [$version]" CHANGELOG.md \
    || die "$MANIFEST version $version has no '## [$version]' section in CHANGELOG.md"
echo "version $version (last release v$last)"
