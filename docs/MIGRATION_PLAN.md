# 日本語パス移行ガイド

## 概要

DB4LAWでは、条文ファイルを日本語パス構造で管理します。Tier1ビルド後に移行スクリプトを実行することで、英語パスから日本語パスへ変換されます。

## 共通モジュール

移行スクリプトは以下の共通モジュールを使用しています：

| モジュール | 場所 | 用途 |
|------------|------|------|
| `article_formatter.py` | `src/legalkg/utils/` | 条文番号変換 |
| `markdown.py` | `src/legalkg/utils/` | YAML frontmatter処理 |
| `config.py` | `scripts/migration/` | パス設定 |

## 移行済み法令

| 法令 | 本則 | 附則 | 移行日 |
|------|------|------|--------|
| 刑法 | 264 | 68 | 2025-01 |
| 民法 | 1,167 | 221 | 2025-01 |
| 日本国憲法 | 103 | 1 | 2025-01 |
| 所有者不明土地法 | 63 | 36 | 2025-01 |

## ディレクトリ構造

### 変換前（Tier1出力）
```
/刑法/
├── articles/
│   ├── main/
│   │   ├── Article_1.md
│   │   └── Article_3_2.md
│   └── suppl/
│       └── 平成19年法律第54号/
│           └── 平成19年法律第54号_Article_1.md
└── 刑法.md
```

### 変換後（日本語パス）
```
/刑法/
├── 本文/
│   ├── 第1条.md
│   └── 第3条の2.md
├── 附則/
│   └── 改正法/
│       └── H19_L54/
│           └── 附則第1条.md
└── 刑法.md
```

## 新規法令の移行手順

### 1. Tier1+2ビルド

```bash
# targets.yaml に法令IDを追加
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges
```

### 2. 日本語パス移行

```bash
# Dry-run で確認
python scripts/migration/migrate_to_japanese.py --law {法令名} --dry-run

# 実行
python scripts/migration/migrate_to_japanese.py --law {法令名} --apply
```

### 3. 外部法参照の修正

```bash
python scripts/migration/fix_id_collision.py --law {法令名} \
  --pending-log scripts/migration/_artifacts/pending_links.jsonl \
  --apply
```

### 4. 親ファイルリンク追加

```bash
python scripts/migration/add_parent_links.py --law {法令名}
```

## ファイル名変換ルール

### 本則

| パターン | 変換前 | 変換後 |
|----------|--------|--------|
| 通常 | `Article_1.md` | `第1条.md` |
| 枝番 | `Article_3_2.md` | `第3条の2.md` |
| 範囲 | `Article_73:76.md` | `第73条から第76条まで.md` |

### 附則

| パターン | 変換前 | 変換後 |
|----------|--------|--------|
| 複数条 | `{法令号}/..._Article_1.md` | `改正法/{KEY}/附則第1条.md` |
| 単一 | `{法令号}.md` | `{法令号}.md`（変更なし） |

### 改正法キー変換

| 日本語表記 | キー |
|------------|------|
| 令和3年法律第37号 | R3_L37 |
| 平成19年法律第54号 | H19_L54 |
| 昭和22年法律第124号 | S22_L124 |

## YAMLフィールド変換

```yaml
# 変換前
article_num: '1'
id: JPLAW:140AC0000000045#main#1
part: main

# 変換後
article_num: 第1条
id: JPLAW:140AC0000000045#本文#第1条
part: 本文
```

## トラブルシューティング

### グレーアウトノードが表示される

外部法への参照がリンク化されている可能性があります：

```bash
# 問題のリンクを検出
python scripts/migration/fix_id_collision.py --law {法令名} --dry-run

# 修正を適用
python scripts/migration/fix_id_collision.py --law {法令名} --apply
```

### 親ファイルにリンクがない

```bash
python scripts/migration/add_parent_links.py --law {法令名}
```

## 生成物

移行スクリプトは以下のファイルを生成します：

| ファイル | 場所 | 内容 |
|----------|------|------|
| `migration_mapping.csv` | `scripts/migration/_artifacts/` | パス変換対応表 |
| `pending_links.jsonl` | `scripts/migration/_artifacts/` | 保留リンク記録 |
| `resolved_links.jsonl` | `scripts/migration/_artifacts/` | 解決済みリンク |
