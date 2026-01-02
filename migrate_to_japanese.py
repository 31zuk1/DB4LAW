#!/usr/bin/env python3
"""
刑法ディレクトリ日本語統一移行スクリプト

目的: articles/main, articles/suppl を 本文/, 附則/ に移行し、
     ファイル名・YAML・wikilinkを日本語化する。

使用方法:
    python migrate_to_japanese.py --dry-run --sample 10   # Dry-run（サンプル10件）
    python migrate_to_japanese.py --dry-run              # Dry-run（全件）
    python migrate_to_japanese.py                        # 本番実行
"""

import re
import csv
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import yaml


class JapaneseMigrator:
    """刑法ディレクトリを日本語化する移行ツール"""

    def __init__(self, law_dir: Path):
        self.law_dir = law_dir
        self.articles_dir = law_dir / "articles"
        self.main_dir = self.articles_dir / "main"
        self.suppl_dir = self.articles_dir / "suppl"

        self.new_main_dir = law_dir / "本文"
        self.new_suppl_dir = law_dir / "附則"

        # ファイル名マッピング（旧パス → 新パス）
        self.file_mapping: Dict[Path, Path] = {}

        # wikilink変換マッピング（Article_N → 第N条）
        self.wikilink_mapping: Dict[str, str] = {}

    def convert_main_filename(self, old_name: str) -> str:
        """
        本則ファイル名を日本語に変換
        Article_N[_M][:K].md → 第N条[のM][からK].md
        """
        stem = old_name.replace('.md', '').replace('Article_', '')

        # 範囲形式: 73:76 → 第73条から第76条まで
        if ':' in stem:
            start, end = stem.split(':')
            return f"第{start}条から第{end}条まで.md"

        # 枝番形式: 3_2 → 第3条の2
        if '_' in stem:
            main, sub = stem.split('_', 1)  # 最初の_のみで分割
            return f"第{main}条の{sub}.md"

        # 通常形式: 1 → 第1条
        return f"第{stem}条.md"

    def convert_suppl_filename(self, old_name: str, parent_law: str) -> str:
        """
        附則ファイル名を日本語に変換
        {改正法}_{Article_N}.md → 附則第N条.md
        {改正法}.md → {改正法}.md（単一ファイル型は変更なし）
        """
        # 単一ファイル型（改正法.md）は変更なし
        if not old_name.startswith(parent_law + '_'):
            return old_name

        # 複数ファイル型: {改正法}_Article_N.md → 附則第N条.md
        article_part = old_name.replace(parent_law + '_', '').replace('.md', '')
        if article_part.startswith('Article_'):
            article_num = article_part.replace('Article_', '')

            # 枝番対応
            if '_' in article_num:
                main, sub = article_num.split('_', 1)
                return f"附則第{main}条の{sub}.md"
            else:
                return f"附則第{article_num}条.md"

        return old_name

    def convert_article_id(self, article_id: str) -> str:
        """
        条文ID（wikilink用）を日本語に変換
        Article_N[_M] → 第N条[のM]
        """
        article_id = article_id.replace('Article_', '')

        # 範囲形式
        if ':' in article_id:
            start, end = article_id.split(':')
            return f"第{start}条から第{end}条まで"

        # 枝番形式
        if '_' in article_id:
            main, sub = article_id.split('_', 1)
            return f"第{main}条の{sub}"

        # 通常形式
        return f"第{article_id}条"

    def generate_file_mapping(self):
        """全ファイルのマッピングテーブルを生成"""
        print("📊 ファイル名マッピングテーブルを生成中...")

        # 本則ファイル
        for old_file in sorted(self.main_dir.glob('*.md')):
            new_filename = self.convert_main_filename(old_file.name)
            new_path = self.new_main_dir / new_filename
            self.file_mapping[old_file] = new_path

            # wikilinkマッピングも生成
            old_id = old_file.stem  # Article_1
            new_id = new_filename.replace('.md', '')  # 第1条
            self.wikilink_mapping[old_id] = new_id

        # 附則ファイル
        for old_file in sorted(self.suppl_dir.rglob('*.md')):
            parent_law = old_file.parent.name if old_file.parent != self.suppl_dir else None

            if parent_law and parent_law != 'suppl':
                # サブディレクトリ内のファイル
                new_filename = self.convert_suppl_filename(old_file.name, parent_law)
                new_path = self.new_suppl_dir / parent_law / new_filename
            else:
                # 直下のファイル（単一ファイル型）
                new_filename = old_file.name  # 変更なし
                new_path = self.new_suppl_dir / new_filename

            self.file_mapping[old_file] = new_path

        print(f"✅ マッピング完了: {len(self.file_mapping)} ファイル")

    def save_mapping_csv(self, output_path: Path):
        """マッピングテーブルをCSVに保存"""
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['旧パス', '新パス', 'サイズ(bytes)'])

            for old_path, new_path in sorted(self.file_mapping.items()):
                size = old_path.stat().st_size if old_path.exists() else 0
                writer.writerow([
                    str(old_path.relative_to(self.law_dir)),
                    str(new_path.relative_to(self.law_dir)),
                    size
                ])

        print(f"💾 マッピングCSV保存: {output_path}")

    def update_yaml_frontmatter(self, content: str, old_path: Path, new_path: Path) -> str:
        """
        YAMLフロントマターを日本語化
        - article_num: '1' → '第1条'
        - id: #main#1 → #本文#第1条
        - part: main → 本文, suppl → 附則
        - references_explicit[].target_id: Article_N → 第N条
        """
        # YAMLとボディを分離
        if not content.startswith('---'):
            return content

        parts = content.split('---', 2)
        if len(parts) < 3:
            return content

        yaml_str = parts[1]
        body = parts[2]

        try:
            metadata = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            print(f"⚠️  YAML解析エラー: {old_path} - {e}")
            return content

        # article_num の変換
        if 'article_num' in metadata:
            old_num = metadata['article_num']

            if old_num == 'Provision':
                # 附則（単一ファイル型）
                metadata['article_num'] = '附則'
            elif old_num and old_num != 'Provision':
                # 本則 or 附則（複数ファイル型）
                is_suppl = 'suppl' in str(old_path)

                if ':' in str(old_num):
                    # 範囲形式
                    start, end = str(old_num).split(':')
                    metadata['article_num'] = f'第{start}条から第{end}条まで'
                elif '_' in str(old_num):
                    # 枝番形式
                    main, sub = str(old_num).split('_', 1)
                    if is_suppl:
                        metadata['article_num'] = f'附則第{main}条の{sub}'
                    else:
                        metadata['article_num'] = f'第{main}条の{sub}'
                else:
                    # 通常形式
                    if is_suppl:
                        metadata['article_num'] = f'附則第{old_num}条'
                    else:
                        metadata['article_num'] = f'第{old_num}条'

        # part の変換
        if 'part' in metadata:
            if metadata['part'] == 'main':
                metadata['part'] = '本文'
            elif metadata['part'] == 'suppl':
                metadata['part'] = '附則'

        # law_name の設定（空の場合）
        if 'law_name' in metadata and metadata['law_name'] == '':
            metadata['law_name'] = '刑法'

        # id の変換
        if 'id' in metadata:
            old_id = metadata['id']
            # JPLAW:140AC0000000045#main#1 → JPLAW:140AC0000000045#本文#第1条
            old_id = old_id.replace('#main#', '#本文#')
            old_id = old_id.replace('#suppl#', '#附則#')

            # 条番号部分を変換
            if '#本文#' in old_id:
                prefix, suffix = old_id.rsplit('#本文#', 1)
                if suffix == 'Provision':
                    new_suffix = '附則'
                elif ':' in suffix:
                    start, end = suffix.split(':')
                    new_suffix = f'第{start}条から第{end}条まで'
                elif '_' in suffix:
                    main, sub = suffix.split('_', 1)
                    new_suffix = f'第{main}条の{sub}'
                else:
                    new_suffix = f'第{suffix}条'
                metadata['id'] = f"{prefix}#本文#{new_suffix}"

            elif '#附則#' in old_id:
                prefix, suffix = old_id.rsplit('#附則#', 1)
                if suffix == 'Provision':
                    new_suffix = '附則'
                elif ':' in suffix:
                    start, end = suffix.split(':')
                    new_suffix = f'附則第{start}条から第{end}条まで'
                elif '_' in suffix:
                    main, sub = suffix.split('_', 1)
                    new_suffix = f'附則第{main}条の{sub}'
                else:
                    new_suffix = f'附則第{suffix}条'
                metadata['id'] = f"{prefix}#附則#{new_suffix}"

        # references_explicit の target_id 変換
        if 'references_explicit' in metadata and isinstance(metadata['references_explicit'], list):
            for ref in metadata['references_explicit']:
                if 'target_id' in ref:
                    old_target = ref['target_id']

                    # アンカー部分（#第2項等）を分離
                    if '#' in old_target:
                        target_base, anchor = old_target.split('#', 1)
                        new_target_base = self.convert_article_id(target_base)
                        ref['target_id'] = f"{new_target_base}#{anchor}"
                    else:
                        ref['target_id'] = self.convert_article_id(old_target)

        # YAML を再シリアライズ
        new_yaml_str = yaml.dump(metadata, allow_unicode=True, sort_keys=False, default_flow_style=False)

        return f"---\n{new_yaml_str}---{body}"

    def update_wikilinks_in_body(self, content: str) -> str:
        """
        本文中のwikilinkを日本語に変換
        [[Article_N]] → [[第N条]]
        [[Article_N#第2項]] → [[第N条#第2項]]
        """

        def replace_wikilink(match):
            full_link = match.group(0)  # [[Article_109#第2項]]
            inner = match.group(1)  # Article_109#第2項

            # アンカーを分離
            if '#' in inner:
                article_part, anchor = inner.split('#', 1)
            else:
                article_part, anchor = inner, None

            # Article_ を日本語に変換
            if article_part in self.wikilink_mapping:
                new_article = self.wikilink_mapping[article_part]
            else:
                # マッピングにない場合は手動変換
                new_article = self.convert_article_id(article_part)

            # アンカーを復元
            if anchor:
                return f"[[{new_article}#{anchor}]]"
            else:
                return f"[[{new_article}]]"

        # wikilinkパターン: [[Article_...]]
        pattern = r'\[\[(Article_[^\]]+)\]\]'
        return re.sub(pattern, replace_wikilink, content)

    def migrate_file(self, old_path: Path, new_path: Path, dry_run: bool = False) -> bool:
        """単一ファイルを移行"""
        try:
            # ファイル読み込み
            with open(old_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # YAML更新
            content = self.update_yaml_frontmatter(content, old_path, new_path)

            # wikilink更新
            content = self.update_wikilinks_in_body(content)

            if not dry_run:
                # ディレクトリ作成
                new_path.parent.mkdir(parents=True, exist_ok=True)

                # ファイル書き込み
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write(content)

            return True

        except Exception as e:
            print(f"❌ エラー: {old_path} → {new_path}")
            print(f"   {e}")
            return False

    def update_parent_file(self, dry_run: bool = False):
        """親ファイル（刑法.md）のリンクを更新"""
        parent_file = self.law_dir / "刑法.md"

        if not parent_file.exists():
            print(f"⚠️  親ファイルが見つかりません: {parent_file}")
            return

        print("📝 親ファイル（刑法.md）のリンクを更新中...")

        with open(parent_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 本則リンク変換
        # [[articles/main/Article_1.md|第1条]] → [[本文/第1条.md|第1条]]
        def replace_main_link(match):
            old_article_file = match.group(1)  # Article_1.md
            display_text = match.group(2)  # 第1条 or 第3の2条

            new_filename = self.convert_main_filename(old_article_file)

            # 表示テキストの修正（第3の2条 → 第3条の2）
            if 'の' in display_text and '条' in display_text:
                # 第3の2条 → 第3条の2
                display_text = re.sub(r'第(\d+)の(\d+)条', r'第\1条の\2', display_text)

            return f"[[本文/{new_filename}|{display_text}]]"

        content = re.sub(
            r'\[\[articles/main/(Article_[^\]]+\.md)\|([^\]]+)\]\]',
            replace_main_link,
            content
        )

        # 附則リンク変換（ディレクトリ型）
        # [[articles/suppl/平成19年法律第54号/平成19年法律第54号_Article_1.md|第1条]]
        # → [[附則/平成19年法律第54号/附則第1条.md|附則第1条]]
        def replace_suppl_dir_link(match):
            law_name = match.group(1)  # 平成19年法律第54号
            old_article_file = match.group(2)  # 平成19年法律第54号_Article_1.md
            display_text = match.group(3)  # 第1条

            new_filename = self.convert_suppl_filename(old_article_file, law_name)

            # 表示テキストに「附則」を追加
            if not display_text.startswith('附則'):
                display_text = f"附則{display_text}"

            return f"[[附則/{law_name}/{new_filename}|{display_text}]]"

        content = re.sub(
            r'\[\[articles/suppl/([^/]+)/([^\]]+\.md)\|([^\]]+)\]\]',
            replace_suppl_dir_link,
            content
        )

        # 附則リンク変換（単一ファイル型）
        # [[articles/suppl/昭和22年法律第124号.md|昭和22年法律第124号]]
        # → [[附則/昭和22年法律第124号.md|昭和22年法律第124号]]
        content = re.sub(
            r'\[\[articles/suppl/([^\]]+\.md)\|([^\]]+)\]\]',
            r'[[附則/\1|\2]]',
            content
        )

        if not dry_run:
            with open(parent_file, 'w', encoding='utf-8') as f:
                f.write(content)

        print("✅ 親ファイル更新完了")

    def cleanup_old_structure(self, dry_run: bool = False):
        """旧ディレクトリ（articles/）を削除"""
        if dry_run:
            print(f"🗑️  [DRY-RUN] 削除対象: {self.articles_dir}")
            return

        if self.articles_dir.exists():
            print(f"🗑️  旧ディレクトリを削除中: {self.articles_dir}")
            shutil.rmtree(self.articles_dir)
            print("✅ 削除完了")

    def validate_migration(self) -> Tuple[int, int]:
        """
        移行結果を検証
        Returns: (成功数, 失敗数)
        """
        print("🔍 移行結果を検証中...")

        success = 0
        failed = 0

        for new_path in self.file_mapping.values():
            if new_path.exists():
                success += 1
            else:
                failed += 1
                print(f"❌ ファイルが存在しません: {new_path}")

        print(f"✅ 検証完了: {success} 成功, {failed} 失敗")
        return success, failed

    def run(self, dry_run: bool = False, sample: Optional[int] = None):
        """移行を実行"""
        print("=" * 60)
        print("🚀 刑法ディレクトリ日本語統一移行")
        print("=" * 60)

        if dry_run:
            print("⚠️  DRY-RUN モード（実際のファイル変更はありません）")
        if sample:
            print(f"📊 サンプルモード（最初の{sample}件のみ処理）")

        print()

        # Phase 1: マッピング生成
        self.generate_file_mapping()

        # マッピングCSV保存
        csv_path = self.law_dir.parent.parent / "migration_mapping.csv"
        self.save_mapping_csv(csv_path)

        print()

        # Phase 2: ファイル移行
        print("📦 ファイルを移行中...")

        items = list(self.file_mapping.items())
        if sample:
            items = items[:sample]

        success_count = 0
        fail_count = 0

        for i, (old_path, new_path) in enumerate(items, 1):
            print(f"[{i}/{len(items)}] {old_path.name} → {new_path.relative_to(self.law_dir)}")

            if self.migrate_file(old_path, new_path, dry_run):
                success_count += 1
            else:
                fail_count += 1

        print(f"\n✅ 移行完了: {success_count} 成功, {fail_count} 失敗")

        print()

        # Phase 3: 親ファイル更新
        if not sample:  # サンプルモードでは親ファイル更新をスキップ
            self.update_parent_file(dry_run)
            print()

        # Phase 4: 検証（dry-runでない場合）
        if not dry_run and not sample:
            self.validate_migration()
            print()

            # Phase 5: 旧ディレクトリ削除
            self.cleanup_old_structure(dry_run)

        print()
        print("=" * 60)
        print("✨ 移行処理が完了しました")
        print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="刑法ディレクトリ日本語統一移行")
    parser.add_argument('--dry-run', action='store_true', help='Dry-runモード（ファイル変更なし）')
    parser.add_argument('--sample', type=int, help='サンプル件数（テスト用）')
    args = parser.parse_args()

    # 刑法ディレクトリのパス
    law_dir = Path("/Users/haramizuki/Project/DB4LAW/Vault/laws/刑法")

    if not law_dir.exists():
        print(f"❌ エラー: 刑法ディレクトリが見つかりません: {law_dir}")
        exit(1)

    # 移行実行
    migrator = JapaneseMigrator(law_dir)
    migrator.run(dry_run=args.dry_run, sample=args.sample)
