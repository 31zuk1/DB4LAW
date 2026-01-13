
import re
import json
from pathlib import Path
from typing import List, Dict
from ..utils.numerals import kanji_to_int

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

    def replace_refs(self, text: str, law_name: str) -> str:
        """
        Replace matched references with Obsidian WikiLinks.
        e.g. "第九条" -> "[[laws/刑法/本文/第9条.md|第九条]]"

        重要: 外部法令への参照はリンク化しない
        - 「民事執行法第N条」のように外部法名が前置されている場合
        - 「同法第N条」のように他法律を参照している場合
        """
        # 外部法令名パターン（リンク化を除外する）
        external_law_patterns = [
            r'民事執行法', r'民事訴訟法', r'民事保全法', r'商法', r'会社法',
            r'破産法', r'不動産登記法', r'戸籍法', r'家事事件手続法',
            r'地方自治法', r'自然公園法', r'競売法', r'借地借家法',
            r'建物の区分所有等に関する法律', r'農地法', r'信託法',
            r'電子記録債権法', r'住民基本台帳法', r'行政手続における特定の個人を識別するための番号の利用等に関する法律',
            r'商業登記法', r'金融商品取引法', r'保険業法', r'信用金庫法',
            r'労働金庫法', r'消費生活協同組合法', r'医療法', r'農業協同組合法',
            r'水産業協同組合法', r'森林組合法', r'中小企業等協同組合法',
            r'がん登録等の推進に関する法律', r'社債、株式等の振替に関する法律',
            r'一般社団法人及び一般財団法人に関する法律', r'外国法人の登記及び夫婦財産契約の登記に関する法律',
            r'会社更生法', r'金融機関等の更生手続の特例等に関する法律',
            r'資産の流動化に関する法律', r'投資信託及び投資法人に関する法律',
            r'損害保険料率算出団体に関する法律', r'同法'
        ]

        def _replacer(m):
            original_text = m.group(0)  # e.g. 第九条
            match_start = m.start()

            # マッチ位置の前100文字を取得して外部法参照かチェック
            context_start = max(0, match_start - 100)
            context = text[context_start:match_start]

            # 外部法令名が直近にある場合はリンク化しない
            for pattern in external_law_patterns:
                if re.search(pattern + r'[^第]{0,20}$', context):
                    return original_text  # リンク化せずにそのまま返す

            # 「同法」が直前にある場合もリンク化しない
            if re.search(r'同法[^第]{0,10}$', context):
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
