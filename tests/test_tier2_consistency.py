#!/usr/bin/env python3
"""
tier2.py SSOT (Single Source of Truth) 一貫性テスト

テスト目的:
- replace_refs と extract_refs（edges.jsonl生成）の一貫性を検証
- WikiLink生成とエッジ抽出が同一の参照解釈に基づくことを保証

テスト項目:
1. External law ignore の一貫性
2. Cross-link の一貫性
3. スコープ連続（法令名＋第N条、第M条パターン）
4. replace_refs 互換性（既存動作が変わらないこと）
5. 同法によるスコープリセット

論点メモ:
- SCOPE_RESET_PATTERNS に '同法' が含まれている
- 「刑法第5条、同法第6条」→ 同法で刑法スコープがリセットされ、
  第6条は親法デフォルトに戻る（現状実装）
- この挙動が正しいかは議論の余地があるが、テストで現状を固定する
"""

import sys
from pathlib import Path
import tempfile
import pytest

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from legalkg.core.tier2 import (
    EdgeExtractor,
    set_vault_root,
    clear_law_id_cache,
    resolve_law_id_from_vault,
)


@pytest.fixture
def extractor():
    """EdgeExtractor インスタンスを提供"""
    return EdgeExtractor()


@pytest.fixture
def vault_fixture(tmp_path):
    """
    テスト用の最小 Vault を作成

    構造:
    - laws/刑法/刑法.md (egov_law_id: 140AC0000000045)
    - laws/民法/民法.md (egov_law_id: 129AC0000000089)
    """
    laws_dir = tmp_path / "laws"

    # 刑法
    keiho_dir = laws_dir / "刑法"
    keiho_dir.mkdir(parents=True)
    keiho_md = keiho_dir / "刑法.md"
    keiho_md.write_text("""---
egov_law_id: '140AC0000000045'
id: JPLAW:140AC0000000045
title: 刑法
---
# 刑法
""", encoding='utf-8')

    # 民法
    minpo_dir = laws_dir / "民法"
    minpo_dir.mkdir(parents=True)
    minpo_md = minpo_dir / "民法.md"
    minpo_md.write_text("""---
egov_law_id: '129AC0000000089'
id: JPLAW:129AC0000000089
title: 民法
---
# 民法
""", encoding='utf-8')

    # キャッシュをクリアしてから Vault root を設定
    clear_law_id_cache()
    set_vault_root(tmp_path)

    yield tmp_path

    # クリーンアップ
    clear_law_id_cache()


class TestExternalLawIgnore:
    """外部法令参照の無視（リンク化もエッジ化もしない）"""

    def test_external_law_not_linked_and_no_edge(self, extractor):
        """
        外部法令（民事執行法など）への参照はリンク化せず、エッジも生成しない

        入力: 「民事執行法第二十条」（現在法: 民法）
        期待:
        - replace_refs: リンク化しない
        - edges: 0件
        """
        text = "民事執行法第二十条の規定により、"
        law_name = "民法"
        source_law_id = "129AC0000000089"
        source_node_id = "JPLAW:129AC0000000089#main#10"

        replaced, edges = extractor.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_node_id,
            is_amendment_fragment=False
        )

        # リンク化されていない
        assert "[[" not in replaced
        assert replaced == text

        # エッジも0件
        assert len(edges) == 0

    def test_external_law_scope_continuation(self, extractor):
        """
        外部法令スコープ内の連続参照もエッジ化しない

        入力: 「土地収用法第八十四条、第八十五条」（現在法: 民法）
        期待:
        - 両方ともリンク化しない
        - edges: 0件
        """
        text = "土地収用法第八十四条、第八十五条の規定を準用する。"
        law_name = "民法"
        source_law_id = "129AC0000000089"
        source_node_id = "JPLAW:129AC0000000089#main#10"

        replaced, edges = extractor.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_node_id,
            is_amendment_fragment=False
        )

        # リンク化されていない
        assert "[[" not in replaced

        # エッジも0件
        assert len(edges) == 0


