"""Severity `suggestion` renamed to `note` in reviewer agents and commands (B42)."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AGENTS = ROOT / "plugins/pd/agents"
COMMANDS = ROOT / "plugins/pd/commands"
SEVERITY_AGENTS = ["security-reviewer.md", "ds-analysis-reviewer.md", "ds-code-reviewer.md"]
OLD_SEVERITY = re.compile(r"blocker \| warning \| suggestion|\| suggestion \|")


def text(path):
    return path.read_text()


def test_c1_severity_enums_say_note():
    for name in SEVERITY_AGENTS:
        body = text(AGENTS / name)
        assert not OLD_SEVERITY.search(body), name
        expected = 2 if name == "ds-analysis-reviewer.md" else 1
        assert body.count("blocker | warning | note") == expected, name


def test_c2_retro_facilitator_distribution():
    body = text(AGENTS / "retro-facilitator.md")
    assert "blocker vs warning vs note" in body
    assert "blocker vs warning vs suggestion" not in body


def test_c3_commands_list_notes():
    for name in ["review-ds-code.md", "review-ds-analysis.md"]:
        body = text(COMMANDS / name)
        assert "List notes" in body, name
        assert "List suggestions" not in body, name


def test_c4_fix_text_field_kept():
    for name in SEVERITY_AGENTS:
        assert '"suggestion": "How to fix it"' in text(AGENTS / name), name


def test_c5_remaining_suggestion_hits_are_allowed():
    hits = []
    for base in (AGENTS, COMMANDS):
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            for number, line in enumerate(text(path).splitlines(), 1):
                if "suggestion" not in line or '"suggestion":' in line:
                    continue
                if "Feature suggestion" in line and path.name in ("design-reviewer.md", "plan-reviewer.md"):
                    continue
                hits.append(f"{path.name}:{number}:{line.strip()}")
    assert hits == []


def test_c6_hook_suite_passes():
    result = subprocess.run(
        ["bash", "plugins/pd/hooks/tests/test-hooks.sh"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
