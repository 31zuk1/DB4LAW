"""
Tests for edge_schema.py - EdgeSchema v1/v2 conversion and containment edges
"""
import pytest
from legalkg.core.edge_schema import (
    EdgeSchema,
    edge_to_v1,
    edge_to_v2,
    create_chapter_containment_edge,
    create_section_containment_edge,
    EdgeWriter,
    generate_containment_edges_from_aggregator,
)
from legalkg.core.tier1 import StructureAggregator


class TestEdgeToV1:
    """v1 変換は入力をそのまま返す"""

    def test_refs_edge_unchanged(self):
        edge = {
            "from": "JPLAW:140AC0000000045#main#1",
            "to": "JPLAW:140AC0000000045#main#2",
            "type": "refers_to",
            "evidence": "第二条",
            "confidence": 0.9,
            "source": "regex_v2",
        }
        result = edge_to_v1(edge)
        assert result == edge

    def test_external_edge_unchanged(self):
        edge = {
            "from": "JPLAW:140AC0000000045#main#1",
            "to": "JPLAW:EXTERNAL_刑法#article#199",
            "type": "refers_to",
            "evidence": "刑法第百九十九条",
            "confidence": 0.8,
            "kind": "external_ref",
            "source": "regex_v2",
        }
        result = edge_to_v1(edge)
        assert result == edge


class TestEdgeToV2:
    """v1 refs -> v2 変換"""

    def test_internal_refs_converted(self):
        edge = {
            "from": "JPLAW:140AC0000000045#main#1",
            "to": "JPLAW:140AC0000000045#main#2",
            "type": "refers_to",
            "evidence": "第二条",
            "confidence": 0.9,
            "source": "regex_v2",
        }
        result = edge_to_v2(edge)
        assert result["source"] == "JPLAW:140AC0000000045#main#1"
        assert result["target"] == "JPLAW:140AC0000000045#main#2"
        assert result["type"] == "refs"
        assert result["relation"] == "internal"
        assert result["evidence"] == "第二条"
        assert result["confidence"] == 0.9

    def test_external_refs_converted(self):
        edge = {
            "from": "JPLAW:140AC0000000045#main#1",
            "to": "JPLAW:EXTERNAL_刑法#article#199",
            "type": "refers_to",
            "evidence": "刑法第百九十九条",
            "confidence": 0.8,
            "kind": "external_ref",
            "source": "regex_v2",
        }
        result = edge_to_v2(edge)
        assert result["source"] == "JPLAW:140AC0000000045#main#1"
        assert result["target"] == "JPLAW:EXTERNAL_刑法#article#199"
        assert result["type"] == "refs"
        assert result["relation"] == "external"
        assert result["evidence"] == "刑法第百九十九条"

    def test_containment_edge_passthrough(self):
        """既に v2 形式（containment edge）はそのまま返す"""
        edge = {
            "source": "JPLAW:140AC0000000045#chapter#1",
            "target": "JPLAW:140AC0000000045#main#1",
            "type": "contains",
            "relation": "chapter_contains_article",
        }
        result = edge_to_v2(edge)
        assert result == edge


class TestContainmentEdgeCreation:
    """包含エッジ生成"""

    def test_chapter_containment_edge(self):
        edge = create_chapter_containment_edge(
            "JPLAW:140AC0000000045#chapter#1",
            "JPLAW:140AC0000000045#main#1"
        )
        assert edge["source"] == "JPLAW:140AC0000000045#chapter#1"
        assert edge["target"] == "JPLAW:140AC0000000045#main#1"
        assert edge["type"] == "contains"
        assert edge["relation"] == "chapter_contains_article"

    def test_section_containment_edge(self):
        edge = create_section_containment_edge(
            "JPLAW:140AC0000000045#chapter#1#section#1",
            "JPLAW:140AC0000000045#main#1"
        )
        assert edge["source"] == "JPLAW:140AC0000000045#chapter#1#section#1"
        assert edge["target"] == "JPLAW:140AC0000000045#main#1"
        assert edge["type"] == "contains"
        assert edge["relation"] == "section_contains_article"


