#!/usr/bin/env python3
"""
DB4LAW: ID衝突問題の修正スクリプト

問題A: 附則条文のID重複を解消
- canonical_id を改正法IDを含む形式に統一
- id フィールドは e-Gov 互換のまま維持（source.id に移動）

問題B/C: 外部法参照・削除条文の検出とスタブ生成

問題D: 削除条文の範囲ノードへのリダイレクト
- 第156条 への参照を 第155:157条.md へ自動リダイレクト
"""

import re
import sys
import yaml
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field

# 共通モジュールのインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))
from legalkg.utils.article_formatter import (
    normalize_amendment_id,
    extract_amendment_key_from_path,
)
from legalkg.utils.markdown import parse_frontmatter, serialize_frontmatter

# 設定と pending links 機能
from config import get_law_dir, LAWS_PATH
from pending_links import (
    PendingLink,
    create_pending_link,
    append_pending,
    extract_amendment_info_from_path,
    extract_article_number_from_link,
    DEFAULT_PENDING_LOG,
)


@dataclass
class ArticleRange:
    """削除条文の範囲情報"""
    start: int
    end: int
    filename: str

    def contains(self, article_num: int) -> bool:
        """指定された条文番号がこの範囲に含まれるか"""
        return self.start <= article_num <= self.end

    def span(self) -> int:
        """範囲の長さ"""
        return self.end - self.start


@dataclass
class RangeRedirect:
    """範囲ノードへのリダイレクト情報"""
    source_file: Path
    original_text: str
    original_target: str
    new_target: str
    article_num: int


@dataclass
class UnresolvedLink:
    """未解決リンク情報"""
    source_file: Path
    target_path: str
    original_text: str
    reason: str  # 'external_law' | 'missing_article' | 'deleted_article'
    external_law_name: Optional[str] = None
    # pending links 用の追加フィールド
    display_text: Optional[str] = None  # 表示テキスト
    context_before: str = ""  # リンク前の文脈（最大200文字）
    context_after: str = ""   # リンク後の文脈（最大200文字）
    match_span: Optional[Dict[str, int]] = None  # {"start": int, "end": int}


def extract_amendment_id_from_path(file_path: Path) -> Optional[str]:
    """
    ファイルパスから改正法IDを抽出
    .../附則/改正法/H11_L87/附則第1条.md → 'H11_L87'

    Note: normalize_amendment_id は article_formatter からインポート済み
    """
    # 共通モジュールを使用
    return extract_amendment_key_from_path(file_path)


def build_range_index(law_dir: Path) -> List[ArticleRange]:
    """
    本文ディレクトリ内の範囲ノードをインデックス化

    対応形式:
    - 旧形式: 第155:157条.md
    - 新形式: 第155条から第157条まで.md

    例: ArticleRange(155, 157, "第155条から第157条まで.md")
    """
    ranges = []
    honbun_dir = law_dir / "本文"

    if not honbun_dir.exists():
        return ranges

    # 範囲形式のパターン
    # 旧形式: 第{start}:{end}条.md
    colon_pattern = re.compile(r'^第(\d+):(\d+)条\.md$')
    # 新形式: 第{start}条から第{end}条まで.md
    japanese_pattern = re.compile(r'^第(\d+)条から第(\d+)条まで\.md$')

    seen_ranges = set()  # 重複排除用

    # 旧形式を検索
    for file_path in honbun_dir.glob('第*:*条.md'):
        match = colon_pattern.match(file_path.name)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            key = (start, end)
            if key not in seen_ranges:
                seen_ranges.add(key)
                ranges.append(ArticleRange(start, end, file_path.name))

    # 新形式を検索（旧形式と重複する場合は新形式を優先）
    for file_path in honbun_dir.glob('第*条から第*条まで.md'):
        match = japanese_pattern.match(file_path.name)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            key = (start, end)
            if key in seen_ranges:
                # 重複: 新形式で上書き
                ranges = [r for r in ranges if (r.start, r.end) != key]
            seen_ranges.add(key)
            ranges.append(ArticleRange(start, end, file_path.name))

    # ソート: start順
    ranges.sort(key=lambda r: r.start)

    return ranges


def find_range_for_article(article_num: int, ranges: List[ArticleRange]) -> Optional[ArticleRange]:
    """
    指定された条文番号を含む範囲ノードを検索

    競合時の優先順位:
    1. 範囲が短い (end - start が最小)
    2. start が大きい (より具体的)
    """
    matching_ranges = [r for r in ranges if r.contains(article_num)]

    if not matching_ranges:
        return None

    if len(matching_ranges) == 1:
        return matching_ranges[0]

    # 競合時は優先順位で選択
    matching_ranges.sort(key=lambda r: (r.span(), -r.start))
    return matching_ranges[0]


