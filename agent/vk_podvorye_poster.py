#!/usr/bin/env python3
"""
VK Autoposter для группы «Своё Подворье» (Канал Б)
Публикует посты из очереди, поддерживает опросы и отложенный постинг.
Использует библиотеку vk_api (pip install vk_api).

Использование:
    python vk_podvorye_poster.py post <номер_поста>   — публикует конкретный пост
    python vk_podvorye_poster.py post_all              — публикует все неопубликованные
    python vk_podvorye_poster.py schedule              — отложенный постинг (по контент-плану)
    python vk_podvorye_poster.py status                — показывает статус постов
    python vk_podvorye_poster.py check_token           — проверка валидности токена
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
VK_TOKEN = ENV.get("VK_PODVORYE_TOKEN", "")
VK_GROUP_ID = ENV.get("VK_PODVORYE_GROUP_ID", "").lstrip("-")

CONTENT_DIR = os.path.join(BASE_DIR, "vk_content", "podvorye")
POSTED_LOG = os.path.join(CONTENT_DIR, "posted_log.json")


def get_poster():
    """Создание VKPoster для Подворья."""
    return VKPoster(token=VK_TOKEN, group_id=VK_GROUP_ID, env=ENV)


def get_photo_keywords(post):
    """Извлекает ключевые слова для поиска фото из метаданных поста."""
    # Мета-тег имеет приоритет
    if "photo_query" in post["meta"]:
        return post["meta"]["photo_query"]
    # Из текста поста
    for line in post["text"].split("\n"):
        if line.startswith("# ФОТО-ЗАПРОС:"):
            return line.replace("# ФОТО-ЗАПРОС:", "").strip()
    # Иначе рубрика + тема
    rubric = post["meta"].get("rubric", "")
    title = post["meta"].get("title", "")
    keywords = f"{rubric} {title}".strip()
    return keywords if keywords else "птицеводство подворье"


def publish_post(poster, post, publish_date=None, with_photo=True):
    """Публикация поста в VK."""
    if post["is_poll"]:
        return publish_poll_post(poster, post, publish_date)

    attachment = None

    # Ищем фото через каскад
    if with_photo:
        keywords = get_photo_keywords(post)
        attachment = poster.upload_photo_from_url(keywords, group_name="podvorye")

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


def publish_poll_post(poster, post, publish_date=None):
    """Публикация поста с опросом."""
    poll_options = post.get("poll_options", [])
    poll_text = post.get("poll_text", post["text"])

    if not poll_options:
        print(f"⚠️ Пост #{post['index']} — опрос без вариантов, публикую как обычный пост")
        post["is_poll"] = False
        return publish_post(poster, post, publish_date)

    # Убираем секцию опроса из текста
    clean_text = re.sub(r'\[ОПРОС.*?\n\n', '', poll_text, flags=re.DOTALL)
    clean_text = re.sub(r'Варианты:.*?(?=\n\n|$)', '', clean_text, flags=re.DOTALL)
    emoji_starters = ["🐔", "🐣", "🦆", "🦃", "🐇", "🐐", "🐝", "🌱", "🏙"]
    clean_lines = [l for l in clean_text.split("\n")
                   if not any(l.strip().startswith(e) for e in emoji_starters)]
    message = "\n".join(clean_lines).strip() or post["text"]

    # Создаём опрос через vk_api
    poll_attachment = poster.create_poll(
        question="Кто живёт на вашем подворье?",
        answers=poll_options,
        is_multiple=True,
    )

    if not poll_attachment:
        print("⚠️ Не удалось создать опрос, публикую как текстовый пост")
        post["is_poll"] = False
        return publish_post(poster, post, publish_date)

    post_id = poster.post(
        message=message,
        attachments=poll_attachment,
        publish_date=publish_date,
    )

    if post_id:
        print(f"✅ Пост-опрос #{post['index']} опубликован! post_id={post_id}")
    else:
        print(f"❌ Ошибка при публикации опроса #{post['index']}")
    return post_id


# ═══════════════════════════════════════════════
# CLI-команды
# ═══════════════════════════════════════════════

def cmd_check_token():
    """Проверка валидности токена."""
    poster = get_poster()
    info = poster.check_token()

    print(f"\n{'='*60}")
    print("  🔑 ПРОВЕРКА ТОКЕНА — «Своё Подворье»")
    print(f"{'='*60}\n")
    print(f"  Group ID: {VK_GROUP_ID}")
    print(f"  Token: {VK_TOKEN[:20]}...")

    if info["ok"]:
        print(f"  ✅ Группа: {info['name']}")
        print(f"  👥 Подписчиков: {info['members']}")
        wall = poster.get_wall_count()
        print(f"  📋 Постов на стене: {wall}")
    else:
        print(f"  ❌ Ошибка: {info['error']}")
    print(f"\n{'='*60}\n")


def cmd_post(post_number):
    """Публикация конкретного поста по номеру."""
    poster = get_poster()
    posts = parse_posts_from_file(os.path.join(CONTENT_DIR, "week1_posts.md"))
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
    posts = parse_posts_from_file(os.path.join(CONTENT_DIR, "week1_posts.md"))
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
    """Отложенный постинг — по одному посту в день с 10:00 MSK."""
    poster = get_poster()
    posts = parse_posts_from_file(os.path.join(CONTENT_DIR, "week1_posts.md"))
    log = load_posted_log(POSTED_LOG)

    unpublished = [p for p in posts if str(p["index"]) not in log]
    if not unpublished:
        print("✅ Все посты уже опубликованы!")
        return

    now = datetime.now()
    start = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if start <= now:
        start += timedelta(days=1)

    print(f"📅 Планирую {len(unpublished)} постов начиная с {start.strftime('%d.%m.%Y %H:%M')}")

    for i, post in enumerate(unpublished):
        publish_date = start + timedelta(days=i)
        print(f"\n--- Планирую пост #{post['index']} на {publish_date.strftime('%d.%m %H:%M')} ---")
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
    posts = parse_posts_from_file(os.path.join(CONTENT_DIR, "week1_posts.md"))
    log = load_posted_log(POSTED_LOG)

    print(f"\n{'='*60}")
    print("  📊 СТАТУС ПОСТОВ «Своё Подворье» (Канал Б)")
    print(f"  Группа: vk.com/club{VK_GROUP_ID}")
    print(f"{'='*60}\n")

    for post in posts:
        idx = str(post["index"])
        status = "✅" if idx in log else "⏳"
        title = post["meta"].get("title", f"Пост {idx}")
        rubric = post["meta"].get("rubric", "")

        if idx in log:
            info = log[idx]
            scheduled = " (📅 отложенный)" if info.get("scheduled") else ""
            print(f"  {status} #{idx} | {title} | post_id={info['post_id']}{scheduled}")
        else:
            print(f"  {status} #{idx} | {title} | {rubric}")

    published = sum(1 for p in posts if str(p["index"]) in log)
    print(f"\n  Итого: {published}/{len(posts)} опубликовано\n")


def main():
    if not VK_TOKEN:
        print("❌ VK_PODVORYE_TOKEN не найден в .env!")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]

    if command == "check_token":
        cmd_check_token()
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
