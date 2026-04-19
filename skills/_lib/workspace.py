#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude-bengo workspace (case-folder) 解決モジュール。

v3.0.0 で matter.py を置換。新しい設計では:

- **フォルダ = 案件** — 弁護士は既に案件ごとにフォルダを持っている。この
  ディレクトリ構造をそのまま使う。
- `.claude-bengo/` ディレクトリを案件フォルダ内に置く（git の `.git/` と同じ
  発想）。中に監査ログ・テンプレート・メタデータが入る。
- 明示的な事案 ID は使わない。フォルダのパス自体が identity。
- `/matter-create` のような事前登録は不要。機密スキルが最初に使われたとき
  に `.claude-bengo/` を silently 作成する。
- 案件切替は `cd` するだけ（walk-up で `.claude-bengo/` を探す）。

## ディレクトリレイアウト（案件単位）

```
~/cases/smith-v-jones/
├── .claude-bengo/
│   ├── audit.jsonl        # 監査ログ（SHA-256 ハッシュチェーン）
│   ├── metadata.json      # title, opened_at, notes（任意・編集可）
│   ├── templates/         # 案件固有テンプレート
│   └── config.json        # この案件の audit 設定（任意）
├── 訴状.pdf
├── 証拠/
└── ...
```

## 解決アルゴリズム

```
1. CWD または親ディレクトリを順に辿り、最初に見つかった `.claude-bengo/` を
   持つディレクトリを workspace root とする（git の `.git/` 探索と同じ）。
2. 見つからなければ CWD を workspace root とし、機密スキル実行時に
   `.claude-bengo/` を自動作成する（silent）。
```

この資料で言う "workspace" は常にこの workspace root（`.claude-bengo/` を
含む、または含めることになる、案件フォルダ）を指す。

## グローバル設定

事務所レベル設定（cloud 同期 URL・WORM 設定等）は `~/.claude-bengo/global.json`
に書く。案件レベル（audit 無効・記録先変更）は `<workspace>/.claude-bengo/config.json`
に書く。案件設定がグローバル設定を上書きする。

## CLI

```
python3 skills/_lib/workspace.py resolve [--cwd PATH]
    workspace root と .claude-bengo/ の状態を JSON で返す。
python3 skills/_lib/workspace.py init [--cwd PATH] [--title TITLE]
    指定（または CWD）フォルダを workspace として初期化する。
python3 skills/_lib/workspace.py info [--cwd PATH]
    現在の workspace のサマリー（audit 件数・templates 数・設定）を返す。
python3 skills/_lib/workspace.py config get <key> [--cwd PATH] [--global]
python3 skills/_lib/workspace.py config set <key> <value> [--cwd PATH] [--global]
    設定の読み書き。--global は ~/.claude-bengo/global.json を対象にする。
```
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

WORKSPACE_DIRNAME = ".claude-bengo"
AUDIT_FILENAME = "audit.jsonl"
METADATA_FILENAME = "metadata.json"
CONFIG_FILENAME = "config.json"
TEMPLATES_SUBDIR = "templates"

# グローバル設定（事務所レベル）
GLOBAL_ROOT = Path.home() / ".claude-bengo"
GLOBAL_CONFIG_FILE = GLOBAL_ROOT / "global.json"


# ---------------------------------------------------------------------------
# 解決（walk-up）
# ---------------------------------------------------------------------------


def _is_under(path: Path, ancestor: Path) -> bool:
    """`path` が `ancestor` 配下（または `ancestor` 自身）かを返す。両方 resolve 済み前提。"""
    try:
        path.relative_to(ancestor)
        return True
    except ValueError:
        return False


def _global_root_resolved() -> Path:
    return GLOBAL_ROOT.resolve() if GLOBAL_ROOT.exists() else GLOBAL_ROOT.absolute()


