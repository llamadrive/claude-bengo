#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude-bengo 監査ログ記録モジュール。

日本の法律事務所が弁護士法第23条（秘密保持義務）および個人情報保護法
第25条（委託先監督義務）を遵守するために、本プラグインで処理した文書の
メタデータを追記専用ログとして記録する。

## 記録する情報
- タイムスタンプ（ISO 8601 ローカルタイムゾーン付き）
- セッション ID
- スキル名
- イベント種別（file_read / file_write / api_call / command_start / command_end / rotation）
- ファイル名ハッシュ（SHA-256、常時記録。依頼者氏名の秘匿のため）
- ファイル名そのもの（デフォルト空文字、`--log-filename` で明示的にオプトインした場合のみ記録）
- バイト数
- ファイル内容の SHA-256
- ハッシュチェーン（`prev_hash`、改ざん検知用）

## 記録しない情報
- ファイルの中身（プライバシー保護のため）
- Claude API の入出力本文

## ログ場所
- デフォルト: `~/.claude-bengo/audit.jsonl`（グローバルログ。事案横断イベントの保存先）
- 上書き: 環境変数 `CLAUDE_BENGO_AUDIT_PATH`
- 無効化: `CLAUDE_BENGO_AUDIT_PATH=/dev/null` (POSIX) または `=NUL` (Windows)

## 事案（matter）スコープのログ（v2.0.0 〜）

複数事案を同一端末で扱う事務所向けに、事案ごとに独立した監査ログへ書き込める。

```
~/.claude-bengo/matters/{matter-id}/audit.jsonl
```

- `--matter <id>` フラグを `record` / `verify` / `export` に渡すと、その事案のログへ
  ルーティングする（ハッシュチェーン・ロック・ローテーションは事案ごとに独立）。
- `--matter` 未指定時は従来どおりグローバルログを使う。matter-create / matter-switch
  のような事案横断イベント、および非機密スキル（law-search 等）はグローバル側に残す。
- 環境変数 `CLAUDE_BENGO_AUDIT_AUTO_MATTER=1` を設定すると、`--matter` 未指定かつ
  `CLAUDE_BENGO_AUDIT_PATH` も未設定の場合に `matter.resolve()` で自動解決し、
  有効な事案が見つかればそのログへ書き込む。既定は opt-in（従来挙動を保つ）。
- 事案が存在しない場合、`record` は exit 2 で終了する（先に `/matter-create` が必要）。
  孤児ログを作らない設計。

## 事案スコープ時の優先順位（高い順）

1. 明示 `--matter <id>` フラグ
2. 環境変数 `CLAUDE_BENGO_AUDIT_PATH`（テスト／カスタム設定向けの明示オーバーライド）
3. `CLAUDE_BENGO_AUDIT_AUTO_MATTER=1` かつ `matter.resolve()` が有効 matter を返した場合
4. 既定 `~/.claude-bengo/audit.jsonl`

## ハッシュチェーンによる改ざん検知

各レコードには直前の行の SHA-256 ハッシュ値が `prev_hash` として埋め込まれる。
先頭レコードは 64 個の 0 を使用する。行を書き換える・削除するとチェーンが破綻し、
`verify` サブコマンドで検出可能となる。

ハッシュチェーンは**ファイル単位**で独立している。事案 A のログと事案 B のログは
別々のチェーンを持ち、互いに干渉しない。`verify --matter <id> --all` はその事案の
アクティブログ＋ローテート済みログをまとめて検証する。

ただしログファイル全体の削除は検知できない。WORM 要件がある場合は、顧客管理の
追記専用ストレージ（例: S3 Object Lock）へ定期的にエクスポートすること。

## CLI 使用例

```
python3 skills/_lib/audit.py record --skill typo-check --event file_read --file "準備書面.docx"
python3 skills/_lib/audit.py record --matter smith-v-jones --skill typo-check --event file_read --file "準備書面.docx"
python3 skills/_lib/audit.py record --skill typo-check --event file_read --file "準備書面.docx" --log-filename
python3 skills/_lib/audit.py export --matter smith-v-jones --since 2026-04-01 --format csv
python3 skills/_lib/audit.py verify --matter smith-v-jones --all
python3 skills/_lib/audit.py --self-test
```
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

DEFAULT_AUDIT_PATH = Path.home() / ".claude-bengo" / "audit.jsonl"
SESSION_ID_FILE = Path.home() / ".claude-bengo" / "session_id.txt"
SESSION_TTL_SECONDS = 3600  # 1 時間

# Python 3.8 では `__file__` が相対のまま残ることがあり、self-test 内で
# subprocess が `cwd` を変えた時に「No such file」で失敗する（Python 3.9+ の
# bpo-20443 で絶対化される）。module load 時に一度だけ解決しておく。
SELF_PATH = os.path.abspath(__file__)


def _load_matter_module():
    """matter.py を遅延ロードする。

    audit.py と matter.py は同じ `skills/_lib/` に同居しているため、
    `__file__` の親ディレクトリを sys.path 先頭に挿入してインポートする。
    他の呼出元の sys.path を汚さないため、インポート後は元に戻す。
    """
    import importlib

    here = str(Path(__file__).resolve().parent)
    added = False
    if here not in sys.path:
        sys.path.insert(0, here)
        added = True
    try:
        return importlib.import_module("matter")
    finally:
        if added:
            try:
                sys.path.remove(here)
            except ValueError:
                pass

VALID_EVENTS = {
    "file_read",
    "file_write",
    "api_call",
    "command_start",
    "command_end",
    "rotation",
    # v2.6.1 計算器コンプライアンスイベント
    "calc_run",      # 決定論計算器の実行開始
    "calc_result",   # 計算結果（金額等の主要数値）
}

# `/dev/null` 相当として扱うパス。`os.devnull` は POSIX では `/dev/null`、
# Windows では `nul` を返すため、プラットフォーム差を吸収する。
SENTINEL_PATHS = {os.devnull, "NUL", "nul", "/dev/null"}

# ハッシュチェーンの先頭に置くゼロハッシュ（先行行なしを示す）
ZERO_HASH = "0" * 64

# ログローテーションの閾値（既定 50 MiB）
# 環境変数 `CLAUDE_BENGO_AUDIT_MAX_BYTES` で上書き可能（主にテスト用途）
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def _is_sentinel(p: Path) -> bool:
    """センチネルパス（/dev/null 相当）か判定する。

    Windows で `Path("/dev/null")` が `\\dev\\null` に正規化される件に対応して、
    スラッシュを正規化したうえで比較する。
    """
    s = str(p).replace("\\", "/").lower()
    return s in {"/dev/null", "dev/null", "nul"} or s.endswith("/nul") or s.endswith("/dev/null")


