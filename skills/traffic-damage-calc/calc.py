#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交通事故損害賠償計算モジュール（赤い本基準）。

本スクリプトは、交通事故の被害者側損害賠償額を、日弁連交通事故相談センター
東京支部編「民事交通事故訴訟損害賠償額算定基準」（通称「赤い本」）の基準に
従い決定論的に計算するCLIツールである。LLM の推論ではなく、判例・実務で
確立した計算式と表値を用いる。

## 計算対象

1. **積極損害（治療等の実費）**
   - 治療費・通院交通費・装具費・入院雑費・付添看護費

2. **消極損害（得べかりし利益）**
   - 休業損害
   - 後遺障害逸失利益（Leibniz 係数を用いた年3%の中間利息控除）
   - 死亡逸失利益（生活費控除率を加味）

3. **慰謝料**
   - 入通院慰謝料（赤い本別表 I: 通常／別表 II: 他覚所見なし軽傷）
   - 後遺障害慰謝料（等級別）
   - 死亡慰謝料

4. **弁護士費用（損害元本の 10%、判例実務）**

5. **過失相殺（民法 722 条 2 項）**

## 関連条文・基準

- 民法 709 条（不法行為による損害賠償）
- 民法 710 条（非財産的損害の賠償）
- 民法 722 条 2 項（過失相殺）
- 自動車損害賠償保障法（自賠責との関係）
- 改正民法 404 条（2020/04/01〜の法定利率 3%）
- 赤い本別表 I／II（入通院慰謝料）
- 労災 14 級 1 号〜1 級 1 号（労働能力喪失率表）

## 入力スキーマ

```json
{
  "victim": {
    "name": "甲野太郎",
    "age_at_accident": 35,
    "gender": "male",
    "occupation_type": "salaried",
    "annual_income": 5000000,
    "is_household_supporter": true
  },
  "accident": {
    "date": "2024-04-01",
    "victim_fault_percent": 10
  },
  "medical": {
    "hospital_days": 30,
    "outpatient_days": 60,
    "outpatient_period_months": 6,
    "medical_fees": 1200000,
    "transportation": 50000,
    "equipment": 30000,
    "nursing_days_hospital": 10,
    "nursing_days_outpatient": 0,
    "severity": "major"
  },
  "lost_wages": {
    "days_off_work": 90,
    "daily_wage_override": null
  },
  "disability": {
    "grade": 12,
    "years_until_67": 32
  },
  "death": null,
  "options": {
    "include_lawyer_fee": true,
    "include_delay_interest": true,
    "settlement_date": "2026-04-17"
  }
}
```

## 対応範囲外（現バージョンでの明示的な非対応事項）

- 介護費用（将来介護）— 症状固定時の生活状況に大きく依存するため手計算推奨
- 家屋改造費・自動車改造費
- 損益相殺（自賠責既払額・労災・健康保険等）— 別途控除する運用を想定
- 物損（修理費・代車費・評価損）— 本計算器は人身損害に特化
- 定期金賠償
- 青本・任意保険基準（赤い本のみ）
- 赤い本別表 II（他覚所見なし軽傷） の詳細テーブル — 主要値のみ収録

これらは将来バージョンで対応予定である。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 定数・参照テーブル（赤い本 2024 年版準拠）
# ---------------------------------------------------------------------------

# 労働能力喪失率（労災保険法施行規則 別表第一に準拠。裁判実務で同値を使う）
DISABILITY_LOSS_RATES: Dict[int, Fraction] = {
    1: Fraction(100, 100),
    2: Fraction(100, 100),
    3: Fraction(100, 100),
    4: Fraction(92, 100),
    5: Fraction(79, 100),
    6: Fraction(67, 100),
    7: Fraction(56, 100),
    8: Fraction(45, 100),
    9: Fraction(35, 100),
    10: Fraction(27, 100),
    11: Fraction(20, 100),
    12: Fraction(14, 100),
    13: Fraction(9, 100),
    14: Fraction(5, 100),
}

