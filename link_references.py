#!/usr/bin/env python3
"""
DB4LAW: 条文参照自動リンク化ツール
明示的条文参照を機械的に抽出し、Obsidian wikilinkに変換する
"""

import re
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import sys

# 漢数字変換マップ
KANJI_TO_NUM = {
    '〇': 0, '零': 0,
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '百': 100, '千': 1000
}

RELATIVE_NUMS = {
    '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
}

@dataclass
class Reference:
    """条文参照情報"""
    target_id: str  # Article_N または Article_N_M
    type: str  # absolute | relative
    original: str  # 元の表現
    snippet: str  # 前後の文脈
    resolved: bool = True
    note: Optional[str] = None
    range_start: Optional[str] = None
    range_end: Optional[str] = None

    def to_dict(self):
        """YAML出力用の辞書に変換"""
        d = {
            'target_id': self.target_id,
            'type': self.type,
            'original': self.original,
            'snippet': self.snippet,
            'resolved': self.resolved
        }
        if self.range_start and self.range_end:
            d['range'] = {'start': self.range_start, 'end': self.range_end}
        if self.note:
            d['note'] = self.note
        return d


def kanji_to_int(kanji_str: str) -> int:
    """漢数字を整数に変換"""
    # 全角数字の処理
    if kanji_str.isdigit():
        return int(kanji_str)

    # 半角数字の処理
    try:
        return int(kanji_str)
    except ValueError:
        pass

    # 漢数字の処理
    result = 0
    temp = 0

    for char in kanji_str:
        if char in ['十', '百', '千']:
            if temp == 0:
                temp = 1
            result += temp * KANJI_TO_NUM[char]
            temp = 0
        elif char in KANJI_TO_NUM:
            temp = KANJI_TO_NUM[char]

    result += temp
    return result


def normalize_article_num(article_str: str) -> Tuple[Optional[int], Optional[int]]:
    """
    条文番号の正規化
    「第百九条」→ (109, None)
    「第三条の二」→ (3, 2)
    """
    # 「第」と「条」を除去
    article_str = article_str.replace('第', '').replace('条', '')

    # 「の」で分割
    if 'の' in article_str:
        parts = article_str.split('の')
        main = kanji_to_int(parts[0].strip())
        sub = kanji_to_int(parts[1].strip()) if len(parts) > 1 else None
        return (main, sub)
    else:
        return (kanji_to_int(article_str.strip()), None)


def article_num_to_id(main: int, sub: Optional[int] = None) -> str:
    """
    条文番号からファイル名形式のIDを生成
    (109, None) → "Article_109"
    (3, 2) → "Article_3_2"
    """
    if sub is not None:
        return f"Article_{main}_{sub}"
    else:
        return f"Article_{main}"


