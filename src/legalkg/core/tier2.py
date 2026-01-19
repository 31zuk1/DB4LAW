import re
import json
from pathlib import Path
from typing import List, Dict, Tuple
from ..utils.numerals import kanji_to_int
from ..utils.patterns import strip_wikilinks

# ==============================================================================
# 定数定義
# ==============================================================================
# コンテキスト窓サイズ: 外部法令名の出現を検出する際の後方探索範囲
# 300文字は日本語で約10〜15文程度をカバー（句点で区切る前のフォールバック用）
CONTEXT_WINDOW_EXTERNAL_LAW = 300

# コンテキスト窓サイズ: 直近の法令名検出用（法令名＋第N条パターン）
# 100文字は「○○法第1条」のような短い参照パターンをカバー
CONTEXT_WINDOW_IMMEDIATE = 100

# 法令名から「第」までの許容最大距離
# 例: 「刑法[0〜20文字]第N条」のような参照パターンで、間に入りうる文字数
# 括弧付き番号「（平成○年法律第○号）」等を考慮して20文字
MAX_LAW_NAME_TO_DAI_DISTANCE = 20

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
SCOPE_RESET_PATTERNS: Tuple[str, ...] = (
    # 同〜参照
    '同法', '同条', '同項', '同号', '同表', '同附則',
    # 前後参照
    '前条', '次条', '前項', '次項', '前号', '次号',
    # 本〜参照
    '本条', '本項', '本号',
    # 間接参照（指示語）
    'その', '当該',
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


def find_cross_link_scope(text: str, match_position: int, current_law: str) -> str | None:
    """
    クロスリンクスコープ内の法令を検索

    同一文内に「法令名＋第N条」パターンが出現しており、その後に照応語がない場合、
    その法令へのクロスリンクスコープが有効と判定する。
    これにより「刑法第176条、第177条」のような連続参照を正しく処理できる。

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
        # 法律名 + 第 のパターンを検索（法律名の直後に「第」がある場合のみ）
        pattern = re.escape(variant) + r'第'
        for match in re.finditer(pattern, sentence_cleaned):
            pos = match.start()
            if pos > last_law_pos:
                last_law_pos = pos
                last_law_end = match.end()

        # 追加: 法律名が文末にある場合（「新民法第749条」のように、
        # 法令名の直後に現在処理中の「第N条」がある場合）もスコープ有効とする
        # この場合、sentence_cleanedは「...新民法」で終わり、
        # 「第」は現在処理中の参照の一部
        if sentence_cleaned.endswith(variant):
            end_pos = len(sentence_cleaned)
            start_pos = end_pos - len(variant)
            if start_pos > last_law_pos:
                last_law_pos = start_pos
                last_law_end = end_pos  # 「第」は含まないがスコープは有効

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


class EdgeExtractor:
    def __init__(self):
        # Ref pattern supporting Kanji numerals
        # 第X条 where X can be Kanji or digits
        # Also supports "のY"
        # Kanji chars: 一二三四五六七八九十百千
        kanji_class = r"[0-9一二三四五六七八九十百千]+"
        self.ref_pattern = re.compile(rf"第({kanji_class}(?:の{kanji_class})*)条")
        
    def extract_refs(self, text: str, source_id: str) -> List[Dict]:
        edges = []
        matches = self.ref_pattern.finditer(text)
        for m in matches:
            ref_num_raw = m.group(1)
            
            # Convert raw (possibly Kanji) to normalized ID suffix
            # e.g. "十九" -> "19", "二十の三" -> "20_3"
            
            article_num = ref_num_raw
            sub_num = None
            
            if "の" in ref_num_raw:
                parts = ref_num_raw.split("の")
                article_num = str(kanji_to_int(parts[0]))
                sub_num = str(kanji_to_int(parts[1]))
                target_key = f"{article_num}_{sub_num}"
            else:
                article_num = str(kanji_to_int(ref_num_raw))
                target_key = article_num
                
            # Construct target ID
            if "JPLAW:" in source_id:
                parts = source_id.split("#")
                law_id_raw = parts[0] # JPLAW:LAWID
                
                # Assume main provision
                target_id = f"{law_id_raw}#main#{target_key}"
                
                # Filter self-references? (Optional)
                if target_id == source_id:
                    continue
                
                edge = {
                    "from": source_id,
                    "to": target_id,
                    "type": "refers_to",
                    "evidence": m.group(0),
                    "confidence": 0.9,
                    "source": "regex_v1"
                }
                edges.append(edge)
                
        return edges

    def replace_refs(
        self,
        text: str,
        law_name: str,
        is_amendment_fragment: bool = False
    ) -> str:
        """
        Replace matched references with Obsidian WikiLinks.
        e.g. "第九条" -> "[[laws/刑法/本文/第9条.md|第九条]]"

        重要: 外部法令への参照はリンク化しない
        - 「民事執行法第N条」のように外部法名が前置されている場合
        - 「同法第N条」のように他法律を参照している場合

        改正法断片モード (is_amendment_fragment=True):
        - 「裸の第N条」（法律名なし）はリンク化しない
        - 「民法第N条」のように親法名が明示されている場合はリンク化する
        - 外部法参照は従来通りリンク化しない

        Args:
            text: 変換対象テキスト
            law_name: 親法名（例: '民法'）
            is_amendment_fragment: 改正法断片内の場合 True

        Returns:
            WikiLinks に変換されたテキスト
        """
        def _replacer(m):
            original_text = m.group(0)  # e.g. 第九条
            match_start = m.start()
            match_end = m.end()

            # 0. 「第N条の規定による」パターンはリンク化しない
            # これは改正法自身の条文番号への参照であり、親法の条文ではない
            after_text = text[match_end:match_end + 10]
            if after_text.startswith('の規定による') or after_text.startswith('の規定に'):
                return original_text

            # マッチ位置の前の文脈を取得してチェック
            context_start = max(0, match_start - CONTEXT_WINDOW_IMMEDIATE)
            context = text[context_start:match_start]

            # 括弧内（法令番号など）を除去してチェック
            # 例: 「○○法律（平成二十五年法律第八十六号）」→「○○法律」
            context_cleaned = re.sub(r'（[^）]*）', '', context)

            # 1. クロスリンク対象法令が直近にある場合はその法令へリンク
            # 長い法令名から順にチェック（事前ソート済みリストを使用）
            # 境界チェックも行い、より長い法令名の部分マッチを防ぐ
            cross_link_target = None
            for cross_law_name in CROSS_LINKABLE_LAWS_SORTED:
                # 法令名 + 0〜N文字 + 第（現在位置）のパターンを検索
                pattern = re.escape(cross_law_name) + rf'[^第]{{0,{MAX_LAW_NAME_TO_DAI_DISTANCE}}}$'
                match = re.search(pattern, context_cleaned)
                if match:
                    # 境界チェック: より長い法令名の一部でないことを確認
                    if not is_valid_law_name_boundary(context_cleaned, match.start()):
                        continue  # 無効な境界なので次の（より短い）法令名を試す
                    target_folder = CROSS_LINKABLE_LAWS[cross_law_name]
                    # 自法令への参照は通常処理（クロスリンクではない）
                    if target_folder != law_name:
                        cross_link_target = target_folder
                    break

            # 1b. 直近に見つからない場合、文スコープ内のクロスリンク対象を検索
            # 「刑法第176条、第177条」のような連続参照に対応
            if cross_link_target is None:
                cross_link_target = find_cross_link_scope(text, match_start, law_name)

            # 2. 外部法令名が直近にある場合はリンク化しない
            if cross_link_target is None:
                for ext_law in EXTERNAL_LAW_PATTERNS:
                    ext_pattern = re.escape(ext_law) + rf'[^第]{{0,{MAX_LAW_NAME_TO_DAI_DISTANCE}}}$'
                    if re.search(ext_pattern, context_cleaned):
                        return original_text  # リンク化せずにそのまま返す

            # 2b. 直近に見つからない場合、文スコープ内の外部法令をチェック
            # 「外部法第1条、第2条」のような連続参照に対応
            if cross_link_target is None:
                if has_external_law_scope(text, match_start):
                    return original_text  # リンク化せずにそのまま返す

            # 2c. 同一文脈内に外部法令名が出現している場合は裸の参照をリンク化しない
            # 「土地収用法...準用する第八十四条」のようなケースに対応
            # クロスリンク先が明示されている場合はスキップ（そちらを優先）
            if cross_link_target is None:
                if has_external_law_in_context(text, match_start):
                    return original_text  # リンク化せずにそのまま返す

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
            # 注: クロスリンク対象が見つかった場合はスコープチェックをスキップ
            if cross_link_target is None and is_amendment_fragment:
                if not has_parent_law_scope(text, match_start, law_name):
                    # 親法スコープ外 = 裸の参照 → リンク化しない
                    return original_text

            ref_num_raw = m.group(1)

            if "の" in ref_num_raw:
                parts = ref_num_raw.split("の")
                article_num = str(kanji_to_int(parts[0]))
                sub_num = str(kanji_to_int(parts[1]))
                target_filename = f"第{article_num}条の{sub_num}.md"
            else:
                article_num = str(kanji_to_int(ref_num_raw))
                target_filename = f"第{article_num}条.md"

            # クロスリンク先が見つかった場合はそちらを使用
            target_law = cross_link_target if cross_link_target else law_name
            link_path = f"laws/{target_law}/本文/{target_filename}"

            return f"[[{link_path}|{original_text}]]"

        return self.ref_pattern.sub(_replacer, text)

    def _format_article_key(self, num_str: str) -> str:
        return num_str.replace("の", "_") 
