"""
DB4LAW: Markdown/YAMLフロントマター処理ユーティリティ

Obsidian形式のMarkdownファイル（YAMLフロントマター付き）の
読み書きを一元管理するモジュール。
"""

import yaml
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class MarkdownDocument:
    """YAMLフロントマター付きMarkdownドキュメント"""
    metadata: Dict[str, Any]
    body: str
    raw_yaml: str = ""  # 元のYAML文字列（フォーマット保持用）

    def to_string(self) -> str:
        """Markdownファイル形式の文字列に変換"""
        yaml_str = yaml.dump(
            self.metadata,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ).rstrip()
        return f"---\n{yaml_str}\n---\n{self.body}"


def parse_frontmatter(content: str) -> Optional[MarkdownDocument]:
    """
    YAMLフロントマター付きMarkdownをパース

    Args:
        content: Markdownファイルの内容

    Returns:
        MarkdownDocument オブジェクト、パース失敗時は None

    Examples:
        >>> doc = parse_frontmatter('---\\nid: test\\n---\\n# Title')
        >>> doc.metadata['id']
        'test'
        >>> doc.body
        '\\n# Title'
    """
    if not content.startswith('---'):
        return None

    parts = content.split('---', 2)
    if len(parts) < 3:
        return None

    yaml_str = parts[1].strip()
    body = parts[2]

    try:
        metadata = yaml.safe_load(yaml_str)
        if metadata is None:
            metadata = {}
        return MarkdownDocument(
            metadata=metadata,
            body=body,
            raw_yaml=yaml_str
        )
    except yaml.YAMLError:
        return None


def serialize_frontmatter(metadata: Dict[str, Any], body: str) -> str:
    """
    YAMLメタデータと本文をMarkdown形式に結合

    Args:
        metadata: YAMLフロントマターとして出力するdict
        body: Markdown本文

    Returns:
        完全なMarkdownファイル内容

    Examples:
        >>> content = serialize_frontmatter({'id': 'test'}, '# Title')
        >>> print(content)
        ---
        id: test
        ---
        # Title
    """
    yaml_str = yaml.dump(
        metadata,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    return f"---\n{yaml_str}\n---\n{body}"


def read_markdown_file(file_path: Path) -> Optional[MarkdownDocument]:
    """
    Markdownファイルを読み込んでパース

    Args:
        file_path: ファイルパス

    Returns:
        MarkdownDocument オブジェクト、失敗時は None
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        return parse_frontmatter(content)
    except (IOError, OSError):
        return None


def write_markdown_file(
    file_path: Path,
    doc: MarkdownDocument,
    create_parents: bool = True
) -> bool:
    """
    MarkdownDocumentをファイルに書き込み

    Args:
        file_path: 出力先パス
        doc: 書き込むドキュメント
        create_parents: 親ディレクトリを自動作成するか

    Returns:
        成功時 True
    """
    try:
        if create_parents:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(doc.to_string(), encoding='utf-8')
        return True
    except (IOError, OSError):
        return False


def update_metadata(
    file_path: Path,
    updates: Dict[str, Any],
    dry_run: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    ファイルのYAMLメタデータを更新

    Args:
        file_path: 対象ファイル
        updates: 更新するフィールドのdict
        dry_run: True の場合は実際に書き込まない

    Returns:
        (成功フラグ, エラーメッセージ)

    Examples:
        >>> success, error = update_metadata(path, {'law_name': '刑法'})
    """
    doc = read_markdown_file(file_path)
    if doc is None:
        return False, f"ファイル読み込み失敗: {file_path}"

    # メタデータを更新
    doc.metadata.update(updates)

    if not dry_run:
        if not write_markdown_file(file_path, doc):
            return False, f"ファイル書き込み失敗: {file_path}"

    return True, None


def get_metadata_field(
    file_path: Path,
    field: str,
    default: Any = None
) -> Any:
    """
    ファイルのYAMLメタデータから特定フィールドを取得

    Args:
        file_path: 対象ファイル
        field: フィールド名
        default: フィールドが存在しない場合のデフォルト値

    Returns:
        フィールドの値
    """
    doc = read_markdown_file(file_path)
    if doc is None:
        return default
    return doc.metadata.get(field, default)


def validate_required_fields(
    doc: MarkdownDocument,
    required: list
) -> Tuple[bool, list]:
    """
    必須フィールドの存在を検証

    Args:
        doc: 検証対象のドキュメント
        required: 必須フィールド名のリスト

    Returns:
        (全て存在するか, 欠損フィールドのリスト)

    Examples:
        >>> valid, missing = validate_required_fields(doc, ['id', 'law_name'])
        >>> if not valid:
        ...     print(f"Missing fields: {missing}")
    """
    missing = [f for f in required if f not in doc.metadata or doc.metadata[f] is None]
    return len(missing) == 0, missing


class MarkdownBatchProcessor:
    """
    複数Markdownファイルの一括処理ユーティリティ

    Usage:
        processor = MarkdownBatchProcessor(law_dir)
        for doc, path in processor.iter_articles():
            # 処理
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def iter_articles(self, pattern: str = "**/*.md"):
        """
        パターンに一致するMarkdownファイルを順次読み込み

        Yields:
            (MarkdownDocument, Path) のタプル
        """
        for file_path in sorted(self.base_dir.glob(pattern)):
            doc = read_markdown_file(file_path)
            if doc is not None:
                yield doc, file_path

    def count_files(self, pattern: str = "**/*.md") -> int:
        """パターンに一致するファイル数をカウント"""
        return len(list(self.base_dir.glob(pattern)))
