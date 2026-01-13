# DB4LAW - Legal Knowledge Graph

日本の法令データをObsidian形式のナレッジグラフに変換するツールです。e-Gov法令APIから法令データを取得し、条文単位のノードと条文間の参照関係（wikilink）を抽出します。

## 特徴

- **日本語パス対応**: `本文/第1条.md`、`附則/改正法/R3_L37/附則第1条.md` などの日本語ディレクトリ構造
- **Wikilink自動生成**: 条文間参照（「第十九条」など）を自動的にObsidian wikiliksに変換
- **漢数字対応**: 「第十九条」「第二十三条の三」などの漢数字表記を自動変換
- **キャッシング**: API応答をMD5ハッシュベースでキャッシュし、再実行時の高速化
- **Obsidian Graph View**: 生成されたVaultをObsidianで開くことで法令のナレッジグラフを可視化

## 処理済み法令

| 法令名 | 本則条文数 | 附則ファイル数 | エッジ数 |
|--------|-----------|---------------|---------|
| 刑法 | 264 | 68 | 713 |
| 民法 | 1,167 | 221 | 1,294 |
| 日本国憲法 | 103 | 1 | 64 |
| 所有者不明土地法 | 63 | 36 | 415 |

## セットアップ

### 必要要件

- Python 3.11以上
- インターネット接続（e-Gov APIへのアクセスに必要）

### インストール

```bash
pip install -r requirements.txt
# または開発モードで
pip install -e .
```

## 使い方

### 基本ワークフロー

```bash
# 1. targets.yaml に処理したい法令IDを追加
# 2. Tier1+2を実行（条文抽出 + 参照リンク化）
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges

# 3. 日本語パスへ移行
python scripts/migration/migrate_to_japanese.py --law 刑法 --apply

# 4. 外部法参照の修正（必要に応じて）
python scripts/migration/fix_id_collision.py --law 刑法 --apply

# 5. 親ファイルにリンク追加
python scripts/migration/add_parent_links.py --law 刑法
```

### targets.yaml の書き方

```yaml
targets:
  - 321CONSTITUTION        # 日本国憲法
  - 140AC0000000045       # 刑法
  - 129AC0000000089       # 民法
  - 430AC0000000049       # 所有者不明土地法
```

## 出力形式

### ディレクトリ構造

```
Vault/laws/刑法/
├── 刑法.md                    # 親ノード（全条文・附則へのリンク）
├── 本文/
│   ├── 第1条.md
│   ├── 第2条.md
│   └── ...
├── 附則/
│   └── 改正法/
│       ├── R3_L37/           # 令和3年法律第37号
│       │   ├── 附則第1条.md
│       │   └── ...
│       └── H19_L54/          # 平成19年法律第54号
└── edges.jsonl               # 参照グラフ
```

### 条文ファイル例

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

##
人を殺した者は、死刑又は無期若しくは五年以上の懲役に処する。
```

### Wikilink形式

条文内の参照は自動的にwikiliksに変換されます：

```markdown
<!-- 変換前 -->
第十九条の規定により...

<!-- 変換後 -->
[[laws/刑法/本文/第19条.md|第十九条]]の規定により...
```

## プロジェクト構造

```
DB4LAW/
├── src/legalkg/              # メインパッケージ
│   ├── client/               # APIクライアント（e-Gov, NDL）
│   ├── core/                 # Tier0/1/2 コアロジック
│   └── utils/                # 漢数字変換など
├── scripts/
│   ├── migration/            # 移行・修正スクリプト
│   │   ├── migrate_to_japanese.py   # 日本語パス移行
│   │   ├── fix_id_collision.py      # 外部法参照修正
│   │   ├── add_parent_links.py      # 親ノードリンク追加
│   │   ├── pending_links.py         # 保留リンク管理
│   │   ├── relink_pending.py        # 保留リンク再リンク
│   │   └── _artifacts/              # 生成物（CSV, JSONL）
│   ├── analysis/             # リンク処理・分析
│   ├── debug/                # デバッグスクリプト
│   └── utils/                # ユーティリティ
├── data/                     # ドメイン分類YAML
├── Vault/laws/               # Obsidian Vault出力先
└── targets.yaml              # 処理対象法令リスト
```

## 移行スクリプト

### migrate_to_japanese.py

英語パス（`articles/main/Article_1.md`）から日本語パス（`本文/第1条.md`）へ移行。

```bash
python scripts/migration/migrate_to_japanese.py --law 刑法 --dry-run
python scripts/migration/migrate_to_japanese.py --law 刑法 --apply
```

### fix_id_collision.py

外部法（民事執行法など）への誤リンクを解除し、保留リンクとして記録。

```bash
python scripts/migration/fix_id_collision.py --law 民法 \
  --pending-log scripts/migration/_artifacts/pending_links.jsonl \
  --apply
```

### relink_pending.py

外部法ノードが作成された後、保留リンクを復元。

```bash
python scripts/migration/relink_pending.py --filter-law 民法 --dry-run
python scripts/migration/relink_pending.py --filter-law 民法 --apply
```

## ノードIDスキーマ

| タイプ | 形式 | 例 |
|--------|------|-----|
| 法令 | `JPLAW:{LAW_ID}` | `JPLAW:140AC0000000045` |
| 本則条文 | `JPLAW:{LAW_ID}#本文#第N条` | `JPLAW:140AC0000000045#本文#第199条` |
| 附則条文 | `JPLAW:{LAW_ID}#附則#附則第N条` | `JPLAW:140AC0000000045#附則#附則第1条` |

## データソース

- **e-Gov法令API**: `https://laws.e-gov.go.jp/api/1`
- **国立国会図書館API**: `https://ndlsearch.ndl.go.jp/api/opensearch`

## ライセンス

MIT
