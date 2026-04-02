---
name: lawsuit-analysis
description: This skill should be used when the user asks to "analyze a lawsuit", "訴訟分析", "事件分析", "書面分析", "case analysis", "判決分析", "訴訟書類の整理", or wants to extract structured information from litigation documents.
version: 1.0.0
---

# 訴訟分析（lawsuit-analysis）

訴訟関連文書を読み取り、タイムライン・登場人物・主張・認否を構造化して抽出し、HTMLレポートを生成する。

## ワークフロー

### Step 1: 文書群の取得

ユーザーに訴訟関連文書を提供してもらう。$ARGUMENTS でパスが指定されている場合はそれを使用する。

対応文書:
- 訴状（complaint）
- 答弁書（answer）
- 準備書面（brief） — 原告側・被告側
- 証拠説明書（evidence list）
- 判決書（judgment）
- 調停調書（mediation record）
- その他の裁判関連文書

各文書がどの当事者のものかを特定する（ファイル名や内容から推定し、ユーザーに確認する）。

### Step 2: 文書読取

各文書を読み取る:
- PDF → Read ツール（Claude vision）
- DOCX → `mcp__docx-editor__read_document`

### Step 3: 構造化データの抽出

以下のスキーマで情報を抽出する。詳細は `references/extraction-schema.md` を参照する。

```json
{
  "summary": "文書群全体の概要（約200字）",
  "keyPoints": ["主要事実1", "主要事実2"],
  "timeline": [
    {
      "id": "e1",
      "date": "YYYY-MM-DD",
      "title": "事象のタイトル",
      "description": "詳細説明",
      "category": "法的手続き | 契約関連 | 事実関係 | その他",
      "importance": 7
    }
  ],
  "characters": [
    {
      "id": "p1",
      "name": "正式名称",
      "role": "原告 | 被告 | 証人 | 弁護士 | 裁判官 | 関係者",
      "description": "文書中の記述",
      "importance": 8
    }
  ],
  "relationships": [
    {
      "source": "p1",
      "target": "p2",
      "type": "雇用 | 取引 | 親族 | 代理 | その他",
      "description": "関係の説明"
    }
  ],
  "arguments": [
    {
      "id": "a1",
      "title": "主張の核心",
      "description": "主張内容の詳細",
      "party": "原告 | 被告",
      "supporting_points": ["根拠1（証拠IDで参照可: ev1）"],
      "opposing_points": ["反論1"],
      "ninhi": "認める | 否認 | 一部認める | 不知 | 不明"
    }
  ],
  "evidence": [
    { "id": "ev1", "party": "原告", "number": "甲第1号証", "title": "...", "date": "...", "purpose": "..." }
  ]
}
```

**抽出時の注意:**
- 事実に基づく抽出のみ。推測や解釈は含めない。
- タイムラインは日付昇順。訴訟のきっかけとなった事件にフォーカスする。各書面の提出日は含めない。
- 認否（ninhi）は答弁書・準備書面の「認否」セクションから抽出する。
- supporting_points には証拠IDを参照できる（例: "甲第1号証(ev1)により..."）。
- importance は案件全体における相対的重要性（1-10）。
- IDは `e{連番}`, `p{連番}`, `a{連番}` 形式。

### Step 4: HTMLレポート生成

`mcp__html-report__render_report` でレポートを生成する。レポート構造の詳細は `references/report-structure-guide.md` を参照する。

推奨ブロック構成:
1. **ヘッダ**: 事件名、事件番号
2. **概要**: summary を section + paragraph で表示
3. **キーメトリクス**: stat_cards（文書数、登場人物数、タイムライン項目数）
4. **タイムライン**: timeline ブロックで時系列表示
5. **登場人物**: card_grid で人物プロフィール
6. **関係図**: 関係性をテーブルまたは diagram で表示
7. **主張と認否**: table ブロックで認否ステータスをバッジ色分け
   - 認める → 緑バッジ
   - 否認 → 赤バッジ
   - 一部認める → 黄バッジ
   - 不知 → 青バッジ
   - 不明 → グレーバッジ

### Step 5: 出力

HTMLファイルとして `lawsuit_report_{YYYY-MM-DD}.html` に出力する。
出力先はユーザーに確認する。

### Step 6: サマリー表示

抽出結果の要約をテキストで表示する:

```
## 訴訟分析結果

- 文書数: 5件
- 登場人物: 4名
- タイムライン項目: 12件
- 主張: 6件（認める: 2, 否認: 3, 不明: 1）

### 概要
[summary テキスト]
```

## エラーハンドリング

- 文書が1件のみ: 単一文書でも分析は可能。ただし認否追跡は答弁書がないと不完全になる旨を伝える。
- 文書の当事者が不明: ユーザーに確認する。
- 50ページ超の文書: セクション分割で読み取り、進捗を報告する。
- 日付が特定できないイベント: `date` を `"不明"` とし、タイムラインの末尾に配置する。
