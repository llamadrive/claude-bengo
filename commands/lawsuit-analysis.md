---
description: 訴訟関連文書を分析し構造化レポート（.agent 形式）を生成
allowed-tools: Read, Write, Glob, mcp__docx-editor__read_document, Bash(python3 skills/_lib/audit.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/consent.py:*), Bash(python3 skills/family-tree/open_viewer.py:*)
---

訴訟関連文書（訴状、答弁書、準備書面、証拠説明書等）を読み取り、構造化データ（タイムライン、登場人物、主張・認否・証拠）を抽出して `.agent` ファイルを生成する。
MCP Apps 対応環境（Claude Desktop, Cursor 等）では自動的にインライン描画、Claude Code CLI では既定のブラウザで viewer が自動起動する。
監査ログは現在の案件フォルダ（workspace）の `./.claude-bengo/audit.jsonl` に記録される。
`./.claude-bengo/` がまだ無ければ、実行時に現在のフォルダへ自動作成される。

$ARGUMENTS: 文書ファイルのパスまたはディレクトリ（任意。なければ対話で確認）。

まず `skills/lawsuit-analysis/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
