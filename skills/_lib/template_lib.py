#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude-bengo 同梱テンプレートのレジストリと `/template-install` バックエンド。

同梱テンプレートはプラグインディレクトリの `templates/_bundled/{id}/` に
`{id}.yaml` + `{id}.xlsx` のペアで配置される。`_registry.yaml` が
利用可能なテンプレートのメタデータを列挙する。

`/template-install` はアクティブな matter の `templates/` ディレクトリへ
同梱テンプレートをコピーする。matter 未設定では動作しない（機密情報を扱う
`template-create` / `template-fill` と同じ制約）。

## CLI

```
python3 skills/_lib/template_lib.py list [--format json]
    同梱テンプレート一覧を表示する
python3 skills/_lib/template_lib.py install <id> [--matter <id>] [--replace]
    指定テンプレートをアクティブ matter にコピーする
python3 skills/_lib/template_lib.py show <id>
    テンプレートのメタデータ詳細を表示する
```
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

# プラグインディレクトリ配下の同梱ディレクトリ
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
BUNDLED_DIR = PLUGIN_ROOT / "templates" / "_bundled"
REGISTRY_FILE = BUNDLED_DIR / "_registry.yaml"
MANIFEST_FILE = BUNDLED_DIR / "_manifest.sha256"

# 同梱テンプレート ID は conservative regex（ファイルシステム安全）
BUNDLED_ID_RE = re.compile(r"^[a-z0-9][-a-z0-9_]{0,63}$")


# ---------------------------------------------------------------------------
# workspace.py の遅延ロード（v3.0.0〜）
# ---------------------------------------------------------------------------


def _load_workspace():
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


# ---------------------------------------------------------------------------
# レジストリ読込
# ---------------------------------------------------------------------------


