#!/usr/bin/env python3
"""
動的法令名レジストリのテスト

テスト対象:
1. レジストリの読み込み・正規化・キャッシュ
2. 法令名検出ヘルパー (find_law_name_before_dai, find_dynamic_law_in_sentence)
3. 自法/外部法判定 (_is_self_law)
4. CrossLinkResult データクラス
5. 抑制動作（許可リスト外の外部法令 → プレーンテキスト）
6. クロスリンク許可（CROSS_LINKABLE_LAWS → リンク生成）
"""

import json
import re
from pathlib import Path

import pytest

from legalkg.core.tier2 import (
    CrossLinkResult,
    EdgeExtractor,
    _normalize_law_name,
    _is_self_law,
    find_law_name_before_dai,
    find_dynamic_law_in_sentence,
    load_law_name_registry,
    get_law_name_registry,
    get_law_name_registry_set,
    get_normalized_cross_linkable,
    clear_vault_caches,
    set_vault_root,
    CROSS_LINKABLE_LAWS,
)


def _assert_not_wikilinked(result: str, article_text: str):
    """article_text が wikilink 化されていないことを確認"""
    pattern = rf"\[\[[^\]]*\|{re.escape(article_text)}\]\]"
    assert re.search(pattern, result) is None, (
        f"'{article_text}' should not be wikilinked, but found in: {result}"
    )


