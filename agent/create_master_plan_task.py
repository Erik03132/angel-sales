import os

import requests
from dotenv import load_dotenv

load_dotenv()

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")
PTENCHIKOVA_ID = 15

# ГЕНЕРАЛЬНЫЙ ПЛАН
CHECKLIST_ITEMS = [
    {"TITLE": "SEO: Создать и внедрить llms.txt", "IS_COMPLETE": "Y"},
    {"TITLE": "SEO: Внедрить микроразметку Schema.org (Product/Offer)", "IS_COMPLETE": "N"},
    {"TITLE": "SEO: Оптимизация под Voice Search (блоки ответов)", "IS_COMPLETE": "N"},
    {"TITLE": "DZEN: Публикация статьи '5 ошибок при покупке цыплят'", "IS_COMPLETE": "N"},
    {"TITLE": "DZEN: Публикация статьи 'КОББ-500 vs РОСС-308'", "IS_COMPLETE": "N"},
    {"TITLE": "DZEN: Публикация статьи 'Чем кормить бройлера'", "IS_COMPLETE": "N"},
    {"TITLE": "AVITO: Запуск A/B теста (Оффер Бройлер)", "IS_COMPLETE": "N"},
    {"TITLE": "AVITO: Запуск A/B теста (Оффер Индюк БИГ-6)", "IS_COMPLETE": "N"},
    {"TITLE": "AVITO: Запуск A/B теста (Оффер Утка Муллард)", "IS_COMPLETE": "N"},
    {"TITLE": "AVITO: Настройка регионального постинга (08:30)", "IS_COMPLETE": "N"},
    {"TITLE": "VK: Полный ребрендинг группы (Обложка + Описание)", "IS_COMPLETE": "N"},
    {"TITLE": "VK: Деплой и запуск Mini App (Калькулятор кормов)", "IS_COMPLETE": "N"},
    {"TITLE": "CRM: Массовая рассылка по 'спящей' базе (Реактивация)", "IS_COMPLETE": "N"}
]

def create_master_task():
    url = f"{BITRIX_URL}/tasks.task.add.json"
    description = (
        "[B]Генеральный план продвижения IncuBird 2.0[/B]\n\n"
        "Этот документ является дорожной картой для Анжелы Птенчиковой. "
        "Здесь собраны все микро-задачи Фазы 2. По мере выполнения я буду проставлять галочки.\n\n"
        "Артемий (Фронтенд) и Шекспир (Копирайт) работают по этому же списку."
    )
    params = {
        "fields": {
            "TITLE": "🚀 INCUBIRD 2.0: ГЕНЕРАЛЬНЫЙ ПЛАН ПРОДВИЖЕНИЯ",
            "DESCRIPTION": description,
            "RESPONSIBLE_ID": PTENCHIKOVA_ID,
            "PRIORITY": "2", # High
            "GROUP_ID": 0 # Sandbox default
        }
    }
    resp = requests.post(url, json=params)
    result = resp.json()
    if "result" in result:
        return result["result"]["task"]["id"]
    return None

def add_checklist_item(task_id, item_title, is_complete="N"):
    url = f"{BITRIX_URL}/task.checklistitem.add.json"
    params = {
        "taskId": task_id,
        "fields": {
            "TITLE": item_title,
            "IS_COMPLETE": is_complete
        }
    }
    resp = requests.post(url, json=params)
    return resp.json()

if __name__ == "__main__":
    print("🛠 Создание генерального плана в CRM...")
    task_id = create_master_task()
    
    if task_id:
        print(f"✅ Мастер-задача создана (ID: {task_id})")
        for item in CHECKLIST_ITEMS:
            res = add_checklist_item(task_id, item["TITLE"], item["IS_COMPLETE"])
            if "result" in res:
                print(f"   - Добавлен пункт: {item['TITLE']}")
            else:
                print(f"   - ❌ Ошибка в пункте {item['TITLE']}: {res}")
        print("\n🚀 План полностью развернут. Можете проверять галочки!")
    else:
        print("❌ Ошибка при создании мастер-задачи.")
