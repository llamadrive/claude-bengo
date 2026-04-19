#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""未払残業代計算モジュール（労基法 37 条準拠）。

月別の労働時間記録から、労働基準法 37 条に基づく割増賃金の未払額を
決定論的に計算する。時効（3 年）内外も区別する。

## 関連条文・基準

- 労働基準法 32 条: 法定労働時間（1 日 8 時間・1 週 40 時間）
- 労働基準法 37 条: 割増賃金（時間外 1.25 倍、深夜 1.25 倍、休日 1.35 倍）
- 労働基準法施行規則 20 条: 1 時間あたり賃金の算定方法
- 労働基準法 115 条: 賃金請求権の時効 3 年（2020/04 改正後）
- 労働基準法 37 条 1 項但書: 月 60 時間超の時間外は 1.5 倍（2023/04 中小適用）

## 割増率

| 種別 | 割増率 |
|---|---|
| 法定時間外（月 60 時間以下） | 1.25 倍 |
| 法定時間外（月 60 時間超） | 1.5 倍 |
| 深夜（22:00-05:00）単独 | 1.25 倍 |
| 法定時間外＋深夜 | 1.5 倍 |
| 法定時間外＋深夜（60 時間超） | 1.75 倍 |
| 法定休日 | 1.35 倍 |
| 法定休日＋深夜 | 1.6 倍 |

## 基礎賃金の算定

1 時間あたり賃金 = 月額賃金 / 1 ヶ月平均所定労働時間

1 ヶ月平均所定労働時間 = (365 - 年間休日) × 1 日所定労働時間 / 12

控除対象: 家族手当・通勤手当・住宅手当（手当の内容によっては控除しない場合あり）

## 対応範囲外

- 固定残業代（みなし残業代）の控除計算
- 年俸制の割増賃金
- 管理監督者（労基法 41 条 2 号）の例外
- 裁量労働制・事業場外労働のみなし時間
- 変形労働時間制（1 ヶ月単位・1 年単位）
- 家族手当等の詳細な除外判定（UI 上 annual_deductions で一括控除扱い）
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from fractions import Fraction
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 割増率（労基法 37 条、2023/04 中小適用の 60 時間超対応）
# ---------------------------------------------------------------------------

RATE_OVERTIME = Fraction(125, 100)            # 時間外（〜60h/月）
RATE_OVERTIME_OVER_60 = Fraction(150, 100)    # 時間外（60h/月 超）
RATE_NIGHT = Fraction(125, 100)               # 深夜単独（時間外なし）
RATE_OVERTIME_NIGHT = Fraction(150, 100)      # 時間外＋深夜
RATE_OVERTIME_NIGHT_OVER_60 = Fraction(175, 100)  # 時間外（60h超）＋深夜
RATE_HOLIDAY = Fraction(135, 100)             # 法定休日
RATE_HOLIDAY_NIGHT = Fraction(160, 100)       # 法定休日＋深夜

# 遅延損害金の利率
DELAY_INTEREST_RATE = Fraction(3, 100)  # 年 3%（改正民法 404 条）

# 時効（賃金請求権）— 労基法 115 条
#
# 2020/04/01 改正で 2 年 → 3 年に延長された。境界は賃金の「支払期日」基準で、
# 支払期日が 2020/04/01 以降の請求権は 3 年、それ以前は旧法の 2 年。
# 混在ケースでは記録ごとに時効期間が異なるため、per-record で判定する。
STATUTE_YEARS_POST_2020 = 3
STATUTE_YEARS_PRE_2020 = 2
STATUTE_CHANGE_DATE = _dt.date(2020, 4, 1)


def _statute_years_for_payday(payday: _dt.date) -> int:
    """支払期日に適用する時効年数を返す（2020/04/01 境界）。"""
    return STATUTE_YEARS_POST_2020 if payday >= STATUTE_CHANGE_DATE else STATUTE_YEARS_PRE_2020


def _subtract_years(d: _dt.date, years: int) -> _dt.date:
    """日付から N 年引く（うるう年の 2/29 → 2/28 に落とす安全版）。"""
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


# ---------------------------------------------------------------------------
# 1 時間あたり賃金の算定
# ---------------------------------------------------------------------------


