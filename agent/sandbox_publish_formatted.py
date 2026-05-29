import os
import re

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def markdown_to_bbcode(text):
    text = re.sub(r'^#\s+(.*)$', r'[SIZE=6][B]\1[/B][/SIZE]', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.*)$', r'[SIZE=5][B]\1[/B][/SIZE]', text, flags=re.MULTILINE)
    text = re.sub(r'^###\s+(.*)$', r'[SIZE=4][B]\1[/B][/SIZE]', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.*?)\*\*', r'[B]\1[/B]', text)
    
    lines = text.split('\n')
    in_list = False
    result = []
    for line in lines:
        if line.startswith('*   ') or line.startswith('-   ') or line.startswith('* '):
            if not in_list:
                result.append('[LIST]')
                in_list = True
            result.append(f'[*] {line[2:].strip()}')
        else:
            if in_list:
                result.append('[/LIST]')
                in_list = False
            result.append(line)
    if in_list:
        result.append('[/LIST]')
    return '\n'.join(result)

def publish_formatted_article():
    article_path = os.path.join(BASE_DIR, "seo", "content", "dzen_article_3_feeding.md")
    
    try:
        with open(article_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print("Ошибка чтения файла статьи:", str(e))
        return

    bbcode_content = markdown_to_bbcode(content)
    
    # Прямая ссылка на картинку в интернете (чтобы Битрикс сам раскрыл её в посте)
    IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Bresse_chicks.jpg/800px-Bresse_chicks.jpg"

    post_text = (
        "[B][COLOR=#ff0000][НА СОГЛАСОВАНИЕ][/COLOR] Оформленная статья с иллюстрацией[/B]\n\n"
        "Андрей, Игорь! Теперь картинка не прикреплена файлом, а [B]интегрирована прямо в текст[/B] (как обложка), "
        "чтобы вы могли оценить итоговый вид.\n"
        "--------------------------------------------------\n\n"
        f"[IMG]{IMAGE_URL}[/IMG]\n\n"
        f"{bbcode_content}"
    )
    
    print("Отправляем в Живую Ленту с inline-картинкой...")
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
            "POST_TITLE": "📄 [ФИНАЛ] Кормление суточных бройлеров v2",
            "POST_MESSAGE": post_text,
            "DEST": ["UA"]
        }, timeout=30)
        res = resp.json()
        if res.get("result"):
            print("✅ Отформатированная статья успешно выложена!")
        else:
            print("⚠️ Ошибка выкладки:", res)
    except Exception as e:
        print("Ошибка сети:", str(e))

if __name__ == "__main__":
    publish_formatted_article()
