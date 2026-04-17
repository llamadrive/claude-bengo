---
description: 登録済み matter（事案）の一覧を表示する
allowed-tools: Bash(python3 skills/_lib/matter.py:*)
---

登録済みの matter（事案）を一覧表示する。

## 手順

```bash
python3 skills/_lib/matter.py list
```

出力はテキスト形式（既定）。各 matter について id・title・client・case_number・opened・templates 数・path を表示する。

JSON で欲しい場合は `--format json` を付ける。

## アクティブ matter も併せて表示

リスト表示後、現在解決されている matter を付け加える:

```bash
python3 skills/_lib/matter.py resolve
```

`source` が `flag` / `env` / `cwd-ref` / `current` / `none` のいずれで解決されたかを案内する。`none` の場合は `/matter-create` か `/matter-switch` を案内する。

## 表示例

```
登録済み matter:

  smith-v-jones
    title:       Smith v. Jones 損害賠償請求事件
    client:      Smith Corporation
    case_number: 令和6年（ワ）第1234号
    opened:      2026-04-17
    templates:   3 件
    path:        /Users/you/.claude-bengo/matters/smith-v-jones

  20260415-a1b2c3
    title:       imported-from-case-001
    templates:   5 件
    path:        /Users/you/.claude-bengo/matters/20260415-a1b2c3

現在のアクティブ matter: smith-v-jones（解決元: cwd-ref at /Users/you/cases/smith-v-jones/.claude-bengo-matter-ref）
```

## 0件の場合

登録済み matter がない場合は `/matter-create` を案内する。
