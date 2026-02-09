# DB4LAW Vault Reader (`apps/ui`)

DB4LAW の Vault（Markdown 群）を **read-only** で閲覧するための Web UI です。
Obsidian 互換として以下を扱います。

- YAML frontmatter
- wikilink `[[...]]` / `[[...|alias]]`

## 主な機能

- 3カラム UI
- 左: 検索ボックス + Vault/インデックス状態
- 中央: 検索結果一覧
- 右: ブラウザライクなタブ + Markdown プレビュー + frontmatter + outgoing/incoming + 近傍グラフ
- 開いているタブは `.md` パス付きで表示
- グラフ深さ（1-4）を切替可能
- プレビュー内 wikilink 遷移
- プレビュー内の相対Markdownリンク（`編/章/節/条/附則`）遷移
- 曖昧リンク時の候補表示（同名ファイル衝突）
- 初回はバックグラウンドで Vault 件数インデックス化（UIは先に操作可能）
- incoming はタブを開いた時に遅延読み込み
- 検索結果は「表示件数 / 総件数」を表示し、`Load more` で追加表示

## 想定ディレクトリ構造

```text
DB4LAW/
  Vault/                # 例: 既定候補1
  data/vault/           # 例: 既定候補2
  apps/
    ui/
      ...
```

## 設定

`.env.local` または環境変数で Vault の場所を指定します。

```bash
VAULT_PATH=../../Vault
TARGETS_PATH=../../targets.yaml
```

未指定の場合は次の順で探索します。

1. `../../Vault`
2. `../../vault`
3. `../../data/vault`
4. `../Vault`
5. `./Vault`

`TARGETS_PATH` 未指定時は次を順に探索します。

1. `../../targets.yaml`
2. `../targets.yaml`
3. `./targets.yaml`

`targets.yaml` が見つかった場合、検索結果一覧はその `targets` に含まれる law_id のみを対象にします（例: `120 shown / 8,918 total`）。

## 開発

```bash
cd apps/ui
npm install
npm run dev
```

ブラウザで `http://localhost:3000` を開きます。

`npm run dev` は起動前に `.next` をクリアし、`apps/ui` の `next dev` 二重起動を防止します。
既存の `apps/ui` dev サーバーがあれば自動停止してから起動します。

## ビルドと起動

```bash
cd apps/ui
npm run build
npm run start
```

## 変更範囲検証

`apps/ui` 以外の変更があれば失敗します。

```bash
cd apps/ui
npm run check:readonly
```
