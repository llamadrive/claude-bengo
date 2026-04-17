#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calc.py の単体テスト。

標準ライブラリのみで動作する自己完結型テストランナーである。
pytest も利用可能だが、必須ではない。

実行方法:
    python3 skills/inheritance-calc/test_calc.py

全テストが成功すると exit code 0、失敗すると非ゼロで終了する。
"""

from __future__ import annotations

import os
import sys
import traceback
from fractions import Fraction
from typing import Callable, List, Tuple

# calc.py を import できるようパス調整
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import calc  # noqa: E402


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------


def _share_map(result: dict) -> dict:
    """id → Fraction の辞書に変換する。"""
    out = {}
    for s in result["shares"]:
        n, d = s["share"].split("/")
        out[s["id"]] = Fraction(int(n), int(d))
    return out


def _iryubun_map(result: dict) -> dict:
    out = {}
    for s in result.get("iryubun") or []:
        if s["share"] == "0":
            out[s["id"]] = Fraction(0)
        else:
            n, d = s["share"].split("/")
            out[s["id"]] = Fraction(int(n), int(d))
    return out


# ---------------------------------------------------------------------------
# 各シナリオ
# ---------------------------------------------------------------------------


def test_01_spouse_plus_three_children():
    """配偶者 + 生存した子3人 → 1/2、1/6、1/6、1/6。"""
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "甲野花子", "kind": "spouse", "status": "alive"},
            {"id": "c1", "name": "一郎", "kind": "child", "status": "alive"},
            {"id": "c2", "name": "二郎", "kind": "child", "status": "alive"},
            {"id": "c3", "name": "三郎", "kind": "child", "status": "alive"},
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    assert r["rank"] == 1
    assert m["s"] == Fraction(1, 2)
    assert m["c1"] == Fraction(1, 6)
    assert m["c2"] == Fraction(1, 6)
    assert m["c3"] == Fraction(1, 6)


def test_02_spouse_two_children_one_deceased_with_two_grandchildren():
    """配偶者 + 生存した子2人 + 死亡した子1人（孫2人）。

    配偶者 1/2、生存した子 1/6 ずつ、孫 1/12 ずつ。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "甲野花子", "kind": "spouse", "status": "alive"},
            {"id": "c1", "name": "一郎", "kind": "child", "status": "alive"},
            {"id": "c2", "name": "二郎", "kind": "child", "status": "alive"},
            {"id": "c3", "name": "三郎", "kind": "child", "status": "deceased"},
            {
                "id": "g1", "name": "孫1", "kind": "grandchild",
                "status": "alive", "parent_id": "c3",
            },
            {
                "id": "g2", "name": "孫2", "kind": "grandchild",
                "status": "alive", "parent_id": "c3",
            },
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    assert r["rank"] == 1
    assert m["s"] == Fraction(1, 2)
    assert m["c1"] == Fraction(1, 6)
    assert m["c2"] == Fraction(1, 6)
    assert m["g1"] == Fraction(1, 12)
    assert m["g2"] == Fraction(1, 12)


