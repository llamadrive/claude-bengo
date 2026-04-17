---
description: 訴訟関連文書を分析し構造化レポート（HTML）を生成
allowed-tools: Read, Write, Glob, mcp__docx-editor__read_document, mcp__html-report__*, Bash(python3 skills/_lib/audit.py:*), Bash(python3 skills/_lib/matter.py:*)
---

訴訟関連文書（訴状、答弁書、準備書面、証拠説明書等）を読み取り、構造化データ（タイムライン、登場人物、主張・認否・証拠）を抽出してHTMLレポートを生成する。
監査ログはアクティブな matter（事案）のログに記録される。事案未設定では実行できない。

$ARGUMENTS: 文書ファイルのパスまたはディレクトリ（任意。なければ対話で確認）。`--matter <id>` フラグでアクティブな事案を明示指定できる。

まず `skills/lawsuit-analysis/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
