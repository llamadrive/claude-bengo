---
description: 戸籍謄本PDFから家族関係を分析しHTMLの相関図を生成
allowed-tools: Read, Write, Glob, Bash(python3 skills/family-tree/encode.py:*), Bash(python3 skills/_lib/audit.py:*), Bash(python3 skills/_lib/matter.py:*)
---

戸籍謄本のPDF文書から人物と関係性を抽出し、裁判所標準形式（相続関係説明図）のHTMLを生成する。
監査ログはアクティブな matter（事案）のログに記録される。事案未設定では実行できない。

$ARGUMENTS: 戸籍謄本PDFのパス（任意。なければ対話で確認）。`--matter <id>` フラグでアクティブな事案を明示指定できる。

まず `skills/family-tree/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
