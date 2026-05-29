#!/usr/bin/env python3
"""
📋 OK Content Generator — подготовка постов для ручной публикации в Одноклассники.

Логика:
  1. Берёт неопубликованный пост из vk_content/podvorye/
  2. Адаптирует текст под аудиторию ОК (более тёплый, простой стиль)
  3. Генерирует фото через Imagen 4.0 + US SOCKS5 прокси
  4. Сохраняет в ok/ГГГГ-ММ-ДД/post.txt + photo.png
  5. Помечает пост как "готов к публикации" в ok_queue.json

Результат: папка ok/ с готовым контентом — бери и публикуй!

Использование:
  python3 ok_content_gen.py               # подготовить 1 пост на сегодня
  python3 ok_content_gen.py --count 3     # подготовить 3 поста
  python3 ok_content_gen.py --list        # показать что уже готово
  python3 ok_content_gen.py --pending     # показать что ещё в очереди
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(BASE_DIR, "agent")
sys.path.insert(0, AGENT_DIR)

from vk_smart_poster import _make_imagen_prompt, generate_imagen_photo, parse_all_posts

# ═══════════════════════════════════════════════
# Конфигурация
# ═══════════════════════════════════════════════

ROOT_DIR = os.path.dirname(BASE_DIR)                          # freelance-2026/
OK_DIR = os.path.join(ROOT_DIR, "ok")                         # freelance-2026/ok/

# Mapping of groups to their VK content directories
GROUPS = {
    "podvorye": {
        "content_dir": os.path.join(BASE_DIR, "vk_content", "podvorye"),
        "name": "Своё Подворье",
    },
    "vezemcyp": {
        "content_dir": os.path.join(BASE_DIR, "vk_content", "vezemcyp"),
        "name": "ВезёмЦыплят",
    },
}

# Default group (can be overridden via CLI)
DEFAULT_GROUP = "podvorye"

QUEUE_LOG = os.path.join(OK_DIR, "ok_queue.json")             # очередь постов

DEFAULT_PHOTO_PROMPT = (
    "Charming Russian rural farmstead with wooden house, vegetable garden, "
    "free-range chickens on green grass, warm golden hour light. "
    "No text, no words, no letters, no watermarks. 4:3 ratio."
)


# ═══════════════════════════════════════════════
# Адаптация текста под OK
# ═══════════════════════════════════════════════

def adapt_text_for_ok(vk_text: str) -> str:
    """
    Адаптирует текст под аудиторию ОК:
    - Убирает markdown-разметку ВК (**bold**, [ссылки|id])
    - Добавляет emoji если их мало
    - ОК-аудитория: 35-55 лет, тёплый разговорный стиль
    """
    import re

    text = vk_text

    # Убираем VK-ссылки вида [Своё Подворье|club238230663]
    text = re.sub(r'\[([^\|]+)\|[^\]]+\]', r'\1', text)

    # Убираем markdown bold (**текст**)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)

    # Убираем одиночные звёздочки
    text = re.sub(r'\*([^*]+)\*', r'\1', text)

    # Убираем лишние пробелы
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


# ═══════════════════════════════════════════════
# Queue management (per group)
# ═══════════════════════════════════════════════

def load_queue(group: str) -> dict:
    queue_path = os.path.join(OK_DIR, group, "ok_queue.json")
    if os.path.exists(queue_path):
        with open(queue_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"generated": [], "posted": [], "_keys_generated": [], "_keys_posted": []}

def save_queue(data: dict, group: str) -> None:
    group_dir = os.path.join(OK_DIR, group)
    os.makedirs(group_dir, exist_ok=True)
    queue_path = os.path.join(group_dir, "ok_queue.json")
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)




def get_pending_posts(group: str, count: int = 1) -> list:
    """Возвращает посты, которые ещё не подготовлены для OK в указанной группе."""
    content_dir = GROUPS.get(group, {}).get("content_dir")
    if not content_dir:
        return []
    all_posts = parse_all_posts(content_dir)
    queue = load_queue(group)
    generated_keys = set(queue.get("_keys_generated", []))
    pending = [p for p in all_posts if p.get("post_id_key", "") not in generated_keys]
    return pending[:count]


def load_env() -> dict:
    env = {}
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    for k, v in os.environ.items():
        if k not in env:
            env[k] = v
    return env


# ═══════════════════════════════════════════════
# README для папки OK
# ═══════════════════════════════════════════════

def write_ok_readme():
    readme_path = os.path.join(OK_DIR, "README.md")
    os.makedirs(OK_DIR, exist_ok=True)
    if os.path.exists(readme_path):
        return
    content = """# 📋 OK — Готовые посты для Одноклассников

