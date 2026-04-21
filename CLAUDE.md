# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run / Stop

```bash
python3 server.py              # foreground
python3 server.py &            # background
./claude-math                  # wrapper: starts server (if down) + opens browser pane

# Verify listener / kill background instance
lsof -nP -iTCP:3456 -sTCP:LISTEN
kill $(lsof -tiTCP:3456 -sTCP:LISTEN)
```

Port is overridable via `CLAUDE_MATH_PORT` (default `3456`). There are no tests, build, or lint steps — Python 3 stdlib only, no dependencies to install.

## Architecture

The entire app is **two files**: `server.py` (Python HTTP server with the HTML/CSS/JS embedded as a single `HTML_PAGE` string literal) and `claude-math` (bash wrapper). There is no build step, no bundler, no package.json — edits to the frontend happen inside the triple-quoted string in `server.py`.

### Data flow

```
Claude Code  →  ~/.claude/projects/**/*.jsonl  →  server.py (polls)  →  browser (KaTeX)
```

The server never talks to Claude Code directly. It reads the JSONL transcript files that Claude Code writes to `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. The project directory encoding is `-`-separated (e.g. `/Users/foo/bar` → `-Users-foo-bar`); `list_sessions()` reverses this heuristically and takes the last two path components as a short label.

### Server endpoints

- `GET /` — serves the embedded HTML page.
- `GET /api/sessions` — lists the 15 most recently modified JSONL files with id / project / label (first user message preview) / mtime. Full file paths are **deliberately stripped** before JSON encoding.
- `GET /api/messages?session=<id>` — re-parses the JSONL on every request and returns `{messages, file_size, session_file}`. No caching, no diffing server-side.

### Client polling model

The browser polls `/api/messages` every **500 ms** and `/api/sessions` every **3000 ms** (`POLL_MS`, `SESSION_POLL_MS` in the inline script). Re-render is triggered only when `messages.length` or `file_size` changes — so a truncated / rewritten file will redraw, but identical-length polls are no-ops. On each redraw the whole `#messages` container is replaced; there is no incremental DOM patching.

### JSONL parsing (`extract_messages`)

Only lines with `type == "human"` or `type == "assistant"` are surfaced. Message content may be either a plain string or a list of parts — only parts with `type == "text"` are joined; tool use / tool results / thinking blocks are dropped. Malformed JSON lines are silently skipped.

### Markdown + math rendering pipeline (`basicMarkdown` in the inline script)

Order matters and is load-bearing — changes that reorder these passes will break each other:

1. Stash math blocks, fenced code blocks, inline code, and GFM tables into placeholders (`%%MATH_n%%`, `%%CB_n%%`, `%%IC_n%%`, `%%TB_n%%`) so subsequent regex passes don't corrupt their contents. The display-math stash (`$$([^$]+)$$`) also collapses any embedded newlines to spaces at this step so KaTeX auto-render can locate the block — **do not** add a separate pre-pass that pairs `$$` across lines, because it will match the closing `$$` of one block with the opening `$$` of the next and destroy all the plain text (headings, `---`, tables) between them.
2. Apply line-oriented markdown regexes (headings, bold/italic, `---`, blockquote, lists, paragraph wrap). The paragraph-wrap regex `^(?!<[hupob]|<li|<hr|%%)(.*\S.*)$` is the gate that keeps placeholders and already-converted block tags from being wrapped in `<p>`.
3. Restore placeholders in reverse order (tables → code → inline code → math), so KaTeX's `renderMathInElement` sees raw `$$...$$` again.

When adding a new block-level construct, add it to the placeholder stash **and** update the paragraph-wrap negative lookahead.
