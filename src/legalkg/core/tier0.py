import yaml
from pathlib import Path
from typing import List, Dict
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
        
        # Prepare index map to save later
        id_to_name = {}

        from tqdm import tqdm
        for law in tqdm(law_list, desc="Generating Metadata"):
            law_name = self._process_law(law)
            law_id = law["LawId"]
            if law_name:
                id_to_name[law_id] = law_name

        # Save index
        with open(self.laws_dir / "index.json", "w", encoding="utf-8") as f:
            import json
            json.dump(id_to_name, f, ensure_ascii=False, indent=2)

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
        
        # Determine paths
        # Structure: Vault/laws/<LawName>/...
        # LawName is unique enough for now?
        # Collision handling: if exists and different ID -> LawName_ID?
        
        safe_title = sanitize_filename(law_name)
        if not safe_title:
             safe_title = f"Law_{law_id}" # fallback
        
        law_dir = self.laws_dir / safe_title
        
        # Check collision
        # If law_dir exists, check if it's the same law
        if law_dir.exists():
            # Check existing meta
            existing_md = law_dir / f"{safe_title}.md"
            if existing_md.exists():
                try:
                    with open(existing_md, "r", encoding="utf-8") as f:
                        content = f.read()
                        if content.startswith("---"):
                             # quick parse
                             pass # Ideally parse yaml, check ID
                except:
                    pass
            # If collision (different ID), append ID to dirname
            # Simpler: check if we processed this ID before?
            # Or just accept overwrite if same name for now?
            # User said "collisions are rare".
            # Let's trust unique names for now, or maybe append ID if needed later.
            pass

        law_dir.mkdir(parents=True, exist_ok=True)
        
        # Also clean up old ID directory if exists?
        # The user said "Change all".
        # We need to remove laws/<ID> if it exists.
        old_id_dir = self.laws_dir / law_id
        if old_id_dir.exists():
            import shutil
            shutil.rmtree(old_id_dir)

        # Generate YAML frontmatter
        fm = {
            "id": f"JPLAW:{law_id}",
            "type": "law",
            "egov_law_id": law_id,
            "law_no": law_no,
            "title": law_name,
            "promulgation_date": promulgation_date,
            "as_of": self.as_of,
            "tier": 0,
            "egov_class": egov_classes,
            "domain": domains,
            "tags": [law_name, "kind/law"],
            "links": {
                "egov": f"https://laws.e-gov.go.jp/law/{law_id}"
            }
        }
        
        # Write sanitized filename.md
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
            
        # Cleanup old law.md (inside new dir if any)
        old_path = law_dir / "law.md"
        if old_path.exists() and old_path != md_path:
            old_path.unlink()
            
        return safe_title

