# 木＋参照グラフ設計 実装計画

## 現状調査結果

### 1. 階層構造の問題

| ノード | 現在の parent | 期待する parent |
|--------|--------------|----------------|
| 章 | 法令 | 法令 (OK) |
| 節 | 章 | 章 (OK) |
| 条文 | **法令** | **章 or 節** |

**問題**: 条文の parent が常に法令直下を指しており、木構造が浅い。

### 2. Graph 毛玉化の原因

| ノード | 本文内 wikilink 数 | 影響 |
|--------|-------------------|------|
| 刑法 章ノード (42件) | 343 | 章→条文のリンクが大量 |
| 会社法 章/節 (72件) | 2,113 | さらに大量 |

章/節ノードの「この章の条文」セクションが Graph で大量のエッジとして表示される。

### 3. 現在の木構造イメージ

```
law ─┬─ chapter ─── section
     │
     └─ article ← 全条文が法令直下に孤立
```

### 4. 目標の木構造イメージ

```
law ─┬─ chapter ─┬─ section ─── article
     │           │
     │           └─ article (節なし)
     │
     └─ article (章なし法令)
```

---

## 案の比較

### 案A: 最小変更（parent のみ修正）

**変更内容:**
- 条文の parent を直上階層に修正
- 章/節ノードの条文一覧はそのまま

**メリット:**
- 変更箇所が少ない
- 情報量は維持

**デメリット:**
- Graph は依然として毛玉化する（章→条文の下向きリンクが残る）

### 案B: Graph 最適化（parent + 条文一覧の扱い変更）

**変更内容:**
- 条文の parent を直上階層に修正
- 章/節ノードの条文一覧 wikilink を Dataview クエリに置換

**メリット:**
- Graph が「木の幹 + 条文参照の横線」になる
- 毛玉化を大幅に抑制

**デメリット:**
- Dataview プラグイン依存
- 既存 Vault のマイグレーションが必要

### 案C: ハイブリッド（Graph 用と表示用を分離）

**変更内容:**
- 条文の parent を直上階層に修正
- 章/節ノードの条文一覧を frontmatter `article_links` フィールドに移動
- 本文は Dataview で動的生成

**メリット:**
- frontmatter にリンク情報を保持（外部ツールで利用可能）
- Graph は木構造のみ

**デメリット:**
- 構造変更が大きい

---

## 推奨案: 案B（Graph 最適化）

### 理由

1. **目標達成度が高い**: Graph が「木 + 参照」になる
2. **既存の frontmatter を活用**: `article_ids`, `article_nums` は既に存在
3. **Dataview は標準的**: Obsidian エコシステムで広く使用
4. **段階的導入可能**: Phase 分割で安全に移行

---

## 実装計画

### Phase 0: 準備（現状維持しつつ基盤整備）

**目的**: 既存 Vault を壊さずに新機能をオプトイン可能に

**タスク:**

| タスク | 変更ファイル | 完了条件 |
|--------|-------------|----------|
| 0-1. `--parent-mode` フラグ追加 | `cli.py`, `tier1.py` | `hierarchical` (新) / `flat` (旧) 選択可能 |
| 0-2. 単体テスト追加 | `tests/test_tier1_parent.py` | parent が直上階層を指すことを検証 |

**コマンド例:**
```bash
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges --parent-mode hierarchical
```

### Phase 1: 条文 parent の階層化

**目的**: 条文の parent を直上階層に設定

**タスク:**

| タスク | 変更ファイル | 完了条件 |
|--------|-------------|----------|
| 1-1. `_build_frontmatter` で parent 計算 | `tier1.py` | section > chapter > law の優先順 |
| 1-2. 章/節ファイル名の解決ロジック | `tier1.py` | `_format_chapter_name`, `_format_section_name` 再利用 |
| 1-3. 孤立条文の処理 | `tier1.py` | chapter_num がない場合は law 直下 |
| 1-4. テスト | `tests/test_tier1_parent.py` | 全パターン網羅 |

**変更の詳細 (tier1.py `_build_frontmatter`):**

```python
# 現在
"parent": f"[[laws/{law_name}/{law_name}]]" if law_name else None,

# 変更後（parent_mode == "hierarchical" の場合）
parent = self._resolve_parent(law_name, context)
```

```python
def _resolve_parent(self, law_name: str, context: Optional[Dict]) -> Optional[str]:
    """条文の直上階層を解決"""
    if not law_name:
        return None

    # 節が存在する場合
    if context and context.get("section_num") is not None:
        chapter_num = context.get("chapter_num")
        section_num = context.get("section_num")
        chapter_title = context.get("chapter_title")
        chapter_name = self._format_chapter_name(chapter_num, chapter_title)
        section_name = self._format_section_name(section_num, context.get("section_title"))
        return f"[[laws/{law_name}/節/{chapter_name}{section_name}]]"

    # 章が存在する場合
    if context and context.get("chapter_num") is not None:
        chapter_num = context.get("chapter_num")
        chapter_title = context.get("chapter_title")
        chapter_name = self._format_chapter_name(chapter_num, chapter_title)
        return f"[[laws/{law_name}/章/{chapter_name}]]"

    # 孤立条文（章/節なし）
    return f"[[laws/{law_name}/{law_name}]]"
```

### Phase 2: 章/節ノードの条文一覧を Dataview 化

**目的**: Graph から章→条文の下向きリンクを除去

**タスク:**

| タスク | 変更ファイル | 完了条件 |
|--------|-------------|----------|
| 2-1. `--chapter-links` フラグ追加 | `cli.py`, `tier1.py` | `wikilink` (旧) / `dataview` (新) |
| 2-2. 章ノード本文生成を変更 | `tier1.py` | Dataview クエリ生成 |
| 2-3. 節ノード本文生成を変更 | `tier1.py` | Dataview クエリ生成 |
| 2-4. マイグレーションスクリプト | `scripts/migration/` | 既存 Vault を変換 |

