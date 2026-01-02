# 刑法ディレクトリ日本語統一移行計画

## 1. 移行目標

刑法配下のファイル構造・命名を英語表記から日本語表記に統一し、Obsidian運用（wikilink）を維持する。

### 変更前（現状）
```
/刑法/
├── articles/
│   ├── main/
│   │   ├── Article_1.md
│   │   ├── Article_3_2.md（枝番）
│   │   └── Article_73:76.md（範囲）
│   └── suppl/
│       ├── 平成19年法律第54号/
│       │   └── 平成19年法律第54号_Article_1.md
│       └── 昭和22年法律第124号.md
└── 刑法.md
```

### 変更後（目標）
```
/刑法/
├── 本文/
│   ├── 第1条.md
│   ├── 第3条の2.md（枝番）
│   └── 第73条から第76条まで.md（範囲）
├── 附則/
│   ├── 平成19年法律第54号/
│   │   └── 附則第1条.md
│   └── 昭和22年法律第124号.md
└── 刑法.md
```

## 2. ファイル名変換ルール

### 2.1 本則ファイル（301ファイル）

| 現在のファイル名 | 新しいファイル名 | 変換ルール |
|-----------------|-----------------|-----------|
| `Article_1.md` | `第1条.md` | `第{N}条.md` |
| `Article_3_2.md` | `第3条の2.md` | `第{N}条の{M}.md`（枝番） |
| `Article_105_2.md` | `第105条の2.md` | `第{N}条の{M}.md`（枝番） |
| `Article_73:76.md` | `第73条から第76条まで.md` | `第{N}条から第{M}条まで.md`（範囲） |

**変換アルゴリズム:**
```python
def convert_main_filename(old_name: str) -> str:
    """Article_N[_M][:K] → 第N条[のM][からK]"""
    stem = old_name.replace('.md', '').replace('Article_', '')

    # 範囲形式: 73:76 → 第73条から第76条まで
    if ':' in stem:
        start, end = stem.split(':')
        return f"第{start}条から第{end}条まで.md"

    # 枝番形式: 3_2 → 第3条の2
    if '_' in stem:
        main, sub = stem.split('_')
        return f"第{main}条の{sub}.md"

    # 通常形式: 1 → 第1条
    return f"第{stem}条.md"
```

### 2.2 附則ファイル（68ファイル）

#### パターンA: 複数ファイル型（ディレクトリ内）
| 現在のファイル名 | 新しいファイル名 |
|-----------------|-----------------|
| `平成19年法律第54号/平成19年法律第54号_Article_1.md` | `平成19年法律第54号/附則第1条.md` |
| `平成19年法律第54号/平成19年法律第54号_Article_2.md` | `平成19年法律第54号/附則第2条.md` |

**変換ルール:** プレフィックス（改正法番号）を削除し、`附則第{N}条.md`に統一

#### パターンB: 単一ファイル型
| 現在のファイル名 | 新しいファイル名 |
|-----------------|-----------------|
| `昭和22年法律第124号.md` | `昭和22年法律第124号.md`（変更なし） |

**理由:** すでに日本語形式のため変更不要

### 2.3 ディレクトリ名変換

| 現在 | 新規 |
|------|------|
| `articles/main/` | `本文/` |
| `articles/suppl/` | `附則/` |

## 3. YAML メタデータ変換ルール

### 3.1 本則ファイルのYAML変換

**変更前:**
```yaml
---
article_num: '1'
heading: （国内犯）
id: JPLAW:140AC0000000045#main#1
law_id: 140AC0000000045
part: main
law_name: 刑法
references_explicit:
  - target_id: Article_109
    type: absolute
    original: 第百九条
    resolved: true
references_explicit_count: 1
---
```

**変更後:**
```yaml
---
article_num: '第1条'
heading: （国内犯）
id: JPLAW:140AC0000000045#本文#第1条
law_id: 140AC0000000045
part: 本文
law_name: 刑法
references_explicit:
  - target_id: 第109条
    type: absolute
    original: 第百九条
    resolved: true
references_explicit_count: 1
---
```

**変換マッピング:**

| フィールド | 変換ルール | 例 |
|-----------|-----------|-----|
| `article_num` | `'1'` → `'第1条'` | 枝番: `'3_2'` → `'第3条の2'` |
| `id` | `#main#1` → `#本文#第1条` | 全体: `JPLAW:XXX#本文#第1条` |
| `part` | `main` → `本文` | - |
| `references_explicit[].target_id` | `Article_109` → `第109条` | 項付き: `Article_109#第2項` → `第109条#第2項` |

### 3.2 附則ファイルのYAML変換

**変更前（複数ファイル型）:**
```yaml
---
article_num: '1'
heading: （施行期日）
id: JPLAW:140AC0000000045#suppl#1
law_id: 140AC0000000045
part: suppl
law_name: 刑法
---
```

