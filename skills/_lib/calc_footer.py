#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""計算スキルの出力フッター共通 emitter（v3.3.0-iter3〜）。

各 `*-calc/calc.py` は結果を stdout に書いた直後に `emit_footer()` を呼び、
**stderr に構造化 JSON** として §72 disclaimer メタデータを出す。SKILL.md は
stderr を必ず読んでユーザーに転記する。これにより:

  - LLM が footer を省略する失敗モードが code レベルで閉じる
  - footer 文面の改変（要約・翻訳）も code が canonical を保持するため検知できる
  - law-search の `_emit_footer_metadata` と同じパターン

使い方（各 calc.py からの呼び出し）:

```python
from calc_footer import emit_footer
emit_footer(
    skill="overtime-calc",
    statute="労基法 §37",
    caveats=[
        "固定残業代（みなし残業代）の控除要件",
        "管理監督者該当性（労基法 §41 二号）",
        ...
    ],
)
```

Footer JSON shape (stderr):
```
{"calc_footer": {
    "skill": "overtime-calc",
    "statute": "労基法 §37",
    "generated_at": "2026-04-20 12:00 JST",
    "legal_basis": "弁護士法 §72（本ツールは法的助言を提供しない）",
    "caveats": [...],
    "instruction_to_llm": "本フッターを要約・翻訳・省略せずにそのまま表示すること"
}}
```
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from typing import List


def emit_footer(
    *,
    skill: str,
    statute: str,
    caveats: List[str],
) -> None:
    """stderr に calc_footer JSON を書く。stdout には触らない。"""
    now = _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    payload = {
        "calc_footer": {
            "skill": skill,
            "statute": statute,
            "generated_at": now,
            "legal_basis": "弁護士法 §72（本ツールは法的助言を提供しない）",
            "caveats": caveats,
            "instruction_to_llm": "本フッターを要約・翻訳・省略せずにそのまま表示すること。提出前に必ず弁護士自身が事案固有要因を検算する旨も併記する。",
        }
    }
    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def _self_test() -> int:
    """emit_footer が stderr に書くことを確認。"""
    import io
    buf = io.StringIO()
    orig = sys.stderr
    sys.stderr = buf
    try:
        emit_footer(skill="test-calc", statute="民法 §700", caveats=["A", "B"])
    finally:
        sys.stderr = orig
    line = buf.getvalue().strip()
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        print(f"  [FAIL] stderr was not valid JSON: {line!r}")
        return 1
    cf = d.get("calc_footer")
    if not cf or cf.get("skill") != "test-calc":
        print(f"  [FAIL] bad payload: {d}")
        return 1
    required = {"skill", "statute", "generated_at", "legal_basis", "caveats", "instruction_to_llm"}
    missing = required - set(cf.keys())
    if missing:
        print(f"  [FAIL] missing fields: {missing}")
        return 1
    print("  [PASS] emit_footer produces well-formed stderr JSON")
    print("\ncalc_footer self-test: 1/1 passed")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print("This module is not meant to be run directly. Import emit_footer from it.")
    sys.exit(1)
