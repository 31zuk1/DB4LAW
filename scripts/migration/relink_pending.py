#!/usr/bin/env python3
"""
DB4LAW: Pending Links 再リンクスクリプト

pending_links.jsonl に記録された保留リンクを、
ターゲットノードが作成された後に再リンクする。
"""

import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import asdict

from pending_links import (
    PendingLink,
    load_pending,
    load_resolved,
    append_pending,
    extract_article_number_from_link,
    DEFAULT_PENDING_LOG,
    DEFAULT_RESOLVED_LOG,
)


def find_vault_root(start_path: Path = None) -> Optional[Path]:
    """
    Vaultルートディレクトリを探索

    Args:
        start_path: 探索開始パス

    Returns:
        Vaultルートパス、または None
    """
    if start_path is None:
        start_path = Path.cwd()

    # 上位ディレクトリを探索
    current = start_path.resolve()
    while current != current.parent:
        vault_path = current / 'Vault'
        if vault_path.is_dir() and (vault_path / 'laws').is_dir():
            return vault_path
        current = current.parent

    return None


def generate_target_candidates(
    record: PendingLink,
    vault_root: Path,
    src_law_name: str
) -> List[Path]:
    """
    保留リンクのターゲット候補パスを生成

    Args:
        record: PendingLinkレコード
        vault_root: Vaultルートパス
        src_law_name: ソース法律名

    Returns:
        候補パスのリスト
    """
    candidates = []
    laws_dir = vault_root / 'laws'

    # リンクから条文番号を抽出
    article_num = extract_article_number_from_link(record.original_wikilink)
    article_filename = f"第{article_num}条.md" if article_num else None

    if record.kind == "external_law":
        # 外部法名からディレクトリを検索
        external_law_name = record.hints.get('external_law_name')
        if external_law_name and article_filename:
            # 完全一致
            target_law_dir = laws_dir / external_law_name
            if target_law_dir.is_dir():
                candidates.append(target_law_dir / '本文' / article_filename)

            # glob検索（コスト制限付き）
            for law_dir in laws_dir.iterdir():
                if law_dir.is_dir() and external_law_name in law_dir.name:
                    candidates.append(law_dir / '本文' / article_filename)
                    if len(candidates) >= 10:  # コスト制限
                        break

    elif record.kind == "amendment_self" or record.hints.get('amendment_key'):
        # 改正法ノードへの再リンク
        amendment_key = record.hints.get('amendment_key')
        if amendment_key and article_filename:
            # 複数のパス規約を試す
            patterns = [
                f"附則/改正法/{amendment_key}/本文/{article_filename}",
                f"附則/改正法/{amendment_key}/附則{article_filename}",
                f"附則/改正法/{amendment_key}/{article_filename}",
            ]
            for pattern in patterns:
                candidates.append(laws_dir / src_law_name / pattern)

    # unknown の場合も amendment_key があれば試す
    if record.kind == "unknown" and record.hints.get('amendment_key'):
        amendment_key = record.hints.get('amendment_key')
        if amendment_key and article_filename:
            patterns = [
                f"附則/改正法/{amendment_key}/本文/{article_filename}",
                f"附則/改正法/{amendment_key}/附則{article_filename}",
                f"附則/改正法/{amendment_key}/{article_filename}",
            ]
            for pattern in patterns:
                candidates.append(laws_dir / src_law_name / pattern)

    return candidates


def find_target(record: PendingLink, vault_root: Path) -> Optional[Path]:
    """
    保留リンクのターゲットを検索

    Args:
        record: PendingLinkレコード
        vault_root: Vaultルートパス

    Returns:
        存在するターゲットパス、または None
    """
    candidates = generate_target_candidates(record, vault_root, record.src_law_name)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def find_marker_position(content: str, pending_id: str) -> Optional[Tuple[int, int]]:
    """
    Markdown内のマーカー位置を検索

    Args:
        content: ファイル内容
        pending_id: Pending ID

    Returns:
        (マーカー開始位置, マーカー終了位置) または None
    """
    # %%DB4LAW:{"id":"xxx"}%% 形式を検索
    # 正規表現のブレースをエスケープ
    pattern = r'%%DB4LAW:\{"id":"' + re.escape(pending_id) + r'"\}%%'
    match = re.search(pattern, content)
    if match:
        return match.start(), match.end()
    return None