def _calc_hourly_wage(monthly_salary: int, monthly_scheduled_hours: Fraction) -> int:
    """月額賃金 ÷ 1 ヶ月平均所定労働時間 = 1 時間あたり賃金（円、小数切り上げ）。"""
    if monthly_scheduled_hours <= 0:
        raise ValueError("monthly_scheduled_hours は正の値")
    hourly = Fraction(monthly_salary) / monthly_scheduled_hours
    # 労基則 19 条の趣旨から小数は切り上げ
    if hourly.denominator == 1:
        return int(hourly.numerator)
    return int(hourly.numerator // hourly.denominator) + 1


def _calc_monthly_scheduled_hours(annual_holidays: int, daily_hours: Fraction) -> Fraction:
    """1 ヶ月平均所定労働時間 = (365 - 年間休日) × 1日所定労働時間 / 12."""
    working_days = 365 - annual_holidays
    return Fraction(working_days) * daily_hours / Fraction(12)


# ---------------------------------------------------------------------------
# バリデーション
# ---------------------------------------------------------------------------


def _validate(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("入力は JSON オブジェクト")

    emp = payload.get("employee")
    if not isinstance(emp, dict):
        raise ValueError("employee フィールドが必要")

    salary = emp.get("monthly_salary")
    if not isinstance(salary, int) or salary <= 0:
        raise ValueError(f"employee.monthly_salary は正の整数（受信: {salary}）")

    wh = payload.get("work_hours", {})
    if "monthly_scheduled_hours" not in wh and (
        "annual_holidays" not in wh or "daily_scheduled_hours" not in wh
    ):
        raise ValueError(
            "work_hours は monthly_scheduled_hours か "
            "(annual_holidays + daily_scheduled_hours) のいずれかが必要"
        )

    records = payload.get("monthly_records", [])
    if not isinstance(records, list) or not records:
        raise ValueError("monthly_records は空でないリストが必要")

    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise ValueError(f"monthly_records[{i}] はオブジェクト")
        ym = r.get("year_month")
        try:
            parts = ym.split("-")
            int(parts[0])
            int(parts[1])
        except (AttributeError, IndexError, ValueError):
            raise ValueError(f"monthly_records[{i}].year_month は YYYY-MM 形式")

        for key in (
            "legal_overtime_h", "overtime_over_60_h", "night_h",
            "overtime_night_h", "overtime_night_over_60_h",
            "holiday_h", "holiday_night_h",
        ):
            v = r.get(key, 0)
            if not isinstance(v, (int, float)) or v < 0:
                raise ValueError(f"monthly_records[{i}].{key} は 0 以上の数値")

        # F-025: legal_overtime_h と overtime_over_60_h は disjoint でなければ
        # ならない。ユーザーが total_overtime を legal_overtime_h に入れて
        # さらに over_60 を重複設定する double-count バグを防ぐ。
        lot = r.get("legal_overtime_h", 0) or 0
        ot60 = r.get("overtime_over_60_h", 0) or 0
        if ot60 > 0 and lot > 60:
            raise ValueError(
                f"monthly_records[{i}]: legal_overtime_h ({lot}) は月 60 時間以下の"
                f"時間外のみを指すため、overtime_over_60_h ({ot60}) と併用するときは "
                "60 以下である必要がある。合計 70 時間なら legal_overtime_h=60, "
                "overtime_over_60_h=10 と分割指定してほしい。"
            )


# ---------------------------------------------------------------------------
# メイン計算
# ---------------------------------------------------------------------------


def compute(payload: dict) -> dict:
    """未払残業代を計算する。"""
    _validate(payload)

    emp = payload["employee"]
    wh = payload.get("work_hours", {})

    monthly_salary = emp["monthly_salary"]
    if "monthly_scheduled_hours" in wh:
        monthly_hours = Fraction(str(wh["monthly_scheduled_hours"]))
    else:
        annual_holidays = int(wh["annual_holidays"])
        daily_hours = Fraction(str(wh["daily_scheduled_hours"]))
        monthly_hours = _calc_monthly_scheduled_hours(annual_holidays, daily_hours)

    hourly_wage = _calc_hourly_wage(monthly_salary, monthly_hours)

    # 時効判定（労基法 115 条）: 賃金支払期日から per-record で時効年数を決める。
    # 支払期日 ≥ 2020/04/01 なら 3 年、それ以前は旧法の 2 年。
    # options.statute_years が明示指定された場合は上書き（特殊事案用の escape hatch）。
    options = payload.get("options") or {}
    statute_override = options.get("statute_years")
    filing_date_str = options.get("filing_date")
    if filing_date_str:
        filing_date = _dt.date.fromisoformat(filing_date_str)
    else:
        filing_date = _dt.date.today()

    per_month: List[dict] = []
    total_within_statute = Fraction(0)
    total_outside_statute = Fraction(0)

    for rec in payload["monthly_records"]:
        ym = rec["year_month"]
        year, month = [int(x) for x in ym.split("-")]
        ym_date = _dt.date(year, month, 1)

        # per-record 時効: 支払期日（月末近似）から適用年数を決定
        if statute_override is not None:
            rec_statute_years = int(statute_override)
        else:
            # 実務上「支払期日」は通常その月の末日以降。境界判定では
            # 月初日を payday proxy として使う（保守的に古い側に倒す）。
            rec_statute_years = _statute_years_for_payday(ym_date)
        rec_cutoff = _subtract_years(filing_date, rec_statute_years).replace(day=1)

        ot = Fraction(str(rec.get("legal_overtime_h", 0)))
        ot60 = Fraction(str(rec.get("overtime_over_60_h", 0)))
        night = Fraction(str(rec.get("night_h", 0)))
        ot_night = Fraction(str(rec.get("overtime_night_h", 0)))
        ot_night_60 = Fraction(str(rec.get("overtime_night_over_60_h", 0)))
        holiday = Fraction(str(rec.get("holiday_h", 0)))
        holiday_night = Fraction(str(rec.get("holiday_night_h", 0)))

        # 各区分の割増賃金
        # 時間外（60h 以下）: wage × 1.25 に対する割増「分」のみではなく、
        # 労基法 37 条 は「時間外労働時間そのものに対する割増計算」だが、
        # 実務は「時間外時間 × 1.25 × hourly」全額を請求する。本計算器も
        # 未払額として全額（通常賃金分も含めた 1.25 倍）を算出する。
        # ただし "night_h"（深夜単独）は通常の所定内労働時間中の深夜労働を
        # 想定し、割増分 0.25 のみを計算する（通常賃金は既払と仮定）。
        amounts = {
            "overtime_normal": ot * Fraction(hourly_wage) * RATE_OVERTIME,
            "overtime_over_60": ot60 * Fraction(hourly_wage) * RATE_OVERTIME_OVER_60,
            "night_only_surcharge": night * Fraction(hourly_wage) * (RATE_NIGHT - Fraction(1)),
            "overtime_night": ot_night * Fraction(hourly_wage) * RATE_OVERTIME_NIGHT,
            "overtime_night_over_60": ot_night_60 * Fraction(hourly_wage) * RATE_OVERTIME_NIGHT_OVER_60,
            "holiday": holiday * Fraction(hourly_wage) * RATE_HOLIDAY,
            "holiday_night": holiday_night * Fraction(hourly_wage) * RATE_HOLIDAY_NIGHT,
        }
        month_total = sum(amounts.values(), Fraction(0))

        in_statute = ym_date >= rec_cutoff
        if in_statute:
            total_within_statute += month_total
        else:
            total_outside_statute += month_total

        per_month.append({
            "year_month": ym,
            "hours": {
                "legal_overtime_h": float(ot),
                "overtime_over_60_h": float(ot60),
                "night_h": float(night),
                "overtime_night_h": float(ot_night),
                "overtime_night_over_60_h": float(ot_night_60),
                "holiday_h": float(holiday),
                "holiday_night_h": float(holiday_night),
            },
            "amount": int(month_total),
            "within_statute": in_statute,
            "statute_years_applied": rec_statute_years,
            "breakdown": {k: int(v) for k, v in amounts.items() if v > 0},
        })

    # 遅延損害金（オプション）
    delay = Fraction(0)
    delay_detail = {}
    if options.get("include_delay_interest"):
        # F-029: payday_day_of_month を options で指定可（既定 28）。翌月 25 日
        # など事務所ごとに異なる支払期日を反映できる。
        payday_dom = int(options.get("payday_day_of_month", 28))
        if not (1 <= payday_dom <= 31):
            raise ValueError(
                f"options.payday_day_of_month は 1-31（受信: {payday_dom}）"
            )
        delay_detail = {
            "rate": "年 3%",
            "payday_day_of_month": payday_dom,
            "note": f"各月 {payday_dom} 日を支払期日とみなして、filing_date までの利息を概算",
        }
        for m in per_month:
            if not m["within_statute"]:
                continue
            year, month = [int(x) for x in m["year_month"].split("-")]
            # その月に該当日がなければ月末日に丸める
            try:
                wage_date = _dt.date(year, month, payday_dom)
            except ValueError:
                if month == 12:
                    wage_date = _dt.date(year + 1, 1, 1) - _dt.timedelta(days=1)
                else:
                    wage_date = _dt.date(year, month + 1, 1) - _dt.timedelta(days=1)
            days = (filing_date - wage_date).days
            if days <= 0:
                continue
            delay += Fraction(m["amount"]) * DELAY_INTEREST_RATE * Fraction(days, 365)

    # 記録ごとに適用した時効年数のユニーク値
    statute_years_values = sorted({m["statute_years_applied"] for m in per_month})

    return {
        "summary": {
            "monthly_salary": monthly_salary,
            "monthly_scheduled_hours": float(monthly_hours),
            "hourly_wage": hourly_wage,
            "statute_years_applied": statute_years_values if len(statute_years_values) > 1 else (statute_years_values[0] if statute_years_values else STATUTE_YEARS_POST_2020),
            "statute_override": statute_override,
            "filing_date": filing_date.isoformat(),
            "total_unpaid_within_statute": int(total_within_statute),
            "total_unpaid_outside_statute": int(total_outside_statute),
            "total_unpaid_all": int(total_within_statute + total_outside_statute),
            "delay_interest": int(delay),
            "grand_total_claimable": int(total_within_statute + delay),
        },
        "per_month": per_month,
        "delay_interest_detail": delay_detail,
        "notes": [
            "労働基準法 37 条に基づく割増賃金の計算",
            "割増率: 時間外 1.25 / 60h超 1.5 / 深夜 +0.25 / 休日 1.35",
            "基礎賃金: 月額 ÷ 1 ヶ月平均所定労働時間",
            "時効（労基法 115 条）: 支払期日が 2020/04/01 以降は 3 年、それ以前は旧法の 2 年。記録ごとに自動判定（options.statute_years で明示上書き可）",
            "固定残業代・管理監督者例外・みなし労働時間等の特殊事情は未対応",
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
    return 0


def _print_pretty(result: dict) -> None:
    s = result["summary"]
    print("\n## 未払残業代計算結果（労基法 37 条）\n")
    print(f"  月額賃金              : {s['monthly_salary']:>12,} 円")
    print(f"  1 ヶ月平均所定労働時間: {s['monthly_scheduled_hours']:>12.2f} 時間")
    print(f"  1 時間あたり賃金      : {s['hourly_wage']:>12,} 円/時")
    sy = s['statute_years_applied']
    sy_str = f"{sy} 年" if isinstance(sy, int) else f"{'/'.join(str(x) for x in sy)} 年（境界跨ぎ）"
    print(f"  時効（年）            : {sy_str:>12}")
    print(f"  時効起算              : {s['statute_cutoff']}")
    print()
    print(f"  時効内未払額          : {s['total_unpaid_within_statute']:>12,} 円")
    if s['total_unpaid_outside_statute'] > 0:
        print(f"  時効超過分            : {s['total_unpaid_outside_statute']:>12,} 円（請求不可）")
    if s['delay_interest'] > 0:
        print(f"  遅延損害金（年3%）    : {s['delay_interest']:>12,} 円")
    print(f"  ═══════════════════════════════════")
    print(f"  ★ 請求可能額合計     : {s['grand_total_claimable']:>12,} 円")


def main() -> int:
    ap = argparse.ArgumentParser(description="未払残業代計算（労基法 37 条）")
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
