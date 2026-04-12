# Claude Math Viewer

Claude Code の出力に含まれる LaTeX 数式をリアルタイムでレンダリングするローカルビューアです。
Claude Code のセッションログ（JSONL）を直接読み取るため、パイプや `tee` は不要です。

A local viewer that renders LaTeX math in Claude Code output in real time.
It reads Claude Code session logs (JSONL) directly, so no piping or `tee` is required.

---

## デモ / Demo

### 日本語

ターミナルで Claude Code を普通に使うだけで、隣のブラウザペインに数式がレンダリングされます。

```
$$\hat{y} = f(x, \mathcal{A}_i)$$
```

KaTeX でレンダリングされます。

### English

Just use Claude Code normally in your terminal, and math will render in a browser pane beside it.

```
$$\hat{y} = f(x, \mathcal{A}_i)$$
```

Rendered with KaTeX.

---

## セットアップ / Setup

### 日本語

#### 必要なもの

- Python 3（macOS では通常プリインストール）
- ブラウザ（[cmux](https://cmux.com) のブラウザペイン推奨）

#### インストール

```bash
git clone https://github.com/YOUR_USERNAME/claude-math-viewer.git
cd claude-math-viewer
chmod +x claude-math
```

エイリアス設定（任意）:

```bash
echo 'alias claude-math="/path/to/claude-math-viewer/claude-math"' >> ~/.zshrc
source ~/.zshrc
```

### English

#### Requirements

- Python 3 (usually preinstalled on macOS)
- A browser ([cmux](https://cmux.com) browser pane recommended)

#### Install

```bash
git clone https://github.com/YOUR_USERNAME/claude-math-viewer.git
cd claude-math-viewer
chmod +x claude-math
```

Optional alias setup:

```bash
echo 'alias claude-math="/path/to/claude-math-viewer/claude-math"' >> ~/.zshrc
source ~/.zshrc
```

---

## 使い方 / Usage

### 日本語

#### cmux の場合

```bash
# ビューアを起動（サーバー起動 + 右にブラウザペインが開く）
claude-math

# 同じまたは別のペインで Claude Code を普通に使う
claude
```

#### Cursor の場合

```bash
# ターミナルでサーバー起動
python3 server.py &
```

`Cmd+Shift+P` → `Simple Browser: Show` → `http://localhost:3456` を入力すると、
エディタ横のペインに数式ビューアが表示されます。

#### cmux なしの場合

```bash
# ターミナル1: サーバー起動
python3 server.py

# ターミナル2: Claude Code を普通に使う
claude

# ブラウザで http://localhost:3456 を開く
```

#### 動作確認と終了

サーバーが起動しているかは、別ターミナルで以下を実行して確認できます。

```bash
lsof -nP -iTCP:3456 -sTCP:LISTEN
```

`python3` などのプロセスが表示されれば、サーバーは `3456` 番ポートで待ち受け中です。ポートを変更している場合は `3456` をその値に置き換えてください。

終了方法:

```bash
# 前景で起動した場合
Ctrl+C

# バックグラウンドで起動した場合
kill $(lsof -tiTCP:3456 -sTCP:LISTEN)
```

ポートを変更している場合は `3456` をその値に置き換えてください。

### English

#### With cmux

```bash
# Start the viewer (launches the server and opens a browser pane on the right)
claude-math

# Use Claude Code normally in the same or another pane
claude
```

#### With Cursor

```bash
# Start the server from the terminal
python3 server.py &
```

Open `Cmd+Shift+P` → `Simple Browser: Show` → enter `http://localhost:3456`.
The math viewer will appear as a side pane in the editor.

#### Without cmux

```bash
# Terminal 1: start the server
python3 server.py

# Terminal 2: use Claude Code normally
claude

# Open http://localhost:3456 in your browser
```

#### Verify and Stop

You can verify that the server is running from another terminal:

```bash
lsof -nP -iTCP:3456 -sTCP:LISTEN
```

If you see a process such as `python3`, the server is listening on port `3456`. If you changed the port, replace `3456` with that value.

How to stop:

```bash
# If started in the foreground
Ctrl+C

# If started in the background
kill $(lsof -tiTCP:3456 -sTCP:LISTEN)
```

If you changed the port, replace `3456` with that value.

---

## 機能 / Features

### 日本語

- **リアルタイムレンダリング**: 500ms ポーリングで数式を即座に表示
- **セッション切替**: ブラウザ上部のタブで複数セッションを切り替え可能
- **パイプ不要**: `~/.claude/projects/` の JSONL ログを直接読み取り
- **KaTeX 対応**: `$$...$$`, `$...$`, `\[...\]`, `\(...\)` をサポート
- **Markdown レンダリング**: ヘッダー、コードブロック、リストなども表示
- **ダークテーマ**: 目に優しいデザイン
- **依存関係ゼロ**: Python 3 標準ライブラリのみ使用（KaTeX は CDN から読み込み）

### English

- **Real-time rendering**: 500ms polling for near-instant math display
- **Session switcher**: switch between multiple Claude Code sessions via browser tabs
- **No piping needed**: reads JSONL logs directly from `~/.claude/projects/`
- **KaTeX support**: supports `$$...$$`, `$...$`, `\[...\]`, and `\(...\)`
- **Markdown rendering**: displays headers, code blocks, lists, and more
- **Dark theme**: easy on the eyes
- **Zero dependencies**: uses only the Python 3 standard library (KaTeX is loaded from CDN)

---

## 構成 / Structure

### 日本語

```text
claude-math-viewer/
├── server.py      — Python HTTP サーバー + HTML/KaTeX（全部入り）
├── claude-math    — ラッパースクリプト（cmux 対応）
├── .gitignore
└── README.md
```

### English

```text
claude-math-viewer/
├── server.py      — Python HTTP server + embedded HTML/KaTeX
├── claude-math    — Wrapper script with cmux support
├── .gitignore
└── README.md
```

---

## 設定 / Configuration

### 日本語

環境変数で変更できます。

| 変数 | デフォルト | 説明 |
|---|---|---|
| `CLAUDE_MATH_PORT` | `3456` | サーバーポート |

### English

You can change the behavior with environment variables.

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_MATH_PORT` | `3456` | Server port |

---

## 仕組み / How It Works

### 日本語

```text
Claude Code (terminal)
    ↓ writes session log
~/.claude/projects/**/*.jsonl
    ↓ reads (polling)
Python HTTP server (localhost:3456)
    ↓ serves
Browser (KaTeX rendering)
```

Claude Code はセッションログを `~/.claude/projects/` 以下に JSONL 形式で自動保存します。
このツールのサーバーがそのファイルを監視し、user/assistant メッセージを抽出して、
KaTeX 付きの HTML としてブラウザに配信します。

### English

```text
Claude Code (terminal)
    ↓ writes session log
~/.claude/projects/**/*.jsonl
    ↓ reads (polling)
Python HTTP server (localhost:3456)
    ↓ serves
Browser (KaTeX rendering)
```

Claude Code automatically saves session logs as JSONL under `~/.claude/projects/`.
This tool watches those files, extracts user and assistant messages,
and serves them to the browser as KaTeX-enabled HTML.

---

## ライセンス / License

### 日本語

MIT

### English

MIT