# 後遺障害慰謝料（赤い本）
DISABILITY_CONSOLATION: Dict[int, int] = {
    1: 28_000_000,
    2: 23_700_000,
    3: 19_900_000,
    4: 16_700_000,
    5: 14_000_000,
    6: 11_800_000,
    7: 10_000_000,
    8: 8_300_000,
    9: 6_900_000,
    10: 5_500_000,
    11: 4_200_000,
    12: 2_900_000,
    13: 1_800_000,
    14: 1_100_000,
}

# 死亡慰謝料（赤い本）
DEATH_CONSOLATION = {
    "household_supporter": 28_000_000,  # 家計の主柱
    "mother_spouse": 25_000_000,        # 母親・配偶者
    "other": 22_000_000,                # その他（独身・子・高齢者等）
}

# 付添看護費（赤い本、1 日あたり円）
NURSING_FEE_HOSPITAL = 6500
NURSING_FEE_OUTPATIENT = 3300

# 入院雑費（赤い本、1 日あたり円）
HOSPITAL_MISC_PER_DAY = 1500

# 賃金センサス（主婦等の場合の基礎収入）
# 女性全年齢平均の直近値（令和4年: 約 399 万円）。年度更新可
# 参考: 厚生労働省「賃金構造基本統計調査」
WAGE_CENSUS_FEMALE_ALL_AGE = 3_990_000

# 生活費控除率（死亡逸失利益の控除）
LIVING_COST_DEDUCTION = {
    ("male", "household_supporter_multi"): Fraction(30, 100),  # 被扶養者 2 人以上
    ("male", "household_supporter_single"): Fraction(40, 100),  # 被扶養者 1 人
    ("male", "single"): Fraction(50, 100),
    ("female", "household_supporter"): Fraction(30, 100),
    ("female", "single"): Fraction(30, 100),
}

# 法定利率（中間利息控除・遅延損害金用）
# 改正民法 404 条: 2020/04/01 より年 3%、それ以前は年 5%。
# 事故日（不法行為時）によって分岐する — 赤い本 p. 375 ほか判例実務に従う。
LEGAL_INTEREST_RATE_POST_2020 = Fraction(3, 100)
LEGAL_INTEREST_RATE_PRE_2020 = Fraction(5, 100)
INTEREST_RATE_CHANGE_DATE = "2020-04-01"

# 互換のため旧シンボルも残す（事故日非依存で呼ばれる既存テスト用デフォルト）
LEGAL_INTEREST_RATE = LEGAL_INTEREST_RATE_POST_2020


def _rate_for_accident_date(accident_date: Optional[str]) -> Fraction:
    """事故日から適用法定利率を決定する。

    2020/04/01 以降の不法行為: 3%
    それより前: 5%
    日付が不明/不正な場合は 3%（直近判例基準）を返す。
    """
    if not accident_date:
        return LEGAL_INTEREST_RATE_POST_2020
    try:
        import datetime as _dt
        d = _dt.date.fromisoformat(accident_date)
    except (ValueError, TypeError):
        return LEGAL_INTEREST_RATE_POST_2020
    cutoff = _dt.date(2020, 4, 1)
    return LEGAL_INTEREST_RATE_POST_2020 if d >= cutoff else LEGAL_INTEREST_RATE_PRE_2020

# 弁護士費用（判例実務: 認容額の 10%）
LAWYER_FEE_RATE = Fraction(10, 100)


# ---------------------------------------------------------------------------
# 赤い本 入通院慰謝料表（簡易抜粋: 通院月数・入院月数クロス）
#
# 別表 I: 通常の傷害（他覚所見あり / 骨折等）
# 別表 II: 他覚所見なし軽症（むちうち等）
#
# 完全な表は 15 月 × 15 月の 225 セル。本実装は実務でよく使う範囲
# （通院 0-12 月 × 入院 0-12 月）をカバーする。
#
# 単位: 万円
# ---------------------------------------------------------------------------

