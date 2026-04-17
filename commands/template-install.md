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

## 利用可能な同梱テンプレート（v2.2.0 現在）

| ID | カテゴリ | タイトル |
|---|---|---|
| `creditor-list` | 破産・再生 | 債権者一覧表 |
| `bankruptcy-dohaishi` | 破産・再生 | 破産申立書（同時廃止型・個人） |
| `estate-inventory` | 相続 | 遺産目録 |
| `inheritance-renunciation` | 相続 | 相続放棄申述書 |
| `inheritance-division-agreement` | 相続 | 遺産分割協議書 |
| `settlement-traffic` | 交通事故 | 交通事故示談書（雛形） |
| `divorce-agreement` | 家事事件 | 離婚協議書 |
| `naiyou-shoumei` | 一般民事 | 内容証明郵便（通知書） |
| `complaint-loan-repayment` | 民事訴訟 | 訴状（貸金返還請求） |
| `answer-generic` | 民事訴訟 | 答弁書（民事訴訟） |
| `overtime-calc-sheet` | 労働 | 未払残業代計算書 |
| `labor-tribunal-application` | 労働 | 労働審判申立書 |
| `power-of-attorney` | 汎用 | 委任状（弁護士） |

**追加予定:** 養育費算定表、陳述書雛形（家事・刑事）、個人再生申立書、後見開始申立書、調停申立書、支払督促申立書、示談書（刑事弁護）、株主総会議事録、内容証明（貸金催告・解除通知等のバリアント）等。

同梱テンプレートは参考用の雛形である。**提出前に最新の裁判所ホームページ・法テラス様式を確認**すること。レイアウトが実際の書式と異なる場合がある。

## エラーハンドリング

- **matter 未設定**: Step 0 で中止、`/matter-create` を案内
- **テンプレート ID が無効**: 同梱リストを表示して正しい ID を案内
- **既存と衝突**: `--replace` の有無を確認、ユーザーの承諾を得てから上書き
- **ファイル欠落**: レジストリと同梱ファイルの不整合。プラグインの再インストールを提案（`/bengo-update`）
