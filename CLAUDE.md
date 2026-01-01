# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LegalKG generates a knowledge graph of Japanese laws in Obsidian Vault format. It fetches law data from e-Gov API, parses legal text into structured nodes, extracts cross-references, and enriches with National Diet Library metadata.

## Common Commands

### Setup
```bash
pip install -r requirements.txt
# OR for development
pip install -e .
```

### Build Commands

**Tier 0 - Generate metadata for all laws (~2000+):**
```bash
python -m legalkg build-tier0 --vault ./Vault --as-of 2025-12-30
```
Runtime: ~1 hour due to rate limiting (0.5s between requests)

**Tier 1 - Generate article nodes for specific laws:**
```bash
# First edit targets.yaml to specify law IDs
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml
```

**Tier 1+2 - Articles + reference extraction:**
```bash
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges
```

**Enrichment - Add NDL legislative metadata:**
```bash
python -m legalkg enrich-ndl --vault ./Vault --targets targets.yaml
```

### Testing Commands

**Run unit tests:**
```bash
pytest
```

**Debug NDL API queries:**
```bash
python debug_ndl.py
```

**Test reference extraction regex:**
```bash
python debug_regex.py
```

## Architecture

### Three-Tier Data Model

The project uses a progressive enrichment architecture:

1. **Tier 0** (`src/legalkg/core/tier0.py`): Fetches law list from e-Gov API and generates metadata files for ~2000+ laws
   - Output: `Vault/laws/{LAW_ID}/{title}.md` with YAML frontmatter

2. **Tier 1** (`src/legalkg/core/tier1.py`): Parses XML for targeted laws and extracts individual articles
   - Output: `articles/main/Article_{N}.md` and `articles/suppl/Article_{N}.md`

3. **Tier 2** (`src/legalkg/core/tier2.py`): Extracts cross-references between articles using regex
   - Pattern: `第{kanji_numerals}条` (e.g., 第十九条 → Article 19)
   - Output: `edges.jsonl` containing reference graph edges

### Client-Cache Pattern

All API clients extend `BaseClient` (`src/legalkg/client/base.py`):
- MD5-based file caching in `cache/` directory (no TTL)
- Automatic rate limiting (0.5s for e-Gov, 1.0s for NDL)
- Session reuse for connection pooling

**Key clients:**
- `EgovClient` (`src/legalkg/client/egov.py`): Fetches law list and full XML
- `NdlClient` (`src/legalkg/client/ndl.py`): Queries legislative process metadata

### Node ID Schema

- **Law:** `JPLAW:{LAW_ID}` (e.g., `JPLAW:140AC0000000045`)
- **Article:** `JPLAW:{LAW_ID}#{part}#{article_num}` (e.g., `JPLAW:140AC0000000045#main#1`)
- **Sub-article:** Uses underscore notation (e.g., `#main#19_3` for Article 19-3)

### Domain Classification

Laws are categorized using two YAML files in `data/`:
- `class_to_domain.yaml`: Maps e-Gov classifications to legal domains (36 mappings)
- `domain_overrides.yaml`: Manual overrides for specific laws

**Domains:** 民事法, 刑事法, 公法, 税法, 経済法, 社会法, 環境法, 行政法, 憲法・公法

### Kanji Numeral Processing

The `kanji_to_int()` function (`src/legalkg/utils/numerals.py`) converts Japanese numerals to integers:
- Simple: 一 → 1, 十 → 10
- Complex: 二十三 → 23, 百二十 → 120
- Sub-articles: 十九の三 → "19_3"

Used extensively in reference extraction to normalize article numbers.

### Output Format

**Law metadata file:**
```yaml
---
id: JPLAW:140AC0000000045
egov_law_id: 140AC0000000045
law_no: 明治四十年法律第四十五号
title: 刑法
tier: 2
domain: []
---

# 刑法
...
```

**Edge file (edges.jsonl):**
```json
{"from": "JPLAW:140AC0000000045#main#1", "to": "JPLAW:140AC0000000045#main#19", "type": "refers_to", "evidence": "第十九条", "confidence": 0.9, "source": "regex_v1"}
```

## Key Files

- `src/legalkg/cli.py`: Typer-based CLI commands
- `src/legalkg/config.py`: API URLs and project paths
- `src/legalkg/core/tier2.py`: Reference extraction regex patterns
- `src/legalkg/client/base.py`: HTTP client with caching/rate limiting
- `src/legalkg/utils/numerals.py`: Kanji numeral conversion logic
- `targets.yaml`: List of law IDs to process (user-maintained)

## Data Sources

- **e-Gov Law API** (`https://laws.e-gov.go.jp/api/1`): Official source of law text and metadata
- **NDL OpenSearch** (`https://ndlsearch.ndl.go.jp/api/opensearch`): Legislative process data (bill submission, proposers, etc.)

## Testing Notes

- Test directory exists but contains no tests yet
- pytest configured to use `tests/` directory
- Debug scripts (`debug_ndl.py`, `debug_regex.py`) serve as manual integration tests
- Consider mocking API responses for unit tests to avoid rate limits