# 別表 I（通院月数が列、入院月数が行）— 赤い本 2024 年版
# 行: 入院 0, 1, 2, 3, 4, 5, 6 月
# 列: 通院 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 月
_TABLE_I = [
    # 入院 0 月
    [0, 28, 52, 73, 90, 105, 116, 124, 132, 139, 145, 150, 154],
    # 入院 1 月
    [53, 77, 98, 115, 130, 141, 149, 157, 164, 170, 175, 179, 183],
    # 入院 2 月
    [101, 122, 139, 154, 166, 174, 182, 189, 195, 200, 205, 209, 213],
    # 入院 3 月
    [145, 162, 177, 188, 196, 204, 211, 217, 223, 228, 233, 237, 241],
    # 入院 4 月
    [184, 196, 208, 215, 222, 229, 236, 242, 248, 253, 258, 262, 266],
    # 入院 5 月
    [217, 228, 236, 244, 251, 258, 264, 270, 276, 281, 286, 290, 294],
    # 入院 6 月
    [244, 252, 260, 267, 273, 280, 286, 292, 298, 303, 308, 312, 316],
]

# 別表 II（軽傷用）— 赤い本 2024 年版。別表 I の約 3/4 〜 2/3
_TABLE_II = [
    # 入院 0 月
    [0, 19, 36, 53, 67, 79, 89, 97, 103, 109, 113, 117, 119],
    # 入院 1 月
    [35, 52, 69, 83, 95, 105, 113, 119, 125, 129, 133, 135, 137],
    # 入院 2 月
    [66, 83, 97, 109, 119, 127, 133, 139, 143, 147, 149, 151, 153],
    # 入院 3 月
    [92, 106, 118, 128, 136, 142, 148, 152, 156, 158, 160, 162, 164],
    # 入院 4 月
    [116, 128, 138, 146, 152, 158, 162, 166, 168, 170, 172, 174, 176],
    # 入院 5 月
    [135, 145, 153, 159, 165, 169, 173, 175, 177, 179, 181, 183, 184],
    # 入院 6 月
    [152, 160, 166, 172, 176, 180, 182, 184, 186, 187, 188, 189, 190],
]


def _consolation_lookup(table: List[List[int]], hospital_months: int, outpatient_months: int) -> int:
    """慰謝料テーブルから値を引く。月数は最大 6 月（入院）／12 月（通院）に clamp。"""
    h = max(0, min(hospital_months, len(table) - 1))
    o = max(0, min(outpatient_months, len(table[0]) - 1))
    return table[h][o] * 10_000  # 万円 → 円


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def _leibniz_coefficient(years: int, rate: Fraction = LEGAL_INTEREST_RATE_POST_2020) -> Fraction:
    """Leibniz 係数（中間利息控除）。

    年利 r, n 年分の現在価値係数 = Σ(1 / (1+r)^k) for k=1..n
    赤い本の Leibniz 係数表と一致する（年利 3% の場合）。
    """
    if years <= 0:
        return Fraction(0)
    one_plus_r = Fraction(1) + rate
    total = Fraction(0)
    term = Fraction(1)
    for _ in range(years):
        term = term / one_plus_r
        total = total + term
    return total


def _months_from_days(days: int) -> int:
    """日数を整数月に切り上げる（慰謝料表引き用、30 日 = 1 月の実務慣行）。"""
    if days <= 0:
        return 0
    return (days + 29) // 30


