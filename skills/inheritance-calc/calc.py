#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法定相続分計算モジュール（民法に基づく決定論的計算）。

本スクリプトは、被相続人と相続人候補のグラフ表現から、民法の規定に従い
法定相続分および遺留分を正確に計算するCLIツールである。

## 関連条文

- 民法887条  子の相続権・代襲相続・再代襲
- 民法889条  直系尊属・兄弟姉妹の相続権（兄弟姉妹の代襲は1代限り）
- 民法890条  配偶者の相続権
- 民法900条  法定相続分（半血兄弟姉妹は全血の1/2）
- 民法901条  代襲相続人の相続分
- 民法939条  相続放棄の効果（放棄者は最初から相続人でなかったとみなす）
- 民法1042条 遺留分

## 入力スキーマ

```
{
  "decedent": {"id": "d", "name": "甲野太郎"},
  "heirs": [
    {"id": "h1", "name": "…", "kind": "spouse", "status": "alive"},
    {"id": "h2", "name": "…", "kind": "child", "status": "alive", "adoption": "none"},
    …
  ],
  "compute_iryubun": false
}
```

### kind の値

- `spouse`            配偶者
- `child`             子（実子または普通養子）
- `grandchild`        孫（代襲相続人。`parent_id` で被代襲者の子を指定）
- `great_grandchild`  ひ孫（再代襲。`parent_id` で被代襲者の孫を指定）
- `parent`            父母
- `grandparent`       祖父母
- `sibling_full`      全血兄弟姉妹
- `sibling_half`      半血兄弟姉妹
- `nephew_niece`      甥姪（代襲相続人。`parent_id` で被代襲兄弟姉妹を指定）

### status の値

- `alive`       生存
- `deceased`    先に死亡（代襲相続の起点となり得る）
- `renounced`   相続放棄（子孫は代襲しない。民法939条）

### adoption（child にのみ指定）

- `none`     実子または普通養子（本家の相続人として扱う）
- `special`  特別養子（民法817条の2）。このフィールドは**実親からの相続**に
             関する入力で使用する。`special` を指定した子は実親の相続人
             リストに含めてはならない（特別養子は実親との法律上の親族関係が
             終了する）。養親からの相続の場合は `none` で扱ってよい。

## 出力

JSON を標準出力に出す。`--pretty` を付けると人間が読める表形式も出力する。

## 対応範囲外（現バージョンでの明示的な非対応事項）

- 二重相続資格（一人が複数の相続資格を併有する場合、例: 養子かつ代襲相続人）
- 胎児の相続権（民法886条）
- 相続欠格（民法891条）・廃除（民法892条）
- 寄与分（民法904条の2）・特別受益（民法903条）
- 配偶者居住権（民法1028条以下）
- 相続人不存在時の特別縁故者への分与（民法958条の2）

これらは将来バージョンで対応予定である。二重相続資格のケース（例: 被相続人の
孫が養子縁組により子となり、かつ死亡した実親を代襲する場合）は本スキルでは
単一資格のみ処理するため、該当する場合はユーザー側で各資格分を手動で合算する
必要がある。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------


@dataclass
class Heir:
    """相続人候補のノードを表す。"""

    id: str
    name: str
    kind: str
    status: str = "alive"
    parent_id: Optional[str] = None
    adoption: str = "none"

    # 計算中に使用する内部フィールド
    children: List["Heir"] = field(default_factory=list)


VALID_KINDS = {
    "spouse",
    "child",
    "grandchild",
    "great_grandchild",
    "parent",
    "grandparent",
    "sibling_full",
    "sibling_half",
    "nephew_niece",
}

VALID_STATUS = {"alive", "deceased", "renounced"}
VALID_ADOPTION = {"none", "special"}


# ---------------------------------------------------------------------------
# 入力バリデーション
# ---------------------------------------------------------------------------


