#!/usr/bin/env python3
"""
verify_generation.py - Phase A 生成検証スクリプト

生成前後の Vault を比較し、意味的等価性を検証する。
- frontmatter の新規キーは無視可能
- edges.jsonl は Counter で multiset 比較（重複検出）
- body は末尾空白と EOF 改行のみ正規化
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Any, Set, List, Tuple
import yaml


# =============================================================================
# Normalization
# =============================================================================

def normalize_body(text: str) -> str:
    """
    本文の正規化（最小限）:
    - 各行の末尾空白を削除
    - EOF の改行を1つに正規化
    連続空行の圧縮は行わない（意味的差異の可能性）
    """
    lines = text.split('\n')
    # 各行の末尾空白を削除
    lines = [line.rstrip() for line in lines]
    # 末尾の空行を削除してから1つの改行を追加
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines) + '\n' if lines else ''


def normalize_frontmatter(fm: Dict[str, Any], ignore_keys: Set[str]) -> Dict[str, Any]:
    """
    frontmatter から無視キーを除外した辞書を返す
    """
    return {k: v for k, v in fm.items() if k not in ignore_keys}


# =============================================================================
# Parsing
# =============================================================================

def parse_markdown(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Markdown ファイルを frontmatter と body に分離
    Returns: (frontmatter_dict, body_str)
    """
    if not content.startswith('---'):
        return {}, content

    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, content

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        fm = {}

    body = parts[2].lstrip('\n')  # frontmatter 直後の改行は除去
    return fm, body


def load_edges_file(path: Path) -> Counter:
    """
    edges.jsonl を読み込み、Counter として返す
    重複エッジの検出が可能
    """
    if not path.exists():
        return Counter()

    edges = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    edge = json.loads(line)
                    # エッジを正規化（キー順序の違いを吸収）
                    normalized = json.dumps(edge, sort_keys=True, ensure_ascii=False)
                    edges.append(normalized)
                except json.JSONDecodeError:
                    continue

    return Counter(edges)


# =============================================================================
# Comparison
# =============================================================================

class ComparisonResult:
    """比較結果を保持するクラス"""

    def __init__(self):
        self.missing_files: List[str] = []      # snapshot にあるが新規にない
        self.new_files: List[str] = []          # 新規にあるが snapshot にない
        self.frontmatter_diffs: List[Dict] = [] # frontmatter の差異
        self.body_diffs: List[Dict] = []        # body の差異
        self.edge_diffs: List[Dict] = []        # edges.jsonl の差異

    @property
    def is_compatible(self) -> bool:
        """後方互換性があるかどうか"""
        return (
            len(self.missing_files) == 0 and
            len(self.frontmatter_diffs) == 0 and
            len(self.body_diffs) == 0 and
            len(self.edge_diffs) == 0
        )

    def summary(self) -> str:
        """結果サマリを文字列で返す"""
        lines = []
        lines.append(f"Missing files: {len(self.missing_files)}")
        lines.append(f"New files: {len(self.new_files)}")
        lines.append(f"Frontmatter diffs: {len(self.frontmatter_diffs)}")
        lines.append(f"Body diffs: {len(self.body_diffs)}")
        lines.append(f"Edge diffs: {len(self.edge_diffs)}")
        lines.append(f"Compatible: {self.is_compatible}")
        return '\n'.join(lines)


def compare_directories(
    snapshot_dir: Path,
    current_dir: Path,
    ignore_keys: Set[str]
) -> ComparisonResult:
    """
    2つのディレクトリを比較
    """
    result = ComparisonResult()

    # ファイル一覧を取得
    snapshot_files = set()
    current_files = set()

    for f in snapshot_dir.rglob('*'):
        if f.is_file():
            rel = f.relative_to(snapshot_dir)
            snapshot_files.add(str(rel))

    for f in current_dir.rglob('*'):
        if f.is_file():
            rel = f.relative_to(current_dir)
            current_files.add(str(rel))

    # 欠落・追加ファイル
    result.missing_files = sorted(snapshot_files - current_files)
    result.new_files = sorted(current_files - snapshot_files)

    # 共通ファイルを比較
    common_files = snapshot_files & current_files

    for rel_path in sorted(common_files):
        snapshot_file = snapshot_dir / rel_path
        current_file = current_dir / rel_path

        if rel_path.endswith('.md'):
            compare_markdown_files(
                snapshot_file, current_file, rel_path,
                ignore_keys, result
            )
        elif rel_path.endswith('.jsonl') or rel_path == 'edges.jsonl':
            compare_edge_files(
                snapshot_file, current_file, rel_path, result
            )

    return result


