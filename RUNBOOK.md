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
gpg --version         # GPG 2.x（/bengo-update で signer 検証に使う）
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
  [3] html-report MCP ............. OK
  [4] agent-format MCP ............ OK
  [5] fixtures .................... OK ({N} dirs)
  [6] templates ................... OK
  [7] skills ...................... OK ({M} skills)
```

**失敗時の診断:**
- `MCP サーバが見つからない` → `npm install -g @knorq/xlsx-mcp-server@2.0.0 @knorq/docx-mcp-server@2.0.0 @knorq/html-report-server@2.0.0 @agent-format/mcp@0.1.7` を先に実行する
- `Python not found` → PATH を確認

---

## 3. 事案未設定での機密スキル拒否を確認 (1 分)

事案未作成の状態で、機密スキルを誤って呼ぶと拒否されることを確認する:

```
/template-list
```

**想定結果:**

```
エラー: アクティブな matter が設定されていない。

以下のいずれかを実行してから再度試してほしい:
  /matter-list         — 登録済み matter を確認
  /matter-switch <id>  — 既存 matter に切替
  /matter-create       — 新規 matter を作成
  または --matter <id> フラグで明示指定
```

これが表示されれば matter ガードが効いている。**想定外に「テンプレート 0 件」等のメッセージが出た場合は v1.x の漏れ込みなので、`~/.claude-bengo/matters/` のディレクトリ状況を確認する。**

---

## 4. 最初の事案を作成 (2 分)

```
/matter-create
```

対話で以下のように回答する:

| プロンプト | 回答（初回テスト用） |
|---|---|
| データ取扱い同意 | `yes` |
| matter ID | 空欄（自動生成 `YYYYMMDD-{hex}` を使う） |
| title | `スモークテスト事案` |
| client | 空欄 |
| case_number | 空欄 |
| 作業ディレクトリに matter-ref を置くか | `no`（今回はテストのみ） |
| 既定 matter に設定するか | `yes` |

**想定結果:** `matter '{auto-id}' を作成した` と表示され、以下のコマンドが使えるようになる。

---

## 5. 非機密スキルの動作確認 (2 分)

事案に依存しない 2 スキルをテスト:

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

## 6. 監査ログの確認 (2 分)

機密スキルを動かす前に、監査ログが事案ごとに分離されていることを確認する:

```sh
# [sh] 監査ログが空であることを確認（まだ機密スキルを動かしていないため）
ls ~/.claude-bengo/matters/
cat ~/.claude-bengo/matters/*/audit.jsonl 2>&1 || echo "まだログなし (期待通り)"
```

ここまでで構造確認が終わったら、実データで機密スキルをテストする。

---

## 7. 機密スキルのスモークテスト (5 分)

**事前準備:** テスト用の合成ファイルを用意する（**実在の顧客データは絶対に使わない**）。架空の氏名（甲野太郎、乙山花子）と番地（東京都千代田区霞が関1-1-1）を使う。

### 7a. テンプレート登録

```
/template-create 財産目録.xlsx
```

（事前に架空データで作成した XLSX を指定。なければこのステップはスキップして 7c へ）

**想定結果:** 対話でフィールドを確認し、`~/.claude-bengo/matters/{matter_id}/templates/` に YAML + XLSX ペアが保存される。

### 7b. テンプレート入力

```
/template-fill 通帳.pdf
```

（架空の通帳 PDF を指定）

**想定結果:** 作業ディレクトリに `財産目録_filled.xlsx` が出力される。抽出失敗フィールドは `[要確認]` で黄色背景。

### 7c. 監査ログに記録されていることを確認

```sh
# [sh]
python3 ~/.claude/plugins/claude-bengo/skills/_lib/audit.py verify
```

**想定結果:**

```
## audit.jsonl
PASS line 1
PASS line 2
...
summary: ok=N, fail=0, legacy=0, total=N
```

**`fail=0` であること**がチェーン整合性の証。`fail > 0` の場合はチェーン破綻（改ざんまたはツールバグ）。

### 7d. 改ざん検知のデモ

```sh
# [sh] 監査ログの 1 行を意図的に書き換える（"skill" キー名を大文字化）
python3 -c "
from pathlib import Path
m = next(iter(Path.home().joinpath('.claude-bengo/matters').iterdir()))
log = m / 'audit.jsonl'
text = log.read_text()
# 全レコード共通で含まれる '\"skill\":' を書き換えるため、確実に tampering が発生する
tampered = text.replace('\"skill\":', '\"SKILL\":', 1)
if tampered == text:
    raise SystemExit('ERROR: ログに \"skill\" フィールドが見つからない。7b の実行をやり直してほしい。')
log.write_text(tampered)
print('tampered:', log)
"

# verify が検知するか
python3 ~/.claude/plugins/claude-bengo/skills/_lib/audit.py verify
```

**想定結果:** `FAIL line X: prev_hash mismatch` と表示され exit code が 1 になる。**これが出ないと改ざん検知が機能していないので、インストールをやり直す。**

テスト後、該当事案ディレクトリを削除して元に戻す:

```sh
# [sh] テスト事案を削除
rm -rf ~/.claude-bengo/matters/{test-matter-id}
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
/bengo-update
```

**想定結果:** `git fetch --tags` → 最新タグを探す → **署名付きタグがない場合は中止**。v2.12.0 タグが `git tag -s` で署名されて GitHub に push されていれば、signer を表示して確認を求める。

初回の場合「署名付きリリースが見つからない」と出ても正常（タグ署名は deployment 側の作業）。

---

## 10. サインオフチェックリスト

以下全てが ✅ になればスモークテスト完了:

- [ ] `/verify` が全 OK
- [ ] 事案未設定時の機密スキル拒否が動作
- [ ] `/matter-create` で事案作成成功
- [ ] `/matter-list` で作成事案が見える
- [ ] `/law-search 民法709条` で条文取得
- [ ] `/inheritance-calc` で決定論的な分数計算
- [ ] 機密スキル実行後、`audit.py verify` が fail=0
- [ ] 意図的改ざん後、`audit.py verify` が fail>0 で検知
- [ ] （任意）`/family-tree` で HTML 生成
- [ ] `/bengo-update` が署名付きタグのみを受け入れ

---

## 監査ログの保持ポリシー（v2.6.1〜）

複数の弁護士が日常的に使用する中規模事務所（30-50 人）では、監査ログの
肥大化が運用上の問題になる可能性がある。以下のポリシー策定を推奨する:

### ローテーション制御

各 matter の `audit.jsonl` は 50 MB（既定）でローテートされ、履歴ファイル
として `audit.jsonl.YYYYMMDDTHHMMSS` に切り出される。

**環境変数 `CLAUDE_BENGO_AUDIT_KEEP`** で保持する履歴数を制御できる:

```bash
# 直近 10 世代のみ保持（古いローテート済みは自動削除）
export CLAUDE_BENGO_AUDIT_KEEP=10
```

### 規模別推奨値

| 事務所規模 | CLAUDE_BENGO_AUDIT_KEEP | 備考 |
|---|---|---|
| solo (1-5 人) | 未設定（無制限保持） | ディスク圧迫の心配なし |
| 小規模 (6-30 人) | 20 | 約 1 GB/matter が上限 |
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
chmod 700 ~/.claude-bengo ~/.claude-bengo/matters
```

### matter resolver が意図しない事案を選ぶ

```
/matter-info
```

`source` が `env` / `cwd-ref` / `current` のどれかで解決されている。意図と違えば:

- `env` → `unset MATTER_ID`
- `cwd-ref` → `rm {cwd}/.claude-bengo-matter-ref`
- `current` → `/matter-switch <正しいID>`

---

## リファレンス

- 全コマンド一覧・対応プラットフォーム: `README.md`
- 変更履歴・ブレーキング変更: `CHANGELOG.md`
- プラグイン内部構造・開発者向け規約: `CLAUDE.md`
- 統合テスト: `python3 scripts/e2e.py`
- セルフテスト: `python3 skills/_lib/matter.py --self-test`, `python3 skills/_lib/audit.py --self-test`
