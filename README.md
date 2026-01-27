# DB4LAW

日本の法令をObsidian Vault形式のナレッジグラフに変換するツール。

e-Gov法令APIから法令XMLを取得し、条文単位のMarkdownノードに分解、条文間の参照関係をObsidian WikiLinksとして自動抽出する。

## 概要

```
Vault/laws/刑法/
├── 刑法.md                    # 親ノード（全条文へのリンク）
├── 本文/                      # 本則条文
│   ├── 第1条.md
│   ├── 第199条.md
│   └── ...
├── 章/                        # 章ノード
│   ├── 第1章.md
│   └── ...
├── 節/                        # 節ノード（存在する法令のみ）
│   └── ...
├── 附則/
│   └── 改正法/
│       ├── R5_L28/           # 令和5年法律第28号
│       │   ├── 附則第1条.md
│       │   └── ...
│       └── H7_L91/
└── edges.jsonl               # 参照グラフ（JSONL形式）
```

## 処理済み法令

| 法令名 | 本則 | 附則 | 参照エッジ |
|--------|------|------|-----------|
| 刑法 | 301 | 68 | 713 |
| 民法 | 1,167 | 221 | 1,982 |
| 日本国憲法 | 103 | - | 1 |
| 刑事訴訟法 | 715 | 121 | 2,766 |
| 民事訴訟法 | 453 | 92 | 1,019 |
| 会社法 | 1,078 | 31 | 10,000+ |
| 行政事件訴訟法 | 51 | 36 | 500+ |
| 所有者不明土地法 | 63 | 14 | 415 |

## 主な機能

### 条文間参照の自動リンク化

```markdown
# 変換前
第十九条の規定により...

# 変換後
[[laws/刑法/本文/第19条.md|第十九条]]の規定により...
```

### 参照解決の優先順位

参照は以下の優先順位で解決される：

1. **法令番号付き参照** - `弁護士法（昭和二十四年法律第二百五号）第三十条` → 弁護士法へ
2. **本法系参照** - `本法第十条`, `この法律第五条`, `当該法第三条` → 自法令へ
3. **明示法令名** - `刑法第百九十九条`, `会社法第一条` → 指定法令へ
4. **同法スコープ** - `民法第749条、第771条` → 列挙はスコープ継続

### 本法/この法律/当該法 参照

自己参照パターンを正しく解釈：

```markdown
# 本法参照
本法第十条の規定 → [[laws/テスト法/本文/第10条.md|第十条]]

# 列挙対応
本法第一条、第二条、第三条 → すべて自法令にリンク
```

### クロスリンク（法令間参照）

処理済み法令間の参照を自動でクロスリンク化：

```markdown
# 刑法附則内の参照
刑事訴訟法[[laws/刑事訴訟法/本文/第344条.md|第三百四十四条]]に一項を加える...
```

- 長い法令名を優先マッチ（「刑事訴訟法」を「刑法」より先に検出）
- 文末の法令名を直近参照として優先（同一文内に複数法令がある場合）

### Vault実在ベースリンク

EXTERNAL_LAW_PATTERNSに含まれる法令でも、Vaultに存在すればリンク化：

```markdown
# 会社法がVaultに存在する場合
会社法第一条 → [[laws/会社法/本文/第1条.md|第一条]]

# 少年法がVaultに存在しない場合
少年法第一条 → 少年法第一条（リンク化しない）
```

### 親法スコープ判定

「民法第749条、第771条及び第788条」のような列挙パターンを正しく検出：

- 同一文内で法律名（民法/新民法/旧民法等）が出現した後の「第N条」をリンク化
- 照応語（同法、同条、その、当該等）でスコープをリセット
- 段落区切りでスコープをリセット

### 外部法参照の除外

60以上の外部法パターンを認識し、誤リンクを防止：

```python
# tier2.py EXTERNAL_LAW_PATTERNS
'民事執行法', '土地収用法', '公証人法', '少年法', ...
```

クロスリンク対象法令は `CROSS_LINKABLE_LAWS`（エイリアス辞書）で管理：

```python
# tier2.py CROSS_LINKABLE_LAWS
'刑法': '刑法',
'旧刑法': '刑法',      # エイリアス
'憲法': '日本国憲法',  # 正規化
```

### 改正法断片モデル

e-Gov統合条文では改正法が親法の附則に断片として分散格納される。
これを識別し、適切なメタデータを付与：

```yaml
suppl_kind: amendment
amendment_law_id: R5_L28
amend_law:
  num: 令和五年五月一七日法律第二八号
  normalized_id: R5_L28
  scope: partial
  parent_law_id: 140AC0000000045
  parent_law_name: 刑法
```

改正法断片内の裸の「第N条」は改正法自身を指すためリンク化しない（方式B）。

### 構造ノード（章・節）

章・節の構造ノードを自動生成：

```yaml
# 章/第2章の2.md
---
type: chapter
chapter_num: 22
chapter_title: 第二章の二　社債管理補助者
article_ids: [...]
---
```

### Obsidian Breadcrumbs / Dataview 対応

階層ナビゲーションとデータ検索用のメタデータを自動付与：

```yaml
type: article                      # ノード種別
parent: '[[laws/刑法/刑法]]'       # 親法ノードへのリンク
tags:
  - 刑法
  - kind/article                   # 種別タグ
```

**ノード種別 (`type`):**

