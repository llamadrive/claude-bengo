# Changelog

本プロジェクトの変更履歴を [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) 形式で記録する。バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [2.1.0] - 2026-04-17

Track A の最初のリリース: 同梱テンプレート・書式ライブラリの導入。
SMB（tier 2/3 弁護士）が日々使う裁判所書式・実務書式を `/template-install`
一撃でアクティブ matter に取り込めるようにした。

### Added — 同梱テンプレートライブラリ

- **`/template-install`** コマンド: プラグイン同梱の裁判所書式・実務雛形を
  アクティブ matter にコピーする。一覧表示・インストール・上書き対応。
- **`skills/_lib/template_lib.py`** (~340 行): レジストリ読込・インストール・
  CLI。matter 未作成時は exit 2、上書き衝突は exit 3 で区別。
- **`skills/_lib/xlsx_writer.py`** (~220 行): stdlib のみの最小 XLSX 書込器。
  openpyxl 非依存。日本語セル値・結合セル・列幅・太字書式に対応。
  @knorq/xlsx-mcp-server@2.0.0 での読み戻し互換性を確認済み。
- **`scripts/build_bundled_forms.py`**: 同梱テンプレート YAML+XLSX 生成
  スクリプト。今後の書式追加はここにビルダ関数を足すだけで済む。

### Added — 同梱テンプレート 3 種（第一弾）

| ID | カテゴリ | 用途 |
|---|---|---|
| `creditor-list` | 破産・再生 | 自己破産・個人再生申立の添付「債権者一覧表」（7 列: №/債権者名/住所/種類/元金/利息/備考） |
| `estate-inventory` | 相続 | 遺産分割協議・限定承認に用いる「遺産目録」（積極財産＋消極財産の 2 テーブル） |
| `settlement-traffic` | 交通事故 | 任意保険会社・加害者との直接交渉後の「示談書」雛形（当事者・事故内容・示談金・清算条項） |

第二弾予定: 養育費算定表、離婚協議書雛形、未払残業代計算書、内容証明郵便
雛形、訴状・答弁書・陳述書雛形、破産・個人再生申立書、労働審判申立書等。
Track B（`/traffic-damage-calc` 等の決定論的計算）は別リリースで対応。

### Added — E2E カバレッジ

`scripts/e2e.py` に 6 件の新シナリオ:
- 10a.1 レジストリ列挙
- 10a.2 インストール→ YAML+XLSX コピー成立
- 10a.3 ファイルが正しく matter dir に配置される
- 10a.4 再インストールは `--replace` なしで拒否（exit 3）
- 10a.5 `--replace` で上書き成功
- 10a.6 存在しない matter へのインストールは拒否

合計 34/34 pass（旧 28 + 新 6）。

### Changed

- `.claude-plugin/plugin.json`: 2.0.1 → 2.1.0

### Docs

- `commands/template-install.md`: コマンド定義
- `templates/_bundled/_registry.yaml`: 同梱テンプレートレジストリ
- この CHANGELOG エントリに予定リストを明記

### Known limitations

- 同梱 XLSX は参考レイアウト。**実際の裁判所書式と cell 単位で一致するとは
  限らない。提出前に最新の裁判所ホームページ・法テラス様式を確認する運用が
  必須**。このため registry には「提出前確認が必要」の但し書きを今後追加予定。
- 現行 3 種は stdlib 生成のため書式の見栄えは最小限。高度な罫線・塗り潰し・
  ヘッダ／フッタは次期バージョンで（必要なら openpyxl を optional dep に）。

## [2.0.1] - 2026-04-17

v2.0.0 直後の triple-PE（Anthropic・OpenAI・Harvey）による再レビューで指摘された運用ハードニング項目を適用。Tier 2/3（solo/mid-market）向けの本番運用ブロッカーを全て解消。Tier 1（BigLaw）構造ブロッカーの一部も部分対応。

### Security / Hardening

- **`~/.claude-bengo/` と `matters/` を 0o700 に強制** (OpenAI V2-001, Harvey H1): macOS 既定の `drwxr-xr-x` では他 OS ユーザーや Spotlight / Time Machine が `ls ~/.claude-bengo/matters/` で依頼者名を示唆する matter ID を enumerate できてしまう問題を修正。`create_matter` / `set_current_matter` の都度 `_ensure_root_mode()` で冪等に 0o700 を再適用する。
- **`.claude-bengo-matter-ref` のシンボリックリンク拒否** (Anthropic V2-003, Harvey H2): `_read_matter_ref` でシンボリックリンクを明示的に拒否し stderr に WARN を出す。共有 Dropbox 等に置かれた悪意ある ref から任意ファイルへの間接読取を防ぐ（`copy_file.py` と対称のセキュリティ方針）。
- **`MATTER_ID` env が cwd-ref を override した場合に stderr WARN** (Harvey H3): シェル設定（`.zshrc` 等）で `MATTER_ID` を固定したまま事案別フォルダに `cd` したとき、意図しない事案へ書込する footgun を可視化。抑止は `CLAUDE_BENGO_SILENT_MATTER_OVERRIDE=1`。
- **`drop_matter_ref` は事案の実在を検証** (Anthropic V2-002): `set_current_matter` と対称に `matter_exists()` チェックを追加。タイポ ID の ref を作成してしまう UX 事故を防ぐ。
- **`RESERVED_IDS` に `matters`, `lock`, `tmp` を追加** (Anthropic V2-001): ディレクトリ名衝突による混乱を防止。

