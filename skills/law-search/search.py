#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e-Gov 法令 API クライアント。

本スクリプトは Claude Code プラグイン claude-bengo の law-search スキルから
呼び出される補助ツールである。シェル経由で文字列を展開すると注入攻撃の
原因になるため、すべての引数は argparse で Python の値として受け取る。

サブコマンド:
  fetch-article   条番号を指定して単一条文の XML を取得する。
  search-keyword  法令全文 XML をダウンロードし条見出しをキーワード検索する。
  clear-cache     ユーザー固有キャッシュの XML を削除する。
  self-test       オフライン自己診断（キャッシュの完全性・権限等）を実行する。

キャッシュはユーザーのホーム配下（`~/.claude-bengo/cache/law-search/`）に
24 時間保存する。共有 /tmp を避け、各キャッシュエントリに SHA-256 の
サイドカーを併置することで改ざん（キャッシュポイズニング）を検出する。
`CLAUDE_BENGO_CACHE_PATH` 環境変数でキャッシュルートを上書きできる。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# ------------------------------------------------------------------------------
# 定数
# ------------------------------------------------------------------------------

# NIT: バージョンは plugin.json から動的に読み込む。ハードコード回避。
def _plugin_version() -> str:
    try:
        plugin_root = Path(__file__).resolve().parent.parent.parent
        manifest = plugin_root / ".claude-plugin" / "plugin.json"
        if manifest.exists():
            import json as _json
            data = _json.loads(manifest.read_text(encoding="utf-8"))
            return data.get("version", "unknown")
    except Exception:
        pass
    return "unknown"


USER_AGENT = f"claude-bengo/{_plugin_version()} (+https://github.com/llamadrive/claude-bengo)"
REQUEST_TIMEOUT = 30  # 秒
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 時間
LEGACY_CACHE_SUBDIR = "claude-bengo"  # 旧キャッシュ（共有 tmp 下）— 参照しない
CACHE_ENV_VAR = "CLAUDE_BENGO_CACHE_PATH"
MAX_RETRIES = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
RETRY_BASE_DELAY = 1.0  # 秒
RETRY_MAX_DELAY = 8.0  # 秒
KEYWORD_MAX_LEN = 50
SIDECAR_SUFFIX = ".sha256"

LAW_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{1,20}$")
ARTICLE_NUM_PATTERN = re.compile(r"^[0-9]+(_[0-9]+)*$")

# F-033: law-id-list.tsv freshness check
LAW_ID_LIST_PATH = Path(__file__).resolve().parent / "references" / "law-id-list.tsv"
LAW_ID_LIST_STALE_DAYS = 180
LAW_ID_LIST_REFUSE_DAYS = 365
_LAW_ID_LIST_WARNED = False


def _check_law_id_list_freshness() -> Optional[Tuple[int, str]]:
    """`law-id-list.tsv` の生成日付を読み、古ければ (age_days, ISO date) を返す。

    `# Generated: YYYY-MM-DD` 先頭行を探す。見つからなければ None。
    """
    if not LAW_ID_LIST_PATH.exists():
        return None
    try:
        import datetime as _dt
        with LAW_ID_LIST_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^#\s*Generated:\s*(\d{4}-\d{2}-\d{2})", line.strip())
                if m:
                    gen_date = _dt.date.fromisoformat(m.group(1))
                    age = (_dt.date.today() - gen_date).days
                    return (age, m.group(1))
                # ヘッダー行を数行超えたら打ち切り
                if not line.startswith("#"):
                    break
    except (OSError, ValueError):
        return None
    return None


def _warn_if_stale() -> None:
    """起動時（fetch-article 等の前）に stale 判定して stderr 警告する。"""
    global _LAW_ID_LIST_WARNED
    if _LAW_ID_LIST_WARNED:
        return
    info = _check_law_id_list_freshness()
    if info is None:
        return
    age, gen_date = info
    if age >= LAW_ID_LIST_REFUSE_DAYS:
        _LAW_ID_LIST_WARNED = True
        raise SystemExit(
            f"ERROR: law-id-list.tsv が {age} 日経過（{gen_date} 生成）。"
            f"{LAW_ID_LIST_REFUSE_DAYS} 日を超えると法令 ID がリネーム／削除されている"
            "可能性が高く、誤った条文引用のリスクがある。`CLAUDE_BENGO_ALLOW_STALE_LAW_LIST=1` で"
            "強制続行できるが、最新 e-Gov API で law-id-list.tsv を再生成することを強く推奨する。"
        )
    if age >= LAW_ID_LIST_STALE_DAYS:
        _LAW_ID_LIST_WARNED = True
        print(
            f"WARN: law-id-list.tsv は {age} 日経過（{gen_date} 生成）。最新法令との乖離可能性あり。"
            "定期的な再生成を推奨する。",
            file=sys.stderr,
        )

