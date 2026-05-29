#!/usr/bin/env python3
"""
📦 VK MASS UPLOAD — Загрузить 20 постов в ВК за 1 раз

Использование (когда сеть заработает):
    python3 vk_mass_upload.py --all      — загрузить все 20 постов
    python3 vk_mass_upload.py --date DD_MM_YYYY — за дату
"""

import json
import os
import subprocess
import sys
import urllib.parse
from datetime import datetime

BASE_DIR = "/Users/igorvasin/freelance-2026"
CONTENT_DIR = os.path.join(BASE_DIR, "content_day")

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

def vk_call(method: str, params: dict, token: str = None) -> dict:
    """Вызов VK API через curl"""
    if token:
        params["access_token"] = token
    params["v"] = VK_V
    
    url = f"https://api.vk.com/method/{method}"
    cmd = ["curl", "-s", "--max-time", "30", url]
    for k, v in params.items():
        cmd += ["-d", f"{k}={urllib.parse.quote(str(v))}"]
    
    result = subprocess.run(cmd, capture_output=True, timeout=35)
    return json.loads(result.stdout)


def upload_photo(photo_path: str) -> str | None:
    """Загружает фото в ВК → возвращает attachment"""
    if not os.path.exists(photo_path):
        return None
    
    # 1. Получаем URL
    upload_data = vk_call("photos.getWallUploadServer", 
                         {"group_id": VK_GROUP_ID}, 
                         VK_USER_TOKEN)
    
    if "error" in upload_data:
        print(f"   ❌ {upload_data['error']['error_msg']}")
        return None
    
    upload_url = upload_data["response"]["upload_url"]
    
    # 2. Загружаем
    upload_cmd = [
        "curl", "-s", "--max-time", "30",
        "-F", f"photo=@{photo_path}",
        upload_url
    ]
    
    upload_result = subprocess.run(upload_cmd, capture_output=True, timeout=35)
    upload_resp = json.loads(upload_result.stdout)
    
    if not upload_resp.get("photo"):
        return None
    
    # 3. Сохраняем
    save_data = vk_call("photos.saveWallPhoto", {
        "group_id": VK_GROUP_ID,
        "photo": upload_resp.get("photo", ""),
        "server": upload_resp.get("server", ""),
        "hash": upload_resp.get("hash", ""),
    }, VK_USER_TOKEN)
    
    if "error" in save_data:
        return None
    
    photos = save_data.get("response", [])
    if not photos:
        return None
    
    p = photos[0]
    return f"photo{p['owner_id']}_{p['id']}"


def publish_draft(text: str, attachment: str = None, scheduled_time: int = None) -> int | None:
    """Публикует пост или создаёт отложенный"""
    params = {
        "owner_id": f"-{VK_GROUP_ID}",
        "message": text,
        "from_group": "1",
    }
    
    if attachment:
        params["attachments"] = attachment
    
    # Если указано время — создаём отложенный пост
    if scheduled_time:
        params["publish_date"] = scheduled_time
    
    result = vk_call("wall.post", params, VK_GROUP_TOKEN)
    
    if "error" in result:
        print(f"   ❌ {result['error']['error_msg']}")
        return None
    
    response = result.get("response", {})
    post_id = response.get("post_id")
    
    if scheduled_time:
        print(f"   ⏰ Отложено на: {datetime.fromtimestamp(scheduled_time).strftime('%d.%m %H:%M')}")
    else:
        print(f"   ✅ Опубликовано: VK #{post_id}")
    
    return post_id


# ─── Массовая загрузка ───────────────────────────────────────────────────────

def get_all_posts() -> list:
    """Возвращает список всех постов в /content_day/"""
    posts = []
    
    if not os.path.exists(CONTENT_DIR):
        return posts
    
    for date in sorted(os.listdir(CONTENT_DIR)):
        date_path = os.path.join(CONTENT_DIR, date)
        if not os.path.isdir(date_path):
            continue
        
        for folder in sorted(os.listdir(date_path)):
            folder_path = os.path.join(date_path, folder)
            if not os.path.isdir(folder_path):
                continue
            
            post_file = os.path.join(folder_path, "post.txt")
            photo_file = os.path.join(folder_path, "photo.png")
            
            if os.path.exists(post_file):
                posts.append({
                    "date": date,
                    "folder": folder,
                    "post_file": post_file,
                    "photo_file": photo_file if os.path.exists(photo_file) else None,
                    "path": folder_path
                })
    
    return posts


