#!/usr/bin/env python3
"""
構造ノード見出しの重複修正スクリプト

Tier1 生成ロジックと同じ整形関数を使って、既存の編/章/節ノード本文を補正する。

修正対象:
- 先頭見出し（# ...）
- 章/節への WikiLink 表示名（|...）

Usage:
    # dry-run
    uv run python scripts/migration/fix_structure_headings.py --vault ./Vault

    # apply
    uv run python scripts/migration/fix_structure_headings.py --vault ./Vault --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from legalkg.utils.markdown import read_markdown_file, write_markdown_file
from legalkg.utils.structure_titles import (
    extract_structure_subtitle,
    format_chapter_name,
    format_part_name,
    format_section_name,
)


HEADING_RE = re.compile(r"^# .*$", re.MULTILINE)
WIKILINK_WITH_ALIAS_RE = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")
CHAPTER_FILE_RE = re.compile(r"^(?:第\d+編)?(第\d+章(?:の\d+)?)\.md$")
SECTION_FILE_RE = re.compile(r"^(?:第\d+編)?(?:第\d+章(?:の\d+)?)?(第\d+節(?:の\d+)?)\.md$")


@dataclass
class Stats:
    scanned_files: int = 0
    changed_files: int = 0
    heading_changes: int = 0
    link_alias_changes: int = 0


def _with_optional_subtitle(base: str, subtitle: Optional[str]) -> str:
    if subtitle:
        return f"{base} {subtitle}"
    return base


def _build_expected_heading(metadata: dict) -> Optional[str]:
    node_type = metadata.get("type")

    if node_type == "part":
        part_num = metadata.get("part_num")
        if part_num is None:
            return None
        base = format_part_name(int(part_num))
        subtitle = extract_structure_subtitle(metadata.get("part_title"), "編")
        return _with_optional_subtitle(base, subtitle)

    if node_type == "chapter":
        chapter_num = metadata.get("chapter_num")
        if chapter_num is None:
            return None
        chapter_title = metadata.get("chapter_title")
        base = format_chapter_name(int(chapter_num), chapter_title)
        subtitle = extract_structure_subtitle(chapter_title, "章")
        return _with_optional_subtitle(base, subtitle)

    if node_type == "section":
        chapter_num = metadata.get("chapter_num")
        section_num = metadata.get("section_num")
        if chapter_num is None or section_num is None:
            return None
        chapter_title = metadata.get("chapter_title")
        section_title = metadata.get("section_title")
        chapter_base = format_chapter_name(int(chapter_num), chapter_title)
        section_base = format_section_name(int(section_num), section_title)
        chapter_subtitle = extract_structure_subtitle(chapter_title, "章")
        section_subtitle = extract_structure_subtitle(section_title, "節")
        left = _with_optional_subtitle(chapter_base, chapter_subtitle)
        right = _with_optional_subtitle(section_base, section_subtitle)
        return f"{left} {right}"

    return None


def _replace_first_heading(body: str, expected_heading: str) -> tuple[str, int]:
    match = HEADING_RE.search(body)
    if not match:
        return body, 0

    old_line = match.group(0)
    new_line = f"# {expected_heading}"
    if old_line == new_line:
        return body, 0

    updated = body[:match.start()] + new_line + body[match.end():]
    return updated, 1


def _extract_structure_base_from_path(path: str, unit: str) -> Optional[str]:
    file_name = Path(path).name
    if unit == "章":
        match = CHAPTER_FILE_RE.match(file_name)
    else:
        match = SECTION_FILE_RE.match(file_name)
    if not match:
        return None
    return match.group(1)


def _normalize_structure_alias(alias: str, base: str, unit: str) -> str:
    raw = alias.strip()
    if raw.startswith(base):
        trailing = raw[len(base):].lstrip(" \u3000\t")
    else:
        pattern = re.compile(rf"^(第\d+{unit}(?:の\d+)?)(.*)$")
        match = pattern.match(raw)
        if not match:
            return alias
        base = match.group(1)
        trailing = match.group(2).lstrip(" \u3000\t")

    subtitle = extract_structure_subtitle(trailing, unit) if trailing else None
    normalized = _with_optional_subtitle(base, subtitle)
    return normalized


def _normalize_structure_link_aliases(body: str) -> tuple[str, int]:
    changes = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changes
        path = match.group(1)
        alias = match.group(2)

        unit: Optional[str] = None
        if "/章/" in path or path.startswith("章/"):
            unit = "章"
        elif "/節/" in path or path.startswith("節/"):
            unit = "節"

        if not unit:
            return match.group(0)

        base = _extract_structure_base_from_path(path, unit)
        if not base:
            return match.group(0)

        new_alias = _normalize_structure_alias(alias, base, unit)
        if new_alias == alias:
            return match.group(0)

        changes += 1
        return f"[[{path}|{new_alias}]]"

    updated = WIKILINK_WITH_ALIAS_RE.sub(repl, body)
    return updated, changes


def _iter_target_files(law_dir: Path):
    for sub_dir in ("編", "章", "節"):
        node_dir = law_dir / sub_dir
        if not node_dir.exists():
            continue
        for md_file in sorted(node_dir.glob("*.md")):
            yield md_file


def _process_file(md_file: Path, apply: bool) -> tuple[bool, int, int]:
    doc = read_markdown_file(md_file)
    if doc is None:
        return False, 0, 0

    expected_heading = _build_expected_heading(doc.metadata)
    if not expected_heading:
        return False, 0, 0

    body, heading_changes = _replace_first_heading(doc.body, expected_heading)
    body, alias_changes = _normalize_structure_link_aliases(body)

    changed = (heading_changes + alias_changes) > 0
    if changed and apply:
        doc.body = body
        write_markdown_file(md_file, doc)

    return changed, heading_changes, alias_changes


def main():
    parser = argparse.ArgumentParser(description="構造ノード見出しの重複修正")
    parser.add_argument("--vault", type=Path, default=Path("./Vault"), help="Vault ディレクトリ")
    parser.add_argument("--law", type=str, help="特定の法令IDに限定")
    parser.add_argument("--apply", action="store_true", help="変更を適用する")
    args = parser.parse_args()

    dry_run = not args.apply
    laws_dir = args.vault / "laws"
    if not laws_dir.exists():
        print(f"Error: laws directory not found: {laws_dir}", file=sys.stderr)
        sys.exit(1)

    if args.law:
        law_dirs = [laws_dir / args.law]
        if not law_dirs[0].exists():
            print(f"Error: law directory not found: {law_dirs[0]}", file=sys.stderr)
            sys.exit(1)
    else:
        law_dirs = sorted(d for d in laws_dir.iterdir() if d.is_dir())

    stats = Stats()
    changed_samples: list[str] = []

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"[{mode}] Scanning {len(law_dirs)} law directories...")

    for law_dir in law_dirs:
        for md_file in _iter_target_files(law_dir):
            stats.scanned_files += 1
            changed, heading_changes, alias_changes = _process_file(md_file, apply=args.apply)
            if not changed:
                continue
            stats.changed_files += 1
            stats.heading_changes += heading_changes
            stats.link_alias_changes += alias_changes
            if len(changed_samples) < 20:
                changed_samples.append(str(md_file))

    print(f"Scanned files: {stats.scanned_files}")
    print(f"Changed files: {stats.changed_files}")
    print(f"Heading updates: {stats.heading_changes}")
    print(f"Link alias updates: {stats.link_alias_changes}")

    if changed_samples:
        print("Examples:")
        for sample in changed_samples:
            print(f"  - {sample}")

    if dry_run and stats.changed_files > 0:
        print("Run with --apply to write changes.")


if __name__ == "__main__":
    main()
