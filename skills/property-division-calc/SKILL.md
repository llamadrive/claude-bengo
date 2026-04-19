---
name: property-division-calc
description: This skill should be used when the user asks to "calculate property division", "離婚の財産分与", "財産分与計算", "清算金", "夫婦共有財産の分与", or wants deterministic computation of divorce property division under 民法 768.
version: 1.0.0
---

# 離婚財産分与計算（property-division-calc）

民法 768 条に基づき、離婚時の夫婦共有財産の分与額を決定論的に計算する。

## ワークフロー

### Step 0: workspace は自動解決される（v3.0.0〜）

機密スキル実行時、CWD（または親ディレクトリ）の `.claude-bengo/` を walk-up で探す。見つからなければ CWD に silently 新規作成する。弁護士が事前に`/matter-create` のような登録を行う必要はない。

### Step 1: 財産の聴取

各財産について:

| フィールド | 内容 |
|---|---|
| name | 財産名 |
| asset_type | cash / deposit / real_estate / securities / movable / insurance / retirement / corporate_shares / other |
| value | 評価額（円、原則別居時点） |
| owner | husband / wife / joint |
| is_special_property | 特有財産なら true（民法 762 条 1 項） |
| special_reason | 特有の理由（婚姻前/相続/贈与 等） |

### Step 2: 債務の聴取

共有債務（住宅ローン残・共同生活債務等）を {amount, description} のリストで列挙。

### Step 3: 貢献度の確認

既定 50:50。医師・経営者等で差が認められる場合 `contribution_ratio: {husband: 7, wife: 3}` のように指定する。

### Step 4: 監査ログ記録 + 計算実行

```bash
python3 skills/_lib/audit.py record --skill property-division-calc --event calc_run --note "財産数: {N}"
python3 skills/property-division-calc/calc.py calc --pretty --json '<payload>'
python3 skills/_lib/audit.py record --skill property-division-calc --event calc_result --note "清算金={settlement_amount}円"
```

### Step 5: 結果の提示

- 分与対象財産（共有財産合計 - 共有債務）
- 夫・妻の取得すべき額
- 実効的な現有額（債務案分済み）
- 清算金の方向と額

### Step 6: 注意事項の案内

- **年金分割は別計算**（厚生年金保険法 78 条の 2）。本計算器は対象外
- **慰謝料的財産分与・扶養的財産分与も対象外**。本計算器は「清算的部分」のみ
- **不動産評価は時価で**。査定書・路線価等の裏付け必要
- **退職金**は婚姻期間中の増加分のみが原則対象

## 対応範囲外

- 年金分割（別計算、3 号分割 or 合意分割）
- 慰謝料的・扶養的財産分与
- 税務（譲渡所得税・贈与税）
- 将来発生する退職金の現価換算

## セルフテスト

`python3 skills/property-division-calc/test_calc.py` — 12 件の典型ケース。

## 次の一手（ユーザーに提案する）

計算完了時、結果表示の後に以下を提案する:

```
💡 次の一手:
  - 養育費・婚姻費用を計算: /child-support-calc（子がいる場合）
  - 離婚協議書を作成: /template-install → 「離婚協議書」を選択
  - 完成した協議書を校正: /typo-check 離婚協議書.docx
```
