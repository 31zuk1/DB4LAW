import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from typing import Dict, Optional, List
from .base import BaseClient
import logging
import re

logger = logging.getLogger(__name__)

class NDLClient(BaseClient):
    """
    Client for National Diet Library Search API (OpenSearch).
    Docs: https://ndlsearch.ndl.go.jp/api/opensearch
    """
    BASE_URL = "https://ndlsearch.ndl.go.jp/api/opensearch"

    def __init__(self):
        super().__init__(rate_limit_sec=1.0) # Polite 1s delay

    def fetch_law_metadata(self, law_number: str, law_title: str = "") -> Optional[Dict]:
        """
        Search NDL for the law by its number and return metadata.
        Args:
            law_number: e.g. "明治四十年法律第四十五号"
            law_title: e.g. "刑法"
        """
        params = {
            # "dgroup": "hourei", # Found to return 0 results often
            "any": law_number,
            "cnt": 5 
        }
        
        cache_key = f"ndl_{law_number}"
        
        try:
            # Use BaseClient.request which handles caching and rate limiting
            content = self.request(
                method="GET",
                url=self.BASE_URL,
                params=params,
                cache_key=cache_key,
                response_type="text"
            )
            if not content:
                return None
                
            return self._parse_response(content, law_number, law_title)
            
        except Exception as e:
            logger.error(f"NDL search failed for {law_number}: {e}")
            return None

    def _parse_response(self, xml_text: str, target_law_no: str, target_law_title: str) -> Optional[Dict]:
        try:
            root = ET.fromstring(xml_text)
            # Namespace map usually needed for RSS
            # <rss version="2.0" ... <channel><item>...
            # Items are the results.
            
            # Find the best matching item.
            channel = root.find("channel")
            if not channel:
                return None
            
            items = channel.findall("item")
            
            # 1. Exact law number match in title
            for item in items:
                title = item.find("title").text if item.find("title") is not None else ""
                if target_law_no in title:
                    return self._extract_metadata_from_item(item)
            
            # 2. Law title match in title (if law_title provided)
            if target_law_title:
                for item in items:
                    title = item.find("title").text if item.find("title") is not None else ""
                    if target_law_title == title or f" {target_law_title} " in f" {title} " or title.startswith(target_law_title):
                         return self._extract_metadata_from_item(item)
            
            # 3. Fallback to first item
            if items:
                logger.info(f"NDL: No exact match, using first: {items[0].find('title').text}")
                return self._extract_metadata_from_item(items[0])

            return None
            
        except ET.ParseError:
            logger.error("Failed to parse NDL XML")
            return None

    def _extract_metadata_from_item(self, item: ET.Element) -> Dict:
        """
        Extract extended metadata from RSS item.
        NDL returns dc:creator, dc:date etc.
        Legislative info might be in description or specific fields.
        
        Actually NDL "hourei" metadata in RSS is often limited.
        However, let's grab what we can.
        
        Common fields in NDL OpenSearch (hourei):
        - title
        - link
        - author (Proposer?)
        - pubDate (Promulgation?)
        - description (Abstract?)
        - dc:publisher (Diet?)
        """
        ns = {
            'dc': 'http://purl.org/dc/elements/1.1/',
            'openSearch': 'http://a9.com/-/spec/opensearchrss/1.0/',
            'dcterms': 'http://purl.org/dc/terms/' # sometimes used
        }
        
        # Helper to find with namespace
        def get_text(elem, tag, namespaces=ns):
            found = elem.find(tag, namespaces)
            return found.text if found is not None else None

        meta = {
            "source": "NDL",
            "url": item.find("link").text if item.find("link") is not None else None,
            "title_ndl": item.find("title").text,
        }
        
        # Proposer / Creator
        # In NDL Law, author often indicates "内閣" or "衆議院議員..."
        creator = get_text(item, "dc:creator") or get_text(item, "author")
        if creator:
            meta["proposer"] = creator
            
        # Date
        # pubDate in RSS is usually RFC822. 
        # dc:date might be ISO (YYYY-MM-DD)
        date = get_text(item, "dc:date")
        if date:
            meta["promulgation_date_ndl"] = date
            
        # Description often contains details
        desc = item.find("description").text
        if desc:
            meta["description"] = desc
            
        return meta
