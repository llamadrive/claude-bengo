# bengo-toolkit チートシート — 1 枚リファレンス

書棚や机に貼って使う 1 枚リファレンス。印刷推奨。

---

## 迷ったら覚える 3 コマンド

| コマンド | 用途 |
|---|---|
| **`/help`** | タスクから機能を探す対話メニュー（これだけ覚えれば OK） |
| **`/quickstart`** | 相続・離婚・交通事故の 30 分ツアー（初回用） |
| **`/verify`** | 環境動作確認（不具合時の自己診断） |

## 初回インストール

Claude Code 内で 2 コマンド:

```
/plugin marketplace add llamadrive/bengo-toolkit
/plugin install bengo-toolkit@llamadrive
```

Claude Code を再起動し `/verify` が全 OK を出せば完了。

**もしくは自然言語で:** 「離婚調停の準備したい」「戸籍から家系図作って」「民法709条」

---

## 業務別ワンライナー

### 相続案件
```
/family-tree 戸籍.pdf         → 相続関係説明図 HTML 出力
/inheritance-calc             → 法定相続分（分数で正確）
/iryubun-calc                 → 遺留分侵害額
/template-install             → 「遺産分割協議書」を選択
```

### 離婚案件
```
/property-division-calc       → 財産分与（民法768条）
/child-support-calc           → 養育費・婚姻費用（令和元年方式）
/template-install             → 「離婚協議書」「調停申立書」
```

### 交通事故
```
/traffic-damage-calc          → 赤い本基準で損害賠償
/template-install             → 「交通事故示談書」
/lawsuit-analysis 訴状.pdf    → 訴訟文書の分析
```

### 労働
```
/overtime-calc                → 未払残業代（時効3年判定込）
/template-install             → 「労働審判申立書」「就業規則」
```

### 債務整理
```
/debt-recalc                  → 利息制限法引き直し
/template-install             → 「債権者一覧表」「破産申立書」
```

### 訴訟全般
```
/lawsuit-analysis 訴状.pdf 答弁書.pdf
/typo-check 準備書面.docx     → 校正（修正履歴付き）
/law-search 民法709条         → 条文参照（e-Gov API）
/template-fill 通帳.pdf       → 財産目録に自動入力
```

### 企業法務
```
/template-install             → 「株主総会議事録」「取締役会議事録」
                                 「就業規則」「契約書レビューチェックリスト」
```

---

## 案件フォルダ（v3.0.0〜）

```
cd ~/cases/smith-v-jones      → 案件フォルダに移動
claude                        → Claude Code 起動（案件は CWD から自動解決）
/case-info                    → 現在の案件状態を確認
/audit-config                 → 監査ログ設定
```

機密スキル（typo-check, template-fill, family-tree, lawsuit-analysis 等）を
最初に使ったときに `.claude-bengo/` が自動作成される。事前登録は不要。
別の案件へは `cd` するだけで切替わる。

---

## 同梱テンプレート 31 種（`/template-install` で選ぶ）

| カテゴリ | 主な書式 |
|---|---|
| **家事事件** | 離婚協議書・調停申立書・婚姻費用分担・陳述書・養育費・後見 |
| **相続** | 遺産目録・相続放棄・遺産分割協議書 |
| **企業法務** | 株主総会・取締役会・就業規則・契約書レビュー・労働契約書 |
| **破産・再生** | 債権者一覧表・破産申立・個人再生・家計収支表 |
| **民事訴訟** | 訴状・答弁書・支払督促・少額訴訟・即決和解 |
| **労働** | 残業代計算書・労働審判・労働契約書 |
| **刑事弁護** | 弁護人選任・刑事示談・刑事陳述書 |
| **交通事故** | 示談書 |
| **一般民事** | 内容証明 |
| **汎用** | 委任状 |

---

## 決定論計算器 7 種

LLM の推論ではなく確定ロジック（分数演算）で計算。法廷で結果の根拠を問われても確定的。

| コマンド | 根拠法令 |
|---|---|
| `/inheritance-calc` | 民法887・889・890・900条（代襲・半血・放棄対応） |
| `/traffic-damage-calc` | 赤い本（民事交通事故訴訟損害賠償額算定基準） |
| `/child-support-calc` | 令和元年改定算定方式 |
| `/debt-recalc` | 利息制限法 + 民法704条（年5%利息） |
| `/overtime-calc` | 労基法37条（時間外1.25/60h超1.5/深夜+0.25/休日1.35・時効3年） |
| `/iryubun-calc` | 民法1042-1048条 |
| `/property-division-calc` | 民法768条 |

---

## トラブル時

| 症状 | 対処 |
|---|---|
| 案件フォルダが意図と違う | `/case-info` で確認 → 正しいフォルダへ `cd` |
| `MCP サーバが見つからない` | `/verify` → 指示された npm install を実行 |
| PDF が読めない | 300dpi+ でスキャン、または OCR 処理 |
| 書式位置がズレる | `/template-create` で再登録 |
| 更新したい | `/plugin install bengo-toolkit@llamadrive`（Claude Code 標準） |

---

## フィードバック

- バグ・機能要望: https://github.com/llamadrive/bengo-toolkit/issues
- セキュリティ: `security@llama-drive.com`
- 週次レビュー: パイロット期間中のみ、担当マネージャへ Slack / メール

バージョン: **v3.3.0** | 最終更新: 2026-04-20（単一情報源: `.claude-plugin/plugin.json`）
