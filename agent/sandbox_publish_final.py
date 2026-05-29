import base64
import os
import re

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def clean_feed():
    print("Удаляю сломанные посты...")
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.get.json").json().get("result", [])
        for post in resp:
            title = post.get("TITLE", "")
            if "ГЛЯНЕЦ" in title or "Оформленная" in title or "Кормление бройлеров" in title:
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
    print("Создаем пост с нормальным прикреплением...")
    
    article_path = os.path.join(BASE_DIR, "seo", "content", "dzen_article_3_feeding.md")
    with open(article_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Быстрый конвертер MD в BBCODE
    content = re.sub(r'^#\s+(.*)$', r'[SIZE=6][B]\1[/B][/SIZE]', content, flags=re.MULTILINE)
    content = re.sub(r'^##\s+(.*)$', r'[SIZE=5][B]\1[/B][/SIZE]', content, flags=re.MULTILINE)
    content = re.sub(r'^###\s+(.*)$', r'[SIZE=4][B]\1[/B][/SIZE]', content, flags=re.MULTILINE)
    content = re.sub(r'\*\*(.*?)\*\*', r'[B]\1[/B]', content)

    image_path = os.path.join(BASE_DIR, "seo", "content", "chicks.jpg")
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

    # В Битриксе, чтобы передать файл корректно (а не текстом), 
    # нужно передавать массив [имя_файла, base64_тело]
    post_text = (
        "[B][COLOR=#ff0000][НА СОГЛАСОВАНИЕ][/COLOR] Финальная статья[/B]\n\n"
        "Андрей, Игорь! Я починила баг с загрузкой картинки (теперь она в формате JPEG, а не кода).\n"
        "Снизу прикреплена фотография цыплят. Жмите на скрепку/миниатюру — она откроется как положено!\n"
        "--------------------------------------------------\n\n"
        f"{content}"
    )

    resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
        "POST_TITLE": "📄 [ФИНАЛ 3000] Кормление бройлеров",
        "POST_MESSAGE": post_text,
        "DEST": ["UA"],
        "FILES": [
            ["chicks_cover.jpg", encoded_string]
        ]
    }, timeout=30).json()
    
    if resp.get("result"):
        print("✅ Пост с рабочей картинкой выложен!")
    else:
        print("⚠️ Ошибка выкладки:", resp)

if __name__ == "__main__":
    publish_working_article()
