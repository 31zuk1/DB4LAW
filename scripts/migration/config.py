"""
DB4LAW: 移行スクリプト共通設定

パス解決と設定値を一元管理するモジュール。
環境に依存しないポータブルな設定を提供。
"""

import os
from pathlib import Path
from typing import Optional


def get_project_root() -> Path:
    """
    プロジェクトルートディレクトリを取得

    以下の優先順位で決定:
    1. 環境変数 DB4LAW_ROOT
    2. このファイルからの相対パス（../../）
    3. カレントディレクトリから上位探索

    Returns:
        プロジェクトルートのPath
    """
    # 環境変数から取得
    env_root = os.environ.get('DB4LAW_ROOT')
    if env_root:
        return Path(env_root).resolve()

    # このファイルからの相対パス
    # scripts/migration/config.py → ../../
    script_based = Path(__file__).parent.parent.parent
    if (script_based / 'Vault').is_dir():
        return script_based.resolve()

    # カレントディレクトリから上位探索
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / 'Vault').is_dir() and (current / 'src' / 'legalkg').is_dir():
            return current
        current = current.parent

    # フォールバック: このファイルの2階層上
    return Path(__file__).parent.parent.parent.resolve()


def get_vault_path() -> Path:
    """Vaultディレクトリのパスを取得"""
    return get_project_root() / 'Vault'


def get_laws_path() -> Path:
    """laws ディレクトリのパスを取得"""
    return get_vault_path() / 'laws'


def get_law_dir(law_name: str) -> Path:
    """
    指定した法律のディレクトリパスを取得

    Args:
        law_name: 法律名（例: '刑法', '民法'）

    Returns:
        法律ディレクトリのPath
    """
    return get_laws_path() / law_name


def get_artifacts_path() -> Path:
    """
    _artifacts ディレクトリのパスを取得
    （生成物の保存先）
    """
    artifacts = Path(__file__).parent / '_artifacts'
    artifacts.mkdir(parents=True, exist_ok=True)
    return artifacts


def find_law_by_id(law_id: str) -> Optional[Path]:
    """
    法令IDからディレクトリを検索

    Args:
        law_id: e-Gov法令ID（例: '140AC0000000045'）

    Returns:
        法令ディレクトリのPath、見つからない場合は None
    """
    laws_dir = get_laws_path()
    if not laws_dir.exists():
        return None

    for law_dir in laws_dir.iterdir():
        if not law_dir.is_dir():
            continue
        # 親ファイルのYAMLからlaw_idをチェック
        parent_file = law_dir / f"{law_dir.name}.md"
        if parent_file.exists():
            content = parent_file.read_text(encoding='utf-8')
            if f"law_id: {law_id}" in content or f"egov_law_id: {law_id}" in content:
                return law_dir
    return None


def list_processed_laws() -> list:
    """
    処理済み法律（日本語ディレクトリ構造を持つもの）のリストを取得

    Returns:
        法律名のリスト
    """
    laws_dir = get_laws_path()
    if not laws_dir.exists():
        return []

    processed = []
    for law_dir in sorted(laws_dir.iterdir()):
        if not law_dir.is_dir():
            continue
        # 本文/ または 附則/ ディレクトリが存在するか
        if (law_dir / '本文').is_dir() or (law_dir / '附則').is_dir():
            processed.append(law_dir.name)
    return processed


# ==============================================================================
# 定数
# ==============================================================================

# プロジェクトルート（モジュールロード時に解決）
PROJECT_ROOT = get_project_root()

# 主要ディレクトリ
VAULT_PATH = PROJECT_ROOT / 'Vault'
LAWS_PATH = VAULT_PATH / 'laws'
CACHE_PATH = PROJECT_ROOT / 'cache'
SCRIPTS_PATH = PROJECT_ROOT / 'scripts'
ARTIFACTS_PATH = SCRIPTS_PATH / 'migration' / '_artifacts'

# デフォルトログファイル
DEFAULT_PENDING_LOG = ARTIFACTS_PATH / 'pending_links.jsonl'
DEFAULT_RESOLVED_LOG = ARTIFACTS_PATH / 'resolved_links.jsonl'
DEFAULT_MAPPING_CSV = ARTIFACTS_PATH / 'migration_mapping.csv'


# ==============================================================================
# ユーティリティ
# ==============================================================================

def ensure_artifacts_dir():
    """_artifacts ディレクトリが存在することを確認"""
    ARTIFACTS_PATH.mkdir(parents=True, exist_ok=True)


def get_relative_path(absolute_path: Path, base: Optional[Path] = None) -> str:
    """
    絶対パスを相対パスに変換

    Args:
        absolute_path: 変換する絶対パス
        base: 基準ディレクトリ（デフォルト: PROJECT_ROOT）

    Returns:
        相対パス文字列
    """
    if base is None:
        base = PROJECT_ROOT
    try:
        return str(absolute_path.relative_to(base))
    except ValueError:
        return str(absolute_path)
