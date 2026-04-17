#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""child-support-calc のユニットテスト。

令和元年改定算定表の代表的セルと計算結果を突き合わせて検証する。
実際の算定表（東京家裁公開）と数万円単位までは一致するはず。
（1,000 円単位丸めの差異は許容）
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from calc import (
    compute,
    _basic_income,
    _child_index,
    _round_to_1000,
    CHILD_INDEX_0_14,
    CHILD_INDEX_15_19,
)


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")
    return cond


def test_01_child_index_table() -> bool:
    ok = (
        _child_index(0) == 62
        and _child_index(10) == 62
        and _child_index(14) == 62
        and _child_index(15) == 85
        and _child_index(19) == 85
    )
    # 範囲外
    try:
        _child_index(20)
        ok = False
    except ValueError:
        pass
    try:
        _child_index(-1)
        ok = False
    except ValueError:
        pass
    return _check("01. 子の生活費指数テーブル", ok, "0-14: 62 / 15-19: 85 / 20+: 範囲外")


def test_02_salary_basic_income_rates() -> bool:
    """給与所得者の基礎収入割合: 年収 500 万 → 42%。"""
    basic, rate, oor = _basic_income(500_0000, "salary")
    ok = basic == 210_0000 and float(rate) == 0.42 and not oor
    return _check("02. 給与500万 → 基礎収入 210万 (42%)", ok, f"basic={basic}")


def test_03_business_basic_income_rates() -> bool:
    """自営業者の基礎収入割合: 所得 500 万 → 本実装は 54%。

    令和元年研究報告の公開資料によって微妙に bracket が異なるが、本実装は
    563万円までを 54% bracket に含める。重要なのは (a) 決定論的、
    (b) 同一所得なら自営 > 給与、(c) 算定表の近似値に収まる、という 3 点。
    """
    basic, rate, oor = _basic_income(500_0000, "business")
    ok = basic == 270_0000 and float(rate) == 0.54 and not oor
    # 自営 > 給与 の不変条件も確認
    salary_basic, _, _ = _basic_income(500_0000, "salary")
    ok_relative = basic > salary_basic
    return _check(
        "03. 自営500万 → 基礎収入 270万 (54%) ＋ 自営>給与の不変条件",
        ok and ok_relative,
        f"basic={basic}, salary_basic={salary_basic}",
    )


def test_04_round_to_1000() -> bool:
    ok = (
        _round_to_1000(54321) == 54000
        and _round_to_1000(54500) == 55000
        and _round_to_1000(54999) == 55000
        and _round_to_1000(0) == 0
        and _round_to_1000(-100) == 0
    )
    return _check("04. 1000 円単位丸め", ok)


def test_05_child_support_1child_0_14() -> bool:
    """子1人(10歳), 義務者給与500万, 権利者給与100万 → 算定表 4-6万円/月。

    令和元年算定表（表1・養育費 子1人・0-14歳）では 4-6 万円/月 範囲内。
    標準算定方式の計算:
      義務者基礎 = 500万 × 0.42 = 210万
      権利者基礎 = 100万 × 0.46 = 46万
      子の生活費 = 210万 × 62 / 162 = 約80.4万
      義務者分担 = 80.4万 × 210/256 = 約65.9万/年
      月額 = 65.9万 / 12 = 約54,900 → 55,000 円
    """
    payload = {
        "kind": "child_support",
        "obligor": {"annual_income": 500_0000, "income_type": "salary"},
        "obligee": {"annual_income": 100_0000, "income_type": "salary"},
        "children": [{"age": 10}],
    }
    r = compute(payload)
    # 算定表 4-6 万円/月 の範囲内 (40,000-60,000)
    ok = 40_000 <= r["monthly_amount"] <= 60_000
    return _check(
        "05. 養育費 子1人(10歳) 義務者500万/権利者100万",
        ok,
        f"月額 {r['monthly_amount']:,} 円",
    )