def extract_article_number(link_target: str) -> Optional[int]:
    """
    リンクターゲットから条文番号を抽出
    例:
    - "第156条" → 156
    - "laws/民法/本文/第156条.md" → 156
    - "第156条#第1項" → 156
    - "第3条の2" → None (枝番は対象外)
    """
    # パスからファイル名を抽出
    if '/' in link_target:
        link_target = link_target.split('/')[-1]

    # .md を除去
    link_target = link_target.replace('.md', '')

    # アンカーを除去
    if '#' in link_target:
        link_target = link_target.split('#')[0]

    # 単条形式のマッチング: 第N条 (枝番なし)
    match = re.match(r'^第(\d+)条$', link_target)
    if match:
        return int(match.group(1))

    return None


def redirect_to_range_nodes(law_dir: Path, dry_run: bool = False) -> List[RangeRedirect]:
    """
    単条参照を範囲ノードにリダイレクト

    例: [[第156条|第百五十六条]] → [[laws/民法/本文/第155:157条.md|第百五十六条]]

    対応形式:
    - [[第N条]]
    - [[第N条|漢数字表記]]
    - [[第N条#項号]]
    - [[laws/法律名/本文/第N条.md]]
    - [[laws/法律名/本文/第N条.md|表記]]
    """
    law_name = law_dir.name
    redirects: List[RangeRedirect] = []

    # 範囲インデックス構築
    ranges = build_range_index(law_dir)
    if not ranges:
        return redirects

    print(f"   範囲ノード検出: {len(ranges)}件")
    for r in ranges:
        print(f"     - {r.filename} (第{r.start}条〜第{r.end}条)")

    # wikilink パターン
    wikilink_pattern = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')

    # 全ファイルをスキャン
    for md_file in law_dir.rglob('*.md'):
        if md_file.name == f'{law_name}.md':  # 親ファイルはスキップ
            continue

        # 範囲ノード自身はスキップ
        if ':' in md_file.stem:
            continue

        try:
            content = md_file.read_text(encoding='utf-8')
            new_content = content
            file_redirects = []

            for match in wikilink_pattern.finditer(content):
                link_target = match.group(1)
                display_text = match.group(2)

                # 条文番号を抽出
                article_num = extract_article_number(link_target)
                if article_num is None:
                    continue

                # 範囲ノードを検索
                range_node = find_range_for_article(article_num, ranges)
                if range_node is None:
                    continue

                # 新しいリンクターゲットを構築
                # パス形式を維持: laws/民法/本文/第155:157条.md
                if link_target.startswith('laws/'):
                    # 絶対パス形式
                    new_target = f"laws/{law_name}/本文/{range_node.filename}"
                elif link_target.endswith('.md'):
                    # 相対パス形式（.md付き）
                    new_target = range_node.filename
                else:
                    # シンプルな形式: 第N条 → 第N:M条
                    new_target = range_node.filename.replace('.md', '')

                # アンカーがある場合は警告のみ（範囲ノードにアンカーは無効）
                if '#' in link_target:
                    anchor = link_target.split('#')[1]
                    print(f"   警告: アンカー付きリンクのリダイレクト: {match.group(0)} (アンカー #{anchor} は無視されます)")

                # 新しいwikilink構築
                if display_text:
                    new_link = f"[[{new_target}|{display_text}]]"
                else:
                    # 元の表示を維持
                    original_display = link_target.split('/')[-1].replace('.md', '')
                    new_link = f"[[{new_target}|{original_display}]]"

                # 置換
                new_content = new_content.replace(match.group(0), new_link, 1)

                file_redirects.append(RangeRedirect(
                    source_file=md_file,
                    original_text=match.group(0),
                    original_target=link_target,
                    new_target=new_target,
                    article_num=article_num
                ))

            # ファイル更新
            if file_redirects and not dry_run:
                md_file.write_text(new_content, encoding='utf-8')

            redirects.extend(file_redirects)

        except Exception as e:
            print(f"   警告: {md_file.name} の処理に失敗: {e}")

    return redirects


