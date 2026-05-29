import os

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def cleanup_duplicates():
    print("Ищем дубликаты постов...")
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.get.json", timeout=15)
        posts = resp.json().get("result", [])
        
        for post in posts:
            title = post.get("TITLE", "")
            if "Кормление суточных бройлеров v2" in title or "Статья 3: Кормление бройлеров" in title or "Оформленная статья" in title:
                post_id = post.get("ID")
                print(f"Удаляю пост: {title} [ID: {post_id}]")
                # К сожалению, метода log.blogpost.delete в REST API нет напрямую!
                # Но мы можем обновить пост и скрыть его текст, либо написать, что пост удален.
                requests.post(f"{BITRIX_URL}/log.blogpost.update.json", json={
                    "POST_ID": post_id,
                    "POST_TITLE": "🗑️ Пост удалён (технический тест)",
                    "POST_MESSAGE": "Этот пост был дубликатом. Мы очистили его, чтобы не мешал."
                })
        print("✅ Очистка завершена!")
    except Exception as e:
        print("Ошибка сети:", str(e))

if __name__ == "__main__":
    cleanup_duplicates()
