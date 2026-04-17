# Changelog

本プロジェクトの変更履歴を [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) 形式で記録する。バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [1.1.1] - 2026-04-17

### Security

- **F-020 監査ログの改ざん耐性**: `skills/_lib/audit.py` に SHA-256 ハッシュチェーン（`prev_hash`）を追加。各レコードに直前行のハッシュを埋め込み、書換・削除・並替を `verify` サブコマンドで検出可能に。ローテーション（50 MB 超）を跨いでもチェーンは継続する。fsync + fcntl.flock（POSIX）/ msvcrt.locking（Windows）で並行書込も安全。セルフテスト 10/10 pass（10 プロセス × 10 書込の並行テスト含む）。
- **F-021 law-search キャッシュポイズニング対策**: キャッシュ位置を共有 `/tmp` から `~/.claude-bengo/cache/law-search/` に移動（`0o700` perms）。書込は atomic（`tmp + os.replace`）、読込前に SHA-256 サイドカー検証、改ざん検知時は自動削除。セルフテスト 21/21 pass。
- **F-022 calc.py エッジケース**: `parent_id` サイクル検出（自己参照含む）、`adoption` フィールドのスコープチェック（`kind='child'` 以外は拒否）、二重相続資格（`kind='child' + parent_id != None`）の検出を追加。テスト 15 のロックダウン（spouse=3/8, sibling=0）と新規テスト 16-19 追加。19/19 tests pass。
- **F-023 Windows クロスプラットフォーム対応**: `Bash(cp:*)` 許可を `skills/_lib/copy_file.py`（shutil ベース）に置換。`commands/template-fill.md`, `commands/template-create.md` を更新。`skills/family-tree/SKILL.md` のハードコード `/tmp/claude-bengo-familytree-...json` を CWD 相対の `.claude-bengo-familytree.json` に変更。CI に `Bash(cp:*)` リグレッション検出 lint を追加。

### Privacy

- **audit.py ファイル名保護**: ファイル名は既定で平文記録しない（`filename` は空文字）。識別は `filename_sha256`（basename の SHA-256）で行う。依頼者氏名などの識別情報が監査ログに残ることを防ぐ。フォレンジック目的で平文を残したい場合は `--log-filename` オプトインで明示指定。
- **audit.py センチネル修正**: `CLAUDE_BENGO_AUDIT_PATH=NUL` が POSIX で literal `./NUL` ファイルを作成するバグを修正（`os.devnull`・`NUL`・`nul`・`/dev/null` をセンチネルとして処理）。

### Changed

- `.claude-plugin/plugin.json`: 1.1.0 → 1.1.1
- `.mcp.json`: `xlsx-mcp-server@1.1.0` → `@knorq/xlsx-mcp-server@2.0.0`（および他の 2 件も `@knorq/*@2.0.0` へ移行。npm 側でスコープ化・`--provenance` 付き公開・GitHub OIDC 経由でビルドソース検証）
- `skills/law-search/SKILL.md`: version 1.1.0 → 1.2.0（キャッシュ関連記述更新）
- `commands/family-tree.md`, `commands/template-fill.md`, `commands/template-create.md`: `allowed-tools` 更新

### Added

- `skills/_lib/copy_file.py` — クロスプラットフォームのファイルコピーヘルパー。
- `skills/_lib/audit.py verify` — 監査ログのハッシュチェーン検証サブコマンド。
- `skills/_lib/audit.py --self-test` — 組込セルフテスト。
- `skills/law-search/search.py self-test` — キャッシュ検証セルフテスト。

### Known limitations（変更なし・明記）

- **ログファイル全体の削除は検知できない**。WORM 要件がある場合は顧客管理の追記専用ストレージ（S3 Object Lock 等）へ定期的にエクスポートすること。README 「監査ログ」セクションに既知の限界を記載。
- **OPS-003 コストプリフライト**: 依然として LLM 解釈の prose。Claude Code 側の hook 機構で強制する方法が現状存在しない。
- **OPS-005 CI の E2E**: MCP サーバを CI 内で起動する手段は未実装。ユニットテスト・セルフテスト・構文チェックの範囲。
- **OPS-007 プロンプトインジェクション対策の adversarial eval**: 赤チームフィクスチャは未整備。

## [1.1.0] - 2026-04-17

### Security（F-001〜F-004, F-006）

