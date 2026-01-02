#!/usr/bin/env python3
"""
日本国憲法のYAMLメタデータを日本語形式に一括更新
"""

import yaml
from pathlib import Path
import re

def update_constitution_yaml(file_path: Path):
    """憲法ファイルのYAMLを日本語形式に更新"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if not content.startswith('---'):
        print(f"⚠️  YAMLなし: {file_path.name}")
        return False

    parts = content.split('---', 2)
    if len(parts) < 3:
        print(f"⚠️  YAML形式エラー: {file_path.name}")
        return False

    yaml_str = parts[1]
    body = parts[2]

    try:
        metadata = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        print(f"❌ YAML解析エラー: {file_path.name} - {e}")
        return False

    # article_num の更新
    if 'article_num' in metadata:
        old_num = str(metadata['article_num'])

        if old_num.isdigit():
            # '50' → '第50条'
            metadata['article_num'] = f'第{old_num}条'
        elif old_num == 'Provision':
            # 'Provision' → '附則'
            metadata['article_num'] = '附則'

    # part の更新
    if 'part' in metadata:
        if metadata['part'] == 'main':
            metadata['part'] = '本文'
        elif metadata['part'] == 'suppl':
            metadata['part'] = '附則'

    # id の更新
    if 'id' in metadata:
        old_id = metadata['id']

        # JPLAW:321CONSTITUTION#main#50 → JPLAW:321CONSTITUTION#本文#第50条
        old_id = old_id.replace('#main#', '#本文#')
        old_id = old_id.replace('#suppl#', '#附則#')

        # 条番号部分を更新
        if '#本文#' in old_id:
            prefix, suffix = old_id.rsplit('#本文#', 1)
            if suffix.isdigit():
                new_suffix = f'第{suffix}条'
                metadata['id'] = f"{prefix}#本文#{new_suffix}"
            elif suffix == 'Provision':
                metadata['id'] = f"{prefix}#本文#附則"
        elif '#附則#' in old_id:
            prefix, suffix = old_id.rsplit('#附則#', 1)
            if suffix.isdigit():
                new_suffix = f'附則第{suffix}条'
                metadata['id'] = f"{prefix}#附則#{new_suffix}"
            elif suffix == 'Provision':
                metadata['id'] = f"{prefix}#附則#附則"

    # YAML を再シリアライズ
    new_yaml_str = yaml.dump(metadata, allow_unicode=True, sort_keys=False, default_flow_style=False)
    new_content = f"---\n{new_yaml_str}---{body}"

    # ファイル書き込み
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True


def update_parent_file_links(parent_file: Path):
    """親ファイル（日本国憲法.md）のリンクを更新"""
    with open(parent_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # articles/main/Article_N.md → 本文/第N条.md
    def replace_link(match):
        article_num = match.group(1)  # Article_1
        display_text = match.group(2)  # 第1条

        num = article_num.replace('Article_', '')
        new_filename = f"第{num}条.md"

        return f"[[本文/{new_filename}|{display_text}]]"

    content = re.sub(
        r'\[\[articles/main/(Article_\d+)\.md\|([^\]]+)\]\]',
        replace_link,
        content
    )

    with open(parent_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ 親ファイルのリンク更新完了")


if __name__ == '__main__':
    # 憲法ディレクトリ
    kenpo_dir = Path('/Users/haramizuki/Project/DB4LAW/Vault/laws/日本国憲法')
    main_dir = kenpo_dir / '本文'

    if not main_dir.exists():
        print(f"❌ エラー: {main_dir} が存在しません")
        exit(1)

    print("=" * 60)
    print("🚀 日本国憲法 YAML一括更新")
    print("=" * 60)

    # 本文ファイル更新
    article_files = sorted(main_dir.glob('第*.md'))

    print(f"\n📦 本文ファイルを更新中... ({len(article_files)}ファイル)")

    success = 0
    failed = 0

    for file_path in article_files:
        if update_constitution_yaml(file_path):
            success += 1
            print(f"✓ {file_path.name}")
        else:
            failed += 1

    print(f"\n✅ 更新完了: {success} 成功, {failed} 失敗")

    # 親ファイル更新
    print(f"\n📝 親ファイル（日本国憲法.md）のリンクを更新中...")
    parent_file = kenpo_dir / '日本国憲法.md'

    if parent_file.exists():
        update_parent_file_links(parent_file)
    else:
        print(f"⚠️  親ファイルが見つかりません: {parent_file}")

    print("\n" + "=" * 60)
    print("✨ 全ての処理が完了しました")
    print("=" * 60)
