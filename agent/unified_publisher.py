#!/usr/bin/env python3
"""
unified_publisher.py — Единый постинг из папки ok/ во все платформы.

Источник контента: ok/<дата_номер>/post.txt + photo.png
Платформы: Telegram, ВКонтакте, Одноклассники, Дзен (через ТГ‑мост)

Использование:
  python3 unified_publisher.py --next              # опубликовать следующий пост
  python3 unified_publisher.py --next --count 3    # опубликовать 3 поста
  python3 unified_publisher.py --post 2026-05-13_01  # конкретный пост
  python3 unified_publisher.py --status            # показать статус всех постов
  python3 unified_publisher.py --preview           # просмотр очереди (5 постов)
  python3 unified_publisher.py --preview --count 20  # просмотр 20 постов
  python3 unified_publisher.py --next --only tg    # только в Telegram
  python3 unified_publisher.py --next --only vk    # только в ВК
  python3 unified_publisher.py --next --dry        # сухой прогон (ничего не публикует)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ── Пути ──
BASE_DIR = Path(__file__).parent.parent          # ai-eggs/
CONTENT_DIR = BASE_DIR.parent / "ok"             # freelance-2026/ok/
LOG_PATH = CONTENT_DIR / "unified_log.json"
ENV_FILE = BASE_DIR / ".env"

# ── Загрузка .env ──
load_dotenv(ENV_FILE, override=True)

# ── Импорт адаптеров ──
sys.path.insert(0, str(BASE_DIR / "agent"))
from publish_adapters import Post, publish_to_dzen, publish_to_ok, publish_to_tg

# ── VK конфиг (берём из .env) ──
VK_TOKEN = os.getenv("VK_USER_TOKEN")
VK_GROUPS = {
    "vezemcyp": os.getenv("VK_VEZEMCYP_GROUP_ID", "-238316002"),
    "podvorye": os.getenv("VK_PODVORYE_GROUP_ID", "-238230663"),
}
# По умолчанию постим в «Своё Подворье»
VK_DEFAULT_GROUP = "podvorye"


def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# Единый лог
# ═══════════════════════════════════════════════════════════════════════════
def load_log() -> dict:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    return {}


def save_log(data: dict):
    LOG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# Сканирование готового контента
# ═══════════════════════════════════════════════════════════════════════════
def scan_posts() -> list[dict]:
    """Возвращает список готовых постов из ok/, отсортированных по дате."""
    posts = []
    if not CONTENT_DIR.exists():
        return posts

    for d in sorted(CONTENT_DIR.iterdir()):
        if not d.is_dir():
            continue
        # Пропускаем служебные папки (podvorye, vezemcyp и т.д.)
        if not re.match(r"^\d{4}-\d{2}-\d{2}", d.name):
            continue
        post_file = d / "post.txt"
        photo_file = d / "photo.png"
        if not post_file.exists():
            continue
        posts.append({
            "id": d.name,
            "dir": d,
            "post_file": post_file,
            "photo_file": photo_file if photo_file.exists() else None,
        })
    return posts


def get_pending_posts() -> list[dict]:
    """Посты, которые ещё не были опубликованы ни на одну платформу."""
    db = load_log()
    all_posts = scan_posts()
    return [p for p in all_posts if p["id"] not in db]


def parse_post_text(post_file: Path) -> tuple[str, str]:
    """Читает post.txt → возвращает (title, text)."""
    content = post_file.read_text(encoding="utf-8").strip()
    lines = content.split("\n", 1)
    title = lines[0].strip()
    text = lines[1].strip() if len(lines) > 1 else ""
    return title, text


# ═══════════════════════════════════════════════════════════════════════════
# VK публикация (встроенная, без внешних библиотек)
# ═══════════════════════════════════════════════════════════════════════════
def publish_to_vk(vk_text: str, image_path: Path | None,
                  group_key: str = "podvorye") -> int | None:
    """Публикует пост в стену группы ВК. Возвращает post_id или None."""
    if not VK_TOKEN:
        log_msg("⚠️ VK_USER_TOKEN не задан — пропускаю VK.")
        return None

    group_id = VK_GROUPS.get(group_key, VK_GROUPS["podvorye"])
    photo_ids = []

    # Загружаем фото, если есть
    if image_path and image_path.exists():
        try:
            params = urllib.parse.urlencode({
                "group_id": group_id.lstrip("-"),
                "access_token": VK_TOKEN,
                "v": "5.199"
            })
            with urllib.request.urlopen(
                f"https://api.vk.com/method/photos.getWallUploadServer?{params}", timeout=15
            ) as r:
                upload_url = json.loads(r.read())["response"]["upload_url"]

            with open(image_path, "rb") as f:
                img_data = f.read()
            boundary = "----FormBoundary7MA4YWxkTrZu0gW"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="photo"; filename="{image_path.name}"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(upload_url, data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                upload_resp = json.loads(r.read())

            params2 = urllib.parse.urlencode({
                "group_id": group_id.lstrip("-"),
                "server": upload_resp["server"],
                "photo":  upload_resp["photo"],
                "hash":   upload_resp["hash"],
                "access_token": VK_TOKEN,
                "v": "5.199"
            })
            with urllib.request.urlopen(
                f"https://api.vk.com/method/photos.saveWallPhoto?{params2}", timeout=15
            ) as r:
                saved = json.loads(r.read())["response"][0]
            photo_ids.append(f"photo{saved['owner_id']}_{saved['id']}")
            log_msg(f"  📸 VK фото: {photo_ids[-1]}")
        except Exception as e:
            log_msg(f"  ⚠️ VK фото ошибка: {e}")

    post_params = {
        "owner_id": group_id,
        "from_group": 1,
        "message": vk_text,
        "access_token": VK_TOKEN,
        "v": "5.199"
    }
    if photo_ids:
        post_params["attachments"] = ",".join(photo_ids)

    data = urllib.parse.urlencode(post_params).encode()
    req = urllib.request.Request("https://api.vk.com/method/wall.post",
        data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        post_id = resp["response"]["post_id"]
        log_msg(f"  ✅ VK: пост {post_id}")
        return post_id
    except Exception as e:
        log_msg(f"  ❌ VK ошибка: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Главная функция публикации
# ═══════════════════════════════════════════════════════════════════════════
PLATFORMS = ["tg", "vk", "ok", "dzen"]

def publish_post(post_info: dict, only: list[str] | None = None,
                 dry: bool = False) -> dict:
    """Публикует один пост на все (или выбранные) платформы.
    Возвращает dict с результатами."""
    post_id = post_info["id"]
    title, text = parse_post_text(post_info["post_file"])
    photo = post_info["photo_file"]

    targets = only if only else PLATFORMS
    full_text = f"{title}\n\n{text}" if text else title

    log_msg(f"\n{'═' * 55}")
    log_msg(f"  📌 Пост: {post_id}")
    log_msg(f"  📝 {title[:60]}...")
    log_msg(f"  🎯 Платформы: {', '.join(targets)}")
    if dry:
        log_msg("  ⚙️  DRY RUN — ничего не публикуется")
    log_msg(f"{'═' * 55}")

    results = {
        "id": post_id,
        "title": title,
        "published_at": datetime.now().isoformat(),
        "platforms": {},
    }

    # ── Telegram ──
    if "tg" in targets:
        if dry:
            log_msg("  🔸 TG: dry — пропуск")
            results["platforms"]["tg"] = "dry"
        else:
            post_obj = Post(title=title, text=text, image_path=photo)
            ok = publish_to_tg(post_obj)
            results["platforms"]["tg"] = "ok" if ok else "error"
            log_msg(f"  {'✅' if ok else '❌'} TG: {'ok' if ok else 'error'}")

    # ── Дзен (через ТГ‑мост) ──
    if "dzen" in targets:
        if dry:
            log_msg("  🔸 Дзен: dry — пропуск")
            results["platforms"]["dzen"] = "dry"
        else:
            post_obj = Post(title=title, text=text, image_path=photo)
            ok = publish_to_dzen(post_obj)
            results["platforms"]["dzen"] = "ok" if ok else "error"
            log_msg(f"  {'✅' if ok else '❌'} Дзен: {'ok' if ok else 'error'}")

    # ── ВКонтакте ──
    if "vk" in targets:
        if dry:
            log_msg("  🔸 VK: dry — пропуск")
            results["platforms"]["vk"] = "dry"
        else:
            vk_id = publish_to_vk(full_text, photo, VK_DEFAULT_GROUP)
            results["platforms"]["vk"] = vk_id if vk_id else "error"

    # ── Одноклассники ──
    if "ok" in targets:
        if dry:
            log_msg("  🔸 OK: dry — пропуск")
            results["platforms"]["ok"] = "dry"
        else:
            post_obj = Post(title=title, text=text, image_path=photo)
            ok_result = publish_to_ok(post_obj)
            results["platforms"]["ok"] = "ok" if ok_result else "error"
            log_msg(f"  {'✅' if ok_result else '❌'} OK: {'ok' if ok_result else 'error'}")

    # ── Записываем в лог ──
    if not dry:
        db = load_log()
        db[post_id] = results
        save_log(db)

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Команды CLI
# ═══════════════════════════════════════════════════════════════════════════
def cmd_status():
    """Показать статус всех постов."""
    all_posts = scan_posts()
    db = load_log()
    published = [p for p in all_posts if p["id"] in db]
    pending = [p for p in all_posts if p["id"] not in db]

    print(f"\n📊 Всего постов: {len(all_posts)}")
    print(f"   ✅ Опубликовано: {len(published)}")
    print(f"   ⏳ Ожидают: {len(pending)}")

    if pending:
        print("\n   Следующие 5 в очереди:")
        for p in pending[:5]:
            title, _ = parse_post_text(p["post_file"])
            has_photo = "📸" if p["photo_file"] else "  "
            print(f"   {has_photo} {p['id']}  {title[:50]}")

    if published:
        print("\n   Последние 5 опубликованных:")
        for p in published[-5:]:
            entry = db[p["id"]]
            platforms = ", ".join(f"{k}:{v}" for k, v in entry.get("platforms", {}).items())
            print(f"   ✅ {p['id']}  [{platforms}]")
    print()


def cmd_preview(count: int):
    """Показать превью ожидающих постов — текст, фото, заголовок."""
    pending = get_pending_posts()
    if not pending:
        print("🎉 Очередь пуста — все посты опубликованы!")
        return

    to_show = pending[:count]
    print(f"\n🔎 ПРЕВЬЮ: {len(to_show)} из {len(pending)} ожидающих постов\n")

    for i, post_info in enumerate(to_show, 1):
        title, text = parse_post_text(post_info["post_file"])
        has_photo = "📸 есть" if post_info["photo_file"] else "❌ НЕТ ФОТО"
        
        print(f"{'─' * 60}")
        print(f"  #{i}  📌 {post_info['id']}")
        print(f"  📷 {has_photo}")
        print(f"  📝 {title}")
        # Показываем первые 200 символов текста
        preview_text = text[:200].replace('\n', '\n     ')
        if text:
            print(f"     {preview_text}")
            if len(text) > 200:
                print(f"     ... (ещё {len(text) - 200} символов)")
        print()

    print(f"{'─' * 60}")
    print(f"\n📊 Итого без фото: {sum(1 for p in to_show if not p['photo_file'])} из {len(to_show)}")
    print(f"\n💡 Для публикации: --next --count {len(to_show)}")
    print(f"   Для просмотра больше: --preview --count {count * 2}\n")


def cmd_next(count: int, only: list[str] | None, dry: bool):
    """Опубликовать следующие N постов."""
    pending = get_pending_posts()
    if not pending:
        print("🎉 Все посты уже опубликованы!")
        return

    to_publish = pending[:count]
    print(f"\n🚀 Публикуем {len(to_publish)} пост(ов) из {len(pending)} ожидающих\n")

    for i, post_info in enumerate(to_publish, 1):
        publish_post(post_info, only=only, dry=dry)
        if i < len(to_publish):
            log_msg("⏸️  Пауза 5 сек...")
            time.sleep(5)

    print(f"\n✅ Готово! Опубликовано: {len(to_publish)}")


def cmd_post(post_id: str, only: list[str] | None, dry: bool):
    """Опубликовать конкретный пост по ID."""
    all_posts = scan_posts()
    match = [p for p in all_posts if p["id"] == post_id]
    if not match:
        print(f"❌ Пост '{post_id}' не найден в ok/")
        return
    publish_post(match[0], only=only, dry=dry)


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Единый постинг из ok/ → TG + VK + OK + Дзен")
    parser.add_argument("--next", action="store_true",
                        help="Опубликовать следующий неопубликованный пост")
    parser.add_argument("--post", type=str, metavar="ID",
                        help="Опубликовать конкретный пост (напр. 2026-05-13_01)")
    parser.add_argument("--status", action="store_true",
                        help="Показать статус всех постов")
    parser.add_argument("--preview", action="store_true",
                        help="Показать превью ожидающих постов")
    parser.add_argument("--count", type=int, default=5,
                        help="Сколько постов показать/опубликовать (по умолчанию 5)")
    parser.add_argument("--only", type=str, nargs="+",
                        choices=PLATFORMS,
                        help="Публиковать только на указанные платформы")
    parser.add_argument("--dry", action="store_true",
                        help="Сухой прогон — ничего не публикуется")
    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.preview:
        cmd_preview(args.count)
    elif args.next:
        cmd_next(args.count, args.only, args.dry)
    elif args.post:
        cmd_post(args.post, args.only, args.dry)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
