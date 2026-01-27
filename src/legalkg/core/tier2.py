import re
import json
from pathlib import Path
from functools import lru_cache
from typing import List, Dict, Tuple, Optional
from ..utils.numerals import kanji_to_int
from ..utils.patterns import strip_wikilinks
from ..utils.markdown import read_markdown_file

# ==============================================================================
# 定数定義
# ==============================================================================
# コンテキスト窓サイズ: 外部法令名の出現を検出する際の後方探索範囲
# 300文字は日本語で約10〜15文程度をカバー（句点で区切る前のフォールバック用）
CONTEXT_WINDOW_EXTERNAL_LAW = 300

# コンテキスト窓サイズ: 直近の法令名検出用（法令名＋第N条パターン）
# 100文字は「○○法第1条」のような短い参照パターンをカバー
CONTEXT_WINDOW_IMMEDIATE = 100

# 法令名直後の「第」を文末で検出するための正規表現サフィックス
#
# 「法令名 + 許容セパレータ + 文末」にマッチする。
# 許容セパレータ: の, 、, \n のみ（最大1文字）
#
# 注意: 括弧付き番号「（平成○年法律第○号）」は context_cleaned で除去済み
# なので、ここでは考慮不要。
#
# NG パターン（マッチしない）:
#   - 「民法の規定にかかわらず、」→ 距離が遠すぎる
#   - 「民法に定める」→ 「に」は許容セパレータではない
#
# OK パターン（マッチする）:
#   - 「民法」 → 直接接続
#   - 「民法の」 → の + 第N条
#   - 「民法、」 → 読点 + 第N条
#   - 「民法\n」 → 改行 + 第N条
#
# 使用例: re.escape(law_name) + LAW_NAME_SUFFIX_PATTERN
LAW_NAME_SUFFIX_PATTERN = r'(?:[の、\n])?$'

# ==============================================================================
# クロスリンク対象法令（Vault内に本文が存在する法令）
# ==============================================================================
# これらの法令名が条文参照の直前にある場合、その法令へのクロスリンクを生成する。
# 新たな法令を処理した場合はこの辞書に追加する。
# キー: 法令名（バリエーション含む）, 値: Vault内のフォルダ名
CROSS_LINKABLE_LAWS: Dict[str, str] = {
    # 刑法
    '刑法': '刑法',
    '新刑法': '刑法',
    '旧刑法': '刑法',
    '改正前の刑法': '刑法',
    '改正後の刑法': '刑法',
    # 民法
    '民法': '民法',
    '新民法': '民法',
    '旧民法': '民法',
    '改正前の民法': '民法',
    '改正後の民法': '民法',
    # 日本国憲法
    '日本国憲法': '日本国憲法',
    '憲法': '日本国憲法',
    # 刑事訴訟法
    '刑事訴訟法': '刑事訴訟法',
    '新刑事訴訟法': '刑事訴訟法',
    '旧刑事訴訟法': '刑事訴訟法',
    '改正前の刑事訴訟法': '刑事訴訟法',
    '改正後の刑事訴訟法': '刑事訴訟法',
    # 民事訴訟法
    '民事訴訟法': '民事訴訟法',
    '新民事訴訟法': '民事訴訟法',
    '旧民事訴訟法': '民事訴訟法',
    '改正前の民事訴訟法': '民事訴訟法',
    '改正後の民事訴訟法': '民事訴訟法',
    # 所有者不明土地の利用の円滑化等に関する特別措置法
    '所有者不明土地の利用の円滑化等に関する特別措置法': '所有者不明土地の利用の円滑化等に関する特別措置法',
    '所有者不明土地法': '所有者不明土地の利用の円滑化等に関する特別措置法',
}


# ==============================================================================
# 外部法令名パターン（リンク化を除外する）
# ==============================================================================
# 条文参照（第N条）の直前にこれらの法令名がある場合、
# 他法令への参照と判断してリンク化をスキップする。
# 新たな外部法令が必要な場合はこのリストに追加する。
# 注: CROSS_LINKABLE_LAWS に含まれる法令はクロスリンク処理で先に処理されるため、
#     ここに重複して記載する必要はない。
EXTERNAL_LAW_PATTERNS: Tuple[str, ...] = (
    # 刑事系（刑事訴訟法はクロスリンク対象のため除外）
    '少年法', '刑事収容施設及び被収容者等の処遇に関する法律',
    '更生保護法', '犯罪被害者等の権利利益の保護を図るための刑事手続に付随する措置に関する法律',
    '少年鑑別所法', '裁判員の参加する刑事裁判に関する法律',
    '検察審査会法', '組織的犯罪処罰法',
    '組織的な犯罪の処罰及び犯罪収益の規制等に関する法律',
    '犯罪捜査のための通信傍受に関する法律',
    '国際捜査共助等に関する法律', '逃亡犯罪人引渡法',
    '犯罪による収益の移転防止に関する法律',
    # 民事系（民事訴訟法はクロスリンク対象のため除外）
    '民事執行法', '民事保全法', '商法', '会社法',
    '破産法', '不動産登記法', '戸籍法', '家事事件手続法',
    '借地借家法', '建物の区分所有等に関する法律',
    '商業登記法', '外国法人の登記及び夫婦財産契約の登記に関する法律',
    '会社更生法', '仲裁法', '非訟事件手続法', '公証人法',
    '不正競争防止法', '著作権法', '特許法', '商標法',
    '民事調停法', '労働審判法',
    # 土地・不動産系
    '土地収用法', '都市計画法', '土地基本法', '鉄道抵当法',
    # 行政系
    '地方自治法', '自然公園法', '農地法', '住民基本台帳法',
    '行政手続における特定の個人を識別するための番号の利用等に関する法律',
    '行政代執行法', '特定非営利活動促進法', '出入国管理及び難民認定法',
    '行政事件訴訟法', '国家賠償法', '行政手続法',
    # 金融・経済系
    '信託法', '電子記録債権法', '金融商品取引法', '保険業法',
    '信用金庫法', '労働金庫法', '資産の流動化に関する法律',
    '投資信託及び投資法人に関する法律', '損害保険料率算出団体に関する法律',
    '社債、株式等の振替に関する法律',
    '金融機関等の更生手続の特例等に関する法律',
    # 組合・法人系
    '消費生活協同組合法', '農業協同組合法', '水産業協同組合法',
    '森林組合法', '中小企業等協同組合法',
    '一般社団法人及び一般財団法人に関する法律',
    # 医療・その他
    '医療法', 'がん登録等の推進に関する法律',
    # 交通・自動車系
    '自動車の運転により人を死傷させる行為等の処罰に関する法律',
    '道路交通法',
    # 廃止法・旧法
    '競売法',
    # 施行法
    '民法施行法', '刑事訴訟法施行法',
    # 同法参照
    '同法',
)