class TestCrossLinkConsistency:
    """クロスリンク（他法令への参照）の一貫性"""

    def test_crosslink_to_keiho(self, extractor, vault_fixture):
        """
        他法令（刑法）への参照がWikiLinkとエッジの両方で正しくターゲットを指す

        入力: 「刑法第百九十九条」（現在法: 民法）
        期待:
        - replace_refs: laws/刑法/本文/第199条.md へのリンク
        - edges: target は 刑法の law_id（140AC0000000045）を使用
        """
        extractor_with_vault = EdgeExtractor(vault_root=vault_fixture)

        text = "刑法第百九十九条の規定は、"
        law_name = "民法"
        source_law_id = "129AC0000000089"
        source_node_id = "JPLAW:129AC0000000089#main#10"

        replaced, edges = extractor_with_vault.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_node_id,
            is_amendment_fragment=False
        )

        # 刑法へのWikiLinkが生成されている
        assert "[[laws/刑法/本文/第199条.md|第百九十九条]]" in replaced

        # エッジも刑法の law_id を使用
        assert len(edges) == 1
        assert edges[0]["to"] == "JPLAW:140AC0000000045#main#199"
        assert edges[0]["from"] == source_node_id

    def test_crosslink_without_vault_no_edge(self):
        """
        Vault が設定されていない場合、クロスリンクのWikiLinkは生成するが
        エッジは生成しない（law_id が解決できないため）

        入力: 「刑法第百九十九条」（現在法: 民法、Vault なし）
        期待:
        - replace_refs: laws/刑法/本文/第199条.md へのリンク（生成する）
        - edges: 0件（law_id 解決不可）
        """
        # グローバルキャッシュをクリアしてテスト
        clear_law_id_cache()
        set_vault_root(None)

        # Vault root を設定しない extractor
        extractor_no_vault = EdgeExtractor(vault_root=None)

        text = "刑法第百九十九条の規定は、"
        law_name = "民法"
        source_law_id = "129AC0000000089"
        source_node_id = "JPLAW:129AC0000000089#main#10"

        replaced, edges = extractor_no_vault.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_node_id,
            is_amendment_fragment=False
        )

        # WikiLinkは生成される
        assert "[[laws/刑法/本文/第199条.md|第百九十九条]]" in replaced

        # エッジは生成されない（law_id 解決不可）
        assert len(edges) == 0


class TestScopeContinuation:
    """スコープ連続（「法令名＋第N条、第M条」パターン）"""

    def test_crosslink_scope_continuation(self, extractor, vault_fixture):
        """
        クロスリンクスコープ内の連続参照が同じ法令を指す

        入力: 「刑法第百九十九条及び第二百条」（現在法: 民法）
        期待:
        - 両方とも刑法へのリンク
        - edges も両方とも刑法の law_id を使用
        """
        extractor_with_vault = EdgeExtractor(vault_root=vault_fixture)

        text = "刑法第百九十九条及び第二百条の規定は、"
        law_name = "民法"
        source_law_id = "129AC0000000089"
        source_node_id = "JPLAW:129AC0000000089#main#10"

        replaced, edges = extractor_with_vault.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_node_id,
            is_amendment_fragment=False
        )

        # 両方とも刑法へリンク
        assert "[[laws/刑法/本文/第199条.md|第百九十九条]]" in replaced
        assert "[[laws/刑法/本文/第200条.md|第二百条]]" in replaced

        # エッジも両方とも刑法
        assert len(edges) == 2
        assert edges[0]["to"] == "JPLAW:140AC0000000045#main#199"
        assert edges[1]["to"] == "JPLAW:140AC0000000045#main#200"


