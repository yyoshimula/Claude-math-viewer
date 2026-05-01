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

import base64
import glob
import http.server
import json
import os
import struct
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

PORT = int(os.environ.get("CLAUDE_MATH_PORT", 3456))
CLAUDE_DIR = os.path.expanduser("~/.claude/projects")
CONFIG_DIR = os.path.expanduser("~/.config/claude-math-viewer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_config(updates):
    cfg = load_config()
    cfg.update(updates)
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass
    # Atomic-ish write: write to temp in the same dir, then rename.
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=CONFIG_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CONFIG_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_gemini_key():
    """Layered resolution: env var wins, then the on-disk config file."""
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if k:
        return k, "env"
    cfg = load_config()
    k = cfg.get("gemini_api_key")
    if isinstance(k, str) and k.strip():
        return k.strip(), "file"
    return None, "none"

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
    padding: 24px 24px 96px;  /* extra bottom padding so the sticky controls bar doesn't cover content */
  }

  .controls-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: rgba(10, 10, 12, 0.92);
    border-top: 1px solid var(--border);
    backdrop-filter: blur(8px);
    z-index: 100;
  }
  .controls-inner {
    max-width: 820px;
    margin: 0 auto;
    padding: 12px 24px;
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
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

  .header-right {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .speech-toggle {
    padding: 5px 12px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-dim);
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.04em;
    cursor: pointer;
    transition: all 0.2s;
  }
  .speech-toggle:hover {
    border-color: var(--accent-dim);
    color: var(--text);
  }
  .speech-toggle.on {
    border-color: var(--accent);
    background: rgba(129, 140, 248, 0.12);
    color: var(--text-bright);
  }

  .voice-select {
    padding: 5px 8px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-dim);
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    cursor: pointer;
    max-width: 140px;
  }
  .voice-select:hover { color: var(--text); border-color: var(--accent-dim); }

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
    padding: 8px 0;
    scrollbar-width: none;
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--bg);
    border-bottom: 1px solid var(--border);
    backdrop-filter: blur(6px);
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
    <div class="header-right">
      <div class="status">
        <div class="status-dot" id="statusDot"></div>
        <span id="statusText">waiting</span>
      </div>
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

<div class="controls-bar">
  <div class="controls-inner">
    <select class="voice-select" id="backendSelect" title="TTSバックエンド">
      <option value="say">macOS</option>
      <option value="gemini">Gemini</option>
    </select>
    <select class="voice-select" id="voiceSelect" title="読み上げ音声"></select>
    <button class="speech-toggle" id="apiKeyBtn" type="button" style="display:none" title="Gemini APIキーを設定">APIキー</button>
    <button class="speech-toggle" id="speechToggle" type="button">音声 OFF</button>
  </div>
</div>

