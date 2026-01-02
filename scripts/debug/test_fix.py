#!/usr/bin/env python3
"""
Test the fix for relative references with item/clause numbers
"""

from pathlib import Path
from link_references import process_article

# Test on 第19条の2
test_file = Path('/Users/haramizuki/Project/DB4LAW/Vault/laws/刑法/本文/第19条の2.md')

print("=" * 80)
print(f"Testing: {test_file.name}")
print("=" * 80)

result = process_article(test_file, dry_run=True)

if 'error' in result:
    print(f"ERROR: {result['error']}")
else:
    print(f"\n抽出された参照: {result['references_count']}件")
    print(f"  - Resolved: {result['resolved_count']}")
    print(f"  - Unresolved: {result['unresolved_count']}")

    print("\n参照詳細:")
    for i, ref in enumerate(result['references'], 1):
        print(f"{i}. {ref.original} → {ref.target_id}")
        print(f"   Type: {ref.type}, Resolved: {ref.resolved}")
        if ref.note:
            print(f"   Note: {ref.note}")

    print("\n置換:")
    for old, new in result['replacements']:
        print(f"  {old} → {new}")

    print("\n変更あり:", result['changed'])

    if result['changed']:
        print("\n=== 新しい内容 ===")
        print(result['new_content'][:500])
