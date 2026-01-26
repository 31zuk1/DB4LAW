from .base import BaseClient
from ..config import EGOV_API_BASE_URL, EGOV_API_V2_BASE_URL
from typing import List, Dict, Any, Optional
import logging
import requests

logger = logging.getLogger(__name__)


def json_to_xml(node: Any) -> str:
    """
    Convert v2 API JSON tree structure to XML string.

    v2 format:
    {
        "tag": "Law",
        "attr": {"Era": "Showa", ...},
        "children": [
            {"tag": "LawNum", "attr": {}, "children": ["昭和三十七年..."]},
            ...
        ]
    }

    Returns:
        XML string compatible with v1 API response
    """
    if isinstance(node, str):
        # Text node - escape XML special characters
        return (node
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

    if not isinstance(node, dict):
        return str(node)

    tag = node.get("tag", "")
    attr = node.get("attr", {})
    children = node.get("children", [])

    # Build attribute string
    attr_str = ""
    if attr:
        attr_parts = []
        for k, v in attr.items():
            # Escape attribute values
            escaped_v = str(v).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
            attr_parts.append(f'{k}="{escaped_v}"')
        attr_str = " " + " ".join(attr_parts)

    # Build children content
    if not children:
        return f"<{tag}{attr_str}/>"

    children_str = "".join(json_to_xml(child) for child in children)
    return f"<{tag}{attr_str}>{children_str}</{tag}>"


class EGovClient(BaseClient):
    def __init__(self):
        super().__init__(rate_limit_sec=0.5)
        self.base_url = EGOV_API_BASE_URL
        self.base_url_v2 = EGOV_API_V2_BASE_URL
        # Timeout settings (seconds)
        self.timeout_v2 = 60  # v2 API timeout
        self.timeout_v1 = 180  # v1 API timeout (longer as fallback)

    def fetch_law_list(self) -> List[Dict[str, Any]]:
        """
        Fetches the list of all laws (lawlists/1) and parses XML.
        Returns a list of dicts with LawId, LawName, etc.
        """
        url = f"{self.base_url}/lawlists/1"
        xml_content = self.request("GET", url, cache_key="egov_law_list_v1_xml", response_type="text")

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(xml_content, "xml")

        laws = []
        for info in soup.find_all("LawNameListInfo"):
            law = {}
            for child in info.children:
                if child.name:
                    law[child.name] = child.text
            laws.append(law)

        return laws

    def fetch_law_xml(self, law_id: str) -> str:
        """
        Fetches the XML content of a specific law.

        Strategy:
        1. Try v2 API first (faster, more reliable)
        2. Fall back to v1 API if v2 fails
        3. Raise error if both fail
        """
        # Check cache first (uses v1 cache key for compatibility)
        cache_key = f"egov_law_{law_id}"
        cache_path = self._get_cache_path(cache_key)
        cached_data = self._load_cache(cache_path)
        if cached_data is not None:
            logger.debug(f"Cache hit: {cache_key}")
            return cached_data

        # Try v2 API first
        xml_content = self._fetch_law_xml_v2(law_id)

        if xml_content is None:
            # Fall back to v1 API
            logger.info(f"Falling back to v1 API for {law_id}")
            xml_content = self._fetch_law_xml_v1(law_id)

        if xml_content is None:
            raise RuntimeError(f"Failed to fetch law {law_id} from both v1 and v2 APIs")

        # Cache the result
        self._save_cache(cache_path, xml_content)
        return xml_content

    def _fetch_law_xml_v2(self, law_id: str) -> Optional[str]:
        """
        Fetch law data from v2 API and convert to XML.

        Returns:
            XML string if successful, None if failed
        """
        url = f"{self.base_url_v2}/law_data/{law_id}"

        try:
            logger.info(f"Fetching (v2): {url}")
            resp = self.session.get(url, timeout=self.timeout_v2)
            resp.raise_for_status()

            data = resp.json()
            law_full_text = data.get("law_full_text")

            if not law_full_text:
                logger.warning(f"v2 API returned no law_full_text for {law_id}")
                return None

            # Convert JSON tree to XML
            xml_content = json_to_xml(law_full_text)

            # Add XML declaration
            xml_content = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_content}'

            logger.info(f"Successfully fetched {law_id} via v2 API")
            return xml_content

        except requests.exceptions.Timeout:
            logger.warning(f"v2 API timeout for {law_id} (timeout={self.timeout_v2}s)")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"v2 API connection error for {law_id}: {e}")
            return None
        except requests.exceptions.HTTPError as e:
            logger.warning(f"v2 API HTTP error for {law_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"v2 API unexpected error for {law_id}: {type(e).__name__}: {e}")
            return None

    def _fetch_law_xml_v1(self, law_id: str) -> Optional[str]:
        """
        Fetch law data from v1 API (legacy fallback).

        Returns:
            XML string if successful, None if failed
        """
        url = f"{self.base_url}/lawdata/{law_id}"

        try:
            logger.info(f"Fetching (v1): {url}")
            resp = self.session.get(url, timeout=self.timeout_v1)
            resp.raise_for_status()

            logger.info(f"Successfully fetched {law_id} via v1 API")
            return resp.text

        except requests.exceptions.Timeout:
            logger.error(f"v1 API timeout for {law_id} (timeout={self.timeout_v1}s)")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"v1 API connection error for {law_id}: {e}")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"v1 API HTTP error for {law_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"v1 API unexpected error for {law_id}: {type(e).__name__}: {e}")
            return None