**変更後:**
```yaml
---
article_num: '附則第1条'
heading: （施行期日）
id: JPLAW:140AC0000000045#附則#附則第1条
law_id: 140AC0000000045
part: 附則
law_name: 刑法
---
```

**変更前（単一ファイル型）:**
```yaml
---
article_num: Provision
heading: 附則
id: JPLAW:140AC0000000045#suppl#Provision
part: suppl
---
```

**変更後:**
```yaml
---
article_num: 附則
heading: 附則
id: JPLAW:140AC0000000045#附則#附則
part: 附則
---
```

## 4. wikilink 更新戦略

### 4.1 本文内のwikilink変換

**パターン1: 単純な条文参照**
```markdown
# 変更前
[[Article_109]]

# 変更後
[[第109条]]
```

**パターン2: 項付き参照**
```markdown
# 変更前
[[Article_109#第2項]]

# 変更後
[[第109条#第2項]]
```

**パターン3: 枝番参照**
```markdown
# 変更前
[[Article_3_2]]

# 変更後
[[第3条の2]]
```

**変換アルゴリズム:**
```python
def convert_wikilink(link: str) -> str:
    """[[Article_N[_M][#anchor]]] → [[第N条[のM][#anchor]]]"""
    # [[Article_109#第2項]] → Article_109#第2項
    inner = link.replace('[[', '').replace(']]', '')

    # アンカーを分離
    if '#' in inner:
        article_part, anchor = inner.split('#', 1)
    else:
        article_part, anchor = inner, None

    # Article_ プレフィックスを削除
    article_part = article_part.replace('Article_', '')

    # 枝番処理
    if '_' in article_part:
        main, sub = article_part.split('_')
        new_article = f"第{main}条の{sub}"
    else:
        new_article = f"第{article_part}条"

    # アンカーを復元
    if anchor:
        return f"[[{new_article}#{anchor}]]"
    else:
        return f"[[{new_article}]]"
```

### 4.2 親ファイル（刑法.md）のリンク更新

**本則セクション:**
```markdown
# 変更前
- [[articles/main/Article_1.md|第1条]]
- [[articles/main/Article_3_2.md|第3の2条]]

# 変更後
- [[本文/第1条.md|第1条]]
- [[本文/第3条の2.md|第3条の2]]
```

**附則セクション:**
```markdown
# 変更前
- [[articles/suppl/平成19年法律第54号/平成19年法律第54号_Article_1.md|第1条]]

# 変更後
- [[附則/平成19年法律第54号/附則第1条.md|附則第1条]]
```

## 5. 依存スクリプトの更新

### 5.1 更新が必要なファイル

| ファイル | 更新内容 | 優先度 |
|---------|---------|--------|
| `link_references.py` | `article_num_to_id()`を日本語形式に変更 | 高 |
| `apply_links.py` | globパターンを日本語ファイル名に対応 | 高 |
| `src/legalkg/core/tier1.py` | ファイル名生成を日本語形式に変更 | 中 |
| `src/legalkg/core/tier2.py` | target_id生成を日本語形式に対応 | 中 |
| `scripts/add_law_name_to_articles.py` | globパターン更新 | 低 |

### 5.2 `link_references.py` の主要変更箇所

**現在 (103-112行):**
```python
def article_num_to_id(main: int, sub: Optional[int] = None) -> str:
    if sub is not None:
        return f"Article_{main}_{sub}"
    else:
        return f"Article_{main}"
```

**変更後:**
```python
def article_num_to_id(main: int, sub: Optional[int] = None) -> str:
    if sub is not None:
        return f"第{main}条の{sub}"
    else:
        return f"第{main}条"
```

**globパターン (150行):**
```python
# 現在
for f in articles_dir.glob('Article_*.md'):

# 変更後
for f in articles_dir.glob('第*.md'):
```

## 6. 移行手順（段階的実施）

### Phase 1: 事前準備（リスク最小化）

1. **完全バックアップ**
   ```bash
   cp -r /Users/haramizuki/Project/DB4LAW/Vault/laws/刑法 \
         /Users/haramizuki/Project/DB4LAW/Vault_backup_刑法_$(date +%Y%m%d_%H%M%S)
   ```

2. **gitコミット**
   ```bash
   cd /Users/haramizuki/Project/DB4LAW
   git add -A
   git commit -m "移行前チェックポイント: 刑法日本語化開始前"
   ```

3. **ファイル名マッピングテーブル生成**
   - 全369ファイル（301本則 + 68附則）の変換マップをCSV生成
   - 変換前後のパスを明記

### Phase 2: 移行スクリプト開発

**スクリプト構成:**
```
migrate_to_japanese.py
├── Phase1: ファイルコピー（新構造に複製）
├── Phase2: YAML更新
├── Phase3: wikilink更新（本文内）
├── Phase4: 親ファイル更新
├── Phase5: 旧ファイル削除
└── Phase6: 検証
```

**各Phaseの詳細:**

