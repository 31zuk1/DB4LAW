"""
DB4LAW: 漢数字変換モジュール（後方互換ラッパー）

このモジュールは後方互換性のために維持されています。
実装は article_formatter.py に統合されました。

使用例:
    from legalkg.utils.numerals import kanji_to_int
    kanji_to_int('二十三')  # → 23
"""

from .article_formatter import kanji_to_int

__all__ = ['kanji_to_int']
