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
from typing import Dict, List, Optional, Tuple

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
    scope: str = "case",
) -> Dict[str, str]:
    """同梱テンプレートを指定スコープのテンプレートディレクトリへコピーする。

    v3.3.0 でデフォルトを `case` に戻した（以前は `global`）。tier-2/3 firm の
    senior lawyer が無意識に firm-wide へ配置してしまい、他案件の global/
    shadowing が混線するリスクがあるため。firm 全体で使い回したい場合は
    `scope="global"` を明示、あるいは登録後に `/template-promote` を使う。

    - `scope="global"` → `~/.claude-bengo/templates/{id}.{yaml,xlsx}`
      firm-wide 書式（同梱テンプレートは本来これ）。workspace 初期化不要。
    - `scope="case"` → `<workspace>/.claude-bengo/templates/{id}.{yaml,xlsx}`
      現在の案件フォルダに限定。workspace が未初期化なら silently 初期化する。

    戻り値: {yaml_dst, xlsx_dst, scope, bundled_id, replaced, integrity_verified,
             workspace_root (scope=case のみ)}
    """
    if scope not in ("global", "case"):
        raise ValueError(f"scope は 'global' または 'case' のどちらか。指定値: {scope!r}")

    ws = _load_workspace()

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

    if scope == "global":
        dst_dir = ws.ensure_global_templates_dir()
        workspace_root: Optional[str] = None
    else:
        ws.ensure_workspace()
        dst_dir = ws.templates_dir()
        dst_dir.mkdir(parents=True, exist_ok=True)
        workspace_root = str(ws.resolve_workspace())

    dst_yaml = dst_dir / f"{bundled_id}.yaml"
    dst_xlsx = dst_dir / f"{bundled_id}.xlsx"

    if (dst_yaml.exists() or dst_xlsx.exists()) and not replace:
        scope_label = "事務所グローバル" if scope == "global" else "この案件フォルダ"
        raise FileExistsError(
            f"{scope_label}に既に '{bundled_id}' が存在する。上書きには --replace を指定してほしい。"
        )

    shutil.copy2(src_yaml, dst_yaml, follow_symlinks=False)
    shutil.copy2(src_xlsx, dst_xlsx, follow_symlinks=False)

    result: Dict[str, str] = {
        "bundled_id": bundled_id,
        "scope": scope,
        "yaml_dst": str(dst_yaml),
        "xlsx_dst": str(dst_xlsx),
        "replaced": str(replace),
        "integrity_verified": str(integrity_verified),
    }
    if workspace_root is not None:
        result["workspace_root"] = workspace_root
    return result


# ---------------------------------------------------------------------------
# PII code-gate（v3.3.0-iter1〜）
# ---------------------------------------------------------------------------


class PIIFoundError(ValueError):
    """global スコープへの書込時に PII が検出された場合に投げる。

    発生時は **ユーザー側での overridable ではない**。findings 属性に
    検出されたレコード一覧を持つ。開発バックドア:
    - admin lock 未設定（CI 等）: 環境変数 `CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL=1`
      で続行
    - admin lock 設定済み: 環境変数 `CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL=<admin passphrase>`
      （PBKDF2 照合）で続行。`=1` は無効化される
    いずれもユーザー向けフラグではない。
    """
    def __init__(self, findings: List[Dict], xlsx_path: Path):
        self.findings = findings
        self.xlsx_path = xlsx_path
        preview = ", ".join(
            f"{f.get('cell','?')}[{f.get('category','?')}]"
            for f in findings[:5]
        )
        more = f" 他 {len(findings) - 5} 件" if len(findings) > 5 else ""
        super().__init__(
            f"{xlsx_path.name} に PII らしき記述が {len(findings)} 件検出された ({preview}{more})。"
            " global スコープへの保存を拒否する。case スコープで登録するか、XLSX 側で PII を削除してから再実行してほしい。"
        )


