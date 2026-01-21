from pathlib import Path
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
from ..client.egov import EGovClient
import logging
import yaml
import json

logger = logging.getLogger(__name__)

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
            # Handle if targets.yaml has structure like {targets: [...]}
            if isinstance(data, dict) and "targets" in data:
                return data["targets"]
            return []

    def _get_law_name(self, law_md_path: Path) -> str:
        """Extract law name from the parent law's metadata file."""
        try:
            with open(law_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse frontmatter
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
            "timestamp": "2025-12-30" # Should be dynamic in real app
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
        xml_text = self.client.fetch_law_xml(law_id)
        if not xml_text:
            logger.warning(f"No XML for {law_id}")
            return

        # Parse XML
        soup = BeautifulSoup(xml_text, "xml")
        
        # Determine law structure
        # e-Gov XML: <LawNum>, <LawBody><MainProvision>...</MainProvision><SupplProvision>...</SupplProvision>
        
        from ..utils.fs import find_law_dir_by_id
        law_dir = find_law_dir_by_id(self.laws_dir, law_id)
        
        if not law_dir or not law_dir.exists():
            logger.warning(f"Tier 0 metadata not found for {law_id} (Dir lookup failed), skipping article generation.")
            return
        
        from ..utils.fs import get_law_node_file
        law_md_path = get_law_node_file(law_dir)
        # If not found, maybe create partial one?
        # Tier 1 generally assumes Tier 0 exists.
        
        # Extract law name from parent law metadata
        law_name = self._get_law_name(law_md_path) if law_md_path else ""

        if extract_edges:
            from .tier2 import EdgeExtractor, set_vault_root
            # Vault ルートを設定（クロスリンク edges の law_id 解決に使用）
            set_vault_root(self.vault_root)
            all_edges = []
            
        # Updated to use Japanese folder names directly under law root
        # articles_dir = law_dir / "articles"  <-- Removed
        # (articles_dir / "main").mkdir(exist_ok=True)
        # (articles_dir / "suppl").mkdir(exist_ok=True)

        honbun_dir = law_dir / "本文"
        fusoku_dir = law_dir / "附則"
        honbun_dir.mkdir(exist_ok=True)
        fusoku_dir.mkdir(exist_ok=True)

        self._process_part(soup.find("MainProvision"), law_id, honbun_dir, "main", extract_edges, all_edges if extract_edges else None, law_name=law_name, amend_law_num=None)

        # Handle multiple SupplProvision
        init_suppl_count = 0  # 初期附則のカウンター
        for i, spl in enumerate(soup.find_all("SupplProvision")):
            # AmendLawNum が存在すれば改正法断片、なければ初期附則
            raw_amend_num = spl.get("AmendLawNum")  # None if not present

            if raw_amend_num:
                # 改正法断片: 法律番号をサニタイズしてディレクトリ名に
                safe_amend = re.sub(r'[^\w\-]', '_', raw_amend_num)
                file_key_prefix = safe_amend
            else:
                # 初期附則: 日本語名を使用（制定時附則, 制定時附則2, ...）
                if init_suppl_count == 0:
                    safe_amend = "制定時附則"
                else:
                    safe_amend = f"制定時附則{init_suppl_count + 1}"
                init_suppl_count += 1
                file_key_prefix = None  # 初期附則はファイル名にプレフィックスを付けない

            # Check if this provision has articles
            has_articles = bool(spl.find("Article"))

            if has_articles:
                # Use subdirectory
                out_dir = fusoku_dir / safe_amend
                out_dir.mkdir(exist_ok=True, parents=True)
                self._process_part(spl, law_id, out_dir, "suppl", extract_edges, all_edges if extract_edges else None, file_key_override=file_key_prefix, law_name=law_name, amend_law_num=raw_amend_num)
            else:
                # Use direct file under suppl/
                out_dir = fusoku_dir
                self._process_part(spl, law_id, out_dir, "suppl", extract_edges, all_edges if extract_edges else None, file_key_override=safe_amend, amend_law_num=raw_amend_num)

        if extract_edges and all_edges:
            with open(law_dir / "edges.jsonl", "w", encoding="utf-8") as f:
                for edge in all_edges:
                    f.write(json.dumps(edge, ensure_ascii=False) + "\n")

        # Update law.md content tier -> 2 if edges extracted
        final_tier = 2 if extract_edges else 1
        if law_md_path:
            self._update_law_tier(law_md_path, final_tier)

    def _process_part(self, container, law_id: str, out_dir: Path, part_type: str, extract_edges: bool = False, edge_list: List = None, file_key_override: str = None, law_name: str = "", amend_law_num: Optional[str] = None):
        """
        条文パートを処理してMarkdownファイルを生成

        Args:
            container: BeautifulSoup要素（MainProvision または SupplProvision）
            law_id: 法令ID
            out_dir: 出力ディレクトリ
            part_type: 'main' または 'suppl'
            extract_edges: エッジ抽出を行うか
            edge_list: エッジ蓄積リスト
            file_key_override: ファイル名プレフィックス
            law_name: 親法名
            amend_law_num: AmendLawNum属性値（改正法断片の場合に設定）
                           None = 本文 or 初期附則（リンク化する）
                           値あり = 改正法断片（裸の第N条はリンク化しない）
        """
        if not container:
            return

        # 改正法断片判定: AmendLawNum が存在すれば改正法断片
        is_amendment_fragment = amend_law_num is not None

        # Find Articles
        articles = container.find_all("Article")
        
        # Fallback: Some SupplProvision have no Article, just Paragraphs directly.
        if not articles:
            # Check for direct paragraphs
            direct_paragraphs = container.find_all("Paragraph", recursive=False)
            if direct_paragraphs:
                # Treat as a single unit
                if file_key_override:
                    file_key = file_key_override
                else:
                    file_key = "Provision"

                file_path = out_dir / f"{file_key}.md"

                # Frontmatter（先に node_id を生成）
                node_id = f"JPLAW:{law_id}#{part_type}#Provision"

                content = f"# 附則\n\n"

                # Setup extractor for linking
                # SSOT: extract_edges=True の場合は replace_refs_with_edges を使用
                from .tier2 import EdgeExtractor
                extractor = EdgeExtractor(vault_root=self.vault_root if extract_edges else None)
                provision_edges = []  # この Provision から抽出されたエッジ

                for p in direct_paragraphs:
                    p_num = p.find("ParagraphNum")
                    p_num_text = p_num.text if p_num else ""

                    sentences = p.find_all("Sentence")
                    raw_text = "".join([s.text for s in sentences])

                    # Link Injection & Edge Extraction (SSOT)
                    if law_name:
                        if extract_edges and edge_list is not None:
                            text, edges = extractor.replace_refs_with_edges(
                                text=raw_text,
                                law_name=law_name,
                                source_law_id=law_id,
                                source_node_id=node_id,
                                is_amendment_fragment=is_amendment_fragment
                            )
                            provision_edges.extend(edges)
                        else:
                            text = extractor.replace_refs(raw_text, law_name, is_amendment_fragment=is_amendment_fragment)
                    else:
                        text = raw_text

                    content += f"## {p_num_text}\n{text}\n\n"

                    items = p.find_all("Item")
                    for item in items:
                        i_title = item.find("ItemTitle")
                        i_title_text = i_title.text if i_title else ""
                        i_sentences = item.find_all("Sentence")
                        i_raw_text = "".join([s.text for s in i_sentences])

                        # Link Injection & Edge Extraction (SSOT)
                        if law_name:
                            if extract_edges and edge_list is not None:
                                i_text, i_edges = extractor.replace_refs_with_edges(
                                    text=i_raw_text,
                                    law_name=law_name,
                                    source_law_id=law_id,
                                    source_node_id=node_id,
                                    is_amendment_fragment=is_amendment_fragment
                                )
                                provision_edges.extend(i_edges)
                            else:
                                i_text = extractor.replace_refs(i_raw_text, law_name, is_amendment_fragment=is_amendment_fragment)
                        else:
                            i_text = i_raw_text

                        content += f"- {i_title_text} {i_text}\n"

                # エッジを蓄積
                if extract_edges and edge_list is not None:
                    edge_list.extend(provision_edges)

                fm = {
                    "id": node_id,
                    "law_id": law_id,
                    "law_name": law_name,
                    "part": part_type,
                    "article_num": "Provision",
                    "heading": "附則",
                    "tags": [law_name] if law_name else []
                }

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("---\n")
                    yaml.dump(fm, f, allow_unicode=True, default_flow_style=False)
                    f.write("---\n\n")
                    f.write(content)
                return

        for art in articles:
            # ... (existing code extracting num, file_key)
            num = art.get("Num")
            if not num: continue

            # Japanese Filename Generation
            parts = num.split('_')
            if len(parts) == 1:
                jp_article_name = f"第{parts[0]}条"
            elif len(parts) == 2:
                jp_article_name = f"第{parts[0]}条の{parts[1]}"
            else:
                 # Fallback for complex numbers
                 safe_num_jp = num.replace('_', 'の')
                 jp_article_name = f"第{safe_num_jp}条"

            base_name = jp_article_name
            if file_key_override:
                 # If override provided (which denotes the amend law num), prefix it.
                 # We need to ensure we pass it in build() when has_articles too.
                 file_key = f"{file_key_override}_{base_name}"
            else:
                 file_key = base_name

            file_path = out_dir / f"{file_key}.md"

            # ... (content extraction)
            caption = art.find("ArticleCaption")
            caption_text = caption.text if caption else ""
            title = art.find("ArticleTitle")
            title_text = title.text if title else ""

            content = f"# {title_text} {caption_text}\n\n"

            # Frontmatter（先に node_id を生成）
            node_id = f"JPLAW:{law_id}#{part_type}#{num}"

            # Setup extractor for linking
            # SSOT: extract_edges=True の場合は replace_refs_with_edges を使用
            from .tier2 import EdgeExtractor
            extractor = EdgeExtractor(vault_root=self.vault_root if extract_edges else None)
            article_edges = []  # この条文から抽出されたエッジ

            paragraphs = art.find_all("Paragraph")
            for p in paragraphs:
                p_num = p.find("ParagraphNum")
                p_num_text = p_num.text if p_num else ""

                sentences = p.find_all("Sentence")
                raw_text = "".join([s.text for s in sentences])

                # Link Injection & Edge Extraction (SSOT)
                if law_name:
                    if extract_edges and edge_list is not None:
                        # SSOT: 置換とエッジ抽出を同時に行う
                        text, edges = extractor.replace_refs_with_edges(
                            text=raw_text,
                            law_name=law_name,
                            source_law_id=law_id,
                            source_node_id=node_id,
                            is_amendment_fragment=is_amendment_fragment
                        )
                        article_edges.extend(edges)
                    else:
                        # エッジ抽出不要時は replace_refs のみ
                        text = extractor.replace_refs(raw_text, law_name, is_amendment_fragment=is_amendment_fragment)
                else:
                    text = raw_text

                content += f"## {p_num_text}\n{text}\n\n"

                items = p.find_all("Item")
                for item in items:
                    i_title = item.find("ItemTitle")
                    i_title_text = i_title.text if i_title else ""
                    i_sentences = item.find_all("Sentence")
                    i_raw_text = "".join([s.text for s in i_sentences])

                    # Link Injection & Edge Extraction (SSOT)
                    if law_name:
                        if extract_edges and edge_list is not None:
                            # SSOT: 置換とエッジ抽出を同時に行う
                            i_text, i_edges = extractor.replace_refs_with_edges(
                                text=i_raw_text,
                                law_name=law_name,
                                source_law_id=law_id,
                                source_node_id=node_id,
                                is_amendment_fragment=is_amendment_fragment
                            )
                            article_edges.extend(i_edges)
                        else:
                            i_text = extractor.replace_refs(i_raw_text, law_name, is_amendment_fragment=is_amendment_fragment)
                    else:
                        i_text = i_raw_text

                    content += f"- {i_title_text} {i_text}\n"

            # エッジを蓄積
            if extract_edges and edge_list is not None:
                edge_list.extend(article_edges)

            fm = {
                "id": node_id,
                "law_id": law_id,
                "law_name": law_name,
                "part": part_type,
                "article_num": num,
                "heading": caption_text,
                "tags": [law_name] if law_name else []
            }

            # 改正法断片の場合は追加メタデータを付与
            if is_amendment_fragment and amend_law_num:
                from ..utils.article_formatter import normalize_amendment_id
                normalized_id = normalize_amendment_id(amend_law_num)

                # 既存フィールド（フラット）
                fm["suppl_kind"] = "amendment"
                fm["amendment_law_id"] = normalized_id
                fm["amendment_law_title"] = amend_law_num

                # amend_law ネスト構造（将来の統合用）
                fm["amend_law"] = {
                    "num": amend_law_num,              # AmendLawNum 原文
                    "normalized_id": normalized_id,    # R3_L37 形式
                    "scope": "partial",                # 断片であることを明示
                    "parent_law_id": law_id,
                    "parent_law_name": law_name,
                }

            with open(file_path, "w", encoding="utf-8") as f:
                f.write("---\n")
                yaml.dump(fm, f, allow_unicode=True, default_flow_style=False)
                f.write("---\n\n")
                f.write(content)

    def _update_law_tier(self, md_path: Path, tier: int):
        if not md_path.exists(): 
            return
        
        # Simple read/regex replace to avoid parsing/dumping full yaml which might lose comments?
        # But yaml dump is safer for structure.
        # User said "metadata ... generated", I generated it with yaml.dump.
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read() # Read all, separate FM
        
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_str = parts[1]
                fm = yaml.safe_load(fm_str)
                if fm.get("tier", 0) < tier:
                    fm["tier"] = tier
                    new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False)
                    new_content = f"---{new_fm}---{parts[2]}"
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