def fix_supplementary_ids(law_dir: Path, dry_run: bool = False) -> Dict:
    """附則ファイルのID修正"""
    law_name = law_dir.name
    suppl_dir = law_dir / "附則"

    if not suppl_dir.exists():
        return {'updated': 0, 'skipped': 0, 'errors': []}

    stats = {'updated': 0, 'skipped': 0, 'errors': []}

    # 改正法ディレクトリ内のファイルを処理
    for md_file in suppl_dir.rglob('*.md'):
        try:
            content = md_file.read_text(encoding='utf-8')

            if not content.startswith('---'):
                stats['skipped'] += 1
                continue

            parts = content.split('---', 2)
            if len(parts) < 3:
                stats['skipped'] += 1
                continue

            yaml_str = parts[1]
            body = parts[2]

            try:
                metadata = yaml.safe_load(yaml_str)
            except yaml.YAMLError as e:
                stats['errors'].append(f"{md_file.name}: YAML parse error - {e}")
                continue

            if not metadata:
                stats['skipped'] += 1
                continue

            modified = False

            # 改正法IDを取得
            amendment_id = extract_amendment_id_from_path(md_file)

            if amendment_id:
                # canonical_id の修正
                article_num = metadata.get('article_num', '附則')
                # 「附則」が重複しないように処理
                if article_num.startswith('附則'):
                    article_part = article_num
                else:
                    article_part = f"附則{article_num}"

                new_canonical_id = f"{law_name}_{article_part}_{amendment_id}"

                if metadata.get('canonical_id') != new_canonical_id:
                    metadata['canonical_id'] = new_canonical_id
                    modified = True

                # amendment_law_id フィールドを追加
                if metadata.get('amendment_law_id') != amendment_id:
                    metadata['amendment_law_id'] = amendment_id
                    modified = True

                # source.id に元の e-Gov ID を保存
                if 'source' not in metadata:
                    metadata['source'] = {}

                if 'id' in metadata and metadata.get('source', {}).get('id') != metadata['id']:
                    metadata['source']['id'] = metadata['id']
                    metadata['source']['provider'] = 'e-gov'
                    modified = True

            if not modified:
                stats['skipped'] += 1
                continue

            # YAML を再シリアライズ
            new_yaml = yaml.dump(
                metadata,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False
            )

            new_content = f"---\n{new_yaml}---{body}"

            if not dry_run:
                md_file.write_text(new_content, encoding='utf-8')

            stats['updated'] += 1

        except Exception as e:
            stats['errors'].append(f"{md_file.name}: {e}")

    return stats


def find_unresolved_links(law_dir: Path) -> List[UnresolvedLink]:
    """未解決リンクの検出"""
    unresolved = []
    law_name = law_dir.name

    # 外部法名パターン（他法律への参照を検出）
    external_law_patterns = [
        r'民事執行法', r'民事訴訟法', r'民事保全法', r'商法', r'会社法',
        r'破産法', r'不動産登記法', r'戸籍法', r'家事事件手続法',
        r'地方自治法', r'自然公園法', r'競売法', r'借地借家法',
        r'建物の区分所有等に関する法律', r'農地法', r'信託法',
        r'電子記録債権法', r'住民基本台帳法',
        r'行政手続における特定の個人を識別するための番号の利用等に関する法律',
        r'商業登記法', r'金融商品取引法', r'保険業法', r'信用金庫法',
        r'労働金庫法', r'消費生活協同組合法', r'医療法', r'農業協同組合法',
        r'水産業協同組合法', r'森林組合法', r'中小企業等協同組合法',
        r'社債、株式等の振替に関する法律', r'一般社団法人及び一般財団法人に関する法律',
        r'会社更生法', r'金融機関等の更生手続の特例等に関する法律',
        r'資産の流動化に関する法律', r'投資信託及び投資法人に関する法律',
        r'土地収用法', r'行政不服審査法', r'行政事件訴訟法', r'民法',  # 土地関連法
        r'同法', r'附則', r'旧法', r'新法'  # 「同法」「附則」「旧法」「新法」も外部参照の可能性
    ]
    external_law_regex = '|'.join(external_law_patterns)

    # wikilink パターン
    wikilink_pattern = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')

    # 本文ディレクトリの全ファイルを検索
    for md_file in law_dir.rglob('*.md'):
        if md_file.name == f'{law_name}.md':  # 親ファイルはスキップ
            continue

        try:
            content = md_file.read_text(encoding='utf-8')

            # YAML frontmatter をスキップ
            if content.startswith('---'):
                yaml_end = content.find('---', 3)
                if yaml_end > 0:
                    body = content[yaml_end + 3:]
                else:
                    body = content
            else:
                body = content

            for match in wikilink_pattern.finditer(body):
                link_target = match.group(1)
                display_text = match.group(2) or link_target

                # アンカーリンクの処理 (第109条#第1項 → 第109条)
                base_target = link_target.split('#')[0] if '#' in link_target else link_target

                # 空のベースターゲット（同一ファイル内アンカー）はスキップ
                if not base_target:
                    continue

                # リンク先ファイルの存在確認
                if base_target.endswith('.md'):
                    # 絶対パス形式: laws/民法/本文/第63条.md
                    if base_target.startswith('laws/'):
                        target_path = law_dir.parent.parent / base_target
                    else:
                        target_path = md_file.parent / base_target
                else:
                    # 相対パス形式: 第63条
                    target_path = md_file.parent / f"{base_target}.md"

                if not target_path.exists():
                    # 外部法参照かどうかチェック
                    # リンクの前後の文脈を取得
                    start_pos = max(0, match.start() - 200)
                    end_pos = min(len(body), match.end() + 200)
                    context_before = body[start_pos:match.start()]
                    context_after = body[match.end():end_pos]

                    external_match = re.search(external_law_regex, context_before)

                    # 共通フィールド
                    common_fields = {
                        'source_file': md_file,
                        'target_path': link_target,
                        'original_text': match.group(0),
                        'display_text': display_text,
                        'context_before': context_before,
                        'context_after': context_after,
                        'match_span': {'start': match.start(), 'end': match.end()},
                    }

                    if external_match:
                        unresolved.append(UnresolvedLink(
                            **common_fields,
                            reason='external_law',
                            external_law_name=external_match.group(0)
                        ))
                    else:
                        unresolved.append(UnresolvedLink(
                            **common_fields,
                            reason='missing_article'
                        ))

        except Exception as e:
            print(f"Warning: Failed to process {md_file}: {e}")

    return unresolved


