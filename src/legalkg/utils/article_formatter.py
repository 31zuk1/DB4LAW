"""
DB4LAW: 条文番号変換ユーティリティ

条文番号の各種形式変換を一元管理するモジュール。
- 漢数字 ⇔ 算用数字
- Article_N ⇔ 第N条
- 改正法タイトル ⇔ 正規化キー (H11_L87)
"""

import re
from typing import Optional, Tuple, Dict

# ==============================================================================
# 漢数字変換
# ==============================================================================

KANJI_TO_DIGIT: Dict[str, int] = {
    '〇': 0, '零': 0,
    '一': 1, '壱': 1,
    '二': 2, '弐': 2,
    '三': 3, '参': 3,
    '四': 4,
    '五': 5,
    '六': 6,
    '七': 7,
    '八': 8,
    '九': 9,
}

UNIT_MAP: Dict[str, int] = {
    '十': 10,
    '百': 100,
    '千': 1000,
    '万': 10000,
}

ERA_TO_CODE: Dict[str, str] = {
    '明治': 'M', '大正': 'T', '昭和': 'S', '平成': 'H', '令和': 'R'
}

CODE_TO_ERA: Dict[str, str] = {v: k for k, v in ERA_TO_CODE.items()}


def kanji_to_int(text: str) -> int:
    """
    漢数字を整数に変換

    対応形式:
    - 位取り形式: 二十三 → 23, 百二 → 102, 千二百三十四 → 1234
    - 連結形式: 一一 → 11, 八七 → 87

    Args:
        text: 漢数字文字列

    Returns:
        整数値

    Examples:
        >>> kanji_to_int('二十三')
        23
        >>> kanji_to_int('百二')
        102
        >>> kanji_to_int('一一')
        11
    """
    if not text:
        return 0
    if text.isdigit():
        return int(text)

    # 位取り形式の検出（十百千万が含まれる）
    has_unit = any(c in UNIT_MAP for c in text)

    if has_unit:
        return _parse_positional_kanji(text)
    else:
        return _parse_concatenative_kanji(text)


def _parse_positional_kanji(text: str) -> int:
    """位取り形式の漢数字をパース（二十三 → 23）"""
    total = 0
    current = 0

    for char in text:
        if char in KANJI_TO_DIGIT:
            current = KANJI_TO_DIGIT[char]
        elif char in UNIT_MAP:
            unit = UNIT_MAP[char]
            if current == 0:
                current = 1
            total += current * unit
            current = 0

    total += current
    return total


def _parse_concatenative_kanji(text: str) -> int:
    """連結形式の漢数字をパース（一一 → 11）"""
    result = ''
    for char in text:
        if char in KANJI_TO_DIGIT:
            result += str(KANJI_TO_DIGIT[char])
    return int(result) if result else 0


def kanji_to_arabic_simple(text: str) -> str:
    """
    漢数字を算用数字文字列に変換（単純置換）

    位取りを考慮せず、各文字を個別に変換。
    法律番号の年・号の変換に使用。

    Args:
        text: 漢数字を含む文字列

    Returns:
        算用数字に置換された文字列

    Examples:
        >>> kanji_to_arabic_simple('一一')
        '11'
        >>> kanji_to_arabic_simple('八七')
        '87'
    """
    result = ''
    for char in text:
        if char in KANJI_TO_DIGIT:
            result += str(KANJI_TO_DIGIT[char])
        else:
            result += char
    return result


# ==============================================================================
# 条文番号変換
# ==============================================================================

def article_id_to_japanese(article_id: str) -> str:
    """
    英語形式の条文IDを日本語形式に変換

    Args:
        article_id: 'Article_N' または 'N' 形式

    Returns:
        '第N条' 形式

    Examples:
        >>> article_id_to_japanese('Article_1')
        '第1条'
        >>> article_id_to_japanese('Article_3_2')
        '第3条の2'
        >>> article_id_to_japanese('73:76')
        '第73条から第76条まで'
    """
    # Article_ プレフィックスを除去
    stem = article_id.replace('Article_', '')

    # 範囲形式: 73:76 → 第73条から第76条まで
    if ':' in stem:
        start, end = stem.split(':', 1)
        return f"第{start}条から第{end}条まで"

    # 枝番形式: 3_2 → 第3条の2
    if '_' in stem:
        main, sub = stem.split('_', 1)
        return f"第{main}条の{sub}"

    # 通常形式: 1 → 第1条
    return f"第{stem}条"


def article_filename_to_japanese(old_name: str, is_suppl: bool = False) -> str:
    """
    ファイル名を日本語形式に変換

    Args:
        old_name: 'Article_N.md' 形式
        is_suppl: 附則の場合 True

    Returns:
        '第N条.md' または '附則第N条.md' 形式

    Examples:
        >>> article_filename_to_japanese('Article_1.md')
        '第1条.md'
        >>> article_filename_to_japanese('Article_1.md', is_suppl=True)
        '附則第1条.md'
    """
    stem = old_name.replace('.md', '').replace('Article_', '')
    prefix = '附則' if is_suppl else ''

    # 範囲形式
    if ':' in stem:
        start, end = stem.split(':', 1)
        return f"{prefix}第{start}条から第{end}条まで.md"

    # 枝番形式
    if '_' in stem:
        main, sub = stem.split('_', 1)
        return f"{prefix}第{main}条の{sub}.md"

    # 通常形式
    return f"{prefix}第{stem}条.md"


