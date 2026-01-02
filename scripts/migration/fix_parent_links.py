#!/usr/bin/env python3
"""刑法.md 内の附則リンクを新しい正規化パスに更新するスクリプト"""

import re
from pathlib import Path

# 元号マッピング
ERA_MAP = {
    '明治': 'M',
    '大正': 'T',
    '昭和': 'S',
    '平成': 'H',
    '令和': 'R',
}

# 漢数字マッピング
KANJI_NUMS = {
    '〇': 0, '一': 1, '二': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
}


def kanji_to_int(kanji_str: str) -> int:
    """漢数字を整数に変換（連続形式対応）"""
    if not kanji_str:
        return 0

    # 位取り形式（十、百、千あり）
    if any(c in kanji_str for c in '十百千'):
        result = 0
        current = 0
        for char in kanji_str:
            if char in KANJI_NUMS:
                current = KANJI_NUMS[char]
            elif char == '十':
                result += (current if current else 1) * 10
                current = 0
            elif char == '百':
                result += (current if current else 1) * 100
                current = 0
            elif char == '千':
                result += (current if current else 1) * 1000
                current = 0
        result += current
        return result
    else:
        # 連続形式（一六 → 16）
        return int(''.join(str(KANJI_NUMS.get(c, 0)) for c in kanji_str))


def normalize_law_title(title: str) -> str:
    """
    昭和一六年三月一二日法律第六一号 → S16_L61
    平成一九年五月二三日法律第五四号 → H19_L54
    """
    pattern = r'(明治|大正|昭和|平成|令和)([〇一二三四五六七八九十]+)年.*法律第([〇一二三四五六七八九十]+)号'
    match = re.search(pattern, title)
    if not match:
        return None

    era = ERA_MAP[match.group(1)]
    year = kanji_to_int(match.group(2))
    law_num = kanji_to_int(match.group(3))

    return f"{era}{year}_L{law_num}"


def update_links(content: str) -> tuple[str, int]:
    """
    [[附則/平成一九年五月二三日法律第五四号/附則第1条.md|...]]
    → [[附則/改正法/H19_L54/附則第1条.md|...]]

    [[附則/平成三年四月一七日法律第三一号.md|...]]
    → [[附則/改正法/H3_L31/附則.md|...]]
    """
    count = 0

    # パターン1: サブディレクトリ形式
    def replace_subdir(match):
        nonlocal count
        old_dir = match.group(1)
        filename = match.group(2)
        label = match.group(3)

        normalized = normalize_law_title(old_dir)
        if normalized:
            count += 1
            return f'[[附則/改正法/{normalized}/{filename}|{label}]]'
        return match.group(0)

    # パターン2: 単一ファイル形式
    def replace_single(match):
        nonlocal count
        old_name = match.group(1)
        label = match.group(2)

        normalized = normalize_law_title(old_name)
        if normalized:
            count += 1
            return f'[[附則/改正法/{normalized}/附則.md|{label}]]'
        return match.group(0)

    # サブディレクトリ形式を処理
    pattern_subdir = r'\[\[附則/([^/\]]+)/([^\]|]+)\|([^\]]+)\]\]'
    content = re.sub(pattern_subdir, replace_subdir, content)

    # 単一ファイル形式を処理
    pattern_single = r'\[\[附則/([^/\]]+\.md)\|([^\]]+)\]\]'
    content = re.sub(pattern_single, replace_single, content)

    return content, count


def main():
    keihoo_path = Path('/Users/haramizuki/Project/DB4LAW/Vault/laws/刑法/刑法.md')

    content = keihoo_path.read_text(encoding='utf-8')
    updated_content, count = update_links(content)

    if count > 0:
        keihoo_path.write_text(updated_content, encoding='utf-8')
        print(f"更新完了: {count} リンクを修正しました")
    else:
        print("修正対象のリンクはありませんでした")

    # 確認用: 残りの旧形式リンクをチェック
    remaining = re.findall(r'\[\[附則/(?!改正法)[^\]]+\]\]', updated_content)
    if remaining:
        print(f"\n警告: まだ旧形式のリンクが {len(remaining)} 件残っています:")
        for link in remaining[:5]:
            print(f"  {link}")


if __name__ == '__main__':
    main()
