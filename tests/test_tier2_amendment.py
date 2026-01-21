#!/usr/bin/env python3
"""
DB4LAW: tier2 改正法断片対応のテスト

テスト対象:
- replace_refs() の is_amendment_fragment 引数
- 裸の第N条 vs 法律名付き参照の判定
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from legalkg.core.tier2 import EdgeExtractor


class TestReplaceRefsAmendmentFragment:
    """改正法断片モードのテスト"""

    def setup_method(self):
        self.extractor = EdgeExtractor()

    def test_main_text_normal_linking(self):
        """本文では従来通りリンク化される"""
        text = "第二十七条に規定する場合"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=False)
        assert "[[laws/民法/本文/第27条.md|第二十七条]]" in result

    def test_amendment_bare_ref_not_linked(self):
        """改正法断片では裸の第N条はリンク化されない"""
        text = "第二十七条に規定する場合"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        # リンク化されていないことを確認
        assert "[[" not in result
        assert "第二十七条" in result

    def test_amendment_with_parent_law_name_linked(self):
        """改正法断片でも親法名付きならリンク化される"""
        text = "民法第二十七条に規定する場合"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        # 親法名付きなのでリンク化される
        assert "[[laws/民法/本文/第27条.md|第二十七条]]" in result

    def test_amendment_external_law_not_linked(self):
        """改正法断片で外部法参照はリンク化されない（従来通り）"""
        text = "住民基本台帳法第三十条の規定"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        # 外部法なのでリンク化されない
        assert "[[" not in result
        assert "第三十条" in result

    def test_main_text_external_law_not_linked(self):
        """本文でも外部法参照はリンク化されない（従来通り）"""
        text = "民事執行法第六十三条の規定"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=False)
        # 外部法なのでリンク化されない
        assert "[[" not in result
        assert "第六十三条" in result

    def test_amendment_mixed_refs(self):
        """改正法断片で混在参照の正しい処理"""
        text = "第一条及び民法第二条の規定により第三条を改正"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        # 第一条: 裸 → リンク化されない
        assert "[[laws/民法/本文/第1条.md|第一条]]" not in result
        # 民法第二条: 親法名付き → リンク化される
        assert "[[laws/民法/本文/第2条.md|第二条]]" in result
        # 第三条: 裸 → リンク化されない
        assert "[[laws/民法/本文/第3条.md|第三条]]" not in result

    def test_amendment_branch_article(self):
        """改正法断片で枝番条文の処理"""
        text = "民法第三条の二を改正する"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        # 親法名付きなのでリンク化される
        assert "[[laws/民法/本文/第3条の2.md|第三条の二]]" in result

    def test_main_text_branch_article(self):
        """本文で枝番条文の処理"""
        text = "第十九条の二に規定する"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=False)
        assert "[[laws/民法/本文/第19条の2.md|第十九条の二]]" in result


class TestParentLawNameVariations:
    """親法名の表記揺れ対応テスト"""

    def setup_method(self):
        self.extractor = EdgeExtractor()

    def test_with_particle_no(self):
        """「民法の第N条」（「の」挿入）"""
        text = "民法の第二十七条に規定する"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        assert "[[laws/民法/本文/第27条.md|第二十七条]]" in result

    def test_with_parenthesis_annotation(self):
        """「民法（改正前）第N条」（括弧内注釈）"""
        text = "民法（改正前）第二十七条の規定"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        assert "[[laws/民法/本文/第27条.md|第二十七条]]" in result

    def test_with_punctuation(self):
        """「民法、第N条」（読点挿入）"""
        text = "民法、第二十七条を参照"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        assert "[[laws/民法/本文/第27条.md|第二十七条]]" in result

    def test_with_newline(self):
        """改行を挟む場合"""
        text = "民法\n第二十七条の規定"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        assert "[[laws/民法/本文/第27条.md|第二十七条]]" in result

    def test_distance_limit(self):
        """距離50文字超はリンク化しない"""
        text = "民法" + "あ" * 60 + "第二十七条"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=True)
        assert "[[" not in result


class TestReplaceRefsBackwardCompatibility:
    """後方互換性のテスト"""

    def setup_method(self):
        self.extractor = EdgeExtractor()

    def test_default_not_amendment_fragment(self):
        """デフォルトでは is_amendment_fragment=False"""
        text = "第一条に規定する"
        # 引数なしで呼び出し
        result = self.extractor.replace_refs(text, "民法")
        # リンク化される（デフォルト動作維持）
        assert "[[laws/民法/本文/第1条.md|第一条]]" in result

    def test_kanji_numeral_conversion(self):
        """漢数字変換が正しく動作する"""
        text = "第百九十九条の規定"
        result = self.extractor.replace_refs(text, "刑法", is_amendment_fragment=False)
        assert "[[laws/刑法/本文/第199条.md|第百九十九条]]" in result

    def test_normal_mode_no_kitei_scope_reset(self):
        """
        通常モード（本則）: 「の規定により」後の参照もリンク化される

        仕様の固定:
        - 通常モード（is_amendment_fragment=False）では、「の規定により」は
          スコープリセットとして機能しない
        - 「民法第二条の規定により、第三条...」の「第三条」は民法へリンクされる
        - 改正法断片モードとは異なる動作（そちらでは「第三条」はリンク化されない）

        Note:
        - この動作は、has_parent_law_scope() が「法令名＋第」の最後の出現位置を
          基準にしており、同一文内に「民法第」があればスコープが維持されるため
        - 将来 SCOPE_RESET_PATTERNS を分離する場合、この挙動を維持すること
        """
        text = "民法第二条の規定により、第三条を適用する"
        result = self.extractor.replace_refs(text, "民法", is_amendment_fragment=False)

        # 民法第二条: リンク化される
        assert "[[laws/民法/本文/第2条.md|第二条]]" in result
        # 第三条: 通常モードではリンク化される（改正法断片モードとは異なる）
        assert "[[laws/民法/本文/第3条.md|第三条]]" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
