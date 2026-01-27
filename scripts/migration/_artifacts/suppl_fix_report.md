# 附則ノード修正レポート

## 1. 調査結果

### 1.1 e-Gov データ構造

刑法（法令ID: 140AC0000000045）のe-Gov XMLデータを調査した結果：

- **全てのSupplProvisionがAmendLawNum属性を持つ**
- 現行附則（制定時の附則）は存在しない
- 36個の改正法附則が確認された

```xml
<SupplProvision AmendLawNum="昭和一六年三月一二日法律第六一号">
<SupplProvision AmendLawNum="平成一三年七月四日法律第九七号" Extract="true">
```

### 1.2 現行附則 vs 改正法附則の判別ルール

| 条件 | 分類 |
|------|------|
| `AmendLawNum` 属性あり | 改正法附則 (amendment) |
| `AmendLawNum` 属性なし | 現行附則 (current) |

**刑法の場合**: 全て改正法附則（明治40年制定時の附則は含まれていない）

### 1.3 空見出しの発生原因

**発生箇所**: `src/legalkg/core/tier1.py` 行185, 301

```python
content += f"## {p_num_text}\n{text}\n\n"
```

**原因**: `ParagraphNum` が空の場合、`## ` だけが出力される

**発生例**:
```markdown
# 附則

##
本法施行ノ期日ハ勅令ヲ以テ之ヲ定ム
```

### 1.4 改正法タイトル正規化

| 入力（元データ） | 出力（正規化） | 短縮形式 |
|-----------------|---------------|----------|
| 昭和一六年三月一二日法律第六一号 | 昭和16年法律第61号 | S16_L61 |
| 平成一三年七月四日法律第九七号 | 平成13年法律第97号 | H13_L97 |
| 令和四年六月一七日法律第六七号 | 令和4年法律第67号 | R4_L67 |

## 2. 修正内容

### 2.1 ディレクトリ構造

修正前:
```
Vault/laws/刑法/附則/
├── 昭和一六年三月一二日法律第六一号.md
├── 平成一九年五月二三日法律第五四号/
│   ├── 附則第1条.md
│   └── 附則第2条.md
```

修正後:
```
Vault/laws/刑法/附則/
├── 現行/                    # 現行附則（該当なし）
└── 改正法/
    ├── S16_L61/
    │   └── 附則.md
    ├── H19_L54/
    │   ├── 附則第1条.md
    │   └── 附則第2条.md
```

### 2.2 YAMLスキーマ

修正後のYAMLフロントマター:

```yaml
---
article_num: 附則
heading: 附則
id: JPLAW:140AC0000000045#附則#附則
law_id: 140AC0000000045
law_name: 刑法
part: 附則
canonical_id: 刑法_附則__昭和16年法律第61号
suppl_kind: amendment
amendment_law_title: 昭和一六年三月一二日法律第六一号
amendment_law_normalized: 昭和16年法律第61号
aliases:
  - 附則
  - 昭和一六年三月一二日法律第六一号
source:
  provider: e-gov
  id: JPLAW:140AC0000000045#附則#附則
  law_id: 140AC0000000045
---
```

### 2.3 空見出しの修正

修正前:
```markdown
# 附則

##
本法施行ノ期日ハ勅令ヲ以テ之ヲ定ム
```

修正後:
```markdown
# 附則（昭和16年法律第61号）

本法施行ノ期日ハ勅令ヲ以テ之ヲ定ム
```

## 3. 統計

| 項目 | 件数 |
|------|------|
| 総附則ファイル数 | 68 |
| 改正法附則 | 68 |
| 現行附則 | 0 |
| 空見出し修正対象 | 13 |

## 4. 既存リンク互換

### 4.1 aliases による吸収

以下のエイリアスを自動生成:
- `附則第N条` (条番号あり)
- `suppl_article_N` (条番号あり)
- 改正法タイトル（元の漢数字形式）

### 4.2 スタブファイル

旧位置にスタブを残すオプションを実装済み（デフォルトはオフ）:
```markdown
---
redirect_to: '新パス'
---

→ [[新ファイル名]]
```

## 5. 使用方法

```bash
# Dry-run（変更なし、確認のみ）
python tools/fix_supplementary_articles.py --law 刑法 --dry-run --limit 10

# 実適用
python tools/fix_supplementary_articles.py --law 刑法 --apply

# 全件処理
python tools/fix_supplementary_articles.py --law 刑法 --apply
```

## 6. 今後の課題

1. **tier1.py の根本修正**: 生成時点で空見出しを出力しないようにする
2. **現行附則の対応**: 他の法令で現行附則が存在する場合の処理
3. **リンク一括置換**: 必要に応じてVault全体のリンクを更新
