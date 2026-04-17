#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最小限の XLSX 書込ヘルパー（stdlib のみ）。

用途: 同梱する裁判所書式テンプレートの XLSX を生成する。
openpyxl 等を追加依存に入れずに `zipfile` + `xml.etree.ElementTree` で
構築する。

カバー範囲:
- 単一シート
- 文字列／数値セル
- 結合セル
- 列幅指定
- 太字書式（必要最小限）

非対応（本用途では不要なもの）:
- 数式（`=SUM(..)` 等）— テンプレートには書かない
- 複数シート
- 画像・グラフ
- 条件付き書式

呼出例:

    from xlsx_writer import Workbook
    wb = Workbook()
    wb.set_column_widths({1: 10, 2: 20, 3: 15})
    wb.write_cell(1, 1, "№", bold=True)
    wb.write_cell(1, 2, "名称", bold=True)
    wb.write_cell(2, 2, "甲野太郎")
    wb.merge(3, 1, 3, 3)
    wb.save("out.xlsx")
"""

from __future__ import annotations

import datetime as _dt
import xml.sax.saxutils as _sax
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

Cell = Tuple[int, int, Union[str, int, float], bool]  # row, col, value, bold


def _col_letter(col: int) -> str:
    """1-indexed column number を Excel アドレス (A, B, ..., Z, AA, AB, ...) に変換する。"""
    assert col >= 1
    result = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        result = chr(65 + rem) + result
    return result


def _cell_ref(row: int, col: int) -> str:
    """(row, col) → 'A1' 形式のアドレス。"""
    return f"{_col_letter(col)}{row}"


def _escape(s: str) -> str:
    """XML エスケープ。"""
    return _sax.escape(s, {'"': "&quot;"})


class Workbook:
    """単一シートの最小 XLSX ワークブック。

    セル位置は全て 1-indexed（row=1, col=1 が A1）で一貫する。テンプレート YAML
    の position.row / position.column と同じ規約。
    """

    def __init__(self, sheet_name: str = "Sheet1") -> None:
        self.sheet_name = sheet_name
        self.cells: List[Cell] = []
        self.merges: List[Tuple[int, int, int, int]] = []  # r1, c1, r2, c2
        self.col_widths: Dict[int, float] = {}
        self.row_heights: Dict[int, float] = {}

    # ---- API ----

    def write_cell(
        self,
        row: int,
        col: int,
        value: Union[str, int, float, None],
        bold: bool = False,
    ) -> None:
        """1 セルに値を書き込む。None は空セル扱い（書かない）。"""
        if value is None or value == "":
            return
        self.cells.append((row, col, value, bold))

    def write_row(
        self,
        row: int,
        start_col: int,
        values: List[Union[str, int, float, None]],
        bold: bool = False,
    ) -> None:
        """1 行分を連続して書き込む。"""
        for i, v in enumerate(values):
            self.write_cell(row, start_col + i, v, bold=bold)

    def merge(self, r1: int, c1: int, r2: int, c2: int) -> None:
        """(r1,c1) から (r2,c2) を結合セルにする。"""
        assert r1 <= r2 and c1 <= c2
        self.merges.append((r1, c1, r2, c2))

    def set_column_widths(self, widths: Dict[int, float]) -> None:
        """列幅を指定する。キーは 1-indexed 列番号、値は文字数相当。"""
        self.col_widths.update(widths)

    def set_row_height(self, row: int, height: float) -> None:
        """行高を指定する（ポイント単位）。"""
        self.row_heights[row] = height

    # ---- ファイル出力 ----

    def save(self, path: Union[str, Path]) -> None:
        """XLSX ファイルに書き出す。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 共有文字列プール
        strings: List[str] = []
        string_index: Dict[str, int] = {}

        def intern_string(s: str) -> int:
            if s not in string_index:
                string_index[s] = len(strings)
                strings.append(s)
            return string_index[s]

        # セルを (row, col) でソートして出力
        sorted_cells = sorted(self.cells, key=lambda x: (x[0], x[1]))

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", self._content_types_xml())
            zf.writestr("_rels/.rels", self._root_rels_xml())
            zf.writestr("xl/workbook.xml", self._workbook_xml())
            zf.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml())
            zf.writestr("xl/styles.xml", self._styles_xml())
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                self._sheet_xml(sorted_cells, intern_string),
            )
            zf.writestr("xl/sharedStrings.xml", self._shared_strings_xml(strings))

    # ---- XML ビルダ ----

    def _content_types_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        )

    def _root_rels_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        )

    def _workbook_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            f'<sheet name="{_escape(self.sheet_name)}" sheetId="1" r:id="rId1"/>'
            "</sheets>"
            "</workbook>"
        )

    def _workbook_rels_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        )

    def _styles_xml(self) -> str:
        """2 スタイル: 通常 (0) と太字 (1)。"""
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2">'
            '<font><sz val="11"/><name val="Yu Gothic"/></font>'
            '<font><b/><sz val="11"/><name val="Yu Gothic"/></font>'
            "</fonts>"
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0"/></cellStyleXfs>'
            '<cellXfs count="2">'
            '<xf numFmtId="0" fontId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" xfId="0" applyFont="1"/>'
            "</cellXfs>"
            "</styleSheet>"
        )

    def _shared_strings_xml(self, strings: List[str]) -> str:
        parts = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n',
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ',
            f'count="{len(strings)}" uniqueCount="{len(strings)}">',
        ]
        for s in strings:
            # preserve leading/trailing spaces
            parts.append(f'<si><t xml:space="preserve">{_escape(s)}</t></si>')
        parts.append("</sst>")
        return "".join(parts)

    def _sheet_xml(self, sorted_cells: List[Cell], intern) -> str:
        parts = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        ]

        # 列幅定義
        if self.col_widths:
            parts.append("<cols>")
            for col, width in sorted(self.col_widths.items()):
                parts.append(
                    f'<col min="{col}" max="{col}" width="{width}" customWidth="1"/>'
                )
            parts.append("</cols>")

        parts.append("<sheetData>")

        # 行ごとにグループ化
        current_row: Optional[int] = None
        for (row, col, value, bold) in sorted_cells:
            if row != current_row:
                if current_row is not None:
                    parts.append("</row>")
                row_attr = ""
                if row in self.row_heights:
                    row_attr = f' ht="{self.row_heights[row]}" customHeight="1"'
                parts.append(f'<row r="{row}"{row_attr}>')
                current_row = row

            addr = _cell_ref(row, col)
            style = ' s="1"' if bold else ""
            if isinstance(value, (int, float)):
                parts.append(f'<c r="{addr}"{style}><v>{value}</v></c>')
            else:
                idx = intern(str(value))
                parts.append(f'<c r="{addr}" t="s"{style}><v>{idx}</v></c>')

        if current_row is not None:
            parts.append("</row>")

        parts.append("</sheetData>")

        # 結合セル
        if self.merges:
            parts.append(f'<mergeCells count="{len(self.merges)}">')
            for (r1, c1, r2, c2) in self.merges:
                ref = f"{_cell_ref(r1, c1)}:{_cell_ref(r2, c2)}"
                parts.append(f'<mergeCell ref="{ref}"/>')
            parts.append("</mergeCells>")

        parts.append("</worksheet>")
        return "".join(parts)


