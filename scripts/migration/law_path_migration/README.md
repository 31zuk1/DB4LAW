# Law Path Migration

法令ディレクトリを日本語名から `law_id` 形式に移行するためのスクリプト群。

## 目的

Linux ファイルシステムの 255 バイト制限により、長い日本語法令名（85文字以上）を持つディレクトリが CI でチェックアウトできない問題を根本的に解決する。

## 移行後の構造

```
Vault/laws/
├── 140AC0000000045/          # law_id (ASCII のみ)
│   ├── law.md                # 固定ファイル名
│   ├── 本文/                 # 条文（そのまま維持）
│   └── 附則/
├── 129AC0000000089/
│   └── law.md
└── _index/
    ├── manifest.jsonl        # 移行マニフェスト
    ├── laws.json             # 機械可読索引
    └── migration_log.jsonl   # 移行ログ
```

## 実行手順

### 1. マニフェスト生成

```bash
cd /path/to/DB4LAW

# Dry-run で確認
python scripts/migration/law_path_migration/generate_manifest.py --dry-run

# マニフェスト生成
python scripts/migration/law_path_migration/generate_manifest.py
```

**出力**: `Vault/_index/manifest.jsonl`

**注意**: law_id の衝突が検出された場合、エラーで停止します。

### 2. 移行実行

```bash
# Dry-run で確認
python scripts/migration/law_path_migration/migrate_laws.py --dry-run

# 実際に移行（破壊的変更）
python scripts/migration/law_path_migration/migrate_laws.py
```

**出力**: `Vault/_index/migration_log.jsonl`

**処理内容**:
- ディレクトリを `laws/<law_id>/` にリネーム
- 代表 md を `law.md` にリネーム
- frontmatter に `law_id`, `aliases` を追加
- 120 バイト超のファイル名はハッシュ名に短縮

### 3. インデックス生成

```bash
python scripts/migration/law_path_migration/generate_index.py
```

**出力**:
- `Vault/_index/laws.json` - 機械可読索引
- `Vault/laws_index.md` - Obsidian 用索引

### 4. パス検証

```bash
python scripts/check_paths.py
```

**チェック内容**:
- `laws/` 直下は ASCII のみ
- パスコンポーネント ≤ 120 バイト
- 相対パス全体 ≤ 200 バイト

### 5. リンクレポート生成

```bash
python scripts/migration/law_path_migration/report_broken_links.py --only-prefix laws/
```

**出力**: `Vault/reports/broken_links.txt`

## law_id 決定ルール

優先順位:
1. `egov_law_id` フィールド
2. `law_id` フィールド
3. `id` フィールド（`JPLAW:` プレフィックス除去）
4. ハッシュ生成: `HASH_` + SHA1(正規化タイトル + 公布日 + URL)[:12]

## 注意事項

- **破壊的変更**: 移行は不可逆。事前にバックアップを推奨
- **内部リンク**: 移行後、既存の wikilink は壊れる可能性あり
- **CI 依存**: 移行完了後、CI がパスすることを確認

## トラブルシューティング

### law_id 衝突

同じ law_id が複数の法令に割り当てられた場合:

```
ERROR: law_id collisions detected!
law_id: 123ABC456DEF
  - 法令A
  - 法令B
```

**対処**: frontmatter の `egov_law_id` を手動で確認・修正

### 移行エラー

```
ERROR: Target directory already exists
```

**対処**: 既に移行済みの可能性。`migration_log.jsonl` を確認

## 関連ファイル

- `scripts/check_paths.py` - パス検証スクリプト（CI で使用）
- `Vault/_index/manifest.jsonl` - 移行マニフェスト
- `Vault/_index/laws.json` - 法令索引
- `Vault/laws_index.md` - Obsidian 索引
