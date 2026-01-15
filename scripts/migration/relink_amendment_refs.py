#!/usr/bin/env python3
"""
DB4LAW: 改正法断片内の誤解除リンクを復元

unlink_amendment_refs.py のバグにより誤って解除されたリンクを復元する。

対象条件（すべて満たす場合のみリンク化）:
1. suppl_kind: amendment のファイルのみ（パス推定も含む）
2. laws/<親法>/本文/ へのリンクのみ（他法は対象外）
3. 同一文（句点から句点まで）限定
4. 最後に出現した親法名バリエーション以降（tail）で判定
5. 照応語（同法、同条等）があればスコープOFF
6. 段落区切り（改行2連続）でスコープリセット

親法名バリエーション:
- 民法, 新民法, 旧民法, 改正前の民法, 改正後の民法

スコープリセット照応語:
- 同法, 同条, 同項, 同号, 同表, 同附則
- 前条, 次条, 前項, 次項, 前号, 次号
- 本条, 本項, 本号
- その, 当該（間接参照）

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


def get_law_name_variants(law_name: str) -> tuple:
    """法律名のバリエーションを返す"""
    return (
        law_name,                    # 民法
        f'新{law_name}',             # 新民法
        f'旧{law_name}',             # 旧民法
        f'改正前の{law_name}',       # 改正前の民法
        f'改正後の{law_name}',       # 改正後の民法
    )


# スコープをリセットする照応語パターン
# これらが法名出現後（tail）に含まれていればスコープをOFFにする
SCOPE_RESET_PATTERNS: tuple = (
    # 同〜参照
    '同法', '同条', '同項', '同号', '同表', '同附則',
    # 前後参照
    '前条', '次条', '前項', '次項', '前号', '次号',
    # 本〜参照
    '本条', '本項', '本号',
    # 間接参照（指示語）
    'その', '当該',
)


def has_parent_law_scope(body: str, match_position: int, law_name: str) -> bool:
    """
    親法スコープ内かどうかを判定（同一文限定・tail判定）

    「親法スコープ」= 法律名（民法/新民法等）が出現してから、
    スコープリセット条件に当たるまでの範囲。
    この範囲内では、裸の第N条も親法への参照としてリンク化する。

    スコープ判定ルール:
    1. 同一文内（句点から現在位置まで）を対象
    2. 段落区切り（改行2連続）があればその後ろのみ対象
    3. 最後に出現した親法名バリエーションの位置を特定
    4. その位置より後（tail）に照応語（同法、同条等）があればスコープOFF

    安全策:
    - laws/<親法>/本文/ のみ（外部法は対象外）
    - WikiLinkは表示テキストに置換してからチェック

    Args:
        body: ファイル本文（frontmatter除く）
        match_position: マッチ位置
        law_name: 親法名

    Returns:
        True: 親法スコープ内（リンク化すべき）
        False: スコープ外（リンク化しない）
    """
    # 現在位置より前のテキストを取得
    before_text = body[:match_position]

    # 最後の句点（。）を探す（文の開始位置）
    last_period = before_text.rfind('。')
    sentence_start = last_period + 1 if last_period >= 0 else 0

    # 現在の文（句点から現在位置まで）を取得
    current_sentence = before_text[sentence_start:]

    # 段落区切り（改行2連続）があればその後ろのみ対象
    paragraph_break = current_sentence.rfind('\n\n')
    if paragraph_break >= 0:
        current_sentence = current_sentence[paragraph_break + 2:]

    # WikiLinkを表示テキストに置換してからチェック
    # [[laws/民法/本文/第749条.md|第七百四十九条]] → 第七百四十九条
    sentence_cleaned = re.sub(
        r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]',
        r'\1',
        current_sentence
    )

    # 法律名バリエーションの最後の出現位置を探す
    variants = get_law_name_variants(law_name)
    last_law_pos = -1
    for variant in variants:
        pos = sentence_cleaned.rfind(variant)
        if pos > last_law_pos:
            last_law_pos = pos

    # 法律名が見つからなければスコープ外
    if last_law_pos < 0:
        return False

    # tail = 最後の法律名出現位置以降のテキスト
    tail = sentence_cleaned[last_law_pos:]

    # tail内に照応語（同法、同条等）があればスコープをリセット
    for reset_pattern in SCOPE_RESET_PATTERNS:
        if reset_pattern in tail:
            return False

    return True


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

                # 親法スコープ判定（同一文限定）
                if has_parent_law_scope(body, match_start, law_name):
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

                        # 文脈取得（句点から現在位置まで）
                        before_text = body[:match_start]
                        last_period = before_text.rfind('。')
                        sentence_start = last_period + 1 if last_period >= 0 else 0
                        sentence_context = before_text[sentence_start:]
                        # 表示用に最後の40文字に制限
                        display_context = sentence_context[-40:] if len(sentence_context) > 40 else sentence_context

                        relinked_refs.append(RelinkedRef(
                            file=md_file,
                            original=ref_text,
                            replacement=wikilink,
                            context=display_context
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