def _check_pii_for_global(xlsx_path: Path) -> None:
    """XLSX が global スコープに保存されても安全か検証する。

    PII 検出時は `PIIFoundError` を投げる（ユーザーの override 不可）。

    開発者バックドア（v3.3.0-iter2〜 強化）:
    `CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL` 環境変数に **現行の admin passphrase** を
    設定すると findings を無視して続行する。以前は `=1` で通ったが、これは
    誰でも flip できる穴だった。現在は admin lock と同じパスフレーズが必要で、
    事務所管理者でない開発者は使えない。

    admin lock が未設定の環境では `=1` の従来挙動（テスト/CI 用）を許容する。
    """
    here = Path(__file__).resolve().parent
    sys_path_added = False
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
        sys_path_added = True
    try:
        import importlib
        pii_scan = importlib.import_module("pii_scan")
    except ImportError:
        raise PIIFoundError(
            [{"cell": "N/A", "category": "scanner_unavailable"}], xlsx_path,
        )
    finally:
        if sys_path_added:
            try:
                sys.path.remove(str(here))
            except ValueError:
                pass

    result = pii_scan.scan_xlsx(xlsx_path)
    if result.get("verdict") == "clean":
        return

    backdoor = os.environ.get("CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL")
    if backdoor:
        # admin lock があるならパスフレーズ一致が必須。無ければ `=1` で従来互換。
        ws = _load_workspace()
        cfg = ws.load_global_config()
        admin_lock = cfg.get("admin_lock")
        if isinstance(admin_lock, dict) and "hash_hex" in admin_lock:
            # admin lock あり → passphrase match 必須
            here2 = Path(__file__).resolve().parent
            added2 = False
            if str(here2) not in sys.path:
                sys.path.insert(0, str(here2))
                added2 = True
            try:
                import importlib
                consent = importlib.import_module("consent")
            finally:
                if added2:
                    try:
                        sys.path.remove(str(here2))
                    except ValueError:
                        pass
            if not consent._verify_passphrase(backdoor, admin_lock):
                # パスフレーズ不一致 → バックドア無効
                raise PIIFoundError(result.get("findings", []), xlsx_path)
            # admin-verified bypass: 最小限の警告のみ（findings 件数は stderr に
            # 流さない — 偶発的なログ流出で PII 件数という side-channel を
            # 第三者に漏らさないため）
            print(
                "警告: admin passphrase により PII スキャンが bypass された。global 保存を続行する。",
                file=sys.stderr,
            )
            return
        # admin lock 未設定（開発/CI 環境）→ `=1` でも通す
        if backdoor == "1":
            print(
                f"警告: admin lock 未設定かつ CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL=1。"
                f"{len(result.get('findings', []))} 件の PII 検出を無視。",
                file=sys.stderr,
            )
            return
    raise PIIFoundError(result.get("findings", []), xlsx_path)


def save_user_template(
    source_xlsx: Path,
    template_id: str,
    *,
    scope: str = "case",
    yaml_content: Optional[str] = None,
    replace: bool = False,
) -> Dict[str, str]:
    """ユーザー作成テンプレートを保存する（code-level PII guard 付き）。

    `/template-create` の Write + copy_file.py の代替。SKILL は本関数を叩くことで
    global スコープ時の PII チェックを **必ず** 通過する。

    Args:
      source_xlsx: 元 XLSX のパス
      template_id: 登録 ID（ファイル名、BUNDLED_ID_RE で検証済みの英数字）
      scope: "case" または "global"
      yaml_content: 書き込む YAML 定義（None なら既存 YAML を期待）
      replace: 既存を上書きするか

    Raises:
      PIIFoundError: scope="global" かつ XLSX に PII 検出
      ValueError: ID 不正
      FileExistsError: replace=False で既存衝突
    """
    if not BUNDLED_ID_RE.match(template_id):
        raise ValueError(f"無効なテンプレート ID: {template_id!r}")
    if scope not in ("case", "global"):
        raise ValueError(f"scope は 'case' または 'global'。指定値: {scope!r}")

    source = Path(source_xlsx).expanduser()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"source xlsx が存在しない: {source}")

    # ** CRITICAL: global 保存前に PII スキャン（code-enforced） **
    if scope == "global":
        _check_pii_for_global(source)

    ws = _load_workspace()
    if scope == "global":
        dst_dir = ws.ensure_global_templates_dir()
    else:
        ws.ensure_workspace()
        dst_dir = ws.templates_dir()
        dst_dir.mkdir(parents=True, exist_ok=True)

    dst_yaml = dst_dir / f"{template_id}.yaml"
    dst_xlsx = dst_dir / f"{template_id}.xlsx"

    if (dst_yaml.exists() or dst_xlsx.exists()) and not replace:
        raise FileExistsError(
            f"{dst_dir} に既に '{template_id}' が存在する。上書きには replace=True を指定してほしい。"
        )

    if yaml_content is not None:
        dst_yaml.write_text(yaml_content, encoding="utf-8")
    elif not dst_yaml.exists():
        raise FileNotFoundError(
            f"yaml_content 未指定で、既存 YAML ({dst_yaml}) もない。YAML 内容を渡してほしい。"
        )
    shutil.copy2(source, dst_xlsx, follow_symlinks=False)

    return {
        "id": template_id,
        "scope": scope,
        "yaml_path": str(dst_yaml),
        "xlsx_path": str(dst_xlsx),
        "pii_scanned": "True" if scope == "global" else "False",
    }


