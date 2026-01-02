#!/usr/bin/env python3
"""
刑法.mdの附則リンクを修正し、グレーアウトノード生成を防ぐ
"""

import re
from pathlib import Path

def fix_parent_file_links():
    """親ファイル（刑法.md）の附則リンクを修正"""
    parent_file = Path('/Users/haramizuki/Project/DB4LAW/Vault/laws/刑法/刑法.md')

    with open(parent_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # パターン1: Article形式のリンクを修正
    # [[附則/.../XX_Article_1.md|...]] → [[附則/.../XX_第1条.md|...]]
    def replace_article_link(match):
        path_prefix = match.group(1)  # 附則/平成...号
        law_name = match.group(2)      # 平成...号
        article_num = match.group(3)   # 1, 2, etc.
        display_text = match.group(4)  # 附則第1条

        new_filename = f"{law_name}_第{article_num}条.md"
        return f"[[{path_prefix}/{new_filename}|{display_text}]]"

    # [[附則/XX号/XX号_Article_N.md|附則第N条]]
    content = re.sub(
        r'\[\[(附則/([^/]+))/\2_Article_(\d+)\.md\|([^\]]+)\]\]',
        replace_article_link,
        content
    )

    with open(parent_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ 刑法.md の附則リンク修正完了")


def remove_rogue_directories():
    """誤生成されたVault直下の附則ディレクトリを削除"""
    import shutil

    rogue_dir = Path('/Users/haramizuki/Project/DB4LAW/Vault/附則')

    if rogue_dir.exists():
        print(f"🗑️  誤生成ディレクトリ削除中: {rogue_dir}")
        shutil.rmtree(rogue_dir)
        print("✅ 削除完了")
    else:
        print("ℹ️  誤生成ディレクトリは存在しません")


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 附則リンク修正とグレーアウトノード対策")
    print("=" * 60)
    print()

    # Step 1: 親ファイルリンク修正
    print("📝 Step 1: 親ファイルのリンクを修正中...")
    fix_parent_file_links()
    print()

    # Step 2: 誤生成ディレクトリ削除
    print("🗑️  Step 2: 誤生成ディレクトリを削除中...")
    remove_rogue_directories()
    print()

    print("=" * 60)
    print("✨ 全ての処理が完了しました")
    print("=" * 60)
    print()
    print("次のアクション:")
    print("1. Obsidianを再起動してキャッシュをクリア")
    print("2. グラフビューでグレーアウトノードが消えていることを確認")
