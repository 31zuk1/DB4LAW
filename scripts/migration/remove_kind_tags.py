#!/usr/bin/env python3
"""
DB4LAW: kind/ タグ削除マイグレーションスクリプト

tags から kind/* を削除する。type フィールドが同じ役割を果たすため不要。

Usage:
    # dry-run
    python scripts/migration/remove_kind_tags.py --vault ./Vault

    # apply
    python scripts/migration/remove_kind_tags.py --vault ./Vault --apply
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.utils.markdown import read_markdown_file, write_markdown_file


@dataclass
class ChangeRecord:
    file_path: str
    old_tags: list
    new_tags: list
    removed_tags: list
    status: str  # changed, unchanged, skipped, error
    error_message: Optional[str] = None


def remove_kind_tags(tags: list) -> tuple[list, list]:
    """tags から kind/* を削除"""
    if not tags:
        return [], []

    new_tags = [t for t in tags if not str(t).startswith("kind/")]
    removed = [t for t in tags if str(t).startswith("kind/")]
    return new_tags, removed


def process_file(file_path: Path, vault_path: Path, dry_run: bool) -> ChangeRecord:
    """単一ファイルを処理"""
    rel_path = str(file_path.relative_to(vault_path))

    try:
        doc = read_markdown_file(file_path)
    except Exception as e:
        return ChangeRecord(
            file_path=rel_path,
            old_tags=[],
            new_tags=[],
            removed_tags=[],
            status="error",
            error_message=str(e),
        )

    if not doc.metadata:
        return ChangeRecord(
            file_path=rel_path,
            old_tags=[],
            new_tags=[],
            removed_tags=[],
            status="skipped",
            error_message="No frontmatter",
        )

    old_tags = doc.metadata.get("tags", [])
    if not old_tags:
        return ChangeRecord(
            file_path=rel_path,
            old_tags=[],
            new_tags=[],
            removed_tags=[],
            status="unchanged",
        )

    new_tags, removed = remove_kind_tags(old_tags)

    if not removed:
        return ChangeRecord(
            file_path=rel_path,
            old_tags=old_tags,
            new_tags=new_tags,
            removed_tags=[],
            status="unchanged",
        )

    if not dry_run:
        if new_tags:
            doc.metadata["tags"] = new_tags
        else:
            # タグが空になった場合は削除
            del doc.metadata["tags"]
        write_markdown_file(file_path, doc)

    return ChangeRecord(
        file_path=rel_path,
        old_tags=old_tags,
        new_tags=new_tags,
        removed_tags=removed,
        status="changed",
    )


def main():
    parser = argparse.ArgumentParser(description="tags から kind/* を削除")
    parser.add_argument("--vault", type=Path, default=Path("./Vault"))
    parser.add_argument("--law", type=str, help="単一法令に絞る")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path)

    args = parser.parse_args()
    dry_run = not args.apply

    laws_dir = args.vault / "laws"
    if not laws_dir.exists():
        print(f"Error: {laws_dir} not found")
        sys.exit(1)

    # 対象ファイル収集
    if args.law:
        law_dirs = [laws_dir / args.law]
    else:
        law_dirs = [d for d in laws_dir.iterdir() if d.is_dir()]

    files = []
    for law_dir in law_dirs:
        files.extend(law_dir.rglob("*.md"))

    print(f"{'[DRY-RUN] ' if dry_run else ''}Processing {len(files)} files...")

    records = []
    changed_count = 0

    for file_path in files:
        record = process_file(file_path, args.vault, dry_run)
        records.append(record)
        if record.status == "changed":
            changed_count += 1

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    changed = [r for r in records if r.status == "changed"]
    unchanged = [r for r in records if r.status == "unchanged"]
    skipped = [r for r in records if r.status == "skipped"]
    errors = [r for r in records if r.status == "error"]

    print(f"  Total files:  {len(records)}")
    print(f"  Changed:      {len(changed)}")
    print(f"  Unchanged:    {len(unchanged)}")
    print(f"  Skipped:      {len(skipped)}")
    print(f"  Errors:       {len(errors)}")

    if changed:
        print()
        print("Sample changes:")
        for r in changed[:5]:
            print(f"  {r.file_path}")
            print(f"    removed: {r.removed_tags}")

    # Log output
    output_path = args.output
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifacts_dir = Path(__file__).parent / "_artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifacts_dir / f"remove_kind_tags_{timestamp}.jsonl"

    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    print(f"\nLog written to: {output_path}")

    if dry_run and changed:
        print("\nTo apply changes, run with --apply flag")


if __name__ == "__main__":
    main()
