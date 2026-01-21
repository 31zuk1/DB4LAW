"""
外部法令参照のスコープ判定テスト

会社法第943条のような「他法令条番号の大量列挙」で発生する
誤リンク問題を検出・防止するためのテストケース。

=== 将来の改善方針 ===

TestExternalLawWithLawNumber の各テストは現在「リンク化しない」ことを
検証しているが、これは暫定対応。将来的には以下のように改善予定:

1. 対象法令（例: 弁護士法）がVaultに存在する場合:
   - その法令の条文ノードへ正しくリンク + edge生成
   - assert "[[laws/弁護士法/本文/第30条の28.md|第三十条の二十八]]" in result

2. 対象法令がVaultに存在しない場合:
   - リンク化はしないが、edge として「外部参照」を保持
   - edges に {"to": "external:弁護士法#第30条の28", ...} が含まれる

このテストファイルは、上記の改善が実装された際にテストケースを更新すること。
"""

import pytest
from legalkg.core.tier2 import EdgeExtractor


class TestExternalLawWithLawNumber:
    """
    「法令名（法令番号）第N条」パターンの外部法参照テスト

    会社法第943条で問題となったケース:
    - 弁護士法（昭和二十四年法律第二百五号）第三十条の二十八
    - 司法書士法（昭和二十五年法律第百九十七号）第四十五条の二

    これらは外部法令への参照であり、会社法の条文としてリンクしてはならない。
    """

    def setup_method(self):
        self.extractor = EdgeExtractor()

    def test_external_law_with_law_number_not_linked(self):
        """
        「法令名（法令番号）第N条」は外部法参照としてリンク化しない

        入力: 弁護士法（昭和二十四年法律第二百五号）第三十条の二十八第六項
        期待: 第三十条の二十八 はリンク化されない（外部法参照）
        """
        text = "弁護士法（昭和二十四年法律第二百五号）第三十条の二十八第六項において"
        result = self.extractor.replace_refs(text, "会社法")

        # 外部法参照なのでリンク化されてはならない
        assert "[[laws/会社法" not in result
        assert "第三十条の二十八" in result  # プレーンテキストのまま

    def test_external_law_司法書士法(self):
        """司法書士法への参照もリンク化しない"""
        text = "司法書士法（昭和二十五年法律第百九十七号）第四十五条の二第六項"
        result = self.extractor.replace_refs(text, "会社法")

        assert "[[laws/会社法" not in result

    def test_external_law_multiple_in_enumeration(self):
        """
        列挙ブロック内の複数外部法参照

        会社法第943条の実際のパターン（簡略版）
        """
        text = (
            "弁護士法（昭和二十四年法律第二百五号）第三十条の二十八第六項、"
            "司法書士法（昭和二十五年法律第百九十七号）第四十五条の二第六項、"
            "土地家屋調査士法（昭和二十五年法律第二百二十八号）第四十条の二第六項において"
        )
        result = self.extractor.replace_refs(text, "会社法")

        # すべて外部法参照なのでリンク化されてはならない
        assert "[[laws/会社法" not in result


class TestCrossLinkScopeReset:
    """
    クロスリンクスコープのリセットテスト

    会社法第774条の8で問題となったケース:
    - 民法第九十三条...の規定は、第七百七十四条の四...

    「の規定は、」の後は新しい文脈なのでスコープをリセットすべき。
    """

    def setup_method(self):
        self.extractor = EdgeExtractor()

    def test_scope_reset_after_no_kitei_ha(self):
        """
        「の規定は、」後の参照はクロスリンクスコープから外れる

        入力: 民法第九十三条の規定は、第七百七十四条の四において
        期待:
        - 第九十三条 → 民法へリンク（クロスリンク）
        - 第七百七十四条の四 → 会社法へリンク（自法令、スコープリセット後）
        """
        text = "民法第九十三条の規定は、第七百七十四条の四において適用する"
        result = self.extractor.replace_refs(text, "会社法")

        # 第九十三条 は民法へリンク
        assert "[[laws/民法/本文/第93条.md|第九十三条]]" in result
        # 第七百七十四条の四 は会社法へリンク（スコープリセット後）
        assert "[[laws/会社法/本文/第774条の4.md|第七百七十四条の四]]" in result
        # 民法第774条の4 への誤リンクがないこと
        assert "[[laws/民法/本文/第774条の4.md" not in result

    def test_scope_continues_within_enumeration(self):
        """
        同一句読点区間内ではスコープが継続

        入力: 民法第九十三条第一項及び第九十四条第一項
        期待: 両方とも民法へリンク
        """
        text = "民法第九十三条第一項及び第九十四条第一項の規定"
        result = self.extractor.replace_refs(text, "会社法")

        assert "[[laws/民法/本文/第93条.md|第九十三条]]" in result
        assert "[[laws/民法/本文/第94条.md|第九十四条]]" in result


class TestSelfLawReference:
    """
    自法令参照のテスト

    会社法内で「第N条」が出たとき、それが会社法自身への参照かどうか。
    """

    def setup_method(self):
        self.extractor = EdgeExtractor()

    def test_self_reference_linked(self):
        """自法令への参照はリンク化される"""
        text = "第九百五十五条第一項の規定に違反し"
        result = self.extractor.replace_refs(text, "会社法")

        assert "[[laws/会社法/本文/第955条.md|第九百五十五条]]" in result

    def test_no_mistaken_crosslink_for_high_article_number(self):
        """
        高い条番号は他法へクロスリンクされない

        民法の後に第700条台の参照があっても、民法には700条台がないので
        会社法への自己参照として扱うべき。
        """
        text = "民法の規定にかかわらず、第七百七十四条の四を適用"
        result = self.extractor.replace_refs(text, "会社法")

        # 「民法の」だけではスコープが発生しない（「民法第N条」パターンがない）
        # 第774条の4 は会社法へリンク
        assert "[[laws/会社法/本文/第774条の4.md|第七百七十四条の四]]" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
