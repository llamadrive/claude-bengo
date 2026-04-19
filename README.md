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

Git はインストール不要（プラグイン管理は Claude Code が内蔵する git 機構を使う）。

### 対応プラットフォーム

| OS | 状態 | 備考 |
|----|------|------|
| macOS | ✅ | Python 3 は `brew install python3` で追加可能 |
| Linux (Ubuntu/Debian/RHEL) | ✅ | `apt install python3` / `dnf install python3` |
| Windows 10/11 | ⚠ | PowerShell ターミナルを使用。Node.js と Python を PATH に追加する。本プラグインは POSIX 前提の箇所があるため、動作報告を歓迎する |
| WSL2 | ✅ | 推奨環境。Windows 上で Linux と同等の挙動になる |

### インストール（推奨: 2 コマンドで完了）

Claude Code を起動し、以下を **Claude Code 内で** 実行する（ターミナルでの `git clone` は不要）:

```
/plugin marketplace add llamadrive/claude-bengo
/plugin install claude-bengo@claude-bengo
```

Claude Code が GitHub からリポジトリを取得し、自動的にプラグインとして登録する。インストール完了後、Claude Code を再起動すれば 3 つの MCP サーバが起動する（初回 30 秒程度）。

更新は Claude Code 内で `/plugin install claude-bengo@claude-bengo` を実行する（marketplace.json の最新バージョンを取得）。

#### インストール確認

```
/verify
```

全項目が OK と表示されれば導入成功。

#### 旧インストール方法（git clone、開発者向け）

開発者がプラグインを改変しながら使う場合は、ローカルクローンを marketplace として登録する:

```bash
# macOS / Linux / WSL2
git clone https://github.com/llamadrive/claude-bengo.git ~/claude-bengo-dev
```

Claude Code 内で:

```
/plugin marketplace add ~/claude-bengo-dev
/plugin install claude-bengo@claude-bengo
```

必要な 3 つの MCP サーバは `.mcp.json` で自動設定される（Claude Code が起動時に `npx -y` で取得）:

- `@knorq/xlsx-mcp-server@2.0.0` — XLSX 読書
- `@knorq/docx-mcp-server@2.0.0` — DOCX 読書・track changes
- `@agent-format/mcp@0.1.9` — 家系図・訴訟分析を Claude Desktop 内にインライン描画

バージョンはピン留めされており、更新は Claude Code 標準の `/plugin install claude-bengo@claude-bengo` 経由で行う（marketplace.json の `version` を見て最新版をキャッシュへ展開）。初回起動時は npx キャッシュがないため各 MCP の初回取得に 30 秒程度かかる（以降はキャッシュから即起動）。

### 案件フォルダ（v3.0.0〜）

v3.0.0 で matter ID 概念を廃止。**フォルダ = 案件**。弁護士は既に案件ごとに
フォルダを持っているので、その構造をそのまま使う。

```
~/cases/
├── smith-v-jones/
│   ├── .claude-bengo/        ← 最初に機密スキルを使ったとき自動作成
│   │   ├── audit.jsonl       ← SHA-256 ハッシュチェーン
│   │   ├── metadata.json
│   │   └── templates/
│   ├── 訴状.pdf
│   └── 証拠/
└── tanaka-divorce/
    ├── .claude-bengo/
    ├── 戸籍.pdf
    └── ...
```

**使い方:** `cd ~/cases/smith-v-jones` してから Claude Code を起動。機密スキル
を最初に実行したときに `.claude-bengo/` が自動作成され、以降はそこに監査ログ・
テンプレートが蓄積される。`/matter-create` のような事前登録は不要。

### 案件の切替

案件を変えるときは `cd` するだけ:

```bash
cd ~/cases/tanaka-divorce && claude
```

Claude Code は CWD から親ディレクトリに向けて `.claude-bengo/` を走査（git の
`.git/` と同じ挙動）。最初に見つかったフォルダが案件 root。

案件の状態を見たい場合:
```
/case-info      — 現在の案件フォルダ（workspace）のサマリー
/audit-config   — 監査ログ設定（記録先・HMAC・クラウド同期）
```

### v2 からの移行

