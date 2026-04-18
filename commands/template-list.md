---
description: 登録済みテンプレートの一覧を表示（アクティブな matter 単位）
allowed-tools: Read, Glob, Bash(python3 skills/_lib/matter.py:*)
---

アクティブな matter（事案）の templates ディレクトリ内の YAML ファイル（_schema.yaml を除く）を一覧表示する。
`--matter <id>` フラグでアクティブな事案を明示指定できる。

### Step 0: Matter の解決

処理開始前に、現在アクティブな matter を解決する:

```bash
python3 skills/_lib/matter.py resolve
```

戻り値の JSON から `matter_id` と `source` を取得する。

- `matter_id` が null（`source=none`）の場合: 本コマンドは matter 設定なしでは実行できない。以下のメッセージを表示して処理を中止する:

  ```
  エラー: アクティブな matter が設定されていない。
  
  以下のいずれかを実行してから再度試してほしい:
    /matter-list         — 登録済み matter を確認
    /matter-switch <id>  — 既存 matter に切替
    /matter-create       — 新規 matter を作成
    または --matter <id> フラグで明示指定
  ```

- `matter_id` が解決できた場合: 処理を続行する。

### Step 1: テンプレートディレクトリの解決

```bash
python3 skills/_lib/matter.py info {matter_id}
```

戻り値 JSON の `templates_dir` フィールドがアクティブ matter のテンプレートディレクトリ（`~/.claude-bengo/matters/{matter_id}/templates/`）である。

### Step 2: YAML の列挙・読取・表示

`{templates_dir}/*.yaml` を Glob で検索し、`_schema.yaml` を除外する。各 YAML を Read で読み取って以下の形式で表示する:

```
matter '{matter_id}' の登録済みテンプレート:
  1. {title}（カテゴリ: {category} / フィールド: {fields数}件）
  2. ...

操作:
  /template-fill — テンプレートにデータを入力する
  /template-create — 新しいテンプレートを登録する
```

テンプレートが0件の場合は、以下のメッセージで 3 つの選択肢を案内する:

```
matter '{matter_id}' にテンプレートは未登録。

以下のいずれか:
  📦 同梱書式から選ぶ（推奨・31 種類）   → /template-install
  ✏️  独自の XLSX 書式を登録              → /template-create <XLSXパス>
  💡 何ができるか確認                     → /help で 1「書類を作成する」を選ぶ
```