# ==============================================================================
# 事前ソート済みリスト（パフォーマンス最適化）
# ==============================================================================
# 注意: これらのリストはモジュールロード時に1回だけ生成される。
# CROSS_LINKABLE_LAWS / EXTERNAL_LAW_PATTERNS を動的に変更する場合は
# これらのリストも再生成する必要がある（現時点では想定していない）。

# 長い法令名から順にマッチするためのソート済みリスト
# 例: 「刑事訴訟法」が「刑法」より先にマッチするように
CROSS_LINKABLE_LAWS_SORTED: Tuple[str, ...] = tuple(
    sorted(CROSS_LINKABLE_LAWS.keys(), key=len, reverse=True)
)

# 外部法令名も同様に長い順でソート
EXTERNAL_LAW_PATTERNS_SORTED: Tuple[str, ...] = tuple(
    sorted(EXTERNAL_LAW_PATTERNS, key=len, reverse=True)
)


# ==============================================================================
# 本法/この法律/当該法 パターン（内部参照）
# ==============================================================================
# これらのパターンは自己参照（当該法令内の条文への参照）を示す。
# 「本法第N条」「この法律第N条」「当該法第N条」「当該法律第N条」
#
# 列挙対応: 「本法第X条、第Y条、第Z条の二」のような列挙を分割処理する。

# 本法系のプレフィックスパターン
SELF_LAW_PREFIXES: Tuple[str, ...] = (
    '本法',
    'この法律',
    '当該法律',
    '当該法',
)

# 本法系プレフィックス（長い順にソート済み）
SELF_LAW_PREFIXES_SORTED: Tuple[str, ...] = tuple(
    sorted(SELF_LAW_PREFIXES, key=len, reverse=True)
)


# ==============================================================================
# 法令名 → law_id 解決（クロスリンク edges 生成用）
# ==============================================================================

# グローバルキャッシュ: 法令名 → egov_law_id
_LAW_ID_CACHE: Dict[str, Optional[str]] = {}

# グローバルキャッシュ: Vault 内の法令ディレクトリ名セット
# run 中に一度だけロードし、法令存在チェックを高速化
_VAULT_LAW_DIRS_CACHE: Optional[set] = None

# グローバル設定: Vault ルートパス（初回呼び出し時に設定）
_VAULT_ROOT: Optional[Path] = None


def get_vault_law_dirs(vault_root: Optional[Path] = None) -> set:
    """
    Vault 内の法令ディレクトリ名セットを取得（キャッシュ付き）

    初回呼び出し時に Vault/laws/ 配下のディレクトリ一覧をロードし、
    以降はキャッシュを返す。これにより法令存在チェックが O(1) になる。

    Args:
        vault_root: Vault ルートパス（省略時はグローバル設定を使用）

    Returns:
        法令ディレクトリ名のセット（例: {'刑法', '民法', '会社法', ...}）
    """
    global _VAULT_LAW_DIRS_CACHE, _VAULT_ROOT

    if _VAULT_LAW_DIRS_CACHE is not None:
        return _VAULT_LAW_DIRS_CACHE

    root = vault_root or _VAULT_ROOT
    if root is None:
        return set()

    laws_dir = root / "laws"
    if not laws_dir.exists():
        _VAULT_LAW_DIRS_CACHE = set()
        return _VAULT_LAW_DIRS_CACHE

    # ディレクトリのみを取得
    _VAULT_LAW_DIRS_CACHE = {
        d.name for d in laws_dir.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    }
    return _VAULT_LAW_DIRS_CACHE


def clear_vault_caches() -> None:
    """
    Vault 関連のキャッシュをクリア

    テスト用、または Vault 構造が変更された場合に使用。
    """
    global _LAW_ID_CACHE, _VAULT_LAW_DIRS_CACHE
    _LAW_ID_CACHE = {}
    _VAULT_LAW_DIRS_CACHE = None


def set_vault_root(vault_root: Path) -> None:
    """
    Vault ルートパスを設定

    Args:
        vault_root: Vault ディレクトリへのパス
    """
    global _VAULT_ROOT
    _VAULT_ROOT = vault_root


def resolve_law_id_from_vault(law_name: str, vault_root: Optional[Path] = None) -> Optional[str]:
    """
    法令名から egov_law_id を解決

    Vault/laws/<法令名>/<法令名>.md の frontmatter から egov_law_id を取得。
    結果はキャッシュされる。

    Args:
        law_name: 法令名（例: '刑法'）
        vault_root: Vault ルートパス（省略時はグローバル設定を使用）

    Returns:
        egov_law_id（例: '140AC0000000045'）、見つからなければ None
    """
    global _LAW_ID_CACHE, _VAULT_ROOT

    # キャッシュ確認
    if law_name in _LAW_ID_CACHE:
        return _LAW_ID_CACHE[law_name]

    # Vault ルート解決
    root = vault_root or _VAULT_ROOT
    if root is None:
        _LAW_ID_CACHE[law_name] = None
        return None

    # 法令ディレクトリから CROSS_LINKABLE_LAWS のマッピングを使用してフォルダ名を取得
    folder_name = CROSS_LINKABLE_LAWS.get(law_name, law_name)

    # 法令 md ファイルを探す
    law_dir = root / "laws" / folder_name
    law_md = law_dir / f"{folder_name}.md"

    if not law_md.exists():
        _LAW_ID_CACHE[law_name] = None
        return None

    # frontmatter から egov_law_id を取得
    doc = read_markdown_file(law_md)
    if doc is None:
        _LAW_ID_CACHE[law_name] = None
        return None

    law_id = doc.metadata.get('egov_law_id')
    _LAW_ID_CACHE[law_name] = law_id
    return law_id


def clear_law_id_cache() -> None:
    """法令ID キャッシュをクリア（テスト用）"""
    global _LAW_ID_CACHE
    _LAW_ID_CACHE = {}


