# AGENTS

このファイルは、DB4LAW を扱う実装エージェント向けの運用メモです。

## Environment

- Python は `>=3.11` 必須（`pyproject.toml`）。
- 基本コマンドは `uv` 前提で実行する。
- 依存反映は `uv sync`、反映不整合時は `uv sync --reinstall-package legalkg`。

## Core Commands

- Tier1 実行:
  - `uv run python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges`
- QA:
  - `uv run python scripts/qa/check_wikilinks.py --vault ./Vault`
  - `PYTHONPATH=src pytest -q`
- 見出し補正（再生成なし）:
  - `uv run python scripts/migration/fix_structure_headings.py --vault ./Vault`
  - `uv run python scripts/migration/fix_structure_headings.py --vault ./Vault --apply`

## Projection Vault (`db4law-proj`)

- 作成:
  - `uv run db4law-proj create --laws <law_id,...>`
- 追加/削除:
  - `uv run db4law-proj add --session-id <id> --laws <law_id,...>`
  - `uv run db4law-proj remove --session-id <id> --laws <law_id,...>`
- 診断:
  - `uv run db4law-proj doctor --session-id <id>`
- 起動:
  - `uv run db4law-proj open --session-id <id>`

### Obsidian 連携注意点

- 投影Vault起動時、`~/Library/Application Support/obsidian/obsidian.json` の vault registry を自動更新してから開く。
- source law ディレクトリ配下の `.obsidian` は誤起動の原因になるため、必要に応じて除去する。
  - `uv run db4law-proj clean-markers --session-id <id>`
  - `uv run db4law-proj clean-markers --session-id <id> --apply`

## Documentation Rule

- 仕様変更時は最低でも以下を同期更新する:
  - `README.md`
  - `docs/projection_vault.md`
  - この `AGENTS.md`
