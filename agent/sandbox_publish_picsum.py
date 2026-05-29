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
            if "[ФИНАЛ 3000]" in title:
                post_id = post.get("ID")
                requests.post(f"{BITRIX_URL}/log.blogpost.update.json", json={
                    "POST_ID": post_id,
                    "POST_TITLE": "🗑️ Пост удалён (сломанное фото)",
                    "POST_MESSAGE": "Очистка."
                })
    except Exception:
        pass

def publish_working_article():
    clean_feed()
    print("Скачиваем НАДЕЖНУЮ тестовую картинку (Picsum)...")
    
    image_path = os.path.join(BASE_DIR, "seo", "content", "real_image.jpg")
    img_resp = requests.get("https://picsum.photos/800/400")
    
    if img_resp.status_code == 200 and img_resp.content.startswith(b'\xff\xd8'): # Проверка на реальный JPEG
        with open(image_path, "wb") as f:
            f.write(img_resp.content)
        print("✅ Изображение скачано и проверено (это 100% JPEG, а не HTML!)")
    else:
        print("Ошибка скачивания картинки!")
        return

    article_path = os.path.join(BASE_DIR, "seo", "content", "dzen_article_3_feeding.md")
    with open(article_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'^#\s+(.*)$', r'[SIZE=6][B]\1[/B][/SIZE]', content, flags=re.MULTILINE)
    content = re.sub(r'^##\s+(.*)$', r'[SIZE=5][B]\1[/B][/SIZE]', content, flags=re.MULTILINE)
    content = re.sub(r'^###\s+(.*)$', r'[SIZE=4][B]\1[/B][/SIZE]', content, flags=re.MULTILINE)
    content = re.sub(r'\*\*(.*?)\*\*', r'[B]\1[/B]', content)

    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

    post_text = (
        "[B][COLOR=#ff0000][НА СОГЛАСОВАНИЕ][/COLOR] Финальная статья[/B]\n\n"
        "Андрей, Игорь! Я нашел причину: Википедия вместо картинки отдала мне HTML-страницу с ошибкой, "
        "а я не глядя прикрепил её как JPEG. Теперь я добавил проверку байтов: скрипт скачивает "
        "случайную фотографию (заглушку) и проверяет, что это реально картинка.\n\n"
        "Жмите на скрепку внизу — теперь там 100% откроется фото!\n"
        "--------------------------------------------------\n\n"
        f"{content}"
    )

    print("Заливаем в Битрикс...")
    resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
        "POST_TITLE": "📄 [ТЕПЕРЬ ТОЧНО ФИНАЛ] Кормление бройлеров",
        "POST_MESSAGE": post_text,
        "DEST": ["UA"],
        "FILES": [
            ["cover.jpg", encoded_string]
        ]
    }, timeout=30).json()
    
    if resp.get("result"):
        print("✅ Пост с ПРОВЕРЕННОЙ картинкой выложен!")
    else:
        print("⚠️ Ошибка выкладки:", resp)

if __name__ == "__main__":
    publish_working_article()