def test_06_child_support_1child_15_19() -> bool:
    """子1人(17歳), 義務者給与500万, 権利者給与100万。15-19歳は指数85なので高い。"""
    payload = {
        "kind": "child_support",
        "obligor": {"annual_income": 500_0000, "income_type": "salary"},
        "obligee": {"annual_income": 100_0000, "income_type": "salary"},
        "children": [{"age": 17}],
    }
    r = compute(payload)
    # 15-19歳 → 0-14歳よりも高額、算定表 6-8 万円範囲 (6万〜8万)
    ok = 55_000 <= r["monthly_amount"] <= 85_000
    return _check(
        "06. 養育費 子1人(17歳) → 指数85で増額",
        ok,
        f"月額 {r['monthly_amount']:,} 円",
    )


def test_07_child_support_2children_mixed() -> bool:
    """子2人(5歳・16歳), 義務者給与600万, 権利者0。"""
    payload = {
        "kind": "child_support",
        "obligor": {"annual_income": 600_0000, "income_type": "salary"},
        "obligee": {"annual_income": 0, "income_type": "salary"},
        "children": [{"age": 5}, {"age": 16}],
    }
    r = compute(payload)
    # 指数合計 62+85=147、権利者基礎収入 0 → 義務者が子の標準生活費全額負担
    # 義務者基礎 = 600万 × 0.42 = 252万 (525万ブラケット)
    # 子の生活費 = 252万 × 147/247 = 約149.9万
    # 義務者分担 = 149.9万 × 252/252 = 149.9万
    # 月額 = 149.9万/12 = 約12.5万 → 125,000 円
    ok = 100_000 <= r["monthly_amount"] <= 150_000
    return _check(
        "07. 養育費 子2人(5,16歳) 義務者600万/権利者0",
        ok,
        f"月額 {r['monthly_amount']:,} 円",
    )


def test_08_spousal_support_no_children() -> bool:
    """婚姻費用 子なし, 義務者給与500万, 権利者給与100万。"""
    payload = {
        "kind": "spousal_support",
        "obligor": {"annual_income": 500_0000, "income_type": "salary"},
        "obligee": {"annual_income": 100_0000, "income_type": "salary"},
        "children": [],
    }
    r = compute(payload)
    # 義務者基礎 = 210万, 権利者基礎 = 46万
    # 権利者世帯 = (210+46) × 100/200 = 128万
    # 義務者分担 = 128 - 46 = 82万 / 年
    # 月額 = 82万/12 = 約68,300 → 68,000 円
    ok = 55_000 <= r["monthly_amount"] <= 80_000
    return _check(
        "08. 婚姻費用 子なし 義務者500/権利者100",
        ok,
        f"月額 {r['monthly_amount']:,} 円",
    )


def test_09_spousal_support_1child() -> bool:
    """婚姻費用 子1人(10歳), 義務者給与500万, 権利者給与100万。"""
    payload = {
        "kind": "spousal_support",
        "obligor": {"annual_income": 500_0000, "income_type": "salary"},
        "obligee": {"annual_income": 100_0000, "income_type": "salary"},
        "children": [{"age": 10}],
    }
    r = compute(payload)
    # 算定表（婚姻費用 子1人 0-14）では 8-10 万円/月 範囲
    # 義務者基礎 = 210, 権利者基礎 = 46
    # 権利者世帯 = (210+46) × 162/262 = 256 × 162/262 = 約158.3万
    # 義務者分担 = 158.3 - 46 = 112.3万 / 12 = 約93,583 → 94,000 円
    ok = 70_000 <= r["monthly_amount"] <= 110_000
    return _check(
        "09. 婚姻費用 子1人(10歳) 義務者500/権利者100",
        ok,
        f"月額 {r['monthly_amount']:,} 円",
    )


def test_10_obligee_exceeds_obligor_child_support() -> bool:
    """権利者年収＞義務者年収 (養育費). 義務者分担は少ないか 0 近辺。"""
    payload = {
        "kind": "child_support",
        "obligor": {"annual_income": 200_0000, "income_type": "salary"},
        "obligee": {"annual_income": 500_0000, "income_type": "salary"},
        "children": [{"age": 10}],
    }
    r = compute(payload)
    # 義務者基礎 < 権利者基礎のため、義務者分担は小さくなる
    ok = r["monthly_amount"] < 40_000
    return _check(
        "10. 権利者収入＞義務者の場合 (養育費)",
        ok,
        f"月額 {r['monthly_amount']:,} 円",
    )