def law_exists_in_vault(law_name: str, vault_root: Optional[Path] = None) -> bool:
    """
    法令が Vault に存在するかどうかを判定

    キャッシュを活用した2段階チェック:
    1. キャッシュで法令ディレクトリの存在を確認（O(1)）
    2. 本文ディレクトリの存在を確認（条文が存在することを保証）

    Args:
        law_name: 法令名（例: '弁護士法'）
        vault_root: Vault ルートパス（省略時はグローバル設定を使用）

    Returns:
        True: 法令が Vault に存在し、本文ディレクトリがある
        False: 法令が Vault に存在しない
    """
    global _VAULT_ROOT

    root = vault_root or _VAULT_ROOT
    if root is None:
        return False

    # 1. キャッシュでクイックチェック（存在しない場合は即座に False）
    vault_laws = get_vault_law_dirs(root)
    if law_name not in vault_laws:
        # CROSS_LINKABLE_LAWS のエイリアスもチェック
        resolved_name = CROSS_LINKABLE_LAWS.get(law_name)
        if resolved_name is None or resolved_name not in vault_laws:
            return False
        law_name = resolved_name

    # 2. 本文ディレクトリが存在するかチェック（条文の存在を保証）
    honbun_dir = root / "laws" / law_name / "本文"
    return honbun_dir.exists()


def extract_external_law_with_num(context: str) -> Optional[Tuple[str, str]]:
    """
    「法令名（法令番号）」パターンから法令名を抽出

    会社法第943条のような「他法令条番号の大量列挙」パターン:
    - 弁護士法（昭和二十四年法律第二百五号）
    - 司法書士法（昭和二十五年法律第百九十七号）

    Args:
        context: 条文参照の直前のコンテキスト

    Returns:
        (法令名, 法令番号) のタプル、マッチしなければ None
        例: ('弁護士法', '昭和二十四年法律第二百五号')
    """
    # まず、コンテキストが「...法（...号）」で終わるかチェック
    base_pattern = r'([^\s。、「（）]{1,30}法)（([^）]{5,40}号)）$'
    base_match = re.search(base_pattern, context)
    if not base_match:
        return None

    # マッチした法令名候補
    raw_law_name = base_match.group(1)
    law_num = base_match.group(2)

    # セパレータで分割して最後の法令名部分を取得
    # セパレータ: 若しくは、並びに、及び、又は、、、。
    separators = ['若しくは', '並びに', '及び', '又は', '、', '。']

    # 法令名候補内で最後のセパレータ位置を探す
    last_sep_end = 0
    for sep in separators:
        pos = raw_law_name.rfind(sep)
        if pos >= 0:
            sep_end = pos + len(sep)
            if sep_end > last_sep_end:
                last_sep_end = sep_end

    # セパレータ以降を法令名として返す
    law_name = raw_law_name[last_sep_end:]

    # 法令名が空、または「法」だけ、または2文字未満なら無効
    if len(law_name) < 2 or law_name == '法':
        return None

    return (law_name, law_num)


def get_law_name_variants(law_name: str) -> Tuple[str, ...]:
    """
    法律名のバリエーションを返す

    Args:
        law_name: 親法名（例: '民法'）

    Returns:
        法律名バリエーションのタプル
    """
    return (
        law_name,                    # 民法
        f'新{law_name}',             # 新民法
        f'旧{law_name}',             # 旧民法
        f'改正前の{law_name}',       # 改正前の民法
        f'改正後の{law_name}',       # 改正後の民法
    )


# スコープをリセットする照応語パターン
# これらが法名出現後（tail）に含まれていればスコープをOFFにする
#
# TODO: 「の規定により」等のパターンは、通常条文（本則）で使用されると
#       意図しないスコープリセットが発生する可能性がある。
#       例: 「民法第2条の規定により、第3条を...」では、通常モードでも
#       「第3条」がスコープ外扱いになりうる。
#       現時点では has_parent_law_scope() が「法令名＋第」の最後の出現位置を
#       基準にしており、「の規定により」後でも同一文内に「民法第」があれば
#       スコープが維持されるため、実用上の問題は少ない。
#       将来的に問題が発生した場合は、以下の分離を検討:
#       - SCOPE_RESET_PATTERNS_COMMON: 照応語（同法、前条等）- 常に有効
#       - SCOPE_RESET_PATTERNS_AMENDMENT_ONLY: の規定により等 - 改正法断片のみ有効
#
SCOPE_RESET_PATTERNS: Tuple[str, ...] = (
    # 同〜参照
    '同法', '同条', '同項', '同号', '同表', '同附則',
    # 前後参照
    '前条', '次条', '前項', '次項', '前号', '次号',
    # 本〜参照
    '本条', '本項', '本号',
    # 間接参照（指示語）
    'その', '当該',
    # 規定参照終了パターン（改正法文脈で、親法の規定を参照した後に
    # 改正法自身の条文を参照する場合）
    # 注: 通常モードでの副作用については上記 TODO 参照
    'の規定により', 'の規定に基づき', 'の規定を適用',
    # 「の規定は、」は法令の規定内容を説明する導入句であり、
    # 後続の条文参照は別の文脈（自法令への参照など）に移行
    'の規定は',
)


# 法令名の直前に来ることが許される文字パターン
# これら以外の文字が直前にある場合、より長い法令名の一部である可能性がある
LAW_NAME_VALID_PREFIXES: Tuple[str, ...] = (
    # 接頭辞
    '新', '旧',
    # 句読点・記号
    '、', '。', '「', '」', '（', '）', '・', '，', '．',
    # 改行・空白
    '\n', '\r', ' ', '　',
    # 助詞・接続
    'の', 'は', 'が', 'を', 'に', 'と', 'で', 'も', 'や', 'び',
    # 指示語など
    'る', 'き', 'て', 'し',
)


def is_valid_law_name_boundary(text: str, match_start: int) -> bool:
    """
    法令名マッチが有効な境界にあるかチェック

    より長い法令名の部分文字列としてマッチしている場合はFalseを返す。
    例: "刑事訴訟法" 内の "刑法" は無効なマッチ

    Args:
        text: マッチ対象のテキスト
        match_start: マッチ開始位置

    Returns:
        True: 有効な境界（リンク化してよい）
        False: 無効な境界（より長い法令名の一部）
    """
    # 文字列の先頭ならOK
    if match_start == 0:
        return True

    # 直前の文字を取得
    prev_char = text[match_start - 1]

    # 許可された前置文字ならOK
    if prev_char in LAW_NAME_VALID_PREFIXES:
        return True

    # それ以外はNG（より長い法令名の一部である可能性）
    return False


