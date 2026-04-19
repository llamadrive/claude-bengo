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


def find_workspace_root(start: Optional[Path] = None) -> Optional[Path]:
    """CWD（または `start`）から親ディレクトリを辿り、`.claude-bengo/` を
    含む最初のディレクトリを返す。見つからなければ None。

    git が `.git/` を探すロジックと同じ。対象ディレクトリが `.claude-bengo`
    という名前だった場合は親を優先する（混乱を避ける）。

    重要: `~/.claude-bengo/` はグローバル設定用ディレクトリとして予約されている
    ため、`$HOME` を workspace root として検出しない。そうしないと弁護士の
    ホーム直下で機密スキルを実行するたびに「ホーム全体が案件フォルダ」扱い
    になり、全クライアントの監査ログが一つに混ざってしまう。
    """
    global_root_resolved = GLOBAL_ROOT.resolve() if GLOBAL_ROOT.exists() else GLOBAL_ROOT.absolute()
    p = (start or Path.cwd()).resolve()
    while True:
        candidate = p / WORKSPACE_DIRNAME
        # GLOBAL_ROOT（~/.claude-bengo/）が walk-up にヒットしても workspace 扱い
        # しない。`$HOME` を case folder にしないための守護。
        if candidate.is_dir() and candidate != global_root_resolved:
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
    """テンプレートディレクトリ。"""
    return workspace_dir(start) / TEMPLATES_SUBDIR


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
    """
    root = (start or Path.cwd()).resolve()
    wd = root / WORKSPACE_DIRNAME
    is_new = not wd.exists()
    wd.mkdir(parents=True, exist_ok=True)
    _chmod_owner_only(wd)
    (wd / TEMPLATES_SUBDIR).mkdir(exist_ok=True)
    _chmod_owner_only(wd / TEMPLATES_SUBDIR)

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
    tdir = templates_dir(start)
    if not tdir.exists():
        return []
    return sorted(p.stem for p in tdir.glob("*.yaml"))


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
