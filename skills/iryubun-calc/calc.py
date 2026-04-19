#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""遺留分侵害額計算モジュール（民法 1042 条以下）。

本スクリプトは、遺言・生前贈与等により遺留分権利者の遺留分が侵害された場合
の、民法 1046 条に基づく金銭請求額を決定論的に計算する。`inheritance-calc` と
組み合わせて使う。

## 関連条文

- 民法 1042 条 遺留分割合（直系尊属のみ 1/3、それ以外 1/2）
- 民法 1043 条 遺留分算定の基礎財産
- 民法 1044 条 生前贈与の加算（10 年内の特別受益・1 年内の第三者贈与）
- 民法 1045 条 贈与の評価（相続開始時点の価額）
- 民法 1046 条 遺留分侵害額請求権（金銭請求化、2019 年改正）
- 民法 1047 条 受遺者・受贈者の負担順位

## 計算フロー

1. 遺留分算定基礎財産 = 積極財産 + 加算贈与 - 債務
2. 総体的遺留分 = 基礎財産 × 遺留分割合（1/2 or 1/3）
3. 個別的遺留分 = 総体的遺留分 × 法定相続分
4. 遺留分侵害額 = 個別的遺留分 - (請求者が受けた遺贈・生前贈与 + 相続により取得する財産 - 相続債務負担分)

## 対応範囲外

- 不動産・株式等の評価方法（ユーザー指定値を使用）
- 遺留分侵害請求の時効判定（民法 1048 条、1 年 / 10 年）
- 複数受遺者・受贈者間の負担配分の詳細（概略のみ）
- 寄与分・特別受益との複雑な相互作用
- 配偶者居住権（民法 1028 条以下）

## 入力スキーマ上の重要な取り決め (F-027)

`basis.positive_estate` は **相続開始時の積極財産の総額** を指す。ここには:

- 預貯金・不動産・動産等の遺産評価額
- `basis.specific_bequests` として列挙する個別遺贈の対象財産の価額

の **両方を含めて集計する**（二重計上しない）。specific_bequests は基礎財産
への加算対象ではなく、あくまで遺留分侵害算定時の「請求者が受けた遺贈」の
控除対象として使う（民法 1046 条）。

生前贈与は別系統で加算する:
- `lifetime_gifts_to_heirs`: 相続人への贈与（原則 10 年以内、民法 1044 条 3 項）
- `third_party_gifts`: 第三者への贈与（原則 1 年以内、または悪意あり）

**典型的な入力ミスと結果:**

- positive_estate に遺贈対象の価額を含め忘れた → 基礎財産が過小算定され、
  遺留分侵害額が実際より少なく出る
- specific_bequests を基礎財産への加算として扱った → 基礎財産を二重計上し、
  請求額が過大
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

# 遺留分割合（民法 1042 条）
# 直系尊属のみが相続人のとき 1/3、それ以外 1/2
SOUTAITEKI_RITSU_ASCENDANTS_ONLY = Fraction(1, 3)
SOUTAITEKI_RITSU_DEFAULT = Fraction(1, 2)

# 遺留分権利者（民法 1042 条）
# 兄弟姉妹は遺留分権利者でない（民法 1042 条括弧書）
IRYUBUN_ELIGIBLE_KINDS = {
    "spouse", "child", "grandchild", "great_grandchild",
    "parent", "grandparent",
}


