---
description: 裁判所書類テンプレートに資料データを自動入力
allowed-tools: Read, Write, Glob, Bash(cp:*), mcp__xlsx-editor__*
---

登録済みXLSXテンプレートに、PDFや画像から抽出したデータを自動入力する。

$ARGUMENTS にソースファイルパスが含まれる場合はそれを使用し、なければユーザーに確認する。

まず `skills/template-fill/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
