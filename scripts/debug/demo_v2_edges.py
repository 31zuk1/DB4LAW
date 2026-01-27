#!/usr/bin/env python3
"""
v2 Edge Schema のデモスクリプト

edges.jsonl だけを使って:
1. 特定章配下の条文取得
2. 節 → 条文列の走査
を行い、v1 との差分（簡単さ）を確認する。
"""
import json
from pathlib import Path
from collections import defaultdict


def load_edges(jsonl_path: Path) -> list:
    """edges.jsonl を読み込む"""
    edges = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                edges.append(json.loads(line))
    return edges


def demo_v1_get_chapter_articles(edges: list, chapter_num: int) -> list:
    """
    v1 スキーマで「第N章の条文」を取得する

    問題点: v1 には containment edges がないため、
    edges.jsonl だけでは章→条文の関係が分からない。
    各条文の frontmatter を読む必要がある。
    """
    # v1 では edges.jsonl に章→条文の関係がない
    # refs edges しかないので、章→条文の取得は不可能
    return []  # 不可能


def demo_v2_get_chapter_articles(edges: list, chapter_num: int) -> list:
    """
    v2 スキーマで「第N章の条文」を取得する

    利点: containment edges があるため、
    edges.jsonl だけで章→条文の関係が取得できる。
    """
    articles = []
    chapter_id_suffix = f"#chapter#{chapter_num}"

    for edge in edges:
        if edge.get("type") == "contains" and edge.get("relation") == "chapter_contains_article":
            if chapter_id_suffix in edge["source"]:
                articles.append(edge["target"])

    return articles


def demo_v2_get_section_articles(edges: list, chapter_num: int, section_num: int) -> list:
    """
    v2 スキーマで「第N章第M節の条文」を取得する
    """
    articles = []
    section_id_suffix = f"#chapter#{chapter_num}#section#{section_num}"

    for edge in edges:
        if edge.get("type") == "contains" and edge.get("relation") == "section_contains_article":
            if section_id_suffix in edge["source"]:
                articles.append(edge["target"])

    return articles


def demo_v2_build_chapter_index(edges: list) -> dict:
    """
    v2 スキーマで章→条文のインデックスを構築

    利点: O(N) で全章のインデックスが作れる
    """
    index = defaultdict(list)

    for edge in edges:
        if edge.get("type") == "contains" and edge.get("relation") == "chapter_contains_article":
            # source から章番号を抽出
            source = edge["source"]
            # JPLAW:XXX#chapter#N
            parts = source.split("#chapter#")
            if len(parts) == 2:
                chapter_num = int(parts[1])
                index[chapter_num].append(edge["target"])

    return dict(index)


def demo_v2_refs_by_chapter(edges: list, chapter_articles: set) -> list:
    """
    v2 スキーマで「特定章内の条文間参照」を取得

    利点: containment + refs を組み合わせたクエリが可能
    """
    internal_refs = []

    for edge in edges:
        if edge.get("type") == "refs" and edge.get("relation") == "internal":
            if edge["source"] in chapter_articles and edge["target"] in chapter_articles:
                internal_refs.append(edge)

    return internal_refs


def main():
    import sys

    # デフォルトは刑法
    law_name = sys.argv[1] if len(sys.argv) > 1 else "刑法"
    vault_path = Path("Vault/laws") / law_name / "edges.jsonl"

    if not vault_path.exists():
        print(f"Error: {vault_path} not found")
        return

    edges = load_edges(vault_path)

    # スキーマ判定
    first_edge = edges[0] if edges else {}
    is_v2 = "source" in first_edge and "target" in first_edge

    print(f"=== {law_name} edges.jsonl demo ===")
    print(f"Total edges: {len(edges)}")
    print(f"Schema: {'v2' if is_v2 else 'v1'}")
    print()

    if not is_v2:
        print("v1 スキーマでは containment edges がないため、")
        print("章→条文の関係を edges.jsonl だけで取得できません。")
        print("各条文の frontmatter を読む必要があります。")
        return

    # v2 デモ
    print("--- Demo 1: 第1章の条文を取得 ---")
    ch1_articles = demo_v2_get_chapter_articles(edges, 1)
    print(f"第1章の条文数: {len(ch1_articles)}")
    if ch1_articles:
        print(f"最初の3条: {ch1_articles[:3]}")
    print()

    print("--- Demo 2: 章インデックスを構築 ---")
    chapter_index = demo_v2_build_chapter_index(edges)
    print(f"章の数: {len(chapter_index)}")
    for ch_num in sorted(chapter_index.keys())[:5]:
        print(f"  第{ch_num}章: {len(chapter_index[ch_num])}条")
    if len(chapter_index) > 5:
        print(f"  ... (他 {len(chapter_index) - 5} 章)")
    print()

    # 会社法の場合は節も確認
    if law_name == "会社法":
        print("--- Demo 3: 第2章第1節の条文を取得 ---")
        sec_articles = demo_v2_get_section_articles(edges, 2, 1)
        print(f"第2章第1節の条文数: {len(sec_articles)}")
        if sec_articles:
            print(f"最初の3条: {sec_articles[:3]}")
        print()

    print("--- Demo 4: 第1章内の条文間参照 ---")
    ch1_set = set(ch1_articles)
    ch1_refs = demo_v2_refs_by_chapter(edges, ch1_set)
    print(f"第1章内の参照エッジ数: {len(ch1_refs)}")
    if ch1_refs:
        ref = ch1_refs[0]
        print(f"例: {ref['source']} -> {ref['target']} ({ref.get('evidence', '')})")
    print()

    print("=== v2 の価値 ===")
    print("1. edges.jsonl だけで章/節→条文の関係が取得可能")
    print("2. frontmatter を読まずにグラフクエリが可能")
    print("3. containment + refs を組み合わせた分析が可能")
    print("4. O(N) で全章のインデックス構築が可能")


if __name__ == "__main__":
    main()
