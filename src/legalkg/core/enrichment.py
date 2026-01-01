from pathlib import Path
from typing import List
import yaml
import logging
from ..client.ndl import NDLClient
from tqdm import tqdm

logger = logging.getLogger(__name__)

class Enricher:
    def __init__(self, vault_root: Path, targets_path: Path):
        self.vault_root = vault_root
        self.targets = self._load_targets(targets_path)
        self.client = NDLClient()
        self.laws_dir = self.vault_root / "laws"

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

    def enrich(self):
        print(f"Enriching {len(self.targets)} laws via NDL...")
        if not self.targets:
            print("No targets provided/found.")
            return

        success_count = 0
        
        for law_id in tqdm(self.targets, desc="Enriching (NDL)"):
            try:
                if self._enrich_law(law_id):
                    success_count += 1
            except Exception as e:
                logger.error(f"Enrichment failed for {law_id}: {e}")
        
        print(f"Enrichment completed. Updated {success_count}/{len(self.targets)} laws.")

    def _enrich_law(self, law_id: str) -> bool:
        from ..utils.fs import get_law_node_file
        
        law_dir = self.laws_dir / law_id
        law_md_path = get_law_node_file(law_dir)
        
        if not law_md_path or not law_md_path.exists():
            return False
        
        # Read current metadata
        with open(law_md_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        fm = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1])
                body = parts[2]
        
        law_no = fm.get("law_no")
        if not law_no:
            return False
            
        # Skip if already enriched? (Optional)
        # if "legislative_origin" in fm: return True
        
        # Fetch NDL
        law_title = fm.get("title", "")
        meta = self.client.fetch_law_metadata(law_no, law_title)
        if not meta:
            logger.info(f"NDL: No data found for {law_no} ({law_id})")
            return False
            
        # Merge metadata
        # Add to 'legislative_origin' or similar
        fm["legislative_origin"] = meta
        
        # Best effort cabinet matching? (Not implemented yet, just raw NDL)
        
        # Write back
        new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False)
        with open(law_md_path, "w", encoding="utf-8") as f:
            f.write(f"---\n{new_fm}---\n{body}")
            
        return True