def _to_int(fraction: Fraction) -> int:
    """Fraction を円単位に丸める（銀行丸めではなく通常の四捨五入）。"""
    # Fraction -> float via // で整数除算していくが、大きな値で精度が落ちるので
    # 分子分母から直接計算
    if fraction.denominator == 1:
        return int(fraction.numerator)
    # 四捨五入
    numer = fraction.numerator
    denom = fraction.denominator
    sign = -1 if numer * denom < 0 else 1
    n = abs(numer)
    d = abs(denom)
    # n/d を四捨五入
    result = (n + d // 2) // d
    return sign * result


# ---------------------------------------------------------------------------
# バリデーション
# ---------------------------------------------------------------------------


def _validate(payload: dict) -> dict:
    """入力を正規化し、不整合があれば ValueError を投げる。"""
    if not isinstance(payload, dict):
        raise ValueError("入力は JSON オブジェクトでなければならない。")

    victim = payload.get("victim") or {}
    if not isinstance(victim, dict):
        raise ValueError("victim フィールドが不正。")

    age = victim.get("age_at_accident")
    if not isinstance(age, int) or not 0 <= age <= 120:
        raise ValueError(f"victim.age_at_accident は 0-120 の整数が必要（受信: {age}）")

    gender = victim.get("gender")
    if gender not in ("male", "female"):
        raise ValueError("victim.gender は 'male' か 'female'")

    occupation = victim.get("occupation_type")
    valid_occupations = {"salaried", "self_employed", "household", "student", "unemployed", "part_time"}
    if occupation not in valid_occupations:
        raise ValueError(f"victim.occupation_type は {sorted(valid_occupations)} のいずれか")

    fault = payload.get("accident", {}).get("victim_fault_percent", 0)
    if not isinstance(fault, (int, float)) or not 0 <= fault <= 100:
        raise ValueError(f"accident.victim_fault_percent は 0-100（受信: {fault}）")

    disability = payload.get("disability")
    if disability:
        grade = disability.get("grade")
        if grade is not None and grade not in DISABILITY_LOSS_RATES:
            raise ValueError(f"disability.grade は 1-14（受信: {grade}）")

    return payload


# ---------------------------------------------------------------------------
# 各損害項目の計算
# ---------------------------------------------------------------------------


def _calc_positive_damages(payload: dict) -> Dict[str, int]:
    """積極損害（実費）の集計。"""
    med = payload.get("medical") or {}
    hosp_days = med.get("hospital_days", 0) or 0
    outp_days = med.get("outpatient_days", 0) or 0
    nurse_hosp = med.get("nursing_days_hospital", 0) or 0
    nurse_outp = med.get("nursing_days_outpatient", 0) or 0

    items = {
        "medical_fees": med.get("medical_fees", 0) or 0,
        "transportation": med.get("transportation", 0) or 0,
        "equipment": med.get("equipment", 0) or 0,
        "hospital_misc": hosp_days * HOSPITAL_MISC_PER_DAY,
        "nursing_hospital": nurse_hosp * NURSING_FEE_HOSPITAL,
        "nursing_outpatient": nurse_outp * NURSING_FEE_OUTPATIENT,
    }
    items["total"] = sum(items.values())
    return items


def _calc_lost_wages(payload: dict) -> Dict[str, int]:
    """休業損害。"""
    victim = payload.get("victim") or {}
    lw = payload.get("lost_wages") or {}
    days_off = lw.get("days_off_work", 0) or 0
    if days_off <= 0:
        return {"daily_wage": 0, "days_off": 0, "total": 0}

    # 日額の基礎収入
    daily_override = lw.get("daily_wage_override")
    if daily_override is not None:
        daily = int(daily_override)
    else:
        occupation = victim.get("occupation_type")
        annual_income = victim.get("annual_income")

        if occupation == "household":
            # 主婦の休業損害は賃金センサス女性全年齢平均を使う
            daily = WAGE_CENSUS_FEMALE_ALL_AGE // 365
        elif annual_income and annual_income > 0:
            # 給与所得者・自営業: 事故前 3 ヶ月の給与 ÷ 日数が判例の原則だが、
            # 本計算器では年収 / 365 を近似として使う（実務でも多用）
            daily = annual_income // 365
        else:
            daily = 0

    total = daily * days_off
    return {"daily_wage": daily, "days_off": days_off, "total": total}


def _calc_loss_of_future_earnings(payload: dict, rate: Fraction) -> Dict[str, int]:
    """後遺障害逸失利益（将来得られたはずの収入の喪失）。

    `rate` は事故日から決定した法定利率（2020/04/01 前後で 5% / 3%）。
    """
    disability = payload.get("disability")
    if not disability:
        return {"total": 0, "note": "後遺障害なし"}

    grade = disability.get("grade")
    if grade is None or grade not in DISABILITY_LOSS_RATES:
        return {"total": 0, "note": "等級未指定"}

    victim = payload.get("victim") or {}
    age = victim.get("age_at_accident", 0)
    occupation = victim.get("occupation_type")

    # 稼働可能年数（原則 67 歳まで）
    years = disability.get("years_until_67")
    if years is None:
        years = max(0, 67 - age)

    if years <= 0:
        return {"total": 0, "note": "稼働可能年数 0 以下"}

    # 基礎収入
    annual_income = victim.get("annual_income") or 0
    if occupation == "household" and annual_income == 0:
        annual_income = WAGE_CENSUS_FEMALE_ALL_AGE

    loss_rate = DISABILITY_LOSS_RATES[grade]
    leibniz = _leibniz_coefficient(years, rate)
    total_f = Fraction(annual_income) * loss_rate * leibniz
    total = _to_int(total_f)

    return {
        "total": total,
        "annual_income": annual_income,
        "grade": grade,
        "loss_rate": f"{loss_rate.numerator}/{loss_rate.denominator} ({float(loss_rate)*100:.0f}%)",
        "years": years,
        "leibniz": f"{float(leibniz):.4f}",
        "interest_rate": f"{float(rate)*100:.0f}%",
    }


def _calc_death_lost_earnings(payload: dict, rate: Fraction) -> Dict[str, int]:
    """死亡逸失利益。`rate` は事故日由来の法定利率。"""
    death = payload.get("death")
    if not death:
        return {"total": 0, "note": "死亡なし"}

    victim = payload.get("victim") or {}
    age = victim.get("age_at_accident", 0)
    gender = victim.get("gender", "male")
    is_supporter = victim.get("is_household_supporter", False)
    dep_count = death.get("dependent_count", 0)

    annual_income = victim.get("annual_income") or 0
    if annual_income <= 0:
        # 無収入者でも死亡逸失利益は賃金センサスベースで認められる場合がある
        # ここでは 0 を返し、上位で手動計算を促す
        return {"total": 0, "note": "年収 0、賃金センサスベースの手計算を検討"}

    years = max(0, 67 - age)
    if years <= 0:
        return {"total": 0, "note": "稼働可能年数 0"}

    # 生活費控除率
    if gender == "male":
        if is_supporter and dep_count >= 2:
            key = ("male", "household_supporter_multi")
        elif is_supporter:
            key = ("male", "household_supporter_single")
        else:
            key = ("male", "single")
    else:
        if is_supporter:
            key = ("female", "household_supporter")
        else:
            key = ("female", "single")
    deduction_rate = LIVING_COST_DEDUCTION[key]

    leibniz = _leibniz_coefficient(years, rate)
    effective_rate = Fraction(1) - deduction_rate
    total_f = Fraction(annual_income) * effective_rate * leibniz
    total = _to_int(total_f)

    return {
        "total": total,
        "annual_income": annual_income,
        "deduction_rate": f"{float(deduction_rate)*100:.0f}%",
        "years": years,
        "leibniz": f"{float(leibniz):.4f}",
        "interest_rate": f"{float(rate)*100:.0f}%",
    }


def _calc_hospitalization_consolation(payload: dict) -> Dict[str, int]:
    """入通院慰謝料（赤い本）。"""
    med = payload.get("medical") or {}
    hosp_days = med.get("hospital_days", 0) or 0
    outp_days = med.get("outpatient_days", 0) or 0

    if hosp_days == 0 and outp_days == 0:
        return {"total": 0, "note": "通院・入院なし"}

    hosp_months = _months_from_days(hosp_days)
    outp_months = _months_from_days(outp_days)

    # severity は必須。未指定で別表 I（通常傷害、金額高）に silently default すると
    # 軽傷（むち打ち等）案件で慰謝料を 30-50% 過大請求してしまう — 弁護士にとって
    # 実害のある malpractice-adjacent 挙動のため、ここで明示エラーにする。
    severity_raw = med.get("severity")
    if severity_raw is None:
        raise ValueError(
            "medical.severity は必須。'major'（別表 I・骨折等他覚所見あり）または "
            "'minor'（別表 II・むち打ち等他覚所見なし軽傷）を明示的に指定してほしい。"
        )
    severity = str(severity_raw).lower()
    if severity in ("minor", "minor_whiplash", "soft_tissue"):
        amount = _consolation_lookup(_TABLE_II, hosp_months, outp_months)
        table = "赤い本別表 II（軽傷用）"
    elif severity in ("major", "standard"):
        amount = _consolation_lookup(_TABLE_I, hosp_months, outp_months)
        table = "赤い本別表 I（通常傷害）"
    else:
        raise ValueError(
            f"medical.severity は 'major' か 'minor' のいずれか（受信: {severity_raw}）"
        )

    return {
        "total": amount,
        "hospital_months": hosp_months,
        "outpatient_months": outp_months,
        "table": table,
    }


def _calc_disability_consolation(payload: dict) -> Dict[str, int]:
    """後遺障害慰謝料。"""
    disability = payload.get("disability")
    if not disability:
        return {"total": 0, "note": "後遺障害なし"}
    grade = disability.get("grade")
    if grade not in DISABILITY_CONSOLATION:
        return {"total": 0, "note": "等級未指定または範囲外"}
    return {
        "total": DISABILITY_CONSOLATION[grade],
        "grade": grade,
    }


def _calc_death_consolation(payload: dict) -> Dict[str, int]:
    """死亡慰謝料。"""
    death = payload.get("death")
    if not death:
        return {"total": 0, "note": "死亡なし"}
    victim = payload.get("victim") or {}
    gender = victim.get("gender", "male")
    is_supporter = victim.get("is_household_supporter", False)

    if is_supporter:
        key = "household_supporter"
    elif gender == "female":
        key = "mother_spouse"
    else:
        key = "other"

    return {
        "total": DEATH_CONSOLATION[key],
        "category": key,
    }


# ---------------------------------------------------------------------------
# メイン計算関数
# ---------------------------------------------------------------------------


def compute_damages(payload: dict) -> dict:
    """交通事故損害賠償額を計算する。"""
    _validate(payload)

    accident_date = (payload.get("accident") or {}).get("date")
    rate = _rate_for_accident_date(accident_date)

    pos = _calc_positive_damages(payload)
    lost_wages = _calc_lost_wages(payload)
    future_loss = _calc_loss_of_future_earnings(payload, rate)
    death_loss = _calc_death_lost_earnings(payload, rate)
    hosp_consol = _calc_hospitalization_consolation(payload)
    disability_consol = _calc_disability_consolation(payload)
    death_consol = _calc_death_consolation(payload)

    # 損害の合計（過失相殺・弁護士費用前）
    subtotal = (
        pos["total"]
        + lost_wages["total"]
        + future_loss["total"]
        + death_loss["total"]
        + hosp_consol["total"]
        + disability_consol["total"]
        + death_consol["total"]
    )

    # 過失相殺
    # Fraction(str(fault)) により float 表現誤差を回避（例: 1.13% を正確に 113/10000 に変換）
    fault = payload.get("accident", {}).get("victim_fault_percent", 0)
    fault_frac = Fraction(str(fault)) / 100
    after_fault_f = Fraction(subtotal) * (Fraction(1) - fault_frac)
    after_fault = _to_int(after_fault_f)

    # 弁護士費用
    options = payload.get("options") or {}
    include_lawyer = options.get("include_lawyer_fee", True)
    lawyer_fee = _to_int(Fraction(after_fault) * LAWYER_FEE_RATE) if include_lawyer else 0

    # 遅延損害金（年3%、事故日〜示談日／訴訟時）は概算として別項で計上
    # 正確な計算には日数ベースが必要なため、本器では目安のみ返す
    delay_info = {}
    if options.get("include_delay_interest"):
        settlement_date = options.get("settlement_date")
        accident_date = payload.get("accident", {}).get("date")
        if settlement_date and accident_date:
            try:
                import datetime as _dt
                d1 = _dt.date.fromisoformat(accident_date)
                d2 = _dt.date.fromisoformat(settlement_date)
                days = (d2 - d1).days
                if days > 0:
                    # after_fault を元本とし、事故日由来の法定利率 × 日数 / 365
                    interest_f = Fraction(after_fault) * rate * Fraction(days, 365)
                    delay_info = {
                        "days": days,
                        "amount": _to_int(interest_f),
                        "note": f"年 {float(rate)*100:.0f}%（改正民法 404条）× {days}日",
                    }
            except (ValueError, TypeError):
                delay_info = {"note": "日付パースに失敗"}

    delay = delay_info.get("amount", 0)
    grand_total = after_fault + lawyer_fee + delay

    return {
        "summary": {
            "subtotal_before_fault": subtotal,
            "victim_fault_percent": fault,
            "after_fault_reduction": after_fault,
            "lawyer_fee": lawyer_fee,
            "delay_interest": delay,
            "grand_total": grand_total,
        },
        "breakdown": {
            "positive_damages": pos,
            "lost_wages": lost_wages,
            "future_earnings_loss": future_loss,
            "death_earnings_loss": death_loss,
            "hospitalization_consolation": hosp_consol,
            "disability_consolation": disability_consol,
            "death_consolation": death_consol,
        },
        "delay_interest_detail": delay_info,
        "notes": [
            "金額はすべて円単位の整数（四捨五入）",
            "赤い本 2024 年版の表値・係数を使用",
            "過失相殺は民法 722 条 2 項に基づき被害者過失割合を控除",
            "弁護士費用は損害額の 10%（判例実務、民法 709 条類推）",
            f"中間利息控除・遅延損害金は事故日由来の法定利率 {float(rate)*100:.0f}%（2020/04/01 境界分岐、改正民法 404条）を使用",
            "損益相殺（自賠責既払額・労災・健康保険等）は本計算器では控除しない — 別途差し引き要",
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
            print(json.dumps({"error": f"入力ファイル読込に失敗: {e}"}, ensure_ascii=False), file=sys.stderr)
            return 2
    elif args.json:
        try:
            payload = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"--json が不正: {e}"}, ensure_ascii=False), file=sys.stderr)
            return 1
    else:
        text = sys.stdin.read()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"stdin JSON が不正: {e}"}, ensure_ascii=False), file=sys.stderr)
            return 1

    try:
        result = compute_damages(payload)
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
    b = result["breakdown"]
    print(f"## 交通事故損害賠償計算結果\n")
    print("### 内訳")
    print(f"  積極損害（実費）          : {b['positive_damages']['total']:>12,} 円")
    print(f"  休業損害                  : {b['lost_wages']['total']:>12,} 円")
    print(f"  後遺障害逸失利益          : {b['future_earnings_loss']['total']:>12,} 円")
    print(f"  死亡逸失利益              : {b['death_earnings_loss']['total']:>12,} 円")
    print(f"  入通院慰謝料              : {b['hospitalization_consolation']['total']:>12,} 円")
    print(f"  後遺障害慰謝料            : {b['disability_consolation']['total']:>12,} 円")
    print(f"  死亡慰謝料                : {b['death_consolation']['total']:>12,} 円")
    print(f"  ───────────────────────────────────")
    print(f"  小計（過失相殺前）        : {s['subtotal_before_fault']:>12,} 円")
    print(f"  過失相殺 (-{s['victim_fault_percent']}%)     : {s['after_fault_reduction']:>12,} 円")
    print(f"  弁護士費用 (+10%)         : {s['lawyer_fee']:>12,} 円")
    if s['delay_interest']:
        print(f"  遅延損害金                : {s['delay_interest']:>12,} 円")
    print(f"  ═══════════════════════════════════")
    print(f"  ★ 合計請求額              : {s['grand_total']:>12,} 円")


def main() -> int:
    ap = argparse.ArgumentParser(description="交通事故損害賠償計算（赤い本基準）")
    ap.add_argument("--self-test", action="store_true", help="組込セルフテストを実行")
    sub = ap.add_subparsers(dest="command")

    p_calc = sub.add_parser("calc", help="損害額を計算")
    p_calc.add_argument("--input", help="入力 JSON ファイルパス")
    p_calc.add_argument("--json", help="入力 JSON 文字列（直接）")
    p_calc.add_argument("--pretty", action="store_true", help="人間可読な表形式で出力")

    args = ap.parse_args()

    if args.self_test:
        # Lazy import to avoid circular
        here = sys.path[0] if sys.path else "."
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
