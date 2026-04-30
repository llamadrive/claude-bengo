#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""初回使用時の案内メッセージ（非ブロッキング）。

claude-bengo は Claude Code のプラグインであり、文書の送受信は Claude Code
本体 (Anthropic API) の仕組みで行われる。本プラグイン独自のクラウド送信経路は
ない。したがって本モジュールは **同意ゲートではなく** 初回使用時の 1 回のみの
informational notice である:

  - 本プラグインがローカル追加する振る舞い（監査ログ等）を一言だけ知らせる
  - 所属事務所の AI 利用ポリシー確認を促す
  - 確認キーワード・パスフレーズ・ブロッキングは一切なし
  - 2 回目以降は silently exit 0

状態は `~/.claude-bengo/global.json` の `first_run_notice_shown_at` に記録する。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict


NOTICE_TEXT = """
bengo-toolkit へようこそ。

本プラグインは Claude Code 上で動くツール群で、文書の送受信は Claude Code
本体 (Anthropic API) の仕組みで行われる。プラグイン独自のクラウド送信経路
はない。データ取扱いは Claude Code の利用規約に従う。

本プラグインがローカルで追加するのは:
  ・監査ログ  .claude-bengo/audit.jsonl（案件フォルダ内、HMAC チェーン付き）
  ・同梱の法律書式・計算ロジック・出力ディレクトリ

クライアント文書を処理する前に、所属事務所の AI 利用ポリシーを一度確認
しておくことを推奨する。以降この案内は表示されない。
""".strip()


# ---------------------------------------------------------------------------
# workspace ヘルパー遅延 import
# ---------------------------------------------------------------------------


def _ws():
    import importlib
    here = str(Path(__file__).resolve().parent)
    added = False
    if here not in sys.path:
        sys.path.insert(0, here)
        added = True
    try:
        return importlib.import_module("workspace")
    finally:
        if added:
            try:
                sys.path.remove(here)
            except ValueError:
                pass


def _load_global() -> Dict[str, object]:
    return _ws().load_global_config()


def _save_global(cfg: Dict[str, object]) -> None:
    _ws().save_global_config(cfg)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def notice_status() -> Dict[str, object]:
    cfg = _load_global()
    shown = cfg.get("first_run_notice_shown_at")
    return {"shown": bool(shown), "shown_at": shown}


def mark_shown() -> Dict[str, object]:
    cfg = _load_global()
    now = time.time()
    cfg["first_run_notice_shown_at"] = now
    _save_global(cfg)
    return {"shown_at": now}


def reset() -> Dict[str, object]:
    cfg = _load_global()
    removed = cfg.pop("first_run_notice_shown_at", None) is not None
    _save_global(cfg)
    return {"reset": removed}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_notice(args: argparse.Namespace) -> int:
    """初回なら NOTICE_TEXT を stdout に出して mark。既出なら silently exit 0。"""
    st = notice_status()
    if st["shown"] and not args.force:
        return 0
    print(NOTICE_TEXT)
    mark_shown()
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    print(json.dumps(notice_status(), ensure_ascii=False, indent=2))
    return 0


def _cmd_reset(args: argparse.Namespace) -> int:
    print(json.dumps(reset(), ensure_ascii=False))
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

    ws = _ws()
    with tempfile.TemporaryDirectory() as td:
        orig_gr = ws.GLOBAL_ROOT
        orig_gc = ws.GLOBAL_CONFIG_FILE
        fake_gr = Path(td) / ".claude-bengo"
        ws.GLOBAL_ROOT = fake_gr
        ws.GLOBAL_CONFIG_FILE = fake_gr / "global.json"
        try:
            check("1. not shown by default", notice_status()["shown"] is False)
            mark_shown()
            check("2. after mark_shown, status reports shown", notice_status()["shown"] is True)
            reset()
            check("3. reset clears shown flag", notice_status()["shown"] is False)
        finally:
            ws.GLOBAL_ROOT = orig_gr
            ws.GLOBAL_CONFIG_FILE = orig_gc

    print(f"\nfirst_run self-test: {ok}/{ok + fail} passed")
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="claude-bengo 初回使用案内（非ブロッキング）")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="command")

    p_notice = sub.add_parser("notice", help="初回のみ案内を出して mark。既出なら silent")
    p_notice.add_argument("--force", action="store_true", help="shown でも強制表示（テスト用）")
    p_notice.set_defaults(func=_cmd_notice)

    sub.add_parser("status", help="JSON で現在の案内表示状態を返す").set_defaults(func=_cmd_status)
    sub.add_parser("reset", help="shown フラグを削除（テスト用）").set_defaults(func=_cmd_reset)

    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if args.command is None:
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