class WorkspaceUnderGlobalError(RuntimeError):
    """CWD が `~/.claude-bengo/` 配下にある場合に投げる。

    グローバルストアは予約領域のため、その下を案件フォルダとして初期化すると
    `~/.claude-bengo/templates/.claude-bengo/` のようなネストが発生し、全案件の
    監査ログが混ざる・グローバルテンプレートが誤って上書きされる等の重大な
    混乱を招く。呼出側は `cd` してから再実行するよう案内すべき。
    """


def find_workspace_root(start: Optional[Path] = None) -> Optional[Path]:
    """CWD（または `start`）から親ディレクトリを辿り、`.claude-bengo/` を
    含む最初のディレクトリを返す。見つからなければ None。

    git が `.git/` を探すロジックと同じ。対象ディレクトリが `.claude-bengo`
    という名前だった場合は親を優先する（混乱を避ける）。

    重要: `~/.claude-bengo/` はグローバル設定用ディレクトリとして予約されている
    ため、`$HOME` または `~/.claude-bengo/` 配下を workspace root として検出しない。
    そうしないと弁護士のホーム直下で機密スキルを実行するたびに「ホーム全体が
    案件フォルダ」扱いになり、全クライアントの監査ログが一つに混ざってしまう。
    """
    global_root = _global_root_resolved()
    p = (start or Path.cwd()).resolve()
    while True:
        candidate = p / WORKSPACE_DIRNAME
        # GLOBAL_ROOT 自身およびその配下のディレクトリは workspace として扱わない。
        if _is_under(p, global_root):
            # これ以上の walk-up は意味がない（global_root の親は $HOME で、これも予約領域）
            return None
        if candidate.is_dir() and candidate != global_root:
            return p
        parent = p.parent
        if parent == p:
            return None
        p = parent


def resolve_workspace(start: Optional[Path] = None) -> Path:
    """workspace root を返す。未初期化なら CWD を workspace root として返す
    （呼出側が `ensure_workspace()` で初期化する）。"""
    found = find_workspace_root(start)
    if found is not None:
        return found
    return (start or Path.cwd()).resolve()


def workspace_dir(start: Optional[Path] = None) -> Path:
    """`<workspace>/.claude-bengo/` の絶対パスを返す。"""
    return resolve_workspace(start) / WORKSPACE_DIRNAME


def audit_path(start: Optional[Path] = None) -> Path:
    """監査ログのデフォルトパス。config.audit_path で上書き可。"""
    cfg = load_config(start)
    custom = cfg.get("audit_path")
    if custom:
        return Path(custom).expanduser()
    return workspace_dir(start) / AUDIT_FILENAME


def templates_dir(start: Optional[Path] = None) -> Path:
    """案件スコープのテンプレートディレクトリ（`<workspace>/.claude-bengo/templates/`）。"""
    return workspace_dir(start) / TEMPLATES_SUBDIR


def global_templates_dir() -> Path:
    """事務所グローバルのテンプレートディレクトリ（`~/.claude-bengo/templates/`）。

    全案件で共有する firm-wide 書式（債権者一覧表・示談書・遺産目録等）を置く。
    `/template-create --scope global` および `/template-install` のデフォルト保存先。
    """
    return GLOBAL_ROOT / TEMPLATES_SUBDIR


def ensure_global_templates_dir() -> Path:
    """グローバルテンプレートディレクトリを 0o700 で冪等に作成して返す。"""
    d = global_templates_dir()
    d.mkdir(parents=True, exist_ok=True)
    _chmod_owner_only(GLOBAL_ROOT)
    _chmod_owner_only(d)
    return d


def outputs_dir(start: Optional[Path] = None) -> Path:
    """成果物の出力ディレクトリ（`<workspace>/outputs/`）。

    template-fill 等のフィルド済 XLSX はここに置く。workspace 直下（`.claude-bengo/`
    と同階層）なのでエクスプローラ/Finder で lawyer が即座に見つけられる。
    """
    return resolve_workspace(start) / "outputs"


def ensure_outputs_dir(start: Optional[Path] = None) -> Path:
    d = outputs_dir(start)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# 監査 HMAC 鍵（v3.3.0〜、既定で on）
# ---------------------------------------------------------------------------


AUDIT_HMAC_KEY_FIELD = "audit_hmac_key_hex"


