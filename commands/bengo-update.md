---
description: claude-bengo プラグインを最新版に更新（署名付きタグのみ）
allowed-tools: Bash(git:*), Read
---

claude-bengo プラグインを、GPG 署名付きの最新リリースタグへ更新する。

## セキュリティ方針

- **HEAD ではなく署名付きタグから更新する** — 署名のないコミットは取り込まない
- **ユーザー承認なしに更新しない** — 変更内容をユーザーに確認してもらってから `git merge` を実行する
- **ロールバック可能にする** — 現在のコミット SHA を事前に記録する

## 手順

プラグインディレクトリ（通常 `~/.claude/plugins/claude-bengo`）で以下を順に実行する。プラグインディレクトリのパスはユーザーに確認するか、`$CLAUDE_PLUGIN_ROOT` 環境変数があればそれを使う。

### Step 1: 現在の状態を記録

```bash
git -C {plugin_dir} rev-parse HEAD
```

現在の SHA を記憶する（ロールバック用）。

### Step 2: リモートタグを取得

```bash
git -C {plugin_dir} fetch --tags --prune
```

### Step 3: 最新の署名付きタグを検索

```bash
git -C {plugin_dir} tag -l 'v*' --sort=-version:refname
```

結果の先頭のタグから順に署名を検証する:

```bash
git -C {plugin_dir} verify-tag {tag_name} 2>&1
```

- 署名検証に**成功**したタグを採用する
- 署名がない、または検証に失敗したタグはスキップする
- 全てのタグで署名検証に失敗した場合、ユーザーに「署名付きリリースが見つからない。更新を中止する」と報告して終了する

### Step 4: 変更内容を表示

採用するタグと現在の HEAD を比較する:

```bash
git -C {plugin_dir} log --oneline {current_sha}..{tag_name}
git -C {plugin_dir} diff --stat {current_sha}..{tag_name}
```

さらに、`CHANGELOG.md` が存在する場合は該当バージョンのセクションを抽出して表示する。

### Step 5: ユーザー承認

以下の形式で確認する:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  claude-bengo アップデート確認
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  現在: {current_sha_short} ({current_tag or "unknown"})
  更新先: {new_tag} (署名検証: OK / 署名者: {signer})

  変更コミット数: {N} 件
  変更ファイル数: {M} 件

  主な変更:
  - {commit1}
  - {commit2}
  ...

  続行するか？（yes/no）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**ユーザーが `yes` 以外を回答した場合は更新を中止する。** 自然言語の曖昧な回答（「うん」「たぶん」等）は `no` として扱う。

### Step 6: タグへチェックアウト

承認されたら、タグへ明示的にチェックアウトする（`git pull` は使わない — ローカル変更を勝手にマージしないため）:

```bash
git -C {plugin_dir} checkout {tag_name}
```

ローカルに未コミットの変更がある場合は checkout が失敗する。その場合はユーザーに「プラグインディレクトリに未コミットの変更がある。手動で確認してほしい」と報告して中止する。**`--force` は絶対に使わない。**

### Step 7: MCP サーバ再起動の案内

`.mcp.json` に変更があった場合、Claude Code の再起動を促す:

```bash
git -C {plugin_dir} diff {current_sha} {tag_name} -- .mcp.json
```

差分があれば「MCP サーバ設定が変更された。Claude Code を再起動して設定を反映してほしい」と案内する。

### Step 8: 結果サマリー

```
更新完了: {current_tag or current_sha_short} → {new_tag}
ロールバック手順: git -C {plugin_dir} checkout {current_sha}
```

## エラーハンドリング

- **署名検証失敗**: 「タグ {tag} の署名を検証できない（gpg 鍵がインポートされていないか、不正な署名）。更新を中止する。GPG 公開鍵のインポート手順は README を参照してほしい」
- **ローカル変更がある**: 「プラグインディレクトリに未コミットの変更がある: `{files}`。手動で確認してから再実行してほしい」
- **ネットワークエラー**: 「GitHub への接続に失敗した。インターネット接続を確認してほしい」
- **署名付きタグが1件もない**: 「署名付きリリースが公開されていない。プラグイン提供元に確認してほしい」
