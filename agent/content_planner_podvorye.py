#!/usr/bin/env python3
"""
📅 Content Planner for "Своё Подворье" VK community

Generates diverse content plan:
- 1 out of 5: poultry (chickens, broilers)
- 2 out of 5: garden, vegetables
- 1 out of 5: rabbits, goats
- 1 out of 5: bees, other farm animals
- Bonus: polls, tips, seasonal advice

Agents workflow:
1. Marketer → topics & brief
2. Shakespeare → articles
3. Rembrandt → photo prompts
"""

import os
from datetime import datetime, timedelta

BASE_DIR = "/Users/igorvasin/freelance-2026"
CONTENT_DIR = os.path.join(BASE_DIR, "content_day")

# Content themes for "Своё Подворье" (non-commercial, all Russia)
THEMES = [
    # 🥕 Garden & Vegetables (2 out of 5)
    {
        "category": "garden",
        "topics": [
            "Что посадить в мае: личный опыт огородника",
            "Умная грядка без химии: лайфхаки",
            "Рассада в мае: когда и что сажать в открытом грунте",
            "Борьба с вредителями без ядов: народные средства",
            "Теплица в мае: уход за томатами и огурцами",
        ]
    },
    # 🐇 Rabbits & Goats (1 out of 5)
    {
        "category": "rabbits",
        "topics": [
            "Кролики на мясо: породы, сроки, окупаемость",
            "Как содержать козу в частном хозяйстве",
            "Козье молоко: польза и как правильно доить",
            "Разведение кроликов: клетки, корм, болезни",
        ]
    },
    # 🐔 Poultry (1 out of 5)
    {
        "category": "poultry",
        "topics": [
            "Инкубаторы для дома: Несушка vs Золушка — честное сравнение",
            "Бройлеры vs несушки: что выгоднее для подворья",
            "Кормление цыплят с первого дня: схемы и нормы",
            "Породы кур для России: обзор с фото",
        ]
    },
    # 🐝 Bees & Other (1 out of 5)
    {
        "category": "bees",
        "topics": [
            "Пчёлы на подворье: с чего начать новичку",
            "Мёд с собственной пасеки: оборудование и уход",
            "Как содержать уток и гусей: личный опыт",
        ]
    },
    # 💡 Tips & Polls (bonus)
    {
        "category": "tips",
        "topics": [
            "Топ-5 ошибок новичка на подворье",
            "Лайфхаки птицевода: экономим на кормах",
            "Опрос: кто живёт на вашем подворье?",
            "Калькулятор прибыли: считаем окупаемость",
        ]
    },
]


def generate_content_plan(days: int = 20, start_date: datetime = None):
    """Generate content plan for N days"""
    if start_date is None:
        start_date = datetime.now()
    
    plan = []
    theme_index = 0
    
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_str = date.strftime("%d_%m_%Y")
        
        # Rotate themes (diverse content)
        category_data = THEMES[theme_index % len(THEMES)]
        topic = category_data["topics"][i % len(category_data["topics"])]
        
        plan.append({
            "date": date_str,
            "category": category_data["category"],
            "topic": topic,
            "folder": f"{i+1:02d}_{category_data['category']}"
        })
        
        theme_index += 1
        # Skip every 5th to make poultry 1 out of 5
        if i % 5 == 4:
            theme_index = 2  # Jump to garden
    
    return plan


def create_content_folders(plan: list):
    """Create content folders with placeholder articles"""
    for item in plan:
        date_path = os.path.join(CONTENT_DIR, item["date"])
        folder_path = os.path.join(date_path, item["folder"])
        os.makedirs(folder_path, exist_ok=True)
        
        # Create post.txt with topic
        post_file = os.path.join(folder_path, "post.txt")
        with open(post_file, "w", encoding="utf-8") as f:
            f.write(f"{item['topic']}\n\n[Текст статьи будет сгенерирован Шекспиром...]\n\n#своёподворье #птицеводство #огород")
        
        print(f"✅ Создано: {item['date']}/{item['folder']} — {item['topic'][:50]}")


if __name__ == "__main__":
    print("="*70)
    print("📅 Контент-план: Своё Подворье (до конца мая 2026)")
    print("="*70)
    print()
    
    # Generate plan from May 16 to May 31 (16 days)
    start = datetime(2026, 5, 16)
    plan = generate_content_plan(days=16, start_date=start)
    
    print(f"📋 Утверждено тем: {len(plan)}")
    print()
    
    for item in plan:
        emoji = {
            "garden": "🥕",
            "rabbits": "🐇",
            "poultry": "🐔",
            "bees": "🐝",
            "tips": "💡"
        }.get(item["category"], "📝")
        
        print(f"{emoji} {item['date']} | {item['topic'][:55]}")
    
    print()
    print("Создаю папки...")
    create_content_folders(plan)
    
    print()
    print("="*70)
    print("✅ Готово! Следующий шаг: запуск Шекспира для генерации текстов")
    print("="*70)