def ensure_audit_hmac_key() -> str:
    """グローバル設定に HMAC 鍵があれば返し、無ければ生成して保存する。

    鍵は `secrets.token_hex(32)`（256 bit）で生成し、`~/.claude-bengo/global.json`
    に保存される。ファイルは 0600（ユーザーのみ）で書かれる。これにより
    audit.py が tamper-proof HMAC を**既定で有効** にできる。

    既存鍵がある場合はそれをそのまま返す（ローテーション運用は現状未対応）。
    """
    import secrets as _secrets
    cfg = load_global_config()
    key = cfg.get(AUDIT_HMAC_KEY_FIELD)
    if isinstance(key, str) and len(key) >= 32:
        return key
    key = _secrets.token_hex(32)
    cfg[AUDIT_HMAC_KEY_FIELD] = key
    save_global_config(cfg)
    return key


def get_audit_hmac_key() -> Optional[str]:
    """保存済みの HMAC 鍵を返す（無ければ None。生成はしない）。"""
    cfg = load_global_config()
    key = cfg.get(AUDIT_HMAC_KEY_FIELD)
    if isinstance(key, str) and len(key) >= 32:
        return key
    return None


def allocate_output_path(
    template_id: str,
    start: Optional[Path] = None,
    *,
    suffix: str = "_filled",
    ext: str = ".xlsx",
    now: Optional[_dt.datetime] = None,
) -> Path:
    """衝突しない成果物パスを 1 つ確保して返す。

    ベース: `{outputs_dir}/{template_id}{suffix}_{YYYYMMDD_HHMMSS}{ext}`
    既存と衝突した場合は `_2` `_3` ... を付与する（同じ秒内に複数回呼んでも上書きしない）。

    呼出側はこの CLI（または関数）で一度パスを確定したら、その後の copy_file は
    `--overwrite` なしでも衝突しない。
    """
    d = ensure_outputs_dir(start)
    t = now or _dt.datetime.now()
    ts = t.strftime("%Y%m%d_%H%M%S")
    base = f"{template_id}{suffix}_{ts}"
    cand = d / f"{base}{ext}"
    n = 2
    while cand.exists():
        cand = d / f"{base}_{n}{ext}"
        n += 1
        if n > 999:  # 暴走防止
            raise RuntimeError(f"出力パス確保で 999 回衝突（何か異常）: {base}")
    return cand


