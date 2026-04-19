# claude-bengo 初回インストール スモークテスト runbook

法律事務所への導入時の最初のチェックリスト。新規端末に claude-bengo を配置し、基本機能が動作することを 15〜20 分で確認する。

全てのコマンドは**ターミナル**ではなく、**Claude Code セッション内で実行**することを前提とする（`/verify` 等のスラッシュコマンドは Claude Code の UI から呼び出す）。Python / git 等の直接コマンドは **[sh]** と明記する。

---

## 0. 前提環境の確認 (2 分)

```sh
# [sh] 以下のコマンドで各バージョンを確認する
node --version        # v18.0.0 以上
python3 --version     # 3.8 以上
git --version         # 2.20 以上（signed tag 検証のため）
# gpg は v3.0.1 以降不要（Claude Code 標準の /plugin install が更新を担う）
```

**想定結果:** 全てバージョン表示。1 件でも「command not found」なら、該当ツールをインストールしてから再実行。

---

## 1. プラグイン配置 (1 分)

Claude Code を起動し、**Claude Code 内で** 以下 2 行を実行する（ターミナル作業は不要）:

```
/plugin marketplace add llamadrive/claude-bengo
/plugin install claude-bengo@claude-bengo
```

**想定結果:** 各コマンドが「Added marketplace...」「Installed claude-bengo v2.14.0」等を返す。その後 Claude Code を再起動。

**失敗時の診断:**
- `already exists` → 前回の試行が残っている。`/plugin marketplace remove claude-bengo` で削除してから再試行
- `network error` → 企業プロキシ環境では `HTTPS_PROXY` を設定してから Claude Code を起動する
- `node / npm / python3 not found` → Node.js 18+ / Python 3.8+ を先にインストール

---

## 2. Claude Code を起動して /verify を実行 (2 分)

Claude Code を起動し、プラグインが読み込まれていることを確認する:

```
/verify
```

**想定結果（期待出力）:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  claude-bengo 動作確認レポート
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [1] xlsx-editor MCP ............. OK
  [2] docx-editor MCP ............. OK
  [3] agent-format MCP ............ OK
  [4] fixtures .................... OK ({N} dirs)
  [5] templates ................... OK
  [6] skills ...................... OK ({M} skills)
```

**v3.0.0〜の補足:** matter 作成ステップは廃止された。`cd` したフォルダが
案件となり、機密スキルを最初に使ったときに `.claude-bengo/` が自動作成される。

**失敗時の診断:**
- `MCP サーバが見つからない` → `npm install -g @knorq/xlsx-mcp-server@2.0.0 @knorq/docx-mcp-server@2.0.0 @agent-format/mcp@0.1.9` を先に実行する
- `Python not found` → PATH を確認

---

## 3. 試用フォルダを準備 (1 分)

v3.0.0 では「フォルダ = 案件」。スモークテスト用の試用フォルダを作る:

```sh
# [sh]
mkdir -p ~/cases/smoke-test
cd ~/cases/smoke-test
```

Claude Code を起動していた場合は、このフォルダから起動し直す（案件
コンテキストが CWD から解決されるため）:

```sh
# [sh]
cd ~/cases/smoke-test && claude
```

**ポイント:** `/matter-create` は廃止された。このフォルダで機密スキルを
最初に動かすと、`.claude-bengo/` が自動作成される。事前登録は不要。

---

## 4. 非機密スキルの動作確認 (2 分)

案件に依存しない 2 スキルをテスト:

```
/law-search 民法709条
```

**想定結果:** e-Gov API から民法709条の条文テキスト（「故意又は過失によって他人の権利又は法律上保護される利益を...」）が整形表示される。失敗時はインターネット接続を確認。

```
/inheritance-calc
配偶者と子供3人、子1人が相続放棄した場合の法定相続分
```

**想定結果:** 決定論的計算による分数表示。**Fraction ベースなので丸め誤差なし。**

```
| 相続人 | 法定相続分 |
|-------|----------|
| 配偶者 | 1/2     |
| 子1   | 1/4     |
| 子2   | 1/4     |
```

---

## 5. 機密スキルのスモークテスト (5 分)

**事前準備:** テスト用の合成ファイルを用意する（**実在の顧客データは絶対に使わない**）。架空の氏名（甲野太郎、乙山花子）と番地（東京都千代田区霞が関1-1-1）を使う。

### 5a. テンプレート登録（CWD = ~/cases/smoke-test で実行）

```
/template-create 財産目録.xlsx
```

**想定結果:** 対話でフィールドを確認し、`~/cases/smoke-test/.claude-bengo/templates/` に YAML + XLSX ペアが保存される（案件フォルダが自動初期化される）。

### 5b. テンプレート入力

```
/template-fill 通帳.pdf
```

**想定結果:** 作業ディレクトリに `財産目録_filled.xlsx` が出力される。抽出失敗フィールドは `[要確認]` で黄色背景。

### 5c. 監査ログ確認

```sh
# [sh] cd ~/cases/smoke-test 前提
ls -la .claude-bengo/
cat .claude-bengo/audit.jsonl | head -5
python3 ~/.claude/plugins/cache/claude-bengo/claude-bengo/3.0.0/skills/_lib/audit.py verify
```

**想定結果:**

```
## audit.jsonl
PASS line 1
...
summary: ok=N, fail=0, legacy=0, total=N
```

**`fail=0`** がチェーン整合性の証。

### 5d. 改ざん検知デモ

```sh
# [sh]
python3 -c "
from pathlib import Path
log = Path('.claude-bengo/audit.jsonl')
text = log.read_text()
tampered = text.replace('\"skill\":', '\"SKILL\":', 1)
if tampered == text:
    raise SystemExit('ERROR: ログに \"skill\" フィールドが見つからない')
