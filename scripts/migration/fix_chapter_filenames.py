#!/usr/bin/env python3
"""
章ファイル名修正スクリプト

「第X章の2」が誤って「第X2章.md」として生成されている問題を修正。
frontmatter の chapter_title に「章の」が含まれる場合、正しいファイル名にリネーム。

例:
- 第62章.md (chapter_title: "第六章の二　妊産婦等") → 第6章の2.md
- 第102章.md (chapter_title: "第十章の二　...") → 第10章の2.md

Usage:
    # dry-run
    python scripts/migration/fix_chapter_filenames.py --vault ./Vault

    # apply
    python scripts/migration/fix_chapter_filenames.py --vault ./Vault --apply
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.utils.markdown import read_markdown_file, write_markdown_file


def format_chapter_name(chapter_num: int, chapter_title: Optional[str] = None) -> str:
    """
    章番号を正しいファイル名形式に変換。

    chapter_title に「章の」が含まれる場合は枝番号として処理。
    """
    if chapter_title and "章の" in chapter_title:
        main_num = chapter_num // 10
        sub_num = chapter_num % 10
        return f"第{main_num}章の{sub_num}"
    if chapter_num >= 100 and chapter_num % 10 != 0:
        main_num = chapter_num // 10
        sub_num = chapter_num % 10
        return f"第{main_num}章の{sub_num}"
    return f"第{chapter_num}章"


def analyze_chapter_file(file_path: Path) -> Optional[Tuple[str, str, str]]:
    """
    章ファイルを分析し、リネームが必要かどうかを判定。

    Returns:
        (current_name, correct_name, chapter_title) if rename needed, else None
    """
    try:
        doc = read_markdown_file(file_path)
    except Exception as e:
        print(f"Warning: Failed to read {file_path}: {e}", file=sys.stderr)
        return None

    chapter_num = doc.metadata.get("chapter_num")
    chapter_title = doc.metadata.get("chapter_title")

    if chapter_num is None:
        return None

    current_name = file_path.stem
    correct_name = format_chapter_name(chapter_num, chapter_title)

    if current_name != correct_name:
        return (current_name, correct_name, chapter_title or "")

    return None


def update_chapter_content(file_path: Path, old_name: str, new_name: str) -> bool:
    """
    章ファイルの内容（見出し）を更新。
    """
    try:
        doc = read_markdown_file(file_path)

        # 見出しを更新: # 第62章 → # 第6章の2
        old_heading_pattern = f"# {old_name}"
        new_heading = f"# {new_name}"
        doc.body = doc.body.replace(old_heading_pattern, new_heading)

        write_markdown_file(file_path, doc)
        return True
    except Exception as e:
        print(f"Error updating content {file_path}: {e}", file=sys.stderr)
        return False


def update_references_in_file(file_path: Path, law_id: str, old_name: str, new_name: str) -> int:
    """
    ファイル内の参照を更新。

    Returns:
        更新した参照の数
    """
    try:
        doc = read_markdown_file(file_path)
        original_body = doc.body

        # WikiLink 参照を更新
        # [[laws/{law_id}/章/第62章.md|...]] → [[laws/{law_id}/章/第6章の2.md|...]]
        old_link_pattern = f"章/{old_name}.md"
        new_link = f"章/{new_name}.md"
        doc.body = doc.body.replace(old_link_pattern, new_link)

        # 表示テキストも更新
        # |第62章]] → |第6章の2]]
        old_display_pattern = f"|{old_name}]]"
        new_display = f"|{new_name}]]"
        doc.body = doc.body.replace(old_display_pattern, new_display)

        if doc.body != original_body:
            write_markdown_file(file_path, doc)
            return doc.body.count(new_link) - original_body.count(new_link)

        return 0
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="章ファイル名の枝番号修正"
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
        help="特定の法令IDに限定",
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

    print(f"{'[DRY-RUN] ' if dry_run else ''}Scanning {len(law_dirs)} laws for chapter file renames...")
    print()

    renames_needed = []

    # Phase 1: リネームが必要なファイルを収集
    for law_dir in law_dirs:
        chapter_dir = law_dir / "章"
        if not chapter_dir.exists():
            continue

        for chapter_file in sorted(chapter_dir.glob("*.md")):
            result = analyze_chapter_file(chapter_file)
            if result:
                old_name, new_name, chapter_title = result
                renames_needed.append({
                    "law_dir": law_dir,
                    "chapter_file": chapter_file,
                    "old_name": old_name,
                    "new_name": new_name,
                    "chapter_title": chapter_title,
                })

    if not renames_needed:
        print("No renames needed.")
        return

    print(f"Found {len(renames_needed)} files to rename:")
    print()

    for item in renames_needed:
        law_name = item["law_dir"].name
        print(f"  [{law_name}] {item['old_name']}.md → {item['new_name']}.md")
        print(f"      chapter_title: {item['chapter_title'][:40]}...")

    print()

    if dry_run:
        print("To apply changes, run with --apply flag")
        return

    # Phase 2: 参照を先に更新
    print("Updating references...")
    total_refs_updated = 0

    for item in renames_needed:
        law_dir = item["law_dir"]
        law_id = law_dir.name
        old_name = item["old_name"]
        new_name = item["new_name"]

        # 法令ディレクトリ内のすべてのファイルで参照を更新
        for md_file in law_dir.rglob("*.md"):
            refs = update_references_in_file(md_file, law_id, old_name, new_name)
            total_refs_updated += refs

    print(f"  Updated {total_refs_updated} references")

    # Phase 3: 章ファイルの内容を更新
    print("Updating chapter file contents...")
    for item in renames_needed:
        chapter_file = item["chapter_file"]
        old_name = item["old_name"]
        new_name = item["new_name"]
        update_chapter_content(chapter_file, old_name, new_name)

    # Phase 4: ファイルをリネーム
    print("Renaming files...")
    for item in renames_needed:
        chapter_file = item["chapter_file"]
        new_name = item["new_name"]
        new_file = chapter_file.parent / f"{new_name}.md"

        chapter_file.rename(new_file)
        print(f"  Renamed: {chapter_file.name} → {new_file.name}")

    print()
    print("Done!")
    print(f"  Files renamed: {len(renames_needed)}")
    print(f"  References updated: {total_refs_updated}")


if __name__ == "__main__":
    main()
