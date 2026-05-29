import os

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def publish_article_to_feed():
    print("Чтение статьи...")
    article_path = os.path.join(BASE_DIR, "seo", "content", "dzen_article_2_cobb_vs_ross.md")
    
    try:
        with open(article_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print("Ошибка чтения файла:", str(e))
        return

    post_text = (
        "📝 **[НА СОГЛАСОВАНИЕ] Бройлеры РОСС-308 или КОББ-500** 📝\n\n"
        "Андрей, Игорь! Шекспир написал эту статью в стиле E-E-A-T (Экспертность, Авторитетность, Человечность), "
        "чтобы нейросети Яндекса не распознали генерацию и дали ей зеленый свет в ранжировании.\n\n"
        "Оцените текст (если всё ОК — отложим до получения доступов в Дзен/ВК):\n"
        "--------------------------------------------------\n\n"
        f"{content}"
    )
    
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
            "POST_TITLE": "📄 Проект статьи: КОББ-500 vs РОСС-308",
            "POST_MESSAGE": post_text,
            "DEST": ["UA"] 
        }, timeout=15)
        print("✅ Статья успешно выложена в Живую Ленту!")
    except Exception as e:
        print("Ошибка сети:", str(e))

if __name__ == "__main__":
    publish_article_to_feed()
