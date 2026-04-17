#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同梱テンプレートの YAML + XLSX を生成するビルドスクリプト。

各テンプレート定義を Python コード内に持ち、stdlib のみで YAML と XLSX を
`templates/_bundled/{id}/{id}.yaml` と `{id}.xlsx` に書き出す。

実行:
    python3 scripts/build_bundled_forms.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "_lib"))

from xlsx_writer import Workbook  # noqa: E402

BUNDLED = ROOT / "templates" / "_bundled"


# ---------------------------------------------------------------------------
# YAML エミッタ（stdlib のみ、テンプレート YAML は構造が決まっているため十分）
# ---------------------------------------------------------------------------


def _emit_yaml(doc: dict) -> str:
    """template YAML を手書きで構築する。matter.py の metadata パーサと互換。

    単純な "key: value" を主軸にしつつ、リスト/ネストを必要な範囲で扱う。
    """
    lines: List[str] = []
    for k, v in doc.items():
        if k == "fields":
            lines.append("fields:")
            for f in v:
                lines.append(f"  - id: {f['id']}")
                lines.append(f"    label: \"{f['label']}\"")
                lines.append(f"    type: {f['type']}")
                lines.append(f"    required: {str(f.get('required', False)).lower()}")
                if "position" in f:
                    lines.append("    position:")
                    lines.append(f"      row: {f['position']['row']}")
                    lines.append(f"      column: {f['position']['column']}")
                if "range" in f:
                    r = f["range"]
                    lines.append("    range:")
                    lines.append(f"      headerRow: {r['headerRow']}")
                    lines.append(f"      dataStartRow: {r['dataStartRow']}")
                    lines.append(f"      startColumn: {r['startColumn']}")
                    lines.append(f"      endRow: {r['endRow']}")
                    lines.append(f"      endColumn: {r['endColumn']}")
                if "columns" in f:
                    lines.append("    columns:")
                    for col in f["columns"]:
                        lines.append(f"      - id: {col['id']}")
                        lines.append(f"        label: \"{col['label']}\"")
                        lines.append(f"        type: {col['type']}")
                        if "description" in col:
                            lines.append(f"        description: \"{col['description']}\"")
                if "options" in f:
                    lines.append("    options:")
                    for opt in f["options"]:
                        lines.append(f"      - \"{opt}\"")
        else:
            # scalar keys: id, title, description, category, templateFile
            v_str = str(v)
            if any(ch in v_str for ch in [":", "#", '"']):
                v_str = '"' + v_str.replace('"', '\\"') + '"'
            lines.append(f"{k}: {v_str}")
    return "\n".join(lines) + "\n"


List = list  # for type hint above


# ---------------------------------------------------------------------------
# Form 1: 債権者一覧表 (creditor-list)
# ---------------------------------------------------------------------------


def build_creditor_list(out_dir: Path) -> None:
    tid = "creditor-list"
    yaml_doc = {
        "id": tid,
        "title": "債権者一覧表",
        "description": "自己破産・個人再生の申立に添付する債権者一覧表",
        "category": "破産・再生",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {
                "id": "case_title",
                "label": "事件名／申立人氏名",
                "type": "text",
                "required": True,
                "position": {"row": 2, "column": 2},
            },
            {
                "id": "submitted_date",
                "label": "作成日",
                "type": "date",
                "required": True,
                "position": {"row": 3, "column": 2},
            },
            {
                "id": "creditors",
                "label": "債権者一覧",
                "type": "table",
                "required": True,
                "range": {
                    "headerRow": 6,
                    "dataStartRow": 7,
                    "startColumn": 1,
                    "endRow": 30,
                    "endColumn": 7,
                },
                "columns": [
                    {"id": "no", "label": "№", "type": "number"},
                    {"id": "creditor_name", "label": "債権者名", "type": "text", "description": "正式名称で記載"},
                    {"id": "address", "label": "住所", "type": "text"},
                    {"id": "debt_kind", "label": "債権の種類", "type": "text", "description": "例: 貸付金 / 立替金 / カードローン / 保証債務"},
                    {"id": "principal", "label": "元金", "type": "number", "description": "円単位"},
                    {"id": "interest", "label": "利息・遅延損害金", "type": "number", "description": "円単位"},
                    {"id": "notes", "label": "備考", "type": "text", "description": "連帯保証人・担保の有無等"},
                ],
            },
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="債権者一覧表")
    wb.set_column_widths({1: 5, 2: 28, 3: 30, 4: 20, 5: 15, 6: 18, 7: 20})
    # Title block
    wb.merge(1, 1, 1, 7)
    wb.write_cell(1, 1, "債権者一覧表", bold=True)
    wb.write_cell(2, 1, "事件名／申立人:", bold=True)
    wb.write_cell(3, 1, "作成日:", bold=True)
    wb.merge(5, 1, 5, 7)
    wb.write_cell(5, 1, "（下表に債権者を順次記載）")
    # Table header row (row 6)
    wb.write_row(6, 1, ["№", "債権者名", "住所", "債権の種類", "元金(円)", "利息・遅延損害金(円)", "備考"], bold=True)
    # Sample row (row 7) — will be overwritten by /template-fill
    wb.write_row(7, 1, [1, "", "", "", "", "", ""])
    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 2: 遺産目録 (estate-inventory)