def _audit_path(matter_id: Optional[str] = None) -> Path:
    """監査ログファイルのパスを取得する。

    優先順位:
      1. 明示 `matter_id`（呼出側で解決・検証済み）
      2. 環境変数 `CLAUDE_BENGO_AUDIT_PATH`（明示オーバーライド。テスト用途）
      3. `CLAUDE_BENGO_AUDIT_AUTO_MATTER=1` かつ matter.resolve() が有効 matter を返す場合
      4. 既定 `~/.claude-bengo/audit.jsonl`

    matter_id が指定された場合は matter.matter_audit_path を経由するため、
    `CLAUDE_BENGO_ROOT` 環境変数のオーバーライドも尊重される。
    """
    if matter_id:
        m = _load_matter_module()
        return m.matter_audit_path(matter_id)

    override = os.environ.get("CLAUDE_BENGO_AUDIT_PATH")
    if override:
        return Path(override)

    # opt-in 自動解決
    if os.environ.get("CLAUDE_BENGO_AUDIT_AUTO_MATTER") == "1":
        try:
            m = _load_matter_module()
            result = m.resolve()
            auto_id = result.get("matter_id")
            if auto_id and result.get("exists"):
                return m.matter_audit_path(auto_id)
        except Exception:
            # 自動解決失敗時はグローバルログへフォールバック（監査を止めない）
            pass

    return DEFAULT_AUDIT_PATH


def _resolve_matter_for_write(matter_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """書込用に matter_id を検証する。

    戻り値: (resolved_matter_id, error_json_string)
    - 引数 matter_id が None なら (None, None)
    - 命名規則違反 → (None, JSON エラー)
    - 事案ディレクトリ未作成 → (None, JSON エラー)
    - 有効な場合 → (matter_id, None)
    """
    if not matter_id:
        return None, None
    m = _load_matter_module()
    ok, reason = m.validate_matter_id(matter_id)
    if not ok:
        return None, json.dumps(
            {"error": f"--matter の値が無効: {reason}"}, ensure_ascii=False
        )
    if not m.matter_exists(matter_id):
        msg = (
            f"エラー: matter '{matter_id}' が存在しない。\n"
            f"先に `/matter-create {matter_id}` を実行するか、/matter-list で既存 matter を確認してほしい。"
        )
        return None, json.dumps({"error": msg}, ensure_ascii=False)
    return matter_id, None


def _max_bytes() -> int:
    """ローテーション閾値を返す。環境変数で上書き可能。"""
    v = os.environ.get("CLAUDE_BENGO_AUDIT_MAX_BYTES")
    if v:
        try:
            n = int(v)
            if n > 0:
                return n
        except ValueError:
            pass
    return DEFAULT_MAX_BYTES


def _ensure_parent(p: Path) -> None:
    """親ディレクトリを作成する（POSIX では 0700）。センチネルパスは無視する。"""
    if _is_sentinel(p):
        return
    parent = p.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except (OSError, NotImplementedError):
        # Windows や特殊 FS では無視する
        pass


def _get_session_id() -> str:
    """セッション ID を取得する。環境変数優先、なければファイルキャッシュ。"""
    env_id = os.environ.get("CLAUDE_BENGO_SESSION_ID")
    if env_id:
        return env_id

    try:
        SESSION_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        if SESSION_ID_FILE.exists():
            mtime = SESSION_ID_FILE.stat().st_mtime
            if time.time() - mtime < SESSION_TTL_SECONDS:
                cached = SESSION_ID_FILE.read_text(encoding="utf-8").strip()
                if cached:
                    return cached
        # 新規生成
        sid = secrets.token_hex(16)
        SESSION_ID_FILE.write_text(sid, encoding="utf-8")
        try:
            os.chmod(SESSION_ID_FILE, 0o600)
        except (OSError, NotImplementedError):
            pass
        return sid
    except OSError:
        # ファイル書込に失敗した場合でも ID は返す（監査を止めない）
        return secrets.token_hex(16)


def _iso_now() -> str:
    """ローカルタイムゾーン付きの ISO 8601 タイムスタンプを返す。"""
    now = _dt.datetime.now().astimezone()
    return now.isoformat(timespec="milliseconds")


def _sha256_file(path: Path, max_bytes: int = 100 * 1024 * 1024) -> Optional[str]:
    """ファイルの SHA-256 を計算する。100MB を超えるファイルは None を返す。"""
    try:
        size = path.stat().st_size
        if size > max_bytes:
            return None
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _sha256_text(text: str) -> str:
    """UTF-8 文字列の SHA-256 を返す。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    """バイト列の SHA-256 を返す。"""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# ハッシュチェーン／ファイルロック
# ---------------------------------------------------------------------------


def _read_last_line_bytes(path: Path, tail_size: int = 8192) -> Optional[bytes]:
    """ログの末尾行のバイト列を返す。空ファイルなら None。

    ファイル末尾から最大 `tail_size` バイトを読み、改行で分割する。
    各レコードは 1 KB 程度なので 8 KB あれば十分。
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return None
    read = min(size, tail_size)
    with path.open("rb") as f:
        f.seek(size - read)
        chunk = f.read(read)
    # 末尾の余分な改行を除去
    chunk = chunk.rstrip(b"\n")
    if not chunk:
        return None
    # 最後の改行以降がファイル末尾行
    nl = chunk.rfind(b"\n")
    if nl < 0:
        # 読み出した範囲に改行がない場合は、それがそのまま1行目の一部
        # （tail_size を超える先頭だけの単一行は監査用途では事実上発生しない）
        return chunk
    return chunk[nl + 1 :]


def _compute_prev_hash(path: Path) -> str:
    """書き込み前に参照すべき `prev_hash` を計算する。

    ファイル未作成／空なら ZERO_HASH。既存なら末尾行の SHA-256（改行除く）。
    """
    if not path.exists():
        return ZERO_HASH
    last = _read_last_line_bytes(path)
    if last is None:
        return ZERO_HASH
    return _sha256_bytes(last)


class _FileLock:
    """POSIX 上では fcntl.flock を用いた協調的排他制御。

    並行書込時にハッシュチェーンが破綻しないよう、prev_hash 取得から
    追記・fsync までをロック範囲に含める。Windows では msvcrt.locking を使用。
    取得失敗時は warning を出して続行する（ロックなし、可搬性優先）。
    """

    def __init__(self, path: Path):
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self._fh = None  # type: ignore[var-annotated]
        self._mode = None  # type: ignore[var-annotated]

    def __enter__(self) -> "_FileLock":
        fallback_reason: Optional[str] = None
        try:
            # ロックファイルは親ディレクトリに作成する
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.lock_path, "a+")
            if os.name == "posix":
                try:
                    import fcntl  # type: ignore

                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
                    self._mode = "flock"
                except Exception as e:
                    fallback_reason = f"fcntl.flock failed: {e}"
                    self._mode = None
            else:
                try:
                    import msvcrt  # type: ignore

                    # 末尾に移動しロック（ブロッキング）
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_LOCK, 1)
                    self._mode = "msvcrt"
                except Exception as e:
                    fallback_reason = f"msvcrt.locking failed: {e}"
                    self._mode = None
        except Exception as e:
            fallback_reason = f"lockfile open failed: {e}"
            self._mode = None

        # ロック取得失敗時は非ロック続行するが、stderr に警告を出す。
        # 並行書込ではチェーン破綻の可能性があるため、運用者に可視化する。
        # 環境変数 `CLAUDE_BENGO_AUDIT_SILENT_LOCK_FALLBACK=1` で抑止可能。
        if self._mode is None and fallback_reason:
            if os.environ.get("CLAUDE_BENGO_AUDIT_SILENT_LOCK_FALLBACK") != "1":
                print(
                    f"WARN: audit.py _FileLock fallback to unlocked mode ({fallback_reason}). "
                    "Concurrent writes may break the hash chain. "
                    "Set CLAUDE_BENGO_AUDIT_SILENT_LOCK_FALLBACK=1 to suppress.",
                    file=sys.stderr,
                )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        try:
            if self._fh is not None:
                if self._mode == "flock":
                    import fcntl  # type: ignore

                    try:
                        fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                elif self._mode == "msvcrt":
                    try:
                        import msvcrt  # type: ignore

                        self._fh.seek(0)
                        msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                self._fh.close()
        finally:
            self._fh = None


