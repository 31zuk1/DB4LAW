#!/usr/bin/env python3
"""
Migration script to add law_name property to all existing article files.
"""
from pathlib import Path
import yaml
import sys

def get_law_name(law_dir: Path) -> str:
    """Extract law name from the parent law's markdown file."""
    # Find the law's main markdown file (e.g., 刑法.md)
    law_files = list(law_dir.glob("*.md"))
    if not law_files:
        return ""
    
    law_file = law_files[0]  # Should be only one
    
    with open(law_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse frontmatter
    if not content.startswith('---'):
        return ""
    
    parts = content.split('---', 2)
    if len(parts) < 3:
        return ""
    
    frontmatter = yaml.safe_load(parts[1])
    return frontmatter.get('title', '')

def add_law_name_to_article(article_path: Path, law_name: str) -> bool:
    """Add law_name to an article's frontmatter."""
    with open(article_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse frontmatter
    if not content.startswith('---'):
        print(f"  ⚠️  No frontmatter in {article_path.name}")
        return False
    
    parts = content.split('---', 2)
    if len(parts) < 3:
        print(f"  ⚠️  Invalid frontmatter in {article_path.name}")
        return False
    
    frontmatter_str = parts[1]
    body = parts[2]
    
    # Parse YAML
    frontmatter = yaml.safe_load(frontmatter_str)
    
    # Check if law_name already exists
    if 'law_name' in frontmatter:
        print(f"  ⏭️  Already has law_name: {article_path.name}")
        return False
    
    # Add law_name
    frontmatter['law_name'] = law_name
    
    # Reconstruct file
    new_frontmatter = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)
    new_content = f"---\n{new_frontmatter}---{body}"
    
    # Write back
    with open(article_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"  ✅ Added law_name to {article_path.name}")
    return True

def process_law(law_dir: Path) -> tuple[int, int]:
    """Process all articles in a law directory."""
    law_name = get_law_name(law_dir)
    if not law_name:
        print(f"⚠️  Could not find law name for {law_dir.name}")
        return 0, 0
    
    print(f"\n📚 Processing: {law_name} ({law_dir.name})")
    
    articles_dir = law_dir / "articles"
    if not articles_dir.exists():
        print(f"  ⚠️  No articles directory")
        return 0, 0
    
    # Find all article markdown files
    article_files = list(articles_dir.rglob("*.md"))
    
    total = len(article_files)
    updated = 0
    
    for article_file in article_files:
        if add_law_name_to_article(article_file, law_name):
            updated += 1
    
    print(f"  📊 Updated {updated}/{total} articles")
    return total, updated

def main():
    vault_root = Path("Vault")
    laws_dir = vault_root / "laws"
    
    if not laws_dir.exists():
        print(f"❌ Laws directory not found: {laws_dir}")
        sys.exit(1)
    
    print("🚀 Starting migration: Adding law_name to article frontmatter")
    print(f"📁 Vault: {vault_root.absolute()}")
    
    total_articles = 0
    total_updated = 0
    
    # Process each law directory
    for law_dir in sorted(laws_dir.iterdir()):
        if not law_dir.is_dir():
            continue
        
        articles, updated = process_law(law_dir)
        total_articles += articles
        total_updated += updated
    
    print(f"\n✨ Migration complete!")
    print(f"📊 Total: {total_updated}/{total_articles} articles updated")

if __name__ == "__main__":
    main()