class TestScopeReset:
    """
    スコープリセット（同法による処理）

    論点:
    - EXTERNAL_LAW_PATTERNS に '同法' が含まれている
    - 「刑法第5条及び同法第6条」の場合：
      - 「第五条」は刑法へリンク
      - 「同法第六条」は外部法令参照として扱われ、リンク化されない

    現状実装の理由:
    - 「同法」は指示代名詞であり、参照先を機械的に解決できない
    - 安全側に倒して、外部法令参照として扱う（リンク化しない）

    将来の改善案:
    - 直前の法令名を追跡して「同法」を解決する
    - ただしこれは複雑なロジックになるため、現時点では見送り

    現時点では現状実装をテストで固定し、将来の仕様変更時にテストを更新する。
    """

    def test_douhou_not_linked(self, extractor, vault_fixture):
        """
        「同法」は外部法令として扱われ、リンク化されない（現状仕様）

        入力: 「刑法第五条及び同法第六条」（現在法: 民法）
        現状期待:
        - 第五条: 刑法へリンク
        - 第六条: 「同法」は EXTERNAL_LAW_PATTERNS にあるため、リンク化されない

        将来仕様変更時はこのテストの期待値を更新すること。
        """
        extractor_with_vault = EdgeExtractor(vault_root=vault_fixture)

        text = "刑法第五条及び同法第六条の規定は、"
        law_name = "民法"
        source_law_id = "129AC0000000089"
        source_node_id = "JPLAW:129AC0000000089#main#10"

        replaced, edges = extractor_with_vault.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_node_id,
            is_amendment_fragment=False
        )

        # 第五条は刑法へ
        assert "[[laws/刑法/本文/第5条.md|第五条]]" in replaced

        # 第六条は「同法」直後のため、リンク化されない
        # 注: 「同法」は EXTERNAL_LAW_PATTERNS に含まれる
        assert "同法第六条" in replaced  # リンク化されずにそのまま残る
        assert "[[" not in replaced.split("同法")[1]  # 同法以降にはリンクがない

        # エッジは1件のみ（第五条のみ）
        assert len(edges) == 1
        assert edges[0]["to"] == "JPLAW:140AC0000000045#main#5"


class TestReplaceRefsCompatibility:
    """replace_refs 互換性（既存動作が変わらないこと）"""

    def test_internal_reference(self, extractor):
        """
        自法令への内部参照が正しくリンク化される

        入力: 「第七条」（現在法: 民法）
        期待: laws/民法/本文/第7条.md へのリンク
        """
        text = "前条の規定は、第七条に準用する。"
        law_name = "民法"

        replaced = extractor.replace_refs(text, law_name)

        assert "[[laws/民法/本文/第7条.md|第七条]]" in replaced

    def test_internal_reference_with_sub_number(self, extractor):
        """
        枝番号付き条文参照の処理

        日本語法令では「第十九条の二」のように、条番号の後に枝番が続く形式。
        regex パターン: 第(N)条(?:の(M))? で最大一致を保証。

        入力: 「第十九条の二の規定により、」（現在法: 民法）
        期待: 「第十九条の二」が完全にリンク化される
        """
        text = "第十九条の二の規定により、"
        law_name = "民法"

        replaced = extractor.replace_refs(text, law_name)

        # 「第十九条の二」が完全にマッチし、第19条の2.md にリンク
        assert "[[laws/民法/本文/第19条の2.md|第十九条の二]]" in replaced
        assert "の規定により" in replaced

    def test_replace_refs_same_as_replace_refs_with_edges(self, extractor):
        """
        replace_refs と replace_refs_with_edges の置換結果が同一
        """
        text = "第一条及び第二条の規定は、刑法第百九十九条に準用する。"
        law_name = "民法"

        # replace_refs
        replaced1 = extractor.replace_refs(text, law_name)

        # replace_refs_with_edges
        replaced2, _ = extractor.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id="129AC0000000089",
            source_node_id="JPLAW:129AC0000000089#main#10",
            is_amendment_fragment=False
        )

        assert replaced1 == replaced2


