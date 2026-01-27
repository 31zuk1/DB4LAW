"""
Test for Phase 3: Vault 実在ベース一般化

- EXTERNAL_LAW_PATTERNS 内の法令でも Vault に存在すればリンク化
- CROSS_LINKABLE_LAWS のエイリアス機能は維持
- Vault に存在しない法令はリンク化しない
"""
import pytest
from pathlib import Path
from legalkg.core.tier2 import (
    EdgeExtractor,
    set_vault_root,
    clear_vault_caches,
    law_exists_in_vault,
    get_vault_law_dirs,
    EXTERNAL_LAW_PATTERNS,
    CROSS_LINKABLE_LAWS,
)


class TestVaultCache:
    """Vault キャッシュのテスト"""

    @pytest.fixture(autouse=True)
    def setup(self):
        clear_vault_caches()
        yield
        clear_vault_caches()

    def test_get_vault_law_dirs_returns_set(self):
        """get_vault_law_dirs がセットを返す"""
        vault_root = Path('./Vault')
        set_vault_root(vault_root)
        dirs = get_vault_law_dirs(vault_root)
        assert isinstance(dirs, set)
        assert '刑法' in dirs
        assert '民法' in dirs
        assert '会社法' in dirs

    def test_cache_is_reused(self):
        """キャッシュが再利用される"""
        vault_root = Path('./Vault')
        dirs1 = get_vault_law_dirs(vault_root)
        dirs2 = get_vault_law_dirs(vault_root)
        assert dirs1 is dirs2  # 同一オブジェクト

    def test_law_exists_in_vault_uses_cache(self):
        """law_exists_in_vault がキャッシュを使用"""
        vault_root = Path('./Vault')
        # 存在する法令
        assert law_exists_in_vault('刑法', vault_root) is True
        assert law_exists_in_vault('民法', vault_root) is True
        # 存在しない法令
        assert law_exists_in_vault('存在しない法', vault_root) is False