# ---------------------------------------------------------------------------
# 昇格／降格（case ↔ global）
# ---------------------------------------------------------------------------


def _move_template(
    template_id: str,
    *,
    src_scope: str,
    dst_scope: str,
    replace: bool,
    keep_original: bool,
) -> Dict[str, str]:
    """`{id}.yaml` + `{id}.xlsx` を src_scope → dst_scope に移す共通ロジック。

    - `promote`: case → global, keep_original=False（moveに相当。案件側の shadowing を解消）
    - `demote`:  global → case, keep_original=True（copy に相当。他案件の global は維持）
    - `scope` へのコピー後、src_scope のファイルを削除するかは keep_original で制御

    戻り値: {id, src_scope, dst_scope, src_yaml, src_xlsx, dst_yaml, dst_xlsx,
             replaced, kept_original}
    """
    if src_scope == dst_scope:
        raise ValueError(f"src と dst のスコープが同じ: {src_scope}")
    if src_scope not in ("case", "global") or dst_scope not in ("case", "global"):
        raise ValueError(f"無効なスコープ: src={src_scope} dst={dst_scope}")
    if not BUNDLED_ID_RE.match(template_id):
        raise ValueError(f"無効なテンプレート ID: {template_id!r}")

    ws = _load_workspace()

    def _scope_paths(scope: str) -> Tuple[Path, Path, Path]:
        if scope == "global":
            d = ws.ensure_global_templates_dir()
        else:
            ws.ensure_workspace()
            d = ws.templates_dir()
            d.mkdir(parents=True, exist_ok=True)
        return d, d / f"{template_id}.yaml", d / f"{template_id}.xlsx"

    _, src_yaml, src_xlsx = _scope_paths(src_scope)
    if not src_yaml.exists() or not src_xlsx.exists():
        scope_label = "事務所グローバル" if src_scope == "global" else "この案件フォルダ"
        raise FileNotFoundError(
            f"{scope_label}にテンプレート '{template_id}' が見つからない "
            f"(yaml={src_yaml.exists()}, xlsx={src_xlsx.exists()})"
        )

    _, dst_yaml, dst_xlsx = _scope_paths(dst_scope)
    dst_yaml_existed = dst_yaml.exists()
    dst_xlsx_existed = dst_xlsx.exists()
    if (dst_yaml_existed or dst_xlsx_existed) and not replace:
        dst_label = "事務所グローバル" if dst_scope == "global" else "この案件フォルダ"
        raise FileExistsError(
            f"{dst_label}に既に '{template_id}' が存在する。上書きには --replace を指定してほしい。"
        )

    # --- 原子的コピー（stage-then-rename）---
    # .tmp にコピー → 両方揃ったら元に rename で上書き（rename は POSIX で原子的）。
    # 途中で失敗したら dst を元状態に戻す。これにより:
    #   - コピー途中でクラッシュしても dst が半端な状態で残らない
    #   - --replace 時の「yaml は新、xlsx は旧」の不整合が起きない
    stage_yaml = dst_yaml.with_suffix(dst_yaml.suffix + ".staging")
    stage_xlsx = dst_xlsx.with_suffix(dst_xlsx.suffix + ".staging")
    # 既存の staging 残骸があれば掃除
    for p in (stage_yaml, stage_xlsx):
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    try:
        shutil.copy2(src_yaml, stage_yaml, follow_symlinks=False)
        shutil.copy2(src_xlsx, stage_xlsx, follow_symlinks=False)
    except Exception:
        for p in (stage_yaml, stage_xlsx):
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        raise

    # --replace 時に dst の現状を別 backup に退避（ロールバック用）
    backup_yaml = dst_yaml.with_suffix(dst_yaml.suffix + ".backup") if dst_yaml_existed else None
    backup_xlsx = dst_xlsx.with_suffix(dst_xlsx.suffix + ".backup") if dst_xlsx_existed else None
    try:
        if backup_yaml:
            dst_yaml.replace(backup_yaml)
        if backup_xlsx:
            dst_xlsx.replace(backup_xlsx)
        stage_yaml.replace(dst_yaml)
        stage_xlsx.replace(dst_xlsx)
    except Exception:
        # ロールバック: backup があれば戻す / staging を消す
        for src, dst in ((backup_yaml, dst_yaml), (backup_xlsx, dst_xlsx)):
            if src and src.exists():
                try:
                    src.replace(dst)
                except OSError:
                    pass
        for p in (stage_yaml, stage_xlsx):
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
        raise
    else:
        for p in (backup_yaml, backup_xlsx):
            if p and p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    delete_failed = False
    delete_error: Optional[str] = None
    if not keep_original:
        # 原本削除も best-effort だが、失敗時は result に delete_failed=True を載せて
        # caller が stale な case 側を検知できるようにする。サイレントに成功扱いしない。
        for p in (src_yaml, src_xlsx):
            try:
                p.unlink()
            except OSError as e:
                delete_failed = True
                delete_error = str(e)
                print(
                    f"警告: 元ファイル削除に失敗: {p} — {e}。"
                    f"コピーは成功したが case 側に残骸があるため、"
                    f"手動で削除するか /template-promote の再実行が必要。",
                    file=sys.stderr,
                )

    result: Dict[str, str] = {
        "id": template_id,
        "src_scope": src_scope,
        "dst_scope": dst_scope,
        "src_yaml": str(src_yaml),
        "src_xlsx": str(src_xlsx),
        "dst_yaml": str(dst_yaml),
        "dst_xlsx": str(dst_xlsx),
        "replaced": str(replace),
        "kept_original": str(keep_original),
        "delete_failed": str(delete_failed),
    }
    if delete_error:
        result["delete_error"] = delete_error
    return result


