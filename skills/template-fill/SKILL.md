---
name: template-fill
description: This skill should be used when the user asks to "fill a template", "テンプレート入力", "書式入力", "裁判所書類の作成", "テンプレートに入力", "書式に記入", "この書式に入れて", "PDFからテンプレートに", "書類を作成して", or wants to auto-populate court documents from source materials.
version: 1.0.0
---

# テンプレート入力（template-fill）

登録済みテンプレートに、ソース文書（PDF・画像）から抽出したデータを自動入力する。

## 前提条件

テンプレートが `/template-create` で事前登録されている必要がある。`templates/` ディレクトリに `{id}.yaml` + `{id}.xlsx` のペアが存在すること。

## ワークフロー

### Step 1: テンプレート一覧の取得

Glob で `templates/*.yaml` を検索し、`_schema.yaml` を除外する。

- **0件の場合**: ユーザーに以下の選択肢を提示する:
  - ユーザーが $ARGUMENTS や会話で XLSX ファイルを指定している場合: 「テンプレートが未登録である。この XLSX をテンプレートとして登録してからデータ入力を行うか？」と確認し、承諾されれば `skills/template-create/SKILL.md` を Read して inline でテンプレート作成フローを実行した後、続けてデータ入力に進む。
  - XLSX の指定がない場合: 「テンプレートが登録されていない。`/template-create` でテンプレートを登録してほしい。」と案内する。
- **1件の場合**: 自動選択し確認する。
- **複数件の場合**: 各YAMLを Read で読み取り、title と category を一覧表示してユーザーに選択させる。

### Step 2: ソース文書の確認

ユーザーにデータ抽出元のソース文書を確認する。$ARGUMENTS で指定されている場合はそれを使用する。

対応フォーマット:
- PDF（テキスト埋め込みまたは高解像度画像）
- 画像ファイル（PNG, JPG, JPEG）
- 複数ファイル指定可能

### Step 3: テンプレート定義の読込

選択されたYAMLを Read で読み込み、フィールド定義を取得する:
- 各フィールドの `id`, `label`, `type`, `position`/`range`
- テーブルフィールドの `columns` 定義

### Step 4: 出力ファイルの作成

テンプレートXLSXファイル（`templates/{id}.xlsx`）を出力先にコピーする（Bash の `cp`）。
出力ファイル名: `{元テンプレート名}_filled.xlsx`（またはユーザー指定）

### Step 5: ソース文書からのデータ抽出

ソース文書を Read ツール（Claude vision）で読み取る。

フィールド定義を参照しながら、各フィールドに対応するデータを抽出する。データ抽出の詳細パターン（当事者情報、事件情報、金額、日付の元号変換等）は `skills/template-fill/references/field-mapping-guide.md` を Read ツールで読み込んで参照する。抽出時の注意:

- **日付フィールド**: 元号（令和/平成/昭和等）と西暦の両方を認識する。テンプレートの既存フォーマットに合わせて変換する。
- **数値フィールド**: カンマ区切り・全角/半角を正規化する。
- **テーブルフィールド**: 複数行のデータを行ごとに分解し、各列に対応付ける。
- **選択フィールド**: options リストとのファジーマッチを行う。

### Step 6: データの書込

コピーしたXLSXに対して、xlsx-editor MCP でデータを書き込む。

**単一セルフィールド:**
`mcp__xlsx-editor__write_cell` を使用する。
- `row`: フィールドの `position.row`（1-indexed）
- `column`: フィールドの `position.column`（1-indexed、列番号を列アドレスに変換: 1→A, 2→B, ...）
- `value`: 抽出値

効率化のため、複数セルをまとめて `mcp__xlsx-editor__write_cells` で一括書込する。

**テーブルフィールド:**
1. テンプレートのテーブル範囲の `dataStartRow`（データ開始行）から書き込む。**`headerRow` には絶対に書き込まない**
2. 書き込み前に `mcp__xlsx-editor__read_sheet` で `dataStartRow` の内容を確認する。列ラベル（№, 名称, 金額 等）が含まれている場合はヘッダ行である可能性が高いため、次の行にずらす
3. データ行数がテンプレート行数（`endRow - dataStartRow + 1`）を超過する場合は `mcp__xlsx-editor__insert_rows` で行を追加する
4. `mcp__xlsx-editor__write_rows` でデータを書き込む

### Step 7: 結果サマリー

入力結果をテーブル形式で表示する:

```
| フィールド | 値 | ステータス |
|-----------|-----|----------|
| 原告氏名 | 甲野太郎 | ✓ 入力済 |
| 事故日 | 令和5年3月1日 | ✓ 入力済 |
| 請求金額 | — | ⚠ 要確認 |
```

抽出できなかったフィールドには `[要確認]` をセルに書き込み、`mcp__xlsx-editor__format_cells` で黄色背景（`#FFFF00`）を適用して視覚的に目立たせる。ユーザーに手動入力を促す。

## 複数ソース文書の統合

複数のソース文書が提供された場合:
- 各文書から独立にデータを抽出する。
- 同一フィールドに複数の値が抽出された場合はユーザーに確認する。
- テーブルフィールドは各文書のデータを統合（行を結合）する。

## エラーハンドリング

- テンプレートXLSXが見つからない: YAMLの `templateFile` を確認し、パスの修正を提案する。
- ソース文書が読めない: スキャン品質の問題を報告し、OCR済みPDFの使用を提案する。
- フィールド位置が実際のXLSXと一致しない: 警告を出し、`/template-create` での再登録を提案する。