# ---------------------------------------------------------------------------


def build_estate_inventory(out_dir: Path) -> None:
    tid = "estate-inventory"
    yaml_doc = {
        "id": tid,
        "title": "遺産目録",
        "description": "遺産分割協議・相続放棄の検討に用いる財産目録",
        "category": "相続",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "decedent_name", "label": "被相続人氏名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "death_date", "label": "死亡年月日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "created_date", "label": "作成日", "type": "date", "required": True, "position": {"row": 4, "column": 2}},
            {
                "id": "positive_assets",
                "label": "積極財産（プラスの財産）",
                "type": "table",
                "required": True,
                "range": {"headerRow": 7, "dataStartRow": 8, "startColumn": 1, "endRow": 25, "endColumn": 5},
                "columns": [
                    {"id": "no", "label": "№", "type": "number"},
                    {"id": "asset_type", "label": "種別", "type": "text", "description": "例: 預貯金 / 不動産 / 有価証券 / 動産"},
                    {"id": "detail", "label": "内容", "type": "text", "description": "金融機関・所在地・物件名等"},
                    {"id": "value", "label": "評価額(円)", "type": "number"},
                    {"id": "notes", "label": "備考", "type": "text"},
                ],
            },
            {
                "id": "negative_assets",
                "label": "消極財産（マイナスの財産）",
                "type": "table",
                "required": False,
                "range": {"headerRow": 28, "dataStartRow": 29, "startColumn": 1, "endRow": 40, "endColumn": 5},
                "columns": [
                    {"id": "no", "label": "№", "type": "number"},
                    {"id": "debt_type", "label": "種別", "type": "text", "description": "例: 住宅ローン / 借入金 / 未払税金"},
                    {"id": "creditor", "label": "債権者", "type": "text"},
                    {"id": "value", "label": "金額(円)", "type": "number"},
                    {"id": "notes", "label": "備考", "type": "text"},
                ],
            },
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="遺産目録")
    wb.set_column_widths({1: 5, 2: 18, 3: 36, 4: 18, 5: 24})
    wb.merge(1, 1, 1, 5)
    wb.write_cell(1, 1, "遺 産 目 録", bold=True)
    wb.write_cell(2, 1, "被相続人氏名:", bold=True)
    wb.write_cell(3, 1, "死亡年月日:", bold=True)
    wb.write_cell(4, 1, "作成日:", bold=True)
    # Positive assets section
    wb.merge(6, 1, 6, 5)
    wb.write_cell(6, 1, "【積極財産（プラスの財産）】", bold=True)
    wb.write_row(7, 1, ["№", "種別", "内容", "評価額(円)", "備考"], bold=True)
    wb.write_row(8, 1, [1, "", "", "", ""])
    # Negative assets section
    wb.merge(27, 1, 27, 5)
    wb.write_cell(27, 1, "【消極財産（マイナスの財産）】", bold=True)
    wb.write_row(28, 1, ["№", "種別", "債権者", "金額(円)", "備考"], bold=True)
    wb.write_row(29, 1, [1, "", "", "", ""])
    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 3: 交通事故示談書 (settlement-traffic)
# ---------------------------------------------------------------------------


