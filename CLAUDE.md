# claude-bengo — Claude Code Plugin for Japanese Law Firms

## 初回利用時の案内

ユーザーがこのプラグインを初めて使用する場合（会話の最初のメッセージで法律関連の作業を依頼された場合、または「何ができる？」「使い方は？」と聞かれた場合）、以下の案内を日本語で表示する:

```
claude-bengo（クロード弁護）— 法律事務所向け Claude Code プラグイン v2.9.0

覚えるコマンドは 3 つだけ:
  /help        — タスクから機能を探す（今日何をしたい？）
  /quickstart  — 30 分ツアー（相続・離婚・交通事故の 3 シナリオ）
  /verify      — 環境動作確認

あるいは自然言語で「離婚調停の準備をしたい」「戸籍から相続関係図を作って」
「民法709条を見せて」のように話しかけるだけでも動く。

■ 事案（matter）管理:
  /matter-create   — 新規事案を登録（v1.x から移行する場合は --import-from-cwd）
  /matter-list     — 登録済み事案の一覧 + アクティブ事案
  /matter-switch   — アクティブ事案を切替
  /matter-info     — 事案の詳細表示

■ 機密文書を扱うコマンド（アクティブ事案が必要）:
  /typo-check      — 法律文書（DOCX）の誤字脱字・表記揺れを校正する
  /family-tree     — 戸籍謄本PDFから相続関係説明図を生成する
  /template-install — 同梱書式（債権者一覧表・遺産目録・示談書等）をインストール
  /template-create — 独自のXLSX書式をテンプレートとして登録する
  /template-fill   — 登録済みテンプレートにPDFからデータを自動入力する
  /lawsuit-analysis — 訴訟文書を分析しレポートを生成する

■ 機密データ対応のコマンド（アクティブ事案が必要）:
  /traffic-damage-calc — 交通事故損害賠償を赤い本基準で決定論的に計算する
  /child-support-calc  — 養育費・婚姻費用を令和元年改定算定方式で計算する
  /debt-recalc         — 利息制限法で引き直し計算、残元本・過払金を算出する
  /overtime-calc       — 労基法37条の未払残業代を月別に計算する
  /iryubun-calc        — 遺留分侵害額を民法1042条以下に基づき計算する
  /property-division-calc — 離婚時の財産分与を民法768条に基づき計算する

■ 事案設定不要なコマンド:
  /law-search      — e-Gov法令APIから条文を検索・参照する（2,078法令対応）
  /inheritance-calc — 法定相続分を決定論的に計算する

■ 初めて使う場合:
  1. /matter-create で最初の事案を作成
     （v1.x ユーザーは /matter-create --import-from-cwd で既存テンプレートを取込）
  2. /typo-check 準備書面.docx 等で校正を試す
     または /law-search 民法709条 で条文を検索

⚠ 本プラグインで処理される文書は Anthropic の Claude API を通じてクラウドで処理されます。
  クライアントの機密文書を処理する前に、所属事務所のAI利用ポリシーを確認してください。
  監査ログは事案ごとに ~/.claude-bengo/matters/{id}/audit.jsonl に SHA-256 ハッシュチェーン付きで記録されます。
```

## データプライバシー・守秘義務

**重要:** 本プラグインで処理される文書は Anthropic の Claude API を通じて送信される。

- クライアントの機密情報を含む文書を処理する前に、所属法律事務所の AI 利用ポリシーを確認すること。
- 弁護士法第23条（秘密保持義務）および個人情報保護法の遵守はユーザーの責任である。
- 本プラグインは弁護士の業務を補助するツールであり、法的助言を提供するものではない（弁護士法第72条）。

ユーザーが初めて機密文書を処理する際は、上記の注意事項を表示する。

## 自然言語からの機能マッチング

