# fixtures/

`/verify all` が各スキルの精度テストを実行するためのテストデータ。

## 構成

```
fixtures/
├── template-fill/
│   ├── source-complaint.pdf      [INPUT] 訴状の素材データ（合成データ）
│   ├── template-complaint.xlsx   [INPUT] 訴状テンプレート
│   ├── template-complaint.yaml   [INPUT] フィールド定義
│   └── expected-output.json      [EXPECTED] 期待される入力結果
│
├── family-tree/
│   ├── koseki-simple.pdf         [INPUT] 合成戸籍謄本（2-3人）
│   ├── koseki-complex.pdf        [INPUT] 合成戸籍謄本（3世代、代襲あり）
│   ├── expected-simple.json      [EXPECTED] persons + relationships
│   └── expected-complex.json     [EXPECTED] persons + relationships
│
├── typo-check/
│   ├── brief-with-errors.docx    [INPUT] 故意に誤字脱字を入れた準備書面
│   ├── brief-clean.docx          [INPUT] 校正済み参照用（任意）
│   └── expected-corrections.json [EXPECTED] 検出されるべき修正一覧
│
└── lawsuit-analysis/
    ├── complaint.pdf              [INPUT] 合成訴状
    ├── answer.pdf                 [INPUT] 合成答弁書
    ├── expected-timeline.json     [EXPECTED] タイムライン
    └── expected-characters.json   [EXPECTED] 登場人物
```

## ステータス

`python3 scripts/verify.py` が現状を報告する。不足しているファイルは
warning として表示される。

### 現時点で不足している入力ファイル（要準備）

以下のファイルは **必ず合成データ（架空の氏名・住所）** で作成する。
実在の顧客情報・戸籍情報を `fixtures/` にコミットしてはならない。

| ファイル | 要件 |
|----------|------|
| `template-fill/source-complaint.pdf` | 合成された請求原因事実を含む訴状素材。`expected-output.json` の値に整合すること。 |
| `family-tree/koseki-simple.pdf` | 合成戸籍謄本。筆頭者1名 + 配偶者1名 + 子1-2名。 |
| `family-tree/koseki-complex.pdf` | 合成戸籍謄本。3世代、先に死亡した子1名（代襲相続テスト用）。 |
| `typo-check/brief-with-errors.docx` | 準備書面フォーマットで、以下の誤りを1つ以上含む: 暇疵→瑕疵、行なう→行う、民法709条→民法第709条、原告/申立人の混在、「ものとする」の誤用。 |
| `typo-check/brief-clean.docx` | 上記の誤りを全て修正した参照バージョン（任意、diff テスト用）。 |
| `lawsuit-analysis/complaint.pdf` | 合成訴状。当事者2-3名、時系列事実3-5件、証拠1-2件（甲号証）。 |
| `lawsuit-analysis/answer.pdf` | 合成答弁書。訴状の各主張に対する認否を明示（認める・否認・一部認める）。 |

## 合成データの作り方

### 氏名
- 原告側: 甲野太郎、甲野花子、甲野一郎、甲野良子
- 被告側: 乙山次郎、乙山三郎、乙山桜子
- 第三者: 丙川四郎、丁田五郎

これらは民法教科書・判例研究で慣用される架空名。実在の氏名と衝突しない。

### 住所
- 東京都千代田区霞が関1-1-1（架空番地）
- 東京都新宿区西新宿2-2-2（架空番地）

### 生年月日
- 昭和40年1月1日、平成5年3月3日 等。実在しそうな日付でも可（合成データであることが前提）。

### 金額・事件番号
- 金額: 300,000円、1,500,000円 等の切りの良い数値。
- 事件番号: 令和5年（ワ）第1234号（架空）。

## 注意

- 作成したファイルは `fixtures/{skill}/` 配下にコミットする。
- ライセンスは本プロジェクトの LICENSE に従う（合成データであれば問題なし）。
- 実在の戸籍情報・顧客情報を使用しないこと。**リポジトリに実データが混入した場合、GitHub のコミット履歴からも確実に除去する必要がある（git filter-repo 等）。**
