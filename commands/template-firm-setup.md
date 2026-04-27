---
description: 事務所スコープ（firm）のテンプレート共有フォルダを設定する（OS の同期クライアントがマウントしているローカルパスを指定）
allowed-tools: Bash(python3 skills/_lib/workspace.py:*)
---

事務所全員で共有するテンプレートディレクトリのローカルパスを設定する。本プラグインは
認証や upload を行わず、設定されたローカルディレクトリを読み書きするだけ。実体の同期は
OS の同期クライアント（Google Drive for desktop / Dropbox / OneDrive / SMB マウント等）
が担当する。

$ARGUMENTS:
- パス（必須、`--unset` を除く）— OS 同期クライアントがマウントしているローカルディレクトリ
- `--unset` — 既存設定を削除する

## 典型的なセットアップ

事務所の admin が一度だけ:

1. Google Shared Drive（または社内 SMB / Dropbox 共有フォルダ）に
   `事務所/法人テンプレート/` のようなフォルダを作る
2. チーム全員にアクセス権を付与
3. 各 lawyer が自分の端末で同期クライアントを起動し、フォルダがローカルにマウント
   されることを確認（macOS なら `~/Library/CloudStorage/GoogleDrive-.../Shared drives/...`）

各 lawyer が一度だけ:

```
/template-firm-setup ~/Library/CloudStorage/GoogleDrive-xxx@firm.jp/Shared\ drives/事務所/法人テンプレート
```

## ワークフロー

### Step 1: パス検証 + 設定書込

```bash
python3 skills/_lib/workspace.py firm-setup "<absolute path>"
```

戻り値 JSON:
```json
{
  "ok": true,
  "firm_templates_path": "/path/to/folder",
  "readme_created": true,
  "message": "firm スコープを ... に設定した。"
}
```

エラーケース（exit 1）:
- パスが存在しない → 「OS の同期クライアントがマウントしているか確認してほしい」と案内
- ディレクトリではない（ファイル等）→ 「ディレクトリを指定してほしい」と案内
- `~/.claude-bengo/` 配下を指定 → 「user スコープと混線するので不可」と案内

### Step 2: 完了案内

設定成功後、以下を案内する:

```
firm スコープを設定した: {path}

以降:
  /template-list                       — case + firm + user の全テンプレートを一覧
  /template-create --scope firm        — このフォルダに新規テンプレートを登録（PII 検出時は拒否）
  /template-install <id> --scope firm  — 同梱書式を firm にインストール
  /template-promote <id> --to firm     — case → firm に昇格（admin 用フロー）
  /template-demote <id> --from firm    — firm → case にコピー（特定案件だけカスタマイズ）

注意: このフォルダには PII を含むファイルを置かないこと。事務所全員から見える。
PII スキャンは promote / save 時に自動的にかかる（検出時は拒否）。
```

### Step 3: 設定削除（`--unset`）

```bash
python3 skills/_lib/workspace.py firm-setup --unset
```

戻り値:
```json
{"unset": true, "message": "firm スコープ設定を削除した。"}
```

削除後は firm スコープが unconfigured になり、resolver は silently スキップする
（case → user に戻る）。

## 状態確認

```bash
python3 skills/_lib/workspace.py firm-status
# → {"state": "unconfigured" | "unreachable" | "reachable", "path": "..."}
```

- `unconfigured` — まだ設定されていない
- `unreachable` — 設定済みだがランタイムでパスが見つからない（Drive 未マウント、削除等）
- `reachable` — 正常

## エラーハンドリング

- `unreachable` 状態で `/template-fill` が走った場合、firm をスキップして case → user で
  解決する（silently）。case にも user にも対象テンプレートが無く、firm にだけある
  ような状況は次回 PR で詳細な remediation メッセージを出す予定。
