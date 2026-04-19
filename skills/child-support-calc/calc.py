#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""養育費・婚姻費用計算モジュール（令和元年改定標準算定方式）。

本スクリプトは、離婚後の養育費および別居中の婚姻費用を、令和元年（2019 年）
12 月の東京家裁・大阪家裁共同研究報告「養育費・婚姻費用算定表」の改定版で
示された標準算定方式に基づき決定論的に計算する。令和元年の算定表
（東京家裁ウェブサイト等で公開）はこの数式から導出される。

## 関連条文・基準

- 民法 766 条（離婚後の子の監護費用）
- 民法 877 条（直系血族の扶養義務）
- 民法 760 条（夫婦間の費用分担）
- 令和元年 12 月 23 日 家裁家事部研究報告（標準算定方式）

## 計算の概要

標準算定方式:

1. **基礎収入** = 年収 × 基礎収入割合
   - 給与所得者と自営業者で割合が異なる（自営業のほうが高率）

2. **生活費指数**
   - 親: 100
   - 子 0-14 歳: 62
   - 子 15-19 歳: 85

3. **養育費月額**
   ```
   子の標準的生活費 = 義務者基礎収入 × Σ子指数 / (100 + Σ子指数)
   義務者分担額 = 子の標準的生活費 × 義務者基礎収入 / (義務者+権利者基礎収入)
   養育費月額 = 義務者分担額 / 12
   ```

4. **婚姻費用月額**
   ```
   権利者世帯の生活費 = (義務者+権利者基礎収入) × (100 + Σ子指数) / (200 + Σ子指数)
   義務者分担額 = 権利者世帯の生活費 - 権利者基礎収入
   婚姻費用月額 = 義務者分担額 / 12
   ```

## 対応範囲外（現バージョンでの明示的な非対応事項）

- 算定表範囲外（義務者年収 2,000 万超、または権利者年収が義務者を上回る
  高額所得のケース）: 警告を出すが計算は試みる。実務では個別加算事由等の
  検討が必要
- 住宅ローン負担の調整
- 私立学校費用・塾費用等の特別費用（加算事由）
- 再婚・養子縁組による扶養義務の変動
- 義務者の生活保護受給者化
- 子の健康保険料・医療費の個別調整

これらが関係する場合は、ユーザーに別途手計算を促す。
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# 基礎収入割合（令和元年改定）
#
# 年収に応じた階層別割合。給与所得者・自営業者（事業所得）で異なる。
# 令和元年算定表の根拠データ（東京家裁家事部研究報告書より）。
# ---------------------------------------------------------------------------

# 給与所得者（給与収入から税・社会保険料を控除した基礎収入割合）
# 単位: (上限年収円, 割合分子, 割合分母)
_SALARY_BRACKETS: List[Tuple[int, int, int]] = [
    (75_0000, 54, 100),
    (100_0000, 50, 100),
    (125_0000, 46, 100),
    (175_0000, 44, 100),
    (275_0000, 43, 100),
    (525_0000, 42, 100),
    (725_0000, 41, 100),
    (1325_0000, 40, 100),
    (1475_0000, 39, 100),
    (2000_0000, 38, 100),
]

# 自営業者（事業所得から税・社会保険料相当を控除した基礎収入割合）
_BUSINESS_BRACKETS: List[Tuple[int, int, int]] = [
    (66_0000, 61, 100),
    (82_0000, 60, 100),
    (98_0000, 59, 100),
    (256_0000, 58, 100),
    (349_0000, 57, 100),
    (392_0000, 56, 100),
    (496_0000, 55, 100),
    (563_0000, 54, 100),
    (784_0000, 53, 100),
    (942_0000, 52, 100),
    (1046_0000, 51, 100),
    (1179_0000, 50, 100),
    (1482_0000, 49, 100),
    (1567_0000, 48, 100),
]

# 生活費指数
PARENT_INDEX = 100
CHILD_INDEX_0_14 = 62
CHILD_INDEX_15_19 = 85
SPOUSE_INDEX = 100  # 婚姻費用計算で権利者の生活費指数


def _basic_income_rate(income_type: str, annual_income: int) -> Fraction:
    """年収に対する基礎収入割合を返す。"""
    if income_type == "salary":
        brackets = _SALARY_BRACKETS
    elif income_type == "business":
        brackets = _BUSINESS_BRACKETS
    else:
        raise ValueError(f"income_type は 'salary' または 'business'（受信: {income_type}）")

    for upper, num, den in brackets:
        if annual_income <= upper:
            return Fraction(num, den)
    # 範囲外（高額）: 上限の割合を適用しつつ呼出元に警告用メッセージを出させる
    return Fraction(brackets[-1][1], brackets[-1][2])


