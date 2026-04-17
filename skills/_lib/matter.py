#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude-bengo マター（事案）管理モジュール。

法律事務所が複数のクライアント案件を同一の端末で処理する場合、
テンプレート・監査ログ・作業成果物を事案ごとに分離する必要がある。
本モジュールは事案識別子（matter id）の解決・ディレクトリ管理・メタデータ
読み書きを担当する。

## ディレクトリレイアウト

```
~/.claude-bengo/
├── matters/
│   ├── smith-v-jones/
│   │   ├── metadata.yaml           事案メタデータ（title, client, 事件番号, ...）
│   │   ├── templates/
│   │   │   ├── 財産目録.yaml
│   │   │   └── 財産目録.xlsx
│   │   └── audit.jsonl             事案固有の監査ログ（ハッシュチェーン）
│   └── 20260417-a7b3c2/
│       └── ...
├── current-matter                  /matter-switch で設定した既定事案 ID
├── session_id.txt
└── cache/
    └── law-search/...              事案横断（公開法令データのため分離不要）
```

作業ディレクトリにも事案ポインタを置ける:

```
~/cases/smith-v-jones/
├── .claude-bengo-matter-ref        1 行で事案 ID のみ記載
├── 訴状.pdf
└── ...
```

`cd ~/cases/smith-v-jones` すると Level 3 で自動検出される。

## 事案 ID 解決の優先順位

1. `--matter <id>` フラグ（最優先。呼出元が明示指定）
2. 環境変数 `MATTER_ID`（シェルセッション単位）
3. `{cwd}/.claude-bengo-matter-ref`（作業ディレクトリポインタ）
4. `~/.claude-bengo/current-matter`（/matter-switch で設定した既定値）

いずれも未設定の場合、機密スキルはエラーを返して `/matter-create` 等の
案内を出す。非機密スキル（law-search, inheritance-calc, verify,
bengo-update）は事案設定不要で動作する。

## CLI

```
python3 skills/_lib/matter.py resolve [--cwd PATH]
    アクティブな事案 ID と解決元（flag/env/cwd-ref/current/none）を JSON で出す。
python3 skills/_lib/matter.py list
    登録済み事案の一覧を JSON で出す。
python3 skills/_lib/matter.py info <matter-id>
    指定事案のメタデータ・パス・監査ログサイズを出す。
python3 skills/_lib/matter.py create <matter-id> [--title ...] [--client ...] [--case-number ...]
    事案ディレクトリとメタデータを作成する。
python3 skills/_lib/matter.py switch <matter-id>
    current-matter を更新する。
python3 skills/_lib/matter.py drop-ref <matter-id> [--path PATH]
    指定ディレクトリ（既定 CWD）に .claude-bengo-matter-ref を置く。
python3 skills/_lib/matter.py import-from-cwd [--matter-id ID]
    CWD の templates/ を新規事案に取り込む（v1.x 互換移行）。
python3 skills/_lib/matter.py validate <matter-id>
    ID が命名規則を満たすかを返す（exit 0=有効, 1=無効）。
```
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import secrets
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 事案ディレクトリのルート（環境変数で上書き可）
DEFAULT_ROOT = Path.home() / ".claude-bengo"
MATTERS_SUBDIR = "matters"
CURRENT_MATTER_FILE = "current-matter"
MATTER_REF_FILENAME = ".claude-bengo-matter-ref"
METADATA_FILENAME = "metadata.yaml"
TEMPLATES_SUBDIR = "templates"
AUDIT_FILENAME = "audit.jsonl"

# 事案 ID の命名規則: 小文字英数＋ハイフン/アンダースコア、64文字以内、先頭は英数字
MATTER_ID_RE = re.compile(r"^[a-z0-9][-a-z0-9_]{0,63}$")

# 予約 ID（システム用途のため事案 ID として使えない）
RESERVED_IDS = {
    "current-matter",
    "cache",
    "session_id",
    "audit",
    "sessions",
    "matters",  # 親ディレクトリ名との衝突防止
    "lock",
    "tmp",
}


# ---------------------------------------------------------------------------
# ルート・パス解決
# ---------------------------------------------------------------------------


