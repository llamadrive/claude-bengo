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


# ---------------------------------------------------------------------------
# Form 14: 陳述書（家事）(statement-family)
#
# 法的根拠: 家事事件手続法 56条（書面の提出）、民事訴訟法 215条（書証）
# 用途: 家事事件（離婚調停・遺産分割・後見等）の当事者の主張・事情を書面化
# 構成: 氏名・住所・生年月日 / 本文 / 作成日 / 署名
# ---------------------------------------------------------------------------


def build_statement_family(out_dir: Path) -> None:
    tid = "statement-family"
    yaml_doc = {
        "id": tid,
        "title": "陳述書（家事事件）",
        "description": "家事調停・審判における当事者の陳述書。離婚・遺産分割・後見等で使用",
        "category": "家事事件",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "case_number", "label": "事件番号", "type": "text", "required": False, "position": {"row": 2, "column": 2}, "description": "例: 令和6年(家イ)第1234号"},
            {"id": "case_type", "label": "事件名", "type": "text", "required": True, "position": {"row": 3, "column": 2}, "description": "例: 夫婦関係調整調停事件"},
            {"id": "court_name", "label": "家庭裁判所", "type": "text", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "party_role", "label": "当事者の別", "type": "text", "required": True, "position": {"row": 6, "column": 2}, "description": "例: 申立人 / 相手方"},
            {"id": "statement_author_name", "label": "陳述者氏名", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "statement_author_birth", "label": "生年月日", "type": "date", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "statement_author_address", "label": "住所", "type": "text", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "statement_body", "label": "陳述内容", "type": "textarea", "required": True, "position": {"row": 12, "column": 1}, "description": "時系列順に事実を記載。推測・伝聞と自己体験を区別すること"},
            {"id": "declaration_date", "label": "作成日", "type": "date", "required": True, "position": {"row": 29, "column": 2}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="陳述書")
    wb.set_column_widths({1: 22, 2: 54})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "陳　述　書", bold=True)
    wb.write_cell(2, 1, "事件番号:")
    wb.write_cell(3, 1, "事件名:")
    wb.write_cell(4, 1, "家庭裁判所:")

    wb.merge(5, 1, 5, 2)
    wb.write_cell(5, 1, "【陳述者】", bold=True)
    wb.write_cell(6, 1, "当事者の別:")
    wb.write_cell(7, 1, "氏名:")
    wb.write_cell(8, 1, "生年月日:")
    wb.write_cell(9, 1, "住所:")

    wb.merge(10, 1, 10, 2)
    wb.write_cell(10, 1, "【陳述内容】", bold=True)
    wb.merge(11, 1, 11, 2)
    wb.write_cell(11, 1, "次のとおり陳述する。", bold=False)
    # 長文陳述ブロック（1 セル）
    for r in range(12, 28):
        wb.write_cell(r, 1, "")

    wb.merge(28, 1, 28, 2)
    wb.write_cell(28, 1, "【作成】", bold=True)
    wb.write_cell(29, 1, "作成日:")
    wb.merge(31, 1, 31, 2)
    wb.write_cell(31, 1, "陳述者　署名：　　　　　　　　　　　　　　印", bold=False)

    wb.merge(33, 1, 33, 2)
    wb.write_cell(33, 1, "※ 家事事件手続法 56条（書面の提出）。推測・伝聞と自己体験を区別し、事実のみを記載する。")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 15: 家事調停申立書 (family-mediation-application)
#
# 法的根拠: 家事事件手続法 244条（調停の申立）、同 255条（申立書の記載事項）
# 調停前置主義: 人事訴訟事件（離婚等）は原則として調停前置（家事事件手続法 257条）
# 申立費用: 収入印紙 1,200円（夫婦関係調整等）、連絡用郵便切手
# ---------------------------------------------------------------------------


def build_family_mediation(out_dir: Path) -> None:
    tid = "family-mediation-application"
    yaml_doc = {
        "id": tid,
        "title": "家事調停申立書（夫婦関係調整等）",
        "description": "離婚・養育費・面会交流・婚姻費用等の家事調停申立書雛形",
        "category": "家事事件",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄家庭裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "相手方の住所地を管轄する家裁（家事審判規則 129条）"},
            {"id": "filing_date", "label": "申立日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "mediation_type", "label": "調停種別", "type": "text", "required": True, "position": {"row": 4, "column": 2}, "description": "例: 夫婦関係調整（離婚） / 養育費請求 / 婚姻費用分担 / 面会交流"},
            {"id": "applicant_name", "label": "申立人氏名", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "applicant_address", "label": "申立人住所", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "applicant_birth", "label": "申立人生年月日", "type": "date", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "applicant_occupation", "label": "申立人職業", "type": "text", "required": False, "position": {"row": 9, "column": 2}},
            {"id": "respondent_name", "label": "相手方氏名", "type": "text", "required": True, "position": {"row": 11, "column": 2}},
            {"id": "respondent_address", "label": "相手方住所", "type": "text", "required": True, "position": {"row": 12, "column": 2}},
            {"id": "respondent_birth", "label": "相手方生年月日", "type": "date", "required": False, "position": {"row": 13, "column": 2}},
            {
                "id": "children",
                "label": "未成年の子",
                "type": "table",
                "required": False,
                "range": {"headerRow": 16, "dataStartRow": 17, "startColumn": 1, "endRow": 21, "endColumn": 3},
                "columns": [
                    {"id": "child_name", "label": "氏名", "type": "text"},
                    {"id": "child_birth", "label": "生年月日", "type": "date"},
                    {"id": "currently_with", "label": "現在の監護者", "type": "text"},
                ],
            },
            {"id": "application_summary", "label": "申立の趣旨", "type": "textarea", "required": True, "position": {"row": 23, "column": 2}, "description": "例: 1. 申立人と相手方は離婚する。 2. 長女○○の親権者を申立人と定める。"},
            {"id": "application_reason", "label": "申立の実情", "type": "textarea", "required": True, "position": {"row": 25, "column": 2}, "description": "婚姻の経緯、現在の問題状況、別居・話合いの経緯等"},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="家事調停申立書")
    wb.set_column_widths({1: 4, 2: 22, 3: 54})
    wb.merge(1, 1, 1, 3)
    wb.write_cell(1, 1, "家事調停申立書", bold=True)
    wb.write_cell(2, 2, "管轄家庭裁判所:")
    wb.write_cell(3, 2, "申立日:")
    wb.write_cell(4, 2, "調停種別:")

    wb.merge(5, 1, 5, 3)
    wb.write_cell(5, 1, "【申立人】", bold=True)
    for row, label in [(6, "氏名:"), (7, "住所:"), (8, "生年月日:"), (9, "職業:")]:
        wb.write_cell(row, 2, label)

    wb.merge(10, 1, 10, 3)
    wb.write_cell(10, 1, "【相手方】", bold=True)
    for row, label in [(11, "氏名:"), (12, "住所:"), (13, "生年月日:")]:
        wb.write_cell(row, 2, label)

    wb.merge(15, 1, 15, 3)
    wb.write_cell(15, 1, "【未成年の子】", bold=True)
    wb.write_row(16, 1, ["氏名", "生年月日", "現在の監護者"], bold=True)
    for r in range(17, 22):
        wb.write_cell(r, 1, "")

    wb.merge(22, 1, 22, 3)
    wb.write_cell(22, 1, "【申立の趣旨】", bold=True)
    wb.write_cell(23, 2, "趣旨:")

    wb.merge(24, 1, 24, 3)
    wb.write_cell(24, 1, "【申立の実情】", bold=True)
    wb.write_cell(25, 2, "実情:")

    wb.merge(27, 1, 27, 3)
    wb.write_cell(27, 1, "※ 管轄: 相手方の住所地の家庭裁判所（家事審判規則 129条）")
    wb.merge(28, 1, 28, 3)
    wb.write_cell(28, 1, "※ 手数料: 収入印紙 1,200円（事件類型により異なる）+ 連絡用郵便切手")
    wb.merge(29, 1, 29, 3)
    wb.write_cell(29, 1, "※ 調停前置: 人事訴訟事件は調停前置（家事事件手続法 257条）")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 16: 家計収支表 (household-budget)
#
# 用途: 自己破産・個人再生申立の添付資料
# 期間: 通常 2-3ヶ月分を並べて提出する
# ---------------------------------------------------------------------------


