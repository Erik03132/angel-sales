import os

import requests
from dotenv import load_dotenv

load_dotenv()

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

POST_TITLE = "📢 ПОПОЛНЕНИЕ ПЛАНА ПРОДВИЖЕНИЯ (АНЖЕЛА ПТЕНЧИКОВА)"
POST_MESSAGE = """
Бро, я расширила Мастер-план! Теперь там полный фарш. 

🚀 **Добавлено в бэклог:**
- **Одноклассники:** Реакция профиля (там 2900+ друзей, это же золотая жила!) и настройка группы.
- **MAX Messenger:** Полная стыковка с CRM.
- **Авито 2.0:** План на 20 сочных объявлений по алгоритмам 2026 года.

⚠️ **Жду твоей отмашки по:**
1. Оплате тарифа "Расширенный" на Авито (без него 20 штук не пульнуть).
2. Логинам/паролям от ВК и Одноклассников.

Как только дашь доступы — я влетаю и начинаю бомбить контентом! 🐥🔥
"""

def post_to_feed(title, message):
    url = f"{BITRIX_URL}/log.blogpost.add.json"
    params = {
        "POST_TITLE": title,
        "POST_MESSAGE": message,
        "DEST": ["UA"] # All users
    }
    resp = requests.post(url, json=params)
    return resp.json()

if __name__ == "__main__":
    print("📡 Публикация в Живую ленту...")
    res = post_to_feed(POST_TITLE, POST_MESSAGE)
    if "result" in res:
        print(f"✅ Пост опубликован! ID: {res['result']}")
    else:
        print(f"❌ Ошибка: {res}")
