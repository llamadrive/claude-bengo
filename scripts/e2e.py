#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude-bengo 統合（E2E）テスト。

スキル間のつなぎ目を実際に CLI を呼び出して検証する。単体のセルフテストでは
各モジュール内の論理は検証できるが、モジュール間の呼出契約（skill が matter.py
→ audit.py → copy_file.py の順で呼ぶ流れ）は検証できないため、本スクリプトで
以下を実地に再現する:

1. 事案ライフサイクル: create → list → switch → info
2. matter-ref ドロップと 4 段階優先順位の再現
3. v1.x からの移行（import-from-cwd）
4. 事案スコープの監査記録と verify
5. 事案境界: 事案 A のログに事案 B から書き込めないこと
6. copy_file による XLSX 複製
7. 機密スキルの「matter 未設定で中止」動作を `resolve` → `source=none` を通じて再現
8. 並行事案への並列書込とチェーン独立性
9. `_schema.yaml` のシステム同梱テンプレートが scripts から読み取れる
10. セキュリティ: シンボリックリンク ref の拒否、`MATTER_ID` 上書き警告

ネットワーク・MCP サーバ・実在 PDF に依存する部分は対象外（スキル内 Claude
実行と MCP 呼出は手動テストが必要）。

使い方:
    python3 scripts/e2e.py          全テスト実行
    python3 scripts/e2e.py --keep   後片付けを省略（デバッグ用）

終了コード:
    0  全ケース合格
    1  1 件以上失敗
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
WORKSPACE = str(ROOT / "skills" / "_lib" / "workspace.py")
AUDIT = str(ROOT / "skills" / "_lib" / "audit.py")
COPY_FILE = str(ROOT / "skills" / "_lib" / "copy_file.py")


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------


class Case:
    def __init__(self) -> None:
        self.passed: List[str] = []
        self.failed: List[Tuple[str, str]] = []

    def ok(self, name: str, detail: str = "") -> None:
        tag = f"  [PASS] {name}"
        if detail:
            tag += f" — {detail}"
        print(tag)
        self.passed.append(name)

    def ng(self, name: str, detail: str) -> None:
        print(f"  [FAIL] {name} — {detail}")
        self.failed.append((name, detail))

    def summary(self) -> int:
        print()
        print(f"e2e: {len(self.passed)} passed, {len(self.failed)} failed")
        if self.failed:
            print()
            print("Failed:")
            for name, detail in self.failed:
                print(f"  - {name}: {detail}")
        return 0 if not self.failed else 1


def run(
    cmd: List[str],
    env: Optional[dict] = None,
    cwd: Optional[Path] = None,
    input_text: Optional[str] = None,
    timeout: int = 15,
) -> Tuple[int, str, str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=merged_env,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        timeout=timeout,
    )
    return r.returncode, r.stdout, r.stderr


def section(title: str) -> None:
    print()
    print("━" * 60)
    print(f"  {title}")
    print("━" * 60)


# ---------------------------------------------------------------------------
# シナリオ
# ---------------------------------------------------------------------------


def scenario_workspace_flow(c: Case, sandbox: Path) -> None:
    """v3.0.0: workspace ベースの基本フロー検証。"""
    section("1. workspace-based flow (v3.0.0)")

    # Two separate case folders under sandbox
    case_a = sandbox / "cases" / "smith-v-jones"
    case_b = sandbox / "cases" / "tanaka-divorce"
    case_a.mkdir(parents=True)
    case_b.mkdir(parents=True)

    env = {"CLAUDE_BENGO_SESSION_ID": "e2e-workspace"}

    # 1. Unitialized CWD → resolve says not initialized
    rc, out, _ = run([PY, WORKSPACE, "resolve"], env=env, cwd=case_a)
    payload = json.loads(out)
    if rc == 0 and payload.get("initialized") is False:
        c.ok("1.1 uninitialized folder detected", f"root={payload['workspace_root']}")
    else:
        c.ng("1.1 uninitialized folder detected", out)

    # 2. Record from case_a auto-initializes .claude-bengo/
    rc, _, _ = run(
        [PY, AUDIT, "record", "--skill", "e2e", "--event", "file_read", "--note", "a1"],
        env=env, cwd=case_a,
    )
    audit_a = case_a / ".claude-bengo" / "audit.jsonl"
    if rc == 0 and audit_a.exists() and audit_a.stat().st_size > 0:
        c.ok("1.2 record auto-creates .claude-bengo/ in CWD", f"size={audit_a.stat().st_size}")
    else:
        c.ng("1.2 record auto-creates .claude-bengo/ in CWD", f"rc={rc}")

    # 3. Record from case_b lands in case_b, NOT case_a
    rc, _, _ = run(
        [PY, AUDIT, "record", "--skill", "e2e", "--event", "file_read", "--note", "b1"],
        env=env, cwd=case_b,
    )
    audit_b = case_b / ".claude-bengo" / "audit.jsonl"
    if rc == 0 and audit_b.exists() and audit_a.read_text().count("b1") == 0:
        c.ok("1.3 writes are isolated per case folder", "")
    else:
        c.ng("1.3 writes are isolated per case folder", f"")

    # 4. Walk-up from nested dir finds parent workspace
    nested = case_a / "evidence" / "photos"
    nested.mkdir(parents=True)
    before = audit_a.stat().st_size
    rc, _, _ = run(
        [PY, AUDIT, "record", "--skill", "e2e", "--event", "file_read", "--note", "nested"],
        env=env, cwd=nested,
    )
    after = audit_a.stat().st_size
    if rc == 0 and after > before:
        c.ok("1.4 walk-up resolves parent workspace from nested dir", f"grew={after - before}")
    else:
        c.ng("1.4 walk-up resolves parent workspace from nested dir", f"rc={rc}")

    # 5. verify returns chain OK
    rc, out, _ = run([PY, AUDIT, "verify"], env=env, cwd=case_a)
    if rc == 0 and "fail=0" in out:
        c.ok("1.5 verify returns chain OK", "")
    else:
        c.ng("1.5 verify returns chain OK", out)

    # 6. /case-info equivalent — `workspace info`
    rc, out, _ = run([PY, WORKSPACE, "info"], env=env, cwd=case_a)
    info = json.loads(out)
    if rc == 0 and info.get("initialized") and info.get("audit", {}).get("lines", 0) >= 2:
        c.ok("1.6 workspace info shows state", f"lines={info['audit']['lines']}")
    else:
        c.ng("1.6 workspace info shows state", out)

    # 7. config.audit_enabled=false disables logging
    cfg = case_a / ".claude-bengo" / "config.json"
    cfg.write_text(json.dumps({"audit_enabled": False}), encoding="utf-8")
    before = audit_a.stat().st_size
    rc, _, _ = run(
        [PY, AUDIT, "record", "--skill", "e2e", "--event", "file_read", "--note", "skip"],
        env=env, cwd=case_a,
    )
    after = audit_a.stat().st_size
    if rc == 0 and after == before:
        c.ok("1.7 audit_enabled=false disables logging", "")
    else:
        c.ng("1.7 audit_enabled=false disables logging", f"grew={after - before}")
    cfg.unlink()  # cleanup


