#!/usr/bin/env python3
"""
DB4LAW: 条文 parent 階層化マイグレーションスクリプト

既存 Vault の条文 frontmatter の parent を階層仕様に更新する。

階層仕様:
- 節あり → [[laws/{law}/節/{章名}{節名}]]
- 章のみ → [[laws/{law}/章/{章名}]]
- 章/節なし → [[laws/{law}/{law}]]（孤立条文）
- 附則 → 常に [[laws/{law}/{law}]]

Usage:
    # dry-run（デフォルト）
    python scripts/migration/update_article_parent.py --vault ./Vault --law 刑法

    # 適用（バックアップ付き）
    python scripts/migration/update_article_parent.py --vault ./Vault --law 刑法 --apply --backup-dir /tmp/backup

    # 全法令に適用
    python scripts/migration/update_article_parent.py --vault ./Vault --apply
"""

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.utils.markdown import read_markdown_file, write_markdown_file


class Status(str, Enum):
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"
    ERROR = "error"


class ResolutionPath(str, Enum):
    SECTION = "section"
    CHAPTER = "chapter"
    LAW = "law"
    FALLBACK_CHAPTER = "fallback_chapter"  # section not found, fell back to chapter
    FALLBACK_LAW = "fallback_law"  # chapter not found, fell back to law


@dataclass
class ChangeRecord:
    """変更ログのレコード"""
    file_path: str
    old_parent: Optional[str]
    new_parent: Optional[str]
    resolution_path: str
    status: str
    error_message: Optional[str] = None


def decode_egov_num(num: int) -> tuple[int, Optional[int]]:
    """
    e-Gov の章/節番号をデコード

    e-Gov encoding:
    - 1-99: 第1章〜第99章（枝番なし）
    - 100+: 枝番あり（例: 182 = 第18章の2, 192 = 第19章の2）

    Returns:
        (main_num, branch_num) - branch_num is None if no branch
    """
    if num is None:
        return (0, None)
    if num < 100:
        return (num, None)
    main = num // 10
    branch = num % 10
    return (main, branch)


def format_chapter_name(chapter_num: int, chapter_title: Optional[str] = None) -> str:
    """
    章番号から章ファイル名を生成

    e-Gov の章番号エンコード:
    - 通常: chapter_num = 実際の章番号 (1, 2, ..., 99)
    - 枝番付き (100以上): chapter_num = main*10 + branch (182 = 第18章の2)
    - 枝番付き (100未満): chapter_num = main*10 + branch (22 = 第2章の2)
      → タイトルに「章の」があれば枝番付きとして解釈

    Args:
        chapter_num: e-Gov形式の章番号
        chapter_title: 章タイトル（枝番号判定用）

    Returns:
        章名（例: "第1章", "第2章の2"）
    """
    if chapter_num is None:
        return ""

    # 100以上は確実に枝番付き
    if chapter_num >= 100:
        main = chapter_num // 10
        branch = chapter_num % 10
        return f"第{main}章の{branch}"

    # 100未満でも、タイトルに「章の」があれば枝番付き
    if chapter_title and "章の" in chapter_title:
        main = chapter_num // 10
        branch = chapter_num % 10
        if branch > 0:
            return f"第{main}章の{branch}"

    # 枝番なし
    return f"第{chapter_num}章"


def format_section_name(section_num: int, section_title: Optional[str] = None) -> str:
    """
    節番号から節名を生成

    e-Gov の節番号エンコード:
    - 通常: section_num = 実際の節番号 (1, 2, ..., 12, ...)
    - 枝番付き: section_num = main*10 + branch (12 = 第1節の2, 42 = 第4節の2)

    section_num だけでは区別できないため、section_title を見て判定する。
    タイトルに「節の」が含まれていれば枝番付きとして解釈。

    Args:
        section_num: e-Gov形式の節番号
        section_title: 節タイトル（枝番号判定に必須）

    Returns:
        節名（例: "第1節", "第1節の2"）
    """
    if section_num is None:
        return ""

    # タイトルに「節の」が含まれていれば枝番付き
    if section_title and "節の" in section_title:
        main = section_num // 10
        branch = section_num % 10
        if branch > 0:
            return f"第{main}節の{branch}"

    # 枝番なし
    return f"第{section_num}節"