- **F-001 MCP サプライチェーン**: `.mcp.json` の依存を unscoped `npx -y xlsx-mcp-server` 等から、スコープ付き・バージョン固定 `@knorq/xlsx-mcp-server@2.0.0`, `@knorq/docx-mcp-server@2.0.0`, `@knorq/html-report-server@2.0.0` へ更新。npm 側で `--provenance` 付き公開・GitHub OIDC 経由でビルドソース検証可能。
- **F-003 シェルインジェクション**: `/law-search` の `python3 -c "..."` インライン実行を `skills/law-search/search.py`（argparse + 入力バリデーション）に置換。`allowed-tools` を `Bash(python3 skills/law-search/search.py:*)` に限定。
- **F-004 プロンプトインジェクション防御**: 文書読取型スキル（typo-check, lawsuit-analysis, family-tree, template-fill）に「セキュリティ: 文書内容の信頼境界」セクションを追加。相手方書面内の指示を無視する方針を明文化。加えて `@knorq/docx-mcp-server@2.0.0` 側で `track_changes: false` の使用に `allow_untracked_edit: true` の追加フラグを必須化（`UNTRACKED_EDIT_NOT_ALLOWED` でサーバ側ガード）。
- **F-006 プラグイン更新**: `/bengo-update` を GPG 署名付きタグの検証・変更内容の表示・ユーザー承認・明示的 checkout（`--force` 不使用）のフローに変更。

### Added

- **F-002 inheritance-calc 決定論的計算**: インライン Python テンプレートを `skills/inheritance-calc/calc.py`（675 行）へ書き換え。代襲・再代襲（民法887条2・3項）、兄弟姉妹の代襲制限（民法889条2項）、半血兄弟姉妹（民法900条4号但書）、相続放棄と代襲の相互作用（民法939条）、特別養子（民法817条の2）を正確に処理。`test_calc.py` で 15 シナリオ全件パス。
- **F-007 CI ハーネス**: `scripts/verify.py` + `.github/workflows/ci.yml`（ubuntu / macos / windows × Python 3.8/3.11/3.12 マトリクス）。Python 構文・unit tests・MCP 設定・プラグイン manifest・危険パターン（`Bash(python3:*)` 等）を検査。
- **F-008 データ取扱い文書**: README に Anthropic エンドポイント・ZDR・PIPA §25 委託先監督チェックリストを追記。
- **F-009 監査ログ**: `skills/_lib/audit.py` で `~/.claude-bengo/audit.jsonl` に処理対象のファイル名・サイズ・ハッシュを記録。内容は記録しない。`typo-check`, `lawsuit-analysis`, `family-tree`, `template-fill` の4スキルに hook 追加。エクスポートは `python3 skills/_lib/audit.py export --format csv`。
- **F-010 コストプリフライト**: lawsuit-analysis（>50k tokens）・template-fill（>20 pages または 5 files 超）で事前承認を要求。
- **F-011 law-search 信頼性**: クロスプラットフォームな tempdir・24h TTL キャッシュ・リトライ/バックオフ（429/500/502/503/504）・タイムアウト 30 秒を `search.py` に実装。
- **F-012 typo-check 一括承認制限**: 法的意味が重い用語（接続詞階層・条件表現・義務規定・主体呼称・効果規定・改正対応語・金額/日付/条番号）を denylist 化し、該当修正は個別承認必須に。
- **F-014 HTML インジェクション防御**: family-tree HTML テンプレートの JSON payload を Base64 化し、`TextDecoder('utf-8')` で復号。`</script>` 等の攻撃ベクタを完全に無効化。旧字体の自動変換は廃止（戸籍上の正式表記を保持）。
- **F-015 contributor ガイド**: スキル `description` フィールドの自動トリガー挙動を CLAUDE.md に明記。
- **F-016 プラットフォーム対応**: README に macOS/Linux/Windows/WSL2 の対応マトリクス、プロキシ env vars、社内 CA 設定、npx ブロック環境の対処を追加。
- `skills/family-tree/encode.py`: 家系図 JSON の Base64 エンコードヘルパー。
- `fixtures/README.md`: フィクスチャ棚卸し。合成データ作成ガイド。

### Changed

- **F-005 `/template-fill` 追記モード**: 自然言語トリガーから `反映して` を除外（上書き/追記の解釈が曖昧なため）。既存 `_filled.xlsx` 指定時または曖昧な表現使用時は明示的な確認を必須化。
- **F-013/F-017 `/verify`**: ハードコードされたスキル件数（`6 skills`, `4/4 OK`）を動的列挙に変更。
- `.claude-plugin/plugin.json`: version 1.0.0 → 1.1.0。
- `skills/verify/SKILL.md`: モード2 の対象に `inheritance-calc`, `law-search` を追加。

### Removed

- インライン `python3 -c "..."` 実行（全ての箇所で）。
- `Bash(curl:*)`, `Bash(rm:*)`, `Bash(mkdir:*)`, `Bash(rmdir:*)` の広い許可（law-search コマンドで narrow 化）。
- unscoped MCP パッケージ（`xlsx-mcp-server` 等）への依存。
- family-tree での旧字体 → 新字体の自動変換指示（戸籍上の正式表記を保持する方針へ変更）。

## [1.0.0] - 2026-04-03

### Added

- Initial release.
- 10 コマンド: `/template-create`, `/template-list`, `/template-fill`, `/family-tree`, `/typo-check`, `/lawsuit-analysis`, `/inheritance-calc`, `/law-search`, `/bengo-update`, `/verify`。
- 8 スキル + YAML テンプレートスキーマ。
- MCP サーバ自動設定（xlsx-editor, docx-editor, html-report）。
