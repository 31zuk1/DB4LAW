#!/usr/bin/env python3
"""
DB4LAW: 改正法断片のリンクバグ再現テスト

民事訴訟法/附則/令和五年五月一七日法律第二八号/令和五年五月一七日法律第二八号_第1条.md
で発見された複数のバグを再現し、修正後のリグレッションを防止する。

バグ1: 改正法断片でクロスリンクスコープが裸参照に適用される
バグ2: 外部法令がクロスリンクスコープを無効化しない
バグ3: 未定義法令名（刑法等一部改正法）後の参照が誤リンクされる
バグ4: 「附則第N条」が本文へリンクされる
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from legalkg.core.tier2 import EdgeExtractor, set_vault_root


class TestAmendmentFragmentCrossLinkScopeBug:
    """
    バグ1: 改正法断片でクロスリンクスコープが裸参照に適用される

    問題: 改正法断片内で、文中に「刑事訴訟法第344条」があると、
    後続の裸の「第二条」も刑事訴訟法へリンクされてしまう。

    正しい動作: 改正法断片内では、法令名が直接付いていない裸参照は
    リンク化しない（改正法自身の条文番号への参照の可能性があるため）。
    """

    def setup_method(self):
        vault_root = Path(__file__).parent.parent / "Vault"
        set_vault_root(vault_root)
        self.extractor = EdgeExtractor(vault_root=vault_root)

    def test_bare_ref_after_crosslink_not_linked(self):
        """
        改正法断片: 「刑事訴訟法第344条...第二条中刑法」の「第二条」はリンク化しない

        文脈: 改正法の条項構成を説明するテキスト
        - 「第一条中刑事訴訟法第344条」= 刑事訴訟法第344条は刑事訴訟法へリンク（明示法令名）
        - 「第二条中刑法」= 第二条は改正法自身の第二条なのでリンク化しない
        """
        text = "第一条中刑事訴訟法第三百四十四条に一項を加える改正規定、第二条中刑法"
        result = self.extractor.replace_refs(text, "民事訴訟法", is_amendment_fragment=True)

        # 「刑事訴訟法第344条」は刑事訴訟法へリンクされる
        assert "[[laws/刑事訴訟法/本文/第344条.md|第三百四十四条]]" in result

        # 「第二条」は裸参照なのでリンク化されない
        assert "[[laws/刑事訴訟法/本文/第2条.md|第二条]]" not in result
        # 刑法へもリンクされない
        assert "[[laws/刑法/本文/第2条.md|第二条]]" not in result

    def test_multiple_bare_refs_not_linked(self):
        """
        改正法断片: 複数の裸参照がある場合、すべてリンク化しない
        """
        text = "第一条及び第二条並びに第三条の規定"
        result = self.extractor.replace_refs(text, "民事訴訟法", is_amendment_fragment=True)

        # すべてリンク化されない
        assert "[[" not in result


class TestExternalLawInvalidatesScopeBug:
    """
    バグ2: 外部法令がクロスリンクスコープを無効化しない

    問題: 文中に「刑法第97条...出入国管理及び難民認定法第72条」があると、
    「第72条」が刑法へリンクされてしまう。

    正しい動作: 出入国管理及び難民認定法はVaultに存在しないので、
    「出入国管理及び難民認定法第72条」はリンク化しない。
    また、直前の「刑法」スコープは無効化される。
    """

    def setup_method(self):
        vault_root = Path(__file__).parent.parent / "Vault"
        set_vault_root(vault_root)
        self.extractor = EdgeExtractor(vault_root=vault_root)

    def test_external_law_ref_not_linked_to_wrong_target(self):
        """
        「出入国管理及び難民認定法第72条」は刑法へリンクされない

        Context: 第三条中出入国管理及び難民認定法第七十二条
        - 「出入国管理及び難民認定法」は EXTERNAL_LAW_PATTERNS に含まれる
        - Vault に存在しないので、リンク化しない
        """
        text = "第三条中出入国管理及び難民認定法第七十二条の改正規定"
        result = self.extractor.replace_refs(text, "民事訴訟法", is_amendment_fragment=True)

        # 刑法へリンクされてはならない
        assert "[[laws/刑法/本文/第72条.md" not in result
        # 出入国管理及び難民認定法はVaultに存在しないのでリンクなし
        assert "[[laws/出入国管理及び難民認定法" not in result
        # 第72条はプレーンテキストのまま
        assert "第七十二条" in result

    def test_external_law_after_crosslink_invalidates_scope(self):
        """
        刑法スコープ後に外部法令が来た場合、外部法令への参照はリンクしない

        Context: 刑法第97条...出入国管理及び難民認定法第72条
        - 「刑法第97条」は刑法へリンク（明示法令名）
        - 「出入国管理及び難民認定法第72条」はリンク化しない（外部法、Vault非存在）
        """
        text = "刑法第九十七条及び出入国管理及び難民認定法第七十二条の改正規定"
        result = self.extractor.replace_refs(text, "民事訴訟法", is_amendment_fragment=True)

        # 「刑法第97条」は刑法へリンクされる
        assert "[[laws/刑法/本文/第97条.md|第九十七条]]" in result

        # 「第72条」は刑法へリンクされてはならない
        assert "[[laws/刑法/本文/第72条.md" not in result


class TestUndefinedLawNameBug:
    """
    バグ3: 未定義法令名（刑法等一部改正法）後の参照が誤リンクされる

    問題: 「刑法等一部改正法第11条」の「第11条」が刑事訴訟法へリンクされる。
    「刑法等一部改正法」はCROSS_LINKABLE_LAWSにもEXTERNAL_LAW_PATTERNSにもないため、
    文中の他の法令（刑事訴訟法）のスコープが誤って適用される。

    正しい動作: 「刑法等一部改正法」は定義されていないが、法令名として認識し、
    後続の「第11条」はリンク化しない。
    """

    def setup_method(self):
        vault_root = Path(__file__).parent.parent / "Vault"
        set_vault_root(vault_root)
        self.extractor = EdgeExtractor(vault_root=vault_root)

    def test_undefined_law_ref_not_linked(self):
        """
        「刑法等一部改正法第11条」はリンク化しない

        「刑法等一部改正法」は:
        - CROSS_LINKABLE_LAWS に含まれない
        - EXTERNAL_LAW_PATTERNS に含まれない
        - しかし「法」で終わる法令名パターン

        → 既存の法令へリンクしてはならない
        """
        text = "刑法等一部改正法第十一条中少年鑑別所法第百三十二条の改正規定"
        result = self.extractor.replace_refs(text, "民事訴訟法", is_amendment_fragment=True)

        # 「第11条」は刑事訴訟法へリンクされてはならない
        assert "[[laws/刑事訴訟法/本文/第11条.md|第十一条]]" not in result
        # 刑法へもリンクされてはならない
        assert "[[laws/刑法/本文/第11条.md|第十一条]]" not in result

        # 「少年鑑別所法第132条」もリンク化しない（Vault非存在）
        assert "[[" not in result


class TestSupplementPrefixBug:
    """
    バグ4: 「附則第N条」が本文へリンクされる

    問題: 「附則第36条」が「[[laws/刑事訴訟法/本文/第36条.md|第三十六条]]」
    にリンクされてしまう。

    正しい動作: 「附則」プレフィックスがある参照は附則条文への参照であり、
    本文（本則）へリンクしてはならない。改正法断片内では附則も改正法自身の
    附則を指すのでリンク化しない。
    """

    def setup_method(self):
        vault_root = Path(__file__).parent.parent / "Vault"
        set_vault_root(vault_root)
        self.extractor = EdgeExtractor(vault_root=vault_root)

    def test_fuzoku_ref_not_linked_to_honbun(self):
        """
        「附則第36条」は本文へリンクされない

        Context: 附則第三十六条及び第四十条の規定
        - 「附則第36条」は附則条文への参照
        - 本文/第36条.md へリンクしてはならない
        """
        text = "附則第三十六条及び第四十条の規定"
        result = self.extractor.replace_refs(text, "民事訴訟法", is_amendment_fragment=True)

        # 本文へのリンクは生成されない
        assert "[[laws/民事訴訟法/本文/第36条.md" not in result
        assert "[[laws/民事訴訟法/本文/第40条.md" not in result
        assert "[[laws/刑事訴訟法/本文/第36条.md" not in result
        assert "[[laws/刑事訴訟法/本文/第40条.md" not in result

    def test_fuzoku_ref_with_law_name_also_not_linked(self):
        """
        「民法附則第5条」も本文へリンクされない
        """
        text = "民法附則第五条の規定"
        result = self.extractor.replace_refs(text, "民事訴訟法", is_amendment_fragment=True)

        # 本文へのリンクは生成されない
        assert "[[laws/民法/本文/第5条.md" not in result

    def test_fuzoku_compound_pattern(self):
        """
        「附則第5条第1項及び第2項」も本文へリンクされない
        """
        text = "附則第五条第一項及び第二項の規定"
        result = self.extractor.replace_refs(text, "民事訴訟法", is_amendment_fragment=True)

        # 本文へのリンクは生成されない
        assert "[[" not in result

    def test_fuzoku_enumeration_pattern(self):
        """
        「附則第9条及び第10条」の列挙パターン

        Context: 附則第九条及び第十条の規定
        - 「第九条」も「第十条」も附則条文への参照
        - どちらも本文へリンクされてはならない
        """
        text = "附則第九条及び第十条第一項の規定"
        result = self.extractor.replace_refs(text, "刑法", is_amendment_fragment=True)

        # 本文へのリンクは生成されない
        assert "[[laws/刑法/本文/第9条.md" not in result
        assert "[[laws/刑法/本文/第10条.md" not in result
        assert "[[" not in result

    def test_fuzoku_enumeration_with_wikilink(self):
        """
        既にWikiLink化された附則参照の後の列挙

        Context: 附則[[...]]及び第十条
        - WikiLinkを除去してチェック
        """
        # シミュレート: 第九条が先に処理されてWikiLinkになっている場合
        # （実際には附則第九条はリンク化されないが、テスト用）
        text = "附則第九条及び第十条"
        result = self.extractor.replace_refs(text, "刑法", is_amendment_fragment=True)

        # 本文へのリンクは生成されない
        assert "[[" not in result


class TestCombinedScenario:
    """
    実際の民事訴訟法附則第1条のパターンを再現するテスト
    """

    def setup_method(self):
        vault_root = Path(__file__).parent.parent / "Vault"
        set_vault_root(vault_root)
        self.extractor = EdgeExtractor(vault_root=vault_root)

    def test_minjisocho_fuzoku_article1_pattern(self):
        """
        民事訴訟法附則第1条の実際のパターン（簡略版）

        正しいリンク化:
        - 「刑事訴訟法第三百四十四条」→ 刑事訴訟法へ（明示法令名）
        - 「第二条」→ リンク化しない（改正法自身の条文）
        - 「刑法第九十七条」→ 刑法へ（明示法令名）
        - 「出入国管理及び難民認定法第七十二条」→ リンク化しない（外部法）
        - 「附則第三十六条」→ リンク化しない（附則参照）
        """
        text = (
            "第一条中刑事訴訟法第三百四十四条に一項を加える改正規定、"
            "第二条中刑法第九十七条及び第九十八条の改正規定並びに"
            "第三条中出入国管理及び難民認定法第七十二条の改正規定"
            "並びに附則第三十六条の規定"
        )
        result = self.extractor.replace_refs(text, "民事訴訟法", is_amendment_fragment=True)

        # 正しくリンク化される参照
        assert "[[laws/刑事訴訟法/本文/第344条.md|第三百四十四条]]" in result
        assert "[[laws/刑法/本文/第97条.md|第九十七条]]" in result
        assert "[[laws/刑法/本文/第98条.md|第九十八条]]" in result

        # リンク化されてはならない参照
        # 「第二条」は改正法自身の条文なのでリンク化しない
        assert "[[laws/刑事訴訟法/本文/第2条.md|第二条]]" not in result
        assert "[[laws/刑法/本文/第2条.md|第二条]]" not in result

        # 「第三条」は改正法自身の条文なのでリンク化しない
        assert "[[laws/民事訴訟法/本文/第3条.md|第三条]]" not in result
        assert "[[laws/刑法/本文/第3条.md|第三条]]" not in result

        # 「出入国管理及び難民認定法第72条」は外部法なのでリンク化しない
        assert "[[laws/刑法/本文/第72条.md|第七十二条]]" not in result

        # 「附則第36条」は附則参照なのでリンク化しない
        assert "[[laws/民事訴訟法/本文/第36条.md" not in result

    def test_kaisei_mae_ato_pattern(self):
        """
        「令和四年改正前刑法第十三条」のパターン

        リグレッション防止テスト:
        - 「改正前刑法」「改正後刑法」のように改正前後の法令への参照は
          明示的な法令名参照としてリンク化される
        """
        text = "令和四年改正前刑法第十三条の規定"
        result = self.extractor.replace_refs(text, "刑法", is_amendment_fragment=True)

        # 「刑法第13条」は刑法へリンクされる（改正前刑法は刑法への参照）
        assert "[[laws/刑法/本文/第13条.md|第十三条]]" in result

    def test_kaisei_ato_pattern(self):
        """
        「改正後民法」のパターン
        """
        text = "改正後民法第百条の規定"
        result = self.extractor.replace_refs(text, "刑法", is_amendment_fragment=True)

        # 「民法第100条」は民法へリンクされる
        assert "[[laws/民法/本文/第100条.md|第百条]]" in result

    def test_shin_kaishaho_enumeration(self):
        """
        「新会社法第244条第三項、第244条の二」の列挙パターン

        改正法断片内で「新会社法」に続く列挙された条文参照は
        すべて会社法へリンクされる。
        """
        text = "新会社法第二百四十四条第三項、第二百四十四条の二の規定"
        result = self.extractor.replace_refs(text, "会社法", is_amendment_fragment=True)

        # 「第244条」は会社法へリンク
        assert "[[laws/会社法/本文/第244条.md|第二百四十四条]]" in result
        # 列挙された「第244条の2」も会社法へリンク
        assert "[[laws/会社法/本文/第244条の2.md|第二百四十四条の二]]" in result

    def test_shin_kaishaho_multiple_enumeration(self):
        """
        「新会社法第244条第三項、第244条の二、第282条第二項及び第三項、第286条の二」

        複数の条文が列挙されている場合もすべてリンク化される。
        """
        text = "新会社法第二百四十四条第三項、第二百四十四条の二、第二百八十二条第二項及び第二百八十六条の二の規定"
        result = self.extractor.replace_refs(text, "会社法", is_amendment_fragment=True)

        # すべて会社法へリンク
        assert "[[laws/会社法/本文/第244条.md|第二百四十四条]]" in result
        assert "[[laws/会社法/本文/第244条の2.md|第二百四十四条の二]]" in result
        assert "[[laws/会社法/本文/第282条.md|第二百八十二条]]" in result
        assert "[[laws/会社法/本文/第286条の2.md|第二百八十六条の二]]" in result


class TestAmendmentLawSelfReference:
    """
    バグ5: 「第N条中{法令名}」パターンで改正法自身の条文がリンク化される

    問題: 施行期日条項などで「第一条中刑事訴訟法第三百四十四条」のようなテキストがある場合、
    「第一条」が親法（例: 刑法）へリンクされてしまう。

    正しい動作: 「第N条中{法令名}」パターンでは、第N条は改正法自身の条文番号を指すため、
    リンク化しない（ただし「刑事訴訟法第三百四十四条」は正しくリンク化する）。
    """

    def setup_method(self):
        vault_root = Path(__file__).parent.parent / "Vault"
        set_vault_root(vault_root)
        self.extractor = EdgeExtractor(vault_root=vault_root)

    def test_article_naka_pattern_not_linked(self):
        """
        「第一条中刑事訴訟法」の「第一条」はリンク化しない

        Context: 公布の日第一条中刑事訴訟法第三百四十四条に一項を加える改正規定
        - 「第一条」= 改正法の第一条（刑事訴訟法を改正する条文）
        - 「第三百四十四条」= 刑事訴訟法の第344条（正しくリンク化）
        """
        text = "公布の日第一条中刑事訴訟法第三百四十四条に一項を加える改正規定"
        result = self.extractor.replace_refs(text, "刑法", is_amendment_fragment=True)

        # 「第一条」は改正法自身の条文なのでリンク化されない
        assert "[[laws/刑法/本文/第1条.md|第一条]]" not in result
        assert "[[laws/刑事訴訟法/本文/第1条.md|第一条]]" not in result

        # 「刑事訴訟法第三百四十四条」は正しくリンク化される
        assert "[[laws/刑事訴訟法/本文/第344条.md|第三百四十四条]]" in result

    def test_multiple_naka_pattern_not_linked(self):
        """
        「第一条中...第二条中...第三条中」の複数パターン

        Context: 第一条中刑事訴訟法...第二条中刑法...第三条中出入国管理及び難民認定法
        - すべての「第N条」は改正法自身の条文
        """
        text = "第一条中刑事訴訟法第三百四十四条の改正規定、第二条中刑法第九十七条の改正規定並びに第三条中出入国管理及び難民認定法第七十二条の改正規定"
        result = self.extractor.replace_refs(text, "刑法", is_amendment_fragment=True)

        # すべての「第N条中」パターンはリンク化されない
        assert "[[laws/刑法/本文/第1条.md|第一条]]" not in result
        assert "[[laws/刑法/本文/第2条.md|第二条]]" not in result
        assert "[[laws/刑法/本文/第3条.md|第三条]]" not in result

        # クロスリンク可能な「刑事訴訟法第344条」「刑法第97条」はリンク化される
        assert "[[laws/刑事訴訟法/本文/第344条.md|第三百四十四条]]" in result
        assert "[[laws/刑法/本文/第97条.md|第九十七条]]" in result

        # Vaultに存在しない法令（出入国管理及び難民認定法）はリンク化されない
        assert "[[laws/出入国管理及び難民認定法" not in result

    def test_naka_pattern_with_law_prefix_linked(self):
        """
        「刑事訴訟法第一条中...」のように法令名が付いている場合はリンク化する
        """
        text = "刑事訴訟法第一条中の規定"
        result = self.extractor.replace_refs(text, "刑法", is_amendment_fragment=True)

        # 「刑事訴訟法第一条」は刑事訴訟法へリンク化される
        assert "[[laws/刑事訴訟法/本文/第1条.md|第一条]]" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