def test_03_spouse_plus_one_renounced_child_plus_one_alive_child():
    """配偶者 + 放棄した子 + 生存した子 → 配偶者 1/2、生存子 1/2。

    放棄者は最初から相続人でなかったとみなされる（民法939条）。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "alive"},
            {"id": "c1", "name": "放棄子", "kind": "child", "status": "renounced"},
            {"id": "c2", "name": "生存子", "kind": "child", "status": "alive"},
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    assert "c1" not in m, "放棄者には相続分がない"
    assert m["s"] == Fraction(1, 2)
    assert m["c2"] == Fraction(1, 2)


def test_04_renounced_child_with_grandchildren_no_substitute():
    """放棄した子の孫は代襲しない（放棄 ≠ 死亡）。

    他に子がいない場合は第2順位（親）に移行する。
    """
    # ケース A: 放棄した子の孫がいても代襲しない、かつ他に生存子あり
    payload_a = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "alive"},
            {"id": "c1", "name": "放棄子", "kind": "child", "status": "renounced"},
            {
                "id": "g1", "name": "放棄子の孫", "kind": "grandchild",
                "status": "alive", "parent_id": "c1",
            },
            {"id": "c2", "name": "生存子", "kind": "child", "status": "alive"},
        ],
    }
    ra = calc.compute_shares(payload_a)
    ma = _share_map(ra)
    assert "g1" not in ma, "放棄者の子は代襲しない"
    assert ma["s"] == Fraction(1, 2)
    assert ma["c2"] == Fraction(1, 2)

    # ケース B: 放棄子しかおらず、その孫もいる → 第2順位に移行
    payload_b = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "alive"},
            {"id": "c1", "name": "放棄子", "kind": "child", "status": "renounced"},
            {
                "id": "g1", "name": "放棄子の孫", "kind": "grandchild",
                "status": "alive", "parent_id": "c1",
            },
            {"id": "p1", "name": "父", "kind": "parent", "status": "alive"},
        ],
    }
    rb = calc.compute_shares(payload_b)
    mb = _share_map(rb)
    assert rb["rank"] == 2, "第1順位全員放棄 → 第2順位"
    assert mb["s"] == Fraction(2, 3)
    assert mb["p1"] == Fraction(1, 3)
    assert "g1" not in mb


def test_05_no_spouse_two_parents():
    """配偶者なし、父母2人 → 各 1/2。"""
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "p1", "name": "父", "kind": "parent", "status": "alive"},
            {"id": "p2", "name": "母", "kind": "parent", "status": "alive"},
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    assert r["rank"] == 2
    assert m["p1"] == Fraction(1, 2)
    assert m["p2"] == Fraction(1, 2)


def test_06_spouse_plus_two_parents():
    """配偶者 + 父母2人 → 配偶者 2/3、父母 各 1/6。"""
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "alive"},
            {"id": "p1", "name": "父", "kind": "parent", "status": "alive"},
            {"id": "p2", "name": "母", "kind": "parent", "status": "alive"},
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    assert r["rank"] == 2
    assert m["s"] == Fraction(2, 3)
    assert m["p1"] == Fraction(1, 6)
    assert m["p2"] == Fraction(1, 6)


def test_07_spouse_plus_full_and_half_siblings():
    """配偶者 + 全血兄弟1人 + 半血兄弟2人。

    兄弟姉妹総計 1/4。単位: 全血=1、半血=1/2。
    合計単位 = 1 + 2*(1/2) = 2。全血 1/4 * 1/2 = 1/8。
    半血 各 1/4 * 1/4 = 1/16。
    合計 3/4 + 1/8 + 2*1/16 = 3/4 + 1/8 + 1/8 = 1。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "alive"},
            {"id": "b1", "name": "全血兄", "kind": "sibling_full", "status": "alive"},
            {"id": "b2", "name": "半血弟1", "kind": "sibling_half", "status": "alive"},
            {"id": "b3", "name": "半血弟2", "kind": "sibling_half", "status": "alive"},
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    assert r["rank"] == 3
    assert m["s"] == Fraction(3, 4)
    assert m["b1"] == Fraction(1, 8)
    assert m["b2"] == Fraction(1, 16)
    assert m["b3"] == Fraction(1, 16)