def has_external_law_in_context(text: str, match_position: int) -> bool:
    """
    同一文脈内に外部法令名が出現しているかチェック

    同一文内に外部法令名（土地収用法など）が出現している場合、
    裸の「第N条」参照がその外部法令を指している可能性があるため、
    親法へのリンク化を抑制する。

    句点（。）の扱いに注意:
    - 括弧内（）や引用符内「」の句点は文の区切りとしてカウントしない

    Args:
        text: 全体テキスト
        match_position: マッチ位置

    Returns:
        True: 外部法令名が文脈内に存在（リンク化を抑制すべき）
        False: 外部法令名なし
    """
    # 現在位置より前のコンテキスト窓を取得
    context_start = max(0, match_position - CONTEXT_WINDOW_EXTERNAL_LAW)
    before_text = text[context_start:match_position]

    # WikiLinkを表示テキストに置換
    context_cleaned = strip_wikilinks(before_text)

    # 外部法令名を長い順に検索（事前ソート済みリストを使用）
    for ext_law in EXTERNAL_LAW_PATTERNS_SORTED:
        pos = context_cleaned.rfind(ext_law)
        if pos >= 0:
            # 法令名出現位置から現在位置までのテキストを取得
            between = context_cleaned[pos:]

            # 括弧内・引用符内の句点は除外して文の区切りをチェック
            # 簡易的に、ネストしない括弧・引用符を除去
            between_no_paren = re.sub(r'（[^）]*）', '', between)
            between_no_quote = re.sub(r'「[^」]*」', '', between_no_paren)

            # 文の区切り（。）がなければ同一文内
            if '。' not in between_no_quote:
                return True

    return False


def has_self_law_prefix(context: str) -> bool:
    """
    コンテキストが本法系プレフィックスで終わるかチェック

    「本法」「この法律」「当該法」「当該法律」の直後に第N条が来る場合、
    これは自己参照（当該法令内の条文への参照）である。

    Args:
        context: マッチ位置の直前のテキスト（括弧除去済み）

    Returns:
        True: 本法系プレフィックスが直前にある（内部参照として処理すべき）
        False: 本法系プレフィックスなし
    """
    # 末尾の空白を除去
    context_stripped = context.rstrip()

    # 長い順にチェック（「当該法律」を「当該法」より先に）
    for prefix in SELF_LAW_PREFIXES_SORTED:
        if context_stripped.endswith(prefix):
            return True

    return False


def find_cross_link_scope(
    text: str,
    match_position: int,
    current_law: str,
    vault_root: Optional[Path] = None
) -> Optional[str]:
    """
    クロスリンクスコープ内の法令を検索

    同一文内に「法令名＋第N条」パターンが出現しており、その後に照応語がない場合、
    その法令へのクロスリンクスコープが有効と判定する。
    これにより「刑法第176条、第177条」のような連続参照を正しく処理できる。

    Phase 3: Vault 実在ベース一般化
    - CROSS_LINKABLE_LAWS に加え、EXTERNAL_LAW_PATTERNS もチェック
    - EXTERNAL_LAW_PATTERNS の法令は Vault 存在確認後にスコープ設定

    重要: 単なる法令名の列挙（「刑法、暴力行為等処罰に関する法律...」）では
    スコープを有効にしない。法令名の直後に「第」が続く場合のみ有効。

    Args:
        text: 全体テキスト
        match_position: マッチ位置
        current_law: 現在処理中の法律名

    Returns:
        クロスリンク先の法律フォルダ名、見つからない場合は None
    """
    # 現在位置より前のテキストを取得
    before_text = text[:match_position]

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
    sentence_cleaned = strip_wikilinks(current_sentence)

    # 括弧内（法令番号など）を除去
    sentence_cleaned = re.sub(r'（[^）]*）', '', sentence_cleaned)

    # =========================================================================
    # Phase 1: 文末法令名チェック（直近優先ルール）
    # =========================================================================
    # 文脈が法令名で終わっている場合、その法令名の直後の「第」は処理中の参照の一部。
    # 例: 「...新刑事訴訟法」+ 処理中の「第290条」→ 新刑事訴訟法への参照
    #
    # これにより、同一文内に複数の法令参照があっても、直近のものが優先される:
    # 「旧刑法第176条...新刑事訴訟法第290条」
    #   → 第290条は「新刑事訴訟法」にリンク（「旧刑法」スコープは無効化）
    for immediate_law_name in CROSS_LINKABLE_LAWS_SORTED:
        if sentence_cleaned.endswith(immediate_law_name):
            target_folder = CROSS_LINKABLE_LAWS[immediate_law_name]
            if target_folder == current_law:
                # 自法令への参照 → クロスリンクではない（親法リンクを使用）
                return None
            else:
                # 他法令への参照 → その法令へクロスリンク
                return target_folder

    # =========================================================================
    # Phase 1b: 文末 EXTERNAL_LAW_PATTERNS チェック（Vault 存在確認付き）
    # =========================================================================
    # CROSS_LINKABLE_LAWS に含まれない法令でも、文末にあり Vault に存在すれば
    # その法令へのクロスリンクとして処理する。
    # 例: 「刑法第百九十九条及び会社法」+ 処理中の「第一条」→ 会社法への参照
    for ext_law in EXTERNAL_LAW_PATTERNS_SORTED:
        # CROSS_LINKABLE_LAWS と重複する場合はスキップ（Phase 1 で処理済み）
        if ext_law in CROSS_LINKABLE_LAWS:
            continue
        if sentence_cleaned.endswith(ext_law):
            if ext_law == current_law:
                # 自法令への参照 → クロスリンクではない
                return None
            # Vault 存在チェック
            if law_exists_in_vault(ext_law, vault_root):
                return ext_law
            # Vault に存在しない場合は次の法令名を試す

    # =========================================================================
    # Phase 2: 文中「法令名＋第」パターン検索
    # =========================================================================
    # 文末に法令名がない場合、文中の「法令名＋第N条」パターンを検索。
    # 長い法令名から順にチェックし、最後に出現した他法令のスコープを返す。
    last_match_pos = -1
    last_match_law = None
    last_match_end = -1

    for cross_law_name in CROSS_LINKABLE_LAWS_SORTED:
        # 法令名 + 第 のパターンを検索（法令名の直後に「第」がある場合のみ）
        pattern = re.escape(cross_law_name) + r'第'
        for match in re.finditer(pattern, sentence_cleaned):
            pos = match.start()
            if pos > last_match_pos:
                target_folder = CROSS_LINKABLE_LAWS[cross_law_name]
                # 自法令への参照は除外
                if target_folder != current_law:
                    last_match_pos = pos
                    last_match_law = target_folder
                    last_match_end = match.end()

    # =========================================================================
    # Phase 2b: EXTERNAL_LAW_PATTERNS の Vault 存在チェック付き検索
    # =========================================================================
    # CROSS_LINKABLE_LAWS に含まれない法令でも、Vault に存在すればスコープ設定
    for ext_law in EXTERNAL_LAW_PATTERNS_SORTED:
        # CROSS_LINKABLE_LAWS と重複する場合はスキップ（すでに処理済み）
        if ext_law in CROSS_LINKABLE_LAWS:
            continue

        pattern = re.escape(ext_law) + r'第'
        for match in re.finditer(pattern, sentence_cleaned):
            pos = match.start()
            if pos > last_match_pos:
                # 自法令への参照は除外
                if ext_law != current_law:
                    # Vault 存在チェック
                    if law_exists_in_vault(ext_law, vault_root):
                        last_match_pos = pos
                        last_match_law = ext_law  # Vault のフォルダ名として使用
                        last_match_end = match.end()

    if last_match_law is None:
        return None

    # tail = 法令名＋第 の後のテキスト（法令名自体を含めない）
    tail = sentence_cleaned[last_match_end:]

    # tail内に照応語（同法、同条等）があればスコープをリセット
    for reset_pattern in SCOPE_RESET_PATTERNS:
        if reset_pattern in tail:
            return None

    return last_match_law


