"""
Test for Phase A-2: Chapter/Section Structure Node Generation
"""
import pytest
import yaml
from pathlib import Path
from legalkg.core.tier1 import (
    StructureAggregator,
    ChapterAgg,
    SectionAgg,
    Tier1Builder,
)


class TestStructureAggregator:
    """StructureAggregator のユニットテスト"""

    def test_add_article_to_chapter(self):
        """章への条文追加"""
        agg = StructureAggregator()
        context = {
            "chapter_num": 1,
            "chapter_title": "総則",
            "section_num": None,
            "section_title": None,
        }
        agg.add_article(context, "JPLAW:123#main#1", "1", "（趣旨）")

        assert 1 in agg.chapters
        chapter = agg.chapters[1]
        assert chapter.chapter_num == 1
        assert chapter.chapter_title == "総則"
        assert chapter.article_ids == ["JPLAW:123#main#1"]
        assert chapter.article_nums == ["1"]
        assert chapter.section_count == 0

    def test_add_article_to_section(self):
        """節への条文追加"""
        agg = StructureAggregator()
        context = {
            "chapter_num": 1,
            "chapter_title": "総則",
            "section_num": 2,
            "section_title": "通則",
        }
        agg.add_article(context, "JPLAW:123#main#5", "5", "（定義）")

        # 章にも追加される
        assert 1 in agg.chapters
        chapter = agg.chapters[1]
        assert chapter.section_count == 1
        assert 2 in chapter.section_nums

        # 節に追加される
        key = (1, 2)
        assert key in agg.sections
        section = agg.sections[key]
        assert section.chapter_num == 1
        assert section.section_num == 2
        assert section.section_title == "通則"
        assert section.article_ids == ["JPLAW:123#main#5"]
        assert section.article_nums == ["5"]

    def test_no_chapter_context(self):
        """章コンテキストなしの場合は集計されない"""
        agg = StructureAggregator()
        context = {
            "chapter_num": None,
            "chapter_title": None,
            "section_num": None,
            "section_title": None,
        }
        agg.add_article(context, "JPLAW:123#main#1", "1", "")

        assert len(agg.chapters) == 0
        assert len(agg.sections) == 0

    def test_multiple_articles_same_chapter(self):
        """同一章への複数条文追加"""
        agg = StructureAggregator()
        context = {"chapter_num": 1, "chapter_title": "総則", "section_num": None, "section_title": None}

        agg.add_article(context, "JPLAW:123#main#1", "1", "")
        agg.add_article(context, "JPLAW:123#main#2", "2", "")
        agg.add_article(context, "JPLAW:123#main#3", "3", "")

        chapter = agg.chapters[1]
        assert len(chapter.article_ids) == 3
        assert len(chapter.article_nums) == 3

    def test_article_heading_stored(self):
        """見出し情報が保存される"""
        agg = StructureAggregator()
        context = {"chapter_num": 1, "chapter_title": None, "section_num": None, "section_title": None}
        agg.add_article(context, "JPLAW:123#main#1", "1", "（趣旨）")

        assert agg.article_headings["1"] == "（趣旨）"


class TestChapterAgg:
    """ChapterAgg のテスト"""

    def test_section_count(self):
        """section_count プロパティ"""
        chapter = ChapterAgg(1, "総則")
        assert chapter.section_count == 0

        chapter.section_nums.add(1)
        assert chapter.section_count == 1

        chapter.section_nums.add(2)
        chapter.section_nums.add(3)
        assert chapter.section_count == 3


class TestTier1BuilderFormatArticleName:
    """_format_article_name のテスト"""

    @pytest.fixture
    def builder(self, tmp_path):
        targets_file = tmp_path / "targets.yaml"
        targets_file.write_text("targets: []")
        return Tier1Builder(tmp_path, targets_file)

    def test_simple_article(self, builder):
        assert builder._format_article_name("1") == "第1条"
        assert builder._format_article_name("199") == "第199条"

    def test_branch_article(self, builder):
        assert builder._format_article_name("1_2") == "第1条の2"
        assert builder._format_article_name("19_3") == "第19条の3"

    def test_complex_branch(self, builder):
        # 3段階以上の枝番
        assert builder._format_article_name("1_2_3") == "第1の2の3条"