def build_household_budget(out_dir: Path) -> None:
    tid = "household-budget"
    yaml_doc = {
        "id": tid,
        "title": "家計収支表",
        "description": "自己破産・個人再生の申立添付資料。通常2-3ヶ月分を並べて提出",
        "category": "破産・再生",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "applicant_name", "label": "申立人氏名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "period_label", "label": "対象期間", "type": "text", "required": True, "position": {"row": 3, "column": 2}, "description": "例: 令和6年1月〜3月"},
            {"id": "family_count", "label": "同居家族数（本人含む）", "type": "number", "required": True, "position": {"row": 4, "column": 2}},
            {
                "id": "income_table",
                "label": "収入",
                "type": "table",
                "required": True,
                "range": {"headerRow": 7, "dataStartRow": 8, "startColumn": 1, "endRow": 13, "endColumn": 5},
                "columns": [
                    {"id": "item", "label": "項目", "type": "text", "description": "給与/賞与/年金/事業収入/児童手当/その他"},
                    {"id": "m1", "label": "1ヶ月目(円)", "type": "number"},
                    {"id": "m2", "label": "2ヶ月目(円)", "type": "number"},
                    {"id": "m3", "label": "3ヶ月目(円)", "type": "number"},
                    {"id": "notes", "label": "備考", "type": "text"},
                ],
            },
            {
                "id": "expense_table",
                "label": "支出",
                "type": "table",
                "required": True,
                "range": {"headerRow": 16, "dataStartRow": 17, "startColumn": 1, "endRow": 35, "endColumn": 5},
                "columns": [
                    {"id": "item", "label": "項目", "type": "text", "description": "家賃/食費/水道光熱費/通信費/医療費/教育費/保険料/交通費/その他"},
                    {"id": "m1", "label": "1ヶ月目(円)", "type": "number"},
                    {"id": "m2", "label": "2ヶ月目(円)", "type": "number"},
                    {"id": "m3", "label": "3ヶ月目(円)", "type": "number"},
                    {"id": "notes", "label": "備考", "type": "text"},
                ],
            },
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="家計収支表")
    wb.set_column_widths({1: 18, 2: 14, 3: 14, 4: 14, 5: 24})
    wb.merge(1, 1, 1, 5)
    wb.write_cell(1, 1, "家計収支表", bold=True)
    wb.write_cell(2, 1, "申立人氏名:")
    wb.write_cell(3, 1, "対象期間:")
    wb.write_cell(4, 1, "同居家族数:")

    wb.merge(6, 1, 6, 5)
    wb.write_cell(6, 1, "【収入】", bold=True)
    wb.write_row(7, 1, ["項目", "1ヶ月目(円)", "2ヶ月目(円)", "3ヶ月目(円)", "備考"], bold=True)
    for r in range(8, 14):
        wb.write_cell(r, 1, "")

    wb.merge(14, 1, 14, 5)
    wb.write_cell(14, 1, "【支出】", bold=True)
    wb.write_row(15, 1, ["項目", "1ヶ月目(円)", "2ヶ月目(円)", "3ヶ月目(円)", "備考"], bold=True)
    for r in range(16, 36):
        wb.write_cell(r, 1, "")

    wb.merge(37, 1, 37, 5)
    wb.write_cell(37, 1, "【収支】", bold=True)
    wb.write_cell(38, 1, "差引(収入-支出):")

    wb.merge(40, 1, 40, 5)
    wb.write_cell(40, 1, "※ 領収書・給与明細等、支出の裏付となる資料も合わせて提出すること")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 17: 個人再生申立書（小規模）(rehabilitation-small)
#
# 法的根拠: 民事再生法 221-245条（小規模個人再生）、同規則 100条以下
# 要件:
#   - 負債総額が住宅ローン除き 5,000万円以下
#   - 将来において継続的に収入を得る見込みがある
# 最低弁済額:
#   - 100万円未満: 負債総額
#   - 100-500万: 100万円
#   - 500-1,500万: 負債総額の 1/5
#   - 1,500-3,000万: 300万円
#   - 3,000-5,000万: 負債総額の 1/10
# 住宅資金特別条項: 住宅ローンは別枠で維持可能（民再 196-206条）
# ---------------------------------------------------------------------------


def build_rehabilitation_small(out_dir: Path) -> None:
    tid = "rehabilitation-small"
    yaml_doc = {
        "id": tid,
        "title": "個人再生申立書（小規模再生）",
        "description": "民事再生法 221条以下の小規模個人再生申立書雛形。住宅資金特別条項の適用も選択可能",
        "category": "破産・再生",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄地方裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "申立人の住所地を管轄する地裁（民再 5条）"},
            {"id": "filing_date", "label": "申立日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "applicant_name", "label": "申立人氏名", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "applicant_address", "label": "申立人住所", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "applicant_birth", "label": "申立人生年月日", "type": "date", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "applicant_occupation", "label": "職業・勤務先", "type": "text", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "monthly_income", "label": "月収（手取り/円）", "type": "number", "required": True, "position": {"row": 9, "column": 2}, "description": "将来の継続的収入見込みの根拠となる"},
            {"id": "total_debt_excluding_housing", "label": "負債総額（住宅ローン除く/円）", "type": "number", "required": True, "position": {"row": 11, "column": 2}, "description": "5,000万円以下が要件"},
            {"id": "housing_loan", "label": "住宅ローン残高（円）", "type": "number", "required": False, "position": {"row": 12, "column": 2}},
            {"id": "creditor_count", "label": "債権者数", "type": "number", "required": True, "position": {"row": 13, "column": 2}},
            {"id": "estimated_min_payment", "label": "最低弁済額（円）", "type": "number", "required": True, "position": {"row": 15, "column": 2}, "description": "負債総額に応じた法定基準（民再 231条2項）"},
            {"id": "payment_plan_years", "label": "弁済期間（年）", "type": "number", "required": True, "position": {"row": 16, "column": 2}, "description": "原則3年、特別の事情により最長5年"},
            {"id": "housing_special_clause", "label": "住宅資金特別条項の適用希望", "type": "text", "required": True, "position": {"row": 18, "column": 2}, "description": "はい / いいえ"},
            {"id": "rehabilitation_reason", "label": "再生に至った事情", "type": "textarea", "required": True, "position": {"row": 20, "column": 2}, "description": "借入開始・返済困難化の経緯と今後の返済可能性"},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="個人再生申立書")
    wb.set_column_widths({1: 26, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "小規模個人再生手続開始申立書", bold=True)
    wb.write_cell(2, 1, "管轄地方裁判所:")
    wb.write_cell(3, 1, "申立日:")

    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "【申立人】", bold=True)
    for row, label in [(5, "氏名:"), (6, "住所:"), (7, "生年月日:"), (8, "職業・勤務先:"), (9, "月収（手取り/円）:")]:
        wb.write_cell(row, 1, label)

    wb.merge(10, 1, 10, 2)
    wb.write_cell(10, 1, "【負債・弁済計画の概要】", bold=True)
    wb.write_cell(11, 1, "負債総額（住宅ローン除く/円）:")
    wb.write_cell(12, 1, "住宅ローン残高（円）:")
    wb.write_cell(13, 1, "債権者数:")
    wb.write_cell(15, 1, "最低弁済額（円）:")
    wb.write_cell(16, 1, "弁済期間（年）:")

    wb.merge(17, 1, 17, 2)
    wb.write_cell(17, 1, "【住宅資金特別条項】", bold=True)
    wb.write_cell(18, 1, "適用希望:")

    wb.merge(19, 1, 19, 2)
    wb.write_cell(19, 1, "【再生に至った事情】", bold=True)
    wb.write_cell(20, 1, "事情説明:")

    wb.merge(22, 1, 22, 2)
    wb.write_cell(22, 1, "【申立の趣旨】", bold=True)
    wb.merge(23, 1, 23, 2)
    wb.write_cell(23, 1, "1. 申立人について小規模個人再生手続を開始する。")
    wb.merge(24, 1, 24, 2)
    wb.write_cell(24, 1, "2.（住宅特別条項がある場合）住宅資金特別条項に基づく再生計画の認可を求める。")

    wb.merge(26, 1, 26, 2)
    wb.write_cell(26, 1, "【最低弁済額の法定基準（民再 231条2項）】", bold=True)
    wb.merge(27, 1, 27, 2)
    wb.write_cell(27, 1, "100万円未満: 負債総額 / 100-500万: 100万円 / 500-1,500万: 1/5 / 1,500-3,000万: 300万円 / 3,000-5,000万: 1/10")

    wb.merge(29, 1, 29, 2)
    wb.write_cell(29, 1, "※ 要件: 負債総額 5,000万円以下（住宅ローン除く）・将来継続的収入の見込み（民再 221条）")
    wb.merge(30, 1, 30, 2)
    wb.write_cell(30, 1, "※ 添付: 債権者一覧表・財産目録・家計収支表・給与明細等。`/template-install creditor-list household-budget` で取得可")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 18: 弁護人選任届 (criminal-defense-appointment)
#
# 法的根拠: 刑事訴訟法 30条（被告人・被疑者の弁護人選任）、32条、刑訴規則 17条
# 提出先: 事件が係属している裁判所・検察庁・警察署
# 連名: 被告人（または被疑者）と弁護人双方の署名押印
# ---------------------------------------------------------------------------