EGOV_ARTICLE_URL = "https://laws.e-gov.go.jp/api/1/articles;lawId={law_id};article={article};"
EGOV_LAWDATA_URL = "https://laws.e-gov.go.jp/api/1/lawdata/{law_id}"

# 終了コード
EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_NETWORK = 2
EXIT_PARSE = 3

# 旧キャッシュの注意喚起は 1 プロセス内で 1 回だけ表示する
_LEGACY_NOTICE_EMITTED = False


# ------------------------------------------------------------------------------
# キャッシュ基盤
# ------------------------------------------------------------------------------


def cache_dir() -> Path:
    """ユーザー固有キャッシュディレクトリを返す。必要なら作成する。

    `CLAUDE_BENGO_CACHE_PATH` が設定されていればそれを採用する。既定は
    `~/.claude-bengo/cache/law-search/` であり、POSIX では 0o700 で作成する。
    """
    override = os.environ.get(CACHE_ENV_VAR)
    if override:
        base = Path(override).expanduser()
    else:
        base = Path.home() / ".claude-bengo" / "cache" / "law-search"

    # 親ディレクトリを含め 0o700 で作成する（POSIX のみ有効）。
    # Windows では NTFS ACL のユーザープロファイル既定（所有者アクセス）に従う。
    base.mkdir(parents=True, exist_ok=True)
    _ensure_owner_only(base)

    _maybe_emit_legacy_notice()
    return base


def _ensure_owner_only(path: Path) -> None:
    """POSIX 上でディレクトリ権限を 0o700 に揃える。失敗は致命的としない。"""
    if os.name != "posix":
        return
    try:
        current = stat.S_IMODE(path.stat().st_mode)
        if current != 0o700:
            os.chmod(path, 0o700)
    except OSError:
        # 権限変更に失敗してもキャッシュ機能は継続する。
        pass


def _maybe_emit_legacy_notice() -> None:
    """旧キャッシュ（共有 tmp）が残っていれば一度だけ注意喚起する。

    仕様により旧キャッシュは信頼せず、そのまま無視する。削除もしない
    （他ユーザーの所有物の可能性がある）。
    """
    global _LEGACY_NOTICE_EMITTED
    if _LEGACY_NOTICE_EMITTED:
        return
    legacy = Path(tempfile.gettempdir()) / LEGACY_CACHE_SUBDIR
    if legacy.exists():
        sys.stderr.write(
            "# 旧キャッシュ（共有 tmp）は使用せず、新キャッシュを構築する。\n"
        )
    _LEGACY_NOTICE_EMITTED = True


def cache_path_article(law_id: str, article_num: str) -> Path:
    """単一条文 XML のキャッシュパスを返す。"""
    return cache_dir() / f"article_{law_id}_{article_num}.xml"


def cache_path_law(law_id: str) -> Path:
    """法令全文 XML のキャッシュパスを返す。"""
    return cache_dir() / f"law_{law_id}.xml"


def sidecar_path(xml_path: Path) -> Path:
    """XML キャッシュに対応するサイドカーのパスを返す。"""
    return xml_path.with_name(xml_path.name + SIDECAR_SUFFIX)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _unlink_quiet(path: Path) -> None:
    """存在すれば削除し、ENOENT は無視する。"""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        # 他のエラーも致命的ではないため継続する。
        pass


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """一時ファイルに書き込み、`os.replace` で原子的にリネームする。

    プロセス中断や並行プロセスによる読み取りの最中に、部分的な内容が
    読まれる TOCTOU レースを防ぐ。
    """
    tmp = path.with_name(path.name + ".tmp")
    # 既存の .tmp（前回異常終了の残骸）は上書きしてよい。
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def _build_sidecar_line(digest: str, url: str, fetched_at: str) -> bytes:
    """サイドカーの 1 行を構築する（`<hex>  <url>  <iso8601>`）。"""
    return f"{digest}  {url}  {fetched_at}\n".encode("utf-8")


