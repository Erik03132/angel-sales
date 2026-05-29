#!/usr/bin/env python3
"""
📤 VK PUBLISHER — Публикация из /content_day/ в ВК

Берёт посты из /content_day/DD_MM_YYYY/ → загружает фото в ВК → публикует пост

Использование:
    python3 vk_publisher.py publish --date 16_05_2026    — публикация за дату
    python3 vk_publisher.py status                       — статус кэша
    python3 vk_publisher.py upload --folder 01_podvorye  — загрузить фото в кэш
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime

BASE_DIR = "/Users/igorvasin/freelance-2026"
CONTENT_DIR = os.path.join(BASE_DIR, "content_day")
DATA_DIR = os.path.join(BASE_DIR, "ai-eggs", "data")

sys.path.insert(0, os.path.join(BASE_DIR, "ai-eggs", "agent"))

# ─── Загрузка .env ────────────────────────────────────────────────────────────

def load_env():
    env = {}
    env_path = os.path.join(BASE_DIR, "ai-eggs", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env

ENV = load_env()

VK_USER_TOKEN = ENV.get("VK_USER_TOKEN", "")
VK_GROUP_TOKEN = ENV.get("VK_PODVORYE_TOKEN", "")
VK_GROUP_ID = ENV.get("VK_PODVORYE_GROUP_ID", "").lstrip("-")
VK_V = "5.199"

# ─── VK API ───────────────────────────────────────────────────────────────────

def vk_call(method: str, params: dict) -> dict:
    """Вызов VK API через curl"""
    params["access_token"] = VK_USER_TOKEN
    params["v"] = VK_V
    
    url = f"https://api.vk.com/method/{method}"
    cmd = ["curl", "-s", "--max-time", "30", url]
    for k, v in params.items():
        cmd += ["-d", f"{k}={urllib.parse.quote(str(v))}"]
    
    result = subprocess.run(cmd, capture_output=True, timeout=35)
    return json.loads(result.stdout)


def upload_photo_to_vk_cache(photo_path: str) -> str | None:
    """
    Загружает фото в ВК (photos.getWallUploadServer → save).
    Возвращает attachment: photo{owner_id}_{id}
    """
    if not os.path.exists(photo_path):
        print(f"   ❌ Фото не найдено: {photo_path}")
        return None
    
    print(f"   📤 Загрузка фото: {os.path.basename(photo_path)}")
    
    # 1. Получаем URL для загрузки
    upload_data = vk_call("photos.getWallUploadServer", {"group_id": VK_GROUP_ID})
    
    if "error" in upload_data:
        print(f"   ❌ VK API: {upload_data['error']['error_msg']}")
        return None
    
    upload_url = upload_data["response"]["upload_url"]
    print("   📍 Upload URL получен")
    
    # 2. Загружаем файл через curl multipart
    upload_cmd = [
        "curl", "-s", "--max-time", "30",
        "-F", f"photo=@{photo_path}",
        upload_url
    ]
    
    upload_result = subprocess.run(upload_cmd, capture_output=True, timeout=35)
    upload_resp = json.loads(upload_result.stdout)
    
    if not upload_resp.get("photo"):
        print(f"   ❌ Загрузка не удалась: {upload_resp}")
        return None
    
    print("   ✅ Фото загружено на сервер VK")
    
    # 3. Сохраняем фото
    save_data = vk_call("photos.saveWallPhoto", {
        "group_id": VK_GROUP_ID,
        "photo": upload_resp.get("photo", ""),
        "server": upload_resp.get("server", ""),
        "hash": upload_resp.get("hash", ""),
    })
    
    if "error" in save_data:
        print(f"   ❌ VK save: {save_data['error']['error_msg']}")
        return None
    
    photos = save_data.get("response", [])
    if not photos:
        return None
    
    p = photos[0]
    attachment = f"photo{p['owner_id']}_{p['id']}"
    
    print(f"   ✅ Attachment: {attachment}")
    return attachment


def publish_post(text: str, attachment: str = None) -> int | None:
    """Публикует пост в ВК через wall.post (Group Token)"""
    params = {
        "owner_id": f"-{VK_GROUP_ID}",
        "message": text,
        "from_group": "1",
    }
    
    if attachment:
        params["attachments"] = attachment
    
    # Используем Group Token для публикации!
    params["access_token"] = VK_GROUP_TOKEN
    params["v"] = VK_V
    
    url = "https://api.vk.com/method/wall.post"
    cmd = ["curl", "-s", "--max-time", "15", url]
    for k, v in params.items():
        cmd += ["-d", f"{k}={urllib.parse.quote(str(v))}"]
    
    result = subprocess.run(cmd, capture_output=True, timeout=20)
    resp = json.loads(result.stdout)
    
    if "error" in resp:
        print(f"   ❌ Публикация: {resp['error']['error_msg']}")
        return None
    
    post_id = resp["response"].get("post_id")
    print(f"   ✅ Опубликован пост #{post_id}")
    return post_id


# ─── Работа с /content_day/ ───────────────────────────────────────────────────

def get_date_folders() -> list:
    """Возвращает список папок дат в /content_day/"""
    if not os.path.exists(CONTENT_DIR):
        return []
    
    folders = []
    for name in sorted(os.listdir(CONTENT_DIR)):
        folder_path = os.path.join(CONTENT_DIR, name)
        if os.path.isdir(folder_path) and re.match(r"\d{2}_\d{2}_\d{4}", name):
            folders.append(name)
    
    return folders


def get_post_folders(date_folder: str) -> list:
    """Возвращает список постов для даты"""
    date_path = os.path.join(CONTENT_DIR, date_folder)
    if not os.path.exists(date_path):
        return []
    
    folders = []
    for name in sorted(os.listdir(date_path)):
        folder_path = os.path.join(date_path, name)
        if os.path.isdir(folder_path) and re.match(r"\d{2}_", name):
            folders.append(name)
    
    return folders


def publish_folder(date_folder: str, post_folder: str) -> dict:
    """Публикует один пост в ВК"""
    post_path = os.path.join(CONTENT_DIR, date_folder, post_folder)
    post_file = os.path.join(post_path, "post.txt")
    photo_file = os.path.join(post_path, "photo.png")
    
    print(f"\n📝 Публикация: {date_folder}/{post_folder}")
    
    # Читаем текст
    if not os.path.exists(post_file):
        print("   ❌ post.txt не найден")
        return {"status": "error", "error": "no post.txt"}
    
    with open(post_file, "r", encoding="utf-8") as f:
        text = f.read()
    
    print(f"   Текст: {text[:60]}...")
    
    # Загружаем фото
    attachment = None
    if os.path.exists(photo_file):
        attachment = upload_photo_to_vk_cache(photo_file)
    else:
        print("   ⚠️ Фото не найдено — публикация без фото")
    
    # Публикуем
    post_id = publish_post(text, attachment)
    
    if post_id:
        # Сохраняем статус
        status_file = os.path.join(post_path, "status.json")
        status = {
            "vk_post_id": post_id,
            "vk_attachment": attachment,
            "published_at": datetime.now().isoformat(),
            "status": "published"
        }
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        
        print(f"   📊 Статус сохранён: {status_file}")
        
        return {"status": "published", "post_id": post_id, "attachment": attachment}
    else:
        return {"status": "error", "error": "publish failed"}


# ─── CLI ──────────────────────────────────────────────────────────────────────

def cmd_publish(date: str = None):
    """Публикация постов за дату"""
    if not date:
        # Берём сегодняшнюю дату
        date = datetime.now().strftime("%d_%m_%Y")
    
    print(f"📤 Публикация за {date}")
    
    post_folders = get_post_folders(date)
    if not post_folders:
        print("   ⚠️ Постов не найдено")
        return
    
    print(f"   Найдено постов: {len(post_folders)}")
    
    for folder in post_folders:
        result = publish_folder(date, folder)
        print(f"   Результат: {result['status']}")


def cmd_status():
    """Статус кэша"""
    print("📊 /content_day/ статус")
    
    dates = get_date_folders()
    print(f"   Даты: {len(dates)}")
    
    for date in dates:
        posts = get_post_folders(date)
        print(f"   {date}: {len(posts)} постов")
        
        for post in posts:
            status_file = os.path.join(CONTENT_DIR, date, post, "status.json")
            if os.path.exists(status_file):
                with open(status_file) as f:
                    status = json.load(f)
                print(f"      {post}: ✅ VK #{status.get('vk_post_id', '?')}")
            else:
                print(f"      {post}: ⏳ Не опубликован")


def cmd_upload(folder: str):
    """Загрузить фото в кэш ВК"""
    date = datetime.now().strftime("%d_%m_%Y")
    post_path = os.path.join(CONTENT_DIR, date, folder)
    photo_file = os.path.join(post_path, "photo.png")
    
    if not os.path.exists(photo_file):
        print(f"❌ Фото не найдено: {photo_file}")
        return
    
    attachment = upload_photo_to_vk_cache(photo_file)
    if attachment:
        print(f"✅ Загружено: {attachment}")


def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python3 vk_publisher.py publish --date DD_MM_YYYY")
        print("  python3 vk_publisher.py status")
        print("  python3 vk_publisher.py upload --folder XX_name")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "publish":
        date = None
        if "--date" in sys.argv:
            idx = sys.argv.index("--date")
            if idx + 1 < len(sys.argv):
                date = sys.argv[idx + 1]
        cmd_publish(date)
    
    elif command == "status":
        cmd_status()
    
    elif command == "upload":
        folder = None
        if "--folder" in sys.argv:
            idx = sys.argv.index("--folder")
            if idx + 1 < len(sys.argv):
                folder = sys.argv[idx + 1]
        cmd_upload(folder)
    
    else:
        print(f"❌ Неизвестная команда: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