def _validate(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("入力は JSON オブジェクト")

    basis = payload.get("basis")
    if not isinstance(basis, dict):
        raise ValueError("basis フィールドが必要")

    for key in ("positive_estate", "debts"):
        v = basis.get(key)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"basis.{key} は 0 以上の整数（受信: {v!r}）")

    gifts = basis.get("lifetime_gifts_to_heirs", [])
    if not isinstance(gifts, list):
        raise ValueError("basis.lifetime_gifts_to_heirs はリスト")
    for i, g in enumerate(gifts):
        if not isinstance(g, dict) or "amount" not in g or "heir_id" not in g:
            raise ValueError(f"lifetime_gifts_to_heirs[{i}] には heir_id と amount が必要")
        amt = g["amount"]
        if isinstance(amt, bool) or not isinstance(amt, int) or amt < 0:
            raise ValueError(f"lifetime_gifts_to_heirs[{i}].amount は 0 以上の整数")

    third_party_gifts = basis.get("third_party_gifts", [])
    if not isinstance(third_party_gifts, list):
        raise ValueError("basis.third_party_gifts はリスト")
    for i, g in enumerate(third_party_gifts):
        amt = g.get("amount") if isinstance(g, dict) else None
        if isinstance(amt, bool) or not isinstance(amt, int) or amt is None or amt < 0:
            raise ValueError(f"third_party_gifts[{i}].amount は 0 以上の整数")

    heirs = payload.get("heirs", [])
    if not isinstance(heirs, list) or not heirs:
        raise ValueError("heirs は非空リスト")
    for i, h in enumerate(heirs):
        if not isinstance(h, dict) or "id" not in h or "kind" not in h:
            raise ValueError(f"heirs[{i}] には id と kind が必要")
        if "legal_share" in h:
            ls = h["legal_share"]
            if not isinstance(ls, (int, float, str)):
                raise ValueError(f"heirs[{i}].legal_share は '1/2' 形式の文字列か数値")

    req = payload.get("requesting_heir_id")
    if not isinstance(req, str) or not req:
        raise ValueError("requesting_heir_id は必須")


def _parse_share(v) -> Fraction:
    """legal_share の値を Fraction に正規化する。"""
    if isinstance(v, Fraction):
        return v
    if isinstance(v, int) and not isinstance(v, bool):
        return Fraction(v)
    if isinstance(v, float):
        # Fraction.from_float は精度問題を引き起こすので限定
        return Fraction(v).limit_denominator(10000)
    if isinstance(v, str):
        if "/" in v:
            num, den = v.split("/", 1)
            return Fraction(int(num.strip()), int(den.strip()))
        return Fraction(v)
    raise ValueError(f"share 値が不正: {v!r}")


