#!/usr/bin/env python3
"""
Fix all broken links in the Vault:
1. Generate missing chapter/section nodes from article frontmatter
2. Unlink references to non-existent articles
"""

import re
import json
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, Set, Tuple

import yaml


def parse_frontmatter(content: str) -> Tuple[Optional[dict], str]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith('---'):
        return None, content

    parts = content.split('---', 2)
    if len(parts) < 3:
        return None, content

    try:
        fm = yaml.safe_load(parts[1])
        return fm, '---' + parts[1] + '---' + parts[2]
    except yaml.YAMLError:
        return None, content


def serialize_frontmatter(fm: dict, body: str) -> str:
    """Serialize frontmatter to markdown."""
    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return '---\n' + fm_str + '---\n' + body


def collect_chapter_info(vault_root: Path) -> Dict[str, Dict[str, dict]]:
    """
    Collect chapter info from article frontmatter.
    Returns: {law_id: {chapter_filename: {title, num, articles}}}
    Chapter filename is extracted from parent field (e.g., 第6章.md, 第6章の2.md)
    """
    laws_dir = vault_root / 'laws'
    chapters = defaultdict(lambda: defaultdict(lambda: {'title': '', 'num': 0, 'articles': []}))

    # Pattern to extract chapter filename from parent field
    # [[laws/{law_id}/章/{chapter_name}.md]] or [[laws/{law_id}/章/{chapter_name}.md|...]]
    chapter_parent_pattern = re.compile(r'\[\[laws/[^/]+/章/([^|\]]+\.md)(?:\|[^\]]+)?\]\]')

    for law_dir in laws_dir.iterdir():
        if not law_dir.is_dir():
            continue

        law_id = law_dir.name
        honbun_dir = law_dir / '本文'

        if not honbun_dir.exists():
            continue

        for article_file in honbun_dir.glob('*.md'):
            try:
                content = article_file.read_text(encoding='utf-8')
            except Exception:
                continue

            fm, _ = parse_frontmatter(content)
            if not fm:
                continue

            # Extract chapter info from parent field
            parent = fm.get('parent', '')
            chapter_match = chapter_parent_pattern.search(parent)

            if chapter_match:
                chapter_filename = chapter_match.group(1)  # e.g., "第6章.md" or "第6章の2.md"
                chapter_name = chapter_filename.replace('.md', '')  # e.g., "第6章" or "第6章の2"
                chapter_title = fm.get('chapter_title', '')
                chapter_num = fm.get('chapter_num', 0)

                chapters[law_id][chapter_name]['title'] = chapter_title
                chapters[law_id][chapter_name]['num'] = chapter_num
                chapters[law_id][chapter_name]['articles'].append(article_file.name)

    return chapters


def collect_section_info(vault_root: Path) -> Dict[str, Dict[str, dict]]:
    """
    Collect section info from article frontmatter.
    Returns: {law_id: {section_key: {chapter_num, chapter_title, section_num, section_title, articles}}}
    Section key format: "第{chapter_num}章第{section_num}節"
    """
    laws_dir = vault_root / 'laws'
    sections = defaultdict(lambda: defaultdict(lambda: {
        'chapter_num': 0, 'chapter_title': '',
        'section_num': 0, 'section_title': '',
        'articles': []
    }))

    for law_dir in laws_dir.iterdir():
        if not law_dir.is_dir():
            continue

        law_id = law_dir.name
        honbun_dir = law_dir / '本文'

        if not honbun_dir.exists():
            continue

        for article_file in honbun_dir.glob('*.md'):
            try:
                content = article_file.read_text(encoding='utf-8')
            except Exception:
                continue

            fm, _ = parse_frontmatter(content)
            if not fm:
                continue

            # Extract section info (only if both chapter and section exist)
            chapter_num = fm.get('chapter_num')
            section_num = fm.get('section_num')

            if chapter_num is not None and section_num is not None:
                section_key = f"第{chapter_num}章第{section_num}節"
                sections[law_id][section_key]['chapter_num'] = chapter_num
                sections[law_id][section_key]['chapter_title'] = fm.get('chapter_title', '')
                sections[law_id][section_key]['section_num'] = section_num
                sections[law_id][section_key]['section_title'] = fm.get('section_title', '')
                sections[law_id][section_key]['articles'].append(article_file.name)

    return sections