def build_criminal_defense_appointment(out_dir: Path) -> None:
    tid = "criminal-defense-appointment"
    yaml_doc = {
        "id": tid,
        "title": "弁護人選任届",
        "description": "刑事事件の弁護人選任届。被疑者段階・被告人段階・公判段階で都度提出",
        "category": "刑事弁護",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "submission_target", "label": "提出先", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "例: ○○地方裁判所 刑事部 御中 / ○○警察署長 殿"},
            {"id": "filing_date", "label": "提出日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "case_type", "label": "事件の段階", "type": "select", "required": True, "position": {"row": 4, "column": 2}, "options": ["被疑者段階", "被告人段階（起訴前）", "被告人段階（公判中）"]},
            {"id": "case_number", "label": "事件番号", "type": "text", "required": False, "position": {"row": 5, "column": 2}, "description": "例: 令和6年(わ)第1234号"},
            {"id": "suspect_name", "label": "被疑者・被告人氏名", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "suspect_address", "label": "住所", "type": "text", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "suspect_birth", "label": "生年月日", "type": "date", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "offense", "label": "罪名", "type": "text", "required": True, "position": {"row": 10, "column": 2}, "description": "例: 窃盗 / 傷害 / 詐欺"},
            {"id": "attorney_name", "label": "弁護人氏名", "type": "text", "required": True, "position": {"row": 12, "column": 2}},
            {"id": "law_firm", "label": "所属事務所", "type": "text", "required": True, "position": {"row": 13, "column": 2}},
            {"id": "firm_address", "label": "事務所住所", "type": "text", "required": True, "position": {"row": 14, "column": 2}},
            {"id": "firm_phone", "label": "事務所電話", "type": "text", "required": True, "position": {"row": 15, "column": 2}},
            {"id": "attorney_registration", "label": "弁護士登録番号", "type": "text", "required": True, "position": {"row": 16, "column": 2}},
            {"id": "bar_association", "label": "所属弁護士会", "type": "text", "required": True, "position": {"row": 17, "column": 2}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="弁護人選任届")
    wb.set_column_widths({1: 22, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "弁護人選任届", bold=True)
    wb.write_cell(2, 1, "提出先:")
    wb.write_cell(3, 1, "提出日:")
    wb.write_cell(4, 1, "事件の段階:")
    wb.write_cell(5, 1, "事件番号:")

    wb.merge(6, 1, 6, 2)
    wb.write_cell(6, 1, "【被疑者・被告人】", bold=True)
    for row, label in [(7, "氏名:"), (8, "住所:"), (9, "生年月日:"), (10, "罪名:")]:
        wb.write_cell(row, 1, label)

    wb.merge(11, 1, 11, 2)
    wb.write_cell(11, 1, "【弁護人】", bold=True)
    for row, label in [(12, "氏名:"), (13, "所属事務所:"), (14, "事務所住所:"),
                        (15, "事務所電話:"), (16, "弁護士登録番号:"), (17, "所属弁護士会:")]:
        wb.write_cell(row, 1, label)

    wb.merge(19, 1, 19, 2)
    wb.write_cell(19, 1, "上記の事件について、上記の弁護士を弁護人に選任する。", bold=True)

    wb.merge(21, 1, 21, 2)
    wb.write_cell(21, 1, "被疑者・被告人　署名：　　　　　　　　　　　　　　印")
    wb.merge(22, 1, 22, 2)
    wb.write_cell(22, 1, "弁護人　　　　　署名：　　　　　　　　　　　　　　印")

    wb.merge(24, 1, 24, 2)
    wb.write_cell(24, 1, "※ 提出は原則選任ごとに行う（被疑者段階→起訴後→上訴審で新たに提出）")
    wb.merge(25, 1, 25, 2)
    wb.write_cell(25, 1, "※ 法的根拠: 刑事訴訟法 30条・32条、刑訴規則 17条")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 19: 刑事示談書 (criminal-settlement)
#
# 法的根拠: 刑法上の一般情状酌量要素（量刑実務）、民法 709条
# 目的: 被害者との合意による損害賠償・宥恕の書面化。量刑判断に大きく影響
# 構成: 当事者 / 事件概要 / 示談金 / 宥恕・告訴取下げ / 清算条項
# ---------------------------------------------------------------------------


def build_criminal_settlement(out_dir: Path) -> None:
    tid = "criminal-settlement"
    yaml_doc = {
        "id": tid,
        "title": "示談書（刑事事件）",
        "description": "刑事事件における被害者との示談書。宥恕・告訴取下げ条項を含むことが多い",
        "category": "刑事弁護",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "victim_name", "label": "被害者氏名", "type": "text", "required": True, "position": {"row": 3, "column": 3}},
            {"id": "victim_address", "label": "被害者住所", "type": "text", "required": True, "position": {"row": 4, "column": 3}},
            {"id": "perpetrator_name", "label": "加害者氏名", "type": "text", "required": True, "position": {"row": 5, "column": 3}},
            {"id": "perpetrator_address", "label": "加害者住所", "type": "text", "required": True, "position": {"row": 6, "column": 3}},
            {"id": "offense", "label": "被疑事実・罪名", "type": "text", "required": True, "position": {"row": 8, "column": 3}},
            {"id": "incident_date", "label": "事件発生日", "type": "date", "required": True, "position": {"row": 9, "column": 3}},
            {"id": "incident_summary", "label": "事件の概要", "type": "textarea", "required": True, "position": {"row": 10, "column": 3}},
            {"id": "settlement_amount", "label": "示談金（円）", "type": "number", "required": True, "position": {"row": 12, "column": 3}},
            {"id": "payment_method", "label": "支払方法", "type": "text", "required": True, "position": {"row": 13, "column": 3}, "description": "例: 本日現金で支払済 / ○月○日までに指定口座振込"},
            {"id": "forgiveness", "label": "宥恕条項", "type": "text", "required": True, "position": {"row": 15, "column": 3}, "description": "被害者が加害者を宥恕する旨。量刑上 critical"},
            {"id": "withdrawal_of_charge", "label": "告訴・被害届の取下げ", "type": "text", "required": False, "position": {"row": 16, "column": 3}, "description": "親告罪・被害届の場合。例: 告訴を取り下げる / 既に取下げ済み"},
            {"id": "settlement_date", "label": "示談成立日", "type": "date", "required": True, "position": {"row": 19, "column": 3}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="刑事示談書")
    wb.set_column_widths({1: 4, 2: 22, 3: 50})
    wb.merge(1, 1, 1, 3)
    wb.write_cell(1, 1, "示　談　書（刑事事件）", bold=True)

    wb.merge(2, 1, 2, 3)
    wb.write_cell(2, 1, "【当事者】", bold=True)
    wb.write_cell(3, 2, "被害者氏名:")
    wb.write_cell(4, 2, "被害者住所:")
    wb.write_cell(5, 2, "加害者氏名:")
    wb.write_cell(6, 2, "加害者住所:")

    wb.merge(7, 1, 7, 3)
    wb.write_cell(7, 1, "【事件の内容】", bold=True)
    wb.write_cell(8, 2, "被疑事実・罪名:")
    wb.write_cell(9, 2, "事件発生日:")
    wb.write_cell(10, 2, "事件の概要:")

    wb.merge(11, 1, 11, 3)
    wb.write_cell(11, 1, "【示談金】", bold=True)
    wb.write_cell(12, 2, "示談金（円）:")
    wb.write_cell(13, 2, "支払方法:")

    wb.merge(14, 1, 14, 3)
    wb.write_cell(14, 1, "【宥恕・告訴取下げ】", bold=True)
    wb.write_cell(15, 2, "宥恕条項:")
    wb.write_cell(16, 2, "告訴取下げ:")

    wb.merge(17, 1, 17, 3)
    wb.write_cell(17, 1, "【清算条項】", bold=True)
    wb.merge(18, 1, 18, 3)
    wb.write_cell(18, 1, "被害者及び加害者は、本示談書に定めるもののほか、本件に関し互いに何らの請求もしないことを確認する。")
    wb.write_cell(19, 2, "示談成立日:")

    wb.merge(21, 1, 21, 3)
    wb.write_cell(21, 1, "本示談書を 2 通作成し、被害者・加害者各 1 通を保有する。", bold=True)
    wb.merge(23, 1, 23, 3)
    wb.write_cell(23, 1, "被害者　署名：　　　　　　　　　　　　　　印")
    wb.merge(24, 1, 24, 3)
    wb.write_cell(24, 1, "加害者　署名：　　　　　　　　　　　　　　印")

    wb.merge(26, 1, 26, 3)
    wb.write_cell(26, 1, "※ 検察官・裁判所へ示談書を提出することで、不起訴処分・執行猶予・減刑の可能性が高まる")
    wb.merge(27, 1, 27, 3)
    wb.write_cell(27, 1, "※ 親告罪（名誉毀損・一部の性犯罪等）は告訴取下げが不起訴の要件となる")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 20: 後見開始申立書 (guardianship-application)
#
# 法的根拠: 民法 7条（成年後見開始）、家事事件手続法 117条以下
# 管轄: 本人の住所地を管轄する家庭裁判所
# 申立権者: 本人・配偶者・4親等内の親族・検察官等（民法 7条）
# 必要書類: 申立書 + 診断書 + 本人・申立人の戸籍謄本 + 本人の登記されていないことの証明書等
# ---------------------------------------------------------------------------


def build_guardianship_application(out_dir: Path) -> None:
    tid = "guardianship-application"
    yaml_doc = {
        "id": tid,
        "title": "後見開始申立書",
        "description": "成年後見開始の審判申立書雛形。本人の住所地を管轄する家裁に提出",
        "category": "家事事件",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄家庭裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "本人の住所地を管轄する家裁"},
            {"id": "filing_date", "label": "申立日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "guardianship_type", "label": "申立の類型", "type": "select", "required": True, "position": {"row": 4, "column": 2}, "options": ["後見", "保佐", "補助"]},
            {"id": "applicant_name", "label": "申立人氏名", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "applicant_address", "label": "申立人住所", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "applicant_relationship", "label": "本人との関係", "type": "text", "required": True, "position": {"row": 8, "column": 2}, "description": "例: 長男 / 配偶者 / 兄"},
            {"id": "person_name", "label": "本人氏名", "type": "text", "required": True, "position": {"row": 10, "column": 2}},
            {"id": "person_honseki", "label": "本人本籍", "type": "text", "required": True, "position": {"row": 11, "column": 2}},
            {"id": "person_address", "label": "本人住所", "type": "text", "required": True, "position": {"row": 12, "column": 2}},
            {"id": "person_birth", "label": "本人生年月日", "type": "date", "required": True, "position": {"row": 13, "column": 2}},
            {"id": "person_current_location", "label": "本人所在地（現在）", "type": "text", "required": False, "position": {"row": 14, "column": 2}, "description": "入院・入所先等、住所と異なる場合"},
            {"id": "reason_summary", "label": "申立の実情", "type": "textarea", "required": True, "position": {"row": 16, "column": 2}, "description": "本人の状態（認知症の程度・時期）、日常生活への影響、必要とする支援"},
            {"id": "candidate_name", "label": "後見人候補者氏名", "type": "text", "required": False, "position": {"row": 18, "column": 2}, "description": "候補者がいる場合のみ。家裁の判断により第三者が選任されることもある"},
            {"id": "candidate_relationship", "label": "候補者と本人の関係", "type": "text", "required": False, "position": {"row": 19, "column": 2}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="後見開始申立書")
    wb.set_column_widths({1: 22, 2: 54})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "後見・保佐・補助開始申立書", bold=True)
    wb.write_cell(2, 1, "管轄家庭裁判所:")
    wb.write_cell(3, 1, "申立日:")
    wb.write_cell(4, 1, "申立の類型:")

    wb.merge(5, 1, 5, 2)
    wb.write_cell(5, 1, "【申立人】", bold=True)
    for row, label in [(6, "氏名:"), (7, "住所:"), (8, "本人との関係:")]:
        wb.write_cell(row, 1, label)

    wb.merge(9, 1, 9, 2)
    wb.write_cell(9, 1, "【本人】", bold=True)
    for row, label in [(10, "氏名:"), (11, "本籍:"), (12, "住所:"), (13, "生年月日:"), (14, "現在の所在地:")]:
        wb.write_cell(row, 1, label)

    wb.merge(15, 1, 15, 2)
    wb.write_cell(15, 1, "【申立の実情】", bold=True)
    wb.write_cell(16, 1, "本人の状態・申立理由:")

    wb.merge(17, 1, 17, 2)
    wb.write_cell(17, 1, "【後見人候補者】", bold=True)
    wb.write_cell(18, 1, "候補者氏名:")
    wb.write_cell(19, 1, "本人との関係:")

    wb.merge(21, 1, 21, 2)
    wb.write_cell(21, 1, "【申立の趣旨】", bold=True)
    wb.merge(22, 1, 22, 2)
    wb.write_cell(22, 1, "1. 本人について後見（保佐・補助）を開始する。")
    wb.merge(23, 1, 23, 2)
    wb.write_cell(23, 1, "2. 後見人（保佐人・補助人）として上記候補者を選任する。")

    wb.merge(25, 1, 25, 2)
    wb.write_cell(25, 1, "※ 添付書類: 診断書・本人の戸籍謄本・住民票・登記されていないことの証明書・申立人の戸籍謄本等")
    wb.merge(26, 1, 26, 2)
    wb.write_cell(26, 1, "※ 法的根拠: 民法 7条・11条・15条、家事事件手続法 117-136条")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 21: 支払督促申立書 (payment-demand)
#
# 法的根拠: 民事訴訟法 382条以下
# 特徴: 書面審査のみで債務名義が得られる簡易手続。相手方が異議を出すと通常訴訟に移行
# 管轄: 債務者の住所地を管轄する簡易裁判所の書記官
# 手数料: 通常訴訟の 1/2
# ---------------------------------------------------------------------------


def build_payment_demand(out_dir: Path) -> None:
    tid = "payment-demand"
    yaml_doc = {
        "id": tid,
        "title": "支払督促申立書",
        "description": "金銭支払請求の簡易手続。書記官の書面審査のみで債務名義が得られる",
        "category": "民事訴訟",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄簡易裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "債務者の住所地の簡易裁判所（民訴 383条）"},
            {"id": "filing_date", "label": "申立日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "creditor_name", "label": "債権者氏名", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "creditor_address", "label": "債権者住所", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "debtor_name", "label": "債務者氏名", "type": "text", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "debtor_address", "label": "債務者住所", "type": "text", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "claim_amount", "label": "請求金額（元本/円）", "type": "number", "required": True, "position": {"row": 11, "column": 2}},
            {"id": "interest_rate", "label": "利率（年%）", "type": "text", "required": False, "position": {"row": 12, "column": 2}, "description": "例: 年3% / 年15%"},
            {"id": "interest_start_date", "label": "利息起算日", "type": "date", "required": False, "position": {"row": 13, "column": 2}},
            {"id": "claim_cause", "label": "請求の原因", "type": "textarea", "required": True, "position": {"row": 15, "column": 2}, "description": "金銭消費貸借・立替金・売買代金等、債権発生の原因と経緯"},
            {"id": "court_fee", "label": "申立手数料（印紙/円）", "type": "number", "required": True, "position": {"row": 17, "column": 2}, "description": "通常訴訟の 1/2"},
            {"id": "postage_stamps", "label": "連絡用郵便切手", "type": "text", "required": True, "position": {"row": 18, "column": 2}, "description": "裁判所指定額（通常 1,000円程度）"},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="支払督促申立書")
    wb.set_column_widths({1: 22, 2: 54})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "支払督促申立書", bold=True)
    wb.write_cell(2, 1, "管轄簡易裁判所:")
    wb.write_cell(3, 1, "申立日:")

    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "【債権者】", bold=True)
    wb.write_cell(5, 1, "氏名:")
    wb.write_cell(6, 1, "住所:")

    wb.merge(7, 1, 7, 2)
    wb.write_cell(7, 1, "【債務者】", bold=True)
    wb.write_cell(8, 1, "氏名:")
    wb.write_cell(9, 1, "住所:")

    wb.merge(10, 1, 10, 2)
    wb.write_cell(10, 1, "【請求の趣旨】", bold=True)
    wb.write_cell(11, 1, "請求金額（元本/円）:")
    wb.write_cell(12, 1, "利率:")
    wb.write_cell(13, 1, "利息起算日:")

    wb.merge(14, 1, 14, 2)
    wb.write_cell(14, 1, "【請求の原因】", bold=True)
    wb.write_cell(15, 1, "原因の説明:")

    wb.merge(16, 1, 16, 2)
    wb.write_cell(16, 1, "【費用】", bold=True)
    wb.write_cell(17, 1, "申立手数料（印紙/円）:")
    wb.write_cell(18, 1, "連絡用郵便切手:")

    wb.merge(20, 1, 20, 2)
    wb.write_cell(20, 1, "【手続の注意】", bold=True)
    wb.merge(21, 1, 21, 2)
    wb.write_cell(21, 1, "※ 根拠: 民事訴訟法 382条以下。書面審査のみで債務名義が得られる簡易手続")
    wb.merge(22, 1, 22, 2)
    wb.write_cell(22, 1, "※ 債務者が支払督促送達後 2 週間以内に異議を申し立てない場合、仮執行宣言の申立が可能")
    wb.merge(23, 1, 23, 2)
    wb.write_cell(23, 1, "※ 異議が出た場合、通常訴訟に移行（民訴 395条）")
    wb.merge(24, 1, 24, 2)
    wb.write_cell(24, 1, "※ 60万円以下の金銭請求は少額訴訟のほうが適する場合もある（民訴 368条）")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 22: 養育費請求調停申立書 (child-support-application)
