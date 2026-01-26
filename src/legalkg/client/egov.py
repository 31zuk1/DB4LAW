"""
e-Gov API Client - v2 Native Implementation

v2 API の JSON を SSOT として直接返却する設計。
XML 変換は廃止。
"""
from .base import BaseClient
from ..config import EGOV_API_V2_BASE_URL
from typing import List, Dict, Any, Optional
import logging
import requests
import json

logger = logging.getLogger(__name__)


class EGovClient(BaseClient):
    """e-Gov API v2 クライアント（JSON ネイティブ）"""

    def __init__(self):
        super().__init__(rate_limit_sec=0.5)
        self.base_url_v2 = EGOV_API_V2_BASE_URL
        self.timeout = 60

    def fetch_law_list(self) -> List[Dict[str, Any]]:
        """
        法令一覧を v2 API から取得。

        Returns:
            法令情報のリスト（LawId, LawName 等を含む dict）
        """
        # v2 API の法令一覧エンドポイント
        url = f"{self.base_url_v2}/laws"
        cache_key = "egov_law_list_v2_json"
        cache_path = self._get_cache_path(cache_key)
        cached_data = self._load_cache(cache_path)

        if cached_data is not None:
            logger.debug(f"Cache hit: {cache_key}")
            return json.loads(cached_data)

        try:
            logger.info(f"Fetching law list from v2 API: {url}")
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            # v2 API の応答形式に応じて変換
            laws = []
            for item in data.get("laws", []):
                laws.append({
                    "LawId": item.get("law_id", ""),
                    "LawName": item.get("law_name", ""),
                    "LawNo": item.get("law_num", ""),
                    "PromulgationDate": item.get("promulgation_date", ""),
                })

            self._save_cache(cache_path, json.dumps(laws, ensure_ascii=False))
            return laws

        except Exception as e:
            logger.error(f"Failed to fetch law list: {e}")
            raise

    def fetch_law_data(self, law_id: str) -> Dict[str, Any]:
        """
        法令データを v2 API から JSON として取得。

        Args:
            law_id: 法令ID（例: 337AC0000000139）

        Returns:
            law_full_text を含む JSON dict

        Raises:
            RuntimeError: 取得に失敗した場合
        """
        cache_key = f"egov_law_v2_{law_id}"
        cache_path = self._get_cache_path(cache_key)
        cached_data = self._load_cache(cache_path)

        if cached_data is not None:
            logger.debug(f"Cache hit: {cache_key}")
            return json.loads(cached_data)

        url = f"{self.base_url_v2}/law_data/{law_id}"

        try:
            logger.info(f"Fetching law data (v2): {url}")
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()

            data = resp.json()

            if "law_full_text" not in data:
                raise RuntimeError(f"v2 API returned no law_full_text for {law_id}")

            logger.info(f"Successfully fetched {law_id} via v2 API")
            self._save_cache(cache_path, json.dumps(data, ensure_ascii=False))
            return data

        except requests.exceptions.Timeout:
            raise RuntimeError(f"v2 API timeout for {law_id} (timeout={self.timeout}s)")
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"v2 API HTTP error for {law_id}: {e}")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"v2 API connection error for {law_id}: {e}")

    def get_law_full_text(self, law_id: str) -> Dict[str, Any]:
        """
        law_full_text（JSON ツリー）を直接取得。

        Args:
            law_id: 法令ID

        Returns:
            law_full_text の JSON ツリー（tag/attr/children 構造）
        """
        data = self.fetch_law_data(law_id)
        return data["law_full_text"]