ユーザーが自然言語で業務を依頼した場合、以下のパターンに基づいて該当コマンドを提案する。
**スラッシュコマンドを強制せず**、ユーザーが「◯◯したい」と言ったら即座に該当スキルを
呼ぶか、複数候補がある場合は 1 つに絞る確認質問を返す。

| ユーザー発話の典型 | 提案する機能 |
|---|---|
| 「離婚したい」「離婚の準備」「慰謝料」「親権」 | `/property-division-calc` + `/child-support-calc` + 離婚協議書テンプレート |
| 「相続の準備」「遺産分割」「法定相続分」 | `/family-tree` + `/inheritance-calc` + 遺産分割協議書テンプレート |
| 「戸籍を読んで」「家系図」「相続関係説明図」 | `/family-tree` |
| 「遺留分」「遺言に書かれてないから請求したい」 | `/iryubun-calc` |
| 「過払金」「借金の整理」「債務整理」「取引履歴から計算」 | `/debt-recalc` |
| 「残業代」「未払賃金」「労働審判」 | `/overtime-calc` + 労働審判申立書テンプレート |
| 「交通事故」「人身事故」「赤い本」「損害賠償」 | `/traffic-damage-calc` + 示談書テンプレート |
| 「校正して」「誤字脱字」「準備書面のチェック」 | `/typo-check` |
| 「訴状の分析」「答弁書と訴状を整理」「事件のタイムライン」 | `/lawsuit-analysis` |
| 「民法◯◯条」「会社法」「労基法」「条文を見たい」 | `/law-search` |
| 「書式を登録」「XLSX のテンプレート化」 | `/template-create` |
| 「財産目録に入力」「通帳データをテンプレートに」 | `/template-fill` |
| 「書式を追加したい」「示談書のひな形が欲しい」 | `/template-install` |
| 「何ができる？」「使い方は？」「はじめ方」 | `/help` または `/quickstart` |
| 「事案を作りたい」「新しいクライアント」 | `/matter-create` |
| 「事案を切替」「別の案件に」 | `/matter-switch` または `/matter-list` |

**マッチしない場合** は `/help` のタスクメニューを表示してユーザーに選択させる。複数の機能が
関与する場合（例: 「相続の準備」は family-tree と inheritance-calc 両方）、ユーザーに
「まず戸籍を読む？それとも相続分計算から？」と確認する。

## スキル開発時の注意（contributors 向け）

各 SKILL.md のフロントマター `description` フィールドは、**Claude がユーザー発話からスキルを自動選択する際のトリガー**としても機能する。このため以下に注意する:

- **曖昧な動詞を追加する前に、他のスキルとの競合を検討する。** 例: 「反映して」は template-fill の追記モードと混同される恐れがある（上書きと解釈するユーザーもいるため除外済み）。
- **破壊的操作を示す動詞は description に含めない。** 編集・上書き・削除の意図は `$ARGUMENTS` の明示フラグで受ける。
- **description を変更した際は、他のスキルの description と重複・競合がないか確認する。** `grep -h "^description:" skills/*/SKILL.md` で一覧できる。
- トリガーフレーズは日本語と英語の両方を並記する（`"校正", "proofread"` など）が、曖昧な English verbs（`"handle"`, `"process"`）は避ける。

## MCP利用ルール

- **Excel操作**: `mcp__xlsx-editor__*` を使用する。セル読取は `read_sheet`、書込は `write_cell` / `write_cells` / `write_rows`、構造確認は `get_workbook_info`。複数セルの一括書込には `write_cells` を使用してパフォーマンスを向上させる。
- **Word操作**: `mcp__docx-editor__*` を使用する。文書読取は `read_document`、編集は `edit_paragraph`（`track_changes: true` で修正履歴付き）。複数パラグラフの一括編集には `edit_paragraphs`（複数形）を使用する。コメントは `add_comment`。
- **HTMLレポート**: `mcp__html-report__*` を使用する。レポート生成は `render_report`。
- **filesystem MCP は使わない**。ファイル操作は Claude Code ネイティブの Read / Write / Edit / Glob を使用する。