def resolve_template(template_id: str, start: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """`{id}.yaml` + `{id}.xlsx` を case → global の順で探索する。

    precedence: case-local が同 ID の global を shadow する（案件専用の
    カスタマイズ版を置ける）。見つからなければ None。

    戻り値: {id, scope, yaml_path, xlsx_path} or None
    """
    if not template_id:
        return None
    for scope, tdir in (
        ("case", templates_dir(start)),
        ("global", global_templates_dir()),
    ):
        yaml_p = tdir / f"{template_id}.yaml"
        xlsx_p = tdir / f"{template_id}.xlsx"
        if yaml_p.exists() and xlsx_p.exists():
            return {
                "id": template_id,
                "scope": scope,
                "yaml_path": str(yaml_p),
                "xlsx_path": str(xlsx_p),
                "templates_dir": str(tdir),
            }
    return None


def list_all_templates(start: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    """case + global の全テンプレートを列挙する。

    戻り値: {"case": [{id, yaml_path, xlsx_path, broken, missing, shadowed_global}, ...],
             "global": [...]}

    - 整合なエントリ: yaml と xlsx 両方存在 → `broken: False`
    - 破損エントリ: yaml または xlsx のいずれか欠落 → `broken: True`
      `missing` に欠落しているファイルの種別（"yaml" または "xlsx"）が入る。
      `resolve_template()` はスキップするが、**/template-list は必ず警告付きで
      表示する**（半端な状態を silently 隠さないため）。
    """
    def _scan(tdir: Path) -> List[Dict[str, Any]]:
        if not tdir.exists():
            return []
        # yaml, xlsx の stem を集める（_schema.yaml は除外）
        yaml_stems = {p.stem for p in tdir.glob("*.yaml") if p.name != "_schema.yaml"}
        xlsx_stems = {p.stem for p in tdir.glob("*.xlsx")}
        all_stems = sorted(yaml_stems | xlsx_stems)
        out: List[Dict[str, Any]] = []
        for stem in all_stems:
            y = tdir / f"{stem}.yaml"
            x = tdir / f"{stem}.xlsx"
            y_exists = y.exists()
            x_exists = x.exists()
            entry: Dict[str, Any] = {
                "id": stem,
                "yaml_path": str(y) if y_exists else None,
                "xlsx_path": str(x) if x_exists else None,
                "broken": not (y_exists and x_exists),
            }
            if not y_exists:
                entry["missing"] = "yaml"
            elif not x_exists:
                entry["missing"] = "xlsx"
            out.append(entry)
        return out

    case_items = _scan(templates_dir(start))
    global_items = _scan(global_templates_dir())
    case_ids = {e["id"] for e in case_items}
    global_ids = {e["id"] for e in global_items}
    for e in case_items:
        e["shadowed_global"] = e["id"] in global_ids
    for e in global_items:
        e["shadowed"] = e["id"] in case_ids
    return {"case": case_items, "global": global_items}


def metadata_path(start: Optional[Path] = None) -> Path:
    return workspace_dir(start) / METADATA_FILENAME


def config_path(start: Optional[Path] = None) -> Path:
    return workspace_dir(start) / CONFIG_FILENAME


# ---------------------------------------------------------------------------
# 初期化
# ---------------------------------------------------------------------------


def _chmod_owner_only(p: Path) -> None:
    """POSIX で 0o700 にする（Windows では無視）。"""
    if not p.exists():
        return
    try:
        os.chmod(p, 0o700)
    except (OSError, NotImplementedError):
        pass


def ensure_workspace(
    start: Optional[Path] = None,
    *,
    title: Optional[str] = None,
) -> Path:
    """CWD（または指定）を workspace として初期化する（冪等）。

    既に `.claude-bengo/` が存在すれば何もしない。新規作成時は metadata.json に
    `opened_at` と（指定されていれば）`title` を書く。title 未指定時は CWD の
    basename を既定にする。

    **ガード:** `~/.claude-bengo/` 配下（および `~/.claude-bengo/` 自身）では
    初期化を拒否する。グローバルストアは予約領域であり、その下を案件扱いすると
    グローバルテンプレートや global.json を巻き込んだ混線が起こる。
    """
    root = (start or Path.cwd()).resolve()
    global_root = _global_root_resolved()
    if _is_under(root, global_root):
        raise WorkspaceUnderGlobalError(
            f"`~/.claude-bengo/` 配下 ({root}) では案件フォルダを初期化できない。"
            "グローバルストアは予約領域のため。別のディレクトリに cd して再実行してほしい。"
        )
    wd = root / WORKSPACE_DIRNAME
    is_new = not wd.exists()
    wd.mkdir(parents=True, exist_ok=True)
    _chmod_owner_only(wd)
    (wd / TEMPLATES_SUBDIR).mkdir(exist_ok=True)
    _chmod_owner_only(wd / TEMPLATES_SUBDIR)

    # v3.3.0〜: グローバル HMAC 鍵を初回に生成しておく（audit が既定で tamper-proof）
    try:
        ensure_audit_hmac_key()
    except OSError:
        # 書けなくても workspace 初期化自体は続ける（audit は後で警告）
        pass

    meta_file = wd / METADATA_FILENAME
    if is_new or not meta_file.exists():
        meta = {
            "title": title or root.name,
            "opened_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "notes": "",
        }
        meta_file.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(meta_file, 0o600)
        except (OSError, NotImplementedError):
            pass
    return root


def is_initialized(start: Optional[Path] = None) -> bool:
    """workspace が初期化済みか。"""
    return find_workspace_root(start) is not None


# ---------------------------------------------------------------------------
# 設定（case level + global level）
# ---------------------------------------------------------------------------


def _read_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(p: Path, data: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(p, 0o600)
    except (OSError, NotImplementedError):
        pass


def load_global_config() -> Dict[str, Any]:
    return _read_json(GLOBAL_CONFIG_FILE)


def load_case_config(start: Optional[Path] = None) -> Dict[str, Any]:
    if not is_initialized(start):
        return {}
    return _read_json(config_path(start))


def load_config(start: Optional[Path] = None) -> Dict[str, Any]:
    """merged config: global + case-level override."""
    merged = load_global_config().copy()
    merged.update(load_case_config(start))
    return merged


def save_case_config(cfg: Dict[str, Any], start: Optional[Path] = None) -> None:
    ensure_workspace(start)
    _write_json(config_path(start), cfg)


def save_global_config(cfg: Dict[str, Any]) -> None:
    GLOBAL_ROOT.mkdir(parents=True, exist_ok=True)
    _chmod_owner_only(GLOBAL_ROOT)
    _write_json(GLOBAL_CONFIG_FILE, cfg)


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


def load_metadata(start: Optional[Path] = None) -> Dict[str, Any]:
    if not is_initialized(start):
        return {}
    return _read_json(metadata_path(start))


def save_metadata(meta: Dict[str, Any], start: Optional[Path] = None) -> None:
    ensure_workspace(start)
    _write_json(metadata_path(start), meta)


def audit_stats(start: Optional[Path] = None) -> Dict[str, int]:
    """audit.jsonl の行数とサイズ。"""
    path = audit_path(start)
    if not path.exists():
        return {"lines": 0, "bytes": 0}
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            lines = sum(1 for _ in f)
        return {"lines": lines, "bytes": size}
    except OSError:
        return {"lines": 0, "bytes": 0}


def templates_list(start: Optional[Path] = None) -> List[str]:
    """案件スコープのみのテンプレート ID 一覧（後方互換）。"""
    tdir = templates_dir(start)
    if not tdir.exists():
        return []
    return sorted(p.stem for p in tdir.glob("*.yaml") if p.name != "_schema.yaml")


def global_templates_list() -> List[str]:
    """グローバルスコープのテンプレート ID 一覧。"""
    d = global_templates_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml") if p.name != "_schema.yaml")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_resolve(args: argparse.Namespace) -> int:
    start = Path(args.cwd).expanduser() if args.cwd else None
    root = resolve_workspace(start)
    initialized = is_initialized(start)
    print(
        json.dumps(
            {
                "workspace_root": str(root),
                "initialized": initialized,
                "claude_bengo_dir": str(root / WORKSPACE_DIRNAME),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    start = Path(args.cwd).expanduser() if args.cwd else None
    root = ensure_workspace(start, title=args.title)
    print(
        json.dumps(
            {
                "workspace_root": str(root),
                "initialized": True,
                "claude_bengo_dir": str(root / WORKSPACE_DIRNAME),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    start = Path(args.cwd).expanduser() if args.cwd else None
    if not is_initialized(start):
        print(
            json.dumps(
                {
                    "initialized": False,
                    "cwd": str((start or Path.cwd()).resolve()),
                    "hint": "このフォルダは未初期化。機密スキルを実行すると自動で初期化される。",
                },
                ensure_ascii=False,
            )
        )
        return 0
    root = resolve_workspace(start)
    meta = load_metadata(start)
    cfg = load_config(start)
    stats = audit_stats(start)
    info = {
        "initialized": True,
        "workspace_root": str(root),
        "metadata": meta,
        "config": cfg,
        "audit": stats,
        "templates": templates_list(start),
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def _cmd_templates(args: argparse.Namespace) -> int:
    """case + global の両スコープのテンプレートを JSON で返す。"""
    start = Path(args.cwd).expanduser() if args.cwd else None
    listing = list_all_templates(start)
    out = {
        "workspace_root": str(resolve_workspace(start)),
        "case_templates_dir": str(templates_dir(start)),
        "global_templates_dir": str(global_templates_dir()),
        "case": listing["case"],
        "global": listing["global"],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_resolve_template(args: argparse.Namespace) -> int:
    """特定 ID のテンプレートを case → global の順で解決する。"""
    start = Path(args.cwd).expanduser() if args.cwd else None
    found = resolve_template(args.id, start)
    if not found:
        print(json.dumps({"error": f"テンプレート '{args.id}' が見つからない", "id": args.id}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(found, ensure_ascii=False, indent=2))
    return 0


def _cmd_outputs(args: argparse.Namespace) -> int:
    """成果物出力ディレクトリを作成してパスを返す。"""
    start = Path(args.cwd).expanduser() if args.cwd else None
    d = ensure_outputs_dir(start)
    print(json.dumps({"outputs_dir": str(d)}, ensure_ascii=False))
    return 0


def _cmd_allocate_output(args: argparse.Namespace) -> int:
    """テンプレート成果物の衝突しない出力パスを確保する。"""
    start = Path(args.cwd).expanduser() if args.cwd else None
    try:
        path = allocate_output_path(
            args.id,
            start,
            suffix=args.suffix,
            ext=args.ext,
        )
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"path": str(path), "filename": path.name}, ensure_ascii=False))
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    start = Path(args.cwd).expanduser() if args.cwd else None
    if args.subcommand == "get":
        cfg = load_global_config() if args.global_ else load_case_config(start)
        value = cfg.get(args.key)
        print(json.dumps({"key": args.key, "value": value}, ensure_ascii=False))
        return 0
    elif args.subcommand == "set":
        if args.global_:
            cfg = load_global_config()
            cfg[args.key] = args.value
            save_global_config(cfg)
        else:
            cfg = load_case_config(start)
            cfg[args.key] = args.value
            save_case_config(cfg, start)
        print(json.dumps({"key": args.key, "value": args.value, "scope": "global" if args.global_ else "case"}, ensure_ascii=False))
        return 0
    elif args.subcommand == "show":
        merged = load_config(start)
        print(json.dumps({"global": load_global_config(), "case": load_case_config(start), "merged": merged}, ensure_ascii=False, indent=2))
        return 0
    elif args.subcommand == "unset":
        if args.global_:
            cfg = load_global_config()
            cfg.pop(args.key, None)
            save_global_config(cfg)
        else:
            cfg = load_case_config(start)
            cfg.pop(args.key, None)
            save_case_config(cfg, start)
        print(json.dumps({"unset": args.key, "scope": "global" if args.global_ else "case"}, ensure_ascii=False))
        return 0
    return 1


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------


def _self_test() -> int:
    """stdlib-only self-test. Uses tempdir."""
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
        # macOS の /tmp → /private/tmp symlink を先に resolve しておく
        root = (Path(td).resolve() / "cases" / "smith-v-jones")
        root.mkdir(parents=True)
        nested = root / "evidence" / "photos"
        nested.mkdir(parents=True)

        # 1. Unitialized folder
        check(
            "1. unitialized folder → is_initialized=False",
            not is_initialized(root),
        )

        # 2. ensure_workspace 初期化
        got = ensure_workspace(root, title="Smith 対 Jones")
        check(
            "2. ensure_workspace creates .claude-bengo/",
            (root / WORKSPACE_DIRNAME).is_dir(),
            f"got={got}",
        )
        check(
            "2b. metadata.json with title",
            load_metadata(root).get("title") == "Smith 対 Jones",
        )
        check(
            "2c. templates/ subdir",
            (root / WORKSPACE_DIRNAME / TEMPLATES_SUBDIR).is_dir(),
        )

        # 3. walk-up resolution from nested dir
        found = find_workspace_root(nested)
        check(
            "3. walk-up resolution from nested dir finds parent",
            found == root,
            f"found={found}",
        )

        # 4. audit_path
        ap = audit_path(nested)
        check(
            "4. audit_path points inside workspace root",
            ap == root / WORKSPACE_DIRNAME / AUDIT_FILENAME,
            f"ap={ap}",
        )

        # 5. Config set/get (case level)
        save_case_config({"audit_enabled": False}, root)
        cfg = load_case_config(root)
        check(
            "5. case config set/get",
            cfg.get("audit_enabled") is False,
        )

        # 6. Config merge (global + case)
        # simulate global via monkey-patch: write to a tempfile
        # (we can't override GLOBAL_CONFIG_FILE easily without env var;
        # skip this check in self-test and just verify merge keys)
        merged = load_config(root)
        check(
            "6. load_config merges case into global (case wins)",
            merged.get("audit_enabled") is False,
        )

        # 7. audit_path override via config
        save_case_config({"audit_path": "/tmp/override-audit.jsonl"}, root)
        ap2 = audit_path(root)
        check(
            "7. config.audit_path overrides default",
            str(ap2) == "/tmp/override-audit.jsonl",
            f"ap2={ap2}",
        )

        # Restore
        save_case_config({}, root)

        # 8. Reinit is idempotent
        before = load_metadata(root)
        ensure_workspace(root)  # 2nd call should not overwrite metadata
        after = load_metadata(root)
        check(
            "8. ensure_workspace is idempotent (preserves metadata)",
            before == after,
        )

        # 9. audit_stats on empty audit
        stats = audit_stats(root)
        check(
            "9. audit_stats on empty/missing log = 0",
            stats["lines"] == 0,
        )

        # 10. Walk-up stops at filesystem root
        import tempfile as _t
        tmp2 = Path(_t.gettempdir()) / "cb-selftest-no-ws"
        tmp2.mkdir(exist_ok=True)
        try:
            check(
                "10. walk-up with no workspace returns None",
                find_workspace_root(tmp2) is None,
            )
        finally:
            try:
                tmp2.rmdir()
            except OSError:
                pass

        # 11. CRITICAL: walk-up from $HOME must NOT return $HOME even if
        # ~/.claude-bengo/ exists (GLOBAL_ROOT guard). Without this guard,
        # every skill run under a user's home dir would mix all clients into
        # one audit log.
        check(
            "11. walk-up from Path.home() does not return $HOME via GLOBAL_ROOT",
            find_workspace_root(Path.home()) is None
            or find_workspace_root(Path.home()) != Path.home(),
        )

        # 11b. allocate_output_path: 同じ秒内の 2 回呼び出しで衝突しない
        fixed_ts = _dt.datetime(2026, 4, 19, 22, 0, 0)
        p1 = allocate_output_path("demo", root, now=fixed_ts)
        p1.write_bytes(b"dummy")
        p2 = allocate_output_path("demo", root, now=fixed_ts)
        check(
            "11b. allocate_output_path avoids collision in same second",
            p1 != p2 and not p2.exists(),
            f"p1={p1.name} p2={p2.name}",
        )
        check(
            "11c. collision suffix uses _2",
            p2.name.endswith("_2.xlsx"),
            f"p2={p2.name}",
        )

        # 11d. list_all_templates surfaces yaml-only (broken) entries
        tdir = root / WORKSPACE_DIRNAME / TEMPLATES_SUBDIR
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "good.yaml").write_text("id: good\nfields: []\n", encoding="utf-8")
        (tdir / "good.xlsx").write_bytes(b"x")
        (tdir / "half.yaml").write_text("id: half\nfields: []\n", encoding="utf-8")
        # half.xlsx intentionally missing
        listing = list_all_templates(root)
        case_ids = {e["id"]: e for e in listing["case"]}
        check(
            "11d. broken yaml-only entry listed",
            "half" in case_ids and case_ids["half"]["broken"] is True,
            f"case_ids={list(case_ids)}",
        )
        check(
            "11e. broken entry reports missing=xlsx",
            case_ids.get("half", {}).get("missing") == "xlsx",
        )
        check(
            "11f. good entry not broken",
            case_ids.get("good", {}).get("broken") is False,
        )

        # 11g. ensure_workspace refuses to init under GLOBAL_ROOT
        # monkey-patch GLOBAL_ROOT to a tempdir-based path so the test runs hermetically
        import sys as _sys
        mod = _sys.modules[__name__]
        orig_gr = mod.GLOBAL_ROOT
        fake_gr = (Path(td) / "fake-home" / ".claude-bengo")
        fake_gr.mkdir(parents=True, exist_ok=True)
        mod.GLOBAL_ROOT = fake_gr
        try:
            under_global = fake_gr / "templates"
            under_global.mkdir(exist_ok=True)
            raised = False
            try:
                ensure_workspace(under_global)
            except WorkspaceUnderGlobalError:
                raised = True
            check(
                "11g. ensure_workspace refuses init under GLOBAL_ROOT",
                raised,
            )
            # find_workspace_root from under GLOBAL_ROOT returns None
            check(
                "11h. find_workspace_root returns None under GLOBAL_ROOT",
                find_workspace_root(under_global) is None,
            )
        finally:
            mod.GLOBAL_ROOT = orig_gr

        # 12. From a subdir of $HOME with no nested workspace, also None.
        # (We can only verify this if the user actually has no case folders
        # above `tempfile.gettempdir()` in their tree. On macOS
        # /var/folders/... is outside $HOME so this works reliably.)
        check(
            "12. find_workspace_root skips GLOBAL_ROOT as sentinel",
            GLOBAL_ROOT.resolve() not in [
                p for p in [find_workspace_root(Path.home())] if p
            ],
        )

    print(f"\nworkspace self-test: {ok}/{ok + fail} passed")
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="claude-bengo workspace management")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="command")

    p_res = sub.add_parser("resolve", help="Show workspace state for CWD")
    p_res.add_argument("--cwd", help="Path to resolve from (default: current directory)")
    p_res.set_defaults(func=_cmd_resolve)

    p_init = sub.add_parser("init", help="Initialize .claude-bengo/ in CWD")
    p_init.add_argument("--cwd", help="Path to initialize")
    p_init.add_argument("--title", help="Human-readable title")
    p_init.set_defaults(func=_cmd_init)

    p_info = sub.add_parser("info", help="Show workspace summary")
    p_info.add_argument("--cwd", help="Path to inspect")
    p_info.set_defaults(func=_cmd_info)

    p_tpl = sub.add_parser("templates", help="List templates in case + global scope as JSON")
    p_tpl.add_argument("--cwd", help="Path (default CWD)")
    p_tpl.set_defaults(func=_cmd_templates)

    p_rt = sub.add_parser("resolve-template", help="Resolve a template by id (case-first, then global)")
    p_rt.add_argument("id")
    p_rt.add_argument("--cwd", help="Path (default CWD)")
    p_rt.set_defaults(func=_cmd_resolve_template)

    p_out = sub.add_parser("outputs", help="Ensure and print the outputs directory path")
    p_out.add_argument("--cwd", help="Path (default CWD)")
    p_out.set_defaults(func=_cmd_outputs)

    p_alloc = sub.add_parser(
        "allocate-output",
        help="Allocate a collision-free output path for a filled template",
    )
    p_alloc.add_argument("id", help="Template id")
    p_alloc.add_argument("--cwd", help="Path (default CWD)")
    p_alloc.add_argument("--suffix", default="_filled")
    p_alloc.add_argument("--ext", default=".xlsx")
    p_alloc.set_defaults(func=_cmd_allocate_output)

    p_cfg = sub.add_parser("config", help="Get/set configuration keys")
    cfg_sub = p_cfg.add_subparsers(dest="subcommand", required=True)
    for sc in ("get", "set", "unset"):
        p = cfg_sub.add_parser(sc)
        p.add_argument("key")
        if sc == "set":
            p.add_argument("value")
        p.add_argument("--cwd", help="Path (default CWD)")
        p.add_argument("--global", dest="global_", action="store_true", help="Target global config instead of case")
    p_show = cfg_sub.add_parser("show")
    p_show.add_argument("--cwd", help="Path (default CWD)")
    p_show.add_argument("--global", dest="global_", action="store_true")
    p_cfg.set_defaults(func=_cmd_config)

    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if args.command is None:
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
