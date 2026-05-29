#!/usr/bin/env python3
"""
VK Autoposter для группы «ВезёмЦыплят» (Канал А)
Публикует посты из очереди, поддерживает загрузку фото и отложенный постинг.
Использует библиотеку vk_api (pip install vk_api).

Использование:
    python vk_vezemcyp_poster.py test_post              — тестовый пост (без фото)
    python vk_vezemcyp_poster.py test_post_photo <путь>  — тестовый пост + фото
    python vk_vezemcyp_poster.py post <номер_поста>      — публикует конкретный пост
    python vk_vezemcyp_poster.py post_all                — публикует все неопубликованные
    python vk_vezemcyp_poster.py schedule                — отложенный постинг (по контент-плану)
    python vk_vezemcyp_poster.py status                  — показывает статус постов
    python vk_vezemcyp_poster.py check_token             — проверка валидности токена
"""

import os
import re
import sys
import time
from datetime import datetime, timedelta

# Базовый модуль VK
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vk_poster_base import (
    BASE_DIR,
    VKPoster,
    load_env,
    load_posted_log,
    parse_posts_from_file,
    save_posted_log,
)

# --- Конфигурация ---
ENV = load_env()

# ВезёмЦыплят — Community Token с правами wall,photos
VK_TOKEN = ENV.get("VK_VEZEMCYP_TOKEN", ENV.get("VK_SERVICE_TOKEN", ""))
VK_GROUP_ID = ENV.get("VK_VEZEMCYP_GROUP_ID", ENV.get("VK_GROUP_ID", "")).lstrip("-")

CONTENT_DIR = os.path.join(BASE_DIR, "vk_content", "vezemcyp")
ASSETS_DIR = os.path.join(CONTENT_DIR, "assets")
POSTED_LOG = os.path.join(CONTENT_DIR, "posted_log.json")

os.makedirs(ASSETS_DIR, exist_ok=True)


def get_poster():
    """Создание VKPoster для ВезёмЦыплят."""
    return VKPoster(token=VK_TOKEN, group_id=VK_GROUP_ID, env=ENV)


def find_post_photo(post):
    """Поиск локального фото для поста в assets/."""
    title = post["meta"].get("title", "")
    post_id_match = re.search(r'[A-Z]\.(\d+)', title)
    if post_id_match:
        post_num = post_id_match.group(1)
        for ext in ["jpg", "jpeg", "png", "webp"]:
            candidate = os.path.join(ASSETS_DIR, f"post_{post_num}.{ext}")
            if os.path.exists(candidate):
                return candidate
    return None


def publish_post(poster, post, publish_date=None):
    """Публикация поста в VK."""
    attachment = None

    # Сначала проверяем локальное фото
    photo_path = find_post_photo(post)
    if photo_path:
        attachment = poster.upload_photo(photo_path)

    post_id = poster.post(
        message=post["text"],
        attachments=attachment,
        publish_date=publish_date,
    )

    if post_id:
        print(f"✅ Пост #{post['index']} опубликован! post_id={post_id}")
    else:
        print(f"❌ Ошибка при публикации поста #{post['index']}")
    return post_id


# ═══════════════════════════════════════════════
# CLI-команды
# ═══════════════════════════════════════════════

def cmd_check_token():
    """Проверка валидности токена и доступа к группе."""
    poster = get_poster()
    info = poster.check_token()

    print(f"\n{'='*60}")
    print("  🔑 ПРОВЕРКА ТОКЕНА VK — «ВезёмЦыплят»")
    print(f"{'='*60}\n")
    print(f"  Group ID: {VK_GROUP_ID}")
    print(f"  Token: {VK_TOKEN[:20]}...")
    print(f"  Тип: {'VK_VEZEMCYP_TOKEN' if ENV.get('VK_VEZEMCYP_TOKEN') else 'VK_SERVICE_TOKEN (⚠️ не подходит для постинга!)'}")
    print()

    if info["ok"]:
        print(f"  ✅ Группа: {info['name']}")
        print(f"  👥 Подписчиков: {info['members']}")
        wall = poster.get_wall_count()
        print(f"  📋 Постов на стене: {wall}")
        print(f"  🔗 https://vk.com/club{VK_GROUP_ID}")
    else:
        print(f"  ❌ Ошибка: {info['error']}")
    print(f"\n{'='*60}\n")


