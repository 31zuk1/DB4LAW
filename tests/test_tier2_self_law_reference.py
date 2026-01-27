"""
Test for Phase 1: 本法/この法律/当該法 参照（内部参照）

優先順位: 法令番号付き参照 > 本法系 > 明示法令名 > 同法
"""
import pytest
from legalkg.core.tier2 import EdgeExtractor, has_self_law_prefix, SELF_LAW_PREFIXES_SORTED


class TestHasSelfLawPrefix:
    """has_self_law_prefix ヘルパー関数のテスト"""

    def test_honpo_direct(self):
        """本法 直接参照"""
        assert has_self_law_prefix("本法") is True
        assert has_self_law_prefix("...本法") is True
        assert has_self_law_prefix("条文は本法") is True

    def test_kono_houritsu_direct(self):
        """この法律 直接参照"""
        assert has_self_law_prefix("この法律") is True
        assert has_self_law_prefix("...この法律") is True

    def test_tougai_houritsu_direct(self):
        """当該法律 直接参照"""
        assert has_self_law_prefix("当該法律") is True
        assert has_self_law_prefix("当該法") is True

    def test_trailing_whitespace(self):
        """末尾空白があっても検出"""
        assert has_self_law_prefix("本法 ") is True
        assert has_self_law_prefix("この法律　") is True

    def test_not_self_law(self):
        """本法系でない場合は False"""
        assert has_self_law_prefix("刑法") is False
        assert has_self_law_prefix("民法") is False
        assert has_self_law_prefix("") is False
        assert has_self_law_prefix("法律") is False


class TestSelfLawPrefixesSorted:
    """SELF_LAW_PREFIXES_SORTED が長い順にソートされていることを確認"""

    def test_sorted_by_length_descending(self):
        lengths = [len(p) for p in SELF_LAW_PREFIXES_SORTED]
        assert lengths == sorted(lengths, reverse=True)

    def test_tougai_houritsu_before_tougai_hou(self):
        """当該法律 が 当該法 より先に来る"""
        idx_houritsu = SELF_LAW_PREFIXES_SORTED.index('当該法律')
        idx_hou = SELF_LAW_PREFIXES_SORTED.index('当該法')
        assert idx_houritsu < idx_hou


class TestSelfLawReferenceBasic:
    """本法参照の基本テスト"""

    @pytest.fixture
    def extractor(self):
        return EdgeExtractor()

    def test_honpo_single(self, extractor):
        """本法第N条 単独参照"""
        text = "本法第十条の規定による"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/テスト法/本文/第10条.md|第十条]]" in result

    def test_kono_houritsu_single(self, extractor):
        """この法律第N条 単独参照"""
        text = "この法律第五条に定める"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/テスト法/本文/第5条.md|第五条]]" in result

    def test_tougai_houritsu_single(self, extractor):
        """当該法律第N条 単独参照"""
        text = "当該法律第三条の規定"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/テスト法/本文/第3条.md|第三条]]" in result

    def test_tougai_hou_single(self, extractor):
        """当該法第N条 単独参照"""
        text = "当該法第七条を適用する"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/テスト法/本文/第7条.md|第七条]]" in result

    def test_honpo_with_branch_number(self, extractor):
        """本法第N条のM 枝番号付き参照"""
        text = "本法第十九条の二に規定する"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/テスト法/本文/第19条の2.md|第十九条の二]]" in result


class TestSelfLawEnumeration:
    """本法列挙のテスト（「第」付き列挙のみ）"""

    @pytest.fixture
    def extractor(self):
        return EdgeExtractor()

    def test_honpo_enumeration_two(self, extractor):
        """本法第X条、第Y条 二項目列挙"""
        text = "本法第十条、第二十条の規定"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/テスト法/本文/第10条.md|第十条]]" in result
        assert "[[laws/テスト法/本文/第20条.md|第二十条]]" in result

    def test_honpo_enumeration_three(self, extractor):
        """本法第X条、第Y条、第Z条 三項目列挙"""
        text = "本法第一条、第二条、第三条に定める"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/テスト法/本文/第1条.md|第一条]]" in result
        assert "[[laws/テスト法/本文/第2条.md|第二条]]" in result
        assert "[[laws/テスト法/本文/第3条.md|第三条]]" in result

    def test_honpo_enumeration_with_branch(self, extractor):
        """本法第X条、第Y条、第Z条の二 枝番号を含む列挙"""
        text = "本法第十条、第二十条、第二十一条の二を準用する"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/テスト法/本文/第10条.md|第十条]]" in result
        assert "[[laws/テスト法/本文/第20条.md|第二十条]]" in result
        assert "[[laws/テスト法/本文/第21条の2.md|第二十一条の二]]" in result

    def test_kono_houritsu_enumeration(self, extractor):
        """この法律第X条、第Y条 列挙"""
        text = "この法律第五条、第六条、第七条の二を適用"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/テスト法/本文/第5条.md|第五条]]" in result
        assert "[[laws/テスト法/本文/第6条.md|第六条]]" in result
        assert "[[laws/テスト法/本文/第7条の2.md|第七条の二]]" in result


