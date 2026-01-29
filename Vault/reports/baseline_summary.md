# Baseline Summary Report

**Generated:** 2026-01-29
**Git Commit:** 3f7d9e10b52202cc9781bc67657e64c0c8635171
**Python Version:** 3.12.8

## Test Results

- **Total Tests:** 172
- **Passed:** 172
- **Failed:** 0

## WikiLink Integrity Check

- **Scanned Files:** 13,788
- **Total Links:** 15,152
- **Broken Links:** 3

### Broken Links Detail

All 3 broken links are references to non-existent articles in 刑事訴訟法 (future articles not yet enacted):

| Source File | Target | Line |
|-------------|--------|------|
| laws/刑事訴訟法/附則/令和五年五月一七日法律第二八号/令和五年五月一七日法律第二八号_第8条.md | laws/刑事訴訟法/本文/第98条の15.md | 43 |
| laws/刑事訴訟法/附則/令和五年五月一七日法律第二八号/令和五年五月一七日法律第二八号_第8条.md | laws/刑事訴訟法/本文/第98条の16.md | 43 |
| laws/刑事訴訟法/附則/令和五年五月一七日法律第二八号/令和五年五月一七日法律第二八号_第8条.md | laws/刑事訴訟法/本文/第98条の20.md | 43 |

**Status:** Expected - these articles do not yet exist in the integrated law text.

## Known Issues (From SESSION_MEMO)

### 1. Supplement Enumeration Wrong-Target Links (附則列挙パターンの誤リンク)

**Symptom:**
```
附則第五条第三項、第六条第三項、[[laws/刑事訴訟法/本文/第8条.md|第八条]]第五項...
```

Articles in supplement enumeration (附則第五条、第六条、第八条) are incorrectly linking to 刑事訴訟法 instead of remaining as plain text references to the amendment law's own supplements.

**Affected Files:**
- `laws/刑法/附則/令和五年五月一七日法律第二八号/令和五年五月一七日法律第二八号_第1条.md` (lines 32, 37)

**Root Cause:**
- Current "closest law name" logic finds `刑事訴訟法第三百四十四条` in extended context
- Subsequent bare references like `第八条` in the supplement enumeration are incorrectly attributed to 刑事訴訟法

**Impact:** Limited (only a few files), but represents a fundamental scope management issue.

## Error Classification Summary

| Category | Count | Status |
|----------|-------|--------|
| Broken Links (Expected) | 3 | Known - future articles |
| Wrong-Target Links | 2+ occurrences | Needs fix - scope management |
| Metadata Deficiency | TBD | Needs audit |
| Amendment Fragment Issues | 0 | Fixed in previous session |
| Deleted Article Redirects | TBD | Needs audit |

## Recommendations

1. **Implement Audit Script** - Create `scripts/qa/audit_vault.py` for comprehensive validation
2. **Add Provenance Tracking** - Implement manifest.json for build reproducibility
3. **Fix Scope Management** - Redesign tier2.py to use state machine for scope handling
4. **Add Regression Tests** - Test cases for supplement enumeration patterns
