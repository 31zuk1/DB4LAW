# Issue: 存在しない条文へのリンクが残る問題

## 問題

改正法断片内で、親法に存在しない条番号へのリンクが生成されている。

### 具体例

```markdown
# 民法/附則/改正法/R3_L37/附則第1条.md

[[laws/民法/本文/第38:84条.md|第四十五条]]
[[laws/民法/本文/第38:84条.md|第六十七条]]
[[laws/民法/本文/第38:84条.md|第七十一条]]
```

- 民法には第38条までしか存在しない（本則の最終条文は第1050条だが、削除条文を除くと第38条以降は欠番が多い）
- `第38:84条.md` は範囲ノード（redirect-ranges）として生成されたファイル
- 改正法内の「第四十五条」等は、**改正法自身の条文番号**であり、親法への参照ではない

## 期待される動作

以下のいずれかの動作が期待される：

1. **生成時点でリンク化しない** - 親法に存在しない条番号はリンク化しない
2. **範囲ノードへ寄せる** - 削除条文の場合は範囲ノードへリンク
3. **後処理で確実に修正** - pending_links に回して後で解決

## 関連コード・機能

| ファイル | 機能 |
|---------|------|
| `src/legalkg/core/tier2.py` | 参照抽出・リンク化ロジック |
| `scripts/migration/fix_id_collision.py` | `--redirect-ranges` オプション |
| `src/legalkg/utils/range_index.py` | 範囲ノードのインデックス |
| `scripts/migration/pending_links.py` | 遅延リンク解決スキーマ |

## 方針案

### A案: tier2で親法の条文範囲外はリンク化しない

**メリット**: 生成時点で問題を防げる
**デメリット**: 親法の条文一覧を事前に取得する必要がある

```python
# tier2.py の replace_refs() に追加
if article_num > max_article_in_law:
    return original_text  # リンク化しない
```

### B案: pending_links に回す

**メリット**: 既存の遅延解決フローを活用
**デメリット**: 後処理が必要、未解決リンクが残るリスク

```python
# 存在しない条文への参照を pending_links.jsonl に記録
pending_links.append({
    "source_file": file_path,
    "target_article": "第45条",
    "reason": "article_not_found",
    "context": "改正法断片内の参照"
})
```

### C案: range_index で即座に範囲ノードへ

**メリット**: 削除条文のケースを正確に処理
**デメリット**: 範囲ノードが存在しない場合の処理が必要

```python
# tier2.py で範囲ノードを参照
if not article_exists(article_num):
    range_node = range_index.find_range(article_num)
    if range_node:
        return f"[[{range_node}|{display_text}]]"
    else:
        return original_text  # リンク化しない
```

## 推奨: A案 + C案の組み合わせ

1. **tier2 生成時**: 親法に条文が存在するかチェック
2. **存在しない場合**: 範囲ノードを検索
3. **範囲ノードあり**: 範囲ノードへリンク
4. **範囲ノードなし**: リンク化しない（プレーンテキスト）

## 影響範囲

- 民法: `第38:84条.md` へのリンク多数
- 刑法: 同様のケースあり
- 今後追加する法律にも影響

## 優先度

中（グラフの正確性に影響するが、閲覧には支障なし）

## 関連Issue/PR

- cc929d22: 改正法断片の誤リンク解除（本Issueの前提となる修正）
- docs/AMENDMENT_VAULT_DESIGN.md: 改正法統合Vault設計
