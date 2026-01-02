from src.legalkg.client.ndl import NDLClient
import logging
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO)

client = NDLClient()

# Test cases
queries = [
    "明治四十年法律第四十五号", # Penal Code
    "昭和二十一年憲法" # Constitution
]

for q in queries:
    print(f"\n--- Query: {q} ---")
    
    variants = [
        {"title": q, "dgroup": "hourei"},
        {"any": q},
        {"title": q}, 
    ]
    
    for params in variants:
        params["cnt"] = 5
        print(f"\n  Testing params: {params}")
        try:
            print(f"URL: {client.BASE_URL} params={params}")
            resp = client.session.get(client.BASE_URL, params=params)
            print(f"Status: {resp.status_code}")
            
            # Parse items
            try:
                root = ET.fromstring(resp.text)
                channel = root.find("channel")
                if channel:
                    items = channel.findall("item")
                    print(f"    Found {len(items)} items.")
                    for item in items:
                        t_elem = item.find("title") 
                        t = t_elem.text if t_elem is not None else "No Title"
                        print(f"    - Item Title: {t}")
                        
                        desc_elem = item.find("description")
                        d = desc_elem.text[:100] if desc_elem is not None else "No Desc"
                        print(f"      Desc: {d}")
                        
                        # Namespaces for dc
                        ns = {'dc': 'http://purl.org/dc/elements/1.1/'}
                        creator = item.find("dc:creator", ns)
                        c = creator.text if creator is not None else "No Creator"
                        print(f"      Creator: {c}")
                else:
                    print("    No channel found.")
            except Exception as e:
                print(f"    Parse Error: {e}")

        except Exception as e:
            print(f"    Request Error: {e}")
