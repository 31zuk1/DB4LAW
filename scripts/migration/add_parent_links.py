#!/usr/bin/env python3
"""
法律の親ファイル(.md)に本文・附則へのwikiリンクを追加するスクリプト
"""

import re
import argparse
from pathlib import Path


def extract_article_sort_key(filename: str) -> tuple:
    """
    ファイル名からソート用のキーを抽出
    第1条.md -> (1, 0, 0)
    第1条の2.md -> (1, 2, 0)
    第100条.md -> (100, 0, 0)
    第100条の2.md -> (100, 2, 0)
    第638:640条.md -> (638, 0, 640)  # 範囲形式
    """
    name = filename.replace('.md', '')

    # 範囲形式: 第N:M条
    match = re.match(r'第(\d+):(\d+)条', name)
    if match:
        start_num = int(match.group(1))
        end_num = int(match.group(2))
        return (start_num, 0, end_num)

    # 第N条の形式
    match = re.match(r'第(\d+)条(?:の(\d+))?', name)
    if match:
        main_num = int(match.group(1))
        sub_num = int(match.group(2)) if match.group(2) else 0
        return (main_num, sub_num, 0)

    # 附則第N条の形式
    match = re.match(r'附則第(\d+)条(?:の(\d+))?', name)
    if match:
        main_num = int(match.group(1))
        sub_num = int(match.group(2)) if match.group(2) else 0
        return (main_num, sub_num, 0)

    # その他（附則.md など）
    return (0, 0, 0)


def normalize_suppl_dirname(dirname: str) -> str:
    """
    附則ディレクトリ名を表示用に正規化
    S51_L66 -> 昭和51年法律第66号
    H8_L110 -> 平成8年法律第110号
    R3_L24 -> 令和3年法律第24号
    """
    era_map = {
        'M': '明治',
        'T': '大正',
        'S': '昭和',
        'H': '平成',
        'R': '令和'
    }

    match = re.match(r'([MTSHR])(\d+)_L(\d+)', dirname)
    if match:
        era = era_map.get(match.group(1), match.group(1))
        year = match.group(2)
        law_num = match.group(3)
        return f"{era}{year}年法律第{law_num}号"

    # すでに日本語形式の場合はそのまま返す
    return dirname


def generate_links_for_law(law_dir: Path, dry_run: bool = False) -> str:
    """法律ディレクトリからリンクを生成"""

    law_name = law_dir.name
    main_dir = law_dir / "本文"
    suppl_dir = law_dir / "附則"

    lines = []

    # 本文リンク
    if main_dir.exists():
        article_files = list(main_dir.glob('第*.md'))
        article_files.sort(key=lambda f: extract_article_sort_key(f.name))

        lines.append(f"\n## 本則（全{len(article_files)}条）\n")

        for f in article_files:
            display_name = f.stem  # .md を除去
            lines.append(f"- [[本文/{f.name}|{display_name}]]")

    # 附則リンク
    if suppl_dir.exists():
        kaisei_dir = suppl_dir / "改正法"

        if kaisei_dir.exists():
            # 改正法ディレクトリ内のサブディレクトリを取得
            suppl_subdirs = sorted([d for d in kaisei_dir.iterdir() if d.is_dir()])

            if suppl_subdirs:
                lines.append(f"\n## 附則（改正法: {len(suppl_subdirs)}件）\n")

                for subdir in suppl_subdirs:
                    display_name = normalize_suppl_dirname(subdir.name)
                    # サブディレクトリ内のファイル数をカウント
                    file_count = len(list(subdir.glob('*.md')))

                    # 最初のファイルへのリンク、またはディレクトリ内の代表ファイル
                    files = sorted(subdir.glob('*.md'), key=lambda f: extract_article_sort_key(f.name))
                    if files:
                        first_file = files[0]
                        rel_path = f"附則/改正法/{subdir.name}/{first_file.name}"
                        if file_count == 1:
                            lines.append(f"- [[{rel_path}|{display_name}]]")
                        else:
                            lines.append(f"- [[{rel_path}|{display_name}]] ({file_count}条)")

        # 改正法以外の附則ファイル（直下のファイル）
        direct_suppl_files = list(suppl_dir.glob('*.md'))
        if direct_suppl_files:
            direct_suppl_files.sort(key=lambda f: extract_article_sort_key(f.name))
            lines.append(f"\n### 現行附則\n")
            for f in direct_suppl_files:
                display_name = f.stem
                lines.append(f"- [[附則/{f.name}|{display_name}]]")

    return '\n'.join(lines)


def update_law_file(law_dir: Path, dry_run: bool = False):
    """法律ファイルを更新"""

    law_name = law_dir.name
    law_file = law_dir / f"{law_name}.md"

    if not law_file.exists():
        print(f"エラー: {law_file} が見つかりません")
        return False

    content = law_file.read_text(encoding='utf-8')

    # YAMLフロントマター + Metadata セクションの後に追加
    # 既存のリンクセクションがあれば置換

    # ## 本則 または ## 附則 の開始位置を探す
    existing_links_start = None
    for marker in ['## 本則', '## 附則']:
        pos = content.find(marker)
        if pos != -1:
            if existing_links_start is None or pos < existing_links_start:
                existing_links_start = pos

    if existing_links_start is not None:
        # 既存のリンクセクションを削除
        base_content = content[:existing_links_start].rstrip()
    else:
        base_content = content.rstrip()

    # 新しいリンクを生成
    links_content = generate_links_for_law(law_dir, dry_run)

    new_content = base_content + '\n' + links_content + '\n'

    if dry_run:
        print(f"[DRY-RUN] {law_file.name} を更新します")
        print(f"リンク数: {links_content.count('[[')}")
        print("---")
        print(links_content[:500] + "..." if len(links_content) > 500 else links_content)
    else:
        law_file.write_text(new_content, encoding='utf-8')
        print(f"✓ {law_file.name} を更新しました（リンク数: {links_content.count('[[')}）")

    return True


def main():
    parser = argparse.ArgumentParser(description="法律の親ファイルにリンクを追加")
    parser.add_argument('--law', required=True, help='対象の法律名（例: 民法）')
    parser.add_argument('--dry-run', action='store_true', help='Dry-runモード')
    args = parser.parse_args()

    vault_path = Path("/Users/haramizuki/Project/DB4LAW/Vault/laws")
    law_dir = vault_path / args.law

    if not law_dir.exists():
        print(f"エラー: ディレクトリが見つかりません: {law_dir}")
        return

    update_law_file(law_dir, args.dry_run)


if __name__ == '__main__':
    main()
