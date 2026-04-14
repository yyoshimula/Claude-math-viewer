#!/usr/bin/env python3
"""
Claude Code Math Viewer - Real-time LaTeX rendering for Claude Code output.

Watches Claude Code's own JSONL transcript files directly.
No tee, no script, no piping needed.
Supports session switching via browser UI.

Usage:
  1. Start:   python3 server.py
  2. Browse:  http://localhost:3456
  3. Just use Claude Code normally in another pane.
"""

import http.server
import json
import glob
import os
import time
import urllib.parse

PORT = int(os.environ.get("CLAUDE_MATH_PORT", 3456))
CLAUDE_DIR = os.path.expanduser("~/.claude/projects")

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Math Viewer</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+JP:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0a0c;
    --bg-card: #111114;
    --bg-code: #1a1a20;
    --border: #222228;
    --text: #d4d4d8;
    --text-dim: #71717a;
    --text-bright: #fafafa;
    --accent: #818cf8;
    --accent-dim: #6366f1;
    --green: #34d399;
    --user-bg: #1a1a2e;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'IBM Plex Sans', 'IBM Plex Sans JP', system-ui, sans-serif;
    font-size: 15px;
    line-height: 1.7;
    min-height: 100vh;
  }

  .container {
    max-width: 820px;
    margin: 0 auto;
    padding: 24px 24px 40px;
  }

  /* Header */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .logo {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 12px var(--accent-dim);
  }

  .header h1 {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-dim);
  }

  .status {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-dim);
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-dim);
    transition: background 0.3s;
  }

  .status-dot.live {
    background: var(--green);
    box-shadow: 0 0 8px rgba(52, 211, 153, 0.4);
    animation: pulse 2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  /* Session switcher */
  .session-bar {
    display: flex;
    gap: 6px;
    margin-bottom: 20px;
    overflow-x: auto;
    padding-bottom: 4px;
    scrollbar-width: none;
  }
  .session-bar::-webkit-scrollbar { display: none; }

  .session-tab {
    flex-shrink: 0;
    padding: 6px 14px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-dim);
    font-size: 12px;
    font-family: 'JetBrains Mono', monospace;
    cursor: pointer;
    transition: all 0.2s;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .session-tab:hover {
    border-color: var(--accent-dim);
    color: var(--text);
  }

  .session-tab.active {
    border-color: var(--accent);
    background: rgba(129, 140, 248, 0.1);
    color: var(--text-bright);
  }

  .session-tab .tab-time {
    color: var(--text-dim);
    font-size: 10px;
    margin-left: 6px;
  }

  /* Messages */
  .message {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 16px;
    transition: border-color 0.3s;
  }

  .message.new { border-color: var(--accent-dim); }

  .message.user {
    background: var(--user-bg);
    border-color: #2a2a4e;
  }

  .message-role {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 12px;
  }

  .message.user .message-role { color: var(--accent); }

  .message-body h1, .message-body h2, .message-body h3, .message-body h4 {
    color: var(--text-bright);
    margin-top: 1.2em;
    margin-bottom: 0.4em;
    font-weight: 600;
  }
  .message-body h1 { font-size: 1.5em; }
  .message-body h2 { font-size: 1.25em; }
  .message-body h3 { font-size: 1.1em; }
  .message-body p { margin-bottom: 0.7em; }

  .message-body ul, .message-body ol {
    padding-left: 1.5em;
    margin-bottom: 0.7em;
  }
  .message-body li { margin-bottom: 0.2em; }

  .message-body pre {
    background: var(--bg-code);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px;
    overflow-x: auto;
    margin: 0.8em 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    line-height: 1.5;
  }

  .message-body code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.88em;
    background: var(--bg-code);
    padding: 2px 5px;
    border-radius: 4px;
  }

  .message-body pre code { background: none; padding: 0; }

  .message-body blockquote {
    border-left: 3px solid var(--accent-dim);
    padding-left: 14px;
    color: var(--text-dim);
    margin: 0.8em 0;
  }

  .message-body strong { color: var(--text-bright); font-weight: 600; }

  .message-body hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 1.2em 0;
  }

  .message-body .table-wrap {
    overflow-x: auto;
    margin: 0.9em 0;
    border-radius: 8px;
    border: 1px solid var(--border);
  }
  .message-body table {
    border-collapse: collapse;
    font-size: 0.95em;
    width: 100%;
  }
  .message-body thead {
    background: var(--bg-code);
  }
  .message-body th,
  .message-body td {
    border-bottom: 1px solid var(--border);
    border-right: 1px solid var(--border);
    padding: 8px 14px;
    text-align: left;
    vertical-align: top;
  }
  .message-body th:last-child,
  .message-body td:last-child {
    border-right: none;
  }
  .message-body tbody tr:last-child td {
    border-bottom: none;
  }
  .message-body th {
    color: var(--text-bright);
    font-weight: 600;
    font-size: 0.86em;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }
  .message-body tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.02);
  }
  .message-body tbody tr:hover {
    background: rgba(129, 140, 248, 0.06);
  }

  /* KaTeX */
  .katex-display {
    margin: 1em 0;
    padding: 14px;
    background: rgba(129, 140, 248, 0.04);
    border-radius: 8px;
    border: 1px solid rgba(129, 140, 248, 0.08);
    overflow-x: auto;
  }
  .katex { font-size: 1.15em; }

  .empty-state {
    text-align: center;
    color: var(--text-dim);
    padding: 80px 0;
  }
  .empty-state p { margin-bottom: 8px; }
  .empty-state code {
    display: inline-block;
    margin-top: 8px;
    padding: 6px 14px;
    background: var(--bg-code);
    border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: var(--accent);
    border: 1px solid var(--border);
  }

  .footer {
    margin-top: 24px;
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-dim);
  }

  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="header-left">
      <div class="logo"></div>
      <h1>Claude Math Viewer</h1>
    </div>
    <div class="status">
      <div class="status-dot" id="statusDot"></div>
      <span id="statusText">waiting</span>
    </div>
  </div>

  <div class="session-bar" id="sessionBar"></div>

  <div id="messages">
    <div class="empty-state" id="emptyState">
      <p>Watching for Claude Code sessions...</p>
      <code>Just run claude in another pane</code>
    </div>
  </div>

  <div class="footer">
    <span id="footerInfo">watching ~/.claude/projects/</span>
    <span id="footerTime">—</span>
  </div>
