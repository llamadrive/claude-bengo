---
description: 法律文書の誤字脱字・表記揺れを校正（修正履歴付き）
allowed-tools: Read, Write, Glob, mcp__docx-editor__*, Bash(python3 skills/_lib/audit.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/first_run.py:*)
---

DOCX法律文書を日本語法律文書作成ルールに照合し、誤字脱字・文法エラー・表記揺れを検出する。
承認された修正は修正履歴（Track Changes）付きで適用する。
監査ログは現在の案件フォルダ（workspace）の `./.claude-bengo/audit.jsonl` に記録される。
`./.claude-bengo/` がまだ無ければ、実行時に現在のフォルダへ自動作成される。

$ARGUMENTS: DOCXファイルのパス（任意。なければ対話で確認）。

まず `skills/typo-check/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