#
# 法的根拠: 民法 766条（離婚後の子の監護）、民法 877条（親族の扶養義務）、
#           家事事件手続法 244条
# 算定: 令和元年改定の標準算定方式（東京・大阪家裁）が実務上の基準
# ---------------------------------------------------------------------------


def build_child_support_application(out_dir: Path) -> None:
    tid = "child-support-application"
    yaml_doc = {
        "id": tid,
        "title": "養育費請求調停申立書",
        "description": "離婚後または別居中の養育費請求の調停申立書。令和元年改定算定表を踏まえて金額を提示",
        "category": "家事事件",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄家庭裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "相手方の住所地の家裁"},
            {"id": "filing_date", "label": "申立日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "applicant_name", "label": "申立人（権利者）氏名", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "applicant_address", "label": "申立人住所", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "applicant_income", "label": "申立人年収（円）", "type": "number", "required": True, "position": {"row": 7, "column": 2}, "description": "給与所得者は源泉徴収票の支払金額、自営業者は所得金額"},
            {"id": "respondent_name", "label": "相手方（義務者）氏名", "type": "text", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "respondent_address", "label": "相手方住所", "type": "text", "required": True, "position": {"row": 10, "column": 2}},
            {"id": "respondent_income", "label": "相手方年収（円）", "type": "number", "required": False, "position": {"row": 11, "column": 2}, "description": "不明な場合は推定額＋根拠を別途説明"},
            {
                "id": "children",
                "label": "対象となる子",
                "type": "table",
                "required": True,
                "range": {"headerRow": 14, "dataStartRow": 15, "startColumn": 1, "endRow": 19, "endColumn": 3},
                "columns": [
                    {"id": "child_name", "label": "氏名", "type": "text"},
                    {"id": "child_birth", "label": "生年月日", "type": "date"},
                    {"id": "child_age", "label": "年齢", "type": "number"},
                ],
            },
            {"id": "requested_monthly_amount", "label": "請求月額（子1人あたり/円）", "type": "number", "required": True, "position": {"row": 21, "column": 2}, "description": "令和元年改定算定表による概算額"},
            {"id": "requested_start_date", "label": "請求開始日", "type": "date", "required": True, "position": {"row": 22, "column": 2}, "description": "原則、調停申立の月から"},
            {"id": "requested_end_date", "label": "請求終了時点", "type": "text", "required": True, "position": {"row": 23, "column": 2}, "description": "例: 子が満20歳に達する月 / 大学卒業"},
            {"id": "application_reason", "label": "申立の実情", "type": "textarea", "required": True, "position": {"row": 25, "column": 2}, "description": "離婚・別居の経緯、現在の監護状況、任意の話合いが不調に至った事情等"},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="養育費調停申立書")
    wb.set_column_widths({1: 4, 2: 24, 3: 54})
    wb.merge(1, 1, 1, 3)
    wb.write_cell(1, 1, "養育費請求調停申立書", bold=True)
    wb.write_cell(2, 2, "管轄家庭裁判所:")
    wb.write_cell(3, 2, "申立日:")

    wb.merge(4, 1, 4, 3)
    wb.write_cell(4, 1, "【申立人（権利者）】", bold=True)
    for row, label in [(5, "氏名:"), (6, "住所:"), (7, "年収（円）:")]:
        wb.write_cell(row, 2, label)

    wb.merge(8, 1, 8, 3)
    wb.write_cell(8, 1, "【相手方（義務者）】", bold=True)
    for row, label in [(9, "氏名:"), (10, "住所:"), (11, "年収（円）:")]:
        wb.write_cell(row, 2, label)

    wb.merge(13, 1, 13, 3)
    wb.write_cell(13, 1, "【対象となる子】", bold=True)
    wb.write_row(14, 1, ["氏名", "生年月日", "年齢"], bold=True)
    for r in range(15, 20):
        wb.write_cell(r, 1, "")

    wb.merge(20, 1, 20, 3)
    wb.write_cell(20, 1, "【請求内容】", bold=True)
    wb.write_cell(21, 2, "請求月額（子1人/円）:")
    wb.write_cell(22, 2, "請求開始日:")
    wb.write_cell(23, 2, "請求終了時点:")

    wb.merge(24, 1, 24, 3)
    wb.write_cell(24, 1, "【申立の実情】", bold=True)
    wb.write_cell(25, 2, "経緯・現状:")

    wb.merge(27, 1, 27, 3)
    wb.write_cell(27, 1, "※ 金額算定: 令和元年改定の標準算定方式（東京・大阪家裁）が実務上の基準。`/traffic-damage-calc` の次に Track B で `/child-support-calc` を実装予定")
    wb.merge(28, 1, 28, 3)
    wb.write_cell(28, 1, "※ 手数料: 収入印紙 1,200円 + 連絡用郵便切手")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 23: 婚姻費用分担請求調停申立書 (spousal-support-application)
