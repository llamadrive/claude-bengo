#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""typo-check 自動承認 denylist の programmatic 検査（F-031）。

SKILL.md に列挙された denylist カテゴリ（接続詞階層・時/とき/場合・義務規定・
主体呼称・効果規定・2020 改正語・金額/日付/条番号/当事者氏名）は、LLM の
自己判断では bypass されうるため、独立した Python モジュールで判定する。

## 使い方

```bash
python3 skills/_lib/denylist.py check \
    --original "瑕疵" --suggested "契約不適合"
# → exit 1, stderr に denylist 該当理由が出る
```

Exit code:
  0 — denylist に該当しない（自動承認してよい）
  1 — denylist に該当（ユーザー個別確認が必須）
  2 — 入力エラー
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# カテゴリ定義（SKILL.md と対応する）
# ---------------------------------------------------------------------------

# 接続詞階層（「及び」「並びに」「又は」「若しくは」）
CONNECTIVE_HIERARCHY = {
    "及び", "並びに", "又は", "若しくは",
    # 異体字・かな変換
    "および", "ならびに", "または", "もしくは",
}

# 時・とき・場合
TIME_MARKERS = {"時", "とき", "場合"}

# 義務規定の語尾（「しなければならない」「することができない」「することを要する」等）
OBLIGATION_ENDINGS = [
    "しなければならない", "してはならない",
    "することができる", "することができない",
    "することを要する", "することを要しない",
    "するものとする", "するものではない",
    "なければならない", "ならない",
]

# 主体呼称（原告・被告・債務者・委託者 等）
PARTY_TERMS = {
    "原告", "被告",
    "控訴人", "被控訴人",
    "上告人", "被上告人",
    "申立人", "相手方",
    "債権者", "債務者",
    "委託者", "受託者", "受益者",
    "贈与者", "受贈者",
    "遺贈者", "受遺者",
    "賃貸人", "賃借人",
    "売主", "買主",
    "使用者", "労働者",
    "当事者",
}

# 効果規定の語（「無効」「取消し」「解除」「終了」）
EFFECT_TERMS = {
    "無効", "取消し", "取り消し",
    "解除", "解約", "終了",
    "失効", "消滅",
}

# 2020 改正民法で変わった語（瑕疵 → 契約不適合、等）
REFORM_2020_PAIRS = {
    "瑕疵": "契約不適合",
    "隠れた瑕疵": "契約不適合",
    "要素の錯誤": "錯誤",
}

# 金額・日付・条番号・当事者氏名を示すパターン（正規表現）
MONEY_PATTERNS = [
    re.compile(r"\d[\d,]*\s*(円|万円|億円)"),
    re.compile(r"(金)?\d+[\d,]*"),
]
DATE_PATTERNS = [
    re.compile(r"(令和|平成|昭和|大正|明治)\d+年\d+月\d+日"),
    re.compile(r"(令和|平成|昭和|大正|明治)\d+年"),
    re.compile(r"\d{4}年\d+月\d+日"),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
]
ARTICLE_PATTERNS = [
    re.compile(r"(民法|会社法|商法|刑法|労働基準法|憲法|民事訴訟法|刑事訴訟法|破産法|民事執行法|労働契約法|特定商取引法|電子契約法|行政手続法|独占禁止法|知的財産基本法|著作権法|特許法|商標法|不正競争防止法|個人情報の保護に関する法律|会社計算規則|家事事件手続法|人事訴訟法)"),
    re.compile(r"第?\d+条"),
    re.compile(r"\d+条\d+項"),
]

# ---------------------------------------------------------------------------
# 検査ロジック
# ---------------------------------------------------------------------------


def _contains_any(text: str, items) -> List[str]:
    hits = []
    for s in items:
        if s in text:
            hits.append(s)
    return hits


def _contains_any_pattern(text: str, patterns: List[re.Pattern]) -> List[str]:
    hits = []
    for p in patterns:
        for m in p.finditer(text):
            hits.append(m.group(0))
    return hits


