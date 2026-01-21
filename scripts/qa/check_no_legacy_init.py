#!/usr/bin/env python3
"""
レガシー init_* 形式が残っていないことを検証するQAスクリプト

検出対象:
- ディレクトリ名: init_0, init_1, ... (init_* で始まる)
- ファイル名: init_0.md, init_1.md, ... (init_*.md)
- 旧形式ファイル名: init_0_第N条.md (init_*_第 で始まる)

Usage:
    python scripts/qa/check_no_legacy_init.py --vault ./Vault
    python scripts/qa/check_no_legacy_init.py --vault ./Vault --only-prefix laws/

Exit codes:
    0: レガシー形式なし（OK）
    1: レガシー形式が検出された（NG）
"""

import argparse
import re
import sys
from pathlib import Path


def find_legacy_init(vault_path: Path, only_prefix: str = None) -> dict:
    """
    レガシー init_* 形式を検出

    Returns:
        dict: {
            "dirs": [(path, name), ...],
            "files": [(path, name), ...],
            "prefixed_files": [(path, name), ...]
        }
    """
    results = {
        "dirs": [],
        "files": [],
        "prefixed_files": []
    }

    search_path = vault_path
    if only_prefix:
        search_path = vault_path / only_prefix

    if not search_path.exists():
        return results

    # init_* ディレクトリを検出
    for d in search_path.rglob("init_*"):
        if d.is_dir() and re.match(r'^init_\d+$', d.name):
            rel_path = d.relative_to(vault_path)
            results["dirs"].append((str(rel_path), d.name))

    # init_*.md ファイルを検出（ディレクトリ直下）
    for f in search_path.rglob("init_*.md"):
        if f.is_file():
            if re.match(r'^init_\d+\.md$', f.name):
                # init_0.md 形式
                rel_path = f.relative_to(vault_path)
                results["files"].append((str(rel_path), f.name))
            elif re.match(r'^init_\d+_第\d+条', f.name):
                # init_0_第N条.md 形式
                rel_path = f.relative_to(vault_path)
                results["prefixed_files"].append((str(rel_path), f.name))

    return results


def main():
    parser = argparse.ArgumentParser(
        description="レガシー init_* 形式が残っていないことを検証"
    )
    parser.add_argument('--vault', required=True, help='Vaultディレクトリのパス')
    parser.add_argument('--only-prefix', help='検索対象を絞るプレフィックス（例: laws/）')
    args = parser.parse_args()

    vault_path = Path(args.vault)
    if not vault_path.exists():
        print(f"エラー: {vault_path} が見つかりません")
        sys.exit(1)

    print(f"Scanning {vault_path}...")
    if args.only_prefix:
        print(f"  Prefix filter: {args.only_prefix}")

    results = find_legacy_init(vault_path, args.only_prefix)

    total_issues = (
        len(results["dirs"]) +
        len(results["files"]) +
        len(results["prefixed_files"])
    )

    print()
    print("=" * 50)
    print("レガシー init_* 検出結果")
    print("=" * 50)

    if results["dirs"]:
        print(f"\n【ディレクトリ】 {len(results['dirs'])} 件")
        for path, name in results["dirs"][:10]:
            print(f"  - {path}")
        if len(results["dirs"]) > 10:
            print(f"  ... 他 {len(results['dirs']) - 10} 件")

    if results["files"]:
        print(f"\n【単一ファイル (init_N.md)】 {len(results['files'])} 件")
        for path, name in results["files"][:10]:
            print(f"  - {path}")
        if len(results["files"]) > 10:
            print(f"  ... 他 {len(results['files']) - 10} 件")

    if results["prefixed_files"]:
        print(f"\n【プレフィックス付きファイル (init_N_第M条.md)】 {len(results['prefixed_files'])} 件")
        for path, name in results["prefixed_files"][:10]:
            print(f"  - {path}")
        if len(results["prefixed_files"]) > 10:
            print(f"  ... 他 {len(results['prefixed_files']) - 10} 件")

    print()
    print("=" * 50)
    print(f"  合計: {total_issues} 件")
    print("=" * 50)

    if total_issues > 0:
        print("\n✗ レガシー形式が検出されました")
        print("  → scripts/migration/migrate_init_to_japanese.py で移行してください")
        sys.exit(1)
    else:
        print("\n✓ レガシー形式は検出されませんでした")
        sys.exit(0)


if __name__ == '__main__':
    main()
