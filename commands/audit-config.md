---
description: 監査ログ設定を表示・変更する（記録先・HMAC・クラウド同期・ファイル名記録）
allowed-tools: Read, Write, Bash(python3 skills/_lib/workspace.py:*)
---

現在の workspace の監査ログ設定を表示・変更する。

## $ARGUMENTS の扱い

- **引数なし**: 現在の設定を表示し、変更メニューを出す
- **`show`**: 設定を表示して終了（対話なし）
- **`enable` / `disable`**: 監査ログの on/off を切り替える
- **`set <key> <value>`**: 特定キーを直接設定する
- **`--global`**: 事務所共通設定（`~/.claude-bengo/global.json`）を対象にする

## 動作

### 設定の読み込み

```bash
python3 skills/_lib/workspace.py config show
```

workspace がまだ初期化されていない場合は CWD を workspace として silently
初期化してから表示する。

### 表示内容

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  監査ログ設定 — ~/cases/smith-v-jones
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  記録:            有効
  記録先:          ./.claude-bengo/audit.jsonl (デフォルト)
  ファイル名記録:  無効（SHA-256 ハッシュのみ）
  フルパス記録:    無効
  HMAC 署名:       無効（鍵未設定）
  クラウド同期:    無効

  累計記録件数:    127
  ハッシュチェーン: 整合（最終検証: 2026-04-19 14:30）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  何を変更する?
    1. 記録先を変更（他フォルダ・事務所共有ボリューム・S3 直書き等）
    2. ファイル名記録を有効化（平文ファイル名を記録）
    3. HMAC 署名を有効化（改竄不可能化、鍵は事務所金庫保管）
    4. クラウド同期を有効化（claude-bengo-cloud へ送信）
    5. 完全に無効化（非推奨）
    0. 表示のみ、何もしない
```

### 変更フロー

**1. 記録先変更:**
- 新しいパスを質問（既定・workspace 外の絶対パス・tmpfs 等）
- 外部パスの場合は `CLAUDE_BENGO_AUDIT_ALLOW_EXTERNAL_PATH` 設定が必要な旨を説明
- `workspace.py config set audit_path <新パス>` で保存

**2. ファイル名記録:**
- 依頼者識別リスクを 2 行で説明
- 明示的に yes → `workspace.py config set log_filenames true`
- フルパスも欲しい場合は追加で `log_full_path true` を提示

**3. HMAC 署名:**
- 鍵生成方法を提示: `openssl rand -hex 32` で 64 文字 hex を作り、事務所金庫で
  保管するよう案内
- 環境変数 `CLAUDE_BENGO_AUDIT_HMAC_KEY` に設定する手順を表示
- **鍵は rotate しない**（過去のログが検証不能になる）と強く注記

**4. クラウド同期:**
- `--global` スコープで設定することを推奨（事務所全体の cloud URL なので）
- `workspace.py config set cloud_url <URL> --global`
- `workspace.py config set cloud_token <token> --global` も設定
- 手動 ingest コマンドの例を表示

**5. 完全無効化:**
- 警告: 弁護士会対応の監査証跡がなくなる旨を明示
- 2 段階確認
- `workspace.py config set audit_enabled false`

### グローバル vs case-level の使い分け

- case-level（既定）: この案件フォルダだけに適用
- global（`--global` フラグ付き）: 事務所の既定値。個別案件で上書き可能

表示時は両方をマージした実効値を見せる。

## 例

```
/audit-config                              # 現状表示 + 変更メニュー
/audit-config show                         # 表示のみ
/audit-config disable                      # 無効化（確認あり）
/audit-config enable                       # 再有効化
/audit-config set log_filenames true       # 単発変更
/audit-config set cloud_url https://... --global   # 事務所全体設定
```