# ---------------------------------------------------------------------------
# ローテーション
# ---------------------------------------------------------------------------


def _keep_count() -> Optional[int]:
    """保持するローテート済みログの本数。`CLAUDE_BENGO_AUDIT_KEEP` で指定。

    未設定または 0 以下なら None（無制限）。WORM 要件のある事務所向けは
    通常 None のまま外部ストレージへエクスポートする。ディスク逼迫を避けたい
    事務所は 10〜30 程度が目安。
    """
    v = os.environ.get("CLAUDE_BENGO_AUDIT_KEEP")
    if not v:
        return None
    try:
        n = int(v)
        return n if n > 0 else None
    except ValueError:
        return None


def _prune_rotations(active: Path, keep: int) -> None:
    """ローテート済みログを古い順に削除し、keep 本のみ残す。

    削除前に stderr へ通知して運用者が気づけるようにする（監査痕跡が消える操作のため）。
    """
    if not active.parent.exists():
        return
    prefix = active.name + "."
    rotated = [
        p for p in active.parent.iterdir()
        if p.is_file()
        and p.name.startswith(prefix)
        and not p.name.endswith(".lock")
    ]
    rotated.sort(key=lambda p: p.name)  # 古い順
    excess = max(0, len(rotated) - keep)
    for p in rotated[:excess]:
        try:
            print(
                f"INFO: audit.py pruning old rotated log (KEEP={keep}): {p.name}",
                file=sys.stderr,
            )
            p.unlink()
        except OSError:
            pass


def _rotate_if_needed(path: Path) -> Optional[str]:
    """ファイルサイズが閾値を超えていればローテートする。

    旧ログを `audit.jsonl.{YYYYMMDDTHHMMSS}` にリネームし、新しいログの
    先頭に置く `rotation` イベントの `prev_hash`（旧ログ末尾行のハッシュ）と
    リネーム後のファイル名を返す。ローテートしなかった場合は None。

    `CLAUDE_BENGO_AUDIT_KEEP=N` が設定されている場合、ローテート後に古い
    rotate ファイルを `N` 本を残して削除する（未設定なら削除しない）。
    """
    if _is_sentinel(path) or not path.exists():
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size < _max_bytes():
        return None

    # 旧ログ末尾のハッシュをチェーンの継続起点とする
    last = _read_last_line_bytes(path)
    continuation_hash = _sha256_bytes(last) if last else ZERO_HASH

    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    rotated = path.with_name(path.name + "." + ts)
    # 万一衝突したら連番を付与する
    i = 1
    while rotated.exists():
        rotated = path.with_name(path.name + f".{ts}.{i}")
        i += 1
    os.rename(path, rotated)

    # 保持数を超える古いローテート済みログを削除（opt-in）
    keep = _keep_count()
    if keep is not None:
        _prune_rotations(path, keep)

    return json.dumps(
        {"prev_hash": continuation_hash, "rotated_from": rotated.name},
        ensure_ascii=False,
    )


