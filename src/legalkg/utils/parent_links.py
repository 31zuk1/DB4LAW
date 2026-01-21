"""
Utility functions for generating parent law file links.
"""

import re
from pathlib import Path
from typing import List, Tuple


def extract_article_sort_key(filename: str) -> Tuple[int, int, int]:
    """
    Extract sort key from article filename.

    Examples:
        第1条.md -> (1, 0, 0)
        第1条の2.md -> (1, 2, 0)
        第100条.md -> (100, 0, 0)
        第638:640条.md -> (638, 0, 640)  # Range format
        init_0_第1条.md -> (1, 0, 0)  # With prefix
    """
    name = filename.replace('.md', '')

    # Prefix format: {prefix}_第N条 or {prefix}_第N条のM
    match = re.match(r'.+_第(\d+)条(?:の(\d+))?$', name)
    if match:
        main_num = int(match.group(1))
        sub_num = int(match.group(2)) if match.group(2) else 0
        return (main_num, sub_num, 0)

    # Range format: 第N:M条
    match = re.match(r'第(\d+):(\d+)条', name)
    if match:
        start_num = int(match.group(1))
        end_num = int(match.group(2))
        return (start_num, 0, end_num)

    # 第N条 format
    match = re.match(r'第(\d+)条(?:の(\d+))?', name)
    if match:
        main_num = int(match.group(1))
        sub_num = int(match.group(2)) if match.group(2) else 0
        return (main_num, sub_num, 0)

    # 附則第N条 format
    match = re.match(r'附則第(\d+)条(?:の(\d+))?', name)
    if match:
        main_num = int(match.group(1))
        sub_num = int(match.group(2)) if match.group(2) else 0
        return (main_num, sub_num, 0)

    # Others (附則.md etc.)
    return (0, 0, 0)


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


def generate_links_for_law(law_dir: Path) -> str:
    """
    Generate markdown links content for a law directory.

    Args:
        law_dir: Path to the law directory (e.g., Vault/laws/刑法)

    Returns:
        Markdown string with links to all articles
    """
    main_dir = law_dir / "本文"
    suppl_dir = law_dir / "附則"

    lines: List[str] = []

    # Main text links
    if main_dir.exists():
        article_files = list(main_dir.glob('第*.md'))
        article_files.sort(key=lambda f: extract_article_sort_key(f.name))

        lines.append(f"\n## 本則（全{len(article_files)}条）\n")

        for f in article_files:
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
        law_dir: Path to the law directory

    Returns:
        True if update was successful, False otherwise
    """
    law_name = law_dir.name
    law_file = law_dir / f"{law_name}.md"

    if not law_file.exists():
        return False

    content = law_file.read_text(encoding='utf-8')

    # Find existing links section start position
    existing_links_start = None
    for marker in ['## 本則', '## 附則']:
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
