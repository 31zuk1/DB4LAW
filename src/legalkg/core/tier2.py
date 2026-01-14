
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple
from ..utils.numerals import kanji_to_int

# ==============================================================================
# 外部法令名パターン（リンク化を除外する）
# ==============================================================================
# 条文参照（第N条）の直前にこれらの法令名がある場合、
# 他法令への参照と判断してリンク化をスキップする。
# 新たな外部法令が必要な場合はこのリストに追加する。
EXTERNAL_LAW_PATTERNS: Tuple[str, ...] = (
    # 民事系
    '民事執行法', '民事訴訟法', '民事保全法', '商法', '会社法',
    '破産法', '不動産登記法', '戸籍法', '家事事件手続法',
    '借地借家法', '建物の区分所有等に関する法律',
    '商業登記法', '外国法人の登記及び夫婦財産契約の登記に関する法律',
    '会社更生法',
    # 行政系
    '地方自治法', '自然公園法', '農地法', '住民基本台帳法',
    '行政手続における特定の個人を識別するための番号の利用等に関する法律',
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
    # 廃止法・旧法
    '競売法',
    # 同法参照
    '同法',
)


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

            # マッチ位置の前100文字を取得して文脈チェック
            context_start = max(0, match_start - 100)
            context = text[context_start:match_start]

            # 1. 外部法令名が直近にある場合はリンク化しない（従来通り）
            for pattern in EXTERNAL_LAW_PATTERNS:
                if re.search(re.escape(pattern) + r'[^第]{0,20}$', context):
                    return original_text  # リンク化せずにそのまま返す

            # 2. 改正法断片モード: 裸の第N条（法律名なし）はリンク化しない
            #
            # TODO: 将来的には frontmatter の suppl_kind / amendment_law_id を
            #       真実として使用する。現在は呼び出し側 (tier1) が AmendLawNum
            #       属性から判定して is_amendment_fragment を渡している。
            #       frontmatter ベースの判定に移行する際は、ここでファイルパスから
            #       メタデータを読み取るか、呼び出し側で suppl_kind を渡す形にする。
            #
            if is_amendment_fragment:
                # 親法名が直前にある場合はリンク化する（例: 「民法第N条」「民法の第N条」）
                # 許容距離: 50文字
                # 許容文字: 「の」「各種括弧」「句読点」「空白/改行/全角スペース」
                # 括弧内テキスト: 「民法（改正前）第N条」のように括弧内の注釈も許容
                near_context = context[-50:] if len(context) >= 50 else context
                # 許容パターン: 法名 + (許容文字 | 括弧内テキスト)* + 末尾
                # 括弧内テキスト: （...）または (...)
                bracket_content = r'(?:[（\(][^）\)]*[）\)])?'
                simple_chars = r'[\s\u3000の「」『』【】、。,.\[\]]*'
                parent_law_pattern = re.escape(law_name) + r'(?:' + simple_chars + bracket_content + r')*' + r'$'
                if not re.search(parent_law_pattern, near_context):
                    # 親法名がない = 裸の参照 → リンク化しない
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

            link_path = f"laws/{law_name}/本文/{target_filename}"

            return f"[[{link_path}|{original_text}]]"

        return self.ref_pattern.sub(_replacer, text)

    def _format_article_key(self, num_str: str) -> str:
        return num_str.replace("の", "_") 
