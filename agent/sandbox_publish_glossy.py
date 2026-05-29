import base64
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

def publish_perfect_article():
    print("Чтение статьи...")
    article_path = os.path.join(BASE_DIR, "seo", "content", "dzen_article_3_feeding.md")
    with open(article_path, "r", encoding="utf-8") as f:
        content = f.read()

    bbcode_content = markdown_to_bbcode(content)
    image_path = os.path.join(BASE_DIR, "seo", "content", "chicks.jpg")
    
    print("Получение ID хранилища Общего диска...")
    storages = requests.post(f"{BITRIX_URL}/disk.storage.getlist.json").json().get("result", [])
    storage_id = None
    for s in storages:
        if "Общий" in str(s.get("NAME")) or s.get("ENTITY_TYPE") == "common":
            storage_id = s.get("ID")
            break
    if not storage_id and storages:
        storage_id = storages[0].get("ID")
        
    print(f"Загрузка картинки на диск (Storage ID: {storage_id})...")
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        
    upload_resp = requests.post(f"{BITRIX_URL}/disk.storage.uploadfile.json", json={
        "id": storage_id,
        "data": {"NAME": "premium_cover.jpg"},
        "fileContent": encoded_string
    }).json()
    
    file_id = upload_resp.get("result", {}).get("ID")
    if not file_id:
        print("Ошибка загрузки файла:", upload_resp)
        return
        
    print(f"Файл успешно загружен. File ID: {file_id}")
    
    post_text = (
        "[B][COLOR=#ff0000][НА СОГЛАСОВАНИЕ][/COLOR] Оформленная статья с иллюстрацией[/B]\n\n"
        "Игорь, вот он — идеальный глянцевый вариант!\n"
        "Мы загрузили картинку напрямую на сервер Битрикса, поэтому теперь она "
        "раскрывается [B]полноценной обложкой[/B], а не просто тегом или ссылкой.\n\n"
        "Это ровно тот формат, который мы ждали.\n"
        "--------------------------------------------------\n\n"
        f"{bbcode_content}"
    )

    print("Публикация поста с привязанным файлом-обложкой...")
    resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
        "POST_TITLE": "🌟 [ГЛЯНЕЦ] Кормление бройлеров",
        "POST_MESSAGE": post_text,
        "DEST": ["UA"],
        "FILES": [f"n{file_id}"]  # 'n' + ID файла — это внутренний формат прикрепления с диска в Битрикс!
    }, timeout=30).json()
    
    if resp.get("result"):
        print("✅ Идеальный пост с обложкой на диске выложен!")
    else:
        print("⚠️ Ошибка выкладки:", resp)

if __name__ == "__main__":
    publish_perfect_article()
