---
name: iryubun-calc
description: This skill should be used when the user asks to "calculate iryubun", "遺留分侵害額", "遺留分", "遺留分侵害額請求", "遺贈", "生前贈与の遺留分算入", or wants deterministic computation of reserved-portion infringement under 民法 1042-1048.
version: 1.0.0
---

# 遺留分侵害額計算（iryubun-calc）

民法 1042 条以下に基づき、遺贈・生前贈与により遺留分が侵害された場合の金銭請求額を決定論的に計算する。`/inheritance-calc` と組み合わせて使う。

## ワークフロー

### Step -1: 同意ゲート（v3.3.0-iter2〜 機密スキルに格上げ）

本 skill は遺産評価書・残高証明書等の client 書類を扱う可能性があるため、
事務所管理者の同意が必要:

```bash
python3 skills/_lib/consent.py check
```

exit 非 0 なら skill を中断して `/consent` を案内する（未設定なら admin-setup → grant、設定済みなら grant のみ）。

### Step 0: workspace の解決

機密スキル実行時、CWD（または親ディレクトリ）の `.claude-bengo/` を walk-up で探す。見つからなければ CWD に silently 新規作成する。弁護士が事前に`/matter-create` のような登録を行う必要はない。

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
python3 skills/_lib/audit.py record --skill iryubun-calc --event calc_run --note "請求者: {requesting_heir_id}"
python3 skills/iryubun-calc/calc.py calc --pretty --json '<payload>'
python3 skills/_lib/audit.py record --skill iryubun-calc --event calc_result --note "侵害額={iryubun_infringement}円"
```

### Step 5: 結果の提示

基礎財産・総体的遺留分（1/2 or 1/3）・個別的遺留分・請求者既受領分・侵害額の内訳を提示する。

### Step 5.5: 必須出力フッター（v3.3.0-iter3〜 code-emitted 省略不可）

**v3.3.0-iter3〜: footer は calc.py が stderr に JSON として emit する。**
SKILL.md は fabricate しない — stderr の `calc_footer` をそのまま読んで表示する:

```bash
python3 skills/iryubun-calc/calc.py --json '<input>' 2>/tmp/calc-footer.json
cat /tmp/calc-footer.json   # 末尾行に {"calc_footer": {...}} が付く
```

結果の直後に以下を**そのまま**表示する:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠ 本計算は民法 §1042 以下（遺留分侵害額請求）に基づく決定論的補助計算である。
  弁護士法第72条に基づき、本ツールは法的助言を提供しない。
  提出前に必ず弁護士自身が以下を検算してほしい:
    • 基礎財産評価（不動産・株式・生前贈与の時価判断）
    • 1年以内贈与・特別受益の算入範囲（民法 §1044）
    • 時効（民法 §1048 — 1年/10年）の起算点
    • 相続人の範囲と個別的遺留分率
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

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
