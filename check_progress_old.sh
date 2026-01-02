#!/bin/bash
# 要約の進行状況を確認するスクリプト

echo "=== AI要約の進行状況 ==="
echo ""

# 刑法の要約数
keibou_total=$(find Vault/laws/刑法/articles -name "*.md" | wc -l | tr -d ' ')
keibou_done=$(find Vault/laws/刑法/articles -name "*.md" -exec grep -l "## AI要約" {} \; | wc -l | tr -d ' ')
echo "刑法: $keibou_done / $keibou_total 件完了"

# 憲法の要約数
kenpou_total=$(find Vault/laws/日本国憲法/articles -name "*.md" | wc -l | tr -d ' ')
kenpou_done=$(find Vault/laws/日本国憲法/articles -name "*.md" -exec grep -l "## AI要約" {} \; | wc -l | tr -d ' ')
echo "日本国憲法: $kenpou_done / $kenpou_total 件完了"

# 合計
total=$((keibou_total + kenpou_total))
done=$((keibou_done + kenpou_done))
echo ""
echo "合計: $done / $total 件完了 ($(echo "scale=1; $done * 100 / $total" | bc)%)"

# 最新の要約をサンプル表示
echo ""
echo "=== 最新の要約例 ==="
latest=$(find Vault/laws/刑法/articles -name "*.md" -exec grep -l "## AI要約" {} \; | head -1)
if [ -n "$latest" ]; then
    echo "ファイル: $latest"
    echo ""
    grep -A 3 "## AI要約" "$latest" | tail -2
fi