def _write_line_atomic(path: Path, line: str, prev_hash_override: Optional[str] = None) -> None:
    """1 行を追記し、fsync する。

    `prev_hash_override` が与えられた場合、それを record の prev_hash として使い、
    そうでなければファイル末尾から自動計算する。line は JSON オブジェクト文字列の
    `prev_hash` フィールドを後付けで埋めるため、ここでは dict を渡すのではなく
    既に完成した1行を書き込む。
    """
    _ensure_parent(path)
    f = open(path, "a", encoding="utf-8")
    try:
        f.write(line + "\n")
        try:
            f.flush()
            os.fsync(f.fileno())
        except (OSError, AttributeError, ValueError) as e:
            # 一部 FS では fsync が失敗する。警告のみで続行。
            print(
                json.dumps(
                    {"warning": f"fsync failed (record still written): {e}"},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
    finally:
        f.close()
    try:
        os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


# ---------------------------------------------------------------------------
# record サブコマンド
# ---------------------------------------------------------------------------


def _build_record(
    *,
    skill: str,
    event: str,
    filename: str,
    filename_sha256: str,
    bytes_: Optional[int],
    sha256: str,
    api_calls: int,
    note: str,
    prev_hash: str,
    rotated_from: Optional[str] = None,
) -> dict:
    """フィールド順序を固定した record dict を返す（JSON 決定性のため）。

    `rotated_from` は rotation イベント専用。通常の記録時は省略する。
    """
    rec: dict = {
        "ts": _iso_now(),
        "session_id": _get_session_id(),
        "skill": skill,
        "event": event,
        "filename": filename,
        "filename_sha256": filename_sha256,
        "bytes": bytes_,
        "sha256": sha256,
        "api_calls": api_calls,
        "note": note,
        "prev_hash": prev_hash,
    }
    if rotated_from is not None:
        rec["rotated_from"] = rotated_from
    return rec


def cmd_record(args: argparse.Namespace) -> int:
    if args.event not in VALID_EVENTS:
        print(
            json.dumps(
                {"error": f"invalid event '{args.event}'. Valid: {sorted(VALID_EVENTS)}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    # 明示 --matter があれば検証（存在しなければ exit 2）
    matter_id = getattr(args, "matter", None)
    if matter_id:
        resolved, err = _resolve_matter_for_write(matter_id)
        if err is not None:
            print(err, file=sys.stderr)
            # 命名規則違反は 1、matter 未作成は 2
            m = _load_matter_module()
            ok, _ = m.validate_matter_id(matter_id)
            return 1 if not ok else 2
        path = _audit_path(matter_id=resolved)
    else:
        path = _audit_path()

    # センチネル（/dev/null 相当）の場合は短絡して成功扱いで戻る。
    # ここで戻らないと POSIX でも macOS/Linux で `NUL` という名のファイルが
    # カレントディレクトリに作られてしまう（再現済みのバグ）。
    if _is_sentinel(path):
        print(json.dumps({"info": f"audit disabled (path={path})"}, ensure_ascii=False))
        return 0

    filename_plain = ""
    filename_hash = ""
    bytes_ = None
    sha = args.sha256

    if args.file:
        p = Path(args.file)
        # `filename_sha256` は常に basename（UTF-8）を対象に計算する。
        # 絶対パスやディレクトリ名を含めるとクライアント識別の手掛かりが増える
        # ため、既定では常に basename で固定する。
        base = p.name
        filename_hash = _sha256_text(base)

        # `--log-filename` が指定された場合のみ、平文ファイル名を記録する。
        # `--full-path` は `--log-filename` とセットの場合のみ有効。
        if args.log_filename:
            filename_plain = str(p) if args.full_path else base
        else:
            filename_plain = ""

        if p.exists() and p.is_file():
            try:
                bytes_ = p.stat().st_size
            except OSError:
                bytes_ = None
            if not sha:
                sha = _sha256_file(p)
    elif args.bytes is not None:
        bytes_ = args.bytes

    try:
        _ensure_parent(path)
        with _FileLock(path):
            # ローテーション（必要なら）
            rotation_meta = _rotate_if_needed(path)
            if rotation_meta is not None:
                meta = json.loads(rotation_meta)
                rot_rec = _build_record(
                    skill="_audit",
                    event="rotation",
                    filename="",
                    filename_sha256="",
                    bytes_=None,
                    sha256="",
                    api_calls=0,
                    note=f"rotated from {meta['rotated_from']}",
                    prev_hash=meta["prev_hash"],
                    rotated_from=meta["rotated_from"],
                )
                _write_line_atomic(path, json.dumps(rot_rec, ensure_ascii=False))

            # 通常レコードの prev_hash を計算し、追記
            prev_hash = _compute_prev_hash(path)
            record = _build_record(
                skill=args.skill,
                event=args.event,
                filename=filename_plain,
                filename_sha256=filename_hash,
                bytes_=bytes_,
                sha256=sha or "",
                api_calls=args.api_calls,
                note=args.note or "",
                prev_hash=prev_hash,
            )
            _write_line_atomic(path, json.dumps(record, ensure_ascii=False))
    except OSError as e:
        print(
            json.dumps({"error": f"failed to write audit log: {e}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    # 成功時は記録内容を stdout に出す（Claude が確認用に参照できる）
    print(json.dumps(record, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# export サブコマンド
# ---------------------------------------------------------------------------


def cmd_export(args: argparse.Namespace) -> int:
    matter_id = getattr(args, "matter", None)
    if matter_id:
        resolved, err = _resolve_matter_for_write(matter_id)
        if err is not None:
            print(err, file=sys.stderr)
            m = _load_matter_module()
            ok, _ = m.validate_matter_id(matter_id)
            return 1 if not ok else 2
        path = _audit_path(matter_id=resolved)
    else:
        path = _audit_path()
    if not path.exists():
        print(json.dumps({"error": f"audit log not found: {path}"}), file=sys.stderr)
        return 2

    since_date: Optional[_dt.date] = None
    if args.since:
        try:
            since_date = _dt.date.fromisoformat(args.since)
        except ValueError:
            print(
                json.dumps({"error": f"invalid --since: {args.since} (expect YYYY-MM-DD)"}),
                file=sys.stderr,
            )
            return 1

    records = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 破損行は無視する
                if args.skill and rec.get("skill") != args.skill:
                    continue
                if since_date:
                    ts = rec.get("ts", "")
                    try:
                        rec_date = _dt.date.fromisoformat(ts.split("T")[0])
                    except ValueError:
                        continue
                    if rec_date < since_date:
                        continue
                records.append(rec)
    except OSError as e:
        print(json.dumps({"error": f"failed to read audit log: {e}"}), file=sys.stderr)
        return 2

    if args.format == "csv":
        import csv

        writer = csv.writer(sys.stdout)
        writer.writerow(
            [
                "ts",
                "session_id",
                "skill",
                "event",
                "filename",
                "filename_sha256",
                "bytes",
                "sha256",
                "api_calls",
                "note",
                "prev_hash",
            ]
        )
        for r in records:
            writer.writerow(
                [
                    r.get("ts", ""),
                    r.get("session_id", ""),
                    r.get("skill", ""),
                    r.get("event", ""),
                    r.get("filename", ""),
                    r.get("filename_sha256", ""),
                    r.get("bytes", ""),
                    r.get("sha256", ""),
                    r.get("api_calls", 0),
                    r.get("note", ""),
                    r.get("prev_hash", ""),
                ]
            )
    else:
        print(json.dumps(records, ensure_ascii=False, indent=2))

    return 0


# ---------------------------------------------------------------------------
# verify サブコマンド
# ---------------------------------------------------------------------------


def _verify_file(path: Path) -> Tuple[int, int, int, List[str]]:
    """ハッシュチェーンを検証する。

    戻り値: (ok_count, fail_count, legacy_count, messages)
    - ok_count: prev_hash が整合した行
    - fail_count: チェーン破綻を検知した行
    - legacy_count: prev_hash フィールドを持たない旧形式の行
    - messages: 各行の PASS/FAIL/LEGACY メッセージ
    """
    ok = 0
    fail = 0
    legacy = 0
    msgs: List[str] = []

    prev_line_bytes: Optional[bytes] = None
    chain_started = False  # 最初の prev_hash 行を見たら True
    lineno = 0

    with path.open("rb") as f:
        for raw in f:
            lineno += 1
            line_stripped = raw.rstrip(b"\n")
            if not line_stripped:
                continue
            try:
                rec = json.loads(line_stripped.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                fail += 1
                msgs.append(f"FAIL line {lineno}: malformed JSON ({e})")
                prev_line_bytes = line_stripped
                continue

            if "prev_hash" not in rec:
                legacy += 1
                msgs.append(f"LEGACY line {lineno}: no prev_hash (pre-chain record)")
                prev_line_bytes = line_stripped
                continue

            expected: Optional[str]
            if not chain_started:
                # ローテーション由来のファイルの先頭: `rotation` イベントは
                # 旧ログ末尾行のハッシュを prev_hash として持つ。旧ログが同一
                # ディレクトリに残っていれば検証する。なければ「境界」として
                # 通過させる（OK 扱いにメッセージだけ ROTATION_BOUNDARY）。
                if rec.get("event") == "rotation" and rec.get("rotated_from"):
                    sibling = path.parent / rec["rotated_from"]
                    if sibling.exists():
                        sibling_tail = _read_last_line_bytes(sibling)
                        expected = _sha256_bytes(sibling_tail) if sibling_tail else ZERO_HASH
                        if rec.get("prev_hash") == expected:
                            ok += 1
                            msgs.append(
                                f"PASS line {lineno}: rotation continuation verified "
                                f"against {rec['rotated_from']}"
                            )
                        else:
                            fail += 1
                            msgs.append(
                                f"FAIL line {lineno}: rotation prev_hash mismatch with "
                                f"{rec['rotated_from']} tail "
                                f"(expected {expected[:12]}..., got "
                                f"{str(rec.get('prev_hash'))[:12]}...)"
                            )
                    else:
                        # 旧ログが削除・別場所に退避済み。チェーン境界として通過
                        ok += 1
                        msgs.append(
                            f"PASS line {lineno}: rotation boundary (rotated file "
                            f"'{rec['rotated_from']}' not present; cross-file verification skipped)"
                        )
                    chain_started = True
                    prev_line_bytes = line_stripped
                    continue

                # 通常のチェーン開始: ZERO_HASH または旧形式末尾ハッシュ
                if prev_line_bytes is None:
                    expected = ZERO_HASH
                else:
                    expected = _sha256_bytes(prev_line_bytes)
                chain_started = True
            else:
                # 以降は直前の行（既に chain 内）のハッシュでなければならない
                assert prev_line_bytes is not None
                expected = _sha256_bytes(prev_line_bytes)

            if rec.get("prev_hash") == expected:
                ok += 1
                msgs.append(f"PASS line {lineno}")
            else:
                fail += 1
                msgs.append(
                    f"FAIL line {lineno}: prev_hash mismatch "
                    f"(expected {expected[:12]}..., got {str(rec.get('prev_hash'))[:12]}...)"
                )

            prev_line_bytes = line_stripped

    return ok, fail, legacy, msgs


def _discover_rotated_siblings(active: Path) -> List[Path]:
    """アクティブログと同じ親ディレクトリに存在するローテート済みログを列挙する。

    命名規則: `audit.jsonl.{YYYYMMDDTHHMMSS}` または `audit.jsonl.{ts}.{N}`。
    タイムスタンプ昇順で返す（古いものから順に）。
    """
    if not active.parent.exists():
        return []
    prefix = active.name + "."
    candidates = [
        p
        for p in active.parent.iterdir()
        if p.is_file() and p.name.startswith(prefix) and not p.name.endswith(".lock")
    ]
    # ファイル名の末尾タイムスタンプで昇順ソート
    candidates.sort(key=lambda p: p.name)
    return candidates


def cmd_ingest(args: argparse.Namespace) -> int:
    """監査ログを claude-bengo-cloud にアップロードする。

    Bearer token で認証（firm_api_tokens で検証）。ndjson (改行区切り JSON)
    を `application/x-ndjson` で POST する。リクエストはバッチ分割され、
    冪等 — 同じエントリを複数回送信しても cloud 側でハッシュチェーンで
    重複検出される設計（MVP では単純に全件 insert するが、将来重複排除予定）。
    """
    import urllib.request
    import urllib.error

    token = args.token or os.environ.get("CLAUDE_BENGO_CLOUD_TOKEN")
    if not token:
        print(
            json.dumps(
                {
                    "error": (
                        "Bearer token が未指定。--token か環境変数 "
                        "CLAUDE_BENGO_CLOUD_TOKEN を設定してほしい。"
                    )
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    matter_id = getattr(args, "matter", None)
    if matter_id:
        m = _load_matter_module()
        ok, reason = m.validate_matter_id(matter_id)
        if not ok or not m.matter_exists(matter_id):
            print(
                json.dumps(
                    {"error": f"matter '{matter_id}' が無効または未作成: {reason}"},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        path = m.matter_audit_path(matter_id)
    else:
        path = DEFAULT_AUDIT_PATH

    if not path.exists():
        print(
            json.dumps({"error": f"ログファイルが存在しない: {path}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    # Collect entries, optionally filtered by --since.
    since: Optional[_dt.date] = None
    if args.since:
        try:
            since = _dt.date.fromisoformat(args.since)
        except ValueError:
            print(
                json.dumps(
                    {"error": f"--since は YYYY-MM-DD 形式で: {args.since}"},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2

    entries: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            stripped = raw_line.rstrip("\n")
            if not stripped.strip():
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                continue  # tolerate partial/corrupt final lines
            if since is not None:
                ts = rec.get("ts", "")
                try:
                    rec_date = _dt.date.fromisoformat(ts[:10])
                    if rec_date < since:
                        continue
                except Exception:
                    pass
            if matter_id:
                rec["matter_id"] = matter_id
            # Phase C-1: compute this_hash BEFORE we mutate the record for
            # transport. Cloud uses this to verify the chain (each entry's
            # prev_hash must match the previous entry's this_hash).
            # We hash the RAW line bytes so the value is independent of
            # JSON re-serialization quirks (space-after-colon, key order).
            rec["this_hash"] = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
            entries.append(rec)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "would_send": len(entries),
                    "source": str(path),
                    "url": args.url,
                    "matter": matter_id,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if not entries:
        print(
            json.dumps({"info": "送信対象のエントリなし（0件）"}, ensure_ascii=False)
        )
        return 0

    batch_size = max(1, min(args.batch_size, 10_000))
    sent = 0
    for i in range(0, len(entries), batch_size):
        batch = entries[i : i + batch_size]
        body = "\n".join(json.dumps(e, ensure_ascii=False) for e in batch).encode("utf-8")
        req = urllib.request.Request(
            args.url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-ndjson",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                resp_json = json.loads(resp_body) if resp_body else {}
                sent += int(resp_json.get("imported", len(batch)))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(
                json.dumps(
                    {
                        "error": f"HTTP {e.code}: {err_body}",
                        "sent_before_failure": sent,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1
        except urllib.error.URLError as e:
            print(
                json.dumps(
                    {
                        "error": f"network error: {e.reason}",
                        "sent_before_failure": sent,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1

    print(
        json.dumps(
            {"sent": sent, "batches": (len(entries) + batch_size - 1) // batch_size},
            ensure_ascii=False,
        )
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    matter_id = getattr(args, "matter", None)
    if args.path:
        # --path は最優先。事案スコープ外の任意ファイルを検証する用途。
        path = Path(args.path)
    elif matter_id:
        resolved, err = _resolve_matter_for_write(matter_id)
        if err is not None:
            print(err, file=sys.stderr)
            m = _load_matter_module()
            ok, _ = m.validate_matter_id(matter_id)
            return 1 if not ok else 2
        path = _audit_path(matter_id=resolved)
    else:
        path = _audit_path()
    if _is_sentinel(path):
        print(json.dumps({"info": f"audit disabled (path={path})"}, ensure_ascii=False))
        return 0
    if not path.exists():
        print(json.dumps({"error": f"audit log not found: {path}"}), file=sys.stderr)
        return 2

    # `--all` 指定時はローテート済みファイルも順に検証する
    files_to_verify: List[Path] = []
    if getattr(args, "all", False):
        siblings = _discover_rotated_siblings(path)
        files_to_verify.extend(siblings)
        files_to_verify.append(path)
    else:
        files_to_verify.append(path)

    total_ok = 0
    total_fail = 0
    total_legacy = 0

    for f in files_to_verify:
        print(f"## {f.name}")
        ok, fail, legacy, msgs = _verify_file(f)
        for m in msgs:
            print(m)
        print(
            f"  subtotal: ok={ok}, fail={fail}, legacy={legacy}, total={ok + fail + legacy}"
        )
        print()
        total_ok += ok
        total_fail += fail
        total_legacy += legacy

    print(
        f"summary: ok={total_ok}, fail={total_fail}, legacy={total_legacy}, "
        f"total={total_ok + total_fail + total_legacy} "
        f"(files verified: {len(files_to_verify)})"
    )
    print(
        "NOTE: 'chain intact' にはログファイル全体の削除や先頭ブロックの総入替は"
        "含まれない。外部 WORM ストレージ（例: S3 Object Lock）へ定期エクスポート"
        "しない限り、完全な改ざん耐性は得られない。"
    )
    if not getattr(args, "all", False):
        siblings = _discover_rotated_siblings(path)
        if siblings:
            print(
                f"INFO: {len(siblings)} 件のローテート済みログが検出された。"
                "全て検証するには `verify --all` を実行する。"
            )
    return 0 if total_fail == 0 else 1


# ---------------------------------------------------------------------------
# セルフテスト
# ---------------------------------------------------------------------------


def _self_test() -> int:
    """自己テスト群。stdlib のみで完結する。

    テスト内容:
      1. 100 件連続書込でチェーンが整合する
      2. 1 行改変で FAIL を検出する
      3. 行削除で FAIL を検出する
      4. 行の入替で FAIL を検出する
      5. `/dev/null` と `NUL` 指定でファイルが作られない
      6. 10 並列プロセス書込でもチェーンが破綻しない（flock 前提）
      7. サイズ閾値超過で rotation イベントが挿入される
      8. `filename` はデフォルト空、`--log-filename` でのみ記録される
      9. `filename_sha256` は常時記録される
     10. `--matter <id>` で事案スコープのログへルーティングされる
     11. 存在しない matter を指定すると exit 2 で失敗する
     12. `CLAUDE_BENGO_AUDIT_AUTO_MATTER=1` で matter が自動解決される
     13. `verify --matter <id>` が事案スコープログを検証する
     14. `export --matter <id>` が事案スコープログのみ読む
     15. 異なる matter への並行書込が相互干渉しない（ロックが別）
     16. `verify --matter <id> --all` がローテート済み事案ログを含めて検証する
    """
    import tempfile
    import subprocess
    import shutil

    results: List[Tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")

    # 一時ディレクトリ
    tmpdir = Path(tempfile.mkdtemp(prefix="audit-selftest-"))
    try:
        # --- 1. 100 件連続書込 ---
        t1 = tmpdir / "chain100.jsonl"
        env = os.environ.copy()
        env["CLAUDE_BENGO_AUDIT_PATH"] = str(t1)
        env["CLAUDE_BENGO_SESSION_ID"] = "selftest-1"
        for i in range(100):
            rc = subprocess.call(
                [
                    sys.executable,
                    SELF_PATH,
                    "record",
                    "--skill",
                    "selftest",
                    "--event",
                    "file_read",
                    "--note",
                    f"seq-{i}",
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if rc != 0:
                add("1. 100 sequential writes", False, f"rc={rc} at iter {i}")
                break
        else:
            ok, fail, legacy, _ = _verify_file(t1)
            add(
                "1. 100 sequential writes",
                ok == 100 and fail == 0 and legacy == 0,
                f"ok={ok}, fail={fail}, legacy={legacy}",
            )

        # --- 2. 1 行改変検知 ---
        t2 = tmpdir / "tamper.jsonl"
        shutil.copy(t1, t2)
        with t2.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        # 50 行目の note を書き換える
        rec = json.loads(lines[50])
        rec["note"] = "TAMPERED"
        lines[50] = json.dumps(rec, ensure_ascii=False) + "\n"
        with t2.open("w", encoding="utf-8") as f:
            f.writelines(lines)
        _, fail, _, _ = _verify_file(t2)
        # 51 行目以降の prev_hash が全部ずれるはず
        add("2. detect single-line tampering", fail > 0, f"fail={fail}")

        # --- 3. 行削除検知 ---
        t3 = tmpdir / "delete.jsonl"
        shutil.copy(t1, t3)
        with t3.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        del lines[40]
        with t3.open("w", encoding="utf-8") as f:
            f.writelines(lines)
        _, fail, _, _ = _verify_file(t3)
        add("3. detect line deletion", fail > 0, f"fail={fail}")

        # --- 4. 行入替検知 ---
        t4 = tmpdir / "reorder.jsonl"
        shutil.copy(t1, t4)
        with t4.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        lines[10], lines[20] = lines[20], lines[10]
        with t4.open("w", encoding="utf-8") as f:
            f.writelines(lines)
        _, fail, _, _ = _verify_file(t4)
        add("4. detect line reordering", fail > 0, f"fail={fail}")

        # --- 5. /dev/null と NUL 指定 ---
        cwd_before = os.getcwd()
        cwd_sentinel = tmpdir / "sentinel"
        cwd_sentinel.mkdir()
        for target in ("/dev/null", "NUL", "nul"):
            env_s = env.copy()
            env_s["CLAUDE_BENGO_AUDIT_PATH"] = target
            rc = subprocess.call(
                [
                    sys.executable,
                    SELF_PATH,
                    "record",
                    "--skill",
                    "selftest",
                    "--event",
                    "file_read",
                    "--note",
                    f"devnull-{target}",
                ],
                env=env_s,
                cwd=str(cwd_sentinel),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            nul_file = cwd_sentinel / "NUL"
            nul_lower = cwd_sentinel / "nul"
            # Windows では `Path("NUL").exists()` が device として True を返し、
            # unlink も WinError 87 で失敗するため、regular file のみを検出する。
            def _is_real_file(p: Path) -> bool:
                try:
                    return p.is_file() and not p.is_symlink() and p.stat().st_size >= 0 and sys.platform != "win32"
                except OSError:
                    return False
            created_spurious = _is_real_file(nul_file) or _is_real_file(nul_lower)
            add(
                f"5. sentinel path '{target}' — no file created, rc=0",
                rc == 0 and not created_spurious,
                f"rc={rc}, spurious_file={created_spurious}",
            )
            # cleanup between iterations (Windows 予約名はスキップ)
            if sys.platform != "win32":
                for p in (nul_file, nul_lower):
                    if p.exists():
                        try:
                            p.unlink()
                        except OSError:
                            pass
        os.chdir(cwd_before)

        # --- 6. 並列書込 (10 プロセス × 10 回) ---
        t6 = tmpdir / "parallel.jsonl"
        env_p = env.copy()
        env_p["CLAUDE_BENGO_AUDIT_PATH"] = str(t6)
        procs = []
        for i in range(10):
            env_p_i = env_p.copy()
            env_p_i["CLAUDE_BENGO_SESSION_ID"] = f"par-{i}"
            # 各プロセスで 10 回書き込むワンライナー
            code = (
                "import subprocess, sys, os;\n"
                "for j in range(10):\n"
                "    subprocess.call([sys.executable, os.environ['AUDIT_PY'], 'record',\n"
                "                     '--skill','selftest','--event','file_read',\n"
                "                     '--note', f'par-{os.environ[\"CLAUDE_BENGO_SESSION_ID\"]}-{j}'])\n"
            )
            env_p_i["AUDIT_PY"] = __file__
            p = subprocess.Popen(
                [sys.executable, "-c", code],
                env=env_p_i,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            procs.append(p)
        for p in procs:
            p.wait()
        ok6, fail6, legacy6, _ = _verify_file(t6)
        total6 = ok6 + fail6 + legacy6
        add(
            "6. 10-process parallel writes (flock-serialized)",
            fail6 == 0 and total6 == 100,
            f"ok={ok6}, fail={fail6}, total={total6}",
        )

        # --- 7. ローテーション ---
        t7 = tmpdir / "rotate.jsonl"
        env_r = env.copy()
        env_r["CLAUDE_BENGO_AUDIT_PATH"] = str(t7)
        env_r["CLAUDE_BENGO_AUDIT_MAX_BYTES"] = "2048"  # 2 KB で発動
        env_r["CLAUDE_BENGO_SESSION_ID"] = "rotsess"
        for i in range(30):
            subprocess.call(
                [
                    sys.executable,
                    SELF_PATH,
                    "record",
                    "--skill",
                    "selftest",
                    "--event",
                    "file_read",
                    "--note",
                    f"rot-{i}-" + ("x" * 100),
                ],
                env=env_r,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        rotated_files = list(tmpdir.glob("rotate.jsonl.*"))
        # 新ログに rotation イベントが含まれるはず
        has_rotation_event = False
        if t7.exists():
            for ln in t7.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if r.get("event") == "rotation":
                    has_rotation_event = True
                    break
        add(
            "7. size-based rotation triggers",
            len(rotated_files) >= 1 and has_rotation_event,
            f"rotated_files={len(rotated_files)}, rotation_event={has_rotation_event}",
        )

        # --- 8. filename privacy default ---
        t8 = tmpdir / "privacy.jsonl"
        env_v = env.copy()
        env_v["CLAUDE_BENGO_AUDIT_PATH"] = str(t8)
        env_v["CLAUDE_BENGO_SESSION_ID"] = "privsess"
        sample = tmpdir / "山田太郎_戸籍.txt"
        sample.write_text("dummy", encoding="utf-8")
        # (a) デフォルト: filename が空、filename_sha256 が入る
        subprocess.call(
            [
                sys.executable,
                    SELF_PATH,
                "record",
                "--skill",
                "selftest",
                "--event",
                "file_read",
                "--file",
                str(sample),
            ],
            env=env_v,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # (b) --log-filename: filename に basename が入る
        subprocess.call(
            [
                sys.executable,
                    SELF_PATH,
                "record",
                "--skill",
                "selftest",
                "--event",
                "file_read",
                "--file",
                str(sample),
                "--log-filename",
            ],
            env=env_v,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        lines = [
            json.loads(l)
            for l in t8.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        expected_hash = _sha256_text("山田太郎_戸籍.txt")
        privacy_ok = (
            len(lines) == 2
            and lines[0]["filename"] == ""
            and lines[0]["filename_sha256"] == expected_hash
            and lines[1]["filename"] == "山田太郎_戸籍.txt"
            and lines[1]["filename_sha256"] == expected_hash
        )
        add(
            "8-9. filename privacy default + filename_sha256 always present",
            privacy_ok,
            f"default_fn='{lines[0].get('filename') if lines else '?'}', "
            f"optin_fn='{lines[1].get('filename') if len(lines) > 1 else '?'}'",
        )

        # --- 10-16. matter スコープ関連テスト ---
        # 事案スコープテスト用に CLAUDE_BENGO_ROOT を tmpdir 配下に固定する。
        # matter.py は CLAUDE_BENGO_ROOT を尊重するため、ホームディレクトリを汚さない。
        matter_root = tmpdir / "matter-root"
        env_m = {k: v for k, v in os.environ.items() if k != "CLAUDE_BENGO_AUDIT_PATH"}
        env_m["CLAUDE_BENGO_ROOT"] = str(matter_root)
        env_m["CLAUDE_BENGO_SESSION_ID"] = "matter-selftest"
        # matter.py の CLI で事案を作成する（同プロセスで作ると os.environ を変更する
        # 必要があるが、サブプロセスで実行すれば副作用を本プロセスに及ぼさない）。
        matter_py = str(Path(__file__).parent / "matter.py")
        alpha_id = "selftest-alpha"
        beta_id = "selftest-beta"
        for mid in (alpha_id, beta_id):
            subprocess.call(
                [sys.executable, matter_py, "create", mid, "--title", f"Test {mid}"],
                env=env_m,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        alpha_audit = matter_root / "matters" / alpha_id / "audit.jsonl"
        beta_audit = matter_root / "matters" / beta_id / "audit.jsonl"

        # --- 10. --matter で事案スコープへルーティング ---
        rc = subprocess.call(
            [
                sys.executable,
                    SELF_PATH,
                "record",
                "--matter",
                alpha_id,
                "--skill",
                "selftest",
                "--event",
                "file_read",
                "--note",
                "matter-routed",
            ],
            env=env_m,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        add(
            "10. --matter routes to matter-scoped path",
            rc == 0 and alpha_audit.exists() and alpha_audit.stat().st_size > 0,
            f"rc={rc}, exists={alpha_audit.exists()}",
        )

        # --- 11. 存在しない matter → exit 2 ---
        rc = subprocess.call(
            [
                sys.executable,
                    SELF_PATH,
                "record",
                "--matter",
                "nonexistent-matter",
                "--skill",
                "selftest",
                "--event",
                "file_read",
                "--note",
                "should-fail",
            ],
            env=env_m,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # 孤児ログが作られていないことも確認
        orphan = matter_root / "matters" / "nonexistent-matter" / "audit.jsonl"
        add(
            "11. nonexistent matter → exit 2 (no orphan log)",
            rc == 2 and not orphan.exists(),
            f"rc={rc}, orphan_exists={orphan.exists()}",
        )

        # --- 12. CLAUDE_BENGO_AUDIT_AUTO_MATTER=1 で自動解決 ---
        env_auto = dict(env_m)
        env_auto["CLAUDE_BENGO_AUDIT_AUTO_MATTER"] = "1"
        env_auto["MATTER_ID"] = alpha_id  # matter.resolve() が env から拾う
        # グローバルログが誤って作られないよう、一旦 AUDIT_PATH を削除する
        env_auto.pop("CLAUDE_BENGO_AUDIT_PATH", None)
        before_size = alpha_audit.stat().st_size if alpha_audit.exists() else 0
        rc = subprocess.call(
            [
                sys.executable,
                    SELF_PATH,
                "record",
                "--skill",
                "selftest",
                "--event",
                "file_read",
                "--note",
                "auto-routed",
            ],
            env=env_auto,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        after_size = alpha_audit.stat().st_size if alpha_audit.exists() else 0
        add(
            "12. AUTO_MATTER=1 auto-resolves matter",
            rc == 0 and after_size > before_size,
            f"rc={rc}, grew={after_size - before_size} bytes",
        )

        # --- 13. verify --matter ---
        # alpha に 20 レコード追加してチェーンを育てる
        for i in range(20):
            subprocess.call(
                [
                    sys.executable,
                    SELF_PATH,
                    "record",
                    "--matter",
                    alpha_id,
                    "--skill",
                    "selftest",
                    "--event",
                    "file_read",
                    "--note",
                    f"verify-{i}",
                ],
                env=env_m,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        proc = subprocess.run(
            [sys.executable, SELF_PATH, "verify", "--matter", alpha_id],
            env=env_m,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        add(
            "13. verify --matter on matter-scoped log",
            proc.returncode == 0 and b"fail=0" in proc.stdout,
            f"rc={proc.returncode}",
        )

        # --- 14. export --matter ---
        # beta にも1件書き込んで、export --matter alpha に beta の記録が混入しないことを確認
        subprocess.call(
            [
                sys.executable,
                    SELF_PATH,
                "record",
                "--matter",
                beta_id,
                "--skill",
                "selftest",
                "--event",
                "file_read",
                "--note",
                "beta-only",
            ],
            env=env_m,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc = subprocess.run(
            [sys.executable, SELF_PATH, "export", "--matter", alpha_id],
            env=env_m,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        export_ok = False
        if proc.returncode == 0:
            try:
                recs = json.loads(proc.stdout.decode("utf-8"))
                # どのレコードも note に "beta-only" を含まない
                export_ok = all(r.get("note") != "beta-only" for r in recs) and len(recs) >= 20
            except json.JSONDecodeError:
                export_ok = False
        add(
            "14. export --matter filters to that matter's log",
            export_ok,
            f"rc={proc.returncode}",
        )

        # --- 15. 異なる matter への並行書込が相互干渉しない ---
        # alpha と beta に同時に10回ずつ書込むプロセスを走らせる
        parallel_procs = []
        for target_mid in (alpha_id, beta_id):
            code = (
                "import subprocess, sys, os;\n"
                "for j in range(10):\n"
                "    subprocess.call([sys.executable, os.environ['AUDIT_PY'], 'record',\n"
                "                     '--matter', os.environ['TARGET_MID'],\n"
                "                     '--skill','selftest','--event','file_read',\n"
                "                     '--note', f'parmatter-{j}'])\n"
            )
            env_par = dict(env_m)
            env_par["AUDIT_PY"] = __file__
            env_par["TARGET_MID"] = target_mid
            env_par["CLAUDE_BENGO_SESSION_ID"] = f"par-{target_mid}"
            parallel_procs.append(
                subprocess.Popen(
                    [sys.executable, "-c", code],
                    env=env_par,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        for p in parallel_procs:
            p.wait()
        ok_a, fail_a, legacy_a, _ = _verify_file(alpha_audit)
        ok_b, fail_b, legacy_b, _ = _verify_file(beta_audit)
        add(
            "15. concurrent writes to different matters don't interfere",
            fail_a == 0 and fail_b == 0,
            f"alpha(ok={ok_a},fail={fail_a}), beta(ok={ok_b},fail={fail_b})",
        )

        # --- 16. verify --matter <id> --all（ローテート込み）---
        gamma_id = "selftest-gamma"
        subprocess.call(
            [sys.executable, matter_py, "create", gamma_id, "--title", "rot test"],
            env=env_m,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        gamma_audit = matter_root / "matters" / gamma_id / "audit.jsonl"
        env_rot_m = dict(env_m)
        env_rot_m["CLAUDE_BENGO_AUDIT_MAX_BYTES"] = "2048"
        env_rot_m["CLAUDE_BENGO_SESSION_ID"] = "rot-matter"
        for i in range(30):
            subprocess.call(
                [
                    sys.executable,
                    SELF_PATH,
                    "record",
                    "--matter",
                    gamma_id,
                    "--skill",
                    "selftest",
                    "--event",
                    "file_read",
                    "--note",
                    f"rot-{i}-" + ("x" * 100),
                ],
                env=env_rot_m,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        rotated_matter_files = list(gamma_audit.parent.glob("audit.jsonl.*"))
        # .lock を除外
        rotated_matter_files = [p for p in rotated_matter_files if not p.name.endswith(".lock")]
        proc = subprocess.run(
            [sys.executable, SELF_PATH, "verify", "--matter", gamma_id, "--all"],
            env=env_m,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        add(
            "16. verify --matter --all covers rotated matter logs",
            proc.returncode == 0
            and len(rotated_matter_files) >= 1
            and b"fail=0" in proc.stdout,
            f"rc={proc.returncode}, rotated={len(rotated_matter_files)}",
        )

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print()
    print(f"self-test: {passed}/{total} passed")
    return 0 if passed == total else 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="claude-bengo 監査ログ（ファイルのメタデータのみ記録、内容は記録しない）",
    )
    ap.add_argument("--self-test", action="store_true", help="組込セルフテストを実行する")
    sub = ap.add_subparsers(dest="command")

    # record
    p_rec = sub.add_parser("record", help="監査イベントを1件記録する")
    p_rec.add_argument(
        "--matter",
        help="事案（matter）ID を指定し、その事案の audit.jsonl へ記録する",
    )
    p_rec.add_argument("--skill", required=True, help="スキル名（例: typo-check）")
    p_rec.add_argument("--event", required=True, help=f"イベント種別 {sorted(VALID_EVENTS)}")
    p_rec.add_argument("--file", help="対象ファイルパス")
    p_rec.add_argument(
        "--log-filename",
        action="store_true",
        help="ファイル名を平文で記録する（既定は SHA-256 のみ）。依頼者識別情報を保存する場合の明示的オプトイン",
    )
    p_rec.add_argument(
        "--full-path",
        action="store_true",
        help="絶対パスを記録する（`--log-filename` と併用時のみ有効。既定は basename）",
    )
    p_rec.add_argument("--bytes", type=int, help="バイト数を明示指定（file が無い時用）")
    p_rec.add_argument("--sha256", help="SHA-256 を明示指定（file があれば自動計算）")
    p_rec.add_argument("--note", help="任意の短いメモ")
    p_rec.add_argument("--api-calls", type=int, default=0, help="API 呼び出し回数の増分")

    # export
    p_exp = sub.add_parser("export", help="監査ログをエクスポートする")
    p_exp.add_argument(
        "--matter",
        help="事案 ID を指定し、その事案のログのみをエクスポートする",
    )
    p_exp.add_argument("--since", help="この日付以降のみ（YYYY-MM-DD）")
    p_exp.add_argument("--skill", help="このスキルの記録のみ")
    p_exp.add_argument("--format", choices=["json", "csv"], default="json", help="出力形式")

    # ingest
    p_ing = sub.add_parser(
        "ingest",
        help="監査ログを claude-bengo-cloud にアップロードする",
    )
    p_ing.add_argument(
        "--matter",
        help="事案 ID を指定し、その事案のログのみ送信する。未指定時はグローバルログ。",
    )
    p_ing.add_argument(
        "--url",
        required=True,
        help="cloud エンドポイント URL（例: https://cloud.example.com/api/audit/ingest）",
    )
    p_ing.add_argument(
        "--token",
        help="Bearer token。未指定時は環境変数 CLAUDE_BENGO_CLOUD_TOKEN を使う。",
    )
    p_ing.add_argument(
        "--since",
        help="この日付以降のみ（YYYY-MM-DD）。未指定時は全件送信（冪等、重複は cloud 側でマージ）。",
    )
    p_ing.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="1 HTTP リクエストあたりのエントリ数（既定 500、cloud 側上限 10000）",
    )
    p_ing.add_argument(
        "--dry-run",
        action="store_true",
        help="送信せず、何件送る予定か stdout に出力する。",
    )

    # verify
    p_ver = sub.add_parser("verify", help="ハッシュチェーンの整合性を検証する")
    p_ver.add_argument(
        "--matter",
        help="事案 ID を指定し、その事案のログを検証する（--path 未指定時）",
    )
    p_ver.add_argument("--path", help="検証対象ファイル（--matter より優先）")
    p_ver.add_argument(
        "--all",
        action="store_true",
        help="アクティブログ＋同ディレクトリのローテート済みログを全て検証する",
    )

    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    if args.command == "record":
        return cmd_record(args)
    elif args.command == "export":
        return cmd_export(args)
    elif args.command == "verify":
        return cmd_verify(args)
    elif args.command == "ingest":
        return cmd_ingest(args)
    ap.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
