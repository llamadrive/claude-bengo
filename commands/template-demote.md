---
description: 事務所グローバルのテンプレートを現在の案件フォルダにコピーする（この案件だけ微修正したいとき）
allowed-tools: Read, Bash(python3 skills/_lib/template_lib.py:*), Bash(python3 skills/_lib/workspace.py:*)
---

`~/.claude-bengo/templates/` にあるテンプレートを現在の案件フォルダの
`.claude-bengo/templates/` に **コピー**する（global 側は残す）。これにより
`/template-fill` はこの案件からは case 側を優先使用する（shadowing）。
他の案件は従来どおり global を参照する。

$ARGUMENTS: テンプレート ID（必須）。`--replace` で case 側の既存を上書き。

## 典型的なユースケース

firm-wide の標準書式を、この事件に限り一部カスタマイズしたい場合（項目追加・
文言差し替え等）。global を直接いじると全案件に波及してしまうため、case に
コピーしてそれを編集する。

## ワークフロー

### Step 1: 現状確認

```bash
python3 skills/_lib/workspace.py templates
```

`global` 配列に対象 ID があるか確認する。無ければ「事務所グローバルに `{id}` は
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
  "id": "...", "src_scope": "global", "dst_scope": "case",
  "dst_yaml": "<workspace>/.claude-bengo/templates/{id}.yaml",
  "replaced": "False", "kept_original": "True"
}
```

### Step 3: 完了案内

```
テンプレート '{id}' をこの案件フォルダにコピーした（global は維持）。
  コピー先: <workspace>/.claude-bengo/templates/{id}.{yaml,xlsx}
  事務所全体: 従来どおり（他案件に影響なし）

この案件からは case 版が優先的に使われる（shadowing）。YAML / XLSX を
自由に編集してよい。変更を事務所全体に反映したくなったら /template-promote
で昇格（既存 global は上書きされる点に注意）。
```

### エラーハンドリング

- case 側に同 ID がある → `exit 3`。`--replace` 併用を確認
- 対象 ID が global 側にない → `exit 1`