def _validate_and_build(payload: dict) -> Tuple[dict, List[Heir], bool]:
    """入力JSONを検証し、被相続人情報・相続人リスト・遺留分フラグを返す。"""
    if not isinstance(payload, dict):
        raise ValueError("入力はJSONオブジェクトでなければならない。")

    decedent = payload.get("decedent")
    if not isinstance(decedent, dict) or "name" not in decedent:
        raise ValueError("decedent フィールドに name を含めること。")

    heirs_raw = payload.get("heirs", [])
    if not isinstance(heirs_raw, list):
        raise ValueError("heirs はリストでなければならない。")

    heirs: List[Heir] = []
    seen_ids = set()
    for idx, entry in enumerate(heirs_raw):
        if not isinstance(entry, dict):
            raise ValueError(f"heirs[{idx}] はオブジェクトでなければならない。")
        hid = entry.get("id")
        if not hid:
            raise ValueError(f"heirs[{idx}] に id がない。")
        if hid in seen_ids:
            raise ValueError(f"id が重複している: {hid}")
        seen_ids.add(hid)

        kind = entry.get("kind")
        if kind not in VALID_KINDS:
            raise ValueError(f"heirs[{idx}] の kind が不正: {kind}")

        status = entry.get("status", "alive")
        if status not in VALID_STATUS:
            raise ValueError(f"heirs[{idx}] の status が不正: {status}")

        adoption = entry.get("adoption", "none")
        if adoption not in VALID_ADOPTION:
            raise ValueError(f"heirs[{idx}] の adoption が不正: {adoption}")

        heir = Heir(
            id=hid,
            name=entry.get("name", hid),
            kind=kind,
            status=status,
            parent_id=entry.get("parent_id"),
            adoption=adoption,
        )
        heirs.append(heir)

    # adoption フィールドは kind='child' でのみ意味を持つ
    for h in heirs:
        if h.kind != "child" and h.adoption != "none":
            raise ValueError(
                f"adoption フィールドは kind='child' でのみ有効である"
                f"（受け取った: kind='{h.kind}', adoption='{h.adoption}'）。"
                "孫・ひ孫・甥姪などの代襲相続人には adoption を指定しないでほしい。"
            )

    # 特別養子は実親の相続人リストに含めてはならない
    for h in heirs:
        if h.kind == "child" and h.adoption == "special":
            raise ValueError(
                f"特別養子（{h.name}）は実親の相続人リストに含められない。"
                "養親からの相続の場合は adoption を 'none' としてほしい。"
            )

    # parent_id の整合性チェック
    id_map = {h.id: h for h in heirs}
    for h in heirs:
        if h.parent_id and h.parent_id not in id_map:
            raise ValueError(
                f"heirs[{h.id}] の parent_id={h.parent_id} に対応する相続人が存在しない。"
            )

    # 自己参照（self-loop）の早期検出
    for h in heirs:
        if h.parent_id == h.id:
            raise ValueError(
                f"parent_id でサイクルが検出された: {h.id} → {h.id}. "
                "各人物は自分以外の親に紐付ける必要がある。"
            )

    compute_iryubun = bool(payload.get("compute_iryubun", False))
    return decedent, heirs, compute_iryubun


# ---------------------------------------------------------------------------
# 相続人グラフの構築
# ---------------------------------------------------------------------------


def _link_descendants(heirs: List[Heir]) -> None:
    """parent_id に基づき代襲者を親ノードの children にぶら下げる。"""
    id_map = {h.id: h for h in heirs}
    for h in heirs:
        if h.parent_id:
            parent = id_map.get(h.parent_id)
            if parent is not None:
                parent.children.append(h)


def _detect_cycles(heirs: List[Heir]) -> None:
    """parent_id の連鎖にサイクルが存在しないか検証する。

    heir A の parent_id が B を指し、さらに辿って A に戻ってくる場合、
    下流の計算ロジック（代襲探索等）が無限再帰に陥る、または誤った結果を
    静かに返すおそれがある。本関数は各ノードから parent_id を辿り、
    既訪問ノードに戻ってきた時点でサイクルと判定して拒否する。
    """
    id_map = {h.id: h for h in heirs}
    for start in heirs:
        visited: List[str] = []
        seen: set = set()
        cur: Optional[Heir] = start
        while cur is not None and cur.parent_id:
            visited.append(cur.id)
            seen.add(cur.id)
            nxt = id_map.get(cur.parent_id)
            if nxt is None:
                # parent_id 不整合は _validate_and_build で既に検出済み
                break
            if nxt.id in seen:
                path = " → ".join(visited + [nxt.id])
                raise ValueError(
                    f"parent_id でサイクルが検出された: {path}. "
                    "各人物は一意の親に紐付ける必要がある。"
                )
            cur = nxt


