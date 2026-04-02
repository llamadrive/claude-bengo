---
description: 登録済みテンプレートの一覧を表示
allowed-tools: Read, Glob
---

templates/ ディレクトリ内の YAML ファイル（_schema.yaml を除く）を Glob で検索し、各 YAML を Read で読み取って一覧を表示する。

表示項目: テンプレート名、カテゴリ、フィールド数、ファイル名

テンプレートが0件の場合は `/template-create` での登録を案内する。
