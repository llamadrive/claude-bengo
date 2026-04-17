# Changelog

本プロジェクトの変更履歴を [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) 形式で記録する。バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [2.6.1] - 2026-04-17

v2.6.0 直後の triple-PE（Anthropic・OpenAI・Harvey）による最終レビューで
指摘された Tier 2 向けブロッカー・Harvey 競合分析上の demo 攻撃角度・
Anthropic の minor hardening 項目を一括対応。これにより OpenAI は Tier 2
フル承認、Harvey の 4 つの new demo 角度のうち 3 つが無効化される。

### Security / Hardening

- **V26-OPS-001** `skills/child-support-calc/calc.py`: `_child_index` と
  `_validate` で bool/float の age を明示的に拒否。`age=19.5` → 15-19
  指数として扱う silent bug を修正。`age=True` / `annual_income=True` も拒否。
- **V26-OPS-002** `skills/debt-recalc/calc.py:102`: 取引 amount の
  bool を明示的に拒否。`amount=True` → ¥1 取引として扱う silent bug を修正。
- **V26-001** `skills/_lib/xlsx_writer.py:60-80`: `write_cell` 入力ガード。
  `float('inf')` / `float('nan')` / 文字列内 NUL バイト を明示的に拒否。
  Excel ファイル破損の future-proofing（build 時のみ呼ばれるため現時点では
  live 攻撃面はない）。

### Compliance / Audit

- **V26-OPS-003 (Tier 2 ブロッカー)** 4 計算器と `/template-install` に
  監査ログ hook を追加:
  - `traffic-damage-calc/SKILL.md`: 計算前 `calc_run`、計算後 `calc_result`
    （合計額内訳を note に）
  - `child-support-calc/SKILL.md`: 同様に月額計算結果を記録
  - `debt-recalc/SKILL.md`: 過払金額・残元本を記録
  - `overtime-calc/SKILL.md`: 時効内未払額・遅延損害金を記録
  - `commands/template-install.md`: インストール後に `file_write` を記録
  - `audit.py` の `VALID_EVENTS` に `calc_run` と `calc_result` を追加
  効果: ¥60M 養育費計算や ¥6M 過払金計算が無痕跡で実行される問題を解消。
  法律事務所のコンプライアンス監査要件（弁護士会・法務部監査）を満たす。

### Supply Chain Security (Harvey デモ対策)

- **Template integrity manifest** `scripts/build_bundled_forms.py`:
  `_write_manifest()` が `templates/_bundled/_manifest.sha256` を生成。
  全 46 ファイル（23 × {yaml, xlsx}）の SHA-256 を記録。
- **`template_lib.install_template()`**: `_verify_bundled_integrity()` で
  install 前にマニフェストと照合。改ざん検知時は `ValueError` で停止し、
  `/bengo-update` による再取得を案内。マニフェスト不在の場合は警告のみで
  続行（後方互換）。
- **`--skip-integrity` オプション**: 検証を明示的にスキップ（デバッグ用、
  非推奨）。

  Harvey の "template supply-chain swap" デモが機能しなくなる:
  プラグイン配布後に `templates/_bundled/complaint-loan-repayment.yaml`
  の field mapping を書き換えると install 時に hash mismatch で停止。

### Entropy / Identity

- **`audit.py` session ID bump** `secrets.token_hex(6)` → `secrets.token_hex(16)`:
  48 bit → 128 bit。birthday collision 確率を ~16M セッションから ~18 兆兆
  セッションに引き上げ。Harvey のデモで「session_id が 12 hex しかない」
  との批判を無効化。

### Documentation

- **`RUNBOOK.md`** に「監査ログの保持ポリシー」セクションを追加。
  事務所規模（solo / 小/中/大規模）別の `CLAUDE_BENGO_AUDIT_KEEP` 推奨値、
  S3 Object Lock 等への外部エクスポート運用例（cron 日次）。
- **`templates/_bundled/_registry.yaml` settlement-traffic**: 清算条項に
  後遺障害カーブアウトを手動追加すべき旨を description に明記（Anthropic
  のフォーム内容レビュー指摘対応）。

### Tests

- `child-support-calc/test_calc.py`: 23 tests (v2.6.0 の 20 + float/bool
  age 拒否 + bool annual_income 拒否)
- `debt-recalc/test_calc.py`: 16 tests (v2.6.0 の 15 + bool amount 拒否)
- `xlsx_writer.py`: 4 tests (v2.6.0 の 3 + inf/NaN/NUL 拒否ガード)
- E2E: 49/49 維持（test count 依存を "0 failed" チェックに切替え、release
  ごとのメンテナンスを不要化）

### PE Review Posture Summary

- **Anthropic**: Approve → Approve（変化なし、V26-001 対応済み）
- **OpenAI**: Tier 3 Approve / Tier 2 Conditional → Tier 3 Approve /
  **Tier 2 Approve**（V26-OPS-001/002/003 対応済み）
- **Harvey**: 🟡→🟠 competitive threat での 4 つの new demo 角度のうち
  - ✅ Template supply-chain swap: 対応済（manifest 検証）
  - ✅ Session ID collision: 対応済（entropy 48→128 bit）
  - ✅ Calculator edge-case silent extrapolation: 部分対応（validation
    強化で silent ではなくなる）
  - ❌ 23-form PII exhaust: 構造的。US residency 対応が必要 → Tier 1 領域

### 未対応（Tier 1 構造的ブロッカー、本 release 範囲外）

- US data residency（Anthropic API)
- SSO / 弁護士登録番号 binding
- 企業 MSA / DPA 法人格
- WORM 監査ログ（local 削除は依然可能、external export が前提）
- iManage / D1-Law / Westlaw-Japan integration
- 企業法務 (契約書レビュー・株主総会議事録) の深堀り

いずれも Path C-enterprise（別 SaaS 製品）で対応する領域。

## [2.6.0] - 2026-04-17