def _parse_sidecar(path: Path) -> Optional[str]:
    """サイドカーから期待 SHA-256 を取り出す。読めなければ None。"""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    # 形式: "<hex>  <url>  <iso8601>"。先頭トークンを期待ハッシュとして採用する。
    head = raw.split(None, 1)[0]
    if re.fullmatch(r"[0-9a-fA-F]{64}", head):
        return head.lower()
    return None


def _write_cache_atomic(path: Path, content_bytes: bytes, url: str) -> None:
    """XML 本体とサイドカーを一対で原子的に書き込む。

    順序:
      1. `path.tmp` / `sidecar.tmp` に書き込む。
      2. 本体を先に `os.replace`（XML 本体が必ず先に確定する）。
      3. サイドカーを最後に `os.replace`（サイドカーの存在 == 本体も確定済み）。
    これにより「サイドカーが見える = 本体も見える」という不変条件が成立し、
    読み手は常にサイドカー起点で検証できる。
    """
    digest = _sha256_bytes(content_bytes)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    side = sidecar_path(path)
    sidecar_bytes = _build_sidecar_line(digest, url, fetched_at)

    # 古い対はまず削除する（中途半端な状態を避ける）。
    _unlink_quiet(side)

    # 1. 本体を書き込む（tmp → rename）。
    _atomic_write_bytes(path, content_bytes)
    # 2. サイドカーを書き込む（tmp → rename）。最後にリネームする。
    _atomic_write_bytes(side, sidecar_bytes)


def _read_verified_cache(path: Path) -> Optional[bytes]:
    """キャッシュ本体とサイドカーを検証したうえで内容を返す。

    不整合があれば両ファイルを削除し None を返す（＝キャッシュミス扱い）。
    """
    if not path.exists():
        return None
    side = sidecar_path(path)
    if not side.exists():
        # 旧形式（サイドカー無し）。改ざん検出不能のため信頼せず破棄する。
        _unlink_quiet(path)
        return None

    expected = _parse_sidecar(side)
    if expected is None:
        _unlink_quiet(path)
        _unlink_quiet(side)
        return None

    try:
        actual_digest = _sha256_file(path)
        data = path.read_bytes()
    except OSError:
        _unlink_quiet(path)
        _unlink_quiet(side)
        return None

    if actual_digest != expected:
        # 改ざんまたは破損。両ファイルを破棄する。
        _unlink_quiet(path)
        _unlink_quiet(side)
        return None

    return data


def is_cache_fresh(path: Path) -> bool:
    """キャッシュ本体が TTL 以内に更新されていれば True を返す。

    TTL 判定は本体の mtime を用いる（サイドカーも同時に書き出すため同等）。
    """
    if not path.exists():
        return False
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age < CACHE_TTL_SECONDS


def read_cache_if_valid(path: Path) -> Optional[str]:
    """TTL とサイドカーを検証してキャッシュ内容（str）を返す。

    - TTL 切れ: キャッシュミス扱い
    - サイドカー欠落 / ハッシュ不一致: 本体とサイドカーを削除しキャッシュミス
    - 全条件通過: UTF-8 としてデコードした本文を返す
    """
    if not is_cache_fresh(path):
        # TTL 切れ — サイドカーも含め破棄する。
        if path.exists():
            _unlink_quiet(path)
            _unlink_quiet(sidecar_path(path))
        return None
    verified = _read_verified_cache(path)
    if verified is None:
        return None
    try:
        return verified.decode("utf-8")
    except UnicodeDecodeError:
        # UTF-8 として読めない場合は replace でフォールバックする（既存挙動踏襲）。
        return verified.decode("utf-8", errors="replace")


def write_cache_best_effort(path: Path, text: str, url: str) -> None:
    """キャッシュ本体＋サイドカーを書き込む。失敗しても致命的ではない。"""
    try:
        _write_cache_atomic(path, text.encode("utf-8"), url)
    except OSError as exc:
        sys.stderr.write(f"# キャッシュ書込に失敗した（処理は継続する）: {exc}\n")


