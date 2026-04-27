---
description: ユーザースコープのテンプレートを現在の案件フォルダにコピーする（この案件だけ微修正したいとき）
allowed-tools: Read, Bash(python3 skills/_lib/template_lib.py:*), Bash(python3 skills/_lib/workspace.py:*)
---

user または firm スコープにあるテンプレートを現在の案件フォルダの
`.claude-bengo/templates/` に **コピー**する（src 側は残す）。これにより
`/template-fill` はこの案件からは case 側を優先使用する（shadowing）。
他の案件は従来どおり src スコープを参照する。

$ARGUMENTS:
- テンプレート ID（必須）
- `--from user` — ユーザースコープ `~/.claude-bengo/templates/` から降格（既定）
- `--from firm` — 事務所スコープ（要 `/template-firm-setup`）から降格
- `--replace` で case 側の既存を上書き

## 典型的なユースケース

端末全案件用の標準書式を、この事件に限り一部カスタマイズしたい場合（項目追加・
文言差し替え等）。user を直接いじると全案件に波及してしまうため、case に
コピーしてそれを編集する。

## ワークフロー

### Step 1: 現状確認

```bash
python3 skills/_lib/workspace.py templates
```

`user` 配列に対象 ID があるか確認する。無ければ「ユーザースコープに `{id}` は
ない。`/template-install` で同梱書式から入れるか、`/template-create` で新規登録
してほしい」と案内。

### Step 2: 降格実行

```bash
python3 skills/_lib/template_lib.py demote <id>
# case 側に既存があれば: python3 skills/_lib/template_lib.py demote <id> --replace
```

戻り値 JSON（抜粋）:
```json
{
  "id": "...", "src_scope": "user", "dst_scope": "case",
  "dst_yaml": "<workspace>/.claude-bengo/templates/{id}.yaml",
  "replaced": "False", "kept_original": "True"
}
```

### Step 3: 完了案内

```
テンプレート '{id}' をこの案件フォルダにコピーした（user は維持）。
  コピー先: <workspace>/.claude-bengo/templates/{id}.{yaml,xlsx}
  ユーザースコープ: 従来どおり（他案件に影響なし）

この案件からは case 版が優先的に使われる（shadowing）。YAML / XLSX を
自由に編集してよい。変更を端末全体に反映したくなったら /template-promote
で昇格（既存 user は上書きされる点に注意）。
```

### エラーハンドリング

- case 側に同 ID がある → `exit 3`。`--replace` 併用を確認
- 対象 ID が user 側にない → `exit 1`
