import base64
import os

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def publish_article_with_image():
    print("Чтение текста статьи...")
    article_path = os.path.join(BASE_DIR, "seo", "content", "dzen_article_3_feeding.md")
    try:
        with open(article_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print("Ошибка чтения файла статьи:", str(e))
        return

    # Загружаем сгенерированную картинку
    image_path = "/Users/igorvasin/.gemini/antigravity/brain/52ca0a9b-b226-41b2-b52d-47c4187e40f4/feeding_chicks_cover_1777051966891.png"
    print("Кодируем картинку в base64...")
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        print("Ошибка чтения картинки:", str(e))
        return

    post_text = (
        "📝 **[НА СОГЛАСОВАНИЕ] Оформленная статья с иллюстрацией** 📝\n\n"
        "Андрей, посмотри, как выглядит итоговый вариант статьи вместе с уникальной картинкой от нашего Рембрандта.\n\n"
        "Алгоритмы Дзена очень жестко наказывают за столы из интернета. Поэтому этот кадр был сгенерирован с нуля "
        "и является 100% уникальным, что даст статье турбо-буст при публикации.\n\n"
        "--------------------------------------------------\n\n"
        f"{content}"
    )
    
    print("Отправляем в Живую Ленту с прикрепленной фотографией...")
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
            "POST_TITLE": "📄 Статья 3: Кормление бройлеров (с иллюстрацией!)",
            "POST_MESSAGE": post_text,
            "DEST": ["UA"],
            "FILES": [
                ["feeding_chicks.png", encoded_string]
            ]
        }, timeout=30)
        res = resp.json()
        if res.get("result"):
            print("✅ Статья с картинкой успешно выложена в Живую Ленту!")
        else:
            print("⚠️ Ошибка выкладки:", res)
    except Exception as e:
        print("Ошибка сети:", str(e))

if __name__ == "__main__":
    publish_article_with_image()
