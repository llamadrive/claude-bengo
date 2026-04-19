#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""初回クラウド送信同意ゲート（v3.3.0〜）。

背景: 本プラグインは機密文書（戸籍・訴状・通帳等）を Anthropic API 経由で
クラウドに送信する。READMEに書いてはいるが、senior low-tech lawyer が最初の
skill 実行前に読んでいる保証はない。コンプライアンス上、**機密文書を開く前に
必ずユーザーの明示的な同意を取る** 必要がある。

## 仕組み
- 同意状態は `~/.claude-bengo/global.json` の `consent_granted_at` に記録
- 同意したターミジョンも `consent_version` として記録する（同意内容が変われば
  再同意が必要になる）
- 機密スキルは Step 0 で `consent.py check` を叩き、exit 非 0 なら skill 全体を
  中断して「先に `/consent` で admin-setup → grant を実行してほしい」と案内する
- `consent.py grant` で同意を記録（`--version X` でバージョン指定、LLM が
  勝手に行わないように `--answer` 必須）

## 同意内容 (v1)
以下の内容にユーザーが同意したことを記録する:
1. クライアント機密文書が Anthropic PBC のクラウドで処理される（既定 US リージョン）
2. 弁護士法 §23（秘密保持）・個人情報保護法の遵守はユーザーの責任である
3. 本プラグインは弁護士業務の補助ツールであり、法的助言を提供しない（弁護士法 §72）
4. 監査ログは `.claude-bengo/audit.jsonl` に HMAC-SHA256 チェーン付きで記録される

ユーザーがこれを読んで明示的に承諾した時のみ `grant` を実行すること。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Dict, Optional

# 同意内容のバージョン。文言変更時に bump すると既存同意が失効して再取得される。
CURRENT_CONSENT_VERSION = "2"  # v3.3.0-iter1: admin-gated 化

# 承認語 allowlist。曖昧な語は承認として扱わない（fill_gate と同様の設計）。
_APPROVE_WORDS = {
    "yes", "y", "はい", "同意", "同意する", "承諾", "承諾する",
    "accept", "i consent", "確認した", "理解した",
}

# --- admin lock (事務所管理者パスフレーズ) ---

ADMIN_LOCK_FIELD = "admin_lock"  # global.json のキー
PBKDF2_ITERATIONS = 200_000       # 2026 時点の妥当なデフォルト
PBKDF2_ALGO = "sha256"