def cmd_test_post():
    """Тестовый пост без фото."""
    test_file = os.path.join(CONTENT_DIR, "test_post.md")
    if not os.path.exists(test_file):
        print(f"❌ Файл не найден: {test_file}")
        return

    with open(test_file, "r", encoding="utf-8") as f:
        content = f.read()

    lines = [l for l in content.split("\n")
             if not (l.startswith("# ") and any(k in l for k in ["Тип:", "Платформа:", "ТЕСТОВЫЙ"]))]
    text = "\n".join(lines).strip()

    poster = get_poster()
    post = {"index": 0, "meta": {"title": "Тестовый пост"}, "text": text, "is_poll": False}

    print("\n--- Тестовый пост (без фото) ---")
    print(f"Текст ({len(text)} символов):\n{text[:200]}...")
    print()

    post_id = poster.post(message=text)
    if post_id:
        print(f"✅ Тестовый пост опубликован! post_id={post_id}")
        log = load_posted_log(POSTED_LOG)
        log["test"] = {"post_id": post_id, "published_at": datetime.now().isoformat(), "title": "Тестовый пост"}
        save_posted_log(POSTED_LOG, log)


def cmd_test_post_photo(photo_path):
    """Тестовый пост с фото."""
    test_file = os.path.join(CONTENT_DIR, "test_post.md")
    if not os.path.exists(test_file):
        print(f"❌ Файл не найден: {test_file}")
        return
    if not os.path.exists(photo_path):
        print(f"❌ Фото не найдено: {photo_path}")
        return

    with open(test_file, "r", encoding="utf-8") as f:
        content = f.read()

    lines = [l for l in content.split("\n")
             if not (l.startswith("# ") and any(k in l for k in ["Тип:", "Платформа:", "ТЕСТОВЫЙ"]))]
    text = "\n".join(lines).strip()

    poster = get_poster()
    attachment = poster.upload_photo(photo_path)

    print(f"\n--- Тестовый пост (с фото: {os.path.basename(photo_path)}) ---")
    post_id = poster.post(message=text, attachments=attachment)
    if post_id:
        print(f"✅ Тестовый пост + фото опубликован! post_id={post_id}")
        log = load_posted_log(POSTED_LOG)
        log["test_photo"] = {"post_id": post_id, "published_at": datetime.now().isoformat(),
                             "title": "Тестовый пост + фото", "photo": photo_path}
        save_posted_log(POSTED_LOG, log)


def cmd_post(post_number):
    """Публикация конкретного поста по номеру."""
    poster = get_poster()
    posts = parse_posts_from_file(os.path.join(CONTENT_DIR, "starter_posts.md"))
    log = load_posted_log(POSTED_LOG)

    target = next((p for p in posts if p["index"] == post_number), None)
    if not target:
        print(f"❌ Пост #{post_number} не найден (всего постов: {len(posts)})")
        return

    if str(post_number) in log:
        print(f"⚠️ Пост #{post_number} уже опубликован (post_id={log[str(post_number)]['post_id']})")
        resp = input("Опубликовать повторно? (y/n): ")
        if resp.lower() != "y":
            return

    post_id = publish_post(poster, target)
    if post_id:
        log[str(post_number)] = {
            "post_id": post_id,
            "published_at": datetime.now().isoformat(),
            "title": target["meta"].get("title", ""),
        }
        save_posted_log(POSTED_LOG, log)


def cmd_post_all():
    """Публикация всех неопубликованных постов (с паузой 30 сек)."""
    poster = get_poster()
    posts = parse_posts_from_file(os.path.join(CONTENT_DIR, "starter_posts.md"))
    log = load_posted_log(POSTED_LOG)

    unpublished = [p for p in posts if str(p["index"]) not in log]
    if not unpublished:
        print("✅ Все посты уже опубликованы!")
        return

    print(f"📋 Найдено {len(unpublished)} неопубликованных постов из {len(posts)}")

    for i, post in enumerate(unpublished):
        print(f"\n--- Публикую пост #{post['index']}: {post['meta'].get('title', '')} ---")
        post_id = publish_post(poster, post)

        if post_id:
            log[str(post["index"])] = {
                "post_id": post_id,
                "published_at": datetime.now().isoformat(),
                "title": post["meta"].get("title", ""),
            }
            save_posted_log(POSTED_LOG, log)

        if i < len(unpublished) - 1:
            print("⏳ Пауза 30 сек (лимит VK API)...")
            time.sleep(30)

    print(f"\n🏁 Готово! Опубликовано постов: {len(unpublished)}")


