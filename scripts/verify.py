#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude-bengo verification harness.

使い方:
    python3 scripts/verify.py [--quick] [--json]

実行内容:
    1. 構文チェック: 全 Python スクリプト
    2. ユニットテスト: inheritance-calc/test_calc.py
    3. 検証テスト: law-search/search.py の入力バリデーション（ネットワーク不使用）
    4. フィクスチャ棚卸: 期待 JSON に対応する入力ファイルの有無を報告
    5. MCP 設定検証: .mcp.json が有効な JSON でバージョン固定されていること
    6. プラグインマニフェスト検証: .claude-plugin/plugin.json の妥当性
    7. スキル一覧: 全 SKILL.md のフロントマター確認
    8. コマンド/ドキュメント契約検証: help 件数、stale matter 記述、不要な local 設定
    9. consent.py セルフテスト: admin lock / grant / revoke のオフライン検証

終了コード:
    0  全チェック合格（警告は許容）
    1  1件以上の失敗
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Windows cp1252 コンソールでは Unicode 箱罫 (━) が UnicodeEncodeError を起こす。
# Python 3.7+ の reconfigure で強制的に UTF-8 にして、失敗時は BOX_CHAR を ASCII に
# フォールバックする。これで macOS / Linux / Windows 全てで同一出力になる。
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    BOX_CHAR = "\u2501"  # ━
except (AttributeError, OSError):
    BOX_CHAR = "-"

ROOT = Path(__file__).resolve().parent.parent


class Report:
    def __init__(self) -> None:
        self.passes: List[str] = []
        self.failures: List[str] = []
        self.warnings: List[str] = []

    def passed(self, msg: str) -> None:
        self.passes.append(msg)
        print(f"  [PASS] {msg}")

    def failed(self, msg: str) -> None:
        self.failures.append(msg)
        print(f"  [FAIL] {msg}")

    def warned(self, msg: str) -> None:
        self.warnings.append(msg)
        print(f"  [WARN] {msg}")


def header(title: str) -> None:
    print()
    print(BOX_CHAR * 40)
    print(f"  {title}")
    print(BOX_CHAR * 40)


def run(cmd: List[str], timeout: int = 60) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError as e:
        return -1, "", f"command not found: {e}"


# ---------------------------------------------------------------------------
# 1. Python syntax
# ---------------------------------------------------------------------------


def check_python_syntax(r: Report) -> None:
    header("1. Python syntax check")
    for py in sorted(ROOT.rglob("*.py")):
        if any(part.startswith(".") for part in py.parts):
            continue
        rel = py.relative_to(ROOT)
        try:
            ast.parse(py.read_text(encoding="utf-8"))
            r.passed(f"syntax: {rel}")
        except SyntaxError as e:
            r.failed(f"syntax: {rel} ({e})")


# ---------------------------------------------------------------------------
# 2. inheritance-calc unit tests
# ---------------------------------------------------------------------------


def run_calc_tests(r: Report) -> None:
    header("2. inheritance-calc unit tests")
    test_file = ROOT / "skills" / "inheritance-calc" / "test_calc.py"
    if not test_file.exists():
        r.failed("inheritance-calc: test_calc.py not found")
        return
    rc, out, err = run([sys.executable, str(test_file)], timeout=30)
    last = (out or err).strip().splitlines()[-1] if (out or err) else ""
    if rc == 0:
        r.passed(f"inheritance-calc: {last}")
    else:
        r.failed(f"inheritance-calc: tests failed ({last})")
        for line in (out + err).splitlines()[-15:]:
            print(f"      {line}")


# ---------------------------------------------------------------------------
# 3. law-search offline validation
# ---------------------------------------------------------------------------


def check_law_search(r: Report) -> None:
    header("3. law-search input validation (offline)")
    search_py = ROOT / "skills" / "law-search" / "search.py"
    if not search_py.exists():
        r.failed("law-search: search.py not found")
        return

    # Reject malformed law-id
    rc, _, _ = run(
        [sys.executable, str(search_py), "fetch-article", "--law-id", "bad;id", "--article", "709"],
        timeout=5,
    )
    if rc != 0:
        r.passed("law-search: rejects malformed law-id")
    else:
        r.failed("law-search: malformed law-id was accepted")

    # Reject malformed article
    rc, _, _ = run(
        [sys.executable, str(search_py), "fetch-article", "--law-id", "129AC0000000089", "--article", "abc"],
        timeout=5,
    )
    if rc != 0:
        r.passed("law-search: rejects malformed article number")
    else:
        r.failed("law-search: malformed article number was accepted")

    # Reject overlong keyword
    rc, _, _ = run(
        [
            sys.executable,
            str(search_py),
            "search-keyword",
            "--law-id",
            "129AC0000000089",
            "--keyword",
            "A" * 60,
        ],
        timeout=5,
    )
    if rc != 0:
        r.passed("law-search: rejects overlong keyword")
    else:
        r.failed("law-search: overlong keyword was accepted")

    # Accept valid 枝番号 syntax (offline — just arg validation, no network)
    rc, out, err = run(
        [sys.executable, str(search_py), "fetch-article", "--help"],
        timeout=5,
    )
    if rc == 0 and "article" in out.lower():
        r.passed("law-search: --help is available")
    else:
        r.failed("law-search: --help broken")