**Dataview クエリ例:**

```markdown
## この章の条文

```dataview
TABLE article_num AS "条番号", heading AS "見出し"
FROM "laws/刑法/本文"
WHERE chapter_num = 1
SORT article_num ASC
```

### Phase 3: マイグレーション & QA

**目的**: 既存 Vault の更新と品質保証

**タスク:**

| タスク | 変更ファイル | 完了条件 |
|--------|-------------|----------|
| 3-1. マイグレーションスクリプト作成 | `scripts/migration/update_parent.py` | 条文の parent を一括更新 |
| 3-2. 章/節リンク変換スクリプト | `scripts/migration/convert_chapter_links.py` | wikilink → Dataview |
| 3-3. WikiLink 整合性チェック | `scripts/qa/check_wikilinks.py` | broken 0 |
| 3-4. 全テスト実行 | `tests/` | 139+ tests PASS |
| 3-5. リグレッションチェック | 手動 | CLAUDE.md 記載のコマンド実行 |

---

## テスト計画

### 新規テスト (tests/test_tier1_parent.py)

```python
class TestParentHierarchy:
    """parent が直上階層を指すことを検証"""

    def test_article_with_section_parent_is_section(self):
        """節がある条文の parent は節を指す"""
        # 会社法第100条: section_num=6 → parent = [[laws/会社法/節/第1章第6款]]
        pass

    def test_article_with_chapter_only_parent_is_chapter(self):
        """節がない条文の parent は章を指す"""
        # 刑法第199条: chapter_num=26, section_num=None → parent = [[laws/刑法/章/第26章]]
        pass

    def test_article_without_structure_parent_is_law(self):
        """章/節がない条文の parent は法令を指す"""
        # 孤立条文 → parent = [[laws/法令名/法令名]]
        pass

    def test_parent_is_always_single(self):
        """parent は常に1本（配列ではない）"""
        pass

    def test_chapter_parent_is_law(self):
        """章の parent は法令を指す"""
        pass

    def test_section_parent_is_chapter(self):
        """節の parent は章を指す"""
        pass
```

### 既存テスト確認

- `test_tier1_structure_nodes.py`: 構造ノード生成テスト
- `test_tier2_*.py`: 参照抽出テスト（影響なし）

---

## リスクと対策

### リスク1: Graph が依然として毛玉化

**原因**: 条文間参照 wikilink が多い場合

**対策**:
- 外部参照は曖昧ならリンク化しない（既に実装済み）
- 内部参照は価値が高いので許容
- Obsidian の Graph 設定で depth 調整を推奨

### リスク2: Dataview プラグイン非依存環境

**原因**: Dataview がインストールされていない環境

**対策**:
- `--chapter-links wikilink` オプションで旧動作を維持可能
- README に Dataview 推奨を明記

### リスク3: 既存 Vault の再生成が必要

**影響範囲**:
- 処理済み法令 8件の全条文ファイル（約4,000件）

**対策**:
- マイグレーションスクリプトで parent のみ更新（本文は変更なし）
- `--dry-run` で影響確認後に適用

### リスク4: パフォーマンス

**原因**: 階層解決のための追加処理

**対策**:
- `_resolve_parent` は context を参照するだけなので O(1)
- Vault 存在チェックのキャッシュは既に実装済み

---

## CLAUDE.md 追記案

```markdown
### Parent Hierarchy Mode

条文の `parent` フィールドは以下の優先順位で直上階層を指す:

1. 節が存在 → `[[laws/{法令}/節/{章名}{節名}]]`
2. 章のみ存在 → `[[laws/{法令}/章/{章名}]]`
3. 章/節なし → `[[laws/{法令}/{法令}]]`（孤立条文）

**生成時オプション:**
```bash
# 階層的 parent（推奨）
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges --parent-mode hierarchical

# フラット parent（旧動作）
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges --parent-mode flat
```

**マイグレーション:**
```bash
# dry-run（変更確認）
python scripts/migration/update_article_parent.py --vault ./Vault --law 刑法 --dry-run

# 変更を適用（バックアップ付き）
python scripts/migration/update_article_parent.py --vault ./Vault --law 刑法 --apply --backup-dir /tmp/backup

# 全法令に適用
python scripts/migration/update_article_parent.py --vault ./Vault --apply --backup-dir /tmp/backup
```
```

---

## まず最初にやるべき1手

**Phase 1-1: `_build_frontmatter` の parent 計算ロジック変更**

理由:
1. 最も重要な変更（木構造の正本を作る）
2. 単独でテスト可能
3. 既存 Vault への影響を `--parent-mode` フラグで制御可能
4. Phase 2 の前提条件

具体的なアクション:
1. `tier1.py` に `_resolve_parent` メソッド追加
2. `_build_frontmatter` で parent 計算を条件分岐
3. テスト `test_tier1_parent.py` 作成
4. 刑法で動作確認

---

## 完了条件チェックリスト

- [x] Phase 0: `--parent-mode` フラグ動作（不要と判断、常に hierarchical）
- [x] Phase 1: 条文の parent が直上階層を指す（2026-01-28 完了）
- [ ] Phase 2: 章/節ノードの条文一覧が Dataview クエリ
- [x] Phase 3: 既存 Vault マイグレーション完了（2026-01-28 完了、3817件更新）
- [x] QA: `check_wikilinks.py` broken 0（2026-01-28 確認）
- [x] QA: pytest 154 tests PASS（2026-01-28 確認）
- [x] QA: リグレッションチェック PASS（2026-01-28 確認）