def check_denylist(original: str, suggested: str) -> Tuple[bool, List[str]]:
    """original → suggested の変更が denylist に該当するか。

    戻り値: (is_denylist, reasons)
    """
    reasons: List[str] = []
    combined = (original or "") + " " + (suggested or "")

    # 接続詞階層
    conn_orig = _contains_any(original, CONNECTIVE_HIERARCHY)
    conn_sug = _contains_any(suggested, CONNECTIVE_HIERARCHY)
    if conn_orig or conn_sug:
        if set(conn_orig) != set(conn_sug):
            reasons.append(
                f"接続詞階層の変更が検出された（original: {conn_orig}, suggested: {conn_sug}）。"
                "「及び/並びに/又は/若しくは」は法律文書で意味が厳密に定まるため個別確認必須。"
            )

    # 時・とき・場合
    tm_orig = _contains_any(original, TIME_MARKERS)
    tm_sug = _contains_any(suggested, TIME_MARKERS)
    if set(tm_orig) != set(tm_sug) and (tm_orig or tm_sug):
        reasons.append(
            f"「時/とき/場合」の使い分けが変わっている（original: {tm_orig}, suggested: {tm_sug}）。"
            "「時」は時点、「とき」は仮定、「場合」は前提条件で厳密区分あり。"
        )

    # 義務規定
    for ending in OBLIGATION_ENDINGS:
        o_has = ending in original
        s_has = ending in suggested
        if o_has != s_has:
            reasons.append(
                f"義務規定の語尾が変更されている（'{ending}' original={o_has} / suggested={s_has}）。"
                "義務の有無は契約の効力に直結するため個別確認必須。"
            )
            break

    # 主体呼称
    p_orig = _contains_any(original, PARTY_TERMS)
    p_sug = _contains_any(suggested, PARTY_TERMS)
    if set(p_orig) != set(p_sug) and (p_orig or p_sug):
        reasons.append(
            f"主体呼称が変更されている（original: {p_orig}, suggested: {p_sug}）。"
            "誰が何をするかは訴訟の核心であり、呼称変更は内容変更に相当。"
        )

    # 効果規定
    e_orig = _contains_any(original, EFFECT_TERMS)
    e_sug = _contains_any(suggested, EFFECT_TERMS)
    if set(e_orig) != set(e_sug) and (e_orig or e_sug):
        reasons.append(
            f"効果規定の変更（original: {e_orig}, suggested: {e_sug}）。"
            "「無効」「取消し」「解除」は法的効果が異なるため個別確認必須。"
        )

    # 2020 改正語
    for old, new in REFORM_2020_PAIRS.items():
        if old in original and new in suggested:
            reasons.append(
                f"2020 年改正語の置換（{old} → {new}）。旧民法準拠の契約書では原文維持すべき場合あり。"
            )

    # 金額
    m_orig = _contains_any_pattern(original, MONEY_PATTERNS)
    m_sug = _contains_any_pattern(suggested, MONEY_PATTERNS)
    if set(m_orig) != set(m_sug):
        reasons.append(
            f"金額表記の変更（original: {m_orig}, suggested: {m_sug}）。金額は個別確認必須。"
        )

    # 日付
    d_orig = _contains_any_pattern(original, DATE_PATTERNS)
    d_sug = _contains_any_pattern(suggested, DATE_PATTERNS)
    if set(d_orig) != set(d_sug):
        reasons.append(
            f"日付表記の変更（original: {d_orig}, suggested: {d_sug}）。日付は個別確認必須。"
        )

    # 条番号
    a_orig = _contains_any_pattern(original, ARTICLE_PATTERNS)
    a_sug = _contains_any_pattern(suggested, ARTICLE_PATTERNS)
    if set(a_orig) != set(a_sug):
        reasons.append(
            f"条番号・法令名の変更（original: {a_orig}, suggested: {a_sug}）。個別確認必須。"
        )

    # 当事者氏名（カタカナ・漢字の連続 + 「さん」「氏」等は簡易検出）
    name_re = re.compile(r"[一-龯々]{2,}(?:氏|さん|様|君)")
    n_orig = set(name_re.findall(original))
    n_sug = set(name_re.findall(suggested))
    if n_orig != n_sug:
        reasons.append(
            f"当事者氏名（候補）の変更（original: {n_orig}, suggested: {n_sug}）。個別確認必須。"
        )

    return (bool(reasons), reasons)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="typo-check denylist checker")
    sub = ap.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="original/suggested を denylist 判定する")
    p_check.add_argument("--original", required=True)
    p_check.add_argument("--suggested", required=True)
    p_check.add_argument("--format", choices=["text", "json"], default="text")

    p_self = sub.add_parser("self-test", help="組込セルフテスト")

    args = ap.parse_args()

    if args.command == "check":
        is_deny, reasons = check_denylist(args.original, args.suggested)
        if args.format == "json":
            print(json.dumps({"denylist": is_deny, "reasons": reasons}, ensure_ascii=False))
        else:
            for r in reasons:
                print(r, file=sys.stderr)
        return 1 if is_deny else 0

    if args.command == "self-test":
        return _self_test()

    ap.print_help()
    return 2


def _self_test() -> int:
    cases: List[Tuple[str, str, bool]] = [
        # original, suggested, expected_deny
        ("瑕疵", "契約不適合", True),  # 2020 改正語
        ("甲", "乙", False),  # 単純誤字（denylist 外）
        ("及び", "並びに", True),  # 接続詞階層
        ("とき", "時", True),  # 時間/条件の使い分け
        ("原告", "被告", True),  # 主体呼称
        ("取消し", "解除", True),  # 効果規定
        ("金100万円", "金200万円", True),  # 金額
        ("令和5年4月1日", "令和5年4月2日", True),  # 日付
        ("民法第709条", "民法第710条", True),  # 条番号
        ("無効である", "取消しできる", True),  # 効果規定
        ("色字", "漢字", False),  # 単純誤字
    ]
    passed = 0
    for original, suggested, expected in cases:
        is_deny, _ = check_denylist(original, suggested)
        ok = is_deny == expected
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {original!r} → {suggested!r} expected_deny={expected} got={is_deny}")
        if ok:
            passed += 1
    total = len(cases)
    print(f"\n結果: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
