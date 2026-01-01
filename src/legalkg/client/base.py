import hashlib
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any
import logging
from ..config import CACHE_DIR, USER_AGENT

logger = logging.getLogger(__name__)

class BaseClient:
    def __init__(self, cache_dir: Path = CACHE_DIR, rate_limit_sec: float = 1.0):
        self.cache_dir = cache_dir
        self.rate_limit_sec = rate_limit_sec
        self.last_request_time = 0.0
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _get_cache_path(self, key: str) -> Path:
        hashed = hashlib.md5(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{hashed}.json"

    def _load_cache(self, cache_path: Path) -> Optional[Any]:
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Corrupted cache file: {cache_path}")
        return None

    def _save_cache(self, cache_path: Path, data: Any):
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def request(self, method: str, url: str, params: Optional[Dict] = None, cache_key: Optional[str] = None, response_type: str = "json") -> Any:
        if cache_key:
            cache_path = self._get_cache_path(cache_key)
            cached_data = self._load_cache(cache_path)
            if cached_data is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_data

        # Rate limiting
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_sec:
            time.sleep(self.rate_limit_sec - elapsed)

        logger.info(f"Fetching: {url}")
        try:
            resp = self.session.request(method, url, params=params)
            resp.raise_for_status()
            self.last_request_time = time.time()

            if response_type == "json":
                data = resp.json()
            else:
                data = resp.text

            if cache_key:
                self._save_cache(cache_path, data)
            
            return data
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise
