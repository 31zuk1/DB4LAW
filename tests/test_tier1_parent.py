"""
Test for parent hierarchy in Tier1 article generation.

木構造の正本として、条文の parent は直上階層を指す:
1. 節が存在 → [[laws/{法令}/節/{章名}{節名}]]
2. 章のみ存在 → [[laws/{法令}/章/{章名}]]
3. 章/節なし → [[laws/{法令}/{法令}]]（孤立条文）
"""
import pytest
from legalkg.core.tier1 import Tier1Builder


class TestResolveParent:
    """_resolve_parent メソッドのテスト"""

    @pytest.fixture
    def builder(self, tmp_path):
        targets_file = tmp_path / "targets.yaml"
        targets_file.write_text("targets: []")
        return Tier1Builder(vault_root=tmp_path, targets_path=targets_file)

    def test_article_with_section_parent_is_section(self, builder):
        """節がある条文の parent は節を指す"""
        context = {
            "chapter_num": 1,
            "chapter_title": "第一章　設立",
            "section_num": 6,
            "section_title": "第六款　定款の変更",
        }
        parent = builder._resolve_parent("会社法", context, "main")
        assert parent == "[[laws/会社法/節/第1章第6節]]"

    def test_article_with_chapter_only_parent_is_chapter(self, builder):
        """節がない条文の parent は章を指す"""
        context = {
            "chapter_num": 26,
            "chapter_title": "第二十六章　殺人の罪",
            "section_num": None,
            "section_title": None,
        }
        parent = builder._resolve_parent("刑法", context, "main")
        assert parent == "[[laws/刑法/章/第26章]]"

    def test_article_without_structure_parent_is_law(self, builder):
        """章/節がない条文の parent は法令を指す"""
        context = None
        parent = builder._resolve_parent("テスト法", context, "main")
        assert parent == "[[laws/テスト法/テスト法]]"

    def test_article_with_empty_context_parent_is_law(self, builder):
        """空の context でも法令を指す"""
        context = {}
        parent = builder._resolve_parent("テスト法", context, "main")
        assert parent == "[[laws/テスト法/テスト法]]"

    def test_supplement_parent_is_always_law(self, builder):
        """附則の parent は常に法令を指す（階層構造がないため）"""
        context = {
            "chapter_num": 1,
            "chapter_title": "第一章",
            "section_num": 1,
            "section_title": "第一節",
        }
        parent = builder._resolve_parent("刑法", context, "suppl")
        assert parent == "[[laws/刑法/刑法]]"

    def test_parent_with_no_law_name_returns_none(self, builder):
        """law_name が空の場合は None を返す"""
        context = {"chapter_num": 1}
        parent = builder._resolve_parent("", context, "main")
        assert parent is None

        parent = builder._resolve_parent(None, context, "main")
        assert parent is None

    def test_chapter_with_branch_number(self, builder):
        """枝番号付き章（第2章の2）の parent パス"""
        context = {
            "chapter_num": 22,  # e-Gov encoding for 第2章の2
            "chapter_title": "第二章の二　社債管理補助者",
            "section_num": None,
        }
        parent = builder._resolve_parent("会社法", context, "main")
        assert parent == "[[laws/会社法/章/第2章の2]]"

    def test_section_with_branch_number(self, builder):
        """枝番号付き節の parent パス"""
        context = {
            "chapter_num": 1,
            "chapter_title": "第一章",
            "section_num": 12,  # e-Gov encoding for 第1節の2
            "section_title": "第一節の二",
        }
        parent = builder._resolve_parent("テスト法", context, "main")
        assert parent == "[[laws/テスト法/節/第1章第1節の2]]"


class TestBuildFrontmatterParent:
    """_build_frontmatter での parent 設定テスト"""

    @pytest.fixture
    def builder(self, tmp_path):
        targets_file = tmp_path / "targets.yaml"
        targets_file.write_text("targets: []")
        return Tier1Builder(vault_root=tmp_path, targets_path=targets_file)

    def test_main_article_with_chapter_has_chapter_parent(self, builder):
        """本則条文で章がある場合は章を parent に"""
        context = {
            "chapter_num": 26,
            "chapter_title": "第二十六章　殺人の罪",
        }
        fm = builder._build_frontmatter(
            node_id="JPLAW:140AC0000000045#main#199",
            part_type="main",
            law_id="140AC0000000045",
            law_name="刑法",
            article_num="199",
            heading="（殺人）",
            is_amendment_fragment=False,
            amend_law_num=None,
            context=context,
        )
        assert fm["parent"] == "[[laws/刑法/章/第26章]]"

    def test_main_article_with_section_has_section_parent(self, builder):
        """本則条文で節がある場合は節を parent に"""
        context = {
            "chapter_num": 1,
            "chapter_title": "第一章　設立",
            "section_num": 1,
            "section_title": "第一節　総則",
        }
        fm = builder._build_frontmatter(
            node_id="JPLAW:417AC0000000086#main#25",
            part_type="main",
            law_id="417AC0000000086",
            law_name="会社法",
            article_num="25",
            heading="",
            is_amendment_fragment=False,
            amend_law_num=None,
            context=context,
        )
        assert fm["parent"] == "[[laws/会社法/節/第1章第1節]]"

    def test_supplement_has_law_parent(self, builder):
        """附則条文は法令を parent に"""
        context = {"chapter_num": 1}
        fm = builder._build_frontmatter(
            node_id="JPLAW:140AC0000000045#suppl#1",
            part_type="suppl",
            law_id="140AC0000000045",
            law_name="刑法",
            article_num="1",
            heading="",
            is_amendment_fragment=False,
            amend_law_num=None,
            context=context,
        )
        assert fm["parent"] == "[[laws/刑法/刑法]]"

    def test_amendment_fragment_has_law_parent(self, builder):
        """改正法断片は法令を parent に"""
        context = {"chapter_num": 1}
        fm = builder._build_frontmatter(
            node_id="JPLAW:140AC0000000045#suppl#1",
            part_type="suppl",
            law_id="140AC0000000045",
            law_name="刑法",
            article_num="1",
            heading="",
            is_amendment_fragment=True,
            amend_law_num="令和五年法律第二八号",
            context=context,
        )
        assert fm["parent"] == "[[laws/刑法/刑法]]"

    def test_parent_is_always_string_not_list(self, builder):
        """parent は常に文字列（リストではない）"""
        context = {"chapter_num": 1, "section_num": 1}
        fm = builder._build_frontmatter(
            node_id="test",
            part_type="main",
            law_id="test",
            law_name="テスト法",
            article_num="1",
            heading="",
            is_amendment_fragment=False,
            amend_law_num=None,
            context=context,
        )
        assert isinstance(fm["parent"], str)
        assert not isinstance(fm["parent"], list)


class TestChapterSectionParent:
    """章/節ノードの parent テスト（既存動作の確認）"""

    def test_chapter_parent_is_law(self):
        """章ノードの parent は法令（tier1.py 行927で設定）"""
        # これは既存の動作を確認するテスト
        # 章ノード生成時に parent = [[laws/{law_name}/{law_name}]] となることを確認
        pass  # 実際のファイル生成テストは統合テストで実施

    def test_section_parent_is_chapter(self):
        """節ノードの parent は章（tier1.py 行995で設定）"""
        # これは既存の動作を確認するテスト
        # 節ノード生成時に parent = [[laws/{law_name}/章/{chapter_name}]] となることを確認
        pass  # 実際のファイル生成テストは統合テストで実施
