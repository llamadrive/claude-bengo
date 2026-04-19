#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""リリース前に実クライアント成果物がリポジトリに残っていないかを検査する（v3.3.0〜）。

背景: 開発者が自分の案件で動作確認すると `family_tree_YYYY-MM-DD_{氏名}.html`
等の実クライアント由来ファイルがリポジトリ root に生成される。`.gitignore` で
追跡対象外になっていても、開発マシン上の release tarball / rsync / IDE の
インデクサ等で漏洩経路になりうる。

本スクリプトは release 前に以下を検査し、1 件でも該当ファイルがあれば exit 1:

  - `family_tree_*.{html,agent}`
  - `lawsuit_report_*.{html,agent}`
  - `*_filled_*.xlsx`（outputs/ 以外の場所）
  - `*_reviewed.docx`
  - `.claude-bengo/` ディレクトリ（workspace が repo 内にある）
  - `.env` / `credentials.json`

CI から `python3 scripts/pre_release_check.py` を実行し、exit 0 でなければ
release tag を打たせないようにする運用を推奨。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent


def _is_gitignored(rel_path: str) -> bool:
    """git check-ignore で rel_path が ignore 済みか確認する。

    ディレクトリ単位の ignore（例: `.gitignore` で `.claude-bengo`）にも対応する
    ため、git 自身に問い合わせる。git がない / 非 git 環境では False を返す
    （従来の厳格な挙動に戻る）。
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", rel_path],
            capture_output=True,
            timeout=5,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

# (glob, description) の組
CLIENT_ARTIFACT_PATTERNS: List[Tuple[str, str]] = [
    ("family_tree_*.html", "family-tree 出力（HTML）"),
    ("family_tree_*.agent", "family-tree 出力（agent）"),
    ("lawsuit_report_*.html", "lawsuit-analysis 出力"),
    ("lawsuit_report_*.agent", "lawsuit-analysis 出力"),
    ("*_filled_*.xlsx", "template-fill 出力"),
    ("*_reviewed.docx", "typo-check 出力"),
    ("outputs/*", "outputs ディレクトリの残骸"),
]

FORBIDDEN_DIRS: List[Tuple[str, str]] = [
    (".claude-bengo", "案件 workspace がリポジトリ内にある"),
]

FORBIDDEN_FILES: List[Tuple[str, str]] = [
    (".env", "環境変数ファイル"),
    ("credentials.json", "認証情報ファイル"),
    ("secrets.yaml", "シークレット YAML"),
]


def scan(respect_gitignore: bool = True) -> List[str]:
    findings: List[str] = []

    def _skip(rel_str: str) -> bool:
        if rel_str.startswith("fixtures/") or rel_str.startswith("templates/_bundled/"):
            return True
        if respect_gitignore and _is_gitignored(rel_str):
            return True
        return False

    for pattern, desc in CLIENT_ARTIFACT_PATTERNS:
        for p in ROOT.glob(pattern):
            rel = p.relative_to(ROOT)
            rel_str = str(rel)
            if _skip(rel_str):
                continue
            findings.append(f"  ⛔ {rel_str} ({desc})")
    for name, desc in FORBIDDEN_DIRS:
        d = ROOT / name
        if d.is_dir():
            if _skip(name) or _skip(name + "/"):
                continue
            findings.append(f"  ⛔ {name}/ ({desc})")
    for name, desc in FORBIDDEN_FILES:
        f = ROOT / name
        if f.is_file():
            if _skip(name):
                continue
            findings.append(f"  ⛔ {name} ({desc})")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="リリース前の実クライアント成果物検出")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="警告も失敗扱い（追加パターンを後で拡張するため）",
    )
    ap.add_argument(
        "--no-gitignore",
        action="store_true",
        help="gitignore 済みパスもチェック対象に含める（厳格モード。開発機でも .claude-bengo/ を置いてほしくない場合に使う）",
    )
    args = ap.parse_args()

    findings = scan(respect_gitignore=not args.no_gitignore)
    if not findings:
        print("✅ リリース前チェック OK — 実クライアント成果物はリポジトリに存在しない。")
        return 0
    print("⚠ リリース前チェック失敗:")
    for f in findings:
        print(f)
    print("\n上記ファイル／ディレクトリを削除するか、別の場所（開発者の案件フォルダ等）に")
    print("移動してから release tag を打ってほしい。.gitignore 登録だけでは不十分:")
    print("tarball / rsync / IDE インデクサ経由で漏洩する可能性がある。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
