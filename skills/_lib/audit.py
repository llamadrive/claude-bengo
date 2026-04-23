#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude-bengo 監査ログ記録モジュール（v3.0.0 workspace-based 設計）。

日本の法律事務所が弁護士法第23条（秘密保持義務）および個人情報保護法
第25条（委託先監督義務）を遵守するために、本プラグインで処理した文書の
メタデータを追記専用ログとして記録する。

## v3.0.0 の主な変更

matter ID 概念を廃止。監査ログは**案件フォルダごと**に自動配置される:

```
~/cases/smith-v-jones/.claude-bengo/audit.jsonl
~/cases/tanaka-divorce/.claude-bengo/audit.jsonl
```

解決は `workspace.py` が行う（CWD から walk-up して `.claude-bengo/` を持つ
最初のディレクトリを workspace root とみなす）。案件フォルダの切替 =
`cd` するだけ。

## 記録する情報
- タイムスタンプ（ISO 8601 + monotonic_ns）
- セッション ID
- スキル名
- イベント種別（file_read / file_write / api_call / command_start / command_end / rotation / calc_run / calc_result）
- ファイル名ハッシュ（SHA-256、常時記録。依頼者氏名の秘匿のため）
- ファイル名そのもの（既定空文字。`--log-filename` で opt-in）
- バイト数
- ファイル内容の SHA-256
- ハッシュチェーン（`prev_hash`、改ざん検知用）
- 任意 HMAC（`CLAUDE_BENGO_AUDIT_HMAC_KEY` で opt-in）

## 記録しない情報
- ファイルの中身
- Claude API の入出力本文

## ログパスの解決優先順位（高い順）

1. `CLAUDE_BENGO_AUDIT_PATH` 環境変数（テスト・明示オーバーライド）
2. workspace の `config.json` で `audit_path` が設定されている場合
3. 既定: `<workspace>/.claude-bengo/audit.jsonl`（CWD から walk-up で解決）

workspace が未初期化の場合、機密スキル実行時に `workspace.ensure_workspace()`
が silently 初期化する（弁護士が matter 作成を意識する必要なし）。

## 完全無効化

`config.audit_enabled: false`（case-level、`/audit-config` で設定）または
`CLAUDE_BENGO_AUDIT_PATH=/dev/null` で audit を完全無効化できる。

## CLI 使用例

