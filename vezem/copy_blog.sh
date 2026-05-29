#!/bin/bash
BRAIN="$HOME/.gemini/antigravity/brain/34831ae9-8432-4f87-b8ee-6bf998e3c1e2"
PUB="$HOME/freelance-2026/ai-eggs/vezem/public"

cp "$BRAIN/blog_delivery_1776592500433.png" "$PUB/blog_delivery.png"
cp "$BRAIN/blog_chicks_care_1776592514504.png" "$PUB/blog_chicks.png"
cp "$BRAIN/blog_dominant_compare_1776592527194.png" "$PUB/blog_dominant.png"

echo "✅ 3 фото для блога скопированы!"

cd "$HOME/freelance-2026/ai-eggs/vezem"
rm -f copy_images.sh
git add -A
git commit -m "Blog: thematic images + expand articles on click"
git push origin main

echo "🚀 Блог обновлён и залит!"
