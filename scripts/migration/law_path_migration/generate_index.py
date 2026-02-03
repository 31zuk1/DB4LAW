#!/usr/bin/env python3
"""
Generate law indexes after migration.

Creates:
- Vault/_index/laws.json - Machine-readable index
- Vault/laws_index.md - Human-readable Obsidian index
"""

import json
from pathlib import Path
from typing import Optional

import yaml


def parse_frontmatter(content: str) -> Optional[dict]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith('---'):
        return None

    parts = content.split('---', 2)
    if len(parts) < 3:
        return None

    try:
        return yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None


def find_law_file(law_dir: Path) -> Optional[Path]:
    """
    Find the law file in a directory.
    Looks for *_law.md pattern.
    """
    # Find *_law.md files
    law_files = list(law_dir.glob('*_law.md'))
    if law_files:
        return law_files[0]
    return None


def scan_migrated_laws(vault_root: Path) -> list[dict]:
    """
    Scan migrated law directories and collect index information.
    """
    laws_dir = vault_root / 'laws'
    records = []

    for law_dir in sorted(laws_dir.iterdir()):
        if not law_dir.is_dir():
            continue

        # Skip special directories
        if law_dir.name.startswith('.') or law_dir.name == '_index':
            continue

        law_md = find_law_file(law_dir)
        if not law_md:
            print(f"WARNING: No *_law.md in {law_dir}")
            continue

        try:
            content = law_md.read_text(encoding='utf-8')
        except Exception as e:
            print(f"ERROR: Cannot read {law_md}: {e}")
            continue

        fm = parse_frontmatter(content)
        if fm is None:
            fm = {}

        law_id = law_dir.name
        official_title = fm.get('official_title') or fm.get('title') or law_id
        aliases = fm.get('aliases', [])
        if isinstance(aliases, str):
            aliases = [aliases]

        # Get tier info
        tier = fm.get('tier', 0)

        # Get law number
        law_no = fm.get('law_no', '')

        # Get promulgation date
        promulgation_date = fm.get('promulgation_date', '')

        # Get egov link
        egov_link = ''
        if isinstance(fm.get('links'), dict):
            egov_link = fm['links'].get('egov', '')
        elif fm.get('egov_law_id'):
            egov_link = f"https://laws.e-gov.go.jp/law/{fm['egov_law_id']}"

        record = {
            'law_id': law_id,
            'official_title': official_title,
            'aliases': aliases,
            'path': f"laws/{law_id}/{law_md.name}",
            'tier': tier,
            'law_no': law_no,
            'promulgation_date': promulgation_date,
            'egov_link': egov_link
        }

        records.append(record)

    return records


def write_json_index(records: list[dict], output_path: Path):
    """Write machine-readable JSON index."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    index = {
        'version': '1.0',
        'count': len(records),
        'laws': records
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def write_markdown_index(records: list[dict], output_path: Path):
    """Write human-readable Obsidian markdown index."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        '---',
        'title: 法令索引',
        'type: index',
        '---',
        '',
        '# 法令索引',
        '',
        f'総法令数: {len(records)}',
        '',
        '## 法令一覧',
        '',
        '| 法令名 | 法令番号 | Tier |',
        '|--------|----------|------|',
    ]

    # Sort by official_title
    sorted_records = sorted(records, key=lambda r: r['official_title'])

    for r in sorted_records:
        title = r['official_title']
        # Truncate long titles for table display
        if len(title) > 50:
            title = title[:47] + '...'

        law_no = r['law_no'] or '-'
        tier = r['tier']

        # Create wikilink
        link = f"[[{r['path']}|{title}]]"

        lines.append(f"| {link} | {law_no} | {tier} |")

    lines.append('')
    lines.append('## Tier別集計')
    lines.append('')

    # Count by tier
    tier_counts = {}
    for r in records:
        t = r['tier']
        tier_counts[t] = tier_counts.get(t, 0) + 1

    for tier in sorted(tier_counts.keys()):
        lines.append(f'- Tier {tier}: {tier_counts[tier]} 件')

    lines.append('')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate law indexes')
    parser.add_argument('--vault', type=Path, default=Path('Vault'),
                        help='Path to Vault directory')
    parser.add_argument('--json-output', type=Path, default=None,
                        help='JSON index output path')
    parser.add_argument('--md-output', type=Path, default=None,
                        help='Markdown index output path')

    args = parser.parse_args()

    vault_root = args.vault.resolve()

    print(f"Scanning {vault_root / 'laws'}...")
    records = scan_migrated_laws(vault_root)
    print(f"Found {len(records)} laws")

    # Write JSON index
    json_path = args.json_output or (vault_root / '_index' / 'laws.json')
    write_json_index(records, json_path)
    print(f"JSON index written to: {json_path}")

    # Write Markdown index
    md_path = args.md_output or (vault_root / 'laws_index.md')
    write_markdown_index(records, md_path)
    print(f"Markdown index written to: {md_path}")

    # Summary
    tier_counts = {}
    for r in records:
        t = r['tier']
        tier_counts[t] = tier_counts.get(t, 0) + 1

    print(f"\nTier breakdown:")
    for tier in sorted(tier_counts.keys()):
        print(f"  Tier {tier}: {tier_counts[tier]}")

    return 0


if __name__ == '__main__':
    exit(main())
