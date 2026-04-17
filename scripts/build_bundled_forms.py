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


# ---------------------------------------------------------------------------
# Form 4: 離婚協議書 (divorce-agreement)
#
# 法的根拠: 民法 763 条（協議離婚）、民法 766 条（親権・監護・養育費）、
#           民法 768 条（財産分与）、民法 709/710 条（慰謝料）、
#           厚生年金保険法 78 条の 2（年金分割の合意）
#
# 実務上の構成:
#   - 当事者（夫婦）の基本情報
#   - 離婚の合意
#   - 親権・監護権（子ごと）
#   - 養育費（金額・支払期間・支払方法）
#   - 面会交流
#   - 財産分与
#   - 慰謝料
#   - 年金分割（合意分割 or 3号分割）
#   - 清算条項
#
# 注: 公正証書化を前提とする場合、公証役場で追加の審査がある。本雛形は
#     協議書案の基本構成のみを提供する。
# ---------------------------------------------------------------------------


def build_divorce_agreement(out_dir: Path) -> None:
    tid = "divorce-agreement"
    yaml_doc = {
        "id": tid,
        "title": "離婚協議書",
        "description": "協議離婚時の合意内容を記載する書面。公正証書化前の草案として使用する",
        "category": "家事事件",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "husband_name", "label": "夫氏名", "type": "text", "required": True, "position": {"row": 3, "column": 3}},
            {"id": "husband_birth", "label": "夫生年月日", "type": "date", "required": True, "position": {"row": 4, "column": 3}},
            {"id": "husband_address", "label": "夫住所", "type": "text", "required": True, "position": {"row": 5, "column": 3}},
            {"id": "wife_name", "label": "妻氏名", "type": "text", "required": True, "position": {"row": 6, "column": 3}},
            {"id": "wife_birth", "label": "妻生年月日", "type": "date", "required": True, "position": {"row": 7, "column": 3}},
            {"id": "wife_address", "label": "妻住所", "type": "text", "required": True, "position": {"row": 8, "column": 3}},
            {"id": "marriage_date", "label": "婚姻日", "type": "date", "required": True, "position": {"row": 9, "column": 3}},
            {"id": "separation_date", "label": "別居開始日", "type": "date", "required": False, "position": {"row": 10, "column": 3}},
            {
                "id": "children",
                "label": "子の情報",
                "type": "table",
                "required": False,
                "range": {"headerRow": 13, "dataStartRow": 14, "startColumn": 1, "endRow": 18, "endColumn": 4},
                "columns": [
                    {"id": "child_name", "label": "氏名", "type": "text"},
                    {"id": "child_birth", "label": "生年月日", "type": "date"},
                    {"id": "custodian", "label": "親権者", "type": "text", "description": "夫 / 妻 / 共同"},
                    {"id": "notes", "label": "備考", "type": "text"},
                ],
            },
            {"id": "child_support_monthly", "label": "養育費月額（子1人あたり/円）", "type": "number", "required": False, "position": {"row": 20, "column": 3}},
            {"id": "child_support_period", "label": "養育費支払期間", "type": "text", "required": False, "position": {"row": 21, "column": 3}, "description": "例: 子が満20歳に達する月まで / 大学卒業まで"},
            {"id": "child_support_method", "label": "養育費支払方法", "type": "text", "required": False, "position": {"row": 22, "column": 3}, "description": "例: 毎月末日までに妻指定口座へ振込"},
            {"id": "visitation", "label": "面会交流", "type": "textarea", "required": False, "position": {"row": 23, "column": 3}, "description": "例: 月1回、第2土曜日、場所は双方協議"},
            {"id": "property_division", "label": "財産分与", "type": "textarea", "required": False, "position": {"row": 25, "column": 3}, "description": "対象財産の特定と分配方法"},
            {"id": "consolation_money", "label": "慰謝料（円）", "type": "number", "required": False, "position": {"row": 26, "column": 3}},
            {"id": "pension_split", "label": "年金分割の割合", "type": "text", "required": False, "position": {"row": 27, "column": 3}, "description": "例: 0.5 / 按分割合"},
            {"id": "agreement_date", "label": "合意日", "type": "date", "required": True, "position": {"row": 30, "column": 3}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="離婚協議書")
    wb.set_column_widths({1: 4, 2: 24, 3: 54})
    wb.merge(1, 1, 1, 3)
    wb.write_cell(1, 1, "離　婚　協　議　書", bold=True)

    wb.merge(2, 1, 2, 3)
    wb.write_cell(2, 1, "【当事者】", bold=True)
    for row, label in [(3, "夫氏名:"), (4, "夫生年月日:"), (5, "夫住所:"),
                        (6, "妻氏名:"), (7, "妻生年月日:"), (8, "妻住所:"),
                        (9, "婚姻日:"), (10, "別居開始日（該当あれば）:")]:
        wb.write_cell(row, 2, label)

    wb.merge(11, 1, 11, 3)
    wb.write_cell(11, 1, "【離婚の合意】 夫及び妻は、双方の協議により本日離婚することに合意した。", bold=False)

    wb.merge(12, 1, 12, 3)
    wb.write_cell(12, 1, "【子の情報・親権】", bold=True)
    wb.write_row(13, 1, ["氏名", "生年月日", "親権者", "備考"], bold=True)
    for r in range(14, 19):
        wb.write_cell(r, 1, "")

    wb.merge(19, 1, 19, 3)
    wb.write_cell(19, 1, "【養育費】", bold=True)
    wb.write_cell(20, 2, "月額（子1人/円）:")
    wb.write_cell(21, 2, "支払期間:")
    wb.write_cell(22, 2, "支払方法:")

    wb.write_cell(23, 2, "【面会交流】:")
    wb.merge(24, 1, 24, 3)
    wb.write_cell(24, 1, "【財産分与・慰謝料・年金分割】", bold=True)
    wb.write_cell(25, 2, "財産分与:")
    wb.write_cell(26, 2, "慰謝料（円）:")
    wb.write_cell(27, 2, "年金分割の割合:")

    wb.merge(28, 1, 28, 3)
    wb.write_cell(28, 1, "【清算条項】", bold=True)
    wb.merge(29, 1, 29, 3)
    wb.write_cell(29, 1, "夫及び妻は、本協議書に定めるもののほか、互いに財産上・精神上の請求をしないことを確認する。")

    wb.write_cell(30, 2, "合意日:")
    wb.merge(32, 1, 32, 3)
    wb.write_cell(32, 1, "本協議書を 2 通作成し、夫妻各 1 通を保有する。", bold=True)
    wb.write_cell(34, 1, "夫　署名：　　　　　　　　　　　　　　印")
    wb.write_cell(35, 1, "妻　署名：　　　　　　　　　　　　　　印")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 5: 内容証明郵便 (naiyou-shoumei)
