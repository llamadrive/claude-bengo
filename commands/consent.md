---
description: 機密文書処理の管理者承認フロー（admin 認証で gate される）
allowed-tools: Bash(python3 skills/_lib/consent.py:*)
---

本プラグインで機密文書（PDF・DOCX・XLSX）を処理するには、**事務所管理者
（admin）の承認** を経た同意が必要（v3.3.0〜）。

$ARGUMENTS（以下のキーワードで分岐。`consent.py` の CLI サブコマンドと 1:1 対応する）:
- `status` または引数なし — 同意と admin_lock の状態を表示（→ `consent.py status`）
- `show` — 同意書本文を表示（→ `consent.py show`）
- `admin-setup` — 事務所管理者パスフレーズを初期設定（一度だけ。→ `consent.py admin-setup`）
- `grant` — 同意書を表示後、admin 承認付きで同意を記録（→ `consent.py grant`）
- `revoke` — 同意を取り消す（admin 認証必須。→ `consent.py revoke`）

## ワークフロー

### 初回セットアップ（事務所管理者のみ実施）

1. 管理者（senior partner 等）が 8 文字以上の firm-wide パスフレーズを決める
   （事務所金庫・パスワードマネージャで厳重保管）
2. 管理者自身が以下を実行:

```bash
python3 skills/_lib/consent.py admin-setup --passphrase "<firm-wide-passphrase>"
```

成功すると `~/.claude-bengo/global.json` に PBKDF2-HMAC-SHA256 (200k iterations)
でストレッチした hash のみが保存される。平文パスフレーズはどこにも残らない。

### 通常運用（admin が同意をセッションごとに有効化する）

機密スキル (`/typo-check`, `/template-fill` 等) を初めて使う前に:

1. 状態確認:
   ```bash
   python3 skills/_lib/consent.py status
   ```
   `{"granted": false, "admin_lock": true}` なら未承認。

2. 同意書を確認:
   ```bash
   python3 skills/_lib/consent.py show
   ```
   admin が内容を全員に説明する。

3. 管理者が承認:
   ```bash
   python3 skills/_lib/consent.py grant \
     --answer "同意する" \
     --admin-passphrase "<firm-wide-passphrase>"
   ```
   これにより `consent_granted_at` が記録され、以降のセッションで機密スキルが
   解禁される（同意 version が bump されるまで継続）。

### 取り消し（admin のみ）

```bash
python3 skills/_lib/consent.py revoke --admin-passphrase "<firm-wide-passphrase>"
```

一般ユーザーは revoke できない（admin 認証が必須）。

## パスフレーズのローテーション

事務所内のパスフレーズを更新したい場合（人事異動・定期更新等）:

```bash
python3 skills/_lib/consent.py admin-setup \
  --passphrase "<新パスフレーズ>" \
  --force \
  --old-passphrase "<現行パスフレーズ>"
```

**`--force` 単体では拒否される**（v3.3.0-iter2〜、takeover 対策）。現行
パスフレーズの提示が必須。現行を知らない者は admin lock を上書きできない。

## 重要

- **admin-passphrase を忘れた場合**: 通常ルートでは復旧できない（これは設計）。
  事務所 IT 担当が `~/.claude-bengo/global.json` から `admin_lock` キーを
  手動削除し初回扱いで再設定する必要がある。この復旧は物理的なマシン管理権限
  がないと実行できないため、最終的な lock 管理は OS レベルに委ねられる。
- 同意内容（version）が bump されると、再度 admin 承認を経る必要がある。これは
  コンプライアンス要件の変更を lawyer に気付かせるため。
