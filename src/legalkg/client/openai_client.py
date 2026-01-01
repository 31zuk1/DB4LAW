import os
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv
import time
import logging

logger = logging.getLogger(__name__)

class OpenAIClient:
    def __init__(self, api_key: Optional[str] = None, rate_limit_delay: float = 0.5):
        """
        Initialize OpenAI API client.
        
        Args:
            api_key: Optional API key. If not provided, will load from environment.
            rate_limit_delay: Delay between API calls in seconds.
        """
        # Load .env file if exists
        load_dotenv()
        
        # Get API key
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables or .env file")
        
        # Initialize client
        self.client = OpenAI(api_key=self.api_key)
        
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
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "あなたは法律を一般の人にわかりやすく説明する専門家です。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
            logger.debug(f"API Response: {response}")
            logger.debug(f"Choices: {response.choices}")
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
            else:
                logger.error(f"Empty response from API: {response}")
                return "要約の生成に失敗しました: APIからの応答が空でした"
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"要約の生成に失敗しました: {str(e)}"