def compare_markdown_files(
    snapshot_file: Path,
    current_file: Path,
    rel_path: str,
    ignore_keys: Set[str],
    result: ComparisonResult
):
    """Markdown ファイルを比較"""
    with open(snapshot_file, 'r', encoding='utf-8') as f:
        snapshot_content = f.read()
    with open(current_file, 'r', encoding='utf-8') as f:
        current_content = f.read()

    snap_fm, snap_body = parse_markdown(snapshot_content)
    curr_fm, curr_body = parse_markdown(current_content)

    # frontmatter 比較（ignore_keys を除外）
    snap_fm_norm = normalize_frontmatter(snap_fm, ignore_keys)
    curr_fm_norm = normalize_frontmatter(curr_fm, ignore_keys)

    if snap_fm_norm != curr_fm_norm:
        result.frontmatter_diffs.append({
            'file': rel_path,
            'snapshot': snap_fm_norm,
            'current': curr_fm_norm,
        })

    # body 比較
    snap_body_norm = normalize_body(snap_body)
    curr_body_norm = normalize_body(curr_body)

    if snap_body_norm != curr_body_norm:
        result.body_diffs.append({
            'file': rel_path,
            'snapshot_preview': snap_body_norm[:500],
            'current_preview': curr_body_norm[:500],
        })


def compare_edge_files(
    snapshot_file: Path,
    current_file: Path,
    rel_path: str,
    result: ComparisonResult
):
    """edges.jsonl を Counter で比較"""
    snap_edges = load_edges_file(snapshot_file)
    curr_edges = load_edges_file(current_file)

    if snap_edges != curr_edges:
        # 差分詳細
        missing_edges = snap_edges - curr_edges  # snapshot にあるが current にない
        extra_edges = curr_edges - snap_edges    # current にあるが snapshot にない

        result.edge_diffs.append({
            'file': rel_path,
            'missing_count': sum(missing_edges.values()),
            'extra_count': sum(extra_edges.values()),
            'missing_sample': list(missing_edges.elements())[:5],
            'extra_sample': list(extra_edges.elements())[:5],
        })


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Verify generation compatibility between snapshot and current Vault'
    )
    parser.add_argument(
        '--snapshot', required=True,
        help='Path to snapshot directory'
    )
    parser.add_argument(
        '--current', required=True,
        help='Path to current Vault laws directory'
    )
    parser.add_argument(
        '--law', required=False,
        help='Specific law name to compare (e.g., 会社法)'
    )
    parser.add_argument(
        '--ignore-new-keys', nargs='*', default=[],
        help='Frontmatter keys to ignore (e.g., chapter_num chapter_title)'
    )
    parser.add_argument(
        '--output', '-o', required=False,
        help='Output JSON report path'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show detailed diff information'
    )

    args = parser.parse_args()

    snapshot_base = Path(args.snapshot)
    current_base = Path(args.current)

    if args.law:
        snapshot_dir = snapshot_base / args.law
        current_dir = current_base / args.law
    else:
        snapshot_dir = snapshot_base
        current_dir = current_base

    if not snapshot_dir.exists():
        print(f"Error: Snapshot directory not found: {snapshot_dir}")
        sys.exit(1)
    if not current_dir.exists():
        print(f"Error: Current directory not found: {current_dir}")
        sys.exit(1)

    # Phase A の新規キーをデフォルトで無視
    ignore_keys = set(args.ignore_new_keys) | {
        'chapter_num', 'chapter_title',
        'section_num', 'section_title',
        'has_proviso',
    }

    print(f"Comparing:")
    print(f"  Snapshot: {snapshot_dir}")
    print(f"  Current:  {current_dir}")
    print(f"  Ignoring keys: {sorted(ignore_keys)}")
    print()

    result = compare_directories(snapshot_dir, current_dir, ignore_keys)

    print(result.summary())
    print()

    if args.verbose:
        if result.missing_files:
            print("Missing files:")
            for f in result.missing_files[:20]:
                print(f"  - {f}")
            if len(result.missing_files) > 20:
                print(f"  ... and {len(result.missing_files) - 20} more")
            print()

        if result.new_files:
            print("New files:")
            for f in result.new_files[:20]:
                print(f"  + {f}")
            if len(result.new_files) > 20:
                print(f"  ... and {len(result.new_files) - 20} more")
            print()

        if result.frontmatter_diffs:
            print("Frontmatter differences:")
            for diff in result.frontmatter_diffs[:5]:
                print(f"  File: {diff['file']}")
                print(f"    Snapshot: {diff['snapshot']}")
                print(f"    Current:  {diff['current']}")
            if len(result.frontmatter_diffs) > 5:
                print(f"  ... and {len(result.frontmatter_diffs) - 5} more")
            print()

        if result.body_diffs:
            print("Body differences:")
            for diff in result.body_diffs[:5]:
                print(f"  File: {diff['file']}")
            if len(result.body_diffs) > 5:
                print(f"  ... and {len(result.body_diffs) - 5} more")
            print()

        if result.edge_diffs:
            print("Edge differences:")
            for diff in result.edge_diffs:
                print(f"  File: {diff['file']}")
                print(f"    Missing: {diff['missing_count']}, Extra: {diff['extra_count']}")
            print()

    # JSON レポート出力
    if args.output:
        report = {
            'compatible': result.is_compatible,
            'missing_files': result.missing_files,
            'new_files': result.new_files,
            'frontmatter_diffs': result.frontmatter_diffs,
            'body_diffs': [{'file': d['file']} for d in result.body_diffs],
            'edge_diffs': result.edge_diffs,
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Report written to: {args.output}")

    # 互換性がない場合は exit code 1
    sys.exit(0 if result.is_compatible else 1)


if __name__ == '__main__':
    main()
