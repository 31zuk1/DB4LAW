import yaml
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set
from ..client.egov import EGovClient
from ..config import DATA_DIR

class Tier0Builder:
    def __init__(self, vault_root: Path, as_of: str):
        self.vault_root = vault_root
        self.as_of = as_of
        self.client = EGovClient()
        self.laws_dir = self.vault_root / "laws"
        self.class_to_domain = self._load_class_to_domain()
        self.domain_overrides = self._load_domain_overrides()

    def _load_class_to_domain(self) -> Dict[str, str]:
        path = DATA_DIR / "class_to_domain.yaml"
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_domain_overrides(self) -> Dict[str, List[str]]:
        path = DATA_DIR / "domain_overrides.yaml"
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}
    
    def _map_domains(self, law_id: str, egov_classes: List[str]) -> List[str]:
        # Check overrides first
        if law_id in self.domain_overrides:
            return self.domain_overrides[law_id]
        
        domains = set()
        for cls in egov_classes:
            if cls in self.class_to_domain:
                domains.add(self.class_to_domain[cls])
            else:
                domains.add("その他") # Fallback
        
        return sorted(list(domains))

    def build(self):
        print("Fetching law list from e-Gov...")
        law_list = self.client.fetch_law_list()
        
        print(f"Found {len(law_list)} laws.")

        from tqdm import tqdm
        for law in tqdm(law_list, desc="Generating Metadata"):
            self._process_law(law)

    def _process_law(self, law_data: Dict):
        # Extract fields
        law_id = law_data.get("LawId")
        law_no = law_data.get("LawNo")
        law_name = law_data.get("LawName")
        promulgation_date = law_data.get("PromulgationDate")
        
        # e-Gov List XML doesn't seem to have per-law Category easily accessible
        # We will use empty list for now, or map from LawNo if possible.
        egov_classes = []

        domains = self._map_domains(law_id, egov_classes)

        from ..utils.fs import sanitize_filename
        
        # Create directory
        law_dir = self.laws_dir / law_id
        law_dir.mkdir(parents=True, exist_ok=True)

        # Generate YAML frontmatter
        fm = {
            "id": f"JPLAW:{law_id}",
            "egov_law_id": law_id,
            "law_no": law_no,
            "title": law_name,
            "promulgation_date": promulgation_date,
            "as_of": self.as_of,
            "tier": 0,
            "egov_class": egov_classes,
            "domain": domains,
            "links": {
                "egov": f"https://laws.e-gov.go.jp/law/{law_id}"
            }
        }
        
        # Write sanitized filename.md
        safe_title = sanitize_filename(law_name)
        if not safe_title:
             safe_title = "law" # fallback
             
        md_path = law_dir / f"{safe_title}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.dump(fm, f, allow_unicode=True, default_flow_style=False)
            f.write("---\n\n")
            f.write(f"# {law_name}\n\n")
            f.write("## Metadata\n")
            f.write(f"- Law ID: `{law_id}`\n")
            f.write(f"- Law No: {law_no}\n")
            f.write(f"- Promulgation Date: {promulgation_date}\n")
            
        # Cleanup old law.md
        old_path = law_dir / "law.md"
        if old_path.exists() and old_path != md_path:
            old_path.unlink()