def generate_section_files(vault_root: Path, sections: Dict[str, Dict[str, dict]], dry_run: bool = False) -> int:
    """Generate missing section files."""
    created = 0
    laws_dir = vault_root / 'laws'

    for law_id, law_sections in sections.items():
        law_dir = laws_dir / law_id
        section_dir = law_dir / '節'

        # Get law name from law file
        law_name = law_id
        law_files = list(law_dir.glob('*_law.md'))
        if law_files:
            try:
                content = law_files[0].read_text(encoding='utf-8')
                fm, _ = parse_frontmatter(content)
                if fm:
                    law_name = fm.get('title') or fm.get('official_title') or law_id
            except Exception:
                pass

        for section_key, info in law_sections.items():
            section_file = section_dir / f"{section_key}.md"

            if section_file.exists():
                continue

            # Create section file
            chapter_num = info['chapter_num']
            chapter_title = info['chapter_title']
            section_num = info['section_num']
            section_title = info['section_title']

            # Parent is the chapter
            chapter_name = f"第{chapter_num}章"

            fm = {
                'id': f"JPLAW:{law_id}#section#{chapter_num}_{section_num}",
                'type': 'section',
                'parent': f"[[laws/{law_id}/章/{chapter_name}.md]]",
                'law_id': law_id,
                'law_name': law_name,
                'chapter_num': chapter_num,
                'chapter_title': chapter_title,
                'section_num': section_num,
                'section_title': section_title,
                'tags': [law_name]
            }

            title_text = section_key
            if section_title:
                title_text += f" {section_title}"

            body = f"\n# {title_text}\n"

            if dry_run:
                print(f"Would create: {section_file}")
            else:
                section_dir.mkdir(parents=True, exist_ok=True)
                section_file.write_text(serialize_frontmatter(fm, body), encoding='utf-8')
                print(f"Created: {section_file}")

            created += 1

    return created


def generate_chapter_files(vault_root: Path, chapters: Dict[str, Dict[str, dict]], dry_run: bool = False) -> int:
    """Generate missing chapter files."""
    created = 0
    laws_dir = vault_root / 'laws'

    for law_id, law_chapters in chapters.items():
        law_dir = laws_dir / law_id
        chapter_dir = law_dir / '章'

        # Get law name from law file
        law_name = law_id
        law_files = list(law_dir.glob('*_law.md'))
        if law_files:
            try:
                content = law_files[0].read_text(encoding='utf-8')
                fm, _ = parse_frontmatter(content)
                if fm:
                    law_name = fm.get('title') or fm.get('official_title') or law_id
            except Exception:
                pass

        for chapter_name, info in law_chapters.items():
            chapter_file = chapter_dir / f"{chapter_name}.md"

            if chapter_file.exists():
                continue

            # Create chapter file
            chapter_num = info['num']
            chapter_title = info['title']

            fm = {
                'id': f"JPLAW:{law_id}#chapter#{chapter_num}",
                'type': 'chapter',
                'parent': f"[[laws/{law_id}/{law_name[:20]}_law.md|{law_name}]]",
                'law_id': law_id,
                'law_name': law_name,
                'chapter_num': chapter_num,
                'chapter_title': chapter_title,
                'tags': [law_name]
            }

            title_text = f"{chapter_name}"
            if chapter_title:
                title_text += f" {chapter_title}"

            body = f"\n# {title_text}\n"

            if dry_run:
                print(f"Would create: {chapter_file}")
            else:
                chapter_dir.mkdir(parents=True, exist_ok=True)
                chapter_file.write_text(serialize_frontmatter(fm, body), encoding='utf-8')
                print(f"Created: {chapter_file}")

            created += 1

    return created


