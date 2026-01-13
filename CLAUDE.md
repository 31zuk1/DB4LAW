# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DB4LAW generates a knowledge graph of Japanese laws in Obsidian Vault format. It fetches law data from e-Gov API, parses legal text into structured nodes with Japanese directory paths, and extracts cross-references as Obsidian wikilinks.

## Common Commands

### Setup
```bash
pip install -r requirements.txt
# OR for development
pip install -e .
```

### Build Commands

**Tier 1+2 - Generate articles with reference extraction:**
```bash
# Edit targets.yaml to specify law IDs first
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges
```

**Migration to Japanese paths:**
```bash
python scripts/migration/migrate_to_japanese.py --law 刑法 --dry-run
python scripts/migration/migrate_to_japanese.py --law 刑法 --apply
```

**Fix external law references:**
```bash
python scripts/migration/fix_id_collision.py --law 民法 \
  --pending-log scripts/migration/_artifacts/pending_links.jsonl \
  --apply
```

**Add parent file links:**
```bash
python scripts/migration/add_parent_links.py --law 刑法
```

### Debug Commands

```bash
# NDL API queries
python scripts/debug/debug_ndl.py

# Reference extraction regex
python scripts/debug/debug_regex.py
```

## Architecture

### Three-Tier Data Model

1. **Tier 0** (`src/legalkg/core/tier0.py`): Fetches law list from e-Gov API
   - Output: `Vault/laws/{LAW_ID}/{title}.md` with YAML frontmatter

2. **Tier 1** (`src/legalkg/core/tier1.py`): Parses XML and extracts individual articles
   - Raw output: `articles/main/Article_{N}.md` and `articles/suppl/...`
   - After migration: `本文/第N条.md` and `附則/改正法/{KEY}/附則第N条.md`

3. **Tier 2** (`src/legalkg/core/tier2.py`): Extracts cross-references using regex
   - Pattern: `第{kanji_numerals}条` → wikilink
   - Output: `edges.jsonl` containing reference graph edges

### Japanese Path Convention

After running `migrate_to_japanese.py`, articles use Japanese paths:

```
Vault/laws/刑法/
├── 刑法.md                    # Parent node with links to all articles
├── 本文/                      # Main text (本則)
│   ├── 第1条.md
│   └── 第199条.md
├── 附則/                      # Supplementary provisions
│   └── 改正法/                # Amendment laws
│       ├── R3_L37/           # 令和3年法律第37号
│       └── H19_L54/          # 平成19年法律第54号
└── edges.jsonl
```

### Node ID Schema

- **Law:** `JPLAW:{LAW_ID}` (e.g., `JPLAW:140AC0000000045`)
- **Main Article:** `JPLAW:{LAW_ID}#本文#第N条` (e.g., `#本文#第199条`)
- **Supplementary:** `JPLAW:{LAW_ID}#附則#附則第N条`
- **Sub-article:** Uses `の` notation (e.g., `第19条の2`)

### Migration Scripts

Located in `scripts/migration/`:

| Script | Purpose |
|--------|---------|
| `migrate_to_japanese.py` | Convert English paths to Japanese |
| `fix_id_collision.py` | Unlink external law references |
| `add_parent_links.py` | Add wikilinks to parent file |
| `pending_links.py` | Schema for deferred link resolution |
| `relink_pending.py` | Restore links when target nodes exist |

### Pending Links System

When external law references are unlinked, they are recorded in JSONL for later restoration:

```bash
# Record pending links when unlinking
python scripts/migration/fix_id_collision.py --law 民法 \
  --pending-log scripts/migration/_artifacts/pending_links.jsonl --apply

# Restore links after external law nodes are created
python scripts/migration/relink_pending.py --filter-law 民法 --apply
```

## Key Files

- `src/legalkg/cli.py`: Typer-based CLI commands
- `src/legalkg/core/tier2.py`: Reference extraction regex patterns
- `src/legalkg/utils/numerals.py`: Kanji numeral conversion logic
- `scripts/migration/migrate_to_japanese.py`: Japanese path migration
- `scripts/migration/fix_id_collision.py`: External reference handling
- `scripts/migration/_artifacts/`: Generated CSV/JSONL files
- `targets.yaml`: List of law IDs to process

## Processed Laws

| Law | Articles | Supplements | Edges |
|-----|----------|-------------|-------|
| 刑法 | 264 | 68 | 713 |
| 民法 | 1,167 | 221 | 1,294 |
| 日本国憲法 | 103 | 1 | 64 |
| 所有者不明土地法 | 63 | 36 | 415 |

## Data Sources

- **e-Gov Law API** (`https://laws.e-gov.go.jp/api/1`): Official law text and metadata
- **NDL OpenSearch** (`https://ndlsearch.ndl.go.jp/api/opensearch`): Legislative process data

## Project Structure

```
DB4LAW/
├── src/legalkg/              # Main package
│   ├── client/               # API clients (e-Gov, NDL)
│   ├── core/                 # Tier0/1/2 core logic
│   └── utils/                # Kanji conversion, etc.
├── scripts/
│   ├── migration/            # Migration & fix scripts
│   │   └── _artifacts/       # Generated files (CSV, JSONL)
│   ├── analysis/             # Link processing
│   ├── debug/                # Debug scripts
│   └── utils/                # Shell utilities
├── data/                     # Domain classification YAML
├── Vault/laws/               # Obsidian Vault output
└── targets.yaml              # Target law IDs
```