<script>
const POLL_MS = 500;
const SESSION_POLL_MS = 3000;
let currentSession = null;  // null = auto (latest)
let lastMsgCount = 0;
let lastFileSize = 0;
let sessions = [];
let speechEnabled = false;
let lastSpokenIndex = -1;  // index in messages[] of last assistant msg we've already dispatched
let selectedBackend = localStorage.getItem('cmv.backend') || 'say';
let voicesByBackend = {};
try { voicesByBackend = JSON.parse(localStorage.getItem('cmv.voicesByBackend') || '{}'); } catch(e) {}
// Back-compat: legacy single 'cmv.voice' key from earlier version.
const legacyVoice = localStorage.getItem('cmv.voice');
if (legacyVoice && !voicesByBackend.say) voicesByBackend.say = legacyVoice;
let selectedVoice = voicesByBackend[selectedBackend] || (selectedBackend === 'gemini' ? 'Kore' : 'Kyoko');

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function basicMarkdown(text) {
  // Protect display math from markdown processing, and at the same time collapse any
  // embedded newlines to spaces so KaTeX auto-render can find them as a single block.
  // Doing the collapse here (not as a separate pre-pass) avoids the classic pitfall
  // where a naive `/\$\$[\s\S]*?\$\$/` pre-pass pairs the *closing* `$$` of one block
  // with the *opening* `$$` of the next, swallowing the plain text (headings, ---,
  // tables) that sits between them.
  const mathBlocks = [];
  text = text.replace(/\$\$([^$]+)\$\$/g, (_, inner) => {
    mathBlocks.push('$$' + inner.replace(/\n/g, ' ').trim() + '$$');
    return '%%MATH_' + (mathBlocks.length - 1) + '%%';
  });
  text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_, inner) => {
    mathBlocks.push('\\[' + inner.replace(/\n/g, ' ').trim() + '\\]');
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
  lastSpokenIndex = -1;  // baseline will be re-established on first poll
  postSpeak('');  // stop any in-flight speech from the previous session
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
      const prevMsgCount = lastMsgCount;
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

      // On first load of a session, don't replay history — mark everything already spoken.
      if (prevMsgCount === 0 && lastSpokenIndex < 0) {
        lastSpokenIndex = data.messages.length - 1;
      } else {
        maybeSpeakNew(data.messages);
      }
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

function stripForSpeech(text) {
  let t = text;
  t = t.replace(/```[\s\S]*?```/g, ' コード省略 ');
  t = t.replace(/`[^`]+`/g, '');
  t = t.replace(/\$\$[\s\S]*?\$\$/g, ' 数式 ');
  t = t.replace(/\\\[[\s\S]*?\\\]/g, ' 数式 ');
  t = t.replace(/\$[^$\n]+\$/g, ' 数式 ');
  t = t.replace(/\\\([\s\S]*?\\\)/g, ' 数式 ');
  t = t.replace(/^\|.*\|\s*$/gm, '');
  t = t.replace(/^#{1,6}\s+/gm, '');
  t = t.replace(/^>\s+/gm, '');
  t = t.replace(/^---+\s*$/gm, '');
  t = t.replace(/\*\*(.+?)\*\*/g, '$1');
  t = t.replace(/\*(.+?)\*/g, '$1');
  t = t.replace(/__(.+?)__/g, '$1');
  t = t.replace(/_(.+?)_/g, '$1');
  t = t.replace(/^[-*]\s+/gm, '');
  t = t.replace(/^\d+\.\s+/gm, '');
  t = t.replace(/\s+/g, ' ').trim();
  return t;
}

function postSpeak(text) {
  fetch('/api/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: text, voice: selectedVoice, backend: selectedBackend }),
  }).catch(() => {});
}

function rememberVoice() {
  voicesByBackend[selectedBackend] = selectedVoice;
  localStorage.setItem('cmv.voicesByBackend', JSON.stringify(voicesByBackend));
}

async function loadVoicesForBackend() {
  const sel = document.getElementById('voiceSelect');
  const keyBtn = document.getElementById('apiKeyBtn');
  try {
    const res = await fetch('/api/voices?backend=' + encodeURIComponent(selectedBackend));
    if (!res.ok) return;
    const data = await res.json();
    const voices = data.voices || [];
    if (voices.length === 0) { sel.style.display = 'none'; return; }
    sel.style.display = '';
    sel.innerHTML = '';
    const stored = voicesByBackend[selectedBackend];
    const fallback = selectedBackend === 'gemini' ? 'Kore' : 'Kyoko';
    if (stored && voices.includes(stored)) selectedVoice = stored;
    else selectedVoice = voices.includes(fallback) ? fallback : voices[0];
    voices.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      if (v === selectedVoice) opt.selected = true;
      sel.appendChild(opt);
    });
    rememberVoice();

    if (selectedBackend === 'gemini') {
      keyBtn.style.display = '';
      if (!data.gemini_available) {
        setStatus('error', 'APIキー未設定');
      } else if (data.gemini_key_source === 'env') {
        keyBtn.title = '環境変数で設定済み (UIからの変更は反映されません)';
      } else {
        keyBtn.title = 'Gemini APIキーを変更';
      }
    } else {
      keyBtn.style.display = 'none';
    }
  } catch (e) {}
}

async function promptAndSaveApiKey() {
  const key = prompt(
    'Gemini APIキーを入力 (https://aistudio.google.com/apikey で発行)\n\n' +
    '保存先: ~/.config/claude-math-viewer/config.json (600)'
  );
  if (!key) return;
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gemini_api_key: key.trim() }),
    });
    if (res.ok) {
      setStatus('live', 'APIキー保存しました');
      loadVoicesForBackend();
    } else {
      const err = await res.json().catch(() => ({}));
      setStatus('error', 'APIキー保存失敗: ' + (err.error || res.status));
    }
  } catch (e) {
    setStatus('error', 'APIキー保存失敗: 通信エラー');
  }
}

function maybeSpeakNew(messages) {
  // Only speak the latest assistant message newer than lastSpokenIndex;
  // skip any intermediate ones (interrupt semantics).
  if (!speechEnabled) {
    lastSpokenIndex = messages.length - 1;
    return;
  }
  let target = -1;
  for (let i = messages.length - 1; i > lastSpokenIndex; i--) {
    if (messages[i].role === 'assistant') { target = i; break; }
  }
  lastSpokenIndex = messages.length - 1;
  if (target >= 0) {
    const plain = stripForSpeech(messages[target].content);
    if (plain) postSpeak(plain);
  }
}

function updateSpeechButton() {
  const btn = document.getElementById('speechToggle');
  btn.textContent = speechEnabled ? '音声 ON' : '音声 OFF';
  btn.classList.toggle('on', speechEnabled);
}

function toggleSpeech() {
  speechEnabled = !speechEnabled;
  updateSpeechButton();
  if (speechEnabled) {
    // Baseline: don't replay existing history — only speak messages arriving from now on.
    lastSpokenIndex = lastMsgCount - 1;
  } else {
    // Stop any in-flight speech.
    postSpeak('');
  }
}

document.getElementById('speechToggle').addEventListener('click', toggleSpeech);
document.getElementById('voiceSelect').addEventListener('change', (e) => {
  selectedVoice = e.target.value;
  rememberVoice();
  if (speechEnabled) postSpeak('');  // stop current playback; next msg uses new voice
});
document.getElementById('backendSelect').value = selectedBackend;
document.getElementById('backendSelect').addEventListener('change', (e) => {
  selectedBackend = e.target.value;
  localStorage.setItem('cmv.backend', selectedBackend);
  if (speechEnabled) postSpeak('');
  loadVoicesForBackend();
});
document.getElementById('apiKeyBtn').addEventListener('click', promptAndSaveApiKey);

// Initial load
loadVoicesForBackend();
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


# Shared playback state — both `say` and `afplay` are tracked here so either
# backend can preempt whatever is currently playing.
_playback_state = {"proc": None}
_playback_lock = threading.Lock()

# Cache of ja_JP voices parsed once from `say -v '?'`.
_voice_cache = {"say": None}

# Gemini 2.5 Flash TTS prebuilt voices (from the public docs). No per-locale filter;
# each voice is multilingual and the model infers Japanese from the input text.
GEMINI_VOICES = [
    "Kore", "Puck", "Zephyr", "Charon", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_SAMPLE_RATE = 24000


def list_japanese_voices():
    """Parse `say -v '?'` and return deduplicated ja_JP voice names."""
    if _voice_cache["say"] is not None:
        return _voice_cache["say"]
    names = []
    try:
        out = subprocess.check_output(["say", "-v", "?"], stderr=subprocess.DEVNULL,
                                       timeout=5).decode("utf-8", "replace")
        seen = set()
        for line in out.splitlines():
            if "ja_JP" not in line:
                continue
            paren = line.find("(")
            name = (line[:paren] if paren > 0 else line.split("  ")[0]).strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    except Exception:
        pass
    _voice_cache["say"] = names
    return names


def voices_for_backend(backend):
    if backend == "gemini":
        return list(GEMINI_VOICES)
    return list_japanese_voices()


def _stop_current_playback_locked():
    """Caller must hold _playback_lock."""
    prev = _playback_state["proc"]
    if prev is not None and prev.poll() is None:
        try:
            prev.terminate()
        except Exception:
            pass
    _playback_state["proc"] = None


def _start_say(text, voice):
    voices = list_japanese_voices()
    if voices and voice not in voices:
        voice = "Kyoko"
    try:
        proc = subprocess.Popen(
            ["say", "-v", voice],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None
    try:
        proc.stdin.write(text.encode("utf-8"))
        proc.stdin.close()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
        return None
    return proc


def _gemini_synthesize(text, voice):
    """Call Gemini TTS, return raw PCM bytes (24kHz 16-bit mono) or None on error."""
    api_key, _ = get_gemini_key()
    if not api_key:
        print("[tts] Gemini API key not set (env or ~/.config/claude-math-viewer/config.json)")
        return None
    if voice not in GEMINI_VOICES:
        voice = "Kore"
    # Gemini TTS treats the text as a prompt, not raw speech content. Wrap with an
    # explicit "read aloud" instruction or it will try to reply and return HTTP 400
    # ("Model tried to generate text, but it should only be used for TTS").
    tts_prompt = f"次の文章をそのまま自然な声で読み上げてください:\n\n{text}"
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent")
    body = json.dumps({
        "contents": [{"parts": [{"text": tts_prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice},
                },
            },
        },
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            err_body = ""
        print(f"[tts] gemini HTTP {e.code}: {err_body}")
        return None
    except Exception as e:
        print(f"[tts] gemini request failed: {e}")
        return None
    try:
        parts = data["candidates"][0]["content"]["parts"]
        for p in parts:
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    except (KeyError, IndexError, TypeError):
        pass
    print(f"[tts] gemini: no audio in response: {str(data)[:300]}")
    return None


def _write_wav(pcm_bytes, sample_rate=GEMINI_SAMPLE_RATE):
    """Wrap raw 16-bit mono PCM in a WAV container; return the temp file path."""
    fd, path = tempfile.mkstemp(prefix="cmv-tts-", suffix=".wav")
    try:
        num_channels = 1
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(pcm_bytes)
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + data_size, b"WAVE",
            b"fmt ", 16, 1, num_channels, sample_rate, byte_rate,
            block_align, bits_per_sample,
            b"data", data_size,
        )
        with os.fdopen(fd, "wb") as f:
            f.write(header)
            f.write(pcm_bytes)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            os.unlink(path)
        except Exception:
            pass
        raise
    return path


def _start_afplay(wav_path):
    try:
        return subprocess.Popen(
            ["afplay", wav_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None


def speak(text, backend="say", voice="Kyoko"):
    """Dispatch to the selected backend. Empty text just stops current playback."""
    if not text:
        with _playback_lock:
            _stop_current_playback_locked()
        return

    if backend == "gemini":
        # Synthesize *before* taking the lock so concurrent /api/messages polls aren't
        # blocked. The synthesis call is the slow part (~1-2s round-trip).
        pcm = _gemini_synthesize(text, voice)
        if not pcm:
            return
        try:
            wav_path = _write_wav(pcm)
        except Exception as e:
            print(f"[tts] wav write failed: {e}")
            return
        with _playback_lock:
            _stop_current_playback_locked()
            proc = _start_afplay(wav_path)
            if proc is not None:
                _playback_state["proc"] = proc
        return

    # default: macOS `say`
    with _playback_lock:
        _stop_current_playback_locked()
        proc = _start_say(text, voice)
        if proc is not None:
            _playback_state["proc"] = proc


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _allowed_origin(self):
        """CSRF guard: if an Origin header is present, require it to be our own
        localhost origin. Non-browser clients (curl, scripts) omit Origin entirely
        and are allowed through."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        allowed = (f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}")
        return origin in allowed

    def do_POST(self):
        if not self._allowed_origin():
            self.send_response(403)
            self.end_headers()
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/config":
            length = int(self.headers.get("Content-Length", 0) or 0)
            key = ""
            if length > 0:
                try:
                    body = self.rfile.read(length)
                    data = json.loads(body)
                    if isinstance(data, dict):
                        k = data.get("gemini_api_key", "")
                        if isinstance(k, str):
                            key = k.strip()
                except Exception:
                    pass
            if not key:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"error":"missing gemini_api_key"}')
                return
            try:
                save_config({"gemini_api_key": key})
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(
                    {"error": f"save failed: {e}"}).encode())
                return
            self.send_response(204)
            self.end_headers()
            return

        if parsed.path == "/api/speak":
            length = int(self.headers.get("Content-Length", 0) or 0)
            text = ""
            voice = "Kyoko"
            backend = "say"
            if length > 0:
                try:
                    body = self.rfile.read(length)
                    data = json.loads(body)
                    if isinstance(data, dict):
                        t = data.get("text", "")
                        if isinstance(t, str):
                            text = t
                        v = data.get("voice", "")
                        if isinstance(v, str) and v:
                            voice = v
                        b = data.get("backend", "")
                        if isinstance(b, str) and b in ("say", "gemini"):
                            backend = b
                except Exception:
                    text = ""
            # Cap to a sane length; trailing cutoff is fine for TTS.
            if len(text) > 4000:
                text = text[:4000]
            # Run in a thread so the HTTP request returns immediately; the client
            # does not need to block on the TTS round-trip.
            threading.Thread(target=speak, args=(text, backend, voice),
                             daemon=True).start()
            self.send_response(204)
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())

        elif parsed.path == "/api/voices":
            backend = params.get("backend", ["say"])[0]
            if backend not in ("say", "gemini"):
                backend = "say"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            key, source = get_gemini_key()
            self.wfile.write(json.dumps({
                "voices": voices_for_backend(backend),
                "backend": backend,
                "gemini_available": bool(key),
                "gemini_key_source": source,  # "env" | "file" | "none"
            }, ensure_ascii=False).encode())

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
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
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