def has_external_law_scope(text: str, match_position: int) -> bool:
    """
    外部法令スコープが有効かどうかを判定

    同一文内に「外部法令名＋第N条」パターンが出現しており、
    その後に照応語（同法等）がない場合、スコープ内と判定する。
    これにより「外部法第1条、第2条」のような連続参照を正しくリンク化しない。

    重要: 単なる法令名の列挙（「刑法、暴力行為等処罰に関する法律...」）では
    スコープを有効にしない。法令名の直後に「第」が続く場合のみ有効。

    Args:
        text: 全体テキスト
        match_position: マッチ位置

    Returns:
        True: 外部法令スコープ内（リンク化しない）
        False: スコープ外
    """
    # 現在位置より前のテキストを取得
    before_text = text[:match_position]

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
    sentence_cleaned = strip_wikilinks(current_sentence)

    # 括弧内（法令番号など）を除去
    sentence_cleaned = re.sub(r'（[^）]*）', '', sentence_cleaned)

    # 外部法令名 + 第N条 パターンの最後の出現を探す
    # 長い法令名から順にチェック（事前ソート済みリストを使用）
    last_match_pos = -1
    last_match_end = -1

    for ext_law in EXTERNAL_LAW_PATTERNS_SORTED:
        # 法令名 + 第 のパターンを検索（法令名の直後に「第」がある場合のみ）
        pattern = re.escape(ext_law) + r'第'
        for match in re.finditer(pattern, sentence_cleaned):
            pos = match.start()
            if pos > last_match_pos:
                last_match_pos = pos
                last_match_end = match.end()

    if last_match_pos < 0:
        return False

    # tail = 法令名＋第 の後のテキスト（法令名自体を含めない）
    tail = sentence_cleaned[last_match_end:]

    # tail内に照応語（同法、同条等）があればスコープをリセット
    for reset_pattern in SCOPE_RESET_PATTERNS:
        if reset_pattern in tail:
            return False

    return True


def has_parent_law_scope(text: str, match_position: int, law_name: str) -> bool:
    """
    親法スコープが有効かどうかを判定

    「親法スコープ」= 法律名＋第N条 パターンが出現してから、
    スコープリセット条件に当たるまでの範囲。
    この範囲内では、裸の第N条も親法への参照としてリンク化する。

    重要: 単なる法律名の出現（「刑法等の一部を改正する法律...」）では
    スコープを有効にしない。法律名の直後に「第」が続く場合のみ有効。

    スコープ判定ルール:
    1. 同一文内（句点から現在位置まで）を対象
    2. 段落区切り（改行2連続）があればその後ろのみ対象
    3. 最後に出現した「親法名＋第」パターンの位置を特定
    4. その位置より後（tail）に照応語（同法、同条等）があればスコープOFF

    例: 「新民法第749条、第771条及び第788条」
        → 「新民法第」が出現、tail内に照応語なし → すべてリンク化

    例: 「民法第1条及び同法第2条」
        → 「民法第」後に「同法」→ 第2条のスコープはOFF

    例: 「刑法等の一部を改正する法律...第491条」
        → 「刑法第」パターンなし → スコープ無効

    Args:
        text: 全体テキスト
        match_position: マッチ位置
        law_name: 親法名

    Returns:
        True: 親法スコープ内（リンク化すべき）
        False: スコープ外（リンク化しない）
    """
    # 現在位置より前のテキストを取得
    before_text = text[:match_position]

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
    sentence_cleaned = strip_wikilinks(current_sentence)

    # 括弧内（法令番号など）を除去
    sentence_cleaned = re.sub(r'（[^）]*）', '', sentence_cleaned)

    # 法律名バリエーション + 第 パターンの最後の出現位置を探す
    variants = get_law_name_variants(law_name)
    last_law_pos = -1
    last_law_end = -1

    for variant in variants:
        # 法律名 + (の|、|\n)? + 第 のパターンを検索
        # 「民法第N条」「民法の第N条」「民法、第N条」「民法\n第N条」に対応
        pattern = re.escape(variant) + r'(?:[の、\n])?第'
        for match in re.finditer(pattern, sentence_cleaned):
            pos = match.start()
            if pos > last_law_pos:
                last_law_pos = pos
                last_law_end = match.end()

        # 追加: 法律名（または法律名+区切り文字）が文末にある場合
        # 「新民法第749条」「民法の第749条」「民法、第749条」のように、
        # 法令名の直後に現在処理中の「第N条」がある場合もスコープ有効とする
        # この場合、sentence_cleanedは「...新民法」「...民法の」「...民法、」で終わり、
        # 「第」は現在処理中の参照の一部
        for suffix in [variant + 'の', variant + '、', variant + '\n', variant]:
            if sentence_cleaned.endswith(suffix):
                end_pos = len(sentence_cleaned)
                start_pos = end_pos - len(suffix)
                if start_pos > last_law_pos:
                    last_law_pos = start_pos
                    last_law_end = end_pos  # 「第」は含まないがスコープは有効
                break  # 長い方を優先

    # 法律名＋第パターンが見つからなければスコープ外
    if last_law_pos < 0:
        return False

    # tail = 法律名＋第 の後のテキスト（法律名自体を含めない）
    tail = sentence_cleaned[last_law_end:]

    # tail内に照応語（同法、同条等）があればスコープをリセット
    for reset_pattern in SCOPE_RESET_PATTERNS:
        if reset_pattern in tail:
            return False

    return True


