---
name: template-create
description: This skill should be used when the user asks to "create a template", "テンプレート作成", "書式を登録", "XLSXをテンプレート化", "テンプレート登録", "この書式を登録して", "テンプレートを追加", or wants to register a new court document template from an XLSX file.
version: 1.0.0
---

# テンプレート作成（template-create）

ユーザーが持ち込んだXLSXファイルを分析し、入力フィールドを定義してテンプレートとして登録する。

## ワークフロー

### Step 0: Matter の解決

処理開始前に、現在アクティブな matter（事案）を解決する:

```bash
python3 skills/_lib/matter.py resolve
```

戻り値の JSON から `matter_id` と `source` を取得する。

- `matter_id` が null（`source=none`）の場合: **テンプレートは事案に紐づいて保存されるため、本スキルは matter 設定なしでは実行できない**。以下のメッセージを表示して処理を中止する:

  ```
  エラー: アクティブな matter が設定されていない。
  
  以下のいずれかを実行してから再度試してほしい:
    /matter-list         — 登録済み matter を確認
    /matter-switch <id>  — 既存 matter に切替
    /matter-create       — 新規 matter を作成
    または --matter <id> フラグで明示指定
  ```

- `matter_id` が解決できた場合: 処理を続行する。ユーザーに**1 回だけ**アクティブ matter を確認する:

  ```
  matter '{matter_id}' で処理を続行する（解決元: {source}）。
  ```

続いて、テンプレート保存先ディレクトリを解決する:

```bash
python3 skills/_lib/matter.py info {matter_id}
```

戻り値 JSON の `templates_dir` フィールドを以降のステップで `{matter_templates_dir}` として参照する。

### Step 1: XLSXファイルの確認

ユーザーにベースとなるXLSXファイルのパスを確認する。$ARGUMENTS で指定されている場合はそれを使用する。

ファイルが存在することを Glob または Read で確認する。

### Step 2: シート構造の分析

以下のMCPツールでXLSXの構造を把握する:

1. `mcp__xlsx-editor__get_workbook_info` — シート一覧、行数・列数、結合セル情報を取得
2. `mcp__xlsx-editor__read_sheet` — セルデータを取得。**大きなシート（50行超 or 結合セル多数）は `range` パラメータで30行ずつ分割して読み取る**（例: `range: "A1:N30"` → `range: "A31:N60"` → ...）。全体を一括読取するとトークン制限を超えてエラーになる場合がある

複数シートがある場合はユーザーにどのシートをテンプレート対象とするか確認する。

### Step 3: フィールド候補の提案

セルデータを分析し、入力フィールド候補を特定する。以下のパターンを探す:

**単一セルフィールド候補:**
- 空セルの左または上にラベルテキストがある箇所（例: 「氏名」の右隣が空 → テキストフィールド）
- 「年月日」「日付」等のラベル隣接空セル → 日付フィールド
- 「金額」「円」等のラベル隣接空セル → 数値フィールド
- プレースホルダ的テキスト（「○○」「記入」等）が入ったセル

**テーブルフィールド候補:**
- ヘッダ行 + 空行が繰り返される領域
- 「No.」「番号」「№」等のヘッダを持つ表形式の領域

**重要: テーブルの headerRow と dataStartRow の区別**
- ヘッダ行（headerRow）: 列ラベルが記載された行（例: №, 金融機関の名称, 残高 等）
- データ開始行（dataStartRow）: ヘッダの直下にある最初のデータ行（通常 headerRow + 1）
- `range.dataStartRow` には必ずデータ開始行を指定する。ヘッダ行を指定してはならない
- 判別方法: セルの値が列ラベル（名称、種類、金額、所在 等）であればヘッダ行。数字や具体的なデータ（○○銀行、100万円 等）であればデータ行

**選択フィールド候補:**
- データ検証（ドロップダウン）が設定されたセル

ユーザーにフィールド候補の一覧をテーブルで提示する:

```
| # | ラベル | セル位置 | 推定タイプ | 根拠 |
|---|--------|----------|-----------|------|
| 1 | 原告氏名 | C3 | text | 「原告氏名」(B3)の右隣が空 |
| 2 | 事故日 | C5 | date | 「事故年月日」(B5)の右隣が空 |
| 3 | 損害一覧 | A10:E20 | table | ヘッダ行+空行の繰り返し |
```

### Step 4: ユーザーとの対話でフィールド確定

ユーザーと対話しながら以下を確定する:

1. **フィールドの採否**: 候補を承認/却下/追加
2. **フィールドID**: 英数字のスネークケースID（例: `plaintiff_name`, `accident_date`）
3. **フィールドラベル**: 日本語表示名
4. **フィールドタイプ**: `text` | `number` | `date` | `textarea` | `select` | `table`
5. **必須/任意**: `required: true/false`
6. **セル位置**:
   - 単一セル: `position: { row: N, column: N }` (1-indexed)
   - テーブル: `range: { headerRow, dataStartRow, startColumn, endRow, endColumn }` (1-indexed)
     - `headerRow`: 列ラベルの行番号
     - `dataStartRow`: 最初のデータ行番号（**ヘッダ行ではなく、その下の行**）
7. **テーブルの場合**: 各列の定義 `columns: [{ id, label, type }]`
8. **選択の場合**: 選択肢 `options: [...]`

### Step 5: メタデータの確認

テンプレートの基本情報をユーザーに確認する:

- `id`: 一意識別子（ファイル名に使用。英数字・ハイフン）
- `title`: テンプレート名（日本語）
- `description`: 説明（1-2文）
- `category`: カテゴリ（自由記述。例: 民事訴訟, 家事事件, 交通事故, 相続, 労働）

### Step 6: YAML保存

確定したフィールド定義をYAML形式で `{matter_templates_dir}/{id}.yaml` に Write ツールで保存する（アクティブ matter のテンプレートディレクトリ内。Step 0 で matter.py info から解決した `templates_dir` を使用する）。`{matter_templates_dir}` は matter 作成時に自動生成されているはずだが、万一存在しない場合は作成する。

YAML形式はプラグインの `templates/_schema.yaml` に準拠する。

### Step 7: XLSXコピー

元のXLSXファイルを `{matter_templates_dir}/{id}.xlsx` にコピーする。`cp` コマンドは Windows で動作しないため、クロスプラットフォームの Python ヘルパーを使う:

```bash
python3 skills/_lib/copy_file.py --src "<source.xlsx>" --dst "{matter_templates_dir}/{id}.xlsx"
```

元ファイルは変更しない。

### Step 8: 完了サマリー

以下を表示する:
- 対象 matter の ID
- テンプレート名とID
- 登録フィールド数（タイプ別内訳）
- 保存先パス（YAML + XLSX。matter ディレクトリ配下）
- `/template-fill` での使用方法

## セル位置の変換

XLSXのセルアドレス（A1, B3 等）をYAMLの行列番号に変換する:
- A1 → row: 1, column: 1
- C5 → row: 5, column: 3
- 列: A=1, B=2, C=3, ... Z=26, AA=27, ...

## エラーハンドリング

- XLSX以外のファイル: 対応フォーマットを案内する。
- 空のシート: 「テンプレートとして使用するセルがありません」と報告する。
- 既存IDとの重複（現在の matter 内で既に同 ID のテンプレートがある）: 上書きするか別IDにするかユーザーに確認する。
- matter のテンプレートディレクトリが存在しない場合: 作成する。
