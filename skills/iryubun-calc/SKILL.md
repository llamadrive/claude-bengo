---
name: iryubun-calc
description: This skill should be used when the user asks to "calculate iryubun", "遺留分侵害額", "遺留分", "遺留分侵害額請求", "遺贈", "生前贈与の遺留分算入", or wants deterministic computation of reserved-portion infringement under 民法 1042-1048.
version: 1.0.0
---

# 遺留分侵害額計算（iryubun-calc）

民法 1042 条以下に基づき、遺贈・生前贈与により遺留分が侵害された場合の金銭請求額を決定論的に計算する。`/inheritance-calc` と組み合わせて使う。

## ワークフロー

### Step 0: Matter 解決

`python3 skills/_lib/matter.py resolve` — 未設定なら中止。

### Step 1: 基礎財産情報の聴取

| 項目 | 内容 |
|---|---|
| positive_estate | 積極財産（預貯金・不動産・株式等の合計、円） |
| debts | 相続債務（円） |
| lifetime_gifts_to_heirs | 相続人への生前贈与（10 年以内、特別受益）。{heir_id, amount} のリスト |
| third_party_gifts | 第三者への贈与（1 年以内 or 悪意）。{amount} のリスト |
| specific_bequests | 特定遺贈。{recipient_id, amount} のリスト |

### Step 2: 相続人情報の聴取

`inheritance-calc` と同じスキーマで heir を列挙。各 heir に `legal_share`（法定相続分を Fraction 文字列 "1/2" 等）と `inherited_net_amount`（実際に相続した純額）を付ける。

### Step 3: 請求者の特定

`requesting_heir_id` で遺留分侵害額請求を行う相続人を指定する。兄弟姉妹は遺留分権利者ではない（民法 1042 条但書）ので、請求不可。

### Step 4: 監査ログ記録 + 計算実行

```bash
python3 skills/_lib/audit.py record --matter {matter_id} --skill iryubun-calc --event calc_run --note "請求者: {requesting_heir_id}"
python3 skills/iryubun-calc/calc.py calc --pretty --json '<payload>'
python3 skills/_lib/audit.py record --matter {matter_id} --skill iryubun-calc --event calc_result --note "侵害額={iryubun_infringement}円"
```

### Step 5: 結果の提示

基礎財産・総体的遺留分（1/2 or 1/3）・個別的遺留分・請求者既受領分・侵害額の内訳を提示する。

### Step 6: 時効の確認

民法 1048 条:
- 短期 1 年: 侵害を知ったときから
- 除斥 10 年: 相続開始から

両方とも失効すると請求不可。Step 5 で時効の懸念について助言する。

## 対応範囲外

- 不動産・株式の評価（ユーザー指定値を使用）
- 寄与分・特別受益との複雑な相互作用（単純な額加算で処理）
- 配偶者居住権（民法 1028 条以下）
- 受遺者・受贈者の負担順位（民法 1047 条）
- 時効の自動判定

## セルフテスト

`python3 skills/iryubun-calc/test_calc.py` — 15 件の実務典型ケース。

## 次の一手（ユーザーに提案する）

計算完了時、結果表示の後に以下を提案する:

```
💡 次の一手:
  - 法定相続分を確認: /inheritance-calc（未実行の場合）
  - 遺留分侵害額請求の内容証明を作成: /template-install → 「内容証明」
  - 民法 1042 条の条文を確認: /law-search 民法1042条
```
