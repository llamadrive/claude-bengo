---
name: inheritance-calc
description: This skill should be used when the user asks to "calculate inheritance shares", "法定相続分を計算", "相続分を出して", "相続割合", "誰がどれだけ相続する", "遺留分", or wants to compute statutory inheritance shares from a family tree.
version: 1.0.0
---

# 法定相続分計算（inheritance-calc）

家族関係データから民法の規定に基づき法定相続分を決定論的に計算する。**LLM の推論ではなく、民法の条文ロジックに従った正確な計算を行う。**

## ワークフロー

### Step 1: 家族関係データの取得

以下のいずれかからデータを取得する:
- 同一会話内で `/family-tree` を実行済みの場合: そのデータを使用
- ユーザーが口頭で家族構成を説明した場合: 聞き取りからデータを構築
- 戸籍謄本 PDF がある場合: `/family-tree` を先に実行してデータを抽出

必要なデータ:
- 被相続人（死亡者）の特定
- 配偶者の有無
- 子の有無と人数（養子含む）
- 子が先に死亡している場合、その子（孫）の有無
- 直系尊属（父母）の生存状況
- 兄弟姉妹の有無（半血/全血の区別含む）
- 相続放棄した者がいるか

### Step 2: 相続人の確定

`skills/inheritance-calc/references/inheritance-rules.md` を Read ツールで読み込み、以下の順序で相続人を確定する:

**相続人の順位（民法887条・889条・890条）:**

1. **常に相続人:** 配偶者（民法890条）
2. **第1順位:** 子（民法887条1項）
   - 子が被相続人より先に死亡 → その子（孫）が代襲相続（民法887条2項）
   - 孫も死亡 → ひ孫が再代襲（民法887条3項）
3. **第2順位（子がいない場合のみ）:** 直系尊属（民法889条1号）
   - 父母が生存 → 父母
   - 父母が死亡、祖父母が生存 → 祖父母（親等が近い者が優先）
4. **第3順位（子も直系尊属もいない場合のみ）:** 兄弟姉妹（民法889条2号）
   - 兄弟姉妹が先に死亡 → その子（甥姪）が代襲相続（1代限り）

**相続放棄の処理:**
- 相続放棄した者は最初から相続人でなかったものとみなす
- 相続放棄者の子は代襲相続しない（放棄 ≠ 死亡）
- 第1順位の全員が放棄 → 第2順位に移行

### Step 3: 法定相続分の計算

**民法900条の計算ルール:**

| 相続人の組合せ | 配偶者の相続分 | 他の相続人の相続分 |
|-------------|------------|--------------|
| 配偶者 + 子 | 1/2 | 子が 1/2 を均等分割 |
| 配偶者 + 直系尊属 | 2/3 | 直系尊属が 1/3 を均等分割 |
| 配偶者 + 兄弟姉妹 | 3/4 | 兄弟姉妹が 1/4 を均等分割 |
| 配偶者のみ | 1/1（全部） | — |
| 子のみ（配偶者なし） | — | 子が均等分割 |
| 直系尊属のみ | — | 直系尊属が均等分割 |
| 兄弟姉妹のみ | — | 兄弟姉妹が均等分割 |

**特殊ルール:**

- **代襲相続（民法901条）:** 代襲相続人の相続分 = 被代襲者が受けるべきであった相続分。代襲者が複数いる場合は均等分割。
- **半血兄弟姉妹（民法900条4号但書）:** 父母の一方のみを同じくする兄弟姉妹の相続分は、父母の双方を同じくする兄弟姉妹の相続分の 1/2。
- **養子:** 実子と同一の相続分。

### Step 4: 計算の実行

**Python スクリプトで決定論的に計算する。** LLM の推論に頼らない。

