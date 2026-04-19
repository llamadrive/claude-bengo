---
description: 交通事故の損害賠償額を赤い本基準で決定論的に計算
allowed-tools: Read, Glob, Bash(python3 skills/traffic-damage-calc/calc.py:*), Bash(python3 skills/traffic-damage-calc/test_calc.py:*), Bash(python3 skills/_lib/workspace.py:*), Bash(python3 skills/_lib/audit.py:*)
---

交通事故による人身損害の賠償額を、日弁連交通事故相談センター東京支部編「民事交通事故訴訟損害賠償額算定基準」（通称「赤い本」）の基準に従って計算する。LLM の推論ではなく、判例と実務で確立した表値・係数を用いた決定論的計算。

## 計算項目

- 積極損害（治療費・交通費・装具費・入院雑費・付添看護費）
- 消極損害（休業損害・後遺障害逸失利益・死亡逸失利益、Leibniz 係数による中間利息控除）
- 慰謝料（入通院・後遺障害・死亡、赤い本別表 I/II 準拠）
- 弁護士費用（10%、判例実務）
- 遅延損害金（年3%、改正民法 404 条）
- 過失相殺（民法 722 条 2 項）

$ARGUMENTS: 対話で入力するか、JSON ファイルを指定する。`--matter <id>` フラグで明示的に事案を指定可能。

## 使い方

対話形式で被害者・事故・治療情報を順次確認する。具体的な手順は `skills/traffic-damage-calc/SKILL.md` に従う。

まず `skills/traffic-damage-calc/SKILL.md` を Read ツールで読み込み、そこに記載された手順に従って実行する。
