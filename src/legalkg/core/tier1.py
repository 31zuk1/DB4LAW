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
            from .tier2 import EdgeExtractor
            extractor = EdgeExtractor()
            all_edges = []
            
            # Iterate over generated files to extract edges?
            # Or extract during XML processing?
            # XML processing has the structure.
            
            # Let's do it during XML processing or iterate text.
            # Since we iterate parts, we can accumulate edges.
            pass # See below for actual integration in _process_part
            
        articles_dir = law_dir / "articles"
        articles_dir.mkdir(exist_ok=True)
        (articles_dir / "main").mkdir(exist_ok=True)
        (articles_dir / "suppl").mkdir(exist_ok=True)

        self._process_part(soup.find("MainProvision"), law_id, articles_dir / "main", "main", extract_edges, all_edges if extract_edges else None, law_name=law_name)
        
        # Handle multiple SupplProvision
        for i, spl in enumerate(soup.find_all("SupplProvision")):
            amend_num = spl.get("AmendLawNum", f"init_{i}")
            safe_amend = re.sub(r'[^\w\-]', '_', amend_num)
            
            # Check if this provision has articles
            has_articles = bool(spl.find("Article"))
            
            if has_articles:
                # Use subdirectory
                out_dir = articles_dir / "suppl" / safe_amend
                out_dir.mkdir(exist_ok=True, parents=True)
                self._process_part(spl, law_id, out_dir, "suppl", extract_edges, all_edges if extract_edges else None, file_key_override=safe_amend, law_name=law_name)
            else:
                # Use direct file under suppl/
                # pass custom optional filename to _process_part?
                # or modify _process_part to handle it.
                # Let's pass 'file_key_override' to process_part
                out_dir = articles_dir / "suppl"
                self._process_part(spl, law_id, out_dir, "suppl", extract_edges, all_edges if extract_edges else None, file_key_override=safe_amend)

        if extract_edges and all_edges:
            with open(law_dir / "edges.jsonl", "w", encoding="utf-8") as f:
                for edge in all_edges:
                    f.write(json.dumps(edge, ensure_ascii=False) + "\n")

        # Update law.md content tier -> 2 if edges extracted
        final_tier = 2 if extract_edges else 1
        if law_md_path:
            self._update_law_tier(law_md_path, final_tier)

    def _process_part(self, container, law_id: str, out_dir: Path, part_type: str, extract_edges: bool = False, edge_list: List = None, file_key_override: str = None, law_name: str = ""):
        if not container:
            return

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
                
                content = f"# 附則\n\n"
                full_text_for_edge = ""
                
                for p in direct_paragraphs:
                    p_num = p.find("ParagraphNum")
                    p_num_text = p_num.text if p_num else ""
                    
                    sentences = p.find_all("Sentence")
                    text = "".join([s.text for s in sentences])
                    
                    content += f"## {p_num_text}\n{text}\n\n"
                    full_text_for_edge += text + "\n"
                    
                    items = p.find_all("Item")
                    for item in items:
                        i_title = item.find("ItemTitle")
                        i_title_text = i_title.text if i_title else ""
                        i_sentences = item.find_all("Sentence")
                        i_text = "".join([s.text for s in i_sentences])
                        content += f"- {i_title_text} {i_text}\n"
                        full_text_for_edge += i_text + "\n"

                # Frontmatter
                node_id = f"JPLAW:{law_id}#{part_type}#Provision"
                fm = {
                    "id": node_id,
                    "law_id": law_id,
                    "law_name": law_name,
                    "part": part_type,
                    "article_num": "Provision",
                    "heading": "附則"
                }

                # Extract Edges
                if extract_edges and edge_list is not None:
                    from .tier2 import EdgeExtractor
                    extractor = EdgeExtractor()
                    edges = extractor.extract_refs(full_text_for_edge, node_id)
                    edge_list.extend(edges)

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
            
            # Intuitive file naming: Article_1, Article_1_2
            safe_num = num.replace("_", "_") # already _ in XML usually?
            # XML Num is usually "1", "1_2"
            
            # If we are in a checked-in subdirectory for suppl, we might want to keep Article_1.md
            # But user complained about collision.
            # Collision only happens if they search by filename and both are "Article_1.md".
            # If we prefix with AmendLawNum, it becomes unique.
            
            if file_key_override and "suppl" in str(out_dir):
                 # This branch shouldn't be reached if we are using subdir based on previous logic?
                 # Wait, logic above:
                 # if has_articles: out_dir = .../suppl/safe_amend
                 # if not has_articles: out_dir = .../suppl, file_key_override=safe_amend
                 
                 # So if has_articles, out_dir already includes safe_amend directory.
                 # User says: articles/suppl/平成.../Article_1.md vs articles/main/Article_1.md
                 # The user wants unique FILENAMES even across folders?
                 # "Search problem" implies flat file search.
                 
                 # So we should prepend the safe_amend to the filename itself?
                 # Even inside the folder? Or maybe we don't need the folder if we have unique filenames?
                 # But folder is good for grouping.
                 
                 # Let's verify if we can pass safe_amend even when using subdir.
                 # We need to change the call in build() first.
                 pass

            base_name = f"Article_{safe_num}"
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
            
            full_text_for_edge = ""
            
            paragraphs = art.find_all("Paragraph")
            for p in paragraphs:
                p_num = p.find("ParagraphNum")
                p_num_text = p_num.text if p_num else ""
                
                sentences = p.find_all("Sentence")
                text = "".join([s.text for s in sentences])
                
                content += f"## {p_num_text}\n{text}\n\n"
                full_text_for_edge += text + "\n"
                
                items = p.find_all("Item")
                for item in items:
                    i_title = item.find("ItemTitle")
                    i_title_text = i_title.text if i_title else ""
                    i_sentences = item.find_all("Sentence")
                    i_text = "".join([s.text for s in i_sentences])
                    content += f"- {i_title_text} {i_text}\n"
                    full_text_for_edge += i_text + "\n"
            
            # Frontmatter
            node_id = f"JPLAW:{law_id}#{part_type}#{num}"
            fm = {
                "id": node_id,
                "law_id": law_id,
                "law_name": law_name,
                "part": part_type,
                "article_num": num,
                "heading": caption_text
            }
            
            # Extract Edges
            if extract_edges and edge_list is not None:
                from .tier2 import EdgeExtractor
                # Re-instantiate or pass? Ideally pass singleton but cheap enough
                extractor = EdgeExtractor()
                edges = extractor.extract_refs(full_text_for_edge, node_id)
                edge_list.extend(edges)

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
