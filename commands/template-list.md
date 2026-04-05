---
description: 登録済みテンプレートの一覧を表示
allowed-tools: Read, Glob
---

作業ディレクトリの `templates/` 内の YAML ファイル（_schema.yaml を除く）を Glob で検索し、各 YAML を Read で読み取って一覧を表示する。

表示形式:
```
登録済みテンプレート:
  1. {title}（カテゴリ: {category} / フィールド: {fields数}件）
  2. ...

操作:
  /template-fill — テンプレートにデータを入力する
  /template-create — 新しいテンプレートを登録する
```

テンプレートが0件の場合は `/template-create` での登録を案内する。
プラグインディレクトリ `~/.claude/plugins/claude-bengo/templates/` にサンプルがある場合はそれも案内する。
