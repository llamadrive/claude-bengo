---
description: 登録済みテンプレートの一覧を表示する（ユーザースコープ + この案件の両方）
allowed-tools: Read, Glob, Bash(python3 skills/_lib/workspace.py:*)
---

ユーザースコープ（`~/.claude-bengo/templates/`）、事務所スコープ（firm-setup で
設定したフォルダ）、現在の案件フォルダの `.claude-bengo/templates/` に登録されている
テンプレートを一覧表示する。

### Step 1: 全スコープの一覧取得

```bash
python3 skills/_lib/workspace.py templates
```

戻り値の JSON:
```json
{
  "workspace_root": "...",
  "case_templates_dir": "...",
  "firm_templates_dir": "..." | null,
  "firm_status": "unconfigured" | "unreachable" | "reachable",
  "user_templates_dir": "...",
  "case":   [{ "id": "...", "broken": false,
               "shadowed_user": false, "shadowed_firm": false }, ...],
  "firm":   [{ "id": "...", "broken": false, "shadowed": false }, ...],
  "user":   [{ "id": "...", "broken": false, "shadowed": false }, ...]
}
```

`firm_status`:
- `unconfigured` — 未設定。`/template-firm-setup` を案内する
- `unreachable` — 設定済みだがランタイムでパスが見つからない（同期クライアント停止等）
- `reachable` — 正常

**broken エントリの扱い:** `broken: true` のエントリは `yaml` または `xlsx` が
欠落している半端な状態。`/template-fill` では使えないが、表示からは**隠さない**
（silently 隠すと「登録したはずなのに一覧にない」とユーザーが混乱する）。
該当行には `⚠ {missing} ファイルが欠落` を併記する。

### Step 2: 各 YAML を Read で読み取りメタデータを取得

各エントリの `yaml_path` を Read で開き、`title` / `category` / `fields` の数を取得する。

### Step 3: 表示

以下の形式で表示する（case を上、firm を中、user を下）:

```
案件 '{workspace_root の basename}' で利用可能なテンプレート:

[この案件のみ] {case_templates_dir}
  1. {title}（カテゴリ: {category} / フィールド: {N}件） ⚠ 事務所版を上書き中

[事務所スコープ] {firm_templates_dir}    [reachable]
  2. {title}（カテゴリ: {category} / フィールド: {N}件） — この案件で上書き中
  3. ...

[ユーザースコープ] {user_templates_dir}
  4. {title}（カテゴリ: {category} / フィールド: {N}件）
  5. ...

操作:
  /template-fill                 — テンプレートにデータを入力する
  /template-create               — 新規登録（既定: この案件のみ）
  /template-create --scope firm  — 事務所スコープに登録（PII 検出時は自動拒否）
  /template-create --scope user  — ユーザースコープに登録（PII 検出時は自動拒否）
  /template-install              — 同梱書式をインストール（既定: この案件のみ）
  /template-promote <id> --to firm  — 案件→事務所に昇格（PII code-gate）
  /template-demote <id> --from firm — 事務所→案件にコピー
  /template-firm-setup           — 事務所共有フォルダのローカルパスを 1 度だけ設定
```

- `case` 側エントリで `shadowed_firm: true` または `shadowed_user: true` のものは
  `⚠ {事務所/ユーザー}版を上書き中` を併記
- `firm` 側エントリで `shadowed: true` のものは `— この案件で上書き中` を併記
- `user` 側エントリで `shadowed: true` のものは `— この案件 or 事務所で上書き中` を併記
- `firm_status` が `unconfigured` の場合は `[事務所スコープ]` セクション全体を出さず、
  代わりに「事務所共有テンプレートを使うには `/template-firm-setup` を実行してほしい」と案内
- `firm_status` が `unreachable` の場合は `[事務所スコープ] (path) [⚠ unreachable]` と表示し、
  「同期クライアントを起動するか、フォルダの場所を確認してほしい」と案内
- **`broken: true` のエントリは `⚠ {missing}欠落（再登録が必要）` を併記**。これらは `/template-fill` では使えないが、どのスコープにどう残っているかを示すため必ず表示する
- 両方 0 件の場合は以下を案内:

```
テンプレートが未登録。

以下のいずれか:
  📦 同梱書式から選ぶ（推奨・31 種類）   → /template-install
  ✏️  独自の XLSX 書式を登録              → /template-create <XLSXパス>
  💡 何ができるか確認                     → /help で 1「書類を作成する」を選ぶ
```
