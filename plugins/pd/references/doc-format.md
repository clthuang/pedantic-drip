# Documentation format: markdown source, HTML for reading

pd's documentation clause (plan Part B §3.1). The `updating-docs` skill and every template cite it.

1. **Write markdown.** Every artifact and every doc is authored as `.md`. Markdown is the cheaper output (about 1.6× fewer tokens than bare HTML for the same document, measured 2026-10-14), agents read it back cheaply, and git diffs stay clean.
2. **Read as HTML, generated, never hand-written.** `uv run ${CLAUDE_PLUGIN_ROOT}/scripts/pd-html.py <file.md | dir>` converts markdown to HTML with one stylesheet, `templates/doc.css`.
   - **Output:** `docs/_html/` (gitignored), mirroring the source paths.
   - **Standalone pages:** the stylesheet is inlined. Mermaid diagrams load mermaid.js from a CDN; offline they show as code.
3. **Hand-written HTML is the exception,** for content markdown can't express (a laid-out dashboard, an interactive page). It lives in `docs/` beside its topic, is committed, and links `doc.css` by relative path, using only its classes: no inline styles and no `<style>` blocks of its own.
4. **Generated HTML is never committed and never edited.** The `.md` is the one source: delete a render and regenerate it.
5. **Write markdown that renders as written.** `pd-lint` fails a commit on the first two; `pd-html` warns on them as it renders.
   - **Code holding a backtick** (a regex, a shell command): wrap it in a longer backtick run, as in ``` `` grep 'a `b`' f `` ```, or put it in a fenced block. A backslash doesn't escape a backtick inside a code span.
   - **A `|` in a table cell:** write it as `\|`, even inside backticks, or the cell splits.
   - **Several code examples:** a fenced block, one per line, never joined into one line of code spans.
   - **Placeholders** such as `<path>` go in backticks. A bare one parses as an HTML tag: `pd-html` shows it as text, and other renderers drop it.