def _chmod_owner_only(p: Path) -> None:
    """POSIX 上でディレクトリを 0o700 にする。Windows では無視する。

    親ディレクトリ（`~/.claude-bengo/` や `matters/`）は既定で 0o755 で
    作成されがちだが、事案 ID は依頼者名を示唆する場合があるため、
    同一マシンの他 OS ユーザー（や Spotlight 等のインデクサ）に enumerate
    させないよう所有者専用に落とす。
    """
    if not p.exists():
        return
    try:
        os.chmod(p, 0o700)
    except (OSError, NotImplementedError):
        pass


def _ensure_root_mode() -> None:
    """root_dir と matters_dir を 0o700 に強制する（冪等）。"""
    r = root_dir()
    if r.exists():
        _chmod_owner_only(r)
    m = matters_dir()
    if m.exists():
        _chmod_owner_only(m)


def root_dir() -> Path:
    """claude-bengo のルートディレクトリ。環境変数で上書き可。"""
    override = os.environ.get("CLAUDE_BENGO_ROOT")
    if override:
        return Path(override).expanduser()
    return DEFAULT_ROOT


def matters_dir() -> Path:
    """全事案を格納する親ディレクトリ。"""
    return root_dir() / MATTERS_SUBDIR


def matter_dir(matter_id: str) -> Path:
    """指定事案のルートディレクトリ。"""
    return matters_dir() / matter_id


def matter_templates_dir(matter_id: str) -> Path:
    """指定事案のテンプレートディレクトリ。"""
    return matter_dir(matter_id) / TEMPLATES_SUBDIR


def matter_audit_path(matter_id: str) -> Path:
    """指定事案の監査ログパス。"""
    return matter_dir(matter_id) / AUDIT_FILENAME


def current_matter_file() -> Path:
    """current-matter ファイル（/matter-switch で設定する既定値）。"""
    return root_dir() / CURRENT_MATTER_FILE


# ---------------------------------------------------------------------------
# バリデーション
# ---------------------------------------------------------------------------


def validate_matter_id(matter_id: str) -> Tuple[bool, str]:
    """事案 ID の命名規則を検証する。

    戻り値: (valid, reason)。valid=False のとき reason に理由。
    """
    if not matter_id:
        return False, "事案 ID が空である"
    if not MATTER_ID_RE.match(matter_id):
        return (
            False,
            f"事案 ID は ^[a-z0-9][-a-z0-9_]{{0,63}}$ を満たす必要がある。"
            f"受信: '{matter_id}'（英小文字・数字・ハイフン・アンダースコア、先頭は英数字、1〜64 文字）",
        )
    if matter_id in RESERVED_IDS:
        return False, f"事案 ID '{matter_id}' は予約語のため使えない"
    return True, ""


def generate_matter_id() -> str:
    """自動生成する事案 ID（例: 20260417-a7b3c2）。"""
    date = _dt.date.today().strftime("%Y%m%d")
    suffix = secrets.token_hex(3)  # 6 hex chars
    return f"{date}-{suffix}"


# ---------------------------------------------------------------------------
# 事案の存在チェック
# ---------------------------------------------------------------------------


def matter_exists(matter_id: str) -> bool:
    """指定事案のディレクトリが存在するか。"""
    d = matter_dir(matter_id)
    return d.exists() and d.is_dir()


def list_matter_ids() -> List[str]:
    """登録済み事案 ID の一覧（昇順）。"""
    d = matters_dir()
    if not d.exists():
        return []
    ids: List[str] = []
    for entry in d.iterdir():
        if entry.is_dir() and MATTER_ID_RE.match(entry.name):
            ids.append(entry.name)
    return sorted(ids)


# ---------------------------------------------------------------------------
# メタデータ
# ---------------------------------------------------------------------------


