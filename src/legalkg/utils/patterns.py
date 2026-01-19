"""
共通正規表現パターン定義

このモジュールは、複数のモジュールで使用される正規表現パターンを
一元管理するための薄いユーティリティです。

設計方針:
- パターンとシンプルなヘルパ関数のみを提供
- ビジネスロジックは持たない
- 呼び出し側に依存しない（tier2.py, check_wikilinks.py 双方から安全に使用可能）
"""

import re

# ==============================================================================
# WikiLink パターン
# ==============================================================================

# WikiLinkから表示テキストを抽出するパターン
# [[path|label]] → label, [[label]] → label
# グループ1: 表示テキスト
WIKILINK_DISPLAY_PATTERN = re.compile(r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]')

# WikiLink全体を抽出するパターン
# [[path|label]] → path|label, [[label]] → label
# グループ1: WikiLink内容全体
WIKILINK_FULL_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')


def strip_wikilinks(text: str) -> str:
    """
    WikiLinkを表示テキストに置換する

    [[laws/刑法/本文/第199条.md|第百九十九条]] → 第百九十九条
    [[第百九十九条]] → 第百九十九条

    Args:
        text: WikiLinkを含む可能性のあるテキスト

    Returns:
        WikiLinkが表示テキストに置換されたテキスト
    """
    return WIKILINK_DISPLAY_PATTERN.sub(r'\1', text)