def _hash_passphrase(passphrase: str, salt: bytes) -> str:
    """PBKDF2-HMAC-SHA256 の hex を返す。"""
    dk = hashlib.pbkdf2_hmac(PBKDF2_ALGO, passphrase.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return dk.hex()


def _make_admin_lock(passphrase: str) -> Dict[str, str]:
    """admin.lock の dict を生成する（salt + hash + algo + iter）。"""
    salt = secrets.token_bytes(32)
    return {
        "algo": PBKDF2_ALGO,
        "iter": str(PBKDF2_ITERATIONS),
        "salt_hex": salt.hex(),
        "hash_hex": _hash_passphrase(passphrase, salt),
        "created_at": str(time.time()),
    }


def _verify_passphrase(passphrase: str, lock: Dict[str, str]) -> bool:
    """保存された admin lock と照合する。"""
    if not lock or not isinstance(lock, dict):
        return False
    try:
        salt = bytes.fromhex(lock.get("salt_hex", ""))
        iterations = int(lock.get("iter", "0"))
        algo = lock.get("algo", PBKDF2_ALGO)
        stored = lock.get("hash_hex", "")
    except (ValueError, TypeError):
        return False
    if iterations <= 0 or not salt or not stored:
        return False
    dk = hashlib.pbkdf2_hmac(algo, passphrase.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk.hex(), stored)


# ---------------------------------------------------------------------------
# ワークスペースヘルパー遅延 import
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
# check / grant / revoke
# ---------------------------------------------------------------------------


def has_admin_lock() -> bool:
    """admin.lock（事務所管理者パスフレーズ）が設定されているか。"""
    cfg = _load_global()
    lock = cfg.get(ADMIN_LOCK_FIELD)
    return isinstance(lock, dict) and "hash_hex" in lock and "salt_hex" in lock


def consent_status() -> Dict[str, object]:
    cfg = _load_global()
    granted = cfg.get("consent_granted_at")
    version = cfg.get("consent_version")
    admin = has_admin_lock()
    base = {"admin_lock": admin}
    if not granted:
        return {**base, "granted": False, "reason": "never_granted"}
    if version != CURRENT_CONSENT_VERSION:
        return {
            **base,
            "granted": False,
            "reason": "version_mismatch",
            "previous_version": version,
            "current_version": CURRENT_CONSENT_VERSION,
        }
    return {
        **base,
        "granted": True,
        "granted_at": granted,
        "version": version,
    }


def admin_setup(
    passphrase: str,
    *,
    force: bool = False,
    old_passphrase: Optional[str] = None,
) -> Dict[str, object]:
    """事務所管理者パスフレーズを初回設定する（takeover 不可、v3.3.0-iter2〜）。

    - 初回（既存 lock なし）: `passphrase` のみで成立
    - 再設定（既存 lock あり）: `force=True` **かつ** `old_passphrase` が現在の
      lock と一致する必要がある。以前は `--force` だけで上書きできたが、
      これでは共有ユーザー環境で admin lock を乗っ取られる恐れがあった
      （codex PE 指摘、v3.3.0-iter2 で修正）。
    - 紛失時の復旧: 事務所 IT 担当が `~/.claude-bengo/global.json` から
      `admin_lock` キーを手動削除する運用（そうすると初回扱いで再設定可能）

    パスフレーズは平文では保存せず、PBKDF2-HMAC-SHA256 で 200k 回ストレッチした
    hash のみ保存する。
    """
    if not passphrase or len(passphrase) < 8:
        return {"ok": False, "reason": "too_short", "hint": "8 文字以上のパスフレーズが必要"}
    cfg = _load_global()
    existing = cfg.get(ADMIN_LOCK_FIELD)
    if isinstance(existing, dict) and "hash_hex" in existing:
        # 既存 lock あり → force 必須 + 旧パスフレーズ一致必須
        if not force:
            return {
                "ok": False,
                "reason": "already_set",
                "hint": "admin lock は既に設定されている。変更には --force と --old-passphrase が必要。",
            }
        if not old_passphrase:
            return {
                "ok": False,
                "reason": "old_passphrase_required",
                "hint": "admin lock の上書きには現行パスフレーズの提示が必要（--old-passphrase）。",
            }
        if not _verify_passphrase(old_passphrase, existing):
            return {"ok": False, "reason": "bad_old_passphrase"}
    cfg[ADMIN_LOCK_FIELD] = _make_admin_lock(passphrase)
    _save_global(cfg)
    return {"ok": True, "created_at": cfg[ADMIN_LOCK_FIELD]["created_at"]}


def _require_admin(passphrase: Optional[str]) -> Optional[str]:
    """admin 認証を要求する。通れば None、ダメなら error reason を返す。

    - admin.lock が未設定: setup を案内
    - passphrase 未指定: admin-passphrase required
    - passphrase 不一致: bad_passphrase
    """
    cfg = _load_global()
    lock = cfg.get(ADMIN_LOCK_FIELD)
    if not isinstance(lock, dict):
        return "no_admin_lock"
    if not passphrase:
        return "admin_passphrase_required"
    if not _verify_passphrase(passphrase, lock):
        return "bad_passphrase"
    return None


def _classify(answer: str) -> str:
    t = (answer or "").strip().rstrip("。.!！").lower()
    if not t:
        return "ambiguous"
    for w in _APPROVE_WORDS:
        wl = w.lower()
        if t == wl or t.startswith(wl + " ") or t.startswith(wl + ",") or t.startswith(wl + "、"):
            return "approve"
    return "ambiguous"


def grant_consent(
    answer: str,
    *,
    version: str = CURRENT_CONSENT_VERSION,
    admin_passphrase: Optional[str] = None,
) -> Dict[str, object]:
    """ユーザーの返答を分類し、承認であれば global.json に記録する。

    v3.3.0-iter1〜: 事務所管理者 lock がある場合は `admin_passphrase` が必須。
    これにより「誰でも同意クリックで機密処理を解禁できる」状態を閉じる。
    admin lock が未設定の環境では初回セットアップを案内する（grant を通さない）。
    """
    # admin check（必須）
    err = _require_admin(admin_passphrase)
    if err == "no_admin_lock":
        return {
            "recorded": False,
            "reason": "no_admin_lock",
            "hint": "事務所管理者パスフレーズが未設定。`/consent admin-setup` を先に実行してほしい。",
        }
    if err == "admin_passphrase_required":
        return {
            "recorded": False,
            "reason": "admin_passphrase_required",
            "hint": "事務所管理者の承認が必要。--admin-passphrase を指定してほしい。",
        }
    if err == "bad_passphrase":
        return {"recorded": False, "reason": "bad_passphrase"}

    verdict = _classify(answer)
    if verdict != "approve":
        return {
            "recorded": False,
            "verdict": verdict,
            "hint": "明示的な「同意する / yes / accept」等が必要。曖昧な応答は承認として扱わない。",
        }
    cfg = _load_global()
    now = time.time()
    cfg["consent_granted_at"] = now
    cfg["consent_version"] = version
    # 記録用の逐語（管理者承認で記録、ユーザー応答とは分離）
    cfg["consent_answer"] = answer
    _save_global(cfg)
    return {"recorded": True, "verdict": "approve", "granted_at": now, "version": version}


def revoke_consent(*, admin_passphrase: Optional[str] = None) -> Dict[str, object]:
    """v3.3.0-iter1〜: revoke も admin 認証が必須。"""
    err = _require_admin(admin_passphrase)
    if err == "no_admin_lock":
        # lock が無い状態では consent もあり得ないはずだが念のため
        return {"revoked": False, "reason": "no_admin_lock"}
    if err == "admin_passphrase_required":
        return {"revoked": False, "reason": "admin_passphrase_required"}
    if err == "bad_passphrase":
        return {"revoked": False, "reason": "bad_passphrase"}

    cfg = _load_global()
    removed = []
    for k in ("consent_granted_at", "consent_version", "consent_answer"):
        if k in cfg:
            removed.append(k)
            cfg.pop(k, None)
    _save_global(cfg)
    return {"revoked": bool(removed), "removed_keys": removed}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


DISCLOSURE_TEXT = """
=== claude-bengo 機密文書処理 同意書 (version {v}) ===

本プラグインで機密文書（PDF・DOCX・XLSX）を処理すると、その内容は以下を
通じて送信・処理される:

  1. Anthropic PBC のクラウド API（既定リージョン: 米国）
  2. 必要に応じて MCP サーバ（xlsx-editor / docx-editor / agent-format）
  3. ローカルの監査ログ `.claude-bengo/audit.jsonl`（HMAC-SHA256 チェーン）

以下の事項を **ユーザーの責任** として明確に理解してほしい:

  - 弁護士法 §23（秘密保持義務）および個人情報保護法の遵守
  - 本プラグインは業務補助ツールであり、法的助言を提供しない（弁護士法 §72）
  - クラウド送信前にクライアントの承諾を得ることは弁護士の責務である

上記に同意する場合は、次のように明示的に入力してほしい:
    「同意する」または「yes」または「accept」

同意しないまま処理を進めることはできない。
""".strip()


def _cmd_status(args: argparse.Namespace) -> int:
    print(json.dumps(consent_status(), ensure_ascii=False, indent=2))
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    s = consent_status()
    if s.get("granted"):
        return 0
    print(json.dumps(s, ensure_ascii=False), file=sys.stderr)
    return 1


def _cmd_show(args: argparse.Namespace) -> int:
    print(DISCLOSURE_TEXT.format(v=CURRENT_CONSENT_VERSION))
    return 0


def _cmd_grant(args: argparse.Namespace) -> int:
    result = grant_consent(
        args.answer,
        version=CURRENT_CONSENT_VERSION,
        admin_passphrase=args.admin_passphrase,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("recorded") else 1


def _cmd_revoke(args: argparse.Namespace) -> int:
    print(json.dumps(revoke_consent(admin_passphrase=args.admin_passphrase), ensure_ascii=False, indent=2))
    return 0


def _cmd_admin_setup(args: argparse.Namespace) -> int:
    result = admin_setup(
        args.passphrase,
        force=args.force,
        old_passphrase=args.old_passphrase,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _self_test() -> int:
    import os
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
            s0 = consent_status()
            check("1. no consent by default", s0["granted"] is False and s0["reason"] == "never_granted")
            check("1b. no admin_lock by default", s0["admin_lock"] is False)

            # admin required for grant
            r_no_admin = grant_consent("同意する")
            check(
                "2. grant without admin lock → refused",
                r_no_admin["recorded"] is False and r_no_admin.get("reason") == "no_admin_lock",
            )

            # admin setup
            setup = admin_setup("short")
            check("3. short passphrase refused", setup["ok"] is False and setup["reason"] == "too_short")

            setup2 = admin_setup("firmpass2026!")
            check("4. valid passphrase accepted", setup2["ok"] is True)

            # cannot reset without --force
            setup3 = admin_setup("other-pass-2026")
            check("5. second setup without force refused", setup3["ok"] is False and setup3["reason"] == "already_set")

            # --force alone is not enough; old_passphrase required (v3.3.0-iter2)
            setup_force_no_old = admin_setup("other-pass-2026", force=True)
            check(
                "5b. --force alone rejected (old_passphrase required)",
                setup_force_no_old["ok"] is False and setup_force_no_old["reason"] == "old_passphrase_required",
            )

            # wrong old passphrase rejected
            setup_wrong_old = admin_setup("other-pass-2026", force=True, old_passphrase="wrong")
            check(
                "5c. wrong old_passphrase refused",
                setup_wrong_old["ok"] is False and setup_wrong_old["reason"] == "bad_old_passphrase",
            )

            # valid rotation works
            setup_rotate = admin_setup("new-firm-pass-2026!", force=True, old_passphrase="firmpass2026!")
            check("5d. valid passphrase rotation works", setup_rotate["ok"] is True)
            # revert to original for remaining tests
            admin_setup("firmpass2026!", force=True, old_passphrase="new-firm-pass-2026!")

            # grant requires admin_passphrase now
            r_bad = grant_consent("同意する", admin_passphrase="wrong")
            check("6. wrong passphrase refused", r_bad["recorded"] is False and r_bad["reason"] == "bad_passphrase")

            r_missing = grant_consent("同意する")
            check(
                "7. missing passphrase refused when admin lock set",
                r_missing["recorded"] is False and r_missing["reason"] == "admin_passphrase_required",
            )

            r_ok = grant_consent("同意する", admin_passphrase="firmpass2026!")
            check("8. grant with correct admin passphrase recorded", r_ok["recorded"] is True)

            s1 = consent_status()
            check("9. status shows granted + admin_lock", s1["granted"] is True and s1["admin_lock"] is True)

            # ambiguous still refused even with passphrase
            cfg = _load_global()
            cfg.pop("consent_granted_at", None)
            _save_global(cfg)
            r_amb = grant_consent("maybe", admin_passphrase="firmpass2026!")
            check("10. ambiguous answer still refused even with passphrase", r_amb["recorded"] is False)

            # "yeah" still not accepted (token boundary)
            r_yeah = grant_consent("yeah", admin_passphrase="firmpass2026!")
            check("11. 'yeah' not accepted as consent", r_yeah["recorded"] is False)

            # version bump invalidates even when granted
            grant_consent("yes", admin_passphrase="firmpass2026!")
            cfg = _load_global()
            cfg["consent_version"] = "0"
            _save_global(cfg)
            s2 = consent_status()
            check("12. version mismatch invalidates", s2["granted"] is False and s2["reason"] == "version_mismatch")

            # revoke requires admin too
            grant_consent("yes", admin_passphrase="firmpass2026!")
            rv_no = revoke_consent()
            check("13. revoke without passphrase refused", rv_no["revoked"] is False and rv_no.get("reason") == "admin_passphrase_required")

            rv_bad = revoke_consent(admin_passphrase="wrong")
            check("14. revoke with wrong passphrase refused", rv_bad["revoked"] is False)

            rv_ok = revoke_consent(admin_passphrase="firmpass2026!")
            check("15. revoke with correct passphrase succeeds", rv_ok["revoked"] is True)
            check("16. after revoke, status=not granted", consent_status()["granted"] is False)
        finally:
            ws.GLOBAL_ROOT = orig_gr
            ws.GLOBAL_CONFIG_FILE = orig_gc

    print(f"\nconsent self-test: {ok}/{ok + fail} passed")
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="claude-bengo 機密処理の初回同意ゲート")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="command")

    sub.add_parser("status", help="JSON で現在の同意状態を表示").set_defaults(func=_cmd_status)
    sub.add_parser("check", help="同意済なら exit 0、未同意なら exit 1").set_defaults(func=_cmd_check)
    sub.add_parser("show", help="同意書本文を表示（バージョン付き）").set_defaults(func=_cmd_show)

    p_grant = sub.add_parser("grant", help="ユーザー応答を受けて同意を記録（admin 認証必須）")
    p_grant.add_argument("--answer", required=True, help="ユーザーの raw 返答")
    p_grant.add_argument("--admin-passphrase", help="事務所管理者パスフレーズ")
    p_grant.set_defaults(func=_cmd_grant)

    p_rev = sub.add_parser("revoke", help="同意を取り消す（admin 認証必須）")
    p_rev.add_argument("--admin-passphrase", help="事務所管理者パスフレーズ")
    p_rev.set_defaults(func=_cmd_revoke)

    p_adm = sub.add_parser(
        "admin-setup",
        help="事務所管理者パスフレーズを初期設定する（初回のみ。変更は --force + --old-passphrase）",
    )
    p_adm.add_argument("--passphrase", required=True, help="新しい管理者パスフレーズ（8 文字以上）")
    p_adm.add_argument("--force", action="store_true", help="既存 lock を上書き（--old-passphrase も必要）")
    p_adm.add_argument("--old-passphrase", help="既存 lock 上書き時: 現行パスフレーズ")
    p_adm.set_defaults(func=_cmd_admin_setup)

    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if args.command is None:
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
