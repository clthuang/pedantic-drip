"""Shared parsing for pd's scripts: the frontmatter's YAML subset, the config,
items, sections and log.md entries (plan Part B §5, §6, §12).

Stdlib only, so pd-lint runs offline inside the commit hook.
Self-test: python3 pd_common.py --self-test
"""
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

TYPES = ("feature", "plan", "brainstorm", "rca")
TYPE_DIRS = {"feature": "features", "plan": "plans", "brainstorm": "brainstorms", "rca": "rca"}
STATUSES = ("draft", "active", "blocked", "done", "abandoned")
PHASES = ("specify", "design", "create-plan", "implement", "verify", "finish")
MODES = ("standard", "small", "express")
RISKS = ("security", "migration")
ENTRY_KINDS = ("decision", "phase", "review", "qa", "gate", "run", "handoff",
               "replan", "metrics", "defect", "note", "capped")
DEFAULT_ARTIFACTS_ROOT = "docs/dev_artifacts"
CONFIG_DEFAULTS = {
    "artifacts_root": DEFAULT_ARTIFACTS_ROOT, "base_branch": "auto", "tracker": "none",
    "small_feature_tasks": "3", "many_files": "10",
}

ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
HEADING_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})([+-]\d{2}:\d{2}) ([a-z]+)(?:-(\d+))?(?: (.*))?$")
# A reference to an entry, or to one id inside it: review-2@2026-10-14 11:30+08:00#R1
REF_RE = re.compile(r"\b([a-z]+(?:-\d+)?)@(\d{4}-\d{2}-\d{2} \d{2}:\d{2}[+-]\d{2}:\d{2})(?:#([A-Za-z]+\d+))?")
ISSUE_RE = re.compile(r"^- ([A-Za-z]+\d+) (blocker|warning|note) (\S+?):(\d+) — (.+)$")
STOPWORDS = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "at",
             "from", "is", "are", "be", "as", "into", "via", "per", "its", "it", "this", "that"}
_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):(?:\s+(.*))?$")


# --- the YAML subset ---------------------------------------------------------

