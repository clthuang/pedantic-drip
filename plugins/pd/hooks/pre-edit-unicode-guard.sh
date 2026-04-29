#!/usr/bin/env bash
# pre-edit-unicode-guard.sh — non-blocking warning hook for Edit|Write Unicode codepoints.
# Spec FR-5 + design I-3 (TD-2 revised: bash wrapper + py module).
#
# Always emits {"continue": true} to stdout regardless of any failure path.
# Stderr discipline: python3 internal errors → /dev/null; intentional warnings via tempfile.

set +e  # NEVER let any failure block the hook.

emit_continue() { printf '%s\n' '{"continue": true}'; }

# Belt + suspenders: guarantee stdout emits even on early exit paths below.
trap emit_continue EXIT

if ! command -v python3 >/dev/null 2>&1; then
    exit 0
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
guard_py="${script_dir}/pre-edit-unicode-guard.py"

if [[ ! -f "${guard_py}" ]]; then
    exit 0
fi

# Use portable mktemp form (per design I-3 + plan-review iter 1 portability fix).
warn_file="$(mktemp "${TMPDIR:-/tmp}/pd-unicode-guard.XXXXXX" 2>/dev/null)"
if [[ -z "${warn_file}" || ! -f "${warn_file}" ]]; then
    exit 0
fi

# Replace earlier trap; combined cleanup + emit.
trap 'rm -f "${warn_file}"; emit_continue' EXIT

# Pipe stdin to python; redirect python3 internal stderr to /dev/null.
# Intentional warnings go to ${warn_file} via the script's --warn-file arg.
python3 "${guard_py}" --warn-file "${warn_file}" 2>/dev/null

if [[ -s "${warn_file}" ]]; then
    cat "${warn_file}" >&2
fi

exit 0