#
# 法的根拠: 郵便法 48 条・49 条、郵便約款第148条
# 制約:
#   - 縦書き: 1行20字以内、1枚26行以内（合計 520 字/枚）
#   - 横書き: 1行26字・20行 / 1行20字・26行 / 1行13字・40行
#   - 句読点・括弧も字数に含む
#   - 同文 3 通（差出人控・郵便局保管・受取人送付）を作成
#   - 配達証明を付けるのが通例
#
# 本雛形は横書き（26字×20行）で設計する。XLSX ではセルに詰めて入力すれば
# 郵便局で字数チェック時に問題が出にくい形にしている。
# ---------------------------------------------------------------------------


def build_naiyou_shoumei(out_dir: Path) -> None:
    tid = "naiyou-shoumei"
    yaml_doc = {
        "id": tid,
        "title": "内容証明郵便（通知書）",
        "description": "内容証明郵便の通知書雛形。横書き 26字×20行 = 520字/枚の字数制限に留意する",
        "category": "一般民事",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "recipient_name", "label": "受取人氏名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "recipient_address", "label": "受取人住所", "type": "text", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "sender_name", "label": "差出人氏名", "type": "text", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "sender_address", "label": "差出人住所", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "document_title", "label": "表題", "type": "text", "required": True, "position": {"row": 7, "column": 1}, "description": "例: 通　知　書 / 催　告　書"},
            {"id": "body", "label": "本文", "type": "textarea", "required": True, "position": {"row": 9, "column": 1}, "description": "1行26字以内、合計20行以内に収める（520字/枚まで）。改行もカウント対象"},
            {"id": "issue_date", "label": "作成日", "type": "date", "required": True, "position": {"row": 31, "column": 2}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="内容証明")
    wb.set_column_widths({1: 50})
    wb.merge(1, 1, 1, 1)
    wb.write_cell(1, 1, "【郵便ラベル情報（本文ではない。参考情報）】", bold=True)
    wb.write_cell(2, 1, "受取人氏名:")
    wb.write_cell(3, 1, "受取人住所:")
    wb.write_cell(4, 1, "差出人氏名:")
    wb.write_cell(5, 1, "差出人住所:")

    wb.merge(6, 1, 6, 1)
    wb.write_cell(6, 1, "【本文（ここから下が郵便局に提出する内容証明本体）】", bold=True)
    wb.write_cell(7, 1, "[表題をここに記入  例: 通　知　書]")

    wb.merge(8, 1, 8, 1)
    wb.write_cell(8, 1, "[本文を 1行26字以内・合計20行以内 で記載]")
    # 本文エリア (行 9-28, 20行)
    for r in range(9, 29):
        wb.write_cell(r, 1, "")

    wb.merge(30, 1, 30, 1)
    wb.write_cell(30, 1, "【日付・差出人（本文末尾）】", bold=True)
    wb.write_cell(31, 1, "[作成日  例: 令和6年4月17日]")
    wb.write_cell(32, 1, "[差出人氏名・住所  上記「郵便ラベル情報」と同一]")

    wb.merge(34, 1, 34, 1)
    wb.write_cell(34, 1, "【郵便局持込時の注意】", bold=True)
    wb.merge(35, 1, 35, 1)
    wb.write_cell(35, 1, "同文 3 通（差出人控・郵便局保管・受取人送付）を用意する。配達証明付きで送付することが望ましい。")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 6: 未払残業代計算書 (overtime-calc-sheet)
#
# 法的根拠: 労働基準法 37 条（割増賃金）、同施行規則 19 条（1 時間あたりの賃金）
# 割増率:
#   - 法定時間外（原則 1日8時間 or 1週40時間超）: 1.25 倍以上
#   - 深夜（22:00-05:00）: 1.25 倍追加（時間外と重なれば 1.5 倍）
#   - 法定休日: 1.35 倍
#   - 60h/月 超の時間外: 1.5 倍（大企業は 2023/04 から、中小も適用）
# 消滅時効: 3 年（2020/04 改正以降発生分、民法・労基法 115 条改正）
#
# 1 時間あたり賃金 = 月給 / 1ヶ月平均所定労働時間
# 1ヶ月平均所定労働時間 = (365 - 年間休日) × 1日所定労働時間 ÷ 12
# ---------------------------------------------------------------------------


def build_overtime_calc_sheet(out_dir: Path) -> None:
    tid = "overtime-calc-sheet"
    yaml_doc = {
        "id": tid,
        "title": "未払残業代計算書",
        "description": "労基法 37 条に基づく未払割増賃金の計算書。時効（3年）を踏まえた月別集計",
        "category": "労働",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "employee_name", "label": "労働者氏名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "employer_name", "label": "使用者名称", "type": "text", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "employment_start", "label": "雇用開始日", "type": "date", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "base_monthly_salary", "label": "基本給（月額/円）", "type": "number", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "monthly_work_hours", "label": "1ヶ月平均所定労働時間（h）", "type": "number", "required": True, "position": {"row": 6, "column": 2}, "description": "(365 - 年間休日) × 1日所定労働時間 ÷ 12"},
            {"id": "hourly_wage", "label": "1 時間あたり賃金（円）", "type": "number", "required": True, "position": {"row": 7, "column": 2}, "description": "= 基本給 ÷ 1ヶ月平均所定労働時間"},
            {
                "id": "monthly_log",
                "label": "月別残業時間記録",
                "type": "table",
                "required": True,
                "range": {"headerRow": 10, "dataStartRow": 11, "startColumn": 1, "endRow": 46, "endColumn": 8},
                "columns": [
                    {"id": "year_month", "label": "年月", "type": "text", "description": "例: 令和5年4月"},
                    {"id": "overtime_h", "label": "法定時間外(h)", "type": "number", "description": "1日8h / 週40h 超"},
                    {"id": "night_h", "label": "深夜(h)", "type": "number", "description": "22:00-05:00"},
                    {"id": "holiday_h", "label": "法定休日(h)", "type": "number"},
                    {"id": "over_60h", "label": "60h超(h)", "type": "number", "description": "月60h 超の時間外"},
                    {"id": "overtime_amount", "label": "時間外1.25(円)", "type": "number"},
                    {"id": "night_amount", "label": "深夜0.25追加(円)", "type": "number"},
                    {"id": "holiday_amount", "label": "休日1.35(円)", "type": "number"},
                ],
            },
            {"id": "total_unpaid", "label": "未払総額（円）", "type": "number", "required": True, "position": {"row": 48, "column": 2}},
            {"id": "created_date", "label": "作成日", "type": "date", "required": True, "position": {"row": 50, "column": 2}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="未払残業代計算書")
    wb.set_column_widths({1: 14, 2: 14, 3: 12, 4: 14, 5: 12, 6: 16, 7: 18, 8: 16})
    wb.merge(1, 1, 1, 8)
    wb.write_cell(1, 1, "未払残業代計算書", bold=True)

    wb.write_cell(2, 1, "労働者氏名:")
    wb.write_cell(3, 1, "使用者名称:")
    wb.write_cell(4, 1, "雇用開始日:")
    wb.write_cell(5, 1, "基本給（月額/円）:")
    wb.write_cell(6, 1, "1ヶ月平均所定労働時間:")
    wb.write_cell(7, 1, "1時間あたり賃金:")

    wb.merge(9, 1, 9, 8)
    wb.write_cell(9, 1, "【月別未払賃金計算（消滅時効: 3 年以内）】", bold=True)
    wb.write_row(10, 1, ["年月", "法定時間外(h)", "深夜(h)", "法定休日(h)", "60h超(h)",
                         "時間外×1.25(円)", "深夜+0.25(円)", "休日×1.35(円)"], bold=True)
    for r in range(11, 47):
        wb.write_cell(r, 1, "")

    wb.merge(47, 1, 47, 8)
    wb.write_cell(47, 1, "【集計】", bold=True)
    wb.write_cell(48, 1, "未払総額（円）:")
    wb.write_cell(50, 1, "作成日:")

    wb.merge(52, 1, 52, 8)
    wb.write_cell(52, 1, "※ 2020/04 改正以降発生分の消滅時効は 3 年（従前は 2 年）。遅延損害金は年 3 %（法定利率 2020/04-）。", bold=False)

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 7: 訴状（貸金返還請求）(complaint-loan-repayment)
#
# 法的根拠: 民事訴訟法 134 条（訴状の記載事項）、民事訴訟規則 53 条
# 必要的記載事項:
#   - 当事者（原告・被告）
#   - 法定代理人・訴訟代理人
#   - 請求の趣旨
#   - 請求の原因
#   - 証拠方法
#   - 附属書類（証拠・委任状等）
#   - 事件名・事件の表示（裁判所指定）
#
# 訴額の算定基準: 請求金額（貸金返還は元本のみ、利息は不算入）
# 貼用印紙額: 民事訴訟費用等法別表第一
# ---------------------------------------------------------------------------


def build_complaint_loan(out_dir: Path) -> None:
    tid = "complaint-loan-repayment"
    yaml_doc = {
        "id": tid,
        "title": "訴状（貸金返還請求）",
        "description": "貸金返還請求訴訟の訴状雛形。民事訴訟法 134 条の必要的記載事項を網羅",
        "category": "民事訴訟",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "宛先裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "例: 東京地方裁判所 民事部 御中"},
            {"id": "filing_date", "label": "提出日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "plaintiff_name", "label": "原告氏名", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "plaintiff_address", "label": "原告住所", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "plaintiff_attorney", "label": "原告訴訟代理人", "type": "text", "required": False, "position": {"row": 8, "column": 2}},
            {"id": "defendant_name", "label": "被告氏名", "type": "text", "required": True, "position": {"row": 10, "column": 2}},
            {"id": "defendant_address", "label": "被告住所", "type": "text", "required": True, "position": {"row": 11, "column": 2}},
            {"id": "claim_amount", "label": "請求金額（元本、円）", "type": "number", "required": True, "position": {"row": 13, "column": 2}},
            {"id": "interest_rate", "label": "約定利率（年率%）", "type": "text", "required": False, "position": {"row": 14, "column": 2}, "description": "例: 年15% / 約定なし"},
            {"id": "interest_start_date", "label": "利息起算日", "type": "date", "required": False, "position": {"row": 15, "column": 2}},
            {"id": "suit_value", "label": "訴訟物の価額（円）", "type": "number", "required": True, "position": {"row": 17, "column": 2}, "description": "元本と同額（利息は不算入）"},
            {"id": "stamp_fee", "label": "貼用印紙額（円）", "type": "number", "required": True, "position": {"row": 18, "column": 2}},
            {"id": "lending_date", "label": "貸付日", "type": "date", "required": True, "position": {"row": 21, "column": 2}},
            {"id": "repayment_deadline", "label": "返済期日", "type": "date", "required": True, "position": {"row": 22, "column": 2}},
            {"id": "claim_reason_detail", "label": "請求の原因詳細", "type": "textarea", "required": True, "position": {"row": 23, "column": 2}, "description": "貸付の経緯、催告の事実、現在までの不払い状況"},
            {"id": "evidence_list", "label": "証拠方法", "type": "textarea", "required": True, "position": {"row": 25, "column": 2}, "description": "例: 甲第1号証 金銭消費貸借契約書 / 甲第2号証 催告書"},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="訴状")
    wb.set_column_widths({1: 22, 2: 56})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "訴　　状", bold=True)
    wb.write_cell(2, 1, "宛先裁判所:")
    wb.write_cell(3, 1, "提出日:")
    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "事件名:　貸金返還請求事件", bold=True)

    wb.merge(5, 1, 5, 2)
    wb.write_cell(5, 1, "【当事者】", bold=True)
    wb.write_cell(6, 1, "原告氏名:")
    wb.write_cell(7, 1, "原告住所:")
    wb.write_cell(8, 1, "原告訴訟代理人:")
    wb.write_cell(10, 1, "被告氏名:")
    wb.write_cell(11, 1, "被告住所:")

    wb.merge(12, 1, 12, 2)
    wb.write_cell(12, 1, "【請求の趣旨】", bold=True)
    wb.write_cell(13, 1, "請求金額（元本/円）:")
    wb.write_cell(14, 1, "約定利率:")
    wb.write_cell(15, 1, "利息起算日:")
    wb.merge(16, 1, 16, 2)
    wb.write_cell(16, 1, "1. 被告は、原告に対し、金 [請求金額] 円及びこれに対する [利息起算日] から支払済みまで年 [利率] の割合による金員を支払え。")

    wb.write_cell(17, 1, "訴訟物の価額（円）:")
    wb.write_cell(18, 1, "貼用印紙額（円）:")

    wb.merge(20, 1, 20, 2)
    wb.write_cell(20, 1, "【請求の原因】", bold=True)
    wb.write_cell(21, 1, "貸付日:")
    wb.write_cell(22, 1, "返済期日:")
    wb.write_cell(23, 1, "請求の原因詳細:")

    wb.merge(24, 1, 24, 2)
    wb.write_cell(24, 1, "【証拠方法・附属書類】", bold=True)
    wb.write_cell(25, 1, "証拠方法:")
    wb.merge(26, 1, 26, 2)
    wb.write_cell(26, 1, "附属書類: 訴状副本 1 通、証拠書類副本 各 1 通、委任状 1 通")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 8: 答弁書 (answer-generic)
#
# 法的根拠: 民事訴訟規則 80 条（答弁書の記載事項）
# 構成:
#   - 事件番号・当事者表示
#   - 請求の趣旨に対する答弁
#   - 請求の原因に対する認否（認める / 否認する / 不知）
#   - 抗弁（あれば）
#   - 証拠方法
# ---------------------------------------------------------------------------


def build_answer_generic(out_dir: Path) -> None:
    tid = "answer-generic"
    yaml_doc = {
        "id": tid,
        "title": "答弁書（民事訴訟）",
        "description": "民事訴訟の答弁書雛形。請求の趣旨に対する答弁・原因に対する認否・抗弁を記載",
        "category": "民事訴訟",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "宛先裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "case_number", "label": "事件番号", "type": "text", "required": True, "position": {"row": 3, "column": 2}, "description": "例: 令和6年（ワ）第1234号"},
            {"id": "case_name", "label": "事件名", "type": "text", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "filing_date", "label": "提出日", "type": "date", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "plaintiff_name", "label": "原告氏名", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "defendant_name", "label": "被告氏名", "type": "text", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "defendant_address", "label": "被告住所", "type": "text", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "defendant_attorney", "label": "被告訴訟代理人", "type": "text", "required": False, "position": {"row": 10, "column": 2}},
            {"id": "answer_to_claims", "label": "請求の趣旨に対する答弁", "type": "textarea", "required": True, "position": {"row": 12, "column": 2}, "description": "例: 1. 原告の請求をいずれも棄却する。 2. 訴訟費用は原告の負担とする。"},
            {
                "id": "ninhi_table",
                "label": "請求の原因に対する認否",
                "type": "table",
                "required": True,
                "range": {"headerRow": 15, "dataStartRow": 16, "startColumn": 1, "endRow": 25, "endColumn": 3},
                "columns": [
                    {"id": "paragraph", "label": "訴状段落", "type": "text", "description": "例: 訴状第1項"},
                    {"id": "content_summary", "label": "原告主張の要旨", "type": "text"},
                    {"id": "ninhi", "label": "認否", "type": "text", "description": "認める / 否認する / 一部認める / 不知"},
                ],
            },
            {"id": "abuse_defense", "label": "抗弁", "type": "textarea", "required": False, "position": {"row": 27, "column": 2}, "description": "例: 弁済の抗弁 / 消滅時効の抗弁 / 相殺の抗弁"},
            {"id": "evidence_list", "label": "証拠方法", "type": "textarea", "required": False, "position": {"row": 29, "column": 2}, "description": "例: 乙第1号証 領収書"},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="答弁書")
    wb.set_column_widths({1: 22, 2: 50})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "答　弁　書", bold=True)
    wb.write_cell(2, 1, "宛先裁判所:")
    wb.write_cell(3, 1, "事件番号:")
    wb.write_cell(4, 1, "事件名:")
    wb.write_cell(5, 1, "提出日:")

    wb.merge(6, 1, 6, 2)
    wb.write_cell(6, 1, "【当事者の表示】", bold=True)
    wb.write_cell(7, 1, "原告:")
    wb.write_cell(8, 1, "被告:")
    wb.write_cell(9, 1, "被告住所:")
    wb.write_cell(10, 1, "被告訴訟代理人:")

    wb.merge(11, 1, 11, 2)
    wb.write_cell(11, 1, "【請求の趣旨に対する答弁】", bold=True)
    wb.write_cell(12, 1, "答弁:")

    wb.merge(14, 1, 14, 3)
    wb.write_cell(14, 1, "【請求の原因に対する認否】", bold=True)
    wb.write_row(15, 1, ["訴状段落", "原告主張の要旨", "認否"], bold=True)
    for r in range(16, 26):
        wb.write_cell(r, 1, "")

    wb.merge(26, 1, 26, 2)
    wb.write_cell(26, 1, "【抗弁】", bold=True)
    wb.write_cell(27, 1, "抗弁:")

    wb.merge(28, 1, 28, 2)
    wb.write_cell(28, 1, "【証拠方法】", bold=True)
    wb.write_cell(29, 1, "証拠方法:")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 9: 相続放棄申述書 (inheritance-renunciation)
