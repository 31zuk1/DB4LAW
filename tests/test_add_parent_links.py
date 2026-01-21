#!/usr/bin/env python3
"""
add_parent_links.py のテスト

テスト対象:
- ディレクトリ型初期附則（制定時附則/）へのリンク生成
- 単一ファイル型初期附則（制定時附則.md）へのリンク維持
- 冪等性（2回実行しても重複しない）
- レガシー形式（init_0/）との互換性
"""

from pathlib import Path

import pytest

from legalkg.utils.parent_links import (
    extract_article_sort_key,
    extract_display_name_from_init_file,
    generate_links_for_law,
)


class TestExtractArticleSortKey:
    """ソートキー抽出のテスト"""

    def test_simple_article(self):
        assert extract_article_sort_key("第1条.md") == (1, 0, 0)
        assert extract_article_sort_key("第100条.md") == (100, 0, 0)

    def test_article_with_sub_number(self):
        assert extract_article_sort_key("第1条の2.md") == (1, 2, 0)
        assert extract_article_sort_key("第3条の10.md") == (3, 10, 0)

    def test_range_article(self):
        assert extract_article_sort_key("第638:640条.md") == (638, 0, 640)

    def test_prefixed_article_legacy(self):
        """レガシー init_0_ プレフィックス付きファイル名"""
        assert extract_article_sort_key("init_0_第1条.md") == (1, 0, 0)
        assert extract_article_sort_key("init_0_第10条.md") == (10, 0, 0)
        assert extract_article_sort_key("init_0_第3条の2.md") == (3, 2, 0)

    def test_suppl_article(self):
        assert extract_article_sort_key("附則第1条.md") == (1, 0, 0)


class TestExtractDisplayName:
    """表示名抽出のテスト"""

    def test_simple_article(self):
        """新形式: 第N条.md → 第N条"""
        assert extract_display_name_from_init_file("第1条.md") == "第1条"
        assert extract_display_name_from_init_file("第10条.md") == "第10条"

    def test_legacy_init_file(self):
        """レガシー形式: init_0_第N条.md → 第N条"""
        assert extract_display_name_from_init_file("init_0_第1条.md") == "第1条"
        assert extract_display_name_from_init_file("init_0_第10条.md") == "第10条"

    def test_article_with_sub_number(self):
        assert extract_display_name_from_init_file("第3条の2.md") == "第3条の2"
        assert extract_display_name_from_init_file("init_0_第3条の2.md") == "第3条の2"


class TestGenerateLinksForLaw:
    """リンク生成のテスト（Vault依存）"""

    @pytest.fixture
    def vault_laws_path(self):
        return Path("/Users/haramizuki/Project/DB4LAW/Vault/laws")

    def test_minjisosoho_has_seitei_dir_links(self, vault_laws_path):
        """民事訴訟法: ディレクトリ型初期附則（制定時附則/）へのリンクが生成される"""
        law_dir = vault_laws_path / "民事訴訟法"
        if not law_dir.exists():
            pytest.skip("Vault not found")

        links = generate_links_for_law(law_dir)

        # 制定時附則セクションが存在する
        assert "### 制定時附則" in links

        # 第1条〜第27条へのリンクが存在（第2条は欠番）
        assert "[[附則/制定時附則/第1条.md|第1条]]" in links
        assert "[[附則/制定時附則/第27条.md|第27条]]" in links

        # リンク数が正しい（26条）
        seitei_links = [line for line in links.split('\n') if '制定時附則/' in line]
        assert len(seitei_links) == 26

    def test_keijisosoho_has_seitei_file_link(self, vault_laws_path):
        """刑事訴訟法: 単一ファイル型初期附則（制定時附則.md）へのリンクが維持される"""
        law_dir = vault_laws_path / "刑事訴訟法"
        if not law_dir.exists():
            pytest.skip("Vault not found")

        links = generate_links_for_law(law_dir)

        # 単一ファイル型リンクが存在
        assert "[[附則/制定時附則.md|制定時附則]]" in links

        # ディレクトリ型リンクは存在しない
        assert "制定時附則/" not in links

    def test_idempotency(self, vault_laws_path):
        """冪等性: 2回生成しても同じ結果"""
        law_dir = vault_laws_path / "民事訴訟法"
        if not law_dir.exists():
            pytest.skip("Vault not found")

        links1 = generate_links_for_law(law_dir)
        links2 = generate_links_for_law(law_dir)

        assert links1 == links2

    def test_no_legacy_init_links(self, vault_laws_path):
        """レガシー init_0 形式へのリンクが生成されない"""
        law_dir = vault_laws_path / "民事訴訟法"
        if not law_dir.exists():
            pytest.skip("Vault not found")

        links = generate_links_for_law(law_dir)

        # init_0 へのリンクが存在しない
        assert "init_0" not in links


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