#
# 法的根拠: 民法 760条（夫婦間の費用分担）、家事事件手続法 244条
# 特徴: 離婚前の別居中に請求する。養育費と異なり未成年の子がいなくても成立
# ---------------------------------------------------------------------------


def build_spousal_support_application(out_dir: Path) -> None:
    tid = "spousal-support-application"
    yaml_doc = {
        "id": tid,
        "title": "婚姻費用分担請求調停申立書",
        "description": "別居中の夫婦間における婚姻費用分担請求の調停申立書",
        "category": "家事事件",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄家庭裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "filing_date", "label": "申立日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "applicant_name", "label": "申立人氏名", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "applicant_address", "label": "申立人住所（現住）", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "applicant_income", "label": "申立人年収（円）", "type": "number", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "respondent_name", "label": "相手方氏名", "type": "text", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "respondent_address", "label": "相手方住所", "type": "text", "required": True, "position": {"row": 10, "column": 2}},
            {"id": "respondent_income", "label": "相手方年収（円）", "type": "number", "required": False, "position": {"row": 11, "column": 2}},
            {"id": "marriage_date", "label": "婚姻日", "type": "date", "required": True, "position": {"row": 13, "column": 2}},
            {"id": "separation_date", "label": "別居開始日", "type": "date", "required": True, "position": {"row": 14, "column": 2}},
            {"id": "children_count", "label": "未成年の子（人数）", "type": "number", "required": False, "position": {"row": 15, "column": 2}, "description": "同居する未成年の子"},
            {"id": "requested_monthly_amount", "label": "請求月額（円）", "type": "number", "required": True, "position": {"row": 17, "column": 2}, "description": "令和元年改定算定表（婚姻費用）"},
            {"id": "requested_start_date", "label": "請求開始日", "type": "date", "required": True, "position": {"row": 18, "column": 2}, "description": "原則、調停申立の月から"},
            {"id": "application_reason", "label": "申立の実情", "type": "textarea", "required": True, "position": {"row": 20, "column": 2}, "description": "別居の経緯、現在の生活状況、話合いの経緯等"},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="婚姻費用申立書")
    wb.set_column_widths({1: 22, 2: 54})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "婚姻費用分担請求調停申立書", bold=True)
    wb.write_cell(2, 1, "管轄家庭裁判所:")
    wb.write_cell(3, 1, "申立日:")

    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "【申立人】", bold=True)
    for row, label in [(5, "氏名:"), (6, "住所（現住）:"), (7, "年収（円）:")]:
        wb.write_cell(row, 1, label)

    wb.merge(8, 1, 8, 2)
    wb.write_cell(8, 1, "【相手方】", bold=True)
    for row, label in [(9, "氏名:"), (10, "住所:"), (11, "年収（円）:")]:
        wb.write_cell(row, 1, label)

    wb.merge(12, 1, 12, 2)
    wb.write_cell(12, 1, "【婚姻関係・別居状況】", bold=True)
    for row, label in [(13, "婚姻日:"), (14, "別居開始日:"), (15, "未成年の子（人数）:")]:
        wb.write_cell(row, 1, label)

    wb.merge(16, 1, 16, 2)
    wb.write_cell(16, 1, "【請求内容】", bold=True)
    wb.write_cell(17, 1, "請求月額（円）:")
    wb.write_cell(18, 1, "請求開始日:")

    wb.merge(19, 1, 19, 2)
    wb.write_cell(19, 1, "【申立の実情】", bold=True)
    wb.write_cell(20, 1, "経緯・現状:")

    wb.merge(22, 1, 22, 2)
    wb.write_cell(22, 1, "※ 法的根拠: 民法 760条（夫婦間の費用分担）")
    wb.merge(23, 1, 23, 2)
    wb.write_cell(23, 1, "※ 金額算定: 令和元年改定・婚姻費用標準算定方式")
    wb.merge(24, 1, 24, 2)
    wb.write_cell(24, 1, "※ 離婚前の別居中に請求。離婚後は `child-support-application`（養育費）を使用")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 24: 株主総会議事録 (shareholder-meeting-minutes)
#
# 法的根拠: 会社法 318 条（議事録の作成・備置）、施行規則 72 条
# 要件: 会社の本店に 10 年間備置。支店に写し 5 年間。
# 署名: 出席役員が記名押印（実務）
# ---------------------------------------------------------------------------


