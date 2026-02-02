#!/usr/bin/env python3
"""
Generate broken links report after migration.

Scans all markdown files and checks wikilinks for validity.
Outputs report without auto-fixing.
"""

import re
from pathlib import Path
from typing import Optional


# Pattern to match wikilinks: [[path]] or [[path|alias]]
WIKILINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')


def extract_wikilinks(content: str) -> list[str]:
    """Extract all wikilink targets from markdown content."""
    return WIKILINK_PATTERN.findall(content)


def resolve_link(link: str, source_file: Path, vault_root: Path) -> Optional[Path]:
    """
    Resolve a wikilink to an absolute path.
    Returns None if the link cannot be resolved.
    """
    # Handle absolute paths (starting with /)
    if link.startswith('/'):
        target = vault_root / link[1:]
    else:
        # Relative to source file's directory
        target = source_file.parent / link

    # Normalize the path
    try:
        target = target.resolve()
    except Exception:
        return None

    # Check if it's within vault
    try:
        target.relative_to(vault_root)
    except ValueError:
        return None

    return target


def check_link_exists(target: Path) -> bool:
    """Check if target path exists (with or without .md extension)."""
    if target.exists():
        return True

    # Try adding .md extension
    if not target.suffix:
        md_target = target.with_suffix('.md')
        if md_target.exists():
            return True

    return False


def scan_broken_links(vault_root: Path, only_prefix: str = None) -> list[dict]:
    """
    Scan vault for broken wikilinks.

    Args:
        vault_root: Path to Vault directory
        only_prefix: Only scan files under this prefix (e.g., 'laws/')

    Returns:
        List of broken link records
    """
    broken_links = []

    scan_root = vault_root
    if only_prefix:
        scan_root = vault_root / only_prefix

    if not scan_root.exists():
        print(f"WARNING: Scan root does not exist: {scan_root}")
        return broken_links

    for md_file in scan_root.rglob('*.md'):
        try:
            content = md_file.read_text(encoding='utf-8')
        except Exception as e:
            print(f"WARNING: Cannot read {md_file}: {e}")
            continue

        links = extract_wikilinks(content)

        for link in links:
            # Skip external links
            if link.startswith('http://') or link.startswith('https://'):
                continue

            # Skip anchor-only links
            if link.startswith('#'):
                continue

            # Resolve and check
            target = resolve_link(link, md_file, vault_root)
            if target is None:
                broken_links.append({
                    'source_file': str(md_file.relative_to(vault_root)),
                    'link': link,
                    'reason': 'invalid_path'
                })
                continue

            if not check_link_exists(target):
                broken_links.append({
                    'source_file': str(md_file.relative_to(vault_root)),
                    'link': link,
                    'expected_target': str(target.relative_to(vault_root)),
                    'reason': 'target_not_found'
                })

    return broken_links


def write_report(broken_links: list[dict], output_path: Path):
    """Write broken links report to text file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"Broken Links Report\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"Total broken links: {len(broken_links)}\n\n")

        if not broken_links:
            f.write("No broken links found.\n")
            return

        # Group by source file
        by_source = {}
        for bl in broken_links:
            src = bl['source_file']
            if src not in by_source:
                by_source[src] = []
            by_source[src].append(bl)

        f.write(f"Files with broken links: {len(by_source)}\n\n")
        f.write("-" * 60 + "\n\n")

        for source, links in sorted(by_source.items()):
            f.write(f"## {source}\n")
            for bl in links:
                f.write(f"  - [[{bl['link']}]] ({bl['reason']})\n")
            f.write("\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate broken links report')
    parser.add_argument('--vault', type=Path, default=Path('Vault'),
                        help='Path to Vault directory')
    parser.add_argument('--only-prefix', type=str, default=None,
                        help='Only scan files under this prefix')
    parser.add_argument('--output', type=Path, default=None,
                        help='Output report path')

    args = parser.parse_args()

    vault_root = args.vault.resolve()

    print(f"Scanning for broken links in {vault_root}...")
    if args.only_prefix:
        print(f"  Limited to: {args.only_prefix}")

    broken_links = scan_broken_links(vault_root, args.only_prefix)
    print(f"Found {len(broken_links)} broken links")

    # Write report
    output_path = args.output or (vault_root / 'reports' / 'broken_links.txt')
    write_report(broken_links, output_path)
    print(f"Report written to: {output_path}")

    # Summary by reason
    reasons = {}
    for bl in broken_links:
        r = bl['reason']
        reasons[r] = reasons.get(r, 0) + 1

    if reasons:
        print(f"\nBy reason:")
        for r, count in sorted(reasons.items()):
            print(f"  {r}: {count}")

    return 0


if __name__ == '__main__':
    exit(main())
