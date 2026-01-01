# Legal Knowledge Graph PoC

LegalKG generates a knowledge graph of Japanese laws in Obsidian Vault (Markdown) format.

## Features
- **Tier 0**: Generates metadata for all current laws (~2000+).
- **Tier 1**: Generates individual article nodes for targeted laws.
- **Tier 2**: Extracts references between articles.
- **Enrichment**: Adds NDL (National Diet Library) data like bill submission info.

## Usage

### Setup
```bash
pip install -r requirements.txt
```

### Commands

#### 1. Tier 0 (Metadata)
Fetch law list and generate metadata nodes.
```bash
python -m legalkg build-tier0 --vault ./Vault --as-of 2025-12-30
```

#### 2. Tier 1 & 2 (Articles & Edges)
Generate articles and extract edges for specific laws.
```bash
# Create targets.yaml first
# - 321AC0000000000 (Example Law ID)
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges
```

#### 3. Enrichment
Fetch additional metadata from NDL.
```bash
python -m legalkg enrich-ndl --vault ./Vault --targets targets.yaml
```

## Data Sources
- **e-Gov Law API**: Source of law text and list.
- **National Diet Library (NDL)**: Source of legislative process data.

## License
MIT