def build_shareholder_meeting_minutes(out_dir: Path) -> None:
    tid = "shareholder-meeting-minutes"
    yaml_doc = {
        "id": tid,
        "title": "株主総会議事録",
        "description": "定時・臨時株主総会の議事録雛形（会社法 318 条、施行規則 72 条）",
        "category": "企業法務",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "company_name", "label": "会社名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "meeting_type", "label": "総会種別", "type": "select", "required": True, "position": {"row": 3, "column": 2}, "options": ["定時株主総会", "臨時株主総会"]},
            {"id": "meeting_date", "label": "開催日時", "type": "text", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "meeting_place", "label": "開催場所", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "total_shares", "label": "発行済株式総数", "type": "number", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "voting_shares", "label": "議決権を有する株主の数", "type": "number", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "present_shares", "label": "出席株主の議決権数", "type": "number", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "chair_name", "label": "議長氏名（通常は代表取締役）", "type": "text", "required": True, "position": {"row": 10, "column": 2}},
            {"id": "attending_directors", "label": "出席取締役", "type": "textarea", "required": True, "position": {"row": 11, "column": 2}, "description": "氏名を改行区切りで列挙"},
            {
                "id": "agenda",
                "label": "議題",
                "type": "table",
                "required": True,
                "range": {"headerRow": 14, "dataStartRow": 15, "startColumn": 1, "endRow": 24, "endColumn": 4},
                "columns": [
                    {"id": "no", "label": "議案番号", "type": "text"},
                    {"id": "title", "label": "議題名", "type": "text"},
                    {"id": "summary", "label": "討議要旨", "type": "text"},
                    {"id": "result", "label": "決議結果", "type": "text", "description": "例: 賛成多数で可決 / 全員一致で可決 / 否決"},
                ],
            },
            {"id": "closing_time", "label": "閉会時刻", "type": "text", "required": True, "position": {"row": 26, "column": 2}},
        ],
    }

    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="株主総会議事録")
    wb.set_column_widths({1: 24, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "株主総会議事録", bold=True)
    wb.write_cell(2, 1, "会社名:")
    wb.write_cell(3, 1, "総会種別:")
    wb.write_cell(4, 1, "開催日時:")
    wb.write_cell(5, 1, "開催場所:")
    wb.write_cell(6, 1, "発行済株式総数:")
    wb.write_cell(7, 1, "議決権を有する株主数:")
    wb.write_cell(8, 1, "出席株主の議決権数:")
    wb.merge(9, 1, 9, 2)
    wb.write_cell(9, 1, "【議長・出席役員】", bold=True)
    wb.write_cell(10, 1, "議長氏名:")
    wb.write_cell(11, 1, "出席取締役:")
    wb.merge(13, 1, 13, 4)
    wb.write_cell(13, 1, "【議題】", bold=True)
    wb.write_row(14, 1, ["議案番号", "議題名", "討議要旨", "決議結果"], bold=True)
    for r in range(15, 25):
        wb.write_cell(r, 1, "")
    wb.merge(25, 1, 25, 2)
    wb.write_cell(25, 1, "【閉会】", bold=True)
    wb.write_cell(26, 1, "閉会時刻:")
    wb.merge(28, 1, 28, 2)
    wb.write_cell(28, 1, "上記議事を明確にするため、議長及び出席取締役は次に記名押印する。", bold=True)
    wb.write_cell(30, 1, "議長　代表取締役:　　　　　　　　　　　　　印")
    wb.write_cell(31, 1, "出席取締役:　　　　　　　　　　　　　　　　印")
    wb.merge(33, 1, 33, 2)
    wb.write_cell(33, 1, "※ 会社法 318 条: 本店に 10 年間、支店に写しを 5 年間備え置く")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 25: 取締役会議事録 (board-meeting-minutes)
#
# 法的根拠: 会社法 369 条 3 項（議事録）、施行規則 101 条
# 要件: 出席取締役・監査役が記名押印
# ---------------------------------------------------------------------------


def build_board_meeting_minutes(out_dir: Path) -> None:
    tid = "board-meeting-minutes"
    yaml_doc = {
        "id": tid,
        "title": "取締役会議事録",
        "description": "取締役会議事録雛形（会社法 369 条 3 項、施行規則 101 条）",
        "category": "企業法務",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "company_name", "label": "会社名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "meeting_date", "label": "開催日時", "type": "text", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "meeting_place", "label": "開催場所", "type": "text", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "attending_directors", "label": "出席取締役", "type": "textarea", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "attending_auditors", "label": "出席監査役", "type": "textarea", "required": False, "position": {"row": 7, "column": 2}},
            {"id": "chair_name", "label": "議長", "type": "text", "required": True, "position": {"row": 8, "column": 2}},
            {
                "id": "agenda",
                "label": "議題",
                "type": "table",
                "required": True,
                "range": {"headerRow": 11, "dataStartRow": 12, "startColumn": 1, "endRow": 20, "endColumn": 4},
                "columns": [
                    {"id": "no", "label": "議案", "type": "text"},
                    {"id": "title", "label": "議題", "type": "text"},
                    {"id": "summary", "label": "討議の内容・結果", "type": "text"},
                    {"id": "result", "label": "決議結果", "type": "text"},
                ],
            },
        ],
    }
    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="取締役会議事録")
    wb.set_column_widths({1: 22, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "取締役会議事録", bold=True)
    wb.write_cell(2, 1, "会社名:")
    wb.write_cell(3, 1, "開催日時:")
    wb.write_cell(4, 1, "開催場所:")
    wb.merge(5, 1, 5, 2)
    wb.write_cell(5, 1, "【出席者】", bold=True)
    wb.write_cell(6, 1, "出席取締役:")
    wb.write_cell(7, 1, "出席監査役:")
    wb.write_cell(8, 1, "議長:")
    wb.merge(10, 1, 10, 4)
    wb.write_cell(10, 1, "【議題】", bold=True)
    wb.write_row(11, 1, ["議案", "議題", "討議内容・結果", "決議結果"], bold=True)
    for r in range(12, 21):
        wb.write_cell(r, 1, "")
    wb.merge(22, 1, 22, 2)
    wb.write_cell(22, 1, "上記議事を証するため、議長及び出席取締役・監査役は次に記名押印する。", bold=True)
    wb.write_cell(24, 1, "議長　代表取締役:　　　　　　　　　　　　　印")
    wb.write_cell(25, 1, "取締役:　　　　　　　　　　　　　　　　　　印")
    wb.write_cell(26, 1, "監査役:　　　　　　　　　　　　　　　　　　印")
    wb.merge(28, 1, 28, 2)
    wb.write_cell(28, 1, "※ 会社法 369 条 3 項: 取締役会設置会社は議事録作成義務あり")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 26: 少額訴訟訴状 (small-claims-complaint)
#
# 法的根拠: 民事訴訟法 368 条（少額訴訟）、同 375 条
# 要件: 60 万円以下の金銭請求、1 回の期日で判決原則
# 同一原告が同一簡裁で年 10 回まで
# ---------------------------------------------------------------------------


def build_small_claims_complaint(out_dir: Path) -> None:
    tid = "small-claims-complaint"
    yaml_doc = {
        "id": tid,
        "title": "訴状（少額訴訟）",
        "description": "60万円以下の金銭請求訴訟（民訴法 368 条以下）の訴状雛形",
        "category": "民事訴訟",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄簡易裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "filing_date", "label": "提出日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "plaintiff_name", "label": "原告氏名", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "plaintiff_address", "label": "原告住所", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "defendant_name", "label": "被告氏名", "type": "text", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "defendant_address", "label": "被告住所", "type": "text", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "claim_amount", "label": "請求金額（円）", "type": "number", "required": True, "position": {"row": 11, "column": 2}, "description": "60 万円以下"},
            {"id": "claim_reason", "label": "事件の概要", "type": "textarea", "required": True, "position": {"row": 13, "column": 2}, "description": "金銭消費貸借・未払賃金・敷金返還等の具体的事情"},
            {"id": "evidence", "label": "主要証拠", "type": "textarea", "required": True, "position": {"row": 15, "column": 2}, "description": "例: 甲第 1 号証 契約書、甲第 2 号証 督促状"},
        ],
    }
    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="少額訴訟訴状")
    wb.set_column_widths({1: 22, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "訴状（少額訴訟）", bold=True)
    wb.write_cell(2, 1, "管轄簡易裁判所:")
    wb.write_cell(3, 1, "提出日:")
    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "【当事者】", bold=True)
    wb.write_cell(5, 1, "原告氏名:")
    wb.write_cell(6, 1, "原告住所:")
    wb.write_cell(8, 1, "被告氏名:")
    wb.write_cell(9, 1, "被告住所:")
    wb.merge(10, 1, 10, 2)
    wb.write_cell(10, 1, "【請求の趣旨】", bold=True)
    wb.write_cell(11, 1, "請求金額（円）:")
    wb.merge(12, 1, 12, 2)
    wb.write_cell(12, 1, "【請求の原因】", bold=True)
    wb.write_cell(13, 1, "事件の概要:")
    wb.merge(14, 1, 14, 2)
    wb.write_cell(14, 1, "【証拠方法】", bold=True)
    wb.write_cell(15, 1, "主要証拠:")
    wb.merge(17, 1, 17, 2)
    wb.write_cell(17, 1, "※ 少額訴訟の要件: 60 万円以下の金銭請求、同一簡裁で年 10 回まで（民訴 368 条）")
    wb.merge(18, 1, 18, 2)
    wb.write_cell(18, 1, "※ 原則 1 回の期日で判決、被告の異議で通常訴訟に移行可能")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 27: 即決和解申立書 (immediate-settlement)
#
# 法的根拠: 民事訴訟法 275 条（起訴前の和解）
# 用途: 紛争解決後の執行力付き和解調書を得る
# 効力: 確定判決と同一
# ---------------------------------------------------------------------------