def _assert_wikilinked(result: str, article_text: str):
    """article_text が wikilink 化されていることを確認"""
    pattern = rf"\[\[[^\]]*\|{re.escape(article_text)}\]\]"
    assert re.search(pattern, result) is not None, (
        f"'{article_text}' should be wikilinked, but not found in: {result}"
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mini_vault(tmp_path):
    """
    最小限のテスト用 Vault を作成

    法令:
    - 銀行法 (GINKOU001) — 許可リスト外
    - 信託業法 (SHINTAKU001, alias: 信託法) — 許可リスト外
    - 破産法 (HASAN001) — 許可リスト外
    - 民法 (129AC0000000089) — 許可リスト内
    - 刑法 (140AC0000000045) — 許可リスト内
    - 水産業協同組合法 (323AC0000000242) — source law for suppression tests
    - テスト法 (TEST_SELF_001)
    """
    laws = [
        {"law_id": "GINKOU001", "official_title": "銀行法", "aliases": ["銀行法"]},
        {"law_id": "SHINTAKU001", "official_title": "信託業法", "aliases": ["信託業法", "信託法"]},
        {"law_id": "HASAN001", "official_title": "破産法", "aliases": ["破産法"]},
        {"law_id": "129AC0000000089", "official_title": "民法", "aliases": ["民法"]},
        {"law_id": "140AC0000000045", "official_title": "刑法", "aliases": ["刑法", "旧刑法"]},
        {"law_id": "323AC0000000242", "official_title": "水産業協同組合法", "aliases": ["水産業協同組合法"]},
        {"law_id": "TEST_SELF_001", "official_title": "テスト法", "aliases": ["テスト法", "テスト特別法"]},
    ]

    index_dir = tmp_path / "_index"
    index_dir.mkdir()
    with open(index_dir / "laws.json", 'w', encoding='utf-8') as f:
        json.dump({"laws": laws}, f, ensure_ascii=False)

    # 法令ディレクトリ + ダミー条文ファイル
    for law in laws:
        honbun_dir = tmp_path / "laws" / law["law_id"] / "本文"
        honbun_dir.mkdir(parents=True)
        # 刑法に第199条を用意（クロスリンクテスト用）
        if law["law_id"] == "140AC0000000045":
            (honbun_dir / "第199条.md").write_text("dummy", encoding="utf-8")
        # 民法に第93条を用意
        if law["law_id"] == "129AC0000000089":
            (honbun_dir / "第93条.md").write_text("dummy", encoding="utf-8")
        # 各法令に第1条・第2条を用意
        (honbun_dir / "第1条.md").write_text("dummy", encoding="utf-8")
        (honbun_dir / "第2条.md").write_text("dummy", encoding="utf-8")
        (honbun_dir / "第3条.md").write_text("dummy", encoding="utf-8")

    yield tmp_path

    clear_vault_caches()


@pytest.fixture
def loaded_registry(mini_vault):
    """mini_vault のレジストリをロード済みの状態"""
    clear_vault_caches()
    set_vault_root(mini_vault)
    yield mini_vault
    clear_vault_caches()


# =============================================================================
# CrossLinkResult データクラス
# =============================================================================


class TestCrossLinkResult:

    def test_default_values(self):
        result = CrossLinkResult()
        assert result.target is None
        assert result.suppress is False

    def test_target_only(self):
        result = CrossLinkResult(target="刑法")
        assert result.target == "刑法"
        assert result.suppress is False

    def test_suppress_only(self):
        result = CrossLinkResult(suppress=True)
        assert result.target is None
        assert result.suppress is True


# =============================================================================
# 正規化関数
# =============================================================================


class TestNormalizeLawName:

    def test_basic(self):
        assert _normalize_law_name("銀行法") == "銀行法"

    def test_nfkc(self):
        assert _normalize_law_name("ＡＢＣ法") == "ABC法"

    def test_whitespace_removal(self):
        assert _normalize_law_name("銀行 法") == "銀行法"
        assert _normalize_law_name("銀行\u3000法") == "銀行法"

    def test_empty(self):
        assert _normalize_law_name("") == ""


# =============================================================================
# レジストリの読み込み・キャッシュ
# =============================================================================


class TestLoadLawNameRegistry:

    def test_load_from_mini_vault(self, loaded_registry):
        registry = get_law_name_registry()
        registry_set = get_law_name_registry_set()

        assert len(registry) > 0
        assert len(registry_set) > 0
        assert "銀行法" in registry_set
        assert "GINKOU001" in registry["銀行法"]

    def test_aliases_registered(self, loaded_registry):
        registry = get_law_name_registry()
        assert "信託法" in get_law_name_registry_set()
        assert "SHINTAKU001" in registry["信託法"]

    def test_collision_handling(self, loaded_registry):
        registry = get_law_name_registry()
        assert "テスト法" in registry
        assert "TEST_SELF_001" in registry["テスト法"]

    def test_empty_vault_root(self):
        clear_vault_caches()
        set_vault_root(None)
        assert get_law_name_registry() == {}
        assert get_law_name_registry_set() == set()
        clear_vault_caches()

    def test_missing_index(self, tmp_path):
        clear_vault_caches()
        load_law_name_registry(tmp_path)
        assert get_law_name_registry() == {}
        clear_vault_caches()


# =============================================================================
# 自法/外部法判定
# =============================================================================


class TestIsSelfLaw:

    def test_self_law_detected(self, loaded_registry):
        registry = get_law_name_registry()
        assert _is_self_law("銀行法", "GINKOU001", registry) is True

    def test_external_law_detected(self, loaded_registry):
        registry = get_law_name_registry()
        assert _is_self_law("銀行法", "129AC0000000089", registry) is False

    def test_alias_as_self(self, loaded_registry):
        registry = get_law_name_registry()
        assert _is_self_law("信託法", "SHINTAKU001", registry) is True

    def test_unknown_law_name(self, loaded_registry):
        registry = get_law_name_registry()
        assert _is_self_law("存在しない法", "ANYTHING", registry) is False


# =============================================================================
# 法令名検出ヘルパー
# =============================================================================


class TestFindLawNameBeforeDai:

    def test_basic_detection(self, loaded_registry):
        registry_set = get_law_name_registry_set()
        assert find_law_name_before_dai("銀行法", registry_set) == "銀行法"

    def test_with_preceding_text(self, loaded_registry):
        registry_set = get_law_name_registry_set()
        assert find_law_name_before_dai("この場合における銀行法", registry_set) == "銀行法"

    def test_parenthetical_pattern(self, loaded_registry):
        registry_set = get_law_name_registry_set()
        result = find_law_name_before_dai("銀行法（昭和五十六年法律第五十九号）", registry_set)
        assert result == "銀行法"

    def test_no_match(self, loaded_registry):
        registry_set = get_law_name_registry_set()
        assert find_law_name_before_dai("方法", registry_set) is None

    def test_no_law_suffix(self, loaded_registry):
        registry_set = get_law_name_registry_set()
        assert find_law_name_before_dai("手続", registry_set) is None

    def test_empty_context(self, loaded_registry):
        registry_set = get_law_name_registry_set()
        assert find_law_name_before_dai("", registry_set) is None

    def test_empty_registry(self):
        assert find_law_name_before_dai("銀行法", set()) is None


class TestFindDynamicLawInSentence:

    def test_single_law(self, loaded_registry):
        registry_set = get_law_name_registry_set()
        results = find_dynamic_law_in_sentence("銀行法第二条の規定", registry_set)
        assert len(results) == 1
        assert results[0][1] == "銀行法"

    def test_multiple_laws(self, loaded_registry):
        registry_set = get_law_name_registry_set()
        results = find_dynamic_law_in_sentence("銀行法第二条及び信託業法第三条", registry_set)
        assert len(results) == 2

    def test_no_match(self, loaded_registry):
        registry_set = get_law_name_registry_set()
        results = find_dynamic_law_in_sentence("この規定を準用する", registry_set)
        assert len(results) == 0

    def test_empty_registry(self):
        results = find_dynamic_law_in_sentence("銀行法第二条", set())
        assert len(results) == 0


# =============================================================================
# 抑制動作テスト（mini_vault 完結）
# =============================================================================


class TestSuppression:
    """
    許可リスト外の外部法令参照が抑制されることを確認。

    すべて mini_vault で完結（実 Vault 不要）。
    """

    @pytest.fixture(autouse=True)
    def setup(self, loaded_registry):
        self.extractor = EdgeExtractor(vault_root=loaded_registry)

    def test_ginkou_suppressed(self):
        """銀行法第二条 → プレーンテキスト（許可リスト外）"""
        text = "銀行法第二条の規定に基づき"
        result, edges = self.extractor.replace_refs_with_edges(
            text=text, law_name="水産業協同組合法",
            source_law_id="323AC0000000242",
            source_node_id="JPLAW:323AC0000000242#main#87_2",
            is_amendment_fragment=False
        )
        _assert_not_wikilinked(result, "第二条")
        assert len(edges) == 0

    def test_shintaku_suppressed(self):
        """信託業法第二条 → プレーンテキスト（許可リスト外）"""
        text = "信託業法第二条の規定"
        result, edges = self.extractor.replace_refs_with_edges(
            text=text, law_name="水産業協同組合法",
            source_law_id="323AC0000000242",
            source_node_id="JPLAW:323AC0000000242#main#87_2",
            is_amendment_fragment=False
        )
        _assert_not_wikilinked(result, "第二条")
        assert len(edges) == 0

    def test_parenthetical_suppressed(self):
        """銀行法（昭和...号）第二条 → プレーンテキスト"""
        text = "銀行法（昭和五十六年法律第五十九号）第二条の規定"
        result, edges = self.extractor.replace_refs_with_edges(
            text=text, law_name="水産業協同組合法",
            source_law_id="323AC0000000242",
            source_node_id="JPLAW:323AC0000000242#main#87_2",
            is_amendment_fragment=False
        )
        _assert_not_wikilinked(result, "第二条")
        assert len(edges) == 0

    def test_scope_continuation_suppressed(self):
        """許可リスト外の外部法令スコープ継続 → 後続の裸参照も抑制"""
        text = "破産法第一条、第二条の規定"
        assert "破産法" not in CROSS_LINKABLE_LAWS
        result, edges = self.extractor.replace_refs_with_edges(
            text=text, law_name="民法",
            source_law_id="129AC0000000089",
            source_node_id="JPLAW:129AC0000000089#main#10",
            is_amendment_fragment=False
        )
        _assert_not_wikilinked(result, "第二条")
        assert len(edges) == 0


# =============================================================================
# クロスリンク許可テスト（mini_vault 完結）
# =============================================================================


class TestCrossLinkAllowed:
    """CROSS_LINKABLE_LAWS の法令は引き続きリンク生成される。"""

    @pytest.fixture(autouse=True)
    def setup(self, loaded_registry):
        self.extractor = EdgeExtractor(vault_root=loaded_registry)

    def test_keiho_linked(self):
        """刑法第百九十九条 → リンク生成"""
        assert "刑法" in CROSS_LINKABLE_LAWS
        text = "刑法第百九十九条の規定"
        result, edges = self.extractor.replace_refs_with_edges(
            text=text, law_name="民法",
            source_law_id="129AC0000000089",
            source_node_id="JPLAW:129AC0000000089#main#10",
            is_amendment_fragment=False
        )
        _assert_wikilinked(result, "第百九十九条")
        assert len(edges) == 1
        assert "140AC0000000045" in edges[0]["to"]

    def test_minpo_with_law_number_linked(self):
        """民法（法令番号）第九十三条 → 許可リスト内 → リンク生成"""
        assert "民法" in CROSS_LINKABLE_LAWS
        text = "民法（明治二十九年法律第八十九号）第九十三条の規定"
        result, edges = self.extractor.replace_refs_with_edges(
            text=text, law_name="テスト法",
            source_law_id="TEST_SELF_001",
            source_node_id="JPLAW:TEST_SELF_001#main#1",
            is_amendment_fragment=False
        )
        _assert_wikilinked(result, "第九十三条")
        assert len(edges) == 1
        assert "129AC0000000089" in edges[0]["to"]

    def test_self_law_not_suppressed(self):
        """自法令への裸参照は抑制されない"""
        text = "第一条の規定"
        result, edges = self.extractor.replace_refs_with_edges(
            text=text, law_name="民法",
            source_law_id="129AC0000000089",
            source_node_id="JPLAW:129AC0000000089#main#10",
            is_amendment_fragment=False
        )
        _assert_wikilinked(result, "第一条")


# =============================================================================
# get_normalized_cross_linkable テスト
# =============================================================================


class TestNormalizedCrossLinkable:

    def test_keys_are_normalized(self):
        ncl = get_normalized_cross_linkable()
        for key in ncl:
            assert key == _normalize_law_name(key)

    def test_contains_expected_laws(self):
        ncl = get_normalized_cross_linkable()
        assert "刑法" in ncl
        assert "民法" in ncl
        assert "会社法" in ncl

    def test_aliases_included(self):
        ncl = get_normalized_cross_linkable()
        if "旧刑法" in CROSS_LINKABLE_LAWS:
            assert "旧刑法" in ncl
            assert ncl["旧刑法"] == "刑法"