</div>

<script>
const POLL_MS = 500;
const SESSION_POLL_MS = 3000;
let currentSession = null;  // null = auto (latest)
let lastMsgCount = 0;
let lastFileSize = 0;
let sessions = [];

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function basicMarkdown(text) {
  // Pre-process: collapse multiline $$...$$ into single line so KaTeX can find them
  text = text.replace(/\$\$\s*\n([\s\S]*?)\n\s*\$\$/g, (_, inner) => {
    return '$$' + inner.replace(/\n/g, ' ').trim() + '$$';
  });

  // Also handle \[...\] multiline
  text = text.replace(/\\\[\s*\n([\s\S]*?)\n\s*\\\]/g, (_, inner) => {
    return '\\[' + inner.replace(/\n/g, ' ').trim() + '\\]';
  });

  // Protect display math blocks from markdown processing
  const mathBlocks = [];
  text = text.replace(/\$\$([^$]+)\$\$/g, (m) => {
    mathBlocks.push(m);
    return '%%MATH_' + (mathBlocks.length - 1) + '%%';
  });
  text = text.replace(/\\\[[\s\S]*?\\\]/g, (m) => {
    mathBlocks.push(m);
    return '%%MATH_' + (mathBlocks.length - 1) + '%%';
  });

  const codeBlocks = [];
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    codeBlocks.push('<pre><code>' + escapeHtml(code.trimEnd()) + '</code></pre>');
    return '%%CB_' + (codeBlocks.length - 1) + '%%';
  });

  const inlineCodes = [];
  text = text.replace(/`([^`]+)`/g, (_, code) => {
    inlineCodes.push('<code>' + escapeHtml(code) + '</code>');
    return '%%IC_' + (inlineCodes.length - 1) + '%%';
  });

  // GFM tables
  const tableBlocks = [];
  const formatCell = (s) => s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(
    /^(\|[^\n]+\|)[ \t]*\n(\|[ \t:\-|]*-[ \t:\-|]*\|)[ \t]*\n((?:\|[^\n]+\|[ \t]*\n?)+)/gm,
    (_, header, sep, body) => {
      const parseCells = (line) =>
        line.replace(/^\|/, '').replace(/\|[ \t]*$/, '').split('|').map(c => c.trim());
      const hdr = parseCells(header);
      const aligns = parseCells(sep).map(s => {
        if (/^:-+:$/.test(s)) return 'center';
        if (/^-+:$/.test(s)) return 'right';
        if (/^:-+$/.test(s)) return 'left';
        return '';
      });
      const rows = body.replace(/\n$/, '').split('\n').map(parseCells);

      let html = '<div class="table-wrap"><table><thead><tr>';
      hdr.forEach((h, i) => {
        const a = aligns[i] ? ' style="text-align:' + aligns[i] + '"' : '';
        html += '<th' + a + '>' + formatCell(h) + '</th>';
      });
      html += '</tr></thead><tbody>';
      rows.forEach(r => {
        html += '<tr>';
        r.forEach((c, i) => {
          const a = aligns[i] ? ' style="text-align:' + aligns[i] + '"' : '';
          html += '<td' + a + '>' + formatCell(c) + '</td>';
        });
        html += '</tr>';
      });
      html += '</tbody></table></div>';

      tableBlocks.push(html);
      return '%%TB_' + (tableBlocks.length - 1) + '%%';
    }
  );

  text = text.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(/^---$/gm, '<hr>');
  text = text.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
  text = text.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  text = text.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  text = text.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  text = text.replace(/^(?!<[hupob]|<li|<hr|%%)(.*\S.*)$/gm, '<p>$1</p>');

  text = text.replace(/%%TB_(\d+)%%/g, (_, i) => tableBlocks[i]);
  text = text.replace(/%%CB_(\d+)%%/g, (_, i) => codeBlocks[i]);
  text = text.replace(/%%IC_(\d+)%%/g, (_, i) => inlineCodes[i]);
  text = text.replace(/%%MATH_(\d+)%%/g, (_, i) => mathBlocks[i]);
  return text;
}

function renderMessage(msg) {
  const div = document.createElement('div');
  div.className = 'message ' + msg.role + ' new';
  div.innerHTML =
    '<div class="message-role">' + msg.role + '</div>' +
    '<div class="message-body">' + basicMarkdown(msg.content) + '</div>';

  renderMathInElement(div, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$', right: '$', display: false },
      { left: '\\[', right: '\\]', display: true },
      { left: '\\(', right: '\\)', display: false },
    ],
    throwOnError: false,
  });

  setTimeout(() => div.classList.remove('new'), 600);
  return div;
}

function selectSession(sessionId) {
  currentSession = sessionId;
  lastMsgCount = 0;
  lastFileSize = 0;
  renderSessionTabs();
  pollMessages();
}

function renderSessionTabs() {
  const bar = document.getElementById('sessionBar');
  bar.innerHTML = '';

  sessions.forEach(s => {
    const tab = document.createElement('div');
    tab.className = 'session-tab' + (currentSession === s.id ? ' active' : '');

    const time = new Date(s.mtime * 1000);
    const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    tab.innerHTML = escapeHtml(s.label) +
      '<span class="tab-time">' + timeStr + '</span>';
    tab.title = s.project + ' / ' + s.id;
    tab.onclick = () => selectSession(s.id);
    bar.appendChild(tab);
  });
}

async function pollSessions() {
  try {
    const res = await fetch('/api/sessions');
    if (!res.ok) return;
    const data = await res.json();
    sessions = data.sessions;

    // Auto-select latest if no session selected or current is gone
    if (!currentSession || !sessions.find(s => s.id === currentSession)) {
      if (sessions.length > 0) {
        currentSession = sessions[0].id;
      }
    }

    renderSessionTabs();
  } catch (e) {}
}

async function pollMessages() {
  if (!currentSession) {
    setStatus('waiting', 'waiting');
    return;
  }

  try {
    const res = await fetch('/api/messages?session=' + encodeURIComponent(currentSession));
    if (!res.ok) { setStatus('error', 'error'); return; }
    const data = await res.json();

    if (data.messages.length === 0) {
      setStatus('waiting', 'no messages');
      return;
    }

    if (data.messages.length !== lastMsgCount || data.file_size !== lastFileSize) {
      lastMsgCount = data.messages.length;
      lastFileSize = data.file_size;

      const container = document.getElementById('messages');
      const empty = document.getElementById('emptyState');
      if (empty) empty.remove();

      container.innerHTML = '';
      data.messages.forEach(msg => {
        container.appendChild(renderMessage(msg));
      });

      setStatus('live', data.messages.length + ' msgs');
      document.getElementById('footerTime').textContent =
        new Date().toLocaleTimeString();
      document.getElementById('footerInfo').textContent =
        data.session_file || '';

      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    }
  } catch (e) {
    setStatus('error', 'disconnected');
  }
}

function setStatus(state, text) {
  document.getElementById('statusDot').className =
    'status-dot ' + (state === 'live' ? 'live' : '');
  document.getElementById('statusText').textContent = text;
}

// Initial load
pollSessions().then(() => pollMessages());

// Poll messages frequently, sessions less often
setInterval(pollMessages, POLL_MS);
setInterval(pollSessions, SESSION_POLL_MS);
</script>
</body>
</html>
"""


def list_sessions(limit=15):
    """List recent JSONL session files with metadata."""
    pattern = os.path.join(CLAUDE_DIR, "**", "*.jsonl")
    files = glob.glob(pattern, recursive=True)
    if not files:
        return []

    # Sort by modification time, newest first
    files.sort(key=os.path.getmtime, reverse=True)
    files = files[:limit]

    sessions = []
    for f in files:
        mtime = os.path.getmtime(f)
        session_id = os.path.splitext(os.path.basename(f))[0]

        # Extract project name from path
        # e.g. ~/.claude/projects/-Users-foo-myproject/session.jsonl
        rel = os.path.relpath(f, CLAUDE_DIR)
        project_dir = rel.split(os.sep)[0] if os.sep in rel else ""
        # Decode project path: -Users-foo-bar → /Users/foo/bar
        project_label = project_dir.replace("-", "/", 1).replace("-", "/") if project_dir else "unknown"
        # Shorten to last 2 components
        parts = project_label.rstrip("/").split("/")
        short_label = "/".join(parts[-2:]) if len(parts) >= 2 else project_label

        # Get first user message as preview
        preview = ""
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") == "human":
                        content = obj.get("message", {})
                        if isinstance(content, dict):
                            c = content.get("content", "")
                            if isinstance(c, list):
                                texts = [p.get("text", "") for p in c
                                         if isinstance(p, dict) and p.get("type") == "text"]
                                preview = " ".join(texts)[:60]
                            elif isinstance(c, str):
                                preview = c[:60]
                        elif isinstance(content, str):
                            preview = content[:60]
                        break
        except Exception:
            pass

        label = preview if preview else short_label
        sessions.append({
            "id": session_id,
            "project": short_label,
            "label": label,
            "mtime": mtime,
            "path": f,
        })

    return sessions


def find_session_by_id(session_id):
    """Find a session file by its ID."""
    pattern = os.path.join(CLAUDE_DIR, "**", session_id + ".jsonl")
    files = glob.glob(pattern, recursive=True)
    return files[0] if files else None


def extract_messages(filepath):
    """Extract user/assistant text messages from a JSONL session file."""
    messages = []
    if not filepath or not os.path.exists(filepath):
        return messages

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = obj.get("type", "")

                if msg_type == "human":
                    content = obj.get("message", {})
                    if isinstance(content, dict):
                        c = content.get("content", "")
                        if isinstance(c, list):
                            texts = [p.get("text", "") for p in c
                                     if isinstance(p, dict) and p.get("type") == "text"]
                            text = "\n".join(texts)
                        else:
                            text = str(c)
                    elif isinstance(content, str):
                        text = content
                    else:
                        continue
                    if text.strip():
                        messages.append({"role": "user", "content": text.strip()})

                elif msg_type == "assistant":
                    content = obj.get("message", {})
                    if isinstance(content, dict):
                        c = content.get("content", "")
                        if isinstance(c, list):
                            texts = [p.get("text", "") for p in c
                                     if isinstance(p, dict) and p.get("type") == "text"]
                            text = "\n".join(t for t in texts if t)
                        else:
                            text = str(c)
                    elif isinstance(content, str):
                        text = content
                    else:
                        continue
                    if text.strip():
                        messages.append({"role": "assistant", "content": text.strip()})

    except Exception:
        pass

    return messages


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())

        elif parsed.path == "/api/sessions":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            sessions = list_sessions()
            # Don't send path to client
            safe = [{"id": s["id"], "project": s["project"],
                     "label": s["label"], "mtime": s["mtime"]}
                    for s in sessions]

            self.wfile.write(json.dumps({
                "sessions": safe,
            }, ensure_ascii=False).encode())

        elif parsed.path == "/api/messages":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            session_id = params.get("session", [None])[0]
            if session_id:
                filepath = find_session_by_id(session_id)
            else:
                # Fallback to latest
                all_sessions = list_sessions(limit=1)
                filepath = all_sessions[0]["path"] if all_sessions else None

            messages = extract_messages(filepath)
            file_size = os.path.getsize(filepath) if filepath and os.path.exists(filepath) else 0
            session_name = os.path.basename(filepath) if filepath else None

            self.wfile.write(json.dumps({
                "messages": messages,
                "file_size": file_size,
                "session_file": session_name,
            }, ensure_ascii=False).encode())

        else:
            self.send_response(404)
            self.end_headers()


def main():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\033[38;5;141m●\033[0m Claude Math Viewer")
    print(f"  Server:  http://localhost:{PORT}")
    print(f"  Watch:   {CLAUDE_DIR}")
    print(f"  Usage:   Just run claude in another pane")
    print(f"  Stop:    Ctrl+C\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
