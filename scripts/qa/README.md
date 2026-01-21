# QA スクリプト

Vault の品質を検証するスクリプト群。

## check_wikilinks.py

WikiLink の整合性をチェックし、リンク先が存在しない「壊れたリンク」を検出する。

```bash
# 全 Vault をチェック
python3 scripts/qa/check_wikilinks.py --vault ./Vault

# laws/ 配下のみチェック
python3 scripts/qa/check_wikilinks.py --vault ./Vault --only-prefix laws/
```

- 壊れたリンクが見つかった場合は exit code 1
- 除外パターンは `link_check_ignore.txt` に追加

## check_no_legacy_init.py

レガシー形式の初期附則ディレクトリ/ファイル（`init_0/`, `init_0.md`, `init_0_第N条.md`）が残っていないことを検証する。

```bash
python3 scripts/qa/check_no_legacy_init.py --vault ./Vault
python3 scripts/qa/check_no_legacy_init.py --vault ./Vault --only-prefix laws/
```

- レガシー形式が検出された場合は exit code 1
- 移行には `scripts/migration/migrate_init_to_japanese.py` を使用

## CI での利用

```bash
# 両方のチェックを実行
python3 scripts/qa/check_wikilinks.py --vault ./Vault --only-prefix laws/
python3 scripts/qa/check_no_legacy_init.py --vault ./Vault --only-prefix laws/
```
