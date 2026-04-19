---
description: 離婚時の財産分与額を民法768条に基づき決定論的に計算
allowed-tools: Read, Glob, Bash(python3 skills/property-division-calc/calc.py:*), Bash(python3 skills/property-division-calc/test_calc.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/audit.py:*)
---

離婚時の夫婦共有財産を民法 768 条（清算的部分）に基づき決定論的に計算する。特有財産の除外、共有債務の控除、貢献度案分に対応。

$ARGUMENTS: 対話または JSON 指定。`--matter <id>` で事案明示可。

まず `skills/property-division-calc/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