v2.x で `~/.claude-bengo/matters/` 配下に蓄積したデータは v3 では参照されない。
必要なら手動で新しい案件フォルダへコピーする:

```bash
mkdir -p ~/cases/smith-v-jones/.claude-bengo
cp -r ~/.claude-bengo/matters/smith-v-jones/* ~/cases/smith-v-jones/.claude-bengo/
```

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
npm install -g \
    @knorq/xlsx-mcp-server@2.0.0 \
    @knorq/docx-mcp-server@2.0.0 \
    @agent-format/mcp@0.1.9
```

MCP サーバは npm に `--provenance` 付きで公開されている（`npm publish --provenance`）。GitHub OIDC 経由でビルドソース（リポジトリとコミット SHA）を検証できる。

### 既存 MCP サーバとの競合

既に同名の MCP サーバを設定済みの場合は、既存の設定が優先される場合がある。競合が発生した場合はプラグインの `.mcp.json` から該当サーバを削除すること。

### 複数台への展開（fleet 配布）

Jamf / Intune / Ansible 等で複数の弁護士端末へ配布する場合、以下のいずれか:

**Option A — 端末別セットアップ（推奨、弁護士向け）**

各端末で Claude Code 内から以下 2 行を実行する:

```
/plugin marketplace add llamadrive/claude-bengo
/plugin install claude-bengo@claude-bengo
```

案件データはフォルダごとに分離される（`~/cases/{案件名}/.claude-bengo/`）。同一ユーザーが複数端末で同じ案件に作業する場合は、案件フォルダを暗号化ボリューム（FileVault / BitLocker）経由で同期するか、Dropbox/iCloud 等の共有ボリュームに置く。後者はクラウドに監査ログがアップロードされる点に留意（/audit-config で記録先を別ボリュームへ逃がせる）。

**Option B — 配布スクリプト雛形（Jamf 等、IT 管理者向け）**

マーケットプレイスベースの展開は Claude Code の `installed_plugins.json` を直接書き込む方式。数台なら上記 Option A を推奨。数十台以上のフリート展開では Claude Code の config 直接操作が現実的:

```bash
#!/usr/bin/env bash
set -e
# MCP サーバの事前インストール（npx ブロック環境向け）
npm install -g \
  @knorq/xlsx-mcp-server@2.0.0 \
  @knorq/docx-mcp-server@2.0.0 \
  @agent-format/mcp@0.1.9
