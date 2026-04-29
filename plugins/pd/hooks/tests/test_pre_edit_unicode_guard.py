"""Tests for FR-5 pre-edit-unicode-guard hook.

Tests use subprocess to invoke the bash wrapper with stdin-piped JSON,
testing the full bash + python module chain end-to-end.
"""
import json
import subprocess
from pathlib import Path

import pytest

HOOK_SH = Path(__file__).parent.parent / "pre-edit-unicode-guard.sh"


def _invoke(payload: dict) -> tuple[int, str, str]:
    """Pipe JSON to the hook script. Returns (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        ["bash", str(HOOK_SH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_ac6_single_codepoint_warning():
    """AC-6: single 0x85 codepoint → stderr warning, stdout {"continue":true}, exit 0."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"old_string": chr(0x85)},
    }
    rc, stdout, stderr = _invoke(payload)
    assert rc == 0
    assert stdout.strip() == '{"continue": true}'
    # Stderr regex per AC-6.
    import re
    assert re.search(r"Unicode codepoint.*0x0085.*chr\(0x0085\)", stderr)


def test_ac6b_multi_codepoint_dedup_ordering():
    """AC-6b: dedup + first-occurrence ordering, 4 unique from 7-input."""
    s = chr(0x85) + chr(0xa0) + chr(0x85) + chr(0x2014) + chr(0x2014) + chr(0x2014) + chr(0x3000)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"old_string": s},
    }
    rc, stdout, stderr = _invoke(payload)
    assert rc == 0
    # All 4 unique codepoints in stderr in first-seen order.
    expected = ["0x0085", "0x00a0", "0x2014", "0x3000"]
    last_pos = -1
    for cp in expected:
        pos = stderr.find(cp)
        assert pos > last_pos, f"{cp} missing or out-of-order in stderr"
        last_pos = pos


def test_ac6c_short_circuit_non_pretooluse():
    """AC-6c: hook_event_name != PreToolUse → silent stderr."""
    payload = {
        "hook_event_name": "SessionStart",
        "tool_name": "Edit",
        "tool_input": {"old_string": chr(0x85)},
    }
    rc, stdout, stderr = _invoke(payload)
    assert rc == 0
    assert stdout.strip() == '{"continue": true}'
    assert "Unicode codepoint" not in stderr


def test_ac6d_short_circuit_non_write_edit():
    """AC-6d: tool_name not in (Edit, Write) → silent stderr."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": chr(0x85)},
    }
    rc, stdout, stderr = _invoke(payload)
    assert rc == 0
    assert stdout.strip() == '{"continue": true}'
    assert "Unicode codepoint" not in stderr


def test_ace4_malformed_json():
    """AC-E4: malformed JSON → silent stderr, exit 0, stdout continue."""
    proc = subprocess.run(
        ["bash", str(HOOK_SH)],
        input="not json at all { { ",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == '{"continue": true}'
    assert "Unicode codepoint" not in proc.stderr


def test_ace5_binary_content_no_crash():
    """AC-E5: non-printable codepoints in content → no crash, codepoints > 127 only flagged."""
    # Mix of control chars (0x01) and high codepoint (0x85). Only 0x85 is reported.
    s = "\x01\x02" + chr(0x85)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"content": s},
    }
    rc, stdout, stderr = _invoke(payload)
    assert rc == 0
    assert stdout.strip() == '{"continue": true}'
    # Only 0x85 flagged, not 0x01/0x02.
    assert "0x0085" in stderr
    assert "0x0001" not in stderr
    assert "0x0002" not in stderr


def test_ascii_only_no_warning():
    """Smoke: pure ASCII input produces no warning."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"old_string": "hello world", "new_string": "goodbye world"},
    }
    rc, stdout, stderr = _invoke(payload)
    assert rc == 0
    assert stdout.strip() == '{"continue": true}'
    assert "Unicode codepoint" not in stderr


def test_continue_true_always_emitted():
    """Smoke: stdout always exactly {"continue": true} regardless of stderr."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"old_string": chr(0x85), "new_string": chr(0xa0)},
    }
    rc, stdout, _ = _invoke(payload)
    assert rc == 0
    assert stdout.strip() == '{"continue": true}'