**Track B complete**: 2 つの残タスク `/debt-recalc`（利息制限法引き直し）と
`/overtime-calc`（労基法 37 条割増賃金計算）を同時リリース。これで Track B
の当初スコープがすべて出揃い、SMB 弁護士の日常的な決定論計算タスクの
~65-70% をカバーする。

### Added — debt-recalc

- **`skills/debt-recalc/calc.py`** (~270 行): 貸金業者との取引履歴を
  利息制限法 1 条の上限利率（20%/18%/15%）で引き直し、残元本・過払金・
  過払金利息（民法 704 条の年 5%）を決定論的に算出
- **`skills/debt-recalc/test_calc.py`** (15/15 pass): 利率ブラケット判定、
  同日取引処理（借入→弁済順）、弁済の利息優先充当、元本ブラケット遷移、
  長期返済での過払金発生、過払金利息加算、取引件数混合、バリデーション
- **`skills/debt-recalc/references/risokuhou-guide.md`**: 利息制限法の
  歴史（グレーゾーン金利廃止）、時効 10 年・悪意の受益者要件、取引一連性の
  判例実務、充当順序、計算例 2 件
- **`skills/debt-recalc/SKILL.md`**: matter-aware 5 ステップの対話ワークフロー
- **`commands/debt-recalc.md`**: `/debt-recalc` slash command

### Added — overtime-calc

- **`skills/overtime-calc/calc.py`** (~270 行): 労基法 37 条に基づく未払
  割増賃金を月別労働時間記録から決定論的に算出。時間外 1.25 / 60h 超 1.5 /
  深夜 +0.25 / 休日 1.35 の全組合せに対応。時効 3 年（2020/04 改正後）/
  2 年（改正前）の自動区別
- **`skills/overtime-calc/test_calc.py`** (16/16 pass): 基礎賃金算定、
  時給切り上げ、全組合せの割増率、複数月合算、時効内外区別、年間休日→
  月平均計算、遅延損害金年 3%、バリデーション
- **`skills/overtime-calc/references/labor-guide.md`**: 割増率表、基礎賃金
  算定式、除外手当（家族・通勤・住宅）、時効制度の改正経緯、証拠収集、
  固定残業代・管理監督者・変形労働時間制の例外、計算例 3 件
- **`skills/overtime-calc/SKILL.md`**: matter-aware 6 ステップの対話
- **`commands/overtime-calc.md`**: `/overtime-calc` slash command

### Track B 完成: 4 計算器 + 既存 inheritance-calc の合計 5 スキル

| スキル | 分野 | SMB 業務占有率 | テスト |
|---|---|---|---|
| `/inheritance-calc` | 相続 | ~15% | 19/19 |
| `/traffic-damage-calc` | 交通事故 | ~20% | 20/20 |
| `/child-support-calc` | 家事（養育費・婚姻費用） | ~15% | 20/20 |
| `/debt-recalc` | 破産・再生 | ~10% | 15/15 |
| `/overtime-calc` | 労働 | ~5-10% | 16/16 |
| **合計** | | **~65-70%** | **90/90** |

### Track A + B 総合カバレッジ

Track A（同梱テンプレート 23 種）と Track B（決定論計算 5 種）が揃ったことで、
日本の SMB 弁護士の**書式作成 70% + 決定論計算 65-70%** をこのプラグイン
単体で対応できる。残る gap（Tier 1 BigLaw の SOC2/SSO/residency/MSA・
電子申立・判例検索等）は構造的で、別プロダクト化が必要な領域。

### Verification

- `debt-recalc`: 15/15 pass
- `overtime-calc`: 16/16 pass
- E2E: 49/49 pass (v2.5.0 の 45 + debt-recalc 2 + overtime-calc 2)
- CI: 3 OS × 3 Python = 9 マトリクス × 計 5 計算器 × 単体+E2E すべて緑

### 運用フロー例

**債務整理フロー:**
```
/matter-create                        — 事案作成
/template-install creditor-list       — 債権者一覧表雛形
/template-install household-budget    — 家計収支表雛形
/debt-recalc                          — 各債権者の引き直し計算
/template-install bankruptcy-dohaishi — 破産申立書雛形
/template-fill                        — 計算結果を申立書に転記
```

**労働事件フロー:**
```
/matter-create
/template-install overtime-calc-sheet   — 未払残業代計算書雛形
/overtime-calc                          — 月別計算
/template-install labor-tribunal-application — 労働審判申立書雛形
/template-fill
```

## [2.5.0] - 2026-04-17

Track B-2: `/child-support-calc` — 養育費・婚姻費用の決定論的計算器。
家事事件（SMB 実務の ~15%）のコア計算を令和元年改定算定方式で自動化。
Track A Phase 3 で追加した `child-support-application`・`divorce-agreement`・
`family-mediation-application` 等の書式と直接連携する。

### Added — child-support-calc

- **`skills/child-support-calc/calc.py`** (~300 行): 令和元年改定標準算定方式
  に基づく決定論的計算。Fraction ベースで exact math。養育費（民法 766・
  877 条）と婚姻費用（民法 760 条）の両方に対応。
- **`skills/child-support-calc/test_calc.py`** (20/20 pass): 算定表の
  代表的セルを網羅。給与/自営の基礎収入割合・子の指数（0-14 歳=62、
  15-19 歳=85）・1,000 円単位丸め・算定表範囲内の値一致・高額所得警告・
  権利者＞義務者ケース・子 3 人までの扶養・年収上昇に伴う単調増加
- **`skills/child-support-calc/references/santei-hyou.md`**: 基礎収入割合
  テーブル（給与・自営）、生活費指数、計算例（養育費・婚姻費用）、
  個別加算事由（住宅ローン・私立学校費用・医療費等）の解説
- **`skills/child-support-calc/SKILL.md`**: matter-aware 対話ワークフロー
- **`commands/child-support-calc.md`**: `/child-support-calc` slash command

### 計算式（実装）