#
# 法的根拠: 民法 915 条（3ヶ月の熟慮期間）、民法 938 条（放棄の方式）
#           家事事件手続法 201 条（相続放棄の申述）
# 管轄: 被相続人の最後の住所地を管轄する家庭裁判所
# 期間: 自己のために相続開始があったことを知った時から 3 ヶ月以内
# 必要書類: 申述書 + 被相続人の住民票除票 + 申述人の戸籍謄本 + 被相続人との関係を示す戸籍 + 収入印紙 800 円 + 連絡用切手
# ---------------------------------------------------------------------------


def build_inheritance_renunciation(out_dir: Path) -> None:
    tid = "inheritance-renunciation"
    yaml_doc = {
        "id": tid,
        "title": "相続放棄申述書",
        "description": "家庭裁判所提出用の相続放棄申述書。3ヶ月の熟慮期間に留意",
        "category": "相続",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄家裁", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "被相続人の最後の住所地を管轄する家庭裁判所"},
            {"id": "filing_date", "label": "申述日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "applicant_honseki", "label": "申述人本籍", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "applicant_address", "label": "申述人住所", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "applicant_name", "label": "申述人氏名", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "applicant_birth", "label": "申述人生年月日", "type": "date", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "applicant_occupation", "label": "申述人職業", "type": "text", "required": False, "position": {"row": 9, "column": 2}},
            {"id": "decedent_honseki", "label": "被相続人本籍", "type": "text", "required": True, "position": {"row": 11, "column": 2}},
            {"id": "decedent_last_address", "label": "被相続人最後の住所", "type": "text", "required": True, "position": {"row": 12, "column": 2}},
            {"id": "decedent_name", "label": "被相続人氏名", "type": "text", "required": True, "position": {"row": 13, "column": 2}},
            {"id": "decedent_death_date", "label": "被相続人死亡日", "type": "date", "required": True, "position": {"row": 14, "column": 2}},
            {"id": "relationship", "label": "被相続人との関係", "type": "text", "required": True, "position": {"row": 15, "column": 2}, "description": "例: 長男 / 配偶者 / 兄"},
            {"id": "aware_date", "label": "相続開始を知った日", "type": "date", "required": True, "position": {"row": 17, "column": 2}, "description": "3 ヶ月の熟慮期間の起算日"},
            {"id": "renunciation_reason", "label": "放棄の理由", "type": "textarea", "required": True, "position": {"row": 18, "column": 2}, "description": "例: 被相続人に多額の債務があるため / 他の相続人に相続させたいため"},
            {"id": "estate_summary", "label": "相続財産の概略", "type": "textarea", "required": False, "position": {"row": 20, "column": 2}, "description": "積極財産・消極財産の概算"},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="相続放棄申述書")
    wb.set_column_widths({1: 22, 2: 50})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "相続放棄申述書", bold=True)
    wb.write_cell(2, 1, "管轄家裁:")
    wb.write_cell(3, 1, "申述日:")

    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "【申述人】", bold=True)
    for row, label in [(5, "本籍:"), (6, "住所:"), (7, "氏名:"), (8, "生年月日:"), (9, "職業:")]:
        wb.write_cell(row, 1, label)

    wb.merge(10, 1, 10, 2)
    wb.write_cell(10, 1, "【被相続人】", bold=True)
    for row, label in [(11, "本籍:"), (12, "最後の住所:"), (13, "氏名:"), (14, "死亡日:"), (15, "申述人との関係:")]:
        wb.write_cell(row, 1, label)

    wb.merge(16, 1, 16, 2)
    wb.write_cell(16, 1, "【相続放棄の事由】", bold=True)
    wb.write_cell(17, 1, "相続開始を知った日:")
    wb.write_cell(18, 1, "放棄の理由:")

    wb.merge(19, 1, 19, 2)
    wb.write_cell(19, 1, "【相続財産の概略】", bold=True)
    wb.write_cell(20, 1, "相続財産:")

    wb.merge(22, 1, 22, 2)
    wb.write_cell(22, 1, "【申述】 上記のとおり相続を放棄します。", bold=True)

    wb.merge(24, 1, 24, 2)
    wb.write_cell(24, 1, "※ 期間: 自己のために相続開始があったことを知った時から 3 ヶ月以内（民法 915 条）")
    wb.merge(25, 1, 25, 2)
    wb.write_cell(25, 1, "※ 必要書類: 本書 + 被相続人の住民票除票 + 申述人の戸籍謄本 + 関係を示す戸籍 + 収入印紙 800 円 + 連絡用切手")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 10: 遺産分割協議書 (inheritance-division-agreement)
