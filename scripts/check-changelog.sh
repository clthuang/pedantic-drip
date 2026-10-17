#!/usr/bin/env bash
# Fails when CHANGELOG.md's released sections differ from the base's, other than new sections prepended (a release PR).
# A merge can slip a late PR's [Unreleased] entry into a just-released section without a conflict.
# Usage: scripts/check-changelog.sh <base ref>   (CI passes origin/<the PR's base>)
set -euo pipefail

released() { sed -n '/^## \[[0-9]/,$p'; }
base=$(git show "${1:?usage: $0 <base ref>}:CHANGELOG.md" | released)
head=$(released < CHANGELOG.md)
[[ "$head" == *"$base" ]] || {
    echo "check-changelog: CHANGELOG.md changes a released section; put new entries under [Unreleased]" >&2
    exit 1
}