log.write_text(tampered)
print('tampered:', log)
"

python3 ~/.claude/plugins/cache/claude-bengo/claude-bengo/3.0.0/skills/_lib/audit.py verify
```

**想定結果:** `FAIL line X: prev_hash mismatch` と表示され exit 1。

後始末:

```sh
# [sh] 試用フォルダまるごと削除
cd && rm -rf ~/cases/smoke-test
```

---

## 8. 家族関係図の HTML 出力確認（任意、2 分）

架空の戸籍 PDF があれば:

```
/family-tree 戸籍謄本.pdf
```

**想定結果:** 作業ディレクトリに `family_tree_YYYY-MM-DD.html` が生成される。ブラウザで開くと SVG で相続関係説明図が表示される（裁判所標準形式）。Base64 エンコード経由のため、PDF に悪意あるスクリプトが埋め込まれていても HTML として解釈されない。

---

## 9. 更新フローの確認 (1 分)

```
/plugin install claude-bengo@claude-bengo
```

**想定結果:** Claude Code が marketplace.json を読んで最新バージョンを展開
する。既にインストール済みの場合は「already installed」と出ることも。
Claude Code を再起動して `/verify` で新バージョンが走っていることを確認。

（v2 時代の `/bengo-update` は v3.0.1 で廃止。Claude Code 標準機能に統合した。）

---

## 10. サインオフチェックリスト

以下全てが ✅ になればスモークテスト完了:

- [ ] `/verify` が全 OK
- [ ] 試用フォルダ（CWD）で機密スキル実行 → `.claude-bengo/` が自動生成
- [ ] `/law-search 民法709条` で条文取得
- [ ] `/inheritance-calc` で決定論的な分数計算
- [ ] 機密スキル実行後、`audit.py verify` が fail=0
- [ ] 意図的改ざん後、`audit.py verify` が fail>0 で検知
- [ ] （任意）`/family-tree` で `.agent` 生成
- [ ] `/plugin install claude-bengo@claude-bengo` で更新（再起動後 /verify）

---

## 監査ログの保持ポリシー（v2.6.1〜）

複数の弁護士が日常的に使用する中規模事務所（30-50 人）では、監査ログの
肥大化が運用上の問題になる可能性がある。以下のポリシー策定を推奨する:

### ローテーション制御

各案件フォルダの `./.claude-bengo/audit.jsonl` は 50 MB（既定）でローテートされ、
履歴ファイルとして `audit.jsonl.YYYYMMDDTHHMMSS` に切り出される。

**環境変数 `CLAUDE_BENGO_AUDIT_KEEP`** で保持する履歴数を制御できる:

```bash
# 直近 10 世代のみ保持（古いローテート済みは自動削除）
export CLAUDE_BENGO_AUDIT_KEEP=10
```

### 規模別推奨値

| 事務所規模 | CLAUDE_BENGO_AUDIT_KEEP | 備考 |
|---|---|---|
| solo (1-5 人) | 未設定（無制限保持） | ディスク圧迫の心配なし |
| 小規模 (6-30 人) | 20 | 約 1 GB/案件 が上限 |
| 中規模 (31-100 人) | 10 | 別途外部ストレージ（S3 Object Lock 等）への定期エクスポート必須 |
| 大規模 (100 人超) | 5 | 外部 WORM ストレージ連携を前提とする運用 |

### 外部エクスポート（推奨）

中規模以上では、監査ログをローカル保持するだけでなく、顧客管理の
追記専用ストレージ（S3 Object Lock / Azure Immutable Storage 等）に
定期エクスポートすることを強く推奨する。これによりハッシュチェーンの
整合性を外部ポイントで検証でき、`rm -rf` による履歴抹消のリスクが下がる。

エクスポートスクリプト例（cron で日次実行）:

```bash
python3 ~/.claude/plugins/claude-bengo/skills/_lib/audit.py export \
  --format csv --since $(date -v-1d +%Y-%m-%d) \
  > /path/to/export/audit-$(date +%Y-%m-%d).csv
