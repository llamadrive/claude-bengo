#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""利息制限法引き直し計算モジュール。

本スクリプトは、貸金業者との取引履歴（借入・弁済）を利息制限法の上限利率で
再計算し、真の元本残高・支払済利息・過払金額を決定論的に算出する。
いわゆる「引き直し計算」の自動化。

## 関連条文・基準

- 利息制限法 1 条（利息の最高限度）:
  - 元本 10 万円未満: 年 20%
  - 元本 10 万円以上 100 万円未満: 年 18%
  - 元本 100 万円以上: 年 15%
- 改正利息制限法（平成 22 年 6 月 18 日施行）: グレーゾーン金利を廃止
- 出資法 5 条 2 項: 年 20% 超の貸付を処罰（平成 22 年改正後）
- 最高裁 平成 18 年 1 月 13 日判決（シティズ事件）: みなし弁済要件の厳格化
- 民法 404 条: 法定利率 年 3%（2020/04/01 以降の過払金請求に適用）
- 商法 514 条: 旧商事法定利率 年 6%（2020/03/31 以前）
- 民法 704 条: 悪意の受益者（業者）は年 5% の利息付きで返還

## 計算アルゴリズム（引き直し計算の標準的手順）

1. 取引を日付順にソート
2. 各取引間の経過日数分の利息を計算:
   - 利息 = 残元本 × 利率（残高に応じた上限） × 日数 / 365
3. 取引処理:
   - 弁済: まず未払利息から控除し、残額を元本に充当
   - 借入: まず未払利息を充当し、残額を元本に加算
4. 残元本がマイナスになれば過払金発生
5. 過払金には民法 704 条に基づき年 5% の利息（悪意の受益者）
6. 過払金利息の起算日: 各過払発生日

## 対応範囲外

- 取引の一部が不明な場合の推計計算（満額推定等）
- 貸付残高が 100 万を跨ぐ利率遷移の細かい判例解釈（本器は残高基準で判定）
- 2020/04/01 を跨ぐ事案での法定利率切替（本器は統一して年 5% を使用、
  民法 704 条の「悪意の受益者」は従前実務で年 5%）
- 一部弁済の充当順序の特約がある場合（本器は利息優先充当を使用）
- 過払金の相殺（別口座間での充当）
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 利息制限法の上限利率（利息制限法 1 条）
# ---------------------------------------------------------------------------

def _rate_for_principal(principal: int) -> Fraction:
    """残元本に応じた利息制限法の上限利率を返す。"""
    if principal < 100_000:
        return Fraction(20, 100)  # 年 20%
    elif principal < 1_000_000:
        return Fraction(18, 100)  # 年 18%
    else:
        return Fraction(15, 100)  # 年 15%


# 過払金に対する利息（民法 704 条・悪意の受益者）
OVERPAYMENT_INTEREST_RATE = Fraction(5, 100)  # 年 5%


# ---------------------------------------------------------------------------
# バリデーション
# ---------------------------------------------------------------------------


VALID_TYPES = {"borrowing", "payment"}


def _validate(payload: dict) -> List[dict]:
    """入力を検証し、日付降昇順でソート済みの取引リストを返す。"""
    if not isinstance(payload, dict):
        raise ValueError("入力は JSON オブジェクトでなければならない。")

    transactions = payload.get("transactions", [])
    if not isinstance(transactions, list) or not transactions:
        raise ValueError("transactions は空でないリストが必要")

    normalized = []
    for i, t in enumerate(transactions):
        if not isinstance(t, dict):
            raise ValueError(f"transactions[{i}] はオブジェクトでなければならない")
        try:
            date = _dt.date.fromisoformat(t["date"])
        except (KeyError, ValueError):
            raise ValueError(f"transactions[{i}].date は YYYY-MM-DD 形式")
        ttype = t.get("type")
        if ttype not in VALID_TYPES:
            raise ValueError(f"transactions[{i}].type は 'borrowing' または 'payment'")
        amount = t.get("amount")
        # bool は int のサブクラスだが取引金額として意味をなさないため除外
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise ValueError(
                f"transactions[{i}].amount は正の整数が必要（bool/float 不可、受信: {amount!r}）"
            )
        normalized.append({"date": date, "type": ttype, "amount": amount})

    # 日付昇順、同一日は借入→弁済の順に
    normalized.sort(key=lambda t: (t["date"], 0 if t["type"] == "borrowing" else 1))
    return normalized


# ---------------------------------------------------------------------------
# 引き直し計算
# ---------------------------------------------------------------------------