def find_broken_article_links(vault_root: Path) -> Dict[Path, Set[str]]:
    """
    Find all broken article links (links to non-existent 本文 files).
    Returns: {source_file: {broken_link_path, ...}}
    """
    broken = defaultdict(set)
    laws_dir = vault_root / 'laws'

    # WikiLink pattern
    wikilink_pattern = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')

    for md_file in laws_dir.rglob('*.md'):
        try:
            content = md_file.read_text(encoding='utf-8')
        except Exception:
            continue

        for match in wikilink_pattern.finditer(content):
            link_path = match.group(1)

            # Only check 本文 links
            if '/本文/' not in link_path:
                continue

            # Skip if not starting with laws/
            if not link_path.startswith('laws/'):
                continue

            # Check if target exists
            target = vault_root / link_path
            if not target.exists():
                # Also try without .md
                if not link_path.endswith('.md'):
                    target_with_md = vault_root / (link_path + '.md')
                    if target_with_md.exists():
                        continue

                broken[md_file].add(link_path)

    return broken


def unlink_broken_references(vault_root: Path, broken_links: Dict[Path, Set[str]], dry_run: bool = False) -> int:
    """
    Remove wikilinks to non-existent articles, keeping the display text.
    [[path|text]] -> text
    [[path]] -> 第N条 (extracted from path)
    """
    fixed = 0

    for source_file, links in broken_links.items():
        try:
            content = source_file.read_text(encoding='utf-8')
        except Exception:
            continue

        original = content

        for link_path in links:
            # Pattern with alias: [[path|alias]]
            pattern_with_alias = re.compile(
                r'\[\[' + re.escape(link_path) + r'\|([^\]]+)\]\]'
            )
            content = pattern_with_alias.sub(r'\1', content)

            # Pattern without alias: [[path]]
            # Extract article name from path for display
            article_match = re.search(r'/本文/(第[^/]+)\.md$', link_path)
            if article_match:
                article_name = article_match.group(1)
            else:
                article_name = link_path.split('/')[-1].replace('.md', '')

            pattern_no_alias = re.compile(
                r'\[\[' + re.escape(link_path) + r'\]\]'
            )
            content = pattern_no_alias.sub(article_name, content)

        if content != original:
            if dry_run:
                print(f"Would fix: {source_file} ({len(links)} links)")
            else:
                source_file.write_text(content, encoding='utf-8')
                print(f"Fixed: {source_file} ({len(links)} links)")
            fixed += 1

    return fixed


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Fix all broken links')
    parser.add_argument('--vault', type=Path, default=Path('Vault'),
                        help='Path to Vault directory')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    parser.add_argument('--skip-chapters', action='store_true',
                        help='Skip chapter generation')
    parser.add_argument('--skip-sections', action='store_true',
                        help='Skip section generation')
    parser.add_argument('--skip-unlink', action='store_true',
                        help='Skip unlinking broken article references')

    args = parser.parse_args()
    vault_root = args.vault.resolve()

    print(f"Vault: {vault_root}")
    if args.dry_run:
        print("=== DRY RUN MODE ===\n")

    # Step 1: Generate missing chapter files
    if not args.skip_chapters:
        print("=" * 60)
        print("Step 1: Generating missing chapter files...")
        print("=" * 60)

        chapters = collect_chapter_info(vault_root)
        print(f"Found chapter info for {len(chapters)} laws")

        created = generate_chapter_files(vault_root, chapters, dry_run=args.dry_run)
        print(f"\n{'Would create' if args.dry_run else 'Created'} {created} chapter files")

    # Step 2: Generate missing section files
    if not args.skip_sections:
        print("\n" + "=" * 60)
        print("Step 2: Generating missing section files...")
        print("=" * 60)

        sections = collect_section_info(vault_root)
        total_sections = sum(len(s) for s in sections.values())
        print(f"Found section info for {len(sections)} laws ({total_sections} unique sections)")

        created = generate_section_files(vault_root, sections, dry_run=args.dry_run)
        print(f"\n{'Would create' if args.dry_run else 'Created'} {created} section files")

    # Step 3: Unlink broken article references
    if not args.skip_unlink:
        print("\n" + "=" * 60)
        print("Step 3: Unlinking broken article references...")
        print("=" * 60)

        broken = find_broken_article_links(vault_root)
        total_broken = sum(len(links) for links in broken.values())
        print(f"Found {total_broken} broken article links in {len(broken)} files")

        fixed = unlink_broken_references(vault_root, broken, dry_run=args.dry_run)
        print(f"\n{'Would fix' if args.dry_run else 'Fixed'} {fixed} files")

    print("\nDone!")
    return 0


if __name__ == '__main__':
    exit(main())
