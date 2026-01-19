#!/usr/bin/env python3
"""
WikiLink整合性チェッカー

Vault内のMarkdownファイルからWikiLinkを抽出し、
リンク先ファイルが存在しない「空リンク」を検出する。

Usage:
    python3 scripts/qa/check_wikilinks.py --vault ./Vault
    python3 scripts/qa/check_wikilinks.py --vault ./Vault --only-prefix laws/
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set


@dataclass
class BrokenLink:
    """空リンク情報"""
    source_file: str
    link_text: str
    target_path: str
    line_no: int


# WikiLink抽出用の正規表現
# [[path]], [[path|alias]], [[path#heading]], [[path^blockid]], [[path#heading|alias]]
WIKILINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')


def parse_wikilink(link_content: str) -> Optional[str]:
    """
    WikiLinkの内容からファイルパス部分を抽出

    Args:
        link_content: [[...]] 内の文字列

    Returns:
        ファイルパス（存在チェック対象）、またはNone（スキップ対象）
    """
    # 外部リンク（http://、https://、mailto:）をスキップ
    if link_content.startswith(('http://', 'https://', 'mailto:')):
        return None

    # エイリアス部分を除去: [[path|alias]] → path
    if '|' in link_content:
        link_content = link_content.split('|')[0]

    # ヘディング部分を除去: [[path#heading]] → path
    if '#' in link_content:
        link_content = link_content.split('#')[0]

    # ブロックID部分を除去: [[path^blockid]] → path
    if '^' in link_content:
        link_content = link_content.split('^')[0]

    # 空になった場合はスキップ（[[#heading]]のようなケース）
    if not link_content.strip():
        return None

    return link_content.strip()


def is_absolute_vault_path(link_path: str, vault_root: Path) -> bool:
    """
    リンクパスがVaultルートからの絶対パスかどうかを判定

    Args:
        link_path: WikiLinkから抽出したパス
        vault_root: Vaultのルートディレクトリ

    Returns:
        True: 絶対パス（Vaultルートからのパス）
        False: 相対パス
    """
    # パスの最初のセグメントがVault直下のディレクトリと一致するか確認
    first_segment = link_path.split('/')[0]
    return (vault_root / first_segment).is_dir()


def resolve_link_path(
    link_path: str,
    source_file: Path,
    vault_root: Path
) -> Optional[Path]:
    """
    WikiLinkパスを解決してファイルパスを返す

    解決順序:
    1. Vaultルートからの絶対パス（パスがVault直下のディレクトリで始まる場合）
    2. ソースファイルからの相対パス
    3. Vaultルートからの絶対パス（フォールバック）

    Args:
        link_path: WikiLinkから抽出したパス
        source_file: ソースファイルのパス
        vault_root: Vaultのルートディレクトリ

    Returns:
        解決されたファイルパス（存在する場合）、またはNone
    """
    # .mdがない場合は追加
    if not link_path.endswith('.md'):
        link_path = link_path + '.md'

    # 1. Vault直下のディレクトリで始まる場合は絶対パスとして扱う
    if is_absolute_vault_path(link_path, vault_root):
        absolute_target = vault_root / link_path
        if absolute_target.exists():
            return absolute_target
        # 絶対パスとして指定されているが存在しない
        return None

    # 2. ソースファイルからの相対パスとして解決を試みる
    source_dir = source_file.parent
    relative_target = source_dir / link_path
    if relative_target.exists():
        return relative_target

    # 3. Vaultルートからの絶対パスとして解決を試みる（フォールバック）
    absolute_target = vault_root / link_path
    if absolute_target.exists():
        return absolute_target

    # どちらも存在しない場合はNone
    return None


def get_target_path_for_report(
    link_path: str,
    source_file: Path,
    vault_root: Path
) -> str:
    """
    レポート用のターゲットパス文字列を生成

    Args:
        link_path: WikiLinkから抽出したパス
        source_file: ソースファイルのパス
        vault_root: Vaultのルートディレクトリ

    Returns:
        レポート用のパス文字列
    """
    # .mdがない場合は追加
    if not link_path.endswith('.md'):
        link_path = link_path + '.md'

    # Vault直下のディレクトリで始まる場合は絶対パスとして表示
    if is_absolute_vault_path(link_path, vault_root):
        return link_path

    # 相対パスの場合はソースからの完全パスを計算
    source_dir = source_file.parent
    relative_target = source_dir / link_path

    try:
        return str(relative_target.relative_to(vault_root))
    except ValueError:
        return link_path


def load_ignore_patterns(ignore_file: Path) -> Set[str]:
    """
    ignoreファイルからパターンを読み込む

    フォーマット仕様:
    - 空行は無視
    - 行頭が `#` の行はコメントとして無視
    - 行途中に `#` がある場合、`#` より前のみをパターンとして採用
      例: "laws/民法/本文/第71条.md  # 旧条文" → "laws/民法/本文/第71条.md"
    - 前後の空白は strip する

    Args:
        ignore_file: ignoreファイルのパス

    Returns:
        ignoreパターンのセット
    """
    patterns = set()
    if ignore_file.exists():
        with open(ignore_file, 'r', encoding='utf-8') as f:
            for line in f:
                # インラインコメントを除去（# 以降を削除）
                if '#' in line:
                    line = line.split('#', 1)[0]
                line = line.strip()
                # 空行をスキップ
                if line:
                    patterns.add(line)
    return patterns


def should_ignore(target_path: str, ignore_patterns: Set[str]) -> bool:
    """
    ignoreパターンに部分一致するかチェック

    Args:
        target_path: チェック対象のパス
        ignore_patterns: ignoreパターンのセット

    Returns:
        True: 無視すべき, False: チェック対象
    """
    for pattern in ignore_patterns:
        if pattern in target_path:
            return True
    return False


def extract_wikilinks_from_file(
    file_path: Path,
    vault_root: Path
) -> List[tuple]:
    """
    ファイルからWikiLinkを抽出

    Args:
        file_path: Markdownファイルのパス
        vault_root: Vaultのルートディレクトリ

    Returns:
        (link_text, raw_link_path, line_no) のリスト
        raw_link_pathは[[...]]内のパス部分（.md付与済み）
    """
    links = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_no, line in enumerate(f, 1):
                for match in WIKILINK_PATTERN.finditer(line):
                    link_content = match.group(1)
                    link_text = match.group(0)  # [[...]] 全体

                    parsed_path = parse_wikilink(link_content)
                    if parsed_path is None:
                        continue

                    # .mdがない場合は追加
                    if not parsed_path.endswith('.md'):
                        parsed_path = parsed_path + '.md'

                    links.append((link_text, parsed_path, line_no))
    except Exception as e:
        print(f"Warning: Failed to read {file_path}: {e}", file=sys.stderr)

    return links


def check_wikilinks(
    vault_root: Path,
    ignore_patterns: Set[str],
    only_prefix: Optional[str] = None
) -> tuple:
    """
    Vault内のWikiLinkを検証

    Args:
        vault_root: Vaultのルートディレクトリ
        ignore_patterns: ignoreパターンのセット
        only_prefix: 特定のプレフィックスに限定（例: "laws/"）

    Returns:
        (scanned_files, total_links, broken_links)
    """
    scanned_files = 0
    total_links = 0
    broken_links: List[BrokenLink] = []

    # 検索パスを決定
    search_path = vault_root
    if only_prefix:
        search_path = vault_root / only_prefix
        if not search_path.exists():
            print(f"Warning: Prefix path does not exist: {search_path}", file=sys.stderr)
            search_path = vault_root

    # Markdownファイルを再帰的に走査
    for md_file in search_path.rglob('*.md'):
        # 隠しファイル・ディレクトリをスキップ
        if any(part.startswith('.') for part in md_file.parts):
            continue

        scanned_files += 1
        source_relative = str(md_file.relative_to(vault_root))

        links = extract_wikilinks_from_file(md_file, vault_root)

        for link_text, raw_link_path, line_no in links:
            total_links += 1

            # リンク先の解決を試みる（相対パス→絶対パスの順）
            resolved = resolve_link_path(raw_link_path, md_file, vault_root)

            if resolved is not None:
                # リンク先が存在する
                continue

            # レポート用のターゲットパスを生成
            target_path = get_target_path_for_report(raw_link_path, md_file, vault_root)

            # ignoreパターンに一致する場合はスキップ
            if should_ignore(target_path, ignore_patterns):
                continue

            broken_links.append(BrokenLink(
                source_file=source_relative,
                link_text=link_text,
                target_path=target_path,
                line_no=line_no
            ))

    return scanned_files, total_links, broken_links


def generate_json_report(broken_links: List[BrokenLink], output_path: Path):
    """JSONレポートを生成"""
    report = {
        "generated_at": datetime.now().isoformat(),
        "broken_count": len(broken_links),
        "broken_links": [asdict(link) for link in broken_links]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def generate_md_report(
    broken_links: List[BrokenLink],
    output_path: Path,
    limit: int = 100
):
    """Markdownレポートを生成（ターゲット別にグループ化）"""

    # ターゲットパスでグループ化
    by_target: Dict[str, List[BrokenLink]] = defaultdict(list)
    for link in broken_links:
        by_target[link.target_path].append(link)

    # ターゲット数でソート（多い順）
    sorted_targets = sorted(by_target.items(), key=lambda x: -len(x[1]))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# WikiLink整合性チェックレポート\n\n")
        f.write(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## サマリー\n\n")
        f.write(f"- **空リンク総数**: {len(broken_links)}\n")
        f.write(f"- **ユニークなターゲット数**: {len(by_target)}\n\n")

        if not broken_links:
            f.write("空リンクはありません。\n")
            return

        f.write("## 空リンク一覧（ターゲット別）\n\n")
        f.write(f"※ 上位{limit}件を表示\n\n")

        shown = 0
        for target_path, links in sorted_targets:
            if shown >= limit:
                f.write(f"\n... 他 {len(sorted_targets) - shown} ターゲット省略\n")
                break

            f.write(f"### `{target_path}`\n\n")
            f.write(f"- 参照数: {len(links)}\n")
            f.write(f"- 参照元（最大5件）:\n")

            for link in links[:5]:
                f.write(f"  - `{link.source_file}` (L{link.line_no})\n")

            if len(links) > 5:
                f.write(f"  - ... 他 {len(links) - 5} 件\n")

            f.write("\n")
            shown += 1


def main():
    parser = argparse.ArgumentParser(
        description='WikiLink整合性チェッカー - 空リンクを検出'
    )
    parser.add_argument(
        '--vault',
        type=Path,
        default=Path('./Vault'),
        help='Vaultのルートディレクトリ (default: ./Vault)'
    )
    parser.add_argument(
        '--limit-md',
        type=int,
        default=100,
        help='MDレポートに載せる最大件数 (default: 100)'
    )
    parser.add_argument(
        '--only-prefix',
        type=str,
        default=None,
        help='特定のプレフィックスに限定 (例: laws/)'
    )
    parser.add_argument(
        '--ignore-file',
        type=Path,
        default=Path('scripts/qa/link_check_ignore.txt'),
        help='除外パターンファイル (default: scripts/qa/link_check_ignore.txt)'
    )

    args = parser.parse_args()

    vault_root = args.vault.resolve()
    if not vault_root.exists():
        print(f"Error: Vault directory not found: {vault_root}", file=sys.stderr)
        sys.exit(2)

    # ignoreパターンを読み込み
    ignore_patterns = load_ignore_patterns(args.ignore_file)
    if ignore_patterns:
        print(f"Loaded {len(ignore_patterns)} ignore patterns")

    # チェック実行
    print(f"Scanning {vault_root}...")
    if args.only_prefix:
        print(f"  Prefix filter: {args.only_prefix}")

    scanned_files, total_links, broken_links = check_wikilinks(
        vault_root,
        ignore_patterns,
        args.only_prefix
    )

    # サマリー出力
    print("\n" + "=" * 50)
    print("WikiLink整合性チェック結果")
    print("=" * 50)
    print(f"  Scanned files:  {scanned_files:,}")
    print(f"  Total links:    {total_links:,}")
    print(f"  Broken links:   {len(broken_links):,}")
    print("=" * 50)

    # レポート出力
    reports_dir = vault_root / 'reports'
    json_path = reports_dir / 'link_check_broken.json'
    md_path = reports_dir / 'link_check_broken.md'

    generate_json_report(broken_links, json_path)
    generate_md_report(broken_links, md_path, args.limit_md)

    print(f"\nReports generated:")
    print(f"  - {json_path}")
    print(f"  - {md_path}")

    # 終了コード
    if broken_links:
        print(f"\n❌ Found {len(broken_links)} broken link(s)")
        sys.exit(1)
    else:
        print("\n✓ All links are valid")
        sys.exit(0)


if __name__ == '__main__':
    main()