class TestVaultBasedLinking:
    """Vault 実在ベースリンクのテスト"""

    @pytest.fixture(autouse=True)
    def setup(self):
        clear_vault_caches()
        set_vault_root(Path('./Vault'))
        yield
        clear_vault_caches()

    @pytest.fixture
    def extractor(self):
        return EdgeExtractor(vault_root=Path('./Vault'))

    def test_vault_existing_law_in_external_patterns_linked(self, extractor):
        """EXTERNAL_LAW_PATTERNS に含まれるが Vault に存在する法令はリンク化"""
        # 会社法は EXTERNAL_LAW_PATTERNS に含まれているが、Vault に存在する
        assert '会社法' in EXTERNAL_LAW_PATTERNS
        text = "会社法第一条の規定"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/会社法/本文/第1条.md|第一条]]" in result

    def test_vault_existing_law_enumeration_linked(self, extractor):
        """Vault に存在する法令の列挙もリンク化"""
        text = "会社法第一条、第二条、第三条を準用する"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/会社法/本文/第1条.md|第一条]]" in result
        assert "[[laws/会社法/本文/第2条.md|第二条]]" in result
        assert "[[laws/会社法/本文/第3条.md|第三条]]" in result

    def test_vault_nonexisting_law_not_linked(self, extractor):
        """Vault に存在しない法令はリンク化しない"""
        # 少年法は EXTERNAL_LAW_PATTERNS に含まれているが、Vault に存在しない
        assert '少年法' in EXTERNAL_LAW_PATTERNS
        text = "少年法第一条の規定"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[" not in result
        assert "第一条" in result


class TestAliasPreservation:
    """CROSS_LINKABLE_LAWS エイリアス維持のテスト"""

    @pytest.fixture(autouse=True)
    def setup(self):
        clear_vault_caches()
        set_vault_root(Path('./Vault'))
        yield
        clear_vault_caches()

    @pytest.fixture
    def extractor(self):
        return EdgeExtractor(vault_root=Path('./Vault'))

    def test_kyu_keiho_alias(self, extractor):
        """旧刑法 → 刑法 のエイリアスが機能"""
        assert CROSS_LINKABLE_LAWS.get('旧刑法') == '刑法'
        text = "旧刑法第百九十九条の規定"
        result = extractor.replace_refs(text, "テスト法")
        # 刑法へのリンクが生成される
        assert "[[laws/刑法/本文/第199条.md|第百九十九条]]" in result

    def test_kenpo_alias(self, extractor):
        """憲法 → 日本国憲法 のエイリアスが機能"""
        assert CROSS_LINKABLE_LAWS.get('憲法') == '日本国憲法'
        text = "憲法第九条の規定"
        result = extractor.replace_refs(text, "テスト法")
        # 日本国憲法へのリンクが生成される
        assert "[[laws/日本国憲法/本文/第9条.md|第九条]]" in result

    def test_shin_minpo_alias(self, extractor):
        """新民法 → 民法 のエイリアスが機能"""
        assert CROSS_LINKABLE_LAWS.get('新民法') == '民法'
        text = "新民法第七百九条の規定"
        result = extractor.replace_refs(text, "テスト法")
        assert "[[laws/民法/本文/第709条.md|第七百九条]]" in result


class TestVaultBasedEdges:
    """Vault 実在ベースのエッジ生成テスト"""

    @pytest.fixture(autouse=True)
    def setup(self):
        clear_vault_caches()
        set_vault_root(Path('./Vault'))
        yield
        clear_vault_caches()

    @pytest.fixture
    def extractor(self):
        return EdgeExtractor(vault_root=Path('./Vault'))

    def test_vault_existing_law_generates_edge(self, extractor):
        """Vault に存在する法令への参照がエッジを生成"""
        text = "会社法第一条の規定"
        replaced, edges = extractor.replace_refs_with_edges(
            text=text,
            law_name="テスト法",
            source_law_id="TEST001",
            source_node_id="JPLAW:TEST001#main#1"
        )

        # 会社法へのリンクとエッジが生成される
        assert "[[laws/会社法/本文/第1条.md|第一条]]" in replaced
        assert len(edges) == 1
        edge = edges[0]
        assert edge["from"] == "JPLAW:TEST001#main#1"
        assert "会社法" in str(edge["to"]) or "417AC0000000086" in edge["to"]

    def test_vault_nonexisting_law_no_edge(self, extractor):
        """Vault に存在しない法令への参照はエッジを生成しない"""
        text = "少年法第一条の規定"
        replaced, edges = extractor.replace_refs_with_edges(
            text=text,
            law_name="テスト法",
            source_law_id="TEST001",
            source_node_id="JPLAW:TEST001#main#1"
        )

        # リンクもエッジも生成されない
        assert "[[" not in replaced
        assert len(edges) == 0


class TestMixedReferences:
    """複合参照のテスト"""

    @pytest.fixture(autouse=True)
    def setup(self):
        clear_vault_caches()
        set_vault_root(Path('./Vault'))
        yield
        clear_vault_caches()

    @pytest.fixture
    def extractor(self):
        return EdgeExtractor(vault_root=Path('./Vault'))

    def test_multiple_laws_in_same_text(self, extractor):
        """同一テキスト内の複数法令参照"""
        text = "刑法第百九十九条及び会社法第一条の規定"
        result = extractor.replace_refs(text, "テスト法")
        # 両方リンク化
        assert "[[laws/刑法/本文/第199条.md|第百九十九条]]" in result
        assert "[[laws/会社法/本文/第1条.md|第一条]]" in result

    def test_vault_and_nonvault_laws(self, extractor):
        """Vault 存在法令と非存在法令の混在"""
        text = "会社法第一条及び少年法第二条の規定"
        result = extractor.replace_refs(text, "テスト法")
        # 会社法はリンク化、少年法はリンク化しない
        assert "[[laws/会社法/本文/第1条.md|第一条]]" in result
        assert "少年法第二条" in result
        assert "[[laws/少年法" not in result
