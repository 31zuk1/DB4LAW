"""
DB4LAW: 編/章/節タイトルの表示整形ユーティリティ
"""

from typing import Optional
import re


_STRUCTURE_NUM_TEXT = r"[0-9０-９一二三四五六七八九十百千万〇零]+"


def extract_structure_subtitle(title: Optional[str], unit: str) -> Optional[str]:
    """
    編/章/節タイトルから先頭の番号表記を除去して副題を返す。

    例:
    - 第一章 総則 -> 総則
    - 第二章の二 社債管理補助者 -> 社債管理補助者
    - 第一章 -> None
    """
    if not title:
        return None
    normalized = title.strip()
    pattern = rf"^第{_STRUCTURE_NUM_TEXT}{unit}(?:の{_STRUCTURE_NUM_TEXT})?"
    normalized = re.sub(pattern, "", normalized, count=1).lstrip(" \u3000\t")
    return normalized if normalized else None


def format_part_name(part_num: int) -> str:
    """編番号を可読ファイル名形式に変換: 1 -> 第1編"""
    return f"第{part_num}編"


def format_chapter_name(chapter_num: int, chapter_title: Optional[str] = None) -> str:
    """
    章番号を可読ファイル名形式に変換。

    e-Gov の章番号エンコーディング:
    - 182 = 第十八章の二 -> 第18章の2
    - 22 = 第二章の二 -> 第2章の2 (chapter_title に「章の」が含まれる場合)
    - 18 = 第十八章 -> 第18章
    """
    if chapter_title and "章の" in chapter_title:
        main_num = chapter_num // 10
        sub_num = chapter_num % 10
        return f"第{main_num}章の{sub_num}"
    if chapter_num >= 100 and chapter_num % 10 != 0:
        main_num = chapter_num // 10
        sub_num = chapter_num % 10
        return f"第{main_num}章の{sub_num}"
    return f"第{chapter_num}章"


def format_section_name(section_num: int, section_title: Optional[str] = None) -> str:
    """
    節番号を可読ファイル名形式に変換。

    e-Gov の節番号エンコーディング:
    - 12 = 第一節の二 -> 第1節の2 (section_title に「節の」が含まれる場合)
    - 42 = 第四節の二 -> 第4節の2
    - 12 = 第十二節 -> 第12節
    """
    if section_title and "節の" in section_title:
        main_num = section_num // 10
        sub_num = section_num % 10
        return f"第{main_num}節の{sub_num}"
    return f"第{section_num}節"
