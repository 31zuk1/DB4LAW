# Legal Knowledge Graph PoC

日本の法令データをObsidian形式のナレッジグラフに変換するツールです。e-Gov法令APIから法令データを取得し、条文単位のノードと条文間の参照関係を抽出し、国立国会図書館（NDL）のメタデータで補強します。

## 特徴

本プロジェクトは3層のデータ生成モデルを採用しています：

- **Tier 0（メタデータ生成）**: 現行法令すべて（約2000件以上）のメタデータを生成
- **Tier 1（条文抽出）**: 指定した法令のXMLをパースし、条文単位のMarkdownファイルを生成
- **Tier 2（参照抽出）**: 条文間の相互参照を正規表現で抽出し、ナレッジグラフのエッジを生成
- **補強（Enrichment）**: 国立国会図書館のデータで法案提出情報などを追加

### 主な機能

- **漢数字対応**: 「第十九条」「第二十三条の三」などの漢数字表記を自動変換
- **キャッシング**: API応答をMD5ハッシュベースでキャッシュし、再実行時の高速化
- **レート制限**: e-Gov API（0.5秒）、NDL API（1.0秒）の自動レート制限
- **Obsidian連携**: 生成されたVaultをObsidianで開くことで法令のナレッジグラフを可視化

## セットアップ

### 必要要件

- Python 3.11以上
- インターネット接続（e-Gov API、NDL APIへのアクセスに必要）

### インストール

```bash
# 依存関係のインストール
pip install -r requirements.txt

# または開発モードでインストール
pip install -e .
```

## 使い方

### 基本的なワークフロー

1. **Tier 0を実行**して全法令のメタデータを生成
2. **targets.yamlを編集**して処理したい法令を指定
3. **Tier 1+2を実行**して条文と参照関係を抽出
4. **Enrichmentを実行**してNDLデータを追加（オプション）
5. **Obsidianで開く**してナレッジグラフを可視化

### コマンド詳細

#### 1. Tier 0 - メタデータ生成

全法令のメタデータを取得してMarkdownファイルを生成します。

```bash
python -m legalkg build-tier0 --vault ./Vault --as-of 2025-12-30
```

**オプション:**
- `--vault`: 出力先のVaultディレクトリ（デフォルト: `./Vault`）
- `--as-of`: 基準日（YYYY-MM-DD形式、デフォルト: 当日）

**実行時間:** 約1時間（レート制限により）
**出力:** `Vault/laws/{LAW_ID}/{title}.md` 形式で約2000件以上のファイル

#### 2. Tier 1 - 条文抽出

特定の法令について、条文単位のMarkdownファイルを生成します。

```bash
# まずtargets.yamlを編集
# targets:
#   - 321CONSTITUTION        # 日本国憲法
#   - 140AC0000000045       # 刑法

python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml
```

**出力:**
- `articles/main/Article_{N}.md` - 本則の条文
- `articles/suppl/Article_{N}.md` - 附則の条文

#### 3. Tier 2 - 参照抽出

Tier 1と同時に条文間の参照関係を抽出します。

```bash
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges
```

**抽出パターン例:**
- 「第十九条」→ Article 19への参照
- 「第二十三条の三」→ Article 23_3への参照

**出力:** `edges.jsonl` ファイル（各法令のディレクトリ内）

**例（刑法）:** 713件のエッジを抽出

#### 4. Enrichment - NDLデータ追加

国立国会図書館のAPIから立法過程のメタデータを取得して追加します。

```bash
python -m legalkg enrich-ndl --vault ./Vault --targets targets.yaml
```

**追加される情報:**
- 法案提出者
- 公布日
- 法案の説明

### targets.yamlの書き方

処理対象の法令IDを指定します：

```yaml
targets:
  - 321CONSTITUTION        # 日本国憲法
  - 140AC0000000045       # 刑法
  - 明治29年法律第89号    # 民法
```

法令IDはe-Gov法令APIの形式、または法令番号（「明治29年法律第89号」など）で指定できます。

## デバッグ・開発

### デバッグスクリプト

```bash
# NDL APIの動作確認
python debug_ndl.py

# 参照抽出の正規表現テスト
python debug_regex.py
```

### テスト実行

```bash
pytest
```

### キャッシュ管理

```bash
# キャッシュをクリア（新しいデータを取得したい場合）
rm -rf cache/*.json

# キャッシュサイズを確認
du -sh cache/
```

## プロジェクト構造

```
DB4LAW/
├── src/legalkg/              # メインパッケージ
│   ├── client/               # APIクライアント
│   │   ├── base.py          # キャッシング・レート制限機能付き基底クラス
│   │   ├── egov.py          # e-Gov法令APIクライアント
│   │   └── ndl.py           # 国立国会図書館クライアント
│   ├── core/                # コアロジック
│   │   ├── tier0.py         # メタデータ生成
│   │   ├── tier1.py         # 条文抽出
│   │   ├── tier2.py         # 参照抽出
│   │   └── enrichment.py    # NDL補強
│   ├── utils/               # ユーティリティ
│   │   ├── fs.py            # ファイルシステム操作
│   │   └── numerals.py      # 漢数字変換
│   ├── config.py            # 設定
│   └── cli.py               # CLIインターフェース
├── data/                    # 設定データ
│   ├── class_to_domain.yaml # ドメイン分類マッピング
│   └── domain_overrides.yaml # 手動オーバーライド
├── cache/                   # APIレスポンスキャッシュ
├── Vault/                   # Obsidian Vault出力先
│   └── laws/               # 法令ディレクトリ
├── targets.yaml            # 処理対象法令リスト
└── pyproject.toml          # パッケージ設定
```

## データソース

- **e-Gov法令API** (`https://laws.e-gov.go.jp/api/1`)
  - 法令の全文データとメタデータを提供
  - レート制限: 0.5秒/リクエスト

- **国立国会図書館（NDL）OpenSearch API** (`https://ndlsearch.ndl.go.jp/api/opensearch`)
  - 立法過程のメタデータを提供
  - レート制限: 1.0秒/リクエスト

## 出力形式

### 法令メタデータファイル

```yaml
---
id: JPLAW:140AC0000000045
egov_law_id: 140AC0000000045
law_no: 明治四十年法律第四十五号
title: 刑法
tier: 2
domain: []
---

# 刑法
...
```

### エッジファイル (edges.jsonl)

```json
{"from": "JPLAW:140AC0000000045#main#1", "to": "JPLAW:140AC0000000045#main#19", "type": "refers_to", "evidence": "第十九条", "confidence": 0.9, "source": "regex_v1"}
```

## ノードIDスキーマ

- **法令ノード:** `JPLAW:{LAW_ID}`
  - 例: `JPLAW:140AC0000000045` (刑法)

- **条文ノード:** `JPLAW:{LAW_ID}#{part}#{article_num}`
  - 例: `JPLAW:140AC0000000045#main#1` (刑法第1条)
  - 枝番: `JPLAW:140AC0000000045#main#19_3` (刑法第19条の3)

## ライセンス

MIT