def _detect_dual_heirship(heirs: List[Heir]) -> None:
    """二重相続資格の可能性を検出する。

    同一 id の相続人が複数の相続資格（例: 養子として kind='child' かつ
    代襲相続人として kind='grandchild'）を持つ場合、民法上は両方の資格
    から相続分を受けるとする学説が有力だが、本スキルは単一資格のみを
    処理する。入力段階で id 重複は拒否しているため、ここでは異なる id
    で同一人物が複数のロールを持つケースを構造的に検出する手段がない。

    そこで、次のような構造的ヒューリスティックで検出する:
    - 同一の id が複数エントリで出現した場合（id 重複 — これは既に別途拒否）
    - heir が kind='child' かつ parent_id を持つ場合（= 養子でありながら
      他の死亡子の代襲者として指定される矛盾した構造）

    ここでは kind='child' に parent_id が付与されているケースを二重相続
    資格の疑いとして拒否する。子は被相続人の直接の子であり、parent_id
    で他の相続人に紐付けるべきではない。
    """
    for h in heirs:
        if h.kind == "child" and h.parent_id:
            raise ValueError(
                f"二重相続資格の可能性がある: 相続人 {h.id} は kind='child' で"
                f"ありながら parent_id={h.parent_id} を併有している。"
                "これは養子かつ代襲相続人のケース（例: 孫を養子にしたうえで"
                "実親が先に死亡）を示唆するが、本スキルでは単一資格のみ処理する。"
                "手動で各資格分を合算してほしい。"
                "詳細は calc.py の 対応範囲外 参照。"
            )


def _has_descendant_inheritor(node: Heir) -> bool:
    """node の子孫に、代襲相続し得る者（生存かつ非放棄）が存在するか。

    民法901条に基づき、代襲相続には被代襲者の直系卑属で相続権を有する者が必要。
    """
    for c in node.children:
        if c.status == "renounced":
            # 放棄者は最初から相続人でないから、その系統も代襲不能
            continue
        if c.status == "alive":
            return True
        if c.status == "deceased" and _has_descendant_inheritor(c):
            return True
    return False


# ---------------------------------------------------------------------------
# 子・孫・ひ孫系統の計算（第1順位）
# ---------------------------------------------------------------------------


def _collect_child_lines(heirs: List[Heir]) -> List[Heir]:
    """第1順位の"相続ライン"を構成する子ノードを列挙する。

    民法901条に従い:
    - 生存した子は1ライン。
    - 先に死亡した子で、生存する直系卑属（または代襲可能な孫）が存在するなら1ライン。
    - 放棄した子は0ライン（民法939条）。
    - 死亡した子で直系卑属のない場合は0ライン。
    """
    lines: List[Heir] = []
    for h in heirs:
        if h.kind != "child":
            continue
        if h.status == "renounced":
            continue
        if h.status == "alive":
            lines.append(h)
        elif h.status == "deceased" and _has_descendant_inheritor(h):
            lines.append(h)
    return lines


def _distribute_descendant_line(
    node: Heir, share: Fraction
) -> List[Tuple[Heir, Fraction]]:
    """子・孫・ひ孫系統で、node に割り当てられた share を代襲配分する。

    民法887条・901条。node 自身が生存していれば node が受け取る。死亡していれば
    直系卑属で均等分割する（再代襲可）。放棄者は系統から除外（民法939条）。
    """
    if node.status == "alive":
        return [(node, share)]

    # 死亡している場合は代襲者に配分する
    eligible: List[Heir] = []
    for c in node.children:
        if c.status == "renounced":
            continue
        if c.status == "alive":
            eligible.append(c)
        elif c.status == "deceased" and _has_descendant_inheritor(c):
            eligible.append(c)

    if not eligible:
        return []  # 代襲者不在なので、このラインは消滅する

    per_head = share / len(eligible)
    results: List[Tuple[Heir, Fraction]] = []
    for c in eligible:
        results.extend(_distribute_descendant_line(c, per_head))
    return results


# ---------------------------------------------------------------------------
# 兄弟姉妹系統の計算（第3順位、代襲は1代限り）
# ---------------------------------------------------------------------------


