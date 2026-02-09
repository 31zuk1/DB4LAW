# DB4LAW

**日本法令ナレッジグラフ生成ツール**

[![CI](https://github.com/your-repo/db4law/actions/workflows/ci.yml/badge.svg)](https://github.com/your-repo/db4law/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

e-Gov法令APIから取得した法令XMLを、条文単位のMarkdownノードに分解し、条文間の参照関係をObsidian WikiLinksとして自動抽出するツール。

## 特徴

- **条文単位のノード化**: 各条文を独立したMarkdownファイルとして管理
- **参照の自動リンク化**: 「第十九条」→ `[[laws/.../本文/第19条.md|第十九条]]`
- **法令間クロスリンク**: 処理済み法令間の相互参照を自動検出
- **Obsidian連携**: Breadcrumbs/Dataview対応メタデータを自動付与
- **参照グラフ出力**: edges.jsonlによる機械可読な参照関係

## クイックスタート

```bash
# セットアップ（Python 3.11+）
uv sync

# 法令を処理
uv run python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges

# WikiLink整合性チェック
uv run python scripts/qa/check_wikilinks.py --vault ./Vault
```

## 処理済み法令

| 法令名 | 法令ID | 本則 | 附則 |
|--------|--------|------|------|
| 日本国憲法 | 321CONSTITUTION | 103 | - |
| 刑法 | 140AC0000000045 | 301 | 68 |
| 民法 | 129AC0000000089 | 1,167 | 221 |
| 刑事訴訟法 | 323AC0000000131 | 715 | 121 |
| 民事訴訟法 | 408AC0000000109 | 453 | 92 |
| 会社法 | 417AC0000000086 | 1,078 | 31 |
| 行政事件訴訟法 | 337AC0000000139 | 51 | 36 |
| 労働基準法 | 322AC0000000049 | 136 | 57 |
| 商法 | 132AC0000000048 | 851 | 65 |
| 破産法 | 416AC0000000075 | 280 | 27 |
| 不動産登記法 | 416AC0000000123 | 164 | 21 |
| 行政手続法 | 405AC0000000088 | 46 | 15 |
| 著作権法 | 345AC0000000048 | 124 | 65 |
| 特許法 | 334AC0000000121 | 204 | 70 |
| 借地借家法 | 403AC0000000090 | 54 | 9 |
| 消費者契約法 | 412AC0000000061 | 51 | 22 |
| 所有者不明土地法 | 430AC0000000049 | 63 | 14 |
| 国籍法 | 325AC0000000147 | 20 | 10 |

## 出力構造

```
Vault/laws/{law_id}/
├── {法令名}_law.md           # 親ノード（構造リンク）
├── 本文/                      # 本則条文
│   ├── 第1条.md
│   ├── 第199条.md
│   └── ...
├── 章/                        # 章ノード
│   ├── 第1章.md
│   ├── 第6章の2.md           # 枝番号章
│   └── ...
├── 節/                        # 節ノード（存在する法令のみ）
│   └── 第1章第1節.md
├── 附則/
│   ├── 制定時附則.md         # 直接附則
│   └── 令和五年.../          # 改正法断片
│       ├── ..._第1条.md
│       └── ...
└── edges.jsonl               # 参照グラフ
```

## 参照解決

### 優先順位

1. **法令番号付き参照**: `弁護士法（昭和二十四年法律第二百五号）第三十条` → 弁護士法へ
2. **本法系参照**: `本法第十条`, `この法律第五条` → 自法令へ
3. **明示法令名**: `刑法第百九十九条` → 指定法令へ
4. **列挙スコープ**: `民法第749条、第771条` → スコープ継続

### 変換例

```markdown
# 入力
第十九条の規定により...

# 出力
[[laws/140AC0000000045/本文/第19条.md|第十九条]]の規定により...
```

### クロスリンク対象法令

以下の法令間で相互参照を自動リンク化:

| 法令 | エイリアス |
|------|-----------|
| 刑法 | 旧刑法, 新刑法, 改正前の刑法, 改正後の刑法 |
| 民法 | 旧民法, 新民法, 改正前の民法, 改正後の民法 |
| 日本国憲法 | 憲法 |
| 刑事訴訟法 | 新刑事訴訟法, 旧刑事訴訟法 |
| 民事訴訟法 | 新民事訴訟法, 旧民事訴訟法 |
| 会社法 | 新会社法, 旧会社法 |
| 行政事件訴訟法 | 新行政事件訴訟法, 旧行政事件訴訟法 |
| 所有者不明土地法 | - |

## ノードメタデータ

### Frontmatter構造

```yaml
---
id: JPLAW:140AC0000000045#main#199
type: article
parent: '[[laws/140AC0000000045/刑法_law.md|刑法]]'
law_id: 140AC0000000045
law_name: 刑法
part: main
article_num: '199'
heading: （殺人）
chapter_num: 26
tags:
  - 刑法
---
```

### ノード種別 (`type`)

| 値 | 対象 |
|----|------|
| `law` | 親法ノード |
| `article` | 本文条文 |
| `chapter` | 章ノード |
| `section` | 節ノード |
| `supplement` | 附則 |
| `amendment_fragment` | 改正法断片 |

### Dataviewクエリ例

```dataview
TABLE article_num, heading
FROM "laws/140AC0000000045"
WHERE type = "article"
SORT article_num ASC
```

## コマンドリファレンス

### build-tier1

法令の取得・分解・参照抽出を実行。

```bash
python -m legalkg build-tier1 \
  --vault ./Vault \
  --targets targets.yaml \
  --extract-edges \
  --generate-structure-nodes
```

| オプション | 説明 |
|-----------|------|
| `--vault` | Vaultルートディレクトリ（必須） |
| `--targets` | 対象法令リストYAML（必須） |
| `--extract-edges` | 参照グラフを出力 |
| `--generate-structure-nodes` | 章・節ノードを生成 |
| `--edge-schema` | v2（標準）または v1（互換） |

### マイグレーションスクリプト

| スクリプト | 用途 |
|-----------|------|
| `restructure_tree_links.py` | 木構造リンク再構築（Graph毛玉化防止） |
| `fix_chapter_filenames.py` | 章ファイル名の枝番号修正 |
| `fix_structure_headings.py` | 編/章/節見出しの重複除去（生成ロジック準拠） |
| `normalize_frontmatter.py` | Breadcrumbs/Dataview用メタデータ追加 |
| `fix_amendment_fragment_links.py` | 改正法断片リンク修正 |

```bash
# 既存Vaultの編/章/節見出しを再生成なしで補正（dry-run）
uv run python scripts/migration/fix_structure_headings.py --vault ./Vault

# 実適用
uv run python scripts/migration/fix_structure_headings.py --vault ./Vault --apply
```

### QAスクリプト

```bash
# WikiLink整合性チェック
python scripts/qa/check_wikilinks.py --vault ./Vault

# Vault監査
python scripts/qa/audit_vault.py --vault ./Vault --targets targets.yaml
```

### 投影Vaultランチャー

巨大な `Vault/` を直接開かずに、選択法令だけの軽量Vaultを作る:

```bash
# 例: 刑法と民法のみの投影Vaultを作成
uv run db4law-proj create --laws 140AC0000000045,129AC0000000089

# 投影セッションのリンク健全性を診断
uv run db4law-proj doctor --session-id <session_id>

# Obsidianで投影Vaultを開く
uv run db4law-proj open --session-id <session_id>

# source law配下の誤配置 .obsidian を検査/除去
uv run db4law-proj clean-markers --session-id <session_id>
uv run db4law-proj clean-markers --session-id <session_id> --apply
```

詳細: `docs/projection_vault.md`

#### 投影Vault起動トラブルシュート

- `db4law-proj: command not found` の場合は `uv run db4law-proj ...` を使う。
- `Vault not found` が出る場合は、まず `uv sync --reinstall-package legalkg` 後に再実行する。
- 法令ディレクトリ配下に `.obsidian` があると誤ったVaultが開くことがあるため、`clean-markers` で除去する。

## アーキテクチャ

### 3層データモデル

| Tier | 処理内容 | 出力 |
|------|---------|------|
| Tier 0 | e-Gov APIから法令一覧取得 | 法令メタデータ |
| Tier 1 | XML解析、条文・構造ノード分解 | Markdownファイル |
| Tier 2 | 参照抽出、WikiLink化 | edges.jsonl |

### ノードID体系

```
JPLAW:{LAW_ID}                    # 法令
JPLAW:{LAW_ID}#main#199           # 本則条文
JPLAW:{LAW_ID}#suppl#1            # 附則条文
JPLAW:{LAW_ID}#chapter#1          # 章
JPLAW:{LAW_ID}#chapter#1#section#1 # 節
```

### エッジスキーマ（v2）

```json
{"source": "JPLAW:...", "target": "JPLAW:...", "type": "refs", "relation": "internal"}
{"source": "JPLAW:...#chapter#1", "target": "JPLAW:...#main#1", "type": "contains"}
```

## プロジェクト構成

```
DB4LAW/
├── src/legalkg/
│   ├── cli.py                    # Typer CLI
│   ├── core/
│   │   ├── tier0.py              # 法令一覧取得
│   │   ├── tier1.py              # 条文・構造ノード抽出
│   │   ├── tier2.py              # 参照抽出・リンク化
│   │   └── edge_schema.py        # Edge schema
│   └── utils/
│       ├── article_formatter.py  # 条文番号変換
│       ├── markdown.py           # YAML frontmatter処理
│       └── patterns.py           # WikiLink正規表現
├── scripts/
│   ├── migration/                # マイグレーションスクリプト
│   └── qa/                       # 品質保証スクリプト
├── tests/                        # pytest（174件）
├── Vault/                        # 出力Vault
├── targets.yaml                  # 対象法令リスト
└── CLAUDE.md                     # Claude Code用ガイド
```

## 開発

### セットアップ

```bash
# 推奨
uv sync

# 既存運用
pip install -e .

# 最小構成
pip install -r requirements.txt
```

### テスト

```bash
# 全テスト実行
PYTHONPATH=./src pytest

# 特定テスト
PYTHONPATH=./src pytest tests/test_tier2_vault_based.py -v
```

### 主要テストファイル

| ファイル | テスト内容 |
|---------|----------|
| `test_tier2_self_law_reference.py` | 本法/この法律参照 |
| `test_tier2_vault_based.py` | Vault実在ベースリンク |
| `test_tier2_amendment.py` | 改正法断片処理 |
| `test_tier2_external_law_scope.py` | 外部法令スコープ |
| `test_tier1_structure_nodes.py` | 構造ノード生成 |

## 制限事項

- **改正法断片**: e-Gov統合条文では改正法が親法附則に分散格納される。改正法自身の条文へのリンクは生成不可（改正法Vaultが存在しないため）
- **削除条文**: 後の改正で削除された条文への歴史的参照は空リンクとなる（除外パターンで許容）
- **未施行条文**: 施行日前の改正で追加される条文への参照は空リンクとなる

## データソース

- **e-Gov法令API**: https://laws.e-gov.go.jp/api/1
- **国立国会図書館API**: https://ndlsearch.ndl.go.jp/api/opensearch

## ライセンス

MIT License

## 関連ドキュメント

- [CLAUDE.md](./CLAUDE.md) - Claude Code用開発ガイド
- [docs/AMENDMENT_VAULT_DESIGN.md](./docs/AMENDMENT_VAULT_DESIGN.md) - 改正法Vault設計
- [docs/projection_vault.md](./docs/projection_vault.md) - 投影Vaultランチャー運用
