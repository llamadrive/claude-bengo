---
name: property-division-calc
description: This skill should be used when the user asks to "calculate property division", "離婚の財産分与", "財産分与計算", "清算金", "夫婦共有財産の分与", or wants deterministic computation of divorce property division under 民法 768.
version: 1.0.0
---

# 離婚財産分与計算（property-division-calc）

民法 768 条に基づき、離婚時の夫婦共有財産の分与額を決定論的に計算する。

## ワークフロー

### Step 0: workspace の解決

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

### Step 3.5: 対応範囲外チェック（v3.3.0-iter3〜 必須）

以下のいずれかに該当する場合、**本 skill は清算的財産分与の「骨格数字」のみ**
を返すため、出力前にユーザーへ以下を明示し、続行確認する:

```
以下のいずれかが当事案に該当するか？

  (a) 慰謝料的財産分与・扶養的財産分与を含めたい
  (b) 年金分割（厚年法 §78-2）を含めたい
  (c) 特有財産の認定が争点（相続・贈与・婚姻前取得の立証）
  (d) 不動産の時価評価が未確定（査定書・路線価で幅がある）
  (e) 退職金のうち婚姻期間中増加分の按分方式が未確定
  (f) 債務按分方式について当事者間で争いあり（本 skill は 5 種類から選択する
      が、選択次第で結果が大きく変わる）

1 つでも該当する場合:
  → 「本計算は清算的部分のみの骨格数字。上記 (a)-(f) は本 skill では扱わない。
    弁護士が調整のうえ手計算してほしい」と明示し、ユーザーが明示的に「それでも
    骨格数字だけ見たい」と求めたときのみ Step 4 へ進む。
```

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

### Step 5.5: 必須出力フッター（v3.3.0-iter3〜 code-emitted 省略不可）

**v3.3.0-iter3〜: footer は calc.py が stderr に JSON として emit する。**
SKILL.md は fabricate しない — stderr の `calc_footer` をそのまま読んで表示する:

```bash
python3 skills/property-division-calc/calc.py --json '<input>' 2>/tmp/calc-footer.json
cat /tmp/calc-footer.json   # 末尾行に {"calc_footer": {...}} が付く
```

結果の直後に以下を**そのまま**表示する:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠ 本計算は民法 §768（財産分与）の **清算的部分のみ** の決定論的補助計算である。
  弁護士法第72条に基づき、本ツールは法的助言を提供しない。
  本計算は以下を **扱わない**:
    • 慰謝料的財産分与・扶養的財産分与
    • 年金分割（厚年法 §78-2）
    • 特有財産の判定（相続・贈与・婚姻前取得）
    • 不動産の時価評価（査定書・路線価等）
    • 退職金のうち婚姻期間中増加分の按分
    • 債務の按分方式は 5 種類から選択しており、選択次第で結果が大きく変わる
  提出前に必ず弁護士自身が事案固有の事情を検討してほしい。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

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
