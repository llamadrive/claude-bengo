---
name: traffic-damage-calc
description: This skill should be used when the user asks to "calculate traffic accident damages", "交通事故の損害額を計算", "損害賠償額を算出", "赤い本基準で計算", "逸失利益を計算", "後遺障害の慰謝料", "過失相殺後の金額", or wants deterministic computation of personal-injury damages under the Red Book (赤い本) standard.
version: 1.0.0
---

# 交通事故損害賠償計算（traffic-damage-calc）

赤い本基準で交通事故の損害賠償額を**決定論的に**計算する。LLM の推論ではなく、
実務で確立した計算式と判例表値を用いるため、任意保険会社・相手方弁護士・
裁判所に対して論拠を示せる額が出る。

## 前提条件

- アクティブな matter が設定されていること（機密情報を扱うため）
- 被害者の基本情報・事故の概要・傷害の程度が揃っていること

## 計算できる項目

1. **積極損害（実費）** — 治療費・通院交通費・装具費・入院雑費・付添看護費
2. **消極損害（得べかりし利益）** — 休業損害・後遺障害逸失利益・死亡逸失利益
3. **慰謝料** — 入通院慰謝料（赤い本別表 I/II）・後遺障害慰謝料（等級別）・死亡慰謝料
4. **弁護士費用** — 認容額の 10%（判例実務）
5. **遅延損害金** — 年 3%（改正民法 404 条、2020/04-）
6. **過失相殺** — 民法 722 条 2 項

## ワークフロー

### Step 0: workspace の解決

機密スキル実行時、CWD（または親ディレクトリ）の `.claude-bengo/` を walk-up で探す。見つからなければ CWD に silently 新規作成する。弁護士が事前に`/matter-create` のような登録を行う必要はない。

### Step 1: 被害者情報の聴取

以下を順に確認する。不明な項目は「不明」として進め、後で再確認する:

| 項目 | 確認内容 |
|---|---|
| 氏名 | 被害者氏名 |
| 事故時年齢 | 整数 |
| 性別 | male / female |
| 職業 | `salaried`（給与所得者）/ `self_employed`（自営業）/ `household`（主婦）/ `student`（学生）/ `unemployed`（無職）/ `part_time`（パート） |
| 年収 | 源泉徴収票の支払金額（給与所得者）／確定申告の所得（自営業）。主婦は空欄で賃金センサスを使用 |
| 家計支持者か | true/false。死亡慰謝料の区分に影響 |

### Step 2: 事故情報の聴取

| 項目 | 確認内容 |
|---|---|
| 事故発生日 | YYYY-MM-DD 形式 |
| 被害者過失割合 | 0-100 の数値。過失割合が不明な場合は 0 で仮計算し、別途 `判タ38号` を参照して確定 |

### Step 3: 治療経過の聴取

| 項目 | 確認内容 |
|---|---|
| 入院日数 | 実日数 |
| 通院日数 | 実日数 |
| 治療費総額 | 円 |
| 通院交通費 | 円 |
| 装具・器具費 | 円 |
| 付添看護（入院） | 家族付添の日数 |
| 付添看護（通院） | 家族付添の日数 |
| 傷害の程度 | `major`（骨折・他覚所見あり）/ `minor`（むち打ち等、他覚所見なし）。赤い本別表 I/II を切替 |

### Step 4: 休業損害の聴取

| 項目 | 確認内容 |
|---|---|
| 休業日数 | 実日数 |
| 日額の上書き（任意） | 判例基準で個別計算したい場合に指定 |

### Step 5: 後遺障害の聴取（該当時）

| 項目 | 確認内容 |
|---|---|
| 等級 | 1-14（後遺障害等級） |
| 稼働可能年数 | 原則 67 歳 - 事故時年齢。長期の後遺障害では別途検討 |

### Step 6: 死亡事案の情報（該当時）

| 項目 | 確認内容 |
|---|---|
| 被扶養者数 | 生活費控除率の基準 |

### Step 7: 計算実行

**計算実行前に、監査ログにイベントを記録する（法律事務所のコンプライアンス要件）:**