def recalculate(payload: dict) -> dict:
    """取引履歴を利息制限法で引き直す。"""
    transactions = _validate(payload)

    # 状態
    principal = Fraction(0)  # 残元本
    accrued_interest = Fraction(0)  # 未払利息
    last_date: Optional[_dt.date] = None
    ledger: List[dict] = []

    # 過払金発生時の追跡（過払金ごとに利息を付けるため）
    overpayment_events: List[dict] = []  # {date, amount}

    total_paid_interest = Fraction(0)

    for t in transactions:
        date = t["date"]
        ttype = t["type"]
        amount = Fraction(t["amount"])

        # 前回取引日から今回取引日までの利息を計算
        interest_accrued_this_period = Fraction(0)
        days = 0
        rate_used = Fraction(0)
        if last_date is not None and principal > 0:
            days = (date - last_date).days
            if days > 0:
                rate_used = _rate_for_principal(int(principal))
                interest_accrued_this_period = principal * rate_used * Fraction(days, 365)
                accrued_interest += interest_accrued_this_period
        last_date = date

        entry = {
            "date": date.isoformat(),
            "type": ttype,
            "amount": int(amount),
            "days_since_last": days,
            "rate_applied": f"{float(rate_used)*100:.1f}%" if rate_used > 0 else "—",
            "interest_accrued_this_period": int(interest_accrued_this_period),
        }

        if ttype == "borrowing":
            # 借入: 未払利息を新借入金で弁済し、余った分を元本に加算
            if accrued_interest > 0 and amount >= accrued_interest:
                total_paid_interest += accrued_interest
                amount -= accrued_interest
                accrued_interest = Fraction(0)
            elif accrued_interest > 0:
                # 借入額が利息に満たない場合（通常あり得ないが念のため）
                accrued_interest -= amount
                amount = Fraction(0)
            principal += amount
        else:  # payment
            # 弁済: まず未払利息、次に元本
            if amount <= accrued_interest:
                accrued_interest -= amount
                total_paid_interest += amount
                amount = Fraction(0)
            else:
                total_paid_interest += accrued_interest
                amount -= accrued_interest
                accrued_interest = Fraction(0)
                # 残元本より多く払った場合は過払金
                if amount > principal:
                    overpayment_amount = amount - principal
                    principal = Fraction(0)
                    overpayment_events.append({
                        "date": date,
                        "amount": int(overpayment_amount),
                    })
                    entry["overpayment_this_tx"] = int(overpayment_amount)
                else:
                    principal -= amount
                amount = Fraction(0)

        entry["balance_after"] = int(principal)
        entry["accrued_interest_after"] = int(accrued_interest)
        ledger.append(entry)

    # 過払金の利息計算（最終取引日時点まで、年 5%）
    final_date = transactions[-1]["date"]
    overpayment_principal = sum(e["amount"] for e in overpayment_events)
    overpayment_interest = Fraction(0)
    for e in overpayment_events:
        days_until_final = (final_date - e["date"]).days
        if days_until_final > 0:
            interest = Fraction(e["amount"]) * OVERPAYMENT_INTEREST_RATE * Fraction(
                days_until_final, 365
            )
            overpayment_interest += interest

    remaining_principal = int(principal)
    remaining_interest = int(accrued_interest)

    # ===== 結果生成 =====
    result = {
        "summary": {
            "final_date": final_date.isoformat(),
            "remaining_principal": remaining_principal,
            "remaining_accrued_interest": remaining_interest,
            "remaining_debt_total": remaining_principal + remaining_interest,
            "total_interest_paid_under_risokuhou": int(total_paid_interest),
            "overpayment_principal": overpayment_principal,
            "overpayment_interest_5pct": int(overpayment_interest),
            "overpayment_total": overpayment_principal + int(overpayment_interest),
        },
        "overpayment_events": [
            {"date": e["date"].isoformat(), "amount": e["amount"]}
            for e in overpayment_events
        ],
        "ledger": ledger,
        "notes": [
            "利息制限法 1 条の上限利率（20%/18%/15%）で再計算",
            "残高に応じて利率を自動判定（10 万/100 万の境界）",
            "弁済は未払利息優先充当",
            "過払金には民法 704 条（悪意の受益者）に基づき年 5% の利息付加",
            "2020/04 改正後の新規事案でも従前実務に従い過払金利息は年 5% を使用",
            "実際の請求訴訟では、業者側の悪意の立証が必要",
        ],
    }
    return result


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
            print(json.dumps({"error": f"stdin 不正: {e}"}, ensure_ascii=False), file=sys.stderr)
            return 1

    try:
        result = recalculate(payload)
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.pretty:
        _print_pretty(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _print_pretty(result: dict) -> None:
    s = result["summary"]
    print("\n## 利息制限法 引き直し計算結果\n")
    print(f"  最終取引日            : {s['final_date']}")
    print(f"  残元本                : {s['remaining_principal']:>12,} 円")
    print(f"  未払利息（最終時点）  : {s['remaining_accrued_interest']:>12,} 円")
    print(f"  残債務合計            : {s['remaining_debt_total']:>12,} 円")
    print(f"  支払済利息（引直後）  : {s['total_interest_paid_under_risokuhou']:>12,} 円")
    if s["overpayment_principal"] > 0:
        print()
        print(f"  過払金元本            : {s['overpayment_principal']:>12,} 円")
        print(f"  過払金利息（年5%）    : {s['overpayment_interest_5pct']:>12,} 円")
        print(f"  ★ 過払金返還請求額   : {s['overpayment_total']:>12,} 円")
    print(f"\n  取引件数              : {len(result['ledger']):>12}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="利息制限法 引き直し計算")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("calc", help="取引履歴を利息制限法で引き直し")
    p.add_argument("--input", help="入力 JSON ファイル")
    p.add_argument("--json", help="入力 JSON 文字列")
    p.add_argument("--pretty", action="store_true", help="人間可読形式で出力")

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
