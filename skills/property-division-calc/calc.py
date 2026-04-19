#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""離婚財産分与計算モジュール（民法 768 条）。

離婚時の夫婦間の共有財産分与を決定論的に計算する。夫婦共有財産と
特有財産を区別し、貢献度（既定 50:50）に応じて按分する。

## 関連条文・実務

- 民法 762 条 夫婦の財産関係（特有財産の区別）
- 民法 768 条 協議離婚・裁判離婚時の財産分与
- 最判昭和 36 年 9 月 6 日: 特有財産の推定
- 家族関係事件の実務: 原則 50:50、医師・経営者等で貢献差が認められる例外あり

## 財産の分類

1. **夫婦共有財産（分与対象）**
   - 婚姻中に夫婦が協力して取得した財産
   - 一方の名義でも実質共有
   - 例: 預貯金増加分、不動産、自動車、有価証券、退職金（婚姻期間分）

2. **特有財産（分与対象外、民法 762 条 1 項）**
   - 婚姻前から一方が有していた財産
   - 婚姻中でも相続・贈与で取得した財産
   - 一方の通常業務に属さない特殊な労務による収入

3. **債務**
   - 夫婦共同生活のために生じた債務は共有財産から控除
   - 個人的消費等は各人負担

## 計算フロー

1. 各財産を「夫婦共有 or 特有」に分類
2. 夫婦共有財産の合計 - 共有債務 = 分与対象財産
3. 分与対象財産 × 貢献度 = 各人の取得分
4. 各人の取得分 - 現在名義の財産 = 清算金（正なら受取、負なら支払）

## 対応範囲外

- 不動産の評価方法（ユーザー指定値を使用）
- 退職金の将来発生分の現価換算
- 年金分割（厚生年金保険法 78 条の 2、別計算）
- 慰謝料的財産分与（本計算器は「清算的」部分のみ）
- 扶養的財産分与
- 税務（譲渡所得税・贈与税）の検討
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from typing import Dict, List, Optional


ASSET_TYPES = {
    "cash", "deposit", "real_estate", "securities", "movable",
    "insurance", "retirement", "corporate_shares", "other",
}

OWNER_VALUES = {"husband", "wife", "joint"}


def _validate(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("入力は JSON オブジェクト")

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError("assets はリスト（空配列可）")
    for i, a in enumerate(assets):
        if not isinstance(a, dict):
            raise ValueError(f"assets[{i}] はオブジェクト")
        v = a.get("value")
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"assets[{i}].value は 0 以上の整数")
        if a.get("owner") not in OWNER_VALUES:
            raise ValueError(f"assets[{i}].owner は {sorted(OWNER_VALUES)} のいずれか")
        if a.get("asset_type") and a["asset_type"] not in ASSET_TYPES:
            raise ValueError(f"assets[{i}].asset_type は {sorted(ASSET_TYPES)} のいずれか")

    debts = payload.get("shared_debts", [])
    if not isinstance(debts, list):
        raise ValueError("shared_debts はリスト")
    for i, d in enumerate(debts):
        v = d.get("amount") if isinstance(d, dict) else None
        if isinstance(v, bool) or not isinstance(v, int) or v is None or v < 0:
            raise ValueError(f"shared_debts[{i}].amount は 0 以上の整数")

    ratio = payload.get("contribution_ratio")
    if ratio is not None:
        if not isinstance(ratio, dict) or "husband" not in ratio or "wife" not in ratio:
            raise ValueError("contribution_ratio は {husband, wife} の dict")
        for k in ("husband", "wife"):
            v = ratio[k]
            if not isinstance(v, (int, float)) or v < 0:
                raise ValueError(f"contribution_ratio.{k} は 0 以上の数値")


def _parse_ratio(payload: dict) -> Dict[str, Fraction]:
    r = payload.get("contribution_ratio")
    if not r:
        return {"husband": Fraction(1, 2), "wife": Fraction(1, 2)}
    h = Fraction(r["husband"]).limit_denominator(1000)
    w = Fraction(r["wife"]).limit_denominator(1000)
    total = h + w
    if total == 0:
        raise ValueError("contribution_ratio の合計が 0")
    return {"husband": h / total, "wife": w / total}