```bash
python3 -c "
# 入力: 相続人リスト（Claude が Step 2 で確定したもの）
# 以下の変数を実際の値に置き換えて実行する

spouse = True          # 配偶者の有無
children = 3           # 子の数（代襲相続人含まない）
deceased_children = 0  # 先に死亡した子の数
grandchildren_per_deceased = []  # 死亡した子ごとの孫の数 (例: [2, 1])
ascendants = 0         # 直系尊属の数（第1順位がいない場合のみ）
siblings_full = 0      # 全血兄弟姉妹の数（第1,2順位がいない場合のみ）
siblings_half = 0      # 半血兄弟姉妹の数
renounced = []         # 相続放棄者のリスト（'child', 'spouse' 等）

from fractions import Fraction

# 相続放棄の処理
effective_children = children - (renounced.count('child') if 'child' in renounced else 0)
has_spouse = spouse and 'spouse' not in renounced

# 代襲相続人を含む実効的な子の数
total_child_lines = effective_children - deceased_children + len(grandchildren_per_deceased)

results = {}

if total_child_lines > 0:
    # 第1順位: 配偶者 + 子
    spouse_share = Fraction(1, 2) if has_spouse else Fraction(0)
    children_total = Fraction(1, 2) if has_spouse else Fraction(1)
    per_child = children_total / total_child_lines if total_child_lines > 0 else Fraction(0)
    
    if has_spouse:
        results['配偶者'] = spouse_share
    
    for i in range(effective_children - deceased_children):
        results[f'子{i+1}'] = per_child
    
    for i, gc_count in enumerate(grandchildren_per_deceased):
        parent_share = per_child
        per_grandchild = parent_share / gc_count if gc_count > 0 else Fraction(0)
        for j in range(gc_count):
            results[f'代襲相続人（孫{i+1}-{j+1}）'] = per_grandchild

elif ascendants > 0:
    # 第2順位: 配偶者 + 直系尊属
    spouse_share = Fraction(2, 3) if has_spouse else Fraction(0)
    ascendants_total = Fraction(1, 3) if has_spouse else Fraction(1)
    per_ascendant = ascendants_total / ascendants
    
    if has_spouse:
        results['配偶者'] = spouse_share
    for i in range(ascendants):
        results[f'直系尊属{i+1}'] = per_ascendant

elif siblings_full + siblings_half > 0:
    # 第3順位: 配偶者 + 兄弟姉妹
    spouse_share = Fraction(3, 4) if has_spouse else Fraction(0)
    siblings_total = Fraction(1, 4) if has_spouse else Fraction(1)
    
    # 半血兄弟姉妹は全血の1/2
    # 全血1人分を1単位、半血1人分を0.5単位として計算
    total_units = siblings_full + Fraction(siblings_half, 2)
    per_full = siblings_total / total_units if total_units > 0 else Fraction(0)
    per_half = per_full / 2
    
    if has_spouse:
        results['配偶者'] = spouse_share
    for i in range(siblings_full):
        results[f'兄弟姉妹{i+1}（全血）'] = per_full
    for i in range(siblings_half):
        results[f'兄弟姉妹{i+1}（半血）'] = per_half

elif has_spouse:
    results['配偶者'] = Fraction(1)

# 結果表示
print('法定相続分:')
total = Fraction(0)
for heir, share in results.items():
    pct = float(share) * 100
    print(f'  {heir}: {share} ({pct:.1f}%)')
    total += share
print(f'  合計: {total} ({float(total)*100:.1f}%)')
"
```

**重要:** 上記のスクリプトはテンプレートである。Claude は Step 2 で確定した相続人情報に基づいて変数の値を設定し、スクリプトを実行する。

### Step 5: 結果の表示

計算結果を以下の形式で表示する:

```
## 法定相続分の計算結果

被相続人: 甲野太郎（令和5年2月14日死亡）

### 相続人と法定相続分

| 相続人 | 続柄 | 法定相続分 | 割合 |
|-------|------|---------|------|
| 甲野花子 | 配偶者 | 1/2 | 50.0% |
| 甲野一郎 | 長男 | 1/6 | 16.7% |
| 甲野良子 | 長女 | 1/6 | 16.7% |
| 甲野次郎 | 二男 | 1/6 | 16.7% |
| **合計** | | **1/1** | **100.0%** |

### 計算根拠
- 民法900条1号: 配偶者と子が相続人 → 配偶者 1/2、子 1/2
- 民法900条4号: 子3人で均等分割 → 各 1/6
```

### Step 6: 遺留分の計算（オプション）

ユーザーが遺留分（民法1042条）について質問した場合:

- **遺留分権利者:** 配偶者、子、直系尊属（兄弟姉妹には遺留分なし）
- **遺留分の割合:**
  - 直系尊属のみが相続人 → 被相続人の財産の 1/3
  - それ以外 → 被相続人の財産の 1/2
- **各人の遺留分 = 遺留分全体 × 法定相続分**

### Step 7: /family-tree との連携

同一会話内で `/family-tree` が実行済みの場合:
- 家系図 HTML に計算結果を追記する（各人の名前の横に相続分を表示）
- または別途テキストで計算結果サマリーを出力する

## エラーハンドリング

- 被相続人が特定できない: 「誰が被相続人（亡くなった方）か教えてほしい」
- 相続人が1人もいない: 「相続人不存在のケースである。特別縁故者への分与（民法958条の2）や国庫帰属（民法959条）の可能性がある」
- 情報が不足: 不明な項目について質問する（「お子さんは何人いるか？」「ご両親は健在か？」）
