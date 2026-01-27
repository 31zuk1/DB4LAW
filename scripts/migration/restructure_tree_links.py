#!/usr/bin/env python3
"""
DB4LAW: 木構造リンク再構築スクリプト

Graph毛玉化を防ぐため、各ノードのリンクを直下の子ノードのみに制限する。

構造:
- 法令.md → 章ノードのみ（条文への直接リンクを削除）
- 章ノード → 節ノードのみ（条文への直接リンクを削除）
- 節ノード → 条文（変更なし）

節がない章の場合は、章から条文へ直接リンク（変更なし）

Usage:
    # dry-run
    python scripts/migration/restructure_tree_links.py --vault ./Vault --law 民法

    # apply
    python scripts/migration/restructure_tree_links.py --vault ./Vault --law 民法 --apply
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.utils.markdown import read_markdown_file, write_markdown_file, MarkdownDocument


@dataclass
class ChangeRecord:
    file_path: str
    node_type: str  # law, chapter, section
    old_link_count: int
    new_link_count: int
    removed_links: int
    status: str  # changed, unchanged, skipped, error
    error_message: Optional[str] = None


def get_sections_for_chapter(law_dir: Path, chapter_num: int) -> list[str]:
    """指定した章に属する節ファイル名のリストを取得"""
    section_dir = law_dir / "節"
    if not section_dir.exists():
        return []

    sections = []
    pattern = re.compile(rf"^第{chapter_num}章.*\.md$")
    for f in section_dir.iterdir():
        if f.is_file() and pattern.match(f.name):
            sections.append(f.name)
    return sorted(sections)


def get_chapters(law_dir: Path) -> list[str]:
    """章ファイル名のリストを取得"""
    chapter_dir = law_dir / "章"
    if not chapter_dir.exists():
        return []

    chapters = []
    for f in chapter_dir.iterdir():
        if f.is_file() and f.suffix == ".md":
            chapters.append(f.name)
    return sorted(chapters)


def extract_wikilinks(content: str) -> list[str]:
    """本文からwikilinksを抽出"""
    pattern = r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]'
    return re.findall(pattern, content)


def rebuild_law_node_body(law_name: str, law_dir: Path) -> str:
    """法令ノードの本文を再構築（章へのリンクのみ）"""
    chapters = get_chapters(law_dir)

    lines = [
        f"# {law_name}",
        "",
        "## 構造",
        "",
    ]

    if chapters:
        lines.append("### 章")
        lines.append("")
        for ch in chapters:
            ch_name = ch.replace(".md", "")
            lines.append(f"- [[章/{ch}|{ch_name}]]")
    else:
        # 章がない場合は本文へのリンクを維持
        main_dir = law_dir / "本文"
        if main_dir.exists():
            lines.append("### 本文")
            lines.append("")
            for f in sorted(main_dir.glob("*.md")):
                article_name = f.stem
                lines.append(f"- [[本文/{f.name}|{article_name}]]")

    # 附則セクション
    suppl_dir = law_dir / "附則"
    if suppl_dir.exists():
        lines.append("")
        lines.append("### 附則")
        lines.append("")
        # 附則は改正法サブディレクトリごとにグループ化
        for subdir in sorted(suppl_dir.iterdir()):
            if subdir.is_dir():
                lines.append(f"- {subdir.name}/")

    return "\n".join(lines) + "\n"


def rebuild_chapter_node_body(
    law_name: str,
    law_dir: Path,
    chapter_file: Path,
    chapter_num: int,
    chapter_title: str,
) -> str:
    """章ノードの本文を再構築（節へのリンクのみ、節がなければ条文）"""
    sections = get_sections_for_chapter(law_dir, chapter_num)

    lines = [
        f"# {chapter_title}",
        "",
    ]

    if sections:
        # 節が存在する場合は節へのリンクのみ
        lines.append("## この章の節")
        lines.append("")
        for sec in sections:
            sec_name = sec.replace(".md", "")
            lines.append(f"- [[laws/{law_name}/節/{sec}|{sec_name}]]")
    else:
        # 節がない場合は条文へのリンクを維持
        # frontmatterのarticle_numsを利用
        doc = read_markdown_file(chapter_file)
        article_nums = doc.metadata.get("article_nums", [])
        if article_nums:
            lines.append("## この章の条文")
            lines.append("")
            for art_num in article_nums:
                # article_numを日本語ファイル名に変換
                if "_" in str(art_num):
                    parts = str(art_num).split("_")
                    article_name = f"第{parts[0]}条の{parts[1]}"
                    filename = f"第{parts[0]}条の{parts[1]}.md"
                else:
                    article_name = f"第{art_num}条"
                    filename = f"第{art_num}条.md"
                lines.append(f"- [[laws/{law_name}/本文/{filename}|{article_name}]]")

    return "\n".join(lines) + "\n"


def process_law_node(
    law_dir: Path,
    law_name: str,
    dry_run: bool,
) -> ChangeRecord:
    """法令ノードを処理"""
    law_file = law_dir / f"{law_name}.md"
    rel_path = str(law_file.relative_to(law_dir.parent.parent))

    if not law_file.exists():
        return ChangeRecord(
            file_path=rel_path,
            node_type="law",
            old_link_count=0,
            new_link_count=0,
            removed_links=0,
            status="skipped",
            error_message="File not found",
        )

    try:
        doc = read_markdown_file(law_file)
        old_links = extract_wikilinks(doc.body)
        old_count = len(old_links)

        # 新しい本文を生成
        new_body = rebuild_law_node_body(law_name, law_dir)
        new_links = extract_wikilinks(new_body)
        new_count = len(new_links)

        if old_count == new_count:
            return ChangeRecord(
                file_path=rel_path,
                node_type="law",
                old_link_count=old_count,
                new_link_count=new_count,
                removed_links=0,
                status="unchanged",
            )

        if not dry_run:
            doc.body = "\n" + new_body
            write_markdown_file(law_file, doc)

        return ChangeRecord(
            file_path=rel_path,
            node_type="law",
            old_link_count=old_count,
            new_link_count=new_count,
            removed_links=old_count - new_count,
            status="changed",
        )

    except Exception as e:
        return ChangeRecord(
            file_path=rel_path,
            node_type="law",
            old_link_count=0,
            new_link_count=0,
            removed_links=0,
            status="error",
            error_message=str(e),
        )


def process_chapter_node(
    chapter_file: Path,
    law_dir: Path,
    law_name: str,
    dry_run: bool,
) -> ChangeRecord:
    """章ノードを処理"""
    rel_path = str(chapter_file.relative_to(law_dir.parent.parent))

    try:
        doc = read_markdown_file(chapter_file)
        old_links = extract_wikilinks(doc.body)
        old_count = len(old_links)

        chapter_num = doc.metadata.get("chapter_num")
        chapter_title = doc.metadata.get("chapter_title", "")

        if chapter_num is None:
            return ChangeRecord(
                file_path=rel_path,
                node_type="chapter",
                old_link_count=old_count,
                new_link_count=0,
                removed_links=0,
                status="skipped",
                error_message="No chapter_num in frontmatter",
            )

        # 節があるかチェック
        sections = get_sections_for_chapter(law_dir, chapter_num)

        if not sections:
            # 節がない章は変更しない（条文へのリンクを維持）
            return ChangeRecord(
                file_path=rel_path,
                node_type="chapter",
                old_link_count=old_count,
                new_link_count=old_count,
                removed_links=0,
                status="unchanged",
                error_message="No sections for this chapter",
            )

        # 新しい本文を生成
        new_body = rebuild_chapter_node_body(
            law_name, law_dir, chapter_file, chapter_num, chapter_title
        )
        new_links = extract_wikilinks(new_body)
        new_count = len(new_links)

        if old_count == new_count:
            return ChangeRecord(
                file_path=rel_path,
                node_type="chapter",
                old_link_count=old_count,
                new_link_count=new_count,
                removed_links=0,
                status="unchanged",
            )

        if not dry_run:
            doc.body = "\n" + new_body
            write_markdown_file(chapter_file, doc)

        return ChangeRecord(
            file_path=rel_path,
            node_type="chapter",
            old_link_count=old_count,
            new_link_count=new_count,
            removed_links=old_count - new_count,
            status="changed",
        )

    except Exception as e:
        return ChangeRecord(
            file_path=rel_path,
            node_type="chapter",
            old_link_count=0,
            new_link_count=0,
            removed_links=0,
            status="error",
            error_message=str(e),
        )


def main():
    parser = argparse.ArgumentParser(
        description="木構造リンク再構築（Graph毛玉化防止）"
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path("./Vault"),
        help="Vault ディレクトリ",
    )
    parser.add_argument(
        "--law",
        type=str,
        help="単一法令に絞る",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="変更を適用しない（デフォルト）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="変更を適用する",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="変更ログの出力先（JSONL）",
    )

    args = parser.parse_args()
    dry_run = not args.apply

    laws_dir = args.vault / "laws"
    if not laws_dir.exists():
        print(f"Error: laws directory not found: {laws_dir}")
        sys.exit(1)

    # 対象法令
    if args.law:
        law_dirs = [laws_dir / args.law]
        if not law_dirs[0].exists():
            print(f"Error: law not found: {law_dirs[0]}")
            sys.exit(1)
    else:
        law_dirs = sorted([d for d in laws_dir.iterdir() if d.is_dir()])

    print(f"{'[DRY-RUN] ' if dry_run else ''}Processing {len(law_dirs)} laws...")
    print()

    records: list[ChangeRecord] = []
    total_removed = 0

    for law_dir in law_dirs:
        law_name = law_dir.name
        print(f"Processing {law_name}...")

        # 1. 法令ノードを処理
        record = process_law_node(law_dir, law_name, dry_run)
        records.append(record)
        if record.status == "changed":
            total_removed += record.removed_links
            print(f"  {law_name}.md: {record.old_link_count} → {record.new_link_count} links")

        # 2. 章ノードを処理
        chapter_dir = law_dir / "章"
        if chapter_dir.exists():
            for chapter_file in sorted(chapter_dir.glob("*.md")):
                record = process_chapter_node(chapter_file, law_dir, law_name, dry_run)
                records.append(record)
                if record.status == "changed":
                    total_removed += record.removed_links
                    print(f"  {chapter_file.name}: {record.old_link_count} → {record.new_link_count} links")

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    changed = [r for r in records if r.status == "changed"]
    unchanged = [r for r in records if r.status == "unchanged"]
    skipped = [r for r in records if r.status == "skipped"]
    errors = [r for r in records if r.status == "error"]

    print(f"  Total nodes:    {len(records)}")
    print(f"  Changed:        {len(changed)}")
    print(f"  Unchanged:      {len(unchanged)}")
    print(f"  Skipped:        {len(skipped)}")
    print(f"  Errors:         {len(errors)}")
    print(f"  Links removed:  {total_removed}")
    print()

    if errors:
        print("Errors:")
        for r in errors:
            print(f"  {r.file_path}: {r.error_message}")
        print()

    # Log output
    output_path = args.output
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifacts_dir = Path(__file__).parent / "_artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifacts_dir / f"tree_restructure_{timestamp}.jsonl"

    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    print(f"Log written to: {output_path}")

    if dry_run and len(changed) > 0:
        print()
        print("To apply changes, run with --apply flag")


if __name__ == "__main__":
    main()
