---
description: 新規 matter（事案）を作成する
allowed-tools: Read, Bash(python3 skills/_lib/matter.py:*)
---

新しい matter（事案）を作成する。事案ごとにテンプレート・監査ログを分離して管理できる。

$ARGUMENTS の指定方法:
- 引数なし: 対話で matter ID・title・client 等を確認する
- matter ID 指定: `/matter-create smith-v-jones` — ID を指定して作成（他フィールドは対話）
- `--import-from-cwd`: 現在の作業ディレクトリの `templates/` を新規 matter に取り込む（v1.x からの移行用）

## ワークフロー

### Step 0: データ取扱い同意の確認（初回のみ）

既存 matter が 0 件の場合（`python3 skills/_lib/matter.py list --format json` が空配列を返す場合）、初回利用として以下の案内を必ず表示する:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  データ取扱いの確認（初回）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

本プラグインで処理する文書は、以下のように扱われる:

  • Anthropic Claude API（米国リージョン）へ送信される
  • 商用 API では学習には使用されない
  • デフォルトで 30 日間のログ保持（ZDR 契約で無効化可能）
  • 監査ログは ~/.claude-bengo/matters/{id}/audit.jsonl に
    SHA-256 ハッシュチェーン付きで記録される

続行する前に、所属事務所の AI 利用ポリシー・弁護士法第23条・
個人情報保護法の遵守要件を確認してほしい。

同意して続行するか？（yes/no）
```

`yes` 以外を回答された場合は処理を中止し、`/bengo-update` の README 参照を案内する。

### Step 1: ユーザー入力の確認

$ARGUMENTS で既に matter ID が指定されていない場合、対話で以下を順に確認する:

1. **matter ID** — `^[a-z0-9][-a-z0-9_]{0,63}$` を満たす英数字 ID。
   - **既定の推奨値: 自動生成の不透明 ID**（例: `20260417-a7b3c2`）
   - `/matter-list` をファイルシステム上で `ls` されたときに依頼者名が露出しないよう、人間可読 ID よりも不透明 ID を推奨する
   - 人間可読 ID を使いたい場合は明示的に入力する（例: `smith-v-jones`, `2024-001`）
2. **title** — 人間可読な事案名（日本語可）。例: `甲野対乙山損害賠償請求事件`
   - **title は `metadata.yaml` に 0o600 で保存されるため、ディレクトリ名 enumeration からは見えない**
3. **client** — クライアント名（任意）
4. **case_number** — 事件番号（任意）。例: `令和6年（ワ）第1234号`
5. **opened** — 開始日（任意、既定は今日）

matter ID の命名規則は Python 側で厳密にバリデートされる。日本語・スペース・スラッシュは不可。日本語は `title` フィールドに入れる。

**UX ガイダンス:** ユーザーが ID を省略した場合は自動生成 ID を使って事案を作成し、`title` に人間可読名を入れる運用をデフォルトとする。これにより BigLaw / 法務部監査の観点でもファイルシステム経由の依頼者名漏洩を回避できる（参考: `~/.claude-bengo/matters/` のディレクトリ名は他 OS ユーザーからも見え得る）。

### Step 2: 事案作成

```bash
python3 skills/_lib/matter.py create {matter-id} \
  --title "..." \
  --client "..." \
  --case-number "..." \
  --opened "YYYY-MM-DD"
```

成功時は JSON で `{matter_id, path, created: true}` が返る。既存 ID の場合はエラー終了。

### Step 3: matter-ref のドロップ（任意）

作成直後にユーザーへ確認する:

```
この作業ディレクトリに matter pointer を置くか？
これを置くと、このディレクトリで作業するたび自動的に '{matter_id}' が選択される。
（ファイル: {cwd}/.claude-bengo-matter-ref）

  yes / no
```

承諾されたら:

```bash
python3 skills/_lib/matter.py drop-ref {matter_id}
```

### Step 4: current-matter への設定（任意）

既定事案として設定するかユーザーに確認する:

```
この matter を既定事案として設定するか？
（/matter-switch を明示実行しなくても常にこの matter が使われる）

  yes / no
```

承諾されたら:

```bash
python3 skills/_lib/matter.py switch {matter_id}
```

### Step 5: 完了サマリー

```
matter '{matter_id}' を作成した。
  title:       {title}
  client:      {client}
  case_number: {case_number}
  path:        {path}

次の操作:
  /matter-list         — 登録済み matter を一覧
  /template-create     — この matter にテンプレートを登録
  /matter-info {id}    — この matter の詳細
```

## `--import-from-cwd` モード

$ARGUMENTS に `--import-from-cwd` が含まれている場合、v1.x の `{cwd}/templates/` を新規 matter に取り込む:

```bash
python3 skills/_lib/matter.py import-from-cwd [--matter-id {id}] [--title "..."]
```

元の templates/ は残す（破壊的操作を避けるため）。取り込まれたファイルの一覧を表示する。
