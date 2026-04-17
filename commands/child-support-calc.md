---
description: 養育費・婚姻費用を令和元年改定算定方式で決定論的に計算
allowed-tools: Read, Glob, Bash(python3 skills/child-support-calc/calc.py:*), Bash(python3 skills/child-support-calc/test_calc.py:*), Bash(python3 skills/_lib/matter.py:*), Bash(python3 skills/_lib/audit.py:*)
---

離婚後の養育費（民法 766条・877条）、または別居中の婚姻費用（民法 760条）を、令和元年 12 月改定の標準算定方式に基づいて計算する。東京家裁・大阪家裁公開の算定表と原理的に一致する式を用い、決定論的な目安額を提示する。

## 計算項目

- **養育費**: 子の扶養費。離婚後の監護親が他方に請求
- **婚姻費用**: 夫婦間の生活費分担。別居中に収入の低い側が請求

## 計算方式

1. 基礎収入 = 年収 × 基礎収入割合（給与所得者・自営業者で異なる）
2. 生活費指数: 親 100 / 子 0-14 歳 62 / 15-19 歳 85
3. 養育費月額 = (子の生活費 × 義務者基礎収入 / 両親基礎収入合計) / 12
4. 婚姻費用月額 = (権利者世帯の生活費 - 権利者基礎収入) / 12

$ARGUMENTS: 対話で入力するか、JSON ファイルを指定する。`--matter <id>` で事案を明示指定可能。

## 使い方

まず `skills/child-support-calc/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
