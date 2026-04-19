---
description: 未払残業代を労基法37条に基づいて決定論的に計算
allowed-tools: Read, Glob, Bash(python3 skills/overtime-calc/calc.py:*), Bash(python3 skills/overtime-calc/test_calc.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/audit.py:*)
---

労基法 37 条に基づく未払割増賃金を月別労働時間記録から計算する。割増率（時間外 1.25、60h超 1.5、深夜 +0.25、休日 1.35）を自動適用し、時効 3 年（改正後）の内外を区別する。

## 計算内容

- 基礎賃金 = 月額 ÷ 月平均所定労働時間
- 月別未払額の集計
- 時効内/超過の自動判定
- 遅延損害金（年 3%、オプション）

$ARGUMENTS: 対話で入力、または JSON ファイル指定。

まず `skills/overtime-calc/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