# 運用方針: 監査ログの保持数制限（例: 30本）
echo 'export CLAUDE_BENGO_AUDIT_KEEP=30' >> "$HOME/.zshrc"
# 各端末でユーザー自身が Claude Code を起動し、初回 1 回だけ:
#   /plugin marketplace add llamadrive/claude-bengo
#   /plugin install claude-bengo@claude-bengo
```

**監査ログの中央集約（推奨）**

BigLaw / 法務部で中央集約が要件の場合、各端末で日次以上の頻度で以下を実行し、事務所管理の WORM ストレージ（S3 Object Lock / Azure Immutable Storage）へエクスポートする:

```bash
# v3.0.0: 各案件フォルダの .claude-bengo/audit.jsonl を順次 export
for d in ~/cases/*/; do
  case_name=$(basename "$d")
  if [ -f "$d/.claude-bengo/audit.jsonl" ]; then
    (cd "$d" && python3 ~/.claude/plugins/cache/claude-bengo/claude-bengo/{VERSION}/skills/_lib/audit.py export --format csv) \
      > "/backup/audit-${case_name}-$(date +%Y%m%d).csv"
  fi
done
```

本プラグインはローカル WORM を提供しない（全体削除検知不能）ため、外部ストレージへの定期エクスポートが唯一の完全な改ざん耐性手段となる。

### 初回インストール時のスモークテスト

法律事務所への導入時は `RUNBOOK.md` に従って 15〜20 分の動作確認を実施する。MCP サーバの疎通、試用フォルダでの機密スキル動作、`.claude-bengo/` 自動作成、監査ログのハッシュチェーン検証と改ざん検知までを一通り確認できる。

### パイロット弁護士向け実戦ガイド

動作確認の次は `QUICKSTART.md` を開く。相続・離婚・交通事故の 3 シナリオで全 23 コマンドに触れる 30 分程度のウォークスルーを用意している。フィードバック窓口も同ドキュメントに記載。

### 覚えるコマンドは 3 つだけ

全 23 コマンドを覚える必要はない。以下のいずれかから始めれば自然に全機能に触れる:

| コマンド | 用途 |
|---|---|
| **`/help`** | タスクから機能を探す対話型メニュー。「今日何をしたい？」に答えると該当機能へ誘導 |
| **`/quickstart`** | 3 シナリオ（相続・離婚・交通事故）の 30 分ツアー |
| **`/verify`** | 環境動作確認・診断 |

もしくは自然言語で「**離婚調停の準備をしたい**」「**この戸籍から家系図を作って**」「**民法709条**」のように話しかけるだけでも Claude が該当機能を提案する。書棚に貼れる 1 枚リファレンスは `CHEATSHEET.md`。

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
| **データ保持** | Anthropic の公式データ保持条項に従う（最新値は https://www.anthropic.com/legal を参照）。Zero Data Retention（ZDR）契約を結ぶことで保持を無効化可能（Enterprise プラン） |
| **通信暗号化** | TLS 1.2+ |

**補足:**
- Anthropic の最新のデータ保持・プライバシー条項は https://www.anthropic.com/legal を参照。本ドキュメントの記載と乖離がある場合は公式文書を優先する。
- Claude Code 経由での API 利用は、Anthropic のプラットフォーム規約に従う。

**本プラグインのエンドポイント中立性:**
- 本プラグインは markdown + Python スクリプトの集合体であり、**どの Claude エンドポイントに対しても同一に動作する**。処理リージョンは「どのプラグインを使うか」ではなく「Claude Code をどう設定するか」で決まる。
- 上記表は**既定の Anthropic API 直結構成**の内容。法律事務所が JP リージョン内での処理を要件とする場合、以下の選択肢がある:
  - **AWS Bedrock** 経由で Claude を ap-northeast-1（東京）で実行
  - **Google Vertex AI** 経由で Claude を asia-northeast1（東京）で実行
- いずれも Claude Code 側の環境変数・認証設定で切替える。設定方法は Anthropic 公式ドキュメント（https://docs.anthropic.com 参照）の Claude Code 節を確認してほしい。本プラグインは切替え先のエンドポイントを問わず同一に動作する。
- Bedrock / Vertex 経由での利用は、各クラウドプロバイダーとの契約（BAA / DPA 相当）に従う。LlamaDrive との契約ではない点に留意。

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

| コマンド | 機能 | 機密扱い |
|---------|------|---------|
| `/quickstart` | 60 秒で試す（同梱サンプル、事前準備不要） | — |
| `/help` | タスクから機能を探す対話メニュー | — |
| `/verify` | 動作確認 | — |
| `/case-info` | 現在の案件フォルダの状態を表示 | — |
| `/audit-config` | 監査ログ設定（記録先・HMAC・クラウド同期） | — |
| `/template-install` | 同梱書式（31種）をインストール | ✅ |
| `/template-create` | 独自のXLSX書式をテンプレートとして登録 | ✅ |
| `/template-list` | 現在の案件フォルダのテンプレート一覧 | ✅ |
| `/template-fill` | ソース文書からテンプレートに自動入力 | ✅ |
| `/family-tree` | 戸籍謄本から相続関係説明図を生成 | ✅ |
| `/typo-check` | 法律文書の校正（修正履歴付き） | ✅ |
| `/lawsuit-analysis` | 訴訟文書の分析レポート生成 | ✅ |
| `/inheritance-calc` | 法定相続分の自動計算（民法、代襲・再代襲・半血・放棄対応） | — |
| `/traffic-damage-calc` | 交通事故損害賠償額（赤い本基準） | ✅ |
| `/child-support-calc` | 養育費・婚姻費用（令和元年算定方式） | ✅ |
| `/debt-recalc` | 利息制限法 引き直し計算 | ✅ |
| `/overtime-calc` | 未払残業代（労基法37条、時効判定） | ✅ |
| `/iryubun-calc` | 遺留分侵害額（民法1042-1048条） | ✅ |
| `/property-division-calc` | 離婚財産分与（民法768条） | ✅ |
| `/law-search` | 法令条文の検索（e-Gov API） | — |

「機密扱い」= ✅ のコマンドを最初に実行すると、CWD（または親フォルダ）に `.claude-bengo/` を自動作成し、以降そこに監査ログ・テンプレートを蓄積する。事前に `/matter-create` のような登録を行う必要はない。

---

## 更新方法

### 推奨: auto-update を有効化する（初回 1 回だけ）

Claude Code 内で `/plugin` → **Marketplaces タブ** → claude-bengo を選択 →
**Enable auto-update**。以降は起動時に自動で最新版が取得され、更新があった
場合は「`/reload-plugins` を実行してほしい」の通知が出る。

### 手動更新（auto-update なしの場合）

Claude Code は `/plugin upgrade` のような単発コマンドを提供していないため
（2026-04 時点）、既存プラグインを一度 uninstall してから reinstall する:

```
/plugin marketplace update claude-bengo      ← catalogue を refresh
/plugin uninstall claude-bengo@claude-bengo  ← 削除
/plugin install claude-bengo@claude-bengo    ← 最新版で再取得
/reload-plugins                              ← session に反映
```

`.mcp.json` の変更は `/reload-plugins` では反映されないため、MCP サーバ
バージョンが bump された release の場合は **Claude Code を完全終了（Cmd+Q）
→ 再起動** が必要。

### "already installed globally" エラーが出た場合

Claude Code の既知バグ（[#16174](https://github.com/anthropics/claude-code/issues/16174) 他）
で、`installed_plugins.json` のエントリとディスク cache が desync すると
`/plugin install` が再取得を拒否する。RUNBOOK.md のトラブルシューティング
「プラグイン更新が "already installed globally" で失敗する」を参照。

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
├── commands/                     # スラッシュコマンド定義（23 コマンド）
├── skills/                       # スキル実装（14 スキル + 共通 _lib/）
│   ├── _lib/                     # 共通ライブラリ（audit, workspace, templates, denylist）
│   ├── template-create/          # テンプレート登録ワークフロー
│   ├── template-fill/            # テンプレート入力ワークフロー
│   ├── family-tree/              # 相続関係説明図生成
│   ├── typo-check/               # 法律文書校正（362+ ルール）
│   ├── lawsuit-analysis/         # 訴訟分析
│   ├── law-search/               # e-Gov 法令 API
│   ├── inheritance-calc/         # 法定相続分（決定論）
│   ├── traffic-damage-calc/      # 交通事故損害賠償（赤い本）
│   ├── child-support-calc/       # 養育費・婚姻費用
│   ├── debt-recalc/              # 利息制限法引き直し
│   ├── overtime-calc/            # 未払残業代
│   ├── iryubun-calc/             # 遺留分侵害額
│   ├── property-division-calc/   # 財産分与
│   └── verify/                   # 動作確認
├── templates/                    # 同梱書式 + ユーザー登録
│   ├── _bundled/                 # 同梱 31 書式 + _manifest.sha256
│   └── _schema.yaml              # YAML フォーマット定義
└── fixtures/                     # テスト用サンプルデータ
```

正確なコマンド数 / スキル数は CI で `ls commands/*.md | wc -l` / `ls skills/*/SKILL.md | wc -l` によって検証している。乖離があれば CI が失敗するため、このドキュメントは本質的に最新を保つ。

### MCP サーバ依存

| サーバ | npm パッケージ | 用途 | 自動設定 |
|--------|-------------|------|---------|
| xlsx-editor | `@knorq/xlsx-mcp-server@2.0.0` | XLSX 読書 | ✅ `.mcp.json` |
| docx-editor | `@knorq/docx-mcp-server@2.0.0` | DOCX 読書・track changes | ✅ `.mcp.json` |
| agent-format | `@agent-format/mcp@0.1.9` | 家系図・訴訟分析のインライン描画 | ✅ `.mcp.json` |

### テンプレートYAML仕様

`templates/_schema.yaml` を参照。テーブルフィールドは `headerRow`（ヘッダ行）と `dataStartRow`（データ開始行）を明確に区別する。

</details>
