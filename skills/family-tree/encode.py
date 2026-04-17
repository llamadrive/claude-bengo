#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""家系図データの Base64 エンコーダ。

family-tree-template.html の `__GRAPH_DATA_B64__` プレースホルダを
UTF-8 JSON の Base64 エンコードで置換するためのヘルパー。

使い方:
    python3 skills/family-tree/encode.py --input data.json > out.b64
    python3 skills/family-tree/encode.py --json '{"persons":[...], "relationships":[...]}' > out.b64

Base64 エンコードを用いる理由:
    家系図データには戸籍 PDF から抽出した人物情報が含まれる。戸籍には
    任意の文字列（旧字体、異体字、稀に `</script>` に類似する配列）が
    含まれ得る。Base64 化することで HTML パーサーが payload を誤解釈する
    リスク（XSS / スクリプトタグ early-termination）を完全に排除する。
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path


def _load_data(args: argparse.Namespace) -> dict:
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    elif args.json is not None:
        text = args.json
    else:
        text = sys.stdin.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"invalid JSON: {e}"}), file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, dict):
        print(json.dumps({"error": "root JSON must be an object"}), file=sys.stderr)
        sys.exit(2)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Base64-encode family tree JSON")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--input", help="入力 JSON ファイルパス")
    src.add_argument("--json", help="入力 JSON 文字列（直接）")
    ap.add_argument(
        "--indent",
        action="store_true",
        help="JSON を整形してからエンコードする（デバッグ用）",
    )
    args = ap.parse_args()

    data = _load_data(args)

    # JSON 再シリアライズ: ensure_ascii=False で UTF-8 日本語を保持
    if args.indent:
        json_text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        json_text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    b64 = base64.b64encode(json_text.encode("utf-8")).decode("ascii")
    print(b64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