# その後、aws s3 cp で Object Lock 有効なバケットへアップロード
```

## 本番運用に移す前の追加確認

- [ ] `~/.claude-bengo/` が `0o700` になっていること（`ls -ld ~/.claude-bengo/`）
- [ ] `@knorq/xlsx-mcp-server@2.0.0` 等が `npm --provenance` 表示で確認できること（`npm view @knorq/xlsx-mcp-server --json | grep provenance`）
- [ ] 事務所の AI 利用ポリシー・弁護士法第23条・個人情報保護法要件との整合性を内部確認済みであること
- [ ] 監査ログの外部エクスポート（S3 Object Lock 等）を実施する運用フローが合意されていること
- [ ] Anthropic API の ZDR 契約を結ぶかを事務所として決定済みであること
- [ ] 複数端末展開の場合: `README.md` の「複数台への展開（fleet 配布）」セクションに従い Jamf/Intune スクリプトを準備済み

---

## トラブルシューティング

### MCP サーバが応答しない

```sh
# [sh] 手動で MCP サーバを起動してみる
npx -y @knorq/xlsx-mcp-server@2.0.0 2>&1 | head -5
```

`command not found` が出る場合は `npm install -g @knorq/...` で事前インストール。プロキシ環境では `HTTPS_PROXY` / `NODE_EXTRA_CA_CERTS` を設定（README 参照）。

### Python スクリプトが import エラー

```sh
# [sh] python3 の場所を確認
which python3
# pathlib.Path が動くか
python3 -c "from pathlib import Path; print(Path.home())"
```

Python 3.8 未満が呼ばれている可能性。`python3 --version` で確認。

### `~/.claude-bengo/` のパーミッション不正

```sh
# [sh] 手動修正（POSIX のみ）
chmod 700 ~/cases/*/.claude-bengo
```

### 案件フォルダ（workspace）が意図しないパスで解決される

```
/case-info
```

`workspace_root` として表示されるディレクトリが想定と違う場合:
- CWD のどこか上流に `.claude-bengo/` が存在している（git 的 walk-up）
- 意図しない親フォルダの `.claude-bengo/` を削除するか、別の場所に `cd` する

### プラグイン更新が "already installed globally" で失敗する

Claude Code の既知のバグ（[#16174](https://github.com/anthropics/claude-code/issues/16174) 他）。
marketplace catalogue を更新しても、`installed_plugins.json` のエントリが
残っていると `/plugin install` が再取得を拒否する。cache ディレクトリが
欠落している場合でも同じ症状が出る（ゴースト状態）。

**推奨: auto-update を有効化する**

`/plugin` → Marketplaces タブ → claude-bengo → "Enable auto-update" を選ぶ。
Claude Code 起動時に marketplace と plugin が自動更新される。更新時は
「`/reload-plugins` を実行してほしい」という通知が出る。

**手動更新（auto-update なしの場合）**

```
/plugin marketplace update claude-bengo      ← catalogue のみ refresh
/plugin uninstall claude-bengo@claude-bengo  ← 一度削除
/plugin install claude-bengo@claude-bengo    ← 新バージョンで再取得
/reload-plugins
```

**ゴースト状態の復旧（install が "already installed" と言い続ける）**

Claude Code を完全終了（Cmd+Q）した上で、ターミナルから:

```sh
python3 -c "
import json
from pathlib import Path
r = Path.home() / '.claude/plugins/installed_plugins.json'
d = json.loads(r.read_text())
d['plugins'].pop('claude-bengo@claude-bengo', None)
r.write_text(json.dumps(d, indent=2) + chr(10))
print('removed')
"
```

Claude Code を起動しなおして `/plugin install claude-bengo@claude-bengo` を再実行する。

---

## リファレンス

- 全コマンド一覧・対応プラットフォーム: `README.md`
- 変更履歴・ブレーキング変更: `CHANGELOG.md`
- プラグイン内部構造・開発者向け規約: `CLAUDE.md`
- 統合テスト: `python3 scripts/e2e.py`
- セルフテスト: `python3 skills/_lib/workspace.py --self-test`, `python3 skills/_lib/audit.py --self-test`
