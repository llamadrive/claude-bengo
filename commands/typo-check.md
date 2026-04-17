---
description: 法律文書の誤字脱字・表記揺れを校正（修正履歴付き）
allowed-tools: Read, Write, Glob, mcp__docx-editor__*, Bash(python3 skills/_lib/audit.py:*)
---

DOCX法律文書を日本語法律文書作成ルールに照合し、誤字脱字・文法エラー・表記揺れを検出する。
承認された修正は修正履歴（Track Changes）付きで適用する。

$ARGUMENTS: DOCXファイルのパス（任意。なければ対話で確認）

まず `skills/typo-check/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
