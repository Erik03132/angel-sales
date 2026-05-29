#!/usr/bin/env python3
"""
🔔 VK TRIGGER — Авто-рассылка при публикации в ВК

Слушает ВК (wall.get) каждые 60 сек → при новом посте:
  - TG канал (@svoye_podvorye)
  - MAX канал (бизнес-рассылка)
  - Личное Игорю (для копирования в ОК)

Использование:
    python3 vk_trigger.py start    — запуск polling
    python3 vk_trigger.py status   — статус кэша
    python3 vk_trigger.py test     — тестовый пост
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "ai-eggs", "agent"))

# ─── Конфигурация ─────────────────────────────────────────────────────────────

VK_GROUP_ID = os.getenv("VK_PODVORYE_GROUP_ID", "-238230663").lstrip("-")
VK_TOKEN = os.getenv("VK_PODVORYE_TOKEN", "")

TG_BOT_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN", "")
TG_CHANNEL = "@svoye_podvorye"
TG_IGOR_ID = "176203333"  # Игорь лично

MAX_API_URL = os.getenv("MAX_API_URL", "")  # MAX API endpoint
MAX_CHANNEL_ID = os.getenv("MAX_CHANNEL_ID", "")

CACHE_FILE = os.path.join(BASE_DIR, "data", "vk_trigger_cache.json")
POLL_INTERVAL = 60  # сек

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

# Обновляем конфиг из .env
VK_TOKEN = ENV.get("VK_PODVORYE_TOKEN", VK_TOKEN)
TG_BOT_TOKEN = ENV.get("ANGELOCHKA_BOT_TOKEN", TG_BOT_TOKEN)
MAX_API_URL = ENV.get("MAX_API_URL", MAX_API_URL)
MAX_CHANNEL_ID = ENV.get("MAX_CHANNEL_ID", MAX_CHANNEL_ID)

# ─── Кэш ──────────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    """Загружает кэш: last_post_id, last_check"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_post_id": 0, "last_check": None}


def save_cache(cache: dict):
    """Сохраняет кэш"""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ─── VK API ───────────────────────────────────────────────────────────────────

def vk_call(method: str, params: dict) -> dict:
    """Вызов VK API через curl"""
    import subprocess
    
    params["access_token"] = VK_TOKEN
    params["v"] = "5.199"
    
    url = f"https://api.vk.com/method/{method}"
    cmd = ["curl", "-s", "--max-time", "15", url]
    for k, v in params.items():
        cmd += ["-d", f"{k}={urllib.parse.quote(str(v))}"]
    
    result = subprocess.run(cmd, capture_output=True, timeout=20)
    return json.loads(result.stdout)


def get_new_posts() -> list:
    """Получает новые посты из ВК"""
    cache = load_cache()
    last_id = cache.get("last_post_id", 0)
    
    # Получаем последние 5 постов
    result = vk_call("wall.get", {
        "owner_id": f"-{VK_GROUP_ID}",
        "count": 5,
        "extended": 0
    })
    
    if "error" in result:
        print(f"❌ VK API ошибка: {result['error']['error_msg']}")
        return []
    
    posts = result.get("response", {}).get("items", [])
    
    # Фильтруем только новые
    new_posts = [p for p in posts if p["id"] > last_id]
    
    # Возвращаем в правильном порядке (старые → новые)
    return list(reversed(new_posts))

# ─── TG API ───────────────────────────────────────────────────────────────────

def send_to_tg_channel(text: str, photo_url: str) -> bool:
    """Отправляет в TG канал"""
    if not TG_BOT_TOKEN:
        print("   ❌ TG_BOT_TOKEN не найден")
        return False
    
    base_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
    
    # Скачиваем фото и отправляем
    try:
        # Отправляем фото с подписью
        cmd = [
            "curl", "-s", "--max-time", "30",
            "-F", f"chat_id={TG_CHANNEL}",
            "-F", f"caption={text[:1024]}",
            "-F", "parse_mode=HTML",
            "-F", f"photo={photo_url}",
            f"{base_url}/sendPhoto",
        ]
        
        import subprocess
        result = subprocess.run(cmd, capture_output=True, timeout=35)
        resp = json.loads(result.stdout)
        
        if resp.get("ok"):
            print("   ✅ TG канал: отправлено")
            return True
        else:
            print(f"   ❌ TG ошибка: {resp.get('description', 'unknown')}")
            return False
            
    except Exception as e:
        print(f"   ❌ TG ошибка: {e}")
        return False


