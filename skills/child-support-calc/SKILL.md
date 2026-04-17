---
name: child-support-calc
description: This skill should be used when the user asks to "calculate child support", "養育費を計算", "婚姻費用を計算", "養育費月額", "婚姻費用分担額", "算定表で計算", or wants deterministic computation of child support or marital cost-sharing under the 令和元年改定 standard.
version: 1.0.0
---

# 養育費・婚姻費用計算（child-support-calc）

令和元年 12 月改定の標準算定方式に基づき、養育費または婚姻費用の月額を決定論的に計算する。東京家裁・大阪家裁の公開している算定表（表1〜表19）と原理的に一致する計算式を用いる。

## 前提条件

- アクティブな matter が設定されていること
- 義務者（支払義務者）・権利者（請求権者）の年収が判明していること
- 養育費計算の場合は子の年齢が判明していること

## 計算対象

1. **養育費（民法 766 条・877 条）**: 離婚後に子を監護する親（権利者）が他方（義務者）に請求する子の扶養費
2. **婚姻費用（民法 760 条）**: 別居中の夫婦間の生活費分担

## ワークフロー

### Step 0: Matter の解決

```bash
python3 skills/_lib/matter.py resolve
```

`source=none` ならエラーで中止。解決できた場合のみ続行。

### Step 1: 計算種別の確認

ユーザーに以下を確認:

```
計算するのは「養育費」か「婚姻費用」のどちらか？
  1. 養育費 (child_support)   — 離婚後の子の扶養費
  2. 婚姻費用 (spousal_support) — 別居中の夫婦間の生活費分担
```

### Step 2: 義務者・権利者の年収聴取

| 項目 | 確認内容 |
|---|---|
| 義務者年収（円） | 支払義務者（原則、収入の高い側）の年収 |
| 義務者の所得種別 | `salary`（給与所得者）／`business`（自営業・事業所得） |
| 権利者年収（円） | 支払請求側。収入がない場合は 0 |
| 権利者の所得種別 | `salary` / `business` |

給与所得者の年収は**源泉徴収票の「支払金額」**（額面）を使う。自営業者は確定申告書の「事業所得」を使う。

### Step 3: 子の情報聴取（養育費の場合）

子一人ずつ年齢を確認する。生活費指数:
- 0-14 歳: 62
- 15-19 歳: 85

20 歳以上は原則扶養義務外（民法 877 条）のためエラーとなる。

### Step 4: 計算実行

**計算実行前に監査ログに記録する（法律事務所のコンプライアンス要件）:**

```bash
python3 skills/_lib/audit.py record --matter {matter_id} --skill child-support-calc --event calc_run --note "種別: {child_support or spousal_support} / 義務者: {name} / 子: {children_count}名"
```

続いて、収集した情報を JSON にまとめて `calc.py` を呼び出す:

```bash
python3 skills/child-support-calc/calc.py calc --pretty --json '<payload>'
```

計算結果提示後、結果を監査ログに記録:

```bash
python3 skills/_lib/audit.py record --matter {matter_id} --skill child-support-calc --event calc_result --note "月額={monthly_amount}円"
```

入力 JSON 例（養育費 子1人）:

```json
{
  "kind": "child_support",
  "obligor": {
    "annual_income": 5000000,
    "income_type": "salary"
  },
  "obligee": {
    "annual_income": 1000000,
    "income_type": "salary"
  },
  "children": [
    {"age": 10}
  ]
}
```

婚姻費用の場合:

```json
{
  "kind": "spousal_support",
  "obligor": {"annual_income": 5000000, "income_type": "salary"},
  "obligee": {"annual_income": 1000000, "income_type": "salary"},
  "children": [{"age": 10}]
}
```

### Step 5: 結果の提示

`--pretty` 出力を整形して表示する。主なポイント:

- **月額**（1,000 円単位で四捨五入、算定表の表記慣行）
- **年額**
- **内訳**（義務者・権利者の基礎収入、子の指数合計）
- **警告**（算定表範囲外の場合）

### Step 6: 注意事項の案内

以下をユーザーに明示する:

- 本計算値は**令和元年改定標準算定方式に基づく目安額**
- 以下の個別事情は**本計算器では反映していない**:
  - 住宅ローン負担の調整（義務者が住宅に住み続ける場合等）
  - 私立学校費用・塾費用・医療費等の特別加算
  - 再婚・養子縁組による扶養義務の変動
  - 義務者の生活保護受給者化
- 調停・審判では、裁判官の裁量により標準額から±20-30% 程度増減することがある
- 合意できた月額は `divorce-agreement`（離婚協議書）や `child-support-application`（養育費請求調停申立書）に記載する

## 対応範囲外

- 住宅ローン負担調整: 調整額は「義務者の総収入に住居関係費の何割かを加算する」等の複数流儀があり、事案ごとに検討要
- 私立学校・医療費等の特別費用加算
- 生活保護・障害年金等の特殊な収入源
- 算定表範囲外の高額所得者（義務者年収 2,000 万超）: 警告を出すが計算自体は試みる。実務では「余剰所得が多いほど比例的に増額するとは限らない」という裁判例あり

## エラーハンドリング

- **kind が無効**: 'child_support' または 'spousal_support' を案内
- **養育費で children なし**: 「養育費の計算には子 1 人以上が必要」と案内
- **子の年齢 20 以上**: 「20 歳以上は原則扶養義務外（民法 877 条）」と案内
- **義務者年収 0**: 計算結果 0 + 警告「義務者が生活保護受給者等の場合は別途考慮」

## セルフテスト

```bash
python3 skills/child-support-calc/test_calc.py
```

20 件のテストで以下を検証:
- 基礎収入割合テーブル（給与・自営）
- 子の生活費指数テーブル
- 1,000 円単位丸め
- 養育費（子 1 人 0-14歳）算定表範囲内
- 養育費（子 1 人 15-19歳）指数 85 で増額
- 養育費（子 2 人 混合年齢）
- 婚姻費用（子なし）
- 婚姻費用（子 1 人）
- 権利者＞義務者ケース
- 自営業義務者
- 高額所得者警告
- 子 3 人以上の指数合算
- 年収上昇に伴う月額の単調増加
