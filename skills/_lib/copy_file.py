#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""クロスプラットフォームのファイルコピーヘルパー。

`Bash(cp:*)` 許可は POSIX の `cp` コマンド前提で、Windows の PowerShell
では動作しない。代わりに本ヘルパーを呼び出す。

使い方:
    python3 skills/_lib/copy_file.py --src <source-path> --dst <destination-path>
    python3 skills/_lib/copy_file.py --src a.xlsx --dst b.xlsx --overwrite

挙動:
- `--overwrite` なしで宛先が既存の場合はエラー終了（誤上書き防止）
- 宛先ディレクトリが存在しない場合は作成する
- メタデータ（mtime等）は保持する（shutil.copy2 相当）

終了コード:
    0  成功
    1  引数バリデーションエラー
    2  I/O エラー
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="クロスプラットフォームのファイルコピー")
    ap.add_argument("--src", required=True, help="コピー元ファイルパス")
    ap.add_argument("--dst", required=True, help="コピー先ファイルパス")
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="宛先が存在しても上書きする（デフォルトは拒否）",
    )
    args = ap.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)

    if not src.exists():
        print(f"エラー: コピー元が存在しない: {src}", file=sys.stderr)
        return 1

    if not src.is_file():
        print(f"エラー: コピー元はファイルでなければならない: {src}", file=sys.stderr)
        return 1

    # シンボリックリンクをコピー元として受け付けない。
    # 攻撃者が templates/ 等にシンボリックリンクを配置すると、
    # リンク先（例: /etc/passwd や別件のクライアントファイル）の内容が
    # プラグイン管理下にコピーされる可能性があるため。
    if src.is_symlink():
        print(
            f"エラー: コピー元がシンボリックリンクである: {src}。"
            "セキュリティ上の理由で拒否する。",
            file=sys.stderr,
        )
        return 1

    if dst.exists() and not args.overwrite:
        print(
            f"エラー: 宛先が既に存在する: {dst}（上書きには --overwrite）",
            file=sys.stderr,
        )
        return 1

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst), follow_symlinks=False)
    except OSError as e:
        print(f"エラー: コピーに失敗した: {e}", file=sys.stderr)
        return 2

    print(f"コピー完了: {src} -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