def parse_japanese_article(text: str) -> Optional[Tuple[int, Optional[int]]]:
    """
    日本語条文番号をパース

    Args:
        text: '第N条' または '第N条のM' 形式

    Returns:
        (条番号, 枝番) のタプル。枝番がない場合は None

    Examples:
        >>> parse_japanese_article('第1条')
        (1, None)
        >>> parse_japanese_article('第3条の2')
        (3, 2)
    """
    # 第N条のM
    match = re.match(r'^第(\d+)条の(\d+)$', text)
    if match:
        return int(match.group(1)), int(match.group(2))

    # 第N条
    match = re.match(r'^第(\d+)条$', text)
    if match:
        return int(match.group(1)), None

    # 附則第N条
    match = re.match(r'^附則第(\d+)条$', text)
    if match:
        return int(match.group(1)), None

    # 附則第N条のM
    match = re.match(r'^附則第(\d+)条の(\d+)$', text)
    if match:
        return int(match.group(1)), int(match.group(2))

    return None


def extract_article_number(text: str) -> Optional[int]:
    """
    テキストから条文番号（主番号のみ）を抽出

    Args:
        text: 条文参照を含むテキスト

    Returns:
        条文番号（整数）

    Examples:
        >>> extract_article_number('第199条')
        199
        >>> extract_article_number('第3条の2')
        3
        >>> extract_article_number('laws/刑法/本文/第199条.md')
        199
    """
    # パスの場合はファイル名を抽出
    if '/' in text:
        text = text.split('/')[-1]
    text = text.replace('.md', '')

    # アンカーを除去
    if '#' in text:
        text = text.split('#')[0]

    parsed = parse_japanese_article(text)
    if parsed:
        return parsed[0]

    return None


def article_sort_key(article_name: str) -> Tuple[int, int, str]:
    """
    条文名のソートキーを生成

    Args:
        article_name: '第N条' または '第N条のM' 形式

    Returns:
        (主番号, 枝番, 元の名前) のタプル

    Examples:
        >>> article_sort_key('第1条')
        (1, 0, '第1条')
        >>> article_sort_key('第3条の2')
        (3, 2, '第3条の2')
    """
    parsed = parse_japanese_article(article_name.replace('.md', ''))
    if parsed:
        main, sub = parsed
        return (main, sub or 0, article_name)
    return (99999, 0, article_name)


# ==============================================================================
# 改正法ID変換
# ==============================================================================

def normalize_amendment_id(raw_name: str) -> str:
    """
    改正法タイトルを正規化キーに変換

    Args:
        raw_name: '平成一一年七月一六日法律第八七号' または 'H11_L87'

    Returns:
        'H11_L87' 形式

    Examples:
        >>> normalize_amendment_id('平成一一年法律第八七号')
        'H11_L87'
        >>> normalize_amendment_id('令和3年法律第37号')
        'R3_L37'
        >>> normalize_amendment_id('H11_L87')
        'H11_L87'
    """
    # すでに正規化されている場合
    if re.match(r'^[MTSHR]\d+_L\d+$', raw_name):
        return raw_name

    # 漢数字パターン
    pattern = r'(明治|大正|昭和|平成|令和)([〇一二三四五六七八九]+)年.*法律第([〇一二三四五六七八九]+)号'
    match = re.search(pattern, raw_name)
    if match:
        era = ERA_TO_CODE.get(match.group(1), 'X')
        year = kanji_to_arabic_simple(match.group(2))
        law_num = kanji_to_arabic_simple(match.group(3))
        return f"{era}{year}_L{law_num}"

    # 算用数字パターン
    pattern2 = r'(明治|大正|昭和|平成|令和)(\d+)年.*法律第(\d+)号'
    match2 = re.search(pattern2, raw_name)
    if match2:
        era = ERA_TO_CODE.get(match2.group(1), 'X')
        return f"{era}{match2.group(2)}_L{match2.group(3)}"

    # 変換できない場合はアンダースコアで安全化
    return re.sub(r'[^\w]', '_', raw_name)


def amendment_key_to_title(key: str) -> str:
    """
    正規化キーを改正法タイトルに変換

    Args:
        key: 'H11_L87' 形式

    Returns:
        '平成11年法律第87号' 形式

    Examples:
        >>> amendment_key_to_title('H11_L87')
        '平成11年法律第87号'
        >>> amendment_key_to_title('R3_L37')
        '令和3年法律第37号'
    """
    match = re.match(r'^([MTSHR])(\d+)_L(\d+)$', key)
    if match:
        era = CODE_TO_ERA.get(match.group(1), match.group(1))
        year = match.group(2)
        law_num = match.group(3)
        return f"{era}{year}年法律第{law_num}号"
    return key


def extract_amendment_key_from_path(file_path) -> Optional[str]:
    """
    ファイルパスから改正法キーを抽出

    Args:
        file_path: Path オブジェクトまたは文字列

    Returns:
        'H11_L87' 形式のキー

    Examples:
        >>> extract_amendment_key_from_path('附則/改正法/H11_L87/附則第1条.md')
        'H11_L87'
    """
    from pathlib import Path
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    parts = file_path.parts
    for i, part in enumerate(parts):
        if part == '改正法' and i + 1 < len(parts):
            return normalize_amendment_id(parts[i + 1])
    return None
