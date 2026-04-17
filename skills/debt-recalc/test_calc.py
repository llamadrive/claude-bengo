#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debt-recalc のユニットテスト。

代表的な引き直しパターンを検証する。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from calc import recalculate, _rate_for_principal


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")
    return cond


def test_01_rate_brackets() -> bool:
    """上限利率のブラケット判定。"""
    from fractions import Fraction
    ok = (
        _rate_for_principal(0) == Fraction(20, 100)
        and _rate_for_principal(50_000) == Fraction(20, 100)
        and _rate_for_principal(99_999) == Fraction(20, 100)
        and _rate_for_principal(100_000) == Fraction(18, 100)
        and _rate_for_principal(500_000) == Fraction(18, 100)
        and _rate_for_principal(999_999) == Fraction(18, 100)
        and _rate_for_principal(1_000_000) == Fraction(15, 100)
        and _rate_for_principal(10_000_000) == Fraction(15, 100)
    )
    return _check(
        "01. 利息制限法の上限利率ブラケット",
        ok,
        "10万未満=20%, 10万-100万=18%, 100万以上=15%",
    )


def test_02_simple_loan_no_payment() -> bool:
    """1 回借入・1 回弁済（ぴったり完済）."""
    payload = {
        "transactions": [
            {"date": "2020-01-01", "type": "borrowing", "amount": 500_000},
            {"date": "2020-01-01", "type": "payment", "amount": 500_000},
        ],
    }
    r = recalculate(payload)
    ok = (
        r["summary"]["remaining_principal"] == 0
        and r["summary"]["overpayment_principal"] == 0
    )
    return _check("02. 同日借入＋完済 → 残 0", ok)


def test_03_simple_interest_one_year() -> bool:
    """50 万円 1 年後に一括返済 → 残高 18% 分の利息."""
    payload = {
        "transactions": [
            {"date": "2020-01-01", "type": "borrowing", "amount": 500_000},
            {"date": "2021-01-01", "type": "payment", "amount": 500_000},
        ],
    }
    r = recalculate(payload)
    # 50万 × 18% × 366/365 = 約 90,246 円の利息が発生
    # 50万 弁済 → 利息90,246 が充当され、残り409,754 が元本へ
    # 残元本 = 500,000 - 409,754 = 90,246 円
    remaining = r["summary"]["remaining_principal"]
    expected_range = (88_000, 92_000)
    ok = expected_range[0] <= remaining <= expected_range[1]
    return _check(
        "03. 50万 1 年後に 50万 弁済 → 残元本 ≈ 9万",
        ok,
        f"残 {remaining:,} 円",
    )


def test_04_overpayment_scenario() -> bool:
    """長期にわたる返済で過払金発生.

    借入 50 万 → 毎月 2 万円返済 × 60ヶ月 → 総返済 120 万
    引き直し利率 18% で計算すると元本はとっくに完済 → 過払金発生
    """
    import datetime as _dt
    txs = [{"date": "2015-01-15", "type": "borrowing", "amount": 500_000}]
    # 2015/02 〜 2019/12 まで毎月 15 日に 2 万円返済
    start = _dt.date(2015, 2, 15)
    for m in range(60):
        year = start.year + (start.month - 1 + m) // 12
        month = (start.month - 1 + m) % 12 + 1
        txs.append({"date": f"{year}-{month:02d}-15", "type": "payment", "amount": 20_000})

    r = recalculate({"transactions": txs})
    over = r["summary"]["overpayment_principal"]
    ok = over > 0
    return _check(
        "04. 長期返済で過払金発生",
        ok,
        f"過払金元本 {over:,} 円",
    )


def test_05_validation_empty_transactions() -> bool:
    try:
        recalculate({"transactions": []})
        return _check("05. 空 transactions 拒否", False)
    except ValueError:
        return _check("05. 空 transactions 拒否", True)


def test_06_validation_bad_type() -> bool:
    try:
        recalculate({
            "transactions": [
                {"date": "2020-01-01", "type": "repay", "amount": 10000},
            ]
        })
        return _check("06. 不正 type 拒否", False)
    except ValueError:
        return _check("06. 不正 type 拒否", True)


def test_07_validation_bad_amount() -> bool:
    try:
        recalculate({
            "transactions": [
                {"date": "2020-01-01", "type": "borrowing", "amount": -1000},
            ]
        })
        return _check("07. 負の amount 拒否", False)
    except ValueError:
        return _check("07. 負の amount 拒否", True)


def test_08_validation_bad_date() -> bool:
    try:
        recalculate({
            "transactions": [
                {"date": "2020/01/01", "type": "borrowing", "amount": 10000},
            ]
        })
        return _check("08. 不正な日付形式 拒否", False)
    except ValueError:
        return _check("08. 不正な日付形式 拒否", True)


def test_09_bracket_transition() -> bool:
    """元本が 100 万を跨いだ場合、期間ごとに利率が変わる.

    100 万以上は 15%。本テストは 100 万以上の借入で利率 15% が使われることを確認。
    """
    payload = {
        "transactions": [
            {"date": "2020-01-01", "type": "borrowing", "amount": 2_000_000},
            {"date": "2021-01-01", "type": "payment", "amount": 200_000},
        ],
    }
    r = recalculate(payload)
    # 200 万 × 15% × 366/365 = 約 300,822 円
    # 200,000 弁済のうち全額が利息に充当 → 元本 200 万残
    remaining = r["summary"]["remaining_principal"]
    # 未払利息 = 約 100,822 円
    accrued = r["summary"]["remaining_accrued_interest"]
    ok = remaining == 2_000_000 and 98_000 <= accrued <= 103_000
    return _check(
        "09. 100 万超は 15% 利率で計算",
        ok,
        f"残元本 {remaining:,}、未払利息 {accrued:,}",
    )