def scenario_matter_lifecycle(c: Case, sandbox: Path) -> None:
    section("1. Matter lifecycle: create → list → info → switch")
    env = {"CLAUDE_BENGO_ROOT": str(sandbox)}

    # create
    rc, out, err = run(
        [PY, MATTER, "create", "smith-v-jones", "--title", "Smith v. Jones 損害賠償", "--client", "Smith Corp"],
        env=env,
    )
    if rc != 0:
        c.ng("1.1 create smith-v-jones", f"rc={rc} err={err[:200]}")
        return
    try:
        payload = json.loads(out)
        if payload.get("matter_id") != "smith-v-jones" or not payload.get("created"):
            raise ValueError("unexpected payload")
    except (json.JSONDecodeError, ValueError) as e:
        c.ng("1.1 create smith-v-jones", f"stdout not JSON: {e}")
        return
    c.ok("1.1 create smith-v-jones", f"path={payload['path']}")

    # second matter with auto-generated ID
    rc, out, _ = run([PY, MATTER, "create"], env=env)
    if rc != 0:
        c.ng("1.2 create with auto-generated ID", f"rc={rc}")
        return
    auto_id = json.loads(out).get("matter_id", "")
    if not auto_id or "-" not in auto_id:
        c.ng("1.2 create with auto-generated ID", f"id={auto_id}")
        return
    c.ok("1.2 auto-generated ID", f"id={auto_id}")

    # list
    rc, out, _ = run([PY, MATTER, "list", "--format", "json"], env=env)
    ids = [m["id"] for m in json.loads(out)]
    if "smith-v-jones" in ids and auto_id in ids:
        c.ok("1.3 list shows both matters", f"ids={ids}")
    else:
        c.ng("1.3 list", f"ids={ids}")

    # info
    rc, out, _ = run([PY, MATTER, "info", "smith-v-jones"], env=env)
    info = json.loads(out)
    if info["metadata"]["client"] == "Smith Corp" and info["metadata"]["title"].startswith("Smith"):
        c.ok("1.4 info preserves metadata", f"title={info['metadata']['title']}")
    else:
        c.ng("1.4 info", f"metadata={info.get('metadata')}")

    # switch
    rc, _, _ = run([PY, MATTER, "switch", "smith-v-jones"], env=env)
    if rc != 0:
        c.ng("1.5 switch", f"rc={rc}")
        return
    rc, out, _ = run([PY, MATTER, "resolve"], env=env)
    resolved = json.loads(out)
    if resolved["matter_id"] == "smith-v-jones" and resolved["source"] == "current":
        c.ok("1.5 switch + resolve", f"source={resolved['source']}")
    else:
        c.ng("1.5 switch + resolve", f"resolved={resolved}")


