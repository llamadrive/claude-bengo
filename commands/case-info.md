---
description: 現在の案件フォルダ（workspace）の状態を表示する
allowed-tools: Read, Bash(python3 skills/_lib/workspace.py info:*), Bash(python3 skills/_lib/audit.py verify:*)
---

現在の CWD（または指定ディレクトリ）の workspace 状態を要約する。bengo-toolkit
は案件フォルダごとに `.claude-bengo/` を持つ（ディレクトリ名は v3.7.0 でのリネーム
時にも互換性のため据え置き）。このコマンドはその中身を読み、
監査ログの件数・テンプレート数・メタデータを可視化する。

## $ARGUMENTS

- **引数なし**: 現在の workspace を対象に
- **`--verify`**: ハッシュチェーンの整合性も併せて検証する

## 動作

### Step 1: workspace 解決

```bash
python3 skills/_lib/workspace.py info
```

未初期化の場合は以下を表示:

```
このフォルダ（~/cases/new-case）は bengo-toolkit の案件フォルダとして
初期化されていない。機密スキル（/typo-check, /family-tree 等）を実行すると
自動的に `.claude-bengo/` が作成される。事前登録したい場合:

  python3 skills/_lib/workspace.py init
```

### Step 2: 情報表示

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  案件: smith-v-jones
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  フォルダ:        ~/cases/smith-v-jones
  開始日:          2026-04-10
  最終更新:        2026-04-19 14:30 (2時間前)

  監査ログ:        ~/cases/smith-v-jones/.claude-bengo/audit.jsonl
  件数:            127
  直近イベント:
    - 2026-04-19 14:30: family-tree file_write (family_tree_2026-04-19.agent)
    - 2026-04-19 14:28: family-tree file_read (戸籍.pdf)
    - 2026-04-19 10:15: typo-check file_write (訴状_reviewed.docx)
    - 2026-04-19 10:10: typo-check file_read (訴状.docx)

  テンプレート（3 件）:
    - 財産目録
    - 遺産分割協議書
    - 陳述書（原告）

  設定:            既定（/audit-config で変更可）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 3: --verify 指定時

`python3 skills/_lib/audit.py verify` を実行し、結果を末尾に追加:

```
  ハッシュチェーン検証: OK
    subtotal: ok=127, fail=0, legacy=0, total=127
```

`fail > 0` なら赤字で表示し、弁護士に手動確認を促す。

## 避けること

- 監査ログの中身（filename 等）を一切表示しない — metadata のみ
- 設定変更の質問をしない（`/audit-config` の領域）
- 他の案件フォルダを勝手にスキャンしない
