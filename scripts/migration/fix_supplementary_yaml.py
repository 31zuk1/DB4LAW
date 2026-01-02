#!/usr/bin/env python3
"""
附則ディレクトリ直下の単一ファイル型附則のYAMLを修正
- law_name: '' → law_name: 刑法
- part: suppl → part: 附則
- article_num: Provision → article_num: 附則
- id: #suppl#Provision → #附則#附則
"""

import re
from pathlib import Path
import yaml


def fix_supplementary_yaml(file_path: Path, dry_run: bool = False):
    """単一ファイル型附則のYAMLを修正"""

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # YAMLとボディを分離
    if not content.startswith('---'):
        print(f"⚠️  スキップ（YAMLなし）: {file_path.name}")
        return False

    parts = content.split('---', 2)
    if len(parts) < 3:
        print(f"⚠️  スキップ（YAML不正）: {file_path.name}")
        return False

    yaml_str = parts[1]
    body = parts[2]

    try:
        metadata = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        print(f"❌ YAML解析エラー: {file_path.name} - {e}")
        return False

    # 変更フラグ
    changed = False
    changes = []

    # law_name の修正
    if 'law_name' in metadata and metadata['law_name'] == '':
        metadata['law_name'] = '刑法'
        changed = True
        changes.append("law_name: '' → '刑法'")

    # part の修正
    if 'part' in metadata and metadata['part'] == 'suppl':
        metadata['part'] = '附則'
        changed = True
        changes.append("part: suppl → 附則")

    # article_num の修正
    if 'article_num' in metadata and metadata['article_num'] == 'Provision':
        metadata['article_num'] = '附則'
        changed = True
        changes.append("article_num: Provision → 附則")

    # id の修正
    if 'id' in metadata:
        old_id = metadata['id']
        new_id = old_id

        # #suppl# → #附則#
        new_id = new_id.replace('#suppl#', '#附則#')

        # #Provision → #附則
        new_id = new_id.replace('#Provision', '#附則')

        if new_id != old_id:
            metadata['id'] = new_id
            changed = True
            changes.append(f"id: {old_id} → {new_id}")

    if not changed:
        return False

    # 変更内容を表示
    print(f"📝 {file_path.name}")
    for change in changes:
        print(f"   - {change}")

    if not dry_run:
        # YAML を再シリアライズ
        new_yaml_str = yaml.dump(metadata, allow_unicode=True, sort_keys=False, default_flow_style=False)
        new_content = f"---\n{new_yaml_str}---{body}"

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

    return True


def main(dry_run: bool = False):
    """メイン処理"""
    print("=" * 60)
    print("🚀 附則YAMLフィールド修正")
    print("=" * 60)
    print()

    if dry_run:
        print("⚠️  DRY-RUN モード（実際のファイル変更はありません）")
        print()

    suppl_dir = Path('/Users/haramizuki/Project/DB4LAW/Vault/laws/刑法/附則')

    if not suppl_dir.exists():
        print(f"❌ エラー: 附則ディレクトリが見つかりません: {suppl_dir}")
        return

    # 附則ディレクトリ直下の .md ファイルのみを対象
    md_files = [f for f in suppl_dir.glob('*.md') if f.is_file()]

    print(f"📦 対象ファイル: {len(md_files)}個")
    print()

    fixed_count = 0
    skipped_count = 0

    for md_file in sorted(md_files):
        if fix_supplementary_yaml(md_file, dry_run):
            fixed_count += 1
        else:
            skipped_count += 1

    print()
    print("=" * 60)
    print(f"✅ 完了: {fixed_count}個修正, {skipped_count}個スキップ")
    print("=" * 60)

    if dry_run:
        print()
        print("実際に修正を適用するには、--apply オプションを付けて実行してください:")
        print("  python fix_supplementary_yaml.py --apply")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="附則YAMLフィールド修正")
    parser.add_argument('--apply', action='store_true', help='実際に修正を適用（デフォルトはdry-run）')
    args = parser.parse_args()

    main(dry_run=not args.apply)