class TestEdgeWriter:
    """EdgeWriter のスキーマ変換"""

    def test_v1_writer_returns_original(self):
        writer = EdgeWriter(EdgeSchema.V1)
        edge = {
            "from": "JPLAW:140AC0000000045#main#1",
            "to": "JPLAW:140AC0000000045#main#2",
            "type": "refers_to",
        }
        result = writer.convert(edge)
        assert result == edge

    def test_v2_writer_converts_refs(self):
        writer = EdgeWriter(EdgeSchema.V2)
        edge = {
            "from": "JPLAW:140AC0000000045#main#1",
            "to": "JPLAW:140AC0000000045#main#2",
            "type": "refers_to",
        }
        result = writer.convert(edge)
        assert "source" in result
        assert "target" in result
        assert result["type"] == "refs"

    def test_v2_writer_passthrough_containment(self):
        writer = EdgeWriter(EdgeSchema.V2)
        edge = {
            "source": "JPLAW:140AC0000000045#chapter#1",
            "target": "JPLAW:140AC0000000045#main#1",
            "type": "contains",
            "relation": "chapter_contains_article",
        }
        result = writer.convert(edge)
        assert result == edge


class TestGenerateContainmentEdgesFromAggregator:
    """StructureAggregator から包含エッジを生成"""

    def test_chapter_containment_edges(self):
        aggregator = StructureAggregator()
        context = {
            "chapter_num": 1,
            "chapter_title": "第一章 総則",
            "section_num": None,
            "section_title": None,
        }
        aggregator.add_article(context, "JPLAW:140AC0000000045#main#1", "1", "目的")
        aggregator.add_article(context, "JPLAW:140AC0000000045#main#2", "2", "定義")

        edges = generate_containment_edges_from_aggregator(aggregator, "140AC0000000045")

        assert len(edges) == 2
        assert edges[0]["source"] == "JPLAW:140AC0000000045#chapter#1"
        assert edges[0]["target"] == "JPLAW:140AC0000000045#main#1"
        assert edges[0]["type"] == "contains"
        assert edges[1]["target"] == "JPLAW:140AC0000000045#main#2"

    def test_section_containment_edges(self):
        aggregator = StructureAggregator()
        context = {
            "chapter_num": 1,
            "chapter_title": "第一章 総則",
            "section_num": 1,
            "section_title": "第一節 通則",
        }
        aggregator.add_article(context, "JPLAW:140AC0000000045#main#1", "1", "目的")

        edges = generate_containment_edges_from_aggregator(aggregator, "140AC0000000045")

        # 章と節の両方の包含エッジが生成される
        chapter_edges = [e for e in edges if e["relation"] == "chapter_contains_article"]
        section_edges = [e for e in edges if e["relation"] == "section_contains_article"]

        assert len(chapter_edges) == 1
        assert len(section_edges) == 1
        assert section_edges[0]["source"] == "JPLAW:140AC0000000045#chapter#1#section#1"

    def test_empty_aggregator(self):
        aggregator = StructureAggregator()
        edges = generate_containment_edges_from_aggregator(aggregator, "140AC0000000045")
        assert edges == []


