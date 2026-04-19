"""Tests for pattern_promotion.generators.hook.

Per design C-6 and FR-3-hook:
- `validate_feasibility(feasibility)` returns `(bool, Optional[str])` and must
  reject empty tools arrays, unknown tool enums, and unknown event / check_kind
  values. Accepts schema-correct feasibility dicts.
- `generate(entry, target_meta) -> DiffPlan` emits exactly three FileEdits:
  the hook `.sh`, the `test-{slug}.sh`, and the `hooks.json` patch
  (write_order 0, 1, 2 respectively; hooks.json last because it references
  the .sh path).
- Test script embeds BOTH a positive and negative invocation per TD-7.
- Slug collision auto-suffixes `-2`, `-3`, ... per FR-3-hook step 3.
- Every generated file body carries the TD-8 marker
  `# Promoted from KB entry: <entry-name>` near the top.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pattern_promotion.generators import hook
from pattern_promotion.kb_parser import KBEntry
from pattern_promotion.types import DiffPlan, FileEdit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_FEASIBILITY = {
    "event": "PreToolUse",
    "tools": ["Read", "Edit"],
    "check_kind": "file_path_regex",
    "check_expression": r"^[^/]",
}

MINIMAL_HOOKS_JSON = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/existing.sh"}
                ],
            }
        ]
    }
}


def _entry(name: str = "Block relative paths in tool calls") -> KBEntry:
    return KBEntry(
        name=name,
        description=(
            "Always pass absolute paths to Read/Edit/Glob — relative paths "
            "break when cwd changes mid-session."
        ),
        confidence="high",
        effective_observation_count=4,
        category="anti-patterns",
        file_path=Path("/tmp/anti-patterns.md"),
        line_range=(10, 20),
    )


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    """Minimal plugin-root fixture with an empty hooks/ dir + a hooks.json."""
    root = tmp_path / "pd"
    (root / "hooks" / "tests").mkdir(parents=True)
    (root / "hooks" / "hooks.json").write_text(
        json.dumps(MINIMAL_HOOKS_JSON, indent=2) + "\n"
    )
    return root


# ---------------------------------------------------------------------------
# validate_feasibility
# ---------------------------------------------------------------------------


class TestValidateFeasibility:
    def test_accepts_valid_feasibility(self):
        ok, reason = hook.validate_feasibility(VALID_FEASIBILITY)
        assert ok is True
        assert reason is None

    def test_rejects_empty_tools(self):
        bad = dict(VALID_FEASIBILITY)
        bad["tools"] = []
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False
        assert reason is not None
        assert "tools" in reason.lower()

    def test_rejects_unknown_tool(self):
        bad = dict(VALID_FEASIBILITY)
        bad["tools"] = ["Read", "Nonesuch"]
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False
        assert reason is not None
        assert "Nonesuch" in reason or "unknown" in reason.lower()

    def test_rejects_non_list_tools(self):
        bad = dict(VALID_FEASIBILITY)
        bad["tools"] = "Read"  # string not list
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False

    def test_rejects_unknown_event(self):
        bad = dict(VALID_FEASIBILITY)
        bad["event"] = "OnCoffeeBreak"
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False
        assert reason is not None
        assert "event" in reason.lower()

    def test_rejects_unknown_check_kind(self):
        bad = dict(VALID_FEASIBILITY)
        bad["check_kind"] = "telepathy"
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False

    def test_rejects_missing_required_keys(self):
        ok, reason = hook.validate_feasibility({"event": "PreToolUse"})
        assert ok is False

    def test_rejects_empty_check_expression(self):
        bad = dict(VALID_FEASIBILITY)
        bad["check_expression"] = ""
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False

    def test_rejects_backtick_in_check_expression(self):
        """Backtick enables command substitution in bash double-quotes."""
        bad = dict(VALID_FEASIBILITY)
        bad["check_expression"] = "a.b`whoami`"
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False
        assert reason is not None
        assert "`" in reason or "forbidden" in reason.lower()

    def test_rejects_dollar_paren_in_check_expression(self):
        """$( enables command substitution in bash double-quotes."""
        bad = dict(VALID_FEASIBILITY)
        bad["check_expression"] = "a.b$(whoami)"
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False
        assert reason is not None
        assert "forbidden" in reason.lower()

    def test_rejects_newline_in_check_expression(self):
        """Newlines can break out of single-line template contexts."""
        bad = dict(VALID_FEASIBILITY)
        bad["check_expression"] = "a.b\nextra"
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False

    def test_rejects_null_byte_in_check_expression(self):
        bad = dict(VALID_FEASIBILITY)
        bad["check_expression"] = "a.b\x00rest"
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_generates_three_file_edits(self, plugin_root: Path):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        assert isinstance(plan, DiffPlan)
        assert plan.target_type == "hook"
        assert len(plan.edits) == 3
        for e in plan.edits:
            assert isinstance(e, FileEdit)

    def test_write_order_sh_test_hooksjson(self, plugin_root: Path):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        # Sort by write_order and inspect
        by_order = sorted(plan.edits, key=lambda e: e.write_order)
        orders = [e.write_order for e in by_order]
        assert orders == [0, 1, 2]
        # Name-by-position: .sh first, test second, hooks.json last
        assert by_order[0].path.suffix == ".sh"
        assert by_order[0].path.name.startswith("check-") or by_order[0].path.name.startswith(
            "block-"
        )
        assert by_order[1].path.name.startswith("test-")
        assert by_order[1].path.suffix == ".sh"
        assert by_order[2].path.name == "hooks.json"

    def test_target_path_is_the_hook_sh(self, plugin_root: Path):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        assert plan.target_path.suffix == ".sh"
        assert plan.target_path.name != "hooks.json"
        # target_path should match the write_order=0 edit
        first = sorted(plan.edits, key=lambda e: e.write_order)[0]
        assert plan.target_path == first.path

    def test_sh_has_td8_marker(self, plugin_root: Path):
        entry = _entry("Block relative paths")
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        sh = sorted(plan.edits, key=lambda e: e.write_order)[0]
        assert "# Promoted from KB entry: Block relative paths" in sh.after

    def test_sh_header_shebang(self, plugin_root: Path):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        sh = sorted(plan.edits, key=lambda e: e.write_order)[0]
        assert sh.after.splitlines()[0].startswith("#!/")

    def test_test_script_has_positive_and_negative_cases(
        self, plugin_root: Path
    ):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        test_edit = sorted(plan.edits, key=lambda e: e.write_order)[1]
        body = test_edit.after
        # TD-7: deterministic feasibility check
        assert "POSITIVE_INPUT" in body
        assert "NEGATIVE_INPUT" in body
        # Both cases must be invoked (script must run the hook twice, at least)
        # Count plain invocations/asserts; any two references is enough.
        assert body.count("POSITIVE_INPUT") >= 1
        assert body.count("NEGATIVE_INPUT") >= 1
        # TD-8 marker present
        assert "# Promoted from KB entry:" in body

    def test_test_script_is_executable_shebang(self, plugin_root: Path):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        test_edit = sorted(plan.edits, key=lambda e: e.write_order)[1]
        assert test_edit.after.splitlines()[0].startswith("#!/")

    def test_hooks_json_patch_is_valid_json_and_registers_hook(
        self, plugin_root: Path
    ):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        hj_edit = sorted(plan.edits, key=lambda e: e.write_order)[2]
        parsed = json.loads(hj_edit.after)
        pretooluse = parsed["hooks"]["PreToolUse"]
        # New hook added for Read|Edit tools — count references to the .sh
        sh_name = plan.target_path.name
        refs = [
            h
            for block in pretooluse
            for h in block.get("hooks", [])
            if sh_name in h.get("command", "")
        ]
        assert len(refs) >= 1

    def test_hooks_json_preserves_existing_entries(self, plugin_root: Path):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        hj_edit = sorted(plan.edits, key=lambda e: e.write_order)[2]
        parsed = json.loads(hj_edit.after)
        # Existing "Bash" matcher pointing at existing.sh must still be present
        serialized = json.dumps(parsed)
        assert "existing.sh" in serialized

    def test_hooks_json_action_is_modify(self, plugin_root: Path):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        hj_edit = sorted(plan.edits, key=lambda e: e.write_order)[2]
        assert hj_edit.action == "modify"
        assert hj_edit.before is not None

    def test_sh_and_test_actions_are_create(self, plugin_root: Path):
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        sh = sorted(plan.edits, key=lambda e: e.write_order)[0]
        test_edit = sorted(plan.edits, key=lambda e: e.write_order)[1]
        assert sh.action == "create"
        assert sh.before is None
        assert test_edit.action == "create"
        assert test_edit.before is None

    def test_slug_collision_auto_suffix(self, plugin_root: Path):
        # Pre-seed a .sh at the natural slug path to force a collision.
        entry = _entry("Block relative paths in tool calls")
        # Generate once to discover what the natural slug is.
        plan1 = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        natural_path = plan1.target_path
        natural_path.parent.mkdir(parents=True, exist_ok=True)
        natural_path.write_text("# pre-existing\n")
        # Second generate must suffix -2
        plan2 = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        assert plan2.target_path != natural_path
        assert plan2.target_path.stem.endswith("-2")
        # Chain: collide -2 as well
        plan2.target_path.parent.mkdir(parents=True, exist_ok=True)
        plan2.target_path.write_text("# also here\n")
        plan3 = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        assert plan3.target_path.stem.endswith("-3")

    def test_slug_sanitizes_entry_name(self, plugin_root: Path):
        # Pathological entry name: punctuation, mixed case, trailing space
        entry = _entry("Anti-Pattern:   Bash/Relative Paths!! ")
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        stem = plan.target_path.stem
        # No slashes, no uppercase, no punctuation (except hyphens)
        assert "/" not in stem
        assert stem == stem.lower()
        assert all(c.isalnum() or c == "-" for c in stem)

    def test_generate_calls_validate_feasibility_and_raises_on_bad(
        self, plugin_root: Path
    ):
        entry = _entry()
        with pytest.raises(ValueError):
            hook.generate(
                entry,
                {"feasibility": {"event": "PreToolUse", "tools": []}},
                plugin_root=plugin_root,
            )

    def test_generate_without_feasibility_key_raises(self, plugin_root: Path):
        entry = _entry()
        with pytest.raises(ValueError):
            hook.generate(entry, {}, plugin_root=plugin_root)


# ---------------------------------------------------------------------------
# Shell-injection hardening
# ---------------------------------------------------------------------------


class TestShellInjectionHardening:
    """Ensure user-controlled strings can't break out of shell script contexts."""

    def test_entry_name_injection_is_escaped_in_sh(self, plugin_root: Path):
        """A malicious entry name must not break out of the echo double-quote."""
        # Hostile entry name containing characters that are special inside
        # bash double-quoted strings: ", $, `, \. If not escaped, this would
        # close the echo string and inject commands.
        malicious = 'My Pattern"; rm -rf ~; echo "'
        entry = _entry(malicious)
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        sh = sorted(plan.edits, key=lambda e: e.write_order)[0]
        # We only require safety on the EXECUTABLE lines. Comment lines
        # starting with `#` are never evaluated by bash even if they contain
        # literal `"; rm -rf ~;` text. The at-risk line is the echo inside
        # the `if` block that interpolates entry_name into a double-quoted
        # string.
        code_lines = [
            ln for ln in sh.after.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # The exact break-out sequence `"; rm -rf ~; echo "` must not appear
        # in any executable line — if it did, the echo would close and a
        # separate `rm` command would execute.
        assert '"; rm -rf ~; echo "' not in code, (
            "entry_name shell-break sequence was not escaped in code lines"
        )
        # Double-quote inside entry_name must be backslash-escaped.
        assert '\\"' in code, (
            "expected backslash-escaped double-quote from entry_name sanitization"
        )

    def test_entry_name_with_backtick_is_escaped(self, plugin_root: Path):
        """Backticks would trigger command substitution inside double quotes."""
        entry = _entry("Inject`whoami`pattern")
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        sh = sorted(plan.edits, key=lambda e: e.write_order)[0]
        body = sh.after
        # An un-escaped backtick inside a bash double-quoted string triggers
        # command substitution. We require the generator to have escaped the
        # backtick (prefix with backslash).
        # Every backtick occurrence in the body that's adjacent to the
        # injected token must be preceded by a backslash.
        assert "\\`whoami\\`" in body, (
            "backtick must be backslash-escaped when inside a double-quoted "
            "echo line"
        )

    def test_entry_name_with_newline_is_flattened(self, plugin_root: Path):
        """Newlines in entry_name must not break comment lines into code."""
        entry = _entry("Pattern with\nnewline\nbad")
        plan = hook.generate(
            entry,
            {"feasibility": VALID_FEASIBILITY},
            plugin_root=plugin_root,
        )
        sh = sorted(plan.edits, key=lambda e: e.write_order)[0]
        lines = sh.after.splitlines()
        # The TD-8 marker must appear on EXACTLY ONE line — newlines must
        # not have escaped the comment context.
        td8_lines = [i for i, ln in enumerate(lines) if "Promoted from KB entry" in ln]
        assert len(td8_lines) == 1

    def test_json_field_extractor_with_single_quote_is_escaped(
        self, plugin_root: Path
    ):
        """Single quotes in the jq path must be escaped for single-quoted embedding."""
        feas = dict(VALID_FEASIBILITY)
        feas["check_kind"] = "json_field"
        # jq doesn't actually allow a bare single quote in a path, but the
        # generator must still defend — splicing a raw apostrophe into a
        # single-quoted shell literal closes it.
        feas["check_expression"] = ".tool_input.field_with'apostrophe"
        entry = _entry()
        plan = hook.generate(
            entry,
            {"feasibility": feas},
            plugin_root=plugin_root,
        )
        sh = sorted(plan.edits, key=lambda e: e.write_order)[0]
        body = sh.after
        # The single-quote escape technique transforms ' into '\''
        assert "'\\''" in body, "single-quote escape pattern missing"
        # And the raw expression should not appear unescaped between two
        # surviving single quotes (which would break out).
        assert "field_with'apostrophe" not in body

    def test_backtick_in_check_expression_rejected_at_validation(self):
        """Belt-and-suspenders: validator rejects backtick injection."""
        bad = dict(VALID_FEASIBILITY)
        bad["check_kind"] = "json_field"
        bad["check_expression"] = ".a.b`whoami`"
        ok, reason = hook.validate_feasibility(bad)
        assert ok is False
        assert reason is not None


# ---------------------------------------------------------------------------
# Feature 085 FR-7: regex-aware test stub generation (SC-10 / AC-H6..9 / AC-E11/12)
# ---------------------------------------------------------------------------

import re as _re_stdlib  # avoid shadowing within existing module scope


_COMPLEX_NOTE = (
    "# NOTE: regex too complex for auto-embedded POSITIVE_INPUT — review manually"
)


def _render_test_sh_for(check_kind: str, check_expression: str) -> str:
    """Helper: build a minimal feasibility dict and render the test script."""
    feas = {
        "event": "PreToolUse",
        "tools": ["Read"],
        "check_kind": check_kind,
        "check_expression": check_expression,
    }
    # Slug / hook_rel_path are placeholders for the render — what we
    # assert on is the POSITIVE_INPUT and the presence / absence of
    # the complex-regex note.
    return hook._render_test_sh(
        entry_name="Test Entry",
        slug="test-slug",
        hook_rel_path="test-slug.sh",
        feasibility=feas,
    )


def _extract_positive(script: str) -> str:
    """Extract the string literal assigned to POSITIVE_INPUT in the script."""
    m = _re_stdlib.search(r"POSITIVE_INPUT='([^']*)'", script)
    assert m is not None, f"POSITIVE_INPUT not found in:\n{script}"
    return m.group(1)


class TestRenderTestSimpleRegex:
    """AC-H6/H7/H8: simple regexes produce a POSITIVE_INPUT that matches."""

    def test_render_test_sh_simple_literal_regex(self):
        """AC-H6: `\\.env$` should match the generated POSITIVE_INPUT."""
        script = _render_test_sh_for("file_path_regex", r"\.env$")
        # For file_path_regex the extractor reads .tool_input.file_path.
        # The POSITIVE_INPUT is a JSON fragment wrapping a path; we
        # assert the inner path string matches the regex.
        m = _re_stdlib.search(r'"file_path":"([^"]*)"', script)
        assert m is not None
        path = m.group(1)
        assert _re_stdlib.search(r"\.env$", path), (
            f"POSITIVE file_path {path!r} does not match \\.env$"
        )
        assert _COMPLEX_NOTE not in script

    def test_render_test_sh_alternation(self):
        """AC-H7: `foo|bar` should match the generated POSITIVE_INPUT."""
        script = _render_test_sh_for("content_regex", r"foo|bar")
        m = _re_stdlib.search(r'"content":"([^"]*)"', script)
        assert m is not None
        content = m.group(1)
        assert _re_stdlib.search(r"foo|bar", content), (
            f"POSITIVE content {content!r} does not match foo|bar"
        )
        assert _COMPLEX_NOTE not in script

    def test_render_test_sh_character_class(self):
        """AC-H8: `[a-z]+@example\\.com` should match the generated POSITIVE_INPUT."""
        script = _render_test_sh_for("content_regex", r"[a-z]+@example\.com")
        m = _re_stdlib.search(r'"content":"([^"]*)"', script)
        assert m is not None
        content = m.group(1)
        assert _re_stdlib.search(r"[a-z]+@example\.com", content), (
            f"POSITIVE content {content!r} does not match regex"
        )
        assert _COMPLEX_NOTE not in script


class TestRenderTestComplexRegex:
    """AC-H9 / AC-E11 / AC-E12: complex regexes fall back with a comment."""

    def test_render_test_sh_inline_flag_complex(self):
        """AC-H9: `(?i)secret` is complex — comment must be present."""
        script = _render_test_sh_for("content_regex", r"(?i)secret")
        assert _COMPLEX_NOTE in script

    def test_render_test_sh_backreference_complex(self):
        """AC-E11: `(foo)\\1` is complex — comment must be present."""
        script = _render_test_sh_for("content_regex", r"(foo)\1")
        assert _COMPLEX_NOTE in script
