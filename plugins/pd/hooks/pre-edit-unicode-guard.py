#!/usr/bin/env python3
"""PreToolUse Unicode codepoint guard — non-blocking warning hook.

Reads JSON tool input from stdin; if any of `tool_input.{old_string, new_string, content}`
contain codepoints > 127, emits a warning to a controlled --warn-file (which the bash
wrapper then cats to stderr). Always returns 0 — never blocks tool execution.

Per spec FR-5 + design I-3 + TD-7 (defensive short-circuits retained for testability).
"""
import argparse
import json
import sys

MAX_CODEPOINTS_PER_FIELD = 5  # cap per FR-5 step 4


def scan_field(text):
    """Return UNIQUE codepoints > 127 in first-occurrence order, capped."""
    seen = []
    for c in text or "":
        cp = ord(c)
        if cp > 127 and cp not in seen:
            seen.append(cp)
            if len(seen) >= MAX_CODEPOINTS_PER_FIELD:
                break
    return seen


def format_warning(field_name, codepoints):
    """Format warning per spec FR-5 step 5."""
    pairs = ", ".join(f"(0x{cp:04x}, {chr(cp)!r})" for cp in codepoints)
    first_cp = codepoints[0]
    return (
        f'[pd] Unicode codepoint(s) detected in {field_name}: [{pairs}]. '
        f'Edit/Write may strip these silently. Use Python read-modify-write '
        f'with chr(0x{first_cp:04x}) runtime generation. '
        f'See plugins/pd/skills/systematic-debugging/SKILL.md → "Tooling Friction Escape Hatches".'
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--warn-file', required=True,
                        help='Tempfile for stderr warnings (controlled by bash wrapper).')
    args = parser.parse_args()

    try:
        data = json.load(sys.stdin)
    except Exception:
        # AC-E4: malformed JSON → silent.
        return 0

    # TD-7 defensive short-circuits — testable via stdin pipe (AC-6c, AC-6d).
    if data.get("hook_event_name") != "PreToolUse":
        return 0
    if data.get("tool_name") not in ("Edit", "Write"):
        return 0

    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict):
        return 0

    warnings = []
    for field in ("old_string", "new_string", "content"):
        value = ti.get(field) or ""
        if not isinstance(value, str):
            continue
        cps = scan_field(value)
        if cps:
            warnings.append(format_warning(field, cps))

    if warnings:
        try:
            with open(args.warn_file, 'w', encoding='utf-8') as wf:
                for w in warnings:
                    wf.write(w + '\n')
        except OSError:
            # Fail-quiet on tempfile write error — hook must never block.
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