def _write_metadata(matter_id: str, meta: dict) -> None:
    """メタデータを YAML 風の簡易フォーマットで書き込む。

    依存を追加しないため YAML ライブラリは使わず、key: value の1行形式＋
    マルチライン値のインデントで扱う。値は常に UTF-8 文字列として読み書きする。
    """
    path = matter_dir(matter_id) / METADATA_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [
        "# claude-bengo matter metadata",
        f"# Generated: {_dt.datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
    ]
    for k, v in meta.items():
        if v is None or v == "":
            continue
        # 複数行値は "|" スカラー相当で保存
        if isinstance(v, str) and "\n" in v:
            lines.append(f"{k}: |")
            for ln in v.splitlines():
                lines.append(f"  {ln}")
        else:
            # 特殊文字（コロン・ハッシュ）を含む場合は二重引用で括る
            s = str(v)
            if any(ch in s for ch in (":", "#", "'", '"')) or s != s.strip():
                s_escaped = s.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{k}: "{s_escaped}"')
            else:
                lines.append(f"{k}: {s}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


def _read_metadata(matter_id: str) -> Dict[str, str]:
    """メタデータを読む（簡易パーサ）。存在しない場合は {}。"""
    path = matter_dir(matter_id) / METADATA_FILENAME
    if not path.exists():
        return {}
    meta: Dict[str, str] = {}
    current_key: Optional[str] = None
    current_lines: List[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            meta[current_key] = "\n".join(current_lines).rstrip()
        current_key = None
        current_lines = []

    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if current_key is not None and raw.startswith("  "):
                current_lines.append(raw[2:])
                continue
            flush()
            if not raw or raw.startswith("#"):
                continue
            if ":" in raw:
                k, _, v = raw.partition(":")
                k = k.strip()
                v = v.strip()
                if v == "|":
                    current_key = k
                    current_lines = []
                    continue
                # 引用符除去
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
                meta[k] = v
        flush()
    except OSError:
        return {}
    return meta


# ---------------------------------------------------------------------------
# 作成・切替
# ---------------------------------------------------------------------------


def create_matter(
    matter_id: str,
    title: str = "",
    client: str = "",
    case_number: str = "",
    opened: str = "",
    notes: str = "",
) -> Path:
    """事案ディレクトリとメタデータを作成する。

    既存 ID の場合は FileExistsError。
    """
    ok, reason = validate_matter_id(matter_id)
    if not ok:
        raise ValueError(reason)
    d = matter_dir(matter_id)
    if d.exists():
        raise FileExistsError(f"事案 '{matter_id}' は既に存在する: {d}")
    d.mkdir(parents=True, exist_ok=False)
    (d / TEMPLATES_SUBDIR).mkdir(parents=True, exist_ok=True)
    _chmod_owner_only(d)
    _chmod_owner_only(d / TEMPLATES_SUBDIR)
    _ensure_root_mode()  # 親の `~/.claude-bengo/` と `matters/` も 0o700 に揃える

    meta = {
        "id": matter_id,
        "title": title or matter_id,
        "client": client,
        "case_number": case_number,
        "opened": opened or _dt.date.today().isoformat(),
        "notes": notes,
    }
    _write_metadata(matter_id, meta)
    return d


def set_current_matter(matter_id: str) -> None:
    """current-matter ファイルを更新する。"""
    ok, reason = validate_matter_id(matter_id)
    if not ok:
        raise ValueError(reason)
    if not matter_exists(matter_id):
        raise FileNotFoundError(f"事案 '{matter_id}' は存在しない")
    f = current_matter_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(matter_id.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except (OSError, NotImplementedError):
        pass
    _ensure_root_mode()


def drop_matter_ref(matter_id: str, target_dir: Path) -> Path:
    """指定ディレクトリに .claude-bengo-matter-ref を書き込む。

    事案の実在性も検証する（`set_current_matter` と対称。不整合な ref を
    置いてしまう UX 事故を防ぐ）。
    """
    ok, reason = validate_matter_id(matter_id)
    if not ok:
        raise ValueError(reason)
    if not matter_exists(matter_id):
        raise FileNotFoundError(
            f"事案 '{matter_id}' は存在しない。`/matter-create {matter_id}` で先に作成してほしい。"
        )
    target_dir.mkdir(parents=True, exist_ok=True)
    ref_path = target_dir / MATTER_REF_FILENAME
    ref_path.write_text(matter_id.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(ref_path, 0o600)
    except (OSError, NotImplementedError):
        pass
    return ref_path


# ---------------------------------------------------------------------------
# 解決
# ---------------------------------------------------------------------------


def _read_matter_ref(path: Path) -> Optional[str]:
    """1 行目の事案 ID を読む。空・無効・シンボリックリンクなら None。

    セキュリティ上、シンボリックリンクは拒否する。共有 Dropbox 等に置かれた
    悪意ある ref から任意のファイルへ間接読取されるのを防ぐため。
    """
    try:
        if not path.exists():
            return None
        # シンボリックリンクは明示的に拒否（copy_file.py と対称）
        if path.is_symlink():
            print(
                f"WARN: matter-ref はシンボリックリンクのため無視する: {path}",
                file=sys.stderr,
            )
            return None
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        first_line = text.splitlines()[0].strip()
        ok, _ = validate_matter_id(first_line)
        return first_line if ok else None
    except OSError:
        return None


def resolve(
    cli_flag: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Dict[str, Optional[str]]:
    """4 段階で事案 ID を解決し、ID・解決元・メッセージを返す。

    戻り値フィールド:
      - matter_id: 解決された事案 ID（なければ None）
      - source:    flag / env / cwd-ref / current / none のいずれか
      - path:      解決元の絶対パス（該当する場合）
      - exists:    事案ディレクトリが実在するか
      - message:   ユーザー向け補足メッセージ（任意）
    """
    cwd = Path(cwd) if cwd else Path.cwd()

    # 1. 明示フラグ
    if cli_flag:
        ok, reason = validate_matter_id(cli_flag)
        if not ok:
            return {
                "matter_id": None,
                "source": "flag",
                "path": None,
                "exists": False,
                "message": f"--matter の値が無効: {reason}",
            }
        return {
            "matter_id": cli_flag,
            "source": "flag",
            "path": None,
            "exists": matter_exists(cli_flag),
            "message": "",
        }

    # 2. 環境変数
    env_id = os.environ.get("MATTER_ID", "").strip()
    if env_id:
        ok, reason = validate_matter_id(env_id)
        if ok:
            # cwd-ref が存在するのに env が override している場合、footgun として警告する。
            # シェル設定（.zshrc 等）で MATTER_ID を固定したまま、事案別の作業
            # ディレクトリに `cd` すると意図しない事案へ書込する事故が起きる。
            # 抑止は `CLAUDE_BENGO_SILENT_MATTER_OVERRIDE=1`。
            ref_path_check = cwd / MATTER_REF_FILENAME
            ref_id_check = _read_matter_ref(ref_path_check) if ref_path_check.exists() else None
            if (
                ref_id_check
                and ref_id_check != env_id
                and os.environ.get("CLAUDE_BENGO_SILENT_MATTER_OVERRIDE") != "1"
            ):
                print(
                    f"WARN: MATTER_ID 環境変数 ('{env_id}') が CWD の .claude-bengo-matter-ref "
                    f"('{ref_id_check}') を上書きしている。意図と異なる事案が選択される可能性がある。"
                    "抑止は CLAUDE_BENGO_SILENT_MATTER_OVERRIDE=1。",
                    file=sys.stderr,
                )
            return {
                "matter_id": env_id,
                "source": "env",
                "path": None,
                "exists": matter_exists(env_id),
                "message": "",
            }
        return {
            "matter_id": None,
            "source": "env",
            "path": None,
            "exists": False,
            "message": f"MATTER_ID 環境変数の値が無効: {reason}",
        }

    # 3. 作業ディレクトリの .matter-ref
    ref_path = cwd / MATTER_REF_FILENAME
    ref_id = _read_matter_ref(ref_path)
    if ref_id:
        return {
            "matter_id": ref_id,
            "source": "cwd-ref",
            "path": str(ref_path),
            "exists": matter_exists(ref_id),
            "message": "",
        }

    # 4. current-matter ファイル
    cur_id = _read_matter_ref(current_matter_file())
    if cur_id:
        return {
            "matter_id": cur_id,
            "source": "current",
            "path": str(current_matter_file()),
            "exists": matter_exists(cur_id),
            "message": "",
        }

    # 5. どれもない
    return {
        "matter_id": None,
        "source": "none",
        "path": None,
        "exists": False,
        "message": (
            "アクティブな matter が設定されていない。以下のいずれかを実行してほしい:\n"
            "  /matter-list        — 既存 matter を確認\n"
            "  /matter-switch <id> — 既存 matter に切替\n"
            "  /matter-create      — 新規 matter を作成\n"
            "  または --matter <id> フラグで明示指定"
        ),
    }


# ---------------------------------------------------------------------------
# 移行（v1.x から v2.0 へ）
# ---------------------------------------------------------------------------


# 移行で取り込む許容拡張子（テンプレートペアは .yaml + .xlsx のみ）
IMPORT_ALLOWED_EXT = {".yaml", ".xlsx"}


def import_from_cwd(
    cwd: Path,
    matter_id: Optional[str] = None,
    title: str = "",
    client: str = "",
) -> Tuple[str, List[Path], List[Path]]:
    """CWD の templates/ を新規事案として取り込む。

    戻り値: (matter_id, copied_files, skipped_files)

    取り込み対象は `.yaml` + `.xlsx` のみ。`.DS_Store` や `~$` Excel ロック、
    無関係な PDF などは skipped_files として返す。シンボリックリンクも
    skip 対象（`copy_file.py` と対称のセキュリティ方針）。
    """
    src_dir = cwd / "templates"
    if not src_dir.exists() or not src_dir.is_dir():
        raise FileNotFoundError(f"{cwd}/templates が存在しない")

    if matter_id is None:
        matter_id = generate_matter_id()
    ok, reason = validate_matter_id(matter_id)
    if not ok:
        raise ValueError(reason)
    if matter_exists(matter_id):
        raise FileExistsError(f"事案 '{matter_id}' は既に存在する")

    # 事案作成
    create_matter(
        matter_id,
        title=title or f"imported-from-{cwd.name}",
        client=client,
        notes=f"imported from {cwd}/templates on {_dt.date.today().isoformat()}",
    )

    # テンプレートを事案ディレクトリにコピー（元は残す）
    dst_dir = matter_templates_dir(matter_id)
    copied: List[Path] = []
    skipped: List[Path] = []
    for entry in sorted(src_dir.iterdir()):
        if not entry.is_file():
            skipped.append(entry)
            continue
        if entry.is_symlink():
            skipped.append(entry)
            continue
        # `_schema.yaml` は仕様書であり取り込まない
        if entry.name == "_schema.yaml":
            skipped.append(entry)
            continue
        if entry.suffix.lower() not in IMPORT_ALLOWED_EXT:
            skipped.append(entry)
            continue
        dst = dst_dir / entry.name
        shutil.copy2(entry, dst, follow_symlinks=False)
        copied.append(dst)
    return matter_id, copied, skipped


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_resolve(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).expanduser() if args.cwd else Path.cwd()
    result = resolve(cli_flag=args.matter, cwd=cwd)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("matter_id") else 1


def _cmd_list(args: argparse.Namespace) -> int:
    ids = list_matter_ids()
    out = []
    for mid in ids:
        meta = _read_metadata(mid)
        d = matter_dir(mid)
        try:
            template_count = sum(1 for p in (d / TEMPLATES_SUBDIR).glob("*.yaml"))
        except OSError:
            template_count = 0
        audit = d / AUDIT_FILENAME
        audit_bytes = audit.stat().st_size if audit.exists() else 0
        out.append(
            {
                "id": mid,
                "title": meta.get("title", mid),
                "client": meta.get("client", ""),
                "case_number": meta.get("case_number", ""),
                "opened": meta.get("opened", ""),
                "path": str(d),
                "templates": template_count,
                "audit_bytes": audit_bytes,
            }
        )
    if args.format == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not out:
            print("登録済み事案はない。/matter-create で作成してほしい。")
            return 0
        for m in out:
            print(f"  {m['id']}")
            print(f"    title:       {m['title']}")
            if m["client"]:
                print(f"    client:      {m['client']}")
            if m["case_number"]:
                print(f"    case_number: {m['case_number']}")
            if m["opened"]:
                print(f"    opened:      {m['opened']}")
            print(f"    templates:   {m['templates']} 件")
            print(f"    path:        {m['path']}")
            print()
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    mid = args.matter_id
    ok, reason = validate_matter_id(mid)
    if not ok:
        print(json.dumps({"error": reason}, ensure_ascii=False), file=sys.stderr)
        return 1
    if not matter_exists(mid):
        print(json.dumps({"error": f"事案 '{mid}' は存在しない"}, ensure_ascii=False), file=sys.stderr)
        return 2
    meta = _read_metadata(mid)
    d = matter_dir(mid)
    audit = d / AUDIT_FILENAME
    info = {
        "id": mid,
        "path": str(d),
        "templates_dir": str(d / TEMPLATES_SUBDIR),
        "audit_path": str(audit),
        "audit_bytes": audit.stat().st_size if audit.exists() else 0,
        "metadata": meta,
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def _cmd_create(args: argparse.Namespace) -> int:
    mid = args.matter_id or generate_matter_id()
    ok, reason = validate_matter_id(mid)
    if not ok:
        print(json.dumps({"error": reason}, ensure_ascii=False), file=sys.stderr)
        return 1
    try:
        d = create_matter(
            matter_id=mid,
            title=args.title,
            client=args.client,
            case_number=args.case_number,
            opened=args.opened,
            notes=args.notes,
        )
    except FileExistsError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"matter_id": mid, "path": str(d), "created": True}, ensure_ascii=False, indent=2
        )
    )
    return 0


def _cmd_switch(args: argparse.Namespace) -> int:
    mid = args.matter_id
    ok, reason = validate_matter_id(mid)
    if not ok:
        print(json.dumps({"error": reason}, ensure_ascii=False), file=sys.stderr)
        return 1
    try:
        set_current_matter(mid)
    except (ValueError, FileNotFoundError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"matter_id": mid, "current_matter_file": str(current_matter_file())},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_drop_ref(args: argparse.Namespace) -> int:
    mid = args.matter_id
    target = Path(args.path).expanduser() if args.path else Path.cwd()
    try:
        ref = drop_matter_ref(mid, target)
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"matter_id": mid, "ref_path": str(ref)}, ensure_ascii=False, indent=2))
    return 0


