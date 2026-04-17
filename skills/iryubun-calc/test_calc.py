#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iryubun-calc のユニットテスト."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from calc import compute_iryubun


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")
    return cond


def test_01_spouse_basic() -> bool:
    """配偶者 1/2、遺産 1 億、全部遺贈 → 侵害額 2500 万."""
    payload = {
        "basis": {"positive_estate": 100_000_000, "debts": 0},
        "heirs": [
            {"id": "w", "kind": "spouse", "legal_share": "1/2", "inherited_net_amount": 0},
            {"id": "c1", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "w",
    }
    r = compute_iryubun(payload)
    # 配偶者個別遺留分 = 1/2 × 1/2 = 1/4 → 2,500 万
    ok = r["iryubun_infringement"] == 25_000_000
    return _check(
        "01. 配偶者 + 子 1 人、全部第三者遺贈",
        ok,
        f"{r['iryubun_infringement']:,} 円",
    )


def test_02_ascendants_only() -> bool:
    """直系尊属のみ → 総体的遺留分 1/3."""
    payload = {
        "basis": {"positive_estate": 60_000_000, "debts": 0},
        "heirs": [
            {"id": "p1", "kind": "parent", "legal_share": "1/2", "inherited_net_amount": 0},
            {"id": "p2", "kind": "parent", "legal_share": "1/2", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "p1",
    }
    r = compute_iryubun(payload)
    # 総体 1/3 × 法定 1/2 = 1/6 → 1,000 万
    ok = r["iryubun_infringement"] == 10_000_000 and r["soutaiteki_ritsu"] == "1/3"
    return _check(
        "02. 直系尊属のみ 総体的遺留分 1/3",
        ok,
        f"{r['iryubun_infringement']:,} 円",
    )


def test_03_sibling_not_eligible() -> bool:
    """兄弟姉妹は遺留分権利者でない（民法 1042 条但書）."""
    payload = {
        "basis": {"positive_estate": 50_000_000, "debts": 0},
        "heirs": [
            {"id": "b1", "kind": "sibling_full", "legal_share": "1", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "b1",
    }
    r = compute_iryubun(payload)
    ok = r["iryubun_infringement"] == 0 and "遺留分権利者ではない" in r["note"]
    return _check("03. 兄弟姉妹は遺留分なし", ok)


def test_04_with_lifetime_gift_to_requester() -> bool:
    """請求者本人への生前贈与は基礎財産に加算、かつ受領分として控除."""
    payload = {
        "basis": {
            "positive_estate": 50_000_000,
            "debts": 0,
            "lifetime_gifts_to_heirs": [
                {"heir_id": "c1", "amount": 20_000_000},  # 子に 2000 万贈与
            ],
        },
        "heirs": [
            {"id": "c1", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 0},
            {"id": "c2", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "c1",
    }
    r = compute_iryubun(payload)
    # 基礎財産 = 5000 + 2000 = 7000 万
    # 個別遺留分 = 7000 × 1/2 × 1/2 = 1750 万
    # c1 は 2000 万を受領済み → 侵害なし
    ok = r["iryubun_infringement"] == 0 and r["basis_estate"] == 70_000_000
    return _check(
        "04. 請求者への生前贈与で侵害額相殺",
        ok,
        f"侵害額 {r['iryubun_infringement']:,}、基礎財産 {r['basis_estate']:,}",
    )


def test_05_with_gift_to_other_heir() -> bool:
    """他の相続人への贈与は基礎財産に加算（請求者の侵害額を増やす）."""
    payload = {
        "basis": {
            "positive_estate": 30_000_000,
            "debts": 0,
            "lifetime_gifts_to_heirs": [
                {"heir_id": "c2", "amount": 50_000_000},  # c2 に 5000 万贈与
            ],
        },
        "heirs": [
            {"id": "c1", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 0},
            {"id": "c2", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 50_000_000},
        ],
        "requesting_heir_id": "c1",
    }
    r = compute_iryubun(payload)
    # 基礎 = 3000 + 5000 = 8000 万
    # c1 個別遺留分 = 8000 × 1/2 × 1/2 = 2000 万
    # c1 受領 = 0 → 侵害額 2000 万
    ok = r["iryubun_infringement"] == 20_000_000
    return _check(
        "05. 他相続人への贈与で請求者の侵害額確定",
        ok,
        f"{r['iryubun_infringement']:,}",
    )


def test_06_debts_reduce_basis() -> bool:
    """債務は基礎財産から控除."""
    payload = {
        "basis": {"positive_estate": 100_000_000, "debts": 40_000_000},
        "heirs": [
            {"id": "c1", "kind": "child", "legal_share": "1", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "c1",
    }
    r = compute_iryubun(payload)
    # 基礎 = 1 億 - 4000万 = 6000 万
    # 個別遺留分 = 6000 × 1/2 × 1 = 3000 万
    ok = r["basis_estate"] == 60_000_000 and r["iryubun_infringement"] == 30_000_000
    return _check("06. 債務控除後の基礎財産", ok, f"基礎 {r['basis_estate']:,}")


def test_07_negative_basis() -> bool:
    """債務超過 → 侵害額 0."""
    payload = {
        "basis": {"positive_estate": 10_000_000, "debts": 50_000_000},
        "heirs": [
            {"id": "c1", "kind": "child", "legal_share": "1", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "c1",
    }
    r = compute_iryubun(payload)
    ok = r["iryubun_infringement"] == 0 and "マイナス" in r["note"]
    return _check("07. 債務超過 → 侵害額 0", ok)


def test_08_specific_bequest_to_requester() -> bool:
    """請求者への特定遺贈も受領分として控除."""
    payload = {
        "basis": {
            "positive_estate": 100_000_000,
            "debts": 0,
            "specific_bequests": [{"recipient_id": "c1", "amount": 30_000_000}],
        },
        "heirs": [
            {"id": "c1", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 0},
            {"id": "c2", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "c1",
    }
    r = compute_iryubun(payload)
    # 個別遺留分 = 1 億 × 1/2 × 1/2 = 2500 万
    # c1 の遺贈受領 = 3000 万 → 侵害額 0
    ok = r["iryubun_infringement"] == 0
    return _check("08. 請求者への特定遺贈で相殺", ok)


def test_09_third_party_gift() -> bool:
    """1 年内の第三者贈与も基礎財産に加算."""
    payload = {
        "basis": {
            "positive_estate": 50_000_000,
            "debts": 0,
            "third_party_gifts": [{"amount": 30_000_000}],
        },
        "heirs": [
            {"id": "c1", "kind": "child", "legal_share": "1", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "c1",
    }
    r = compute_iryubun(payload)
    # 基礎 = 5000 + 3000 = 8000 万
    # 遺留分 = 8000 × 1/2 × 1 = 4000 万
    ok = r["iryubun_infringement"] == 40_000_000
    return _check("09. 第三者贈与の加算", ok, f"{r['iryubun_infringement']:,}")


def test_10_validate_missing_requester() -> bool:
    try:
        compute_iryubun({
            "basis": {"positive_estate": 100_000_000, "debts": 0},
            "heirs": [{"id": "c1", "kind": "child", "legal_share": "1"}],
            "requesting_heir_id": "ghost",
        })
        return _check("10. 存在しない requesting_heir_id 拒否", False)
    except ValueError:
        return _check("10. 存在しない requesting_heir_id 拒否", True)


def test_11_validate_bool_amount() -> bool:
    try:
        compute_iryubun({
            "basis": {"positive_estate": True, "debts": 0},
            "heirs": [{"id": "c1", "kind": "child", "legal_share": "1"}],
            "requesting_heir_id": "c1",
        })
        return _check("11. bool positive_estate 拒否", False)
    except ValueError:
        return _check("11. bool positive_estate 拒否", True)


def test_12_inherited_net_reduces_infringement() -> bool:
    """相続により net で取得した額も受領分として控除."""
    payload = {
        "basis": {"positive_estate": 100_000_000, "debts": 0},
        "heirs": [
            {"id": "c1", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 20_000_000},
            {"id": "c2", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 80_000_000},
        ],
        "requesting_heir_id": "c1",
    }
    r = compute_iryubun(payload)
    # 個別遺留分 = 1 億 × 1/2 × 1/2 = 2500 万
    # 受領 = 2000 万
    # 侵害額 = 500 万
    ok = r["iryubun_infringement"] == 5_000_000
    return _check(
        "12. 相続取得分の控除", ok, f"{r['iryubun_infringement']:,}",
    )


def test_13_fraction_legal_share() -> bool:
    """legal_share が Fraction 文字列で与えられる (1/6 等)."""
    payload = {
        "basis": {"positive_estate": 120_000_000, "debts": 0},
        "heirs": [
            {"id": "s", "kind": "spouse", "legal_share": "1/2", "inherited_net_amount": 0},
            {"id": "c1", "kind": "child", "legal_share": "1/6", "inherited_net_amount": 0},
            {"id": "c2", "kind": "child", "legal_share": "1/6", "inherited_net_amount": 0},
            {"id": "c3", "kind": "child", "legal_share": "1/6", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "c1",
    }
    r = compute_iryubun(payload)
    # c1 個別 = 1/2 × 1/6 = 1/12 → 1000 万
    ok = r["iryubun_infringement"] == 10_000_000
    return _check("13. Fraction 形式の法定相続分", ok, f"{r['iryubun_infringement']:,}")


def test_14_ascendants_only_with_one_parent() -> bool:
    """直系尊属 1 人 → 総体 1/3 × 法定 1/1 = 1/3."""
    payload = {
        "basis": {"positive_estate": 30_000_000, "debts": 0},
        "heirs": [
            {"id": "p1", "kind": "parent", "legal_share": "1", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "p1",
    }
    r = compute_iryubun(payload)
    # 3000 × 1/3 × 1 = 1000 万
    ok = r["iryubun_infringement"] == 10_000_000
    return _check("14. 父母 1 人のみ 遺留分 1/3", ok)


def test_15_multiple_gifts_aggregation() -> bool:
    """生前贈与が複数の場合の合算."""
    payload = {
        "basis": {
            "positive_estate": 50_000_000,
            "debts": 0,
            "lifetime_gifts_to_heirs": [
                {"heir_id": "c1", "amount": 10_000_000},
                {"heir_id": "c1", "amount": 20_000_000},  # 請求者への合計 3000 万
                {"heir_id": "c2", "amount": 20_000_000},
            ],
        },
        "heirs": [
            {"id": "c1", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 0},
            {"id": "c2", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "c1",
    }
    r = compute_iryubun(payload)
    # 基礎 = 5000 + 1000 + 2000 + 2000 = 1 億
    # 個別遺留分 = 1 億 × 1/2 × 1/2 = 2500 万
    # c1 受領 = 3000 万 → 侵害なし
    ok = r["iryubun_infringement"] == 0 and r["basis_estate"] == 100_000_000
    return _check("15. 複数贈与の合算", ok)


def run_all() -> int:
    print("iryubun-calc self-test\n")
    tests = [
        test_01_spouse_basic, test_02_ascendants_only, test_03_sibling_not_eligible,
        test_04_with_lifetime_gift_to_requester, test_05_with_gift_to_other_heir,
        test_06_debts_reduce_basis, test_07_negative_basis,
        test_08_specific_bequest_to_requester, test_09_third_party_gift,
        test_10_validate_missing_requester, test_11_validate_bool_amount,
        test_12_inherited_net_reduces_infringement, test_13_fraction_legal_share,
        test_14_ascendants_only_with_one_parent, test_15_multiple_gifts_aggregation,
    ]
    passed = sum(1 for t in tests if t())
    total = len(tests)
    print(f"\n結果: {passed} passed, {total - passed} failed / {total} total")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_all())