def _collect_sibling_lines(heirs: List[Heir]) -> List[Heir]:
    """兄弟姉妹の相続ラインを列挙する。

    民法889条2項により、兄弟姉妹の代襲は甥姪まで。再代襲なし。
    """
    lines: List[Heir] = []
    for h in heirs:
        if h.kind not in ("sibling_full", "sibling_half"):
            continue
        if h.status == "renounced":
            continue
        if h.status == "alive":
            lines.append(h)
        elif h.status == "deceased":
            # 甥姪（生存・非放棄）がいるか
            has_nn = any(
                c.kind == "nephew_niece"
                and c.status == "alive"
                for c in h.children
            )
            if has_nn:
                lines.append(h)
    return lines


def _distribute_sibling_line(
    node: Heir, share: Fraction
) -> List[Tuple[Heir, Fraction]]:
    """兄弟姉妹ラインの配分。代襲は1代限り（民法889条2項）。

    甥姪がさらに死亡していても、その子（大甥大姪）は相続しない。
    """
    if node.status == "alive":
        return [(node, share)]

    # 生存する甥姪のみを代襲者として扱う（再代襲不可）
    eligible = [
        c for c in node.children
        if c.kind == "nephew_niece" and c.status == "alive"
    ]
    if not eligible:
        return []
    per_head = share / len(eligible)
    return [(c, per_head) for c in eligible]


# ---------------------------------------------------------------------------
# 直系尊属（第2順位）の計算
# ---------------------------------------------------------------------------


def _collect_ascendants(heirs: List[Heir]) -> List[Heir]:
    """直系尊属で相続権を有する者を列挙する。

    民法889条1号: 親等が近い者が優先する。父母が1人でも生存していれば
    祖父母は相続しない。
    """
    parents_alive = [
        h for h in heirs
        if h.kind == "parent" and h.status == "alive"
    ]
    if parents_alive:
        return parents_alive
    grandparents_alive = [
        h for h in heirs
        if h.kind == "grandparent" and h.status == "alive"
    ]
    return grandparents_alive


# ---------------------------------------------------------------------------
# 配偶者
# ---------------------------------------------------------------------------


def _find_spouse(heirs: List[Heir]) -> Optional[Heir]:
    """相続権を有する配偶者を返す。放棄・死亡の場合は None。"""
    for h in heirs:
        if h.kind == "spouse" and h.status == "alive":
            return h
    return None


# ---------------------------------------------------------------------------
# メイン計算ロジック
# ---------------------------------------------------------------------------


