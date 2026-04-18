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
import sys
import urllib.parse
import webbrowser
from pathlib import Path

VIEWER_URL = "https://knorq-ai.github.io/agent-format/"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help=".agent file path")
    ap.add_argument(
        "--no-open",
        action="store_true",
        help="Print the viewer URL to stdout instead of launching a browser (for SSH / headless / audit use).",
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
