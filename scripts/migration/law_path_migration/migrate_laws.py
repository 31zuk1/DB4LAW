#!/usr/bin/env python3
"""
Execute law directory migration based on manifest.

Renames law directories from Japanese names to law_id format,
renames representative md to law.md, and updates frontmatter.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Optional

import yaml


def parse_frontmatter(content: str) -> tuple[Optional[dict], str, str]:
    """
    Parse YAML frontmatter from markdown content.
    Returns (frontmatter_dict, frontmatter_raw, body).
    """
    if not content.startswith('---'):
        return None, '', content

    parts = content.split('---', 2)
    if len(parts) < 3:
        return None, '', content

    try:
        fm = yaml.safe_load(parts[1])
        return fm, parts[1], parts[2]
    except yaml.YAMLError:
        return None, parts[1], parts[2]


def serialize_frontmatter(fm: dict) -> str:
    """Serialize frontmatter dict to YAML string."""
    return yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)


def update_frontmatter(content: str, law_id: str, official_title: str, old_name: str) -> str:
    """
    Update frontmatter with law_id, official_title, and aliases.
    """
    fm, _, body = parse_frontmatter(content)
    if fm is None:
        fm = {}

    # Update law_id
    fm['law_id'] = law_id

    # Ensure official_title exists
    if 'official_title' not in fm:
        fm['official_title'] = official_title

    # Ensure title exists
    if 'title' not in fm:
        fm['title'] = official_title

    # Update aliases to include old directory name
    aliases = fm.get('aliases', [])
    if isinstance(aliases, str):
        aliases = [aliases]

    # Add old name if not already present
    if old_name and old_name not in aliases and old_name != official_title:
        aliases.append(old_name)

    # Add official_title if not in aliases
    if official_title not in aliases:
        aliases.insert(0, official_title)

    fm['aliases'] = aliases

    # Rebuild content
    new_content = '---\n' + serialize_frontmatter(fm) + '---' + body
    return new_content


def get_path_bytes(path_component: str) -> int:
    """Get UTF-8 byte length of a path component."""
    return len(path_component.encode('utf-8'))


def generate_short_name(original: str, max_bytes: int = 120) -> str:
    """Generate a shortened name using hash for long file names."""
    hash_val = hashlib.sha1(original.encode('utf-8')).hexdigest()[:8]

    # Try to keep extension
    if '.' in original:
        base, ext = original.rsplit('.', 1)
        return f"{hash_val}.{ext}"
    return hash_val


def rename_long_files(law_dir: Path, max_bytes: int = 120) -> list[dict]:
    """
    Rename files/directories with path components exceeding max_bytes.
    Returns list of rename operations performed.
    """
    renames = []

    # Process deepest paths first to avoid issues with parent renames
    all_paths = sorted(law_dir.rglob('*'), key=lambda p: len(p.parts), reverse=True)

    for path in all_paths:
        if not path.exists():  # May have been moved by parent rename
            continue

        name = path.name
        if get_path_bytes(name) > max_bytes:
            new_name = generate_short_name(name, max_bytes)
            new_path = path.parent / new_name

            # Avoid collision
            counter = 1
            while new_path.exists():
                if '.' in new_name:
                    base, ext = new_name.rsplit('.', 1)
                    new_path = path.parent / f"{base}_{counter}.{ext}"
                else:
                    new_path = path.parent / f"{new_name}_{counter}"
                counter += 1

            path.rename(new_path)
            renames.append({
                'old': str(path.relative_to(law_dir)),
                'new': str(new_path.relative_to(law_dir)),
                'original_name': name
            })

    return renames


def find_representative_md(law_dir: Path) -> Optional[Path]:
    """
    Find the representative markdown file for a law directory.
    Priority: folder name match > law.md > single md > largest md
    """
    md_files = list(law_dir.glob('*.md'))
    if not md_files:
        return None

    dir_name = law_dir.name

    # Priority 0: law.md (already migrated)
    law_md = law_dir / 'law.md'
    if law_md.exists():
        return law_md

    # Priority 1: File matching directory name
    for md in md_files:
        if md.stem == dir_name:
            return md

    # Priority 2: Single md file
    if len(md_files) == 1:
        return md_files[0]

    # Priority 3: Largest file
    return max(md_files, key=lambda f: f.stat().st_size)


def migrate_law_directory(
    vault_root: Path,
    record: dict,
    dry_run: bool = False
) -> dict:
    """
    Migrate a single law directory.
    Returns migration result with status and details.
    """
    old_path = vault_root / record['old_path']
    new_path = vault_root / record['new_path']
    law_id = record['law_id']
    official_title = record['official_title']
    # Extract old_name from old_path
    old_name = Path(record['old_path']).name
    # Find representative md dynamically
    rep_md_path = find_representative_md(old_path) if old_path.exists() else None
    representative_md = rep_md_path.name if rep_md_path else f"{old_name}.md"

    result = {
        'law_id': law_id,
        'old_path': record['old_path'],
        'new_path': record['new_path'],
        'status': 'pending',
        'actions': [],
        'errors': []
    }

    # Check if already migrated
    if old_path.name == law_id:
        result['status'] = 'already_migrated'
        result['actions'].append('Directory already uses law_id')

        # Still need to ensure law.md exists
        law_md = old_path / 'law.md'
        if not law_md.exists():
            # Find representative md and rename
            rep_md = old_path / representative_md
            if rep_md.exists() and not dry_run:
                content = rep_md.read_text(encoding='utf-8')
                content = update_frontmatter(content, law_id, official_title, old_name)
                law_md.write_text(content, encoding='utf-8')
                rep_md.unlink()
                result['actions'].append(f'Renamed {representative_md} -> law.md')
        return result

    if not old_path.exists():
        result['status'] = 'error'
        result['errors'].append(f'Source directory does not exist: {old_path}')
        return result

    if new_path.exists() and new_path != old_path:
        result['status'] = 'error'
        result['errors'].append(f'Target directory already exists: {new_path}')
        return result

    if dry_run:
        result['status'] = 'dry_run'
        result['actions'].append(f'Would rename: {old_path.name} -> {law_id}')
        result['actions'].append(f'Would rename: {representative_md} -> law.md')
        return result

    try:
        # Step 1: Rename long files within directory first
        long_file_renames = rename_long_files(old_path)
        if long_file_renames:
            result['actions'].append(f'Renamed {len(long_file_renames)} long file(s)')
            result['long_file_renames'] = long_file_renames

        # Step 2: Update frontmatter in representative md
        rep_md_path = old_path / representative_md
        if rep_md_path.exists():
            content = rep_md_path.read_text(encoding='utf-8')
            content = update_frontmatter(content, law_id, official_title, old_name)
            rep_md_path.write_text(content, encoding='utf-8')
            result['actions'].append('Updated frontmatter')

            # Step 3: Rename representative md to law.md
            law_md_path = old_path / 'law.md'
            if rep_md_path != law_md_path:
                rep_md_path.rename(law_md_path)
                result['actions'].append(f'Renamed {representative_md} -> law.md')
        else:
            result['errors'].append(f'Representative md not found: {representative_md}')

        # Step 4: Rename directory
        old_path.rename(new_path)
        result['actions'].append(f'Renamed directory: {old_name} -> {law_id}')

        result['status'] = 'success'

    except Exception as e:
        result['status'] = 'error'
        result['errors'].append(str(e))

    return result


def load_manifest(manifest_path: Path) -> list[dict]:
    """Load manifest from JSONL file."""
    records = []
    with open(manifest_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Execute law directory migration')
    parser.add_argument('--vault', type=Path, default=Path('Vault'),
                        help='Path to Vault directory')
    parser.add_argument('--manifest', type=Path, default=None,
                        help='Path to manifest.jsonl (default: Vault/_index/manifest.jsonl)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of migrations (for testing)')
    parser.add_argument('--output', type=Path, default=None,
                        help='Output migration log path')

    args = parser.parse_args()

    vault_root = args.vault.resolve()
    manifest_path = args.manifest or (vault_root / '_index' / 'manifest.jsonl')

    if not manifest_path.exists():
        print(f"ERROR: Manifest not found: {manifest_path}")
        print("Run generate_manifest.py first.")
        return 1

    print(f"Loading manifest from {manifest_path}...")
    records = load_manifest(manifest_path)
    print(f"Loaded {len(records)} records")

    # Filter to only those needing migration
    to_migrate = [r for r in records if r.get('needs_migration', True)]
    print(f"Need migration: {len(to_migrate)}")

    if args.limit:
        to_migrate = to_migrate[:args.limit]
        print(f"Limited to: {len(to_migrate)}")

    if args.dry_run:
        print("\n=== DRY RUN MODE ===\n")

    results = []
    success = 0
    errors = 0
    skipped = 0

    for i, record in enumerate(to_migrate):
        print(f"[{i+1}/{len(to_migrate)}] {record['old_path'][:50]}...")

        result = migrate_law_directory(vault_root, record, dry_run=args.dry_run)
        results.append(result)

        if result['status'] == 'success':
            success += 1
            print(f"  -> {result['law_id']} ✓")
        elif result['status'] == 'dry_run':
            success += 1
            print(f"  -> Would migrate to {result['law_id']}")
        elif result['status'] == 'already_migrated':
            skipped += 1
            print(f"  -> Already migrated")
        else:
            errors += 1
            print(f"  -> ERROR: {result['errors']}")

    print(f"\n{'='*60}")
    print(f"Migration Summary:")
    print(f"  Success: {success}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")

    # Write migration log
    if args.output:
        log_path = args.output
    else:
        log_path = vault_root / '_index' / 'migration_log.jsonl'

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'w', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
    print(f"\nMigration log written to: {log_path}")

    return 1 if errors > 0 else 0


if __name__ == '__main__':
    exit(main())