# ---------------------------------------------------------------------------
# 4. Fixtures inventory
# ---------------------------------------------------------------------------


REQUIRED_FIXTURES = {
    "template-fill": [
        "source-complaint.pdf",
        "template-complaint.xlsx",
        "template-complaint.yaml",
        "expected-output.json",
    ],
    "family-tree": ["koseki-simple.pdf", "expected-simple.json"],
    "typo-check": ["brief-with-errors.docx", "brief-clean.docx", "expected-corrections.json"],
    "lawsuit-analysis": [
        "complaint.pdf",
        "answer.pdf",
        "expected-timeline.json",
        "expected-characters.json",
    ],
}


def check_fixtures(r: Report) -> None:
    header("4. Fixtures inventory")
    for skill, files in REQUIRED_FIXTURES.items():
        base = ROOT / "fixtures" / skill
        present = [f for f in files if (base / f).exists()]
        missing = [f for f in files if not (base / f).exists()]
        if not missing:
            r.passed(f"fixtures/{skill}: complete")
        elif not present:
            r.warned(f"fixtures/{skill}: all missing ({', '.join(missing)})")
        else:
            r.warned(f"fixtures/{skill}: incomplete — missing: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# 5. .mcp.json
# ---------------------------------------------------------------------------


def check_mcp_json(r: Report) -> None:
    header("5. .mcp.json validation")
    path = ROOT / ".mcp.json"
    if not path.exists():
        r.failed(".mcp.json: not found")
        return
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.failed(f".mcp.json: invalid JSON ({e})")
        return

    if "mcpServers" not in doc:
        r.failed(".mcp.json: missing 'mcpServers' key")
        return

    r.passed(".mcp.json: valid JSON with mcpServers")

    import re

    problems = []
    for name, cfg in doc["mcpServers"].items():
        args = cfg.get("args", [])
        for a in args:
            if a.startswith("-"):
                continue
            if "-mcp-server" in a or "-report-server" in a:
                if not re.search(r"@\d+\.\d+\.\d+", a):
                    problems.append(f"unpinned: {name} -> {a}")
                if not a.startswith("@"):
                    problems.append(f"unscoped: {name} -> {a} (use @knorq/...)")
    if not problems:
        r.passed(".mcp.json: all packages pinned and scoped")
    else:
        for p in problems:
            r.failed(f".mcp.json: {p}")


# ---------------------------------------------------------------------------
# 6. Plugin manifest
# ---------------------------------------------------------------------------


def check_manifest(r: Report) -> None:
    header("6. Plugin manifest validation")
    path = ROOT / ".claude-plugin" / "plugin.json"
    if not path.exists():
        r.failed(".claude-plugin/plugin.json: not found")
        return
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.failed(f"plugin.json: invalid JSON ({e})")
        return
    missing = [k for k in ["name", "description", "version"] if k not in doc]
    if missing:
        r.failed(f"plugin.json: missing required keys: {missing}")
    else:
        r.passed(f"plugin.json: valid ({doc['name']} v{doc['version']})")


# ---------------------------------------------------------------------------
# 7. Skill enumeration
# ---------------------------------------------------------------------------


def check_skills(r: Report) -> None:
    header("7. Skills enumeration")
    skill_dir = ROOT / "skills"
    skill_files = sorted(skill_dir.glob("*/SKILL.md"))
    if not skill_files:
        r.failed("skills: no SKILL.md files found")
        return
    print(f"  Found {len(skill_files)} skills:")
    for s in skill_files:
        name = s.parent.name
        first_line = s.read_text(encoding="utf-8").splitlines()[0] if s.exists() else ""
        has_frontmatter = first_line.strip() == "---"
        marker = "" if has_frontmatter else " (missing frontmatter)"
        print(f"    - {name}{marker}")
        if not has_frontmatter:
            r.warned(f"{name}: SKILL.md missing frontmatter")
    r.passed(f"skills: {len(skill_files)} SKILL.md files present")


# ---------------------------------------------------------------------------
# 8. Command enumeration
# ---------------------------------------------------------------------------


def check_commands(r: Report) -> None:
    header("8. Commands enumeration")
    cmd_dir = ROOT / "commands"
    cmd_files = sorted(cmd_dir.glob("*.md"))
    if not cmd_files:
        r.failed("commands: no .md files found")
        return
    print(f"  Found {len(cmd_files)} commands:")
    broad_tools = []
    for c in cmd_files:
        text = c.read_text(encoding="utf-8")
        first_line = text.splitlines()[0] if text else ""
        has_frontmatter = first_line.strip() == "---"
        print(f"    - {c.stem}{'' if has_frontmatter else ' (missing frontmatter)'}")
        # Flag broad Bash permissions as warning
        if "Bash(python3:*)" in text or "Bash(curl:*)" in text:
            broad_tools.append(c.stem)
    if broad_tools:
        r.warned(f"commands with broad Bash permissions: {', '.join(broad_tools)}")
    r.passed(f"commands: {len(cmd_files)} commands present")


# ---------------------------------------------------------------------------
# 9. Repo contract lint
# ---------------------------------------------------------------------------


def check_repo_contracts(r: Report) -> None:
    header("9. Repo contract lint")

    cmd_files = sorted((ROOT / "commands").glob("*.md"))
    command_count = len(cmd_files)

    help_md = ROOT / "commands" / "help.md"
    if not help_md.exists():
        r.failed("commands/help.md: not found")
        return
    help_text = help_md.read_text(encoding="utf-8")

    import re

    counts = re.findall(r"全\s*(\d+)\s*コマンド|(\d+)\s*コマンド", help_text)
    seen_counts = {int(a or b) for a, b in counts if (a or b)}
    if command_count in seen_counts:
        r.passed(f"help.md: command count matches repo ({command_count})")
    else:
        r.failed(f"help.md: command count drift (repo={command_count}, doc={sorted(seen_counts) or 'none'})")

    template_install = ROOT / "commands" / "template-install.md"
    if template_install.exists():
        ti_text = template_install.read_text(encoding="utf-8")
        if "デフォルトは `case`" in ti_text:
            r.passed("template-install.md: default scope documented as case")
        else:
            r.failed("template-install.md: default scope drift (expected case)")
    else:
        r.failed("commands/template-install.md: not found")

    forbidden_patterns = {
        "/matter-create": "removed /matter-create reference",
        "事案未設定": "removed '事案未設定' wording",
        "アクティブな matter": "removed 'アクティブな matter' wording",
        "`--matter <id>`": "removed deprecated --matter flag from command docs",
    }
    offenders = []
    for path in cmd_files:
        if path.name == "help.md":
            # help.md may refer to the historical matter model in migration copy.
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, label in forbidden_patterns.items():
            if pattern in text:
                offenders.append(f"{path.relative_to(ROOT)}: {label}")
    if offenders:
        for msg in offenders:
            r.failed(msg)
    else:
        r.passed("commands: no stale matter-era contract text")

    local_settings = ROOT / ".claude" / "settings.local.json"
    if local_settings.exists():
        r.failed(".claude/settings.local.json: committed local permission file should not exist")
    else:
        r.passed(".claude/settings.local.json: not present")


# ---------------------------------------------------------------------------
# 10. consent self-test
# ---------------------------------------------------------------------------


def check_consent_self_test(r: Report) -> None:
    header("10. consent.py self-test")
    consent_py = ROOT / "skills" / "_lib" / "consent.py"
    if not consent_py.exists():
        r.failed("consent.py: not found")
        return
    rc, out, err = run([sys.executable, str(consent_py), "--self-test"], timeout=30)
    last = (out or err).strip().splitlines()[-1] if (out or err) else ""
    if rc == 0 and "passed" in last:
        r.passed(f"consent.py: {last}")
    else:
        r.failed(f"consent.py: self-test failed ({last})")
        for line in (out + err).splitlines()[-15:]:
            print(f"      {line}")


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="claude-bengo verification harness")
    ap.add_argument("--quick", action="store_true", help="skip slower checks")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()

    r = Report()

    check_python_syntax(r)
    run_calc_tests(r)
    check_law_search(r)
    check_fixtures(r)
    check_mcp_json(r)
    check_manifest(r)
    check_skills(r)
    check_commands(r)
    check_repo_contracts(r)
    check_consent_self_test(r)

    # --- Summary ---
    print()
    print(BOX_CHAR * 40)
    print(f"  結果: {len(r.passes)} passed, {len(r.failures)} failed, {len(r.warnings)} warnings")
    print(BOX_CHAR * 40)

    if r.failures:
        print()
        print("失敗したチェック:")
        for f in r.failures:
            print(f"  - {f}")

    if args.json:
        print()
        print(
            json.dumps(
                {
                    "passed": len(r.passes),
                    "failed": len(r.failures),
                    "warnings": len(r.warnings),
                    "failures": r.failures,
                    "warnings_list": r.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    return 1 if r.failures else 0


if __name__ == "__main__":
    sys.exit(main())
