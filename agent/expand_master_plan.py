import os

import requests
from dotenv import load_dotenv

load_dotenv()

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")
TASK_ID = 22 # ID из предыдущего шага

NEW_ITEMS = [
    "ОЖИДАНИЕ: Оплата тарифа 'Расширенный' на Авито (для 20 новых объявлений)",
    "ОЖИДАНИЕ: Логины/Пароли ВК (проверка доступов для Мини-аппа)",
    "ОЖИДАНИЕ: Логины/Пароли Одноклассники",
    "ОК: Реактивация профиля (2900+ друзей) и группы",
    "МАКС: Полная интеграция мессенджера в CRM",
    "АВИТО: Запуск 20 новых объявлений (Масштабирование)",
    "АВИТО: Настройка коллтрекинга и защиты от пропущенных звонков",
    "ДЗЕН: Публикация 2-го блока статей (кейсы и отзывы)"
]

def add_checklist_item(task_id, item_title):
    url = f"{BITRIX_URL}/task.checklistitem.add.json"
    params = {
        "taskId": task_id,
        "fields": {
            "TITLE": item_title,
            "IS_COMPLETE": "N"
        }
    }
    resp = requests.post(url, json=params)
    return resp.json()

if __name__ == "__main__":
    print(f"🔄 Дополнение Мастер-Плана (Задание ID: {TASK_ID})...")
    for item in NEW_ITEMS:
        res = add_checklist_item(TASK_ID, item)
        if "result" in res:
            print(f"   + Добавлено: {item}")
        else:
            print(f"   - ❌ Ошибка: {res}")
    print("\n✅ マстер-план расширен до полной версии.")