def has_any_law_prefix(context_cleaned: str, law_name: str) -> bool:
    """
    context_cleaned 内に法令名プレフィックスが存在するかを判定

    この関数は、条文参照（第N条）の直前に法令名が出現しているかを
    統一的に判定するためのヘルパー。以下のケースを検出:

    1. クロスリンク対象法令名 + サフィックスパターン
       例: 「刑法第」「民法の第」「刑事訴訟法...第」

    2. 親法名（law_name のバリエーション）+ 区切り文字
       例: 「民法」「新民法」「民法の」「民法、」

    用途:
    - 改正法断片内の「第N条の規定により」判定
    - 裸の参照 vs 法令名付き参照の区別

    Args:
        context_cleaned: 括弧書き除去済みの直前テキスト
        law_name: 親法名（例: '民法'）

    Returns:
        True: 法令名プレフィックスが存在（リンク化対象）
        False: 裸の参照（改正法断片ではリンク化しない）

    Note:
        この関数は境界チェック（is_valid_law_name_boundary）を行わない。
        クロスリンク先の決定時には別途境界チェックが必要。
    """
    # 1. クロスリンク対象法令名をチェック
    # LAW_NAME_SUFFIX_PATTERN: [^第]{0,20}$ で法令名から「第」までの距離を制限
    for cross_law_name in CROSS_LINKABLE_LAWS_SORTED:
        pattern = re.escape(cross_law_name) + LAW_NAME_SUFFIX_PATTERN
        if re.search(pattern, context_cleaned):
            return True

    # 2. 親法名バリエーションをチェック
    # 末尾パターン: 法令名 + オプションの区切り文字（の、、、\n）+ 文字列終端
    for variant in get_law_name_variants(law_name):
        pattern = re.escape(variant) + r'(?:[の、\n])?$'
        if re.search(pattern, context_cleaned):
            return True

    # 3. 本法系プレフィックスをチェック
    # 「本法」「この法律」「当該法律」「当該法」
    if has_self_law_prefix(context_cleaned):
        return True

    return False


