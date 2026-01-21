"""
外部法令参照のスコープ判定テスト

会社法第943条のような「他法令条番号の大量列挙」で発生する
誤リンク問題を検出・防止するためのテストケース。

外部法令参照の処理方針:
1. 対象法令がVaultに存在する場合:
   - その法令の条文ノードへ正しくリンク + edge生成
   - 例: 民法（...）第93条 → [[laws/民法/本文/第93条.md|第九十三条]]

2. 対象法令がVaultに存在しない場合:
   - リンク化はしないが、external edge を生成
   - to = "external:<法令名>#main#<article_id>"
"""

import pytest
from pathlib import Path
from legalkg.core.tier2 import (
    EdgeExtractor,
    set_vault_root,
    extract_external_law_with_num,
)


class TestExtractExternalLawWithNum:
    """
    extract_external_law_with_num 関数の仕様固定テスト

    会社法第943条のような「他法令条番号の大量列挙」パターンで、
    前置テキストがlaw_nameに混ざらないことを保証する。
    """

    def test_simple_law_name(self):
        """
        単純な法令名パターン

        入力: 弁護士法（昭和二十四年法律第二百五号）
        期待: ('弁護士法', '昭和二十四年法律第二百五号')
        """
        context = "弁護士法（昭和二十四年法律第二百五号）"
        result = extract_external_law_with_num(context)

        assert result is not None
        law_name, law_num = result
        assert law_name == "弁護士法"
        assert law_num == "昭和二十四年法律第二百五号"

    def test_separator_wakushikuha(self):
        """
        「若しくは」セパレータで前置テキストをトリム

        入力: この節の規定若しくは農業協同組合法（昭和二十二年法律第百三十二号）
        期待: ('農業協同組合法', '昭和二十二年法律第百三十二号')

        会社法第943条の実際のパターン。
        """
        context = "この節の規定若しくは農業協同組合法（昭和二十二年法律第百三十二号）"
        result = extract_external_law_with_num(context)

        assert result is not None
        law_name, law_num = result
        assert law_name == "農業協同組合法"  # NOT "この節の規定若しくは農業協同組合法"
        assert law_num == "昭和二十二年法律第百三十二号"

    def test_separator_comma(self):
        """
        「、」セパレータで前置テキストをトリム

        入力: 前の法令参照、司法書士法（昭和二十五年法律第百九十七号）
        期待: ('司法書士法', '昭和二十五年法律第百九十七号')
        """
        context = "前の法令参照、司法書士法（昭和二十五年法律第百九十七号）"
        result = extract_external_law_with_num(context)

        assert result is not None
        law_name, law_num = result
        assert law_name == "司法書士法"
        assert law_num == "昭和二十五年法律第百九十七号"

    def test_separator_oyobi(self):
        """
        「及び」セパレータで前置テキストをトリム
        """
        context = "刑法及び刑事訴訟法（昭和二十三年法律第百三十一号）"
        result = extract_external_law_with_num(context)

        assert result is not None
        law_name, law_num = result
        assert law_name == "刑事訴訟法"

    def test_no_match_without_law_suffix(self):
        """
        「法」で終わらないパターンはマッチしない
        """
        context = "何かの規定（昭和二十年第五号）"
        result = extract_external_law_with_num(context)
        assert result is None

    def test_no_match_without_parentheses(self):
        """
        法令番号が括弧で囲まれていないパターンはマッチしない
        """
        context = "弁護士法昭和二十四年法律第二百五号"
        result = extract_external_law_with_num(context)
        assert result is None