class TestStructureNodeGeneration:
    """構造ノード生成の統合テスト"""

    def test_generate_structure_flag_off_no_directories(self, tmp_path):
        """--generate-structure OFF では章/節ディレクトリは作成されない"""
        # Minimal setup
        vault = tmp_path / "Vault"
        laws_dir = vault / "laws" / "テスト法"
        laws_dir.mkdir(parents=True)

        # Create minimal law file
        law_file = laws_dir / "テスト法.md"
        law_file.write_text("""---
id: JPLAW:999TEST
title: テスト法
tier: 0
---
""")

        targets_file = tmp_path / "targets.yaml"
        targets_file.write_text("targets: []")

        builder = Tier1Builder(vault, targets_file)

        # Manually call _generate_structure_nodes with empty aggregator
        agg = StructureAggregator()
        builder._generate_structure_nodes(laws_dir, "999TEST", "テスト法", agg)

        # 章ディレクトリは作成されない（aggregator が空のため）
        assert not (laws_dir / "章").exists()
        assert not (laws_dir / "節").exists()

    def test_chapter_node_content(self, tmp_path):
        """章ノードの内容確認"""
        vault = tmp_path / "Vault"
        laws_dir = vault / "laws" / "テスト法"
        (laws_dir / "本文").mkdir(parents=True)

        targets_file = tmp_path / "targets.yaml"
        targets_file.write_text("targets: []")

        builder = Tier1Builder(vault, targets_file)

        # 集計器にデータを追加
        agg = StructureAggregator()
        context = {"chapter_num": 1, "chapter_title": "総則", "section_num": None, "section_title": None}
        agg.add_article(context, "JPLAW:999#main#1", "1", "（趣旨）")
        agg.add_article(context, "JPLAW:999#main#2", "2", "（定義）")

        # 構造ノード生成
        builder._generate_structure_nodes(laws_dir, "999TEST", "テスト法", agg)

        # 章ファイルが作成される
        chapter_file = laws_dir / "章" / "第1章.md"
        assert chapter_file.exists()

        # frontmatter を確認
        content = chapter_file.read_text()
        assert "---" in content
        parts = content.split("---", 2)
        fm = yaml.safe_load(parts[1])

        assert fm["id"] == "JPLAW:999TEST#chapter#1"
        assert fm["type"] == "chapter"
        assert fm["chapter_num"] == 1
        assert fm["chapter_title"] == "総則"
        assert fm["article_ids"] == ["JPLAW:999#main#1", "JPLAW:999#main#2"]
        assert fm["article_nums"] == ["1", "2"]
        assert fm["section_count"] == 0
        assert "kind/chapter" in fm["tags"]

    def test_section_node_content(self, tmp_path):
        """節ノードの内容確認"""
        vault = tmp_path / "Vault"
        laws_dir = vault / "laws" / "テスト法"
        (laws_dir / "本文").mkdir(parents=True)

        targets_file = tmp_path / "targets.yaml"
        targets_file.write_text("targets: []")

        builder = Tier1Builder(vault, targets_file)

        # 集計器にデータを追加
        agg = StructureAggregator()
        context = {"chapter_num": 2, "chapter_title": "設立", "section_num": 1, "section_title": "通則"}
        agg.add_article(context, "JPLAW:999#main#10", "10", "")
        agg.add_article(context, "JPLAW:999#main#11", "11", "")

        # 構造ノード生成
        builder._generate_structure_nodes(laws_dir, "999TEST", "テスト法", agg)

        # 節ファイルが作成される
        section_file = laws_dir / "節" / "第2章第1節.md"
        assert section_file.exists()

        # frontmatter を確認
        content = section_file.read_text()
        parts = content.split("---", 2)
        fm = yaml.safe_load(parts[1])

        assert fm["id"] == "JPLAW:999TEST#chapter#2#section#1"
        assert fm["type"] == "section"
        assert fm["chapter_num"] == 2
        assert fm["section_num"] == 1
        assert fm["section_title"] == "通則"
        assert fm["article_ids"] == ["JPLAW:999#main#10", "JPLAW:999#main#11"]
        assert fm["article_nums"] == ["10", "11"]
        assert "kind/section" in fm["tags"]

        # parent は章への wikilink
        assert "章/第2章" in fm["parent"]

    def test_omission_principle_chapter_title(self, tmp_path):
        """省略主義: chapter_title が None なら出力しない"""
        vault = tmp_path / "Vault"
        laws_dir = vault / "laws" / "テスト法"
        (laws_dir / "本文").mkdir(parents=True)

        targets_file = tmp_path / "targets.yaml"
        targets_file.write_text("targets: []")

        builder = Tier1Builder(vault, targets_file)

        agg = StructureAggregator()
        context = {"chapter_num": 1, "chapter_title": None, "section_num": None, "section_title": None}
        agg.add_article(context, "JPLAW:999#main#1", "1", "")

        builder._generate_structure_nodes(laws_dir, "999TEST", "テスト法", agg)

        chapter_file = laws_dir / "章" / "第1章.md"
        content = chapter_file.read_text()
        parts = content.split("---", 2)
        fm = yaml.safe_load(parts[1])

        # chapter_title キーが存在しない
        assert "chapter_title" not in fm
