---
description: 法律文書の誤字脱字・表記揺れを校正（修正履歴付き）
allowed-tools: Read, Write, Glob, mcp__docx-editor__*, Bash(python3 skills/_lib/audit.py:*), Bash(python3 skills/_lib/matter.py:*)
---

DOCX法律文書を日本語法律文書作成ルールに照合し、誤字脱字・文法エラー・表記揺れを検出する。
承認された修正は修正履歴（Track Changes）付きで適用する。
監査ログはアクティブな matter（事案）のログに記録される。事案未設定では実行できない。

$ARGUMENTS: DOCXファイルのパス（任意。なければ対話で確認）。`--matter <id>` フラグでアクティブな事案を明示指定できる。

まず `skills/typo-check/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