**養育費:**
```
義務者基礎収入 = 義務者年収 × 基礎収入割合（給与42% or 自営54% 等）
子の標準生活費 = 義務者基礎収入 × Σ(子指数) / (100 + Σ(子指数))
義務者分担（年） = 子の標準生活費 × 義務者基礎収入 / (両親基礎収入合計)
月額 = 年額 / 12 → 1,000 円単位に四捨五入
```

**婚姻費用:**
```
権利者世帯の生活費 = (義務者+権利者基礎収入) × (100 + Σ子指数) / (200 + Σ子指数)
義務者分担（年） = 権利者世帯の生活費 - 権利者基礎収入
月額 = 年額 / 12 → 1,000 円単位
```

### 対応範囲外

- 住宅ローン負担調整（義務者が家を出て払い続ける場合の流儀は複数）
- 私立学校費用・塾費用・医療費等の個別加算
- 再婚・養子縁組による扶養義務変動
- 義務者の生活保護受給者化（警告のみ、月額 0 を返す）
- 算定表範囲外（義務者給与 2,000 万超・自営 1,567 万超）: 計算は試みるが警告

### Verification

- `test_calc.py`: 20/20 pass（1000円単位丸めあるので算定表の 2 万円セル内で
  整合）
- E2E 12.1-12.5: 養育費算定表範囲内、婚姻費用算定表範囲内、kind バリデー
  ション、20 歳子拒否、self-test 実行
- 合計 45/45 pass (v2.4.0 の 40 + 新規 5)

### 運用フロー（典型）

```
/matter-create                        — 事案作成
/template-install divorce-agreement   — 離婚協議書雛形
/template-install child-support-application   — 調停申立書雛形
/child-support-calc                   — 月額算出（決定論）
/template-fill                        — 算定結果を書式に転記
```

Track B 残:
- `/debt-recalc` — 利息制限法引き直し（破産・再生の中核計算）
- `/overtime-calc` — 労基法 37 条の割増賃金

## [2.4.0] - 2026-04-17

Track B-1: `/traffic-damage-calc` — 交通事故損害賠償の決定論的計算器。
SMB 弁護士の最大収益源（全業務の約 20%）である交通事故実務の中心となる
計算を、赤い本基準で正確に自動化する。`/inheritance-calc` のアーキテクチャ
をそのまま踏襲。

### Added — traffic-damage-calc

- **`skills/traffic-damage-calc/calc.py`** (~540 行): 赤い本基準の決定論的
  計算エンジン。Fraction ベースの exact math で丸め誤差なし
- **`skills/traffic-damage-calc/test_calc.py`** (20 tests pass): 軽症むち打ち、
  中等症、14級/12級後遺障害、主婦休業損害、死亡逸失利益、過失相殺、
  弁護士費用、遅延損害金等、実務で典型的なケースを網羅
- **`skills/traffic-damage-calc/references/akai-hon.md`**: 赤い本の主要テーブル
  参照（入通院慰謝料別表 I/II、後遺障害慰謝料、労働能力喪失率、死亡慰謝料、
  生活費控除率、Leibniz 係数、入院雑費・付添看護費）
- **`skills/traffic-damage-calc/SKILL.md`**: matter 解決・9 ステップの対話
  ワークフロー
- **`commands/traffic-damage-calc.md`**: `/traffic-damage-calc` slash command

### 計算対象

- **積極損害**: 治療費・通院交通費・装具費・入院雑費 (1,500 円/日)・
  付添看護費 (入院 6,500 円/日、通院 3,300 円/日)
- **休業損害**: 職業別の日額計算（給与所得者・自営業・主婦は賃金センサス
  女性全年齢平均 399 万円/年）
- **後遺障害逸失利益**: 基礎収入 × 労働能力喪失率 × Leibniz 係数（年利 3%、
  改正民法 404 条準拠）
- **死亡逸失利益**: 基礎収入 × (1 - 生活費控除率) × Leibniz 係数
- **入通院慰謝料**: 赤い本別表 I（骨折等・他覚所見あり）／ II（むち打ち等・
  他覚所見なし）を通院月数 × 入院月数でクロス参照
- **後遺障害慰謝料**: 等級 1 (2,800 万円) 〜 14 (110 万円)
- **死亡慰謝料**: 家計支持者 2,800 万 / 母親・配偶者 2,500 万 / その他 2,200 万
- **弁護士費用**: 認容額の 10% (判例実務、民法 709 条類推)
- **遅延損害金**: 年 3% × 事故日からの日数
- **過失相殺**: 被害者過失 0-100% を損害元本から控除 (民法 722 条 2 項)

### バリデーション

- 等級は 1-14 のみ（範囲外は ValueError）
- 過失割合は 0-100（範囲外は ValueError）
- 年齢は 0-120（範囲外は ValueError）
- 職業は `salaried` / `self_employed` / `household` / `student` / `unemployed` / `part_time`

### 対応範囲外（明示）

- 介護費用（将来介護）
- 家屋・車両改造費
- 損益相殺（自賠責既払額・労災・健康保険）— 別途控除
- 物損（修理費・代車料・評価損）
- 任意保険基準・青本基準

### Verification

- `test_calc.py`: 20/20 pass（軽症〜重篤、過失相殺、弁護士費用、遅延損害金）
- E2E シナリオ 11.1-11.3: 12 級実務ケース合計額（21-23M 範囲内）、入力
  バリデーション、内蔵 self-test を CI で毎回実行
- 合計: 40/40 pass (v2.3.0 の 37 + 新規 3)

### 運用メモ

`settlement-traffic` テンプレートと組み合わせて使う想定:

```
/matter-create          — 事案作成
/template-install settlement-traffic   — 示談書雛形をインストール
/traffic-damage-calc    — 損害額を決定論的に計算
/template-fill          — 計算結果を示談書に転記
```

Track B 今後の予定:
- `/child-support-calc` — 令和元年改定・養育費/婚姻費用算定表（家事事件）
- `/debt-recalc` — 利息制限法引き直し計算（破産・再生）
- `/overtime-calc` — 労基法 37 条の割増賃金計算（労働）

## [2.3.0] - 2026-04-17