### Changed — BigLaw 対応の部分強化

- **`/matter-create` のデフォルトを不透明 ID に変更** (OpenAI V2-002 部分対応): 人間可読 ID（`smith-v-jones` 等）を推奨せず、自動生成 ID（`YYYYMMDD-{hex}`）を既定とする。人間可読な事案名は `title` フィールド（`metadata.yaml`、0o600）に保存されるため、ディレクトリ名 enumeration から依頼者情報が漏洩しない。
- **`/matter-create` に初回同意フロー追加** (OpenAI V2-009 部分対応): 既存 matter が 0 件の場合、Anthropic API・リージョン・ZDR・監査ログの扱いを提示し、明示的な `yes` 回答を要求する。

### Migration

- **`/matter-create --import-from-cwd` は `.yaml` / `.xlsx` ペアのみ取込** (OpenAI V2-004): v1.x の `{cwd}/templates/` から移行する際、`.DS_Store`・`~$` Excel ロック・関係ない PDF・`_schema.yaml` を skip する。`skipped_files` 一覧も出力に含まれる。

### Operations

- **`CLAUDE_BENGO_AUDIT_KEEP=N` による rotation 保持本数制限** (OpenAI V2-005 対応): v1.x 以来「無制限」だったローテート済み監査ログの保持数を任意制限できる環境変数を追加。未設定なら従来通り無制限。削除時は stderr に INFO 出力。
- **CI で `matter.py --self-test`, `audit.py --self-test`, `search.py self-test` を明示実行** (OpenAI V2-006): 従来は `scripts/verify.py` のみだったため、18/18, 17/17, 21/21 のセルフテストが実質 CI 対象外だった。`.github/workflows/ci.yml` で 3 スクリプトのセルフテストを OS × Python マトリクス内で実行する。

### Tests

- `matter.py --self-test` 18/18（v2.0.0 の 14 + 新規 4: 0o700 perms, drop_ref 存在検証, RESERVED_IDS 'matters', symlink ref 拒否）
- `audit.py --self-test` 17/17 維持
- `calc.py test_calc.py` 19/19 維持
- `search.py self-test` 21/21 維持
- `scripts/verify.py` 18 passed

### Still Tier 1 blockers（構造的、本リリースでは未対応）

- データ residency 米国依存（Path C-enterprise SaaS 必要）
- SSO / 弁護士登録番号バインディング未対応（構造的）
- 事務所間の corporate MSA / DPA 主体が不在（事業主体の問題）
- 全体削除（`rm -rf` 相当）の検知は依然不可能（外部 WORM 連携で対処）

## [2.0.0] - 2026-04-17

**BREAKING CHANGE:** 事案（matter）単位のデータ分離を導入した。テンプレートと監査ログは `~/.claude-bengo/matters/{matter-id}/` 配下で管理される。v1.x からの移行は `/matter-create --import-from-cwd` で行う。

### Added — matter（事案）管理

- **`skills/_lib/matter.py`** (743 行): 4 段階優先順位の事案解決器 + CLI。
  - 解決順: `--matter` フラグ → `MATTER_ID` 環境変数 → `{cwd}/.claude-bengo-matter-ref` → `~/.claude-bengo/current-matter`
  - CLI: `resolve`, `list`, `info`, `create`, `switch`, `drop-ref`, `import-from-cwd`, `validate`
  - 事案 ID の命名規則: `^[a-z0-9][-a-z0-9_]{0,63}$` + 予約語拒否
  - 自動生成 ID: `YYYYMMDD-{6-hex}`（例: `20260417-a7b3c2`）
  - メタデータ（title, client, case_number, opened, notes）を `metadata.yaml` に保存
  - セルフテスト 14/14 pass
- **4 つの新規コマンド**:
  - `/matter-create` — 対話で事案を登録、任意で `.claude-bengo-matter-ref` を CWD に配置、`--import-from-cwd` で v1.x のテンプレートを取込
  - `/matter-list` — 登録済み事案 + アクティブ事案の解決元を表示
  - `/matter-switch <id>` — `current-matter` を更新
  - `/matter-info [id]` — 事案詳細（パス、テンプレート数、監査ログサイズ、メタデータ）を表示
