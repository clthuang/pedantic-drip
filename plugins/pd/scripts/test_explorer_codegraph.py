"""Pins the codebase-explorer's CodeGraph-first text, its validate.sh role and the rename checklist line."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "plugins/pd/agents/codebase-explorer.md"
DESIGNING = ROOT / "plugins/pd/skills/designing/SKILL.md"
PLANNING = ROOT / "plugins/pd/skills/planning/SKILL.md"
CODEGRAPH_TOOL = "mcp__codegraph__codegraph_explore"
LOCALES = ["C", "en_US.UTF-8"]

# Verbatim from shape.md, Design, RenameChecklistLine.
RENAME_CHECKLIST_LINE = (
    "- **Renames and store moves list their surfaces:** a rename or a store move (a file, config key or table moving "
    "where its state lives) lists every surface it touches, from a call-graph query of the changed symbol "
    "(`codegraph_explore`, or `codegraph explore` from a shell, when `.codegraph/` exists) plus a grep for each old "
    "name; the artifact records the query and grep commands with their hits (file:line), each marked a surface to "
    "change or history left as it is (a released CHANGELOG section, a done or abandoned work item, a retro, an "
    "archive; anything else, the open backlog and `[Unreleased]` included, is a surface). The reviewer re-runs the "
    "greps, and the query where its tools allow, and checks each recorded hit at file:line; a surface in its output "
    "that the list lacks is a blocker, and a disputed mark is a finding like any other."
)


def section(text, heading):
    """The text from `heading` to the next `## ` heading."""
    match = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, f"no section {heading}"
    return match.group(1)


def frontmatter_tools(text):
    line = re.search(r"^tools:\s*\[(.*)\]\s*$", text, re.M).group(1)
    return [t.strip() for t in line.split(",")]


def set_tools(path, tools):
    text = path.read_text()
    path.write_text(re.sub(r"^tools:.*$", f"tools: [{', '.join(tools)}]", text, count=1, flags=re.M))


@pytest.fixture
def agents_copy(tmp_path):
    for md in (ROOT / "plugins/pd/agents").glob("*.md"):
        shutil.copy(md, tmp_path / md.name)
    return tmp_path


def roles(directory, locale):
    function = subprocess.run(
        ["sed", "-n", "/^agent_roles_errors()/,/^}/p", str(ROOT / "validate.sh")],
        capture_output=True, text=True, check=True).stdout
    result = subprocess.run(
        ["bash", "-c", f'{function}\nagent_roles_errors "$1"', "bash", str(directory)],
        capture_output=True, text=True, env={**os.environ, "LC_ALL": locale})
    return [line for line in result.stdout.splitlines() if line.strip()]


def test_c1_explorer_tools_are_exactly_the_four():
    tools = frontmatter_tools(AGENT.read_text())
    assert set(tools) == {"Glob", "Grep", "Read", CODEGRAPH_TOOL} and len(tools) == 4


@pytest.mark.parametrize("locale", LOCALES)
def test_c2_validate_passes_with_nine_fixture_checks(locale):
    result = subprocess.run(["./validate.sh"], cwd=ROOT, capture_output=True, text=True,
                            env={**os.environ, "LC_ALL": locale})
    assert result.returncode == 0, result.stdout[-2000:]
    assert "the failing fixture fails all 9 checks" in result.stdout


def test_c2_validate_holds_no_stale_eight():
    script = (ROOT / "validate.sh").read_text()
    assert "of 8 errors" not in script and "all 8 checks" not in script


def test_c3_tool_order_and_locale_do_not_matter(agents_copy):
    reordered = [CODEGRAPH_TOOL, "Read", "Grep", "Glob"]
    set_tools(agents_copy / "codebase-explorer.md", reordered)
    assert roles(agents_copy, "C") == [] and roles(agents_copy, "en_US.UTF-8") == []
    set_tools(agents_copy / "codebase-explorer.md", reordered + ["Write"])
    for locale in LOCALES:
        lines = roles(agents_copy, locale)
        assert len(lines) == 1 and "codebase-explorer" in lines[0]


def test_c4_explorer_role_rejects_write_and_the_old_list(agents_copy):
    explorer = agents_copy / "codebase-explorer.md"
    set_tools(explorer, ["Glob", "Grep", "Read", "Write"])
    lines = roles(agents_copy, "C")
    assert len(lines) == 1 and "codebase-explorer" in lines[0] and "Write" in lines[0]
    set_tools(explorer, ["Glob", "Grep", "Read"])
    lines = roles(agents_copy, "C")
    assert len(lines) == 1 and "codebase-explorer" in lines[0] and "(has Glob,Grep,Read)" in lines[0]


def numbered_steps(block):
    return re.findall(r"^\d+\. .*?(?=^\d+\. |\Z)", block, re.M | re.S)


def test_c5_research_process_asks_codegraph_first():
    text = AGENT.read_text()
    process = section(text, "## Research Process")
    steps = numbered_steps(process)
    assert "Parse the query" in steps[0]
    assert not any(tool in steps[0] for tool in ("Glob", "Grep", "Read", "codegraph"))
    names_tool = [i for i, s in enumerate(steps) if re.search(r"Glob|Grep|Read|codegraph_explore", s)]
    first = names_tool[0]
    assert CODEGRAPH_TOOL in steps[first]
    assert not re.search(r"Glob|Grep", steps[first])
    assert all(first < i for i, s in enumerate(steps) if re.search(r"Glob|Grep", s))
    for literal in ("tool not in session", "no index", "error: ", "timeout", ".codegraph/"):
        assert literal in process, literal
    assert any("Glob, Grep and Read" in s and "what CodeGraph didn't answer" in s and "unavailable" in s
               for s in steps)
    strategies = section(text, "## Search Strategies")
    first_feature_item = re.search(r"For features:\n\s*-\s*(.*)", strategies).group(1)
    assert "codegraph_explore" in first_feature_item
    assert "Read files without searching first (CodeGraph, Glob or Grep)" in text


def test_c10_no_symbol_query_and_several_calls():
    process = section(AGENT.read_text(), "## Research Process")
    for literal in ("naming no symbol", "answered", "returned results", "first call's reason"):
        assert literal in process, literal


def test_c11_own_output_shape_leaves_out_search():
    text = AGENT.read_text()
    assert "its own output shape" in text and 'leave out "search"' in text


def test_c6_output_examples_gain_only_search():
    block = section(AGENT.read_text(), "## Output Format")
    examples = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", block, re.S)]
    assert len(examples) == 2
    for example in examples:
        assert set(example) == {"findings", "no_findings_reason", "search"}
        for finding in example["findings"]:
            assert set(finding) == {"finding", "source", "relevance"}
    assert examples[0]["findings"][0]["relevance"] == "high | medium | low"
    assert examples[0]["search"] == ("codegraph | codegraph, then grep | "
                                     "grep (codegraph unavailable: <reason>)")
    assert examples[1]["search"] == "grep (codegraph unavailable: no index)"


def test_c7_stale_index_rule():
    text = AGENT.read_text()
    for literal in ("edited since the last index sync", "auto-sync is DISABLED",
                    "Read each file a finding rests on before citing it"):
        assert literal in text, literal


@pytest.mark.parametrize("skill", [DESIGNING, PLANNING], ids=["designing", "planning"])
def test_c8_rename_checklist_line(skill):
    checklist = section(skill.read_text(), "## Review checklist")
    lines = [l for l in checklist.splitlines()
             if l.startswith("- **Renames and store moves list their surfaces:**")]
    assert lines == [RENAME_CHECKLIST_LINE]


def test_c9_ci_and_changelog():
    ci = (ROOT / ".github/workflows/ci.yml").read_text().splitlines()
    pytest_line = [l for l in ci if "uv run --project plugins/pd pytest" in l]
    assert pytest_line and "plugins/pd/scripts/test_explorer_codegraph.py" in pytest_line[0]
    unreleased = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", (ROOT / "CHANGELOG.md").read_text(),
                           re.M | re.S).group(1)
    assert any("codebase-explorer" in l and "CodeGraph" in l for l in unreleased.splitlines())


def test_c12_reply_is_the_json_object_alone():
    block = section(AGENT.read_text(), "## Output Format")
    assert "Reply with the JSON object alone" in block
    assert "no text before or after it" in block


def test_c12_reply_carries_no_code_fence():
    # Live replies at 669643b6 came back wrapped in a ```json fence, which fails json.loads (Q2).
    block = section(AGENT.read_text(), "## Output Format")
    assert "no ```json fence" in block
