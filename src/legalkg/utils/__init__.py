"""
DB4LAW ユーティリティモジュール
"""

from .article_formatter import (
    kanji_to_int,
    kanji_to_arabic_simple,
    article_id_to_japanese,
    article_filename_to_japanese,
    parse_japanese_article,
    extract_article_number,
    article_sort_key,
    normalize_amendment_id,
    amendment_key_to_title,
    extract_amendment_key_from_path,
)
from .markdown import (
    MarkdownDocument,
    parse_frontmatter,
    serialize_frontmatter,
    read_markdown_file,
    write_markdown_file,
    update_metadata,
    get_metadata_field,
    validate_required_fields,
    MarkdownBatchProcessor,
)

__all__ = [
    # numerals
    'kanji_to_int',
    # article_formatter
    'kanji_to_arabic_simple',
    'article_id_to_japanese',
    'article_filename_to_japanese',
    'parse_japanese_article',
    'extract_article_number',
    'article_sort_key',
    'normalize_amendment_id',
    'amendment_key_to_title',
    'extract_amendment_key_from_path',
    # markdown
    'MarkdownDocument',
    'parse_frontmatter',
    'serialize_frontmatter',
    'read_markdown_file',
    'write_markdown_file',
    'update_metadata',
    'get_metadata_field',
    'validate_required_fields',
    'MarkdownBatchProcessor',
]
