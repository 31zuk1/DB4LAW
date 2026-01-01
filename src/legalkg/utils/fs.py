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
