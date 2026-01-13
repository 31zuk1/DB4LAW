#!/usr/bin/env python3
"""
DB4LAW: Pending Links 共通スキーマ・ユーティリティ

リンク解除時に保存する「保留リンク」の管理機能を提供する。
後から改正法ノード/外部法ノードが作成された際に再リンクするための情報を保持。
"""

import json
import hashlib
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

# 共通モジュールのインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))
from legalkg.utils.article_formatter import (
    normalize_amendment_id,
    amendment_key_to_title,
    extract_article_number,
)

# 設定のインポート
from config import DEFAULT_PENDING_LOG, DEFAULT_RESOLVED_LOG


@dataclass
class PendingLink:
    """保留リンク情報"""
    # 必須フィールド
    id: str                         # 重複排除用ハッシュ
    ts: str                         # ISO8601 with timezone
    src_path: str                   # 編集したmdのリポジトリ相対パス
    src_law_name: str               # --law で処理中の法名
    kind: str                       # "external_law" | "amendment_self" | "unknown"
    anchor_text: str                # 表示文字列（例：第六十六条）
    original_wikilink: str          # 置換前の wiki link 全文字列
    replaced_with: str              # 置換後文字列
    reason: str                     # 判定理由

    # オプションフィールド
    match_span: Optional[Dict[str, int]] = None  # {"start": int, "end": int}
    context_before: str = ""        # リンク前の文脈（最大200文字）
    context_after: str = ""         # リンク後の文脈（最大200文字）
    hints: Dict[str, Any] = field(default_factory=dict)  # 推定情報

    # 状態管理（resolved時に使用）
    status: str = "pending"         # "pending" | "resolved" | "skipped"
    resolved_ts: Optional[str] = None
    resolved_target: Optional[str] = None


def generate_pending_id(
    src_law_name: str,
    src_path: str,
    original_wikilink: str,
    anchor_text: str
) -> str:
    """
    重複排除用ID生成

    Args:
        src_law_name: 処理中の法律名
        src_path: ソースファイルパス
        original_wikilink: 元のwikilink全文
        anchor_text: 表示テキスト

    Returns:
        SHA1ハッシュ（先頭16文字）
    """
    data = f"{src_law_name}|{src_path}|{original_wikilink}|{anchor_text}"
    return hashlib.sha1(data.encode('utf-8')).hexdigest()[:16]


def create_pending_link(
    src_path: Path,
    src_law_name: str,
    original_wikilink: str,
    anchor_text: str,
    replaced_with: str,
    kind: str,
    reason: str,
    match_span: Optional[Dict[str, int]] = None,
    context_before: str = "",
    context_after: str = "",
    hints: Optional[Dict[str, Any]] = None
) -> PendingLink:
    """
    PendingLinkインスタンスを作成

    Args:
        src_path: ソースファイルパス（Pathオブジェクト）
        src_law_name: 処理中の法律名
        original_wikilink: 元のwikilink全文
        anchor_text: 表示テキスト
        replaced_with: 置換後の文字列
        kind: リンク種別
        reason: 判定理由
        match_span: マッチ位置（オプション）
        context_before: 前文脈（オプション）
        context_after: 後文脈（オプション）
        hints: 追加情報（オプション）

    Returns:
        PendingLinkインスタンス
    """
    # 相対パス化（Vault/laws/... 形式）
    src_path_str = str(src_path)
    if 'Vault/' in src_path_str:
        src_path_str = 'Vault/' + src_path_str.split('Vault/')[-1]

    pending_id = generate_pending_id(
        src_law_name,
        src_path_str,
        original_wikilink,
        anchor_text
    )

    return PendingLink(
        id=pending_id,
        ts=datetime.now(timezone.utc).isoformat(),
        src_path=src_path_str,
        src_law_name=src_law_name,
        kind=kind,
        anchor_text=anchor_text,
        original_wikilink=original_wikilink,
        replaced_with=replaced_with,
        reason=reason,
        match_span=match_span,
        context_before=context_before[:200] if context_before else "",
        context_after=context_after[:200] if context_after else "",
        hints=hints or {}
    )


def append_pending(path: Path, record: PendingLink) -> bool:
    """
    JSONL追記

    Args:
        path: JOSNLファイルパス
        record: 追記するPendingLink

    Returns:
        成功時True、失敗時False（処理は継続）
    """
    try:
        # ディレクトリが無ければ作成
        path.parent.mkdir(parents=True, exist_ok=True)

        # 追記モードで開く
        with open(path, 'a', encoding='utf-8') as f:
            json_line = json.dumps(asdict(record), ensure_ascii=False)
            f.write(json_line + '\n')
            f.flush()

        return True

    except Exception as e:
        print(f"  警告: pending log 追記失敗: {path} - {e}")
        return False


def load_pending(path: Path, dedupe: bool = True) -> List[PendingLink]:
    """
    JSONL読み込み

    Args:
        path: JOSNLファイルパス
        dedupe: 重複排除するかどうか

    Returns:
        PendingLinkのリスト
    """
    if not path.exists():
        return []

    records = []
    seen_ids = set()

    with open(path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                record = PendingLink(**data)

                if dedupe:
                    if record.id in seen_ids:
                        continue
                    seen_ids.add(record.id)

                records.append(record)

            except (json.JSONDecodeError, TypeError) as e:
                print(f"  警告: {path}:{line_num} パースエラー: {e}")
                continue

    return records


def load_resolved(path: Path) -> Dict[str, PendingLink]:
    """
    resolved_links.jsonl を読み込み、IDをキーとした辞書を返す

    Args:
        path: resolved_links.jsonl のパス

    Returns:
        {id: PendingLink} の辞書
    """
    records = load_pending(path, dedupe=True)
    return {r.id: r for r in records}


def extract_amendment_info_from_path(file_path: Path) -> Optional[Dict[str, str]]:
    """
    ファイルパスから改正法情報を抽出

    Args:
        file_path: ファイルパス

    Returns:
        {'key': 'R3_L37', 'law_no': '令和3年法律第37号'} 形式、または None
    """
    parts = file_path.parts

    # 改正法ディレクトリを探す
    for i, part in enumerate(parts):
        if part == '改正法' and i + 1 < len(parts):
            amendment_key = parts[i + 1]

            # キーから法律番号を復元（共通モジュール使用）
            law_no = amendment_key_to_title(amendment_key)

            return {
                'key': amendment_key,
                'law_no': law_no
            }

        # 旧形式（日本語ディレクトリ名）
        if '年' in part and '法律第' in part:
            # 共通モジュール使用
            amendment_key = normalize_amendment_id(part)
            return {
                'key': amendment_key,
                'law_no': part
            }

    return None


def extract_article_number_from_link(link_target: str) -> Optional[int]:
    """
    リンクターゲットから条文番号を抽出

    Args:
        link_target: リンクターゲット文字列

    Returns:
        条文番号（整数）、または None
    """
    # 共通モジュールを使用
    return extract_article_number(link_target)