def _basic_income(annual_income: int, income_type: str) -> Tuple[int, Fraction, bool]:
    """年収 → 基礎収入。戻り値: (基礎収入円, 使用した割合, 範囲外フラグ)"""
    if annual_income < 0:
        raise ValueError(f"年収は 0 以上（受信: {annual_income}）")

    out_of_range = False
    if income_type == "salary" and annual_income > 2000_0000:
        out_of_range = True
    elif income_type == "business" and annual_income > 1567_0000:
        out_of_range = True

    rate = _basic_income_rate(income_type, annual_income)
    basic = int(Fraction(annual_income) * rate)
    return basic, rate, out_of_range


def _child_index(age: int) -> int:
    """子の生活費指数（令和元年改定）。

    型チェック: bool と float を明示的に拒否する。Python では bool は int の
    サブクラスで `True == 1`、また `19.5` のような小数年齢は扶養指数として
    意味がない。
    """
    if isinstance(age, bool) or not isinstance(age, int):
        raise ValueError(
            f"子の年齢は整数でなければならない（bool/float は不可、受信型: {type(age).__name__}、値: {age}）"
        )
    if age < 0:
        raise ValueError(f"子の年齢は 0 以上（受信: {age}）")
    if age >= 20:
        raise ValueError(
            f"子の年齢 {age}: 20 歳以上は原則扶養義務対象外（民法 877 条）"
        )
    return CHILD_INDEX_15_19 if age >= 15 else CHILD_INDEX_0_14


# ---------------------------------------------------------------------------
# バリデーション
# ---------------------------------------------------------------------------