def determine_pending_kind(
    link: UnresolvedLink,
    law_dir: Path
) -> Tuple[str, str, Dict]:
    """
    保留リンクの種別を判定

    Returns:
        (kind, reason, hints)
    """
    hints: Dict[str, Any] = {}

    # 1. 外部法名がコンテキストにある場合
    if link.external_law_name and link.external_law_name not in ['同法', '附則', '旧法', '新法']:
        hints['external_law_name'] = link.external_law_name
        return ("external_law", "detected_external_law_name_in_context", hints)

    # 2. 改正法附則配下のファイルの場合、amendment_info を追加
    amendment_info = extract_amendment_info_from_path(link.source_file)
    if amendment_info:
        hints['amendment_key'] = amendment_info['key']
        hints['amendment_law_no'] = amendment_info['law_no']

    # 3. "同法/附則/旧法/新法" だけの場合
    if link.external_law_name in ['同法', '附則', '旧法', '新法']:
        return ("unknown", "same_law_token", hints)

    return ("unknown", "unclassified", hints)


def fix_external_law_links(
    law_dir: Path,
    unresolved: List[UnresolvedLink],
    dry_run: bool = False,
    law_name: Optional[str] = None,
    pending_log: Optional[Path] = None,
    pending_marker: bool = False
) -> Tuple[int, int]:
    """
    外部法参照のリンクを解除（プレーンテキストに戻す）

    Args:
        law_dir: 法律ディレクトリ
        unresolved: 未解決リンクリスト
        dry_run: Dry-runモード
        law_name: 法律名（pending log用）
        pending_log: pending log ファイルパス
        pending_marker: Markdownマーカーを挿入するか

    Returns:
        Tuple[int, int]: (修正件数, pending log 追記件数)
    """
    fixed_count = 0
    pending_count = 0

    # 法律名の取得
    if law_name is None:
        law_name = law_dir.name

    # pending log のデフォルト設定
    if pending_log is None:
        pending_log = DEFAULT_PENDING_LOG

    # ファイルごとにグループ化
    files_to_fix: Dict[Path, List[UnresolvedLink]] = {}
    for link in unresolved:
        if link.reason == 'external_law':
            if link.source_file not in files_to_fix:
                files_to_fix[link.source_file] = []
            files_to_fix[link.source_file].append(link)

    for file_path, links in files_to_fix.items():
        try:
            content = file_path.read_text(encoding='utf-8')
            new_content = content

            for link in links:
                # 表示テキストを取得
                if '|' in link.original_text:
                    # [[laws/民法/本文/第63条.md|第六十三条]] → 第六十三条
                    display = link.original_text.split('|')[1].rstrip(']]')
                else:
                    # [[第63条]] → 第63条
                    display = link.original_text.strip('[]')

                # pending link の種別を判定
                kind, reason, hints = determine_pending_kind(link, law_dir)

                # PendingLink レコードを作成
                pending_record = create_pending_link(
                    src_path=file_path,
                    src_law_name=law_name,
                    original_wikilink=link.original_text,
                    anchor_text=display,
                    replaced_with=display,
                    kind=kind,
                    reason=reason,
                    match_span=link.match_span,
                    context_before=link.context_before,
                    context_after=link.context_after,
                    hints=hints
                )

                # pending log に追記（dry-run でも追記する）
                if append_pending(pending_log, pending_record):
                    pending_count += 1

                # 置換文字列を構築
                if pending_marker:
                    # Obsidian形式のマーカーを追加
                    import json
                    marker_json = json.dumps({"id": pending_record.id}, ensure_ascii=False)
                    replacement = f"{display}%%DB4LAW:{marker_json}%%"
                else:
                    replacement = display

                # 置換実行
                new_content = new_content.replace(link.original_text, replacement)
                fixed_count += 1

            if not dry_run and new_content != content:
                file_path.write_text(new_content, encoding='utf-8')

        except Exception as e:
            print(f"Warning: Failed to fix {file_path}: {e}")

    return fixed_count, pending_count


