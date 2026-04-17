# claude-bengo（クロード弁護）

法律事務所のための Claude Code プラグイン。

裁判所書類の自動入力、戸籍謄本からの相続関係説明図の作成、法律文書の校正、訴訟文書の分析を、対話形式で実行できる。

---

## できること

### 📝 裁判所書類テンプレートの自動入力

裁判所書式（XLSX）を登録しておくと、PDFや画像から必要な情報を読み取り、自動で書式に入力する。

```
/template-create 財産目録.xlsx                         ← 書式を登録（初回のみ）
/template-fill 通帳.pdf                                ← PDFからデータを抽出して自動入力
/template-fill 通帳1.pdf 通帳2.pdf 残高証明書.pdf      ← 複数PDFからデータ統合
/template-fill --continue 財産目録_filled.xlsx 保険証書.pdf  ← 追記入力
```

- 財産目録、証拠説明書、訴状など、あらゆるXLSX書式に対応
- 結合セル・数式・書式設定を保持したまま入力
- 複数のPDFからデータを統合して一括入力
- 追記モード: 前回の入力結果に新しいデータを追加（セクション単位で段階的に入力可能）
- 抽出できなかった項目は黄色で「要確認」表示

### 🌳 相続関係説明図の作成

戸籍謄本のPDFから人物・親族関係を読み取り、裁判所提出用の相続関係説明図を自動生成する。

```
/family-tree 戸籍謄本.pdf
```

- 裁判所標準形式（被相続人・配偶者の二重線、子・孫の枝分かれ）
- 3世代以上の家族構成に対応（子の配偶者も表示）
- 明朝体・モノクロ・印刷対応（「印刷/PDF出力」ボタンでそのまま提出可能）
- インターネット接続不要の完全自己完結HTML

### ✅ 法律文書の校正

準備書面や契約書（DOCX）の誤字脱字・表記揺れを検出し、修正履歴付きで校正する。

```
/typo-check 準備書面.docx
```

- 送り仮名の誤り（行なう→行う）
- 法律用語の誤字（暇疵→瑕疵）
- 「及び/並びに」「又は/若しくは」の使い分け
- 当事者呼称の表記揺れ（原告/申立人の混在）
- 法令引用形式（民法709条→民法第709条）
- 2020年民法改正対応（瑕疵担保→契約不適合）
- 修正はWord の修正履歴として記録 — 弁護士が1件ずつ承認/却下可能

### 🧮 法定相続分の自動計算

家族関係図から民法に基づく法定相続分を正確に計算する。LLMの推論ではなく、決定論的な計算ロジックで正確性を保証。

```
「相続分を計算して」                        ← /family-tree の結果から自動計算
「配偶者と子供3人の場合の相続分は？」       ← 口頭の家族構成からも計算可能
「長男が相続放棄した場合はどうなる？」       ← 条件変更のシミュレーション
```

- 代襲相続（子が先に死亡 → 孫が相続）に対応
- 半血兄弟姉妹の相続分（全血の1/2）を正確に計算
- 相続放棄した場合の再計算
- 遺留分（民法1042条）の計算にも対応
- 分数で正確な値を表示（浮動小数点の丸め誤差なし）

### 📖 法令条文の検索・参照

e-Gov 法令 API から日本の法令2,078件の条文を検索・取得・表示する。条番号がわからなくてもキーワードで条文を探せる。

```
/law-search 民法709条                                ← 条番号で即座に表示
/law-search 会社法 第362条                            ← 取締役会の権限
「民法で子の監護に関する条文を探して」                  ← キーワードで法令内を全文検索
「不法行為に関する条文を見せて」                        ← 頻出トピックから自動推定
「さっきの条文を準備書面に引用して」                    ← 取得した条文を他コマンドで活用
```

- **全2,078法令の条文を参照可能**（法令IDリスト同梱、Grepで即座に検索）
- **条番号不明でもキーワード検索可能** — 法令XMLを一時ダウンロードし、全条文見出しをローカル検索。1,050条の民法でも1秒以内に結果を返す
- 弁護士がよく使う略称に対応（「民訴法」→ 民事訴訟法、「労基法」→ 労働基準法）
- 枝番号の条文にも対応（第766条の2、第766条の3 等の改正追加条文）
- e-Gov 公開 API を使用（認証不要、無料、追加設定不要）
- 取得した条文は `/typo-check` や `/lawsuit-analysis` と連携可能

### 📊 訴訟文書の分析

訴状・答弁書・準備書面を読み取り、タイムライン・登場人物・主張と認否を構造化したレポートを生成する。

