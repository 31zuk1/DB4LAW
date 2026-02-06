#!/usr/bin/env python3
"""
DB4LAW: tier2 リンク再生成スクリプト

動的法令名レジストリ導入後、全記事の WikiLink を再生成する。
既存の WikiLink をプレーンテキストに戻し、tier2 を再実行して
新しい抑制ロジックで正しいリンクを生成する。

edges.jsonl も同時に再生成する。

Usage:
    # dry-run（変更内容を確認、デフォルト）
    python scripts/migration/rerun_tier2_links.py

    # 単一法令のみ
    python scripts/migration/rerun_tier2_links.py --law 129AC0000000089

    # 適用
    python scripts/migration/rerun_tier2_links.py --apply

    # edges.jsonl も再生成（v1 スキーマ）
    python scripts/migration/rerun_tier2_links.py --apply --edges --edge-schema v1
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.core.tier2 import EdgeExtractor, set_vault_root, clear_vault_caches
from legalkg.core.edge_schema import EdgeSchema, EdgeWriter
from legalkg.utils.markdown import read_markdown_file, write_markdown_file
from legalkg.utils.patterns import strip_wikilinks

ELIGIBLE_TYPES = frozenset(('article', 'supplement', 'amendment_fragment'))

# law_id → law_name の逆引きキャッシュ（_index/laws.json から構築）
_LAW_ID_TO_NAME: Dict[str, str] = {}


def load_law_id_to_name(vault_root: Path) -> None:
    """_index/laws.json から law_id → law_name マッピングを構築"""
    global _LAW_ID_TO_NAME
    index_path = vault_root / "_index" / "laws.json"
    if not index_path.exists():
        return
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        for entry in data.get("laws", []):
            lid = entry.get("law_id", "")
            title = entry.get("official_title", "")
            if lid and title:
                _LAW_ID_TO_NAME[lid] = title
    except (json.JSONDecodeError, OSError):
        pass


@dataclass
class FileRecord:
    file_path: str
    old_link_count: int
    new_link_count: int
    edge_count: int
    status: str  # changed, unchanged, skipped, error
    error_message: Optional[str] = None


@dataclass
class LawSummary:
    law_id: str
    total_files: int = 0
    changed: int = 0
    unchanged: int = 0
    skipped: int = 0
    errors: int = 0
    old_links: int = 0
    new_links: int = 0
    total_edges: int = 0


def count_wikilinks(text: str) -> int:
    """WikiLink の数をカウント"""
    return len(re.findall(r'\[\[', text))


def process_file(
    file_path: Path,
    vault_root: Path,
    extractor: EdgeExtractor,
    fallback_law_id: str,
    dry_run: bool,
    generate_edges: bool,
) -> tuple:
    """
    単一ファイルを処理

    Args:
        fallback_law_id: metadata に law_id がない場合のフォールバック（ディレクトリ名）

    Returns:
        (FileRecord, List[Dict]) — レコードとエッジリスト
    """
    rel_path = str(file_path.relative_to(vault_root))

    try:
        doc = read_markdown_file(file_path)

        # metadata.type で選別
        file_type = doc.metadata.get('type', '')
        if file_type not in ELIGIBLE_TYPES:
            return FileRecord(
                file_path=rel_path,
                old_link_count=0,
                new_link_count=0,
                edge_count=0,
                status="skipped",
                error_message=f"type={file_type}",
            ), []

        # law_id: metadata → fallback (ディレクトリ名)
        law_id = doc.metadata.get('law_id', '') or fallback_law_id

        # law_name: metadata → _LAW_ID_TO_NAME[law_id]
        law_name = doc.metadata.get('law_name', '')
        if not law_name:
            law_name = _LAW_ID_TO_NAME.get(law_id, '')

        node_id = doc.metadata.get('id', '')
        is_amendment = (file_type == 'amendment_fragment')

        # フォールバック後もなお不足 → スキップ（index ファイル等）
        if not law_name or not law_id:
            return FileRecord(
                file_path=rel_path,
                old_link_count=0,
                new_link_count=0,
                edge_count=0,
                status="skipped",
                error_message="No law_name/law_id after fallback",
            ), []

        old_link_count = count_wikilinks(doc.body)

        # WikiLink を削除してプレーンテキストに戻す
        plain_body = strip_wikilinks(doc.body)

        # tier2 再実行
        if generate_edges and node_id:
            new_body, edges = extractor.replace_refs_with_edges(
                text=plain_body,
                law_name=law_name,
                source_law_id=law_id,
                source_node_id=node_id,
                is_amendment_fragment=is_amendment,
            )
        else:
            new_body = extractor.replace_refs(
                plain_body,
                law_name,
                is_amendment_fragment=is_amendment,
            )
            edges = []

        new_link_count = count_wikilinks(new_body)

        # 変更チェック
        if doc.body.strip() == new_body.strip():
            return FileRecord(
                file_path=rel_path,
                old_link_count=old_link_count,
                new_link_count=new_link_count,
                edge_count=len(edges),
                status="unchanged",
            ), edges

        if not dry_run:
            doc.body = new_body
            write_markdown_file(file_path, doc)

        return FileRecord(
            file_path=rel_path,
            old_link_count=old_link_count,
            new_link_count=new_link_count,
            edge_count=len(edges),
            status="changed",
        ), edges

    except Exception as e:
        return FileRecord(
            file_path=rel_path,
            old_link_count=0,
            new_link_count=0,
            edge_count=0,
            status="error",
            error_message=str(e),
        ), []


def process_law(
    law_dir: Path,
    vault_root: Path,
    extractor: EdgeExtractor,
    dry_run: bool,
    generate_edges: bool,
    edge_writer: Optional[EdgeWriter],
    verbose: bool,
) -> LawSummary:
    """単一法令ディレクトリを処理"""
    law_id = law_dir.name
    summary = LawSummary(law_id=law_id)
    all_edges: List[Dict] = []

    # law_dir 配下の全 .md を走査し、metadata.type で選別
    md_files = sorted(law_dir.rglob("*.md"))
    if not md_files:
        return summary

    for md_file in md_files:
        summary.total_files += 1
        record, edges = process_file(
            md_file, vault_root, extractor, law_id, dry_run, generate_edges
        )
        all_edges.extend(edges)

        summary.old_links += record.old_link_count
        summary.new_links += record.new_link_count
        summary.total_edges += record.edge_count

        if record.status == "changed":
            summary.changed += 1
            if verbose:
                delta = record.new_link_count - record.old_link_count
                sign = "+" if delta >= 0 else ""
                print(
                    f"  {record.file_path}: "
                    f"{record.old_link_count} -> {record.new_link_count} "
                    f"({sign}{delta})"
                )
        elif record.status == "error":
            summary.errors += 1
            print(f"  ERROR: {record.file_path}: {record.error_message}")
        elif record.status == "unchanged":
            summary.unchanged += 1
        elif record.status == "skipped":
            summary.skipped += 1

    # edges.jsonl 出力（--edges --apply 時は空でも上書きして旧データを除去）
    edges_path = law_dir / "edges.jsonl"
    if generate_edges and edge_writer and not dry_run:
        if all_edges:
            edge_writer.write_jsonl(all_edges, edges_path)
        else:
            # エッジなし → 空ファイルで上書き（旧残骸除去）
            edges_path.write_text("", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="tier2 リンク再生成（動的法令名レジストリ対応）"
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path("./Vault"),
        help="Vault ディレクトリ (default: ./Vault)",
    )
    parser.add_argument(
        "--law",
        type=str,
        help="単一法令 ID に絞る（例: 129AC0000000089）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="変更を適用する（省略時は dry-run）",
    )
    parser.add_argument(
        "--edges",
        action="store_true",
        help="edges.jsonl も再生成する",
    )
    parser.add_argument(
        "--edge-schema",
        choices=["v1", "v2"],
        default="v2",
        help="エッジスキーマ (default: v2)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="変更ファイルを個別表示",
    )

    args = parser.parse_args()
    dry_run = not args.apply

    vault_root = args.vault.resolve()
    laws_dir = vault_root / "laws"
    if not laws_dir.exists():
        print(f"Error: laws directory not found: {laws_dir}")
        sys.exit(1)

    # law_id → law_name 逆引きマップ構築（metadata 欠損時のフォールバック用）
    load_law_id_to_name(vault_root)

    # Vault キャッシュ初期化
    clear_vault_caches()
    set_vault_root(vault_root)

    # EdgeWriter
    edge_writer = None
    if args.edges:
        schema = EdgeSchema.V1 if args.edge_schema == "v1" else EdgeSchema.V2
        edge_writer = EdgeWriter(schema)

    # EdgeExtractor
    extractor = EdgeExtractor(vault_root=vault_root)

    # 対象法令
    if args.law:
        law_dirs = [laws_dir / args.law]
        if not law_dirs[0].exists():
            print(f"Error: law not found: {law_dirs[0]}")
            sys.exit(1)
    else:
        law_dirs = sorted([d for d in laws_dir.iterdir() if d.is_dir()])

    mode = "[DRY-RUN] " if dry_run else ""
    print(f"{mode}Rerunning tier2 links for {len(law_dirs)} law(s)...")
    if args.edges:
        print(f"  Edge generation: enabled (schema {args.edge_schema})")
    print()

    # 集計
    grand_total_files = 0
    grand_changed = 0
    grand_unchanged = 0
    grand_skipped = 0
    grand_errors = 0
    grand_old_links = 0
    grand_new_links = 0
    grand_edges = 0

    for i, law_dir in enumerate(law_dirs, 1):
        if len(law_dirs) > 1 and (i % 100 == 0 or i == len(law_dirs)):
            print(f"  Progress: {i}/{len(law_dirs)} laws...")

        summary = process_law(
            law_dir=law_dir,
            vault_root=vault_root,
            extractor=extractor,
            dry_run=dry_run,
            generate_edges=args.edges,
            edge_writer=edge_writer,
            verbose=args.verbose,
        )

        grand_total_files += summary.total_files
        grand_changed += summary.changed
        grand_unchanged += summary.unchanged
        grand_skipped += summary.skipped
        grand_errors += summary.errors
        grand_old_links += summary.old_links
        grand_new_links += summary.new_links
        grand_edges += summary.total_edges

        # 法令単位サマリ（変更がある場合のみ、non-verbose）
        if summary.changed > 0 and not args.verbose:
            delta = summary.new_links - summary.old_links
            sign = "+" if delta >= 0 else ""
            print(
                f"  {summary.law_id}: {summary.changed} files changed, "
                f"links {summary.old_links} -> {summary.new_links} ({sign}{delta})"
            )

    # Grand Summary
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"  Laws processed:   {len(law_dirs)}")
    print(f"  Total files:      {grand_total_files}")
    print(f"  Changed:          {grand_changed}")
    print(f"  Unchanged:        {grand_unchanged}")
    print(f"  Skipped:          {grand_skipped}")
    print(f"  Errors:           {grand_errors}")
    print()

    delta = grand_new_links - grand_old_links
    sign = "+" if delta >= 0 else ""
    print(f"  Links before:     {grand_old_links}")
    print(f"  Links after:      {grand_new_links}")
    print(f"  Delta:            {sign}{delta}")

    if args.edges:
        print(f"  Edges generated:  {grand_edges}")
    print()

    if dry_run and grand_changed > 0:
        print("To apply changes, run with --apply flag")


if __name__ == "__main__":
    main()