class TestExternalEdgeFormat:
    """
    external edge のフォーマット仕様固定テスト

    to = "external:<law_name>#main#<article_id>" の形式を保証する。
    """

    def setup_method(self):
        vault_root = Path(__file__).parent.parent / "Vault"
        set_vault_root(vault_root)
        self.extractor = EdgeExtractor(vault_root=vault_root)

    def test_article_id_simple(self):
        """
        条番号のみ: 第97条 → 97
        """
        text = "農業協同組合法（昭和二十二年法律第百三十二号）第九十七条において"
        _, edges = self.extractor.replace_refs_with_edges(
            text=text,
            law_name="会社法",
            source_law_id="417AC0000000086",
            source_node_id="JPLAW:417AC0000000086#main#943"
        )

        assert len(edges) == 1
        assert edges[0]["to"] == "external:農業協同組合法#main#97"

    def test_article_id_with_branch(self):
        """
        条番号 + 枝番: 第97条の4 → 97_4
        """
        text = "農業協同組合法（昭和二十二年法律第百三十二号）第九十七条の四において"
        _, edges = self.extractor.replace_refs_with_edges(
            text=text,
            law_name="会社法",
            source_law_id="417AC0000000086",
            source_node_id="JPLAW:417AC0000000086#main#943"
        )

        assert len(edges) == 1
        assert edges[0]["to"] == "external:農業協同組合法#main#97_4"

    def test_943_pattern_law_name_clean(self):
        """
        会社法第943条パターン: law_name に前置テキストが混ざらない

        入力: この節の規定若しくは農業協同組合法（...）第九十七条の四
        期待: to = "external:農業協同組合法#main#97_4"
              NOT "external:この節の規定若しくは農業協同組合法#main#97_4"
        """
        text = "この節の規定若しくは農業協同組合法（昭和二十二年法律第百三十二号）第九十七条の四第五項において"
        _, edges = self.extractor.replace_refs_with_edges(
            text=text,
            law_name="会社法",
            source_law_id="417AC0000000086",
            source_node_id="JPLAW:417AC0000000086#main#943"
        )

        assert len(edges) == 1
        edge = edges[0]
        # law_name は純粋な "農業協同組合法" であること
        assert edge["to"] == "external:農業協同組合法#main#97_4"
        assert "この節の規定若しくは" not in edge["to"]

    def test_edge_required_fields(self):
        """
        external edge の必須フィールドを確認
        """
        text = "弁護士法（昭和二十四年法律第二百五号）第三十条の二十八において"
        _, edges = self.extractor.replace_refs_with_edges(
            text=text,
            law_name="会社法",
            source_law_id="417AC0000000086",
            source_node_id="JPLAW:417AC0000000086#main#943"
        )

        assert len(edges) == 1
        edge = edges[0]

        # 必須フィールド
        assert "from" in edge
        assert "to" in edge
        assert "type" in edge
        assert "evidence" in edge
        assert "confidence" in edge
        assert "source" in edge
        assert "kind" in edge

        # 値の検証
        assert edge["from"] == "JPLAW:417AC0000000086#main#943"
        assert edge["to"].startswith("external:")
        assert edge["type"] == "refers_to"
        assert edge["kind"] == "external_ref"


class TestExternalLawWithLawNumber:
    """
    「法令名（法令番号）第N条」パターンの外部法参照テスト

    会社法第943条で問題となったケース:
    - 弁護士法（昭和二十四年法律第二百五号）第三十条の二十八
    - 司法書士法（昭和二十五年法律第百九十七号）第四十五条の二

    これらは外部法令への参照であり、会社法の条文としてリンクしてはならない。
    Vaultに存在しない場合は external edge のみ生成する。
    """

    def setup_method(self):
        self.extractor = EdgeExtractor()

    def test_external_law_with_law_number_not_linked(self):
        """
        「法令名（法令番号）第N条」はVaultに存在しない場合リンク化しない

        入力: 弁護士法（昭和二十四年法律第二百五号）第三十条の二十八第六項
        期待: 第三十条の二十八 はリンク化されない（external edgeのみ）
        """
        text = "弁護士法（昭和二十四年法律第二百五号）第三十条の二十八第六項において"
        result = self.extractor.replace_refs(text, "会社法")

        # 外部法参照なのでリンク化されてはならない
        assert "[[laws/会社法" not in result
        assert "[[laws/弁護士法" not in result  # Vaultに存在しないのでリンクなし
        assert "第三十条の二十八" in result  # プレーンテキストのまま

    def test_external_law_司法書士法(self):
        """司法書士法への参照もリンク化しない（Vaultに存在しないため）"""
        text = "司法書士法（昭和二十五年法律第百九十七号）第四十五条の二第六項"
        result = self.extractor.replace_refs(text, "会社法")

        assert "[[laws/会社法" not in result
        assert "[[laws/司法書士法" not in result

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