def cmd_schedule():
    """Отложенный постинг — по одному посту каждые 45 минут (для наполнения)."""
    poster = get_poster()
    posts = parse_posts_from_file(os.path.join(CONTENT_DIR, "starter_posts.md"))
    log = load_posted_log(POSTED_LOG)

    unpublished = [p for p in posts if str(p["index"]) not in log]
    if not unpublished:
        print("✅ Все посты уже опубликованы!")
        return

    now = datetime.now()
    start = now + timedelta(hours=1)

    print(f"📅 Планирую {len(unpublished)} постов начиная с {start.strftime('%d.%m.%Y %H:%M')}")
    print("   Интервал: 45 минут между постами")

    for i, post in enumerate(unpublished):
        publish_date = start + timedelta(minutes=45 * i)
        print(f"\n--- Планирую пост #{post['index']} на {publish_date.strftime('%d.%m %H:%M')} ---")
        print(f"    {post['meta'].get('title', 'без названия')}")

        post_id = publish_post(poster, post, publish_date=publish_date)

        if post_id:
            log[str(post["index"])] = {
                "post_id": post_id,
                "published_at": publish_date.isoformat(),
                "scheduled": True,
                "title": post["meta"].get("title", ""),
            }
            save_posted_log(POSTED_LOG, log)

        time.sleep(2)

    print(f"\n🏁 Запланировано {len(unpublished)} постов!")


def cmd_status():
    """Показывает статус публикации."""
    posts = parse_posts_from_file(os.path.join(CONTENT_DIR, "starter_posts.md"))
    log = load_posted_log(POSTED_LOG)

    print(f"\n{'='*60}")
    print("  📊 СТАТУС ПОСТОВ «ВезёмЦыплят» (Канал А)")
    print(f"  Группа: vk.com/club{VK_GROUP_ID}")
    print(f"{'='*60}\n")

    for post in posts:
        idx = str(post["index"])
        status = "✅" if idx in log else "⏳"
        title = post["meta"].get("title", f"Пост {idx}")
        photo = " 📸" if find_post_photo(post) else ""

        if idx in log:
            info = log[idx]
            scheduled = " (📅 отложенный)" if info.get("scheduled") else ""
            print(f"  {status} #{idx} | {title}{photo} | post_id={info['post_id']}{scheduled}")
        else:
            print(f"  {status} #{idx} | {title}{photo}")

    published = sum(1 for p in posts if str(p["index"]) in log)
    print(f"\n  Итого: {published}/{len(posts)} опубликовано")

    if "test" in log:
        print(f"  🧪 Тестовый пост: post_id={log['test']['post_id']}")
    if "test_photo" in log:
        print(f"  🧪 Тестовый пост + фото: post_id={log['test_photo']['post_id']}")
    print()


def main():
    if not VK_TOKEN:
        print("❌ VK_VEZEMCYP_TOKEN (или VK_SERVICE_TOKEN) не найден в .env!")
        print("   Добавьте Community Token группы в .env:")
        print("   VK_VEZEMCYP_TOKEN=vk1.a.xxxxxx...")
        sys.exit(1)

    if not VK_GROUP_ID:
        print("❌ VK_GROUP_ID не найден в .env!")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]

    if command == "check_token":
        cmd_check_token()
    elif command == "test_post":
        cmd_test_post()
    elif command == "test_post_photo" and len(sys.argv) > 2:
        cmd_test_post_photo(sys.argv[2])
    elif command == "post" and len(sys.argv) > 2:
        cmd_post(int(sys.argv[2]))
    elif command == "post_all":
        cmd_post_all()
    elif command == "schedule":
        cmd_schedule()
    elif command == "status":
        cmd_status()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
