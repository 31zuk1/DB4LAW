import os
from typing import Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv
import time
import logging

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, rate_limit_delay: float = 15.0):
        """
        Initialize Gemini API client.
        
        Args:
            api_key: Optional API key. If not provided, will load from environment.
            rate_limit_delay: Delay between API calls in seconds (default 15s for free tier).
        """
        # Load .env file if exists
        load_dotenv()
        
        # Get API key
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables or .env file")
        
        # Initialize client
        self.client = genai.Client(api_key=self.api_key)
        
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()
    
    def generate_summary(self, article_text: str, article_title: str = "") -> str:
        """
        Generate a plain-language summary of a legal article.
        
        Args:
            article_text: The text of the legal article.
            article_title: Optional title/heading of the article.
            
        Returns:
            A plain-language summary in Japanese.
        """
        self._rate_limit()
        
        prompt = f"""以下の法律条文を、法律の専門知識がない一般の人にもわかりやすい日本語で要約してください。

条文タイトル: {article_title}

条文内容:
{article_text}

要約の要件:
- 専門用語を避け、平易な言葉で説明してください
- 箇条書きではなく、自然な文章で記述してください
- 2-3文程度の簡潔な要約にしてください
- 「この条文は」などの前置きは不要です。内容を直接説明してください"""

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"要約の生成に失敗しました: {str(e)}"
