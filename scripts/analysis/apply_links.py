#!/usr/bin/env python3
"""
DB4LAW: 条文参照リンク化を実際に適用
"""

from pathlib import Path
from link_references import process_article
import sys

def apply_to_law(law_dir: Path, dry_run: bool = False):
    """一つの法令の全条文に適用"""
    articles_dir = law_dir / '本文'

    if not articles_dir.exists():
        print(f"Error: {articles_dir} が存在しません")
        return

    article_files = sorted(articles_dir.glob('第*.md'))

    print(f"\n{'='*80}")
    print(f"法令: {law_dir.name}")
    print(f"処理対象: {len(article_files)} ファイル")
    print(f"モード: {'DRY RUN (変更なし)' if dry_run else '実適用 (ファイル更新)'}")
    print(f"{'='*80}\n")

    stats = {
        'total': 0,
        'updated': 0,
        'total_refs': 0,
        'resolved_refs': 0,
        'unresolved_refs': 0,
        'errors': 0
    }

    unresolved_list = []

    for article_file in article_files:
        stats['total'] += 1
        result = process_article(article_file, dry_run=True)

        if 'error' in result:
            print(f"[ERROR] {article_file.name}: {result['error']}")
            stats['errors'] += 1
            continue

        stats['total_refs'] += result['references_count']
        stats['resolved_refs'] += result['resolved_count']
        stats['unresolved_refs'] += result['unresolved_count']

        if result['changed']:
            stats['updated'] += 1

            # unresolvedがあれば記録
            for ref in result['references']:
                if not ref.resolved:
                    unresolved_list.append({
                        'file': article_file.name,
                        'original': ref.original,
                        'target': ref.target_id,
                        'note': ref.note
                    })

            if not dry_run:
                # 実際にファイルを更新
                article_file.write_text(result['new_content'], encoding='utf-8')
                print(f"✓ {article_file.name}: {result['references_count']}件の参照を処理")
            else:
                print(f"  {article_file.name}: {result['references_count']}件の参照")

    # 集計結果
    print(f"\n{'='*80}")
    print(f"=== 集計: {law_dir.name} ===")
    print(f"総ファイル数: {stats['total']}")
    print(f"更新ファイル数: {stats['updated']}")
    print(f"総参照抽出数: {stats['total_refs']}")
    print(f"  - resolved: {stats['resolved_refs']}")
    print(f"  - unresolved: {stats['unresolved_refs']}")
    if stats['errors'] > 0:
        print(f"エラー: {stats['errors']}件")

    if unresolved_list:
        print(f"\n[未解決の参照 ({len(unresolved_list)}件)]")
        for item in unresolved_list[:10]:  # 最初の10件
            print(f"  {item['file']}: {item['original']} → {item['target']}")
            print(f"    理由: {item['note']}")
        if len(unresolved_list) > 10:
            print(f"  ... 他 {len(unresolved_list) - 10}件")

    print(f"{'='*80}\n")

    return stats


if __name__ == '__main__':
    vault_path = Path('/Users/haramizuki/Project/DB4LAW/Vault/laws')

    # コマンドライン引数でdry-runか実適用かを選択
    dry_run = '--apply' not in sys.argv

    if dry_run:
        print("\n" + "="*80)
        print("DRY RUN モード - ファイルは変更されません")
        print("実際に適用するには: python3 apply_links.py --apply")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("実適用モード - ファイルを更新します")
        print("="*80)
        response = input("\n本当に実行しますか？ (yes/no): ")
        if response.lower() != 'yes':
            print("キャンセルしました")
            sys.exit(0)

    # 処理対象の法令
    target_laws = ['刑法', '日本国憲法', '民法']

    for law_name in target_laws:
        law_dir = vault_path / law_name
        if law_dir.exists():
            apply_to_law(law_dir, dry_run=dry_run)

    if not dry_run:
        print("\n✅ 全ての処理が完了しました")