def test_11_obligee_exceeds_obligor_spousal_support_no_children() -> bool:
    """婚姻費用で権利者 > 義務者 + 子なし → 0 に丸められる。"""
    payload = {
        "kind": "spousal_support",
        "obligor": {"annual_income": 100_0000, "income_type": "salary"},
        "obligee": {"annual_income": 500_0000, "income_type": "salary"},
        "children": [],
    }
    r = compute(payload)
    ok = r["monthly_amount"] == 0
    return _check("11. 婚姻費用 権利者＞義務者 子なし → 0", ok)


def test_12_business_obligor() -> bool:
    """自営業の義務者: 割合が給与より高い。"""
    payload = {
        "kind": "child_support",
        "obligor": {"annual_income": 500_0000, "income_type": "business"},
        "obligee": {"annual_income": 0, "income_type": "salary"},
        "children": [{"age": 10}],
    }
    r = compute(payload)
    # 自営500万 → 55% = 275万 → 権利者0
    # 子の生活費 = 275万 × 62/162 = 約105.2万
    # 義務者分担 = 105.2万 × 275/275 = 105.2万 / 12 = 約87,700 → 88,000
    ok = 80_000 <= r["monthly_amount"] <= 95_000
    return _check(
        "12. 自営業の義務者 (所得500万)",
        ok,
        f"月額 {r['monthly_amount']:,} 円",
    )


def test_13_validation_invalid_kind() -> bool:
    """kind が不正."""
    try:
        compute({"kind": "foo", "obligor": {"annual_income": 0, "income_type": "salary"},
                 "obligee": {"annual_income": 0, "income_type": "salary"}})
        return _check("13. kind バリデーション", False)
    except ValueError as e:
        return _check("13. kind バリデーション", "kind は" in str(e))


def test_14_validation_no_children_for_child_support() -> bool:
    """養育費で children なし → エラー."""
    try:
        compute({
            "kind": "child_support",
            "obligor": {"annual_income": 500_0000, "income_type": "salary"},
            "obligee": {"annual_income": 0, "income_type": "salary"},
            "children": [],
        })
        return _check("14. 養育費 children 必須", False)
    except ValueError as e:
        return _check("14. 養育費 children 必須", "children が 1 人以上" in str(e))


def test_15_validation_age_out_of_range() -> bool:
    """子の年齢 20 歳以上 → エラー."""
    try:
        compute({
            "kind": "child_support",
            "obligor": {"annual_income": 500_0000, "income_type": "salary"},
            "obligee": {"annual_income": 0, "income_type": "salary"},
            "children": [{"age": 21}],
        })
        return _check("15. 子の年齢 20 以上 拒否", False)
    except ValueError as e:
        return _check("15. 子の年齢 20 以上 拒否", "20 歳以上" in str(e))


def test_16_high_income_warning() -> bool:
    """義務者年収 2500 万円 (算定表範囲超) → 計算はするが警告."""
    payload = {
        "kind": "child_support",
        "obligor": {"annual_income": 2500_0000, "income_type": "salary"},
        "obligee": {"annual_income": 0, "income_type": "salary"},
        "children": [{"age": 10}],
    }
    r = compute(payload)
    ok = r["monthly_amount"] > 0 and any("算定表範囲を超え" in w for w in r["warnings"])
    return _check(
        "16. 高額所得義務者の警告",
        ok,
        f"月額 {r['monthly_amount']:,}, warnings={len(r['warnings'])}",
    )


def test_17_zero_obligor_income() -> bool:
    """義務者年収 0 → 0 だが警告付き."""
    payload = {
        "kind": "child_support",
        "obligor": {"annual_income": 0, "income_type": "salary"},
        "obligee": {"annual_income": 500_0000, "income_type": "salary"},
        "children": [{"age": 10}],
    }
    r = compute(payload)
    ok = r["monthly_amount"] == 0 and any("生活保護" in w for w in r["warnings"])
    return _check("17. 義務者収入 0 の警告", ok)


