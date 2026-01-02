from src.legalkg.client.egov import EGovClient
from src.legalkg.core.tier2 import EdgeExtractor
from bs4 import BeautifulSoup
import re

client = EGovClient()
# Penal Code
law_id = "140AC0000000045"
xml_text = client.fetch_law_xml(law_id)
soup = BeautifulSoup(xml_text, "xml")

articles = soup.find_all("Article")
print(f"Found {len(articles)} articles.")

extractor = EdgeExtractor()

for i, art in enumerate(articles):
    text = art.get_text()
    matches = extractor.ref_pattern.findall(text)
    if matches:
        print(f"Article {art.get('Num')}: Found {len(matches)} matches: {matches}")
        # Print snippet
        print(f"Snippet: {text[:100]}...")
    
    if i > 20 and not matches:
        # Check if we should have found something
        if "条" in text:
             print(f"Article {art.get('Num')} has '条' but no match. Text: {text[:50]}...")
    
    if i > 50: break