Здесь хранятся подготовленные посты для группы «Своё Подворье» в ОК.

## Структура папок

```
ok/
├── README.md          ← этот файл
├── ok_queue.json      ← лог: что готово, что опубликовано
├── 2026-05-12/        ← дата подготовки
│   ├── post.txt       ← текст поста (адаптирован под ОК)
│   └── photo.png      ← фото (Imagen 4.0)
├── 2026-05-13/
│   ├── post.txt
│   └── photo.png
└── ...
```

## Как публиковать

1. Открой нужную папку по дате
2. Скопируй текст из `post.txt`
3. Открой группу «Своё Подворье» в ОК → Написать
4. Вставь текст, прикрепи `photo.png`
5. Нажми «Поделиться»

## После публикации

Отметь пост как опубликованный:
```bash
python3 ai-eggs/agent/ok_content_gen.py --mark 2026-05-12
```
"""
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)


# ═══════════════════════════════════════════════
# Генерация контента
# ═══════════════════════════════════════════════

def generate_post(post: dict, env: dict, group: str, date_str: str = None) -> dict | None:
    """Генерирует пост и фото, сохраняет в ok/<group>/<YYYY-MM-DD>/."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    post_dir = os.path.join(OK_DIR, group, date_str)
    post_txt_path = os.path.join(post_dir, "post.txt")
    photo_path = os.path.join(post_dir, "photo.png")

    # Если уже есть — пропускаем
    if os.path.exists(post_txt_path):
        # Следующий слот
        for i in range(1, 10):
            alt_dir = os.path.join(OK_DIR, f"{date_str}_{i:02d}")
            if not os.path.exists(os.path.join(alt_dir, "post.txt")):
                post_dir = alt_dir
                post_txt_path = os.path.join(post_dir, "post.txt")
                photo_path = os.path.join(post_dir, "photo.png")
                break

    os.makedirs(post_dir, exist_ok=True)

    # Адаптируем текст
    ok_text = adapt_text_for_ok(post["text"])

    # Сохраняем текст
    with open(post_txt_path, "w", encoding="utf-8") as f:
        f.write(ok_text)
        f.write("\n")

    print(f"  📝 Текст: {post_txt_path}")
    print(f"  👁  Превью: {ok_text[:80]}...")

    # Генерируем фото через Imagen 4
    prompt = _make_imagen_prompt(post["text"], post.get("meta", {}), DEFAULT_PHOTO_PROMPT)
    print(f"  🎨 Imagen 4: «{prompt[:65]}»...")

    photo_bytes = generate_imagen_photo(prompt, env)
    if photo_bytes:
        with open(photo_path, "wb") as f:
            f.write(photo_bytes)
        print(f"  📸 Фото: {photo_path} ({len(photo_bytes)//1024} KB)")
    else:
        print("  ⚠️  Фото не сгенерировано (нет Gemini ключа или прокси)")
        photo_path = None

    return {
        "post_key": post.get("post_id_key", ""),
        "date": date_str,
        "folder": post_dir,
        "post_txt": post_txt_path,
        "photo": photo_path,
        "source_file": post.get("source_file", "?"),
        "text_preview": ok_text[:100],
        "generated_at": datetime.now().isoformat(),
        "posted": False,
    }


# ═══════════════════════════════════════════════
# CLI команды
# ═══════════════════════════════════════════════

def cmd_list(group: str):
    """Показывает готовые посты для указанной группы."""
    queue = load_queue(group)
    generated = queue.get("generated", [])
    if not generated:
        print(f"📭 Нет подготовленных постов для группы {group}. Запустите: python3 ok_content_gen.py <group>")
        return

    print(f"\n{'═' * 55}")
    print(f"  📋 Готовые посты для группы {group} ({len(generated)} шт.)")
    print(f"{'═' * 55}")
    for item in generated:
        status = "✅ Опубликован" if item.get("posted") else "📌 Ждёт публикации"
        print(f"  [{item['date']}] {status}")
        print(f"    📁 {item['folder']}")
        print(f"    👁  {item['text_preview'][:60]}...")
        print()