def build_immediate_settlement(out_dir: Path) -> None:
    tid = "immediate-settlement"
    yaml_doc = {
        "id": tid,
        "title": "即決和解申立書（訴え提起前の和解）",
        "description": "民訴法 275 条の起訴前の和解申立書。執行力付き和解調書の取得が目的",
        "category": "民事訴訟",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "court_name", "label": "管轄簡易裁判所", "type": "text", "required": True, "position": {"row": 2, "column": 2}, "description": "相手方の住所地を管轄する簡裁"},
            {"id": "filing_date", "label": "申立日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "applicant_name", "label": "申立人氏名", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {"id": "applicant_address", "label": "申立人住所", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "respondent_name", "label": "相手方氏名", "type": "text", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "respondent_address", "label": "相手方住所", "type": "text", "required": True, "position": {"row": 9, "column": 2}},
            {"id": "dispute_summary", "label": "紛争の要点", "type": "textarea", "required": True, "position": {"row": 11, "column": 2}},
            {"id": "settlement_terms", "label": "和解条項（案）", "type": "textarea", "required": True, "position": {"row": 13, "column": 2}, "description": "例: 1. 相手方は申立人に対し、金○○円を支払う。 2. 申立人はこれを本和解以外の請求はしない。"},
        ],
    }
    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="即決和解申立書")
    wb.set_column_widths({1: 22, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "即決和解申立書（訴え提起前の和解）", bold=True)
    wb.write_cell(2, 1, "管轄簡易裁判所:")
    wb.write_cell(3, 1, "申立日:")
    wb.merge(4, 1, 4, 2)
    wb.write_cell(4, 1, "【申立人】", bold=True)
    wb.write_cell(5, 1, "氏名:")
    wb.write_cell(6, 1, "住所:")
    wb.merge(7, 1, 7, 2)
    wb.write_cell(7, 1, "【相手方】", bold=True)
    wb.write_cell(8, 1, "氏名:")
    wb.write_cell(9, 1, "住所:")
    wb.merge(10, 1, 10, 2)
    wb.write_cell(10, 1, "【紛争の要点】", bold=True)
    wb.write_cell(11, 1, "紛争の要点:")
    wb.merge(12, 1, 12, 2)
    wb.write_cell(12, 1, "【和解条項】", bold=True)
    wb.write_cell(13, 1, "条項案:")
    wb.merge(15, 1, 15, 2)
    wb.write_cell(15, 1, "※ 民訴法 275 条に基づく訴え提起前の和解。和解成立時は確定判決と同一効力（民訴 267 条）")
    wb.merge(16, 1, 16, 2)
    wb.write_cell(16, 1, "※ 手数料: 収入印紙 2,000 円 + 連絡用郵便切手")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 28: 陳述書（刑事）(criminal-statement)
#
# 用途: 刑事公判における被告人・証人の陳述書。情状弁護資料として
# ---------------------------------------------------------------------------


def build_criminal_statement(out_dir: Path) -> None:
    tid = "criminal-statement"
    yaml_doc = {
        "id": tid,
        "title": "陳述書（刑事事件）",
        "description": "刑事公判での被告人・証人の陳述書。情状弁護・被害者の意見書として",
        "category": "刑事弁護",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "case_number", "label": "事件番号", "type": "text", "required": False, "position": {"row": 2, "column": 2}},
            {"id": "case_name", "label": "事件名・罪名", "type": "text", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "court_name", "label": "裁判所", "type": "text", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "author_role", "label": "作成者の立場", "type": "select", "required": True, "position": {"row": 6, "column": 2}, "options": ["被告人", "証人", "被害者", "親族", "雇主", "嘆願者"]},
            {"id": "author_name", "label": "作成者氏名", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "author_address", "label": "作成者住所", "type": "text", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "relationship", "label": "被告人との関係", "type": "text", "required": False, "position": {"row": 9, "column": 2}, "description": "親族・同僚・恋人・上司等"},
            {"id": "statement_body", "label": "陳述内容", "type": "textarea", "required": True, "position": {"row": 12, "column": 1}, "description": "事実経過・反省・今後の監督等を時系列で記載"},
            {"id": "statement_date", "label": "作成日", "type": "date", "required": True, "position": {"row": 28, "column": 2}},
        ],
    }
    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="陳述書(刑事)")
    wb.set_column_widths({1: 22, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "陳　述　書", bold=True)
    wb.write_cell(2, 1, "事件番号:")
    wb.write_cell(3, 1, "事件名・罪名:")
    wb.write_cell(4, 1, "裁判所:")
    wb.merge(5, 1, 5, 2)
    wb.write_cell(5, 1, "【作成者】", bold=True)
    wb.write_cell(6, 1, "立場:")
    wb.write_cell(7, 1, "氏名:")
    wb.write_cell(8, 1, "住所:")
    wb.write_cell(9, 1, "被告人との関係:")
    wb.merge(11, 1, 11, 2)
    wb.write_cell(11, 1, "【陳述内容】", bold=True)
    for r in range(12, 27):
        wb.write_cell(r, 1, "")
    wb.merge(27, 1, 27, 2)
    wb.write_cell(27, 1, "【作成日・署名】", bold=True)
    wb.write_cell(28, 1, "作成日:")
    wb.merge(30, 1, 30, 2)
    wb.write_cell(30, 1, "作成者　署名：　　　　　　　　　　　　　　印")
    wb.merge(32, 1, 32, 2)
    wb.write_cell(32, 1, "※ 量刑上の考慮資料。事実に反する内容を記載しないこと（偽証罪リスク）")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 29: 契約書レビューチェックリスト (contract-review-checklist)
#
# 用途: 契約書レビュー時の標準チェック項目
# ---------------------------------------------------------------------------


def build_contract_review_checklist(out_dir: Path) -> None:
    tid = "contract-review-checklist"
    yaml_doc = {
        "id": tid,
        "title": "契約書レビューチェックリスト",
        "description": "一般契約書のレビュー時に確認すべき標準項目。リスク所在の事前洗い出し",
        "category": "企業法務",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "contract_title", "label": "契約書名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "counterparty", "label": "相手方", "type": "text", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "review_date", "label": "レビュー日", "type": "date", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "reviewer", "label": "レビュー担当", "type": "text", "required": True, "position": {"row": 5, "column": 2}},
            {
                "id": "checklist",
                "label": "チェック項目",
                "type": "table",
                "required": True,
                "range": {"headerRow": 8, "dataStartRow": 9, "startColumn": 1, "endRow": 40, "endColumn": 5},
                "columns": [
                    {"id": "category", "label": "カテゴリ", "type": "text"},
                    {"id": "item", "label": "チェック項目", "type": "text"},
                    {"id": "status", "label": "状態", "type": "text", "description": "OK / 要修正 / 要検討 / NA"},
                    {"id": "comment", "label": "コメント", "type": "text"},
                    {"id": "action", "label": "対応", "type": "text"},
                ],
            },
        ],
    }
    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="契約書レビュー")
    wb.set_column_widths({1: 12, 2: 30, 3: 12, 4: 34, 5: 20})
    wb.merge(1, 1, 1, 5)
    wb.write_cell(1, 1, "契約書レビューチェックリスト", bold=True)
    wb.write_cell(2, 1, "契約書名:")
    wb.write_cell(3, 1, "相手方:")
    wb.write_cell(4, 1, "レビュー日:")
    wb.write_cell(5, 1, "レビュー担当:")
    wb.merge(7, 1, 7, 5)
    wb.write_cell(7, 1, "【チェック項目】", bold=True)
    wb.write_row(8, 1, ["カテゴリ", "チェック項目", "状態", "コメント", "対応"], bold=True)
    # 代表的なチェック項目を初期値として挿入
    default_items = [
        ("基本", "当事者・契約日・契約書名称が明確か", "", "", ""),
        ("基本", "契約期間・自動更新条項・中途解約条項", "", "", ""),
        ("基本", "準拠法・合意管轄裁判所", "", "", ""),
        ("金銭", "対価・支払方法・支払時期", "", "", ""),
        ("金銭", "消費税・源泉徴収の取扱い", "", "", ""),
        ("履行", "債務内容・履行期限・検収要件", "", "", ""),
        ("履行", "履行遅滞時の損害賠償・遅延損害金", "", "", ""),
        ("責任", "損害賠償範囲・上限額（民法 416 条との関係）", "", "", ""),
        ("責任", "契約不適合責任（民法 562-564 条）", "", "", ""),
        ("責任", "不可抗力条項", "", "", ""),
        ("解除", "解除事由（催告解除・無催告解除）", "", "", ""),
        ("解除", "暴力団排除条項", "", "", ""),
        ("知財", "知的財産権の帰属・利用許諾", "", "", ""),
        ("情報", "秘密保持義務の範囲・期間", "", "", ""),
        ("情報", "個人情報保護法対応（§27 第三者提供）", "", "", ""),
        ("その他", "譲渡禁止・変更書面要件", "", "", ""),
        ("その他", "完全合意条項・分離可能性", "", "", ""),
    ]
    for i, (cat, item, status, comment, action) in enumerate(default_items):
        wb.write_row(9 + i, 1, [cat, item, status, comment, action])
    # 残りは空欄
    for r in range(9 + len(default_items), 41):
        wb.write_cell(r, 1, "")
    wb.merge(42, 1, 42, 5)
    wb.write_cell(42, 1, "※ 業種・取引類型によりチェック項目を加減する。本雛形は汎用版")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 30: 就業規則雛形（簡易版） (work-regulations-template)
#
# 法的根拠: 労働基準法 89 条（作成義務、常時 10 人以上）、90 条（意見聴取）、
#           92 条（労基署届出義務）
# ---------------------------------------------------------------------------