def compute_shares(payload: dict) -> dict:
    """入力から法定相続分（および遺留分）を計算する。"""
    decedent, heirs, compute_iryubun = _validate_and_build(payload)
    # 二重相続資格の検出は graph link より前で行う。
    _detect_dual_heirship(heirs)
    _link_descendants(heirs)
    # サイクル検出は link 後・shares 計算前に実施する。下流の代襲探索が
    # 無限再帰に陥る前に不正入力を拒否する。
    _detect_cycles(heirs)

    spouse = _find_spouse(heirs)
    notes: List[str] = []

    # 各順位で実効的な相続ラインを集める
    child_lines = _collect_child_lines(heirs)
    ascendants = _collect_ascendants(heirs)
    sibling_lines = _collect_sibling_lines(heirs)

    # 放棄処理に関するメモ
    renounced = [h for h in heirs if h.status == "renounced"]
    if renounced:
        notes.append(
            "民法939条により、相続放棄者は最初から相続人でなかったものとみなす。"
            "放棄者の直系卑属は代襲しない。"
        )

    rank: Optional[int] = None
    assignments: List[Tuple[Heir, Fraction]] = []

    if child_lines:
        rank = 1
        notes.append("第1順位（子・その代襲）による相続（民法887条）。")
        line_total = Fraction(1, 2) if spouse else Fraction(1, 1)
        per_line = line_total / len(child_lines)
        for cl in child_lines:
            assignments.extend(_distribute_descendant_line(cl, per_line))
        if spouse:
            assignments.append((spouse, Fraction(1, 2)))
            notes.append(
                "民法900条1号: 配偶者と子が相続 → 配偶者 1/2、子（ライン合計）1/2。"
            )
        else:
            notes.append("子のみが相続 → 子（ライン合計）1/1 を均等分割。")

    elif ascendants:
        rank = 2
        notes.append("第2順位（直系尊属）による相続（民法889条1号）。")
        if any(h.kind == "parent" and h.status == "alive" for h in heirs):
            notes.append("父母（親等が近い者）が優先する（民法889条1号括弧書）。")
        asc_total = Fraction(1, 3) if spouse else Fraction(1, 1)
        per_head = asc_total / len(ascendants)
        for a in ascendants:
            assignments.append((a, per_head))
        if spouse:
            assignments.append((spouse, Fraction(2, 3)))
            notes.append(
                "民法900条2号: 配偶者と直系尊属 → 配偶者 2/3、直系尊属 1/3 を均等分割。"
            )
        else:
            notes.append("直系尊属のみが相続 → 1/1 を均等分割。")

    elif sibling_lines:
        rank = 3
        notes.append("第3順位（兄弟姉妹・その代襲）による相続（民法889条2号）。")
        notes.append(
            "兄弟姉妹の代襲は甥姪までの1代限り（民法889条2項、887条2項の準用）。"
        )
        sib_total = Fraction(1, 4) if spouse else Fraction(1, 1)

        # 半血兄弟姉妹は全血の1/2（民法900条4号但書）
        # 代襲の場合でも、被代襲者（親の兄弟姉妹）の血統区分に従う
        def _weight(node: Heir) -> Fraction:
            return Fraction(1, 2) if node.kind == "sibling_half" else Fraction(1)

        total_units = sum((_weight(s) for s in sibling_lines), Fraction(0))
        for sl in sibling_lines:
            line_share = sib_total * _weight(sl) / total_units
            assignments.extend(_distribute_sibling_line(sl, line_share))

        if any(s.kind == "sibling_half" for s in sibling_lines):
            notes.append(
                "民法900条4号但書: 半血兄弟姉妹の相続分は全血兄弟姉妹の1/2。"
                "代襲の場合も被代襲者の血統区分に従う。"
            )
        if spouse:
            assignments.append((spouse, Fraction(3, 4)))
            notes.append("民法900条3号: 配偶者と兄弟姉妹 → 配偶者 3/4、兄弟姉妹 1/4。")
        else:
            notes.append("兄弟姉妹のみが相続 → 1/1。")

    elif spouse:
        rank = 0  # 配偶者単独（他の順位が存在しない）
        assignments.append((spouse, Fraction(1, 1)))
        notes.append("配偶者のみが相続人 → 配偶者 1/1（民法890条）。")

    else:
        rank = None
        notes.append(
            "相続人が存在しない。民法951条以下の相続財産法人・"
            "民法958条の2の特別縁故者への分与・民法959条の国庫帰属の手続を"
            "検討する必要がある。"
        )

    # 総和が1であることを検証（相続人不存在の場合は0）
    total = sum((s for _, s in assignments), Fraction(0))
    if assignments:
        assert total == Fraction(1), (
            f"計算エラー: 相続分の合計が1にならない（総和={total}）。"
        )
    else:
        assert total == Fraction(0)

    # 出力整形
    shares_out: List[dict] = []
    for heir, share in assignments:
        shares_out.append(
            {
                "id": heir.id,
                "name": heir.name,
                "kind": heir.kind,
                "share": f"{share.numerator}/{share.denominator}",
                "share_percent": round(float(share) * 100, 4),
            }
        )

    iryubun_out: Optional[List[dict]] = None
    if compute_iryubun:
        iryubun_out = _compute_iryubun(rank, assignments, notes)

    return {
        "decedent": decedent.get("name", ""),
        "rank": rank,
        "shares": shares_out,
        "iryubun": iryubun_out,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# 遺留分（民法1042条）
# ---------------------------------------------------------------------------


_IRYUBUN_NONE_KINDS = {
    "sibling_full",
    "sibling_half",
    "nephew_niece",
}


def _compute_iryubun(
    rank: Optional[int],
    assignments: List[Tuple[Heir, Fraction]],
    notes: List[str],
) -> List[dict]:
    """遺留分を計算する。

    民法1042条:
    - 兄弟姉妹（およびその代襲者である甥姪）には遺留分がない。
    - 直系尊属のみが相続人 → 総遺留分 1/3。
    - それ以外 → 総遺留分 1/2。
    - 各人の遺留分 = 総遺留分 × 法定相続分。
    ただし遺留分権利者は 配偶者・子（およびその代襲者）・直系尊属 に限る。
    """
    if not assignments:
        notes.append("遺留分: 相続人不存在のため計算しない。")
        return []

    # 遺留分権利者が存在しない場合（例: 兄弟姉妹のみ）
    any_holder = any(
        h.kind not in _IRYUBUN_NONE_KINDS for h, _ in assignments
    )

    # 直系尊属「のみ」が相続人か
    is_ascendants_only = rank == 2 and all(
        h.kind in ("parent", "grandparent") for h, _ in assignments
    )

    if is_ascendants_only:
        reserved = Fraction(1, 3)
        notes.append("民法1042条1項1号: 直系尊属のみが相続人 → 総遺留分は 1/3。")
    else:
        reserved = Fraction(1, 2)
        if any_holder:
            notes.append("民法1042条1項2号: 総遺留分は 1/2。")

    if any(h.kind in _IRYUBUN_NONE_KINDS for h, _ in assignments):
        notes.append(
            "民法1042条: 兄弟姉妹（甥姪を含む）には遺留分がない。"
        )

    iryubun: List[dict] = []
    for heir, share in assignments:
        if heir.kind in _IRYUBUN_NONE_KINDS:
            iryubun.append(
                {
                    "id": heir.id,
                    "name": heir.name,
                    "kind": heir.kind,
                    "share": "0",
                    "share_percent": 0.0,
                }
            )
            continue
        ir_share = reserved * share
        iryubun.append(
            {
                "id": heir.id,
                "name": heir.name,
                "kind": heir.kind,
                "share": f"{ir_share.numerator}/{ir_share.denominator}",
                "share_percent": round(float(ir_share) * 100, 4),
            }
        )
    return iryubun


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------


def _format_pretty(result: dict) -> str:
    """結果を人間が読みやすい表形式で返す。"""
    lines: List[str] = []
    lines.append(f"被相続人: {result['decedent']}")
    rank_label = {
        0: "配偶者単独",
        1: "第1順位（子・代襲）",
        2: "第2順位（直系尊属）",
        3: "第3順位（兄弟姉妹・代襲）",
        None: "相続人不存在",
    }.get(result["rank"], str(result["rank"]))
    lines.append(f"順位: {rank_label}")
    lines.append("")
    lines.append("法定相続分:")
    lines.append("  " + "-" * 60)
    for s in result["shares"]:
        lines.append(
            f"  {s['name']}（{s['kind']}）: {s['share']} "
            f"({s['share_percent']}%)"
        )
    lines.append("  " + "-" * 60)

    if result.get("iryubun"):
        lines.append("")
        lines.append("遺留分:")
        lines.append("  " + "-" * 60)
        for s in result["iryubun"]:
            lines.append(
                f"  {s['name']}（{s['kind']}）: {s['share']} "
                f"({s['share_percent']}%)"
            )
        lines.append("  " + "-" * 60)

    lines.append("")
    lines.append("根拠・注記:")
    for n in result["notes"]:
        lines.append(f"  - {n}")
    return "\n".join(lines)


def _load_payload(args: argparse.Namespace) -> dict:
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            return json.load(f)
    if args.json:
        return json.loads(args.json)
    raise SystemExit("--input または --json のいずれかを指定してほしい。")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="民法に基づく法定相続分・遺留分の決定論的計算"
    )
    parser.add_argument(
        "--input",
        help="入力JSONファイルのパス",
    )
    parser.add_argument(
        "--json",
        help="入力JSONをインライン文字列で渡す",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="人間が読みやすい表形式でも出力する",
    )
    args = parser.parse_args(argv)

    try:
        payload = _load_payload(args)
        result = compute_shares(payload)
    except (ValueError, json.JSONDecodeError, AssertionError) as e:
        print(json.dumps(
            {"error": str(e)}, ensure_ascii=False, indent=2
        ), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.pretty:
        print("", file=sys.stderr)
        print(_format_pretty(result), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
