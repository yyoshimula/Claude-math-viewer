# Claude Math Viewer

Claude Code の出力に含まれる LaTeX 数式をリアルタイムでレンダリングするローカルビューア。
Claude Code のセッションログ（JSONL）を直接読み取るため、パイプや `tee` は不要。

A local viewer that renders LaTeX math in Claude Code output in real time.
Reads Claude Code's JSONL session logs directly — no piping or `tee` required.

---

## デモ / Demo

ターミナルで Claude Code を普通に使うだけで、隣のブラウザペインに数式がレンダリングされます。

Just use Claude Code normally in your terminal, and math renders in a browser pane beside it.

```
$$\hat{y} = f(x, \mathcal{A}_i)$$
```
↓ KaTeX でレンダリング / Rendered by KaTeX

---

## セットアップ / Setup

### 必要なもの / Requirements

- Python 3（macOS プリインストール済み）
- ブラウザ（[cmux](https://cmux.com) のブラウザペイン推奨）

### インストール / Install

```bash
git clone https://github.com/YOUR_USERNAME/claude-math-viewer.git
cd claude-math-viewer
chmod +x claude-math
```

エイリアスを設定（任意）:

```bash
echo 'alias claude-math="/path/to/claude-math-viewer/claude-math"' >> ~/.zshrc
source ~/.zshrc
```

---

## 使い方 / Usage

### cmux の場合 / With cmux

```bash
# ビューアを起動（サーバー起動 + 右にブラウザペインが開く）
claude-math

# 同じまたは別のペインで Claude Code を普通に使う
claude
```

### Cursor の場合 / With Cursor

```bash
# ターミナルでサーバー起動
python3 server.py &
```

`Cmd+Shift+P` → `Simple Browser: Show` → `http://localhost:3456` を入力。
エディタの横ペインに数式ビューアが表示されます。

Open `Cmd+Shift+P` → `Simple Browser: Show` → enter `http://localhost:3456`.
The math viewer appears as a side pane in the editor.

### cmux なしの場合 / Without cmux

```bash
# ターミナル1: サーバー起動
python3 server.py

# ターミナル2: Claude Code を普通に使う
claude

# ブラウザで http://localhost:3456 を開く
```

---

## 機能 / Features

- **リアルタイムレンダリング** — 500ms ポーリングで数式を即座に表示
- **セッション切替** — ブラウザ上部のタブで複数セッションを切り替え可能
- **パイプ不要** — `~/.claude/projects/` の JSONL ログを直接読み取り
- **KaTeX 対応** — `$$...$$`, `$...$`, `\[...\]`, `\(...\)` すべてサポート
- **Markdown レンダリング** — ヘッダー、コードブロック、リスト等も表示
- **ダークテーマ** — 目に優しいデザイン
- **依存関係ゼロ** — Python 3 標準ライブラリのみ（KaTeX は CDN から読み込み）

---

- **Real-time rendering** — 500ms polling for near-instant math display
- **Session switcher** — Switch between multiple Claude Code sessions via browser tabs
- **No piping needed** — Reads JSONL logs directly from `~/.claude/projects/`
- **KaTeX support** — `$$...$$`, `$...$`, `\[...\]`, `\(...\)` all supported
- **Markdown rendering** — Headers, code blocks, lists, and more
- **Dark theme** — Easy on the eyes
- **Zero dependencies** — Python 3 stdlib only (KaTeX loaded from CDN)

---

## 構成 / Structure

```
claude-math-viewer/
├── server.py      — Python HTTP サーバー + HTML/KaTeX（全部入り）
├── claude-math    — ラッパースクリプト（cmux 対応）
├── .gitignore
└── README.md
```

---

## 設定 / Configuration

環境変数で変更可能:

| 変数 / Variable | デフォルト / Default | 説明 / Description |
|---|---|---|
| `CLAUDE_MATH_PORT` | `3456` | サーバーポート / Server port |

---

## 仕組み / How it works

```
Claude Code (terminal)
    ↓ writes session log
~/.claude/projects/**/*.jsonl
    ↓ reads (polling)
Python HTTP server (localhost:3456)
    ↓ serves
Browser (KaTeX rendering)
```

Claude Code はセッションログを `~/.claude/projects/` 以下に JSONL 形式で自動保存します。
本ツールのサーバーがそのファイルを監視し、user/assistant メッセージを抽出して
KaTeX 付きの HTML としてブラウザに配信します。

Claude Code automatically saves session logs as JSONL under `~/.claude/projects/`.
This tool's server watches those files, extracts user/assistant messages,
and serves them as KaTeX-enabled HTML to the browser.

---

## ライセンス / License

MIT
