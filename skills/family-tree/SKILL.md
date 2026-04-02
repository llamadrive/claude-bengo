---
name: family-tree
description: This skill should be used when the user asks to "analyze a koseki", "戸籍の分析", "家族関係", "相関図", "family tree", "戸籍謄本", "親族関係", "家系図", "戸籍を読んで", "相続関係図", "法定相続情報", "戸籍から相関図を作って", or wants to extract family relationships from documents.
version: 1.0.0
---

# 家族関係図（family-tree）

戸籍謄本PDFから人物と関係性を抽出し、裁判所標準形式（相続関係説明図）のHTMLを生成する。

## ワークフロー

### Step 1: 戸籍謄本PDFの取得

ユーザーに戸籍謄本PDFのパスを確認する。$ARGUMENTS で指定されている場合はそれを使用する。
複数ファイル指定可能（除籍謄本、改製原戸籍も含む）。

手書き戸籍の場合は精度が低下する旨を警告する。

注目人物（中心人物）の指定があればメモする（任意）。

### Step 2: タイムライン抽出（Step 1 of 2）

各PDFを Read ツール（Claude vision）で読み取り、以下の構造で人物情報を抽出する:

```json
{
  "characters": [
    {
      "id": "p1",
      "name": "人物の正式名称",
      "birth": { "date": "生年月日", "place": "出生地" },
      "death": { "date": "死亡年月日", "place": "死亡地" },
      "marriages": [
        { "spouseName": "配偶者名", "date": "婚姻日", "place": "届出地" }
      ],
      "lifeEvents": [
        { "date": "日付", "event": "内容", "relatedPersons": ["関連人物"] }
      ],
      "relationships": [
        { "type": "父/母/子/兄弟姉妹", "person": "相手の名前", "details": "詳細" }
      ],
      "relationshipToFocused": {
        "type": "中心人物との関係",
        "description": "説明",
        "generation": 0
      }
    }
  ],
  "focusedPerson": "中心人物の名前"
}
```

**抽出時の注意:**
- 日付は元号（明治・大正・昭和・平成・令和）または西暦で記載する。
- 旧字体は新字体に変換する（例: 邊→辺、齋→斎、澤→沢）。
- 戸籍フォーマット: 筆頭者（本籍地の代表者）、身分事項（出生・婚姻・死亡等）、従前戸籍（元の戸籍）を正確に読み取る。
- 推測情報は details に明記する。
- 関係性は双方向で記載する（AがBの父 → BはAの子）。
- `relationshipToFocused` の `generation`: 親=-1, 子=1, 同世代=0, 祖父母=-2, 孫=2。

詳細な読取ガイドは `skills/family-tree/references/koseki-extraction-guide.md` を Read ツールで読み込んで参照する。

### Step 3: 関係グラフ構築（Step 2 of 2）

タイムラインデータから可視化用の平坦なグラフデータに変換する:

```json
{
  "persons": [
    {
      "id": "p1",
      "name": "山田太郎",
      "role": "父",
      "birthday": "昭和35年1月15日",
      "address": "東京都千代田区...",
      "deathDate": null
    }
  ],
  "relationships": [
    {
      "type": "spouse",
      "person1Id": "p1",
      "person2Id": "p2",
      "details": "昭和60年婚姻"
    },
    {
      "type": "parent-child",
      "person1Id": "p1",
      "person2Id": "p3",
      "details": "長男"
    }
  ]
}
```

**変換ルール:**
- `type` は `"spouse"` または `"parent-child"` のみ。
- `parent-child` では `person1Id` が常に親。
- `role` は推論する: 父/母/長男/次男/三男/長女/次女/三女/祖父/祖母 等。
- 同一人物の重複排除（複数戸籍に跨がる場合）。
- 養子縁組は `parent-child` として `details` に「養子」と記載する。

**注意:** Step 2 のタイムラインには birthPlace, deathPlace, marriageInfo, generation 等の詳細情報が含まれるが、FlatPerson は可視化に必要な最小限のフィールドのみ保持する。詳細情報は Step 5 のサマリーテキストで出力する。

### Step 4: HTML生成

1. `assets/family-tree-template.html` を Read ツールで読み込む。
2. テンプレート内の `__GRAPH_DATA__` を Step 3 で構築したJSONデータ（`JSON.stringify(data, null, 2)`）で置換する。
3. Write ツールで `family_tree_{YYYY-MM-DD}.html` として出力する。
4. ユーザーに「ブラウザで開くとインタラクティブな家族関係図が表示されます」と案内する。

### Step 5: データサマリー

抽出結果のサマリーをテキストで表示する:

```
## 抽出結果

- 人物数: 6名
- 関係数: 8件（配偶者: 2, 親子: 6）
- 世代数: 3世代
- 注目人物: 山田太郎（指定された場合）

### 人物一覧
| ID | 名前 | 役割 | 生年月日 |
|----|------|------|----------|
| p1 | 山田太郎 | 父 | 昭和35年1月15日 |
| p2 | 山田花子 | 母 | 昭和37年3月20日 |
| ...
```

## データモデル

### FlatPerson
```
id: string        — 一意識別子（"p1", "p2", ...）
name: string      — 氏名
role?: string     — 家族内の役割（父/母/長男/次女 等）
birthday?: string — 生年月日（元号または西暦）
address?: string  — 住所
deathDate?: string — 死亡年月日（存命の場合は省略）
```

### Relationship
```
type: "spouse" | "parent-child"
person1Id: string — 配偶者の場合はどちらでもよい。親子の場合は親。
person2Id: string — 配偶者の場合はどちらでもよい。親子の場合は子。
details?: string  — 補足情報（婚姻日、養子等）
```

## エラーハンドリング

- PDF以外のファイル: 対応フォーマットを案内する。
- 手書き戸籍: 「手書き戸籍の読み取りは精度が保証できません。結果を必ず確認してください。」と警告する。処理は続行する。
- 人物情報が不完全: 抽出できた情報のみでグラフを構築する。不明フィールドは省略する。
- 複数戸籍の矛盾: ユーザーに確認する。新しい方の情報を優先する。
