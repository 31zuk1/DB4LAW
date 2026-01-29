# Final Audit Report: 2026-01-29

## Summary

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Baseline | ✅ Completed | 172 tests passed, 3 expected broken links |
| Phase 2: Provenance | ✅ Completed | BuildManifest, `--write-manifest` option |
| Phase 3: Audit Script | ✅ Completed | `scripts/qa/audit_vault.py` |
| Phase 4: Scope Fix | ✅ Completed | `is_in_supplement_enumeration()` |
| Phase 5: Tests & Report | ✅ Completed | 6 new regression tests, this report |

## Key Changes

### 1. Provenance Tracking (`src/legalkg/core/provenance.py`)

New module for build reproducibility:

```python
from legalkg.core.provenance import (
    create_manifest,      # Create BuildManifest from current state
    write_manifest,       # Write to Vault/.db4law/manifest.json
    read_manifest,        # Read existing manifest
    verify_manifest,      # Compare manifest to current state
    needs_regeneration,   # Check if rebuild is needed
)
```

### 2. CLI Integration (`src/legalkg/cli.py`)

Added `--write-manifest` option (default: True):

```bash
legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges
# → Writes Vault/.db4law/manifest.json
```

### 3. Audit Script (`scripts/qa/audit_vault.py`)

Comprehensive validation script with 5 checks:

```bash
# Report-only mode
python scripts/qa/audit_vault.py --vault ./Vault --targets targets.yaml --report-only

# Fix-safe mode (non-destructive fixes)
python scripts/qa/audit_vault.py --vault ./Vault --targets targets.yaml --fix-safe
```

Checks performed:
- A. Provenance verification
- B. Metadata schema validation
- C. Range node consistency
- D. WikiLink integrity
- E. Regression pattern detection

### 4. Supplement Enumeration Scope Fix (`src/legalkg/core/tier2.py`)

**Problem**: 「附則第五条第三項、第六条第三項、第八条第五項」の列挙において、
「第八条」が刑事訴訟法第8条へ誤ってリンクされていた。

**Root Cause**: 附則列挙スコープが外部法令スコープをブロックしていなかった。

**Solution**: `is_in_supplement_enumeration()` 関数を追加:

```python
def is_in_supplement_enumeration(context: str) -> bool:
    """
    コンテキストが附則列挙スコープ内かどうかをチェック
    「附則第五条、第六条、第八条」のような附則条文の列挙において、
    後続の「第六条」「第八条」は「附則」が省略されているが、
    附則への参照であり外部法令への参照ではない。
    """
```

**Verification**: 問題のファイルで13リンク → 7リンクに削減。
「第八条」への誤リンクが解消された。

## Test Results

```
============================= 178 passed in 0.49s ==============================
```

### New Regression Tests

`tests/test_tier2_amendment_fragment_bugs.py::TestSupplementEnumerationScopeLeak`:

| Test | Description |
|------|-------------|
| `test_fuzoku_enumeration_scope_preserved` | 附則列挙内の参照がリンク化されない |
| `test_fuzoku_enumeration_scope_blocks_external` | 外部法令スコープがブロックされる |
| `test_fuzoku_enumeration_complex_pattern` | 複雑な列挙パターンのテスト |
| `test_fuzoku_enumeration_after_external_law` | 外部法令後の附則列挙 |
| `test_fuzoku_enumeration_scope_reset_by_new_external` | 新しい外部法令でスコープリセット |
| `test_real_r5_l28_pattern` | 実際の令和5年法律第28号パターン |

## Broken Links (Expected)

3 broken links - all are **future articles** (expected):

| Source | Target | Reason |
|--------|--------|--------|
| 会社法本文 | 第842条 | 令和5年法律第28号で追加予定 |
| 会社法本文 | 第910条の2 | 令和5年法律第28号で追加予定 |
| 会社法本文 | 第911条 | 令和5年法律第28号で追加予定 |

These are correctly detected and documented in `Vault/reports/link_check_broken.md`.

## Files Changed

| File | Action |
|------|--------|
| `src/legalkg/core/provenance.py` | New |
| `src/legalkg/cli.py` | Modified |
| `src/legalkg/core/tier2.py` | Modified |
| `scripts/qa/audit_vault.py` | New |
| `docs/PROVENANCE.md` | New |
| `tests/test_tier2_amendment_fragment_bugs.py` | Modified |

## Recommendations

1. **Regenerate Vault**: Run `build-tier1` with `--extract-edges` to apply the fix globally
2. **Run Migration Script**: `scripts/migration/fix_amendment_fragment_links.py` for existing files
3. **CI Integration**: Add audit script to GitHub Actions workflow

## Verification Commands

```bash
# Full test suite
.venv/bin/python -m pytest tests/ -v

# WikiLink check
python scripts/qa/check_wikilinks.py --vault ./Vault

# Regression check: 附則列挙スコープ
grep -r "附則第.*条.*\[\[laws/" Vault/laws/刑法/附則/
# Expected: No matches (附則列挙内の参照はリンク化されない)

# Check specific file
grep -c "\[\[" Vault/laws/刑法/附則/令和五年五月一七日法律第二八号/令和五年五月一七日法律第二八号_第1条.md
# Expected: 7 (down from 13)
```
