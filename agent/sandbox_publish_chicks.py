import base64
import os
import re

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def clean_feed():
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.get.json").json().get("result", [])
        for post in resp:
            title = post.get("TITLE", "")
            if "[ФИНАЛ" in title or "Кормление бройлеров" in title:
                post_id = post.get("ID")
                requests.post(f"{BITRIX_URL}/log.blogpost.update.json", json={
                    "POST_ID": post_id,
                    "POST_TITLE": "🗑️ Пост удалён",
                    "POST_MESSAGE": "Очистка."
                })
    except Exception:
        pass

def publish_working_article():
    clean_feed()
    print("Ищем реальное фото цыплят-бройлеров на Википедии...")
    
    headers = {"User-Agent": "VezemCipBot/1.0"}
    # Ищем статью Broiler и её главную картинку
    search_url = "https://en.wikipedia.org/w/api.php?action=query&titles=Broiler&prop=pageimages&format=json&pithumbsize=800"
    resp = requests.get(search_url, headers=headers).json()
    pages = resp.get("query", {}).get("pages", {})
    img_url = ""
    for page_id in pages:
        if "thumbnail" in pages[page_id]:
            img_url = pages[page_id]["thumbnail"]["source"]
            break

    image_path = os.path.join(BASE_DIR, "seo", "content", "real_chicks.jpg")
    
    if img_url:
        print(f"Скачиваю картинку: {img_url}")
        img_data = requests.get(img_url, headers=headers).content
        with open(image_path, "wb") as f:
            f.write(img_data)
        print("✅ Настоящие цыплята скачаны!")
    else:
        print("Ошибка загрузки.")
        return

    article_path = os.path.join(BASE_DIR, "seo", "content", "dzen_article_3_feeding.md")
    with open(article_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Быстрый конвертер MD в BBCODE
    content = re.sub(r'^#\s+(.*)$', r'[SIZE=6][B]\1[/B][/SIZE]', content, flags=re.MULTILINE)
    content = re.sub(r'^##\s+(.*)$', r'[SIZE=5][B]\1[/B][/SIZE]', content, flags=re.MULTILINE)
    content = re.sub(r'^###\s+(.*)$', r'[SIZE=4][B]\1[/B][/SIZE]', content, flags=re.MULTILINE)
    content = re.sub(r'\*\*(.*?)\*\*', r'[B]\1[/B]', content)

    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

    post_text = (
        "[B][COLOR=#ff0000][НА СОГЛАСОВАНИЕ][/COLOR] Финальная статья про цыплят![/B]\n\n"
        "Андрей, Игорь! Теперь загружена ПРАВИЛЬНАЯ фотография (цыплята бройлеры), "
        "мы берем её напрямую из свободных источников.\n\n"
        "--------------------------------------------------\n\n"
        f"{content}"
    )

    print("Публикация в Битрикс...")
    resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
        "POST_TITLE": "📄 [ФИНАЛ] Кормление бройлеров (с цыплятами!)",
        "POST_MESSAGE": post_text,
        "DEST": ["UA"],
        "FILES": [
            ["real_chicks.jpg", encoded_string]
        ]
    }, timeout=30).json()
    
    if resp.get("result"):
        print("✅ Пост с НАСТОЯЩИМИ цыплятами выложен!")
    else:
        print("⚠️ Ошибка выкладки:", resp)

if __name__ == "__main__":
    publish_working_article()