def cmd_pending(group: str):
    """Показывает посты ВК, которые ещё не подготовлены для OK в указанной группе."""
    posts = get_pending_posts(group, count=50)
    print(f"\n{'═' * 55}")
    print(f"  📌 Ещё не подготовлены для группы {group}: {len(posts)} постов")
    print(f"{'═' * 55}")
    for i, p in enumerate(posts[:10], 1):
        print(f"  {i}. [{p.get('source_file', '?')}] {p['text'][:70]}...")
    if len(posts) > 10:
        print(f"  ... и ещё {len(posts)-10} постов")


def cmd_mark(group: str, date_str: str):
    """Помечает пост как опубликованный в конкретной группе."""
    queue = load_queue(group)
    found = False
    for item in queue.get("generated", []):
        if item.get("date", "").startswith(date_str):
            item["posted"] = True
            item["posted_at"] = datetime.now().isoformat()
            found = True
            print(f"✅ Помечен как опубликованный: {group} {date_str}")
    if found:
        save_queue(queue, group)
    else:
        print(f"❌ Пост за {date_str} в группе {group} не найден")


def cmd_generate(count: int, env: dict, group: str = DEFAULT_GROUP):
    """Генерирует `count` постов для указанной группы."""
    write_ok_readme()
    posts = get_pending_posts(group, count=count)

    if not posts:
        print(f"✅ Все посты уже подготовлены для группы {group}!")
        cmd_pending(group)
        return

    print(f"\n{'═' * 55}")
    print(f"  🚀 Готовим {len(posts)} пост(ов) для группы {group}")
    print(f"{'═' * 55}")

    queue = load_queue(group)
    generated_keys = set(queue.get("_keys_generated", []))
    today = datetime.now()

    for i, post in enumerate(posts):
        post_date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"\n  [{i+1}/{len(posts)}] Дата: {post_date}")
        result = generate_post(post, env, group, date_str=post_date)
        if result:
            queue.setdefault("generated", []).append(result)
            generated_keys.add(post.get("post_id_key", ""))
            queue["_keys_generated"] = list(generated_keys)
            save_queue(queue, group)
            print(f"  ✅ Готово → {result['folder']}")
        else:
            print("  ❌ Ошибка генерации")

    print(f"\n{'═' * 55}")
    print(f"  📁 Все файлы в: {os.path.join(OK_DIR, group)}")
    print(f"  📖 Инструкция: {os.path.join(OK_DIR, 'README.md')}")
    print(f"{'═' * 55}")


# ═══════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="OK Content Generator — готовит посты для ручной публикации")
    parser.add_argument("group", nargs="?", default="all", choices=list(GROUPS.keys()) + ["all"], help="Группа ВК, для которой готовятся посты (или 'all' для всех групп)")
    parser.add_argument("--count", "-n", type=int, default=1, help="Количество постов (по умолчанию 1)")
    parser.add_argument("--list", action="store_true", help="Показать готовые посты")
    parser.add_argument("--pending", action="store_true", help="Показать очередь")
    parser.add_argument("--mark", nargs=2, metavar=("ГРУППА", "ДАТА"), help="Отметить как опубликованный (group YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Сгенерировать все оставшиеся посты для всех групп")
    args = parser.parse_args()

    if args.list:
        cmd_list(args.group)
    elif args.pending:
        cmd_pending(args.group)
    elif args.mark:
        grp, date_str = args.mark
        cmd_mark(grp, date_str)
    else:
        env = load_env()
        if args.all:
            for grp in GROUPS.keys():
                pending = get_pending_posts(grp, count=1000)
                cnt = len(pending)
                if cnt:
                    print(f"\n🚀 Генерируем все ({cnt}) оставшиеся посты для группы {grp}")
                    cmd_generate(cnt, env, group=grp)
        else:
            cmd_generate(args.count, env, group=args.group)


if __name__ == "__main__":
    main()