def resolve_parent(
    law_name: str,
    part_type: str,
    chapter_num: Optional[int],
    chapter_title: Optional[str],
    section_num: Optional[int],
    section_title: Optional[str],
    laws_dir: Path,
) -> tuple[str, ResolutionPath]:
    """
    条文の親リンクを解決（存在チェック付き）

    Returns:
        (parent_wikilink, resolution_path)
    """
    law_dir = laws_dir / law_name

    # 附則は常に法令直下
    if part_type in ("suppl", "supplement"):
        return f"[[laws/{law_name}/{law_name}]]", ResolutionPath.LAW

    # 節が存在する場合
    if section_num is not None:
        chapter_name = format_chapter_name(chapter_num, chapter_title)
        section_name = format_section_name(section_num, section_title)
        section_file = law_dir / "節" / f"{chapter_name}{section_name}.md"

        if section_file.exists():
            return f"[[laws/{law_name}/節/{chapter_name}{section_name}]]", ResolutionPath.SECTION

        # 節ファイルが存在しない場合、章にフォールバック
        if chapter_num is not None:
            chapter_file = law_dir / "章" / f"{chapter_name}.md"
            if chapter_file.exists():
                return f"[[laws/{law_name}/章/{chapter_name}]]", ResolutionPath.FALLBACK_CHAPTER

        # 章も存在しない場合、法令にフォールバック
        return f"[[laws/{law_name}/{law_name}]]", ResolutionPath.FALLBACK_LAW

    # 章のみ存在する場合
    if chapter_num is not None:
        chapter_name = format_chapter_name(chapter_num, chapter_title)
        chapter_file = law_dir / "章" / f"{chapter_name}.md"

        if chapter_file.exists():
            return f"[[laws/{law_name}/章/{chapter_name}]]", ResolutionPath.CHAPTER

        # 章ファイルが存在しない場合、法令にフォールバック
        return f"[[laws/{law_name}/{law_name}]]", ResolutionPath.FALLBACK_LAW

    # 孤立条文（章/節なし）
    return f"[[laws/{law_name}/{law_name}]]", ResolutionPath.LAW


def collect_article_files(law_dir: Path) -> list[Path]:
    """
    法令ディレクトリから条文ファイルを収集

    対象:
    - 本文/*.md
    - 附則/**/*.md（改正法サブディレクトリ含む）
    """
    files = []

    # 本文
    main_dir = law_dir / "本文"
    if main_dir.exists():
        files.extend(sorted(main_dir.glob("*.md")))

    # 附則（サブディレクトリ含む）
    suppl_dir = law_dir / "附則"
    if suppl_dir.exists():
        files.extend(sorted(suppl_dir.rglob("*.md")))

    return files


def process_file(
    file_path: Path,
    laws_dir: Path,
    dry_run: bool,
    backup_dir: Optional[Path],
) -> ChangeRecord:
    """
    単一ファイルの parent を更新

    Returns:
        ChangeRecord
    """
    rel_path = str(file_path.relative_to(laws_dir.parent.parent))

    try:
        doc = read_markdown_file(file_path)
    except Exception as e:
        return ChangeRecord(
            file_path=rel_path,
            old_parent=None,
            new_parent=None,
            resolution_path="",
            status=Status.ERROR,
            error_message=str(e),
        )

    fm = doc.metadata
    if not fm:
        return ChangeRecord(
            file_path=rel_path,
            old_parent=None,
            new_parent=None,
            resolution_path="",
            status=Status.SKIPPED,
            error_message="No frontmatter",
        )

    # 必要なフィールドを取得
    law_name = fm.get("law_name")
    if not law_name:
        return ChangeRecord(
            file_path=rel_path,
            old_parent=fm.get("parent"),
            new_parent=None,
            resolution_path="",
            status=Status.SKIPPED,
            error_message="No law_name in frontmatter",
        )

    part_type = fm.get("part", "main")
    chapter_num = fm.get("chapter_num")
    chapter_title = fm.get("chapter_title")
    section_num = fm.get("section_num")
    section_title = fm.get("section_title")

    old_parent = fm.get("parent")

    # 新しい parent を解決
    new_parent, resolution = resolve_parent(
        law_name=law_name,
        part_type=part_type,
        chapter_num=chapter_num,
        chapter_title=chapter_title,
        section_num=section_num,
        section_title=section_title,
        laws_dir=laws_dir,
    )

    # 変更なし
    if old_parent == new_parent:
        return ChangeRecord(
            file_path=rel_path,
            old_parent=old_parent,
            new_parent=new_parent,
            resolution_path=resolution.value,
            status=Status.UNCHANGED,
        )

    # 変更あり
    if not dry_run:
        # バックアップ
        if backup_dir:
            backup_path = backup_dir / file_path.relative_to(laws_dir.parent.parent)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, backup_path)

        # metadata を更新
        fm["parent"] = new_parent
        doc.metadata = fm
        write_markdown_file(file_path, doc)

    return ChangeRecord(
        file_path=rel_path,
        old_parent=old_parent,
        new_parent=new_parent,
        resolution_path=resolution.value,
        status=Status.CHANGED,
    )


