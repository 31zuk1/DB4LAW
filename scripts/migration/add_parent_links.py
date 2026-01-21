#!/usr/bin/env python3
"""
法律の親ファイル(.md)に本文・附則へのwikiリンクを追加するスクリプト

Usage:
    python add_parent_links.py --law 刑法
    python add_parent_links.py --law 民法 --dry-run
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.utils.parent_links import (
    generate_links_for_law,
    update_law_file_with_links,
)


def update_law_file(law_dir: Path, dry_run: bool = False) -> bool:
    """法律ファイルを更新"""

    law_name = law_dir.name
    law_file = law_dir / f"{law_name}.md"

    if not law_file.exists():
        print(f"エラー: {law_file} が見つかりません")
        return False

    if dry_run:
        links_content = generate_links_for_law(law_dir)
        print(f"[DRY-RUN] {law_file.name} を更新します")
        print(f"リンク数: {links_content.count('[[')}")
        print("---")
        print(links_content[:500] + "..." if len(links_content) > 500 else links_content)
        return True
    else:
        success = update_law_file_with_links(law_dir)
        if success:
            links_content = generate_links_for_law(law_dir)
            print(f"✓ {law_file.name} を更新しました（リンク数: {links_content.count('[[')}）")
        return success


def main():
    parser = argparse.ArgumentParser(description="法律の親ファイルにリンクを追加")
    parser.add_argument('--law', required=True, help='対象の法律名（例: 民法）')
    parser.add_argument('--dry-run', action='store_true', help='Dry-runモード')
    args = parser.parse_args()

    vault_path = Path(__file__).parent.parent.parent / "Vault" / "laws"
    law_dir = vault_path / args.law

    if not law_dir.exists():
        print(f"エラー: ディレクトリが見つかりません: {law_dir}")
        return

    update_law_file(law_dir, args.dry_run)


if __name__ == '__main__':
    main()