def compute_iryubun(payload: dict) -> dict:
    """遺留分侵害額を計算する。"""
    _validate(payload)

    basis = payload["basis"]
    heirs = payload["heirs"]
    requesting_id = payload["requesting_heir_id"]

    positive = Fraction(basis.get("positive_estate", 0))
    debts = Fraction(basis.get("debts", 0))

    lifetime_gifts = basis.get("lifetime_gifts_to_heirs", []) or []
    third_party_gifts = basis.get("third_party_gifts", []) or []
    specific_bequests = basis.get("specific_bequests", []) or []

    # 1. 遺留分算定基礎財産（民法 1043 条・1044 条）
    sum_lifetime = sum(Fraction(g["amount"]) for g in lifetime_gifts)  # 10 年以内推定
    sum_third_party = sum(Fraction(g["amount"]) for g in third_party_gifts)  # 1 年以内 + 悪意
    basis_estate = positive + sum_lifetime + sum_third_party - debts

    if basis_estate < 0:
        return {
            "requesting_heir_id": requesting_id,
            "basis_estate": int(basis_estate),
            "iryubun_infringement": 0,
            "note": "基礎財産がマイナス（債務超過）のため、遺留分侵害額は発生しない",
            "warnings": [],
        }

    # 2. 遺留分権利者の決定と総体的遺留分割合
    # 相続人の種類から「直系尊属のみ」判定
    has_descendants = any(
        h["kind"] in ("child", "grandchild", "great_grandchild") for h in heirs
    )
    has_spouse = any(h["kind"] == "spouse" for h in heirs)
    only_ascendants = not has_descendants and not has_spouse and all(
        h["kind"] in ("parent", "grandparent") for h in heirs
    )
    soutaiteki_ritsu = (
        SOUTAITEKI_RITSU_ASCENDANTS_ONLY if only_ascendants else SOUTAITEKI_RITSU_DEFAULT
    )

    # 3. 請求者の個別的遺留分
    req_heir = next((h for h in heirs if h["id"] == requesting_id), None)
    if req_heir is None:
        raise ValueError(f"requesting_heir_id '{requesting_id}' が heirs に存在しない")

    if req_heir["kind"] not in IRYUBUN_ELIGIBLE_KINDS:
        return {
            "requesting_heir_id": requesting_id,
            "basis_estate": int(basis_estate),
            "iryubun_infringement": 0,
            "note": f"'{req_heir['kind']}' は遺留分権利者ではない（兄弟姉妹等、民法 1042 条但書）",
            "warnings": [],
        }

    req_legal_share = _parse_share(req_heir.get("legal_share", 0))
    individual_iryubun_fraction = soutaiteki_ritsu * req_legal_share
    individual_iryubun_amount = basis_estate * individual_iryubun_fraction

    # 4. 請求者が既に受けた利益（相続取得分 + 遺贈 + 生前贈与）
    already_inherited = Fraction(req_heir.get("inherited_net_amount", 0))
    gift_to_requester = sum(
        Fraction(g["amount"]) for g in lifetime_gifts if g.get("heir_id") == requesting_id
    )
    bequest_to_requester = sum(
        Fraction(b["amount"]) for b in specific_bequests if b.get("recipient_id") == requesting_id
    )

    received_total = already_inherited + gift_to_requester + bequest_to_requester

    # 5. 遺留分侵害額
    infringement_f = individual_iryubun_amount - received_total
    if infringement_f < 0:
        infringement = 0
        note = "請求者が既に受けた利益が個別的遺留分を上回るため、侵害額はない"
    else:
        infringement = int(infringement_f)
        note = "民法 1046 条に基づく金銭請求額"

    warnings: List[str] = []
    if only_ascendants and req_heir["kind"] == "spouse":
        warnings.append("計算上の不整合: 配偶者がいれば only_ascendants にはならない。データ見直しを")
    if basis_estate > 0 and soutaiteki_ritsu == SOUTAITEKI_RITSU_ASCENDANTS_ONLY:
        warnings.append("直系尊属のみの相続人構成では総体的遺留分は 1/3（民法 1042 条 1 項 1 号）")

    return {
        "requesting_heir_id": requesting_id,
        "basis_estate": int(basis_estate),
        "soutaiteki_ritsu": f"{soutaiteki_ritsu.numerator}/{soutaiteki_ritsu.denominator}",
        "requesting_heir_legal_share": f"{req_legal_share.numerator}/{req_legal_share.denominator}",
        "individual_iryubun_fraction": f"{individual_iryubun_fraction.numerator}/{individual_iryubun_fraction.denominator}",
        "individual_iryubun_amount": int(individual_iryubun_amount),
        "received_total": int(received_total),
        "iryubun_infringement": infringement,
        "breakdown": {
            "positive_estate": int(positive),
            "debts": int(debts),
            "lifetime_gifts_sum": int(sum_lifetime),
            "third_party_gifts_sum": int(sum_third_party),
            "already_inherited": int(already_inherited),
            "gift_to_requester": int(gift_to_requester),
            "bequest_to_requester": int(bequest_to_requester),
        },
        "note": note,
        "warnings": warnings,
        "legal_references": [
            "民法 1042 条（遺留分割合）",
            "民法 1043 条・1044 条（基礎財産・生前贈与加算）",
            "民法 1046 条（遺留分侵害額請求権）",
            "民法 1048 条（時効: 1 年（短期） / 10 年（除斥））",
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_calc(args: argparse.Namespace) -> int:
    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
            return 2
    elif args.json:
        try:
            payload = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
            return 1
    else:
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
            return 1

    try:
        result = compute_iryubun(payload)
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.pretty:
        _print_pretty(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _print_pretty(result: dict) -> None:
    print("\n## 遺留分侵害額計算結果\n")
    print(f"  請求者              : {result['requesting_heir_id']}")
    if "basis_estate" in result:
        print(f"  遺留分算定基礎財産  : {result['basis_estate']:>12,} 円")
    if "soutaiteki_ritsu" in result:
        print(f"  総体的遺留分割合    : {result['soutaiteki_ritsu']}")
        print(f"  法定相続分          : {result['requesting_heir_legal_share']}")
        print(f"  個別的遺留分 (割合) : {result['individual_iryubun_fraction']}")
        print(f"  個別的遺留分 (金額) : {result['individual_iryubun_amount']:>12,} 円")
        print(f"  請求者受領分        : {result['received_total']:>12,} 円")
    print(f"  ═══════════════════════════════════")
    print(f"  ★ 遺留分侵害額      : {result['iryubun_infringement']:>12,} 円")
    print(f"\n  備考: {result.get('note', '')}")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"  ⚠ {w}")


def main() -> int:
    ap = argparse.ArgumentParser(description="遺留分侵害額計算（民法 1042 条以下）")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("calc")
    p.add_argument("--input")
    p.add_argument("--json")
    p.add_argument("--pretty", action="store_true")

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