def promote_template(template_id: str, replace: bool = False) -> Dict[str, str]:
    """案件スコープ → 事務所グローバルに **移動**（案件側から削除）。

    典型的なユースケース: 最初は案件専用で登録した書式が他案件でも使えると
    気づいたとき、グローバルに昇格して案件側の shadowing を解消する。

    **v3.3.0-iter1〜: 移動前に pii_scan を通す（code-enforced hard block）。**
    PII 検出時は `PIIFoundError` を投げてファイル移動を行わない。
    """
    if not BUNDLED_ID_RE.match(template_id):
        raise ValueError(f"無効なテンプレート ID: {template_id!r}")

    ws = _load_workspace()
    case_dir = ws.templates_dir()
    src_xlsx = case_dir / f"{template_id}.xlsx"
    if src_xlsx.exists():
        _check_pii_for_global(src_xlsx)  # PIIFoundError を投げうる

    return _move_template(
        template_id,
        src_scope="case",
        dst_scope="global",
        replace=replace,
        keep_original=False,
    )


def demote_template(template_id: str, replace: bool = False) -> Dict[str, str]:
    """事務所グローバル → 案件スコープに **コピー**（global は維持）。

    典型的なユースケース: 特定案件だけ書式を微修正したい場合、global のコピーを
    案件スコープに置いて shadowing を作る。他案件は従来どおり global を参照する
    ため global は残す。
    """
    return _move_template(
        template_id,
        src_scope="global",
        dst_scope="case",
        replace=replace,
        keep_original=True,
    )


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
            scope=getattr(args, "scope", "global"),
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