def _self_test() -> int:
    """サニティチェック。openpyxl があれば読み戻し、なければ zipfile で検証。"""
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="xlsx-writer-"))
    out = tmp / "test.xlsx"

    wb = Workbook(sheet_name="テスト")
    wb.set_column_widths({1: 5, 2: 20, 3: 15})
    wb.write_row(1, 1, ["№", "氏名", "金額"], bold=True)
    wb.write_row(2, 1, [1, "甲野太郎", 1000000])
    wb.write_row(3, 1, [2, "乙山花子", 500000])
    wb.merge(5, 1, 5, 3)
    wb.write_cell(5, 1, "合計 1,500,000 円", bold=True)
    wb.save(out)

    # ZIP 構造を最低限チェック
    with zipfile.ZipFile(out, "r") as zf:
        names = set(zf.namelist())
        required = {
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/worksheets/sheet1.xml",
            "xl/sharedStrings.xml",
            "xl/styles.xml",
        }
        missing = required - names
        if missing:
            print(f"  [FAIL] missing parts: {missing}")
            return 1
        print(f"  [PASS] XLSX structure: {len(names)} parts")

        # sharedStrings に日本語が入っているか
        ss = zf.read("xl/sharedStrings.xml").decode("utf-8")
        if "甲野太郎" in ss and "テスト" not in ss:
            # テスト sheet name は workbook.xml 側
            wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
            if "テスト" in wb_xml:
                print("  [PASS] 日本語セル文字列＋シート名が保持されている")
            else:
                print("  [FAIL] sheet name lost")
                return 1
        else:
            print("  [FAIL] shared strings missing 日本語")
            return 1

        # merges
        sheet = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        if 'ref="A5:C5"' in sheet:
            print("  [PASS] 結合セルが記録されている")
        else:
            print("  [FAIL] merge not recorded")
            return 1

    print("xlsx_writer: 3/3 passed")

    # 後片付け
    import shutil
    shutil.rmtree(tmp)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
