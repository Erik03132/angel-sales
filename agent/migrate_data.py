import os
import json
from vector_db import AngelochkaVectorDB

def run_migration():
    vdb = AngelochkaVectorDB()
    if not vdb.enabled:
        print("❌ Ошибка: Neon DB не настроен. Проверь .env")
        return

    # Загружаем унифицированные знания (Bitrix + Avito + VK)
    brain_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'angelochka_unified_brain.json')
    
    if not os.path.exists(brain_path):
        print(f"❌ Файл {brain_path} не найден. Сначала запусти unify_brain.py")
        return

    with open(brain_path, 'r', encoding='utf-8') as f:
        knowledge = json.load(f)

    print(f"🚀 Начинаю миграцию {len(knowledge)} элементов в Neon DB...")
    
    for i, item in enumerate(knowledge):
        print(f"[{i+1}/{len(knowledge)}] Индексирую: {item['content'][:50]}...")
        vdb.add_knowledge(item['content'], item['metadata'])
        import time
        time.sleep(1.0) # Задержка для обхода лимитов API

    print("✨ Миграция успешно завершена! Анжелочка теперь в облаке.")

if __name__ == "__main__":
    run_migration()
