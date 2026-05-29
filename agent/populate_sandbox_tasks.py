import os

import requests
from dotenv import load_dotenv

load_dotenv()

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")
PTENCHIKOVA_ID = 15

TASKS = [
    {
        "TITLE": "[ПРОМО] Публикация в Dзен: 5 ошибок при покупке цыплят",
        "DESCRIPTION": "Заливка первой статьи из 'Контент-машины'. Оптимизация заголовка и тегов под E-E-A-T.",
        "DEADLINE": "2026-04-26T18:00:00",
    },
    {
        "TITLE": "[ПРОМО] Авито Sniper Shot: А/В Тест Бройлер КОББ-500",
        "DESCRIPTION": "Запустить новое объявление по формуле PMPHS. Сравнить CTR со старым объявлением через 5 дней.",
        "DEADLINE": "2026-04-30T10:00:00",
    },
    {
        "TITLE": "[ПРОМО] Авито Sniper Shot: Оффер Индюки БИГ-6",
        "DESCRIPTION": "Обновление текста на 'Тяжеловесы до 25 кг'. Добавить триггер 'Вет-аптечка в подарок'.",
        "DEADLINE": "2026-04-27T18:00:00",
    },
    {
        "TITLE": "[ПРОМО] VK Mini App: Финальный деплой и проверка калькулятора",
        "DESCRIPTION": "Убедиться, что калькулятор кормов Purina работает корректно и данные улетают в CRM.",
        "DEADLINE": "2026-04-26T12:00:00",
    },
    {
        "TITLE": "[ПРОМО] SEO: Schema.org разметка (Product/Offer) на vezemcip.ru",
        "DESCRIPTION": "Разметить карточки товаров для индексации нейросетями Perplexity и ChatGPT.",
        "DEADLINE": "2026-04-28T18:00:00",
    },
    {
        "TITLE": "[ПРОМО] Реактивация: Массовая рассылка по 'спящей' базе",
        "DESCRIPTION": "Подготовить скрипт рассылки в TG/SMS со ссылкой на новый сайт и акцией на первый заказ.",
        "DEADLINE": "2026-04-29T18:00:00",
    }
]

def add_task(task_data):
    url = f"{BITRIX_URL}/tasks.task.add.json"
    params = {
        "fields": {
            "TITLE": task_data["TITLE"],
            "DESCRIPTION": task_data["DESCRIPTION"],
            "RESPONSIBLE_ID": PTENCHIKOVA_ID,
            "DEADLINE": task_data["DEADLINE"],
            "CREATED_BY": 1 # Гусь Лапчатый (Игорь)
        }
    }
    resp = requests.post(url, json=params)
    return resp.json()

if __name__ == "__main__":
    print("🚀 Анжела Птенчикова начинает занос задач в CRM...")
    for t in TASKS:
        res = add_task(t)
        if "result" in res:
            print(f"✅ Добавлена задача: {t['TITLE']} (ID: {res['result']['task']['id']})")
        else:
            print(f"❌ Ошибка при добавлении {t['TITLE']}: {res}")
