---
description: claude-bengo プラグインを最新版に更新
allowed-tools: Bash(git:*)
---

プラグインディレクトリで `git pull` を実行して最新版に更新する。

```bash
git -C ~/.claude/plugins/claude-bengo pull
```

更新後、変更内容を簡潔に表示する（`git log --oneline -5`）。