def _cmd_import_from_cwd(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).expanduser() if args.cwd else Path.cwd()
    try:
        mid, copied, skipped = import_from_cwd(
            cwd=cwd,
            matter_id=args.matter_id,
            title=args.title,
            client=args.client,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "matter_id": mid,
                "path": str(matter_dir(mid)),
                "imported_files": [str(p) for p in copied],
                "skipped_files": [str(p) for p in skipped],
                "count": len(copied),
                "skipped_count": len(skipped),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    ok, reason = validate_matter_id(args.matter_id)
    if ok:
        print(json.dumps({"valid": True, "matter_id": args.matter_id}, ensure_ascii=False))
        return 0
    print(
        json.dumps({"valid": False, "matter_id": args.matter_id, "reason": reason}, ensure_ascii=False),
        file=sys.stderr,
    )
    return 1


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="claude-bengo 事案（matter）管理")
    ap.add_argument("--self-test", action="store_true", help="組込セルフテストを実行する")
    sub = ap.add_subparsers(dest="command")

    p_res = sub.add_parser("resolve", help="現在の事案 ID を解決する")
    p_res.add_argument("--matter", help="明示指定する事案 ID（最優先）")
    p_res.add_argument("--cwd", help="作業ディレクトリを指定（既定は現在のCWD）")

    p_list = sub.add_parser("list", help="登録済み事案を一覧表示する")
    p_list.add_argument("--format", choices=["text", "json"], default="text")

    p_info = sub.add_parser("info", help="指定事案の詳細を表示する")
    p_info.add_argument("matter_id")

    p_create = sub.add_parser("create", help="事案を作成する")
    p_create.add_argument("matter_id", nargs="?", help="事案 ID（省略時は自動生成）")
    p_create.add_argument("--title", default="")
    p_create.add_argument("--client", default="")
    p_create.add_argument("--case-number", default="")
    p_create.add_argument("--opened", default="")
    p_create.add_argument("--notes", default="")

    p_switch = sub.add_parser("switch", help="current-matter を更新する")
    p_switch.add_argument("matter_id")

    p_drop = sub.add_parser("drop-ref", help="CWD に .claude-bengo-matter-ref を置く")
    p_drop.add_argument("matter_id")
    p_drop.add_argument("--path", help="配置先ディレクトリ（既定は CWD）")

    p_imp = sub.add_parser("import-from-cwd", help="v1.x の {cwd}/templates を事案に取り込む")
    p_imp.add_argument("--matter-id", help="事案 ID（省略時は自動生成）")
    p_imp.add_argument("--title", default="")
    p_imp.add_argument("--client", default="")
    p_imp.add_argument("--cwd", help="取込元（既定は CWD）")

    p_val = sub.add_parser("validate", help="事案 ID が命名規則を満たすかを返す")
    p_val.add_argument("matter_id")

    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    if args.command is None:
        ap.print_help()
        return 1

    handlers = {
        "resolve": _cmd_resolve,
        "list": _cmd_list,
        "info": _cmd_info,
        "create": _cmd_create,
        "switch": _cmd_switch,
        "drop-ref": _cmd_drop_ref,
        "import-from-cwd": _cmd_import_from_cwd,
        "validate": _cmd_validate,
    }
    return handlers[args.command](args)


