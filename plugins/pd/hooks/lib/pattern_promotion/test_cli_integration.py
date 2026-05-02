"""Integration tests for pattern_promotion CLI subcommands.

Phase 1 scope: enumerate subcommand config-wiring tests per Task 1.8.
Remaining subcommands get broader coverage in Phase 4a.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[5]
PLUGIN_LIB = REPO_ROOT / "plugins" / "pd" / "hooks" / "lib"
VENV_PY = REPO_ROOT / "plugins" / "pd" / ".venv" / "bin" / "python"


QUALIFYING_KB = textwrap.dedent("""\
    # Heuristics

    ## Decision Heuristics

    ### Entry Three
    Qualifies at threshold 3 but not at 5.
    - Confidence: high
    - Observation count: 3

    ### Entry Four
    Qualifies at threshold 3 and 4 but not 5.
    - Confidence: high
    - Observation count: 4

    ### Entry Five
    Qualifies at any threshold 3-5.
    - Confidence: high
    - Observation count: 5

    ### Entry Two
    Below threshold 3; ineligible.
    - Confidence: high
    - Observation count: 2
    """)


@pytest.fixture
def project_with_kb(tmp_path: Path) -> Path:
    """A tmp project root with docs/knowledge-bank/ and .claude/pd.local.md."""
    kb = tmp_path / "docs" / "knowledge-bank"
    kb.mkdir(parents=True)
    (kb / "heuristics.md").write_text(QUALIFYING_KB)
    (tmp_path / ".claude").mkdir()
    return tmp_path


def _run_enumerate(
    project_root: Path,
    *,
    sandbox: Path,
    min_observations: int | None = None,
) -> tuple[int, dict]:
    """Invoke the CLI; return (returncode, parsed-status-json).

    Feature 102 FR-5: passes `--include-descriptive` so existing test fixtures
    (which use descriptive prose) continue producing the same counts. New
    tests targeting FR-5 hard-filter behavior call enumerate directly.
    """
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{PLUGIN_LIB}{os.pathsep}{existing}" if existing else str(PLUGIN_LIB)
    )
    cmd = [
        str(VENV_PY),
        "-m",
        "pattern_promotion",
        "enumerate",
        "--sandbox",
        str(sandbox),
        "--kb-dir",
        str(project_root / "docs" / "knowledge-bank"),
        "--project-root",
        str(project_root),
        "--include-descriptive",
    ]
    if min_observations is not None:
        cmd.extend(["--min-observations", str(min_observations)])
    proc = subprocess.run(
        cmd, env=env, capture_output=True, text=True, cwd=project_root
    )
    last_line = (proc.stdout or "").strip().splitlines()[-1]
    return proc.returncode, json.loads(last_line)


# ---------------------------------------------------------------------------
# Task 1.8: min_observations resolution
# ---------------------------------------------------------------------------


class TestMinObservations:
    """CLI behavior for resolving `--min-observations` (keyword: min_observations)."""

    def test_min_observations_config_file_sets_threshold(
        self, project_with_kb: Path, tmp_path: Path
    ):
        # Config says 5 → only Entry Five qualifies.
        (project_with_kb / ".claude" / "pd.local.md").write_text(
            "memory_promote_min_observations: 5\n"
        )
        sandbox = tmp_path / "sb"
        rc, status = _run_enumerate(project_with_kb, sandbox=sandbox)
        assert rc == 0, status
        assert status["status"] == "ok"
        assert status["min_observations"] == 5
        assert status["count"] == 1

    def test_min_observations_cli_flag_overrides_config(
        self, project_with_kb: Path, tmp_path: Path
    ):
        # Config says 5, but --min-observations 2 overrides → all 4 entries
        # with obs>=2 qualify (all 4: Two, Three, Four, Five).
        (project_with_kb / ".claude" / "pd.local.md").write_text(
            "memory_promote_min_observations: 5\n"
        )
        sandbox = tmp_path / "sb"
        rc, status = _run_enumerate(
            project_with_kb, sandbox=sandbox, min_observations=2
        )
        assert rc == 0, status
        assert status["min_observations"] == 2
        assert status["count"] == 4

    def test_min_observations_default_when_config_missing(
        self, project_with_kb: Path, tmp_path: Path
    ):
        # No config file at all → default 3 → Three, Four, Five qualify.
        config = project_with_kb / ".claude" / "pd.local.md"
        if config.exists():
            config.unlink()
        sandbox = tmp_path / "sb"
        rc, status = _run_enumerate(project_with_kb, sandbox=sandbox)
        assert rc == 0, status
        assert status["min_observations"] == 3
        assert status["count"] == 3

    def test_min_observations_entries_json_written_to_sandbox(
        self, project_with_kb: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sb"
        rc, status = _run_enumerate(
            project_with_kb, sandbox=sandbox, min_observations=3
        )
        assert rc == 0
        data_path = Path(status["data_path"])
        assert data_path.is_file()
        # Feature 102 FR-5: entries.json now uses top-level `entries` key
        data = json.loads(data_path.read_text())
        entries = data["entries"] if isinstance(data, dict) else data
        assert isinstance(entries, list)
        assert len(entries) == status["count"]
        for e in entries:
            assert {
                "name",
                "description",
                "confidence",
                "effective_observation_count",
                "category",
                "file_path",
                "line_range",
            }.issubset(e.keys())


# ---------------------------------------------------------------------------
# Task 3.6: mark subcommand
# ---------------------------------------------------------------------------


def _run_mark(
    *,
    kb_file: Path,
    entry_name: str,
    target_type: str,
    target_path: str,
    cwd: Path | None = None,
) -> tuple[int, dict]:
    """Invoke `python -m pattern_promotion mark ...`; return (rc, status)."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{PLUGIN_LIB}{os.pathsep}{existing}" if existing else str(PLUGIN_LIB)
    )
    cmd = [
        str(VENV_PY),
        "-m",
        "pattern_promotion",
        "mark",
        "--kb-file",
        str(kb_file),
        "--entry-name",
        entry_name,
        "--target-type",
        target_type,
        "--target-path",
        target_path,
    ]
    proc = subprocess.run(
        cmd, env=env, capture_output=True, text=True, cwd=cwd or kb_file.parent
    )
    last_line = (proc.stdout or "").strip().splitlines()[-1]
    return proc.returncode, json.loads(last_line)


