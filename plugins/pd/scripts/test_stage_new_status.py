"""Tests for stage in pd-new, pd-status and pd-init (plan Task 8, cases C1 to C10)."""
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
HOOKS = SCRIPTS.parent / "hooks"
sys.path.insert(0, str(SCRIPTS))
from pd_common import make_repo, split_frontmatter  # noqa: E402


def run(cwd, script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=cwd, capture_output=True, text=True)


def set_config(root, *lines):
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "pd.local.md").write_text("\n".join(["---", "artifacts_root: docs/dev_artifacts", "sop: 1", *lines, "---", ""]))


def workitems(root):
    return sorted(p.name for p in (root / "docs/dev_artifacts/workitems").iterdir())


def new_item(root, title, *args):
    r = run(root, "pd-new", "workitem", title, *args)
    return r, (root / r.stdout.strip() / "README.md" if r.returncode == 0 else None)


def stage_of(readme):
    return split_frontmatter(readme.read_text())[0].get("stage")


def test_c1_config_stage_mvp(pd_repo):
    set_config(pd_repo.root, "stage: mvp")
    r, readme = new_item(pd_repo.root, "T")
    assert r.returncode == 0 and stage_of(readme) == "mvp"


def test_c2_default_production(pd_repo):
    set_config(pd_repo.root)
    r, readme = new_item(pd_repo.root, "T")
    assert r.returncode == 0 and stage_of(readme) == "production"
    (pd_repo.root / ".claude" / "pd.local.md").unlink()
    r, readme = new_item(pd_repo.root, "No config")
    assert r.returncode == 0 and stage_of(readme) == "production"


def test_c3_flag_overrides_config(pd_repo):
    set_config(pd_repo.root, "stage: production")
    r, readme = new_item(pd_repo.root, "T", "--stage", "mvp")
    assert r.returncode == 0 and stage_of(readme) == "mvp"


def test_c4_bad_flag_value(pd_repo):
    before = workitems(pd_repo.root)
    r = run(pd_repo.root, "pd-new", "workitem", "T", "--stage", "beta")
    assert r.returncode == 2 and "mvp" in r.stderr and "production" in r.stderr
    assert workitems(pd_repo.root) == before


def test_c5_bad_config_value(pd_repo):
    set_config(pd_repo.root, "stage: beta")
    before = workitems(pd_repo.root)
    r = run(pd_repo.root, "pd-new", "workitem", "T")
    assert r.returncode == 1 and r.stderr.startswith("pd-new: refused:")
    assert "stage" in r.stderr and "mvp" in r.stderr and "production" in r.stderr
    assert workitems(pd_repo.root) == before


def test_c6_stage_on_backlog_refused(pd_repo):
    backlog = pd_repo.root / "docs/dev_artifacts/backlog.md"
    before = backlog.read_text() if backlog.exists() else None
    r = run(pd_repo.root, "pd-new", "backlog", "x", "--stage", "mvp")
    assert r.returncode == 1 and r.stderr.startswith("pd-new: refused:") and "--stage" in r.stderr
    assert (backlog.read_text() if backlog.exists() else None) == before


def add_item(root, id_, status, stage):
    d = root / "docs/dev_artifacts/workitems" / id_
    d.mkdir(parents=True)
    stage_line = f"stage: {stage}\n" if stage else ""
    (d / "README.md").write_text(f"---\nid: {id_}\ntype: workitem\ntitle: {id_}\nstatus: {status}\n"
                                 f"phase: implement\nmode: standard\n{stage_line}---\n# {id_}\n\n## Now\n\nn\n\n## Links\n")
    (d / "log.md").write_text("")


def table_of(out):
    lines = out.split("\n")
    head = next(i for i, l in enumerate(lines) if l.startswith("STATUS"))
    rows = []
    for l in lines[head + 1:]:
        if not l.strip():
            break
        rows.append(l.split())
    return lines[head], rows, lines


def test_c7_stage_column_and_footer(pd_repo):
    root = pd_repo.root
    set_config(root, "stage: production")
    add_item(root, "2026-11-01-aa-open-mvp", "active", "mvp")
    add_item(root, "2026-11-01-bb-open-prod", "active", "production")
    add_item(root, "2026-11-01-cc-done-mvp", "done", "mvp")
    assert run(root, "pd-new", "brainstorm", "idea").returncode == 0
    head, rows, lines = table_of(run(root, "pd-status").stdout)
    assert head.split() == ["STATUS", "PHASE", "TYPE", "ID", "STAGE", "NOW"]
    stage = {r[3]: r[4] for r in rows}
    assert stage["2026-11-01-aa-open-mvp"] == "mvp*"
    assert stage["2026-11-01-bb-open-prod"] == "production"
    assert stage["2026-11-01-cc-done-mvp"] == "mvp"
    assert [r[4] for r in rows if r[2] == "brainstorm"] == ["-"]
    assert "* stage differs from the project default (production)" in lines


def test_c8_missing_key_reads_production(pd_repo):
    root = pd_repo.root
    set_config(root, "stage: production")
    add_item(root, "2026-11-01-dd-legacy", "active", None)
    _, rows, lines = table_of(run(root, "pd-status").stdout)
    assert {r[3]: r[4] for r in rows}["2026-11-01-dd-legacy"] == "production"
    assert not any(l.startswith("* stage differs") for l in lines)


def test_c9_pd_init_writes_stage(tmp_path):
    root = make_repo(tmp_path / "fresh")
    r = run(root, "pd-init")
    assert r.returncode == 0, r.stderr + r.stdout
    assert split_frontmatter((root / ".claude/pd.local.md").read_text())[0]["stage"] == "production"


def test_c10_self_tests():
    for script in ("pd-new", "pd-status", "pd-init"):
        r = run(SCRIPTS, script, "--self-test")
        assert r.returncode == 0, (script, r.stdout + r.stderr)
    for suite in ("test-pd-commit-lint.sh", "test-pd-stop-gate.sh"):
        r = subprocess.run(["bash", str(HOOKS / "tests" / suite)], capture_output=True, text=True)
        assert r.returncode == 0, (suite, r.stdout[-500:] + r.stderr[-500:])