def _cmd_promote(args: argparse.Namespace) -> int:
    try:
        result = promote_template(args.id, replace=args.replace)
    except PIIFoundError as e:
        print(
            json.dumps(
                {
                    "error": str(e),
                    "code": "pii_found",
                    "findings": e.findings[:20],
                    "total_findings": len(e.findings),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except FileExistsError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 3
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_save_user(args: argparse.Namespace) -> int:
    yaml_content = None
    if args.yaml_file:
        yaml_content = Path(args.yaml_file).expanduser().read_text(encoding="utf-8")
    try:
        result = save_user_template(
            Path(args.source),
            args.id,
            scope=args.scope,
            yaml_content=yaml_content,
            replace=args.replace,
        )
    except PIIFoundError as e:
        print(
            json.dumps(
                {
                    "error": str(e),
                    "code": "pii_found",
                    "findings": e.findings[:20],
                    "total_findings": len(e.findings),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    except FileExistsError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 3
    except (ValueError, FileNotFoundError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_demote(args: argparse.Namespace) -> int:
    try:
        result = demote_template(args.id, replace=args.replace)
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except FileExistsError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 3
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _self_test() -> int:
    """サニティチェック。同梱テンプレートのファイル整合性 + promote/demote を検証する。"""
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
            yaml_p = Path(e["_yaml_path"])
            text = yaml_p.read_text(encoding="utf-8")
            if "fields:" not in text:
                print(f"  [FAIL] {bid}: yaml missing 'fields:' block")
                all_ok = False
                continue
            print(f"  [PASS] {bid}: yaml + xlsx present, fields block ok")
    print(f"\ntemplate_lib: registry has {len(entries)} entries")

    # --- promote / demote self-test（一時 HOME + workspace で隔離実行） ---
    import os
    import tempfile
    ok = 0
    fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] promote/demote: {name}{(' — ' + detail) if detail else ''}")
        if cond:
            ok += 1
        else:
            fail += 1

    ws = _load_workspace()
    with tempfile.TemporaryDirectory() as td:
        fake_home = Path(td) / "home"
        fake_home.mkdir()
        case_root = Path(td) / "case-A"
        case_root.mkdir()

        # GLOBAL_ROOT / HOME を一時ディレクトリへ差し替え
        orig_global_root = ws.GLOBAL_ROOT
        orig_global_cfg = ws.GLOBAL_CONFIG_FILE
        orig_home = os.environ.get("HOME")
        ws.GLOBAL_ROOT = fake_home / ".claude-bengo"
        ws.GLOBAL_CONFIG_FILE = ws.GLOBAL_ROOT / "global.json"
        os.environ["HOME"] = str(fake_home)
        cwd_before = Path.cwd()
        os.chdir(case_root)
        try:
            ws.ensure_workspace()
            # case 側に手動でダミーテンプレート（{id}.yaml + 実 xlsx）を置く
            import openpyxl
            case_tdir = ws.templates_dir()
            case_tdir.mkdir(parents=True, exist_ok=True)
            (case_tdir / "promo-test.yaml").write_text("id: promo-test\ntitle: 昇格テスト\nfields: []\n", encoding="utf-8")
            wb_clean = openpyxl.Workbook()
            wb_clean.active["A1"] = "氏名"  # ラベルのみ、PII なし
            wb_clean.active["B1"] = "金額"
            wb_clean.save(case_tdir / "promo-test.xlsx")

            # 1. promote: case → global（moveなので case 側が消える）
            result = promote_template("promo-test")
            global_tdir = ws.global_templates_dir()
            check(
                "1. promoted yaml exists in global",
                (global_tdir / "promo-test.yaml").exists(),
                f"dst_yaml={result['dst_yaml']}",
            )
            check(
                "2. promoted xlsx exists in global",
                (global_tdir / "promo-test.xlsx").exists(),
            )
            check(
                "3. case side removed after promote",
                not (case_tdir / "promo-test.yaml").exists() and not (case_tdir / "promo-test.xlsx").exists(),
            )

            # 4. demote: global → case（copy。global は残る）
            demo_result = demote_template("promo-test")
            check(
                "4. demoted yaml exists in case",
                (case_tdir / "promo-test.yaml").exists(),
                f"dst_yaml={demo_result['dst_yaml']}",
            )
            check(
                "5. global side preserved after demote",
                (global_tdir / "promo-test.yaml").exists(),
            )

            # 6. collision without --replace raises
            raised = False
            try:
                demote_template("promo-test")
            except FileExistsError:
                raised = True
            check("6. demote collision without --replace raises", raised)

            # 7. --replace succeeds
            demo_result2 = demote_template("promo-test", replace=True)
            check("7. demote with --replace succeeds", demo_result2["replaced"] == "True")

            # 8. unknown id raises FileNotFoundError
            raised2 = False
            try:
                promote_template("does-not-exist")
            except FileNotFoundError:
                raised2 = True
            check("8. promote of unknown id raises FileNotFoundError", raised2)

            # 9. invalid id regex raises ValueError
            raised3 = False
            try:
                promote_template("../etc/passwd")
            except ValueError:
                raised3 = True
            check("9. promote of path-traversal id raises ValueError", raised3)

            # 10. --replace atomic swap: failure during stage → original retained
            # sample: put a valid template globally, then try to demote with --replace
            # and verify backup cleanup (no .backup leaked). Success path smoke test.
            global_y = global_tdir / "promo-test.yaml"
            global_x = global_tdir / "promo-test.xlsx"
            # Already exists from promote above. Replace and ensure no .backup left.
            _ = demote_template("promo-test", replace=True)
            leftovers = list(case_tdir.glob("*.backup")) + list(case_tdir.glob("*.staging"))
            leftovers += list(global_tdir.glob("*.backup")) + list(global_tdir.glob("*.staging"))
            check("10. no .staging/.backup left after --replace", not leftovers, f"leftovers={leftovers}")

            # 10b. promote with PII in xlsx must raise PIIFoundError (code-enforced)
            pii_case_dir = case_tdir  # already the case templates dir
            pii_id = "pii-test"
            (pii_case_dir / f"{pii_id}.yaml").write_text(
                f"id: {pii_id}\ntitle: PIIテスト\nfields: []\n", encoding="utf-8",
            )
            wb = openpyxl.Workbook()
            wb.active["A1"] = "氏名: 甲野太郎様"  # PII 混入
            wb.active["A2"] = "東京都千代田区千代田1-1"
            wb.save(pii_case_dir / f"{pii_id}.xlsx")

            raised_pii = False
            try:
                promote_template(pii_id)
            except PIIFoundError:
                raised_pii = True
            check("10b. promote with PII raises PIIFoundError", raised_pii)
            # case side must still be there (promote aborted)
            check(
                "10c. case xlsx preserved after failed promote",
                (pii_case_dir / f"{pii_id}.xlsx").exists(),
            )

            # 10d. with no admin lock set, ALLOW_PII_ON_GLOBAL=1 bypasses (test mode)
            os.environ["CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL"] = "1"
            try:
                r_override = promote_template(pii_id)
                check("10d. ALLOW_PII_ON_GLOBAL=1 bypasses when no admin lock", r_override["dst_scope"] == "global")
            finally:
                os.environ.pop("CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL", None)

            # 10d-bis. with admin lock set, =1 is NOT enough — need passphrase
            # Setup admin lock in the tempdir-mocked global config
            here_lib = Path(__file__).resolve().parent
            if str(here_lib) not in sys.path:
                sys.path.insert(0, str(here_lib))
            import importlib
            consent_mod = importlib.import_module("consent")
            gr = ws.load_global_config()
            # force-set admin lock
            gr["admin_lock"] = consent_mod._make_admin_lock("test-admin-pass")
            ws.save_global_config(gr)

            # re-setup pii xlsx in case (demote already moved it back)
            (pii_case_dir / f"{pii_id}.yaml").write_text(
                f"id: {pii_id}\nfields: []\n", encoding="utf-8",
            )
            wb_p = openpyxl.Workbook()
            wb_p.active["A1"] = "原告 甲野太郎"
            wb_p.save(pii_case_dir / f"{pii_id}.xlsx")
            # ensure not in global yet
            (global_tdir / f"{pii_id}.yaml").unlink(missing_ok=True)
            (global_tdir / f"{pii_id}.xlsx").unlink(missing_ok=True)

            os.environ["CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL"] = "1"
            raised_still = False
            try:
                promote_template(pii_id)
            except PIIFoundError:
                raised_still = True
            finally:
                os.environ.pop("CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL", None)
            check(
                "10d-bis. ALLOW_PII_ON_GLOBAL=1 rejected when admin lock exists",
                raised_still,
            )

            # 10d-ter. correct admin passphrase bypasses
            os.environ["CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL"] = "test-admin-pass"
            try:
                r_pass = promote_template(pii_id)
                check(
                    "10d-ter. correct admin passphrase in env var bypasses",
                    r_pass["dst_scope"] == "global",
                )
            finally:
                os.environ.pop("CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL", None)

            # clean up admin lock for remaining tests
            gr = ws.load_global_config()
            gr.pop("admin_lock", None)
            ws.save_global_config(gr)

            # 10e. save_user_template to global with PII is refused
            pii_src = Path(td) / "user-template.xlsx"
            wb2 = openpyxl.Workbook()
            wb2.active["A1"] = "原告 山田花子"
            wb2.save(pii_src)
            raised2 = False
            try:
                save_user_template(
                    pii_src, "user-pii-test", scope="global",
                    yaml_content="id: user-pii-test\nfields: []\n",
                )
            except PIIFoundError:
                raised2 = True
            check("10e. save_user_template(scope=global) with PII raises", raised2)

            # 10f. case scope ignores PII (local is OK)
            r_case = save_user_template(
                pii_src, "user-pii-test", scope="case",
                yaml_content="id: user-pii-test\nfields: []\n",
            )
            check("10f. save_user_template(scope=case) with PII succeeds", r_case["scope"] == "case")

            # 11. delete_failed flag surfaces when unlink fails (simulate by making
            # src dir read-only on POSIX. Skipped if not root and chmod can't deny).
            # Instead, pre-open a file handle and try on Windows? On macOS unlink
            # succeeds even with read-only parent dir if user owns it. Fall back:
            # check the result shape includes delete_failed key.
            # Re-promote to test the key.
            (case_tdir / "delete-test.yaml").write_text("id: delete-test\nfields: []\n", encoding="utf-8")
            wb_del = openpyxl.Workbook()
            wb_del.active["A1"] = "金額"
            wb_del.save(case_tdir / "delete-test.xlsx")
            r = promote_template("delete-test")
            check("11. promote result includes delete_failed key", "delete_failed" in r)
            check("12. delete_failed=False on normal promote", r.get("delete_failed") == "False")
        finally:
            ws.GLOBAL_ROOT = orig_global_root
            ws.GLOBAL_CONFIG_FILE = orig_global_cfg
            if orig_home is not None:
                os.environ["HOME"] = orig_home
            else:
                os.environ.pop("HOME", None)
            os.chdir(cwd_before)

    print(f"\npromote/demote self-test: {ok}/{ok + fail} passed")
    return 0 if (all_ok and fail == 0) else 1


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
    p_inst.add_argument("--matter", help="（廃止）v3.0.0+ では無視される")
    p_inst.add_argument("--replace", action="store_true", help="既存を上書き")
    p_inst.add_argument(
        "--scope",
        choices=("global", "case"),
        default="case",
        help="case=この案件のみ（既定、v3.3.0〜） / global=事務所全体",
    )
    p_inst.add_argument(
        "--skip-integrity",
        action="store_true",
        help="マニフェスト検証をスキップ（非推奨、デバッグ用）",
    )

    p_prom = sub.add_parser(
        "promote",
        help="案件スコープ → 事務所グローバルへ移動（PII 検出時は拒否）",
    )
    p_prom.add_argument("id")
    p_prom.add_argument("--replace", action="store_true", help="global 側に既存があれば上書き")

    p_save = sub.add_parser(
        "save-user",
        help="ユーザー作成テンプレートを指定スコープに保存（global は PII code-gate 付き）",
    )
    p_save.add_argument("--source", required=True, help="ソース XLSX パス")
    p_save.add_argument("--id", required=True, help="テンプレート ID")
    p_save.add_argument("--scope", choices=("case", "global"), default="case")
    p_save.add_argument("--yaml-file", help="書き込む YAML 定義のファイル（省略時は既存を期待）")
    p_save.add_argument("--replace", action="store_true", help="既存を上書き")

    p_dem = sub.add_parser(
        "demote",
        help="事務所グローバル → 案件スコープへコピー（global は維持）",
    )
    p_dem.add_argument("id")
    p_dem.add_argument("--replace", action="store_true", help="case 側に既存があれば上書き")

    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    if args.command is None:
        ap.print_help()
        return 1

    handlers = {
        "list": _cmd_list,
        "install": _cmd_install,
        "show": _cmd_show,
        "promote": _cmd_promote,
        "demote": _cmd_demote,
        "save-user": _cmd_save_user,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
