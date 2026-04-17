---
description: 現在アクティブな matter、または指定 matter の詳細を表示する
allowed-tools: Bash(python3 skills/_lib/matter.py:*)
---

現在のアクティブ matter、または指定された matter の詳細情報を表示する。

$ARGUMENTS: matter ID（任意。省略時は現在のアクティブ matter）

## 手順

### 引数なしの場合

アクティブ matter を解決する:

```bash
python3 skills/_lib/matter.py resolve
```

解決結果の `matter_id` と `source`（flag / env / cwd-ref / current / none）を表示する。
`source=none` の場合は `/matter-create` または `/matter-switch` を案内する。

続けて、その matter の詳細を表示する:

```bash
python3 skills/_lib/matter.py info {matter_id}
```

### 引数ありの場合

指定された matter の詳細を表示する:

```bash
python3 skills/_lib/matter.py info {matter_id}
```

## 表示項目

- matter ID
- path（matter ディレクトリの絶対パス）
- templates_dir（テンプレートディレクトリ）
- audit_path + audit_bytes（監査ログファイル + 現在のサイズ）
- metadata（title, client, case_number, opened, notes）

## 表示例

```
現在のアクティブ matter: smith-v-jones
  解決元: cwd-ref (/Users/you/cases/smith-v-jones/.claude-bengo-matter-ref)

詳細:
  id:           smith-v-jones
  title:        Smith v. Jones 損害賠償請求事件
  client:       Smith Corporation
  case_number:  令和6年（ワ）第1234号
  opened:       2026-04-17
  path:         /Users/you/.claude-bengo/matters/smith-v-jones
  templates:    /Users/you/.claude-bengo/matters/smith-v-jones/templates
  audit:        /Users/you/.claude-bengo/matters/smith-v-jones/audit.jsonl (12.3 KB)
```