Track A Phase 3: 同梱テンプレートを 13 → 23 種に拡充。家事事件の調停系・
刑事弁護・後見・支払督促等、実務でよく発生するが Phase 1/2 で未カバーだった
領域を埋める。刑事弁護カテゴリを新設。

### Added — 10 新規同梱テンプレート

**家事事件（5件追加、合計6件で同カテゴリ最大）:**
- `statement-family` — 陳述書（家事事件）
- `family-mediation-application` — 家事調停申立書（夫婦関係調整等）
- `child-support-application` — 養育費請求調停申立書（令和元年改定算定方式準拠）
- `spousal-support-application` — 婚姻費用分担請求調停申立書
- `guardianship-application` — 後見開始申立書（後見・保佐・補助の3類型対応）

**破産・再生（2件追加、合計4件）:**
- `rehabilitation-small` — 個人再生申立書（小規模、住宅資金特別条項選択可）
- `household-budget` — 家計収支表（2-3ヶ月分併記用）

**民事訴訟（1件追加、合計3件）:**
- `payment-demand` — 支払督促申立書（民訴法 382条以下の簡易手続）

**刑事弁護（新カテゴリ、2件）:**
- `criminal-defense-appointment` — 弁護人選任届
- `criminal-settlement` — 示談書（刑事事件、宥恕・告訴取下げ条項付）

### Coverage snapshot (v2.3.0)

| カテゴリ | テンプレート数 |
|---|---|
| 家事事件 | 6 |
| 破産・再生 | 4 |
| 相続 | 3 |
| 民事訴訟 | 3 |
| 刑事弁護 | 2 |
| 労働 | 2 |
| 交通事故 | 1 |
| 一般民事 | 1 |
| 汎用 | 1 |
| **合計** | **23** |

この構成で、日本の SMB 弁護士事務所の実務の約 70-80% をカバーできる。

### Verification

全 23 種で以下をパス:

- `template_lib --self-test` 23/23 registry 整合性
- MCP round-trip `@knorq/xlsx-mcp-server@2.0.0` 23/23 成功
- Deep-read spot-check（Phase 3 の 4 フォーム）: 民再221条・民訴382条・民法7条・民訴382/395条 等の critical legal references が MCP 経由で保持されている
- E2E 37/37 pass（v2.2.0 の 35 + Phase-3 install 追加 2）

### Known limitations / Phase 4 候補

Phase 4 で検討中:
- 遺言書（自筆証書・公正証書）— 厳格な要件があるため慎重に設計
- 株主総会議事録・取締役会議事録・就業規則（SME 企業法務）
- 少額訴訟訴状（60万円以下）
- 内容証明のバリアント（契約解除通知・時効催告・解約通知）
- 陳述書（刑事事件）
- 即決和解申立書（民訴 275条）

ただし Phase 3 時点で daily-use gap の主要部分は埋まったため、Phase 4 は
user demand driven で追加する方針。Track B（決定論的計算: 交通事故損害賠償、
養育費、引き直し計算、残業代）が次の重点。

## [2.2.0] - 2026-04-17

Track A Phase 2: 同梱テンプレートライブラリを 3 種 → 13 種に拡充。SMB 弁護士の
実務負荷の大半を占める 8 分野（家事事件・相続・交通事故・破産再生・労働・
民事訴訟・一般民事・汎用）をカバーする。

### Added — 10 新規同梱テンプレート

**家事事件:**
- `divorce-agreement` — 離婚協議書（親権・養育費・面会交流・財産分与・慰謝料・年金分割網羅）

**相続:**
- `inheritance-renunciation` — 相続放棄申述書（民法 915 条の 3 ヶ月熟慮期間明記）
- `inheritance-division-agreement` — 遺産分割協議書（相続人一覧＋分配内容テーブル）

**民事訴訟:**
- `complaint-loan-repayment` — 訴状（貸金返還請求）（民訴法 134 条の必要的記載事項網羅）
- `answer-generic` — 答弁書（請求の趣旨に対する答弁・原因に対する認否・抗弁を構造化）

**労働:**
- `overtime-calc-sheet` — 未払残業代計算書（労基法 37 条・改正後時効 3 年対応）
- `labor-tribunal-application` — 労働審判申立書（3 期日以内の迅速手続）

**破産・再生:**
- `bankruptcy-dohaishi` — 破産申立書（同時廃止型・個人）（債権者一覧表・財産目録を別紙添付）

**一般民事:**
- `naiyou-shoumei` — 内容証明郵便（横書き 26字×20行、520字/枚制約を明示）

**汎用:**
- `power-of-attorney` — 委任状（弁護士）（民訴法 55 条 2 項の特別委任事項個別承諾欄）

各テンプレートは `templates/_bundled/{id}/{id}.yaml` にフィールド定義、
同じく `.xlsx` にレイアウトを持つ。全 13 種で以下が機能することを確認済み:

- `template_lib.py --self-test`: 13/13 エントリの YAML+XLSX 整合性
- MCP round-trip: `@knorq/xlsx-mcp-server@2.0.0` での読み戻し 13/13 成功
- Deep-read spot-check: 残業代の「消滅時効」「民法 915 条」「特別委任事項」等、
  実務上 critical な文言が MCP 経由で完全保持されている
- E2E 35/35 pass（v2.1.0 の 34 + カテゴリ網羅性チェック 1）

### Architecture

本リリースは v2.1.0 で構築した仕組みに純粋な追加で乗る:

- Builder 関数を `scripts/build_bundled_forms.py` に追加するだけ
- Registry `templates/_bundled/_registry.yaml` にエントリを足すだけ
- `xlsx_writer.py` と `template_lib.py` は未変更（設計が十分拡張的だった証左）

### Known limitations

- 同梱 XLSX は実務の参考レイアウト。**裁判所提出前に最新の裁判所ホームページ・
  法テラス様式で cell 配置を最終確認する運用**が必須。各テンプレートの
  legal_basis 欄に準拠法を明記。