#### Phase 2.1: ファイルコピー
```python
# 新ディレクトリ作成
/刑法/本文/
/刑法/附則/{改正法番号}/

# ファイルをコピー（移動ではなくコピー）
# 理由: 問題発生時のロールバックが容易
```

#### Phase 2.2: YAML更新
- 各ファイルのYAMLフロントマターを読み込み
- `article_num`, `id`, `part`, `references_explicit[].target_id`を更新
- 元のYAMLの順序とフォーマットを維持

#### Phase 2.3: wikilink更新（本文内）
- 正規表現で`[[Article_N...]]`パターンを検出
- 日本語形式に置換
- 参照整合性チェック（リンク先ファイルが存在するか）

#### Phase 2.4: 親ファイル更新
- `刑法.md`の全リンクを更新
- 本則セクション（301行）
- 附則セクション（68行）

#### Phase 2.5: 旧ファイル削除
```bash
rm -rf /刑法/articles/
```

#### Phase 2.6: 検証
- リンク切れチェック（全wikilinkの解決確認）
- YAML妥当性チェック
- ファイル数カウント（369ファイル存在確認）

### Phase 3: 依存スクリプト更新

1. `link_references.py`更新
2. `apply_links.py`更新
3. `tier1.py`, `tier2.py`更新（将来の再生成用）
4. 単体テスト実行

### Phase 4: 検証とロールバックテスト

1. **Obsidianで動作確認**
   - グラフビュー表示
   - wikilink遷移テスト
   - 検索機能テスト

2. **ロールバックテスト**
   - バックアップからの復元手順確認

## 7. リスクと対策

| リスク | 影響度 | 対策 |
|--------|--------|------|
| リンク切れ発生 | 高 | Phase 2.6で全リンク検証、不整合時は移行中止 |
| YAML破損 | 高 | YAMLパーサーで妥当性検証、エラー時はスキップしログ記録 |
| ファイル名の文字コード問題 | 中 | UTF-8エンコーディングを明示、macOS/Linux環境で実施 |
| 既存スクリプトとの非互換 | 中 | 更新済みスクリプトを別名で保存、テスト完了後に置換 |
| 移行途中での中断 | 低 | Phase単位でチェックポイント、コピー方式で元ファイル維持 |

## 8. ロールバック計画

**緊急ロールバック手順:**
```bash
# Step 1: 新ディレクトリ削除
rm -rf /Users/haramizuki/Project/DB4LAW/Vault/laws/刑法/本文
rm -rf /Users/haramizuki/Project/DB4LAW/Vault/laws/刑法/附則

# Step 2: gitリセット
cd /Users/haramizuki/Project/DB4LAW
git reset --hard HEAD

# Step 3: バックアップから復元（git履歴がない場合）
cp -r /Users/haramizuki/Project/DB4LAW/Vault_backup_刑法_* \
      /Users/haramizuki/Project/DB4LAW/Vault/laws/刑法
```

## 9. 実装詳細: マッピングテーブル

### 9.1 ファイル名変換サンプル（本則）

| 旧パス | 新パス |
|--------|--------|
| `articles/main/Article_1.md` | `本文/第1条.md` |
| `articles/main/Article_3_2.md` | `本文/第3条の2.md` |
| `articles/main/Article_73:76.md` | `本文/第73条から第76条まで.md` |
| `articles/main/Article_105_2.md` | `本文/第105条の2.md` |
| `articles/main/Article_264.md` | `本文/第264条.md` |

### 9.2 ファイル名変換サンプル（附則）

| 旧パス | 新パス |
|--------|--------|
| `articles/suppl/平成19年法律第54号/平成19年法律第54号_Article_1.md` | `附則/平成19年法律第54号/附則第1条.md` |
| `articles/suppl/昭和22年法律第124号.md` | `附則/昭和22年法律第124号.md` |

## 10. 実装スケジュール

| Phase | タスク | 推定時間 | 担当 |
|-------|--------|---------|------|
| 1 | バックアップ・マッピング生成 | 5分 | スクリプト自動化 |
| 2 | 移行スクリプト開発 | 30-60分 | Claude Code |
| 3 | Dry-run実行・検証 | 10分 | Claude Code |
| 4 | 本番実行 | 5分 | Claude Code |
| 5 | 依存スクリプト更新 | 20分 | Claude Code |
| 6 | 最終検証 | 10分 | Claude Code + User |

**合計推定時間:** 1.5-2時間

## 11. 成功基準

移行成功の判断基準:

1. ✅ 全369ファイルが新構造に移行完了
2. ✅ リンク切れゼロ（全wikilinkが解決可能）
3. ✅ YAML妥当性100%（全ファイルがパース可能）
4. ✅ Obsidianでグラフビュー表示可能
5. ✅ `link_references.py`が新構造で動作
6. ✅ 親ファイル（刑法.md）の全リンクが機能

---

**次のアクション:**
1. ユーザーによる計画承認
2. 移行スクリプト `migrate_to_japanese.py` の実装
3. Dry-run実行とレビュー
4. 本番実行の承認取得
5. 実行と検証