def test_18_three_children() -> bool:
    """子3人(5, 10, 17歳), 義務者給与700万, 権利者0."""
    payload = {
        "kind": "child_support",
        "obligor": {"annual_income": 700_0000, "income_type": "salary"},
        "obligee": {"annual_income": 0, "income_type": "salary"},
        "children": [{"age": 5}, {"age": 10}, {"age": 17}],
    }
    r = compute(payload)
    # 指数合計 62+62+85=209
    # 義務者基礎 = 700万 × 0.41 = 287万
    # 子の生活費 = 287万 × 209/309 = 約194.1万
    # 月額 = 194.1 / 12 = 16.2万 → 162,000 or so
    ok = 130_000 <= r["monthly_amount"] <= 200_000
    return _check(
        "18. 養育費 子3人(5,10,17歳)",
        ok,
        f"月額 {r['monthly_amount']:,} 円 / 指数合計 {r['breakdown']['child_index_sum']}",
    )


def test_19_spousal_support_2children() -> bool:
    """婚姻費用 子2人(3歳・10歳), 義務者給与600万, 権利者給与200万."""
    payload = {
        "kind": "spousal_support",
        "obligor": {"annual_income": 600_0000, "income_type": "salary"},
        "obligee": {"annual_income": 200_0000, "income_type": "salary"},
        "children": [{"age": 3}, {"age": 10}],
    }
    r = compute(payload)
    # 算定表（婚姻費用 子2人 0-14・0-14）義務者600/権利者200 → 約10-12万円
    # 義務者基礎 = 252, 権利者基礎 = 88
    # 指数 = 62+62=124
    # 権利者世帯 = (252+88) × 224/324 = 340 × 224/324 = 約235.1万
    # 義務者分担 = 235.1 - 88 = 147.1万 / 12 = 約122,500 → 123,000
    ok = 90_000 <= r["monthly_amount"] <= 140_000
    return _check(
        "19. 婚姻費用 子2人(3,10歳) 義務者600/権利者200",
        ok,
        f"月額 {r['monthly_amount']:,} 円",
    )


def test_20_obligor_income_brackets_progression() -> bool:
    """同じ子・同じ権利者収入で義務者年収が上がると月額も増加すること."""
    base_payload = {
        "kind": "child_support",
        "obligee": {"annual_income": 0, "income_type": "salary"},
        "children": [{"age": 10}],
    }
    amounts = []
    for income in [200_0000, 400_0000, 600_0000, 800_0000, 1200_0000]:
        payload = dict(base_payload, obligor={"annual_income": income, "income_type": "salary"})
        r = compute(payload)
        amounts.append(r["monthly_amount"])
    # 単調増加を確認
    ok = all(amounts[i] < amounts[i+1] for i in range(len(amounts)-1))
    return _check(
        "20. 義務者年収上昇で月額が単調増加",
        ok,
        f"年収→月額: {list(zip([200_0000, 400_0000, 600_0000, 800_0000, 1200_0000], amounts))}",
    )


def run_all() -> int:
    print("child-support-calc self-test\n")
    tests = [
        test_01_child_index_table,
        test_02_salary_basic_income_rates,
        test_03_business_basic_income_rates,
        test_04_round_to_1000,
        test_05_child_support_1child_0_14,
        test_06_child_support_1child_15_19,
        test_07_child_support_2children_mixed,
        test_08_spousal_support_no_children,
        test_09_spousal_support_1child,
        test_10_obligee_exceeds_obligor_child_support,
        test_11_obligee_exceeds_obligor_spousal_support_no_children,
        test_12_business_obligor,
        test_13_validation_invalid_kind,
        test_14_validation_no_children_for_child_support,
        test_15_validation_age_out_of_range,
        test_16_high_income_warning,
        test_17_zero_obligor_income,
        test_18_three_children,
        test_19_spousal_support_2children,
        test_20_obligor_income_brackets_progression,
    ]
    passed = sum(1 for t in tests if t())
    total = len(tests)
    print(f"\n結果: {passed} passed, {total - passed} failed / {total} total")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_all())