def eprint_json(status: Optional[int], message: str) -> None:
    """stderr に JSON 形式でエラーを出力する。"""
    payload = {"error": message}
    if status is not None:
        payload["status"] = status
    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------------------
# バリデーション
# ------------------------------------------------------------------------------


def validate_law_id(value: str) -> str:
    """法令 ID を検証する。e-Gov の法令 ID は英数字のみである。"""
    if not LAW_ID_PATTERN.match(value):
        raise ValueError(f"不正な法令 ID: {value!r}（英数字 1〜20 文字のみ許容する）")
    return value


def validate_article_num(value: str) -> str:
    """条番号を検証する。枝番号（766_2 等）にも対応する。"""
    if not ARTICLE_NUM_PATTERN.match(value):
        raise ValueError(f"不正な条番号: {value!r}（例: 709, 766_2）")
    return value


def validate_keyword(value: str) -> str:
    """キーワードを検証する。長さ上限と NUL バイト混入を拒否する。"""
    if "\x00" in value:
        raise ValueError("キーワードに NUL バイトを含めることはできない")
    if len(value) > KEYWORD_MAX_LEN:
        raise ValueError(
            f"キーワードが長すぎる（{len(value)} 文字、上限 {KEYWORD_MAX_LEN} 文字）"
        )
    if len(value) == 0:
        raise ValueError("キーワードが空である")
    return value


# ------------------------------------------------------------------------------
# HTTP 取得（retry + backoff + jitter）
# ------------------------------------------------------------------------------


def http_get(url: str) -> bytes:
    """e-Gov API に GET リクエストを送る。

    429 / 5xx 系のレスポンスに対し最大 MAX_RETRIES 回まで指数バックオフで再試行する。
    成功時はレスポンス本文（bytes）を返す。失敗時は RuntimeError を送出する。
    """
    last_error: Optional[str] = None
    last_status: Optional[int] = None

    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                status = resp.getcode()
                body = resp.read()
                if status == 200:
                    return body
                last_status = status
                last_error = f"HTTP {status}"
                if status not in RETRYABLE_STATUS:
                    raise RuntimeError(last_error)
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            last_error = f"HTTP {exc.code}: {exc.reason}"
            if exc.code not in RETRYABLE_STATUS:
                # 再試行不可。即座に失敗として返す。
                raise RuntimeError(last_error) from exc
        except urllib.error.URLError as exc:
            last_error = f"接続エラー: {exc.reason}"
        except TimeoutError:
            last_error = "タイムアウト"

        # 再試行待機（最後の試行後は待たない）
        if attempt < MAX_RETRIES:
            delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
            delay = delay + random.uniform(0, delay * 0.25)  # jitter
            time.sleep(delay)

    message = last_error or "不明なネットワークエラー"
    err = RuntimeError(message)
    err.status = last_status  # type: ignore[attr-defined]
    raise err


# ------------------------------------------------------------------------------
# サブコマンド: fetch-article
# ------------------------------------------------------------------------------


def cmd_fetch_article(args: argparse.Namespace) -> int:
    """単一条文を取得する。キャッシュがあれば完全性検証のうえ再利用する。"""
    try:
        law_id = validate_law_id(args.law_id)
        article = validate_article_num(args.article)
    except ValueError as exc:
        eprint_json(None, str(exc))
        return EXIT_VALIDATION

    url = EGOV_ARTICLE_URL.format(
        law_id=urllib.parse.quote(law_id, safe=""),
        article=urllib.parse.quote(article, safe=""),
    )

    cache = cache_path_article(law_id, article)
    cached_text = read_cache_if_valid(cache)
    if cached_text is not None:
        sys.stdout.write(cached_text)
        return EXIT_OK

    try:
        body = http_get(url)
    except RuntimeError as exc:
        status = getattr(exc, "status", None)
        eprint_json(status, f"e-Gov API 取得失敗: {exc}")
        return EXIT_NETWORK

    text = body.decode("utf-8", errors="replace")
    write_cache_best_effort(cache, text, url)

    sys.stdout.write(text)
    return EXIT_OK


