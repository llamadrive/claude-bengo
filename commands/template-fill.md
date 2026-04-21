---
description: 裁判所書類テンプレートに資料データを自動入力
allowed-tools: Read, Write, Glob, Bash(python3 skills/_lib/copy_file.py:*), Bash(python3 skills/_lib/audit.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/fill_gate.py:*), Bash(python3 skills/_lib/consent.py:*), mcp__xlsx-editor__*
---

登録済みXLSXテンプレートに、PDFや画像から抽出したデータを自動入力する。
テンプレートは現在の案件フォルダ（workspace）に紐づいており、case スコープの
テンプレートは `./.claude-bengo/templates/` から、global スコープの
テンプレートは `~/.claude-bengo/templates/` から自動解決される。

$ARGUMENTS の指定方法:
- ソースファイルのみ: `/template-fill 申立書.pdf` — テンプレートが1件なら自動選択、複数なら選択肢を表示
- テンプレート名 + ソース: `/template-fill 財産目録 通帳.pdf` — テンプレートを明示指定
- 複数ソース: `/template-fill 通帳1.pdf 通帳2.pdf 残高証明書.pdf` — 複数PDFからデータ統合
- 追記モード: `/template-fill --continue 財産目録_filled.xlsx 保険証書.pdf` — 既存の入力済みファイルに追加入力
- 指定なし: 対話で確認

まず `skills/template-fill/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
