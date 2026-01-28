#!/usr/bin/env python3
"""
DB4LAW: 改正法断片のリンク修正スクリプト

改正法断片（type: amendment_fragment）ファイル内の誤ったWikiLinkを修正する。

修正内容:
- 裸の「第N条」参照をリンク解除
- 「附則第N条」参照をリンク解除
- 外部法令（Vault非存在）への参照をリンク解除
- 法令名付き参照は正しくリンク化

Usage:
    # dry-run
    python scripts/migration/fix_amendment_fragment_links.py --law 民事訴訟法

    # apply
    python scripts/migration/fix_amendment_fragment_links.py --law 民事訴訟法 --apply
"""

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.core.tier2 import EdgeExtractor, set_vault_root, clear_vault_caches
from legalkg.utils.markdown import read_markdown_file, write_markdown_file
from legalkg.utils.patterns import strip_wikilinks


@dataclass
class ChangeRecord:
    file_path: str
    old_link_count: int
    new_link_count: int
    status: str  # changed, unchanged, error
    error_message: Optional[str] = None


def count_wikilinks(text: str) -> int:
    """WikiLinkの数をカウント"""
    import re
    return len(re.findall(r'\[\[', text))


def process_file(
    file_path: Path,
    vault_root: Path,
    dry_run: bool,
) -> ChangeRecord:
    """単一ファイルを処理"""
    rel_path = str(file_path.relative_to(vault_root))

    try:
        doc = read_markdown_file(file_path)

        # amendment_fragment のみ対象
        if doc.metadata.get('type') != 'amendment_fragment':
            return ChangeRecord(
                file_path=rel_path,
                old_link_count=0,
                new_link_count=0,
                status="skipped",
                error_message="Not amendment_fragment",
            )

        law_name = doc.metadata.get('law_name', '')
        if not law_name:
            return ChangeRecord(
                file_path=rel_path,
                old_link_count=0,
                new_link_count=0,
                status="error",
                error_message="No law_name in metadata",
            )

        old_link_count = count_wikilinks(doc.body)

        # WikiLinkを削除してプレーンテキストに戻す
        plain_body = strip_wikilinks(doc.body)

        # 新しいロジックでWikiLinkを再生成
        extractor = EdgeExtractor(vault_root=vault_root)
        new_body = extractor.replace_refs(
            plain_body,
            law_name,
            is_amendment_fragment=True
        )

        new_link_count = count_wikilinks(new_body)

        # 変更があるかチェック
        if doc.body.strip() == new_body.strip():
            return ChangeRecord(
                file_path=rel_path,
                old_link_count=old_link_count,
                new_link_count=new_link_count,
                status="unchanged",
            )

        if not dry_run:
            doc.body = new_body
            write_markdown_file(file_path, doc)

        return ChangeRecord(
            file_path=rel_path,
            old_link_count=old_link_count,
            new_link_count=new_link_count,
            status="changed",
        )

    except Exception as e:
        return ChangeRecord(
            file_path=rel_path,
            old_link_count=0,
            new_link_count=0,
            status="error",
            error_message=str(e),
        )


def main():
    parser = argparse.ArgumentParser(
        description="改正法断片のリンク修正"
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path("./Vault"),
        help="Vault ディレクトリ",
    )
    parser.add_argument(
        "--law",
        type=str,
        help="単一法令に絞る",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="変更を適用しない（デフォルト）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="変更を適用する",
    )

    args = parser.parse_args()
    dry_run = not args.apply

    vault_root = args.vault.resolve()
    laws_dir = vault_root / "laws"
    if not laws_dir.exists():
        print(f"Error: laws directory not found: {laws_dir}")
        sys.exit(1)

    # Vault キャッシュを初期化
    set_vault_root(vault_root)

    # 対象法令
    if args.law:
        law_dirs = [laws_dir / args.law]
        if not law_dirs[0].exists():
            print(f"Error: law not found: {law_dirs[0]}")
            sys.exit(1)
    else:
        law_dirs = sorted([d for d in laws_dir.iterdir() if d.is_dir()])

    print(f"{'[DRY-RUN] ' if dry_run else ''}Processing amendment fragments...")
    print()

    records: list[ChangeRecord] = []
    total_files = 0

    for law_dir in law_dirs:
        law_name = law_dir.name
        fuzoku_dir = law_dir / "附則"

        if not fuzoku_dir.exists():
            continue

        # 附則ディレクトリ内のすべてのファイルを処理
        for md_file in fuzoku_dir.rglob("*.md"):
            total_files += 1
            record = process_file(md_file, vault_root, dry_run)
            records.append(record)

            if record.status == "changed":
                print(f"  {record.file_path}: {record.old_link_count} → {record.new_link_count} links")
            elif record.status == "error":
                print(f"  ERROR: {record.file_path}: {record.error_message}")

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    changed = [r for r in records if r.status == "changed"]
    unchanged = [r for r in records if r.status == "unchanged"]
    skipped = [r for r in records if r.status == "skipped"]
    errors = [r for r in records if r.status == "error"]

    print(f"  Total files:    {total_files}")
    print(f"  Changed:        {len(changed)}")
    print(f"  Unchanged:      {len(unchanged)}")
    print(f"  Skipped:        {len(skipped)}")
    print(f"  Errors:         {len(errors)}")
    print()

    if errors:
        print("Errors:")
        for r in errors:
            print(f"  {r.file_path}: {r.error_message}")
        print()

    if dry_run and len(changed) > 0:
        print()
        print("To apply changes, run with --apply flag")


if __name__ == "__main__":
    main()