def test_08_three_full_siblings_plus_one_deceased_with_nephew():
    """配偶者なし、全血兄弟3人 + 死亡した全血兄弟1人（甥1人）。

    4ラインそれぞれ 1/4。甥が代襲で 1/4。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "b1", "name": "兄1", "kind": "sibling_full", "status": "alive"},
            {"id": "b2", "name": "兄2", "kind": "sibling_full", "status": "alive"},
            {"id": "b3", "name": "兄3", "kind": "sibling_full", "status": "alive"},
            {"id": "b4", "name": "兄4", "kind": "sibling_full", "status": "deceased"},
            {
                "id": "n1", "name": "甥", "kind": "nephew_niece",
                "status": "alive", "parent_id": "b4",
            },
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    assert r["rank"] == 3
    assert m["b1"] == Fraction(1, 4)
    assert m["b2"] == Fraction(1, 4)
    assert m["b3"] == Fraction(1, 4)
    assert m["n1"] == Fraction(1, 4)


def test_09_saidaishu_great_grandchild():
    """再代襲: 子・孫が死亡、ひ孫が相続。

    配偶者 + 1ライン（子死亡、孫も死亡、ひ孫2人）。
    → 配偶者 1/2、ひ孫 各 1/4。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "alive"},
            {"id": "c1", "name": "子", "kind": "child", "status": "deceased"},
            {
                "id": "g1", "name": "孫", "kind": "grandchild",
                "status": "deceased", "parent_id": "c1",
            },
            {
                "id": "gg1", "name": "ひ孫1", "kind": "great_grandchild",
                "status": "alive", "parent_id": "g1",
            },
            {
                "id": "gg2", "name": "ひ孫2", "kind": "great_grandchild",
                "status": "alive", "parent_id": "g1",
            },
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    assert r["rank"] == 1
    assert m["s"] == Fraction(1, 2)
    assert m["gg1"] == Fraction(1, 4)
    assert m["gg2"] == Fraction(1, 4)


def test_10_sibling_saidaishu_not_allowed():
    """兄弟姉妹の再代襲は許されない（民法889条2項）。

    兄弟姉妹が死亡、甥姪も死亡、大甥がいる場合、大甥は相続しない。
    このラインは消滅する。
    """
    # 兄弟2人のうち、1人死亡（甥も死亡、大甥のみ）、1人生存
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "b1", "name": "生存兄", "kind": "sibling_full", "status": "alive"},
            {"id": "b2", "name": "死亡兄", "kind": "sibling_full", "status": "deceased"},
            {
                "id": "n1", "name": "死亡甥", "kind": "nephew_niece",
                "status": "deceased", "parent_id": "b2",
            },
            # 大甥に相当するノードが入力に入っていたとしても、calc.py は
            # nephew_niece 以外は兄弟姉妹ラインで評価しないので無視される。
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    # 死亡兄のラインは消滅 → 生存兄が単独で全部
    assert r["rank"] == 3
    assert m["b1"] == Fraction(1, 1)
    assert "n1" not in m


def test_11_all_renounced():
    """全員放棄 → 相続人不存在。"""
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "renounced"},
            {"id": "c1", "name": "子1", "kind": "child", "status": "renounced"},
            {"id": "c2", "name": "子2", "kind": "child", "status": "renounced"},
        ],
    }
    r = calc.compute_shares(payload)
    assert r["rank"] is None
    assert r["shares"] == []
    assert any("相続人が存在しない" in n for n in r["notes"])


def test_12_spouse_only():
    """配偶者のみ → 1/1。"""
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "alive"},
        ],
    }
    r = calc.compute_shares(payload)
    m = _share_map(r)
    assert r["rank"] == 0
    assert m["s"] == Fraction(1, 1)