def compute(payload: dict) -> dict:
    _validate(payload)

    assets = payload.get("assets", [])
    debts = payload.get("shared_debts", [])
    ratio = _parse_ratio(payload)

    # F-030: 債務負担モード（既定は資産保有比率に応じた proportional 按分）
    # 実務では当事者合意で個別に決めることが多いため、mode を選択肢で提供する:
    #   "proportional" (既定) — 各当事者の共有資産保有量に比例して按分
    #   "equal"       — 50:50 で等分
    #   "husband_only" — 夫が全額負担
    #   "wife_only"   — 妻が全額負担
    #   "ratio"       — contribution_ratio と同比率で按分
    debt_mode = (payload.get("options") or {}).get("joint_debt_mode", "proportional")
    valid_modes = {"proportional", "equal", "husband_only", "wife_only", "ratio"}
    if debt_mode not in valid_modes:
        raise ValueError(
            f"joint_debt_mode は {sorted(valid_modes)} のいずれか（受信: {debt_mode!r}）"
        )

    shared_assets: List[dict] = []
    special_assets: List[dict] = []
    husband_shared_total = Fraction(0)
    wife_shared_total = Fraction(0)
    joint_shared_total = Fraction(0)

    for a in assets:
        is_special = bool(a.get("is_special_property", False))
        value = Fraction(a["value"])
        owner = a["owner"]
        entry = {
            "name": a.get("name", a.get("asset_type", "unnamed")),
            "asset_type": a.get("asset_type", "other"),
            "value": int(value),
            "owner": owner,
            "is_special": is_special,
            "special_reason": a.get("special_reason", ""),
        }
        if is_special:
            special_assets.append(entry)
            continue
        shared_assets.append(entry)
        if owner == "husband":
            husband_shared_total += value
        elif owner == "wife":
            wife_shared_total += value
        else:  # joint
            joint_shared_total += value

    total_shared_assets = (
        husband_shared_total + wife_shared_total + joint_shared_total
    )
    total_debts = sum(Fraction(d["amount"]) for d in debts)
    net_shared = total_shared_assets - total_debts

    if net_shared < 0:
        return {
            "summary": {
                "total_shared_assets": int(total_shared_assets),
                "total_debts": int(total_debts),
                "net_shared_assets": int(net_shared),
                "husband_should_get": 0,
                "wife_should_get": 0,
                "husband_current_holdings": int(husband_shared_total + joint_shared_total / 2),
                "wife_current_holdings": int(wife_shared_total + joint_shared_total / 2),
                "settlement_from_husband_to_wife": 0,
                "settlement_from_wife_to_husband": 0,
            },
            "note": "債務超過のため財産分与の対象となる財産がない",
            "warnings": ["債務超過: 財産分与の代わりに債務分担の協議が必要"],
            "special_assets": special_assets,
            "shared_assets": shared_assets,
        }

    husband_should_get = net_shared * ratio["husband"]
    wife_should_get = net_shared * ratio["wife"]

    # 名義 joint は 50:50 で按分（分与前の暫定帰属）
    husband_raw = husband_shared_total + joint_shared_total / 2
    wife_raw = wife_shared_total + joint_shared_total / 2

    # F-030: 債務負担 mode による実効現有額の計算
    if debt_mode == "proportional":
        # 既定: 資産保有比率に応じて按分。
        if total_shared_assets > 0:
            scale = net_shared / total_shared_assets
            husband_current = husband_raw * scale
            wife_current = wife_raw * scale
        else:
            husband_current = Fraction(0)
            wife_current = Fraction(0)
    elif debt_mode == "equal":
        husband_current = husband_raw - total_debts / 2
        wife_current = wife_raw - total_debts / 2
    elif debt_mode == "husband_only":
        husband_current = husband_raw - total_debts
        wife_current = wife_raw
    elif debt_mode == "wife_only":
        husband_current = husband_raw
        wife_current = wife_raw - total_debts
    else:  # ratio
        husband_current = husband_raw - total_debts * ratio["husband"]
        wife_current = wife_raw - total_debts * ratio["wife"]

    # 清算金: 取得すべき額 - 現有額 = 不足分
    # 正 → 相手から受取、負 → 相手へ支払
    husband_settlement = husband_should_get - husband_current

    if husband_settlement > 0:
        # 夫が不足 → 妻から受け取る
        settlement_from_wife_to_husband = int(husband_settlement)
        settlement_from_husband_to_wife = 0
    else:
        settlement_from_wife_to_husband = 0
        settlement_from_husband_to_wife = int(-husband_settlement)

    return {
        "summary": {
            "total_shared_assets": int(total_shared_assets),
            "total_debts": int(total_debts),
            "net_shared_assets": int(net_shared),
            "contribution_ratio": {
                "husband": f"{ratio['husband'].numerator}/{ratio['husband'].denominator}",
                "wife": f"{ratio['wife'].numerator}/{ratio['wife'].denominator}",
            },
            "husband_should_get": int(husband_should_get),
            "wife_should_get": int(wife_should_get),
            "husband_current_holdings": int(husband_current),
            "wife_current_holdings": int(wife_current),
            "settlement_from_husband_to_wife": settlement_from_husband_to_wife,
            "settlement_from_wife_to_husband": settlement_from_wife_to_husband,
        },
        "shared_assets": shared_assets,
        "special_assets": special_assets,
        "joint_debt_mode": debt_mode,
        "notes": [
            "民法 768 条に基づく財産分与計算（清算的部分のみ）",
            "特有財産（婚姻前財産・相続/贈与財産）は分与対象外（民法 762 条 1 項）",
            "既定貢献度は 50:50。医師・経営者等で差を認める場合は contribution_ratio を指定",
            f"共有債務の負担モード: {debt_mode}。民法 761・762 条は共有債務の配分を定めず、当事者合意で決めるのが実務。options.joint_debt_mode で選択可能（proportional/equal/husband_only/wife_only/ratio）",
            "不動産の評価額は時価（査定書・路線価）を用いる",
            "年金分割は別途計算（厚生年金保険法 78 条の 2）",
            "慰謝料的・扶養的財産分与は本計算器の対象外",
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
        result = compute(payload)
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.pretty:
        _print_pretty(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    _emit_footer()
    return 0


def _emit_footer() -> None:
    """v3.3.0-iter3〜: §72 disclaimer を stderr に JSON で emit する。"""
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "_lib"))
    try:
        from calc_footer import emit_footer
        emit_footer(
            skill="property-division-calc",
            statute="民法 §768（財産分与、清算的部分のみ）",
            caveats=[
                "慰謝料的財産分与・扶養的財産分与",
                "年金分割（厚年法 §78-2）",
                "特有財産の判定（相続・贈与・婚姻前取得）",
                "不動産の時価評価（査定書・路線価等）",
                "退職金のうち婚姻期間中増加分の按分",
                "債務の按分方式は 5 種類から選択しており、選択次第で結果が大きく変わる",
            ],
        )
    except ImportError:
        pass


def _print_pretty(result: dict) -> None:
    s = result["summary"]
    print("\n## 離婚財産分与計算結果（民法 768 条）\n")
    print(f"  夫婦共有財産合計    : {s['total_shared_assets']:>12,} 円")
    print(f"  共有債務            : {s['total_debts']:>12,} 円")
    print(f"  分与対象財産        : {s['net_shared_assets']:>12,} 円")
    if "contribution_ratio" in s:
        print(f"  貢献度（夫）        : {s['contribution_ratio']['husband']}")
        print(f"  貢献度（妻）        : {s['contribution_ratio']['wife']}")
        print(f"  夫が取得すべき額    : {s['husband_should_get']:>12,} 円")
        print(f"  妻が取得すべき額    : {s['wife_should_get']:>12,} 円")
        print(f"  夫の現有共有財産    : {s['husband_current_holdings']:>12,} 円")
        print(f"  妻の現有共有財産    : {s['wife_current_holdings']:>12,} 円")
    print(f"  ═══════════════════════════════════")
    if s["settlement_from_husband_to_wife"] > 0:
        print(f"  ★ 夫 → 妻 清算金   : {s['settlement_from_husband_to_wife']:>12,} 円")
    elif s["settlement_from_wife_to_husband"] > 0:
        print(f"  ★ 妻 → 夫 清算金   : {s['settlement_from_wife_to_husband']:>12,} 円")
    else:
        print(f"  ★ 清算金             : 発生なし")
    if result.get("special_assets"):
        print(f"\n  特有財産（分与対象外）: {len(result['special_assets'])} 件")


def main() -> int:
    ap = argparse.ArgumentParser(description="離婚財産分与計算（民法 768 条）")
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
