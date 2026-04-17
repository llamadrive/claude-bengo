---
description: XLSXファイルからテンプレート定義を作成・登録
allowed-tools: Read, Write, Glob, Bash(python3 skills/_lib/copy_file.py:*), Bash(python3 skills/_lib/matter.py:*), mcp__xlsx-editor__*
---

XLSXファイルのセル構造を分析し、入力フィールドを特定してテンプレート定義（YAML）を作成する。
作成した定義とXLSXのコピーは、アクティブな matter（事案）の templates ディレクトリに保存される。

$ARGUMENTS: XLSXファイルのパス（任意。なければ対話で確認）。`--matter <id>` フラグでアクティブな事案を明示指定できる。

まず `skills/template-create/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
