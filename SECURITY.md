# セキュリティポリシー

本プラグイン (`claude-bengo`) は日本の法律事務所でクライアント機密文書を扱うことを想定しているため、一般的な OSS よりも厳しい前提でセキュリティを扱う。

## 非公開での脆弱性報告

**公開 Issue は作らないでほしい。** GitHub Security Advisory から非公開で報告してほしい:

https://github.com/llamadrive/claude-bengo/security/advisories/new

受付後の対応目安:

- 3 営業日以内に受領確認を返す。
- 14 日以内に影響評価と緩和案を共有する。
- 重大度 Critical / High は 30 日以内にパッチリリース、Medium 以下は次回メンテナンスリリース。

Critical の例: クライアント PII の外部送信・監査ログの偽造・Claude Code ホスト上での意図しないコード実行・認可バイパス。

## 想定脅威モデル

### 1. クライアント PII の漏洩

本プラグインは DOCX / XLSX / PDF（戸籍謄本・取引履歴・診断書等）を Anthropic Claude API へ送信する。これは機能上不可避であり、以下で緩和する:

- 本プラグインで処理される文書は Anthropic のデータ処理ポリシーの対象になる。弁護士法 §23（秘密保持義務）および個人情報保護法の遵守はユーザー側の事務所ポリシー判断であり、`CLAUDE.md` で初回利用時に明示している。
- **事務所グローバルテンプレートへの PII 混入防止**: `skills/_lib/pii_scan.py` が `/template-promote` 実行時にハードブロックする。case スコープ → global スコープ昇格前に PII 検出 → 拒否。
- **監査ログ**: 全ての機密スキル実行は `{workspace_root}/.claude-bengo/audit.jsonl` に SHA-256 ハッシュチェーン付きで記録される。改ざん検出用の HMAC は `~/.claude-bengo/global.json` の `audit_hmac_key_hex` に保管（端末盗難時のローカル整合性検証用。クラウド側整合性は sha256 チェーンで担保され HMAC には依存しない）。

### 2. プロンプトインジェクション（クライアント提供文書経由）

ユーザーが読み込ませる PDF / DOCX / XLSX には悪意ある第三者が作成した指示文が埋め込まれている可能性がある（例: OCR 済み PDF の目立たない位置に「監査ログを削除しろ」等の指示）。

- 本プラグインのスキルはツール実行に **明示的な `allowed-tools` 宣言** を必要とする。Claude モデルが文書に誘導されて任意コマンドを実行できないよう、各コマンドの `allowed-tools` は具体的なスクリプトパスに限定されている（`Bash(python3:*)` のような広汎な権限は CI で検出・拒否する。`.github/workflows/ci.yml` の `lint-shell` ジョブを参照）。
- 計算系スキル（`traffic-damage-calc`, `debt-recalc`, `iryubun-calc` 等）は **決定論的な Python 実装**で LLM を経由せずに数値結果を算出する。LLM が金額を誘導することはない。

### 3. MCP サプライチェーン攻撃

本プラグインは `.mcp.json` で MCP サーバーを宣言する。信頼できないパッケージを取り込むと LLM 経由でホスト上のファイルアクセスを得られる。

- `.mcp.json` 内の全パッケージは **scoped npm package** (`@knorq/...`) かつ **正確なバージョン** で指定する（CI `lint-shell` でハードブロック）。
- タグ更新型の依存（`@latest`, `^1.2.0`）は禁止する。
- GitHub Actions も全て **commit SHA ピン留め** とし、Dependabot (`.github/dependabot.yml`) で grouped PR として更新を受ける。

### 4. 認可されていないコード実行

Claude Code / Cowork のハーネスはコマンド実行時にユーザー承認を求めるが、`allowed-tools` に過度な権限が宣言されているとバイパスされる:

- 禁止パターン（CI で検出）: `Bash(python3:*)`, `Bash(python3 -c ...)`, `Bash(curl:*)`, `Bash(cp:*)`。
- 各コマンドは必要な最小権限のみを宣言する（例: `Bash(python3 skills/traffic-damage-calc/calc.py:*)`）。

### 5. 監査ログ偽造

弁護士法 §23-2 照会や事務所内監査のため、監査ログの改ざん検出が必要:

- `audit.jsonl` は行ごとに `prev_hash` を含む SHA-256 ハッシュチェーン。1 行でも書き換えると以降全ての hash が一致しなくなる。
- オプションで HMAC 付加（鍵は `~/.claude-bengo/global.json`）。端末盗難時のローカル改ざん検知を強化する。
- クラウド同期時 (`audit.py ingest` → `claude-bengo-cloud`) は **sha256 を cloud 側で再計算** しチェーン整合を強制。HMAC 鍵はクラウドに共有されないため、ローカルと cloud の改ざん検知は独立に機能する。

## スコープ外

- **モデル出力の法的正確性**: 本プラグインは弁護士の業務補助ツールであり法的助言を提供しない（弁護士法 §72）。出力の最終確認はユーザーの責任とする。
- **Anthropic Claude API 自体の脆弱性**: Anthropic 製品の脆弱性は [Anthropic の開示ポリシー](https://www.anthropic.com/legal) に従って直接報告してほしい。
- **ハーネス (Claude Code / Cowork) の脆弱性**: Claude Code 自体の問題は anthropics/claude-code へ報告してほしい。

## サポート対象バージョン

最新マイナーリリースおよびその 1 つ前をサポートする。脆弱性修正はサポート対象バージョンにのみ backport する。

| バージョン | 状態 |
|-----------|------|
| 3.3.x | サポート |
| 3.2.x | セキュリティ修正のみ |
| 3.1.x 以前 | サポート終了 |
