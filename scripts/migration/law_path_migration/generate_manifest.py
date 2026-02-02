#!/usr/bin/env python3
"""
Generate migration manifest for law directory restructuring.

Scans Vault/laws and creates a manifest mapping old paths to new law_id-based paths.
"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

import yaml


def normalize_title(title: str) -> str:
    """
    Normalize title for deterministic hash generation.
    NFKC normalization + whitespace compression + simple symbol normalization.
    """
    # NFKC normalization
    title = unicodedata.normalize('NFKC', title)
    # Whitespace compression
    title = re.sub(r'\s+', '', title)
    # Common symbol variations
    title = title.replace('（', '(').replace('）', ')')
    title = title.replace('「', '').replace('」', '')
    return title


def generate_hash_id(title: str, promulgation_date: str = "", source_url: str = "") -> str:
    """
    Generate deterministic hash-based ID when no official ID is available.
    Returns first 12 characters of SHA1 hash.
    """
    normalized = normalize_title(title)
    input_str = f"{normalized}|{promulgation_date or ''}|{source_url or ''}"
    hash_val = hashlib.sha1(input_str.encode('utf-8')).hexdigest()
    return hash_val[:12]


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


def find_representative_md(law_dir: Path) -> Optional[Path]:
    """
    Find the representative markdown file for a law directory.
    Priority: folder name match > single md > largest md
    """
    md_files = list(law_dir.glob('*.md'))
    if not md_files:
        return None

    dir_name = law_dir.name

    # Priority 1: File matching directory name
    for md in md_files:
        if md.stem == dir_name:
            return md

    # Priority 2: Single md file
    if len(md_files) == 1:
        return md_files[0]

    # Priority 3: Largest file
    return max(md_files, key=lambda f: f.stat().st_size)


def extract_law_id(frontmatter: dict, title: str, promulgation_date: str = "") -> str:
    """
    Extract or generate law_id from frontmatter.
    Priority: egov_law_id > law_id > id (JPLAW prefix stripped) > hash
    """
    # Priority 1: egov_law_id
    if frontmatter.get('egov_law_id'):
        return frontmatter['egov_law_id']

    # Priority 2: law_id
    if frontmatter.get('law_id'):
        return frontmatter['law_id']

    # Priority 3: id field (strip JPLAW: prefix)
    if frontmatter.get('id'):
        id_val = frontmatter['id']
        if id_val.startswith('JPLAW:'):
            return id_val[6:]
        return id_val

    # Priority 4: Generate hash
    source_url = frontmatter.get('links', {}).get('egov', '')
    return f"HASH_{generate_hash_id(title, promulgation_date, source_url)}"


def get_path_bytes(path_component: str) -> int:
    """Get UTF-8 byte length of a path component."""
    return len(path_component.encode('utf-8'))


def scan_laws_directory(vault_root: Path) -> list[dict]:
    """
    Scan Vault/laws directory and collect law information.
    Returns list of law records.
    """
    laws_dir = vault_root / 'laws'
    if not laws_dir.exists():
        raise FileNotFoundError(f"Laws directory not found: {laws_dir}")

    records = []

    for law_dir in sorted(laws_dir.iterdir()):
        if not law_dir.is_dir():
            continue

        # Skip hidden directories
        if law_dir.name.startswith('.'):
            continue

        # Skip _index directory if it exists
        if law_dir.name == '_index':
            continue

        representative_md = find_representative_md(law_dir)
        if not representative_md:
            print(f"WARNING: No markdown file found in {law_dir}")
            continue

        try:
            content = representative_md.read_text(encoding='utf-8')
        except Exception as e:
            print(f"ERROR: Cannot read {representative_md}: {e}")
            continue

        frontmatter = parse_frontmatter(content)
        if frontmatter is None:
            print(f"WARNING: No frontmatter in {representative_md}")
            frontmatter = {}

        # Extract title
        official_title = (
            frontmatter.get('official_title') or
            frontmatter.get('title') or
            law_dir.name
        )

        # Extract aliases
        aliases = frontmatter.get('aliases', [])
        if isinstance(aliases, str):
            aliases = [aliases]

        # Extract promulgation date
        promulgation_date = frontmatter.get('promulgation_date', '')

        # Determine law_id
        law_id = extract_law_id(frontmatter, official_title, promulgation_date)

        # Check if law_id is ASCII-only
        is_ascii = all(ord(c) < 128 for c in law_id)
        if not is_ascii:
            print(f"WARNING: Non-ASCII law_id generated for {law_dir.name}: {law_id}")
            # Generate hash instead
            source_url = frontmatter.get('links', {}).get('egov', '')
            law_id = f"HASH_{generate_hash_id(official_title, promulgation_date, source_url)}"

        # Collect all files in directory that may need renaming
        long_files = []
        for f in law_dir.rglob('*'):
            if f.is_file():
                for part in f.relative_to(law_dir).parts:
                    if get_path_bytes(part) > 120:
                        long_files.append({
                            'path': str(f.relative_to(law_dir)),
                            'bytes': get_path_bytes(part),
                            'component': part
                        })
                        break

        record = {
            'old_dir_name': law_dir.name,
            'old_path': str(law_dir.relative_to(vault_root)),
            'representative_md': representative_md.name,
            'law_id': law_id,
            'official_title': official_title,
            'aliases': aliases,
            'new_path': f"laws/{law_id}",
            'new_md_path': f"laws/{law_id}/law.md",
            'old_dir_bytes': get_path_bytes(law_dir.name),
            'long_files': long_files,
            'frontmatter': frontmatter
        }

        records.append(record)

    return records


def check_collisions(records: list[dict]) -> dict[str, list[dict]]:
    """Check for law_id collisions."""
    id_map = {}
    for record in records:
        law_id = record['law_id']
        if law_id not in id_map:
            id_map[law_id] = []
        id_map[law_id].append(record)

    collisions = {k: v for k, v in id_map.items() if len(v) > 1}
    return collisions


def write_manifest(records: list[dict], output_path: Path):
    """Write manifest as JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for record in records:
            # Create a cleaner version for the manifest
            manifest_record = {
                'old_path': record['old_path'],
                'law_id': record['law_id'],
                'official_title': record['official_title'],
                'new_path': record['new_path'],
                'new_md_path': record['new_md_path'],
                'old_dir_bytes': record['old_dir_bytes'],
                'needs_migration': record['old_dir_name'] != record['law_id'],
            }
            if record['long_files']:
                manifest_record['long_files_note'] = record['long_files']

            f.write(json.dumps(manifest_record, ensure_ascii=False) + '\n')


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate migration manifest')
    parser.add_argument('--vault', type=Path, default=Path('Vault'),
                        help='Path to Vault directory')
    parser.add_argument('--output', type=Path, default=None,
                        help='Output manifest path (default: Vault/_index/manifest.jsonl)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print summary without writing')

    args = parser.parse_args()

    vault_root = args.vault.resolve()
    output_path = args.output or (vault_root / '_index' / 'manifest.jsonl')

    print(f"Scanning {vault_root / 'laws'}...")
    records = scan_laws_directory(vault_root)
    print(f"Found {len(records)} law directories")

    # Check for collisions
    collisions = check_collisions(records)
    if collisions:
        print("\n" + "=" * 60)
        print("ERROR: law_id collisions detected!")
        print("=" * 60)
        for law_id, conflicting in collisions.items():
            print(f"\nlaw_id: {law_id}")
            for r in conflicting:
                print(f"  - {r['old_dir_name']}")
                print(f"    title: {r['official_title'][:60]}...")
        print("\nCannot proceed with collisions. Aborting.")
        return 1

    # Statistics
    needs_migration = sum(1 for r in records if r['old_dir_name'] != r['law_id'])
    long_dirs = sum(1 for r in records if r['old_dir_bytes'] > 255)
    hash_ids = sum(1 for r in records if r['law_id'].startswith('HASH_'))

    print(f"\nStatistics:")
    print(f"  Total laws: {len(records)}")
    print(f"  Need migration: {needs_migration}")
    print(f"  Directories > 255 bytes: {long_dirs}")
    print(f"  Hash-based IDs: {hash_ids}")

    if args.dry_run:
        print("\nDry run - not writing manifest")
        # Show sample
        print("\nSample records:")
        for r in records[:5]:
            print(f"  {r['old_dir_name'][:40]}... -> {r['law_id']}")
        return 0

    write_manifest(records, output_path)
    print(f"\nManifest written to: {output_path}")

    return 0


if __name__ == '__main__':
    exit(main())
