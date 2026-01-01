from pathlib import Path

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"
DATA_DIR = PROJECT_ROOT / "data"

# e-Gov API
EGOV_API_BASE_URL = "https://laws.e-gov.go.jp/api/1"

# NDL
NDL_SEARCH_URL = "https://hourei.ndl.go.jp/api/hourei" # Placeholder if API exists, else scraping URL

# User Agent
USER_AGENT = "LegalKG-PoC/0.1.0"
