#!/usr/bin/env python3
"""
DB4LAW: 改正法断片内の誤解除リンクを復元

unlink_amendment_refs.py のバグにより誤って解除されたリンクを復元する。

対象:
- 改正法断片（suppl_kind: amendment）内のプレーンテキスト参照
- コンテキスト50文字以内に親法名（民法、新民法等）がある場合にリンク化

Usage:
    python scripts/migration/relink_amendment_refs.py --law 民法 --dry-run
    python scripts/migration/relink_amendment_refs.py --law 民法 --apply
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
class RelinkedRef:
    """復元されたリンク情報"""
    file: Path
    original: str
    replacement: str
    context: str


def should_link_reference(context_before: str, law_name: str) -> bool:
    """
    参照をリンク化すべきかを判定

    Args:
        context_before: 参照の直前のテキスト（50文字程度）
        law_name: 親法名

    Returns:
        True: リンク化すべき（法律名付き参照）
        False: リンク化しない（裸の参照）
    """
    # WikiLinkを表示テキストに置換してからチェック
    context_cleaned = re.sub(
        r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]',
        r'\1',
        context_before
    )

    # 法律名のバリエーション
    law_variants = [
        law_name,                    # 民法
        f'新{law_name}',             # 新民法
        f'旧{law_name}',             # 旧民法
        f'改正前の{law_name}',       # 改正前の民法
        f'改正後の{law_name}',       # 改正後の民法
    ]

    # コンテキスト内に法律名バリエーションがあるかチェック
    for variant in law_variants:
        if variant in context_cleaned:
            return True  # 法律名付き → リンク化すべき

    return False  # 裸の参照 → リンク化しない


def kanji_to_arabic(kanji: str) -> str:
    """漢数字をアラビア数字に変換（ファイル名用）"""
    kanji_map = {
        '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
        '六': '6', '七': '7', '八': '8', '九': '9', '〇': '0',
        '十': '', '百': '', '千': '',
    }

    # 位取り漢数字の処理
    result = 0
    current = 0

    for char in kanji:
        if char in '一二三四五六七八九':
            current = int(kanji_map[char])
        elif char == '十':
            if current == 0:
                current = 1
            result += current * 10
            current = 0
        elif char == '百':
            if current == 0:
                current = 1
            result += current * 100
            current = 0
        elif char == '千':
            if current == 0:
                current = 1
            result += current * 1000
            current = 0
        elif char == '〇':
            # 連番表記（一一 → 11）の場合
            if result == 0 and current == 0:
                return kanji.translate(str.maketrans(
                    '一二三四五六七八九〇', '1234567890'
                ))

    result += current
    return str(result) if result > 0 else kanji.translate(str.maketrans(
        '一二三四五六七八九〇', '1234567890'
    ))


def relink_amendment_refs(
    law_dir: Path,
    dry_run: bool = True
) -> Tuple[Dict[str, int], List[RelinkedRef]]:
    """
    改正法断片内の誤解除リンクを復元

    Args:
        law_dir: 法律ディレクトリ
        dry_run: True なら変更を保存しない

    Returns:
        (stats, relinked_refs)
    """
    law_name = law_dir.name
    suppl_dir = law_dir / "附則"

    stats = {
        'files_scanned': 0,
        'files_modified': 0,
        'links_restored': 0,
        'links_skipped': 0,
        'files_skipped': 0,
        'errors': 0
    }

    relinked_refs: List[RelinkedRef] = []

    if not suppl_dir.exists():
        print(f"  附則ディレクトリが見つかりません: {suppl_dir}")
        return stats, relinked_refs

    # プレーンテキストの条文参照パターン
    # 第N条（既存のWikiLinkは除外）
    # 負の後読みで [[ の直後でないことを確認
    plain_ref_pattern = re.compile(
        r'(?<!\|)(?<!\[)(第[一二三四五六七八九十百千〇]+条(?:の[一二三四五六七八九十百千〇]+)?)'
    )

    # 既存WikiLinkを検出するパターン
    wikilink_pattern = re.compile(
        r'\[\[laws/' + re.escape(law_name) + r'/本文/[^\]]+\]\]'
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
            is_amendment = metadata.get('suppl_kind') == 'amendment'
            if not is_amendment:
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

            # 既存のWikiLinkの位置を記録（これらの内部は処理しない）
            wikilink_spans = [(m.start(), m.end()) for m in wikilink_pattern.finditer(body)]

            def is_inside_wikilink(pos: int) -> bool:
                """指定位置がWikiLink内かどうか"""
                for start, end in wikilink_spans:
                    if start <= pos < end:
                        return True
                return False

            # プレーンテキスト参照を検索
            new_body = body
            offset = 0  # 置換による位置ずれを追跡
            file_modified = False

            for match in plain_ref_pattern.finditer(body):
                match_start = match.start()

                # WikiLink内の参照はスキップ
                if is_inside_wikilink(match_start):
                    continue

                ref_text = match.group(1)  # 第七百七十一条

                # コンテキスト取得
                context_start = max(0, match_start - 50)
                context_before = body[context_start:match_start]

                # リンク化すべきか判定
                if should_link_reference(context_before, law_name):
                    # 漢数字をアラビア数字に変換してファイルパスを生成
                    # 第七百七十一条 → 第771条
                    article_match = re.match(r'第([一二三四五六七八九十百千〇]+)条(の([一二三四五六七八九十百千〇]+))?', ref_text)
                    if article_match:
                        main_num = kanji_to_arabic(article_match.group(1))
                        sub_num = article_match.group(3)
                        if sub_num:
                            sub_num = kanji_to_arabic(sub_num)
                            filename = f"第{main_num}条の{sub_num}.md"
                        else:
                            filename = f"第{main_num}条.md"

                        # WikiLink生成
                        wikilink = f"[[laws/{law_name}/本文/{filename}|{ref_text}]]"

                        # 置換位置を計算
                        adjusted_start = match_start + offset
                        adjusted_end = match.end() + offset

                        # 置換実行
                        new_body = new_body[:adjusted_start] + wikilink + new_body[adjusted_end:]
                        offset += len(wikilink) - len(ref_text)

                        file_modified = True
                        stats['links_restored'] += 1

                        relinked_refs.append(RelinkedRef(
                            file=md_file,
                            original=ref_text,
                            replacement=wikilink,
                            context=context_before[-30:] if len(context_before) > 30 else context_before
                        ))
                else:
                    stats['links_skipped'] += 1

            # ファイル更新
            if file_modified:
                new_content = f"---{yaml_str}---{new_body}"

                if not dry_run:
                    md_file.write_text(new_content, encoding='utf-8')

                stats['files_modified'] += 1

        except Exception as e:
            print(f"  エラー: {md_file.name} - {e}")
            stats['errors'] += 1

    return stats, relinked_refs


def main():
    parser = argparse.ArgumentParser(
        description="改正法断片内の誤解除リンクを復元"
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
    print(f"改正法断片 リンク復元 - {args.law}")
    print(f"モード: {'DRY-RUN' if dry_run else '実行'}")
    print(f"{'='*60}\n")

    stats, relinked_refs = relink_amendment_refs(law_dir, dry_run=dry_run)

    # 結果表示
    if args.verbose and relinked_refs:
        print(f"\n[復元されたリンク（最大20件）]\n")
        for ref in relinked_refs[:20]:
            rel_path = ref.file.relative_to(law_dir)
            print(f"  {rel_path}:")
            print(f"    ...{ref.context}{ref.original}")
            print(f"    → {ref.replacement}")
            print()

    print(f"\n{'='*60}")
    print(f"結果:")
    print(f"  スキャン: {stats['files_scanned']}件")
    print(f"  修正対象: {stats['files_modified']}件")
    print(f"  リンク復元: {stats['links_restored']}件")
    print(f"  スキップ: {stats['links_skipped']}件")
    print(f"  エラー: {stats['errors']}件")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