class TestAmendmentFragment:
    """改正法断片モード（裸の第N条をリンク化しない）"""

    def test_bare_reference_not_linked_in_amendment(self, extractor):
        """
        改正法断片内の裸の参照（法令名なし）はリンク化しない

        入力: 「第十条」（改正法断片内）
        期待:
        - リンク化しない
        - エッジも生成しない
        """
        text = "第十条を次のように改める。"
        law_name = "民法"
        source_law_id = "129AC0000000089"
        source_node_id = "JPLAW:129AC0000000089#suppl#1"

        replaced, edges = extractor.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_node_id,
            is_amendment_fragment=True
        )

        # リンク化されていない
        assert "[[" not in replaced

        # エッジも0件
        assert len(edges) == 0

    def test_explicit_law_name_linked_in_amendment(self, extractor, vault_fixture):
        """
        改正法断片内でも法令名が明示されていればリンク化する

        入力: 「民法第十条」（改正法断片内）
        期待:
        - リンク化する
        - エッジも生成する
        """
        extractor_with_vault = EdgeExtractor(vault_root=vault_fixture)

        text = "民法第十条を次のように改める。"
        law_name = "民法"
        source_law_id = "129AC0000000089"
        source_node_id = "JPLAW:129AC0000000089#suppl#1"

        replaced, edges = extractor_with_vault.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_node_id,
            is_amendment_fragment=True
        )

        # リンク化されている
        assert "[[laws/民法/本文/第10条.md|第十条]]" in replaced

        # エッジも生成されている
        assert len(edges) == 1
        assert edges[0]["to"] == "JPLAW:129AC0000000089#main#10"


class TestEdgeSchema:
    """エッジスキーマの検証"""

    def test_edge_schema(self, extractor, vault_fixture):
        """
        エッジが正しいスキーマで生成される

        注: 「第N条の規定により」パターンはリンク化されないため、
        別のテキストを使用
        """
        extractor_with_vault = EdgeExtractor(vault_root=vault_fixture)

        # 「の規定により」パターンではない参照を使用
        text = "第七条に準用する。"
        law_name = "民法"
        source_law_id = "129AC0000000089"
        source_node_id = "JPLAW:129AC0000000089#main#10"

        _, edges = extractor_with_vault.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_node_id,
            is_amendment_fragment=False
        )

        assert len(edges) == 1
        edge = edges[0]

        # 必須フィールド
        assert "from" in edge
        assert "to" in edge
        assert "type" in edge
        assert "evidence" in edge
        assert "confidence" in edge
        assert "source" in edge

        # 値の検証
        assert edge["from"] == source_node_id
        assert edge["to"] == "JPLAW:129AC0000000089#main#7"
        assert edge["type"] == "refers_to"
        assert edge["evidence"] == "第七条"
        assert edge["confidence"] == 0.9
        assert edge["source"] == "regex_v2"  # SSOT版


class TestLawIdResolver:
    """law_id 解決機能のテスト"""

    def test_resolve_keiho(self, vault_fixture):
        """刑法の law_id が解決できる"""
        law_id = resolve_law_id_from_vault("刑法", vault_fixture)
        assert law_id == "140AC0000000045"

    def test_resolve_minpo(self, vault_fixture):
        """民法の law_id が解決できる"""
        law_id = resolve_law_id_from_vault("民法", vault_fixture)
        assert law_id == "129AC0000000089"

    def test_resolve_unknown_returns_none(self, vault_fixture):
        """存在しない法令は None を返す"""
        law_id = resolve_law_id_from_vault("存在しない法", vault_fixture)
        assert law_id is None

    def test_cache_works(self, vault_fixture):
        """キャッシュが動作する"""
        # 1回目
        law_id1 = resolve_law_id_from_vault("刑法", vault_fixture)

        # 2回目（キャッシュから）
        law_id2 = resolve_law_id_from_vault("刑法", vault_fixture)

        assert law_id1 == law_id2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