def scenario_resolver_precedence(c: Case, sandbox: Path) -> None:
    section("2. Resolver: 4-level precedence (flag > env > cwd-ref > current)")
    env_base = {"CLAUDE_BENGO_ROOT": str(sandbox), "CLAUDE_BENGO_SILENT_MATTER_OVERRIDE": "1"}

    work = sandbox / "casework"
    work.mkdir()

    # Ensure matter exists + drop ref
    run([PY, MATTER, "drop-ref", "smith-v-jones"], env=env_base, cwd=work)

    # cwd-ref beats current
    rc, out, _ = run([PY, MATTER, "resolve"], env=env_base, cwd=work)
    r = json.loads(out)
    if r["source"] == "cwd-ref" and r["matter_id"] == "smith-v-jones":
        c.ok("2.1 cwd-ref beats current", f"source={r['source']}")
    else:
        c.ng("2.1 cwd-ref beats current", f"r={r}")

    # env beats cwd-ref
    env_with_mid = {**env_base, "MATTER_ID": "smith-v-jones"}
    # create a second matter to switch to
    run([PY, MATTER, "create", "other"], env=env_base)
    env_with_mid2 = {**env_base, "MATTER_ID": "other"}
    rc, out, _ = run([PY, MATTER, "resolve"], env=env_with_mid2, cwd=work)
    r = json.loads(out)
    if r["source"] == "env" and r["matter_id"] == "other":
        c.ok("2.2 env beats cwd-ref", f"source={r['source']}")
    else:
        c.ng("2.2 env beats cwd-ref", f"r={r}")

    # flag beats env
    rc, out, _ = run([PY, MATTER, "resolve", "--matter", "smith-v-jones"], env=env_with_mid2, cwd=work)
    r = json.loads(out)
    if r["source"] == "flag" and r["matter_id"] == "smith-v-jones":
        c.ok("2.3 flag beats env", f"source={r['source']}")
    else:
        c.ng("2.3 flag beats env", f"r={r}")

    # env override warning fires when ids differ (without silent env)
    env_noisy = {"CLAUDE_BENGO_ROOT": str(sandbox), "MATTER_ID": "other"}
    rc, _, err = run([PY, MATTER, "resolve"], env=env_noisy, cwd=work)
    if "MATTER_ID" in err and "上書き" in err:
        c.ok("2.4 env override emits stderr WARN", "WARN text present")
    else:
        c.ng("2.4 env override WARN", f"stderr={err[:200]}")


def scenario_symlink_ref_rejected(c: Case, sandbox: Path) -> None:
    section("3. Security: symlink .claude-bengo-matter-ref is rejected")
    if os.name != "posix":
        c.ok("3.1 symlink rejection (skipped on non-POSIX)")
        return
    env = {"CLAUDE_BENGO_ROOT": str(sandbox)}
    work = sandbox / "symlink-case"
    work.mkdir()
    evil_target = sandbox / "attacker-owned.txt"
    evil_target.write_text("smith-v-jones\n", encoding="utf-8")
    (work / ".claude-bengo-matter-ref").symlink_to(evil_target)

    rc, out, err = run([PY, MATTER, "resolve"], env=env, cwd=work)
    r = json.loads(out)
    if r["source"] != "cwd-ref" and "symlink" in err.lower():
        c.ok("3.1 symlink ref rejected", f"source={r['source']} + stderr WARN")
    else:
        c.ng("3.1 symlink ref rejected", f"r={r}, err={err[:200]}")


def scenario_import_from_cwd(c: Case, sandbox: Path) -> None:
    section("4. Migration: import-from-cwd filters to .yaml/.xlsx")
    env = {"CLAUDE_BENGO_ROOT": str(sandbox)}
    legacy = sandbox / "legacy-project"
    (legacy / "templates").mkdir(parents=True)
    # good files
    (legacy / "templates" / "evidence.yaml").write_text("id: evidence\n", encoding="utf-8")
    (legacy / "templates" / "evidence.xlsx").write_bytes(b"fake xlsx")
    (legacy / "templates" / "complaint.yaml").write_text("id: complaint\n", encoding="utf-8")
    # junk that must be skipped
    (legacy / "templates" / ".DS_Store").write_bytes(b"\x00")
    (legacy / "templates" / "notes.txt").write_text("notes", encoding="utf-8")
    (legacy / "templates" / "_schema.yaml").write_text("schema", encoding="utf-8")

    rc, out, _ = run(
        [PY, MATTER, "import-from-cwd", "--matter-id", "migrated-case", "--title", "移行済み事案"],
        env=env,
        cwd=legacy,
    )
    if rc != 0:
        c.ng("4.1 import succeeds", f"rc={rc}")
        return
    payload = json.loads(out)
    if payload.get("count") == 3 and payload.get("skipped_count") == 3:
        c.ok("4.1 import filters junk", f"copied={payload['count']} skipped={payload['skipped_count']}")
    else:
        c.ng("4.1 import filters junk", f"payload={payload}")

    # 取込先に実体があるか
    dst = sandbox / "matters" / "migrated-case" / "templates"
    names = sorted(p.name for p in dst.iterdir())
    expected = ["complaint.yaml", "evidence.xlsx", "evidence.yaml"]
    if names == expected:
        c.ok("4.2 destination contents correct", f"files={names}")
    else:
        c.ng("4.2 destination contents", f"got={names}, want={expected}")

    # 元ファイルは残る（非破壊）
    if (legacy / "templates" / "evidence.yaml").exists():
        c.ok("4.3 source retained")
    else:
        c.ng("4.3 source retained", "deleted unexpectedly")


