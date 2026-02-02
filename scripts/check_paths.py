#!/usr/bin/env python3
"""
Path validation script for Vault/laws.

Checks:
1. laws/ direct children must be ASCII-only (law_id format)
2. No path component exceeds 120 bytes (UTF-8)
3. No relative path from Vault/ exceeds 200 bytes total

Exit codes:
- 0: All checks pass
- 1: Validation errors found
"""

import sys
from pathlib import Path


MAX_COMPONENT_BYTES = 120
MAX_PATH_BYTES = 200


def is_ascii_only(s: str) -> bool:
    """Check if string contains only ASCII characters."""
    return all(ord(c) < 128 for c in s)


def get_bytes(s: str) -> int:
    """Get UTF-8 byte length of string."""
    return len(s.encode('utf-8'))


def check_laws_directories(vault_root: Path) -> list[dict]:
    """
    Check that all direct children of laws/ are ASCII-only.
    """
    laws_dir = vault_root / 'laws'
    issues = []

    if not laws_dir.exists():
        return issues

    for item in laws_dir.iterdir():
        if not item.is_dir():
            continue

        # Skip special directories
        if item.name.startswith('.') or item.name == '_index':
            continue

        if not is_ascii_only(item.name):
            issues.append({
                'type': 'non_ascii_law_dir',
                'path': str(item.relative_to(vault_root)),
                'name': item.name,
                'message': f"Non-ASCII directory name in laws/: {item.name}"
            })

    return issues


def check_path_component_bytes(vault_root: Path) -> list[dict]:
    """
    Check that no path component exceeds MAX_COMPONENT_BYTES.
    """
    issues = []

    for path in vault_root.rglob('*'):
        rel_path = path.relative_to(vault_root)

        for part in rel_path.parts:
            byte_len = get_bytes(part)
            if byte_len > MAX_COMPONENT_BYTES:
                issues.append({
                    'type': 'component_too_long',
                    'path': str(rel_path),
                    'component': part,
                    'bytes': byte_len,
                    'limit': MAX_COMPONENT_BYTES,
                    'message': f"Path component exceeds {MAX_COMPONENT_BYTES} bytes: {part[:30]}... ({byte_len} bytes)"
                })
                break  # Only report once per path

    return issues


def check_total_path_bytes(vault_root: Path) -> list[dict]:
    """
    Check that no relative path exceeds MAX_PATH_BYTES total.
    """
    issues = []

    for path in vault_root.rglob('*'):
        rel_path = str(path.relative_to(vault_root))
        byte_len = get_bytes(rel_path)

        if byte_len > MAX_PATH_BYTES:
            issues.append({
                'type': 'path_too_long',
                'path': rel_path,
                'bytes': byte_len,
                'limit': MAX_PATH_BYTES,
                'message': f"Total path exceeds {MAX_PATH_BYTES} bytes: {rel_path[:50]}... ({byte_len} bytes)"
            })

    return issues


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Validate Vault paths')
    parser.add_argument('--vault', type=Path, default=Path('Vault'),
                        help='Path to Vault directory')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON')
    parser.add_argument('--skip-component-check', action='store_true',
                        help='Skip path component byte check (slow on large vaults)')
    parser.add_argument('--skip-total-check', action='store_true',
                        help='Skip total path byte check (slow on large vaults)')

    args = parser.parse_args()

    vault_root = args.vault.resolve()

    if not vault_root.exists():
        print(f"ERROR: Vault not found: {vault_root}")
        return 1

    all_issues = []

    # Check 1: ASCII-only law directories
    print("Checking laws/ directories for non-ASCII names...")
    issues = check_laws_directories(vault_root)
    all_issues.extend(issues)
    print(f"  Found {len(issues)} issue(s)")

    # Check 2: Path component bytes
    if not args.skip_component_check:
        print("Checking path component byte lengths...")
        issues = check_path_component_bytes(vault_root)
        all_issues.extend(issues)
        print(f"  Found {len(issues)} issue(s)")

    # Check 3: Total path bytes
    if not args.skip_total_check:
        print("Checking total path byte lengths...")
        issues = check_total_path_bytes(vault_root)
        all_issues.extend(issues)
        print(f"  Found {len(issues)} issue(s)")

    # Output results
    if args.json:
        result = {
            'vault': str(vault_root),
            'total_issues': len(all_issues),
            'issues': all_issues
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        if all_issues:
            print(f"FAILED: {len(all_issues)} issue(s) found\n")
            for issue in all_issues[:20]:  # Limit output
                print(f"  [{issue['type']}] {issue['message']}")
            if len(all_issues) > 20:
                print(f"  ... and {len(all_issues) - 20} more")
        else:
            print("PASSED: All path checks successful")
        print(f"{'='*60}")

    return 1 if all_issues else 0


if __name__ == '__main__':
    sys.exit(main())