#
# 法的根拠: 民法 906 条（遺産分割の基準）、民法 907 条（分割の協議・審判）
# 必要: 相続人全員の合意・署名・実印押印
# 登記実務: 不動産の相続登記に本協議書が必要（戸籍一式+印鑑証明書と合わせて）
# 注: 戸籍による相続人の特定が前提。本雛形は協議成立後の記載用
# ---------------------------------------------------------------------------


def build_inheritance_division(out_dir: Path) -> None:
    tid = "inheritance-division-agreement"
    yaml_doc = {
        "id": tid,
        "title": "遺産分割協議書",
        "description": "相続人全員の合意による遺産分割の書面。不動産の相続登記等で使用",
        "category": "相続",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "decedent_name", "label": "被相続人氏名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "decedent_death_date", "label": "被相続人死亡日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "decedent_last_address", "label": "被相続人最後の住所", "type": "text", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "decedent_honseki", "label": "被相続人本籍", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {
                "id": "heirs",
                "label": "相続人（全員）",
                "type": "table",
                "required": True,
                "range": {"headerRow": 8, "dataStartRow": 9, "startColumn": 1, "endRow": 18, "endColumn": 4},
                "columns": [
                    {"id": "name", "label": "氏名", "type": "text"},
                    {"id": "relationship", "label": "被相続人との続柄", "type": "text"},
                    {"id": "address", "label": "住所", "type": "text"},
                    {"id": "seal_confirmed", "label": "印鑑証明取得済", "type": "text", "description": "はい / いいえ"},
                ],
            },
            {
                "id": "allocations",
                "label": "遺産の分割内容",
                "type": "table",
                "required": True,
                "range": {"headerRow": 21, "dataStartRow": 22, "startColumn": 1, "endRow": 40, "endColumn": 4},
                "columns": [
                    {"id": "asset_type", "label": "財産種別", "type": "text", "description": "不動産 / 預貯金 / 有価証券 / 動産 等"},
                    {"id": "detail", "label": "詳細（所在・金融機関等）", "type": "text"},
                    {"id": "value", "label": "評価額(円)", "type": "number"},
                    {"id": "acquirer", "label": "取得者", "type": "text", "description": "相続人の氏名"},
                ],
            },
            {"id": "agreement_date", "label": "協議成立日", "type": "date", "required": True, "position": {"row": 42, "column": 2}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="遺産分割協議書")
    wb.set_column_widths({1: 4, 2: 26, 3: 40, 4: 24})
    wb.merge(1, 1, 1, 4)
    wb.write_cell(1, 1, "遺産分割協議書", bold=True)

    wb.write_cell(2, 1, "被相続人氏名:")
    wb.write_cell(3, 1, "被相続人死亡日:")
    wb.write_cell(4, 1, "被相続人最後の住所:")
    wb.write_cell(5, 1, "被相続人本籍:")

    wb.merge(7, 1, 7, 4)
    wb.write_cell(7, 1, "【相続人】 被相続人の死亡により下記の者らが共同相続人となった。", bold=True)
    wb.write_row(8, 1, ["氏名", "続柄", "住所", "印鑑証明取得済"], bold=True)
    for r in range(9, 19):
        wb.write_cell(r, 1, "")

    wb.merge(20, 1, 20, 4)
    wb.write_cell(20, 1, "【遺産の分割】 相続人全員の協議により、下記のとおり遺産を分割する。", bold=True)
    wb.write_row(21, 1, ["財産種別", "詳細（所在・金融機関等）", "評価額(円)", "取得者"], bold=True)
    for r in range(22, 41):
        wb.write_cell(r, 1, "")

    wb.merge(41, 1, 41, 4)
    wb.write_cell(41, 1, "【協議の成立】", bold=True)
    wb.write_cell(42, 1, "協議成立日:")

    wb.merge(44, 1, 44, 4)
    wb.write_cell(44, 1, "本協議書を相続人の数と同数作成し、各 1 通を保有する。上記合意を証するため、相続人全員が署名し、実印を押印する。", bold=True)

    wb.merge(46, 1, 46, 4)
    wb.write_cell(46, 1, "※ 不動産の相続登記・預貯金の名義変更には、本書に加え相続人全員の印鑑証明書・戸籍謄本等が必要となる。")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 11: 委任状 (power-of-attorney)
#
# 法的根拠: 弁護士法・民事訴訟法 55 条（訴訟代理人の権限）
# 一般委任事項と特別委任事項を区別する（民訴 55 条 2 項）
# 特別委任事項: 反訴・控訴・上告・訴えの取下げ・和解・請求の放棄・認諾等
# ---------------------------------------------------------------------------


def build_power_of_attorney(out_dir: Path) -> None:
    tid = "power-of-attorney"
    yaml_doc = {
        "id": tid,
        "title": "委任状（弁護士）",
        "description": "弁護士への事件処理委任。特別委任事項の個別承諾欄を含む",
        "category": "汎用",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "client_name", "label": "委任者氏名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "client_address", "label": "委任者住所", "type": "text", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "attorney_name", "label": "受任者（弁護士）氏名", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "law_firm", "label": "所属事務所", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "attorney_registration", "label": "弁護士登録番号", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "matter_description", "label": "委任事項", "type": "textarea", "required": True, "position": {"row": 9, "column": 2}, "description": "例: 甲野太郎を被告とする貸金返還請求事件に関する一切の件"},
            {
                "id": "special_powers",
                "label": "特別委任事項（該当に☑）",
                "type": "table",
                "required": True,
                "range": {"headerRow": 12, "dataStartRow": 13, "startColumn": 1, "endRow": 22, "endColumn": 2},
                "columns": [
                    {"id": "power", "label": "特別委任事項", "type": "text"},
                    {"id": "checked", "label": "承諾", "type": "text", "description": "☑ 承諾する / □ 承諾しない"},
                ],
            },
            {"id": "delegation_date", "label": "委任日", "type": "date", "required": True, "position": {"row": 24, "column": 2}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="委任状")
    wb.set_column_widths({1: 26, 2: 50})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "委　任　状", bold=True)
    wb.write_cell(2, 1, "委任者氏名:")
    wb.write_cell(3, 1, "委任者住所:")

    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "【受任者（弁護士）】", bold=True)
    wb.write_cell(5, 1, "受任者氏名:")
    wb.write_cell(6, 1, "所属事務所:")
    wb.write_cell(7, 1, "弁護士登録番号:")

    wb.merge(8, 1, 8, 2)
    wb.write_cell(8, 1, "【委任事項】", bold=True)
    wb.write_cell(9, 1, "事件・案件:")

    wb.merge(10, 1, 10, 2)
    wb.write_cell(10, 1, "委任者は、受任者に対し、上記事件について弁護士として必要な一切の法律行為を委任する。")

    wb.merge(11, 1, 11, 2)
    wb.write_cell(11, 1, "【特別委任事項】（民事訴訟法 55 条 2 項）", bold=True)
    wb.write_row(12, 1, ["特別委任事項", "承諾"], bold=True)
    # プリセットの特別委任事項
    special_items = [
        "反訴の提起",
        "訴えの取下げ",
        "和解・調停の成立",
        "請求の放棄・認諾",
        "控訴・上告・上告受理申立て",
        "復代理人の選任",
        "弁済の受領",
        "法律上の担保権の処分",
        "強制執行・保全処分",
        "第三者への再委任",
    ]
    for i, item in enumerate(special_items):
        wb.write_row(13 + i, 1, [item, "□ 承諾する / □ 承諾しない"])

    wb.merge(23, 1, 23, 2)
    wb.write_cell(23, 1, "【署名欄】", bold=True)
    wb.write_cell(24, 1, "委任日:")
    wb.write_cell(26, 1, "委任者　署名：　　　　　　　　　　　　　　印")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 12: 破産申立書（同時廃止）(bankruptcy-dohaishi)
