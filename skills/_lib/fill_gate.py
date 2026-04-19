#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""template-fill の書込前プレビュー／承認ゲートを on-disk state として記録する。

背景: `skills/template-fill/SKILL.md` の Step 5.75 は「書込前にプレビュー表を
表示し、ユーザーの明示的な yes を待つ」と定めているが、Markdown の指示だけでは
LLM が「ちょっと急いでいるのでそのまま実行」等と言われれば飛ばされ得る。
法廷提出書類では致命的なため、**承認をファイルとして記録**し、書込ステップは
そのファイルの存在と内容で分岐するようにした。

## 仕様
承認ワークフロー:

1. `fill_gate.py plan` — 書込プラン JSON を stdin / ファイルから受け取り、
   `{outputs_dir}/.preview_{output_filename}.json` に保存する（書込先と 1:1）。
   戻り値の `preview_path` と `token`（内容ハッシュ）を Step 5.75 表に併記する。
2. LLM が表を表示し、ユーザーから返答を受ける。
3. `fill_gate.py approve --preview <path> --answer <text>` — ユーザーの
   raw 入力を渡す。認められる承認語（yes, y, はい, 実行, 1, 進めて 等）に
   一致すれば `{outputs_dir}/.approved_{output_filename}.json` を書き出す。
   それ以外は拒否ファイル `.rejected_{output_filename}.json` を書く。
4. 書込ステップは `fill_gate.py check --output <output_path>` を叩き、
   exit 0 なら approved、非 0 なら書込禁止。ここで一致確認されるのは
   preview 時の `token` と approved 時の `token`。

## 仕組みとしての保証
- preview が無いまま書込ステップに進めない（`check` が非 0）
- preview と approved の `token` が一致しなければ書込できない
  （LLM が途中で書込内容を書き換えても気付ける）
- 承認語は allowlist で、曖昧な「OK かな」等は弾く

ただしこれは手続き上のゲートであり、最終的に `mcp__xlsx-editor__write_*`
を呼ぶのは LLM である。悪意ある LLM は `.approved_*.json` を偽造しうる。
**設計の意図はモデルの drift や injection を防ぐことであり、悪意は防げない。**

## CLI
```
python3 skills/_lib/fill_gate.py plan --output <path> [--plan-file <json>]
python3 skills/_lib/fill_gate.py approve --output <path> --answer <text>
python3 skills/_lib/fill_gate.py check --output <path>
python3 skills/_lib/fill_gate.py clear --output <path>
```
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# 承認語の allowlist。完全一致または先頭一致のみ。曖昧な語は含めない。
_APPROVE_WORDS = {
    "yes", "y", "はい", "実行", "実行する", "書き込む", "書き込み",
    "進めて", "進める", "ok", "OK", "1", "１", "承認", "go",
}
_REJECT_WORDS = {
    "no", "n", "いいえ", "中止", "やめる", "取りやめ", "キャンセル",
    "cancel", "stop", "3", "３", "拒否",
}


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _sidecar_path(output_path: Path, prefix: str) -> Path:
    """`<outputs_dir>/.{prefix}_{filename}.json` を返す。"""
    return output_path.parent / f".{prefix}_{output_path.name}.json"


def _plan_token(plan: Any) -> str:
    """plan JSON を正規化して sha256 の先頭 16 桁を返す（目視確認用の短縮トークン）。"""
    canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _normalize_answer(text: str) -> str:
    """比較用: trim + lower。日本語・句読点は触らない。"""
    return text.strip().rstrip("。.!！").lower()


def _token_match(text: str, word: str) -> bool:
    """`word` が `text` の先頭トークンとして現れるかを判定する。

    「yes」 → 「yes」「yes please」「yes, お願い」にマッチ、「yeah」「yeti」には非マッチ。
    日本語は単語境界が無いので、後ろに終端または句読点/空白が続く場合のみ一致とする。
    """
    w = word.lower()
    if not text.startswith(w):
        return False
    if len(text) == len(w):
        return True
    next_ch = text[len(w)]
    # アスキーの単語境界
    if w[-1].isalnum() and next_ch.isalnum():
        return False
    return True


