---
description: 現在の案件フォルダ（workspace）に登録済みテンプレートの一覧を表示
allowed-tools: Read, Glob, Bash(python3 skills/_lib/workspace.py:*)
---

現在の workspace の `.claude-bengo/templates/` ディレクトリ内の YAML ファイル（`_schema.yaml` を除く）を一覧表示する。

### Step 1: workspace の解決

```bash
python3 skills/_lib/workspace.py resolve
```

戻り値の JSON から `workspace_root` と `initialized` を取得する。`initialized: false` の場合は「このフォルダはまだ案件フォルダとして初期化されていない。機密スキルを実行するか `workspace.py init` で初期化してほしい」と 1 行で案内して終了する。

### Step 2: テンプレートディレクトリの解決

`{workspace_root}/.claude-bengo/templates/` が対象ディレクトリ。

### Step 3: YAML の列挙・読取・表示

`{templates_dir}/*.yaml` を Glob で検索し、`_schema.yaml` を除外する。各 YAML を Read で読み取って以下の形式で表示する:

```
案件 '{workspace_root の basename}' の登録済みテンプレート:
  1. {title}（カテゴリ: {category} / フィールド: {fields数}件）
  2. ...

操作:
  /template-fill — テンプレートにデータを入力する
  /template-create — 新しいテンプレートを登録する
```

テンプレートが 0 件の場合は、以下のメッセージで 3 つの選択肢を案内する:

```
この案件フォルダにはテンプレートが未登録。

以下のいずれか:
  📦 同梱書式から選ぶ（推奨・31 種類）   → /template-install
  ✏️  独自の XLSX 書式を登録              → /template-create <XLSXパス>
  💡 何ができるか確認                     → /help で 1「書類を作成する」を選ぶ
```
