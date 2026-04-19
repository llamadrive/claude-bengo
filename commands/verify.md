---
description: claude-bengo プラグインの動作確認テストを実行
allowed-tools: Read, Write, Glob, mcp__xlsx-editor__get_workbook_info, mcp__xlsx-editor__read_sheet, mcp__docx-editor__get_document_info, mcp__docx-editor__read_document, mcp__agent-format__render_agent_inline, Bash(python3 scripts/verify.py:*), Bash(python3 scripts/verify_mcp_integrity.py:*), Bash(python3 skills/_lib/audit.py --self-test:*)
---

claude-bengo の各機能の動作を確認する。

$ARGUMENTS の指定方法:
- 引数なし: MCP サーバ接続テスト + fixtures 存在確認
- スキル名: 指定スキルの機能テスト（template-fill | family-tree | typo-check | lawsuit-analysis）
- `all`: 全スキルの機能テストを順次実行

まず `skills/verify/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
