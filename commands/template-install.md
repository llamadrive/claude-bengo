---
description: 同梱テンプレート（裁判所書式雛形）をアクティブ matter にインストールする
allowed-tools: Read, Bash(python3 skills/_lib/template_lib.py:*), Bash(python3 skills/_lib/matter.py:*)
---

プラグインに同梱されている裁判所書式・実務書式の雛形（債権者一覧表、遺産目録、交通事故示談書等）をアクティブ matter のテンプレートディレクトリにコピーする。コピー後は `/template-fill` から選択・利用できる。

$ARGUMENTS の指定方法:
- 引数なし: 利用可能な同梱テンプレートを一覧表示する
- テンプレート ID: `/template-install creditor-list` — 指定テンプレートをインストール
- `--replace` 付き: `/template-install creditor-list --replace` — 既存を上書き

`--matter <id>` フラグでアクティブな事案を明示指定できる。

## ワークフロー

### Step 0: Matter の解決

処理開始前に、現在アクティブな matter を解決する:

```bash
python3 skills/_lib/matter.py resolve
```

- `source=none` の場合: エラーで中止し、`/matter-create` 等の案内を表示する
- `matter_id` が解決できた場合: ユーザーに 1 回だけアクティブ matter を確認する

### Step 1: 引数の解析

$ARGUMENTS が空、または `list` のみの場合 → Step 2（一覧表示）
$ARGUMENTS にテンプレート ID が含まれる場合 → Step 3（インストール）

### Step 2: 一覧表示

```bash
python3 skills/_lib/template_lib.py list
```

カテゴリ別に同梱テンプレート名・説明を表示する。ユーザーに「どれをインストールするか？」と確認し、決まれば Step 3 に進む。

### Step 3: インストール

```bash
python3 skills/_lib/template_lib.py install <bundled-id>
```

戻り値 JSON の `yaml_dst` と `xlsx_dst` にコピーされる。`--replace` なしで既存と衝突した場合はエラー（exit 3）。上書きしたい場合はユーザーに確認し、承諾されれば `--replace` 付きで再実行する。

### Step 4: 完了案内

インストール成功時、ユーザーに以下を案内する:

```
テンプレート '{title}' を matter '{matter_id}' にインストールした。
  YAML: {yaml_dst}
  XLSX: {xlsx_dst}

使い方:
  /template-list       — 現在の matter のテンプレート一覧（新テンプレートを含む）
  /template-fill       — ソース文書からこのテンプレートにデータを入力
```

## 利用可能な同梱テンプレート（v2.1.0 現在）

| ID | カテゴリ | タイトル |
|---|---|---|
| `creditor-list` | 破産・再生 | 債権者一覧表 |
| `estate-inventory` | 相続 | 遺産目録 |
| `settlement-traffic` | 交通事故 | 交通事故示談書（雛形） |

**追加予定:** 養育費算定表、離婚協議書雛形、内容証明郵便雛形、未払残業代計算書、訴状・答弁書雛形、陳述書雛形、破産・個人再生申立書、労働審判申立書等。

同梱テンプレートは参考用の雛形である。**提出前に最新の裁判所ホームページ・法テラス様式を確認**すること。レイアウトが実際の書式と異なる場合がある。

## エラーハンドリング

- **matter 未設定**: Step 0 で中止、`/matter-create` を案内
- **テンプレート ID が無効**: 同梱リストを表示して正しい ID を案内
- **既存と衝突**: `--replace` の有無を確認、ユーザーの承諾を得てから上書き
- **ファイル欠落**: レジストリと同梱ファイルの不整合。プラグインの再インストールを提案（`/bengo-update`）
