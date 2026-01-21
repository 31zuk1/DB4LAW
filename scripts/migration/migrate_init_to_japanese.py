#!/usr/bin/env python3
"""
init_0 を 制定時附則 にマイグレーションするスクリプト

変更内容:
- init_0/ → 制定時附則/
- init_0.md → 制定時附則.md
- init_0_第N条.md → 第N条.md

Usage:
    # 全法令を dry-run（サマリのみ）
    python scripts/migration/migrate_init_to_japanese.py --dry-run

    # 全法令を dry-run（詳細ログ）
    python scripts/migration/migrate_init_to_japanese.py --dry-run --verbose

    # 特定の法令のみ処理
    python scripts/migration/migrate_init_to_japanese.py --law 民事訴訟法

    # 実際に移行を実行
    python scripts/migration/migrate_init_to_japanese.py
"""

import argparse
import re
from pathlib import Path


class MigrationContext:
    """マイグレーションのコンテキスト（ログ制御用）"""
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.changes = []  # 変更ログ

    def log(self, message: str):
        """詳細ログ（--verbose 時のみ出力）"""
        if self.verbose:
            print(message)
        self.changes.append(message)

    def log_always(self, message: str):
        """常に出力するログ"""
        print(message)


def migrate_init_dir(init_dir: Path, ctx: MigrationContext) -> dict:
    """
    init_N ディレクトリを 制定時附則 形式にマイグレーション

    Returns:
        dict: {"renamed_dir": bool, "renamed_files": int, "skipped": bool}
    """
    result = {"renamed_dir": False, "renamed_files": 0, "skipped": False}

    if not init_dir.is_dir():
        return result

    # ディレクトリ名から新しい名前を決定
    match = re.match(r'init_(\d+)', init_dir.name)
    if not match:
        return result

    index = int(match.group(1))
    if index == 0:
        new_name = "制定時附則"
    else:
        new_name = f"制定時附則{index + 1}"

    new_dir = init_dir.parent / new_name

    if new_dir.exists():
        ctx.log(f"    スキップ: {new_dir.name} は既に存在")
        result["skipped"] = True
        return result

    ctx.log(f"    ディレクトリ: {init_dir.name} → {new_name}")

    if not ctx.dry_run:
        init_dir.rename(new_dir)

    result["renamed_dir"] = True

    # ディレクトリ内のファイルをリネーム
    target_dir = new_dir if not ctx.dry_run else init_dir
    for f in target_dir.glob('*.md'):
        # init_0_第N条.md → 第N条.md
        file_match = re.match(r'init_\d+_(第\d+条(?:の\d+)?\.md)$', f.name)
        if file_match:
            new_filename = file_match.group(1)
            new_path = target_dir / new_filename
            ctx.log(f"      ファイル: {f.name} → {new_filename}")
            if not ctx.dry_run:
                f.rename(new_path)
            result["renamed_files"] += 1

    return result


def migrate_init_file(init_file: Path, ctx: MigrationContext) -> dict:
    """
    単一ファイル型 init_N.md を 制定時附則.md にマイグレーション

    Returns:
        dict: {"renamed": bool, "skipped": bool}
    """
    result = {"renamed": False, "skipped": False}

    if not init_file.is_file():
        return result

    match = re.match(r'init_(\d+)\.md$', init_file.name)
    if not match:
        return result

    index = int(match.group(1))
    if index == 0:
        new_name = "制定時附則.md"
    else:
        new_name = f"制定時附則{index + 1}.md"

    new_path = init_file.parent / new_name

    if new_path.exists():
        ctx.log(f"    スキップ: {new_name} は既に存在")
        result["skipped"] = True
        return result

    ctx.log(f"    ファイル: {init_file.name} → {new_name}")

    if not ctx.dry_run:
        init_file.rename(new_path)

    result["renamed"] = True
    return result


