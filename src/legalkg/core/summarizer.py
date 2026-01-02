from pathlib import Path
from typing import List
import logging
import yaml
from ..client.openai_client import OpenAIClient
from ..utils.fs import find_law_dir_by_id, get_law_node_file

logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self, vault_root: Path, targets_path: Path, force: bool = False):
        """
        Initialize the Summarizer.
        
        Args:
            vault_root: Path to the Vault root directory.
            targets_path: Path to targets.yaml file.
            force: If True, regenerate summaries even if they already exist.
        """
        self.vault_root = vault_root
        self.laws_dir = self.vault_root / "laws"
        self.force = force
        self.client = OpenAIClient()
        self.targets = self._load_targets(targets_path)
    
    def _load_targets(self, path: Path) -> List[str]:
        """Load target law IDs from YAML file."""
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "targets" in data:
                return data["targets"]
            return []
    
    def summarize(self):
        """Process all target laws and generate summaries for their articles."""
        print(f"Summarizing {len(self.targets)} laws...")
        
        from tqdm import tqdm
        total_articles = 0
        total_summarized = 0
        
        for law_id in tqdm(self.targets, desc="Processing Laws"):
            articles_processed, articles_summarized = self._summarize_law(law_id)
            total_articles += articles_processed
            total_summarized += articles_summarized
        
        print(f"Summarization complete. Processed {total_articles} articles, generated {total_summarized} new summaries.")
    
    def _summarize_law(self, law_id: str) -> tuple[int, int]:
        """
        Summarize all articles in a law.
        
        Returns:
            Tuple of (total_articles_processed, articles_summarized)
        """
        law_dir = find_law_dir_by_id(self.laws_dir, law_id)
        if not law_dir:
            logger.warning(f"Law directory not found for {law_id}")
            return 0, 0
        
        # Find all article markdown files
        article_files = []
        
        # Check for English structure: articles/main, articles/suppl
        articles_dir = law_dir / "articles"
        if articles_dir.exists():
            for subdir in ["main", "suppl"]:
                subdir_path = articles_dir / subdir
                if subdir_path.exists():
                    article_files.extend(subdir_path.rglob("*.md"))

        # Check for Japanese structure: 本文, 附則 (directly under law_dir)
        for jp_dir_name in ["本文", "附則"]:
            jp_path = law_dir / jp_dir_name
            if jp_path.exists():
                article_files.extend(jp_path.rglob("*.md"))
        
        if not article_files:
            logger.warning(f"No article files found for {law_id}")
            return 0, 0
        
        articles_processed = 0
        articles_summarized = 0
        
        for article_file in article_files:
            articles_processed += 1
            if self._summarize_article(article_file):
                articles_summarized += 1
        
        return articles_processed, articles_summarized
    
    def _summarize_article(self, article_path: Path) -> bool:
        """
        Generate and append summary to an article file.
        
        Returns:
            True if a new summary was generated, False otherwise.
        """
        try:
            with open(article_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Check if summary already exists
            if "## AI要約" in content and not self.force:
                logger.debug(f"Summary already exists for {article_path.name}, skipping")
                return False
            
            # Parse frontmatter and content
            if not content.startswith("---"):
                logger.warning(f"No frontmatter found in {article_path}")
                return False
            
            parts = content.split("---", 2)
            if len(parts) < 3:
                logger.warning(f"Invalid frontmatter structure in {article_path}")
                return False
            
            frontmatter_str = parts[1]
            body = parts[2]
            
            # Extract title from frontmatter
            fm = yaml.safe_load(frontmatter_str)
            article_title = fm.get("heading", "")
            
            # Extract text content (remove markdown headers)
            text_content = body.replace("## AI要約", "").strip()
            
            # Generate summary
            print(f"Summarizing {article_path.name}...")
            summary = self.client.generate_summary(text_content, article_title)
            
            # Append summary to content
            if "## AI要約" in content:
                # Replace existing summary (even if empty)
                import re
                # Match "## AI要約" followed by anything (including nothing) until next ## or end
                new_content = re.sub(
                    r'## AI要約\s*.*?(?=\n##|\Z)',
                    f'## AI要約\n{summary}',
                    content,
                    flags=re.DOTALL
                )
            else:
                # Append new summary
                new_content = content.rstrip() + f"\n\n## AI要約\n{summary}\n"
            
            # Write back
            with open(article_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            logger.info(f"Generated summary for {article_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to summarize {article_path}: {e}")
            return False
