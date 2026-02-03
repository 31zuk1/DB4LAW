#!/usr/bin/env python3
"""
Rename law.md files to {first 20 chars of title}_law.md for Graph-view clarity.

This script:
1. Reads each law.md file and extracts the title from frontmatter
2. Renames to {title[:20]}_law.md format
3. Generates a mapping file for wikilink updates
"""

import re
import json
from pathlib import Path
from typing import Optional


def extract_title_from_frontmatter(content: str) -> Optional[str]:
    """Extract title field from YAML frontmatter."""
    # Match frontmatter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return None

    frontmatter = match.group(1)

    # Extract title field
    title_match = re.search(r'^title:\s*(.+)$', frontmatter, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
        # Remove quotes if present
        if (title.startswith('"') and title.endswith('"')) or \
           (title.startswith("'") and title.endswith("'")):
            title = title[1:-1]
        return title

    return None


def sanitize_filename(title: str, max_chars: int = 20) -> str:
    """
    Sanitize title for use in filename.
    - Take first max_chars characters
    - Replace problematic characters
    """
    # Take first N characters
    truncated = title[:max_chars]

    # Replace characters that are problematic in filenames
    # Keep most Japanese characters, but replace: / \ : * ? " < > |
    sanitized = re.sub(r'[/\\:*?"<>|]', '_', truncated)

    return sanitized


def scan_law_files(vault_root: Path) -> list[dict]:
    """
    Scan all law.md files and generate rename mapping.

    Returns list of dicts with:
    - law_id: directory name (law ID)
    - old_path: current path (laws/{law_id}/law.md)
    - new_filename: new filename ({title}_law.md)
    - new_path: new path (laws/{law_id}/{title}_law.md)
    - title: original title
    """
    laws_dir = vault_root / 'laws'
    mappings = []

    for law_dir in sorted(laws_dir.iterdir()):
        if not law_dir.is_dir():
            continue

        law_md = law_dir / 'law.md'
        if not law_md.exists():
            continue

        try:
            content = law_md.read_text(encoding='utf-8')
        except Exception as e:
            print(f"WARNING: Cannot read {law_md}: {e}")
            continue

        title = extract_title_from_frontmatter(content)
        if not title:
            print(f"WARNING: No title found in {law_md}")
            continue

        # Generate new filename
        sanitized_title = sanitize_filename(title)
        new_filename = f"{sanitized_title}_law.md"

        law_id = law_dir.name
        mappings.append({
            'law_id': law_id,
            'old_path': f"laws/{law_id}/law.md",
            'new_filename': new_filename,
            'new_path': f"laws/{law_id}/{new_filename}",
            'title': title
        })

    return mappings


def rename_files(vault_root: Path, mappings: list[dict], dry_run: bool = True) -> int:
    """Rename law.md files according to mappings."""
    renamed = 0

    for m in mappings:
        old_file = vault_root / m['old_path']
        new_file = vault_root / m['new_path']

        if not old_file.exists():
            continue

        if dry_run:
            print(f"Would rename: {m['old_path']} -> {m['new_filename']}")
        else:
            old_file.rename(new_file)
            renamed += 1

    return renamed


def write_mapping_file(mappings: list[dict], output_path: Path):
    """Write mapping file for wikilink updates."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for m in mappings:
            f.write(json.dumps(m, ensure_ascii=False) + '\n')

    print(f"Mapping file written to: {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Rename law.md files to include title prefix')
    parser.add_argument('--vault', type=Path, default=Path('Vault'),
                        help='Path to Vault directory')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be renamed without making changes')
    parser.add_argument('--apply', action='store_true',
                        help='Actually rename the files')
    parser.add_argument('--mapping-output', type=Path, default=None,
                        help='Output path for mapping file')

    args = parser.parse_args()

    vault_root = args.vault.resolve()

    if not args.dry_run and not args.apply:
        print("ERROR: Specify --dry-run or --apply")
        return 1

    print(f"Scanning law.md files in {vault_root}...")
    mappings = scan_law_files(vault_root)
    print(f"Found {len(mappings)} law.md files to rename")

    # Write mapping file
    mapping_path = args.mapping_output or (vault_root / '_index' / 'law_rename_mapping.jsonl')
    write_mapping_file(mappings, mapping_path)

    # Show sample
    print("\nSample renames:")
    for m in mappings[:10]:
        print(f"  {m['old_path']} -> {m['new_filename']}")

    if args.dry_run:
        print(f"\nDry run: would rename {len(mappings)} files")
        return 0

    # Actually rename
    renamed = rename_files(vault_root, mappings, dry_run=False)
    print(f"\nRenamed {renamed} files")

    return 0


if __name__ == '__main__':
    exit(main())