class TestSelfLawReferenceWithEdges:
    """本法参照のエッジ生成テスト"""

    @pytest.fixture
    def extractor(self, tmp_path):
        # テスト用の最小限の Vault を作成
        vault = tmp_path / "Vault"
        laws_dir = vault / "laws" / "テスト法"
        laws_dir.mkdir(parents=True)
        law_file = laws_dir / "テスト法.md"
        law_file.write_text("""---
id: JPLAW:TEST001
title: テスト法
---
""")
        return EdgeExtractor(vault_root=vault)

    def test_honpo_generates_internal_edge(self, extractor):
        """本法参照が内部 refs エッジを生成"""
        text = "本法第十条の規定"
        replaced, edges = extractor.replace_refs_with_edges(
            text=text,
            law_name="テスト法",
            source_law_id="TEST001",
            source_node_id="JPLAW:TEST001#main#1"
        )

        assert len(edges) == 1
        edge = edges[0]
        assert edge["from"] == "JPLAW:TEST001#main#1"
        assert edge["to"] == "JPLAW:TEST001#main#10"
        assert edge["type"] == "refers_to"

    def test_honpo_enumeration_generates_multiple_edges(self, extractor):
        """本法列挙が複数の内部 refs エッジを生成"""
        text = "本法第一条、第二条、第三条に定める"
        replaced, edges = extractor.replace_refs_with_edges(
            text=text,
            law_name="テスト法",
            source_law_id="TEST001",
            source_node_id="JPLAW:TEST001#main#99"
        )

        assert len(edges) == 3
        targets = {e["to"] for e in edges}
        assert "JPLAW:TEST001#main#1" in targets
        assert "JPLAW:TEST001#main#2" in targets
        assert "JPLAW:TEST001#main#3" in targets


class TestSelfLawDoesNotInterfereWithOtherPatterns:
    """本法参照が他のパターンに干渉しないことを確認"""

    @pytest.fixture
    def extractor(self):
        return EdgeExtractor()

    def test_explicit_law_name_still_works(self, extractor):
        """明示的な法令名参照は通常通り処理"""
        text = "刑法第百九十九条の規定"
        result = extractor.replace_refs(text, "テスト法")
        # 刑法への参照（CROSS_LINKABLE_LAWS に含まれる）
        assert "[[laws/刑法/本文/第199条.md|第百九十九条]]" in result

    def test_external_law_still_blocked(self, extractor):
        """外部法令参照は引き続きブロック"""
        text = "商法第五百条の規定"
        result = extractor.replace_refs(text, "テスト法")
        # 商法は EXTERNAL_LAW_PATTERNS に含まれる → リンク化しない
        assert "[[" not in result
        assert "第五百条" in result

    def test_bare_reference_in_amendment_still_blocked(self, extractor):
        """改正法断片内の裸参照は引き続きブロック（本法プレフィックスがない場合）"""
        text = "第十条の規定による"
        result = extractor.replace_refs(text, "テスト法", is_amendment_fragment=True)
        # 裸の参照 + is_amendment_fragment → リンク化しない
        assert "[[" not in result

    def test_honpo_in_amendment_still_linked(self, extractor):
        """改正法断片内でも本法参照はリンク化"""
        text = "本法第十条の規定による"
        result = extractor.replace_refs(text, "テスト法", is_amendment_fragment=True)
        # 本法プレフィックスあり → リンク化する
        assert "[[laws/テスト法/本文/第10条.md|第十条]]" in result
