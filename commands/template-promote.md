---
description: 案件スコープのテンプレートをユーザースコープへ昇格する（この端末の全案件で使えるようにする）
allowed-tools: Read, Bash(python3 skills/_lib/template_lib.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/pii_scan.py:*)
---

現在の案件フォルダに登録されたテンプレートを `~/.claude-bengo/templates/` に
**移動**する（案件側からは削除）。移動後はこの端末のどの案件からも `/template-fill`
で選択できるようになる。

$ARGUMENTS: テンプレート ID（必須）。`--replace` で user 側の既存を上書き。

## 典型的なユースケース

案件 A のために登録した独自書式が、他の案件でも使えると気づいたとき。移動すれば
案件 A での shadowing も同時に解消される（user の 1 本にまとまる）。

## ワークフロー

### Step 1: 現状確認

```bash
python3 skills/_lib/workspace.py templates
```

戻り値 JSON の `case` 配列に対象 ID が存在するか確認する。無ければ
「この案件フォルダに `{id}` はない。`/template-list` で確認してほしい」と案内。

### Step 2: 事前 PII 確認（必須・ハードブロック）

**user に昇格するとこの端末の全案件から見えるため、クライアント情報が残っていないか
先に確認する必要がある。** 対象 XLSX に PII 形式の文字列が含まれないかを
スキャンする:

```bash
python3 skills/_lib/pii_scan.py scan --xlsx "<対象の xlsx_path>" --json
```

- `verdict: "clean"` → Step 3 へ進む
- `verdict: "suspicious"` → **v3.3.0〜 昇格を拒否する**（ユーザー override 不可）:

```
⛔ テンプレート '{id}' の昇格を中止した。
   PII のような記述が {N} 件検出されたため:
  - B3 [personal_name]: 「甲野太郎様」
  - D7 [address_jp]: 「〒100-0001 東京都千代田区...」

次のいずれかを選んでほしい:
  1. 案件側の XLSX を開いて PII を削除 → 再実行
  2. 昇格をあきらめて case スコープのまま使い続ける
```

本コマンドは PII 検出時に **スキャン結果のみを提示して終了** する。ユーザーが
「構わないから昇格して」と言っても実行しない（PII のまま user 配置は
secrecy 事故に直結するため）。どうしても昇格させたい場合は
XLSX 側を先に修正してから再実行してほしい。

**開発者・CI 専用バックドア（ユーザーに案内しないこと）:** 環境変数
`CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL=1` で PII findings を無視して昇格できる。
テスト・CI 用の escape hatch で、通常運用では設定しない。

### Step 3: 昇格実行

```bash
python3 skills/_lib/template_lib.py promote <id>
# 上書きが必要なら: python3 skills/_lib/template_lib.py promote <id> --replace
```

**PII は code レベルで強制される（v3.3.0-iter1〜）:** promote_template() が
内部で pii_scan を呼び、findings>0 なら exit 4 で終了する。Step 2 を実行しても
しなくても、最終的に code-gate が通らなければ昇格は起こらない。

戻り値 JSON:
```json
{
  "id": "...", "src_scope": "case", "dst_scope": "user",
  "src_yaml": "...", "src_xlsx": "...",
  "dst_yaml": "~/.claude-bengo/templates/{id}.yaml",
  "dst_xlsx": "~/.claude-bengo/templates/{id}.xlsx",
  "replaced": "False", "kept_original": "False", "delete_failed": "False"
}
```

exit 4 時のエラー JSON:
```json
{"error": "...", "code": "pii_found", "findings": [...], "total_findings": 5}
```

### Step 4: 完了案内

戻り値 JSON の `delete_failed` を必ずチェックする。

**`delete_failed: "False"` の通常ケース:**

```
テンプレート '{id}' をユーザースコープに昇格した。
  移動先: ~/.claude-bengo/templates/{id}.{yaml,xlsx}
  元の案件側: 削除済み（user が唯一のコピー）

以降この端末のどの案件フォルダからでも /template-fill で選択できる。
同じ ID を特定案件だけカスタマイズしたくなったら /template-demote を使う。
```

**`delete_failed: "True"` の場合（コピーは成功したが case 側の unlink に失敗）:**

```
⚠ テンプレート '{id}' のユーザー昇格は成功したが、案件側の削除に失敗した。
  ユーザー: ~/.claude-bengo/templates/{id}.{yaml,xlsx} ✅ 新規配置
  案件側:   {src_yaml} ⚠ 残存（手動削除が必要）

現在 /template-fill は **案件側を優先** するため、このまま放置すると
ユーザー昇格が実質反映されない。以下のいずれかで解決してほしい:
  1. 案件側ファイルを手動で rm してから /template-fill を使う
  2. 権限問題であれば解決後、/template-promote {id} --replace を再実行
  エラー詳細: {delete_error}
```

### エラーハンドリング

- user 側に同 ID がある → `exit 3`。`--replace` 併用を確認
- 対象 ID が case 側にない → `exit 1`。案件側の登録有無を確認
- 無効な ID 形式 → `exit 1`。パストラバーサル防御のため拒否
