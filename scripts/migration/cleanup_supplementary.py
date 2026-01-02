#!/usr/bin/env python3
"""
附則ファイルの重複を削除し、リンクを正しい形式に修正
"""

import re
from pathlib import Path
import os

def remove_old_format_files():
    """古い形式の附則ファイルを削除"""
    suppl_dir = Path('/Users/haramizuki/Project/DB4LAW/Vault/laws/刑法/附則')

    # XX号_第N条.md 形式のファイルを削除
    old_files = list(suppl_dir.rglob('*_第*条.md'))

    print(f"📦 古い形式のファイル: {len(old_files)}個")

    for old_file in old_files:
        print(f"🗑️  削除: {old_file.relative_to(suppl_dir)}")
        os.remove(old_file)

    print(f"✅ {len(old_files)}個のファイルを削除しました")


def fix_parent_file_links():
    """親ファイル（刑法.md）の附則リンクを正しい形式に修正"""
    parent_file = Path('/Users/haramizuki/Project/DB4LAW/Vault/laws/刑法/刑法.md')

    with open(parent_file, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # パターン1: XX号/XX号_第N条.md → XX号/附則第N条.md
    def replace_link(match):
        prefix = match.group(1)      # 附則/平成...号
        law_name = match.group(2)    # 平成...号
        article_num = match.group(3) # 1, 2, 10, 39, etc.
        display_text = match.group(4) # 附則第1条

        new_filename = f"附則第{article_num}条.md"
        return f"[[{prefix}/{new_filename}|{display_text}]]"

    # [[附則/XX号/XX号_第N条.md|附則第N条]]
    content = re.sub(
        r'\[\[(附則/([^/]+))/\2_第(\d+)条\.md\|([^\]]+)\]\]',
        replace_link,
        content
    )

    # 変更があったかチェック
    if content != original_content:
        with open(parent_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ 刑法.md のリンクを修正しました")

        # 変更数をカウント
        changes = len(re.findall(r'附則/[^/]+/附則第\d+条\.md', content))
        print(f"ℹ️  修正したリンク数: {changes}個")
    else:
        print("ℹ️  リンク修正は不要でした")


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 附則ファイル重複削除とリンク修正")
    print("=" * 60)
    print()

    # Step 1: 古いファイル削除
    print("🗑️  Step 1: 古い形式のファイルを削除中...")
    remove_old_format_files()
    print()

    # Step 2: 親ファイルリンク修正
    print("📝 Step 2: 親ファイルのリンクを修正中...")
    fix_parent_file_links()
    print()

    print("=" * 60)
    print("✨ 全ての処理が完了しました")
    print("=" * 60)