# ------------------------------------------------------------------------------
# サブコマンド: search-keyword
# ------------------------------------------------------------------------------


def _strip_namespace(tag: str) -> str:
    """XML タグから名前空間プレフィックスを除去する。"""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _iter_articles_with_parent(root: ET.Element):
    """ルート配下の全 Article 要素を列挙する。

    ElementTree は親参照を持たないが、本関数は ArticleCaption 検索用であり
    Article 自体を返せば十分である。
    """
    for elem in root.iter():
        if _strip_namespace(elem.tag) == "Article":
            yield elem


def cmd_search_keyword(args: argparse.Namespace) -> int:
    """法令全文 XML をキャッシュし、条見出しをキーワード検索する。"""
    try:
        law_id = validate_law_id(args.law_id)
        keyword = validate_keyword(args.keyword)
    except ValueError as exc:
        eprint_json(None, str(exc))
        return EXIT_VALIDATION

    url = EGOV_LAWDATA_URL.format(law_id=urllib.parse.quote(law_id, safe=""))
    cache = cache_path_law(law_id)
    xml_text = read_cache_if_valid(cache)

    if xml_text is None:
        try:
            body = http_get(url)
        except RuntimeError as exc:
            status = getattr(exc, "status", None)
            eprint_json(status, f"e-Gov API 取得失敗: {exc}")
            return EXIT_NETWORK
        xml_text = body.decode("utf-8", errors="replace")
        write_cache_best_effort(cache, xml_text, url)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        eprint_json(None, f"XML パースエラー: {exc}")
        return EXIT_PARSE

    matches = []
    for article in _iter_articles_with_parent(root):
        caption_elem = None
        for child in article:
            if _strip_namespace(child.tag) == "ArticleCaption":
                caption_elem = child
                break
        if caption_elem is None or caption_elem.text is None:
            continue
        caption_text = caption_elem.text
        if keyword in caption_text:
            article_num = article.attrib.get("Num", "")
            matches.append({"article_num": article_num, "caption": caption_text})

    sys.stdout.write(json.dumps(matches, ensure_ascii=False) + "\n")
    return EXIT_OK


# ------------------------------------------------------------------------------
# サブコマンド: clear-cache
# ------------------------------------------------------------------------------


def _delete_with_sidecar(xml_path: Path) -> int:
    """XML 本体とサイドカーを削除し、削除できた件数（0/1/2）を返す。"""
    removed = 0
    if xml_path.exists():
        try:
            xml_path.unlink()
            removed += 1
        except OSError:
            pass
    side = sidecar_path(xml_path)
    if side.exists():
        try:
            side.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def cmd_clear_cache(args: argparse.Namespace) -> int:
    """キャッシュディレクトリ内のファイルを削除する。サイドカーも含む。"""
    base = cache_dir()

    if args.law_id is None:
        # 全削除（.xml とその .sha256 サイドカーをまとめて処理する）
        removed = 0
        for entry in list(base.iterdir()):
            if not entry.is_file():
                continue
            # .sha256 は .xml 側の処理で回収するためスキップする。
            if entry.name.endswith(SIDECAR_SUFFIX):
                continue
            if entry.suffix == ".xml":
                removed += _delete_with_sidecar(entry)
            else:
                # 想定外ファイル（.tmp 残骸等）も掃除する。
                try:
                    entry.unlink()
                    removed += 1
                except OSError:
                    pass
        # 残存する孤児サイドカー（本体が先に消えた場合）を掃除する。
        for entry in list(base.glob(f"*{SIDECAR_SUFFIX}")):
            try:
                entry.unlink()
                removed += 1
            except OSError:
                pass
        sys.stdout.write(f"{removed} 件のキャッシュを削除した。\n")
        return EXIT_OK

    try:
        law_id = validate_law_id(args.law_id)
    except ValueError as exc:
        eprint_json(None, str(exc))
        return EXIT_VALIDATION

    removed = 0
    # 全文 XML とその枝の条文 XML をまとめて削除する。
    targets = [base / f"law_{law_id}.xml"]
    targets.extend(base.glob(f"article_{law_id}_*.xml"))
    for target in targets:
        removed += _delete_with_sidecar(target)
    sys.stdout.write(f"法令 ID {law_id} のキャッシュを {removed} 件削除した。\n")
    return EXIT_OK


