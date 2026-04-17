#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""property-division-calc のユニットテスト."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from calc import compute


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")
    return cond


def test_01_equal_split_husband_owns_all() -> bool:
    """夫名義 4000 万、妻 0 → 夫 → 妻 に 2000 万清算."""
    payload = {
        "assets": [
            {"asset_type": "deposit", "value": 40_000_000, "owner": "husband"},
        ],
    }
    r = compute(payload)
    ok = (
        r["summary"]["settlement_from_husband_to_wife"] == 20_000_000
        and r["summary"]["settlement_from_wife_to_husband"] == 0
    )
    return _check("01. 夫単独名義 4000万 → 夫→妻 2000万", ok)


def test_02_equal_split_both_own() -> bool:
    """夫 3000 万、妻 1000 万 → 夫 → 妻に 1000 万."""
    payload = {
        "assets": [
            {"asset_type": "deposit", "value": 30_000_000, "owner": "husband"},
            {"asset_type": "deposit", "value": 10_000_000, "owner": "wife"},
        ],
    }
    r = compute(payload)
    ok = r["summary"]["settlement_from_husband_to_wife"] == 10_000_000
    return _check("02. 夫3000 妻1000 → 夫→妻 1000", ok, f"{r['summary']['settlement_from_husband_to_wife']:,}")


def test_03_special_property_excluded() -> bool:
    """相続で取得した不動産は特有財産 → 分与対象外."""
    payload = {
        "assets": [
            {"asset_type": "real_estate", "value": 50_000_000, "owner": "husband",
             "is_special_property": True, "special_reason": "父から相続"},
            {"asset_type": "deposit", "value": 10_000_000, "owner": "husband"},
        ],
    }
    r = compute(payload)
    # 特有 5000 万は除外、共有 1000 万 → 夫 → 妻 500 万
    ok = (
        r["summary"]["net_shared_assets"] == 10_000_000
        and r["summary"]["settlement_from_husband_to_wife"] == 5_000_000
        and len(r["special_assets"]) == 1
    )
    return _check("03. 特有財産の除外", ok)


def test_04_debts_reduce_shared() -> bool:
    """共有債務は分与対象財産から控除."""
    payload = {
        "assets": [
            {"asset_type": "deposit", "value": 40_000_000, "owner": "husband"},
        ],
        "shared_debts": [{"amount": 10_000_000, "description": "住宅ローン残"}],
    }
    r = compute(payload)
    # 4000 - 1000 = 3000 → 妻 1500 万
    ok = (
        r["summary"]["net_shared_assets"] == 30_000_000
        and r["summary"]["settlement_from_husband_to_wife"] == 15_000_000
    )
    return _check("04. 共有債務の控除", ok)


def test_05_negative_net() -> bool:
    """債務超過 → 清算金 0、warning 付き."""
    payload = {
        "assets": [
            {"asset_type": "deposit", "value": 5_000_000, "owner": "husband"},
        ],
        "shared_debts": [{"amount": 10_000_000}],
    }
    r = compute(payload)
    ok = (
        r["summary"]["settlement_from_husband_to_wife"] == 0
        and r["summary"]["settlement_from_wife_to_husband"] == 0
        and "債務超過" in r["note"]
    )
    return _check("05. 債務超過", ok)


def test_06_custom_ratio() -> bool:
    """貢献度 7:3 の場合."""
    payload = {
        "assets": [
            {"asset_type": "deposit", "value": 100_000_000, "owner": "husband"},
        ],
        "contribution_ratio": {"husband": 7, "wife": 3},
    }
    r = compute(payload)
    # 夫 7000、妻 3000 → 夫 1億現有、清算 夫→妻 3000 万
    ok = r["summary"]["settlement_from_husband_to_wife"] == 30_000_000
    return _check("06. 貢献度 7:3", ok)


def test_07_joint_ownership() -> bool:
    """joint 財産は 50:50 暫定按分."""
    payload = {
        "assets": [
            {"asset_type": "real_estate", "value": 60_000_000, "owner": "joint"},
        ],
    }
    r = compute(payload)
    # 夫現有 3000、妻現有 3000、各 3000 取得 → 清算金 0
    ok = (
        r["summary"]["husband_current_holdings"] == 30_000_000
        and r["summary"]["settlement_from_husband_to_wife"] == 0
    )
    return _check("07. joint 財産は 50:50 暫定", ok)


def test_08_multiple_assets_mixed() -> bool:
    """複数財産の混合."""
    payload = {
        "assets": [
            {"asset_type": "deposit", "value": 20_000_000, "owner": "husband"},
            {"asset_type": "deposit", "value": 5_000_000, "owner": "wife"},
            {"asset_type": "real_estate", "value": 40_000_000, "owner": "joint"},
            {"asset_type": "securities", "value": 5_000_000, "owner": "husband",
             "is_special_property": True, "special_reason": "婚姻前取得"},
        ],
    }
    r = compute(payload)
    # 共有 = 2000 + 500 + 4000 = 6500 万
    # 夫現有 = 2000 + 2000 (joint/2) = 4000 / 妻現有 = 500 + 2000 = 2500
    # 50:50 なら各 3250、夫→妻 750 万
    ok = (
        r["summary"]["net_shared_assets"] == 65_000_000
        and r["summary"]["settlement_from_husband_to_wife"] == 7_500_000
    )
    return _check(
        "08. 複数財産の混合", ok,
        f"清算 {r['summary']['settlement_from_husband_to_wife']:,}",
    )


def test_09_wife_owns_more() -> bool:
    """妻の方が財産多い → 妻→夫に清算."""
    payload = {
        "assets": [
            {"asset_type": "deposit", "value": 5_000_000, "owner": "husband"},
            {"asset_type": "deposit", "value": 35_000_000, "owner": "wife"},
        ],
    }
    r = compute(payload)
    # 共有 4000 万、各 2000 万 → 妻→夫 1500 万
    ok = r["summary"]["settlement_from_wife_to_husband"] == 15_000_000
    return _check("09. 妻→夫 清算", ok)


def test_10_validate_bad_owner() -> bool:
    try:
        compute({"assets": [{"asset_type": "deposit", "value": 1000, "owner": "son"}]})
        return _check("10. 不正 owner 拒否", False)
    except ValueError:
        return _check("10. 不正 owner 拒否", True)


def test_11_validate_bool_value() -> bool:
    try:
        compute({"assets": [{"asset_type": "deposit", "value": True, "owner": "husband"}]})
        return _check("11. bool value 拒否", False)
    except ValueError:
        return _check("11. bool value 拒否", True)


def test_12_no_assets() -> bool:
    """財産なし → 清算金 0."""
    r = compute({"assets": []})
    ok = (
        r["summary"]["net_shared_assets"] == 0
        and r["summary"]["settlement_from_husband_to_wife"] == 0
    )
    return _check("12. 財産なし", ok)


def run_all() -> int:
    print("property-division-calc self-test\n")
    tests = [
        test_01_equal_split_husband_owns_all,
        test_02_equal_split_both_own,
        test_03_special_property_excluded,
        test_04_debts_reduce_shared,
        test_05_negative_net,
        test_06_custom_ratio,
        test_07_joint_ownership,
        test_08_multiple_assets_mixed,
        test_09_wife_owns_more,
        test_10_validate_bad_owner,
        test_11_validate_bool_value,
        test_12_no_assets,
    ]
    passed = sum(1 for t in tests if t())
    total = len(tests)
    print(f"\n結果: {passed} passed, {total - passed} failed / {total} total")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_all())