class TestExternalLawExternalEdge:
    """
    Vaultに存在しない外部法令への参照で external edge が生成されることをテスト
    """

    def setup_method(self):
        # Vault root を設定（実際のVaultパスを使用）
        vault_root = Path(__file__).parent.parent / "Vault"
        set_vault_root(vault_root)
        self.extractor = EdgeExtractor(vault_root=vault_root)

    def test_external_edge_generated_for_non_vault_law(self):
        """
        Vaultに存在しない法令への参照で external edge が生成される

        入力: 弁護士法（昭和二十四年法律第二百五号）第三十条の二十八
        期待: to = "external:弁護士法#main#30_28" の edge が生成される
        """
        text = "弁護士法（昭和二十四年法律第二百五号）第三十条の二十八第六項において"
        result, edges = self.extractor.replace_refs_with_edges(
            text=text,
            law_name="会社法",
            source_law_id="417AC0000000086",
            source_node_id="JPLAW:417AC0000000086#main#943"
        )

        # リンク化されない
        assert "[[" not in result

        # external edge が生成される
        assert len(edges) == 1
        edge = edges[0]
        assert edge["to"] == "external:弁護士法#main#30_28"
        assert edge["type"] == "refers_to"
        assert edge["kind"] == "external_ref"
        assert "第三十条の二十八" in edge["evidence"]

    def test_external_edge_multiple_laws(self):
        """
        複数の外部法令参照で複数の external edge が生成される
        """
        text = (
            "弁護士法（昭和二十四年法律第二百五号）第三十条の二十八第六項、"
            "司法書士法（昭和二十五年法律第百九十七号）第四十五条の二第六項において"
        )
        result, edges = self.extractor.replace_refs_with_edges(
            text=text,
            law_name="会社法",
            source_law_id="417AC0000000086",
            source_node_id="JPLAW:417AC0000000086#main#943"
        )

        # 2つの external edge が生成される
        assert len(edges) == 2

        # 弁護士法への参照
        bengoshi_edge = [e for e in edges if "弁護士法" in e["to"]][0]
        assert bengoshi_edge["to"] == "external:弁護士法#main#30_28"
        assert bengoshi_edge["kind"] == "external_ref"

        # 司法書士法への参照
        shihoshoshi_edge = [e for e in edges if "司法書士法" in e["to"]][0]
        assert shihoshoshi_edge["to"] == "external:司法書士法#main#45_2"
        assert shihoshoshi_edge["kind"] == "external_ref"


class TestExternalLawInVault:
    """
    Vaultに存在する外部法令への参照でクロスリンクが生成されることをテスト

    「法令名（法令番号）第N条」パターンでも、対象法令がVaultに存在すれば
    正しいクロスリンクを生成する。
    """

    def setup_method(self):
        # Vault root を設定（実際のVaultパスを使用）
        vault_root = Path(__file__).parent.parent / "Vault"
        set_vault_root(vault_root)
        self.extractor = EdgeExtractor(vault_root=vault_root)

    def test_vault_law_with_law_number_linked(self):
        """
        Vaultに存在する法令（民法）への参照は法令番号付きでもリンク化される

        入力: 民法（明治二十九年法律第八十九号）第九十三条
        期待: [[laws/民法/本文/第93条.md|第九十三条]] へリンク
        """
        text = "民法（明治二十九年法律第八十九号）第九十三条の規定を準用する"
        result = self.extractor.replace_refs(text, "会社法")

        # 民法へのクロスリンクが生成される
        assert "[[laws/民法/本文/第93条.md|第九十三条]]" in result
        # 会社法へのリンクはない
        assert "[[laws/会社法" not in result

    def test_vault_law_with_law_number_edge(self):
        """
        Vaultに存在する法令への参照で通常のクロスリンクedgeが生成される
        """
        text = "民法（明治二十九年法律第八十九号）第九十三条の規定を準用する"
        result, edges = self.extractor.replace_refs_with_edges(
            text=text,
            law_name="会社法",
            source_law_id="417AC0000000086",
            source_node_id="JPLAW:417AC0000000086#main#774"
        )

        # クロスリンクが生成される
        assert "[[laws/民法/本文/第93条.md|第九十三条]]" in result

        # 通常の edge が生成される（external ではない）
        assert len(edges) == 1
        edge = edges[0]
        assert edge["to"].startswith("JPLAW:")  # external: ではない
        assert "129AC0000000089" in edge["to"]  # 民法の law_id
        assert "kind" not in edge or edge.get("kind") != "external_ref"


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

    def test_self_law_with_law_number_not_crosslinked(self):
        """
        自法令への参照（法令番号付き）は自法令へリンク

        会社法内で「会社法（...）第N条」が出ても、それは会社法自身への参照。
        """
        text = "会社法（平成十七年法律第八十六号）第九百五十五条の規定"
        result = self.extractor.replace_refs(text, "会社法")

        # 会社法自身へリンク
        assert "[[laws/会社法/本文/第955条.md|第九百五十五条]]" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
