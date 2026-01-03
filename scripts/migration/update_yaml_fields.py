#!/usr/bin/env python3
"""
法律ファイルのYAMLフィールドを日本語化するスクリプト

Tier1ビルド後のファイルに対して:
- article_num: '1' → '第1条'
- part: main → 本文
- id: #main#1 → #本文#第1条
"""

import re
import argparse
from pathlib import Path
import yaml


def convert_article_num(article_num: str, is_suppl: bool = False) -> str:
    """article_num を日本語に変換"""
    if not article_num:
        return article_num

    article_num = str(article_num)

    # すでに日本語化されている場合はスキップ
    if article_num.startswith('第') or article_num.startswith('附則'):
        return article_num

    if article_num == 'Provision':
        return '附則'

    # 範囲形式: 73:76 → 第73条から第76条まで
    if ':' in article_num:
        start, end = article_num.split(':')
        if is_suppl:
            return f'附則第{start}条から附則第{end}条まで'
        return f'第{start}条から第{end}条まで'

    # 枝番形式: 3_2 → 第3条の2
    if '_' in article_num:
        main, sub = article_num.split('_', 1)
        if is_suppl:
            return f'附則第{main}条の{sub}'
        return f'第{main}条の{sub}'

    # 通常形式
    if is_suppl:
        return f'附則第{article_num}条'
    return f'第{article_num}条'


def convert_id(old_id: str) -> str:
    """id フィールドを日本語化"""
    if not old_id:
        return old_id

    # すでに日本語化されている場合はスキップ
    if '#本文#' in old_id or '#附則#' in old_id:
        return old_id

    # part を変換
    old_id = old_id.replace('#main#', '#本文#')
    old_id = old_id.replace('#suppl#', '#附則#')

    # 条番号部分を変換
    if '#本文#' in old_id:
        prefix, suffix = old_id.rsplit('#本文#', 1)
        new_suffix = convert_article_num(suffix, is_suppl=False)
        return f"{prefix}#本文#{new_suffix}"

    if '#附則#' in old_id:
        prefix, suffix = old_id.rsplit('#附則#', 1)
        new_suffix = convert_article_num(suffix, is_suppl=True)
        return f"{prefix}#附則#{new_suffix}"

    return old_id


def update_file(file_path: Path, law_name: str, dry_run: bool = False) -> bool:
    """単一ファイルのYAMLを更新"""
    try:
        content = file_path.read_text(encoding='utf-8')

        if not content.startswith('---'):
            return False

        parts = content.split('---', 2)
        if len(parts) < 3:
            return False

        yaml_str = parts[1]
        body = parts[2]

        try:
            metadata = yaml.safe_load(yaml_str)
        except yaml.YAMLError:
            return False

        if not metadata:
            return False

        modified = False
        is_suppl = '附則' in str(file_path)

        # part の変換
        if 'part' in metadata:
            if metadata['part'] == 'main':
                metadata['part'] = '本文'
                modified = True
            elif metadata['part'] == 'suppl':
                metadata['part'] = '附則'
                modified = True

        # article_num の変換
        if 'article_num' in metadata:
            old_num = metadata['article_num']
            new_num = convert_article_num(old_num, is_suppl)
            if old_num != new_num:
                metadata['article_num'] = new_num
                modified = True

        # id の変換
        if 'id' in metadata:
            old_id = metadata['id']
            new_id = convert_id(old_id)
            if old_id != new_id:
                metadata['id'] = new_id
                modified = True

        # law_name が空の場合は設定
        if 'law_name' in metadata and not metadata['law_name']:
            metadata['law_name'] = law_name
            modified = True

        if not modified:
            return False

        # YAML を再シリアライズ
        new_yaml_str = yaml.dump(
            metadata,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False
        )

        new_content = f"---\n{new_yaml_str}---{body}"

        if not dry_run:
            file_path.write_text(new_content, encoding='utf-8')

        return True

    except Exception as e:
        print(f"  エラー: {file_path.name} - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="法律ファイルのYAMLフィールドを日本語化")
    parser.add_argument('--law', required=True, help='対象の法律名（例: 民法）')
    parser.add_argument('--dry-run', action='store_true', help='Dry-runモード')
    args = parser.parse_args()

    vault_path = Path("/Users/haramizuki/Project/DB4LAW/Vault/laws")
    law_dir = vault_path / args.law

    if not law_dir.exists():
        print(f"エラー: ディレクトリが見つかりません: {law_dir}")
        return

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}YAMLフィールドを日本語化中: {args.law}")
    print()

    # 本文ディレクトリ
    main_dir = law_dir / "本文"
    suppl_dir = law_dir / "附則"

    updated = 0
    skipped = 0

    # 本文ファイルを処理
    if main_dir.exists():
        print(f"本文: {main_dir}")
        for file_path in sorted(main_dir.glob('*.md')):
            if update_file(file_path, args.law, args.dry_run):
                updated += 1
            else:
                skipped += 1

    # 附則ファイルを処理
    if suppl_dir.exists():
        print(f"附則: {suppl_dir}")
        for file_path in sorted(suppl_dir.rglob('*.md')):
            if update_file(file_path, args.law, args.dry_run):
                updated += 1
            else:
                skipped += 1

    print()
    print(f"完了: {updated} 更新, {skipped} スキップ")


if __name__ == '__main__':
    main()