def build_work_regulations_template(out_dir: Path) -> None:
    tid = "work-regulations-template"
    yaml_doc = {
        "id": tid,
        "title": "就業規則（簡易版・テンプレート）",
        "description": "労基法 89 条の必要記載事項を網羅した就業規則雛形。10 人以上の事業場で必要",
        "category": "企業法務",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "company_name", "label": "会社名", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "effective_date", "label": "施行日", "type": "date", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "working_hours", "label": "所定労働時間（1 日）", "type": "text", "required": True, "position": {"row": 6, "column": 2}, "description": "例: 8 時間（9:00 - 18:00、休憩 1 時間）"},
            {"id": "work_days_per_week", "label": "週所定労働日数", "type": "number", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "holidays_annual", "label": "年間所定休日", "type": "number", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "paid_leave_days", "label": "年次有給休暇（初年度）", "type": "number", "required": True, "position": {"row": 10, "column": 2}, "description": "労基法 39 条で 6 ヶ月継続勤務後 10 日"},
            {"id": "salary_payment_date", "label": "賃金支払日", "type": "text", "required": True, "position": {"row": 12, "column": 2}, "description": "例: 毎月 25 日（末締め）"},
            {"id": "retirement_age", "label": "定年年齢", "type": "number", "required": True, "position": {"row": 14, "column": 2}, "description": "高年齢者雇用安定法 8 条: 60 歳以上"},
            {"id": "disciplinary_rules", "label": "懲戒規定", "type": "textarea", "required": True, "position": {"row": 16, "column": 2}, "description": "懲戒事由・種類（戒告/減給/出勤停止/懲戒解雇）"},
        ],
    }
    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="就業規則")
    wb.set_column_widths({1: 22, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "就業規則（簡易版）", bold=True)
    wb.write_cell(2, 1, "会社名:")
    wb.write_cell(3, 1, "施行日:")
    wb.merge(5, 1, 5, 2)
    wb.write_cell(5, 1, "【労働時間・休日】", bold=True)
    wb.write_cell(6, 1, "所定労働時間:")
    wb.write_cell(7, 1, "週所定労働日数:")
    wb.write_cell(8, 1, "年間所定休日:")
    wb.merge(9, 1, 9, 2)
    wb.write_cell(9, 1, "【有給休暇】", bold=True)
    wb.write_cell(10, 1, "年次有給休暇（初年度）:")
    wb.merge(11, 1, 11, 2)
    wb.write_cell(11, 1, "【賃金】", bold=True)
    wb.write_cell(12, 1, "賃金支払日:")
    wb.merge(13, 1, 13, 2)
    wb.write_cell(13, 1, "【定年】", bold=True)
    wb.write_cell(14, 1, "定年年齢:")
    wb.merge(15, 1, 15, 2)
    wb.write_cell(15, 1, "【懲戒】", bold=True)
    wb.write_cell(16, 1, "懲戒規定:")
    wb.merge(18, 1, 18, 2)
    wb.write_cell(18, 1, "【必須記載事項（労基法 89 条）】", bold=True)
    required_items = [
        "(絶対必要記載事項)",
        "1. 始業・終業時刻、休憩時間、休日、休暇",
        "2. 賃金の決定・計算・支払方法、支払時期、昇給",
        "3. 退職に関する事項（解雇事由を含む）",
        "(相対的必要記載事項)",
        "4. 退職手当の定め",
        "5. 臨時の賃金・最低賃金",
        "6. 食費・作業用品等の負担",
        "7. 安全衛生",
        "8. 職業訓練",
        "9. 災害補償・業務外傷病扶助",
        "10. 表彰・制裁の種類・程度",
        "11. その他 全労働者に適用される定め",
    ]
    for i, item in enumerate(required_items):
        wb.write_cell(19 + i, 1, item)
    wb.merge(33, 1, 33, 2)
    wb.write_cell(33, 1, "※ 作成・変更時は過半数労働組合または過半数代表者の意見聴取（労基法 90 条）")
    wb.merge(34, 1, 34, 2)
    wb.write_cell(34, 1, "※ 労基署への届出義務（労基法 89 条）。本雛形は簡易版、業種・規模によりカスタマイズ必須")

    wb.save(out_dir / f"{tid}.xlsx")


# ---------------------------------------------------------------------------
# Form 31: 労働契約書 (employment-contract)
#
# 法的根拠: 労基法 15 条（労働条件明示義務）、労働契約法 4 条
# ---------------------------------------------------------------------------


def build_employment_contract(out_dir: Path) -> None:
    tid = "employment-contract"
    yaml_doc = {
        "id": tid,
        "title": "労働契約書",
        "description": "労基法 15 条の明示事項を網羅した労働契約書雛形。正社員・契約社員両対応",
        "category": "労働",
        "templateFile": f"{tid}.xlsx",
        "fields": [
            {"id": "employer_name", "label": "使用者（会社名）", "type": "text", "required": True, "position": {"row": 2, "column": 2}},
            {"id": "employer_address", "label": "会社住所", "type": "text", "required": True, "position": {"row": 3, "column": 2}},
            {"id": "employer_representative", "label": "代表者", "type": "text", "required": True, "position": {"row": 4, "column": 2}},
            {"id": "employee_name", "label": "労働者氏名", "type": "text", "required": True, "position": {"row": 6, "column": 2}},
            {"id": "employee_address", "label": "労働者住所", "type": "text", "required": True, "position": {"row": 7, "column": 2}},
            {"id": "employee_birth", "label": "労働者生年月日", "type": "date", "required": True, "position": {"row": 8, "column": 2}},
            {"id": "contract_type", "label": "契約種別", "type": "select", "required": True, "position": {"row": 10, "column": 2}, "options": ["正社員", "契約社員", "パート・アルバイト", "嘱託"]},
            {"id": "contract_start", "label": "契約開始日", "type": "date", "required": True, "position": {"row": 11, "column": 2}},
            {"id": "contract_end", "label": "契約期間満了日", "type": "date", "required": False, "position": {"row": 12, "column": 2}, "description": "無期雇用の場合は空欄"},
            {"id": "trial_period", "label": "試用期間", "type": "text", "required": False, "position": {"row": 13, "column": 2}, "description": "例: 採用日から 3 ヶ月"},
            {"id": "work_location", "label": "就業場所", "type": "text", "required": True, "position": {"row": 15, "column": 2}},
            {"id": "job_duties", "label": "業務内容", "type": "textarea", "required": True, "position": {"row": 16, "column": 2}},
            {"id": "working_hours", "label": "所定労働時間", "type": "text", "required": True, "position": {"row": 18, "column": 2}},
            {"id": "break_time", "label": "休憩時間", "type": "text", "required": True, "position": {"row": 19, "column": 2}},
            {"id": "holidays", "label": "休日", "type": "text", "required": True, "position": {"row": 20, "column": 2}},
            {"id": "paid_leave", "label": "年次有給休暇", "type": "text", "required": True, "position": {"row": 21, "column": 2}, "description": "労基法 39 条準拠"},
            {"id": "monthly_salary", "label": "月額賃金（円）", "type": "number", "required": True, "position": {"row": 23, "column": 2}},
            {"id": "allowances", "label": "諸手当", "type": "textarea", "required": False, "position": {"row": 24, "column": 2}, "description": "通勤手当・役職手当・家族手当等"},
            {"id": "salary_payment_date", "label": "賃金支払日", "type": "text", "required": True, "position": {"row": 25, "column": 2}},
            {"id": "signed_date", "label": "契約締結日", "type": "date", "required": True, "position": {"row": 27, "column": 2}},
        ],
    }
    (out_dir / f"{tid}.yaml").write_text(_emit_yaml(yaml_doc), encoding="utf-8")

    wb = Workbook(sheet_name="労働契約書")
    wb.set_column_widths({1: 22, 2: 52})
    wb.merge(1, 1, 1, 2)
    wb.write_cell(1, 1, "労働契約書", bold=True)
    wb.write_cell(2, 1, "使用者:")
    wb.write_cell(3, 1, "会社住所:")
    wb.write_cell(4, 1, "代表者:")
    wb.merge(5, 1, 5, 2)
    wb.write_cell(5, 1, "【労働者】", bold=True)
    wb.write_cell(6, 1, "氏名:")
    wb.write_cell(7, 1, "住所:")
    wb.write_cell(8, 1, "生年月日:")
    wb.merge(9, 1, 9, 2)
    wb.write_cell(9, 1, "【契約条件】", bold=True)
    wb.write_cell(10, 1, "契約種別:")
    wb.write_cell(11, 1, "契約開始日:")
    wb.write_cell(12, 1, "期間満了日:")
    wb.write_cell(13, 1, "試用期間:")
    wb.merge(14, 1, 14, 2)
    wb.write_cell(14, 1, "【就業条件】", bold=True)
    wb.write_cell(15, 1, "就業場所:")
    wb.write_cell(16, 1, "業務内容:")
    wb.merge(17, 1, 17, 2)
    wb.write_cell(17, 1, "【労働時間・休日】", bold=True)
    wb.write_cell(18, 1, "所定労働時間:")
    wb.write_cell(19, 1, "休憩時間:")
    wb.write_cell(20, 1, "休日:")
    wb.write_cell(21, 1, "年次有給休暇:")
    wb.merge(22, 1, 22, 2)
    wb.write_cell(22, 1, "【賃金】", bold=True)
    wb.write_cell(23, 1, "月額賃金（円）:")
    wb.write_cell(24, 1, "諸手当:")
    wb.write_cell(25, 1, "賃金支払日:")
    wb.merge(26, 1, 26, 2)
    wb.write_cell(26, 1, "【締結】", bold=True)
    wb.write_cell(27, 1, "契約締結日:")
    wb.merge(29, 1, 29, 2)
    wb.write_cell(29, 1, "本契約書を 2 通作成し、使用者・労働者各 1 通を保有する。", bold=True)
    wb.write_cell(31, 1, "使用者　記名押印：　　　　　　　　　　　　　印")
    wb.write_cell(32, 1, "労働者　署名　　　：　　　　　　　　　　　　印")
    wb.merge(34, 1, 34, 2)
    wb.write_cell(34, 1, "※ 労基法 15 条 1 項・同施行規則 5 条: 労働条件の明示義務あり")

    wb.save(out_dir / f"{tid}.xlsx")


def _write_manifest() -> None:
    """全同梱テンプレートの SHA-256 マニフェストを書き出す。

    install 時に `template_lib.py` が検証する。マニフェスト自体は git
    追跡されるため、リポジトリ経由の改ざん（例: 悪意あるマージ）は
    git log で検出可能になる。
    """
    import hashlib

    manifest_lines: List[str] = [
        "# claude-bengo bundled template manifest",
        "# 形式: <sha256>  <相対パス>",
        "# このファイルは build_bundled_forms.py により自動生成される。手動編集禁止。",
        "# 改ざん検知用途: /template-install で verify される。",
        "",
    ]
    for entry in sorted(BUNDLED.iterdir()):
        if not entry.is_dir():
            continue
        for f in sorted(entry.iterdir()):
            if not f.is_file():
                continue
            rel = f.relative_to(BUNDLED)
            h = hashlib.sha256()
            with f.open("rb") as fp:
                for chunk in iter(lambda: fp.read(65536), b""):
                    h.update(chunk)
            manifest_lines.append(f"{h.hexdigest()}  {rel}")
    manifest_path = BUNDLED / "_manifest.sha256"
    manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(f"  [OK] wrote manifest with {len(manifest_lines) - 5} entries → {manifest_path}")


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
        # Phase 3 (v2.3.0)
        ("statement-family", build_statement_family),
        ("family-mediation-application", build_family_mediation),
        ("household-budget", build_household_budget),
        ("rehabilitation-small", build_rehabilitation_small),
        ("criminal-defense-appointment", build_criminal_defense_appointment),
        ("criminal-settlement", build_criminal_settlement),
        ("guardianship-application", build_guardianship_application),
        ("payment-demand", build_payment_demand),
        ("child-support-application", build_child_support_application),
        ("spousal-support-application", build_spousal_support_application),
        # Phase 4 (v2.7.0)
        ("shareholder-meeting-minutes", build_shareholder_meeting_minutes),
        ("board-meeting-minutes", build_board_meeting_minutes),
        ("small-claims-complaint", build_small_claims_complaint),
        ("immediate-settlement", build_immediate_settlement),
        ("criminal-statement", build_criminal_statement),
        ("contract-review-checklist", build_contract_review_checklist),
        ("work-regulations-template", build_work_regulations_template),
        ("employment-contract", build_employment_contract),
    ]
    for tid, builder in builders:
        out_dir = BUNDLED / tid
        out_dir.mkdir(parents=True, exist_ok=True)
        builder(out_dir)
        print(f"  [OK] {tid} → {out_dir}")
    print(f"\nbuilt {len(builders)} bundled forms")
    _write_manifest()
    return 0


if __name__ == "__main__":
    sys.exit(main())
