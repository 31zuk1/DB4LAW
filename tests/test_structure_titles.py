from legalkg.utils.structure_titles import (
    extract_structure_subtitle,
    format_chapter_name,
    format_part_name,
    format_section_name,
)


def test_extract_structure_subtitle():
    assert extract_structure_subtitle("第一編　総則", "編") == "総則"
    assert extract_structure_subtitle("第一章　通則", "章") == "通則"
    assert extract_structure_subtitle("第二章の二　社債管理補助者", "章") == "社債管理補助者"
    assert extract_structure_subtitle("第1節 通則", "節") == "通則"
    assert extract_structure_subtitle("第一章", "章") is None
    assert extract_structure_subtitle("通則", "章") == "通則"


def test_format_part_name():
    assert format_part_name(1) == "第1編"
    assert format_part_name(12) == "第12編"


def test_format_chapter_name():
    assert format_chapter_name(1) == "第1章"
    assert format_chapter_name(182) == "第18章の2"
    assert format_chapter_name(22, "第二章の二　社債管理補助者") == "第2章の2"


def test_format_section_name():
    assert format_section_name(1) == "第1節"
    assert format_section_name(12, "第一節の二　売渡株式等") == "第1節の2"