def generate_stub_nodes(law_dir: Path, unresolved: List[UnresolvedLink], dry_run: bool = False, ranges: Optional[List[ArticleRange]] = None) -> Tuple[int, int]:
    """
    削除・欠番条文のスタブノードを生成

    Returns:
        Tuple[int, int]: (生成数, 範囲ノードによりスキップされた数)
    """
    law_name = law_dir.name
    honbun_dir = law_dir / "本文"
    stub_count = 0
    skipped_by_range = 0

    # 範囲インデックスがない場合は構築
    if ranges is None:
        ranges = build_range_index(law_dir)

    # 同一法内の missing_article のみ処理
    missing_articles = [link for link in unresolved if link.reason == 'missing_article']

    # 同じターゲットは1つだけ生成
    seen_targets = set()

    for link in missing_articles:
        target_path = link.target_path

        # ファイル名を抽出
        if target_path.endswith('.md'):
            filename = Path(target_path).name
        else:
            filename = f"{target_path}.md"

        # 本文ディレクトリ内のファイルのみ
        if '本文' not in str(link.source_file):
            continue

        if filename in seen_targets:
            continue
        seen_targets.add(filename)

        # スタブファイルのパス
        stub_path = honbun_dir / filename

        if stub_path.exists():
            continue

        # 条文番号を抽出
        article_match = re.match(r'第(\d+)条(?:の(\d+))?', filename.replace('.md', ''))
        if not article_match:
            continue

        # 範囲ノードに含まれるかチェック
        article_num_int = int(article_match.group(1))
        range_node = find_range_for_article(article_num_int, ranges)
        if range_node is not None:
            print(f"  スキップ: {filename} → 範囲ノード {range_node.filename} に含まれます")
            skipped_by_range += 1
            continue

        article_num = filename.replace('.md', '')

        # 参照元を収集
        referenced_by = []
        for l in missing_articles:
            if l.target_path == target_path or Path(l.target_path).name == filename:
                ref_name = l.source_file.stem
                if ref_name not in referenced_by:
                    referenced_by.append(ref_name)

        # スタブ内容を生成
        stub_metadata = {
            'article_num': article_num,
            'heading': '（削除）',
            'id': f"JPLAW:{law_dir.name}#本文#{article_num}",
            'law_name': law_name,
            'part': '本文',
            'status': 'deleted',
            'referenced_by': referenced_by,
            'source': {
                'provider': 'e-gov',
                'note': 'この条文は削除または欠番です'
            }
        }

        stub_yaml = yaml.dump(
            stub_metadata,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False
        )

        stub_content = f"""---
{stub_yaml}---

# {article_num} （削除）

この条文は削除されています。
"""

        if not dry_run:
            stub_path.write_text(stub_content, encoding='utf-8')

        stub_count += 1
        print(f"  スタブ生成: {filename} (参照元: {', '.join(referenced_by[:3])}{'...' if len(referenced_by) > 3 else ''})")

    return stub_count, skipped_by_range


