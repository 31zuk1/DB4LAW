#!/usr/bin/env python3
"""
DB4LAW: 附則ノード修正ツール

附則ファイルを「現行附則」と「改正法附則」に分類し、
- 空見出しを除去
- YAMLスキーマを正規化
- ディレクトリ構造を再編成
"""

import re
import yaml
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
import argparse


# 漢数字→アラビア数字変換マップ
KANJI_TO_NUM = {
    '〇': '0', '一': '1', '二': '2', '三': '3', '四': '4',
    '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
    '十': '', '百': '', '千': ''
}

ERA_MAP = {
    '明治': 'M', '大正': 'T', '昭和': 'S', '平成': 'H', '令和': 'R'
}


@dataclass
class SupplArticle:
    """附則ノード情報"""
    file_path: Path
    law_name: str
    article_number: Optional[int]  # 条番号（ない場合はNone）
    heading: str
    suppl_kind: str  # 'current' | 'amendment'
    amendment_law_title: Optional[str]  # 改正法タイトル（元の漢数字形式）
    amendment_law_normalized: Optional[str]  # 正規化タイトル
    canonical_id: str
    source_id: str  # 元のID
    source_law_id: str  # 元のlaw_id
    has_empty_headings: bool
    content: str


def kanji_num_to_int(kanji_str: str) -> int:
    """
    漢数字を整数に変換

    対応形式:
    - 一桁: 一, 二, 三, ...
    - 十の位あり: 十, 十一, 二十, 二十三, ...
    - 十の位なし（連続形式）: 一六 → 16, 四三 → 43, 一二四 → 124
    """
    if not kanji_str:
        return 0

    kanji_str = kanji_str.strip()

    # 単一文字
    single_map = {'〇': 0, '一': 1, '二': 2, '三': 3, '四': 4,
                  '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}

    # 「十」「百」「千」が含まれるか確認
    has_positional = any(c in kanji_str for c in ['十', '百', '千'])

    if has_positional:
        # 位取り形式: 二十三, 百二十, 千五百 など
        result = 0
        temp = 0

        for char in kanji_str:
            if char == '千':
                if temp == 0:
                    temp = 1
                result += temp * 1000
                temp = 0
            elif char == '百':
                if temp == 0:
                    temp = 1
                result += temp * 100
                temp = 0
            elif char == '十':
                if temp == 0:
                    temp = 1
                result += temp * 10
                temp = 0
            elif char in single_map:
                temp = single_map[char]

        result += temp
        return result
    else:
        # 連続形式: 一六 → 16, 四三 → 43, 一二四 → 124
        digits = []
        for char in kanji_str:
            if char in single_map:
                digits.append(str(single_map[char]))

        if digits:
            return int(''.join(digits))
        return 0


def normalize_amendment_title(title: str) -> str:
    """
    改正法タイトルを正規化

    入力: '昭和一六年三月一二日法律第六一号'
    出力: '昭和16年法律第61号'

    入力: '平成一三年一二月一二日法律第一五三号'
    出力: '平成13年法律第153号'
    """
    if not title:
        return ""

    # パターン: {元号}{年}年{月}月{日}日法律第{号}号
    pattern = r'(明治|大正|昭和|平成|令和)([〇一二三四五六七八九十百千]+)年([〇一二三四五六七八九十百千]+)月([〇一二三四五六七八九十百千]+)日法律第([〇一二三四五六七八九十百千]+)号'

    match = re.match(pattern, title)
    if match:
        era = match.group(1)
        year = kanji_num_to_int(match.group(2))
        law_num = kanji_num_to_int(match.group(5))
        return f"{era}{year}年法律第{law_num}号"

    # フォールバック: 元のタイトルをそのまま返す
    return title


def normalize_amendment_title_short(title: str) -> str:
    """
    改正法タイトルを短縮形式に正規化（ファイル名用）

    入力: '昭和一六年三月一二日法律第六一号'
    出力: 'S16_L61'
    """
    if not title:
        return ""

    pattern = r'(明治|大正|昭和|平成|令和)([〇一二三四五六七八九十百千]+)年([〇一二三四五六七八九十百千]+)月([〇一二三四五六七八九十百千]+)日法律第([〇一二三四五六七八九十百千]+)号'

    match = re.match(pattern, title)
    if match:
        era = ERA_MAP.get(match.group(1), 'X')
        year = kanji_num_to_int(match.group(2))
        law_num = kanji_num_to_int(match.group(5))
        return f"{era}{year}_L{law_num}"

    # フォールバック: アンダースコアで置換
    return re.sub(r'[^\w]', '_', title)


def fix_empty_headings(content: str) -> Tuple[str, bool]:
    """
    空見出しを修正

    Returns:
        Tuple[str, bool]: (修正後のコンテンツ, 空見出しがあったか)
    """
    has_empty = bool(re.search(r'^##\s*$', content, re.MULTILINE))

    # 空見出しを削除（本文は保持）
    # パターン: "## \n本文" → "本文"
    fixed = re.sub(r'^##\s*\n', '', content, flags=re.MULTILINE)

    return fixed, has_empty


def parse_article_file(file_path: Path) -> Optional[SupplArticle]:
    """附則ファイルを解析"""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

    # YAMLフロントマターを分離
    if not content.startswith('---'):
        return None

    parts = content.split('---', 2)
    if len(parts) < 3:
        return None

    yaml_str = parts[1]
    body = parts[2]

    try:
        metadata = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError:
        return None

    # 空見出しチェック
    _, has_empty = fix_empty_headings(body)

    # 改正法タイトル判定
    # ファイルパスから判定: /附則/改正法名/附則第N条.md または /附則/改正法名.md
    parent_dir = file_path.parent
    if parent_dir.name == '附則':
        # 直下のファイル: ファイル名が改正法名
        amendment_title = file_path.stem
        suppl_kind = 'amendment'
    else:
        # サブディレクトリ内: ディレクトリ名が改正法名
        amendment_title = parent_dir.name
        suppl_kind = 'amendment'

    # 条番号抽出
    article_number = None
    article_num_str = metadata.get('article_num', '')
    if article_num_str and article_num_str != '附則' and article_num_str != 'Provision':
        # '附則第1条' → 1, '1' → 1
        match = re.search(r'(\d+)', str(article_num_str))
        if match:
            article_number = int(match.group(1))

    # 正規化ID生成
    law_name = metadata.get('law_name', '刑法')
    if article_number:
        article_part = f"附則第{article_number}条"
    else:
        article_part = "附則"

    amendment_normalized = normalize_amendment_title(amendment_title)
    canonical_id = f"{law_name}_{article_part}__{amendment_normalized}"

    return SupplArticle(
        file_path=file_path,
        law_name=law_name,
        article_number=article_number,
        heading=metadata.get('heading', ''),
        suppl_kind=suppl_kind,
        amendment_law_title=amendment_title,
        amendment_law_normalized=amendment_normalized,
        canonical_id=canonical_id,
        source_id=metadata.get('id', ''),
        source_law_id=metadata.get('law_id', ''),
        has_empty_headings=has_empty,
        content=content
    )


def generate_fixed_content(article: SupplArticle) -> str:
    """修正後のコンテンツを生成"""
    content = article.content

    # YAMLとボディを分離
    parts = content.split('---', 2)
    if len(parts) < 3:
        return content

    yaml_str = parts[1]
    body = parts[2]

    # YAML更新
    try:
        metadata = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError:
        return content

    # 新しいフィールドを追加
    metadata['canonical_id'] = article.canonical_id
    metadata['suppl_kind'] = article.suppl_kind
    if article.amendment_law_title:
        metadata['amendment_law_title'] = article.amendment_law_title
        metadata['amendment_law_normalized'] = article.amendment_law_normalized

    # aliases 生成（既存リンク互換用）
    aliases = []
    if article.article_number:
        aliases.append(f"附則第{article.article_number}条")
        aliases.append(f"suppl_article_{article.article_number}")
    if article.amendment_law_title:
        aliases.append(article.amendment_law_title)

    # 既存のaliasesがあればマージ
    existing_aliases = metadata.get('aliases', [])
    if isinstance(existing_aliases, list):
        aliases = list(set(aliases + existing_aliases))

    metadata['aliases'] = aliases

    # source情報を整理
    metadata['source'] = {
        'provider': 'e-gov',
        'id': article.source_id,
        'law_id': article.source_law_id
    }

    # 空見出しを修正
    fixed_body, _ = fix_empty_headings(body)

    # タイトル行を正規化
    # "# 附則" → "# 附則第N条（見出し）" or "# 附則（改正法名）"
    if article.article_number and article.heading:
        title_line = f"# 附則第{article.article_number}条（{article.heading}）"
    elif article.article_number:
        title_line = f"# 附則第{article.article_number}条"
    elif article.amendment_law_normalized:
        title_line = f"# 附則（{article.amendment_law_normalized}）"
    else:
        title_line = "# 附則"

    # 既存のタイトル行を置換
    fixed_body = re.sub(r'^# .*\n', '', fixed_body.lstrip(), count=1)
    fixed_body = title_line + '\n\n' + fixed_body.lstrip()

    # YAML再シリアライズ
    new_yaml = yaml.dump(metadata, allow_unicode=True, sort_keys=False, default_flow_style=False)

    return f"---\n{new_yaml}---\n\n{fixed_body}"


def get_new_path(article: SupplArticle, base_dir: Path) -> Path:
    """新しいファイルパスを決定"""
    law_dir = base_dir / article.law_name
    suppl_dir = law_dir / '附則'

    if article.suppl_kind == 'current':
        target_dir = suppl_dir / '現行'
    else:
        # 改正法附則: 正規化タイトルでディレクトリ作成
        safe_name = normalize_amendment_title_short(article.amendment_law_title or '')
        target_dir = suppl_dir / '改正法' / safe_name

    if article.article_number:
        filename = f"附則第{article.article_number}条.md"
    else:
        filename = "附則.md"

    return target_dir / filename


def process_law(law_name: str, vault_dir: Path, dry_run: bool = True, limit: int = None) -> Dict:
    """1つの法令の附則を処理"""
    law_dir = vault_dir / 'laws' / law_name
    suppl_dir = law_dir / '附則'

    if not suppl_dir.exists():
        return {'error': f'附則ディレクトリが存在しません: {suppl_dir}'}

    # 附則ファイルを収集
    md_files = list(suppl_dir.rglob('*.md'))

    if limit:
        md_files = md_files[:limit]

    results = {
        'total': len(md_files),
        'processed': 0,
        'empty_headings_fixed': 0,
        'errors': [],
        'articles': []
    }

    for file_path in md_files:
        article = parse_article_file(file_path)
        if not article:
            results['errors'].append(f"解析失敗: {file_path}")
            continue

        results['processed'] += 1
        if article.has_empty_headings:
            results['empty_headings_fixed'] += 1

        # 修正コンテンツ生成
        fixed_content = generate_fixed_content(article)

        # 新しいパス
        new_path = get_new_path(article, vault_dir / 'laws')

        article_info = {
            'old_path': str(file_path),
            'new_path': str(new_path),
            'canonical_id': article.canonical_id,
            'suppl_kind': article.suppl_kind,
            'has_empty_headings': article.has_empty_headings,
            'amendment_law': article.amendment_law_normalized
        }
        results['articles'].append(article_info)

        if not dry_run:
            # ディレクトリ作成
            new_path.parent.mkdir(parents=True, exist_ok=True)

            # ファイル書き込み
            new_path.write_text(fixed_content, encoding='utf-8')

            # 旧ファイルを削除（新しいパスと異なる場合）
            if file_path != new_path and file_path.exists():
                file_path.unlink()
                # 空になったディレクトリを削除
                try:
                    parent = file_path.parent
                    if parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()
                except Exception:
                    pass  # ディレクトリ削除は失敗しても続行

    return results


def main():
    parser = argparse.ArgumentParser(description='附則ノード修正ツール')
    parser.add_argument('--law', default='刑法', help='対象法令名')
    parser.add_argument('--vault', default='/Users/haramizuki/Project/DB4LAW/Vault', help='Vaultディレクトリ')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Dry-runモード（デフォルト）')
    parser.add_argument('--apply', action='store_true', help='実際に変更を適用')
    parser.add_argument('--limit', type=int, help='処理件数制限')

    args = parser.parse_args()

    dry_run = not args.apply
    vault_dir = Path(args.vault)

    print("=" * 80)
    print("附則ノード修正ツール")
    print("=" * 80)
    print(f"対象法令: {args.law}")
    print(f"Vault: {vault_dir}")
    print(f"モード: {'DRY-RUN（変更なし）' if dry_run else '実適用'}")
    if args.limit:
        print(f"処理件数制限: {args.limit}")
    print("=" * 80)
    print()

    results = process_law(args.law, vault_dir, dry_run=dry_run, limit=args.limit)

    if 'error' in results:
        print(f"エラー: {results['error']}")
        return 1

    print(f"処理結果:")
    print(f"  総ファイル数: {results['total']}")
    print(f"  処理成功: {results['processed']}")
    print(f"  空見出し修正: {results['empty_headings_fixed']}")
    print(f"  エラー: {len(results['errors'])}")
    print()

    if results['articles']:
        print("処理対象ファイル:")
        for i, art in enumerate(results['articles'][:10], 1):
            print(f"  {i}. {art['old_path']}")
            print(f"     → {art['new_path']}")
            print(f"     canonical_id: {art['canonical_id']}")
            print(f"     suppl_kind: {art['suppl_kind']}")
            print(f"     空見出し: {'あり' if art['has_empty_headings'] else 'なし'}")
            print()

        if len(results['articles']) > 10:
            print(f"  ... 他 {len(results['articles']) - 10} 件")

    if results['errors']:
        print("\nエラー一覧:")
        for err in results['errors']:
            print(f"  - {err}")

    if dry_run:
        print("\n" + "=" * 80)
        print("これはDRY-RUNです。実際に変更を適用するには:")
        print(f"  python tools/fix_supplementary_articles.py --law {args.law} --apply")
        print("=" * 80)

    return 0


if __name__ == '__main__':
    exit(main())
