#!/usr/bin/env python3
"""
📅 Batch Scheduler для «Своё Подворье»
Планирует посты из НЕСКОЛЬКИХ md-файлов последовательно.

Использование:
    python schedule_podvorye_batch.py --dry-run          # только показать план
    python schedule_podvorye_batch.py --go               # реально запланировать в VK
    python schedule_podvorye_batch.py --file week2_posts.md --start 2026-05-12 --go
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

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
    return VKPoster(token=VK_TOKEN, group_id=VK_GROUP_ID, env=ENV)


def get_photo_keywords(post):
    """Извлекает ключевые слова для поиска фото."""
    if "photo_query" in post["meta"]:
        return post["meta"]["photo_query"]
    rubric = post["meta"].get("rubric", "")
    title = post["meta"].get("title", "")
    keywords = f"{rubric} {title}".strip()
    return keywords if keywords else "птицеводство подворье"


def schedule_file(poster, filepath, start_date, dry_run=True, start_index=None):
    """
    Планирует посты из одного файла, начиная с start_date.
    Возвращает количество запланированных постов.
    """
    posts = parse_posts_from_file(filepath)
    if not posts:
        print(f"⚠️ Нет постов в {os.path.basename(filepath)}")
        return 0

    log = load_posted_log(POSTED_LOG)
    scheduled_count = 0

    print(f"\n{'='*60}")
    print(f"  📄 {os.path.basename(filepath)} — {len(posts)} постов")
    print(f"  📅 Начало: {start_date.strftime('%d.%m.%Y')} в 10:00")
    print(f"{'='*60}")

    for i, post in enumerate(posts):
        publish_date = start_date.replace(hour=10, minute=0, second=0) + timedelta(days=i)
        post_idx = start_index + i if start_index else post["index"]
        title = post["meta"].get("title", f"Пост {post_idx}")

        # Проверяем, не запланирован ли уже
        if str(post_idx) in log:
            existing = log[str(post_idx)]
            print(f"  ⏭ #{post_idx} | {title} — уже есть (post_id={existing['post_id']})")
            continue

        weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][publish_date.weekday()]
        print(f"  {'🔵' if dry_run else '🟢'} #{post_idx} | {weekday} {publish_date.strftime('%d.%m')} 10:00 | {title}")

        if not dry_run:
            # Ищем фото
            keywords = get_photo_keywords(post)
            attachment = poster.upload_photo_from_url(keywords, group_name="podvorye")

            # Публикуем с отложенной датой
            if post["is_poll"]:
                # Для опросов — создаём poll
                poll_options = post.get("poll_options", [])
                if poll_options:
                    poll_attachment = poster.create_poll(
                        question=title,
                        answers=poll_options,
                        is_multiple=True,
                    )
                    attachment = poll_attachment if poll_attachment else attachment

            post_id = poster.post(
                message=post["text"],
                attachments=attachment,
                publish_date=publish_date,
            )

            if post_id:
                log[str(post_idx)] = {
                    "post_id": post_id,
                    "published_at": publish_date.isoformat(),
                    "scheduled": True,
                    "title": title,
                }
                save_posted_log(POSTED_LOG, log)
                print(f"    ✅ post_id={post_id}")
                scheduled_count += 1
            else:
                print("    ❌ Ошибка публикации")

            import time
            time.sleep(3)  # пауза между вызовами API
        else:
            scheduled_count += 1

    return scheduled_count


def main():
    parser = argparse.ArgumentParser(description="Batch Scheduler для Подворья")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Показать план без публикации (по умолчанию)")
    parser.add_argument("--go", action="store_true",
                        help="Реально запланировать в VK")
    parser.add_argument("--file", type=str, default=None,
                        help="Конкретный файл (по умолчанию: все непубликованные)")
    parser.add_argument("--start", type=str, default=None,
                        help="Дата начала YYYY-MM-DD (по умолчанию: следующий день)")
    parser.add_argument("--start-index", type=int, default=None,
                        help="Стартовый индекс поста (для нумерации в логе)")
    args = parser.parse_args()

    if not VK_TOKEN:
        print("❌ VK_PODVORYE_TOKEN не найден в .env!")
        sys.exit(1)

    dry_run = not args.go

    if dry_run:
        print("\n🔵 РЕЖИМ: DRY-RUN (только показать план)")
        print("   Для реальной публикации добавь: --go\n")
        poster = None
    else:
        print("\n🟢 РЕЖИМ: БОЕВОЙ — публикуем в VK!\n")
        poster = get_poster()

    # Определяем файлы
    if args.file:
        files = [(os.path.join(CONTENT_DIR, args.file), args.start, args.start_index)]
    else:
        # Автоматический каскад: week2 → week3 → week4
        files = [
            ("week2_posts.md", "2026-05-12", 8),
            ("week3_posts.md", "2026-05-19", 13),
            ("week4_posts.md", "2026-05-26", 20),
        ]
        files = [
            (os.path.join(CONTENT_DIR, f), d, idx)
            for f, d, idx in files
            if os.path.exists(os.path.join(CONTENT_DIR, f))
        ]

    if not files:
        print("❌ Нет файлов для планирования")
        sys.exit(1)

    total = 0
    for filepath_or_tuple in files:
        if isinstance(filepath_or_tuple, tuple):
            filepath, start_str, start_idx = filepath_or_tuple
        else:
            filepath = filepath_or_tuple
            start_str = args.start
            start_idx = args.start_index

        if start_str:
            start_date = datetime.strptime(start_str, "%Y-%m-%d")
        else:
            start_date = datetime.now().replace(hour=10, minute=0, second=0) + timedelta(days=1)

        count = schedule_file(poster, filepath, start_date, dry_run=dry_run, start_index=start_idx)
        total += count

    print(f"\n{'='*60}")
    print(f"  🏁 Итого: {total} постов {'запланировано' if not dry_run else '(dry-run)'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