def send_to_igor(text: str, photo_url: str, post_id: int) -> bool:
    """Отправляет Игорю личное сообщение (для копирования в ОК)"""
    if not TG_BOT_TOKEN:
        return False
    
    base_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
    
    # Формируем сообщение для ОК
    ok_message = (
        f"📋 <b>СКОПИРОВАТЬ В ОК</b>\n\n"
        f"📝 Текст:\n{text[:800]}\n\n"
        f"📸 Фото: {photo_url}\n\n"
        f"──────────────────────────────\n"
        f"👆 Копируй текст + скачай фото → ОК\n\n"
        f"🔗 Пост ВК: https://vk.com/wall-{VK_GROUP_ID}_{post_id}"
    )
    
    try:
        cmd = [
            "curl", "-s", "--max-time", "15",
            "-F", f"chat_id={TG_IGOR_ID}",
            "-F", f"text={ok_message}",
            "-F", "parse_mode=HTML",
            f"{base_url}/sendMessage",
        ]
        
        import subprocess
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        resp = json.loads(result.stdout)
        
        if resp.get("ok"):
            print("   ✅ Игорь (ОК): отправлено")
            return True
        else:
            print(f"   ❌TG ошибка: {resp.get('description', 'unknown')}")
            return False
            
    except Exception as e:
        print(f"   ❌ TG ошибка: {e}")
        return False

# ─── MAX API ──────────────────────────────────────────────────────────────────

def send_to_max(text: str, photo_url: str) -> bool:
    """Отправляет в MAX мессенджер"""
    if not MAX_API_URL:
        print("   ⚠️ MAX_API_URL не настроен — пропускаем")
        return False
    
    # MAX API (предположительно совместим с TG или имеет свой REST API)
    # TODO: уточнить формат MAX API
    
    payload = {
        "channel_id": MAX_CHANNEL_ID,
        "text": text,
        "photo_url": photo_url
    }
    
    try:
        import json
        import urllib.request
        
        req = urllib.request.Request(
            MAX_API_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if result.get("status") == "ok":
                print("   ✅ MAX: отправлено")
                return True
            else:
                print(f"   ❌ MAX ошибка: {result}")
                return False
                
    except Exception as e:
        print(f"   ❌ MAX ошибка: {e}")
        return False

# ─── Основной цикл ────────────────────────────────────────────────────────────

def poll_vk():
    """Основной polling цикл"""
    print("🔔 VK TRIGGER запущен")
    print(f"   ВК: -{VK_GROUP_ID}")
    print(f"   TG: {TG_CHANNEL}")
    print(f"   MAX: {MAX_API_URL or 'не настроен'}")
    print(f"   Игорь: {TG_IGOR_ID}")
    print(f"   Интервал: {POLL_INTERVAL} сек")
    print("\n🔍 Проверка кэша...")
    
    cache = load_cache()
    last_id = cache.get("last_post_id", 0)
    print(f"   Последний пост: {last_id}")
    
    print("\n📡 Начинаю polling ВК...\n")
    
    while True:
        try:
            # Получаем новые посты
            new_posts = get_new_posts()
            
            if new_posts:
                print(f"\n📬 Найдено {len(new_posts)} новых постов!")
                
                for post in new_posts:
                    post_id = post["id"]
                    text = post.get("text", "")
                    
                    # Извлекаем фото
                    photo_url = None
                    attachments = post.get("attachments", [])
                    for att in attachments:
                        if att["type"] == "photo":
                            sizes = att["photo"].get("sizes", [])
                            if sizes:
                                photo_url = sizes[-1]["url"]  # Наибольшее
                            break
                    
                    if not text:
                        print("   ⏭️ Пропущено (нет текста)")
                        continue
                    
                    print(f"\n📝 Пост #{post_id}:")
                    print(f"   Текст: {text[:60]}...")
                    print(f"   Фото: {photo_url or 'нет'}")
                    
                    # Рассылаем
                    if photo_url:
                        send_to_tg_channel(text, photo_url)
                        send_to_max(text, photo_url)
                    send_to_igor(text, photo_url, post_id)
                    
                    # Обновляем кэш
                    cache["last_post_id"] = post_id
                    cache["last_check"] = datetime.now().isoformat()
                    save_cache(cache)
                
                print(f"\n✅ Обработано {len(new_posts)} постов")
            else:
                print(".", end="", flush=True)
            
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n\n🛑 Остановлено пользователем")
            break
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            time.sleep(POLL_INTERVAL)

# ─── CLI ──────────────────────────────────────────────────────────────────────

def show_status():
    """Показывает статус кэша"""
    cache = load_cache()
    print("📊 VK TRIGGER статус")
    print(f"   Кэш: {CACHE_FILE}")
    print(f"   Последний пост: {cache.get('last_post_id', 0)}")
    print(f"   Последняя проверка: {cache.get('last_check', 'никогда')}")

def test_post():
    """Тестовый пост"""
    text = "🔔 ТЕСТ VK TRIGGER\n\nЕсли вы это читаете — всё работает!"
    photo_url = "https://images.unsplash.com/photo-1548550023-2bdb3c5beed7?w=800"
    
    print("🧪 Тест рассылки...")
    send_to_tg_channel(text, photo_url)
    send_to_max(text, photo_url)
    send_to_igor(text, photo_url, 0)
    print("\n✅ Тест завершён")

def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python3 vk_trigger.py start   — запуск polling")
        print("  python3 vk_trigger.py status  — статус")
        print("  python3 vk_trigger.py test    — тест")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "start":
        poll_vk()
    elif command == "status":
        show_status()
    elif command == "test":
        test_post()
    else:
        print(f"❌ Неизвестная команда: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
