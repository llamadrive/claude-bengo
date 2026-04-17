#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成スタブ fixture の生成スクリプト（Option B）。

実際のクライアントデータを絶対に含めない合成ファイルを生成する。
`/verify all` が存在チェックを通せるが、本番デモには十分でない「最低限の
参照用 fixture」を作る。

## 生成内容

1. koseki-simple.pdf    戸籍謄本相当（簡易）
2. koseki-complex.pdf   戸籍謄本相当（3 世代・代襲あり）
3. complaint.pdf        訴状（合成）
4. answer.pdf           答弁書（合成）
5. source-complaint.pdf template-fill のソース文書（合成）
6. brief-with-errors.docx 準備書面（意図的誤字混入）
7. brief-clean.docx      準備書面（校正済み）

## 設計方針

- **PDF**: stdlib のみで生成する最小 PDF 構造。Helvetica 英字のみで構成。
  Japanese content は romaji + [SYNTHETIC] マーカー。実戦デモには pilot
  事務所が提供する正式 PDF への差替えが前提。
- **DOCX**: zipfile + 手書き XML で日本語 UTF-8 対応。proper な誤字入り
  文書として機能する。

## なぜ PDF だけ ASCII か

Japanese PDF 生成には CID フォント埋込が必要で、stdlib では実装困難。
Option B の性格上「regression test を通す最低限」として ASCII で
「これは [koseki PDF] の stub である」と記述する方針を取る。
実際の訴状・戸籍 PDF が必要な pilot テストでは、Option A で firm が
提供したファイルと差し替える。
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


# ---------------------------------------------------------------------------
# 最小 PDF 生成器（ASCII only, Helvetica）
# ---------------------------------------------------------------------------


def _make_minimal_pdf(lines: List[str], title: str = "Synthetic Fixture") -> bytes:
    """Helvetica で Latin-only テキストを描画する最小 PDF を生成する。

    lines: 各要素が 1 行の ASCII テキスト。非 ASCII は ? に置換する。
    戻り値: PDF バイト列。
    """
    # 非 ASCII を ? に置換（PDF ストリームが Latin-1 超を扱うには複雑化）
    def _ascii_only(s: str) -> str:
        return "".join(c if ord(c) < 128 else "?" for c in s)

    # PDF オブジェクトを組み立てる
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    objects: List[bytes] = []

    # Content stream
    content_lines = []
    content_lines.append(b"BT\n/F1 10 Tf\n1.2 Tf 12 TL\n50 800 Td\n")
    for i, line in enumerate(lines):
        escaped = _ascii_only(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if i == 0:
            content_lines.append(f"({escaped}) Tj\n".encode("ascii"))
        else:
            content_lines.append(f"T* ({escaped}) Tj\n".encode("ascii"))
    content_lines.append(b"ET\n")
    content_stream = b"".join(content_lines)

    # Object 1: Catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    # Object 2: Pages
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    # Object 3: Page
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    # Object 4: Content
    objects.append(
        f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
        + content_stream
        + b"\nendstream"
    )
    # Object 5: Font (Helvetica)
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    # Assemble body with xref tracking
    body = bytearray()
    offsets: List[int] = [0]  # xref 0 is sentinel
    cursor = len(header)
    body_parts = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(cursor)
        obj_bytes = f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
        body_parts.append(obj_bytes)
        cursor += len(obj_bytes)
    body_bytes = b"".join(body_parts)

    # xref table
    xref_offset = cursor
    xref = [b"xref\n", f"0 {len(objects) + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n".encode("ascii"))
    xref_bytes = b"".join(xref)

    # Trailer
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R "
        f"/Info << /Title ({_ascii_only(title)}) >> >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")

    return header + body_bytes + xref_bytes + trailer


STUB_MARKER = b"[SYNTHETIC STUB FIXTURE"


def _is_stub_or_missing(path: Path) -> bool:
    """Return True if path does not yet exist or is a stub we generated before."""
    if not path.exists():
        return True
    try:
        head = path.read_bytes()[:4096]
    except OSError:
        return True
    return STUB_MARKER in head