class EdgeExtractor:
    """
    条文参照の抽出とWikiLink生成を行うクラス

    SSOT (Single Source of Truth) 設計:
    - 参照解釈ロジックは replace_refs_with_edges() に集約
    - replace_refs() と extract_refs() は replace_refs_with_edges() を呼び出すラッパ
    - これによりWikiLinkとedges.jsonlの不整合を防止
    """

    def __init__(self, vault_root: Optional[Path] = None):
        """
        Args:
            vault_root: Vault ルートパス（クロスリンク edges の target law_id 解決に使用）
        """
        # Ref pattern supporting Kanji numerals
        # 第X条 where X can be Kanji or digits
        # Also supports sub-article numbers like 第N条の二
        # Kanji chars: 一二三四五六七八九十百千
        #
        # 重要: 日本語法令では「第十九条の二」のように、
        # 条番号の後に「のM」が続く形式（条が先、枝番が後）
        # パターン: 第(N)条(?:の(M))? で最大一致を保証
        kanji_class = r"[0-9一二三四五六七八九十百千]+"
        self.ref_pattern = re.compile(rf"第({kanji_class})条(?:の({kanji_class}))?")
        self.vault_root = vault_root

    def replace_refs_with_edges(
        self,
        text: str,
        law_name: str,
        source_law_id: str,
        source_node_id: str,
        is_amendment_fragment: bool = False
    ) -> Tuple[str, List[Dict]]:
        """
        条文参照をWikiLinkに置換し、同時にエッジを収集する（SSOT）

        この関数が参照解釈の唯一の実装であり、replace_refs() と extract_refs() は
        この関数を呼び出すラッパとなっている。

        Args:
            text: 変換対象テキスト
            law_name: 親法名（例: '民法'）
            source_law_id: ソース法令の egov_law_id（例: '129AC0000000089'）
            source_node_id: ソースノードID（例: 'JPLAW:129AC0000000089#main#10'）
            is_amendment_fragment: 改正法断片内の場合 True

        Returns:
            (replaced_text, edges) のタプル
            - replaced_text: WikiLinkに変換されたテキスト
            - edges: 抽出されたエッジのリスト（replace_refsで「リンク化しない」と
                     判断された参照はedgesにも含まれない）
        """
        edges: List[Dict] = []

        def _replacer(m):
            original_text = m.group(0)  # e.g. 第九条
            match_start = m.start()
            match_end = m.end()

            # マッチ位置の前の文脈を取得してチェック
            context_start = max(0, match_start - CONTEXT_WINDOW_IMMEDIATE)
            context = text[context_start:match_start]

            # クロスリンク先の法令（後続処理で設定される可能性あり）
            cross_link_target = None
            cross_link_law_name = None  # マッチした法令名（law_id解決用）
            # 自法令への法令番号付き参照フラグ（セクション2の外部法チェックをスキップ）
            is_self_law_with_num = False

            # 0a. 「法令名（法令番号）第N条」パターンの外部法参照検出
            # このパターンは外部法令への参照であり、自法令としてリンクしてはならない
            # 例: 弁護士法（昭和二十四年法律第二百五号）第三十条の二十八
            #     → 弁護士法への参照（会社法にリンクしない）
            #
            # パターン: XXX法（YYY号）$ （法令名 + 括弧付き法令番号 + 文末）
            # 注: 括弧除去前の raw context でチェック
            #
            # 処理方針:
            #   1. 対象法令がVaultに存在する場合
            #      → その法令の条文ノードへ正しくリンク + edge生成
            #   2. 対象法令がVaultに存在しない場合
            #      → リンクなし、external edge のみ生成
            external_law_info = extract_external_law_with_num(context)
            if external_law_info:
                ext_law_name, ext_law_num = external_law_info

                # 自法令への参照（会社法内の「会社法（...）第N条」など）は通常処理
                # ただしセクション2の外部法チェックをスキップするためフラグを設定
                if ext_law_name == law_name:
                    is_self_law_with_num = True  # 自法令参照 → 外部法チェックスキップ
                elif law_exists_in_vault(ext_law_name, self.vault_root):
                    # Vault に存在する → cross-link 生成（後続処理で wikilink + edge）
                    # cross_link_target, cross_link_law_name は後で設定するので
                    # ここでは ext_law_name を記録して後続チェックをスキップ
                    cross_link_target = ext_law_name
                    cross_link_law_name = ext_law_name
                    # 他の外部法令チェック（2, 2b, 2c）をスキップするためフラグを設定
                    # → 後続処理で cross_link_target があれば外部法チェックはスキップされる
                else:
                    # Vault に存在しない → external edge のみ生成、リンクなし
                    # 条番号をパース
                    article_num_raw = m.group(1)
                    sub_num_raw = m.group(2)
                    article_num = str(kanji_to_int(article_num_raw))
                    if sub_num_raw:
                        sub_num = str(kanji_to_int(sub_num_raw))
                        target_key = f"{article_num}_{sub_num}"
                    else:
                        target_key = article_num

                    # external edge 生成
                    external_target = f"external:{ext_law_name}#main#{target_key}"
                    edge = {
                        "from": source_node_id,
                        "to": external_target,
                        "type": "refers_to",
                        "evidence": original_text,
                        "confidence": 0.9,
                        "source": "regex_v2",
                        "kind": "external_ref"
                    }
                    edges.append(edge)
                    return original_text  # リンク化しない

            # 括弧内（法令番号など）を除去してチェック
            # 例: 「○○法律（平成二十五年法律第八十六号）」→「○○法律」
            context_cleaned = re.sub(r'（[^）]*）', '', context)

            # =====================================================================
            # 0b. 本法/この法律/当該法 パターンの検出（内部参照として確定）
            # =====================================================================
            # 優先順位: 法令番号付き参照 > 本法系 > 明示法令名 > 同法
            #
            # 「本法第N条」「この法律第N条」などは当該法令内の条文への参照。
            # 列挙対応: 「本法第X条、第Y条」のような連続参照も内部参照として処理。
            #
            # 検出パターン:
            #   1. context が本法系プレフィックスで終わる（直接参照）
            #   2. context が「本法系 + 第N条 + 列挙セパレータ」で終わる（列挙の継続）
            #      例: "本法第十条、" の後の "第二十条"
            #   3. context が「本法系 + [[wikilink]] + 列挙セパレータ」で終わる（置換後の列挙継続）
            #      例: "本法[[...]]、" の後の "第二十条"
            is_self_law_reference = False
            if has_self_law_prefix(context_cleaned):
                # パターン1: 直接参照
                is_self_law_reference = True
            elif not is_self_law_reference:
                # パターン2, 3: 列挙の継続をチェック
                # WikiLinkを除去してからチェック（[[...]] → 表示テキスト）
                context_no_wikilink = strip_wikilinks(context_cleaned)
                # 本法系 + 第N条 + 列挙セパレータ（、，, ）で終わるかチェック
                for prefix in SELF_LAW_PREFIXES_SORTED:
                    # パターン: 本法第X条[、，,]\s*$ または 本法第X条の二[、，,]\s*$
                    enum_pattern = re.escape(prefix) + r'第[一-龯〇-九0-9]+条(?:の[一-龯〇-九0-9]+)?[、，,]\s*$'
                    if re.search(enum_pattern, context_no_wikilink):
                        is_self_law_reference = True
                        break

            # 0. 改正法断片モード: 「第N条の規定による」パターンはリンク化しない（裸の参照の場合のみ）
            # これは改正法自身の条文番号への参照であり、親法の条文ではない
            # ただし「民法第N条の規定による」のように法令名が付いている場合はリンク化する
            # 注: 通常モード（本文）では親法の条文への参照としてリンク化する
            if is_amendment_fragment:
                after_text = text[match_end:match_end + 10]
                if after_text.startswith('の規定による') or after_text.startswith('の規定に'):
                    # 直前に法令名があるかチェック（SSOT: has_any_law_prefix に集約）
                    if not has_any_law_prefix(context_cleaned, law_name):
                        return original_text  # 裸の参照 + の規定に → リンク化しない

            # 1. クロスリンク対象法令が直近にある場合はその法令へリンク
            # 長い法令名から順にチェック（事前ソート済みリストを使用）
            # 境界チェックも行い、より長い法令名の部分マッチを防ぐ
            # 注: 0a で外部法令（Vault存在）を検出済みの場合はスキップ
            if cross_link_target is None:
                for cross_law_name in CROSS_LINKABLE_LAWS_SORTED:
                    # 法令名 + 0〜N文字 + 第（現在位置）のパターンを検索
                    pattern = re.escape(cross_law_name) + LAW_NAME_SUFFIX_PATTERN
                    match = re.search(pattern, context_cleaned)
                    if match:
                        # 境界チェック: より長い法令名の一部でないことを確認
                        if not is_valid_law_name_boundary(context_cleaned, match.start()):
                            continue  # 無効な境界なので次の（より短い）法令名を試す
                        target_folder = CROSS_LINKABLE_LAWS[cross_law_name]
                        # 自法令への参照は通常処理（クロスリンクではない）
                        if target_folder != law_name:
                            cross_link_target = target_folder
                            cross_link_law_name = cross_law_name
                        break

            # 2. 外部法令名が直近にある場合の処理
            # Phase 3: Vault 実在ベース一般化
            # - Vault に存在する法令 → クロスリンク生成
            # - Vault に存在しない法令 → リンク化しない
            # 注: 自法令への法令番号付き参照（is_self_law_with_num）または本法参照（is_self_law_reference）はスキップ
            # 重要: 文スコープ検索（1b）より先に直近チェックを実行
            #       「会社法第一条及び少年法第二条」→ 少年法は Vault 非存在なのでリンク化しない
            if cross_link_target is None and not is_self_law_with_num and not is_self_law_reference:
                for ext_law in EXTERNAL_LAW_PATTERNS_SORTED:
                    ext_pattern = re.escape(ext_law) + LAW_NAME_SUFFIX_PATTERN
                    match = re.search(ext_pattern, context_cleaned)
                    if match:
                        # 境界チェック: より長い法令名の一部でないことを確認
                        if not is_valid_law_name_boundary(context_cleaned, match.start()):
                            continue
                        # Vault 存在チェック: 存在すればクロスリンク、存在しなければブロック
                        if law_exists_in_vault(ext_law, self.vault_root):
                            # Vault に存在 → クロスリンク生成
                            cross_link_target = ext_law
                            cross_link_law_name = ext_law
                        else:
                            # Vault に存在しない → リンク化せず、エッジも生成しない
                            return original_text
                        break

            # 1b. 直近に見つからない場合、文スコープ内のクロスリンク対象を検索
            # 「刑法第176条、第177条」のような連続参照に対応
            # Phase 3: EXTERNAL_LAW_PATTERNS も Vault 存在チェック付きで検索
            if cross_link_target is None:
                cross_link_target = find_cross_link_scope(text, match_start, law_name, self.vault_root)
                if cross_link_target:
                    cross_link_law_name = cross_link_target  # フォルダ名=法令名

            # 2b. 直近に見つからない場合、文スコープ内の外部法令をチェック
            # 「外部法第1条、第2条」のような連続参照に対応
            # 注: 自法令への法令番号付き参照（is_self_law_with_num）または本法参照（is_self_law_reference）はスキップ
            if cross_link_target is None and not is_self_law_with_num and not is_self_law_reference:
                if has_external_law_scope(text, match_start):
                    return original_text  # リンク化せず、エッジも生成しない

            # 2c. 同一文脈内に外部法令名が出現している場合は裸の参照をリンク化しない
            # 「土地収用法...準用する第八十四条」のようなケースに対応
            # クロスリンク先が明示されている場合はスキップ（そちらを優先）
            # 注: 自法令への法令番号付き参照（is_self_law_with_num）または本法参照（is_self_law_reference）はスキップ
            if cross_link_target is None and not is_self_law_with_num and not is_self_law_reference:
                if has_external_law_in_context(text, match_start):
                    return original_text  # リンク化せず、エッジも生成しない

            # 3. 改正法断片モード: 裸の第N条（法律名なし）はリンク化しない
            #
            # 「親法スコープ」ルール:
            # - 同一文内（句点から句点まで）に親法名（民法/新民法等）があればリンク化
            # - WikiLinkは表示テキストに置換してからチェック（リンクを跨ぐスコープに対応）
            #
            # 例: 「新民法第七百四十九条、第七百七十一条及び第七百八十八条」
            #     → 「新民法」スコープ有効 → すべてリンク化
            #
            # TODO: 将来的には frontmatter の suppl_kind / amendment_law_id を
            #       真実として使用する。現在は呼び出し側 (tier1) が AmendLawNum
            #       属性から判定して is_amendment_fragment を渡している。
            #
            # 注: クロスリンク対象が見つかった場合、または本法参照の場合はスコープチェックをスキップ
            if cross_link_target is None and is_amendment_fragment and not is_self_law_reference:
                if not has_parent_law_scope(text, match_start, law_name):
                    # 親法スコープ外 = 裸の参照 → リンク化しない、エッジも生成しない
                    return original_text

            # =====================================================================
            # ここに到達 = リンク化する参照 → エッジも生成する
            # =====================================================================

            # 正規表現グループ:
            # group(1): 条番号（例: 十九）
            # group(2): 枝番号（例: 二）、ない場合は None
            article_num_raw = m.group(1)  # e.g., 十九
            sub_num_raw = m.group(2)      # e.g., 二 or None

            article_num = str(kanji_to_int(article_num_raw))
            if sub_num_raw:
                sub_num = str(kanji_to_int(sub_num_raw))
                target_filename = f"第{article_num}条の{sub_num}.md"
                target_key = f"{article_num}_{sub_num}"
            else:
                target_filename = f"第{article_num}条.md"
                target_key = article_num

            # クロスリンク先が見つかった場合はそちらを使用
            target_law_folder = cross_link_target if cross_link_target else law_name
            link_path = f"laws/{target_law_folder}/本文/{target_filename}"

            # =====================================================================
            # エッジ生成
            # =====================================================================
            # target の law_id を解決
            if cross_link_target:
                # クロスリンク: target law の law_id を Vault から解決
                target_law_id = resolve_law_id_from_vault(
                    cross_link_law_name or cross_link_target,
                    self.vault_root
                )
                if target_law_id:
                    target_node_id = f"JPLAW:{target_law_id}#main#{target_key}"
                else:
                    # law_id が解決できない場合はエッジを生成しない（安全側）
                    # ただしWikiLinkは生成する（Vaultには存在するので）
                    target_node_id = None
            else:
                # 自法令への参照
                target_node_id = f"JPLAW:{source_law_id}#main#{target_key}"

            # エッジ追加（自己参照は除外）
            if target_node_id and target_node_id != source_node_id:
                edge = {
                    "from": source_node_id,
                    "to": target_node_id,
                    "type": "refers_to",
                    "evidence": original_text,
                    "confidence": 0.9,
                    "source": "regex_v2"  # SSOT版を示す新バージョン
                }
                edges.append(edge)

            return f"[[{link_path}|{original_text}]]"

        replaced_text = self.ref_pattern.sub(_replacer, text)
        return replaced_text, edges

    def replace_refs(
        self,
        text: str,
        law_name: str,
        is_amendment_fragment: bool = False
    ) -> str:
        """
        条文参照をWikiLinkに置換する（互換性維持用ラッパ）

        内部では replace_refs_with_edges() を呼び出し、置換結果のみを返す。
        エッジ抽出が不要な場合（tier1 配線変更前の互換性維持）に使用。

        Args:
            text: 変換対象テキスト
            law_name: 親法名（例: '民法'）
            is_amendment_fragment: 改正法断片内の場合 True

        Returns:
            WikiLinks に変換されたテキスト
        """
        # 互換性維持: law_id と source_node_id がない場合は空文字列を渡す
        # この場合エッジは生成されないが、置換結果は同一
        replaced_text, _ = self.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id="",
            source_node_id="",
            is_amendment_fragment=is_amendment_fragment
        )
        return replaced_text

    def extract_refs(
        self,
        text: str,
        source_id: str,
        law_name: str = "",
        is_amendment_fragment: bool = False
    ) -> List[Dict]:
        """
        テキストから条文参照を抽出してエッジを返す（SSOT版）

        内部では replace_refs_with_edges() を呼び出し、エッジのみを返す。
        replace_refs() と同じ参照解釈を使用するため、WikiLink生成と
        エッジ抽出の不整合が発生しない。

        Args:
            text: 抽出対象テキスト
            source_id: ソースノードID（例: 'JPLAW:129AC0000000089#main#10'）
            law_name: 親法名（例: '民法'）。省略時は source_id から推測
            is_amendment_fragment: 改正法断片内の場合 True

        Returns:
            エッジのリスト
        """
        # source_id から law_id を抽出
        source_law_id = ""
        if "JPLAW:" in source_id:
            parts = source_id.split("#")
            # JPLAW:129AC0000000089 → 129AC0000000089
            source_law_id = parts[0].replace("JPLAW:", "")

        _, edges = self.replace_refs_with_edges(
            text=text,
            law_name=law_name,
            source_law_id=source_law_id,
            source_node_id=source_id,
            is_amendment_fragment=is_amendment_fragment
        )
        return edges

    def _format_article_key(self, num_str: str) -> str:
        return num_str.replace("の", "_") 
