from .base import BaseClient
from ..config import EGOV_API_BASE_URL
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class EGovClient(BaseClient):
    def __init__(self):
        super().__init__(rate_limit_sec=0.5) # e-Gov can handle faster, but being polite
        self.base_url = EGOV_API_BASE_URL

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
            
            # Category might be in ApplData or separate. 
            # In the XML sample: <ApplData><Category>1</Category><LawNameListInfo>...</LawNameListInfo>...</ApplData>
            # It seems Category applies to the whole list? Or maybe LawNameListInfo has it?
            # The sample shows Category outside LawNameListInfo.
            # Assuming Category 1 means "Current Laws"?
            # We'll stick to extracting what's in LawNameListInfo for now.
            laws.append(law)
            
        return laws

    def fetch_law_xml(self, law_id: str) -> str:
        """
        Fetches the XML content of a specific law (lawdata).
        """
        url = f"{self.base_url}/lawdata/{law_id}"
        # Cache key includes law_id
        return self.request("GET", url, cache_key=f"egov_law_{law_id}", response_type="text")