class ReferenceExtractor:
    """条文参照抽出器"""

    def __init__(self, article_file: Path):
        self.article_file = article_file
        self.current_article_num = None
        self.current_law_name = None
        self.available_articles = set()  # 存在する条文ID集合

        # YAML frontmatterを読み込む
        content = article_file.read_text(encoding='utf-8')
        if content.startswith('---'):
            yaml_end = content.find('---', 3)
            if yaml_end > 0:
                yaml_str = content[3:yaml_end]
                metadata = yaml.safe_load(yaml_str)
                article_num_str = str(metadata.get('article_num', '0'))

                # 範囲形式（'73:76'）の場合は最初の番号を使用
                if ':' in article_num_str:
                    article_num_str = article_num_str.split(':')[0]

                # 枝番形式（'117_2'）の場合は主番号を使用
                if '_' in article_num_str:
                    article_num_str = article_num_str.split('_')[0]

                try:
                    self.current_article_num = int(article_num_str)
                except ValueError:
                    self.current_article_num = 0

                self.current_law_name = metadata.get('law_name', '')

        # 同じディレクトリ内の全条文ファイルを取得
        articles_dir = article_file.parent
        for f in articles_dir.glob('Article_*.md'):
            self.available_articles.add(f.stem)  # Article_N の部分

    def extract_references(self, text: str) -> List[Reference]:
        """本文から全ての参照を抽出"""
        refs = []

        # 1. 絶対参照（第N条、第N条のM、第N条第K項など）
        refs.extend(self._extract_absolute_refs(text))

        # 2. 相対参照（前条、次条など）
        refs.extend(self._extract_relative_refs(text))

        # 3. 同条参照
        refs.extend(self._extract_same_article_refs(text, refs))

        # 重複除去（target_id + original が同じものは1つに）
        unique_refs = []
        seen = set()
        for ref in refs:
            key = (ref.target_id, ref.original)
            if key not in seen:
                seen.add(key)
                unique_refs.append(ref)

        return unique_refs

    def _extract_absolute_refs(self, text: str) -> List[Reference]:
        """絶対参照を抽出"""
        refs = []

        # パターン: 第N条（第K項）（第L号）
        # 漢数字、全角数字、半角数字に対応
        pattern = r'第([〇一二三四五六七八九十百千0-9０-９]+(?:の[〇一二三四五六七八九十百千0-9０-９]+)?)条(?:第([〇一二三四五六七八九十百千0-9０-９]+)項)?(?:第([〇一二三四五六七八九十百千0-9０-９]+)号)?'

        for match in re.finditer(pattern, text):
            article_part = match.group(1)
            item_part = match.group(2)  # 項
            clause_part = match.group(3)  # 号

            # 条文番号を正規化
            try:
                main, sub = normalize_article_num(f'第{article_part}条')
                target_id = article_num_to_id(main, sub)

                # 項・号がある場合はアンカーを追加
                anchor = ""
                if item_part:
                    item_num = kanji_to_int(item_part)
                    anchor = f"#第{item_num}項"

                # スニペット取得（前後20文字）
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                snippet = text[start:end].replace('\n', ' ')

                # 存在チェック
                resolved = target_id in self.available_articles
                note = None if resolved else "ファイルが存在しません"

                refs.append(Reference(
                    target_id=target_id + anchor,
                    type='absolute',
                    original=match.group(0),
                    snippet=snippet,
                    resolved=resolved,
                    note=note
                ))
            except Exception as e:
                # パースエラーは無視（曖昧な場合はリンク化しない）
                pass

        return refs

    def _extract_relative_refs(self, text: str) -> List[Reference]:
        """相対参照を抽出（前条、次条、前二条、前条第N項など）"""
        refs = []

        # パターン: 前条（第K項）、次条（第K項）、前項
        patterns = [
            (r'前([二三四五六七八九十])?条(?:第([〇一二三四五六七八九十百千0-9０-９]+)項)?', -1),  # 前条、前二条、前条第2項など
            (r'次([二三四五六七八九十])?条(?:第([〇一二三四五六七八九十百千0-9０-９]+)項)?', 1),   # 次条、次二条、次条第2項など
        ]

        for pattern, direction in patterns:
            for match in re.finditer(pattern, text):
                num_str = match.group(1)  # 二、三など
                item_str = match.group(2)  # 項番号
                count = RELATIVE_NUMS.get(num_str, 1) if num_str else 1

                # 項がある場合はアンカーを追加
                anchor = ""
                if item_str:
                    item_num = kanji_to_int(item_str)
                    anchor = f"#第{item_num}項"

                if direction == -1:  # 前条
                    for i in range(1, count + 1):
                        target_num = self.current_article_num - i
                        if target_num > 0:
                            target_id = article_num_to_id(target_num)

                            # スニペット取得
                            start = max(0, match.start() - 20)
                            end = min(len(text), match.end() + 20)
                            snippet = text[start:end].replace('\n', ' ')

                            resolved = target_id in self.available_articles
                            note = None if resolved else "ファイルが存在しません"

                            refs.append(Reference(
                                target_id=target_id + anchor,
                                type='relative',
                                original=match.group(0),
                                snippet=snippet,
                                resolved=resolved,
                                note=note
                            ))
                elif direction == 1:  # 次条
                    for i in range(1, count + 1):
                        target_num = self.current_article_num + i
                        target_id = article_num_to_id(target_num)

                        start = max(0, match.start() - 20)
                        end = min(len(text), match.end() + 20)
                        snippet = text[start:end].replace('\n', ' ')

                        resolved = target_id in self.available_articles
                        note = None if resolved else "ファイルが存在しません"

                        refs.append(Reference(
                            target_id=target_id + anchor,
                            type='relative',
                            original=match.group(0),
                            snippet=snippet,
                            resolved=resolved,
                            note=note
                        ))

        return refs

    def _extract_same_article_refs(self, text: str, existing_refs: List[Reference]) -> List[Reference]:
        """同条参照を抽出（直前の絶対/相対参照を指す）"""
        refs = []

        # 「同条」パターン
        pattern = r'同条(?:第([〇一二三四五六七八九十百千0-9０-９]+)項)?'

        # 直前の参照を追跡
        last_absolute_target = None

        for match in re.finditer(pattern, text):
            # 同条は直前の絶対参照または相対参照を指す
            # existing_refs から match.start() より前にある最後の参照を取得
            for ref in reversed(existing_refs):
                if text.find(ref.original) < match.start():
                    last_absolute_target = ref.target_id.split('#')[0]  # アンカーを除去
                    break

            if last_absolute_target:
                item_part = match.group(1)
                anchor = ""
                if item_part:
                    item_num = kanji_to_int(item_part)
                    anchor = f"#第{item_num}項"

                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                snippet = text[start:end].replace('\n', ' ')

                resolved = last_absolute_target in self.available_articles
                note = None if resolved else "同条の参照先が不明"

                refs.append(Reference(
                    target_id=last_absolute_target + anchor,
                    type='relative',
                    original=match.group(0),
                    snippet=snippet,
                    resolved=resolved,
                    note=note
                ))
            else:
                # 同条が解決できない場合
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                snippet = text[start:end].replace('\n', ' ')

                refs.append(Reference(
                    target_id="UNRESOLVED",
                    type='relative',
                    original=match.group(0),
                    snippet=snippet,
                    resolved=False,
                    note="同条の参照先が不明"
                ))

        return refs


