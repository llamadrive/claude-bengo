---
name: verify
description: This skill should be used when the user asks to "verify", "test", "check installation", "動作確認", "テスト", "ヘルスチェック", or wants to verify that the claude-bengo plugin is working correctly.
version: 1.0.0
---

# 動作確認（verify）

claude-bengo プラグインの各機能が正常に動作するか確認する。

## モード

$ARGUMENTS の値に応じて3つのモードで動作する:

### モード1: 接続テスト（引数なし）

MCP サーバの疎通と fixtures の存在を確認する。

**手順:**
0. プラグインの更新を確認する: `Bash(git -C {plugin_dir} fetch --dry-run 2>&1)` で更新の有無を確認する。更新がある場合は「新しいバージョンが利用可能。`/bengo-update` で更新できる。」と案内する。
1. `mcp__xlsx-editor__get_workbook_info` を任意の fixtures XLSX に対して呼び出し、応答を確認する。
2. `mcp__docx-editor__get_document_info` を任意の fixtures DOCX に対して呼び出し、応答を確認する。
3. `mcp__html-report__get_component_examples` を呼び出し、応答を確認する。
4. Glob で `fixtures/` 配下の各サブディレクトリにファイルが存在することを確認する。
5. Glob で `templates/_schema.yaml` が存在することを確認する。
6. Glob で `skills/*/SKILL.md` を検索し、見つかったスキルを列挙する。件数はハードコードしない — Glob の結果をそのまま使う。

**出力:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  claude-bengo 動作確認レポート
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [1] xlsx-editor MCP ............. OK
  [2] docx-editor MCP ............. OK
  [3] html-report MCP ............. OK
  [4] fixtures .................... OK ({N} dirs)
  [5] templates ................... OK
  [6] skills ...................... OK ({M} skills)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  結果: 全項目 OK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

`{N}` と `{M}` は Glob の結果から動的に決まる。ハードコードしない。

MCP サーバが応答しない場合は、そのサーバが設定されていない旨と設定方法を案内する。

### モード2: 個別テスト（スキル名指定）

$ARGUMENTS に `template-fill`, `family-tree`, `typo-check`, `lawsuit-analysis`, `inheritance-calc`, `law-search` のいずれかが指定された場合、該当スキルの機能テストを実行する。

**共通手順:**
1. `fixtures/{skill-name}/` 配下のテストファイルを確認する。
2. ファイルが不足している場合は、不足ファイルを報告して終了する。
3. テストファイルを使用して該当スキルのワークフローを実行する。
4. 出力結果を `fixtures/{skill-name}/expected-*.json` と比較する。
5. 結果を報告する。

**template-fill テスト:**
- fixtures: `source-complaint.pdf`, `template-complaint.xlsx`, `template-complaint.yaml`, `expected-output.json`
- 実行: template-complaint.yaml を templates/ にコピー → /template-fill を実行 → 出力XLSXのセル値を expected-output.json と比較
- 成功基準: フィールド正答率 ≥ 90%

**family-tree テスト:**
- fixtures: `koseki-simple.pdf`, `expected-simple.json`
- 実行: /family-tree を実行 → 抽出された persons/relationships を expected-simple.json と比較
- 成功基準: 人物抽出 ≥ 95%、関係抽出 ≥ 90%

**typo-check テスト:**
- fixtures: `brief-with-errors.docx`, `brief-clean.docx`, `expected-corrections.json`
- 実行: /typo-check を brief-with-errors.docx に実行 → 検出結果を expected-corrections.json と比較
- 成功基準: 適合率 ≥ 85%、再現率 ≥ 75%

**lawsuit-analysis テスト:**
- fixtures: `complaint.pdf`, `answer.pdf`, `expected-timeline.json`, `expected-characters.json`
- 実行: /lawsuit-analysis を実行 → 抽出結果を expected JSONs と比較
- 成功基準: タイムライン再現率 ≥ 80%、人物再現率 ≥ 90%

### モード3: 全テスト（`all` 指定）

`fixtures/` 配下にテストデータが揃っているスキル全ての機能テストを順次実行する。実行件数はハードコードしない — fixtures が存在するスキルだけを動的に列挙する。

**出力（例）:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  claude-bengo 動作確認レポート（全テスト）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [1] MCP サーバ接続 ............. OK
  [2] /template-fill ............. OK (15/15 fields)
  [3] /family-tree ............... OK (4/4 persons, 3/3 rels)
  [4] /typo-check ................ OK (P:92% R:80%)
  [5] /lawsuit-analysis .......... OK (6/6 events, 3/3 chars)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  結果: {合格}/{実行} OK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

WARNING がある場合はその詳細を表示する。

## Fixtures がない場合

fixtures ディレクトリにテストファイルがない場合は:
1. 接続テスト（モード1）のみ実行する。
2. 「テスト用 fixtures が未設定です。fixtures/ ディレクトリにテストファイルを配置してください。」と案内する。
3. 各スキルに必要な fixtures ファイルの一覧を表示する。

## 比較ロジック

### 文字列比較
- 完全一致ではなく意味的一致で判定する。
- 日付フォーマットの差異（「令和5年」vs「2023年」）は一致とみなす。
- 全角/半角の差異は一致とみなす。

### 数値比較
- カンマの有無を無視する。
- 全角/半角を正規化して比較する。

### テーブルデータ比較
- 行の順序を無視し、内容で照合する。
- 一致率 = 正しく抽出された行数 / expected の行数。
