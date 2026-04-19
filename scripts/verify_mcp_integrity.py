#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP 依存パッケージの整合性検証（v3.3.0〜）。

背景: 本プラグインは `.mcp.json` 経由で `@knorq/*`, `@agent-format/*` 等の
npm パッケージに機密文書（戸籍・訴状・通帳 PDF）を渡す。パッケージが
サプライチェーン攻撃で差し替えられれば、全クライアントの文書が流出する。

本スクリプトは:
  1. `.mcp.json` の各サーバ定義から npm パッケージ名とバージョンを抽出
  2. 期待される整合性ダイジェスト (`scripts/mcp_pinned.json`) と照合
  3. npm registry から現在公開されている tarball の integrity SHA-512 を取得
  4. 期待値と一致しなければ exit 1（plugin 使用を止めるべき）

使い方:
  python3 scripts/verify_mcp_integrity.py           # 検証のみ
  python3 scripts/verify_mcp_integrity.py --pin     # 現在公開中の値で pin を更新（開発者用）

pin ファイル (`scripts/mcp_pinned.json`) は git 追跡される。pin 更新は**明示的な
レビューを伴う作業** として扱う（CI で pin 更新 PR をブロックする運用推奨）。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
MCP_FILE = ROOT / ".mcp.json"
PIN_FILE = ROOT / "scripts" / "mcp_pinned.json"

NPM_REGISTRY = "https://registry.npmjs.org"


def _parse_mcp_json() -> List[Tuple[str, str, str]]:
    """.mcp.json から (server_name, package, version) のリストを返す。"""
    data = json.loads(MCP_FILE.read_text(encoding="utf-8"))
    servers = data.get("mcpServers", {})
    out: List[Tuple[str, str, str]] = []
    for name, spec in servers.items():
        args = spec.get("args", [])
        # `npx -y <pkg>@<ver>` を期待
        pkg_spec: Optional[str] = None
        for a in args:
            if a.startswith("@") and "@" in a[1:]:
                pkg_spec = a
                break
        if not pkg_spec:
            continue
        # 先頭 `@` から 2 つ目の `@` でバージョンを分離
        at_idx = pkg_spec.rfind("@")
        pkg = pkg_spec[:at_idx]
        ver = pkg_spec[at_idx + 1:]
        out.append((name, pkg, ver))
    return out


def _fetch_integrity(pkg: str, ver: str) -> Optional[str]:
    """npm registry から `dist.integrity`（SHA-512 base64）を取得する。"""
    url = f"{NPM_REGISTRY}/{pkg.replace('/', '%2F')}/{ver}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.URLError as e:
        print(f"警告: {pkg}@{ver} の registry 取得に失敗: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        return None
    dist = data.get("dist", {})
    return dist.get("integrity")


def _load_pins() -> Dict[str, Dict[str, str]]:
    """期待ダイジェストを読む。{pkg: {version: integrity}} 形式。"""
    if not PIN_FILE.exists():
        return {}
    try:
        return json.loads(PIN_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_pins(pins: Dict[str, Dict[str, str]]) -> None:
    PIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIN_FILE.write_text(
        json.dumps(pins, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify() -> int:
    """現行 .mcp.json の pin 一致を検証する。"""
    servers = _parse_mcp_json()
    pins = _load_pins()
    if not pins:
        print(
            "⚠ scripts/mcp_pinned.json が存在しない。初回は `--pin` で pin を生成してほしい。",
            file=sys.stderr,
        )
        return 2

    problems: List[str] = []
    checked = 0
    for name, pkg, ver in servers:
        expected = pins.get(pkg, {}).get(ver)
        if not expected:
            problems.append(
                f"  ⚠ {pkg}@{ver} ({name}) は pin されていない。"
                "—  scripts/mcp_pinned.json を更新してほしい"
            )
            continue
        actual = _fetch_integrity(pkg, ver)
        if actual is None:
            problems.append(f"  ⚠ {pkg}@{ver} の registry 取得に失敗")
            continue
        if actual != expected:
            problems.append(
                f"  ⛔ {pkg}@{ver} の integrity 不一致。"
                f"\n     expected: {expected}"
                f"\n     actual:   {actual}"
                "\n     サプライチェーン改ざんの可能性。本 plugin の利用を停止し、"
                "内容を監査してほしい。"
            )
            continue
        checked += 1
        print(f"  ✅ {pkg}@{ver} ({name}) — integrity 一致")

    if problems:
        print("\n" + "\n".join(problems))
        print(f"\n検証失敗: {len(problems)} 件の問題があった。")
        return 1
    print(f"\n検証成功: {checked} 件すべて pin と一致した。")
    return 0


def pin() -> int:
    """現行 .mcp.json の npm 公開値で pin ファイルを更新する（開発者用）。"""
    servers = _parse_mcp_json()
    pins = _load_pins()
    updated = 0
    for name, pkg, ver in servers:
        integrity = _fetch_integrity(pkg, ver)
        if not integrity:
            print(f"  ⚠ {pkg}@{ver} の integrity が取得できなかったためスキップ", file=sys.stderr)
            continue
        if pkg not in pins:
            pins[pkg] = {}
        before = pins[pkg].get(ver)
        pins[pkg][ver] = integrity
        if before != integrity:
            updated += 1
            print(f"  📌 {pkg}@{ver} = {integrity}")
    _save_pins(pins)
    print(f"\npin 更新: {updated} 件。{PIN_FILE.relative_to(ROOT)} を確認の上 commit してほしい。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="MCP サーバ依存パッケージの整合性検証")
    ap.add_argument("--pin", action="store_true", help="現行 npm 公開値で pin を更新する")
    args = ap.parse_args()
    if args.pin:
        return pin()
    return verify()


if __name__ == "__main__":
    sys.exit(main())
