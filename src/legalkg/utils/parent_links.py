"""
Utility functions for generating parent law file links.
"""

import re
from pathlib import Path
from typing import List, Tuple, Optional
from .markdown import read_markdown_file


def extract_article_sort_key(filename: str) -> Tuple[int, ...]:
    """
    Extract sort key from article filename.

    Supports complex article numbering patterns:
        第1条.md -> (1, 0, 0, 0)
        第1条の2.md -> (1, 2, 0, 0)
        第100条.md -> (100, 0, 0, 0)
        第638:640条.md -> (638, 0, 0, 640)  # Range format
        init_0_第1条.md -> (1, 0, 0, 0)  # With prefix
        第105の2の8条.md -> (105, 2, 8, 0)  # Complex nested format
        第184の12の2条.md -> (184, 12, 2, 0)  # Complex nested format
    """
    name = filename.replace('.md', '')

    # Complex nested format: 第NのMのK条 (e.g., 第105の2の8条)
    match = re.match(r'第(\d+)(?:の(\d+))?(?:の(\d+))?(?:の(\d+))?条$', name)
    if match:
        main_num = int(match.group(1))
        sub1 = int(match.group(2)) if match.group(2) else 0
        sub2 = int(match.group(3)) if match.group(3) else 0
        sub3 = int(match.group(4)) if match.group(4) else 0
        return (main_num, sub1, sub2, sub3)

    # Prefix format: {prefix}_第N条 or {prefix}_第N条のM
    match = re.match(r'.+_第(\d+)条(?:の(\d+))?$', name)
    if match:
        main_num = int(match.group(1))
        sub_num = int(match.group(2)) if match.group(2) else 0
        return (main_num, sub_num, 0, 0)

    # Range format: 第N:M条
    match = re.match(r'第(\d+):(\d+)条', name)
    if match:
        start_num = int(match.group(1))
        end_num = int(match.group(2))
        return (start_num, 0, 0, end_num)

    # Standard format: 第N条 or 第N条のM
    match = re.match(r'第(\d+)条(?:の(\d+))?', name)
    if match:
        main_num = int(match.group(1))
        sub_num = int(match.group(2)) if match.group(2) else 0
        return (main_num, sub_num, 0, 0)

    # 附則第N条 format
    match = re.match(r'附則第(\d+)条(?:の(\d+))?', name)
    if match:
        main_num = int(match.group(1))
        sub_num = int(match.group(2)) if match.group(2) else 0
        return (main_num, sub_num, 0, 0)

    # Others (附則.md etc.)
    return (0, 0, 0, 0)


def extract_display_name_from_init_file(filename: str) -> str:
    """
    Extract display name from initial supplementary provision filename.

    Examples:
        init_0_第1条.md -> 第1条
        init_0_第10条の2.md -> 第10条の2
    """
    name = filename.replace('.md', '')

    # Extract init_0_第N条 or init_0_第N条のM pattern
    match = re.search(r'(第\d+条(?:の\d+)?)', name)
    if match:
        return match.group(1)

    # Fallback: remove prefix
    if '_' in name:
        return name.split('_', 1)[1]

    return name


def normalize_suppl_dirname(dirname: str) -> str:
    """
    Normalize supplementary provision directory name for display.

    Examples:
        S51_L66 -> 昭和51年法律第66号
        H8_L110 -> 平成8年法律第110号
        R3_L24 -> 令和3年法律第24号
    """
    era_map = {
        'M': '明治',
        'T': '大正',
        'S': '昭和',
        'H': '平成',
        'R': '令和'
    }

    match = re.match(r'([MTSHR])(\d+)_L(\d+)', dirname)
    if match:
        era = era_map.get(match.group(1), match.group(1))
        year = match.group(2)
        law_num = match.group(3)
        return f"{era}{year}年法律第{law_num}号"

    # Already in Japanese format
    return dirname