def scenario_audit_flow(c: Case, sandbox: Path) -> None:
    section("5. Audit: per-matter records + chain + verify")
    env = {"CLAUDE_BENGO_ROOT": str(sandbox)}

    # Create a fake file to hash
    fake = sandbox / "sample.docx"
    fake.write_bytes(b"%PDF-1.5 fake document contents")

    # Record two events under smith-v-jones
    for i, (evt, note) in enumerate(
        [("file_read", "開始"), ("file_write", "校正完了: 12件")]
    ):
        rc, out, err = run(
            [
                PY,
                AUDIT,
                "record",
                "--matter",
                "smith-v-jones",
                "--skill",
                "typo-check",
                "--event",
                evt,
                "--file",
                str(fake),
                "--note",
                note,
            ],
            env=env,
        )
        if rc != 0:
            c.ng(f"5.1 record [{evt}]", f"rc={rc} err={err[:200]}")
            return
        rec = json.loads(out)
        if rec.get("skill") != "typo-check" or rec.get("event") != evt:
            c.ng(f"5.1 record [{evt}]", f"rec={rec}")
            return
    c.ok("5.1 record two events under smith-v-jones")

    # filename_sha256 present, filename empty by default
    audit_path = sandbox / "matters" / "smith-v-jones" / "audit.jsonl"
    lines = [json.loads(l) for l in audit_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if lines and lines[0]["filename"] == "" and lines[0]["filename_sha256"]:
        c.ok("5.2 filename hashed by default", "filename='' + filename_sha256 set")
    else:
        c.ng("5.2 filename hashed by default", f"first={lines[0] if lines else None}")

    # verify
    rc, _, _ = run([PY, AUDIT, "verify", "--matter", "smith-v-jones"], env=env)
    if rc == 0:
        c.ok("5.3 verify smith-v-jones chain intact")
    else:
        c.ng("5.3 verify", f"rc={rc}")

    # tamper middle line
    content = audit_path.read_text(encoding="utf-8").splitlines()
    tampered_line = content[0].replace("開始", "TAMPERED")
    audit_path.write_text(tampered_line + "\n" + "\n".join(content[1:]) + "\n", encoding="utf-8")
    rc, out, _ = run([PY, AUDIT, "verify", "--matter", "smith-v-jones"], env=env)
    if rc != 0 and "FAIL" in out:
        c.ok("5.4 verify detects tampering", "rc!=0 + FAIL message")
    else:
        c.ng("5.4 verify detects tampering", f"rc={rc}")


def scenario_matter_isolation(c: Case, sandbox: Path) -> None:
    section("6. Isolation: records in A don't leak to B")
    env = {"CLAUDE_BENGO_ROOT": str(sandbox)}

    # Reset the chain by writing fresh records under both matters
    for mid in ("smith-v-jones", "other"):
        rc, _, _ = run(
            [PY, AUDIT, "record", "--matter", mid, "--skill", "family-tree", "--event", "file_read", "--note", f"exclusive-to-{mid}"],
            env=env,
        )
        if rc != 0:
            c.ng(f"6.1 record to {mid}", f"rc={rc}")
            return

    a_log = (sandbox / "matters" / "smith-v-jones" / "audit.jsonl").read_text(encoding="utf-8")
    b_log = (sandbox / "matters" / "other" / "audit.jsonl").read_text(encoding="utf-8")

    if "exclusive-to-smith-v-jones" in a_log and "exclusive-to-smith-v-jones" not in b_log:
        c.ok("6.1 matter A record only in A's log")
    else:
        c.ng("6.1 matter A record only in A's log", "cross-contamination detected")

    if "exclusive-to-other" in b_log and "exclusive-to-other" not in a_log:
        c.ok("6.2 matter B record only in B's log")
    else:
        c.ng("6.2 matter B record only in B's log", "cross-contamination detected")

    # verify 両方
    rc1, _, _ = run([PY, AUDIT, "verify", "--matter", "other"], env=env)
    if rc1 == 0:
        c.ok("6.3 matter B chain still valid")
    else:
        c.ng("6.3 matter B chain", f"rc={rc1}")


def scenario_no_matter_refusal(c: Case, sandbox: Path) -> None:
    section("7. Confidential skills refuse when matter unset (simulation)")
    # Simulate by running resolve from an empty CWD with no env / current
    empty = sandbox / "empty-no-matter"
    empty.mkdir()
    env = {
        "CLAUDE_BENGO_ROOT": str(sandbox / "nonexistent-pristine-root"),
    }
    # Remove any inherited MATTER_ID just in case
    for k in ("MATTER_ID",):
        env[k] = ""

    rc, out, _ = run([PY, MATTER, "resolve"], env=env, cwd=empty)
    r = json.loads(out)
    if r["matter_id"] is None and r["source"] == "none":
        c.ok("7.1 no matter set → source=none + message", f"msg_len={len(r.get('message') or '')}")
    else:
        c.ng("7.1 no matter set", f"r={r}")

    # audit record to nonexistent matter is rejected (exit 2)
    rc, _, err = run(
        [PY, AUDIT, "record", "--matter", "ghost-matter", "--skill", "typo-check", "--event", "file_read", "--note", "bogus"],
        env={"CLAUDE_BENGO_ROOT": str(sandbox)},
    )
    if rc == 2 and "存在しない" in err:
        c.ok("7.2 audit to nonexistent matter exits 2", "correct error message")
    else:
        c.ng("7.2 audit to nonexistent matter", f"rc={rc} err={err[:200]}")


def scenario_copy_file(c: Case, sandbox: Path) -> None:
    section("8. copy_file helper: shutil-based, rejects symlinks")
    src = sandbox / "src.xlsx"
    src.write_bytes(b"pretend xlsx")
    dst = sandbox / "out" / "dst.xlsx"

    rc, _, err = run([PY, COPY_FILE, "--src", str(src), "--dst", str(dst)])
    if rc == 0 and dst.exists() and dst.read_bytes() == b"pretend xlsx":
        c.ok("8.1 copy_file normal path")
    else:
        c.ng("8.1 copy_file normal path", f"rc={rc} err={err[:200]}")

    # overwrite without flag → fail
    rc, _, err = run([PY, COPY_FILE, "--src", str(src), "--dst", str(dst)])
    if rc != 0 and "既に存在" in err:
        c.ok("8.2 copy_file refuses overwrite without flag")
    else:
        c.ng("8.2 copy_file overwrite refusal", f"rc={rc} err={err[:200]}")

    # symlink source → reject
    if os.name == "posix":
        sym = sandbox / "sym.xlsx"
        sym.symlink_to(src)
        rc, _, err = run([PY, COPY_FILE, "--src", str(sym), "--dst", str(sandbox / "captured.xlsx")])
        if rc != 0 and "シンボリックリンク" in err:
            c.ok("8.3 copy_file rejects symlink source")
        else:
            c.ng("8.3 copy_file symlink rejection", f"rc={rc} err={err[:200]}")
    else:
        c.ok("8.3 copy_file symlink rejection (skipped on non-POSIX)")


def scenario_permissions(c: Case, sandbox: Path) -> None:
    section("9. Filesystem: root + matters dirs are 0o700 on POSIX")
    if os.name != "posix":
        c.ok("9.1 perms (skipped on non-POSIX)")
        return
    r_mode = sandbox.stat().st_mode & 0o777
    m_mode = (sandbox / "matters").stat().st_mode & 0o777
    if r_mode == 0o700 and m_mode == 0o700:
        c.ok("9.1 root 0o700 + matters 0o700", f"root={oct(r_mode)}, matters={oct(m_mode)}")
    else:
        c.ng("9.1 perms", f"root={oct(r_mode)}, matters={oct(m_mode)}")

    # per-matter dir should also be 0o700
    per = (sandbox / "matters" / "smith-v-jones").stat().st_mode & 0o777
    if per == 0o700:
        c.ok("9.2 per-matter dir 0o700")
    else:
        c.ng("9.2 per-matter perms", f"mode={oct(per)}")


def scenario_template_install(c: Case, sandbox: Path) -> None:
    section("10a. Bundled template install: list + install + idempotency")
    env = {"CLAUDE_BENGO_ROOT": str(sandbox)}
    TEMPLATE_LIB = str(ROOT / "skills" / "_lib" / "template_lib.py")

    # list (no matter needed)
    rc, out, _ = run([PY, TEMPLATE_LIB, "list", "--format", "json"], env=env)
    if rc != 0:
        c.ng("10a.1 list bundled templates", f"rc={rc}")
        return
    entries = json.loads(out)
    ids = {e["id"] for e in entries}
    # v2.3.0 ships 23 forms across 9 categories
    expected = {
        # Phase 1
        "creditor-list", "estate-inventory", "settlement-traffic",
        # Phase 2
        "divorce-agreement", "naiyou-shoumei", "overtime-calc-sheet",
        "complaint-loan-repayment", "answer-generic",
        "inheritance-renunciation", "inheritance-division-agreement",
        "power-of-attorney", "bankruptcy-dohaishi", "labor-tribunal-application",
        # Phase 3
        "statement-family", "family-mediation-application", "household-budget",
        "rehabilitation-small", "criminal-defense-appointment", "criminal-settlement",
        "guardianship-application", "payment-demand",
        "child-support-application", "spousal-support-application",
    }
    if expected.issubset(ids):
        c.ok(f"10a.1 all {len(expected)} bundled templates present in registry", f"count={len(ids)}")
    else:
        c.ng("10a.1 bundled templates present", f"missing={expected - ids}")

    # Categories now include 刑事弁護
    cats = {e.get("category") for e in entries}
    expected_cats = {"破産・再生", "相続", "交通事故", "家事事件", "一般民事", "民事訴訟", "労働", "汎用", "刑事弁護"}
    if expected_cats.issubset(cats):
        c.ok(f"10a.1b all {len(expected_cats)} categories represented", f"cats={sorted(cats)}")
    else:
        c.ng("10a.1b categories", f"missing={expected_cats - cats}")

    # v3.0.0: install resolves workspace from CWD. Use a case folder inside sandbox.
    case_dir = sandbox / "cases" / "template-install-test"
    case_dir.mkdir(parents=True, exist_ok=True)

    rc, out, err = run(
        [PY, TEMPLATE_LIB, "install", "creditor-list"],
        env=env, cwd=case_dir,
    )
    if rc == 0 and "creditor-list.yaml" in out and "creditor-list.xlsx" in out:
        c.ok("10a.2 install copies YAML + XLSX to workspace templates dir")
    else:
        c.ng("10a.2 install", f"rc={rc} out={out[:200]} err={err[:200]}")

    # verify files exist at the destination
    dst_dir = case_dir / ".claude-bengo" / "templates"
    if (dst_dir / "creditor-list.yaml").exists() and (dst_dir / "creditor-list.xlsx").exists():
        c.ok("10a.3 installed files land in workspace templates dir")
    else:
        c.ng("10a.3 installed files", f"contents={list(dst_dir.iterdir()) if dst_dir.exists() else 'missing'}")

    # re-install without --replace fails (exit 3)
    rc, _, err = run(
        [PY, TEMPLATE_LIB, "install", "creditor-list"],
        env=env, cwd=case_dir,
    )
    if rc == 3 and "既に" in err:
        c.ok("10a.4 re-install without --replace refused", "exit 3")
    else:
        c.ng("10a.4 re-install refusal", f"rc={rc} err={err[:200]}")

    # with --replace succeeds
    rc, out, _ = run(
        [PY, TEMPLATE_LIB, "install", "creditor-list", "--replace"],
        env=env, cwd=case_dir,
    )
    if rc == 0 and '"replaced": true' in out:
        c.ok("10a.5 --replace overwrites")
    else:
        c.ng("10a.5 --replace", f"rc={rc} out={out[:200]}")

    # v3.0.0: "ghost matter" 概念は廃止。--matter は deprecated で単に無視される。
    # 代わりに nonexistent template ID のエラー経路をテスト。
    rc, _, err = run(
        [PY, TEMPLATE_LIB, "install", "nonexistent-template"],
        env=env, cwd=case_dir,
    )
    if rc != 0 and "見つからない" in err:
        c.ok("10a.6 install nonexistent template refused")
    else:
        c.ng("10a.6 nonexistent template refusal", f"rc={rc} err={err[:200]}")

    # install a Phase-3 form (different category) to ensure broad coverage works
    rc, out, _ = run(
        [PY, TEMPLATE_LIB, "install", "criminal-defense-appointment"],
        env=env, cwd=case_dir,
    )
    if rc == 0 and "criminal-defense-appointment.yaml" in out:
        c.ok("10a.7 Phase-3 form (刑事) installs to workspace")
    else:
        c.ng("10a.7 Phase-3 install", f"rc={rc}")

    # list shows it after install
    dst = case_dir / ".claude-bengo" / "templates"
    names = {p.name for p in dst.iterdir()} if dst.exists() else set()
    if {"criminal-defense-appointment.yaml", "criminal-defense-appointment.xlsx"}.issubset(names):
        c.ok("10a.8 installed Phase-3 form files exist")
    else:
        c.ng("10a.8 Phase-3 files", f"got={names}")


def scenario_traffic_damage_calc(c: Case, sandbox: Path) -> None:
    section("11. Track B: traffic-damage-calc")
    TDC = str(ROOT / "skills" / "traffic-damage-calc" / "calc.py")

    # Realistic 12 級 scenario
    payload = {
        "victim": {
            "name": "甲野太郎", "age_at_accident": 35, "gender": "male",
            "occupation_type": "salaried", "annual_income": 5_000_000,
            "is_household_supporter": True,
        },
        "accident": {"date": "2024-04-01", "victim_fault_percent": 10},
        "medical": {
            "hospital_days": 30, "outpatient_days": 180,
            "medical_fees": 1_500_000, "transportation": 50_000, "equipment": 30_000,
            "nursing_days_hospital": 10, "severity": "major",
        },
        "lost_wages": {"days_off_work": 90},
        "disability": {"grade": 12, "years_until_67": 32},
        "options": {"include_lawyer_fee": True, "include_delay_interest": False},
    }
    rc, out, err = run([PY, TDC, "calc", "--json", json.dumps(payload)])
    if rc == 0:
        r = json.loads(out)
        # Grand total should be in the ballpark for this case (21M - 23M range)
        gt = r["summary"]["grand_total"]
        if 21_000_000 <= gt <= 23_000_000:
            c.ok("11.1 12級後遺障害シナリオ合計額が実務範囲内", f"grand_total={gt:,}")
        else:
            c.ng("11.1 12級 grand_total", f"got {gt:,}")
    else:
        c.ng("11.1 calc invocation", f"rc={rc} err={err[:200]}")

    # Invalid input rejected
    bad_payload = {"victim": {"age_at_accident": -5, "gender": "male", "occupation_type": "salaried"},
                   "accident": {"date": "2024-04-01", "victim_fault_percent": 0}}
    rc, _, err = run([PY, TDC, "calc", "--json", json.dumps(bad_payload)])
    if rc != 0 and "age_at_accident" in err:
        c.ok("11.2 入力バリデーション（負の年齢）")
    else:
        c.ng("11.2 validation", f"rc={rc} err={err[:200]}")

    # --self-test runs 20-case internal suite
    rc, out, _ = run([PY, TDC, "--self-test"], timeout=30)
    if rc == 0 and "0 failed" in out:
        c.ok("11.3 内蔵 self-test (all pass)")
    else:
        c.ng("11.3 self-test", f"rc={rc}")


def scenario_child_support_calc(c: Case, sandbox: Path) -> None:
    section("12. Track B-2: child-support-calc")
    CSC = str(ROOT / "skills" / "child-support-calc" / "calc.py")

    # 養育費: 算定表 4-6 万円範囲内
    payload = {
        "kind": "child_support",
        "obligor": {"annual_income": 5_000_000, "income_type": "salary"},
        "obligee": {"annual_income": 1_000_000, "income_type": "salary"},
        "children": [{"age": 10}],
    }
    rc, out, err = run([PY, CSC, "calc", "--json", json.dumps(payload)])
    if rc == 0:
        r = json.loads(out)
        if 40_000 <= r["monthly_amount"] <= 60_000:
            c.ok("12.1 養育費 義務者500万/権利者100万/子1人(10歳) 算定表範囲内",
                 f"月額 {r['monthly_amount']:,}")
        else:
            c.ng("12.1 養育費範囲", f"got {r['monthly_amount']:,}")
    else:
        c.ng("12.1 child-support calc", f"rc={rc} err={err[:200]}")

    # 婚姻費用: 算定表 8-10 万円範囲内
    payload2 = dict(payload, kind="spousal_support")
    rc, out, _ = run([PY, CSC, "calc", "--json", json.dumps(payload2)])
    r = json.loads(out)
    if 70_000 <= r["monthly_amount"] <= 110_000:
        c.ok("12.2 婚姻費用 同条件 算定表範囲内", f"月額 {r['monthly_amount']:,}")
    else:
        c.ng("12.2 婚姻費用範囲", f"got {r['monthly_amount']:,}")

    # バリデーション: kind 不正
    rc, _, err = run([PY, CSC, "calc", "--json",
                      json.dumps({"kind": "foo",
                                  "obligor": {"annual_income": 0, "income_type": "salary"},
                                  "obligee": {"annual_income": 0, "income_type": "salary"}})])
    if rc != 0 and "kind は" in err:
        c.ok("12.3 kind バリデーション")
    else:
        c.ng("12.3 validation", f"rc={rc}")

    # 20 歳の子 → エラー
    rc, _, err = run([PY, CSC, "calc", "--json",
                      json.dumps({"kind": "child_support",
                                  "obligor": {"annual_income": 500_0000, "income_type": "salary"},
                                  "obligee": {"annual_income": 0, "income_type": "salary"},
                                  "children": [{"age": 20}]})])
    if rc != 0 and "20 歳以上" in err:
        c.ok("12.4 子 20 歳以上を拒否")
    else:
        c.ng("12.4 age validation", f"rc={rc}")

    # Self-test (count updated per release, just check pass success)
    rc, out, _ = run([PY, CSC, "--self-test"], timeout=30)
    if rc == 0 and "0 failed" in out:
        c.ok("12.5 内蔵 self-test (all pass)")
    else:
        c.ng("12.5 self-test", f"rc={rc}")


def scenario_debt_recalc(c: Case, sandbox: Path) -> None:
    section("13. Track B-3: debt-recalc")
    DR = str(ROOT / "skills" / "debt-recalc" / "calc.py")

    # 2015/02/15 から毎月 2 万返済を 48 ヶ月（過払金発生想定）
    from datetime import date as _date
    txs = [{"date": "2015-01-15", "type": "borrowing", "amount": 500_000}]
    for i in range(48):
        y = 2015 + (1 + i) // 12
        m = (1 + i) % 12 + 1
        txs.append({"date": f"{y}-{m:02d}-15", "type": "payment", "amount": 20_000})
    payload = {"transactions": txs}
    rc, out, err = run([PY, DR, "calc", "--json", json.dumps(payload)])
    if rc == 0:
        r = json.loads(out)
        if r["summary"]["overpayment_principal"] > 0:
            c.ok(f"13.1 長期返済で過払金発生",
                 f"元本 {r['summary']['overpayment_principal']:,}")
        else:
            c.ng("13.1 overpayment", "過払金発生せず")
    else:
        c.ng("13.1 debt-recalc", f"rc={rc} err={err[:200]}")

    rc, out, _ = run([PY, DR, "--self-test"], timeout=30)
    if rc == 0 and "0 failed" in out:
        c.ok("13.2 内蔵 self-test (all pass)")
    else:
        c.ng("13.2 self-test", f"rc={rc}")


def scenario_overtime_calc(c: Case, sandbox: Path) -> None:
    section("14. Track B-4: overtime-calc")
    OC = str(ROOT / "skills" / "overtime-calc" / "calc.py")

    payload = {
        "employee": {"monthly_salary": 300_000},
        "work_hours": {"monthly_scheduled_hours": 150},
        "monthly_records": [
            {"year_month": "2024-04", "legal_overtime_h": 30},
        ],
        "options": {"filing_date": "2024-06-01"},
    }
    rc, out, err = run([PY, OC, "calc", "--json", json.dumps(payload)])
    if rc == 0:
        r = json.loads(out)
        if r["summary"]["total_unpaid_within_statute"] == 75_000:
            c.ok("14.1 時間外 30h × 2000 × 1.25 = 75,000")
        else:
            c.ng("14.1 basic overtime", f"got {r['summary']['total_unpaid_within_statute']}")
    else:
        c.ng("14.1 overtime-calc", f"rc={rc} err={err[:200]}")

    rc, out, _ = run([PY, OC, "--self-test"], timeout=30)
    if rc == 0 and "0 failed" in out:
        c.ok("14.2 内蔵 self-test (all pass)")
    else:
        c.ng("14.2 self-test", f"rc={rc}")


def scenario_iryubun_calc(c: Case, sandbox: Path) -> None:
    section("15. Track B-5: iryubun-calc")
    IC = str(ROOT / "skills" / "iryubun-calc" / "calc.py")
    payload = {
        "basis": {"positive_estate": 100_000_000, "debts": 0},
        "heirs": [
            {"id": "w", "kind": "spouse", "legal_share": "1/2", "inherited_net_amount": 0},
            {"id": "c1", "kind": "child", "legal_share": "1/2", "inherited_net_amount": 0},
        ],
        "requesting_heir_id": "w",
    }
    rc, out, _ = run([PY, IC, "calc", "--json", json.dumps(payload)])
    if rc == 0 and json.loads(out)["iryubun_infringement"] == 25_000_000:
        c.ok("15.1 配偶者遺留分 1/4 × 1億 = 2500万")
    else:
        c.ng("15.1 iryubun", f"rc={rc}")
    rc, out, _ = run([PY, IC, "--self-test"], timeout=30)
    if rc == 0 and "0 failed" in out:
        c.ok("15.2 内蔵 self-test (all pass)")
    else:
        c.ng("15.2 self-test", f"rc={rc}")


def scenario_property_division_calc(c: Case, sandbox: Path) -> None:
    section("16. Track B-6: property-division-calc")
    PD = str(ROOT / "skills" / "property-division-calc" / "calc.py")
    payload = {
        "assets": [
            {"asset_type": "deposit", "value": 40_000_000, "owner": "husband"},
        ],
    }
    rc, out, _ = run([PY, PD, "calc", "--json", json.dumps(payload)])
    if rc == 0 and json.loads(out)["summary"]["settlement_from_husband_to_wife"] == 20_000_000:
        c.ok("16.1 夫単独名義 4000万 → 夫→妻 2000万")
    else:
        c.ng("16.1 property-division", f"rc={rc}")
    rc, out, _ = run([PY, PD, "--self-test"], timeout=30)
    if rc == 0 and "0 failed" in out:
        c.ok("16.2 内蔵 self-test (all pass)")
    else:
        c.ng("16.2 self-test", f"rc={rc}")


def scenario_retention(c: Case, sandbox: Path) -> None:
    section("10b. Audit: KEEP env prunes old rotations")
    log = sandbox / "keep-test-audit.jsonl"
    env = {
        "CLAUDE_BENGO_ROOT": str(sandbox),
        "CLAUDE_BENGO_AUDIT_PATH": str(log),
        "CLAUDE_BENGO_AUDIT_MAX_BYTES": "500",
        "CLAUDE_BENGO_AUDIT_KEEP": "2",
    }
    for i in range(20):
        run(
            [PY, AUDIT, "record", "--skill", "test", "--event", "file_read", "--note", f"r{i}"],
            env=env,
        )
    # count rotated files
    rotated = [p for p in sandbox.iterdir() if p.name.startswith("keep-test-audit.jsonl.") and not p.name.endswith(".lock")]
    if len(rotated) == 2:
        c.ok("10.1 retention cap enforced", f"rotated={len(rotated)}")
    else:
        c.ng("10.1 retention cap", f"rotated={len(rotated)} (expected 2)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="sandbox を削除しない")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="cb-e2e-"))
    sandbox = tmp / "claude-bengo"
    sandbox.mkdir(parents=True)
    print(f"sandbox: {sandbox}")

    c = Case()
    try:
        # v3.0.0: matter ベースのシナリオは workspace ベースに置換
        scenario_workspace_flow(c, sandbox)
        scenario_copy_file(c, sandbox)
        scenario_template_install(c, sandbox)
        scenario_traffic_damage_calc(c, sandbox)
        scenario_child_support_calc(c, sandbox)
        scenario_debt_recalc(c, sandbox)
        scenario_overtime_calc(c, sandbox)
        scenario_iryubun_calc(c, sandbox)
        scenario_property_division_calc(c, sandbox)
        scenario_retention(c, sandbox)
    finally:
        if args.keep:
            print(f"\n[--keep] sandbox retained: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