# ------------------------------------------------------------------------------
# サブコマンド: self-test（オフライン自己診断）
# ------------------------------------------------------------------------------


def _selftest_tempdir_override(tmp: Path) -> None:
    os.environ[CACHE_ENV_VAR] = str(tmp)


def _selftest_run(base: Path) -> Tuple[int, int]:
    """個別の自己診断を走らせ、(passed, failed) を返す。"""
    passed = 0
    failed = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            sys.stdout.write(f"  [PASS] {name}\n")
        else:
            failed += 1
            sys.stdout.write(f"  [FAIL] {name}{(' — ' + detail) if detail else ''}\n")

    # 1. cache_dir() が環境変数を尊重する
    resolved = cache_dir()
    check("cache_dir honors CLAUDE_BENGO_CACHE_PATH", resolved == base,
          f"got {resolved}")

    # 2. POSIX: ディレクトリ権限が 0o700
    if os.name == "posix":
        mode = stat.S_IMODE(resolved.stat().st_mode)
        check("cache dir permissions are 0o700 (POSIX)", mode == 0o700,
              f"got 0o{mode:o}")
    else:
        sys.stdout.write("  [SKIP] cache dir permissions (non-POSIX)\n")

    # 3. 書込で本体とサイドカーが揃う
    xml_path = resolved / "article_TESTLAW_1.xml"
    side = sidecar_path(xml_path)
    _unlink_quiet(xml_path)
    _unlink_quiet(side)
    payload = "<Article>テスト条文</Article>"
    write_cache_best_effort(xml_path, payload, "https://example.invalid/test")
    check("write creates .xml", xml_path.exists())
    check("write creates .sha256 sidecar", side.exists())

    # 4. サイドカー内の SHA-256 が本体と一致する
    expected = _sha256_bytes(payload.encode("utf-8"))
    stored = _parse_sidecar(side)
    check("sidecar contains correct SHA-256", stored == expected,
          f"stored={stored}, expected={expected}")

    # 5. 読み取りが検証に通る
    content = read_cache_if_valid(xml_path)
    check("verified read returns payload", content == payload)

    # 6. 改ざん検出: 本体を書き換えたら拒否される（両ファイル削除）
    write_cache_best_effort(xml_path, payload, "https://example.invalid/test")
    xml_path.write_bytes(b"<Article>TAMPERED</Article>")
    # mtime を現在時刻に保つため touch する（TTL 判定通過のため）
    os.utime(xml_path, None)
    tampered_result = read_cache_if_valid(xml_path)
    check("tampered xml is rejected", tampered_result is None)
    check("tampered xml is deleted", not xml_path.exists())
    check("tampered sidecar is deleted", not side.exists())

    # 7. TTL 切れは再取得扱い
    write_cache_best_effort(xml_path, payload, "https://example.invalid/test")
    old_mtime = time.time() - (CACHE_TTL_SECONDS + 60)
    os.utime(xml_path, (old_mtime, old_mtime))
    stale_result = read_cache_if_valid(xml_path)
    check("expired cache is treated as miss", stale_result is None)
    check("expired cache files are removed", not xml_path.exists() and not side.exists())

    # 8. サイドカー欠落は再取得扱い（旧形式互換）
    write_cache_best_effort(xml_path, payload, "https://example.invalid/test")
    _unlink_quiet(side)
    legacy_result = read_cache_if_valid(xml_path)
    check("missing sidecar is treated as miss", legacy_result is None)
    check("orphan xml is removed when sidecar missing", not xml_path.exists())

    # 9. clear-cache（law-id 指定）でサイドカーも消える
    write_cache_best_effort(xml_path, payload, "https://example.invalid/test")
    other_xml = resolved / "article_TESTLAW_2.xml"
    write_cache_best_effort(other_xml, payload, "https://example.invalid/test2")
    law_xml = resolved / "law_TESTLAW.xml"
    write_cache_best_effort(law_xml, payload, "https://example.invalid/law")

    ns = argparse.Namespace(law_id="TESTLAW")
    cmd_clear_cache(ns)
    check("clear-cache --law-id removes article xml", not xml_path.exists())
    check("clear-cache --law-id removes article sidecar", not sidecar_path(xml_path).exists())
    check("clear-cache --law-id removes other article xml", not other_xml.exists())
    check("clear-cache --law-id removes other article sidecar", not sidecar_path(other_xml).exists())
    check("clear-cache --law-id removes law xml", not law_xml.exists())
    check("clear-cache --law-id removes law sidecar", not sidecar_path(law_xml).exists())

    # 10. clear-cache（全削除）
    write_cache_best_effort(xml_path, payload, "https://example.invalid/test")
    ns_all = argparse.Namespace(law_id=None)
    cmd_clear_cache(ns_all)
    check("clear-cache all removes xml", not xml_path.exists())
    check("clear-cache all removes sidecar", not sidecar_path(xml_path).exists())

    return passed, failed


