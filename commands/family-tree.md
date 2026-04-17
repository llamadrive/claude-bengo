---
description: 戸籍謄本PDFから家族関係を分析しHTMLの相関図を生成
allowed-tools: Read, Write, Glob, Bash(python3 skills/family-tree/encode.py:*), Bash(python3 skills/_lib/audit.py:*)
---

戸籍謄本のPDF文書から人物と関係性を抽出し、裁判所標準形式（相続関係説明図）のHTMLを生成する。

$ARGUMENTS: 戸籍謄本PDFのパス（任意。なければ対話で確認）

まず `skills/family-tree/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