def _write_pdf(path: Path, lines: List[str], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _is_stub_or_missing(path):
        print(f"  [SKIP] {path.relative_to(ROOT)} (real fixture present, {path.stat().st_size} bytes)")
        return
    path.write_bytes(_make_minimal_pdf(lines, title))
    print(f"  [OK] {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# 最小 DOCX 生成器（UTF-8 日本語対応）
# ---------------------------------------------------------------------------


def _make_minimal_docx(paragraphs: List[str]) -> bytes:
    """zipfile + XML で proper な日本語 DOCX を生成する。

    paragraphs: 各要素が 1 パラグラフの文字列（日本語 OK）。
    戻り値: DOCX バイト列。
    """
    import io
    import xml.sax.saxutils as sax

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )

    body_parts = []
    for p in paragraphs:
        escaped = sax.escape(p)
        body_parts.append(f"<w:p><w:r><w:t xml:space=\"preserve\">{escaped}</w:t></w:r></w:p>")
    body = "".join(body_parts)

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", document)
    return buf.getvalue()


def _docx_contains_stub_marker(path: Path) -> bool:
    """Detect stub DOCX by scanning word/document.xml for the marker text."""
    try:
        with zipfile.ZipFile(path) as z:
            if "word/document.xml" not in z.namelist():
                return False
            return b"[SYNTHETIC" in z.read("word/document.xml")[:8192]
    except (zipfile.BadZipFile, OSError):
        return False


def _write_docx(path: Path, paragraphs: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not _docx_contains_stub_marker(path):
        print(f"  [SKIP] {path.relative_to(ROOT)} (real fixture present, {path.stat().st_size} bytes)")
        return
    path.write_bytes(_make_minimal_docx(paragraphs))
    print(f"  [OK] {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# Individual fixture builders
# ---------------------------------------------------------------------------


def build_koseki_simple() -> None:
    lines = [
        "[SYNTHETIC STUB FIXTURE - NOT FOR PRODUCTION]",
        "Represents: koseki-touhon (koseki-simple.pdf)",
        "",
        "Content summary (ASCII only; replace with real PDF for demos):",
        "",
        "Honseki: Tokyo-to Chiyoda-ku Kasumigaseki 1-1-1",
        "Hittosha (head): KONO Taro, born Showa 40-nen 1-gatsu 1-nichi",
        "Spouse: KONO Hanako, born Showa 42-nen 3-gatsu 20-nichi",
        "Child 1: KONO Ichiro, born Heisei 2-nen 5-gatsu 5-nichi",
        "Child 2: KONO Jiro, born Heisei 5-nen 8-gatsu 8-nichi",
        "",
        "Relationships:",
        "  Taro + Hanako (married Showa 60-nen 4-gatsu 1-nichi)",
        "  -> Ichiro (chonan), Jiro (jinan)",
        "",
        "All data is FICTIONAL. To demo /family-tree, replace with real",
        "synthetic koseki PDF per fixtures/README.md.",
    ]
    _write_pdf(FIXTURES / "family-tree" / "koseki-simple.pdf", lines, "koseki-simple stub")


def build_koseki_complex() -> None:
    lines = [
        "[SYNTHETIC STUB FIXTURE - NOT FOR PRODUCTION]",
        "Represents: koseki-touhon - 3 generations with daikyu souzoku",
        "",
        "Honseki: Tokyo-to Chiyoda-ku Kasumigaseki 1-1-1",
        "",
        "Generation 1 (deceased):",
        "  KONO Taro, born Taisho 10-nen 1-gatsu 1-nichi,",
        "    died Reiwa 5-nen 2-gatsu 14-nichi",
        "  KONO Hanako, born Taisho 12-nen, died Heisei 30-nen",
        "",
        "Generation 2:",
        "  KONO Ichiro (chonan) - ALIVE, born Showa 20-nen",
        "  KONO Jiro (jinan) - DIED Reiwa 2-nen 6-gatsu 10-nichi",
        "    (died before Taro, triggers daikyu souzoku for Jiro's children)",
        "  KONO Saburo (sannan) - ALIVE, born Showa 28-nen",
        "",
        "Generation 3 (Jiro's children - daikyu souzoku heirs):",
        "  KONO Shiro, born Heisei 10-nen 4-gatsu 1-nichi",
        "  KONO Goro, born Heisei 13-nen 7-gatsu 15-nichi",
        "",
        "This fixture exercises 3-generation extraction + daikyu souzoku",
        "detection in /family-tree and /inheritance-calc.",
        "",
        "Replace with real synthetic koseki for production demos.",
    ]
    _write_pdf(FIXTURES / "family-tree" / "koseki-complex.pdf", lines, "koseki-complex stub")


def build_complaint() -> None:
    lines = [
        "[SYNTHETIC STUB FIXTURE - NOT FOR PRODUCTION]",
        "Represents: sojo (complaint) for /lawsuit-analysis",
        "",
        "Case: Reiwa 5-nen (wa) Dai 1234-go",
        "Court: Tokyo District Court, Civil Division 1",
        "Filed: Reiwa 5-nen 6-gatsu 1-nichi",
        "Subject: Loan repayment claim (kashikin henkan seikyu jiken)",
        "",
        "Plaintiff: KONO Taro, Tokyo-to Chiyoda-ku Kasumigaseki 1-1-1",
        "Defendant: OTSUYAMA Jiro, Tokyo-to Shinjuku-ku Nishi-Shinjuku 2-2-2",
        "",
        "Claim amount: JPY 3,000,000 + annual 15% interest from 2023-04-01",
        "",
        "Facts (jiken no keii):",
        "  1. Reiwa 4-nen 3-gatsu 1-nichi: Plaintiff lent JPY 3,000,000",
        "     to Defendant under oral agreement, repayment due 2023-12-31",
        "  2. Reiwa 5-nen 1-gatsu 15-nichi: Plaintiff sent demand letter",
        "     by certified mail (naiyo shomei)",
        "  3. Defendant has not responded or repaid",
        "",
        "Evidence: Ko-no. 1 (demand letter copy), Ko-no. 2 (bank transfer record)",
        "",
        "Request: Defendant shall pay JPY 3,000,000 plus interest.",
        "",
        "Replace with real synthetic complaint PDF for demos.",
    ]
    _write_pdf(FIXTURES / "lawsuit-analysis" / "complaint.pdf", lines, "complaint stub")


def build_answer() -> None:
    lines = [
        "[SYNTHETIC STUB FIXTURE - NOT FOR PRODUCTION]",
        "Represents: toben-sho (answer) for /lawsuit-analysis",
        "",
        "Case: Reiwa 5-nen (wa) Dai 1234-go",
        "Corresponds to complaint.pdf in same directory",
        "Filed: Reiwa 5-nen 7-gatsu 10-nichi",
        "",
        "Defendant: OTSUYAMA Jiro (represented by counsel)",
        "",
        "Answer to complaint (seikyu no shushi ni tai suru toben):",
        "  1. Plaintiff's claims shall be dismissed.",
        "  2. Plaintiff shall bear the costs.",
        "",
        "Response to facts (seikyu no gen'in ni tai suru ninhi):",
        "  Paragraph 1: DENIED (hinin)",
        "    Defendant asserts the JPY 3,000,000 transfer was a gift,",
        "    not a loan. No loan agreement was made.",
        "  Paragraph 2: PARTIALLY ADMITTED (ichibu mitomeru)",
        "    Defendant received a letter from Plaintiff but denies it",
        "    constituted a lawful demand.",
        "  Paragraph 3: ADMITTED (mitomeru)",
        "    Defendant has not repaid (because no debt exists).",
        "",
        "Defense (kogen):",
        "  Beneficial gift defense (zoyo no kogen)",
        "",
        "Evidence: Otsu-no. 1 (email exchange re: gift)",
        "",
        "Replace with real synthetic answer PDF for demos.",
    ]
    _write_pdf(FIXTURES / "lawsuit-analysis" / "answer.pdf", lines, "answer stub")


def build_source_complaint() -> None:
    lines = [
        "[SYNTHETIC STUB FIXTURE - NOT FOR PRODUCTION]",
        "Represents: source complaint for /template-fill",
        "",
        "Format matches template-complaint.yaml field definitions.",
        "",
        "Case name: Reiwa 5-nen (wa) Dai 1234-go",
        "Event: Loan dispute between plaintiff and defendant",
        "",
        "Plaintiff info:",
        "  Name: KONO Taro",
        "  Address: Tokyo-to Chiyoda-ku Kasumigaseki 1-1-1",
        "  Phone: 03-0000-0001",
        "",
        "Defendant info:",
        "  Name: OTSUYAMA Jiro",
        "  Address: Tokyo-to Shinjuku-ku Nishi-Shinjuku 2-2-2",
        "  Phone: 03-0000-0002",
        "",
        "Claim:",
        "  Amount: JPY 3,000,000",
        "  Interest rate: 15% per annum",
        "  Interest start: 2023-04-01",
        "",
        "Accident/event details:",
        "  Date: 2022-03-01",
        "  Place: Tokyo",
        "  Nature: Oral loan agreement",
        "",
        "This stub exercises /template-fill field extraction into the",
        "template-complaint.xlsx structure. Replace with real synthetic",
        "source-complaint PDF for demos.",
    ]
    _write_pdf(FIXTURES / "template-fill" / "source-complaint.pdf", lines, "source-complaint stub")


def build_brief_with_errors() -> None:
    """意図的に誤字を混入した準備書面 DOCX。"""
    paragraphs = [
        "令和5年（ワ）第1234号 貸金返還請求事件",
        "原告　甲野太郎",
        "被告　乙山次郎",
        "",
        "準備書面（合成スタブ・意図的誤字入り）",
        "",
        "令和5年7月20日",
        "東京地方裁判所　民事第1部　御中",
        "",
        "原告訴訟代理人　弁護士　丙川三郎",
        "",
        "第1　はじめに",
        "本件は、被告が原告から借り受けた金銭の返還を求める事件である。原告は、被告に対し民法709条に基づき、損害賠償を請求することができるものとする。",
        "",
        "第2　事実関係",
        "原告は令和4年3月1日に被告に対して300万円を貸し付けた。しかし、被告は返済を行なう意思を示さず、契約の暇疵について議論を行なった。",
        "",
        "第3　当事者の主張",
        "申立人（原告）は、被告が契約を履行しないことについて、当然に責任を負うものとする。被告は、原告の主張について否認している。",
        "",
        "第4　結論",
        "以上の理由により、申立人は本件請求の認容を求める次第である。",
        "",
        "[SYNTHETIC STUB - 以下の誤字が意図的に混入されている]",
        "誤字リスト: 709条→第709条 / 行なう→行う / 暇疵→瑕疵 / 原告と申立人の混在 / できるものとする",
    ]
    _write_docx(FIXTURES / "typo-check" / "brief-with-errors.docx", paragraphs)


def build_brief_clean() -> None:
    """校正済みバージョン（ground truth）。"""
    paragraphs = [
        "令和5年（ワ）第1234号 貸金返還請求事件",
        "原告　甲野太郎",
        "被告　乙山次郎",
        "",
        "準備書面（合成スタブ・校正済み）",
        "",
        "令和5年7月20日",
        "東京地方裁判所　民事第1部　御中",
        "",
        "原告訴訟代理人　弁護士　丙川三郎",
        "",
        "第1　はじめに",
        "本件は、被告が原告から借り受けた金銭の返還を求める事件である。原告は、被告に対し民法第709条に基づき、損害賠償を請求することができる。",
        "",
        "第2　事実関係",
        "原告は令和4年3月1日に被告に対して300万円を貸し付けた。しかし、被告は返済を行う意思を示さず、契約の瑕疵について議論を行った。",
        "",
        "第3　当事者の主張",
        "原告は、被告が契約を履行しないことについて、当然に責任を負う。被告は、原告の主張について否認している。",
        "",
        "第4　結論",
        "以上の理由により、原告は本件請求の認容を求める次第である。",
        "",
        "[SYNTHETIC CLEAN VERSION - 校正済み ground truth]",
    ]
    _write_docx(FIXTURES / "typo-check" / "brief-clean.docx", paragraphs)


# ---------------------------------------------------------------------------


def main() -> int:
    print("Building stub fixtures (Option B, synthetic data only)...\n")
    build_koseki_simple()
    build_koseki_complex()
    build_complaint()
    build_answer()
    build_source_complaint()
    build_brief_with_errors()
    build_brief_clean()
    print("\nAll 7 stub fixtures written.")
    print("These are ASCII/Latin placeholders (PDFs) + proper Japanese DOCX.")
    print("Replace PDFs with real synthetic Japanese content before production demos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