class TestContainmentEdgeUniqueness:
    """
    包含エッジの重複防止仕様テスト

    仕様:
    - chapter_contains_article は (chapter_id, article_id) で一意
    - section_contains_article は (section_id, article_id) で一意
    - 同一 run 内で重複 edge を出力しない
    """

    def test_no_duplicate_chapter_edges(self):
        """同一章に同一条文が2回追加されても章エッジは1つだけ"""
        aggregator = StructureAggregator()
        context = {
            "chapter_num": 1,
            "chapter_title": "第一章",
            "section_num": None,
            "section_title": None,
        }
        # 同じ条文を2回追加（通常は起こらないが、回帰防止）
        aggregator.add_article(context, "JPLAW:TEST#main#1", "1", "条文1")
        aggregator.add_article(context, "JPLAW:TEST#main#1", "1", "条文1")  # 重複

        edges = generate_containment_edges_from_aggregator(aggregator, "TEST")
        chapter_edges = [e for e in edges if e["relation"] == "chapter_contains_article"]

        # (source, target) ペアで重複チェック
        pairs = [(e["source"], e["target"]) for e in chapter_edges]
        unique_pairs = set(pairs)

        # 現在の実装では重複が出る可能性があるため、この仕様を明文化
        # 将来的に重複除去を実装する場合はこのテストを修正
        assert len(pairs) == len(unique_pairs), \
            f"Duplicate chapter edges detected: {len(pairs)} edges, {len(unique_pairs)} unique"

    def test_no_duplicate_section_edges(self):
        """同一節に同一条文が2回追加されても節エッジは1つだけ"""
        aggregator = StructureAggregator()
        context = {
            "chapter_num": 1,
            "chapter_title": "第一章",
            "section_num": 1,
            "section_title": "第一節",
        }
        aggregator.add_article(context, "JPLAW:TEST#main#1", "1", "条文1")
        aggregator.add_article(context, "JPLAW:TEST#main#1", "1", "条文1")  # 重複

        edges = generate_containment_edges_from_aggregator(aggregator, "TEST")
        section_edges = [e for e in edges if e["relation"] == "section_contains_article"]

        pairs = [(e["source"], e["target"]) for e in section_edges]
        unique_pairs = set(pairs)

        assert len(pairs) == len(unique_pairs), \
            f"Duplicate section edges detected: {len(pairs)} edges, {len(unique_pairs)} unique"

    def test_multiple_chapters_unique_edges(self):
        """複数章に条文が分散しても各エッジは一意"""
        aggregator = StructureAggregator()

        # 章1に条文1, 2
        ctx1 = {"chapter_num": 1, "chapter_title": "第一章", "section_num": None, "section_title": None}
        aggregator.add_article(ctx1, "JPLAW:TEST#main#1", "1", "条文1")
        aggregator.add_article(ctx1, "JPLAW:TEST#main#2", "2", "条文2")

        # 章2に条文3, 4
        ctx2 = {"chapter_num": 2, "chapter_title": "第二章", "section_num": None, "section_title": None}
        aggregator.add_article(ctx2, "JPLAW:TEST#main#3", "3", "条文3")
        aggregator.add_article(ctx2, "JPLAW:TEST#main#4", "4", "条文4")

        edges = generate_containment_edges_from_aggregator(aggregator, "TEST")
        chapter_edges = [e for e in edges if e["relation"] == "chapter_contains_article"]

        assert len(chapter_edges) == 4
        pairs = [(e["source"], e["target"]) for e in chapter_edges]
        assert len(pairs) == len(set(pairs)), "All chapter edges must be unique"

    def test_multiple_sections_unique_edges(self):
        """複数節に条文が分散しても各エッジは一意"""
        aggregator = StructureAggregator()

        # 章1節1に条文1
        ctx1 = {"chapter_num": 1, "chapter_title": "第一章", "section_num": 1, "section_title": "第一節"}
        aggregator.add_article(ctx1, "JPLAW:TEST#main#1", "1", "条文1")

        # 章1節2に条文2
        ctx2 = {"chapter_num": 1, "chapter_title": "第一章", "section_num": 2, "section_title": "第二節"}
        aggregator.add_article(ctx2, "JPLAW:TEST#main#2", "2", "条文2")

        # 章2節1に条文3
        ctx3 = {"chapter_num": 2, "chapter_title": "第二章", "section_num": 1, "section_title": "第一節"}
        aggregator.add_article(ctx3, "JPLAW:TEST#main#3", "3", "条文3")

        edges = generate_containment_edges_from_aggregator(aggregator, "TEST")
        section_edges = [e for e in edges if e["relation"] == "section_contains_article"]

        assert len(section_edges) == 3
        pairs = [(e["source"], e["target"]) for e in section_edges]
        assert len(pairs) == len(set(pairs)), "All section edges must be unique"