#
# 法的根拠: 破産法 15 条（申立権者）、同 20-25 条（申立書の記載事項）、
#           破産規則 13 条
# 同時廃止: 破産財団をもって破産手続の費用を支弁するのに不足すると認められる
#           場合、破産手続開始と同時に廃止される（破産法 216 条）
# 本雛形は個人債務者の同時廃止型を想定
# ---------------------------------------------------------------------------


def build_bankruptcy_dohaishi(out_dir: Path) -> None:
    tid = "bankruptcy-dohaishi"
    yaml_doc = {
        "id": tid,
        "title": "破産申立書（同時廃止型・個人）",
        "description": "個人の自己破産（同時廃止）の申立書雛形。債権者一覧表・財産目録を別紙添付",
        "category": "破産・再生",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄地方裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "申立人住所地の地方裁判所"},
            {"id": "filing_date", "label": "申立日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "applicant_honseki", "label": "申立人本籍", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "applicant_address", "label": "申立人住所", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "applicant_name", "label": "申立人氏名", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "applicant_birth", "label": "申立人生年月日", "type": "date", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "applicant_occupation", "label": "申立人職業", "type": "text", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "monthly_income", "label": "月収（手取り/円）", "type": "number", "required": True, "position": {"row": 10, "column": 2}},
            {"id": "family_structure", "label": "家族構成", "type": "textarea", "required": True, "position": {"row": 11, "column": 2}, "description": "同居家族の氏名・続柄・収入の有無"},
            {"id": "total_debt", "label": "負債総額（円）", "type": "number", "required": True, "position": {"row": 13, "column": 2}, "description": "債権者一覧表の合計と一致させること"},
            {"id": "creditor_count", "label": "債権者数", "type": "number", "required": True, "position": {"row": 14, "column": 2}},
            {"id": "asset_total", "label": "資産総額（円）", "type": "number", "required": True, "position": {"row": 15, "column": 2}, "description": "財産目録の合計と一致させること"},
            {"id": "bankruptcy_reason", "label": "破産に至った事情", "type": "textarea", "required": True, "position": {"row": 17, "column": 2}, "description": "借入開始から現在に至る経緯・支払不能に陥った原因"},
            {"id": "immunity_requested", "label": "免責許可も申し立てるか", "type": "text", "required": True, "position": {"row": 19, "column": 2}, "description": "はい / いいえ（通常ははい）"},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="破産申立書")
    wb.set_column_widths({1: 24, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "破産手続開始申立書（同時廃止型・個人）", bold=True)
    wb.write_cell(2, 1, "管轄地方裁判所:")
    wb.write_cell(3, 1, "申立日:")

    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "【申立人】", bold=True)
    for row, label in [(5, "本籍:"), (6, "住所:"), (7, "氏名:"), (8, "生年月日:"),
                        (9, "職業:"), (10, "月収（手取り/円）:"), (11, "家族構成:")]:
        wb.write_cell(row, 1, label)

    wb.merge(12, 1, 12, 2)
    wb.write_cell(12, 1, "【負債・資産の概要】", bold=True)
    wb.write_cell(13, 1, "負債総額（円）:")
    wb.write_cell(14, 1, "債権者数:")
    wb.write_cell(15, 1, "資産総額（円）:")

    wb.merge(16, 1, 16, 2)
    wb.write_cell(16, 1, "【破産に至った事情】", bold=True)
    wb.write_cell(17, 1, "事情の説明:")

    wb.merge(18, 1, 18, 2)
    wb.write_cell(18, 1, "【免責許可申立】", bold=True)
    wb.write_cell(19, 1, "免責許可も同時申立:")

    wb.merge(21, 1, 21, 2)
    wb.write_cell(21, 1, "【申立の趣旨】", bold=True)
    wb.merge(22, 1, 22, 2)
    wb.write_cell(22, 1, "1. 申立人について破産手続を開始する。")
    wb.merge(23, 1, 23, 2)
    wb.write_cell(23, 1, "2. 免責を許可する。（免責許可申立を併せて行う場合）")

    wb.merge(25, 1, 25, 2)
    wb.write_cell(25, 1, "【添付書類】", bold=True)
    attachments = [
        "債権者一覧表（/template-install creditor-list で取得可）",
        "財産目録",
        "家計収支表（2ヶ月分以上）",
        "住民票の写し",
        "戸籍謄本",
        "給与明細書（直近2ヶ月分以上）",
        "源泉徴収票",
        "賃貸借契約書の写し（賃借物件に居住する場合）",
    ]
    for i, item in enumerate(attachments):
        wb.write_cell(26 + i, 1, f"  ・{item}")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 13: 労働審判申立書 (labor-tribunal-application)