def process_article(article_file: Path, dry_run: bool = True) -> Dict:
    """1つの条文ファイルを処理"""
    content = article_file.read_text(encoding='utf-8')

    # YAML frontmatterと本文を分離
    if not content.startswith('---'):
        return {'error': 'No YAML frontmatter'}

    yaml_end = content.find('---', 3)
    if yaml_end < 0:
        return {'error': 'Invalid YAML frontmatter'}

    yaml_str = content[3:yaml_end]
    body = content[yaml_end + 3:].lstrip()

    # YAMLをパース
    metadata = yaml.safe_load(yaml_str) or {}

    # 見出し部分と本文を分離（見出しはリンク化しない）
    lines = body.split('\n')
    heading_line_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('# 第') and '条' in line:
            heading_line_idx = i
            break

    # 見出し以降を本文として扱う
    if heading_line_idx >= 0:
        heading = '\n'.join(lines[:heading_line_idx + 1])
        body_content = '\n'.join(lines[heading_line_idx + 1:])
    else:
        heading = ""
        body_content = body

    # 参照を抽出（本文のみから）
    extractor = ReferenceExtractor(article_file)
    references = extractor.extract_references(body_content)

    # 本文を変換（resolved=True のもののみ）
    new_body_content = body_content
    replacements = []

    for ref in references:
        if ref.resolved and 'UNRESOLVED' not in ref.target_id:
            # wikilink形式に変換
            wikilink = f"[[{ref.target_id}]]"

            # 既にリンク化されていないかチェック
            if f"[[{ref.original}]]" not in new_body_content:
                # 元の表現をwikilinkに置換
                # ただし、既に [[...]] になっている場合はスキップ
                pattern = re.escape(ref.original)
                if not re.search(rf'\[\[.*?{pattern}.*?\]\]', new_body_content):
                    new_body_content = new_body_content.replace(ref.original, wikilink, 1)
                    replacements.append((ref.original, wikilink))

    # 見出しと本文を結合
    new_body = heading + '\n' + new_body_content if heading else new_body_content

    # YAMLにreferencesを追加
    metadata['references_explicit'] = [ref.to_dict() for ref in references]
    metadata['references_explicit_count'] = len(references)

    # YAML を再シリアライズ
    new_yaml = yaml.dump(metadata, allow_unicode=True, sort_keys=False, default_flow_style=False)
    new_content = f"---\n{new_yaml}---\n\n{new_body}"

    return {
        'file': article_file.name,
        'references_count': len(references),
        'resolved_count': sum(1 for r in references if r.resolved),
        'unresolved_count': sum(1 for r in references if not r.resolved),
        'replacements': replacements,
        'references': references,
        'old_content': content,
        'new_content': new_content,
        'changed': content != new_content
    }


def dry_run_sample(law_dir: Path, sample_size: int = 10):
    """dry-run: サンプルファイルを処理して差分を表示"""
    articles_dir = law_dir / 'articles' / 'main'

    if not articles_dir.exists():
        print(f"Error: {articles_dir} が存在しません")
        return

    # サンプルファイルを取得
    article_files = sorted(articles_dir.glob('Article_*.md'))[:sample_size]

    print(f"=== DRY RUN: {law_dir.name} ===")
    print(f"処理対象: {len(article_files)} ファイル\n")

    total_refs = 0
    total_resolved = 0
    total_unresolved = 0

    for article_file in article_files:
        result = process_article(article_file, dry_run=True)

        if 'error' in result:
            print(f"[ERROR] {article_file.name}: {result['error']}")
            continue

        total_refs += result['references_count']
        total_resolved += result['resolved_count']
        total_unresolved += result['unresolved_count']

        print(f"{'='*80}")
        print(f"File: {result['file']}")
        print(f"参照数: {result['references_count']} (resolved: {result['resolved_count']}, unresolved: {result['unresolved_count']})")

        if result['references']:
            print(f"\n[抽出された参照]")
            for ref in result['references']:
                status = "✓" if ref.resolved else "✗"
                print(f"  {status} {ref.original} → {ref.target_id} ({ref.type})")
                if not ref.resolved:
                    print(f"     理由: {ref.note}")

        if result['replacements']:
            print(f"\n[本文の変更]")
            for old, new in result['replacements']:
                print(f"  {old} → {new}")

        if result['changed']:
            print(f"\n[YAML差分]")
            print(f"  + references_explicit: {result['references_count']}件")
            print(f"  + references_explicit_count: {result['references_count']}")

        print()

    print(f"{'='*80}")
    print(f"=== 集計 ===")
    print(f"総ファイル数: {len(article_files)}")
    print(f"総参照抽出数: {total_refs}")
    print(f"  - resolved: {total_resolved}")
    print(f"  - unresolved: {total_unresolved}")


if __name__ == '__main__':
    # dry-run実行
    vault_path = Path('/Users/haramizuki/Project/DB4LAW/Vault/laws')

    # 刑法でテスト
    keihan_dir = vault_path / '刑法'

    if keihan_dir.exists():
        dry_run_sample(keihan_dir, sample_size=10)
    else:
        print(f"Error: {keihan_dir} が見つかりません")
