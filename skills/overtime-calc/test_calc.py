#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""overtime-calc のユニットテスト."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from calc import compute, _calc_hourly_wage, _calc_monthly_scheduled_hours
from fractions import Fraction


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")
    return cond


def test_01_monthly_scheduled_hours() -> bool:
    """年間休日 120 日、日 8 時間 → 月平均 163.33 時間。"""
    h = _calc_monthly_scheduled_hours(120, Fraction(8))
    # (365 - 120) × 8 / 12 = 245 × 8 / 12 = 1960 / 12 = 約 163.33
    ok = abs(float(h) - 163.33) < 0.5
    return _check("01. 1 ヶ月平均所定労働時間", ok, f"{float(h):.2f}h")


def test_02_hourly_wage() -> bool:
    """月額 260,000 円、月平均 163.33 時間 → 1,593 円/時。"""
    h = Fraction(1960, 12)  # 163.33...
    wage = _calc_hourly_wage(260_000, h)
    # 260_000 / (1960/12) = 260_000 × 12 / 1960 = 3,120,000 / 1960 = 1591.83... → 切り上げ 1592
    ok = wage == 1592 or wage == 1593
    return _check("02. 1 時間あたり賃金 切り上げ", ok, f"{wage:,} 円/時")


def test_03_simple_overtime() -> bool:
    """時間外 30h のみ, 時給 2000 円 → 75,000 円."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},  # 2000 円/時
        "monthly_records": [
            {"year_month": "2024-04", "legal_overtime_h": 30},
        ],
        "options": {"filing_date": "2024-06-01"},
    }
    r = compute(payload)
    # 30 × 2000 × 1.25 = 75,000
    ok = r["summary"]["total_unpaid_within_statute"] == 75_000
    return _check(
        "03. 時間外 30h × 2000 × 1.25 = 75,000",
        ok,
        f"{r['summary']['total_unpaid_within_statute']:,}",
    )


def test_04_over_60_hours() -> bool:
    """時間外 70h（うち 10h が 60h 超） → 通常 60h × 1.25 + 10h × 1.5."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2024-04", "legal_overtime_h": 60, "overtime_over_60_h": 10},
        ],
        "options": {"filing_date": "2024-06-01"},
    }
    r = compute(payload)
    # 60 × 2000 × 1.25 + 10 × 2000 × 1.5 = 150,000 + 30,000 = 180,000
    ok = r["summary"]["total_unpaid_within_statute"] == 180_000
    return _check(
        "04. 60h 超時間外 1.5 倍",
        ok,
        f"{r['summary']['total_unpaid_within_statute']:,}",
    )


def test_05_night_only_surcharge() -> bool:
    """深夜のみ 10h（所定内労働中の深夜） → 0.25 割増のみ."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2024-04", "night_h": 10},
        ],
        "options": {"filing_date": "2024-06-01"},
    }
    r = compute(payload)
    # 10 × 2000 × 0.25 = 5,000
    ok = r["summary"]["total_unpaid_within_statute"] == 5_000
    return _check("05. 深夜単独 10h × 0.25", ok, f"{r['summary']['total_unpaid_within_statute']:,}")


def test_06_overtime_night() -> bool:
    """時間外＋深夜 10h → 1.5 倍."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2024-04", "overtime_night_h": 10},
        ],
        "options": {"filing_date": "2024-06-01"},
    }
    r = compute(payload)
    # 10 × 2000 × 1.5 = 30,000
    ok = r["summary"]["total_unpaid_within_statute"] == 30_000
    return _check("06. 時間外＋深夜 10h × 1.5", ok)


def test_07_holiday_work() -> bool:
    """法定休日 8h × 1.35."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2024-04", "holiday_h": 8},
        ],
        "options": {"filing_date": "2024-06-01"},
    }
    r = compute(payload)
    # 8 × 2000 × 1.35 = 21,600
    ok = r["summary"]["total_unpaid_within_statute"] == 21_600
    return _check("07. 法定休日 8h × 1.35", ok)


def test_08_holiday_night() -> bool:
    """法定休日＋深夜 4h × 1.6."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2024-04", "holiday_night_h": 4},
        ],
        "options": {"filing_date": "2024-06-01"},
    }
    r = compute(payload)
    # 4 × 2000 × 1.6 = 12,800
    ok = r["summary"]["total_unpaid_within_statute"] == 12_800
    return _check("08. 法定休日＋深夜 4h × 1.6", ok)