def migrate_law(law_dir: Path, ctx: MigrationContext) -> dict:
    """
    法令ディレクトリをマイグレーション

    Returns:
        dict: {"dirs": int, "files": int, "inner_files": int, "skipped": int}
    """
    suppl_dir = law_dir / "附則"

    if not suppl_dir.exists():
        return {"dirs": 0, "files": 0, "inner_files": 0, "skipped": 0}

    result = {"dirs": 0, "files": 0, "inner_files": 0, "skipped": 0}

    # ディレクトリ型を処理
    for d in list(suppl_dir.iterdir()):
        if d.is_dir() and d.name.startswith("init_"):
            dir_result = migrate_init_dir(d, ctx)
            if dir_result["renamed_dir"]:
                result["dirs"] += 1
                result["inner_files"] += dir_result["renamed_files"]
            if dir_result["skipped"]:
                result["skipped"] += 1

    # 単一ファイル型を処理
    for f in list(suppl_dir.glob("init_*.md")):
        if re.match(r'init_\d+\.md$', f.name):
            file_result = migrate_init_file(f, ctx)
            if file_result["renamed"]:
                result["files"] += 1
            if file_result["skipped"]:
                result["skipped"] += 1

    return result


def main():
    parser = argparse.ArgumentParser(
        description="init_0 を 制定時附則 にマイグレーション",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 全法令を dry-run（サマリのみ）
  python scripts/migration/migrate_init_to_japanese.py --dry-run

  # 全法令を dry-run（詳細ログ）
  python scripts/migration/migrate_init_to_japanese.py --dry-run --verbose

  # 特定の法令のみ処理
  python scripts/migration/migrate_init_to_japanese.py --law 民事訴訟法
"""
    )
    parser.add_argument('--law', help='対象の法律名（例: 民事訴訟法）。省略時は全法令')
    parser.add_argument('--dry-run', action='store_true', help='Dry-runモード（実際には変更しない）')
    parser.add_argument('--verbose', '-v', action='store_true', help='詳細ログを出力')
    parser.add_argument('--vault', default='./Vault/laws', help='Vault/laws のパス')
    args = parser.parse_args()

    vault_path = Path(args.vault)

    if not vault_path.exists():
        print(f"エラー: {vault_path} が見つかりません")
        return 1

    ctx = MigrationContext(dry_run=args.dry_run, verbose=args.verbose)

    if args.law:
        law_dirs = [vault_path / args.law]
    else:
        law_dirs = sorted([d for d in vault_path.iterdir() if d.is_dir()])

    total_laws = 0
    total_dirs = 0
    total_files = 0
    total_inner_files = 0
    total_skipped = 0
    changed_laws = []

    for law_dir in law_dirs:
        if not law_dir.exists():
            print(f"エラー: {law_dir} が見つかりません")
            continue

        ctx.log(f"\n処理中: {law_dir.name}")
        result = migrate_law(law_dir, ctx)

        has_changes = result["dirs"] > 0 or result["files"] > 0

        if has_changes:
            changed_laws.append({
                "name": law_dir.name,
                "dirs": result["dirs"],
                "files": result["files"],
                "inner_files": result["inner_files"]
            })
            total_laws += 1

        total_dirs += result["dirs"]
        total_files += result["files"]
        total_inner_files += result["inner_files"]
        total_skipped += result["skipped"]

    # サマリ出力
    print()
    print("=" * 50)
    if args.dry_run:
        print("[DRY-RUN] マイグレーション結果")
    else:
        print("マイグレーション結果")
    print("=" * 50)

    if changed_laws:
        print(f"\n変更があった法令: {len(changed_laws)} 件")
        for law in changed_laws[:20]:  # 最大20件表示
            detail = []
            if law["dirs"] > 0:
                detail.append(f"ディレクトリ{law['dirs']}")
            if law["files"] > 0:
                detail.append(f"ファイル{law['files']}")
            print(f"  - {law['name']} ({', '.join(detail)})")
        if len(changed_laws) > 20:
            print(f"  ... 他 {len(changed_laws) - 20} 件")

    print(f"\n合計:")
    print(f"  対象法令:         {len(law_dirs)} 件")
    print(f"  変更法令:         {total_laws} 件")
    print(f"  ディレクトリ移行: {total_dirs} 件")
    print(f"  ファイル移行:     {total_files} 件（単一ファイル型）")
    print(f"  内部ファイル移行: {total_inner_files} 件（ディレクトリ内）")
    if total_skipped > 0:
        print(f"  スキップ:         {total_skipped} 件")
    print("=" * 50)

    return 0


if __name__ == '__main__':
    exit(main())
