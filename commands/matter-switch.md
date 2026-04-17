---
description: アクティブ matter（既定事案）を切り替える
allowed-tools: Bash(python3 skills/_lib/matter.py:*)
---

current-matter ファイル（`~/.claude-bengo/current-matter`）を更新し、既定事案を切り替える。

$ARGUMENTS: 切替先の matter ID

## 手順

1. ID が指定されていない場合、`/matter-list` の出力を表示して選択肢を提示する
2. ID を検証 + 事案の実在確認を行う:

```bash
python3 skills/_lib/matter.py switch {matter_id}
```

3. 成功時は新しいアクティブ matter を表示する:

```
アクティブ matter を '{matter_id}' に切り替えた。
  既定ファイル: ~/.claude-bengo/current-matter

以降のセッションでも {matter_id} がアクティブ matter となる。
変更したい場合は再度 /matter-switch を実行するか、--matter フラグで明示指定する。
```

## 優先順位の注意

current-matter は 4 段階優先順位の**最下位**である。以下のいずれかが設定されている場合は current-matter より優先される:

1. `--matter` フラグ（コマンド呼出時）
2. `MATTER_ID` 環境変数
3. `{cwd}/.claude-bengo-matter-ref` ファイル（作業ディレクトリに存在する場合）

例えば `cd ~/cases/smith-v-jones` した状態で `.claude-bengo-matter-ref` が置かれていれば、current-matter が別の値でも cwd-ref が優先される。自分の意図と違う matter が選ばれている場合は `/matter-list` → `resolve` で確認してほしい。