def test_09_statute_of_limitations_excludes_old() -> bool:
    """時効 3 年超過分は請求不可."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2020-04", "legal_overtime_h": 30},  # 4 年以上前
            {"year_month": "2024-04", "legal_overtime_h": 30},  # 時効内
        ],
        "options": {
            "filing_date": "2024-06-01",
            "statute_years": 3,
        },
    }
    r = compute(payload)
    ok = (
        r["summary"]["total_unpaid_within_statute"] == 75_000
        and r["summary"]["total_unpaid_outside_statute"] == 75_000
    )
    return _check(
        "09. 時効 3 年で古い月を除外",
        ok,
        f"内 {r['summary']['total_unpaid_within_statute']:,}, 外 {r['summary']['total_unpaid_outside_statute']:,}",
    )


def test_10_delay_interest() -> bool:
    """遅延損害金 年 3%."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2024-04", "legal_overtime_h": 30},
        ],
        "options": {
            "filing_date": "2025-04-28",  # 1 年後相当
            "include_delay_interest": True,
        },
    }
    r = compute(payload)
    # 75,000 × 3% × 365/365 = 2,250
    delay = r["summary"]["delay_interest"]
    ok = 2_100 <= delay <= 2_400
    return _check("10. 遅延損害金 年 3%", ok, f"{delay:,}")


def test_11_annual_holidays_input() -> bool:
    """annual_holidays + daily_scheduled_hours から月平均を計算."""
    payload = {
        "employee": {"monthly_salary": 240_000},
        "work_hours": {"annual_holidays": 120, "daily_scheduled_hours": 8},
        "monthly_records": [
            {"year_month": "2024-04", "legal_overtime_h": 10},
        ],
        "options": {"filing_date": "2024-06-01"},
    }
    r = compute(payload)
    # 月平均 ≈ 163.33、時給 ≈ 1,470（切り上げ）、10 × 1,470 × 1.25 = 18,375
    amount = r["summary"]["total_unpaid_within_statute"]
    ok = 17_500 <= amount <= 19_000
    return _check("11. 年間休日から計算", ok, f"{amount:,}")


def test_12_validation_no_records() -> bool:
    try:
        compute({
            "employee": {"monthly_salary": 300_000},
            "work_hours": {"monthly_scheduled_hours": 150},
            "monthly_records": [],
        })
        return _check("12. 空 monthly_records 拒否", False)
    except ValueError:
        return _check("12. 空 monthly_records 拒否", True)


def test_13_validation_negative_salary() -> bool:
    try:
        compute({
            "employee": {"monthly_salary": -100},
            "work_hours": {"monthly_scheduled_hours": 150},
            "monthly_records": [{"year_month": "2024-04", "legal_overtime_h": 0}],
        })
        return _check("13. 負の月額賃金 拒否", False)
    except ValueError:
        return _check("13. 負の月額賃金 拒否", True)


def test_14_validation_negative_hours() -> bool:
    try:
        compute({
            "employee": {"monthly_salary": 300_000},
            "work_hours": {"monthly_scheduled_hours": 150},
            "monthly_records": [{"year_month": "2024-04", "legal_overtime_h": -5}],
        })
        return _check("14. 負の時間数 拒否", False)
    except ValueError:
        return _check("14. 負の時間数 拒否", True)


def test_15_multi_month_aggregation() -> bool:
    """複数月の合算."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2024-01", "legal_overtime_h": 20},
            {"year_month": "2024-02", "legal_overtime_h": 25},
            {"year_month": "2024-03", "legal_overtime_h": 30},
        ],
        "options": {"filing_date": "2024-06-01"},
    }
    r = compute(payload)
    # 20×2000×1.25 + 25×2000×1.25 + 30×2000×1.25 = 50,000 + 62,500 + 75,000 = 187,500
    ok = r["summary"]["total_unpaid_within_statute"] == 187_500
    return _check("15. 複数月合算", ok, f"{r['summary']['total_unpaid_within_statute']:,}")


def test_16_statute_2_years_legacy() -> bool:
    """改正前事案の時効 2 年."""
    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2019-04", "legal_overtime_h": 30},  # 5 年前
            {"year_month": "2020-06", "legal_overtime_h": 30},  # 2 年超
            {"year_month": "2023-05", "legal_overtime_h": 30},  # 1 年以内
        ],
        "options": {
            "filing_date": "2024-06-01",
            "statute_years": 2,
        },
    }
    r = compute(payload)
    # 2022/06 以降が時効内
    ok = r["summary"]["total_unpaid_within_statute"] == 75_000
    return _check("16. 改正前の時効 2 年", ok)


def run_all() -> int:
    print("overtime-calc self-test\n")
    tests = [
        test_01_monthly_scheduled_hours,
        test_02_hourly_wage,
        test_03_simple_overtime,
        test_04_over_60_hours,
        test_05_night_only_surcharge,
        test_06_overtime_night,
        test_07_holiday_work,
        test_08_holiday_night,
        test_09_statute_of_limitations_excludes_old,
        test_10_delay_interest,
        test_11_annual_holidays_input,
        test_12_validation_no_records,
        test_13_validation_negative_salary,
        test_14_validation_negative_hours,
        test_15_multi_month_aggregation,
        test_16_statute_2_years_legacy,
    ]
    passed = sum(1 for t in tests if t())
    total = len(tests)
    print(f"\n結果: {passed} passed, {total - passed} failed / {total} total")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_all())