def cmd_self_test(_args: argparse.Namespace) -> int:
    """オフライン自己診断を実行する。

    テンポラリディレクトリを `CLAUDE_BENGO_CACHE_PATH` に設定し、キャッシュ
    の書込・検証・改ざん検出・TTL・clear-cache の挙動を検査する。ネット
    ワークは使用しない。
    """
    sys.stdout.write("law-search self-test（オフライン）\n")
    old_override = os.environ.get(CACHE_ENV_VAR)
    global _LEGACY_NOTICE_EMITTED
    saved_notice = _LEGACY_NOTICE_EMITTED
    _LEGACY_NOTICE_EMITTED = True  # 自己診断中は旧キャッシュ通知を抑制する
    with tempfile.TemporaryDirectory(prefix="claude-bengo-selftest-") as tmpdir:
        tmp = Path(tmpdir) / "law-search"
        _selftest_tempdir_override(tmp)
        try:
            passed, failed = _selftest_run(tmp)
        finally:
            # 環境変数を復元する
            if old_override is None:
                os.environ.pop(CACHE_ENV_VAR, None)
            else:
                os.environ[CACHE_ENV_VAR] = old_override
            _LEGACY_NOTICE_EMITTED = saved_notice

    sys.stdout.write(f"結果: {passed} passed, {failed} failed\n")
    return EXIT_OK if failed == 0 else EXIT_VALIDATION


# ------------------------------------------------------------------------------
# エントリポイント
# ------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """argparse パーサを構築する。"""
    parser = argparse.ArgumentParser(
        prog="search.py",
        description="e-Gov 法令 API クライアント（claude-bengo 内部ツール）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch-article", help="単一条文の XML を取得する")
    p_fetch.add_argument("--law-id", required=True, help="法令 ID（例: 129AC0000000089）")
    p_fetch.add_argument("--article", required=True, help="条番号（例: 709 または 766_2）")
    p_fetch.set_defaults(func=cmd_fetch_article)

    p_search = sub.add_parser("search-keyword", help="法令全文から条見出しをキーワード検索する")
    p_search.add_argument("--law-id", required=True, help="法令 ID")
    p_search.add_argument("--keyword", required=True, help="検索キーワード（最大 50 文字）")
    p_search.set_defaults(func=cmd_search_keyword)

    p_clear = sub.add_parser("clear-cache", help="キャッシュを削除する（サイドカー含む）")
    p_clear.add_argument("--law-id", default=None, help="指定時はその法令分のみ削除する")
    p_clear.set_defaults(func=cmd_clear_cache)

    p_self = sub.add_parser("self-test", help="オフライン自己診断を実行する")
    p_self.set_defaults(func=cmd_self_test)

    return parser


def main(argv: Optional[list] = None) -> int:
    """メイン関数。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    # F-033: fetch/search を実行する前に TSV の鮮度をチェック。self-test や
    # clear-cache は skip する。CLAUDE_BENGO_ALLOW_STALE_LAW_LIST=1 で強制続行可能。
    cmd = getattr(args, "command", None) or getattr(args, "func", None).__name__ if hasattr(args, "func") else None
    try:
        if os.environ.get("CLAUDE_BENGO_ALLOW_STALE_LAW_LIST") != "1":
            if cmd in (None,) or (hasattr(args, "func") and args.func.__name__ in ("_cmd_fetch_article", "_cmd_search_keyword")):
                _warn_if_stale()
    except SystemExit:
        raise
    except Exception:
        pass
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