class TestMarkSubcommand:
    """Task 3.6: `mark` CLI wiring (keyword: mark)."""

    def test_mark_inserts_after_confidence_line(self, tmp_path: Path):
        kb = tmp_path / "heuristics.md"
        kb.write_text(
            textwrap.dedent(
                """\
                # Heuristics

                ### Heuristic With Confidence
                A description.
                - Confidence: high
                - Observation count: 3

                ### Other Heuristic
                Unrelated.
                - Confidence: high
                """
            )
        )
        rc, status = _run_mark(
            kb_file=kb,
            entry_name="Heuristic With Confidence",
            target_type="skill",
            target_path="plugins/pd/skills/test-skill/SKILL.md",
        )
        assert rc == 0, status
        assert status["status"] == "ok"
        lines = kb.read_text().splitlines()
        conf_idx = lines.index("- Confidence: high")
        # Promoted line inserted immediately after the Confidence line
        assert lines[conf_idx + 1] == (
            "- Promoted: skill:plugins/pd/skills/test-skill/SKILL.md"
        )
        # Adjacent entries untouched
        assert "### Other Heuristic" in kb.read_text()

    def test_mark_inserts_before_next_sibling_when_no_confidence(
        self, tmp_path: Path
    ):
        kb = tmp_path / "patterns.md"
        kb.write_text(
            textwrap.dedent(
                """\
                # Patterns

                ### Pattern: No Confidence
                A pattern without a Confidence field.
                - Used in: Feature #101
                - Used in: Feature #102
                - Used in: Feature #103

                ### Pattern: Next One
                Another pattern.
                """
            )
        )
        rc, status = _run_mark(
            kb_file=kb,
            entry_name="Pattern: No Confidence",
            target_type="agent",
            target_path="plugins/pd/agents/test-agent.md",
        )
        assert rc == 0, status
        lines = kb.read_text().splitlines()
        # Marker lands before the next sibling heading (which is "### Pattern: Next One").
        sibling_idx = lines.index("### Pattern: Next One")
        # There should be the marker somewhere between the block start and the sibling.
        pattern_idx = lines.index("### Pattern: No Confidence")
        marker = "- Promoted: agent:plugins/pd/agents/test-agent.md"
        block_lines = lines[pattern_idx:sibling_idx]
        assert marker in block_lines
        # And the marker is directly adjacent to the next sibling (trailing
        # blank lines trimmed by kb_parser.mark_entry).
        assert lines[sibling_idx - 1] == marker or (
            lines[sibling_idx - 2] == marker and lines[sibling_idx - 1] == ""
        )

    def test_mark_inserts_at_eof_for_last_entry(self, tmp_path: Path):
        kb = tmp_path / "anti-patterns.md"
        kb.write_text(
            textwrap.dedent(
                """\
                # Anti-Patterns

                ### Anti-Pattern: Only Entry
                A final-and-only entry.
                - Confidence: high
                - Observation count: 4
                """
            )
        )
        rc, status = _run_mark(
            kb_file=kb,
            entry_name="Anti-Pattern: Only Entry",
            target_type="hook",
            target_path="plugins/pd/hooks/check-only.sh",
        )
        assert rc == 0, status
        text = kb.read_text()
        # EOF insertion: marker present, preferring directly after Confidence.
        assert (
            "- Promoted: hook:plugins/pd/hooks/check-only.sh" in text
        )
        # File still ends with a trailing newline.
        assert text.endswith("\n")

    def test_mark_accepts_repo_relative_target_path(self, tmp_path: Path):
        """Marker stores the target path verbatim; test passes a repo-relative
        path (not absolute) and asserts it survives round-trip unchanged."""
        kb = tmp_path / "heuristics.md"
        kb.write_text(
            textwrap.dedent(
                """\
                # Heuristics

                ### Relative Path Marker
                Test repo-relative marker.
                - Confidence: high
                - Observation count: 5
                """
            )
        )
        target_rel = "plugins/pd/skills/creating-tests/SKILL.md"
        rc, status = _run_mark(
            kb_file=kb,
            entry_name="Relative Path Marker",
            target_type="skill",
            target_path=target_rel,
        )
        assert rc == 0, status
        text = kb.read_text()
        assert f"- Promoted: skill:{target_rel}" in text
        # Negative assertion: no absolute path leaked
        assert "- Promoted: skill:/" not in text

    def test_mark_help_lists_required_args(self, tmp_path: Path):
        """`mark --help` prints its four required flags."""
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{PLUGIN_LIB}{os.pathsep}{existing}"
            if existing
            else str(PLUGIN_LIB)
        )
        proc = subprocess.run(
            [str(VENV_PY), "-m", "pattern_promotion", "mark", "--help"],
            env=env,
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert proc.returncode == 0
        out = proc.stdout
        for flag in ("--kb-file", "--entry-name", "--target-type", "--target-path"):
            assert flag in out


# ---------------------------------------------------------------------------
# Task 4a.5: Subprocess Serialization Contract — end-to-end
# ---------------------------------------------------------------------------


def _run_cli(
    *args: str,
    cwd: Path | None = None,
    env_extra: dict | None = None,
) -> tuple[int, str, str]:
    """Invoke `python -m pattern_promotion <args>`; return (rc, stdout, stderr).

    Feature 102 FR-5: when subcommand is "enumerate", auto-inject
    `--include-descriptive` so existing test fixtures (which don't use
    deontic-modal vocabulary) continue to produce the same counts. New
    FR-5-targeted tests in test_kb_parser/test_main bypass this helper.
    """
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{PLUGIN_LIB}{os.pathsep}{existing}" if existing else str(PLUGIN_LIB)
    )
    if env_extra:
        env.update(env_extra)
    final_args = list(args)
    if final_args and final_args[0] == "enumerate" and "--include-descriptive" not in final_args:
        final_args.append("--include-descriptive")
    proc = subprocess.run(
        [str(VENV_PY), "-m", "pattern_promotion", *final_args],
        env=env,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _parse_last_json_line(stdout: str) -> dict:
    """Return the last stdout line parsed as JSON — the status object."""
    lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    assert lines, "stdout was empty"
    last = lines[-1]
    # Contract: single-line JSON (no pretty-printing). Sanity-check one line.
    return json.loads(last)


def _assert_single_line_json(stdout: str) -> dict:
    """Assert the status line is exactly one line and valid JSON."""
    lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    # We allow other lines (e.g. from argparse) above the status but the
    # status itself MUST be a single compact line per contract.
    status_line = lines[-1]
    assert status_line.startswith("{") and status_line.endswith("}"), (
        f"status line is not single-line JSON: {status_line!r}"
    )
    return json.loads(status_line)


# Shared fixtures for the contract suite -----------------------------------


CONTRACT_KB_MD = textwrap.dedent("""\
    # Heuristics

    ### Implementing bundles same-file tasks
    When dispatching implementer agents, group same-file tasks into one dispatch
    so they share context and reduce duplicated reasoning workflow steps.
    - Confidence: high
    - Observation count: 4

    ### Reviewer catches regressions in review phase
    Reviewer agents validate that no regressions slipped in during review phase;
    reject if a previously green test now fails.
    - Confidence: high
    - Observation count: 3
    """)


@pytest.fixture
def contract_project(tmp_path: Path) -> Path:
    """A tmp project with KB fixture + plugin mirror for generator paths."""
    kb = tmp_path / "docs" / "knowledge-bank"
    kb.mkdir(parents=True)
    (kb / "heuristics.md").write_text(CONTRACT_KB_MD)
    (tmp_path / ".claude").mkdir()
    # Minimal plugin-root mirror for generators (skill / agent / command / hook).
    plugin = tmp_path / "plugins" / "pd"
    (plugin / "skills" / "implementing").mkdir(parents=True)
    (plugin / "skills" / "implementing" / "SKILL.md").write_text(
        textwrap.dedent(
            """\
            # implementing

            ## Rules
            - Existing rule.
            """
        )
    )
    (plugin / "agents").mkdir(parents=True)
    (plugin / "agents" / "code-reviewer.md").write_text(
        textwrap.dedent(
            """\
            # code-reviewer

            ## Checks
            - Existing check.
            """
        )
    )
    (plugin / "commands").mkdir(parents=True)
    (plugin / "commands" / "wrap-up.md").write_text(
        textwrap.dedent(
            """\
            # /pd:wrap-up

            ### Step 5a: final touches
            - Existing step body.
            """
        )
    )
    (plugin / "hooks" / "tests").mkdir(parents=True)
    (plugin / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {}}, indent=2) + "\n"
    )
    return tmp_path


