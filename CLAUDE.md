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
- `GET /api/voices?backend=say|gemini` — lists voices for the selected backend. Response includes `gemini_available` (is a key resolvable?) and `gemini_key_source` (`env` | `file` | `none`). macOS voices are parsed once from `say -v '?'` (ja_JP only); Gemini voices are the 30 prebuilt voices hardcoded in `GEMINI_VOICES`.
- `POST /api/speak` — body `{"text": "...", "backend": "say"|"gemini", "voice": "..."}`. Dispatches via `speak()` which is invoked on a daemon thread so the HTTP reply returns immediately. Both backends share `_playback_state` (guarded by `_playback_lock`) — any new request terminates the previous subprocess before starting a new one (interrupt semantics). `say` pipes text to stdin; Gemini calls the API, wraps the returned PCM (24kHz/16bit/mono) in a WAV header via `_write_wav`, and plays with `afplay` on a temp file. Empty text just stops current playback. Text is capped at 4000 chars. The client calls this on each new assistant message when the header "音声 ON" toggle is active; history is never replayed — a baseline `lastSpokenIndex` is set on first load and on session switch.
- `POST /api/config` — body `{"gemini_api_key": "..."}`. Writes to `~/.config/claude-math-viewer/config.json` (mode 0600, dir 0700) via atomic `os.replace`. `get_gemini_key()` resolves the key in this order on every call (no restart needed): env var `GEMINI_API_KEY`/`GOOGLE_API_KEY` → config file → `None`. The UI exposes this via an "APIキー" button visible only when the Gemini backend is selected.

Server uses `ThreadingHTTPServer` so long-running Gemini synthesis (~1–2s) does not stall the 500 ms `/api/messages` polling.

`Handler._allowed_origin()` CSRF-guards every POST: if an `Origin` header is present it must match `http://localhost:{PORT}` or `http://127.0.0.1:{PORT}`, otherwise the request is rejected with 403. Non-browser clients (curl, scripts) that omit `Origin` entirely are allowed through.

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
