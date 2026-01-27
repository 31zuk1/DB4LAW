"""
Edge Schema Definitions and Writers

v1: Phase A 互換スキーマ（既存形式を完全維持）
v2: 実験用統一スキーマ（refs + containment を同型で扱う）
"""
from enum import Enum
from typing import Dict, Any, List
import json


class EdgeSchema(str, Enum):
    """エッジスキーマバージョン"""
    V1 = "v1"  # Phase A 互換（既存形式）
    V2 = "v2"  # 実験用統一スキーマ


# =============================================================================
# v1 Schema (Phase A Compatible - DO NOT MODIFY)
# =============================================================================
# 形式:
# {
#   "from": "JPLAW:...",
#   "to": "JPLAW:...",
#   "type": "refers_to",
#   "evidence": "第N条",
#   "confidence": 0.9,
#   "source": "regex_v2",
#   "kind": "external_ref"  # optional, for external refs
# }


def edge_to_v1(edge: Dict[str, Any]) -> Dict[str, Any]:
    """
    内部表現を v1 形式に変換（既存形式を完全維持）
    """
    # v1 は既存形式そのまま
    return edge


# =============================================================================
# v2 Schema (Experimental Unified Schema)
# =============================================================================
# 形式:
# {
#   "source": "...",
#   "target": "...",
#   "type": "refs" | "contains",
#   "relation": "internal" | "external" | "chapter_contains_article" | "section_contains_article",
#   "evidence": "...",  # refs のみ
#   "confidence": 0.9   # refs のみ
# }


def edge_to_v2(edge: Dict[str, Any]) -> Dict[str, Any]:
    """
    内部表現を v2 形式に変換

    v1 (refs) -> v2 変換:
      from -> source
      to -> target
      type: "refers_to" -> type: "refs"
      kind: "external_ref" -> relation: "external" / なし -> relation: "internal"

    containment edge は既に v2 形式で生成される
    """
    # 既に v2 形式（containment edge）の場合
    if "source" in edge and "target" in edge:
        return edge

    # v1 refs -> v2 変換
    v2_edge: Dict[str, Any] = {
        "source": edge["from"],
        "target": edge["to"],
        "type": "refs",
    }

    # relation: internal / external
    if edge.get("kind") == "external_ref":
        v2_edge["relation"] = "external"
    else:
        v2_edge["relation"] = "internal"

    # evidence と confidence を保持
    if "evidence" in edge:
        v2_edge["evidence"] = edge["evidence"]
    if "confidence" in edge:
        v2_edge["confidence"] = edge["confidence"]

    return v2_edge


# =============================================================================
# Containment Edge Generation (v2 only)
# =============================================================================

def create_chapter_containment_edge(
    chapter_id: str,
    article_id: str
) -> Dict[str, Any]:
    """
    章→条文の包含エッジを生成（v2 形式）
    """
    return {
        "source": chapter_id,
        "target": article_id,
        "type": "contains",
        "relation": "chapter_contains_article"
    }


def create_section_containment_edge(
    section_id: str,
    article_id: str
) -> Dict[str, Any]:
    """
    節→条文の包含エッジを生成（v2 形式）
    """
    return {
        "source": section_id,
        "target": article_id,
        "type": "contains",
        "relation": "section_contains_article"
    }


# =============================================================================
# Edge Writer
# =============================================================================

class EdgeWriter:
    """
    エッジをスキーマに応じた形式で出力する
    """

    def __init__(self, schema: EdgeSchema):
        self.schema = schema

    def convert(self, edge: Dict[str, Any]) -> Dict[str, Any]:
        """エッジを出力形式に変換"""
        if self.schema == EdgeSchema.V1:
            return edge_to_v1(edge)
        else:
            return edge_to_v2(edge)

    def write_jsonl(self, edges: List[Dict[str, Any]], file_path) -> None:
        """エッジリストを JSONL 形式で出力"""
        with open(file_path, "w", encoding="utf-8") as f:
            for edge in edges:
                converted = self.convert(edge)
                f.write(json.dumps(converted, ensure_ascii=False) + "\n")


def generate_containment_edges_from_aggregator(
    aggregator,
    law_id: str
) -> List[Dict[str, Any]]:
    """
    StructureAggregator から包含エッジを生成

    仕様:
    - chapter_contains_article は (chapter_id, article_id) で一意
    - section_contains_article は (section_id, article_id) で一意
    - 同一 run 内で重複 edge を出力しない

    Args:
        aggregator: StructureAggregator インスタンス
        law_id: 法令ID

    Returns:
        包含エッジのリスト（v2 形式、重複なし）
    """
    edges: List[Dict[str, Any]] = []
    seen_pairs: set = set()  # (source, target) で重複チェック

    # 章→条文
    for chapter_num, chapter_agg in aggregator.chapters.items():
        chapter_id = f"JPLAW:{law_id}#chapter#{chapter_num}"
        for article_id in chapter_agg.article_ids:
            pair = (chapter_id, article_id)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                edges.append(create_chapter_containment_edge(chapter_id, article_id))

    # 節→条文
    for (chapter_num, section_num), section_agg in aggregator.sections.items():
        section_id = f"JPLAW:{law_id}#chapter#{chapter_num}#section#{section_num}"
        for article_id in section_agg.article_ids:
            pair = (section_id, article_id)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                edges.append(create_section_containment_edge(section_id, article_id))

    return edges
