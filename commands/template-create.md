---
description: XLSXファイルからテンプレート定義を作成・登録
allowed-tools: Read, Write, Glob, Bash(cp:*), mcp__xlsx-editor__*
---

XLSXファイルのセル構造を分析し、入力フィールドを特定してテンプレート定義（YAML）を作成する。
作成した定義とXLSXのコピーを templates/ ディレクトリに保存する。

$ARGUMENTS: XLSXファイルのパス（任意。なければ対話で確認）

まず `skills/template-create/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
