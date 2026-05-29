#!/usr/bin/env python3
import json
from datetime import datetime, timedelta
from pathlib import Path

# Пути
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
LEARNING_DIR = BASE_DIR / "data" / "call_learnings"
OUTPUT_JSON = BASE_DIR / "vezem" / "src" / "data" / "dynamic_faq.json"
OUTPUT_MD = BASE_DIR / "data" / "FAQ_PREVIEW.md"

def generate_dynamic_faq(days=30):
    print(f"🔄 Генерация динамического FAQ за последние {days} дней...")
    
    all_questions = []
    
    # 1. Собираем данные
    now = datetime.now()
    files_processed = 0
    
    for i in range(days):
        date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        file_path = LEARNING_DIR / f"{date_str}.json"
        
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items = data.get("faq_items", [])
                    for item in items:
                        # Добавляем дату для веса (свежие вопросы важнее)
                        item["date"] = date_str
                        all_questions.append(item)
                files_processed += 1
            except Exception as e:
                print(f"  ⚠️ Ошибка чтения {file_path.name}: {e}")

    if not all_questions:
        print("  ℹ️ Вопросы не найдены.")
        return

    # 2. Агрегация и фильтрация (простая логика: топ по важности)
    # В будущем тут можно добавить fuzzy matching для объединения похожих
    sorted_faq = sorted(all_questions, key=lambda x: (x.get("importance", 0), x.get("date", "")), reverse=True)
    
    # Убираем дубликаты (по тексту вопроса)
    seen_questions = set()
    unique_faq = []
    for item in sorted_faq:
        q = item["question"].strip().lower()
        if q not in seen_questions and len(unique_faq) < 15:
            seen_questions.add(q)
            unique_faq.append({
                "question": item["question"],
                "answer": item["answer"],
                "last_updated": item["date"]
            })

    # 3. Сохраняем JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": now.strftime("%Y-%m-%d %H:%M"),
            "source_days": days,
            "items_count": len(unique_faq),
            "faq": unique_faq
        }, f, ensure_ascii=False, indent=2)
    
    # 4. Сохраняем Markdown Preview
    md_lines = [
        "# 🐔 Динамический FAQ: ВезёмЦыплят",
        "> Сгенерировано автоматически на основе реальных звонков клиентов.",
        "",
        f"**Дата обновления:** {now.strftime('%d.%m.%Y %H:%M')}",
        f"**Период анализа:** {days} дней",
        "",
        "---",
        ""
    ]
    
    for i, item in enumerate(unique_faq, 1):
        md_lines.append(f"### {i}. {item['question']}")
        md_lines.append(f"{item['answer']}")
        md_lines.append(f"*📅 Актуально на: {item['last_updated']}*")
        md_lines.append("")

    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"  ✅ Готово! Сформировано {len(unique_faq)} вопросов.")
    print(f"  💾 JSON: {OUTPUT_JSON}")
    print(f"  💾 Preview: {OUTPUT_MD}")

if __name__ == "__main__":
    generate_dynamic_faq()