- 養育費算定表のような「計算ロジック」は本リリースでは未提供。Track B
  （`/child-support-calc`, `/traffic-damage-calc`, `/debt-recalc`,
  `/overtime-calc`）で決定論的計算モジュールとして実装予定。

## [2.1.0] - 2026-04-17

Track A の最初のリリース: 同梱テンプレート・書式ライブラリの導入。
SMB（tier 2/3 弁護士）が日々使う裁判所書式・実務書式を `/template-install`
一撃でアクティブ matter に取り込めるようにした。

### Added — 同梱テンプレートライブラリ

- **`/template-install`** コマンド: プラグイン同梱の裁判所書式・実務雛形を
  アクティブ matter にコピーする。一覧表示・インストール・上書き対応。
- **`skills/_lib/template_lib.py`** (~340 行): レジストリ読込・インストール・
  CLI。matter 未作成時は exit 2、上書き衝突は exit 3 で区別。
- **`skills/_lib/xlsx_writer.py`** (~220 行): stdlib のみの最小 XLSX 書込器。
  openpyxl 非依存。日本語セル値・結合セル・列幅・太字書式に対応。
  @knorq/xlsx-mcp-server@2.0.0 での読み戻し互換性を確認済み。
- **`scripts/build_bundled_forms.py`**: 同梱テンプレート YAML+XLSX 生成
  スクリプト。今後の書式追加はここにビルダ関数を足すだけで済む。

### Added — 同梱テンプレート 3 種（第一弾）

| ID | カテゴリ | 用途 |
|---|---|---|
| `creditor-list` | 破産・再生 | 自己破産・個人再生申立の添付「債権者一覧表」（7 列: №/債権者名/住所/種類/元金/利息/備考） |
| `estate-inventory` | 相続 | 遺産分割協議・限定承認に用いる「遺産目録」（積極財産＋消極財産の 2 テーブル） |
| `settlement-traffic` | 交通事故 | 任意保険会社・加害者との直接交渉後の「示談書」雛形（当事者・事故内容・示談金・清算条項） |

第二弾予定: 養育費算定表、離婚協議書雛形、未払残業代計算書、内容証明郵便
雛形、訴状・答弁書・陳述書雛形、破産・個人再生申立書、労働審判申立書等。
Track B（`/traffic-damage-calc` 等の決定論的計算）は別リリースで対応。

### Added — E2E カバレッジ

`scripts/e2e.py` に 6 件の新シナリオ:
- 10a.1 レジストリ列挙
- 10a.2 インストール→ YAML+XLSX コピー成立
- 10a.3 ファイルが正しく matter dir に配置される
- 10a.4 再インストールは `--replace` なしで拒否（exit 3）
- 10a.5 `--replace` で上書き成功
- 10a.6 存在しない matter へのインストールは拒否

合計 34/34 pass（旧 28 + 新 6）。

### Changed

- `.claude-plugin/plugin.json`: 2.0.1 → 2.1.0

### Docs

- `commands/template-install.md`: コマンド定義
- `templates/_bundled/_registry.yaml`: 同梱テンプレートレジストリ
- この CHANGELOG エントリに予定リストを明記

### Known limitations

- 同梱 XLSX は参考レイアウト。**実際の裁判所書式と cell 単位で一致するとは
  限らない。提出前に最新の裁判所ホームページ・法テラス様式を確認する運用が
  必須**。このため registry には「提出前確認が必要」の但し書きを今後追加予定。
- 現行 3 種は stdlib 生成のため書式の見栄えは最小限。高度な罫線・塗り潰し・
  ヘッダ／フッタは次期バージョンで（必要なら openpyxl を optional dep に）。

## [2.0.1] - 2026-04-17

v2.0.0 直後の triple-PE（Anthropic・OpenAI・Harvey）による再レビューで指摘された運用ハードニング項目を適用。Tier 2/3（solo/mid-market）向けの本番運用ブロッカーを全て解消。Tier 1（BigLaw）構造ブロッカーの一部も部分対応。

### Security / Hardening

- **`~/.claude-bengo/` と `matters/` を 0o700 に強制** (OpenAI V2-001, Harvey H1): macOS 既定の `drwxr-xr-x` では他 OS ユーザーや Spotlight / Time Machine が `ls ~/.claude-bengo/matters/` で依頼者名を示唆する matter ID を enumerate できてしまう問題を修正。`create_matter` / `set_current_matter` の都度 `_ensure_root_mode()` で冪等に 0o700 を再適用する。
- **`.claude-bengo-matter-ref` のシンボリックリンク拒否** (Anthropic V2-003, Harvey H2): `_read_matter_ref` でシンボリックリンクを明示的に拒否し stderr に WARN を出す。共有 Dropbox 等に置かれた悪意ある ref から任意ファイルへの間接読取を防ぐ（`copy_file.py` と対称のセキュリティ方針）。
- **`MATTER_ID` env が cwd-ref を override した場合に stderr WARN** (Harvey H3): シェル設定（`.zshrc` 等）で `MATTER_ID` を固定したまま事案別フォルダに `cd` したとき、意図しない事案へ書込する footgun を可視化。抑止は `CLAUDE_BENGO_SILENT_MATTER_OVERRIDE=1`。
- **`drop_matter_ref` は事案の実在を検証** (Anthropic V2-002): `set_current_matter` と対称に `matter_exists()` チェックを追加。タイポ ID の ref を作成してしまう UX 事故を防ぐ。
- **`RESERVED_IDS` に `matters`, `lock`, `tmp` を追加** (Anthropic V2-001): ディレクトリ名衝突による混乱を防止。

### Changed — BigLaw 対応の部分強化

- **`/matter-create` のデフォルトを不透明 ID に変更** (OpenAI V2-002 部分対応): 人間可読 ID（`smith-v-jones` 等）を推奨せず、自動生成 ID（`YYYYMMDD-{hex}`）を既定とする。人間可読な事案名は `title` フィールド（`metadata.yaml`、0o600）に保存されるため、ディレクトリ名 enumeration から依頼者情報が漏洩しない。
- **`/matter-create` に初回同意フロー追加** (OpenAI V2-009 部分対応): 既存 matter が 0 件の場合、Anthropic API・リージョン・ZDR・監査ログの扱いを提示し、明示的な `yes` 回答を要求する。