def test_10_multiple_borrowings_and_payments() -> bool:
    """借入・弁済が入り混じるケース."""
    payload = {
        "transactions": [
            {"date": "2020-01-01", "type": "borrowing", "amount": 300_000},
            {"date": "2020-03-01", "type": "payment", "amount": 50_000},
            {"date": "2020-06-01", "type": "borrowing", "amount": 100_000},
            {"date": "2020-09-01", "type": "payment", "amount": 50_000},
            {"date": "2021-01-01", "type": "payment", "amount": 100_000},
        ],
    }
    r = recalculate(payload)
    # 最終残高が 0 以上でかつ ledger が全件含まれている
    ok = (
        len(r["ledger"]) == 5
        and r["summary"]["remaining_principal"] > 0  # 完済していない
    )
    return _check(
        "10. 借入・弁済の混合",
        ok,
        f"残 {r['summary']['remaining_principal']:,}、ledger {len(r['ledger'])} 件",
    )


def test_11_ledger_structure() -> bool:
    """ledger エントリに必要なフィールドが揃っている."""
    payload = {
        "transactions": [
            {"date": "2020-01-01", "type": "borrowing", "amount": 100_000},
            {"date": "2020-02-01", "type": "payment", "amount": 10_000},
        ],
    }
    r = recalculate(payload)
    entry = r["ledger"][1]
    required = {"date", "type", "amount", "days_since_last", "rate_applied",
                "interest_accrued_this_period", "balance_after",
                "accrued_interest_after"}
    ok = required.issubset(set(entry.keys()))
    return _check("11. ledger エントリの構造", ok, f"keys={sorted(entry.keys())}")


def test_12_overpayment_interest_accumulates() -> bool:
    """過払金発生後、利息が年 5% 付く."""
    import datetime as _dt
    txs = [{"date": "2010-01-01", "type": "borrowing", "amount": 300_000}]
    # 短期間で過剰返済して過払金を作る
    txs.append({"date": "2010-02-01", "type": "payment", "amount": 350_000})
    # 過払金発生後、1 年間放置してから最終取引
    txs.append({"date": "2011-02-01", "type": "payment", "amount": 1000})
    r = recalculate(txs := {"transactions": txs})
    over_p = r["summary"]["overpayment_principal"]
    over_i = r["summary"]["overpayment_interest_5pct"]
    ok = over_p > 0 and over_i > 0
    return _check(
        "12. 過払金 + 年 5% 利息",
        ok,
        f"元本 {over_p:,}、利息 {over_i:,}",
    )


def test_13_same_day_ordering() -> bool:
    """同一日付の借入→弁済の順序が正しく処理される."""
    payload = {
        "transactions": [
            # 入力順を逆にしても正規化で 借入→弁済 になるはず
            {"date": "2020-01-01", "type": "payment", "amount": 10_000},
            {"date": "2020-01-01", "type": "borrowing", "amount": 50_000},
        ],
    }
    r = recalculate(payload)
    # 借入 5万 → 弁済 1万 → 残 4万
    ok = r["summary"]["remaining_principal"] == 40_000
    return _check("13. 同日取引は借入→弁済の順", ok)


def test_14_zero_days_no_interest() -> bool:
    """同一日の借入・弁済は利息発生なし."""
    payload = {
        "transactions": [
            {"date": "2020-01-01", "type": "borrowing", "amount": 500_000},
            {"date": "2020-01-01", "type": "payment", "amount": 100_000},
        ],
    }
    r = recalculate(payload)
    # 利息が 0 の状態で弁済が元本を直接減らす
    ok = (
        r["summary"]["remaining_principal"] == 400_000
        and r["summary"]["total_interest_paid_under_risokuhou"] == 0
    )
    return _check("14. 同日取引で利息 0", ok)


def test_15_partial_interest_payment() -> bool:
    """弁済額が利息に満たないケース: 利息充当のみ、元本は減らない."""
    import datetime as _dt
    payload = {
        "transactions": [
            {"date": "2020-01-01", "type": "borrowing", "amount": 500_000},
            # 1 ヶ月後、少額返済
            {"date": "2020-02-01", "type": "payment", "amount": 5_000},
        ],
    }
    r = recalculate(payload)
    # 50万 × 18% × 31/365 = 約 7,644 円の利息
    # 5,000 円弁済 → 全額利息へ → 元本 50万 のまま
    # 未払利息 残 ≈ 2,644 円
    ok = (
        r["summary"]["remaining_principal"] == 500_000
        and 2_000 <= r["summary"]["remaining_accrued_interest"] <= 3_000
    )
    return _check(
        "15. 弁済が利息未満 → 元本維持",
        ok,
        f"残元本 {r['summary']['remaining_principal']:,}、利息 {r['summary']['remaining_accrued_interest']:,}",
    )


def run_all() -> int:
    print("debt-recalc self-test\n")
    tests = [
        test_01_rate_brackets,
        test_02_simple_loan_no_payment,
        test_03_simple_interest_one_year,
        test_04_overpayment_scenario,
        test_05_validation_empty_transactions,
        test_06_validation_bad_type,
        test_07_validation_bad_amount,
        test_08_validation_bad_date,
        test_09_bracket_transition,
        test_10_multiple_borrowings_and_payments,
        test_11_ledger_structure,
        test_12_overpayment_interest_accumulates,
        test_13_same_day_ordering,
        test_14_zero_days_no_interest,
        test_15_partial_interest_payment,
    ]
    passed = sum(1 for t in tests if t())
    total = len(tests)
    print(f"\n結果: {passed} passed, {total - passed} failed / {total} total")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_all())
