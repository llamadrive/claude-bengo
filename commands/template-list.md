---
description: 登録済みテンプレートの一覧を表示する（事務所グローバル + この案件の両方）
allowed-tools: Read, Glob, Bash(python3 skills/_lib/workspace.py:*)
---

事務所グローバル（`~/.claude-bengo/templates/`）と、現在の案件フォルダの
`.claude-bengo/templates/` の両方に登録されているテンプレートを一覧表示する。

### Step 1: 両スコープの一覧取得

```bash
python3 skills/_lib/workspace.py templates
```

戻り値の JSON:
```json
{
  "workspace_root": "...",
  "case_templates_dir": "...",
  "global_templates_dir": "...",
  "case":   [{ "id": "...", "yaml_path": "...", "xlsx_path": "...",
               "broken": false, "missing": null, "shadowed_global": false }, ...],
  "global": [{ "id": "...", "yaml_path": "...", "xlsx_path": "...",
               "broken": false, "missing": null, "shadowed": false }, ...]
}
```

**broken エントリの扱い:** `broken: true` のエントリは `yaml` または `xlsx` が
欠落している半端な状態。`/template-fill` では使えないが、表示からは**隠さない**
（silently 隠すと「登録したはずなのに一覧にない」とユーザーが混乱する）。
該当行には `⚠ {missing} ファイルが欠落` を併記する。

### Step 2: 各 YAML を Read で読み取りメタデータを取得

各エントリの `yaml_path` を Read で開き、`title` / `category` / `fields` の数を取得する。

### Step 3: 表示

以下の形式で表示する（case を上、global を下）:

```
案件 '{workspace_root の basename}' で利用可能なテンプレート:

[この案件のみ] {case_templates_dir}
  1. {title}（カテゴリ: {category} / フィールド: {N}件） ⚠ 事務所版を上書き中
  2. ...

[事務所全体] {global_templates_dir}
  3. {title}（カテゴリ: {category} / フィールド: {N}件）
  4. ...（上書きされている行は「— この案件で上書き中」と付記）

操作:
  /template-fill                   — テンプレートにデータを入力する
  /template-create                 — 新規登録（既定: この案件のみ）
  /template-create --scope global  — 事務所全体に登録（PII 検出時は自動拒否）
  /template-install                — 同梱書式をインストール（既定: この案件のみ）
  /template-promote <id>           — 案件→事務所全体に昇格（PII code-gate）
  /template-demote <id>            — 事務所全体→案件にコピー
```

- `case` 側エントリで `shadowed_global: true` のものは `⚠ 事務所版を上書き中` を併記
- `global` 側エントリで `shadowed: true` のものは `— この案件で上書き中` を併記
- **`broken: true` のエントリは `⚠ {missing}欠落（再登録が必要）` を併記**。これらは `/template-fill` では使えないが、案件/グローバルどちらにどう残っているかを示すため必ず表示する
- 両方 0 件の場合は以下を案内:

```
テンプレートが未登録。

以下のいずれか:
  📦 同梱書式から選ぶ（推奨・31 種類）   → /template-install
  ✏️  独自の XLSX 書式を登録              → /template-create <XLSXパス>
  💡 何ができるか確認                     → /help で 1「書類を作成する」を選ぶ
```