def _strip_comment(line):
    """Drop a ` # comment`; a `#` inside quotes or a word (backlog#id) stays."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'" and (i == 0 or line[i - 1] in " \t[,:-"):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def _split_flow(inner):
    parts, cur, quote = [], "", None
    for ch in inner:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch == ",":
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts]


def scalar(value):
    v = (value or "").strip()
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [scalar(x) for x in _split_flow(inner)] if inner else []
    return v


def parse_yaml(lines):
    """`key: scalar`, `key: [flow, list]`, and `key:` followed by `- item` lines,
    where an item is a scalar or a one-level mapping (`- feature: x` / `  after: [y]`)."""
    data, key = {}, None
    for n, raw in enumerate(lines, 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if indent == 0:
            m = _KEY_RE.match(text)
            if not m:
                raise ValueError(f"line {n}: not `key: value`: {raw.strip()!r}")
            key = m.group(1)
            data[key] = scalar(m.group(2)) if m.group(2) else None
        elif text == "-" or text.startswith("- "):
            if key is None or (data[key] is not None and not isinstance(data[key], list)):
                raise ValueError(f"line {n}: list item outside a list: {raw.strip()!r}")
            if data[key] is None:
                data[key] = []
            item = text[1:].strip()
            m = _KEY_RE.match(item)
            data[key].append({m.group(1): scalar(m.group(2))} if m else scalar(item))
        else:
            m = _KEY_RE.match(text)
            items = data.get(key) if key else None
            if not (m and isinstance(items, list) and items and isinstance(items[-1], dict)):
                raise ValueError(f"line {n}: unexpected indented line: {raw.strip()!r}")
            items[-1][m.group(1)] = scalar(m.group(2))
    return data


def split_frontmatter(text):
    """(frontmatter dict or None, body, the body's first line number). Raises ValueError on bad YAML."""
    if not text.startswith("---\n"):
        return None, text, 1
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return parse_yaml(lines[1:i]), "\n".join(lines[i + 1:]), i + 2
    raise ValueError("frontmatter has no closing ---")


# --- repository, config, items ------------------------------------------------

def git(args, cwd, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip() if r.returncode == 0 else None


def repo_root(start="."):
    top = git(["rev-parse", "--show-toplevel"], start, check=False)
    return Path(top) if top else Path(start).resolve()


def load_config(root):
    cfg = dict(CONFIG_DEFAULTS)
    path = Path(root) / ".claude" / "pd.local.md"
    if path.is_file():
        fm, _, _ = split_frontmatter(path.read_text())
        cfg.update({k: v for k, v in (fm or {}).items() if v is not None})
    return cfg


def artifacts_dir(root, cfg):
    return Path(root) / str(cfg.get("artifacts_root") or DEFAULT_ARTIFACTS_ROOT)


def is_unadopted(root, cfg):
    """An old-layout pd project: docs/features/ exists and the config lacks `sop: 1` (Part B §12)."""
    return (Path(root) / "docs" / "features").is_dir() and str(cfg.get("sop")) != "1"


def as_list(value):
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


def find_items(art):
    """Yield (type, id, control-file path) for every item under the artifacts root."""
    art = Path(art)
    for type_, sub in TYPE_DIRS.items():
        base = art / sub
        if not base.is_dir():
            continue
        if type_ == "feature":
            for d in sorted(p for p in base.iterdir() if p.is_dir()):
                yield type_, d.name, d / "README.md"
        else:
            for f in sorted(base.glob("*.md")):
                yield type_, f.stem, f


def blank_fences(text):
    """Blank fenced code blocks and HTML comments, keeping line numbers."""
    out, fence, comment = [], False, False
    for line in text.split("\n"):
        s = line.strip()
        if comment:
            out.append("")
            comment = "-->" not in s
            continue
        if s.startswith("```"):
            fence = not fence
            out.append("")
            continue
        if fence:
            out.append("")
            continue
        if s.startswith("<!--"):
            comment = "-->" not in s
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def sections(body):
    """`## Name` -> its text, fences and comments ignored for finding headings."""
    plain, raw = blank_fences(body).split("\n"), body.split("\n")
    result, name, start = {}, None, 0
    for i, line in enumerate(plain + ["## "]):
        if line.startswith("## ") or i == len(plain):
            if name is not None:
                result[name] = "\n".join(raw[start:i])
            name, start = line[3:].strip(), i + 1
    return result


def split_log(text):
    """(text above a single file's `## Log` heading, the log after it, the log's first line number).
    Line-based: blank_fences keeps line numbers, not character offsets."""
    lines = text.split("\n")
    for i, line in enumerate(blank_fences(text).split("\n")):
        if re.match(r"^## Log[ \t]*$", line):
            return "\n".join(lines[:i]), "\n".join(lines[i + 1:]), i + 2
    return text, "", 1


def log_text(item_type, control):
    """The log of an item: log.md beside a feature's README, or a single file's `## Log` section."""
    if item_type == "feature":
        p = Path(control).parent / "log.md"
        return (p.read_text(), 1) if p.is_file() else ("", 1)
    _, log, first = split_log(Path(control).read_text())
    return log, first


def parse_log(text, first_line=1):
    """Entries: dicts with date, time, offset, kind, n, rest, body (lines), line, ref.
    A `## ` heading that isn't an entry heading becomes kind None."""
    entries = []
    for i, line in enumerate(blank_fences(text).split("\n")):
        if line.startswith("## "):
            m = HEADING_RE.match(line.rstrip())
            e = {"line": first_line + i, "heading": line.rstrip(), "body": []}
            if m:
                date, time, off, kind, n, rest = m.groups()
                e.update(date=date, time=time, offset=off, kind=kind, n=n, rest=rest or "",
                         ref=f"{kind}{'-' + n if n else ''}@{date} {time}{off}")
            else:
                e.update(kind=None, ref=None, rest="")
            entries.append(e)
        elif entries:
            entries[-1]["body"].append(line)
    return entries


EXPECTATION_RE = re.compile(r"^B(\d+): (.+?) -> (.*\S)\s*$")
TASK_RE = re.compile(r"^#### Task (\d+): (.+?)(\s+\[parallel-safe\])?\s*$")
FIELD_RE = re.compile(r"^- ([a-z][a-z ]*):(?:\s+(.*))?$")
CASE_RE = re.compile(r"^\s+- (C\d+) \[(B\d+(?:,\s*B\d+)*)\] \((fixture|fake): ([^)]+)\): (\S.*)$")
RUN_TASK_RE = re.compile(r"^- task (\d+): merged, proof pass\b")


def parse_tasks(text):
    """Task blocks (plan.md, or express's one block in shape.md): dicts with n, title,
    parallel_safe, wave, line, fields {name: value}, cases [lines under `- test cases:`]."""
    tasks, wave, in_cases = [], None, False
    for i, line in enumerate(blank_fences(text).split("\n"), 1):
        m = re.match(r"^### Wave (\d+)\b", line)
        if m:
            wave, in_cases = int(m.group(1)), False
            continue
        m = TASK_RE.match(line)
        if m:
            tasks.append({"n": int(m.group(1)), "title": m.group(2), "parallel_safe": bool(m.group(3)),
                          "wave": wave, "line": i, "fields": {}, "cases": []})
            in_cases = False
        elif line.startswith("#"):
            in_cases = False
            if tasks and line.startswith(("## ", "### ")):
                tasks[-1].setdefault("end", i)
        elif tasks and "end" not in tasks[-1]:
            m = FIELD_RE.match(line)
            if m:
                in_cases = m.group(1) == "test cases"
                tasks[-1]["fields"][m.group(1)] = (m.group(2) or "").strip()
            elif in_cases and line.strip():
                tasks[-1]["cases"].append(line)
    return tasks


def _closes(entry):
    """Refs named on the entry's `Closes:` lines, as `<ref>#<id>` keys."""
    keys = []
    for line in entry["body"]:
        if line.startswith("Closes:"):
            keys += [f"{k}@{t}#{i}" for k, t, i in REF_RE.findall(line) if i]
    return keys


CLOSERS = ("review", "qa", "decision", "capped")


def open_blockers(entries):
    """Blockers from review and qa issue lines still open at the end of the log (Part B §11).
    A `Closes:` line in a later entry closes one; a blocker with a proposed rejection (`Rejects:`)
    closes only through a decision answered by the user; `Status: closed (legacy)` closes its own."""
    open_, rejected = {}, set()
    for e in entries:
        if e.get("kind") is None:
            continue
        legacy = any(l.strip() == "Status: closed (legacy)" for l in e["body"])
        user_decision = e["kind"] == "decision" and any(l.startswith("A (user, verbatim)") for l in e["body"])
        for line in e["body"]:
            if line.startswith("Rejects:"):
                rejected.update(f"{k}@{t}#{i}" for k, t, i in REF_RE.findall(line) if i)
        # Only these entries may close a blocker (log-entries.md); a forward phase move may not.
        if e["kind"] in CLOSERS or (e["kind"] == "phase" and e["rest"].endswith("(back)")):
            for key in _closes(e):
                if key in open_ and (key not in rejected or user_decision):
                    del open_[key]
        if e["kind"] in ("review", "qa") and not legacy:
            for line in e["body"]:
                m = ISSUE_RE.match(line)
                if m and m.group(2) == "blocker":
                    key = f"{e['ref']}#{m.group(1)}"
                    open_[key] = {"ref": key, "file": m.group(3), "line": int(m.group(4)), "claim": m.group(5)}
    return [dict(b, rejection_proposed=b["ref"] in rejected) for b in open_.values()]


def open_assumptions(entries):
    """A capped entry's `Assumptions:` items (`- A<n>: …`) not closed by a later
    `Closes: capped@<stamp>#A<n>` (§A2): dicts with ref and text."""
    open_ = {}
    for e in entries:
        if e.get("kind") is None:
            continue
        for key in _closes(e):
            open_.pop(key, None)
        if e["kind"] == "capped":
            in_list = False
            for line in e["body"]:
                if re.match(r"^[A-Z][\w-]*:", line):  # a list label (Deferred:, Assumptions:, Closes:) starts a new list
                    in_list = line.startswith("Assumptions:")
                elif in_list:
                    m = re.match(r"^- (A\d+): (.+)$", line)
                    if m:
                        key = f"{e['ref']}#{m.group(1)}"
                        open_[key] = {"ref": key, "text": m.group(2)}
    return list(open_.values())


def retro_triggers(entries):
    """The retro triggers a log records (§A8.3 S4, Part B §9): a second backward move,
    a capped entry, a cost overrun against the original budget, a defect."""
    found = []
    backs = [e for e in entries if e.get("kind") == "phase" and e["rest"].endswith("(back)")]
    if len(backs) >= 2:
        found.append("second backward move")
    if any(e.get("kind") == "capped" for e in entries):
        found.append("capped")
    if any(e.get("kind") == "defect" for e in entries):
        found.append("defect")
    budget = next((m.group(1) for e in entries if e.get("kind") == "run" for l in e["body"]
                   for m in [re.search(r"\bBudget: feature_token_budget=(\d+|unset)\b", l)] if m), None)
    tokens = next((int(m.group(1)) for e in reversed(entries) if e.get("kind") == "metrics" for l in e["body"]
                   for m in [re.search(r"\bTokens: (\d+)\b", l)] if m), None)
    if budget not in (None, "unset") and tokens is not None and tokens > int(budget):
        found.append("cost overrun")
    return found


def now_stamp():
    """`YYYY-MM-DD HH:MM±hh:mm`, the local time with its UTC offset."""
    t = datetime.now().astimezone()
    off = t.strftime("%z")
    return t.strftime("%Y-%m-%d %H:%M") + off[:3] + ":" + off[3:]


def slugify(title):
    words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in STOPWORDS]
    return "-".join(words[:5])


# --- self-test helpers, shared by the scripts' --self-test ---------------------

class Checks:
    def __init__(self, name):
        self.name, self.failed, self.ran = name, [], 0

    def check(self, cond, label):
        self.ran += 1
        if not cond:
            self.failed.append(label)
            print(f"FAIL: {label}")

    def done(self):
        print(f"{self.name} self-test: {self.ran - len(self.failed)}/{self.ran} passed")
        return 1 if self.failed else 0


def make_repo(tmp):
    """A temp git repo with one empty commit, for fixtures."""
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"], ["config", "commit.gpgsign", "false"],
                 ["commit", "-q", "--allow-empty", "-m", "init"]):
        git(args, tmp)
    return tmp