### Migration

- **`/matter-create --import-from-cwd` は `.yaml` / `.xlsx` ペアのみ取込** (OpenAI V2-004): v1.x の `{cwd}/templates/` から移行する際、`.DS_Store`・`~$` Excel ロック・関係ない PDF・`_schema.yaml` を skip する。`skipped_files` 一覧も出力に含まれる。

### Operations

- **`CLAUDE_BENGO_AUDIT_KEEP=N` による rotation 保持本数制限** (OpenAI V2-005 対応): v1.x 以来「無制限」だったローテート済み監査ログの保持数を任意制限できる環境変数を追加。未設定なら従来通り無制限。削除時は stderr に INFO 出力。
- **CI で `matter.py --self-test`, `audit.py --self-test`, `search.py self-test` を明示実行** (OpenAI V2-006): 従来は `scripts/verify.py` のみだったため、18/18, 17/17, 21/21 のセルフテストが実質 CI 対象外だった。`.github/workflows/ci.yml` で 3 スクリプトのセルフテストを OS × Python マトリクス内で実行する。

### Tests

- `matter.py --self-test` 18/18（v2.0.0 の 14 + 新規 4: 0o700 perms, drop_ref 存在検証, RESERVED_IDS 'matters', symlink ref 拒否）
- `audit.py --self-test` 17/17 維持
- `calc.py test_calc.py` 19/19 維持
- `search.py self-test` 21/21 維持
- `scripts/verify.py` 18 passed

### Still Tier 1 blockers（構造的、本リリースでは未対応）

- データ residency 米国依存（Path C-enterprise SaaS 必要）
- SSO / 弁護士登録番号バインディング未対応（構造的）
- 事務所間の corporate MSA / DPA 主体が不在（事業主体の問題）
- 全体削除（`rm -rf` 相当）の検知は依然不可能（外部 WORM 連携で対処）

## [2.0.0] - 2026-04-17

**BREAKING CHANGE:** 事案（matter）単位のデータ分離を導入した。テンプレートと監査ログは `~/.claude-bengo/matters/{matter-id}/` 配下で管理される。v1.x からの移行は `/matter-create --import-from-cwd` で行う。

### Added — matter（事案）管理

- **`skills/_lib/matter.py`** (743 行): 4 段階優先順位の事案解決器 + CLI。
  - 解決順: `--matter` フラグ → `MATTER_ID` 環境変数 → `{cwd}/.claude-bengo-matter-ref` → `~/.claude-bengo/current-matter`
  - CLI: `resolve`, `list`, `info`, `create`, `switch`, `drop-ref`, `import-from-cwd`, `validate`
  - 事案 ID の命名規則: `^[a-z0-9][-a-z0-9_]{0,63}$` + 予約語拒否
  - 自動生成 ID: `YYYYMMDD-{6-hex}`（例: `20260417-a7b3c2`）
  - メタデータ（title, client, case_number, opened, notes）を `metadata.yaml` に保存
  - セルフテスト 14/14 pass
- **4 つの新規コマンド**:
  - `/matter-create` — 対話で事案を登録、任意で `.claude-bengo-matter-ref` を CWD に配置、`--import-from-cwd` で v1.x のテンプレートを取込
  - `/matter-list` — 登録済み事案 + アクティブ事案の解決元を表示
  - `/matter-switch <id>` — `current-matter` を更新
  - `/matter-info [id]` — 事案詳細（パス、テンプレート数、監査ログサイズ、メタデータ）を表示
- **`skills/_lib/audit.py --matter` フラグ** (line 151-183): 事案単位の監査ログへルーティング
  - 優先順: 明示 `--matter` → `CLAUDE_BENGO_AUDIT_PATH` → `CLAUDE_BENGO_AUDIT_AUTO_MATTER=1` + `matter.resolve()` → デフォルト
  - 事案未作成時は exit 2（孤児ログを作らない）
  - 事案単位のハッシュチェーン・ロック・ローテーションは独立
  - `verify --matter <id> --all` で事案内のローテート済みログまで検証
  - セルフテスト 17/17 pass（並行書込の事案間独立性を含む）

### Changed — BREAKING

- **テンプレートの保存場所**: v1.x では `{cwd}/templates/` に保存していたが、v2.0.0 から `~/.claude-bengo/matters/{matter-id}/templates/` に移動。事案未設定では機密スキルは動作しない。
- **監査ログの保存場所**: v1.x のグローバル `~/.claude-bengo/audit.jsonl` は `matter-create` 等の事案横断イベント用。機密スキル（template-fill 等）は事案ログ `~/.claude-bengo/matters/{id}/audit.jsonl` に記録する。
- **機密スキル 5 種** は事案未設定時に明示的エラーで中止する:
  - `template-create`, `template-fill`, `typo-check`, `lawsuit-analysis`, `family-tree`
  - いずれも Step 0 に matter 解決パスを追加。解決できない場合は `/matter-create` 等を案内
- **`/template-list`**: `{cwd}/templates/` ではなくアクティブ事案の `templates/` を走査
- **非機密スキル** は事案設定不要で従来どおり動作: `law-search`, `inheritance-calc`, `verify`, `bengo-update`

### Migration — v1.x → v2.0

v1.x で `{cwd}/templates/` にテンプレートを蓄積していたユーザーは、次のいずれかで移行する:

```bash
/matter-create smith-v-jones --import-from-cwd
```

元の `{cwd}/templates/` は残る（破壊的操作を避けるため）。取り込みが完了したら手動で削除してよい。

### Security

- 事案間の trust boundary 分離: `/template-fill` が別事案のテンプレートを誤って使用することがなくなる
- `.claude-bengo-matter-ref` によるディレクトリ単位の自動検出で、`cd` ベースの作業ワークフローでも事案境界が保てる
- 命名規則 + 予約語チェックでパストラバーサル（`../etc/passwd` 等）を防止

