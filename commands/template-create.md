---
description: XLSXファイルからテンプレート定義を作成・登録
allowed-tools: Read, Write, Glob, Bash(python3 skills/_lib/copy_file.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/template_detect.py:*), Bash(python3 skills/_lib/pii_scan.py:*), Bash(python3 skills/_lib/template_lib.py:*), Bash(python3 skills/_lib/first_run.py:*), mcp__xlsx-editor__*
---

XLSXファイルのセル構造を分析し、入力フィールドを特定してテンプレート定義（YAML）を作成する。
作成した定義とXLSXのコピーは、指定スコープの templates ディレクトリに保存される。
- `--scope case` の場合: `./.claude-bengo/templates/`
- `--scope global` の場合: `~/.claude-bengo/templates/`

$ARGUMENTS: XLSXファイルのパス（任意。なければ対話で確認）。

フラグ:
- `--scope case`   — この案件フォルダのみ（**既定**、v3.3.0〜）。`<workspace>/.claude-bengo/templates/`。
- `--scope global` — 事務所全体で使い回す。`~/.claude-bengo/templates/`。PII 検出時は拒否される。
- `--sample <path>` — 記入済みサンプル XLSX を指定（差分検出モード。推奨）。

まず `skills/template-create/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