def _self_test():
    c = Checks("pd_common")
    fm, body, line = split_frontmatter(
        "---\nid: 2026-10-14-x  # c\nrisk: [security, migration]\norigin: backlog#2026-10-10-foo\n"
        "roadmap:\n  - feature: features/a\n  - planned: b\n    after: [a]\nqa:\n  - uv run pytest -q\n"
        "empty:\n---\n# T\n")
    c.check(fm["id"] == "2026-10-14-x", "comment stripped from a scalar")
    c.check(fm["risk"] == ["security", "migration"], "flow list")
    c.check(fm["origin"] == "backlog#2026-10-10-foo", "a # inside a word is kept")
    c.check(fm["roadmap"] == [{"feature": "features/a"}, {"planned": "b", "after": ["a"]}], "mapping items")
    c.check(fm["qa"] == ["uv run pytest -q"], "scalar list items")
    c.check(fm["empty"] is None and body == "# T\n" and line == 13, "empty key, body and its line")
    for bad in ("---\nid x\n---\n", "---\n  - a\n---\n", "---\nid: x\n"):
        try:
            split_frontmatter(bad)
            c.check(False, f"bad frontmatter raises: {bad!r}")
        except ValueError:
            c.check(True, "")
    c.check(slugify("The Fix for the UI PID-file test under load") == "fix-ui-pid-file-test", "slugify")
    log = ("<!-- example:\n## 2026-01-01 00:00+00:00 note\n-->\n"
           "## 2026-10-14 11:30+08:00 review M1 — codex\n- R1 blocker a.py:3 — x\n```\n## not a heading\n```\n"
           "## 2026-10-14 11:30+08:00 review-2\n## bad heading\n")
    es = parse_log(log)
    c.check([e["kind"] for e in es] == ["review", "review", None], "log kinds, comments and fences skipped")
    c.check(es[0]["ref"] == "review@2026-10-14 11:30+08:00" and es[1]["ref"] == "review-2@2026-10-14 11:30+08:00",
            "entry refs carry the -n suffix")
    c.check(es[0]["line"] == 4 and ISSUE_RE.match(es[0]["body"][0]), "entry line numbers and issue lines")
    c.check(set(sections("## Now\nx\n```\n## Fake\n```\n## Links\ny\n")) == {"Now", "Links"}, "sections skip fences")
    c.check(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}[+-]\d{2}:\d{2}", now_stamp()) is not None, "now_stamp")
    plan = ("## Plan\n### Wave 1\n#### Task 1: parse [parallel-safe]\n- files: a.py\n- uses: none\n"
            "- test cases:\n  - C1 [B1] (fixture: none): x\n### Wave 2\n#### Task 2: io\n- command: `t`\n")
    ts = parse_tasks(plan)
    c.check([(t["n"], t["wave"], t["parallel_safe"]) for t in ts] == [(1, 1, True), (2, 2, False)], "tasks and waves")
    c.check(ts[0]["fields"]["files"] == "a.py" and len(ts[0]["cases"]) == 1 and CASE_RE.match(ts[0]["cases"][0])
            and "files" not in ts[1]["fields"], "task fields and cases stay in their own block")
    blk = parse_log("## 2026-10-14 11:30+08:00 review\n- R1 blocker a.py:3 — x\n- R2 blocker a.py:4 — y\n"
                    "- R3 blocker a.py:5 — z\n- R4 warning a.py:6 — w\n"
                    "## 2026-10-14 11:40+08:00 qa\nCloses: review@2026-10-14 11:30+08:00#R1\n"
                    "Rejects: review@2026-10-14 11:30+08:00#R2, review@2026-10-14 11:30+08:00#R3\n"
                    "## 2026-10-14 11:50+08:00 decision\nA (conductor): reject\n"
                    "Closes: review@2026-10-14 11:30+08:00#R2\n"
                    "## 2026-10-14 11:55+08:00 decision\nA (user, verbatim): \"ok\"\n"
                    "Closes: review@2026-10-14 11:30+08:00#R3\n"
                    "## 2026-10-14 12:00+08:00 qa\nStatus: closed (legacy)\n- Q1 blocker b.py:1 — v\n")
    ob = open_blockers(blk)
    sneaky = parse_log("## 2026-10-14 11:30+08:00 review\n- R1 blocker a.py:3 — x\n- R2 blocker a.py:4 — y\n"
                       "## 2026-10-14 11:40+08:00 note\nCloses: review@2026-10-14 11:30+08:00#R1\n"
                       "## 2026-10-14 11:45+08:00 phase design -> implement\nCloses: review@2026-10-14 11:30+08:00#R1\n"
                       "## 2026-10-14 11:50+08:00 review\nRejects: review@2026-10-14 11:30+08:00#R2\n"
                       "Closes: review@2026-10-14 11:30+08:00#R2\n")
    c.check(sorted(b["ref"][-2:] for b in open_blockers(sneaky)) == ["R1", "R2"],
            "a note or a forward phase can't close a blocker; a same-entry rejection doesn't close it")
    head, log, first = split_log("# T\n<!-- a long\ncomment -->\n## Now\nx\n```\n## Log\n```\n## Log\n## 2026-10-14 11:30+08:00 note\n")
    c.check(head.endswith("```") and log == "## 2026-10-14 11:30+08:00 note\n" and first == 10,
            "split_log is line-based, skipping comments and fences")
    c.check([b["ref"][-2:] for b in ob] == ["R2"] and ob[0]["rejection_proposed"],
            "blockers: Closes closes, a rejection needs the user's decision, legacy is closed, warnings aren't blockers")
    asm = parse_log("## 2026-10-14 16:00+08:00 capped verify\nDeferred:\n- A9: not an assumption\n"
                    "Assumptions:\n- A1: one\n- A2: two\nCloses: review@2026-10-14 11:30+08:00#R4\n- A3: after Closes\n"
                    "## 2026-10-14 17:00+08:00 review\nCloses: capped@2026-10-14 16:00+08:00#A1\n")
    c.check([a["ref"][-2:] for a in open_assumptions(asm)] == ["A2"],
            "assumptions: only the Assumptions list, closed by a later Closes")
    trig = parse_log("## 2026-10-14 10:00+08:00 run goal — started\nBudget: feature_token_budget=100\n"
                     "## 2026-10-14 11:00+08:00 phase verify -> design (back)\n"
                     "## 2026-10-14 12:00+08:00 phase verify -> design (back)\n"
                     "## 2026-10-14 13:00+08:00 metrics\nMode: standard. Tokens: 150 (source: x).\n")
    c.check(retro_triggers(trig) == ["second backward move", "cost overrun"]
            and retro_triggers(trig[:2] + trig[3:]) == ["cost overrun"]
            and retro_triggers(parse_log("## 2026-10-14 10:00+08:00 defect\n")) == ["defect"], "retro triggers")
    with tempfile.TemporaryDirectory() as t:
        r = make_repo(Path(t) / "r")
        c.check(load_config(r)["artifacts_root"] == DEFAULT_ARTIFACTS_ROOT, "config defaults without a file")
        (r / ".claude").mkdir()
        (r / ".claude" / "pd.local.md").write_text("---\nartifacts_root: docs\nsop: 1\n---\n")
        c.check(load_config(r)["artifacts_root"] == "docs" and not is_unadopted(r, load_config(r)), "config file")
    return c.done()


if __name__ == "__main__":
    sys.exit(_self_test() if sys.argv[1:] == ["--self-test"] else 2)
