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
import contextlib
import html
import io
import re
import sys
import tempfile
import webbrowser
from itertools import groupby
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pd_common import (EXPECTATION_RE, Checks, artifacts_dir, find_items, load_config,  # noqa: E402
                       make_repo, repo_root, split_frontmatter)

CSS = Path(__file__).resolve().parent.parent / "templates" / "doc.css"
MERMAID_JS = ('<script type="module">import mermaid from '
              '"https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";'
              'mermaid.initialize({startOnLoad: true});</script>')
STATUS_CLASSES = {"draft", "active", "blocked", "done", "abandoned"}
HTML_TAGS = set("a abbr article aside b blockquote br caption cite code col colgroup dd del details dfn div dl dt "
                "em figcaption figure footer h1 h2 h3 h4 h5 h6 header hr i img ins kbd li main mark nav ol p picture "
                "pre q s samp section small source span strong sub summary sup table tbody td tfoot th thead time tr "
                "u ul var video wbr".split())
VOID_TAGS = {"br", "col", "hr", "img", "source", "wbr"}
TAG_RE = re.compile(r"""<(/?)([A-Za-z][A-Za-z0-9-]*)(?=[\s/>])(?:[^<>"']|"[^"]*"|'[^']*')*>|<(?=/?[A-Za-z])""")
UNPAIRED = ("unpaired backtick: a code span is never closed or was cut short; wrap code holding backticks "
            "in a longer run (``like `this` one``) or a fenced block")
TABLE_PIPE = ("a backtick in this table cell is unpaired: a `|` inside backticks splits the cell (write it "
              "as `\\|`), or a code span is cut short")
SPLIT_SPAN = ("a quoted string holding a backtick split one code span in two; wrap it in a longer backtick "
              "run (`` `x` ``) or a fenced block")


def _md():
    # Without text_join, escapes and entities stay text_special tokens: hazards() tells them from source text.
    md = MarkdownIt("commonmark").enable(["table", "strikethrough"]).disable("text_join")
    md.renderer.rules["text_special"] = md.renderer.rules["text"]
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

    def raw_html(tokens, idx, options, env):
        """A placeholder such as <path> or <feature id> parses as a tag and would vanish: show it as text.
        A tag stays HTML when it names an HTML element and, unless void, the document also closes it."""
        # shortcut: a placeholder named like a tag the document also closes (<b> beside <b>x</b>) stays HTML;
        # pair the tags in document order if that ever bites.
        closed = env.get("closed_tags", set())

        def keep(m):
            if m.group(2) is None:
                return "&lt;"  # a "<name" that never forms a whole tag
            name = m.group(2).lower()
            real = name in HTML_TAGS and (m.group(1) or name in VOID_TAGS or name in closed)
            return m.group(0) if real else html.escape(m.group(0))
        return TAG_RE.sub(keep, tokens[idx].content)

    md.renderer.rules["fence"] = fence
    md.renderer.rules["html_inline"] = md.renderer.rules["html_block"] = raw_html
    md.add_render_rule("link_open", link_open)
    md.add_render_rule("pd_html", lambda self, tokens, idx, options, env: tokens[idx].content)
    return md


def code_spans(line):
    """CommonMark's code spans in a string: (content start, content end) offsets. A run of n backticks
    closes at the next run of exactly n; a backslash escapes a backtick only outside a span."""
    spans, i = [], 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] != "`":
            i += 1
            continue
        n = len(re.match(r"`+", line[i:]).group())
        close = re.compile(r"(?<!`)`{%d}(?!`)" % n).search(line, i + n)
        if close:
            spans.append((i + n, close.start()))
            i = close.end()
        else:
            i += n
    return spans


def _expectation(line, md, env):
    """One `B<n>: <input> -> <outcome>` line as a card, split at the first ` -> ` outside a code span."""
    m = EXPECTATION_RE.match(line)
    rest = line[m.end(1) + 2:].rstrip()
    spans = code_spans(rest)
    arrows = [a.start() for a in re.finditer(" -> ", rest)]
    cut = next((a for a in arrows if not any(s <= a < e for s, e in spans)), arrows[0])
    return (f'<div class="expectation" id="B{m.group(1)}"><span class="id">B{m.group(1)}</span>'
            f'<div class="given">{md.renderInline(rest[:cut], env)}</div>'
            f'<div class="outcome">{md.renderInline(rest[cut + 4:], env)}</div></div>')


