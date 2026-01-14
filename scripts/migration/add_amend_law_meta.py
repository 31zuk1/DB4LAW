#!/usr/bin/env python3
"""
DB4LAW: 既存附則ファイルに amend_law ネスト構造を追加

既存の amendment_law_id / amendment_law_title / suppl_kind をミラーして
amend_law: ネスト構造を追加する。

Usage:
    python scripts/migration/add_amend_law_meta.py --law 民法 --dry-run
    python scripts/migration/add_amend_law_meta.py --law 民法 --apply
"""

import sys
import argparse
import yaml
from pathlib import Path
from typing import Dict, Tuple

# 共通モジュールのインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))
from legalkg.utils.article_formatter import normalize_amendment_id

# 設定のインポート
from config import get_law_dir


def add_amend_law_nested(
    law_dir: Path,
    dry_run: bool = True
) -> Dict[str, int]:
    """
    既存附則ファイルに amend_law ネスト構造を追加

    Args:
        law_dir: 法律ディレクトリ
        dry_run: True なら変更を保存しない

    Returns:
        {'updated': int, 'skipped': int, 'already_has': int, 'errors': int}
    """
    law_name = law_dir.name
    suppl_dir = law_dir / "附則"

    stats = {
        'updated': 0,
        'skipped': 0,
        'already_has': 0,
        'errors': 0
    }

    if not suppl_dir.exists():
        print(f"  附則ディレクトリが見つかりません: {suppl_dir}")
        return stats

    # 附則配下の全 .md ファイルを処理
    for md_file in suppl_dir.rglob('*.md'):
        try:
            content = md_file.read_text(encoding='utf-8')

            if not content.startswith('---'):
                stats['skipped'] += 1
                continue

            # YAML frontmatter を分離
            parts = content.split('---', 2)
            if len(parts) < 3:
                stats['skipped'] += 1
                continue

            yaml_str = parts[1]
            body = parts[2]

            try:
                metadata = yaml.safe_load(yaml_str)
            except yaml.YAMLError as e:
                print(f"  YAML parse error: {md_file.name} - {e}")
                stats['errors'] += 1
                continue

            if not metadata:
                stats['skipped'] += 1
                continue

            # 既に amend_law がある場合はスキップ
            if 'amend_law' in metadata:
                stats['already_has'] += 1
                continue

            # suppl_kind: amendment でないファイルの判定
            # 1. amendment_law_id があれば改正法断片と判定
            # 2. パスに改正法名（年+法律）が含まれていれば改正法断片と判定
            if metadata.get('suppl_kind') != 'amendment':
                if 'amendment_law_id' in metadata:
                    metadata['suppl_kind'] = 'amendment'
                else:
                    # パスから改正法名を推定
                    path_str = str(md_file)
                    is_amendment = False
                    for part in md_file.parts:
                        if '年' in part and '法律' in part and '号' in part:
                            is_amendment = True
                            break
                        if part == '改正法':
                            is_amendment = True
                            break
                    if is_amendment:
                        metadata['suppl_kind'] = 'amendment'
                    else:
                        stats['skipped'] += 1
                        continue

            # amend_law ネスト構造を構築
            amendment_law_id = metadata.get('amendment_law_id', '')
            amendment_law_title = metadata.get('amendment_law_title', '')
            law_id = metadata.get('law_id', '')

            # amendment_law_title がない場合はパスから推定
            if not amendment_law_title:
                # パスから改正法名を取得
                for part in md_file.parts:
                    if '年' in part and '法律' in part:
                        amendment_law_title = part
                        break
                    elif part.startswith(('S', 'H', 'R', 'T', 'M')) and '_L' in part:
                        # 正規化形式の場合
                        from legalkg.utils.article_formatter import amendment_key_to_title
                        amendment_law_title = amendment_key_to_title(part)
                        break

            # normalized_id がない場合は計算
            if not amendment_law_id and amendment_law_title:
                amendment_law_id = normalize_amendment_id(amendment_law_title)
                metadata['amendment_law_id'] = amendment_law_id

            if not amendment_law_id:
                print(f"  スキップ（amendment_law_id 不明）: {md_file.name}")
                stats['skipped'] += 1
                continue

            # amend_law ネスト構造を追加
            metadata['amend_law'] = {
                'num': amendment_law_title or amendment_law_id,
                'normalized_id': amendment_law_id,
                'scope': 'partial',
                'parent_law_id': law_id,
                'parent_law_name': law_name,
            }

            # YAML を再シリアライズ
            new_yaml = yaml.dump(
                metadata,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False
            )

            new_content = f"---\n{new_yaml}---{body}"

            if not dry_run:
                md_file.write_text(new_content, encoding='utf-8')

            stats['updated'] += 1

            if stats['updated'] <= 5:  # 最初の5件だけ表示
                print(f"  + {md_file.relative_to(law_dir)}")

        except Exception as e:
            print(f"  エラー: {md_file.name} - {e}")
            stats['errors'] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="既存附則ファイルに amend_law ネスト構造を追加"
    )
    parser.add_argument('--law', required=True, help='対象の法律名（例: 民法）')
    parser.add_argument('--dry-run', action='store_true', help='Dry-runモード（変更なし）')
    parser.add_argument('--apply', action='store_true', help='実際に変更を適用')

    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("エラー: --dry-run または --apply を指定してください")
        sys.exit(1)

    dry_run = not args.apply

    law_dir = get_law_dir(args.law)
    if not law_dir.exists():
        print(f"エラー: ディレクトリが見つかりません: {law_dir}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"amend_law ネスト構造追加 - {args.law}")
    print(f"モード: {'DRY-RUN' if dry_run else '実行'}")
    print(f"{'='*60}\n")

    stats = add_amend_law_nested(law_dir, dry_run=dry_run)

    print(f"\n{'='*60}")
    print(f"結果:")
    print(f"  更新: {stats['updated']}件")
    print(f"  既存: {stats['already_has']}件（amend_law あり）")
    print(f"  スキップ: {stats['skipped']}件")
    print(f"  エラー: {stats['errors']}件")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