class TestEnumerateContract:
    """Task 4a.5 (1): enumerate writes entries.json and emits single-line JSON."""

    def test_enumerate_produces_sandbox_file_and_status(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sb_enum"
        rc, out, _ = _run_cli(
            "enumerate",
            "--sandbox",
            str(sandbox),
            "--kb-dir",
            str(contract_project / "docs" / "knowledge-bank"),
            "--project-root",
            str(contract_project),
            cwd=contract_project,
        )
        assert rc == 0, out
        status = _assert_single_line_json(out)
        assert status["status"] == "ok"
        # Contract keys
        assert "count" in status and isinstance(status["count"], int)
        assert "entries_path" in status
        assert Path(status["entries_path"]).is_file()
        # data_path (design-level alias) and entries_path agree
        assert Path(status["data_path"]) == Path(status["entries_path"])
        # entries.json contents match count (Feature 102 FR-5: top-level `entries` key)
        data = json.loads(
            (sandbox / "entries.json").read_text(encoding="utf-8")
        )
        entries = data["entries"] if isinstance(data, dict) else data
        assert isinstance(entries, list)
        assert len(entries) == status["count"]
        # Two qualifying entries at default threshold 3
        assert status["count"] == 2


class TestClassifyContract:
    """Task 4a.5 (2): classify reads entries.json, writes classifications.json."""

    def _seed_enumerate(
        self, contract_project: Path, sandbox: Path
    ) -> dict:
        rc, out, _ = _run_cli(
            "enumerate",
            "--sandbox",
            str(sandbox),
            "--kb-dir",
            str(contract_project / "docs" / "knowledge-bank"),
            "--project-root",
            str(contract_project),
            cwd=contract_project,
        )
        assert rc == 0, out
        return _parse_last_json_line(out)

    def test_classify_writes_classifications_json(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sb_classify"
        self._seed_enumerate(contract_project, sandbox)

        rc, out, _ = _run_cli(
            "classify",
            "--sandbox",
            str(sandbox),
            cwd=contract_project,
        )
        assert rc == 0, out
        status = _assert_single_line_json(out)
        assert status["status"] == "ok"
        assert "classifications_path" in status
        path = Path(status["classifications_path"])
        assert path.is_file()
        classifications = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(classifications, list)
        assert len(classifications) == 2
        for c in classifications:
            assert {"entry_name", "scores", "winner", "tied"}.issubset(c.keys())
            assert set(c["scores"].keys()) == {"hook", "skill", "agent", "command"}
            # winner must be one of the 4 targets or None
            assert c["winner"] in (None, "hook", "skill", "agent", "command")
            assert isinstance(c["tied"], bool)

    def test_classify_finds_expected_winners(
        self, contract_project: Path, tmp_path: Path
    ):
        """The fixture entries should route to skill and agent winners."""
        sandbox = tmp_path / "sb_classify_winners"
        self._seed_enumerate(contract_project, sandbox)

        rc, out, _ = _run_cli(
            "classify",
            "--sandbox",
            str(sandbox),
            cwd=contract_project,
        )
        assert rc == 0, out
        status = _parse_last_json_line(out)
        classifications = json.loads(
            Path(status["classifications_path"]).read_text(encoding="utf-8")
        )
        by_name = {c["entry_name"]: c for c in classifications}
        # "Implementing bundles same-file tasks" — contains `implementing`
        # and `workflow` so skill should win.
        imp = by_name["Implementing bundles same-file tasks"]
        assert imp["winner"] == "skill"
        assert imp["scores"]["skill"] >= 1
        # "Reviewer catches regressions in review phase" — matches `reviewer`,
        # `reviewing` (via fragment), `review .* phase`, plus `validates`.
        rev = by_name["Reviewer catches regressions in review phase"]
        assert rev["winner"] == "agent"


class TestGenerateContract:
    """Task 4a.5 (3): generate routes to per-target generator; one test per target."""

    def _seed_enumerate(self, contract_project: Path, sandbox: Path) -> None:
        rc, out, _ = _run_cli(
            "enumerate",
            "--sandbox",
            str(sandbox),
            "--kb-dir",
            str(contract_project / "docs" / "knowledge-bank"),
            "--project-root",
            str(contract_project),
            cwd=contract_project,
        )
        assert rc == 0, out

    def test_generate_skill_target(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sb_gen_skill"
        self._seed_enumerate(contract_project, sandbox)
        meta = {
            "skill_name": "implementing",
            "section_heading": "## Rules",
            "insertion_mode": "append-to-list",
        }
        meta_path = sandbox / "skill_meta.json"
        meta_path.write_text(json.dumps(meta))
        rc, out, _ = _run_cli(
            "generate",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "Implementing bundles same-file tasks",
            "--target-type",
            "skill",
            "--target-meta-json",
            str(meta_path),
            cwd=contract_project,
        )
        assert rc == 0, out
        status = _assert_single_line_json(out)
        assert status["status"] == "ok"
        assert "diff_plan_path" in status
        assert "edit_count" in status
        assert status["edit_count"] == 1
        plan = json.loads(
            Path(status["diff_plan_path"]).read_text(encoding="utf-8")
        )
        assert plan["target_type"] == "skill"
        assert len(plan["edits"]) == 1
        assert plan["edits"][0]["action"] == "modify"
        assert "<!-- Promoted:" in plan["edits"][0]["after"]

    def test_generate_agent_target(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sb_gen_agent"
        self._seed_enumerate(contract_project, sandbox)
        meta = {
            "agent_name": "code-reviewer",
            "section_heading": "## Checks",
            "insertion_mode": "append-to-list",
        }
        meta_path = sandbox / "agent_meta.json"
        meta_path.write_text(json.dumps(meta))
        rc, out, _ = _run_cli(
            "generate",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "Reviewer catches regressions in review phase",
            "--target-type",
            "agent",
            "--target-meta-json",
            str(meta_path),
            cwd=contract_project,
        )
        assert rc == 0, out
        status = _parse_last_json_line(out)
        assert status["status"] == "ok"
        plan = json.loads(
            Path(status["diff_plan_path"]).read_text(encoding="utf-8")
        )
        assert plan["target_type"] == "agent"

    def test_generate_command_target(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sb_gen_command"
        self._seed_enumerate(contract_project, sandbox)
        meta = {
            "command_name": "wrap-up",
            "step_id": "5a",
            "insertion_mode": "append-to-list",
        }
        meta_path = sandbox / "cmd_meta.json"
        meta_path.write_text(json.dumps(meta))
        rc, out, _ = _run_cli(
            "generate",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "Implementing bundles same-file tasks",
            "--target-type",
            "command",
            "--target-meta-json",
            str(meta_path),
            cwd=contract_project,
        )
        assert rc == 0, out
        status = _parse_last_json_line(out)
        assert status["status"] == "ok"
        plan = json.loads(
            Path(status["diff_plan_path"]).read_text(encoding="utf-8")
        )
        assert plan["target_type"] == "command"

    def test_generate_hook_target(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sb_gen_hook"
        self._seed_enumerate(contract_project, sandbox)
        meta = {
            "feasibility": {
                "event": "PreToolUse",
                "tools": ["Edit"],
                "check_kind": "file_path_regex",
                "check_expression": r"^[^/]",
            }
        }
        meta_path = sandbox / "hook_meta.json"
        meta_path.write_text(json.dumps(meta))
        rc, out, _ = _run_cli(
            "generate",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "Implementing bundles same-file tasks",
            "--target-type",
            "hook",
            "--target-meta-json",
            str(meta_path),
            cwd=contract_project,
        )
        assert rc == 0, out
        status = _parse_last_json_line(out)
        assert status["status"] == "ok"
        assert status["edit_count"] == 3
        plan = json.loads(
            Path(status["diff_plan_path"]).read_text(encoding="utf-8")
        )
        assert plan["target_type"] == "hook"
        assert len(plan["edits"]) == 3
        # target_path is the .sh file, not hooks.json.
        assert plan["target_path"].endswith(".sh")
        assert "hooks.json" not in plan["target_path"]

    def test_generate_invalid_meta_returns_exit2(
        self, contract_project: Path, tmp_path: Path
    ):
        """Schema-invalid target_meta → non-zero exit code 2 + status=error."""
        sandbox = tmp_path / "sb_gen_bad"
        self._seed_enumerate(contract_project, sandbox)
        bad_meta = {
            "feasibility": {
                "event": "PreToolUse",
                "tools": [],  # empty tools → validation error
                "check_kind": "file_path_regex",
                "check_expression": "^[^/]",
            }
        }
        meta_path = sandbox / "bad_meta.json"
        meta_path.write_text(json.dumps(bad_meta))
        rc, out, _ = _run_cli(
            "generate",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "Implementing bundles same-file tasks",
            "--target-type",
            "hook",
            "--target-meta-json",
            str(meta_path),
            cwd=contract_project,
        )
        assert rc == 2, (rc, out)
        status = _assert_single_line_json(out)
        assert status["status"] == "error"
        assert "reason" in status

    def test_generate_entry_not_found_returns_nonzero(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sb_gen_404"
        self._seed_enumerate(contract_project, sandbox)
        meta_path = sandbox / "any.json"
        meta_path.write_text(json.dumps({"skill_name": "x"}))
        rc, out, _ = _run_cli(
            "generate",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "NonexistentEntry",
            "--target-type",
            "skill",
            "--target-meta-json",
            str(meta_path),
            cwd=contract_project,
        )
        assert rc != 0
        status = _assert_single_line_json(out)
        assert status["status"] == "error"


class TestApplyContract:
    """Task 4a.5 (4): apply reads diff_plan.json, writes apply_result.json."""

    def _prepare_plan(
        self, contract_project: Path, tmp_path: Path
    ) -> Path:
        """Seed enumerate + generate (skill target) → returns sandbox dir."""
        sandbox = tmp_path / "sb_apply"
        # enumerate
        rc, out, _ = _run_cli(
            "enumerate",
            "--sandbox",
            str(sandbox),
            "--kb-dir",
            str(contract_project / "docs" / "knowledge-bank"),
            "--project-root",
            str(contract_project),
            cwd=contract_project,
        )
        assert rc == 0, out
        # generate skill
        meta = {
            "skill_name": "implementing",
            "section_heading": "## Rules",
            "insertion_mode": "append-to-list",
        }
        meta_path = sandbox / "skill_meta.json"
        meta_path.write_text(json.dumps(meta))
        rc, out, _ = _run_cli(
            "generate",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "Implementing bundles same-file tasks",
            "--target-type",
            "skill",
            "--target-meta-json",
            str(meta_path),
            cwd=contract_project,
        )
        assert rc == 0, out
        return sandbox

    def test_apply_skill_target_happy_path(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = self._prepare_plan(contract_project, tmp_path)
        # Skip the real ./validate.sh baseline run (contract_project is a
        # synthetic fixture; a full validate.sh invocation is out of scope
        # for this CLI-contract test). Behavior of the baseline path itself
        # is covered in test_apply.py::TestBaselineDeltaValidate.
        rc, out, _ = _run_cli(
            "apply",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "Implementing bundles same-file tasks",
            cwd=contract_project,
            env_extra={"PATTERN_PROMOTION_SKIP_VALIDATE_SH": "1"},
        )
        assert rc == 0, out
        status = _assert_single_line_json(out)
        assert status["status"] == "ok"
        assert "result_path" in status
        assert Path(status["result_path"]).is_file()
        result = json.loads(
            Path(status["result_path"]).read_text(encoding="utf-8")
        )
        assert result["success"] is True
        assert result["rolled_back"] is False
        # Target SKILL.md now contains the Promoted marker.
        skill_md = (
            contract_project / "plugins" / "pd" / "skills" / "implementing"
            / "SKILL.md"
        )
        assert "<!-- Promoted:" in skill_md.read_text()

    def test_apply_emits_error_status_on_rollback(
        self, contract_project: Path, tmp_path: Path
    ):
        """Stage 1 failure → non-zero exit, status=error, no file modifications."""
        sandbox = self._prepare_plan(contract_project, tmp_path)
        # Corrupt the diff_plan so modify target does not exist: point at a
        # file that was never on disk.
        dp_path = sandbox / "diff_plan.json"
        dp = json.loads(dp_path.read_text())
        dp["edits"][0]["path"] = str(contract_project / "does_not_exist.md")
        dp["target_path"] = dp["edits"][0]["path"]
        dp_path.write_text(json.dumps(dp))

        rc, out, _ = _run_cli(
            "apply",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "Implementing bundles same-file tasks",
            cwd=contract_project,
            env_extra={"PATTERN_PROMOTION_SKIP_VALIDATE_SH": "1"},
        )
        assert rc == 3, (rc, out)
        status = _assert_single_line_json(out)
        assert status["status"] == "error"
        assert "stage" in status
        assert "reason" in status
        assert "result_path" in status


class TestRoundTripContract:
    """Task 4a.5 (6): end-to-end enumerate → classify → generate → apply.

    Each stage's stdout is valid parseable JSON; each stage's sandbox artifact
    feeds the next.
    """

    def test_full_pipeline_skill_target(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sb_rt"

        # 1) enumerate
        rc, out, _ = _run_cli(
            "enumerate",
            "--sandbox",
            str(sandbox),
            "--kb-dir",
            str(contract_project / "docs" / "knowledge-bank"),
            "--project-root",
            str(contract_project),
            cwd=contract_project,
        )
        assert rc == 0, out
        enum_status = _assert_single_line_json(out)
        assert enum_status["status"] == "ok"
        assert enum_status["count"] == 2

        # 2) classify
        rc, out, _ = _run_cli(
            "classify", "--sandbox", str(sandbox), cwd=contract_project
        )
        assert rc == 0, out
        classify_status = _assert_single_line_json(out)
        assert classify_status["status"] == "ok"
        classifications = json.loads(
            Path(classify_status["classifications_path"]).read_text(
                encoding="utf-8"
            )
        )
        # Find the skill-class winner and use it downstream.
        skill_entry = next(
            (c for c in classifications if c["winner"] == "skill"), None
        )
        assert skill_entry is not None, classifications

        # 3) generate
        meta = {
            "skill_name": "implementing",
            "section_heading": "## Rules",
            "insertion_mode": "append-to-list",
        }
        meta_path = sandbox / "rt_meta.json"
        meta_path.write_text(json.dumps(meta))
        rc, out, _ = _run_cli(
            "generate",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            skill_entry["entry_name"],
            "--target-type",
            "skill",
            "--target-meta-json",
            str(meta_path),
            cwd=contract_project,
        )
        assert rc == 0, out
        gen_status = _assert_single_line_json(out)
        assert gen_status["status"] == "ok"
        assert gen_status["edit_count"] == 1

        # 4) apply — skip real validate.sh on the synthetic contract project
        # (covered separately in test_apply.py::TestBaselineDeltaValidate).
        rc, out, _ = _run_cli(
            "apply",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            skill_entry["entry_name"],
            cwd=contract_project,
            env_extra={"PATTERN_PROMOTION_SKIP_VALIDATE_SH": "1"},
        )
        assert rc == 0, out
        apply_status = _assert_single_line_json(out)
        assert apply_status["status"] == "ok"
        result = json.loads(
            Path(apply_status["result_path"]).read_text(encoding="utf-8")
        )
        assert result["success"] is True
        assert result["rolled_back"] is False

        # Sandbox artifacts all present.
        for name in ("entries.json", "classifications.json", "diff_plan.json",
                     "apply_result.json"):
            assert (sandbox / name).is_file(), name


class TestSerializationContract:
    """Task 4a.5 structural: single-line stdout JSON per subprocess call."""

    def test_enumerate_stdout_is_single_line(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sl_enum"
        rc, out, _ = _run_cli(
            "enumerate",
            "--sandbox",
            str(sandbox),
            "--kb-dir",
            str(contract_project / "docs" / "knowledge-bank"),
            "--project-root",
            str(contract_project),
            cwd=contract_project,
        )
        assert rc == 0
        # Exactly one non-empty stdout line (the status object).
        nonempty = [ln for ln in out.splitlines() if ln.strip()]
        assert len(nonempty) == 1, nonempty
        status = json.loads(nonempty[0])
        # No embedded newlines within the JSON line (compact output).
        assert "\n" not in nonempty[0]
        assert status["status"] == "ok"

    def test_generate_invalid_meta_single_line_error(
        self, contract_project: Path, tmp_path: Path
    ):
        sandbox = tmp_path / "sl_gen_bad"
        # seed enumerate
        rc, out, _ = _run_cli(
            "enumerate",
            "--sandbox",
            str(sandbox),
            "--kb-dir",
            str(contract_project / "docs" / "knowledge-bank"),
            "--project-root",
            str(contract_project),
            cwd=contract_project,
        )
        assert rc == 0
        meta_path = sandbox / "bad.json"
        meta_path.write_text("{\"feasibility\": {\"event\": \"bad\"}}")
        rc, out, _ = _run_cli(
            "generate",
            "--sandbox",
            str(sandbox),
            "--entry-name",
            "Implementing bundles same-file tasks",
            "--target-type",
            "hook",
            "--target-meta-json",
            str(meta_path),
            cwd=contract_project,
        )
        assert rc == 2
        nonempty = [ln for ln in out.splitlines() if ln.strip()]
        assert len(nonempty) == 1, nonempty
        assert json.loads(nonempty[0])["status"] == "error"
