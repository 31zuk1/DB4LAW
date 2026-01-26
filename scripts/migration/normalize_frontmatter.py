#!/usr/bin/env python3
"""
Vault frontmatter 正規化スクリプト

Breadcrumbs / Dataview 用のメタデータを既存ファイルに追加する。
既存の frontmatter は保持し、不足分のみ追記する。

追加するフィールド:
- type: law | article | supplement | amendment_fragment
- parent: "[[laws/{law_name}/{law_name}]]" (親法以外)
- tags: 既存を維持しつつ kind/* を追加

Usage:
    python normalize_frontmatter.py --dry-run           # 変更サマリを表示
    python normalize_frontmatter.py --apply             # 実際に適用
    python normalize_frontmatter.py --apply --law 会社法  # 特定法令のみ
"""

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from collections import defaultdict

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.utils.markdown import (
    read_markdown_file,
    write_markdown_file,
    MarkdownDocument,
)


# ============================================================================
# Constants
# ============================================================================

NODE_TYPE_LAW = "law"
NODE_TYPE_ARTICLE = "article"
NODE_TYPE_SUPPLEMENT = "supplement"
NODE_TYPE_AMENDMENT_FRAGMENT = "amendment_fragment"

KIND_TAG_LAW = "kind/law"
KIND_TAG_ARTICLE = "kind/article"
KIND_TAG_SUPPLEMENT = "kind/supplement"
KIND_TAG_AMENDMENT_FRAGMENT = "kind/amendment_fragment"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class NormalizationResult:
    """正規化結果"""
    file_path: Path
    node_type: str
    added_fields: List[str] = field(default_factory=list)
    added_tags: List[str] = field(default_factory=list)
    updated_fields: List[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    error: Optional[str] = None


@dataclass
class NormalizationSummary:
    """正規化サマリ"""
    total_files: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    error_files: int = 0
    by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    added_type_count: int = 0
    added_parent_count: int = 0
    added_kind_tag_count: int = 0


# ============================================================================
# Node Type Detection
# ============================================================================

def detect_node_type(file_path: Path, doc: MarkdownDocument) -> Optional[str]:
    """
    ファイルパスと frontmatter からノード種別を判定

    判定ロジック:
    - 親法ノード: パスが laws/<法令名>/<法令名>.md に一致
    - 条文ノード: パスに /本文/ があり、article_num が存在
    - 改正法断片: amend_law がある、または suppl_kind == 'amendment'
    - 附則ノード: パスに /附則/ があり、改正法断片でない
    """
    parts = file_path.parts

    # laws ディレクトリ配下かチェック
    if "laws" not in parts:
        return None

    laws_idx = parts.index("laws")
    if len(parts) <= laws_idx + 1:
        return None

    law_name = parts[laws_idx + 1]

    # 親法ノード: laws/<法令名>/<法令名>.md
    if file_path.name == f"{law_name}.md" and len(parts) == laws_idx + 3:
        return NODE_TYPE_LAW

    # 本文 (条文ノード)
    if "本文" in parts:
        return NODE_TYPE_ARTICLE

    # 附則配下
    if "附則" in parts:
        # 改正法断片の判定
        metadata = doc.metadata

        # amend_law がある場合は改正法断片
        if metadata.get("amend_law"):
            return NODE_TYPE_AMENDMENT_FRAGMENT

        # suppl_kind == 'amendment' の場合も改正法断片
        if metadata.get("suppl_kind") == "amendment":
            return NODE_TYPE_AMENDMENT_FRAGMENT

        # amendment_law_id がある場合も改正法断片
        if metadata.get("amendment_law_id"):
            return NODE_TYPE_AMENDMENT_FRAGMENT

        # 附則/改正法/ 配下は改正法断片
        if "改正法" in parts:
            return NODE_TYPE_AMENDMENT_FRAGMENT

        # それ以外は通常の附則
        return NODE_TYPE_SUPPLEMENT

    return None


def get_law_name_from_path(file_path: Path) -> Optional[str]:
    """パスから法令名を取得"""
    parts = file_path.parts
    if "laws" not in parts:
        return None

    laws_idx = parts.index("laws")
    if len(parts) <= laws_idx + 1:
        return None

    return parts[laws_idx + 1]


def get_kind_tag(node_type: str) -> str:
    """ノード種別から kind/* タグを取得"""
    mapping = {
        NODE_TYPE_LAW: KIND_TAG_LAW,
        NODE_TYPE_ARTICLE: KIND_TAG_ARTICLE,
        NODE_TYPE_SUPPLEMENT: KIND_TAG_SUPPLEMENT,
        NODE_TYPE_AMENDMENT_FRAGMENT: KIND_TAG_AMENDMENT_FRAGMENT,
    }
    return mapping.get(node_type, "")


# ============================================================================
# Normalization Logic
# ============================================================================

def normalize_file(
    file_path: Path,
    dry_run: bool = True
) -> NormalizationResult:
    """
    単一ファイルを正規化

    Args:
        file_path: 対象ファイル
        dry_run: True の場合は実際に書き込まない

    Returns:
        NormalizationResult
    """
    result = NormalizationResult(file_path=file_path, node_type="")

    # ファイル読み込み
    doc = read_markdown_file(file_path)
    if doc is None:
        result.error = "ファイル読み込み失敗"
        return result

    # ノード種別判定
    node_type = detect_node_type(file_path, doc)
    if node_type is None:
        result.skipped = True
        result.skip_reason = "ノード種別を判定できない"
        return result

    result.node_type = node_type

    # 法令名取得
    law_name = get_law_name_from_path(file_path)
    if law_name is None and node_type != NODE_TYPE_LAW:
        result.error = "法令名を取得できない"
        return result

    # メタデータ更新フラグ
    modified = False

    # 1. type フィールドの追加
    if "type" not in doc.metadata:
        doc.metadata["type"] = node_type
        result.added_fields.append("type")
        modified = True

    # 2. parent フィールドの追加（親法以外）
    if node_type != NODE_TYPE_LAW:
        if "parent" not in doc.metadata:
            parent_link = f"[[laws/{law_name}/{law_name}]]"
            doc.metadata["parent"] = parent_link
            result.added_fields.append("parent")
            modified = True

    # 3. kind/* タグの追加
    kind_tag = get_kind_tag(node_type)
    if kind_tag:
        tags = doc.metadata.get("tags", [])
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            tags = [tags]

        if kind_tag not in tags:
            tags.append(kind_tag)
            doc.metadata["tags"] = tags
            result.added_tags.append(kind_tag)
            modified = True

    # 変更がなければスキップ
    if not modified:
        result.skipped = True
        result.skip_reason = "変更不要（既に正規化済み）"
        return result

    # ファイル書き込み
    if not dry_run:
        if not write_markdown_file(file_path, doc):
            result.error = "ファイル書き込み失敗"
            return result

    return result


def normalize_vault(
    vault_path: Path,
    dry_run: bool = True,
    target_law: Optional[str] = None
) -> tuple[List[NormalizationResult], NormalizationSummary]:
    """
    Vault 全体を正規化

    Args:
        vault_path: Vault ディレクトリパス
        dry_run: True の場合は実際に書き込まない
        target_law: 特定の法令名のみ処理する場合

    Returns:
        (結果リスト, サマリ)
    """
    results: List[NormalizationResult] = []
    summary = NormalizationSummary()

    laws_dir = vault_path / "laws"
    if not laws_dir.exists():
        return results, summary

    # 対象ディレクトリの決定
    if target_law:
        law_dirs = [laws_dir / target_law]
    else:
        law_dirs = sorted([d for d in laws_dir.iterdir() if d.is_dir()])

    for law_dir in law_dirs:
        if not law_dir.exists():
            continue

        # 法令配下の全 .md ファイルを処理
        for md_file in sorted(law_dir.rglob("*.md")):
            summary.total_files += 1

            result = normalize_file(md_file, dry_run)
            results.append(result)

            if result.error:
                summary.error_files += 1
            elif result.skipped:
                summary.skipped_files += 1
            else:
                summary.processed_files += 1
                summary.by_type[result.node_type] += 1

                if "type" in result.added_fields:
                    summary.added_type_count += 1
                if "parent" in result.added_fields:
                    summary.added_parent_count += 1
                if result.added_tags:
                    summary.added_kind_tag_count += 1

    return results, summary


# ============================================================================
# Output Formatting
# ============================================================================

def print_summary(summary: NormalizationSummary, dry_run: bool):
    """サマリを表示"""
    mode = "[DRY-RUN] " if dry_run else ""

    print(f"\n{'='*60}")
    print(f"{mode}Frontmatter 正規化サマリ")
    print(f"{'='*60}")
    print(f"  総ファイル数:     {summary.total_files:,}")
    print(f"  処理済み:         {summary.processed_files:,}")
    print(f"  スキップ:         {summary.skipped_files:,}")
    print(f"  エラー:           {summary.error_files:,}")
    print()
    print(f"  追加: type        {summary.added_type_count:,} ファイル")
    print(f"  追加: parent      {summary.added_parent_count:,} ファイル")
    print(f"  追加: kind/* tag  {summary.added_kind_tag_count:,} ファイル")
    print()
    print("  種別内訳:")
    for node_type, count in sorted(summary.by_type.items()):
        print(f"    {node_type}: {count:,}")
    print(f"{'='*60}\n")


def print_changes(results: List[NormalizationResult], limit: int = 20):
    """変更内容を表示"""
    changes = [r for r in results if not r.skipped and not r.error]

    if not changes:
        print("変更なし")
        return

    print(f"\n変更ファイル（上位 {min(limit, len(changes))} 件）:")
    for r in changes[:limit]:
        rel_path = r.file_path.name
        parts = []
        if r.added_fields:
            parts.append(f"+{','.join(r.added_fields)}")
        if r.added_tags:
            parts.append(f"+tags:{','.join(r.added_tags)}")
        print(f"  {rel_path}: {' '.join(parts)}")

    if len(changes) > limit:
        print(f"  ... 他 {len(changes) - limit} ファイル")


def print_errors(results: List[NormalizationResult]):
    """エラーを表示"""
    errors = [r for r in results if r.error]

    if not errors:
        return

    print(f"\nエラー ({len(errors)} 件):")
    for r in errors[:10]:
        print(f"  {r.file_path}: {r.error}")

    if len(errors) > 10:
        print(f"  ... 他 {len(errors) - 10} 件")


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Vault frontmatter 正規化（Breadcrumbs/Dataview 用）"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="変更せずにサマリを表示"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="実際に変更を適用"
    )
    parser.add_argument(
        "--law", type=str, default=None,
        help="特定の法令名のみ処理（例: 会社法）"
    )
    parser.add_argument(
        "--vault", type=Path,
        default=Path(__file__).parent.parent.parent / "Vault",
        help="Vault ディレクトリパス"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="詳細出力"
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("--dry-run または --apply を指定してください")

    if args.dry_run and args.apply:
        parser.error("--dry-run と --apply は同時に指定できません")

    vault_path = args.vault
    if not vault_path.exists():
        print(f"エラー: Vault が見つかりません: {vault_path}")
        return 1

    dry_run = args.dry_run

    print(f"Vault: {vault_path}")
    if args.law:
        print(f"対象法令: {args.law}")
    print(f"モード: {'DRY-RUN' if dry_run else 'APPLY'}")
    print()

    results, summary = normalize_vault(vault_path, dry_run, args.law)

    print_summary(summary, dry_run)

    if args.verbose or summary.processed_files <= 50:
        print_changes(results)

    print_errors(results)

    if dry_run and summary.processed_files > 0:
        print("適用するには --apply オプションを使用してください")

    return 0


if __name__ == "__main__":
    exit(main())