```bash
python3 skills/_lib/audit.py record --skill traffic-damage-calc --event calc_run --note "被害者: {victim_name} / 等級: {disability_grade or 'なし'}"
```

続いて、収集した情報を JSON にまとめて `calc.py` を呼び出す:

```bash
python3 skills/traffic-damage-calc/calc.py calc --pretty --json '<heir-json>'
```

計算結果（合計額）をユーザーに提示した後、結果の主要数値を監査ログに記録する:

```bash
python3 skills/_lib/audit.py record --skill traffic-damage-calc --event calc_result --note "grand_total={合計額} / 内訳: 慰謝料={hosp_consol}/逸失利益={future_loss}"
```

入力 JSON 例:

```json
{
  "victim": {
    "name": "甲野太郎",
    "age_at_accident": 35,
    "gender": "male",
    "occupation_type": "salaried",
    "annual_income": 5000000,
    "is_household_supporter": true
  },
  "accident": {
    "date": "2024-04-01",
    "victim_fault_percent": 10
  },
  "medical": {
    "hospital_days": 30,
    "outpatient_days": 180,
    "medical_fees": 1500000,
    "transportation": 50000,
    "equipment": 30000,
    "nursing_days_hospital": 10,
    "severity": "major"
  },
  "lost_wages": {
    "days_off_work": 90
  },
  "disability": {
    "grade": 12,
    "years_until_67": 32
  },
  "options": {
    "include_lawyer_fee": true,
    "include_delay_interest": true,
    "settlement_date": "2026-04-01"
  }
}
```

### Step 8: 結果の提示

`--pretty` 形式の出力を整形して表示し、以下も併記する:

- 準拠基準（赤い本 2024 年版）
- 各項目の内訳
- 合計請求額
- 必要に応じて `settlement-traffic` テンプレートへの転記案内（`/template-install settlement-traffic`）

### Step 9: 論拠の注意書き

計算結果は**赤い本基準の目安額**であり、実際の交渉・訴訟では以下を考慮する旨を
ユーザーに案内する:

- 任意保険会社基準は赤い本よりも低い（3-5 割程度）
- 過失割合は判タ38号の個別類型を要参照
- 損益相殺（自賠責既払額・労災・健康保険）は本計算器では控除しない
- 具体的な交通費・治療費の立証書類（領収書等）が必要
- 後遺障害認定は自賠責調査事務所の認定が必要

## 対応範囲外

以下は本計算器で自動計算しない（範囲外）:

- 介護費用（将来介護）— 症状固定時の生活状況に強く依存
- 家屋改造費・車両改造費
- 損益相殺（自賠責・労災・健康保険・傷病手当金）— 別途控除する運用
- 物損（修理費・代車料・評価損）— 人身損害専用
- 任意保険基準・青本基準（赤い本のみ）
- 年金分割的な定期金賠償

これらが関係する場合は、ユーザーに別途の手計算または専門ソフトの使用を案内する。

## エラーハンドリング

- **等級が 1-14 の範囲外**: 入力エラーとして中止
- **過失割合が 0-100 の範囲外**: 入力エラーとして中止
- **年齢が 0-120 の範囲外**: 入力エラーとして中止
- **職業が既定値以外**: 対応する職業区分を案内
- **年収が未指定 + 主婦以外**: 休業損害・逸失利益が 0 になる旨警告

## セルフテスト

```bash
python3 skills/traffic-damage-calc/test_calc.py
```

20 件の判例・実務ケースで計算結果を検証する（14 級後遺障害、12 級後遺障害、
主婦の休業損害、死亡逸失利益、過失相殺、弁護士費用、遅延損害金等）。

## 次の一手（ユーザーに提案する）

計算完了時、結果表示の後に以下を提案する:

```
💡 次の一手:
  - 交通事故示談書を作成: /template-install → 「交通事故示談書」
  - 不法行為の条文を確認: /law-search 民法709条
  - 訴訟時の書面分析: /lawsuit-analysis 訴状.pdf 答弁書.pdf
```