```
/lawsuit-analysis 訴状.pdf 答弁書.pdf
```

- 事件の時系列整理
- 登場人物と関係性の整理
- 認否の追跡（認める・否認・一部認める・不知・不明）
- 証拠番号（甲号証・乙号証）の対応付け

---

## はじめ方

### 必要なもの

- **Claude Code** — Anthropic の AI コーディングツール（[公式サイト](https://claude.ai/code)）
- **Node.js 18以上** — 内部 MCP サーバの実行に必要（[ダウンロード](https://nodejs.org/)）
- **Python 3.8以上** — 決定論的計算（相続分）・法令検索・監査ログに必要

### 対応プラットフォーム

| OS | 状態 | 備考 |
|----|------|------|
| macOS | ✅ | Python 3 は `brew install python3` で追加可能 |
| Linux (Ubuntu/Debian/RHEL) | ✅ | `apt install python3` / `dnf install python3` |
| Windows 10/11 | ⚠ | PowerShell ターミナルを使用。Node.js と Python を PATH に追加する。本プラグインは POSIX 前提の箇所があるため、動作報告を歓迎する |
| WSL2 | ✅ | 推奨環境。Windows 上で Linux と同等の挙動になる |

### インストール

ターミナルで以下を実行する:

```bash
# macOS / Linux / WSL2
git clone https://github.com/llamadrive/claude-bengo.git ~/.claude/plugins/claude-bengo

# Windows PowerShell
git clone https://github.com/llamadrive/claude-bengo.git $HOME\.claude\plugins\claude-bengo
```

必要なツール（xlsx-editor, docx-editor, html-report）は `.mcp.json` で自動設定される。バージョンはピン留めされており（例: `xlsx-mcp-server@1.1.0`）、`/bengo-update` 実行時に署名付きタグ経由で更新される。

### 企業ネットワーク下での利用

プロキシ経由での実行が必要な場合、以下の環境変数を設定する:

```bash
export HTTPS_PROXY=http://proxy.example.com:8080
export HTTP_PROXY=http://proxy.example.com:8080
export NO_PROXY=localhost,127.0.0.1,api.anthropic.com  # 必要に応じて
```

社内 CA 証明書を使用している場合:

```bash
export NODE_EXTRA_CA_CERTS=/path/to/company-ca-bundle.pem
export REQUESTS_CA_BUNDLE=/path/to/company-ca-bundle.pem  # Python 用
```

**npx ブロック環境:** 厳格な npm 署名検証ポリシーにより `npx -y` が失敗する場合、MCP サーバを事前にインストールする:

```bash
npm install -g @knorq/xlsx-mcp-server@2.0.0 @knorq/docx-mcp-server@2.0.0 @knorq/html-report-server@2.0.0
```

MCP サーバは npm に `--provenance` 付きで公開されている（`npm publish --provenance`）。GitHub OIDC 経由でビルドソース（リポジトリとコミット SHA）を検証できる。

### 既存 MCP サーバとの競合

既に同名の MCP サーバを設定済みの場合は、既存の設定が優先される場合がある。競合が発生した場合はプラグインの `.mcp.json` から該当サーバを削除すること。

### 使ってみる

Claude Code を起動し、普通に日本語で話しかけるだけで動く:

```
「この準備書面をチェックして」          ← 法律文書の校正
「戸籍謄本から相続関係説明図を作って」  ← 家族関係図の生成
「民法709条を見せて」                  ← 法令条文の検索
「この財産目録に通帳のデータを入れて」  ← 裁判所書式の自動入力
```

スラッシュコマンドでも実行可能:

```
/typo-check 準備書面.docx
/family-tree 戸籍謄本.pdf
/law-search 民法709条
/template-create 財産目録.xlsx
```

---

## データの取り扱い

### 重要

本プラグインで処理される文書は、**Anthropic の Claude API を通じてクラウドで処理される**。ローカルのみでの処理ではない。

- クライアントの機密情報を含む文書を処理する前に、**所属法律事務所の AI 利用ポリシー**を確認すること
- **個人情報保護法**に基づく適切な管理の下で使用すること
- **弁護士法第23条**（秘密保持義務）を遵守すること

### データ処理の詳細

| 項目 | 内容 |
|------|------|
| **データ処理者** | Anthropic PBC（米国デラウェア州） |
| **API エンドポイント** | `https://api.anthropic.com` |
| **処理リージョン** | 米国（Anthropic の commercial API のデフォルト） |
| **学習利用** | 商用 API では、ユーザーの入力はモデルの再学習に使われない（Anthropic Commercial Terms of Service 準拠） |
| **データ保持** | デフォルトで 30 日間のログ保持。Zero Data Retention（ZDR）契約を結ぶことで保持を無効化可能（Enterprise プラン） |
| **通信暗号化** | TLS 1.2+ |

**補足:**
- Anthropic の最新のデータ保持・プライバシー条項は https://www.anthropic.com/legal を参照。本ドキュメントの記載と乖離がある場合は公式文書を優先する。
- Claude Code 経由での API 利用は、Anthropic のプラットフォーム規約に従う。

### 個人情報保護法 §25（委託先監督義務）チェックリスト

本プラグインを業務で使用する法律事務所向けの委託先評価シートの雛形:

| 確認事項 | 確認方法 |
|----------|----------|
| ☐ 委託先の特定 | データ処理者は Anthropic PBC である。Claude Code は経由ツール |
| ☐ 安全管理措置 | Anthropic の SOC 2 Type II 報告書を入手・確認する |
| ☐ 契約上の義務 | 事務所が Anthropic の Enterprise / Commercial ToS に合意している |
| ☐ 再委託の確認 | Anthropic が利用するサブプロセッサ一覧を確認する |
| ☐ データ所在地 | 米国サーバでの処理を事務所内規で許容しているか |
| ☐ 監査ログ | `~/.claude-bengo/audit.jsonl` で処理履歴を記録している（本プラグインに内蔵） |
| ☐ 保存期間 | ZDR 契約の要否を検討済み |
| ☐ ユーザー同意 | 依頼者から書面による AI 利用の同意を得ている（推奨） |

### Zero Data Retention（ZDR）の有効化

機微情報を扱う事務所は、Anthropic に ZDR 契約を申請することで API リクエストのログ保持を無効化できる。手続きは Anthropic のサポート窓口（`support@anthropic.com`）経由。ZDR が有効な場合、本プラグインの挙動は変わらないが、Anthropic 側のログが保持されなくなる。

### 監査ログ

本プラグインは処理対象のファイルについて、以下の情報をローカルの追記専用 JSONL に記録する:

- タイムスタンプ・セッション ID・スキル名・イベント種別
- ファイル名ハッシュ（`filename_sha256`、常時記録）・バイト数・ファイル内容の SHA-256
- チェーンハッシュ（`prev_hash`、直前行の SHA-256）
- 任意の短いメモ

**記録しない情報:** ファイルの中身・Claude API の入出力本文。

**プライバシー（ファイル名保護）:**
- ファイル名は既定で**平文記録しない**。`filename` フィールドは空文字のまま。
- ファイル識別は `filename_sha256`（basename の SHA-256）で行う。同じファイルが複数回処理されたことは検出できるが、依頼者氏名等の識別情報は残らない。
- フォレンジック目的で平文を残したい場合は `--log-filename` オプトインで明示指定する（例: `python3 audit.py record --file "山田_戸籍.pdf" --log-filename`）。`--full-path` は `--log-filename` との併用時のみ有効。

**改ざん耐性（ハッシュチェーン）:**
- 各レコードに直前行の SHA-256 が `prev_hash` として埋め込まれる。行の書換・削除・並替はチェーンを破綻させ、`verify` で検出可能。
- 既存の旧形式（`prev_hash` なし）ログもそのまま共存可能。`verify` は旧形式部分を `LEGACY` として表示し、新形式部分のみチェーンを検証する。

```bash
python3 ~/.claude/plugins/claude-bengo/skills/_lib/audit.py verify
```

**ログローテーション:**
- ログが 50 MB を超えると自動で `audit.jsonl.{YYYYMMDDTHHMMSS}` にリネームし、新ファイル先頭に `rotation` イベントを挿入する。`rotation.prev_hash` は旧ログ末尾行のハッシュ値を保持するため、チェーンはローテーションを跨いでも継続する。

**既知の限界（WORM 要件がある場合）:**
- ハッシュチェーンはログ内の改ざんを検出できるが、**ログファイル全体の削除・作り直しは検出できない**。外部チェックポイント（例: 日次で別ホストに送付するハッシュ）なしでは完全な改ざん耐性はない。
- 厳密な WORM 要件がある事務所は、S3 Object Lock 等の顧客管理の追記専用ストレージへ定期的にエクスポートすること。

**ログの場所:**
- デフォルト: `~/.claude-bengo/audit.jsonl`
- 上書き: `export CLAUDE_BENGO_AUDIT_PATH=/path/to/audit.jsonl`
- 無効化: `export CLAUDE_BENGO_AUDIT_PATH=/dev/null`（POSIX）または `=NUL`（Windows）

**エクスポート（コンプライアンス報告用）:**

```bash
python3 ~/.claude/plugins/claude-bengo/skills/_lib/audit.py export --format csv --since 2026-04-01 > audit-2026-04.csv
```

監査対象のスキル: `typo-check`, `lawsuit-analysis`, `family-tree`, `template-fill`（機密文書を処理するスキル）。`law-search`, `inheritance-calc`, `template-create`, `verify` は機密データを扱わないため記録対象外。

### 免責事項

- 本プラグインは弁護士の業務を**補助するツール**であり、法的助言を提供するものではない（弁護士法第72条）
- AI による校正・分析結果は参考情報であり、最終的な判断は必ず弁護士自身が行うこと
- 出力された文書・レポートは**提出前に必ず内容を確認**すること
- 本プラグインの開発者は、Anthropic のデータ処理条項の内容を保証するものではない。最新の条項は Anthropic 公式ページで確認すること

---

## コマンド一覧

| コマンド | 機能 |
|---------|------|
| `/template-create` | XLSX書式をテンプレートとして登録 |
| `/template-list` | 登録済みテンプレートの一覧 |
| `/template-fill` | ソース文書からテンプレートに自動入力 |
| `/family-tree` | 戸籍謄本から相続関係説明図を生成 |
| `/typo-check` | 法律文書の校正（修正履歴付き） |
| `/lawsuit-analysis` | 訴訟文書の分析レポート生成 |
| `/inheritance-calc` | 法定相続分の自動計算 |
| `/law-search` | 法令条文の検索・参照（e-Gov API） |
| `/verify` | 動作確認 |

---

## 更新方法

```
/bengo-update
```

これだけで最新版に更新される。ビルドや再インストールは不要。
`/verify` を実行すると、新しいバージョンがあるか自動で確認する。

---

## トラブルシューティング

### 「MCP サーバが見つからない」と表示される

`/verify` を実行して接続状況を確認する。Node.js がインストールされているか確認すること。

### PDF が読み取れない

スキャン品質が低いPDFは精度が低下する。可能であれば高解像度（300dpi以上）でスキャンし直すか、OCR処理済みのPDFを使用する。

### 相続関係説明図が表示されない

生成されたHTMLファイルをブラウザで直接開く（ダブルクリック）。インターネット接続は不要。表示されない場合はブラウザのJavaScriptが有効か確認する。

### テンプレートの入力位置がずれる

XLSX書式のレイアウトが変更された場合、テンプレート定義と一致しなくなる。`/template-create` で書式を再登録する。

---

## 開発者向け情報

<details>
<summary>ディレクトリ構造・技術仕様（クリックで展開）</summary>

### ディレクトリ構造

```
claude-bengo/
├── .claude-plugin/plugin.json    # プラグインマニフェスト
├── .mcp.json                     # MCP サーバ自動設定
├── CLAUDE.md                     # グローバル設定
├── commands/                     # スラッシュコマンド定義（7件）
├── skills/                       # スキル実装（6件）
│   ├── template-create/          # テンプレート登録ワークフロー
│   ├── template-fill/            # テンプレート入力ワークフロー
│   ├── family-tree/              # 相続関係説明図生成
│   │   └── assets/               # SVG HTMLテンプレート
│   ├── typo-check/               # 法律文書校正
│   │   └── references/           # 362+ 法律文書作成ルール
│   ├── lawsuit-analysis/         # 訴訟分析
│   │   └── references/           # 抽出スキーマ・レポート構造
│   └── verify/                   # 動作確認
├── templates/                    # ユーザー登録テンプレート
│   └── _schema.yaml              # YAML フォーマット定義
└── fixtures/                     # テスト用サンプルデータ
```

### MCP サーバ依存

| サーバ | npm パッケージ | 自動設定 |
|--------|-------------|---------|
| xlsx-editor | `xlsx-mcp-server` | ✅ `.mcp.json` で自動 |
| docx-editor | `docx-mcp-server` | ✅ `.mcp.json` で自動 |
| html-report | `html-report-server` | ✅ `.mcp.json` で自動 |

### テンプレートYAML仕様

`templates/_schema.yaml` を参照。テーブルフィールドは `headerRow`（ヘッダ行）と `dataStartRow`（データ開始行）を明確に区別する。

</details>