def find_anchor_in_context(
    content: str,
    anchor_text: str,
    context_before: str,
    context_after: str
) -> Optional[Tuple[int, int]]:
    """
    コンテキストを使ってアンカーテキストの位置を検索

    Args:
        content: ファイル内容
        anchor_text: 検索するテキスト
        context_before: 前文脈
        context_after: 後文脈

    Returns:
        (開始位置, 終了位置) または None（複数一致の場合も None）
    """
    # アンカーテキストの全出現位置を検索
    positions = []
    start = 0
    while True:
        pos = content.find(anchor_text, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1

    if len(positions) == 0:
        return None

    if len(positions) == 1:
        pos = positions[0]
        return pos, pos + len(anchor_text)

    # 複数一致の場合、コンテキストで絞り込み
    for pos in positions:
        # 前後の文脈をチェック
        content_before = content[max(0, pos - 100):pos]
        content_after = content[pos + len(anchor_text):pos + len(anchor_text) + 100]

        # 前文脈の末尾部分が一致するか
        if context_before and context_before[-50:] in content_before:
            return pos, pos + len(anchor_text)

        # 後文脈の先頭部分が一致するか
        if context_after and context_after[:50] in content_after:
            return pos, pos + len(anchor_text)

    # 絞り込めなかった場合は None
    return None


def build_wikilink(target_path: Path, anchor_text: str, vault_root: Path) -> str:
    """
    Wikilink を構築

    Args:
        target_path: ターゲットファイルパス
        anchor_text: 表示テキスト
        vault_root: Vaultルートパス

    Returns:
        Wikilink文字列
    """
    # Vault相対パスを構築
    try:
        relative_path = target_path.relative_to(vault_root.parent)
    except ValueError:
        relative_path = target_path

    return f"[[{relative_path}|{anchor_text}]]"


def relink_record(
    record: PendingLink,
    vault_root: Path,
    strategy: str,
    dry_run: bool = True
) -> Tuple[bool, str]:
    """
    単一レコードの再リンク処理

    Args:
        record: PendingLinkレコード
        vault_root: Vaultルートパス
        strategy: "marker" | "context" | "both"
        dry_run: Dry-runモード

    Returns:
        (成功フラグ, メッセージ)
    """
    # ターゲットを検索
    target = find_target(record, vault_root)
    if not target:
        return False, "ターゲットが見つかりません"

    # ソースファイルを読み込み
    src_path = vault_root.parent / record.src_path
    if not src_path.exists():
        return False, f"ソースファイルが存在しません: {src_path}"

    content = src_path.read_text(encoding='utf-8')

    # 位置を特定
    position = None
    method_used = None

    if strategy in ['marker', 'both']:
        marker_pos = find_marker_position(content, record.id)
        if marker_pos:
            position = marker_pos
            method_used = 'marker'

    if position is None and strategy in ['context', 'both']:
        context_pos = find_anchor_in_context(
            content,
            record.anchor_text,
            record.context_before,
            record.context_after
        )
        if context_pos:
            position = context_pos
            method_used = 'context'

    if position is None:
        return False, "アンカー位置を特定できません"

    # Wikilinkを構築
    wikilink = build_wikilink(target, record.anchor_text, vault_root)

    # 置換
    start, end = position
    if method_used == 'marker':
        # マーカー手前のanchor_textを含めて置換
        anchor_start = start - len(record.anchor_text)
        if anchor_start >= 0 and content[anchor_start:start] == record.anchor_text:
            new_content = content[:anchor_start] + wikilink + content[end:]
        else:
            new_content = content[:start] + wikilink + content[end:]
    else:
        # context戦略: anchor_textを置換
        new_content = content[:start] + wikilink + content[end:]

    if not dry_run:
        src_path.write_text(new_content, encoding='utf-8')

    return True, f"再リンク成功 ({method_used}) → {target.name}"


def main():
    parser = argparse.ArgumentParser(description="DB4LAW Pending Links 再リンクツール")
    parser.add_argument('--pending-log', type=Path, default=DEFAULT_PENDING_LOG,
                        help=f'Pending log ファイルパス（デフォルト: {DEFAULT_PENDING_LOG}）')
    parser.add_argument('--resolved-log', type=Path, default=DEFAULT_RESOLVED_LOG,
                        help=f'Resolved log ファイルパス（デフォルト: {DEFAULT_RESOLVED_LOG}）')
    parser.add_argument('--vault-root', type=Path, default=None,
                        help='Vaultルートパス（自動検出）')
    parser.add_argument('--strategy', choices=['marker', 'context', 'both'], default='both',
                        help='再リンク戦略（デフォルト: both）')
    parser.add_argument('--dry-run', action='store_true',
                        help='Dry-runモード（変更なし）')
    parser.add_argument('--apply', action='store_true',
                        help='実際に変更を適用')
    parser.add_argument('--filter-law', type=str, default=None,
                        help='特定の法律のみ処理')
    parser.add_argument('--filter-kind', type=str, default=None,
                        help='特定のkindのみ処理')
    args = parser.parse_args()

    # Vaultルートの検出
    vault_root = args.vault_root
    if vault_root is None:
        vault_root = find_vault_root()
    if vault_root is None:
        print("エラー: Vaultルートが見つかりません。--vault-root を指定してください。")
        return

    # 実行モードの確認
    if not args.dry_run and not args.apply:
        print("エラー: --dry-run または --apply を指定してください。")
        return

    dry_run = not args.apply

    print(f"\n{'='*60}")
    print(f"DB4LAW Pending Links 再リンクツール")
    print(f"モード: {'DRY-RUN' if dry_run else '実行'}")
    print(f"戦略: {args.strategy}")
    print(f"Vault: {vault_root}")
    print(f"{'='*60}\n")

    # Pending log を読み込み
    pending_records = load_pending(args.pending_log)
    if not pending_records:
        print(f"Pending log が空です: {args.pending_log}")
        return

    print(f"Pending records: {len(pending_records)}件\n")

    # Resolved log を読み込み（既に解決済みのものを除外）
    resolved = load_resolved(args.resolved_log)
    pending_records = [r for r in pending_records if r.id not in resolved]
    print(f"未解決: {len(pending_records)}件\n")

    # フィルタリング
    if args.filter_law:
        pending_records = [r for r in pending_records if r.src_law_name == args.filter_law]
        print(f"フィルタ後 (law={args.filter_law}): {len(pending_records)}件\n")

    if args.filter_kind:
        pending_records = [r for r in pending_records if r.kind == args.filter_kind]
        print(f"フィルタ後 (kind={args.filter_kind}): {len(pending_records)}件\n")

    # 処理
    success_count = 0
    fail_count = 0
    skip_count = 0

    for record in pending_records:
        success, message = relink_record(record, vault_root, args.strategy, dry_run)

        if success:
            success_count += 1
            print(f"  ✓ {record.src_path}: {record.anchor_text}")
            print(f"    {message}")

            # Resolved log に記録
            if not dry_run:
                from datetime import datetime, timezone
                record.status = "resolved"
                record.resolved_ts = datetime.now(timezone.utc).isoformat()
                append_pending(args.resolved_log, record)
        else:
            fail_count += 1
            print(f"  ✗ {record.src_path}: {record.anchor_text}")
            print(f"    {message}")

    print(f"\n{'='*60}")
    print(f"結果:")
    print(f"  成功: {success_count}件")
    print(f"  失敗: {fail_count}件")
    print(f"  スキップ: {skip_count}件")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