# ---------------------------------------------------------------------------
# セルフテスト
# ---------------------------------------------------------------------------


def _self_test() -> int:
    """組込セルフテスト。

    1. validate_matter_id: 有効／無効パターン
    2. generate_matter_id: 命名規則を満たす
    3. create_matter + matter_exists + list_matter_ids
    4. resolve: 4段階の優先順位
    5. drop_matter_ref + cwd-ref の解決
    6. set_current_matter + current の解決
    7. import_from_cwd: v1.x 移行
    """
    import tempfile

    results: List[Tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, cond, detail))
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")

    # 1. validate
    ok1, _ = validate_matter_id("smith-v-jones")
    ok2, _ = validate_matter_id("20260417-a7b3c2")
    ok3, _ = validate_matter_id("a")
    bad1, _ = validate_matter_id("")
    bad2, _ = validate_matter_id("Smith-V-Jones")  # uppercase
    bad3, _ = validate_matter_id("smith v jones")  # spaces
    bad4, _ = validate_matter_id("../etc")  # path traversal
    bad5, _ = validate_matter_id("current-matter")  # reserved
    check(
        "1. validate_matter_id",
        ok1 and ok2 and ok3 and not bad1 and not bad2 and not bad3 and not bad4 and not bad5,
        f"valid: {ok1,ok2,ok3}, rejected: {not bad1,not bad2,not bad3,not bad4,not bad5}",
    )

    # 2. generate
    gen = generate_matter_id()
    gen_ok, _ = validate_matter_id(gen)
    check("2. generate_matter_id", gen_ok, f"generated={gen}")

    # サンドボックス環境
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = Path(tmpdir) / "claude-bengo"
        os.environ["CLAUDE_BENGO_ROOT"] = str(sandbox)
        # env / current-matter を一旦クリア
        os.environ.pop("MATTER_ID", None)

        try:
            # 3. create_matter + list
            created_dir = create_matter(
                "test-alpha", title="テスト事案", client="甲野太郎"
            )
            ids = list_matter_ids()
            check(
                "3. create_matter + matter_exists + list_matter_ids",
                matter_exists("test-alpha")
                and created_dir.exists()
                and "test-alpha" in ids,
                f"ids={ids}",
            )

            # 重複作成は FileExistsError
            dup_ok = False
            try:
                create_matter("test-alpha")
            except FileExistsError:
                dup_ok = True
            check("3b. duplicate create rejected", dup_ok)

            # 4a. resolve with --matter flag
            r = resolve(cli_flag="test-alpha", cwd=Path(tmpdir))
            check(
                "4a. resolve via --matter flag",
                r["matter_id"] == "test-alpha" and r["source"] == "flag",
                f"source={r['source']}",
            )

            # 4b. resolve via MATTER_ID env
            os.environ["MATTER_ID"] = "test-alpha"
            r = resolve(cli_flag=None, cwd=Path(tmpdir))
            check(
                "4b. resolve via env MATTER_ID",
                r["matter_id"] == "test-alpha" and r["source"] == "env",
                f"source={r['source']}",
            )
            os.environ.pop("MATTER_ID", None)

            # 4c. resolve via cwd-ref
            work = Path(tmpdir) / "case-folder"
            work.mkdir()
            drop_matter_ref("test-alpha", work)
            r = resolve(cli_flag=None, cwd=work)
            check(
                "4c. resolve via cwd-ref",
                r["matter_id"] == "test-alpha" and r["source"] == "cwd-ref",
                f"source={r['source']}",
            )

            # 4d. resolve via current-matter
            set_current_matter("test-alpha")
            r = resolve(cli_flag=None, cwd=Path(tmpdir))
            check(
                "4d. resolve via current-matter",
                r["matter_id"] == "test-alpha" and r["source"] == "current",
                f"source={r['source']}",
            )

            # 4e. priority: flag > env > cwd-ref > current
            os.environ["MATTER_ID"] = "bogus-env"
            # flag beats env
            r = resolve(cli_flag="test-alpha", cwd=work)
            check(
                "4e. flag beats env/cwd-ref/current",
                r["matter_id"] == "test-alpha" and r["source"] == "flag",
            )
            # env beats cwd-ref/current (env is invalid matter so falls through)
            create_matter("test-beta", title="beta")
            os.environ["MATTER_ID"] = "test-beta"
            r = resolve(cli_flag=None, cwd=work)
            check(
                "4f. env beats cwd-ref",
                r["matter_id"] == "test-beta" and r["source"] == "env",
                f"source={r['source']}",
            )
            os.environ.pop("MATTER_ID", None)
            # cwd-ref beats current
            r = resolve(cli_flag=None, cwd=work)
            check(
                "4g. cwd-ref beats current",
                r["matter_id"] == "test-alpha" and r["source"] == "cwd-ref",
                f"source={r['source']}",
            )

            # 5. import_from_cwd
            legacy = Path(tmpdir) / "legacy-project"
            (legacy / "templates").mkdir(parents=True)
            (legacy / "templates" / "sample.yaml").write_text("id: sample\n", encoding="utf-8")
            (legacy / "templates" / "sample.xlsx").write_bytes(b"fake xlsx")
            # v1.x 移行テスト: .yaml/.xlsx ペアは取込、.DS_Store / PDF / _schema.yaml は skip
            (legacy / "templates" / ".DS_Store").write_bytes(b"\x00")
            (legacy / "templates" / "random.pdf").write_bytes(b"pdf junk")
            (legacy / "templates" / "_schema.yaml").write_text("schema", encoding="utf-8")
            mid, copied, skipped = import_from_cwd(legacy, matter_id="legacy-import")
            check(
                "5. import_from_cwd filters to .yaml/.xlsx only",
                mid == "legacy-import"
                and len(copied) == 2
                and len(skipped) == 3
                and matter_exists("legacy-import"),
                f"imported={len(copied)}, skipped={len(skipped)}",
            )

            # 6. no matter set → source=none
            # Fresh sandbox state check: clear env + current-matter
            os.environ.pop("MATTER_ID", None)
            current_matter_file().unlink(missing_ok=True)
            empty_dir = Path(tmpdir) / "nowhere"
            empty_dir.mkdir()
            r = resolve(cli_flag=None, cwd=empty_dir)
            check(
                "6. no matter set → source=none",
                r["matter_id"] is None and r["source"] == "none",
                f"source={r['source']}",
            )

            # 7. metadata round-trip
            meta = _read_metadata("test-alpha")
            check(
                "7. metadata round-trip",
                meta.get("title") == "テスト事案" and meta.get("client") == "甲野太郎",
                f"meta={meta}",
            )

            # 8. v2.0.1 新ハードニング: root と matters が 0o700 になっている（POSIX）
            if os.name == "posix":
                r_mode = sandbox.stat().st_mode & 0o777
                m_mode = (sandbox / MATTERS_SUBDIR).stat().st_mode & 0o777
                check(
                    "8. root/matters_dir perms are 0o700",
                    r_mode == 0o700 and m_mode == 0o700,
                    f"root={oct(r_mode)}, matters={oct(m_mode)}",
                )
            else:
                check("8. root/matters_dir perms (skipped on non-POSIX)", True)

            # 9. drop_matter_ref は存在しない matter を拒否
            drop_rejected = False
            try:
                drop_matter_ref("ghost-matter", Path(tmpdir) / "nowhere-to-drop")
            except FileNotFoundError:
                drop_rejected = True
            check("9. drop_matter_ref rejects nonexistent matter", drop_rejected)

            # 10. "matters" 予約語は拒否される
            reserved_ok = False
            try:
                create_matter("matters")
            except ValueError:
                reserved_ok = True
            check("10. RESERVED_IDS includes 'matters'", reserved_ok)

            # 11. .claude-bengo-matter-ref がシンボリックリンクの場合、resolver は無視
            if os.name == "posix":
                symlink_dir = Path(tmpdir) / "symlink-case"
                symlink_dir.mkdir()
                real_ref = Path(tmpdir) / "elsewhere-ref.txt"
                real_ref.write_text("test-alpha\n", encoding="utf-8")
                (symlink_dir / MATTER_REF_FILENAME).symlink_to(real_ref)
                r = resolve(cli_flag=None, cwd=symlink_dir)
                check(
                    "11. symlinked matter-ref is rejected",
                    r["source"] != "cwd-ref",
                    f"source={r['source']}",
                )
            else:
                check("11. symlinked matter-ref rejection (skipped)", True)

        finally:
            os.environ.pop("CLAUDE_BENGO_ROOT", None)
            os.environ.pop("MATTER_ID", None)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print()
    print(f"self-test: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
