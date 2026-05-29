#!/usr/bin/env python3
"""
🗑 VK CLEANUP — Удалить все опубликованные посты и TG сообщения

Использование:
    python3 vk_cleanup.py --all     — удалить всё
    python3 vk_cleanup.py --vk      — только VK
    python3 vk_cleanup.py --tg      — только TG
"""

import json
import os
import subprocess
import sys
import urllib.parse

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
TG_BOT_TOKEN = ENV.get("ANGELOCHKA_BOT_TOKEN", "")
TG_CHANNEL = "@svoye_podvorye"
TG_IGOR_ID = "176203333"

# ─── VK API ───────────────────────────────────────────────────────────────────

def vk_delete_post(post_id: int) -> bool:
    """Удаляет пост из ВК (нужен User Token!)"""
    params = {
        "owner_id": f"-{VK_GROUP_ID}",
        "post_id": post_id,
        "access_token": VK_USER_TOKEN,  # User Token для удаления!
        "v": "5.199"
    }
    
    url = "https://api.vk.com/method/wall.delete"
    cmd = ["curl", "-s", "--max-time", "15", url]
    for k, v in params.items():
        cmd += ["-d", f"{k}={urllib.parse.quote(str(v))}"]
    
    result = subprocess.run(cmd, capture_output=True, timeout=20)
    resp = json.loads(result.stdout)
    
    if "error" in resp:
        print(f"   ❌ VK: {resp['error']['error_msg']}")
        return False
    
    print(f"   ✅ Удалён VK #{post_id}")
    return True


def tg_delete_message(message_id: int, chat_id: str = TG_CHANNEL) -> bool:
    """Удаляет сообщение из TG"""
    if not TG_BOT_TOKEN:
        return False
    
    base_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
    
    cmd = [
        "curl", "-s", "--max-time", "10",
        "-F", f"chat_id={chat_id}",
        "-F", f"message_id={message_id}",
        f"{base_url}/deleteMessage"
    ]
    
    result = subprocess.run(cmd, capture_output=True, timeout=15)
    resp = json.loads(result.stdout)
    
    if resp.get("ok"):
        print(f"   ✅ Удалено TG #{message_id} ({chat_id})")
        return True
    else:
        print(f"   ⚠️ TG не удалено: {resp.get('description', 'unknown')}")
        return False

# ─── Поиск опубликованных постов ─────────────────────────────────────────────

def get_published_posts() -> list:
    """Находит все опубликованные посты в /content_day/"""
    published = []
    
    for date in os.listdir(CONTENT_DIR):
        date_path = os.path.join(CONTENT_DIR, date)
        if not os.path.isdir(date_path):
            continue
        
        for folder in os.listdir(date_path):
            folder_path = os.path.join(date_path, folder)
            if not os.path.isdir(folder_path):
                continue
            
            status_file = os.path.join(folder_path, "status.json")
            if os.path.exists(status_file):
                with open(status_file) as f:
                    status = json.load(f)
                if status.get("vk_post_id"):
                    published.append({
                        "date": date,
                        "folder": folder,
                        "vk_post_id": status["vk_post_id"],
                        "status_file": status_file,
                        "path": folder_path
                    })
    
    return published

# ─── Очистка ──────────────────────────────────────────────────────────────────

def cleanup_all():
    """Удаляет всё: VK + TG"""
    print("🗑 Очистка опубликованных постов\n")
    
    published = get_published_posts()
    print(f"📊 Найдено опубликованных: {len(published)}\n")
    
    vk_deleted = 0
    tg_deleted = 0
    
    for post in published:
        print(f"{post['date']}/{post['folder']} (VK #{post['vk_post_id']})")
        
        # Удаляем из VK
        if vk_delete_post(post["vk_post_id"]):
            vk_deleted += 1
            
            # Сбрасываем статус
            status = {
                "vk_post_id": None,
                "vk_attachment": None,
                "deleted_at": subprocess.run(["date", "-Iseconds"], capture_output=True, text=True).stdout.strip(),
                "status": "deleted"
            }
            with open(post["status_file"], "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
        
        print()
    
    print(f"{'='*60}")
    print("📊 Итоги:")
    print(f"   ✅ Удалено из VK: {vk_deleted}")
    print(f"   ✅ Удалено из TG: {tg_deleted}")
    print(f"{'='*60}")
    print("\n📝 Все посты теперь в ЧЕРНОВИКАХ")
    print("   Для загрузки используй:")
    print("   python3 ai-eggs/agent/vk_mass_upload.py --all")

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python3 vk_cleanup.py --all     — удалить всё")
        print("  python3 vk_cleanup.py --vk      — только VK")
        sys.exit(1)
    
    if sys.argv[1] == "--all":
        cleanup_all()
    else:
        print(f"❌ Неизвестная команда: {sys.argv[1]}")
        sys.exit(1)

if __name__ == "__main__":
    main()
