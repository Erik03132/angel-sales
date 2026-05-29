#!/usr/bin/env python3
"""
📸 PHOTO CACHE BUILDER — Предзагрузчик фото для VPS

Запускается ЛОКАЛЬНО (где Unsplash доступен).
Скачивает фото → загружает в VK → сохраняет VK attachment IDs в photo_cache.json
VPS-постер читает attachment IDs из кеша — никаких внешних запросов.

Использование:
    python3 photo_cache_builder.py build        — строит кеш для всех постов
    python3 photo_cache_builder.py status        — показывает состояние кеша
    python3 photo_cache_builder.py add "keywords" group  — добавляет одну запись
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from photo_cascade import (
    download_photo,
    fetch_pexels,
    fetch_pixabay,
    fetch_unsplash,
    generate_fal_flux,
    generate_imagen,
    load_env,
    upload_photo_to_vk,
)

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV        = load_env(os.path.join(BASE_DIR, ".env"))
CACHE_FILE = os.path.join(BASE_DIR, "data", "photo_cache.json")

# User token нужен для photos.getWallUploadServer
VK_USER_TOKEN      = ENV.get("VK_USER_TOKEN", "")
VK_PODVORYE_GID    = ENV.get("VK_PODVORYE_GROUP_ID", "").lstrip("-")
VK_VEZEMCYP_GID    = ENV.get("VK_VEZEMCYP_GROUP_ID", ENV.get("VK_GROUP_ID", "")).lstrip("-")

# Маппинг: группа → group_id (токен всегда user token!)
GROUPS = {
    "podvorye": VK_PODVORYE_GID,
    "vezemcyp": VK_VEZEMCYP_GID,
}

# ─── Кеш ──────────────────────────────────────────────────────────────────────

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"💾 Кеш сохранён: {CACHE_FILE}")


def cache_key(keywords: str, group: str) -> str:
    return f"{group}::{keywords.lower().strip()}"


def get_cached(keywords: str, group: str) -> str:
    cache = load_cache()
    return cache.get(cache_key(keywords, group), "")


# ─── Получить и загрузить одно фото ───────────────────────────────────────────

def fetch_and_upload(keywords: str, group: str) -> str:
    """Скачивает фото → загружает в VK (user token) → возвращает attachment-строку."""
    gid = GROUPS.get(group, "")
    if not gid:
        print(f"❌ Не найден group_id для группы '{group}'")
        return ""
    if not VK_USER_TOKEN:
        print("❌ VK_USER_TOKEN не найден в .env — нужен user token для загрузки фото")
        return ""

    unsplash_key = ENV.get("UNSPLASH_ACCESS_KEY", "")
    pexels_key   = ENV.get("PEXELS_API_KEY", "")
    pixabay_key  = ENV.get("PIXABAY_API_KEY", "")
    fal_key      = ENV.get("FAL_KEY", "")
    gemini_key   = ENV.get("GEMINI_API_KEY", "")
    us_proxy     = ENV.get("TELEGRAM_PROXY", "")  # US SOCKS5 для обхода гео-блокировки Google AI

    print(f"\n🔍 [{group}] «{keywords}»")
    photo_url = None
    local_path = None  # AI-генераторы могут вернуть локальный файл

    # ═══ КАСКАД: Стоки → AI-генерация ═══
    # Уровень 1-3: Стоковые фото (бесплатно)
    if unsplash_key:
        photo_url = fetch_unsplash(keywords, unsplash_key)
    if not photo_url and pexels_key:
        photo_url = fetch_pexels(keywords, pexels_key)
    if not photo_url and pixabay_key:
        photo_url = fetch_pixabay(keywords, pixabay_key)

    # Уровень 4: FAL.ai Flux Schnell (~$0.003 за фото)
    if not photo_url and fal_key:
        photo_url = generate_fal_flux(keywords, fal_key)

    # Уровень 5: Google Imagen 4.0 (через US прокси, бесплатно с Pro)
    if not photo_url and gemini_key and us_proxy:
        local_path = generate_imagen(keywords, gemini_key, proxy=us_proxy)

    if not photo_url and not local_path:
        print("  ⚠️ Фото не найдено ни в стоках, ни через AI — запись без фото")
        return ""

    # Для стоков/FAL — скачиваем URL, для Imagen — файл уже локальный
    if not local_path:
        local_path = download_photo(photo_url)
    if not local_path:
        print("  ⚠️ Не удалось скачать фото")
        return ""

    attachment = upload_photo_to_vk(local_path, VK_USER_TOKEN, gid)
    return attachment or ""


# ─── Парсинг постов ───────────────────────────────────────────────────────────

def extract_keywords_from_posts(filepath: str) -> list[dict]:
    """Парсит md-файл постов, извлекает ключевые слова для поиска фото."""
    if not os.path.exists(filepath):
        print(f"⚠️ Файл не найден: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    raw_posts = re.split(r'\n---\n', content)
    results = []

    for i, raw in enumerate(raw_posts):
        raw = raw.strip()
        if not raw:
            continue

        # Ищем # ФОТО-ЗАПРОС: keywords
        keywords = ""
        rubric = ""
        title = f"Пост {i+1}"

        for line in raw.split("\n"):
            if line.startswith("# ФОТО-ЗАПРОС:"):
                keywords = line.replace("# ФОТО-ЗАПРОС:", "").strip()
            elif line.startswith("# Рубрика:"):
                rubric = line.replace("# Рубрика:", "").strip()
            elif line.startswith("# ПОСТ"):
                title = line.lstrip("# ").strip()

        if not keywords:
            keywords = f"{rubric} {title}".strip() or "птицеводство"

        results.append({"index": i+1, "keywords": keywords, "title": title})

    return results


# ─── Команды ──────────────────────────────────────────────────────────────────

def _check_network() -> bool:
    """Проверка HTTP-соединения через curl (без привязки к интерфейсу)."""
    import subprocess
    for url in ("https://api.unsplash.com", "https://pixabay.com"):
        try:
            r = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "--max-time", "8", "--connect-timeout", "6", url],
                capture_output=True, timeout=12
            )
            code = r.stdout.decode().strip()
            if r.returncode == 0 and code not in ("", "000"):
                return True
        except Exception:
            pass
    return False


def cmd_build():
    """Строит кеш для всех постов обеих групп."""
    # Fail-fast: проверяем сеть до старта
    print("🔌 Проверка сети...")
    if not _check_network():
        print("❌ Сеть недоступна (Unsplash/Pixabay не отвечают по HTTPS).")
        print("   Проверь VPN-приложения: AmneziaVPN, Outline, ProtonVPN — закрой все.")
        sys.exit(1)
    print("✅ Сеть OK\n")

    cache = load_cache()
    updated = 0
    network_errors = 0  # счётчик подряд идущих ошибок

    # Файлы постов
    post_files = {
        "podvorye": os.path.join(BASE_DIR, "vk_content", "podvorye", "week1_posts.md"),
        "vezemcyp": os.path.join(BASE_DIR, "vk_content", "vezemcyp", "starter_posts.md"),
    }

    for group, filepath in post_files.items():
        print(f"\n{'='*50}")
        print(f"  📂 Группа: {group}")
        print(f"  Файл: {filepath}")
        print(f"{'='*50}")

        posts = extract_keywords_from_posts(filepath)
        if not posts:
            print(f"  ⚠️ Постов не найдено в {filepath}")
            continue

        for post in posts:
            key = cache_key(post["keywords"], group)
            if key in cache and cache[key]:
                print(f"  ✅ #{post['index']} «{post['keywords'][:40]}» — уже в кеше: {cache[key]}")
                network_errors = 0  # успех сбрасывает счётчик
                continue

            attachment = fetch_and_upload(post["keywords"], group)
            if attachment:
                cache[key] = attachment
                updated += 1
                network_errors = 0
                print(f"  ✅ #{post['index']} → {attachment}")
            else:
                network_errors += 1
                print(f"  ⚠️ #{post['index']} — без фото (ошибок подряд: {network_errors})")
                if network_errors >= 5:
                    save_cache(cache)
                    print("\n🛑 Стоп: 5 ошибок подряд — VPN нестабилен или сеть пропала.")
                    print(f"   Обновлено до прерывания: {updated}")
                    sys.exit(1)

    save_cache(cache)
    print(f"\n🏁 Готово! Обновлено записей: {updated}")


def cmd_status():
    """Показывает состояние кеша."""
    cache = load_cache()
    print(f"\n📊 PHOTO CACHE STATUS — {len(cache)} записей")
    print(f"Файл: {CACHE_FILE}\n")
    for key, val in cache.items():
        group, kw = key.split("::", 1)
        status = f"✅ {val}" if val else "⚠️ нет фото"
        print(f"  [{group}] «{kw[:40]}» → {status}")


def cmd_add(keywords: str, group: str):
    """Добавляет одну запись в кеш."""
    cache = load_cache()
    key = cache_key(keywords, group)
    attachment = fetch_and_upload(keywords, group)
    cache[key] = attachment
    save_cache(cache)
    print(f"\n✅ Добавлено: [{group}] «{keywords}» → {attachment or 'нет фото'}")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "build":
        cmd_build()
    elif cmd == "status":
        cmd_status()
    elif cmd == "add" and len(sys.argv) >= 4:
        cmd_add(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