def _get_law_file_name(law_dir: Path) -> Optional[str]:
    """Get the _law.md filename for a law directory."""
    law_files = list(law_dir.glob("*_law.md"))
    if law_files:
        return law_files[0].name
    return None


def _is_direct_child_of_law(article_path: Path, law_file_name: str) -> bool:
    """
    Check if an article's parent points to the law file (not chapter/section).

    Returns True if the article is a direct child of the law node.
    """
    try:
        doc = read_markdown_file(article_path)
        parent = doc.metadata.get("parent", "")
        # parent format: [[laws/{law_id}/{law_file_name}|{display}]]
        # or: [[laws/{law_id}/章/第N章.md]] for chapter children
        if law_file_name and law_file_name in parent:
            return True
        # Also check for _law.md pattern
        if "_law.md" in parent:
            return True
        return False
    except Exception:
        return False


def generate_links_for_law(law_dir: Path) -> str:
    """
    Generate markdown links content for a law directory.

    Only includes articles that are direct children of the law node
    (i.e., articles whose parent points to _law.md, not to chapter/section).
    This creates a proper tree structure where each node only shows
    its immediate children.

    Args:
        law_dir: Path to the law directory (e.g., Vault/laws/刑法)

    Returns:
        Markdown string with links to direct child articles only
    """
    main_dir = law_dir / "本文"
    chapter_dir = law_dir / "章"
    suppl_dir = law_dir / "附則"
    law_file_name = _get_law_file_name(law_dir)

    lines: List[str] = []

    # Chapter links - if chapters exist, show them as direct children
    if chapter_dir.exists():
        chapter_files = list(chapter_dir.glob('第*.md'))
        if chapter_files:
            # Sort chapters by number
            def chapter_sort_key(f):
                name = f.stem
                match = re.match(r'第(\d+)章(?:の(\d+))?', name)
                if match:
                    main = int(match.group(1))
                    sub = int(match.group(2)) if match.group(2) else 0
                    return (main, sub)
                return (999, 0)

            chapter_files.sort(key=chapter_sort_key)
            lines.append(f"\n## 構造\n")
            lines.append(f"\n### 章（{len(chapter_files)}章）\n")

            for f in chapter_files:
                display_name = f.stem
                lines.append(f"- [[章/{f.name}|{display_name}]]")

    # Main text links - only direct children of law node (when no chapters)
    if main_dir.exists():
        article_files = list(main_dir.glob('第*.md'))
        article_files.sort(key=lambda f: extract_article_sort_key(f.name))

        # Filter to only include articles that are direct children of the law
        direct_children = [
            f for f in article_files
            if _is_direct_child_of_law(f, law_file_name or "")
        ]

        if direct_children:
            lines.append(f"\n## 本則（{len(direct_children)}条）\n")

            for f in direct_children:
                display_name = f.stem  # Remove .md
                lines.append(f"- [[本文/{f.name}|{display_name}]]")

    # Supplementary provision links
    if suppl_dir.exists():
        kaisei_dir = suppl_dir / "改正法"

        if kaisei_dir.exists():
            suppl_subdirs = sorted([d for d in kaisei_dir.iterdir() if d.is_dir()])

            if suppl_subdirs:
                lines.append(f"\n## 附則（改正法: {len(suppl_subdirs)}件）\n")

                for subdir in suppl_subdirs:
                    display_name = normalize_suppl_dirname(subdir.name)
                    file_count = len(list(subdir.glob('*.md')))

                    files = sorted(subdir.glob('*.md'), key=lambda f: extract_article_sort_key(f.name))
                    if files:
                        first_file = files[0]
                        rel_path = f"附則/改正法/{subdir.name}/{first_file.name}"
                        if file_count == 1:
                            lines.append(f"- [[{rel_path}|{display_name}]]")
                        else:
                            lines.append(f"- [[{rel_path}|{display_name}]] ({file_count}条)")

        # Direct supplementary files
        direct_suppl_files = list(suppl_dir.glob('*.md'))
        if direct_suppl_files:
            direct_suppl_files.sort(key=lambda f: extract_article_sort_key(f.name))
            lines.append(f"\n### 現行附則\n")
            for f in direct_suppl_files:
                display_name = f.stem
                lines.append(f"- [[附則/{f.name}|{display_name}]]")

        # Initial supplementary directories
        init_suppl_dirs = [
            d for d in suppl_dir.iterdir()
            if d.is_dir() and d.name != "改正法" and (
                d.name.startswith("init_") or d.name.startswith("制定時附則")
            )
        ]
        if init_suppl_dirs:
            def init_sort_key(d):
                if d.name == "制定時附則":
                    return (0, 0)
                if d.name.startswith("制定時附則"):
                    try:
                        return (0, int(d.name.replace("制定時附則", "") or "1"))
                    except ValueError:
                        return (0, 999)
                if d.name.startswith("init_"):
                    try:
                        return (1, int(d.name.split('_')[1]))
                    except (IndexError, ValueError):
                        return (1, 999)
                return (2, 0)
            init_suppl_dirs.sort(key=init_sort_key)

            for init_dir in init_suppl_dirs:
                init_files = list(init_dir.glob('*.md'))
                if not init_files:
                    continue

                init_files.sort(key=lambda f: extract_article_sort_key(f.name))

                # Determine section name
                if init_dir.name.startswith("制定時附則"):
                    section_name = init_dir.name
                elif init_dir.name.startswith("init_"):
                    dir_index = int(init_dir.name.split('_')[1]) if '_' in init_dir.name else 0
                    if dir_index == 0:
                        section_name = "制定時附則"
                    else:
                        section_name = f"制定時附則{dir_index + 1}"
                else:
                    section_name = init_dir.name

                lines.append(f"\n### {section_name}（全{len(init_files)}条）\n")

                for f in init_files:
                    display_name = extract_display_name_from_init_file(f.name)
                    rel_path = f"附則/{init_dir.name}/{f.name}"
                    lines.append(f"- [[{rel_path}|{display_name}]]")

    return '\n'.join(lines)


