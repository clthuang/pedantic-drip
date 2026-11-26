"""Tests for pd-review-prompt and stage-bars.md (shape.md ReviewPromptCLI, StageBars; plan Task 10, cases C1 to C6, C12)."""
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "pd-review-prompt"
PLUGIN = SCRIPT.parent.parent
SCHEMA_LINE = "Return only a JSON object matching this schema."


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def section(path, heading):
    """The `## heading` section of a markdown file, heading line included, up to the next `## ` heading."""
    text = (PLUGIN / path).read_text()
    m = re.search(rf"^{re.escape(heading)}\n.*?(?=^## |\Z)", text, re.S | re.M)
    assert m, heading
    return m.group(0)


def checklist(skill):
    return section(f"skills/{skill}/SKILL.md", "## Review checklist")


def schema_block():
    body = section("references/workflow-results.md", "## The review call")
    return re.search(r"```json\n(.*?)```", body, re.S).group(1)


def item_dir(pd_repo, stage_line):
    d = pd_repo.root / "docs" / "dev_artifacts" / "workitems" / pd_repo.id
    readme = d / "README.md"
    text = re.sub(r"^stage:.*\n", "", readme.read_text(), flags=re.M)
    if stage_line:
        text = text.replace("\nstatus:", f"\n{stage_line}\nstatus:", 1)
    readme.write_text(text)
    return str(d)


def test_c1_mvp_prompt_in_order(pd_repo):
    r = run("verifying", item_dir(pd_repo, "stage: mvp"))
    assert r.returncode == 0, r.stderr
    parts = ["Stage: mvp\n", checklist("verifying"), section("references/stage-bars.md", "## mvp"),
             SCHEMA_LINE + "\n", schema_block()]
    pos = 0
    for part in parts:
        i = r.stdout.find(part, pos)
        assert i >= 0, part
        pos = i + len(part)
    assert r.stdout.startswith("Stage: mvp\n")


def test_c2_production_prompt(pd_repo):
    r = run("verifying", item_dir(pd_repo, "stage: production"))
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == "Stage: production"
    assert section("references/stage-bars.md", "## production").strip() in r.stdout
    mvp_lines = [ln for ln in section("references/stage-bars.md", "## mvp").splitlines()[1:] if ln.strip()]
    assert mvp_lines and not any(ln in r.stdout for ln in mvp_lines)


def test_c3_no_stage_key_reads_production(pd_repo):
    r = run("verifying", item_dir(pd_repo, None))
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == "Stage: production"


def test_c4_two_skills(pd_repo):
    r = run("designing", "planning", item_dir(pd_repo, "stage: mvp"))
    assert r.returncode == 0, r.stderr
    d, p = checklist("designing"), checklist("planning")
    assert r.stdout.index(d) < r.stdout.index(p)
    assert r.stdout.count("## mvp") == 1 and r.stdout.count("## production") == 0
    assert r.stdout.count(SCHEMA_LINE) == 1 and r.stdout.count(schema_block()) == 1


def test_c5_errors(pd_repo, tmp_path):
    d = item_dir(pd_repo, "stage: mvp")
    for args in (("brainstorming", d), ("verifying", str(tmp_path))):
        r = run(*args)
        assert r.returncode == 1 and r.stdout == "" and r.stderr.startswith("pd-review-prompt:"), args
    assert run().returncode == 2


def test_c6_stage_bars_sections():
    text = (PLUGIN / "references" / "stage-bars.md").read_text()
    assert re.findall(r"^## .*$", text, re.M) == ["## mvp", "## production"]
    mvp = " ".join(section("references/stage-bars.md", "## mvp").split())
    for phrase in ("A blocker only when", "an expectation in shape.md fails on the input it names",
                   "data is lost or exposed", "a security hole opens", "severity warning", "category harden-later",
                   "security review", "risk: security", "R0", "QB<n>", "token budget", "validation at trust boundaries"):
        assert phrase in mvp, phrase
    production = " ".join(section("references/stage-bars.md", "## production").split()).lower()
    assert "each checklist item applies as written" in production


def test_c12_self_test():
    assert run("--self-test").returncode == 0