### Files added

- `skills/_lib/matter.py` (743 行)
- `commands/matter-create.md`
- `commands/matter-list.md`
- `commands/matter-switch.md`
- `commands/matter-info.md`

### Files changed

- `skills/_lib/audit.py` (+429 / -9; matter 対応)
- `skills/template-create/SKILL.md` (+51 / -N; Step 0 追加)
- `skills/template-fill/SKILL.md` (+68 / -N; Step 0 + matter-dir glob)
- `skills/typo-check/SKILL.md` (+44 / -N; Step 0 + matter audit)
- `skills/lawsuit-analysis/SKILL.md` (+40 / -N; Step 0 + matter audit)
- `skills/family-tree/SKILL.md` (+38 / -N; Step 0 + matter audit)
- `commands/template-list.md` (+49 / -N; matter-aware)
- `commands/{template-create,template-fill,typo-check,lawsuit-analysis,family-tree}.md` (allowed-tools に `Bash(python3 skills/_lib/matter.py:*)` 追加)
- `.claude-plugin/plugin.json`: 1.1.1 → 2.0.0

### Tests

v2.0.0 合計: **84 tests, 100% pass**
- matter.py self-test: 14/14
- audit.py self-test: 17/17（v1.1.1 の 10 + matter 対応の 7）
- calc.py test_calc.py: 19/19
- search.py self-test: 21/21
- scripts/verify.py: 18 passed, 0 failed, 4 warnings（fixtures の未整備による warning のみ）

### Out of scope / known limitations

- **テナント分離は単一ユーザー内のみ** — OS ユーザーが同じなら他事案ファイルは依然 `cat` で読める。真のマルチテナント分離は Path C-enterprise（別プロダクト）で扱う。
- **BigLaw 向け構造要件は未対応**: SOC2/ISO27001, SSO/SCIM, JP リージョン固定, MSA 契約主体 — いずれも本プラグインの範囲外。BigLaw 導入は専用 SaaS 製品が必要。
- `.claude-bengo-matter-ref` はファイルシステム読取権限があれば誰でも読める（設計上パブリック情報として扱う）

## [1.1.1] - 2026-04-17

### Security

- **F-020 監査ログの改ざん耐性**: `skills/_lib/audit.py` に SHA-256 ハッシュチェーン（`prev_hash`）を追加。各レコードに直前行のハッシュを埋め込み、書換・削除・並替を `verify` サブコマンドで検出可能に。ローテーション（50 MB 超）を跨いでもチェーンは継続する。fsync + fcntl.flock（POSIX）/ msvcrt.locking（Windows）で並行書込も安全。セルフテスト 10/10 pass（10 プロセス × 10 書込の並行テスト含む）。
- **F-021 law-search キャッシュポイズニング対策**: キャッシュ位置を共有 `/tmp` から `~/.claude-bengo/cache/law-search/` に移動（`0o700` perms）。書込は atomic（`tmp + os.replace`）、読込前に SHA-256 サイドカー検証、改ざん検知時は自動削除。セルフテスト 21/21 pass。
- **F-022 calc.py エッジケース**: `parent_id` サイクル検出（自己参照含む）、`adoption` フィールドのスコープチェック（`kind='child'` 以外は拒否）、二重相続資格（`kind='child' + parent_id != None`）の検出を追加。テスト 15 のロックダウン（spouse=3/8, sibling=0）と新規テスト 16-19 追加。19/19 tests pass。
- **F-023 Windows クロスプラットフォーム対応**: `Bash(cp:*)` 許可を `skills/_lib/copy_file.py`（shutil ベース）に置換。`commands/template-fill.md`, `commands/template-create.md` を更新。`skills/family-tree/SKILL.md` のハードコード `/tmp/claude-bengo-familytree-...json` を CWD 相対の `.claude-bengo-familytree.json` に変更。CI に `Bash(cp:*)` リグレッション検出 lint を追加。

### Privacy

- **audit.py ファイル名保護**: ファイル名は既定で平文記録しない（`filename` は空文字）。識別は `filename_sha256`（basename の SHA-256）で行う。依頼者氏名などの識別情報が監査ログに残ることを防ぐ。フォレンジック目的で平文を残したい場合は `--log-filename` オプトインで明示指定。
- **audit.py センチネル修正**: `CLAUDE_BENGO_AUDIT_PATH=NUL` が POSIX で literal `./NUL` ファイルを作成するバグを修正（`os.devnull`・`NUL`・`nul`・`/dev/null` をセンチネルとして処理）。

### Changed

- `.claude-plugin/plugin.json`: 1.1.0 → 1.1.1
- `.mcp.json`: `xlsx-mcp-server@1.1.0` → `@knorq/xlsx-mcp-server@2.0.0`（および他の 2 件も `@knorq/*@2.0.0` へ移行。npm 側でスコープ化・`--provenance` 付き公開・GitHub OIDC 経由でビルドソース検証）
- `skills/law-search/SKILL.md`: version 1.1.0 → 1.2.0（キャッシュ関連記述更新）
- `commands/family-tree.md`, `commands/template-fill.md`, `commands/template-create.md`: `allowed-tools` 更新

### Added

- `skills/_lib/copy_file.py` — クロスプラットフォームのファイルコピーヘルパー。
- `skills/_lib/audit.py verify` — 監査ログのハッシュチェーン検証サブコマンド。
- `skills/_lib/audit.py --self-test` — 組込セルフテスト。
- `skills/law-search/search.py self-test` — キャッシュ検証セルフテスト。

### Known limitations（変更なし・明記）

- **ログファイル全体の削除は検知できない**。WORM 要件がある場合は顧客管理の追記専用ストレージ（S3 Object Lock 等）へ定期的にエクスポートすること。README 「監査ログ」セクションに既知の限界を記載。
- **OPS-003 コストプリフライト**: 依然として LLM 解釈の prose。Claude Code 側の hook 機構で強制する方法が現状存在しない。
- **OPS-005 CI の E2E**: MCP サーバを CI 内で起動する手段は未実装。ユニットテスト・セルフテスト・構文チェックの範囲。
- **OPS-007 プロンプトインジェクション対策の adversarial eval**: 赤チームフィクスチャは未整備。

