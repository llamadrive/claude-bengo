#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Open a .agent file in the public agent-format viewer.

Reads the file, URI-encodes its contents into the viewer's hash fragment, then
opens the resulting URL in the user's default browser. The hash stays on the
client (browsers don't send fragments to the server), so legal document
content never leaves the user's machine in network requests.

Usage:
    python3 skills/family-tree/open_viewer.py --input family_tree_YYYY-MM-DD.agent
    python3 skills/family-tree/open_viewer.py --input ... --no-open   # print URL only
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import urllib.parse
import webbrowser
from pathlib import Path

VIEWER_URL = "https://knorq-ai.github.io/agent-format/"

# Windows ShellExecute / cmd.exe accept long URLs via os.startfile (no hard
# 8191 CMD limit), but some older tool-chains truncate. Warn past this
# threshold so the user knows to copy the URL manually if the browser
# opens a blank page.
WIN_URL_WARN = 32_000


def _in_claude_code_cli() -> bool:
    """True when invoked from a Claude Code CLI session.

    Claude Code sets `CLAUDECODE=1` and `CLAUDE_CODE_ENTRYPOINT=cli`.
    Claude Desktop does not set these; in Desktop the @agent-format/mcp
    server already renders the `.agent` inline, so auto-opening a second
    browser tab would be redundant.
    """
    return os.environ.get("CLAUDECODE") == "1"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help=".agent file path")
    ap.add_argument(
        "--no-open",
        action="store_true",
        help="Print the viewer URL to stdout instead of launching a browser (for SSH / headless / audit use).",
    )
    ap.add_argument(
        "--auto",
        action="store_true",
        help="Open the browser only when running inside Claude Code CLI "
        "(checks $CLAUDECODE=1). In Claude Desktop the MCP already renders "
        "inline, so this flag avoids opening a redundant browser tab. "
        "When the check fails, the URL is printed instead.",
    )
    args = ap.parse_args()

    p = Path(args.input)
    if not p.exists():
        print(f"エラー: ファイルが見つからない: {p}", file=sys.stderr)
        return 1

    content = p.read_text(encoding="utf-8")
    # Validate it's JSON up front so we fail with a clear message rather than
    # opening a broken page in the browser.
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        print(
            f"エラー: .agent ファイルが有効な JSON ではない: {e}",
            file=sys.stderr,
        )
        return 2

    encoded = urllib.parse.quote(content)
    url = f"{VIEWER_URL}#{encoded}"

    # Windows long-URL advisory: even though os.startfile avoids the 8191
    # CMD limit, some browser shims truncate. Warn the user so they can
    # copy manually if the page loads blank.
    if platform.system() == "Windows" and len(url) > WIN_URL_WARN:
        print(
            f"警告: URL が {len(url)} 文字と長い。Windows ブラウザ経路で "
            f"切り詰められる場合は --no-open で URL を取得し、viewer へ "
            f"ドラッグ&ドロップしてほしい。",
            file=sys.stderr,
        )

    # --auto: opt-in auto-open gated on the Claude Code CLI env var.
    # Protects against a future world where /family-tree is invoked from
    # Claude Desktop (where MCP already renders inline) and we don't want
    # a second browser tab popping open.
    if args.auto and not _in_claude_code_cli():
        print(
            "Claude Code CLI ではない環境のため、ブラウザ自動起動を抑止した。",
            file=sys.stderr,
        )
        print(f"Viewer URL:\n{url}")
        return 0

    if args.no_open:
        print(url)
        return 0

    opened = webbrowser.open(url, new=2)  # new=2 prefers new tab over new window
    if not opened:
        # Fallback: print URL so the user can still copy/paste
        print(
            "webbrowser.open がブラウザ起動を拒否した。以下の URL を手動で開いてほしい:",
            file=sys.stderr,
        )
        print(url)
        return 1

    print(f"既定のブラウザで {p.name} を開いた。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