## ファイル読取

- **PDF**: Claude の vision 機能で直接読み取る（Read ツールで開く）。大量ページのPDFは `pages` パラメータで10ページ以内ずつ分割して読み取る（例: `pages: "1-10"`, `pages: "11-20"`）。
- **DOCX**: `mcp__docx-editor__read_document` でパラグラフ単位のテキストを取得する。大きな文書（50ブロック超）は `start_paragraph` / `end_paragraph` パラメータで50ブロックずつ分割して読み取る。
- **XLSX**: `mcp__xlsx-editor__read_sheet` でセルデータを取得する。大きなシート（50行以上または結合セルが多い場合）は `range` パラメータで分割して読み取る（例: `range: "A1:N30"`, `range: "A31:N60"`）。全体を一括読取するとトークン制限を超える場合がある。まず `get_workbook_info` でシートのサイズを確認し、必要に応じて分割する。

## 出力命名規則

- テンプレート入力結果: `{元テンプレート名}_filled.xlsx`
- 校正結果: `{元ファイル名}_reviewed.docx`
- 家族関係図: `family_tree_{YYYY-MM-DD}.html`（印刷用）+ `family_tree_{YYYY-MM-DD}.agent`（Claude Desktop インライン表示用）
- 訴訟分析レポート: `lawsuit_report_{YYYY-MM-DD}.html`

出力先はユーザーに確認する。指定がなければ入力ファイルと同じディレクトリに出力する。
同名ファイルが既に存在する場合は上書きするかユーザーに確認する。

## 日本語法律文書の基本原則

- 明確性と正確性を最優先とする。
- 一貫性のある表現を使用する。
- 数字は原則として全角算用数字を用いる。**ただし XLSX セルの数値データは半角で書き込む（Excel の数値計算に必要なため）。全角数字ルールは日本語テキスト出力にのみ適用する。**
- 日付の元号（明治・大正・昭和・平成・令和）と西暦の両方に対応する。
- 日本語の文体は**だ・である調**で統一する。`です`・`ます` は使わない。

## エラー方針

エラーメッセージは非技術者（弁護士）にわかりやすい日本語で表示する。以下のテンプレートに従う:

- 読めないPDF: 「このPDFは画像品質が低く、内容を正確に読み取れない可能性がある。可能であれば、高解像度でスキャンし直すか、OCR処理済みのPDFを使用してほしい。」
- パスワード保護DOCX: 「このファイルはパスワードで保護されている。パスワードを解除してから再度お試しいただきたい。」
- 非対応フォーマット: 「このファイル形式には対応していない。対応形式: PDF, DOCX, XLSX, PNG, JPG」
- ファイルを暗黙にスキップしない。処理できないファイルは必ずユーザーに報告する。

## テンプレート（v2.0.0 〜）

テンプレートは**アクティブな事案（matter）**のディレクトリ `~/.claude-bengo/matters/{matter-id}/templates/` に `{id}.yaml` + `{id}.xlsx` のペアで保存される（v1.x の `{cwd}/templates/` ではない）。

- `/template-create` で新規登録（アクティブ事案のテンプレートディレクトリに保存される）
- `/template-list` で一覧表示（アクティブ事案のテンプレートのみ列挙）
- `/template-fill` で選択・入力（出力は CWD に配置される）

テンプレートは事案に紐づく。別の事案で同じテンプレートを使いたい場合は:
- 同じテンプレートを新しい事案で再登録する、または
- `~/.claude-bengo/matters/{A}/templates/` から `~/.claude-bengo/matters/{B}/templates/` に手動でコピーする

v1.x で `{cwd}/templates/` を使用していた場合は `/matter-create --import-from-cwd` で新規事案に取り込む。

フォーマット仕様はプラグインの `templates/_schema.yaml` を参照する。
