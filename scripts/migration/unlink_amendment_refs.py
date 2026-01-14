#!/usr/bin/env python3
"""
DB4LAW: 改正法断片内の親法本文リンクを解除

改正法断片（suppl_kind: amendment）内の親法本文へのリンクを
原則すべてプレーンテキストに戻す。

判定基準:
- 対象: suppl_kind: amendment のファイルのみ（旧形式ディレクトリも含む）
- 解除: [[laws/<法>/本文/<任意>.md|表示]] を原則すべて
        （第N条.md、第38:84条.md のような範囲ノードも含む）
- 維持: リンク直前50文字以内に親法名（例: 民法、新民法、改正前の民法）がある場合のみ

Usage:
    python scripts/migration/unlink_amendment_refs.py --law 民法 --dry-run
    python scripts/migration/unlink_amendment_refs.py --law 民法 --apply
"""

import sys
import re
import argparse
import yaml
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass

# 共通モジュールのインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

# 設定のインポート
from config import get_law_dir


@dataclass
class UnlinkedRef:
    """解除されたリンク情報"""
    file: Path
    original: str
    replacement: str
    reason: str


def is_bare_reference(context_before: str, law_name: str) -> bool:
    """
    リンクが「裸の参照」かどうかを判定

    Args:
        context_before: リンクの直前のテキスト（50文字程度）
        law_name: 親法名

    Returns:
        True: 裸の参照（リンク解除すべき）
        False: 法律名付き参照（維持すべき）
    """
    # 許容パターン: 法名 + (許容文字 | 括弧内テキスト)* + 末尾
    bracket_content = r'(?:[（\(][^）\)]*[）\)])?'
    simple_chars = r'[\s\u3000の「」『』【】、。,.\[\]]*'
    parent_law_pattern = re.escape(law_name) + r'(?:' + simple_chars + bracket_content + r')*' + r'$'

    if re.search(parent_law_pattern, context_before):
        return False  # 法律名付き → 裸ではない

    return True  # 法律名なし → 裸の参照


def unlink_amendment_refs(
    law_dir: Path,
    dry_run: bool = True
) -> Tuple[Dict[str, int], List[UnlinkedRef]]:
    """
    改正法断片内の誤リンクを解除

    Args:
        law_dir: 法律ディレクトリ
        dry_run: True なら変更を保存しない

    Returns:
        (stats, unlinked_refs)
    """
    law_name = law_dir.name
    suppl_dir = law_dir / "附則"

    stats = {
        'files_scanned': 0,
        'files_modified': 0,
        'links_unlinked': 0,
        'links_kept': 0,
        'files_skipped': 0,
        'errors': 0
    }

    unlinked_refs: List[UnlinkedRef] = []

    if not suppl_dir.exists():
        print(f"  附則ディレクトリが見つかりません: {suppl_dir}")
        return stats, unlinked_refs

    # WikiLink パターン: [[laws/<法>/本文/<任意>.md|表示]]
    # 範囲ノード（第38:84条.md）も含めてすべてマッチ
    wikilink_pattern = re.compile(
        r'\[\[laws/' + re.escape(law_name) + r'/本文/([^\]|]+\.md)(?:\|([^\]]+))?\]\]'
    )

    # 附則配下の全 .md ファイルを処理
    for md_file in suppl_dir.rglob('*.md'):
        stats['files_scanned'] += 1

        try:
            content = md_file.read_text(encoding='utf-8')

            if not content.startswith('---'):
                stats['files_skipped'] += 1
                continue

            # YAML frontmatter を分離
            parts = content.split('---', 2)
            if len(parts) < 3:
                stats['files_skipped'] += 1
                continue

            yaml_str = parts[1]
            body = parts[2]

            try:
                metadata = yaml.safe_load(yaml_str)
            except yaml.YAMLError:
                stats['errors'] += 1
                continue

            if not metadata:
                stats['files_skipped'] += 1
                continue

            # suppl_kind: amendment でないファイルはスキップ
            # パスに改正法名があるかもチェック
            is_amendment = metadata.get('suppl_kind') == 'amendment'
            if not is_amendment:
                # パスから推定
                for part in md_file.parts:
                    if '年' in part and '法律' in part and '号' in part:
                        is_amendment = True
                        break
                    if part == '改正法':
                        is_amendment = True
                        break

            if not is_amendment:
                stats['files_skipped'] += 1
                continue

            # リンクを検索して判定
            new_body = body
            file_modified = False

            for match in wikilink_pattern.finditer(body):
                link_full = match.group(0)
                filename = match.group(1)  # 第27条.md, 第38:84条.md など
                display_text = match.group(2)  # 表示テキスト（あれば）

                # マッチ位置の前50文字を取得
                match_start = match.start()
                context_start = max(0, match_start - 50)
                context_before = body[context_start:match_start]

                # 裸の参照かどうか判定
                if is_bare_reference(context_before, law_name):
                    # リンク解除: 表示テキストに置き換え
                    if display_text:
                        replacement = display_text
                    else:
                        # 表示テキストがない場合はファイル名から生成
                        replacement = filename.replace('.md', '')

                    new_body = new_body.replace(link_full, replacement, 1)
                    file_modified = True
                    stats['links_unlinked'] += 1

                    unlinked_refs.append(UnlinkedRef(
                        file=md_file,
                        original=link_full,
                        replacement=replacement,
                        reason="bare_reference"
                    ))
                else:
                    # 法律名付き → 維持
                    stats['links_kept'] += 1

            # ファイル更新
            if file_modified:
                new_content = f"---{yaml_str}---{new_body}"

                if not dry_run:
                    md_file.write_text(new_content, encoding='utf-8')

                stats['files_modified'] += 1

        except Exception as e:
            print(f"  エラー: {md_file.name} - {e}")
            stats['errors'] += 1

    return stats, unlinked_refs


def main():
    parser = argparse.ArgumentParser(
        description="改正法断片内の誤リンクを解除"
    )
    parser.add_argument('--law', required=True, help='対象の法律名（例: 民法）')
    parser.add_argument('--dry-run', action='store_true', help='Dry-runモード（変更なし）')
    parser.add_argument('--apply', action='store_true', help='実際に変更を適用')
    parser.add_argument('--verbose', '-v', action='store_true', help='詳細出力')

    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("エラー: --dry-run または --apply を指定してください")
        sys.exit(1)

    dry_run = not args.apply

    law_dir = get_law_dir(args.law)
    if not law_dir.exists():
        print(f"エラー: ディレクトリが見つかりません: {law_dir}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"改正法断片 誤リンク解除 - {args.law}")
    print(f"モード: {'DRY-RUN' if dry_run else '実行'}")
    print(f"{'='*60}\n")

    stats, unlinked_refs = unlink_amendment_refs(law_dir, dry_run=dry_run)

    # 結果表示
    if args.verbose and unlinked_refs:
        print(f"\n[解除されたリンク（最大20件）]\n")
        for ref in unlinked_refs[:20]:
            rel_path = ref.file.relative_to(law_dir)
            print(f"  {rel_path}:")
            print(f"    {ref.original}")
            print(f"    → {ref.replacement}")
            print()

    print(f"\n{'='*60}")
    print(f"結果:")
    print(f"  スキャン: {stats['files_scanned']}件")
    print(f"  修正対象: {stats['files_modified']}件")
    print(f"  リンク解除: {stats['links_unlinked']}件")
    print(f"  リンク維持: {stats['links_kept']}件")
    print(f"  スキップ: {stats['files_skipped']}件")
    print(f"  エラー: {stats['errors']}件")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