def main():
    parser = argparse.ArgumentParser(description="DB4LAW ID衝突・未解決リンク修正")
    parser.add_argument('--law', required=True, help='対象の法律名（例: 民法）')
    parser.add_argument('--dry-run', action='store_true', help='Dry-runモード（変更なし）')
    parser.add_argument('--fix-ids', action='store_true', help='附則IDの修正')
    parser.add_argument('--fix-links', action='store_true', help='外部法リンクの解除')
    parser.add_argument('--redirect-ranges', action='store_true', help='削除条文リンクを範囲ノードにリダイレクト')
    parser.add_argument('--generate-stubs', action='store_true', help='スタブノード生成')
    parser.add_argument('--all', action='store_true', help='全ての修正を実行')
    parser.add_argument('--report', action='store_true', help='レポート出力のみ')
    # pending links オプション
    parser.add_argument('--pending-log', type=Path, default=DEFAULT_PENDING_LOG,
                        help=f'Pending log ファイルパス（デフォルト: {DEFAULT_PENDING_LOG}）')
    parser.add_argument('--pending-marker', action='store_true',
                        help='Markdownに再リンク用マーカーを埋め込む（デフォルトOFF）')
    args = parser.parse_args()

    law_dir = get_law_dir(args.law)

    if not law_dir.exists():
        print(f"エラー: ディレクトリが見つかりません: {law_dir}")
        return

    print(f"\n{'='*60}")
    print(f"DB4LAW ID修正ツール - {args.law}")
    print(f"モード: {'DRY-RUN' if args.dry_run else '実行'}")
    print(f"{'='*60}\n")

    if args.all:
        args.fix_ids = True
        args.fix_links = True
        args.redirect_ranges = True
        args.generate_stubs = True

    # 範囲インデックスを事前構築（複数箇所で使用）
    ranges = build_range_index(law_dir)

    # 1. 附則ID修正
    if args.fix_ids or args.report:
        print("[1] 附則ID修正...")
        stats = fix_supplementary_ids(law_dir, dry_run=args.dry_run or args.report)
        print(f"   更新: {stats['updated']}, スキップ: {stats['skipped']}")
        if stats['errors']:
            print(f"   エラー: {len(stats['errors'])}件")
            for err in stats['errors'][:5]:
                print(f"     - {err}")

    # 2. 未解決リンク検出
    print("\n[2] 未解決リンク検出...")
    unresolved = find_unresolved_links(law_dir)

    external_links = [l for l in unresolved if l.reason == 'external_law']
    missing_links = [l for l in unresolved if l.reason == 'missing_article']

    print(f"   外部法参照: {len(external_links)}件")
    print(f"   欠落条文参照: {len(missing_links)}件")

    if external_links:
        print("\n   [外部法参照の例]")
        for link in external_links[:5]:
            print(f"     {link.source_file.name}: {link.original_text}")
            print(f"       → {link.external_law_name}への参照")

    if missing_links:
        print("\n   [欠落条文参照の例]")
        for link in missing_links[:5]:
            print(f"     {link.source_file.name}: {link.original_text}")

    # 3. 外部法リンク解除
    if args.fix_links:
        print("\n[3] 外部法リンク解除...")
        fixed, pending = fix_external_law_links(
            law_dir,
            unresolved,
            dry_run=args.dry_run,
            law_name=args.law,
            pending_log=args.pending_log,
            pending_marker=args.pending_marker
        )
        print(f"   修正: {fixed}件")
        print(f"   Pending log: {pending}件 → {args.pending_log}")
        if args.pending_marker:
            print(f"   マーカー埋め込み: ON")

    # 4. 範囲ノードリダイレクト
    if args.redirect_ranges:
        print("\n[4] 範囲ノードリダイレクト...")
        redirects = redirect_to_range_nodes(law_dir, dry_run=args.dry_run)
        print(f"   リダイレクト: {len(redirects)}件")
        if redirects:
            print("\n   [リダイレクト例]")
            for r in redirects[:10]:
                print(f"     {r.source_file.name}: {r.original_text} → [[{r.new_target}|...]]")

    # 5. スタブ生成
    if args.generate_stubs:
        print("\n[5] スタブノード生成...")
        stubs, skipped = generate_stub_nodes(law_dir, unresolved, dry_run=args.dry_run, ranges=ranges)
        print(f"   生成: {stubs}件")
        if skipped > 0:
            print(f"   範囲ノードによりスキップ: {skipped}件")

    print(f"\n{'='*60}")
    print("完了")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
