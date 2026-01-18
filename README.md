# DB4LAW

日本の法令をObsidian Vault形式のナレッジグラフに変換するツール。

e-Gov法令APIから法令XMLを取得し、条文単位のMarkdownノードに分解、条文間の参照関係をObsidian WikiLinksとして自動抽出する。

## 概要

```
Vault/laws/刑法/
├── 刑法.md                    # 親ノード（全条文へのリンク）
├── 本文/
│   ├── 第1条.md              # 各条文
│   ├── 第199条.md
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
| 刑法 | 301 | 136 | 713 |
| 民法 | 1,167 | 442 | 1,982 |
| 日本国憲法 | 103 | - | 1 |
| 所有者不明土地法 | 63 | 14 | 415 |

## 主な機能

### 条文間参照の自動リンク化

```markdown
# 変換前
第十九条の規定により...

# 変換後
[[laws/刑法/本文/第19条.md|第十九条]]の規定により...
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
'刑事訴訟法', '民事執行法', '土地収用法', '公証人法', ...
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

## アーキテクチャ

### 3層データモデル

| Tier | 処理内容 | 出力 |
|------|---------|------|
| Tier 0 | e-Gov APIから法令一覧取得 | `{法令名}.md` |
| Tier 1 | XML解析、条文分解 | `本文/第N条.md`, `附則/...` |
| Tier 2 | 参照抽出、WikiLink化 | `edges.jsonl` |

### ノードID体系

```
JPLAW:{LAW_ID}                    # 法令
JPLAW:{LAW_ID}#本文#第199条        # 本則条文
JPLAW:{LAW_ID}#附則#附則第1条      # 附則条文
```

### 条文ファイル形式

```yaml
---
article_num: 第199条
heading: （殺人）
id: JPLAW:140AC0000000045#本文#第199条
law_id: 140AC0000000045
law_name: 刑法
part: 本文
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
│   │   ├── tier1.py          # 条文抽出
│   │   └── tier2.py          # 参照抽出・リンク化
│   └── utils/
│       ├── article_formatter.py  # 条文番号変換
│       ├── markdown.py           # YAML frontmatter処理
│       └── numerals.py           # 漢数字変換
├── scripts/migration/
│   ├── migrate_to_japanese.py    # 日本語パス移行
│   ├── fix_id_collision.py       # 外部法参照修正
│   ├── add_parent_links.py       # 親ファイルリンク追加
│   ├── unlink_amendment_refs.py  # 改正法断片のリンク解除
│   └── _artifacts/               # 生成CSV/JSONL
├── Vault/laws/               # 出力Vault
└── targets.yaml              # 対象法令リスト
```

## データソース

- **e-Gov法令API**: https://laws.e-gov.go.jp/api/1
- **国立国会図書館API**: https://ndlsearch.ndl.go.jp/api/opensearch

## ライセンス

MIT