def test_13_iryubun_spouse_plus_two_children():
    """遺留分: 配偶者 + 子2人。

    総遺留分 1/2。配偶者 1/2 * 1/2 = 1/4、子 各 1/2 * 1/4 = 1/8。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "alive"},
            {"id": "c1", "name": "子1", "kind": "child", "status": "alive"},
            {"id": "c2", "name": "子2", "kind": "child", "status": "alive"},
        ],
        "compute_iryubun": True,
    }
    r = calc.compute_shares(payload)
    ir = _iryubun_map(r)
    assert ir["s"] == Fraction(1, 4)
    assert ir["c1"] == Fraction(1, 8)
    assert ir["c2"] == Fraction(1, 8)


def test_14_iryubun_ascendants_only():
    """遺留分: 直系尊属のみ → 総遺留分 1/3、各 1/6。"""
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "p1", "name": "父", "kind": "parent", "status": "alive"},
            {"id": "p2", "name": "母", "kind": "parent", "status": "alive"},
        ],
        "compute_iryubun": True,
    }
    r = calc.compute_shares(payload)
    ir = _iryubun_map(r)
    assert ir["p1"] == Fraction(1, 6)
    assert ir["p2"] == Fraction(1, 6)


def test_15_iryubun_siblings_none():
    """遺留分: 配偶者 + 兄弟姉妹の場合、配偶者のみが遺留分権利者。

    民法1042条1項2号により、兄弟姉妹（甥姪を含む）は遺留分権利者では
    ないが、配偶者は兄弟姉妹と共に相続する場合でも遺留分権利者である。

    配偶者の法定相続分は 3/4、総遺留分は 1/2 なので、配偶者の遺留分 =
    1/2 × 3/4 = 3/8 となる。兄弟姉妹の遺留分は 0。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "s", "name": "配偶者", "kind": "spouse", "status": "alive"},
            {"id": "b1", "name": "兄", "kind": "sibling_full", "status": "alive"},
        ],
        "compute_iryubun": True,
    }
    r = calc.compute_shares(payload)
    ir = _iryubun_map(r)
    # 兄弟姉妹の遺留分は 0（民法1042条は配偶者・子・直系尊属に限定）。
    assert ir["b1"] == Fraction(0), "兄弟姉妹には遺留分がない"
    # 配偶者の遺留分は 1/2 × 3/4 = 3/8。この値を明示的にロックダウンする。
    assert ir["s"] == Fraction(3, 8), (
        f"配偶者の遺留分は 3/8 であるべき（実際: {ir['s']}）。"
        "総遺留分 1/2 × 法定相続分 3/4 = 3/8。"
    )


def test_16_parent_id_cycle():
    """parent_id にサイクルがある場合、入力を拒否する。

    h1.parent_id=h2 かつ h2.parent_id=h1 のような循環は、下流の代襲
    探索が無限再帰に陥るおそれがあるため、計算前に ValueError を投げる。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {
                "id": "h1", "name": "A", "kind": "grandchild",
                "status": "alive", "parent_id": "h2",
            },
            {
                "id": "h2", "name": "B", "kind": "grandchild",
                "status": "alive", "parent_id": "h1",
            },
        ],
    }
    try:
        calc.compute_shares(payload)
    except ValueError as e:
        assert "cycle" in str(e) or "サイクル" in str(e), (
            f"エラーメッセージに cycle/サイクル を含むべき: {e}"
        )
    else:
        raise AssertionError("parent_id サイクルが検出されなかった")


def test_17_adoption_on_grandchild():
    """adoption フィールドは kind='child' 以外では使えない。

    grandchild に adoption='special' を指定すると ValueError を投げる。
    意味論的に無意味なフィールドを受け付けて沈黙するのは不安全である。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "c1", "name": "死亡子", "kind": "child", "status": "deceased"},
            {
                "id": "g1", "name": "孫", "kind": "grandchild",
                "status": "alive", "parent_id": "c1",
                "adoption": "special",
            },
        ],
    }
    try:
        calc.compute_shares(payload)
    except ValueError as e:
        assert "kind='child'" in str(e), (
            f"エラーメッセージに kind='child' を含むべき: {e}"
        )
    else:
        raise AssertionError("grandchild への adoption が検出されなかった")


