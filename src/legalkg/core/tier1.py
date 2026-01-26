"""
Tier1 Builder - v2 Native Implementation

e-Gov API v2 の JSON を直接 traverse して条文ノードを生成。
BeautifulSoup / XML 依存を完全廃止。
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
from ..client.egov import EGovClient
import logging
import yaml
import json

from ..utils.parent_links import update_law_file_with_links

logger = logging.getLogger(__name__)


# =============================================================================
# JSON Tree Traversal Helpers
# =============================================================================

def find_child(node: Dict[str, Any], tag: str) -> Optional[Dict[str, Any]]:
    """指定タグの最初の子要素を取得"""
    if not isinstance(node, dict):
        return None
    for child in node.get("children", []):
        if isinstance(child, dict) and child.get("tag") == tag:
            return child
    return None


def find_children(node: Dict[str, Any], tag: str) -> List[Dict[str, Any]]:
    """指定タグの全子要素を取得"""
    if not isinstance(node, dict):
        return []
    return [
        child for child in node.get("children", [])
        if isinstance(child, dict) and child.get("tag") == tag
    ]


def find_all_recursive(node: Dict[str, Any], tag: str) -> List[Dict[str, Any]]:
    """指定タグの要素を再帰的に全て取得"""
    results = []
    if not isinstance(node, dict):
        return results
    if node.get("tag") == tag:
        results.append(node)
    for child in node.get("children", []):
        if isinstance(child, dict):
            results.extend(find_all_recursive(child, tag))
    return results


def get_text(node: Dict[str, Any]) -> str:
    """ノード内の全テキストを再帰的に取得"""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    texts = []
    for child in node.get("children", []):
        texts.append(get_text(child))
    return "".join(texts)


def get_attr(node: Dict[str, Any], key: str, default: str = "") -> str:
    """ノードの属性値を取得"""
    if not isinstance(node, dict):
        return default
    return node.get("attr", {}).get(key, default)


# =============================================================================
# Tier1Builder
# =============================================================================

class Tier1Builder:
    def __init__(self, vault_root: Path, targets_path: Path):
        self.vault_root = vault_root
        self.client = EGovClient()
        self.laws_dir = self.vault_root / "laws"
        self.targets = self._load_targets(targets_path)

    def _load_targets(self, path: Path) -> List[str]:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "targets" in data:
                return data["targets"]
            return []

    def _get_law_name(self, law_md_path: Path) -> str:
        """親法ファイルから法令名を取得"""
        try:
            with open(law_md_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.startswith('---'):
                return ""

            parts = content.split('---', 2)
            if len(parts) < 3:
                return ""

            frontmatter = yaml.safe_load(parts[1])
            return frontmatter.get('title', '')
        except Exception as e:
            logger.warning(f"Failed to extract law name from {law_md_path}: {e}")
            return ""

    def build(self, extract_edges: bool = False):
        print(f"Processing {len(self.targets)} target laws...")

        report = {
            "total_targets": len(self.targets),
            "success": [],
            "failed": [],
            "timestamp": "2025-12-30"
        }

        from tqdm import tqdm
        for law_id in tqdm(self.targets, desc="Processing Laws"):
            try:
                self._process_law(law_id, extract_edges)
                report["success"].append(law_id)
            except Exception as e:
                logger.error(f"Failed to process {law_id}: {e}")
                print(f"Error {law_id}: {e}")
                report["failed"].append({"id": law_id, "error": str(e)})

        with open("report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    def _process_law(self, law_id: str, extract_edges: bool):
        """法令を処理して条文ノードを生成"""
        # v2 JSON を直接取得
        law_tree = self.client.get_law_full_text(law_id)
        if not law_tree:
            logger.warning(f"No law data for {law_id}")
            return

        from ..utils.fs import find_law_dir_by_id
        law_dir = find_law_dir_by_id(self.laws_dir, law_id)

        if not law_dir or not law_dir.exists():
            logger.warning(f"Tier 0 metadata not found for {law_id}, skipping.")
            return

        from ..utils.fs import get_law_node_file
        law_md_path = get_law_node_file(law_dir)
        law_name = self._get_law_name(law_md_path) if law_md_path else ""

        if extract_edges:
            from .tier2 import EdgeExtractor, set_vault_root
            set_vault_root(self.vault_root)
            all_edges = []
        else:
            all_edges = None

        # ディレクトリ作成
        honbun_dir = law_dir / "本文"
        fusoku_dir = law_dir / "附則"
        honbun_dir.mkdir(exist_ok=True)
        fusoku_dir.mkdir(exist_ok=True)

        # LawBody を取得
        law_body = find_child(law_tree, "LawBody")
        if not law_body:
            logger.warning(f"No LawBody found for {law_id}")
            return

        # MainProvision（本文）を処理
        main_provision = find_child(law_body, "MainProvision")
        if main_provision:
            self._process_part(
                main_provision, law_id, honbun_dir, "main",
                extract_edges, all_edges, law_name=law_name, amend_law_num=None
            )

        # SupplProvision（附則）を処理
        init_suppl_count = 0
        for suppl in find_children(law_body, "SupplProvision"):
            raw_amend_num = get_attr(suppl, "AmendLawNum")

            if raw_amend_num:
                # 改正法断片
                safe_amend = re.sub(r'[^\w\-]', '_', raw_amend_num)
                file_key_prefix = safe_amend
            else:
                # 初期附則
                if init_suppl_count == 0:
                    safe_amend = "制定時附則"
                else:
                    safe_amend = f"制定時附則{init_suppl_count + 1}"
                init_suppl_count += 1
                file_key_prefix = None

            # Article の有無を確認
            has_articles = bool(find_all_recursive(suppl, "Article"))

            if has_articles:
                out_dir = fusoku_dir / safe_amend
                out_dir.mkdir(exist_ok=True, parents=True)
                self._process_part(
                    suppl, law_id, out_dir, "suppl",
                    extract_edges, all_edges,
                    file_key_override=file_key_prefix,
                    law_name=law_name, amend_law_num=raw_amend_num
                )
            else:
                self._process_part(
                    suppl, law_id, fusoku_dir, "suppl",
                    extract_edges, all_edges,
                    file_key_override=safe_amend,
                    amend_law_num=raw_amend_num
                )

        # edges.jsonl 出力
        if extract_edges and all_edges:
            with open(law_dir / "edges.jsonl", "w", encoding="utf-8") as f:
                for edge in all_edges:
                    f.write(json.dumps(edge, ensure_ascii=False) + "\n")

        # tier 更新
        final_tier = 2 if extract_edges else 1
        if law_md_path:
            self._update_law_tier(law_md_path, final_tier)

        # 親リンク更新
        update_law_file_with_links(law_dir)

    def _process_part(
        self,
        container: Dict[str, Any],
        law_id: str,
        out_dir: Path,
        part_type: str,
        extract_edges: bool = False,
        edge_list: Optional[List] = None,
        file_key_override: Optional[str] = None,
        law_name: str = "",
        amend_law_num: Optional[str] = None
    ):
        """条文パートを処理してMarkdownファイルを生成"""
        if not container:
            return

        from .tier2 import EdgeExtractor

        # 改正法断片判定: AmendLawNum が存在し、かつ空でない場合
        is_amendment_fragment = bool(amend_law_num)

        # Article を取得
        articles = find_all_recursive(container, "Article")

        # Article がない場合は直接 Paragraph を処理
        if not articles:
            direct_paragraphs = find_children(container, "Paragraph")
            if direct_paragraphs:
                self._process_direct_paragraphs(
                    direct_paragraphs, container, law_id, out_dir, part_type,
                    extract_edges, edge_list, file_key_override,
                    law_name, amend_law_num, is_amendment_fragment
                )
            return

        # 各 Article を処理
        for article in articles:
            self._process_article(
                article, law_id, out_dir, part_type,
                extract_edges, edge_list, file_key_override,
                law_name, amend_law_num, is_amendment_fragment
            )

    def _process_article(
        self,
        article: Dict[str, Any],
        law_id: str,
        out_dir: Path,
        part_type: str,
        extract_edges: bool,
        edge_list: Optional[List],
        file_key_override: Optional[str],
        law_name: str,
        amend_law_num: Optional[str],
        is_amendment_fragment: bool
    ):
        """単一の Article を処理"""
        from .tier2 import EdgeExtractor

        num = get_attr(article, "Num")
        if not num:
            return

        # ファイル名生成
        parts = num.split('_')
        if len(parts) == 1:
            jp_article_name = f"第{parts[0]}条"
        elif len(parts) == 2:
            jp_article_name = f"第{parts[0]}条の{parts[1]}"
        else:
            safe_num_jp = num.replace('_', 'の')
            jp_article_name = f"第{safe_num_jp}条"

        if file_key_override:
            file_key = f"{file_key_override}_{jp_article_name}"
        else:
            file_key = jp_article_name

        file_path = out_dir / f"{file_key}.md"

        # 見出しとタイトル
        caption_node = find_child(article, "ArticleCaption")
        caption_text = get_text(caption_node) if caption_node else ""
        title_node = find_child(article, "ArticleTitle")
        title_text = get_text(title_node) if title_node else ""

        content = f"# {title_text} {caption_text}\n\n"
        node_id = f"JPLAW:{law_id}#{part_type}#{num}"

        extractor = EdgeExtractor(vault_root=self.vault_root if extract_edges else None)
        article_edges = []

        # Paragraph 処理
        for para in find_children(article, "Paragraph"):
            para_content, para_edges = self._process_paragraph(
                para, extractor, law_name, law_id, node_id,
                extract_edges, edge_list is not None, is_amendment_fragment
            )
            content += para_content
            article_edges.extend(para_edges)

        if extract_edges and edge_list is not None:
            edge_list.extend(article_edges)

        # Frontmatter 生成
        fm = self._build_frontmatter(
            node_id, part_type, law_id, law_name, num, caption_text,
            is_amendment_fragment, amend_law_num
        )

        self._write_markdown(file_path, fm, content)

    def _process_direct_paragraphs(
        self,
        paragraphs: List[Dict[str, Any]],
        container: Dict[str, Any],
        law_id: str,
        out_dir: Path,
        part_type: str,
        extract_edges: bool,
        edge_list: Optional[List],
        file_key_override: Optional[str],
        law_name: str,
        amend_law_num: Optional[str],
        is_amendment_fragment: bool
    ):
        """Article なしの直接 Paragraph を処理"""
        from .tier2 import EdgeExtractor

        file_key = file_key_override if file_key_override else "Provision"
        file_path = out_dir / f"{file_key}.md"

        node_id = f"JPLAW:{law_id}#{part_type}#Provision"
        content = f"# 附則\n\n"

        extractor = EdgeExtractor(vault_root=self.vault_root if extract_edges else None)
        provision_edges = []

        for para in paragraphs:
            para_content, para_edges = self._process_paragraph(
                para, extractor, law_name, law_id, node_id,
                extract_edges, edge_list is not None, is_amendment_fragment
            )
            content += para_content
            provision_edges.extend(para_edges)

        if extract_edges and edge_list is not None:
            edge_list.extend(provision_edges)

        # Frontmatter
        if is_amendment_fragment:
            node_type = "amendment_fragment"
            kind_tag = "kind/amendment_fragment"
        else:
            node_type = "supplement"
            kind_tag = "kind/supplement"

        fm = {
            "id": node_id,
            "type": node_type,
            "parent": f"[[laws/{law_name}/{law_name}]]" if law_name else None,
            "law_id": law_id,
            "law_name": law_name,
            "part": part_type,
            "article_num": "Provision",
            "heading": "附則",
            "tags": [law_name, kind_tag] if law_name else [kind_tag]
        }

        self._write_markdown(file_path, fm, content)

    def _process_paragraph(
        self,
        para: Dict[str, Any],
        extractor,
        law_name: str,
        law_id: str,
        node_id: str,
        extract_edges: bool,
        has_edge_list: bool,
        is_amendment_fragment: bool
    ) -> tuple:
        """Paragraph を処理してコンテンツとエッジを返す"""
        edges = []

        # ParagraphNum
        para_num_node = find_child(para, "ParagraphNum")
        para_num_text = get_text(para_num_node) if para_num_node else ""

        # 旧版互換: Paragraph 内の全 Sentence を再帰取得（Item 内含む）
        # BeautifulSoup の find_all("Sentence") と同等の動作
        sentences = find_all_recursive(para, "Sentence")
        raw_text = "".join([get_text(s) for s in sentences])

        # リンク処理
        if law_name:
            if extract_edges and has_edge_list:
                text, para_edges = extractor.replace_refs_with_edges(
                    text=raw_text,
                    law_name=law_name,
                    source_law_id=law_id,
                    source_node_id=node_id,
                    is_amendment_fragment=is_amendment_fragment
                )
                edges.extend(para_edges)
            else:
                text = extractor.replace_refs(raw_text, law_name, is_amendment_fragment=is_amendment_fragment)
        else:
            text = raw_text

        content = f"## {para_num_text}\n{text}\n\n"

        # Item 処理
        for item in find_children(para, "Item"):
            item_content, item_edges = self._process_item(
                item, extractor, law_name, law_id, node_id,
                extract_edges, has_edge_list, is_amendment_fragment
            )
            content += item_content
            edges.extend(item_edges)

        return content, edges

    def _process_item(
        self,
        item: Dict[str, Any],
        extractor,
        law_name: str,
        law_id: str,
        node_id: str,
        extract_edges: bool,
        has_edge_list: bool,
        is_amendment_fragment: bool
    ) -> tuple:
        """Item を処理してコンテンツとエッジを返す"""
        edges = []

        # ItemTitle
        title_node = find_child(item, "ItemTitle")
        title_text = get_text(title_node) if title_node else ""

        # ItemSentence 内の全 Sentence を再帰取得（Column でラップされる場合あり）
        item_sentence = find_child(item, "ItemSentence")
        if item_sentence:
            sentences = find_all_recursive(item_sentence, "Sentence")
            raw_text = "".join([get_text(s) for s in sentences])
        else:
            sentences = find_all_recursive(item, "Sentence")
            raw_text = "".join([get_text(s) for s in sentences])

        # リンク処理
        if law_name:
            if extract_edges and has_edge_list:
                text, item_edges = extractor.replace_refs_with_edges(
                    text=raw_text,
                    law_name=law_name,
                    source_law_id=law_id,
                    source_node_id=node_id,
                    is_amendment_fragment=is_amendment_fragment
                )
                edges.extend(item_edges)
            else:
                text = extractor.replace_refs(raw_text, law_name, is_amendment_fragment=is_amendment_fragment)
        else:
            text = raw_text

        content = f"- {title_text} {text}\n"
        return content, edges

    def _build_frontmatter(
        self,
        node_id: str,
        part_type: str,
        law_id: str,
        law_name: str,
        article_num: str,
        heading: str,
        is_amendment_fragment: bool,
        amend_law_num: Optional[str]
    ) -> Dict[str, Any]:
        """Frontmatter を構築"""
        if is_amendment_fragment:
            node_type = "amendment_fragment"
            kind_tag = "kind/amendment_fragment"
        elif part_type == "suppl":
            node_type = "supplement"
            kind_tag = "kind/supplement"
        else:
            node_type = "article"
            kind_tag = "kind/article"

        fm = {
            "id": node_id,
            "type": node_type,
            "parent": f"[[laws/{law_name}/{law_name}]]" if law_name else None,
            "law_id": law_id,
            "law_name": law_name,
            "part": part_type,
            "article_num": article_num,
            "heading": heading,
            "tags": [law_name, kind_tag] if law_name else [kind_tag]
        }

        if is_amendment_fragment and amend_law_num:
            from ..utils.article_formatter import normalize_amendment_id
            normalized_id = normalize_amendment_id(amend_law_num)

            fm["suppl_kind"] = "amendment"
            fm["amendment_law_id"] = normalized_id
            fm["amendment_law_title"] = amend_law_num

            fm["amend_law"] = {
                "num": amend_law_num,
                "normalized_id": normalized_id,
                "scope": "partial",
                "parent_law_id": law_id,
                "parent_law_name": law_name,
            }

        return fm

    def _write_markdown(self, file_path: Path, fm: Dict[str, Any], content: str):
        """Markdown ファイルを書き出し"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.dump(fm, f, allow_unicode=True, default_flow_style=False)
            f.write("---\n\n")
            f.write(content)

    def _update_law_tier(self, md_path: Path, tier: int):
        if not md_path.exists():
            return

        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_str = parts[1]
                fm = yaml.safe_load(fm_str)
                if fm.get("tier", 0) < tier:
                    fm["tier"] = tier
                    new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False)
                    new_content = f"---\n{new_fm}---{parts[2]}"
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