## [1.1.0] - 2026-04-17

### Security（F-001〜F-004, F-006）

- **F-001 MCP サプライチェーン**: `.mcp.json` の依存を unscoped `npx -y xlsx-mcp-server` 等から、スコープ付き・バージョン固定 `@knorq/xlsx-mcp-server@2.0.0`, `@knorq/docx-mcp-server@2.0.0`, `@knorq/html-report-server@2.0.0` へ更新。npm 側で `--provenance` 付き公開・GitHub OIDC 経由でビルドソース検証可能。
- **F-003 シェルインジェクション**: `/law-search` の `python3 -c "..."` インライン実行を `skills/law-search/search.py`（argparse + 入力バリデーション）に置換。`allowed-tools` を `Bash(python3 skills/law-search/search.py:*)` に限定。
- **F-004 プロンプトインジェクション防御**: 文書読取型スキル（typo-check, lawsuit-analysis, family-tree, template-fill）に「セキュリティ: 文書内容の信頼境界」セクションを追加。相手方書面内の指示を無視する方針を明文化。加えて `@knorq/docx-mcp-server@2.0.0` 側で `track_changes: false` の使用に `allow_untracked_edit: true` の追加フラグを必須化（`UNTRACKED_EDIT_NOT_ALLOWED` でサーバ側ガード）。
- **F-006 プラグイン更新**: `/bengo-update` を GPG 署名付きタグの検証・変更内容の表示・ユーザー承認・明示的 checkout（`--force` 不使用）のフローに変更。

### Added

- **F-002 inheritance-calc 決定論的計算**: インライン Python テンプレートを `skills/inheritance-calc/calc.py`（675 行）へ書き換え。代襲・再代襲（民法887条2・3項）、兄弟姉妹の代襲制限（民法889条2項）、半血兄弟姉妹（民法900条4号但書）、相続放棄と代襲の相互作用（民法939条）、特別養子（民法817条の2）を正確に処理。`test_calc.py` で 15 シナリオ全件パス。
- **F-007 CI ハーネス**: `scripts/verify.py` + `.github/workflows/ci.yml`（ubuntu / macos / windows × Python 3.8/3.11/3.12 マトリクス）。Python 構文・unit tests・MCP 設定・プラグイン manifest・危険パターン（`Bash(python3:*)` 等）を検査。
- **F-008 データ取扱い文書**: README に Anthropic エンドポイント・ZDR・PIPA §25 委託先監督チェックリストを追記。
- **F-009 監査ログ**: `skills/_lib/audit.py` で `~/.claude-bengo/audit.jsonl` に処理対象のファイル名・サイズ・ハッシュを記録。内容は記録しない。`typo-check`, `lawsuit-analysis`, `family-tree`, `template-fill` の4スキルに hook 追加。エクスポートは `python3 skills/_lib/audit.py export --format csv`。
- **F-010 コストプリフライト**: lawsuit-analysis（>50k tokens）・template-fill（>20 pages または 5 files 超）で事前承認を要求。
- **F-011 law-search 信頼性**: クロスプラットフォームな tempdir・24h TTL キャッシュ・リトライ/バックオフ（429/500/502/503/504）・タイムアウト 30 秒を `search.py` に実装。
- **F-012 typo-check 一括承認制限**: 法的意味が重い用語（接続詞階層・条件表現・義務規定・主体呼称・効果規定・改正対応語・金額/日付/条番号）を denylist 化し、該当修正は個別承認必須に。
- **F-014 HTML インジェクション防御**: family-tree HTML テンプレートの JSON payload を Base64 化し、`TextDecoder('utf-8')` で復号。`</script>` 等の攻撃ベクタを完全に無効化。旧字体の自動変換は廃止（戸籍上の正式表記を保持）。
- **F-015 contributor ガイド**: スキル `description` フィールドの自動トリガー挙動を CLAUDE.md に明記。
- **F-016 プラットフォーム対応**: README に macOS/Linux/Windows/WSL2 の対応マトリクス、プロキシ env vars、社内 CA 設定、npx ブロック環境の対処を追加。
- `skills/family-tree/encode.py`: 家系図 JSON の Base64 エンコードヘルパー。
- `fixtures/README.md`: フィクスチャ棚卸し。合成データ作成ガイド。

### Changed

- **F-005 `/template-fill` 追記モード**: 自然言語トリガーから `反映して` を除外（上書き/追記の解釈が曖昧なため）。既存 `_filled.xlsx` 指定時または曖昧な表現使用時は明示的な確認を必須化。
- **F-013/F-017 `/verify`**: ハードコードされたスキル件数（`6 skills`, `4/4 OK`）を動的列挙に変更。
- `.claude-plugin/plugin.json`: version 1.0.0 → 1.1.0。
- `skills/verify/SKILL.md`: モード2 の対象に `inheritance-calc`, `law-search` を追加。

### Removed

- インライン `python3 -c "..."` 実行（全ての箇所で）。
- `Bash(curl:*)`, `Bash(rm:*)`, `Bash(mkdir:*)`, `Bash(rmdir:*)` の広い許可（law-search コマンドで narrow 化）。
- unscoped MCP パッケージ（`xlsx-mcp-server` 等）への依存。
- family-tree での旧字体 → 新字体の自動変換指示（戸籍上の正式表記を保持する方針へ変更）。

## [1.0.0] - 2026-04-03

### Added

- Initial release.
- 10 コマンド: `/template-create`, `/template-list`, `/template-fill`, `/family-tree`, `/typo-check`, `/lawsuit-analysis`, `/inheritance-calc`, `/law-search`, `/bengo-update`, `/verify`。
- 8 スキル + YAML テンプレートスキーマ。
- MCP サーバ自動設定（xlsx-editor, docx-editor, html-report）。
