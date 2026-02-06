#!/usr/bin/env python3
"""
構造整合性バリデータ

章/節ノードの整合性を検証し、以下の問題を検出する：
1. 同一法令内で、異なる part の同番号 chapter が同一ファイルに混在
2. chapter_title と条文レンジが、明らかに異なる編のものを含む
3. ID が一意でない（重複）
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.utils.markdown import read_markdown_file


def validate_law_structure(law_dir: Path) -> List[str]:
    """
    法令ディレクトリの構造整合性を検証

    Returns:
        エラーメッセージのリスト（空なら問題なし）
    """
    errors = []
    law_name = law_dir.name

    chapter_dir = law_dir / "章"
    section_dir = law_dir / "節"
    part_dir = law_dir / "編"

    # ID 重複チェック用
    seen_ids: Dict[str, Path] = {}

    # 章ファイルの検証
    if chapter_dir.exists():
        for chapter_file in chapter_dir.glob("*.md"):
            try:
                doc = read_markdown_file(chapter_file)
                meta = doc.metadata

                node_id = meta.get("id", "")
                part_num = meta.get("part_num")
                chapter_num = meta.get("chapter_num")
                chapter_title = meta.get("chapter_title", "")
                article_nums = meta.get("article_nums", [])

                # ID 重複チェック
                if node_id in seen_ids:
                    errors.append(
                        f"[{law_name}] ID重複: {node_id}\n"
                        f"  - {seen_ids[node_id]}\n"
                        f"  - {chapter_file}"
                    )
                else:
                    seen_ids[node_id] = chapter_file

                # 編がある法令で、chapter_num のみでファイル名が付いている場合は警告
                if part_dir.exists() and list(part_dir.glob("*.md")):
                    if part_num is None and chapter_num is not None:
                        errors.append(
                            f"[{law_name}] 編がある法令で part_num が設定されていない章: {chapter_file.name}"
                        )

                # 条文番号の範囲チェック（異常な範囲を検出）
                if article_nums:
                    # 条文番号を数値に変換（可能な場合）
                    nums = []
                    for num in article_nums:
                        if isinstance(num, str) and ':' in num:
                            # 範囲形式（例: 73:76）
                            continue
                        try:
                            if isinstance(num, str) and '_' in num:
                                # 枝番形式（例: 3_2）
                                main = int(num.split('_')[0])
                                nums.append(main)
                            else:
                                nums.append(int(num))
                        except (ValueError, TypeError):
                            continue

                    if nums:
                        min_num = min(nums)
                        max_num = max(nums)
                        range_size = max_num - min_num

                        # 条文番号の範囲が100以上離れている場合は警告
                        if range_size > 100:
                            errors.append(
                                f"[{law_name}] 条文番号の範囲が広すぎます（異なる編の混在の可能性）:\n"
                                f"  ファイル: {chapter_file.name}\n"
                                f"  章タイトル: {chapter_title}\n"
                                f"  条文範囲: {min_num} ~ {max_num} (差: {range_size})"
                            )

            except Exception as e:
                errors.append(f"[{law_name}] ファイル読み込みエラー: {chapter_file.name}: {e}")

    # 節ファイルの検証
    if section_dir.exists():
        for section_file in section_dir.glob("*.md"):
            try:
                doc = read_markdown_file(section_file)
                meta = doc.metadata

                node_id = meta.get("id", "")

                # ID 重複チェック
                if node_id in seen_ids:
                    errors.append(
                        f"[{law_name}] ID重複: {node_id}\n"
                        f"  - {seen_ids[node_id]}\n"
                        f"  - {section_file}"
                    )
                else:
                    seen_ids[node_id] = section_file

            except Exception as e:
                errors.append(f"[{law_name}] ファイル読み込みエラー: {section_file.name}: {e}")

    return errors


def validate_all_laws(vault_path: Path) -> Tuple[int, int, List[str]]:
    """
    全法令の構造整合性を検証

    Returns:
        (検証した法令数, エラーのある法令数, 全エラーメッセージ)
    """
    laws_dir = vault_path / "laws"
    if not laws_dir.exists():
        return 0, 0, ["Vault/laws ディレクトリが見つかりません"]

    all_errors = []
    law_count = 0
    error_law_count = 0

    for law_dir in sorted(laws_dir.iterdir()):
        if not law_dir.is_dir():
            continue

        law_count += 1
        errors = validate_law_structure(law_dir)

        if errors:
            error_law_count += 1
            all_errors.extend(errors)

    return law_count, error_law_count, all_errors


def main():
    parser = argparse.ArgumentParser(description="構造整合性バリデータ")
    parser.add_argument(
        "--vault", type=Path, default=Path("Vault"),
        help="Vault ディレクトリのパス"
    )
    parser.add_argument(
        "--law", type=str, default=None,
        help="特定の法令のみ検証（法令ID または 法令名）"
    )
    args = parser.parse_args()

    vault_path = args.vault

    if args.law:
        # 特定の法令のみ検証
        law_dir = vault_path / "laws" / args.law
        if not law_dir.exists():
            # 法令名で検索
            laws_dir = vault_path / "laws"
            matches = [d for d in laws_dir.iterdir() if d.is_dir() and args.law in d.name]
            if matches:
                law_dir = matches[0]
            else:
                print(f"法令が見つかりません: {args.law}")
                sys.exit(1)

        errors = validate_law_structure(law_dir)
        if errors:
            print(f"エラー: {len(errors)} 件")
            for error in errors:
                print(f"  {error}")
            sys.exit(1)
        else:
            print(f"✓ {law_dir.name}: 問題なし")
            sys.exit(0)
    else:
        # 全法令を検証
        law_count, error_law_count, all_errors = validate_all_laws(vault_path)

        print(f"検証結果: {law_count} 法令中 {error_law_count} 法令にエラー")

        if all_errors:
            print(f"\nエラー一覧 ({len(all_errors)} 件):")
            for error in all_errors[:50]:  # 最初の50件のみ表示
                print(f"  {error}")
            if len(all_errors) > 50:
                print(f"  ... 他 {len(all_errors) - 50} 件")
            sys.exit(1)
        else:
            print("✓ 全法令で構造整合性に問題なし")
            sys.exit(0)


if __name__ == "__main__":
    main()