def upload_all_posts(dry_run: bool = False, scheduled: bool = False):
    """Загружает все посты в ВК"""
    posts = get_all_posts()
    
    print(f"📦 Найдено постов: {len(posts)}")
    print("🕐 Токен действителен 24 часа — успеваем загрузить все!")
    if scheduled:
        print("📅 Режим: ОТЛОЖЕННЫЕ посты (по дате из папки)")
    else:
        print("📝 Режим: ЧЕРНОВИКИ (не опубликованы)")
    print()
    
    results = {"uploaded": 0, "failed": 0, "skipped": 0}
    
    for i, post in enumerate(posts, 1):
        print(f"\n[{i}/{len(posts)}] {post['date']}/{post['folder']}")
        
        # Читаем текст
        with open(post["post_file"], "r", encoding="utf-8") as f:
            text = f.read()
        
        print(f"   Текст: {text[:50]}...")
        
        # Проверяем статус
        status_file = os.path.join(post["path"], "status.json")
        if os.path.exists(status_file):
            with open(status_file) as f:
                status = json.load(f)
            if status.get("status") == "published":
                print(f"   ⏭️ Уже опубликовано (VK #{status.get('vk_post_id')})")
                results["skipped"] += 1
                continue
        
        # Загружаем фото
        attachment = None
        if post["photo_file"]:
            if not dry_run:
                attachment = upload_photo(post["photo_file"])
                if attachment:
                    print(f"   ✅ Фото: {attachment}")
                else:
                    print("   ⚠️ Фото не загружено")
            else:
                attachment = "photoX_X"  # dry-run
                print("   📸 [DRY] Фото готово")
        
        # Рассчитываем время публикации (из даты папки)
        scheduled_time = None
        if scheduled and not dry_run:
            try:
                # Формат: DD_MM_YYYY
                day, month, year = post["date"].split("_")
                pub_date = datetime(int(year), int(month), int(day), 10, 0)  # 10:00 MSK
                scheduled_time = int(pub_date.timestamp())
                print(f"   📅 Публикация: {pub_date.strftime('%d.%m.%Y %H:%M')}")
            except Exception as e:
                print(f"   ⚠️ Не удалось рассчитать дату: {e}")
                scheduled = False  # fallback на черновики
        
        # Публикуем / создаём черновик
        if not dry_run:
            post_id = publish_draft(text, attachment, scheduled_time if scheduled else None)
            if post_id:
                results["uploaded"] += 1
                
                # Сохраняем статус
                status = {
                    "vk_post_id": post_id,
                    "vk_attachment": attachment,
                    "published_at": datetime.now().isoformat(),
                    "scheduled_time": scheduled_time,
                    "status": "scheduled" if scheduled_time else "draft"
                }
                with open(status_file, "w", encoding="utf-8") as f:
                    json.dump(status, f, ensure_ascii=False, indent=2)
            else:
                print("   ❌ Не опубликовано")
                results["failed"] += 1
        else:
            print("   📝 [DRY] Будет опубликовано")
            results["uploaded"] += 1
    
    # Итог
    print(f"\n{'='*60}")
    print("📊 Итоги:")
    print(f"   ✅ Загружено: {results['uploaded']}")
    print(f"   ❌ Ошибки: {results['failed']}")
    print(f"   ⏭️ Пропущено: {results['skipped']}")
    if scheduled:
        print("   📅 Все посты в ОТЛОЖЕННЫХ")
    else:
        print("   📝 Все посты в ЧЕРНОВИКАХ")
    print(f"{'='*60}")
    
    return results


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python3 vk_mass_upload.py --all          — загрузить все (черновики)")
        print("  python3 vk_mass_upload.py --scheduled    — в ОТЛОЖЕННЫЕ (по дате)")
        print("  python3 vk_mass_upload.py --dry-run      — тест без загрузки")
        sys.exit(1)
    
    if sys.argv[1] == "--all":
        upload_all_posts(dry_run=False, scheduled=False)
    elif sys.argv[1] == "--scheduled":
        upload_all_posts(dry_run=False, scheduled=True)
    elif sys.argv[1] == "--dry-run":
        upload_all_posts(dry_run=True, scheduled=False)
    else:
        print(f"❌ Неизвестная команда: {sys.argv[1]}")
        sys.exit(1)

if __name__ == "__main__":
    main()
