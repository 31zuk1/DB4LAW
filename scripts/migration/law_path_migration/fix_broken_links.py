#!/usr/bin/env python3
"""
Fix broken wikilinks after law directory migration.

Replaces old Japanese path references with new law_id paths.
"""

import json
import re
from pathlib import Path
from typing import Optional


def load_path_mapping(vault_root: Path) -> dict[str, str]:
    """
    Load mapping from old paths to new paths from manifest.
    Returns dict: old_dir_name -> law_id
    """
    manifest_path = vault_root / '_index' / 'manifest.jsonl'
    mapping = {}

    if not manifest_path.exists():
        print(f"WARNING: Manifest not found: {manifest_path}")
        return mapping

    with open(manifest_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            old_path = record.get('old_path', '')
            law_id = record.get('law_id', '')

            if old_path and law_id:
                # Extract old directory name from path
                # old_path is like "laws/日本語名"
                old_dir_name = old_path.replace('laws/', '')
                mapping[old_dir_name] = law_id

    return mapping


def fix_wikilinks_in_content(content: str, mapping: dict[str, str]) -> tuple[str, int]:
    """
    Fix wikilinks in content using the path mapping.
    Returns (new_content, fix_count).
    """
    fix_count = 0

    # Pattern to match wikilinks: [[path]] or [[path|alias]]
    # We need to replace paths like [[laws/日本語名/...]] with [[laws/law_id/...]]
    def replace_link(match):
        nonlocal fix_count
        full_match = match.group(0)
        link_content = match.group(1)
        alias_part = match.group(2) or ''

        # Check if this is a laws/ path
        if not link_content.startswith('laws/'):
            return full_match

        # Extract the law directory name
        parts = link_content.split('/')
        if len(parts) < 2:
            return full_match

        old_law_dir = parts[1]

        # Check if we have a mapping for this
        if old_law_dir in mapping:
            new_law_id = mapping[old_law_dir]
            # Replace the old directory name with new law_id
            parts[1] = new_law_id
            new_link = '/'.join(parts)

            fix_count += 1

            if alias_part:
                return f'[[{new_link}{alias_part}]]'
            else:
                return f'[[{new_link}]]'

        return full_match

    # Match [[...]] or [[...|...]]
    pattern = re.compile(r'\[\[([^\]|]+)(\|[^\]]+)?\]\]')
    new_content = pattern.sub(replace_link, content)

    return new_content, fix_count


def fix_links_in_file(file_path: Path, mapping: dict[str, str], dry_run: bool = False) -> int:
    """
    Fix wikilinks in a single file.
    Returns number of fixes made.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"ERROR: Cannot read {file_path}: {e}")
        return 0

    new_content, fix_count = fix_wikilinks_in_content(content, mapping)

    if fix_count > 0 and not dry_run:
        try:
            file_path.write_text(new_content, encoding='utf-8')
        except Exception as e:
            print(f"ERROR: Cannot write {file_path}: {e}")
            return 0

    return fix_count


def fix_all_links(vault_root: Path, mapping: dict[str, str],
                  only_prefix: str = None, dry_run: bool = False) -> dict:
    """
    Fix all wikilinks in the vault.
    Returns statistics.
    """
    stats = {
        'files_scanned': 0,
        'files_modified': 0,
        'links_fixed': 0
    }

    scan_root = vault_root
    if only_prefix:
        scan_root = vault_root / only_prefix

    if not scan_root.exists():
        print(f"WARNING: Scan root does not exist: {scan_root}")
        return stats

    for md_file in scan_root.rglob('*.md'):
        stats['files_scanned'] += 1

        fix_count = fix_links_in_file(md_file, mapping, dry_run)

        if fix_count > 0:
            stats['files_modified'] += 1
            stats['links_fixed'] += fix_count

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Fix broken wikilinks after migration')
    parser.add_argument('--vault', type=Path, default=Path('Vault'),
                        help='Path to Vault directory')
    parser.add_argument('--only-prefix', type=str, default=None,
                        help='Only fix files under this prefix (e.g., "laws/")')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be fixed without making changes')

    args = parser.parse_args()

    vault_root = args.vault.resolve()

    print("Loading path mapping from manifest...")
    mapping = load_path_mapping(vault_root)
    print(f"Loaded {len(mapping)} path mappings")

    if not mapping:
        print("ERROR: No mappings loaded. Cannot proceed.")
        return 1

    if args.dry_run:
        print("\n=== DRY RUN MODE ===\n")

    print(f"Scanning files in {vault_root}...")
    if args.only_prefix:
        print(f"  Limited to: {args.only_prefix}")

    stats = fix_all_links(vault_root, mapping, args.only_prefix, args.dry_run)

    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Files scanned: {stats['files_scanned']}")
    print(f"  Files {'would be ' if args.dry_run else ''}modified: {stats['files_modified']}")
    print(f"  Links {'would be ' if args.dry_run else ''}fixed: {stats['links_fixed']}")
    print(f"{'='*60}")

    return 0


if __name__ == '__main__':
    exit(main())