- **`skills/_lib/audit.py --matter` フラグ** (line 151-183): 事案単位の監査ログへルーティング
  - 優先順: 明示 `--matter` → `CLAUDE_BENGO_AUDIT_PATH` → `CLAUDE_BENGO_AUDIT_AUTO_MATTER=1` + `matter.resolve()` → デフォルト
  - 事案未作成時は exit 2（孤児ログを作らない）
  - 事案単位のハッシュチェーン・ロック・ローテーションは独立
  - `verify --matter <id> --all` で事案内のローテート済みログまで検証
  - セルフテスト 17/17 pass（並行書込の事案間独立性を含む）

### Changed — BREAKING

- **テンプレートの保存場所**: v1.x では `{cwd}/templates/` に保存していたが、v2.0.0 から `~/.claude-bengo/matters/{matter-id}/templates/` に移動。事案未設定では機密スキルは動作しない。
- **監査ログの保存場所**: v1.x のグローバル `~/.claude-bengo/audit.jsonl` は `matter-create` 等の事案横断イベント用。機密スキル（template-fill 等）は事案ログ `~/.claude-bengo/matters/{id}/audit.jsonl` に記録する。
- **機密スキル 5 種** は事案未設定時に明示的エラーで中止する:
  - `template-create`, `template-fill`, `typo-check`, `lawsuit-analysis`, `family-tree`
  - いずれも Step 0 に matter 解決パスを追加。解決できない場合は `/matter-create` 等を案内
- **`/template-list`**: `{cwd}/templates/` ではなくアクティブ事案の `templates/` を走査
- **非機密スキル** は事案設定不要で従来どおり動作: `law-search`, `inheritance-calc`, `verify`, `bengo-update`

### Migration — v1.x → v2.0

v1.x で `{cwd}/templates/` にテンプレートを蓄積していたユーザーは、次のいずれかで移行する:

```bash
/matter-create smith-v-jones --import-from-cwd
```

元の `{cwd}/templates/` は残る（破壊的操作を避けるため）。取り込みが完了したら手動で削除してよい。

### Security

- 事案間の trust boundary 分離: `/template-fill` が別事案のテンプレートを誤って使用することがなくなる
- `.claude-bengo-matter-ref` によるディレクトリ単位の自動検出で、`cd` ベースの作業ワークフローでも事案境界が保てる
- 命名規則 + 予約語チェックでパストラバーサル（`../etc/passwd` 等）を防止

### Files added

- `skills/_lib/matter.py` (743 行)
- `commands/matter-create.md`
- `commands/matter-list.md`
- `commands/matter-switch.md`
- `commands/matter-info.md`

### Files changed

- `skills/_lib/audit.py` (+429 / -9; matter 対応)
- `skills/template-create/SKILL.md` (+51 / -N; Step 0 追加)
- `skills/template-fill/SKILL.md` (+68 / -N; Step 0 + matter-dir glob)
- `skills/typo-check/SKILL.md` (+44 / -N; Step 0 + matter audit)
- `skills/lawsuit-analysis/SKILL.md` (+40 / -N; Step 0 + matter audit)
- `skills/family-tree/SKILL.md` (+38 / -N; Step 0 + matter audit)
- `commands/template-list.md` (+49 / -N; matter-aware)
- `commands/{template-create,template-fill,typo-check,lawsuit-analysis,family-tree}.md` (allowed-tools に `Bash(python3 skills/_lib/matter.py:*)` 追加)
- `.claude-plugin/plugin.json`: 1.1.1 → 2.0.0

### Tests

v2.0.0 合計: **84 tests, 100% pass**
- matter.py self-test: 14/14
- audit.py self-test: 17/17（v1.1.1 の 10 + matter 対応の 7）
- calc.py test_calc.py: 19/19
- search.py self-test: 21/21
- scripts/verify.py: 18 passed, 0 failed, 4 warnings（fixtures の未整備による warning のみ）

### Out of scope / known limitations

- **テナント分離は単一ユーザー内のみ** — OS ユーザーが同じなら他事案ファイルは依然 `cat` で読める。真のマルチテナント分離は Path C-enterprise（別プロダクト）で扱う。
- **BigLaw 向け構造要件は未対応**: SOC2/ISO27001, SSO/SCIM, JP リージョン固定, MSA 契約主体 — いずれも本プラグインの範囲外。BigLaw 導入は専用 SaaS 製品が必要。
- `.claude-bengo-matter-ref` はファイルシステム読取権限があれば誰でも読める（設計上パブリック情報として扱う）

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