def update_law_file_with_links(law_dir: Path) -> bool:
    """
    Update the parent law file with links to all articles.

    Args:
        law_dir: Path to the law directory (law_id based: e.g., 140AC0000000045/)

    Returns:
        True if update was successful, False otherwise
    """
    # 法令ファイルを検索（*_law.md 形式）
    law_files = list(law_dir.glob("*_law.md"))
    if not law_files:
        # フォールバック: 旧形式（{law_name}.md）
        law_name = law_dir.name
        law_file = law_dir / f"{law_name}.md"
        if not law_file.exists():
            return False
    else:
        law_file = law_files[0]  # 最初の _law.md ファイルを使用

    if not law_file.exists():
        return False

    content = law_file.read_text(encoding='utf-8')

    # Find existing links section start position
    # Include old format markers (## 構造, ### 章) to prevent duplication
    existing_links_start = None
    markers = [
        '## 本則',      # New format: main text section
        '## 附則',      # New format: supplementary section
        '## 構造',      # Old format: structure section
        '## Metadata',  # Some files have Metadata section
        '### 章',       # Old format: chapter list
        '### 現行附則', # Old format: current supplementary
        '\n#\n',        # Lone heading (bug remnant)
    ]
    for marker in markers:
        pos = content.find(marker)
        if pos != -1:
            if existing_links_start is None or pos < existing_links_start:
                existing_links_start = pos

    if existing_links_start is not None:
        # Remove existing links section
        base_content = content[:existing_links_start].rstrip()
    else:
        base_content = content.rstrip()

    # Generate new links
    links_content = generate_links_for_law(law_dir)

    new_content = base_content + '\n' + links_content + '\n'

    law_file.write_text(new_content, encoding='utf-8')
    return True