def _validate(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("入力は JSON オブジェクトでなければならない。")

    kind = payload.get("kind")
    if kind not in ("child_support", "spousal_support"):
        raise ValueError(
            f"kind は 'child_support'（養育費）または 'spousal_support'（婚姻費用）。受信: {kind}"
        )

    for party in ("obligor", "obligee"):
        p = payload.get(party)
        if not isinstance(p, dict):
            raise ValueError(f"{party} フィールドが不正")
        income = p.get("annual_income")
        # bool は int のサブクラスだが年収として意味をなさないため除外
        if isinstance(income, bool) or not isinstance(income, int) or income < 0:
            raise ValueError(f"{party}.annual_income は 0 以上の整数（受信: {income!r}）")
        if p.get("income_type") not in ("salary", "business"):
            raise ValueError(f"{party}.income_type は 'salary' または 'business'")

    children = payload.get("children", [])
    if not isinstance(children, list):
        raise ValueError("children はリスト")
    # 婚姻費用は子なしも可。養育費は少なくとも 1 人必要
    if kind == "child_support" and not children:
        raise ValueError("養育費の計算には children が 1 人以上必要")
    for i, c in enumerate(children):
        if not isinstance(c, dict) or "age" not in c:
            raise ValueError(f"children[{i}] に age が必要")
        age = c["age"]
        if isinstance(age, bool) or not isinstance(age, int):
            raise ValueError(
                f"children[{i}].age は整数（bool/float 不可、受信型: {type(age).__name__}、値: {age!r}）"
            )


# ---------------------------------------------------------------------------
# メイン計算
# ---------------------------------------------------------------------------


def compute(payload: dict) -> dict:
    """養育費または婚姻費用を計算する。"""
    _validate(payload)

    kind = payload["kind"]
    obligor = payload["obligor"]
    obligee = payload["obligee"]
    children = payload.get("children", [])

    obligor_basic, obligor_rate, obligor_oor = _basic_income(
        obligor["annual_income"], obligor["income_type"]
    )
    obligee_basic, obligee_rate, obligee_oor = _basic_income(
        obligee["annual_income"], obligee["income_type"]
    )

    child_index_sum = 0
    children_detail = []
    for c in children:
        age = c["age"]
        idx = _child_index(age)
        child_index_sum += idx
        children_detail.append({"age": age, "index": idx})

    warnings = []
    if obligor_oor:
        warnings.append(
            "義務者の年収が算定表範囲を超えている。標準算定方式で計算するが、高額所得者事案では裁判例と整合しない場合がある"
        )
    if obligee_oor:
        warnings.append("権利者の年収が算定表範囲を超えている。")

    if obligor_basic == 0:
        warnings.append("義務者の基礎収入が 0。実務上、義務者が生活保護受給者等の場合は別途考慮")
        return {
            "kind": kind,
            "monthly_amount": 0,
            "annual_amount": 0,
            "breakdown": {
                "obligor_basic_income": obligor_basic,
                "obligor_rate": f"{float(obligor_rate)*100:.1f}%",
                "obligee_basic_income": obligee_basic,
                "obligee_rate": f"{float(obligee_rate)*100:.1f}%",
                "children": children_detail,
                "child_index_sum": child_index_sum,
            },
            "warnings": warnings + ["義務者基礎収入が 0 のため請求額 0"],
            "notes": _standard_notes(kind),
        }

    # 権利者収入が義務者収入を上回るケース（婚姻費用で発生し得る）
    if kind == "spousal_support" and obligee_basic >= obligor_basic and not children:
        warnings.append(
            "権利者基礎収入が義務者基礎収入以上かつ子なし。婚姻費用は 0 または収入の低い側へ支払う結果となる"
        )

    if kind == "child_support":
        result = _calc_child_support(
            obligor_basic, obligee_basic, child_index_sum, children_detail
        )
    else:  # spousal_support
        result = _calc_spousal_support(
            obligor_basic, obligee_basic, child_index_sum, children_detail
        )

    result["breakdown"].update(
        {
            "obligor_rate": f"{float(obligor_rate)*100:.1f}%",
            "obligee_rate": f"{float(obligee_rate)*100:.1f}%",
        }
    )
    result["warnings"] = warnings
    result["notes"] = _standard_notes(kind)
    return result


def _calc_child_support(
    obligor_basic: int, obligee_basic: int, child_index_sum: int, children: List[dict]
) -> dict:
    """養育費計算。"""
    # 子の標準的生活費 = 義務者基礎収入 × Σ子指数 / (100 + Σ子指数)
    # ただし実務では、双方の基礎収入の合算から子の生活費を按分する。
    # 令和元年改定方式:
    #   子の生活費 = 義務者基礎収入 × (Σ子指数) / (PARENT_INDEX + Σ子指数)
    #   義務者分担 = 子の生活費 × 義務者基礎収入 / (義務者基礎収入 + 権利者基礎収入)
    if obligor_basic + obligee_basic == 0:
        return {
            "kind": "child_support",
            "monthly_amount": 0,
            "annual_amount": 0,
            "breakdown": {
                "obligor_basic_income": obligor_basic,
                "obligee_basic_income": obligee_basic,
                "children": children,
                "child_index_sum": child_index_sum,
                "children_living_cost_annual": 0,
                "obligor_share_annual": 0,
            },
        }

    # 子の生活費（年額）
    children_living_cost = Fraction(obligor_basic) * Fraction(child_index_sum) / Fraction(
        PARENT_INDEX + child_index_sum
    )

    # 義務者分担（年額）= 子の生活費 × 義務者基礎収入 / (義務者基礎収入 + 権利者基礎収入)
    obligor_share = children_living_cost * Fraction(obligor_basic) / Fraction(
        obligor_basic + obligee_basic
    )

    monthly = int(obligor_share / Fraction(12))
    # 実務慣行: 1,000 円単位に丸める（算定表と合わせるため）
    monthly_rounded = _round_to_1000(monthly)
    annual = monthly_rounded * 12

    return {
        "kind": "child_support",
        "monthly_amount": monthly_rounded,
        "annual_amount": annual,
        "breakdown": {
            "obligor_basic_income": obligor_basic,
            "obligee_basic_income": obligee_basic,
            "children": children,
            "child_index_sum": child_index_sum,
            "children_living_cost_annual": int(children_living_cost),
            "obligor_share_annual": int(obligor_share),
            "monthly_before_rounding": monthly,
        },
    }


def _calc_spousal_support(
    obligor_basic: int, obligee_basic: int, child_index_sum: int, children: List[dict]
) -> dict:
    """婚姻費用計算。"""
    if obligor_basic + obligee_basic == 0:
        return {
            "kind": "spousal_support",
            "monthly_amount": 0,
            "annual_amount": 0,
            "breakdown": {
                "obligor_basic_income": obligor_basic,
                "obligee_basic_income": obligee_basic,
                "children": children,
                "child_index_sum": child_index_sum,
                "obligee_household_cost_annual": 0,
            },
        }

    # 権利者世帯（権利者＋子）の生活費
    # = (義務者基礎収入 + 権利者基礎収入) × (100 + Σ子指数) / (200 + Σ子指数)
    numerator = Fraction(100 + child_index_sum)
    denominator = Fraction(200 + child_index_sum)
    obligee_household_cost = (
        Fraction(obligor_basic + obligee_basic) * numerator / denominator
    )
    # 義務者分担 = 権利者世帯の生活費 - 権利者自身の基礎収入
    obligor_share = obligee_household_cost - Fraction(obligee_basic)

    if obligor_share <= 0:
        monthly_rounded = 0
        annual = 0
    else:
        monthly = int(obligor_share / Fraction(12))
        monthly_rounded = _round_to_1000(monthly)
        annual = monthly_rounded * 12

    return {
        "kind": "spousal_support",
        "monthly_amount": monthly_rounded,
        "annual_amount": annual,
        "breakdown": {
            "obligor_basic_income": obligor_basic,
            "obligee_basic_income": obligee_basic,
            "children": children,
            "child_index_sum": child_index_sum,
            "obligee_household_cost_annual": int(obligee_household_cost),
            "obligor_share_annual_pre_round": int(obligor_share) if obligor_share > 0 else 0,
        },
    }


def _round_to_1000(amount: int) -> int:
    """1,000 円単位で四捨五入。

    F-028: 公式「令和元年算定表」は実際には 1〜2万円のバンドで値が記載されており、
    本関数の 1,000 円単位丸めは**算定表の表示粒度とは一致しない**。丸めはあくまで
    実務上の慣行的な表記揃えであり、1,000 円ずれの金額は算定表の同一バンドに
    含まれる。法廷で「算定表のどのセル」に該当するかを主張する際は
    `monthly_before_rounding` を参照して 1万円または 2万円バンドに再丸めしてほしい。
    """
    if amount <= 0:
        return 0
    return ((amount + 500) // 1000) * 1000


def _to_table_band(amount: int, band_width: int = 20000) -> Tuple[int, int]:
    """算定表バンドの下限・上限を返す（F-028）。

    `band_width` 既定は 2万円。1万円バンドを使う場合は 10000 を渡す。
    例: amount=54_000, band_width=20000 → (40_000, 60_000)
    """
    if amount <= 0:
        return (0, 0)
    lower = (amount // band_width) * band_width
    return (lower, lower + band_width)


def _standard_notes(kind: str) -> List[str]:
    base = [
        "令和元年 12 月改定の標準算定方式に基づく計算",
        "金額は 1,000 円単位で四捨五入（算定表の表記慣行、1-2 万円バンドとは別粒度）",
        "算定表バンド比較は breakdown.monthly_before_rounding を参照してほしい",
        "個別事情（住宅ローン・私立学校費用・再婚・健康保険料調整等）は別途加算検討",
        "実際の調停・審判では、裁判官の裁量により標準額から増減されることがある",
    ]
    if kind == "child_support":
        base.append("民法 766 条（離婚後の子の監護費用）・877 条（直系血族の扶養義務）に基づく")
    else:
        base.append("民法 760 条（夫婦間の費用分担）に基づく。離婚前の別居中に請求する")
    return base


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_calc(args: argparse.Namespace) -> int:
    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(json.dumps({"error": f"入力ファイル読込失敗: {e}"}, ensure_ascii=False), file=sys.stderr)
            return 2
    elif args.json:
        try:
            payload = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"--json 不正: {e}"}, ensure_ascii=False), file=sys.stderr)
            return 1
    else:
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"stdin JSON 不正: {e}"}, ensure_ascii=False), file=sys.stderr)
            return 1

    try:
        result = compute(payload)
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.pretty:
        _print_pretty(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _print_pretty(result: dict) -> None:
    label = "養育費" if result["kind"] == "child_support" else "婚姻費用"
    b = result["breakdown"]
    print(f"\n## {label}の計算結果（令和元年改定標準算定方式）\n")
    print(f"  義務者基礎収入  : {b['obligor_basic_income']:>12,} 円 ({b['obligor_rate']})")
    print(f"  権利者基礎収入  : {b['obligee_basic_income']:>12,} 円 ({b['obligee_rate']})")
    print(f"  子の指数合計    : {b['child_index_sum']:>12} (0-14歳: 62 / 15-19歳: 85)")
    for c in b.get("children", []):
        print(f"    - 子 {c['age']} 歳: 指数 {c['index']}")
    print(f"  ═══════════════════════════════════")
    print(f"  ★ 月額          : {result['monthly_amount']:>12,} 円/月")
    print(f"    年額          : {result['annual_amount']:>12,} 円/年")
    if result.get("warnings"):
        print("\n  [警告]")
        for w in result["warnings"]:
            print(f"    ・{w}")


def main() -> int:
    ap = argparse.ArgumentParser(description="養育費・婚姻費用計算（令和元年改定算定方式）")
    ap.add_argument("--self-test", action="store_true", help="組込セルフテスト")
    sub = ap.add_subparsers(dest="command")

    p_calc = sub.add_parser("calc", help="養育費または婚姻費用を計算")
    p_calc.add_argument("--input", help="入力 JSON ファイル")
    p_calc.add_argument("--json", help="入力 JSON 文字列")
    p_calc.add_argument("--pretty", action="store_true", help="人間可読な表形式で出力")

    args = ap.parse_args()

    if args.self_test:
        sys.path.insert(0, str(__file__).rsplit("/", 1)[0])
        from test_calc import run_all
        return run_all()

    if args.command is None:
        ap.print_help()
        return 1
    if args.command == "calc":
        return _cmd_calc(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
