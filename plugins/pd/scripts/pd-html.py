#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["markdown-it-py>=3,<5"]
# ///
"""pd-html: render markdown to standalone HTML with pd's one stylesheet (plan Part B §3.1).

Usage: uv run pd-html.py <file.md | dir> [--open]
       uv run pd-html.py --all [--open]
       uv run pd-html.py --self-test
Output goes to <repo>/docs/_html/, mirroring the source paths. Never commit it.
"""
import html
import re
import sys
import tempfile
import webbrowser
from pathlib import Path

from markdown_it import MarkdownIt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pd_common import (Checks, artifacts_dir, find_items, load_config, make_repo,  # noqa: E402
                       repo_root, split_frontmatter)

CSS = Path(__file__).resolve().parent.parent / "templates" / "doc.css"
MERMAID_JS = ('<script type="module">import mermaid from '
              '"https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";'
              'mermaid.initialize({startOnLoad: true});</script>')
STATUS_CLASSES = {"draft", "active", "blocked", "done", "abandoned"}


def _md():
    md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    default_fence = md.renderer.rules["fence"]

    def fence(tokens, idx, options, env):
        if tokens[idx].info.strip() == "mermaid":
            env["mermaid"] = True
            return f'<pre class="mermaid">{html.escape(tokens[idx].content)}</pre>\n'
        return default_fence(tokens, idx, options, env)

    def link_open(self, tokens, idx, options, env):
        href = tokens[idx].attrGet("href") or ""
        # Relative .md links point at sources; their HTML twins sit at the same relative path.
        if not re.match(r"^[a-z][a-z0-9+.-]*:|^/|^#", href, re.I):
            tokens[idx].attrSet("href", re.sub(r"\.md(?=$|#)", ".html", href))
        return self.renderToken(tokens, idx, options, env)

    md.renderer.rules["fence"] = fence
    md.add_render_rule("link_open", link_open)
    return md


def _cell(text, cls=None):
    return f'<td{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>{html.escape(str(text))}</td>'


def _status(readme):
    try:
        fm, _, _ = split_frontmatter(readme.read_text())
        return (fm or {}).get("status") or "?"
    except (OSError, ValueError):
        return "missing"


def roadmap_table(roadmap, art):
    """Each item's live status, read from its own frontmatter: never stored in the plan."""
    rows = []
    for item in roadmap or []:
        if not isinstance(item, dict):
            continue
        after = ", ".join(item.get("after") or [])
        if "feature" in item:
            path = item["feature"]
            status = _status(art / path / "README.md")
            link = f'<a href="../{html.escape(path)}/README.html">{html.escape(path)}</a>'
            rows.append(f"<tr><td>{link}</td>{_cell(status, status if status in STATUS_CLASSES else None)}"
                        f"{_cell(after)}</tr>")
        elif "planned" in item:
            rows.append(f"<tr>{_cell(item['planned'])}{_cell('planned', 'draft')}{_cell(after)}</tr>")
        elif "dropped" in item:
            rows.append(f"<tr>{_cell(item['dropped'])}{_cell('dropped: ' + str(item.get('reason', '')), 'abandoned')}"
                        f"{_cell(after)}</tr>")
    return ("<table><thead><tr><th>Item</th><th>Status</th><th>After</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>\n")


def frontmatter_box(fm):
    rows = []
    for key in ("id", "status", "phase"):
        if fm.get(key):
            cls = f' class="{fm[key]}"' if key == "status" and fm[key] in STATUS_CLASSES else ""
            rows.append(f"<dt>{key}</dt><dd{cls}>{html.escape(str(fm[key]))}</dd>")
    if fm.get("issue"):
        url = html.escape(str(fm["issue"]))
        rows.append(f'<dt>issue</dt><dd><a href="{url}">{url}</a></dd>' if url.startswith("http")
                    else f"<dt>issue</dt><dd>{url}</dd>")
    return f'<dl class="frontmatter">{"".join(rows)}</dl>\n' if rows else ""


