#!/usr/bin/env python3
"""
One-shot script to fix broken YAML frontmatter in parent law files.

Fixes:
  - `---as_of:` -> `---\nas_of:`
  - `----as_of:` -> `---\nas_of:`
  - Any `---{yaml_key}:` pattern without newline after opening `---`

Target:
  - Only parent law files: Vault/laws/<law>/<law>.md
  - Does NOT touch article files (本文/*.md, 附則/*.md)

Usage:
  python fix_frontmatter.py --dry-run   # Preview changes
  python fix_frontmatter.py --apply     # Apply changes
"""

import argparse
import re
from pathlib import Path


def fix_frontmatter(content: str) -> tuple[str, bool]:
    """
    Fix broken frontmatter where opening --- is not followed by newline.

    Returns:
        (fixed_content, was_changed)
    """
    # Pattern: `---` followed by YAML key (not newline)
    # e.g., `---as_of:`, `----as_of:`, `---domain:`
    pattern = r'^-{3,}([a-zA-Z_][a-zA-Z0-9_]*):'

    match = re.match(pattern, content)
    if match:
        # Replace with proper format: ---\n{key}:
        key = match.group(1)
        fixed_content = re.sub(pattern, f'---\n{key}:', content, count=1)
        return fixed_content, True

    return content, False


def find_parent_law_files(vault_path: Path) -> list[Path]:
    """Find all parent law files (law_name/law_name.md)."""
    laws_dir = vault_path / "laws"
    if not laws_dir.exists():
        return []

    parent_files = []
    for law_dir in laws_dir.iterdir():
        if not law_dir.is_dir():
            continue
        parent_file = law_dir / f"{law_dir.name}.md"
        if parent_file.exists():
            parent_files.append(parent_file)

    return sorted(parent_files)


def main():
    parser = argparse.ArgumentParser(
        description="Fix broken YAML frontmatter in parent law files"
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--apply', action='store_true',
        help='Apply fixes to files'
    )
    parser.add_argument(
        '--vault', type=Path, default=Path(__file__).parent.parent.parent / "Vault",
        help='Path to Vault directory (default: PROJECT_ROOT/Vault)'
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Must specify either --dry-run or --apply")

    vault_path = args.vault
    if not vault_path.exists():
        print(f"Error: Vault not found at {vault_path}")
        return 1

    parent_files = find_parent_law_files(vault_path)
    print(f"Found {len(parent_files)} parent law files")

    fixed_count = 0
    for file_path in parent_files:
        content = file_path.read_text(encoding='utf-8')
        fixed_content, was_changed = fix_frontmatter(content)

        if was_changed:
            fixed_count += 1
            law_name = file_path.parent.name

            if args.dry_run:
                print(f"[DRY-RUN] Would fix: {law_name}/{file_path.name}")
                # Show first few lines before/after
                before_lines = content.split('\n')[:3]
                after_lines = fixed_content.split('\n')[:3]
                print(f"  Before: {before_lines[0]}")
                print(f"  After:  {after_lines[0]}")
            else:
                file_path.write_text(fixed_content, encoding='utf-8')
                print(f"Fixed: {law_name}/{file_path.name}")

    print(f"\n{'Would fix' if args.dry_run else 'Fixed'}: {fixed_count} files")
    return 0


if __name__ == '__main__':
    exit(main())