| 値 | 対象 | kind/* タグ |
|----|------|-------------|
| `law` | 親法ノード | `kind/law` |
| `article` | 本文条文 | `kind/article` |
| `chapter` | 章ノード | `kind/chapter` |
| `section` | 節ノード | `kind/section` |
| `supplement` | 附則 | `kind/supplement` |
| `amendment_fragment` | 改正法断片 | `kind/amendment_fragment` |

**Dataview クエリ例:**

```dataview
TABLE article_num, heading
FROM "laws/刑法"
WHERE type = "article"
SORT article_num ASC
```

### エッジスキーマ

参照グラフは `edges.jsonl` に出力：

```json
{"source": "JPLAW:...", "target": "JPLAW:...", "type": "refs", "relation": "internal"}
{"source": "JPLAW:...#chapter#1", "target": "JPLAW:...#main#1", "type": "contains", "relation": "chapter_contains_article"}
```

### 削除条文の範囲ノード

削除された条文範囲は範囲ノードとして管理：

```
第38:84条.md  # 旧第38条〜第84条（削除）
第71条への参照 → 第38:84条.md にリダイレクト
```

## セットアップ

```bash
# Python 3.11以上
pip install -r requirements.txt
# または
pip install -e .
```

## 使い方

### 1. 対象法令の指定

`targets.yaml` を編集：

```yaml
targets:
  - 321CONSTITUTION        # 日本国憲法
  - 140AC0000000045       # 刑法
  - 129AC0000000089       # 民法
```

### 2. 条文抽出と参照リンク化

```bash
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges
```

### 3. 日本語パスへ移行

```bash
python scripts/migration/migrate_to_japanese.py --law 刑法 --dry-run
python scripts/migration/migrate_to_japanese.py --law 刑法 --apply
```

### 4. 親ファイルにリンク追加

```bash
python scripts/migration/add_parent_links.py --law 刑法
```

### 5. Breadcrumbs/Dataview用メタデータ追加

```bash
# dry-run（変更確認）
python scripts/migration/normalize_frontmatter.py --dry-run --law 刑法

# 適用
python scripts/migration/normalize_frontmatter.py --apply --law 刑法
```

### 6. WikiLink整合性チェック

```bash
python scripts/qa/check_wikilinks.py --vault ./Vault --only-prefix laws/
```

空リンク（参照先が存在しないWikiLink）を検出。削除条文など仕様上許容するパターンは `link_check_ignore.txt` で除外。

## アーキテクチャ

### 3層データモデル

| Tier | 処理内容 | 出力 |
|------|---------|------|
| Tier 0 | e-Gov APIから法令一覧取得 | `{法令名}.md` |
| Tier 1 | XML解析、条文・構造ノード分解 | `本文/第N条.md`, `章/`, `節/`, `附則/...` |
| Tier 2 | 参照抽出、WikiLink化 | `edges.jsonl` |

### ノードID体系

```
JPLAW:{LAW_ID}                    # 法令
JPLAW:{LAW_ID}#main#199           # 本則条文
JPLAW:{LAW_ID}#suppl#1            # 附則条文
JPLAW:{LAW_ID}#chapter#1          # 章
JPLAW:{LAW_ID}#section#1          # 節
```

### 条文ファイル形式

```yaml
---
id: JPLAW:140AC0000000045#main#199
type: article
parent: '[[laws/刑法/刑法]]'
law_id: 140AC0000000045
law_name: 刑法
part: main
article_num: '199'
heading: （殺人）
tags:
  - 刑法
  - kind/article
---

# 第百九十九条 （殺人）

人を殺した者は、死刑又は無期若しくは五年以上の懲役に処する。
```

## プロジェクト構成

```
DB4LAW/
├── src/legalkg/
│   ├── cli.py                # Typer CLI
│   ├── client/               # e-Gov/NDL APIクライアント
│   ├── core/
│   │   ├── tier0.py          # 法令一覧取得
│   │   ├── tier1.py          # 条文・構造ノード抽出
│   │   ├── tier2.py          # 参照抽出・リンク化
│   │   └── edge_schema.py    # Edge schema v1/v2
│   └── utils/
│       ├── article_formatter.py  # 条文番号変換
│       ├── markdown.py           # YAML frontmatter処理
│       ├── numerals.py           # 漢数字変換
│       └── patterns.py           # WikiLink正規表現
├── scripts/
│   ├── migration/
│   │   ├── migrate_to_japanese.py    # 日本語パス移行
│   │   ├── fix_id_collision.py       # 外部法参照修正
│   │   ├── add_parent_links.py       # 親ファイルリンク追加
│   │   ├── unlink_amendment_refs.py  # 改正法断片のリンク解除
│   │   ├── normalize_frontmatter.py  # Breadcrumbs/Dataview用メタデータ追加
│   │   ├── fix_frontmatter.py        # YAML frontmatter修復
│   │   └── _artifacts/               # 生成CSV/JSONL
│   └── qa/
│       ├── check_wikilinks.py        # WikiLink整合性チェック
│       └── link_check_ignore.txt     # 除外パターン
├── tests/                    # pytest テスト（139件）
├── Vault/laws/               # 出力Vault
└── targets.yaml              # 対象法令リスト
```

## テスト

```bash
# 全テスト実行
pytest

# 特定テストファイル
pytest tests/test_tier2_vault_based.py -v
pytest tests/test_tier2_self_law_reference.py -v
```

## データソース

- **e-Gov法令API**: https://laws.e-gov.go.jp/api/1
- **国立国会図書館API**: https://ndlsearch.ndl.go.jp/api/opensearch

## ライセンス

MIT