def expectation_cards(tokens, md, env):
    """Markdown joins consecutive lines into one paragraph, so expectation lines would read as one wall of
    text: in each paragraph, every run of them becomes a block of cards. Code, HTML and lists are untouched."""
    out, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        src = tokens[i + 1].content if t.type == "paragraph_open" and not t.hidden else ""
        lines = src.split("\n")
        # A code span across lines would be cut apart: such a paragraph stays whole.
        if not any(EXPECTATION_RE.match(line) for line in lines) or any("\n" in src[s:e] for s, e in code_spans(src)):
            out.append(t)
            i += 1
            continue
        parts = []
        for is_expectation, run in groupby(lines, key=lambda line: bool(EXPECTATION_RE.match(line))):
            run = list(run)
            parts.append('<div class="expectations">' + "".join(_expectation(x, md, env) for x in run) + "</div>"
                         if is_expectation else f"<p>{md.renderInline(chr(10).join(run), env)}</p>")
        cards = Token("pd_html", "", 0)
        cards.content, cards.map = "\n".join(parts) + "\n", t.map
        out.append(cards)
        i += 3
    return out


def _split_quote(a, b):
    """'x', '`y`' written in single backticks: each span holds an odd count of one quote, and span a ends
    with it opening or span b starts with it closing. A prime (x') or an apostrophe (don't) isn't one."""
    def odd(span, q):
        return (re.sub(r"(?<=\w)'(?=\w)", "", span) if q == "'" else span).count(q) % 2 == 1
    if not a.strip("'\" ") or not b.strip("'\" "):
        return False  # a span showing the quote character itself
    return any(odd(a, q) and odd(b, q) and (re.search(r"(?:^|[^\w])%s\s*$" % q, a)
                                            or re.match(r"\s*%s(?:[^\w]|$)" % q, b)) for q in "'\"")