def _parse_registry_entry(block: str) -> Optional[Dict[str, str]]:
    """`_registry.yaml` のエントリブロックを簡易パースする。

    矢印マーカー（`- id: ...`）で始まるブロックを dict に変換する。
    複数行値は `|` スカラー相当で扱う（matter.py の _read_metadata と同じ規約）。
    """
    entry: Dict[str, str] = {}
    current_key: Optional[str] = None
    current_lines: List[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            entry[current_key] = "\n".join(current_lines).rstrip()
        current_key = None
        current_lines = []

    for raw in block.splitlines():
        stripped = raw.rstrip()
        if current_key is not None and raw.startswith("    "):
            current_lines.append(raw[4:])
            continue
        flush()
        # 先頭 `- id:` を通常の key: value として扱う
        s = stripped.lstrip("- ")
        if not s or s.startswith("#"):
            continue
        if ":" not in s:
            continue
        k, _, v = s.partition(":")
        k = k.strip()
        v = v.strip()
        if v == "|":
            current_key = k
            current_lines = []
            continue
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        entry[k] = v
    flush()
    return entry if entry else None


def load_registry() -> List[Dict[str, str]]:
    """`_registry.yaml` を読み、エントリのリストを返す。

    簡易パーサ。行頭 `- id:` を各エントリの開始と見なし、次の `- id:` か
    EOF までをそのエントリに含める。インデントは矢印マーカー直下の
    4 スペース前提。
    """
    if not REGISTRY_FILE.exists():
        return []
    text = REGISTRY_FILE.read_text(encoding="utf-8")

    # `templates:` 配下の `- id: ...` エントリを抽出する。
    in_templates = False
    blocks: List[List[str]] = []
    current: List[str] = []

    for raw in text.splitlines():
        s = raw.rstrip()
        if not in_templates:
            if s.startswith("templates:"):
                in_templates = True
            continue
        # 次の top-level key で終了
        if s and not s.startswith(" ") and not s.startswith("#") and ":" in s and not s.lstrip().startswith("-"):
            break
        stripped = s.lstrip()
        if stripped.startswith("- id:"):
            if current:
                blocks.append(current)
            current = [s]
        elif current:
            current.append(s)

    if current:
        blocks.append(current)

    entries: List[Dict[str, str]] = []
    for b in blocks:
        # 各ブロック: 先頭行から `  ` プレフィックスを剥がす
        normalized = []
        for line in b:
            if line.startswith("    "):
                normalized.append(line[2:])  # インデントを 2 段剥がす
            elif line.startswith("  - "):
                normalized.append(line[2:])
            elif line.startswith("  "):
                normalized.append(line[2:])
            else:
                normalized.append(line)
        entry = _parse_registry_entry("\n".join(normalized))
        if entry and "id" in entry:
            # 同梱ファイルの実在確認
            bid = entry["id"]
            yaml_p = BUNDLED_DIR / bid / f"{bid}.yaml"
            xlsx_p = BUNDLED_DIR / bid / f"{bid}.xlsx"
            entry["_yaml_exists"] = str(yaml_p.exists())
            entry["_xlsx_exists"] = str(xlsx_p.exists())
            entry["_yaml_path"] = str(yaml_p)
            entry["_xlsx_path"] = str(xlsx_p)
            entries.append(entry)

    return entries


def find_template(bundled_id: str) -> Optional[Dict[str, str]]:
    """指定 ID の同梱テンプレートを返す。無ければ None。"""
    if not BUNDLED_ID_RE.match(bundled_id):
        return None
    for e in load_registry():
        if e.get("id") == bundled_id:
            return e
    return None


# ---------------------------------------------------------------------------
# マニフェスト検証（v2.6.1〜）
#
# プラグインクローン後に悪意ある第三者が templates/_bundled/ 配下の
# YAML/XLSX を書き換える「テンプレートすり替え攻撃」を検知する。
# マニフェストは `scripts/build_bundled_forms.py` により生成され、
# リポジトリに git 追跡される。install 時に対象ファイルの SHA-256 を
# 計算し、マニフェスト記載のハッシュと照合する。
# ---------------------------------------------------------------------------


def _load_manifest() -> Dict[str, str]:
    """`_manifest.sha256` を読んで {相対パス: sha256} の dict を返す。

    マニフェストが存在しない場合は空 dict（後方互換。install は警告付きで続行）。
    """
    if not MANIFEST_FILE.exists():
        return {}
    result: Dict[str, str] = {}
    try:
        for line in MANIFEST_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                result[parts[1]] = parts[0]
    except OSError:
        return {}
    return result


def _sha256(path: Path) -> str:
    """ファイルの SHA-256（16進）を返す。"""
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_bundled_integrity(bundled_id: str) -> Optional[str]:
    """指定テンプレートのファイルがマニフェストと一致するか検証する。

    戻り値:
        None: 整合（またはマニフェスト未整備で検証スキップ）
        str : 不一致の詳細メッセージ
    """
    manifest = _load_manifest()
    if not manifest:
        # F-037: マニフェストが存在しない場合は install を拒否する。
        # 旧実装は "warn + proceed" だったが、これはマニフェスト削除を攻撃経路
        # として使える。明示的に --skip-integrity フラグでのみ許可する。
        return (
            "_manifest.sha256 が存在しない。テンプレート整合性検証ができないため install を中止する。"
            "プラグインクローンが破損している可能性がある。`/plugin install claude-bengo@claude-bengo` で再取得するか、"
            "やむをえず先に進める場合は --skip-integrity を明示指定してほしい。"
        )

    for ext in ("yaml", "xlsx"):
        rel = f"{bundled_id}/{bundled_id}.{ext}"
        expected = manifest.get(rel)
        if not expected:
            return f"マニフェストに {rel} のエントリがない（同梱ファイルが不完全）"
        full = BUNDLED_DIR / rel
        if not full.exists():
            return f"{rel} が存在しない"
        actual = _sha256(full)
        if actual != expected:
            return (
                f"テンプレート '{bundled_id}' のファイル {rel} が改ざんされている可能性がある。\n"
                f"  expected: {expected}\n"
                f"  actual  : {actual}\n"
                f"プラグインを `/plugin install claude-bengo@claude-bengo` で再取得することを検討してほしい。"
            )
    return None


# ---------------------------------------------------------------------------
# インストール
# ---------------------------------------------------------------------------


def install_template(
    bundled_id: str,
    replace: bool = False,
    skip_integrity: bool = False,
) -> Dict[str, str]:
    """同梱テンプレートを現在の workspace のテンプレートディレクトリへコピーする。

    v3.0.0 で matter_id 引数を廃止。workspace 解決 (CWD walk-up) に統一した。
    workspace が未初期化なら CWD に silently 作成する。

    戻り値: {yaml_dst, xlsx_dst, workspace_root, bundled_id, replaced, integrity_verified}
    """
    ws = _load_workspace()
    ws.ensure_workspace()  # silently init if needed

    entry = find_template(bundled_id)
    if not entry:
        raise ValueError(f"同梱テンプレート '{bundled_id}' は見つからない。/template-install で一覧を確認してほしい。")

    # 整合性検証（v2.6.1〜）
    integrity_verified = False
    if not skip_integrity:
        err = _verify_bundled_integrity(bundled_id)
        if err:
            raise ValueError(f"テンプレート整合性検証失敗: {err}")
        integrity_verified = MANIFEST_FILE.exists()

    src_yaml = Path(entry["_yaml_path"])
    src_xlsx = Path(entry["_xlsx_path"])
    if not src_yaml.exists():
        raise FileNotFoundError(f"{src_yaml} が存在しない（レジストリと同梱ファイルの不整合）")
    if not src_xlsx.exists():
        raise FileNotFoundError(f"{src_xlsx} が存在しない（レジストリと同梱ファイルの不整合）")

    dst_dir = ws.templates_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_yaml = dst_dir / f"{bundled_id}.yaml"
    dst_xlsx = dst_dir / f"{bundled_id}.xlsx"

    if (dst_yaml.exists() or dst_xlsx.exists()) and not replace:
        raise FileExistsError(
            f"現在の workspace に既に '{bundled_id}' が存在する。上書きには --replace を指定してほしい。"
        )

    shutil.copy2(src_yaml, dst_yaml, follow_symlinks=False)
    shutil.copy2(src_xlsx, dst_xlsx, follow_symlinks=False)

    return {
        "bundled_id": bundled_id,
        "workspace_root": str(ws.resolve_workspace()),
        "yaml_dst": str(dst_yaml),
        "xlsx_dst": str(dst_xlsx),
        "replaced": replace,
        "integrity_verified": integrity_verified,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> int:
    entries = load_registry()
    if args.format == "json":
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0
    if not entries:
        print("同梱テンプレートが見つからない。")
        return 0
    print("利用可能な同梱テンプレート:")
    print()
    # カテゴリで group 化
    by_cat: Dict[str, List[Dict[str, str]]] = {}
    for e in entries:
        by_cat.setdefault(e.get("category", "その他"), []).append(e)
    for cat in sorted(by_cat):
        print(f"  [{cat}]")
        for e in by_cat[cat]:
            warn = "" if e.get("_yaml_exists") == "True" and e.get("_xlsx_exists") == "True" else " (⚠ 同梱ファイル不足)"
            title = e.get("title", e["id"])
            print(f"    {e['id']:<22}  {title}{warn}")
            if e.get("description"):
                desc = e["description"].splitlines()[0][:80]
                print(f"                              {desc}")
        print()
    print("インストール方法:")
    print("  /template-install <id>         — アクティブ matter に同梱テンプレートをコピー")
    print("  /template-install <id> --replace — 既存を上書き")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    # v3.0.0: workspace 解決（CWD walk-up）。--matter は deprecated で無視される。
    # ID は取得できたが存在しない場合は install_template 側で
    # 「matter が存在しない」エラーを出させる（exit 1）

    try:
        result = install_template(
            args.bundled_id,
            replace=args.replace,
            skip_integrity=getattr(args, "skip_integrity", False),
        )
    except (ValueError, FileNotFoundError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except FileExistsError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 3

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    e = find_template(args.bundled_id)
    if not e:
        print(json.dumps({"error": f"'{args.bundled_id}' が見つからない"}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(e, ensure_ascii=False, indent=2))
    return 0


def _self_test() -> int:
    """サニティチェック。同梱テンプレートのファイル整合性を検証する。"""
    entries = load_registry()
    if not entries:
        print("  [WARN] no bundled templates (registry empty)")
        return 0
    all_ok = True
    for e in entries:
        bid = e.get("id", "?")
        if e.get("_yaml_exists") != "True":
            print(f"  [FAIL] {bid}: yaml missing at {e.get('_yaml_path')}")
            all_ok = False
        elif e.get("_xlsx_exists") != "True":
            print(f"  [FAIL] {bid}: xlsx missing at {e.get('_xlsx_path')}")
            all_ok = False
        else:
            # YAML parseability check
            yaml_p = Path(e["_yaml_path"])
            text = yaml_p.read_text(encoding="utf-8")
            if "fields:" not in text:
                print(f"  [FAIL] {bid}: yaml missing 'fields:' block")
                all_ok = False
                continue
            print(f"  [PASS] {bid}: yaml + xlsx present, fields block ok")
    print(f"\ntemplate_lib: registry has {len(entries)} entries")
    return 0 if all_ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="claude-bengo 同梱テンプレート管理")
    ap.add_argument("--self-test", action="store_true", help="同梱テンプレートの整合性をチェックする")
    sub = ap.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="同梱テンプレートの一覧")
    p_list.add_argument("--format", choices=["text", "json"], default="text")

    p_show = sub.add_parser("show", help="テンプレートの詳細")
    p_show.add_argument("bundled_id")

    p_inst = sub.add_parser("install", help="アクティブ matter にインストール")
    p_inst.add_argument("bundled_id")
    p_inst.add_argument("--matter", help="matter を明示指定（省略時は resolve 結果）")
    p_inst.add_argument("--replace", action="store_true", help="既存を上書き")
    p_inst.add_argument(
        "--skip-integrity",
        action="store_true",
        help="マニフェスト検証をスキップ（非推奨、デバッグ用）",
    )

    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    if args.command is None:
        ap.print_help()
        return 1

    handlers = {"list": _cmd_list, "install": _cmd_install, "show": _cmd_show}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