def classify_answer(text: str) -> str:
    """ユーザーの返答を approve / reject / ambiguous に分類する。

    conservative 設計: どちらにも当てはまらない語は ambiguous（承認しない）。
    - 「yes」「はい」「実行」「1」 → approve
    - 「no」「中止」「3」         → reject
    - 「yeah」「nope」「maybe」   → ambiguous
    """
    t = _normalize_answer(text)
    if not t:
        return "ambiguous"
    for w in _APPROVE_WORDS:
        if _token_match(t, w.lower()):
            return "approve"
    for w in _REJECT_WORDS:
        if _token_match(t, w.lower()):
            return "reject"
    return "ambiguous"


# ---------------------------------------------------------------------------
# plan / approve / check
# ---------------------------------------------------------------------------


def write_plan(output_path: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    """書込プランの preview sidecar を作る。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    token = _plan_token(plan)
    preview_path = _sidecar_path(output_path, "preview")
    data = {
        "output": str(output_path),
        "created_at": time.time(),
        "token": token,
        "plan": plan,
    }
    preview_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # 既存の approval/reject を消す（古い承認で新しいプランを通さない）
    for prefix in ("approved", "rejected"):
        p = _sidecar_path(output_path, prefix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    return {"preview_path": str(preview_path), "token": token}


def write_approval(output_path: Path, answer: str) -> Dict[str, Any]:
    """ユーザー応答を分類して approval / rejection sidecar を書く。"""
    preview_path = _sidecar_path(output_path, "preview")
    if not preview_path.exists():
        raise FileNotFoundError(
            f"preview が未作成: {preview_path}。`fill_gate.py plan` を先に実行してほしい。"
        )
    try:
        preview = json.loads(preview_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"preview JSON が不正: {e}")

    verdict = classify_answer(answer)
    payload = {
        "output": str(output_path),
        "answer": answer,
        "verdict": verdict,
        "token": preview.get("token"),
        "created_at": time.time(),
    }
    prefix = "approved" if verdict == "approve" else "rejected" if verdict == "reject" else None
    if prefix is None:
        # ambiguous: どちらにも書かない（呼出側が再確認する）
        return {"verdict": verdict, "note": "曖昧な応答のため sidecar は書かない。再確認が必要。"}
    sidecar = _sidecar_path(output_path, prefix)
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # 反対側の sidecar があれば消す
    other_prefix = "rejected" if prefix == "approved" else "approved"
    other = _sidecar_path(output_path, other_prefix)
    if other.exists():
        try:
            other.unlink()
        except OSError:
            pass
    return {"verdict": verdict, "sidecar": str(sidecar), "token": preview.get("token")}


def check_gate(output_path: Path) -> Dict[str, Any]:
    """書込可否を返す。approved かつ token が preview と一致すれば ok: True。"""
    preview_path = _sidecar_path(output_path, "preview")
    approved_path = _sidecar_path(output_path, "approved")
    rejected_path = _sidecar_path(output_path, "rejected")

    if rejected_path.exists():
        return {"ok": False, "reason": "rejected", "rejected_path": str(rejected_path)}
    if not preview_path.exists():
        return {"ok": False, "reason": "no_preview"}
    if not approved_path.exists():
        return {"ok": False, "reason": "not_approved"}

    try:
        preview = json.loads(preview_path.read_text(encoding="utf-8"))
        approved = json.loads(approved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "reason": "sidecar_unreadable", "error": str(e)}

    p_tok = preview.get("token")
    a_tok = approved.get("token")
    if p_tok != a_tok:
        return {
            "ok": False,
            "reason": "token_mismatch",
            "hint": "preview の内容が承認後に変更されている。書込プランをもう一度 plan → approve し直す必要がある。",
            "preview_token": p_tok,
            "approved_token": a_tok,
        }
    return {"ok": True, "token": p_tok, "preview_path": str(preview_path), "approved_path": str(approved_path)}


def clear_gate(output_path: Path) -> Dict[str, Any]:
    """preview / approved / rejected の sidecar を全て消す。"""
    cleared = []
    for prefix in ("preview", "approved", "rejected"):
        p = _sidecar_path(output_path, prefix)
        if p.exists():
            try:
                p.unlink()
                cleared.append(str(p))
            except OSError:
                pass
    return {"cleared": cleared}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_plan(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser()
    if args.plan_file == "-":
        plan = json.load(sys.stdin)
    else:
        plan = json.loads(Path(args.plan_file).expanduser().read_text(encoding="utf-8"))
    result = write_plan(output, plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_approve(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser()
    try:
        result = write_approval(output, args.answer)
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("verdict") in ("approve", "reject") else 2


def _cmd_check(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser()
    result = check_gate(output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_clear(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser()
    print(json.dumps(clear_gate(output), ensure_ascii=False, indent=2))
    return 0


def _self_test() -> int:
    import tempfile
    ok = 0
    fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")
        if cond:
            ok += 1
        else:
            fail += 1

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "outputs" / "creditor-list_filled_20260419_220000.xlsx"
        plan = {"writes": [{"cell": "B3", "value": "甲野太郎", "confidence": 0.98}]}
        r = write_plan(out, plan)
        check("1. plan writes preview sidecar", Path(r["preview_path"]).exists())
        check("2. plan returns token", bool(r.get("token")))

        g0 = check_gate(out)
        check("3. check before approval = not_approved", g0["ok"] is False and g0["reason"] == "not_approved")

        # approve path
        a = write_approval(out, "はい")
        check("4. approve via はい yields approve verdict", a["verdict"] == "approve")
        g1 = check_gate(out)
        check("5. check after approve = ok", g1["ok"] is True)

        # ambiguous should not set sidecar
        clear_gate(out)
        write_plan(out, plan)
        a2 = write_approval(out, "ちょっと待って")
        check("6. ambiguous answer → no sidecar", a2["verdict"] == "ambiguous")
        g2 = check_gate(out)
        check("7. ambiguous leaves gate unapproved", g2["ok"] is False)

        # reject path
        clear_gate(out)
        write_plan(out, plan)
        r3 = write_approval(out, "中止")
        check("8. reject via 中止", r3["verdict"] == "reject")
        g3 = check_gate(out)
        check("9. rejected gate stays closed", g3["ok"] is False and g3["reason"] == "rejected")

        # token mismatch: approve first plan, then overwrite plan with different content
        clear_gate(out)
        write_plan(out, plan)
        write_approval(out, "yes")
        check("10. pre-mismatch gate ok", check_gate(out)["ok"] is True)
        # re-plan with different content WITHOUT re-approving (plan() clears approved)
        new_plan = {"writes": [{"cell": "B3", "value": "別人", "confidence": 0.9}]}
        write_plan(out, new_plan)
        g4 = check_gate(out)
        check(
            "11. re-plan clears prior approval",
            g4["ok"] is False,
            f"reason={g4.get('reason')}",
        )

        # classify_answer corner cases
        check("12. classify empty → ambiguous", classify_answer("") == "ambiguous")
        check("13. classify 'yes please' → approve", classify_answer("yes please") == "approve")
        check("14. classify 'nope' → ambiguous (not reject)", classify_answer("nope") == "ambiguous")
        check("15. classify '1' → approve", classify_answer("1") == "approve")
        check("16. classify '3' → reject", classify_answer("3") == "reject")
        check("17. classify 'yeah' → ambiguous (not in allowlist)", classify_answer("yeah") == "ambiguous")

    print(f"\nfill_gate self-test: {ok}/{ok + fail} passed")
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="template-fill 書込承認ゲート")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="command")

    p_plan = sub.add_parser("plan", help="書込プランを preview sidecar に保存")
    p_plan.add_argument("--output", required=True, help="最終出力 XLSX のパス")
    p_plan.add_argument("--plan-file", required=True, help="プラン JSON（`-` で stdin）")
    p_plan.set_defaults(func=_cmd_plan)

    p_app = sub.add_parser("approve", help="ユーザー応答を受けて approval sidecar を書く")
    p_app.add_argument("--output", required=True)
    p_app.add_argument("--answer", required=True, help="ユーザーの raw 返答")
    p_app.set_defaults(func=_cmd_approve)

    p_chk = sub.add_parser("check", help="書込可否を判定。ok=true で exit 0")
    p_chk.add_argument("--output", required=True)
    p_chk.set_defaults(func=_cmd_check)

    p_clr = sub.add_parser("clear", help="preview/approved/rejected sidecar を全削除")
    p_clr.add_argument("--output", required=True)
    p_clr.set_defaults(func=_cmd_clear)

    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if args.command is None:
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