def build_settlement_traffic(out_dir: Path) -> None:
    tid = "settlement-traffic"
    yaml_doc = {
        "id": tid,
        "title": "交通事故示談書（雛形）",
        "description": "交通事故の損害賠償請求に係る示談書の基本雛形。任意保険会社・加害者との直接交渉後の合意書面として使用する",
        "category": "交通事故",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "victim_name", "label": "被害者（甲）氏名", "type": "text", "required": True, "position": {"row": 3, "column": 3}},
            {"id": "victim_address", "label": "被害者住所", "type": "text", "required": True, "position": {"row": 4, "column": 3}},
            {"id": "perpetrator_name", "label": "加害者（乙）氏名", "type": "text", "required": True, "position": {"row": 5, "column": 3}},
            {"id": "perpetrator_address", "label": "加害者住所", "type": "text", "required": True, "position": {"row": 6, "column": 3}},
            {"id": "insurance_company", "label": "加害者側保険会社", "type": "text", "required": False, "position": {"row": 7, "column": 3}},
            {"id": "accident_date", "label": "事故発生日時", "type": "text", "required": True, "position": {"row": 9, "column": 3}},
            {"id": "accident_place", "label": "事故発生場所", "type": "text", "required": True, "position": {"row": 10, "column": 3}},
            {"id": "accident_circumstances", "label": "事故の態様", "type": "textarea", "required": True, "position": {"row": 11, "column": 3}},
            {"id": "injury", "label": "被害者の傷害", "type": "textarea", "required": False, "position": {"row": 12, "column": 3}},
            {"id": "settlement_amount", "label": "示談金総額(円)", "type": "number", "required": True, "position": {"row": 14, "column": 3}},
            {"id": "already_paid", "label": "既払額(自賠責・任意保険等、円)", "type": "number", "required": False, "position": {"row": 15, "column": 3}},
            {"id": "net_payment", "label": "本示談金による追加支払額(円)", "type": "number", "required": True, "position": {"row": 16, "column": 3}},
            {"id": "payment_method", "label": "支払方法", "type": "text", "required": True, "position": {"row": 17, "column": 3}},
            {"id": "payment_deadline", "label": "支払期限", "type": "date", "required": True, "position": {"row": 18, "column": 3}},
            {"id": "settlement_date", "label": "示談成立日", "type": "date", "required": True, "position": {"row": 22, "column": 3}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="交通事故示談書")
    wb.set_column_widths({1: 4, 2: 24, 3: 50})
    wb.merge(1, 1, 1, 3)
    wb.write_cell(1, 1, "示　談　書", bold=True)

    # 当事者
    wb.merge(2, 1, 2, 3)
    wb.write_cell(2, 1, "【当事者】", bold=True)
    wb.write_cell(3, 2, "被害者（甲）氏名:")
    wb.write_cell(4, 2, "被害者住所:")
    wb.write_cell(5, 2, "加害者（乙）氏名:")
    wb.write_cell(6, 2, "加害者住所:")
    wb.write_cell(7, 2, "加害者側保険会社:")

    # 事故の内容
    wb.merge(8, 1, 8, 3)
    wb.write_cell(8, 1, "【事故の内容】", bold=True)
    wb.write_cell(9, 2, "発生日時:")
    wb.write_cell(10, 2, "発生場所:")
    wb.write_cell(11, 2, "事故の態様:")
    wb.write_cell(12, 2, "被害者の傷害:")

    # 示談金
    wb.merge(13, 1, 13, 3)
    wb.write_cell(13, 1, "【示談金】", bold=True)
    wb.write_cell(14, 2, "示談金総額(円):")
    wb.write_cell(15, 2, "既払額(円):")
    wb.write_cell(16, 2, "本示談金による追加支払額(円):")
    wb.write_cell(17, 2, "支払方法:")
    wb.write_cell(18, 2, "支払期限:")

    # 清算条項（標準条項）
    wb.merge(19, 1, 19, 3)
    wb.write_cell(19, 1, "【清算条項】", bold=True)
    wb.merge(20, 1, 20, 3)
    wb.write_cell(20, 1, "甲乙は、上記の示談金の授受をもって本件事故に関する一切の紛争を円満に解決したことを相互に確認し、今後名目を問わず互いに何らの請求もしない。")

    # 成立
    wb.merge(21, 1, 21, 3)
    wb.write_cell(21, 1, "【示談の成立】", bold=True)
    wb.write_cell(22, 2, "示談成立日:")

    # 署名欄（雛形）
    wb.merge(24, 1, 24, 3)
    wb.write_cell(24, 1, "本示談書を 2 通作成し、甲乙各 1 通を保有する。", bold=True)
    wb.write_cell(26, 1, "甲（被害者）署名：　　　　　　　　　　　　　　　印")
    wb.write_cell(27, 1, "乙（加害者）署名：　　　　　　　　　　　　　　　印")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------


def main() -> int:
    builders = [
        ("creditor-list", build_creditor_list),
        ("estate-inventory", build_estate_inventory),
        ("settlement-traffic", build_settlement_traffic),
    ]
    for tid, builder in builders:
        out_dir = BUNDLED / tid
        out_dir.mkdir(parents=True, exist_ok=True)
        builder(out_dir)
        print(f"  [OK] {tid} → {out_dir}")
    print(f"\nbuilt {len(builders)} bundled forms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