```
python3 skills/_lib/audit.py record --skill typo-check --event file_read --file "準備書面.docx"
python3 skills/_lib/audit.py record --skill typo-check --event file_read --file "準備書面.docx" --log-filename
python3 skills/_lib/audit.py export --since 2026-04-01 --format csv
python3 skills/_lib/audit.py verify --all
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


def _load_workspace_module():
    """workspace.py を遅延ロードする。"""
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


# 互換性: 旧呼び出し（skills の SKILL.md に残っている可能性）をエラーにしない
_load_matter_module = _load_workspace_module

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

    Windows の `NUL` デバイスと POSIX の `/dev/null` を安全に判定する。
    endswith の ad-hoc マッチ（例: `/home/user/my-nul` が誤マッチ）を避け、
    exact path 比較のみ行う。
    """
    s = str(p).replace("\\", "/")
    # exact match set（case sensitive for POSIX path, case insensitive for NUL）
    if s in {"/dev/null", "dev/null"}:
        return True
    if s.lower() in {"nul", "/nul", "./nul"}:
        return True
    return False


def _audit_path(matter_id: Optional[str] = None) -> Path:
    """監査ログファイルのパスを取得する（v3.0.0）。

    優先順位:
      1. 環境変数 `CLAUDE_BENGO_AUDIT_PATH`（明示オーバーライド・テスト用）
      2. workspace `.claude-bengo/config.json` の `audit_path`
      3. 既定: `<workspace>/.claude-bengo/audit.jsonl`

    workspace は CWD から walk-up で解決される。未初期化の場合は CWD を
    workspace root として扱う（呼出側が `ensure_workspace()` で初期化する）。

    `matter_id` 引数は v2.x 互換のため残しているが、v3.0.0 では無視される。

    F-010: CLAUDE_BENGO_AUDIT_PATH は安全なパスに限定する。`~/.claude-bengo/`
    配下、workspace 内、tmp ディレクトリ、またはセンチネル（/dev/null 相当）
    のみ許可。それ以外は `CLAUDE_BENGO_AUDIT_ALLOW_EXTERNAL_PATH=1` が必要。
    """
    override = os.environ.get("CLAUDE_BENGO_AUDIT_PATH")
    if override:
        p = Path(override).expanduser()
        if _is_sentinel(p):
            return p
        allow_external = os.environ.get("CLAUDE_BENGO_AUDIT_ALLOW_EXTERNAL_PATH") == "1"
        if allow_external:
            return p
        root_override = os.environ.get("CLAUDE_BENGO_ROOT")
        root = Path(root_override).expanduser() if root_override else (Path.home() / ".claude-bengo")
        import tempfile as _tempfile
        # workspace 内も許可（CWD walk-up で見つかれば）
        ws_mod = _load_workspace_module()
        ws_root = ws_mod.find_workspace_root() or Path.cwd()
        allowed_roots = [root, Path(_tempfile.gettempdir()), Path("/tmp"), Path("/var/folders"), Path("/var/tmp"), ws_root]
        try:
            parent = p.parent
            parent_abs = parent.resolve() if parent.exists() else parent.absolute()
            resolved_str = str(parent_abs / p.name)
            for ar in allowed_roots:
                if ar is None or (not ar.exists() and ar != root):
                    continue
                ar_abs = ar.resolve() if ar.exists() else ar.absolute()
                root_str = str(ar_abs).rstrip(os.sep) + os.sep
                if resolved_str == str(ar_abs) or resolved_str.startswith(root_str):
                    return p
        except (OSError, ValueError):
            pass
        raise ValueError(
            f"CLAUDE_BENGO_AUDIT_PATH={override} は安全なパス（workspace / ~/.claude-bengo/ / tmp）配下でもセンチネルでもない。"
            "外部パスへのリダイレクトは `CLAUDE_BENGO_AUDIT_ALLOW_EXTERNAL_PATH=1` を併用してほしい。"
        )

    # v3.0.0: workspace 解決
    try:
        ws_mod = _load_workspace_module()
        return ws_mod.audit_path()
    except Exception:
        # workspace.py ロード失敗時のフォールバック
        return DEFAULT_AUDIT_PATH


# v3.0.0 で matter 概念が廃止されたため、旧 _resolve_matter_for_write 関数は削除された。
# audit.py は workspace.py の walk-up 解決を使う（_audit_path 参照）。


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
    """セッション ID を取得する。環境変数優先、なければファイルキャッシュ。

    F-020: mtime 未来方向（rsync 等で持ち込まれた変な値）もキャッシュ無効と
    判定する。並行プロセスが同時に初期化しても、O_EXCL で先頭書込を優先し、
    他は読み戻すことで ID 分裂を防ぐ。
    """
    env_id = os.environ.get("CLAUDE_BENGO_SESSION_ID")
    if env_id:
        return env_id

    try:
        SESSION_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        if SESSION_ID_FILE.exists():
            mtime = SESSION_ID_FILE.stat().st_mtime
            now = time.time()
            age = now - mtime
            # 0 ≤ age < TTL のときのみ有効。負（未来 mtime）も invalid。
            if 0 <= age < SESSION_TTL_SECONDS:
                cached = SESSION_ID_FILE.read_text(encoding="utf-8").strip()
                if cached:
                    return cached
        # 新規生成（O_EXCL で race window を閉じる）
        sid = secrets.token_hex(16)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(str(SESSION_ID_FILE), flags, 0o600)
            try:
                os.write(fd, sid.encode("utf-8"))
            finally:
                os.close(fd)
        except FileExistsError:
            # 別プロセスが先に作成した — 読み戻す
            try:
                cached = SESSION_ID_FILE.read_text(encoding="utf-8").strip()
                if cached:
                    return cached
            except OSError:
                pass
            # 読み戻しも失敗 → メモリ内 ID を返す（監査は止めない）
            return sid
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


def _monotonic_ns() -> int:
    """プロセス起動からの単調増加ナノ秒。時計改竄・NTP 巻戻しに強い順序証拠として
    各レコードに埋め込む（民事訴訟法 231 条の電磁的記録の改竄証拠対応）。"""
    return time.monotonic_ns()


# 直前に書いたレコードの monotonic_ns を記憶し、非単調なジャンプを検知する
_LAST_MONOTONIC_NS: Optional[int] = None


def _hmac_key() -> Optional[bytes]:
    """HMAC 署名用の秘密鍵を取得する（v3.3.0〜 既定で有効）。

    優先順:
      1. `CLAUDE_BENGO_AUDIT_HMAC_KEY` 環境変数（テスト・明示オーバーライド）
      2. `~/.claude-bengo/global.json` の `audit_hmac_key_hex`
         （初回 `ensure_workspace()` で `secrets.token_hex(32)` により自動生成）

    **v3.3.0 以降、HMAC は既定で常に on。** これにより監査ログは tamper-proof
    （鍵が漏れない限り偽造不能）になる。以前は opt-in だったが、tier-2/3 firm
    で鍵セットアップは期待できないため既定を反転した。
    """
    k = os.environ.get("CLAUDE_BENGO_AUDIT_HMAC_KEY")
    if k:
        return k.encode("utf-8")
    try:
        ws = _load_workspace_module()
        key = ws.get_audit_hmac_key()
        if key:
            return key.encode("utf-8")
    except Exception:
        pass
    return None


def _compute_hmac(data: bytes, key: bytes) -> str:
    """HMAC-SHA256 を hex で返す。"""
    import hmac as _hmac
    return _hmac.new(key, data, hashlib.sha256).hexdigest()


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

    ファイル末尾から `tail_size` バイトずつ読み進め、末尾行全体が必ず含まれる
    まで拡張する。行が tail_size を超えている場合でも正しく返す（note に長文
    を積んだ場合の corner case 対応、F-019）。
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return None
    # 末尾行の境界（直前の改行）を見つかるまで読み範囲を拡張
    window = tail_size
    with path.open("rb") as f:
        while True:
            read = min(size, window)
            f.seek(size - read)
            chunk = f.read(read)
            chunk_stripped = chunk.rstrip(b"\n")
            if not chunk_stripped:
                return None
            nl = chunk_stripped.rfind(b"\n")
            if nl >= 0:
                return chunk_stripped[nl + 1:]
            # 読み範囲に改行が見つからない:
            # - ファイル全体を読み切った → それが 1 行目
            # - まだファイル冒頭に到達していない → window を倍にして再読込
            if read >= size:
                return chunk_stripped
            window *= 2


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

        # F-006: ロック取得失敗時は fail-closed にする。
        # 並行書込ではチェーン破綻が生じうるため、compliance 目的では黙って
        # unlocked 続行すべきでない。NFS / WSL1 / Docker volume 等の lockd 未対応
        # 環境で意図的に unlocked で使う場合は CLAUDE_BENGO_AUDIT_ALLOW_UNLOCKED=1
        # を設定する（運用者の明示オプトイン）。
        if self._mode is None and fallback_reason:
            if os.environ.get("CLAUDE_BENGO_AUDIT_ALLOW_UNLOCKED") == "1":
                # opt-in: 警告のみで続行
                if os.environ.get("CLAUDE_BENGO_AUDIT_SILENT_LOCK_FALLBACK") != "1":
                    print(
                        f"WARN: audit.py _FileLock fallback to unlocked mode ({fallback_reason}). "
                        "Concurrent writes may break the hash chain.",
                        file=sys.stderr,
                    )
            else:
                # 既定: fail-closed
                try:
                    if self._fh is not None:
                        self._fh.close()
                finally:
                    self._fh = None
                raise RuntimeError(
                    f"audit.py: ファイルロック取得失敗 ({fallback_reason}). "
                    "並行書込でハッシュチェーンが破綻しうるため中止した。"
                    "この環境で意図的にロックなし書込を許可するには "
                    "CLAUDE_BENGO_AUDIT_ALLOW_UNLOCKED=1 を設定してほしい。"
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
    """ファイルサイズが閾値を超えていればローテートする（F-007 atomicity 対応）。

    旧挙動: rename(active → rotated) → caller が new file に rotation record を書込。
    この 2 ステップの間でクラッシュすると new file は存在せず、次回起動時に
    ZERO_HASH から始まる fresh log が作られ、rotated sibling との連続性が
    検知できない（tamper indistinguishable）。

    F-007: staging ファイル経由で「rotation record の書込 → rename swap」を
    ほぼ 1 ステップにする:
      1. rotation record JSON line を `{path}.rotation-staging` に書く
      2. active → rotated にリネーム
      3. staging → active にリネーム
    これで crash 発生時にも少なくとも staging ファイルに rotation anchor が
    残り、次回起動時の recover で検知できる。加えて、active が先に消えている
    状態で fresh start しても、staging が優先される。

    戻り値: rotation record の JSON 文字列（呼び出し元は補助的に参照可能）、
    またはローテートしなかった場合の None。
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

    # rotation record を staging ファイルに事前書込（crash-safe 化）
    rotation_rec = _build_record(
        skill="_audit",
        event="rotation",
        filename="",
        filename_sha256="",
        bytes_=None,
        sha256="",
        api_calls=0,
        note=f"rotated from {rotated.name}",
        prev_hash=continuation_hash,
        rotated_from=rotated.name,
    )
    staging = path.with_name(path.name + ".rotation-staging")
    with open(staging, "w", encoding="utf-8") as sf:
        sf.write(json.dumps(rotation_rec, ensure_ascii=False) + "\n")
        try:
            sf.flush()
            os.fsync(sf.fileno())
        except (OSError, AttributeError, ValueError):
            pass
    try:
        os.chmod(staging, 0o600)
    except (OSError, NotImplementedError):
        pass

    # active → rotated
    os.rename(path, rotated)
    # staging → active（new ログは rotation record 1 行で開始）
    os.rename(staging, path)

    # 保持数を超える古いローテート済みログを削除（opt-in）
    keep = _keep_count()
    if keep is not None:
        _prune_rotations(path, keep)

    return json.dumps(
        {
            "prev_hash": continuation_hash,
            "rotated_from": rotated.name,
            "already_written": True,  # caller は rotation record を重複追記しない
        },
        ensure_ascii=False,
    )


def _recover_rotation_staging(path: Path) -> None:
    """起動時: クラッシュで中断された rotation の staging ファイルを復旧する。

    ケース:
      - staging 存在 + active 不在 → staging → active にリネームして復旧
      - staging 存在 + active 存在 → 中途半端な状態。staging を残すと次回
        rotation で上書きされるため削除して `{staging}.orphaned.{ts}` に退避。
    """
    staging = path.with_name(path.name + ".rotation-staging")
    if not staging.exists():
        return
    if not path.exists():
        # クリーンリカバリ: staging を active に昇格
        try:
            os.rename(staging, path)
            print(
                f"INFO: audit.py recovered rotation staging {staging.name} → {path.name}",
                file=sys.stderr,
            )
        except OSError as e:
            print(
                f"WARN: audit.py rotation staging recovery failed: {e}",
                file=sys.stderr,
            )
    else:
        ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        orphan = staging.with_name(staging.name + f".orphaned.{ts}")
        try:
            os.rename(staging, orphan)
            print(
                f"WARN: audit.py orphaned rotation staging (active file exists) → {orphan.name}",
                file=sys.stderr,
            )
        except OSError:
            pass


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

    F-018/F-019: `monotonic_ns` を全レコードに付与する（時計改竄耐性）。
    前回書いた値より小さい値を観測したら `clock_anomaly` イベントを note に
    書き残す（レコード自体は破棄しない — 監査証跡として残す）。
    opt-in HMAC (`CLAUDE_BENGO_AUDIT_HMAC_KEY`) が設定されていれば hmac フィールドを付加。
    """
    global _LAST_MONOTONIC_NS
    mono_ns = _monotonic_ns()
    clock_note_suffix = ""
    if _LAST_MONOTONIC_NS is not None and mono_ns < _LAST_MONOTONIC_NS:
        # 単調減少 = プロセス再起動しない限りありえない。ただし fork 等で
        # 複数プロセスが独立に monotonic 計時する場合は観測される。
        # ここでは警告として note に追記する（プロセス境界で reset される想定）。
        clock_note_suffix = (
            f" [clock_anomaly: monotonic_ns {mono_ns} < previous {_LAST_MONOTONIC_NS}]"
        )
    _LAST_MONOTONIC_NS = mono_ns

    rec: dict = {
        "ts": _iso_now(),
        "monotonic_ns": mono_ns,
        "session_id": _get_session_id(),
        "skill": skill,
        "event": event,
        "filename": filename,
        "filename_sha256": filename_sha256,
        "bytes": bytes_,
        "sha256": sha256,
        "api_calls": api_calls,
        "note": (note or "") + clock_note_suffix,
        "prev_hash": prev_hash,
    }
    if rotated_from is not None:
        rec["rotated_from"] = rotated_from

    # HMAC: 鍵があれば hmac フィールドを最後に付加。
    #
    # v3.3.1 注記: HMAC は **プラグインローカルの改ざん検出** 用。鍵は
    # `~/.claude-bengo/global.json` の `audit_hmac_key_hex` に保管され、
    # `audit.py verify` が読み直したときに整合を確認する。盗まれた端末上で
    # audit.jsonl を編集された場合の検知に有効。
    #
    # **クラウド側の整合性は HMAC には依存しない。** `this_hash = sha256(raw_line)`
    # を `audit.py ingest` が送り、cloud `/api/audit/ingest` が raw_line から
    # sha256 を再計算してチェーン整合を強制する（v3.3.1 P1）。HMAC 鍵はクラウドに
    # 共有されていないため、cloud は HMAC を検証しない。したがって HMAC は
    # end-to-end 保証ではなく、ローカル盗難時の検証用途のみ。
    key = _hmac_key()
    if key:
        line_without_hmac = json.dumps(rec, ensure_ascii=False)
        rec["hmac"] = _compute_hmac(line_without_hmac.encode("utf-8"), key)
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

    # v3.0.0: workspace resolution.
    # v3.3.0: 監査無効化は **本番では禁じる**。`config.audit_enabled=false` を
    # 尊重するのは `CLAUDE_BENGO_ALLOW_DISABLE_AUDIT=1` が環境変数に設定されて
    # いる時のみ（テスト・デバッグ用途）。それ以外では警告を出して強制的に
    # 記録を続行する。これにより事務所運用中の「とりあえず audit off」ができない。
    ws_mod = _load_workspace_module()
    cfg = ws_mod.load_config()
    disabled_by_cfg = str(cfg.get("audit_enabled", "true")).lower() in ("false", "0", "no")
    allow_disable = os.environ.get("CLAUDE_BENGO_ALLOW_DISABLE_AUDIT") == "1"
    if disabled_by_cfg:
        if allow_disable:
            print(
                json.dumps(
                    {"info": "audit disabled by config.audit_enabled=false (ALLOW_DISABLE_AUDIT=1)"},
                    ensure_ascii=False,
                )
            )
            return 0
        # 本番では尊重しない。stderr に警告を出して続行する。
        print(
            json.dumps(
                {
                    "warning": "audit_enabled=false は本番では尊重しない。"
                    "テスト環境では CLAUDE_BENGO_ALLOW_DISABLE_AUDIT=1 を併設してほしい。"
                    "このイベントは通常どおり記録を続行する。"
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

    path = _audit_path()

    # センチネル（/dev/null 相当）の本番扱い（v3.3.0-iter1〜）:
    # 以前は無条件に短絡して成功扱いだった。これは
    # `CLAUDE_BENGO_AUDIT_PATH=/dev/null` による audit 完全バイパスを許し、
    # 弁護士事務所の compliance 観点で重大な穴だった。
    # 現在は `CLAUDE_BENGO_ALLOW_DISABLE_AUDIT=1` が併設されている場合のみ
    # sentinel を尊重する（テスト・デバッグ専用）。本番ではワークスペース既定
    # パスに差し戻す。
    if _is_sentinel(path):
        if allow_disable:
            print(json.dumps({"info": f"audit disabled (path={path})"}, ensure_ascii=False))
            return 0
        # 警告を出して既定パスにフォールバック
        print(
            json.dumps(
                {
                    "warning": f"CLAUDE_BENGO_AUDIT_PATH={path} は本番では無視する。"
                    "既定の workspace 内パスに記録を続行する。テスト用途であれば "
                    "CLAUDE_BENGO_ALLOW_DISABLE_AUDIT=1 を併設してほしい。"
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        # 環境変数を一時的に剥がして既定に差し戻す（同一プロセス内のこのコマンドのみ）
        os.environ.pop("CLAUDE_BENGO_AUDIT_PATH", None)
        path = _audit_path()

    # workspace 未初期化ならこの時点で silently 作る（既に CWD が workspace
    # でなければ walk-up で見つからない → CWD に新規作成）
    if not ws_mod.is_initialized():
        ws_mod.ensure_workspace()

    filename_plain = ""
    filename_hash = ""
    bytes_ = None
    sha = args.sha256

    if args.file:
        p = Path(args.file)
        base = p.name
        filename_hash = _sha256_text(base)

        # `--log-filename` / `--full-path` は workspace config で制御する
        # （v2.x の matter metadata policy を workspace config に移行）。
        # ただし CLAUDE_BENGO_AUDIT_PATH が明示設定されている場合は policy をバイパス
        # する（ユーザーがパスを明示管理しているため、ファイル名ロギングも自己責任）。
        want_log_fn = bool(args.log_filename)
        want_full_path = bool(args.full_path)
        explicit_path_override = bool(os.environ.get("CLAUDE_BENGO_AUDIT_PATH"))
        if want_log_fn and not explicit_path_override:
            policy_log = str(cfg.get("log_filenames", "false")).lower() in ("true", "1", "yes")
            policy_full = str(cfg.get("log_full_path", "false")).lower() in ("true", "1", "yes")
            if not policy_log:
                print(
                    json.dumps(
                        {
                            "error": (
                                "平文ファイル名のログ記録が workspace config で許可されていない。"
                                "`/audit-config` で `log_filenames: true` を設定してから再試行してほしい。"
                            )
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
                return 2
            if want_full_path and not policy_full:
                print(
                    json.dumps(
                        {
                            "error": (
                                "フルパス記録が workspace config で許可されていない。"
                                "`/audit-config` で `log_full_path: true` を設定してから再試行してほしい。"
                            )
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
                return 2
        if want_log_fn:
            filename_plain = str(p) if want_full_path else base
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
            # F-007: クラッシュ中断された rotation staging の復旧（冪等）
            _recover_rotation_staging(path)

            # ローテーション（必要なら）。F-007 対応後は rotation record が
            # staging 経由で新 active に書込済みのため、ここでは追加書込しない。
            _rotate_if_needed(path)

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
    except RuntimeError as e:
        # F-006: flock 取得失敗などの fail-closed 条件
        print(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
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
    # v3.0.0: workspace resolution
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

    # F-009: 破損行を sum する（export でも verify と同じ扱いにする）
    records = []
    malformed_count = 0
    allow_corruption = getattr(args, "allow_corruption", False)
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    malformed_count += 1
                    continue  # 破損行は後でまとめて警告
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

    if malformed_count > 0 and not allow_corruption:
        print(
            json.dumps(
                {
                    "error": (
                        f"監査ログに {malformed_count} 件の破損行を検出した。export を中止。"
                        "verify で整合を取ってから再実行してほしい。"
                        "緊急時は --allow-corruption で破損行をスキップして出力可能（非推奨）。"
                    )
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 3
    if malformed_count > 0 and allow_corruption:
        print(
            f"WARN: {malformed_count} 件の破損行をスキップして export する (--allow-corruption)",
            file=sys.stderr,
        )

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

    # v3.0.0: workspace resolution
    path = _audit_path()
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

    # F-009: 読取対象には rotated sibling も含める。過去期間の ingest で
    # rotated sibling が抜けるとクラウド側でチェーン再構築不能。
    ingest_paths: List[Path] = []
    ingest_paths.extend(_discover_rotated_siblings(path))
    ingest_paths.append(path)

    # F-009: 不正行を厳格に扱う。verify/export/ingest で挙動が分かれていた
    # 旧実装では、malformed 行を export/ingest が silently skip する一方
    # verify が FAIL するというギャップが、攻撃者による証拠隠蔽を助けた。
    # 既定で malformed 行を検知したら拒否する。運用上どうしても先に進めたい
    # 場合は --allow-corruption で opt-in する。
    entries: List[dict] = []
    malformed: List[Tuple[str, int, str]] = []  # (file, lineno, raw)
    allow_corruption = getattr(args, "allow_corruption", False)
    for p in ingest_paths:
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8") as f:
            for lineno, raw_line in enumerate(f, start=1):
                stripped = raw_line.rstrip("\n")
                if not stripped.strip():
                    continue
                try:
                    rec = json.loads(stripped)
                except json.JSONDecodeError:
                    malformed.append((str(p), lineno, stripped[:120]))
                    continue
                if since is not None:
                    ts = rec.get("ts", "")
                    try:
                        rec_date = _dt.date.fromisoformat(ts[:10])
                        if rec_date < since:
                            continue
                    except Exception:
                        pass
                # F-008: 送信先（クラウド）がハッシュチェーンを再構成できるよう、
                # 元の行バイト列（JSON re-serialization quirks に独立）を raw_line
                # として添付する。this_hash = sha256(raw_line) である。
                rec["raw_line"] = stripped
                rec["this_hash"] = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
                entries.append(rec)

    if malformed and not allow_corruption:
        print(
            json.dumps(
                {
                    "error": (
                        f"監査ログに {len(malformed)} 件の破損行を検出した。ingest を中止。"
                        "冪等性を保証するため、破損行は verify で整合を取ってから再度 ingest してほしい。"
                        "緊急時は --allow-corruption で破損行をスキップして送信可能（非推奨）。"
                    ),
                    "malformed_samples": [
                        {"file": f, "line": ln, "preview": prev}
                        for (f, ln, prev) in malformed[:5]
                    ],
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 3
    if malformed and allow_corruption:
        print(
            f"WARN: {len(malformed)} 件の破損行をスキップして送信する (--allow-corruption)",
            file=sys.stderr,
        )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "would_send": len(entries),
                    "source": str(path),
                    "url": args.url,
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

    # v3.3.1: HTTPS-only guard. Bearer token must never be sent over plain HTTP.
    # Exception: localhost for development, or explicit CLAUDE_BENGO_ALLOW_PLAINTEXT_INGEST=1.
    from urllib.parse import urlparse
    parsed_url = urlparse(args.url)
    allow_plaintext = os.environ.get("CLAUDE_BENGO_ALLOW_PLAINTEXT_INGEST") == "1"
    is_localhost = parsed_url.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed_url.scheme != "https" and not is_localhost and not allow_plaintext:
        print(
            json.dumps(
                {
                    "error": (
                        f"ingest URL は HTTPS である必要がある（bearer token を暗号化なしで送信できない）。"
                        f"指定されたスキーム: {parsed_url.scheme!r}。"
                        f"開発用途で localhost 以外の http を使う場合は "
                        f"CLAUDE_BENGO_ALLOW_PLAINTEXT_INGEST=1 を設定する。"
                    )
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

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
    # v3.0.0: workspace resolution. --path は引き続き任意ファイル検証用。
    if args.path:
        path = Path(args.path)
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

        # --- 10-14. workspace スコープ関連テスト（v3.0.0） ---
        # workspace.py を使って `.claude-bengo/` を案件フォルダに自動配置する。
        workspace_root_a = tmpdir / "cases" / "case-alpha"
        workspace_root_b = tmpdir / "cases" / "case-beta"
        workspace_root_a.mkdir(parents=True)
        workspace_root_b.mkdir(parents=True)

        env_w = {k: v for k, v in os.environ.items() if k != "CLAUDE_BENGO_AUDIT_PATH"}
        env_w["CLAUDE_BENGO_SESSION_ID"] = "workspace-selftest"

        # 10. CWD=case-alpha で record → alpha の audit.jsonl に書かれる
        rc = subprocess.call(
            [
                sys.executable, SELF_PATH, "record",
                "--skill", "selftest", "--event", "file_read", "--note", "workspace-a",
            ],
            env=env_w,
            cwd=str(workspace_root_a),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        alpha_ws_audit = workspace_root_a / ".claude-bengo" / "audit.jsonl"
        add(
            "10. CWD=case-alpha record creates .claude-bengo/audit.jsonl there",
            rc == 0 and alpha_ws_audit.exists() and alpha_ws_audit.stat().st_size > 0,
            f"rc={rc}, exists={alpha_ws_audit.exists()}",
        )

        # 11. 別 CWD (case-beta) で record → beta の audit.jsonl に書かれる
        rc = subprocess.call(
            [
                sys.executable, SELF_PATH, "record",
                "--skill", "selftest", "--event", "file_read", "--note", "workspace-b",
            ],
            env=env_w,
            cwd=str(workspace_root_b),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        beta_ws_audit = workspace_root_b / ".claude-bengo" / "audit.jsonl"
        add(
            "11. CWD=case-beta record routes to separate audit.jsonl",
            rc == 0 and beta_ws_audit.exists() and beta_ws_audit.stat().st_size > 0,
            f"rc={rc}, exists={beta_ws_audit.exists()}",
        )

        # 12. walk-up: CWD=case-alpha/nested/deep → alpha の audit に書かれる
        nested = workspace_root_a / "nested" / "deep"
        nested.mkdir(parents=True)
        before = alpha_ws_audit.stat().st_size
        rc = subprocess.call(
            [
                sys.executable, SELF_PATH, "record",
                "--skill", "selftest", "--event", "file_read", "--note", "from-nested",
            ],
            env=env_w,
            cwd=str(nested),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        after = alpha_ws_audit.stat().st_size
        add(
            "12. walk-up finds parent workspace from nested dir",
            rc == 0 and after > before,
            f"rc={rc}, grew={after - before} bytes",
        )

        # 13. verify in alpha workspace
        # 20 レコード追加してチェーンを育てる
        for i in range(10):
            subprocess.call(
                [
                    sys.executable, SELF_PATH, "record",
                    "--skill", "selftest", "--event", "file_read", "--note", f"v-{i}",
                ],
                env=env_w,
                cwd=str(workspace_root_a),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        proc = subprocess.run(
            [sys.executable, SELF_PATH, "verify"],
            env=env_w,
            cwd=str(workspace_root_a),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        add(
            "13. verify on workspace audit chain",
            proc.returncode == 0 and b"fail=0" in proc.stdout,
            f"rc={proc.returncode}",
        )

        # 14. audit_enabled=false は本番では尊重されない（v3.3.0〜）
        # ALLOW_DISABLE_AUDIT=1 を併設した場合のみ無効化される
        cfg_path = workspace_root_a / ".claude-bengo" / "config.json"
        cfg_path.write_text(json.dumps({"audit_enabled": False}), encoding="utf-8")

        # (a) 既定動作: 無効化無視、記録は継続
        before_a = alpha_ws_audit.stat().st_size
        rc_a = subprocess.call(
            [
                sys.executable, SELF_PATH, "record",
                "--skill", "selftest", "--event", "file_read", "--note", "should-still-log",
            ],
            env=env_w,
            cwd=str(workspace_root_a),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        after_a = alpha_ws_audit.stat().st_size
        add(
            "14a. audit_enabled=false ignored in production (record continues)",
            rc_a == 0 and after_a > before_a,
            f"grew={after_a - before_a}",
        )

        # (b) ALLOW_DISABLE_AUDIT=1 の時だけ無効化される（テスト用）
        env_disable = dict(env_w, CLAUDE_BENGO_ALLOW_DISABLE_AUDIT="1")
        before_b = alpha_ws_audit.stat().st_size
        rc_b = subprocess.call(
            [
                sys.executable, SELF_PATH, "record",
                "--skill", "selftest", "--event", "file_read", "--note", "should-skip",
            ],
            env=env_disable,
            cwd=str(workspace_root_a),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        after_b = alpha_ws_audit.stat().st_size
        add(
            "14b. ALLOW_DISABLE_AUDIT=1 honors audit_enabled=false",
            rc_b == 0 and after_b == before_b,
            f"grew={after_b - before_b}",
        )
        cfg_path.unlink()  # clean up for subsequent tests

        # 15. sentinel /dev/null is NOT honored in production (v3.3.0-iter1)
        # CLAUDE_BENGO_AUDIT_PATH=/dev/null without ALLOW_DISABLE_AUDIT should
        # fall back to workspace default and still record.
        env_sent_prod = dict(env_w, CLAUDE_BENGO_AUDIT_PATH="/dev/null")
        before_s = alpha_ws_audit.stat().st_size
        rc_s = subprocess.call(
            [
                sys.executable, SELF_PATH, "record",
                "--skill", "selftest", "--event", "file_read", "--note", "sentinel-prod",
            ],
            env=env_sent_prod,
            cwd=str(workspace_root_a),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        after_s = alpha_ws_audit.stat().st_size
        add(
            "15. sentinel /dev/null IGNORED in production (record continues)",
            rc_s == 0 and after_s > before_s,
            f"grew={after_s - before_s}",
        )

        # 16. sentinel IS honored when ALLOW_DISABLE_AUDIT=1 (test mode)
        env_sent_test = dict(env_w, CLAUDE_BENGO_AUDIT_PATH="/dev/null", CLAUDE_BENGO_ALLOW_DISABLE_AUDIT="1")
        before_t = alpha_ws_audit.stat().st_size
        rc_t = subprocess.call(
            [
                sys.executable, SELF_PATH, "record",
                "--skill", "selftest", "--event", "file_read", "--note", "sentinel-test",
            ],
            env=env_sent_test,
            cwd=str(workspace_root_a),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        after_t = alpha_ws_audit.stat().st_size
        add(
            "16. sentinel /dev/null honored when ALLOW_DISABLE_AUDIT=1",
            rc_t == 0 and after_t == before_t,
            f"grew={after_t - before_t}",
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
    p_exp.add_argument("--since", help="この日付以降のみ（YYYY-MM-DD）")
    p_exp.add_argument("--skill", help="このスキルの記録のみ")
    p_exp.add_argument("--format", choices=["json", "csv"], default="json", help="出力形式")
    p_exp.add_argument(
        "--allow-corruption",
        action="store_true",
        help="破損行を silently skip する（非推奨・緊急運用時のみ）",
    )

    # ingest
    p_ing = sub.add_parser(
        "ingest",
        help="監査ログを claude-bengo-cloud にアップロードする",
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
    p_ing.add_argument(
        "--allow-corruption",
        action="store_true",
        help="破損行を silently skip する（非推奨・緊急運用時のみ）",
    )

    # verify
    p_ver = sub.add_parser("verify", help="ハッシュチェーンの整合性を検証する")
    p_ver.add_argument("--path", help="検証対象ファイル（workspace より優先）")
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
