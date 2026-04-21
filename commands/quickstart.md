---
description: 60 秒で試す — 同梱サンプルで claude-bengo の出力品質を確認する
---

**目的:** 弁護士に「まず使えるか見せる」。案件フォルダの事前準備も説明文の読み込みも**強要しない**。同梱サンプル（`fixtures/`）で 1-2 分以内に AI の出力を見せ、その品質から「自分の案件でも使えそうか」を各自判断してもらう。

## 哲学

初見の弁護士は:
- 忙しい（5 分しか取れない）
- 半信半疑（AI が法律文書を扱えるのか？）
- 手順の堅さを嫌う（案件フォルダの説明が長いだけでも即離脱しやすい）
- 先にアウトプットを見てから判断したい

よって `/quickstart` は **説明を読ませず、即座にサンプルで動かす**。ドキュメント
`QUICKSTART.md` や `RUNBOOK.md` は「気に入ったら次に読む」ためのもので、本コマンドからは参照させない。

## 応答テンプレート

最初に以下の短いメニューだけを出す:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  claude-bengo を 60 秒で試す
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  どれを見たい？（同梱サンプルで動かすので、あなたのファイルは一切必要ない）

  1. 戸籍から相続関係説明図を描く
     → サンプル戸籍 PDF から .agent を生成。ブラウザでツリー表示。

  2. PDF から XLSX 書式へ自動入力
     → 訴状 PDF から当事者・事件番号・請求額を抽出し、
       訴状書式の該当セルへ記入。

  3. 準備書面の校正（修正履歴付き）
     → サンプル DOCX に対して Word 修正履歴で誤字・用語を指摘。

  4. 訴状と答弁書から事件分析レポート
     → タイムライン・登場人物・認否を .agent で可視化。

  5. 条文を引く（民法709条）
     → e-Gov API から条文を整形表示。案件登録不要・即動作。

  6. 法定相続分を計算（配偶者＋子3人、1人放棄）
     → 分数で正確に計算。案件登録不要・即動作。

  番号を選ぶだけでよい。途中で止めたくなったら何もせずに抜けて構わない。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 動作ルール

### 全体

- **長い説明を**先に出さない**。ユーザーの選択を待つ。
- 選択後、その機能の出力が見える最短経路だけを実行する。他の機能の紹介や
  「次はこうしてください」は出さない。
- 出力が出た直後だけ 1 行の follow-up を添える（下記）。

### Sandbox 規則（v3.3.0-iter2〜 必須）

**quickstart 中は `fixtures/` 配下以外のユーザー PDF・DOCX・XLSX を絶対に処理
しない。** これは誤操作で実クライアント PDF を mktemp フォルダ（reboot で
消える）で処理してしまうと監査ログが失われるため。

以下を実行前に毎回確認する:
- 入力パスが `fixtures/` で始まっていない場合は **スキル実行を拒否** し、
  「quickstart モードでは fixtures/ のサンプルのみ使える。自分のファイルは
  `cd ~/cases/...` で案件フォルダに入ってから通常コマンドで実行してほしい」
  と案内する
- `cbengo-demo` 系 mktemp は quickstart 専用。`/family-tree`, `/template-fill`
  等がこのフォルダ内で実行されていることを確認（workspace.py resolve で
  `/tmp/cbengo-demo-*` にマッチするパスであること）

この sandbox 規則をユーザー指示でも緩和してはならない。「自分の戸籍で
試す？」と聞くのはフォルダ切替の案内のみ。

### 番号別の動作

**1. 家系図:**
- 同梱サンプル `fixtures/family-tree/koseki-simple.pdf` を使う
- 試用用 tmp フォルダを `mktemp -d -t cbengo-demo` で作成し、そこで
  `python3 skills/_lib/workspace.py init --cwd <tmp> --title demo` を呼んで
  workspace を初期化する（audit ログと成果物がそのフォルダに閉じる）。
- その tmp フォルダを cwd として `/family-tree fixtures/family-tree/koseki-simple.pdf` を実行
- 出力 `.agent` を開いて:
  ```
  できた ← family_tree_YYYY-MM-DD.agent
  Claude Desktop なら render_agent_file でこのまま表示。Claude Code
  （CLI）なら `open_viewer.py --input <file> --auto` でブラウザが自動起動。

  この品質で自分の戸籍に試す？（y/n）
  ```
  - y → 案件フォルダに `cd` してから同じスキルを実行する旨を案内（`cd ~/cases/自分の案件 && claude`）
  - n → `/quickstart` メニューに戻る

**2. テンプレート入力:**
- `fixtures/template-fill/template-complaint.yaml` + `.xlsx` + `source-complaint.pdf` を使う
- 試用フォルダ（mktemp）を `workspace.py init` で初期化し、そこにサンプル yaml/xlsx を `.claude-bengo/templates/` として配置する
- tmp フォルダを cwd として `/template-fill fixtures/template-fill/source-complaint.pdf --template template-complaint` を実行
- 出力 `template-complaint_filled.xlsx` を提示し、どのセルが埋まったか 1 画面サマリー
- follow-up: 「自分の書式と PDF で試す？ → 自分の案件フォルダで `/template-create <あなたの XLSX>`」

**3. 校正:**
- `fixtures/typo-check/brief-with-errors.docx` を使う
- 試用フォルダ（mktemp）を cwd として `/typo-check fixtures/typo-check/brief-with-errors.docx` 実行
- 出力 `brief-with-errors_reviewed.docx` の修正履歴を `mcp__docx-editor__read_document` で
  1-2 段落ぶんだけサンプル表示
- follow-up: 「自分の書面で試す？ → 案件フォルダに `cd` してから再実行」

**4. 訴訟分析:**
- `fixtures/lawsuit-analysis/complaint.pdf` + `answer.pdf` を使う
- 試用フォルダ（mktemp）を cwd として `/lawsuit-analysis fixtures/lawsuit-analysis/complaint.pdf fixtures/lawsuit-analysis/answer.pdf`
- 出力 `lawsuit_report_YYYY-MM-DD.agent` を提示
- follow-up: 「自分の訴訟記録で試す？ → 案件フォルダに `cd` してから再実行」

**5. 条文検索:**
- `/law-search 民法709条` を即実行（案件登録不要）
- 出力 1 条文のみ表示
- follow-up: 「別の条文を引く？ → `/law-search <条文>`」

**6. 法定相続分:**
- `/inheritance-calc` を実行し、先に「配偶者と子3人、子1人が相続放棄」の例を内部で解き、
  Fraction 形式の表を見せる（対話なし）
- follow-up: 「自分のケースで計算する？ → `/inheritance-calc` とだけ打って対話開始」

## フォールバック

- サンプルファイルが見つからない場合: `fixtures/` が欠落している旨を 1 行で表示し、
  `/verify` を案内する
- 試用フォルダ（tmp）の作成や `workspace.py init` に失敗した場合: エラー内容を 1 行で表示し、
  ユーザー側で `mkdir ~/claude-bengo-demo && cd ~/claude-bengo-demo` を実行してから再試行するよう案内する

## 避けること

- QUICKSTART.md / RUNBOOK.md / README.md / CLAUDE.md の**読込を指示しない**
- 「前提として /verify を先に...」のような checklist を**先に見せない**
- 選ばれたシナリオ以外のコマンドを紹介しない
- 監査ログ・案件フォルダの概念を**最初に説明しない**（6 を選んだ後にも説明不要）

気になったら `/help`（タスクメニュー）または `QUICKSTART.md`（長編ツアー）を
自発的に読むはず。`/quickstart` はその入口ではない。
