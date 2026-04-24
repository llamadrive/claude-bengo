---
description: 貸金業者との取引履歴を利息制限法で引き直し、残債務・過払金を算出
allowed-tools: Read, Glob, Bash(python3 skills/debt-recalc/calc.py:*), Bash(python3 skills/debt-recalc/test_calc.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/audit.py:*), Bash(python3 skills/_lib/first_run.py:*)
---

貸金業者との取引履歴（借入・弁済の時系列データ）を利息制限法 1 条の上限利率（20%/18%/15%）で再計算し、真の残元本・支払済利息・過払金を決定論的に算出する。債務整理・過払金返還請求の前提計算。

## 計算内容

- 各期間の利息 = 残元本 × 上限利率 × 日数/365
- 弁済の利息優先充当 → 元本減少
- 過払金発生時は民法 704 条の年 5% 利息を付加

$ARGUMENTS: 対話で取引履歴を入力、または JSON ファイルを指定。

まず `skills/debt-recalc/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
