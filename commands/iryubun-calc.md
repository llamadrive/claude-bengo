---
description: 遺留分侵害額を民法1042条以下に基づき決定論的に計算
allowed-tools: Read, Glob, Bash(python3 skills/iryubun-calc/calc.py:*), Bash(python3 skills/iryubun-calc/test_calc.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/audit.py:*)
---

遺留分侵害額請求（民法 1046 条）の金銭請求額を、基礎財産・生前贈与・遺贈・相続取得分から算出する。`/inheritance-calc` の結果と組み合わせて使う。

$ARGUMENTS: 対話または JSON 指定。`--matter <id>` で事案明示可。

まず `skills/iryubun-calc/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