def render(src, root):
    text = src.read_text()
    try:
        fm, body, _ = split_frontmatter(text)
    except ValueError as e:
        print(f"pd-html: {src}: bad frontmatter ({e}); rendering it as text", file=sys.stderr)
        fm, body = None, text
    fm, env = fm or {}, {}
    content = frontmatter_box(fm)
    if fm.get("roadmap"):
        content += "<h2>Roadmap</h2>\n" + roadmap_table(fm["roadmap"], src.resolve().parent.parent)
    content += _md().render(body, env)
    heading = re.search(r"^# (.+)$", body, re.M)
    title = html.escape(str(fm.get("title") or (heading.group(1) if heading else src.stem)))
    page = (f'<!doctype html>\n<html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{title}</title><style>\n{CSS.read_text()}</style></head>\n<body>\n{content}"
            f"{MERMAID_JS if env.get('mermaid') else ''}</body></html>\n")
    out = root / "docs" / "_html" / src.resolve().relative_to(root.resolve()).with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return out


def targets(arg, root):
    if arg != "--all":
        p = Path(arg).resolve()
        return sorted(p.rglob("*.md")) if p.is_dir() else [p]
    found = [f for tier in ("user-guide", "dev-guide", "technical") for f in sorted((root / "docs" / tier).rglob("*.md"))]
    for type_, _, control in find_items(artifacts_dir(root, load_config(root))):
        if control.is_file() and _status(control) == "active":
            found += sorted(control.parent.glob("*.md")) if type_ == "feature" else [control]
    return found


def self_test():
    c = Checks("pd-html")
    with tempfile.TemporaryDirectory() as t:
        root = make_repo(Path(t) / "repo").resolve()
        art = root / "docs" / "dev_artifacts"
        (art / "features" / "2026-10-15-a").mkdir(parents=True)
        (art / "features" / "2026-10-15-a" / "README.md").write_text("---\nid: 2026-10-15-a\nstatus: done\n---\n# A\n")
        (art / "plans").mkdir()
        plan = art / "plans" / "2026-10-14-p.md"
        plan.write_text(
            "---\nid: 2026-10-14-p\ntype: plan\ntitle: P\nstatus: active\nissue: https://x.test/i/1\n"
            "roadmap:\n  - feature: features/2026-10-15-a\n  - planned: b\n    after: [a]\n"
            "  - dropped: c\n    reason: \"not needed\"\n---\n# P\n\n| x | y |\n|---|---|\n| 1 | 2 |\n\n"
            "```python\nprint(1)\n```\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\n"
            "See [other](other.md), [sec](other.md#s), [web](https://x.test/a.md).\n")
        (art / "plans" / "plain.md").write_text("# Plain\n")
        out = render(plan, root)
        page = out.read_text()
        c.check(out == root / "docs/_html/docs/dev_artifacts/plans/2026-10-14-p.html", "output mirrors the source path")
        c.check(".frontmatter dt" in page and "<link" not in page, "doc.css is inlined")
        c.check('href="other.html"' in page and 'href="other.html#s"' in page and "other.md" not in page,
                "relative .md links become .html, anchors kept")
        c.check('href="https://x.test/a.md"' in page, "absolute URLs are left alone")
        c.check('<dl class="frontmatter">' in page and '<dd class="active">active</dd>' in page
                and 'href="https://x.test/i/1"' in page, "frontmatter box with status class and issue link")
        c.check('<td class="done">done</td>' in page, "roadmap shows the feature's live status")
        c.check('<td class="draft">planned</td>' in page and "dropped: not needed" in page, "planned and dropped items")
        c.check("<th>x</th>" in page and "<td>1</td>" in page and "<pre><code" in page, "markdown tables and code render")
        c.check('<pre class="mermaid">flowchart LR' in page and "mermaid.esm.min.mjs" in page
                and "language-mermaid" not in page, "mermaid block left for mermaid.js")
        c.check("mermaid.esm" not in render(art / "plans" / "plain.md", root).read_text(), "no mermaid script without a block")
    return c.done()


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    args = [a for a in argv if a != "--open"]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    root = repo_root(Path(args[0]).parent if args[0] != "--all" else ".")
    outs = [render(f, root) for f in targets(args[0], root)]
    for o in outs:
        print(o)
    if "--open" in argv and outs:
        webbrowser.open(outs[0].as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