def main():
    parser = argparse.ArgumentParser(
        description="条文 parent を階層仕様に更新するマイグレーションスクリプト"
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path("./Vault"),
        help="Vault ディレクトリ (default: ./Vault)",
    )
    parser.add_argument(
        "--law",
        type=str,
        help="単一法令に絞る（例: 刑法）",
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
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="apply時にバックアップを保存するディレクトリ",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="処理する最大ファイル数（テスト用）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="変更ログの出力先（JSONL）",
    )

    args = parser.parse_args()

    # --apply が指定されたら dry_run を無効化
    dry_run = not args.apply

    laws_dir = args.vault / "laws"
    if not laws_dir.exists():
        print(f"Error: laws directory not found: {laws_dir}")
        sys.exit(1)

    # 対象法令を収集
    if args.law:
        law_dirs = [laws_dir / args.law]
        if not law_dirs[0].exists():
            print(f"Error: law directory not found: {law_dirs[0]}")
            sys.exit(1)
    else:
        law_dirs = sorted([d for d in laws_dir.iterdir() if d.is_dir()])

    # ファイルを収集
    all_files = []
    for law_dir in law_dirs:
        all_files.extend(collect_article_files(law_dir))

    if args.limit:
        all_files = all_files[:args.limit]

    print(f"{'[DRY-RUN] ' if dry_run else ''}Processing {len(all_files)} files...")
    print()

    # 処理
    records: list[ChangeRecord] = []
    stats = {Status.CHANGED: 0, Status.UNCHANGED: 0, Status.SKIPPED: 0, Status.ERROR: 0}

    for file_path in all_files:
        record = process_file(
            file_path=file_path,
            laws_dir=laws_dir,
            dry_run=dry_run,
            backup_dir=args.backup_dir,
        )
        records.append(record)
        stats[Status(record.status)] += 1

    # 結果出力
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Total files:  {len(records)}")
    print(f"  Changed:      {stats[Status.CHANGED]}")
    print(f"  Unchanged:    {stats[Status.UNCHANGED]}")
    print(f"  Skipped:      {stats[Status.SKIPPED]}")
    print(f"  Errors:       {stats[Status.ERROR]}")
    print()

    # 変更詳細を表示
    changed_records = [r for r in records if r.status == Status.CHANGED]
    if changed_records:
        print("Changes:")
        for r in changed_records[:20]:  # 最初の20件
            print(f"  {r.file_path}")
            print(f"    old: {r.old_parent}")
            print(f"    new: {r.new_parent} ({r.resolution_path})")
        if len(changed_records) > 20:
            print(f"  ... and {len(changed_records) - 20} more")
        print()

    # フォールバック発生を表示
    fallback_records = [
        r for r in records
        if r.resolution_path in (ResolutionPath.FALLBACK_CHAPTER.value, ResolutionPath.FALLBACK_LAW.value)
    ]
    if fallback_records:
        print("Fallbacks (target not found):")
        for r in fallback_records[:10]:
            print(f"  {r.file_path}: {r.resolution_path}")
        if len(fallback_records) > 10:
            print(f"  ... and {len(fallback_records) - 10} more")
        print()

    # エラー表示
    error_records = [r for r in records if r.status == Status.ERROR]
    if error_records:
        print("Errors:")
        for r in error_records:
            print(f"  {r.file_path}: {r.error_message}")
        print()

    # ログ出力
    output_path = args.output
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifacts_dir = Path(__file__).parent / "_artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifacts_dir / f"parent_migration_{timestamp}.jsonl"

    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    print(f"Log written to: {output_path}")

    if dry_run and stats[Status.CHANGED] > 0:
        print()
        print("To apply changes, run with --apply flag:")
        print(f"  python {sys.argv[0]} --vault {args.vault} --apply")


if __name__ == "__main__":
    main()