def hazards(tokens, first_line):
    """Markdown the parser read differently from how it was written: (line, message) pairs."""
    found, in_table = [], False
    for t in tokens:
        in_table = (in_table or t.type == "table_open") and t.type != "table_close"
        if t.type != "inline" or not t.children:
            continue
        line = first_line + (t.map[0] if t.map else 0)
        kids = t.children + [Token("text", "", 0)] * 2
        for k, mid, b in zip(kids, kids[1:], kids[2:]):
            if k.type == "text" and "`" in k.content:  # a backtick no code span took
                found.append((line, TABLE_PIPE if in_table else UNPAIRED))
            if (k.type == b.type == "code_inline" and mid.type == "text" and mid.content
                    and not re.search(r"\s", mid.content) and _split_quote(k.content, b.content)):
                found.append((line, SPLIT_SPAN))
            # shortcut: a code span across lines loses its line breaks, so later lines report one early.
            line += 1 if k.type in ("softbreak", "hardbreak") else k.content.count("\n")
    return sorted(set(found))


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
        fm, body, first_line = split_frontmatter(text)
    except ValueError as e:
        print(f"pd-html: {src}: bad frontmatter ({e}); rendering it as text", file=sys.stderr)
        fm, body, first_line = None, text, 1
    fm = fm or {}
    env = {"closed_tags": {name.lower() for name in re.findall(r"</([A-Za-z][A-Za-z0-9-]*)\s*>", body)}}
    content = frontmatter_box(fm)
    if fm.get("roadmap"):
        content += "<h2>Roadmap</h2>\n" + roadmap_table(fm["roadmap"], src.resolve().parent.parent)
    md = _md()
    tokens = md.parse(body, env)
    for line, msg in hazards(tokens, first_line):
        print(f"pd-html: WARN {src}:{line}: {msg}", file=sys.stderr)
    content += md.renderer.render(expectation_cards(tokens, md, env), md.options, env)
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
        shape = art / "features" / "2026-10-15-a" / "shape.md"
        shape.write_text("# S\n\n**Apply**\n\nB1: `a -> b` on the file -> exit 0; prints `x -> y`\n"
                         "B2: no args -> usage, exit 2\n\nAfter.\n\n```\nB3: in a fence -> stays code\n```\n")
        page = render(shape, root).read_text()
        c.check(page.count('<div class="expectation"') == 2 and 'id="B1"' in page and 'id="B2"' in page,
                "consecutive expectation lines become one card each, not one paragraph")
        c.check('<div class="given"><code>a -&gt; b</code> on the file</div>' in page
                and '<div class="outcome">exit 0; prints <code>x -&gt; y</code></div>' in page,
                "an expectation splits at the first arrow outside a code span; inline markdown renders")
        c.check("<p>After.</p>" in page and "B3: in a fence -&gt; stays code" in page and 'id="B3"' not in page,
                "text after the run is a paragraph again; a fenced expectation stays code")
        shape.write_text("# S\n\n````markdown\n```\nB1: sample -> code\n```\n````\n\nLead line\n"
                         "B2: ``a -> b`` -> ok, see [spec][s]\n\n[s]: other.md\n")
        page = render(shape, root).read_text()
        c.check('id="B1"' not in page and "B1: sample -&gt; code" in page, "a longer fence holding ``` stays code")
        c.check("<p>Lead line</p>" in page and '<div class="given"><code>a -&gt; b</code></div>' in page
                and 'ok, see <a href="other.html">spec</a>' in page,
                "a lead line stays a paragraph; a double-backtick span keeps its arrow; reference links resolve")
        shape.write_text("# S\n\nprints report: <abs path> for <feature id>, S1 <a> > S2 <b>, in <i>it</i>\n\n"
                         "Text <path title=\"><img src=x onerror=alert(1)>\"> and <bold> after\n\n<!-- note -->\n\n<div>\n<feature id>\n</div>\n\nB1: run -> stdout <path>\n")
        page = render(shape, root).read_text()
        c.check("report: &lt;abs path&gt; for &lt;feature id&gt;, S1 &lt;a&gt; &gt; S2 &lt;b&gt;, in <i>it</i>" in page
                and "<div>\n&lt;feature id&gt;\n</div>" in page and "stdout &lt;path&gt;" in page
                and "<!-- note -->" in page and "<img" not in page and "and &lt;bold&gt; after" in page,
                "a <placeholder> shows as text, whole and in an HTML block too; closed real tags and comments stay HTML")
        shape.write_text("# S\n\n> B1: a -> b\n\n- one\n\n- B2: c -> d\n\n> Example `\n> B9: x -> y\n> ` end.\n")
        page = render(shape, root).read_text()
        c.check('<blockquote>\n<div class="expectations"><div class="expectation" id="B1">' in page
                and '<li>\n<div class="expectations"><div class="expectation" id="B2">' in page
                and "<p>Example <code>B9: x -&gt; y</code> end.</p>" in page,
                "cards keep their blockquote or list; a code span across lines stays one paragraph")

        def warnings(text):
            shape.write_text(text)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                render(shape, root)
            found = (re.match(r"pd-html: WARN .*?\.md:(\d+): (.*)$", w) for w in err.getvalue().splitlines())
            return [(int(m.group(1)), m.group(2)) for m in found if m]
        # The bake-off's shape.md line 54: '`.meta.json`' inside a single-backtick span split it in two.
        line54 = "`>>> f(r'(?!\\w)', 'UI', re.I)` · `>>> re.search(r'\\.meta', '`.meta.json`', re.I)) → True`\n"
        c.check(warnings("---\nid: x\n---\n# S\n\n" + line54) == [(6, SPLIT_SPAN)]
                and warnings("# S\n\n`grep -rn 'highest `NNN`' plugins/` → 0\n") == [(3, SPLIT_SPAN)],
                "a backtick inside a quoted string warns, with the source line (frontmatter counted)")
        c.check(warnings("# S\n\none `open span\n") == [(3, UNPAIRED)]
                and warnings("---\nid: x\n---\n> safe\n> bad `open\n") == [(5, UNPAIRED)]
                and warnings("# S\n\n`\\` and `open\n") == [(3, UNPAIRED)]
                and warnings("# S\n\n| a | b |\n|---|---|\n| `x|y` | z |\n") == [(5, TABLE_PIPE)],
                "an unpaired backtick warns on its own line, beside a code span holding a backslash; so does a table-cell pipe")
        clean = ("---\ntitle: Show ` char\n---\n# S\n\n~~~\nlone ` x\n~~~\n\nPara.\n\n    lone ` in code\n\n"
                 "> `one\n> two`\n\n- `one\n  two`\n\n<span title=\"`\">x</span> and before <!-- ` --> after\n\n"
                 "`x'`/`y'`, `[\"`, `\"]`, `${D}/`/`\"${D}/`, `'`/`'`, a \\` escaped, &#96; and &grave;, `don't`, `'`\n\n| use `a|b` in prose\n\n| a | b |\n|---|---|\n| `x\\|y` | z |\n")
        c.check(warnings(clean) == [], "valid fences, indented code, quotes, lists, HTML, escapes and frontmatter pass")
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