#
# 法的根拠: 労働審判法 5 条（申立の方式）、同規則 9 条
# 3 回以内の期日で終結する迅速手続。通常訴訟へ移行する場合あり
# 申立手数料: 労働審判法 33 条（通常の訴え提起の 2 分の 1）
# ---------------------------------------------------------------------------


def build_labor_tribunal(out_dir: Path) -> None:
    tid = "labor-tribunal-application"
    yaml_doc = {
        "id": tid,
        "title": "労働審判申立書",
        "description": "労働審判法に基づく申立書。3期日以内の迅速手続",
        "category": "労働",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄地方裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "filing_date", "label": "申立日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "applicant_name", "label": "申立人（労働者）氏名", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "applicant_address", "label": "申立人住所", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "applicant_attorney", "label": "申立人代理人", "type": "text", "required": False, "position": {"row": 7, "column": 2}},
            {"id": "respondent_name", "label": "相手方（使用者）名称", "type": "text", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "respondent_address", "label": "相手方所在地", "type": "text", "required": True, "position": {"row": 10, "column": 2}},
            {"id": "respondent_representative", "label": "相手方代表者", "type": "text", "required": True, "position": {"row": 11, "column": 2}},
            {"id": "case_type", "label": "事件の種類", "type": "text", "required": True, "position": {"row": 13, "column": 2}, "description": "例: 解雇無効確認および賃金支払請求 / 未払残業代請求"},
            {"id": "application_summary", "label": "申立の趣旨", "type": "textarea", "required": True, "position": {"row": 14, "column": 2}, "description": "求める解決内容。例: 1. 相手方は申立人が雇用契約上の権利を有する地位にあることを確認する。 2. 相手方は申立人に対し、金○○円を支払え。"},
            {"id": "dispute_points", "label": "紛争の要点", "type": "textarea", "required": True, "position": {"row": 16, "column": 2}, "description": "雇用契約の内容・紛争発生の経緯・現在の状況を時系列で"},
            {"id": "predicted_issues", "label": "予想される争点", "type": "textarea", "required": True, "position": {"row": 18, "column": 2}, "description": "想定される相手方の反論と、それに対する立証計画"},
            {"id": "evidence_list", "label": "証拠方法", "type": "textarea", "required": True, "position": {"row": 20, "column": 2}, "description": "例: 甲第1号証 雇用契約書 / 甲第2号証 タイムカード"},
            {"id": "suit_value", "label": "請求額（訴額）(円)", "type": "number", "required": True, "position": {"row": 22, "column": 2}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="労働審判申立書")
    wb.set_column_widths({1: 24, 2: 54})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "労働審判手続申立書", bold=True)
    wb.write_cell(2, 1, "管轄地方裁判所:")
    wb.write_cell(3, 1, "申立日:")

    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "【申立人（労働者）】", bold=True)
    wb.write_cell(5, 1, "氏名:")
    wb.write_cell(6, 1, "住所:")
    wb.write_cell(7, 1, "代理人:")

    wb.merge(8, 1, 8, 2)
    wb.write_cell(8, 1, "【相手方（使用者）】", bold=True)
    wb.write_cell(9, 1, "名称:")
    wb.write_cell(10, 1, "所在地:")
    wb.write_cell(11, 1, "代表者:")

    wb.merge(12, 1, 12, 2)
    wb.write_cell(12, 1, "【事件の内容】", bold=True)
    wb.write_cell(13, 1, "事件の種類:")
    wb.write_cell(14, 1, "申立の趣旨:")

    wb.merge(15, 1, 15, 2)
    wb.write_cell(15, 1, "【紛争の経緯】", bold=True)
    wb.write_cell(16, 1, "紛争の要点:")

    wb.merge(17, 1, 17, 2)
    wb.write_cell(17, 1, "【争点】", bold=True)
    wb.write_cell(18, 1, "予想される争点:")

    wb.merge(19, 1, 19, 2)
    wb.write_cell(19, 1, "【証拠方法】", bold=True)
    wb.write_cell(20, 1, "証拠方法:")

    wb.merge(21, 1, 21, 2)
    wb.write_cell(21, 1, "【訴額】", bold=True)
    wb.write_cell(22, 1, "請求額（円）:")

    wb.merge(24, 1, 24, 2)
    wb.write_cell(24, 1, "※ 手数料: 通常訴訟の 1/2（労働審判法 33 条）")
    wb.merge(25, 1, 25, 2)
    wb.write_cell(25, 1, "※ 手続: 3 回以内の期日で終結（同法 15 条 2 項）。異議申立で通常訴訟に移行")

    wb.save(out_dir / f"{tid}.xlsx")


def main() -> int:
    builders = [
        # Phase 1 (v2.1.0)
        ("creditor-list", build_creditor_list),
        ("estate-inventory", build_estate_inventory),
        ("settlement-traffic", build_settlement_traffic),
        # Phase 2 (v2.2.0)
        ("divorce-agreement", build_divorce_agreement),
        ("naiyou-shoumei", build_naiyou_shoumei),
        ("overtime-calc-sheet", build_overtime_calc_sheet),
        ("complaint-loan-repayment", build_complaint_loan),
        ("answer-generic", build_answer_generic),
        ("inheritance-renunciation", build_inheritance_renunciation),
        ("inheritance-division-agreement", build_inheritance_division),
        ("power-of-attorney", build_power_of_attorney),
        ("bankruptcy-dohaishi", build_bankruptcy_dohaishi),
        ("labor-tribunal-application", build_labor_tribunal),
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
