#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""traffic-damage-calc のユニットテスト。

実務で典型的なケースを中心に、計算結果が赤い本に整合することを検証する。
pytest 非依存（stdlib のみ）で self-test ランナー形式。

各ケースには赤い本の該当ページや実務計算例を脚注として記載する。
"""

from __future__ import annotations

import sys
from pathlib import Path
from fractions import Fraction

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from calc import (
    compute_damages,
    _leibniz_coefficient,
    _months_from_days,
    _rate_for_accident_date,
    DISABILITY_LOSS_RATES,
    DISABILITY_CONSOLATION,
    LEGAL_INTEREST_RATE,
    LEGAL_INTEREST_RATE_POST_2020,
    LEGAL_INTEREST_RATE_PRE_2020,
)


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")
    return cond


def test_01_leibniz_coefficient() -> bool:
    """Leibniz 係数の既知値テスト（年利 3%）。"""
    # 1 年: 1 / 1.03 ≈ 0.9708...
    # 5 年: 4.5797...
    # 10 年: 8.5302...
    # 20 年: 14.8775...
    # 30 年: 19.6004...
    ok = True
    cases = [
        (1, 0.9708, 0.9709),
        (5, 4.5796, 4.5798),
        (10, 8.5301, 8.5303),
        (20, 14.8774, 14.8776),
        (30, 19.6003, 19.6005),
    ]
    for years, lo, hi in cases:
        v = float(_leibniz_coefficient(years))
        if not lo <= v <= hi:
            ok = False
            print(f"    FAIL: Leibniz({years}) = {v:.4f}, expected {lo}-{hi}")
    return _check("01. Leibniz 係数（年3%）", ok, "1/5/10/20/30 年の既知値に整合")


def test_02_months_from_days() -> bool:
    ok = (
        _months_from_days(0) == 0
        and _months_from_days(1) == 1
        and _months_from_days(30) == 1
        and _months_from_days(31) == 2
        and _months_from_days(60) == 2
        and _months_from_days(61) == 3
    )
    return _check("02. 日数→月数の切り上げ", ok)


def test_03_minor_whiplash() -> bool:
    """軽症むち打ち: 通院3ヶ月, 入院なし, 過失0%."""
    payload = {
        "victim": {
            "name": "甲野太郎", "age_at_accident": 35, "gender": "male",
            "occupation_type": "salaried", "annual_income": 5_000_000,
            "is_household_supporter": True,
        },
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {
            "hospital_days": 0, "outpatient_days": 90,
            "medical_fees": 300_000, "transportation": 20_000,
            "severity": "minor",
        },
    }
    r = compute_damages(payload)
    hosp = r["breakdown"]["hospitalization_consolation"]
    # 別表 II, 通院3月・入院0月 = 53 万円
    ok_consol = hosp["total"] == 530_000
    ok_table = "別表 II" in hosp["table"]
    return _check(
        "03. 軽症むち打ち 通院3月",
        ok_consol and ok_table,
        f"慰謝料 {hosp['total']:,} 円（期待: 530,000 円、別表 II）",
    )


def test_04_moderate_injury_with_table_I() -> bool:
    """中等症: 通院6月・入院1月, 骨折あり(別表I)."""
    payload = {
        "victim": {
            "name": "甲野太郎", "age_at_accident": 35, "gender": "male",
            "occupation_type": "salaried", "annual_income": 5_000_000,
            "is_household_supporter": True,
        },
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {
            "hospital_days": 30, "outpatient_days": 180,
            "severity": "major",
        },
    }
    r = compute_damages(payload)
    hosp = r["breakdown"]["hospitalization_consolation"]
    # 別表 I, 入院1月・通院6月 = 149 万円
    ok = hosp["total"] == 1_490_000 and "別表 I" in hosp["table"]
    return _check(
        "04. 中等症 入院1月+通院6月（別表 I）",
        ok,
        f"慰謝料 {hosp['total']:,} 円（期待: 1,490,000 円）",
    )


def test_05_14kyu_disability() -> bool:
    """14 級後遺障害: 年収 500万、35歳、5%労働能力喪失、32年稼働."""
    payload = {
        "victim": {
            "name": "甲野太郎", "age_at_accident": 35, "gender": "male",
            "occupation_type": "salaried", "annual_income": 5_000_000,
            "is_household_supporter": True,
        },
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {
            "hospital_days": 0, "outpatient_days": 180,
            "severity": "minor",
        },
        "disability": {"grade": 14, "years_until_67": 32},
    }
    r = compute_damages(payload)
    dis = r["breakdown"]["future_earnings_loss"]
    # 500万 × 0.05 × Leibniz(32) ≈ 500万 × 0.05 × 20.3888 = 5,097,210 円前後
    # 詳細値は Fraction 計算で約 5,097,205 円
    expected_low = 5_090_000
    expected_high = 5_110_000
    ok = expected_low <= dis["total"] <= expected_high
    disability_consol = r["breakdown"]["disability_consolation"]["total"]
    ok_consol = disability_consol == DISABILITY_CONSOLATION[14]  # 110万
    return _check(
        "05. 14級9号 後遺障害（むち打ち+神経症状）",
        ok and ok_consol,
        f"逸失利益 {dis['total']:,} 円（範囲 {expected_low:,}-{expected_high:,}）、慰謝料 {disability_consol:,}",
    )


def test_06_12kyu_disability() -> bool:
    """12 級: 年収 500 万、35 歳、14%労働能力喪失、32 年稼働."""
    payload = {
        "victim": {
            "name": "甲野太郎", "age_at_accident": 35, "gender": "male",
            "occupation_type": "salaried", "annual_income": 5_000_000,
            "is_household_supporter": True,
        },
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {"hospital_days": 30, "outpatient_days": 180, "severity": "major"},
        "disability": {"grade": 12, "years_until_67": 32},
    }
    r = compute_damages(payload)
    dis = r["breakdown"]["future_earnings_loss"]
    # 500 万 × 0.14 × 20.3888 ≈ 14,272,160 円前後
    expected_low = 14_250_000
    expected_high = 14_300_000
    ok = expected_low <= dis["total"] <= expected_high
    consol = r["breakdown"]["disability_consolation"]["total"]
    ok_consol = consol == 2_900_000  # 12 級 = 290 万
    return _check(
        "06. 12級13号 後遺障害",
        ok and ok_consol,
        f"逸失利益 {dis['total']:,}、慰謝料 {consol:,}",
    )


def test_07_housewife_lost_wages() -> bool:
    """主婦の休業損害: 賃金センサス女性平均を使用."""
    payload = {
        "victim": {
            "name": "甲野花子", "age_at_accident": 40, "gender": "female",
            "occupation_type": "household", "annual_income": 0,
            "is_household_supporter": False,
        },
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {"hospital_days": 0, "outpatient_days": 60, "severity": "minor"},
        "lost_wages": {"days_off_work": 60},
    }
    r = compute_damages(payload)
    lw = r["breakdown"]["lost_wages"]
    # 賃金センサス 399 万 / 365 ≈ 10,931 円/日 × 60 日 ≈ 655,860
    expected_daily_low = 10_900
    expected_daily_high = 10_960
    ok_daily = expected_daily_low <= lw["daily_wage"] <= expected_daily_high
    ok_total = lw["total"] == lw["daily_wage"] * 60
    return _check(
        "07. 主婦の休業損害（賃金センサス基準）",
        ok_daily and ok_total,
        f"日額 {lw['daily_wage']:,}、総額 {lw['total']:,}",
    )


def test_08_fault_reduction() -> bool:
    """過失相殺 20%: 慰謝料 200万の場合 160万。"""
    payload = {
        "victim": {
            "name": "甲野太郎", "age_at_accident": 35, "gender": "male",
            "occupation_type": "salaried", "annual_income": 5_000_000,
            "is_household_supporter": True,
        },
        "accident": {"date": "2024-04-01", "victim_fault_percent": 20},
        "medical": {"hospital_days": 30, "outpatient_days": 120, "severity": "major"},
    }
    r = compute_damages(payload)
    subtotal = r["summary"]["subtotal_before_fault"]
    after = r["summary"]["after_fault_reduction"]
    # after = subtotal × 0.8
    expected = int(subtotal * 0.8 + 0.5)
    ok = abs(after - expected) <= 2  # rounding tolerance
    return _check(
        "08. 過失相殺 20%",
        ok,
        f"subtotal {subtotal:,} → after {after:,}（期待 {expected:,}）",
    )


def test_09_lawyer_fee() -> bool:
    """弁護士費用は過失相殺後の 10%。"""
    payload = {
        "victim": {
            "name": "甲野太郎", "age_at_accident": 35, "gender": "male",
            "occupation_type": "salaried", "annual_income": 5_000_000,
            "is_household_supporter": True,
        },
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {"hospital_days": 30, "outpatient_days": 120, "severity": "major"},
    }
    r = compute_damages(payload)
    after = r["summary"]["after_fault_reduction"]
    fee = r["summary"]["lawyer_fee"]
    expected_fee = int(after * 0.1 + 0.5)
    return _check(
        "09. 弁護士費用 10%",
        abs(fee - expected_fee) <= 2,
        f"{after:,} × 10% = {fee:,}（期待 {expected_fee:,}）",
    )


def test_10_death_case() -> bool:
    """死亡事案: 家計支持者男性 40 歳、年収 600 万、子 2 人。"""
    payload = {
        "victim": {
            "name": "甲野太郎", "age_at_accident": 40, "gender": "male",
            "occupation_type": "salaried", "annual_income": 6_000_000,
            "is_household_supporter": True,
        },
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {"hospital_days": 0, "outpatient_days": 0, "severity": "major"},
        "death": {"dependent_count": 2},
    }
    r = compute_damages(payload)
    loss = r["breakdown"]["death_earnings_loss"]
    consol = r["breakdown"]["death_consolation"]
    # 600 万 × (1 - 0.3) × Leibniz(27) ≈ 600 万 × 0.7 × 18.3270 ≈ 76,973,400
    expected_low = 76_900_000
    expected_high = 77_100_000
    ok_loss = expected_low <= loss["total"] <= expected_high
    ok_consol = consol["total"] == 28_000_000  # 家計支持者
    return _check(
        "10. 死亡事案 家計支持者男性40歳 子2人",
        ok_loss and ok_consol,
        f"逸失利益 {loss['total']:,}、慰謝料 {consol['total']:,}",
    )


def test_11_invalid_age() -> bool:
    """年齢 -5 はバリデーションエラー。"""
    payload = {
        "victim": {"name": "x", "age_at_accident": -5, "gender": "male",
                   "occupation_type": "salaried"},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
    }
    try:
        compute_damages(payload)
        return _check("11. 負の年齢を拒否", False, "拒否されなかった")
    except ValueError as e:
        return _check("11. 負の年齢を拒否", "age_at_accident" in str(e), str(e)[:100])


def test_12_invalid_fault() -> bool:
    """過失 120% はバリデーションエラー。"""
    payload = {
        "victim": {"name": "x", "age_at_accident": 30, "gender": "male",
                   "occupation_type": "salaried"},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 120},
    }
    try:
        compute_damages(payload)
        return _check("12. 過失 120% を拒否", False)
    except ValueError:
        return _check("12. 過失 120% を拒否", True)


def test_13_invalid_disability_grade() -> bool:
    """等級 15 はバリデーションエラー。"""
    payload = {
        "victim": {"name": "x", "age_at_accident": 30, "gender": "male",
                   "occupation_type": "salaried"},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "disability": {"grade": 15},
    }
    try:
        compute_damages(payload)
        return _check("13. 等級 15 を拒否", False)
    except ValueError:
        return _check("13. 等級 15 を拒否", True)


def test_14_positive_damages_total() -> bool:
    """積極損害の加算: 治療費+交通費+装具+入院雑費+付添看護."""
    payload = {
        "victim": {"name": "x", "age_at_accident": 30, "gender": "male",
                   "occupation_type": "salaried", "annual_income": 5_000_000,
                   "is_household_supporter": False},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {
            "hospital_days": 10, "outpatient_days": 30,
            "medical_fees": 500_000, "transportation": 30_000, "equipment": 50_000,
            "nursing_days_hospital": 5, "nursing_days_outpatient": 10,
            "severity": "major",
        },
    }
    r = compute_damages(payload)
    pos = r["breakdown"]["positive_damages"]
    # 医療費 500,000 + 交通費 30,000 + 装具 50,000
    # + 入院雑費 10日 × 1500 = 15,000
    # + 付添看護 入院 5×6500=32,500 + 通院 10×3300=33,000
    expected = 500_000 + 30_000 + 50_000 + 15_000 + 32_500 + 33_000
    return _check(
        "14. 積極損害の全項目加算",
        pos["total"] == expected,
        f"合計 {pos['total']:,}（期待 {expected:,}）",
    )


def test_15_delay_interest() -> bool:
    """遅延損害金: 年率 3% × 日数。"""
    payload = {
        "victim": {"name": "x", "age_at_accident": 30, "gender": "male",
                   "occupation_type": "salaried", "annual_income": 5_000_000,
                   "is_household_supporter": False},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {"hospital_days": 0, "outpatient_days": 90, "severity": "major"},
        "options": {
            "include_lawyer_fee": False,
            "include_delay_interest": True,
            "settlement_date": "2025-04-01",  # 365 日後
        },
    }
    r = compute_damages(payload)
    after = r["summary"]["after_fault_reduction"]
    delay = r["summary"]["delay_interest"]
    # 1 年間で 3% ちょうど
    expected = int(after * 0.03 + 0.5)
    ok = abs(delay - expected) <= 2
    return _check(
        "15. 遅延損害金 年3% × 365日",
        ok,
        f"{after:,} × 3% = {delay:,}（期待 {expected:,}）",
    )


def test_16_grade_loss_rate_table_completeness() -> bool:
    """1-14 級の労働能力喪失率テーブルが完備."""
    ok = all(g in DISABILITY_LOSS_RATES for g in range(1, 15))
    ok_values = (
        DISABILITY_LOSS_RATES[1] == Fraction(1)
        and DISABILITY_LOSS_RATES[14] == Fraction(5, 100)
        and DISABILITY_LOSS_RATES[12] == Fraction(14, 100)
    )
    return _check(
        "16. 等級 1-14 の喪失率テーブル完備",
        ok and ok_values,
        f"1級=100%, 12級=14%, 14級=5%",
    )


def test_17_self_employed_lost_wages() -> bool:
    """自営業者: annual_income / 365 を日額に使用."""
    payload = {
        "victim": {"name": "x", "age_at_accident": 40, "gender": "male",
                   "occupation_type": "self_employed", "annual_income": 3_650_000,
                   "is_household_supporter": True},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {"hospital_days": 0, "outpatient_days": 60, "severity": "minor"},
        "lost_wages": {"days_off_work": 30},
    }
    r = compute_damages(payload)
    lw = r["breakdown"]["lost_wages"]
    # 3,650,000 / 365 = 10,000 円/日
    ok = lw["daily_wage"] == 10_000 and lw["total"] == 300_000
    return _check("17. 自営業の日額計算", ok, f"日額 {lw['daily_wage']:,}、総額 {lw['total']:,}")


def test_18_no_disability_no_death() -> bool:
    """後遺障害・死亡なしの単純ケース: 慰謝料は入通院のみ."""
    payload = {
        "victim": {"name": "x", "age_at_accident": 30, "gender": "male",
                   "occupation_type": "salaried", "annual_income": 5_000_000,
                   "is_household_supporter": False},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {"hospital_days": 0, "outpatient_days": 60, "severity": "minor"},
    }
    r = compute_damages(payload)
    b = r["breakdown"]
    ok = (
        b["future_earnings_loss"]["total"] == 0
        and b["death_earnings_loss"]["total"] == 0
        and b["disability_consolation"]["total"] == 0
        and b["death_consolation"]["total"] == 0
    )
    return _check("18. 後遺障害・死亡なしの単純ケース", ok)


def test_19_severity_required() -> bool:
    """severity は必須。未指定時は ValueError（silent-default で軽傷を別表 I にしないため）."""
    payload = {
        "victim": {"name": "x", "age_at_accident": 30, "gender": "male",
                   "occupation_type": "salaried", "annual_income": 5_000_000,
                   "is_household_supporter": False},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {"hospital_days": 0, "outpatient_days": 60},  # severity 省略
    }
    try:
        compute_damages(payload)
        return _check("19. severity 未指定は ValueError", False, "拒否されなかった")
    except ValueError as e:
        return _check("19. severity 未指定は ValueError", "severity" in str(e), str(e)[:80])


def test_21_pre_2020_interest_rate() -> bool:
    """F-001: 事故日 2020/03/31 以前は年 5% を使う（改正前 民法 404 条）."""
    pre = _rate_for_accident_date("2020-03-31")
    post = _rate_for_accident_date("2020-04-01")
    on_change = _rate_for_accident_date("2020-04-01")
    ok = pre == LEGAL_INTEREST_RATE_PRE_2020 and post == LEGAL_INTEREST_RATE_POST_2020 and on_change == Fraction(3, 100)
    return _check(
        "21. 2020/04/01 境界で利率 5%↔3% を切替",
        ok,
        f"pre={float(pre):.2%}, post={float(post):.2%}",
    )


def test_22_pre_2020_inflates_future_loss() -> bool:
    """F-001: 事故日 2019 の逸失利益は 2024 より少額（5% 割引で現在価値が下がる）."""
    base = {
        "victim": {"name": "x", "age_at_accident": 35, "gender": "male",
                   "occupation_type": "salaried", "annual_income": 5_000_000,
                   "is_household_supporter": True},
        "medical": {"hospital_days": 0, "outpatient_days": 180, "severity": "minor"},
        "disability": {"grade": 12, "years_until_67": 32},
    }
    p_old = dict(base, accident={"date": "2019-01-01", "victim_fault_percent": 0})
    p_new = dict(base, accident={"date": "2024-04-01", "victim_fault_percent": 0})
    r_old = compute_damages(p_old)["breakdown"]["future_earnings_loss"]["total"]
    r_new = compute_damages(p_new)["breakdown"]["future_earnings_loss"]["total"]
    # 5% 割引は現在価値を約 25-30% 下げる
    ok = r_old < r_new and (r_new - r_old) > r_new * 0.2
    return _check(
        "22. 2019 事故は 2024 事故より Leibniz 現在価値が小さい（5%→3%）",
        ok,
        f"2019: {r_old:,}, 2024: {r_new:,}, delta: {r_new - r_old:,}",
    )


def test_23_fault_precision_fraction() -> bool:
    """F-005: 過失 1.13% が Fraction(str()) で正確に反映される."""
    payload_zero = {
        "victim": {"name": "x", "age_at_accident": 35, "gender": "male",
                   "occupation_type": "salaried", "annual_income": 5_000_000,
                   "is_household_supporter": True},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 0},
        "medical": {"hospital_days": 0, "outpatient_days": 60, "severity": "major"},
    }
    payload_fault = dict(payload_zero)
    payload_fault["accident"] = {"date": "2024-04-01", "victim_fault_percent": 1.13}
    sub = compute_damages(payload_zero)["summary"]["after_fault_reduction"]
    after = compute_damages(payload_fault)["summary"]["after_fault_reduction"]
    # expected reduction: subtotal * 0.0113 exact
    expected_reduction = int(sub * 113 / 10000 + 0.5)
    actual_reduction = sub - after
    # 旧実装 Fraction(int(1.13*100), 10000) は float で 112 → 誤差が出る
    ok = abs(actual_reduction - expected_reduction) <= 1
    return _check(
        "23. 過失 1.13% の Fraction 精度",
        ok,
        f"expected_reduction={expected_reduction}, actual={actual_reduction}",
    )


def test_20_high_fault_70pct() -> bool:
    """過失 70% で大幅減額."""
    payload = {
        "victim": {"name": "x", "age_at_accident": 30, "gender": "male",
                   "occupation_type": "salaried", "annual_income": 5_000_000,
                   "is_household_supporter": False},
        "accident": {"date": "2024-04-01", "victim_fault_percent": 70},
        "medical": {"hospital_days": 30, "outpatient_days": 120, "severity": "major"},
    }
    r = compute_damages(payload)
    subtotal = r["summary"]["subtotal_before_fault"]
    after = r["summary"]["after_fault_reduction"]
    expected = int(subtotal * 0.3 + 0.5)  # 30% が残る
    ok = abs(after - expected) <= 2
    return _check(
        "20. 過失 70% 減額",
        ok,
        f"subtotal {subtotal:,} → after {after:,}（期待 {expected:,}）",
    )


def run_all() -> int:
    print("traffic-damage-calc self-test\n")
    tests = [
        test_01_leibniz_coefficient,
        test_02_months_from_days,
        test_03_minor_whiplash,
        test_04_moderate_injury_with_table_I,
        test_05_14kyu_disability,
        test_06_12kyu_disability,
        test_07_housewife_lost_wages,
        test_08_fault_reduction,
        test_09_lawyer_fee,
        test_10_death_case,
        test_11_invalid_age,
        test_12_invalid_fault,
        test_13_invalid_disability_grade,
        test_14_positive_damages_total,
        test_15_delay_interest,
        test_16_grade_loss_rate_table_completeness,
        test_17_self_employed_lost_wages,
        test_18_no_disability_no_death,
        test_19_severity_required,
        test_20_high_fault_70pct,
        test_21_pre_2020_interest_rate,
        test_22_pre_2020_inflates_future_loss,
        test_23_fault_precision_fraction,
    ]
    passed = 0
    for t in tests:
        if t():
            passed += 1
    total = len(tests)
    print(f"\n結果: {passed} passed, {total - passed} failed / {total} total")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_all())