def test_18_parent_id_self_loop():
    """parent_id が自分自身を指す場合、即座に拒否する。

    h1.parent_id = h1 は論理的にあり得ない。単一ノードのサイクルも
    明示的に検出する。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {
                "id": "h1", "name": "A", "kind": "grandchild",
                "status": "alive", "parent_id": "h1",
            },
        ],
    }
    try:
        calc.compute_shares(payload)
    except ValueError as e:
        assert "サイクル" in str(e) or "cycle" in str(e), (
            f"エラーメッセージに サイクル を含むべき: {e}"
        )
    else:
        raise AssertionError("自己参照サイクルが検出されなかった")


def test_19_dual_heirship_detection():
    """二重相続資格（養子かつ代襲相続人）は本スキルでは処理しない。

    被相続人の孫 h1 を養子にしたうえで、h1 の実親（被相続人の子）が先に
    死亡した場合、民法上の通説では h1 は子としての相続分と代襲分の両方を
    受ける。本スキルはこれを処理しないため、kind='child' に parent_id が
    付与された時点でエラーを返す。
    """
    payload = {
        "decedent": {"id": "d", "name": "甲野太郎"},
        "heirs": [
            {"id": "c0", "name": "死亡子", "kind": "child", "status": "deceased"},
            {
                # 孫を養子にしたので kind='child' かつ parent_id を持つ
                "id": "h1", "name": "養子となった孫", "kind": "child",
                "status": "alive", "adoption": "none", "parent_id": "c0",
            },
        ],
    }
    try:
        calc.compute_shares(payload)
    except ValueError as e:
        assert "二重相続資格" in str(e), (
            f"エラーメッセージに 二重相続資格 を含むべき: {e}"
        )
    else:
        raise AssertionError("二重相続資格のケースが検出されなかった")


# ---------------------------------------------------------------------------
# テストランナー
# ---------------------------------------------------------------------------


ALL_TESTS: List[Tuple[str, Callable[[], None]]] = [
    ("01 配偶者+子3人", test_01_spouse_plus_three_children),
    ("02 配偶者+子2人+死亡子(孫2人)", test_02_spouse_two_children_one_deceased_with_two_grandchildren),
    ("03 配偶者+放棄子+生存子", test_03_spouse_plus_one_renounced_child_plus_one_alive_child),
    ("04 放棄子の孫は代襲しない", test_04_renounced_child_with_grandchildren_no_substitute),
    ("05 父母のみ", test_05_no_spouse_two_parents),
    ("06 配偶者+父母", test_06_spouse_plus_two_parents),
    ("07 配偶者+全血+半血兄弟", test_07_spouse_plus_full_and_half_siblings),
    ("08 兄弟+死亡兄弟の甥代襲", test_08_three_full_siblings_plus_one_deceased_with_nephew),
    ("09 再代襲（ひ孫）", test_09_saidaishu_great_grandchild),
    ("10 兄弟の再代襲不可", test_10_sibling_saidaishu_not_allowed),
    ("11 全員放棄", test_11_all_renounced),
    ("12 配偶者単独", test_12_spouse_only),
    ("13 遺留分（配偶者+子）", test_13_iryubun_spouse_plus_two_children),
    ("14 遺留分（直系尊属のみ）", test_14_iryubun_ascendants_only),
    ("15 遺留分（配偶者+兄弟姉妹）", test_15_iryubun_siblings_none),
    ("16 parent_id サイクル検出", test_16_parent_id_cycle),
    ("17 孫への adoption は無効", test_17_adoption_on_grandchild),
    ("18 parent_id 自己参照の検出", test_18_parent_id_self_loop),
    ("19 二重相続資格の検出", test_19_dual_heirship_detection),
]


def run_all() -> int:
    passed = 0
    failed = 0
    for name, fn in ALL_TESTS:
        try:
            fn()
        except Exception:
            failed += 1
            print(f"[FAIL] {name}")
            traceback.print_exc()
            print()
        else:
            passed += 1
            print(f"[PASS] {name}")

    print()
    print(f"結果: {passed} passed, {failed} failed / {len(ALL_TESTS)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
