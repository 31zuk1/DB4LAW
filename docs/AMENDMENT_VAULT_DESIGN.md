# 改正法Vault統合設計

## 背景

e-Gov の統合条文 XML では、整備法・一括改正法（改正法）は独立法令として取得できず、
各親法の XML の `SupplProvision(AmendLawNum=...)` に「当該親法に関係する断片」として分散格納される。

**例**: 令和3年法律第37号（デジタル社会形成整備法）
- 民法 → `Vault/laws/民法/附則/改正法/R3_L37/` に 6 ファイル
- 刑法 → `Vault/laws/刑法/附則/改正法/R3_L37/` に N ファイル
- 他の法律 → 同様に断片が分散

## 現状のデータモデル

```
Vault/laws/<親法>/附則/
├── 改正法/
│   ├── R3_L37/           # 改正法断片
│   │   ├── 附則第1条.md
│   │   └── 附則第2条.md
│   └── H30_L72/
│       └── ...
└── <初期附則>.md         # AmendLawNum なしの附則
```

各改正法断片ファイルの frontmatter:
```yaml
suppl_kind: amendment
amendment_law_id: R3_L37
amendment_law_title: 令和三年五月一九日法律第三七号
amend_law:
  num: 令和三年五月一九日法律第三七号
  normalized_id: R3_L37
  scope: partial
  parent_law_id: 129AC0000000089
  parent_law_name: 民法
```

## 統合Vault構想

将来的に「改正法を一冊として読みたい」というユースケースに対応するため、
`amend_law.normalized_id` をキーに全断片を収集し、別ディレクトリ（または別Vault）にまとめる。

### 構造案

```
Vault/amendment_laws/            # または別Vault
├── R3_L37/                      # 令和3年法律第37号
│   ├── R3_L37.md                # 親ノード（メタデータ、目次）
│   ├── 民法/                    # 親法ごとのサブディレクトリ
│   │   ├── 附則第1条.md
│   │   └── 附則第2条.md
│   ├── 刑法/
│   │   └── ...
│   └── edges.jsonl              # 改正法内部のエッジ
└── H30_L72/
    └── ...
```

### 統合時の処理

1. 全親法の `附則/改正法/*/` を走査
2. `amend_law.normalized_id` でグループ化
3. 各グループを統合ディレクトリにコピー/リンク
4. 改正法内部の条文参照（第N条）をリンク化
5. edges.jsonl を生成

### メタデータスキーマ（統合後）

親ノード（`R3_L37.md`）:
```yaml
law_type: amendment_law
amendment_law_id: R3_L37
amendment_law_title: 令和3年法律第37号
official_title: デジタル社会の形成を図るための関係法律の整備に関する法律
promulgation_date: 2021-05-19
fragments:
  - parent_law: 民法
    article_count: 6
  - parent_law: 刑法
    article_count: 3
  - ...
total_articles: NN
```

断片ノード（統合後）:
```yaml
# 既存フィールドを維持
amend_law:
  # ...既存フィールド...
  integrated: true                  # 統合済みフラグ
  integrated_path: amendment_laws/R3_L37/民法/附則第1条.md
```

## リンク方針

### 現状（方式B: 断片維持）

- 改正法断片内の「裸の第N条」→ リンク化しない
- 「民法第N条」のように親法名付き → 親法本文へリンク
- 外部法参照 → リンク化しない

### 統合後（方式A: 完全統合）

- 改正法断片内の「第N条」→ 同一改正法内の条文へリンク
- 他法への参照は明示的に外部リンク

## 実装ステップ

### Phase 1（完了）
- [x] `amend_law` ネスト構造を全断片に付与
- [x] `suppl_kind: amendment` で改正法断片を識別可能に
- [x] 裸の第N条参照のリンク化を停止

### Phase 2（未実装）
- [ ] 統合スクリプトのスタブ作成
- [ ] 改正法の正式名称取得（NDL API 等）
- [ ] 統合ディレクトリ生成

### Phase 3（将来）
- [ ] 統合後のリンク解決
- [ ] edges.jsonl 生成
- [ ] Obsidian テンプレート作成

## 制約と考慮事項

1. **e-Gov の制約**: 改正法の全文は取得不可。断片のみ。
2. **断片の重複**: 同一条文が複数親法に影響する場合の扱い
3. **参照解決**: 統合後に改正法内部の参照をどう解決するか
4. **更新追従**: 親法が更新された際の統合Vault同期

## 参考リンク

- [e-Gov 法令API](https://laws.e-gov.go.jp/api/)
- [NDL OpenSearch](https://ndlsearch.ndl.go.jp/api/opensearch)
