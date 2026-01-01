from pathlib import Path
import re
from typing import Optional

def sanitize_filename(name: str) -> str:
    """
    Sanitize a string to be safe for filenames.
    Preserves Japanese characters but removes slashes, colons, etc.
    """
    # Remove chars invalid in Windows/Mac/Linux filenames
    safe = re.sub(r'[\\/*?:"<>|]', '_', name)
    # Trim whitespace and dots
    safe = safe.strip().strip('.')
    return safe

def get_law_node_file(law_dir: Path) -> Optional[Path]:
    """
    Find the main law node markdown file in the law directory.
    It expects single .md file at the root of law_dir, excluding 'law.md' if we are migrating,
    or just any .md file that looks like a law node.
    
    Tier 0 generates <Title>.md.
    """
    if not law_dir.exists():
        return None
        
    # List .md files
    md_files = list(law_dir.glob("*.md"))
    
    # Exclude files that shouldn't be main node if any (unlikely in this structure)
    # But filtering out if multiple found?
    # Ideally there is only one.
    if not md_files:
        return None
        
    # Return the first one found?
    # Or prioritize non-law.md if both exist (migration)?
    
    # If file with Law ID name exists? 
    # Let's just return the first one for now, assuming 1:1 map.
    return md_files[0]

def find_law_dir_by_id(laws_root: Path, law_id: str) -> Optional[Path]:
    """
    Find the law directory given the logic that we use LawName as dir name.
    Since we don't store ID->Name map, we might need to search?
    OR, we assume the caller knows the mapping?
    
    Processing in Tier1 usually starts with ID.
    We need a way to find the folder from ID.
    
    Option 1: Search all folders (Slow?) - 8000 folders.
    Option 2: Tier1 should pre-load ID->Name map from Tier0 source or cache?
              But Tier0 source comes from API list.
    Option 3: We grep 'id: JPLAW:X' ?
    
    Better approach for optimization:
    - Tier0 generates an index file (id_to_path.json).
    - Tier1 reads it.
    
    For now, let's just implement a brute-force search helper or require Name from caller.
    """
    import json
    index_path = laws_root / "index.json"
    if index_path.exists():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
                if law_id in index:
                    return laws_root / index[law_id]
        except Exception:
            pass
            
    # Fallback if index not found or id not in index
    # Brute force search? Or just fail?
    # Tier 1 should run after Tier 0, so index SHOULD exist.
    # If not, maybe we can't find it easily.
    return None
