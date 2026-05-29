#!/usr/bin/env python3
"""
📢 VK Smart Autoposter — автоматическая публикация из markdown-файлов.

Работает с ОБОИМИ форматами контент-файлов:
  Формат A (старый): ## Пост N — дата + текст + хэштеги в `...`
  Формат B (новый): # ПОСТ N + # ФОТО-ЗАПРОС: + --- разделитель

Логика:
  1. Сканирует все .md файлы в папке группы
  2. Находит неопубликованные посты (сверка с posted_log.json)
  3. Генерирует фото через Imagen 4.0 (Gemini API)
  4. Публикует 1 пост и обновляет лог

Использование:
  python3 vk_smart_poster.py vezemcyp          # 1 пост ВезёмЦыплят
  python3 vk_smart_poster.py podvorye           # 1 пост Своё Подворье
  python3 vk_smart_poster.py all                # 1+1 (оба)
  python3 vk_smart_poster.py vezemcyp --count 3 # 3 поста
  python3 vk_smart_poster.py all --dry-run      # без публикации
"""

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(BASE_DIR, "agent")
sys.path.insert(0, AGENT_DIR)

from vk_poster_base import VKPoster, load_env, parse_posts_from_file

# ═══════════════════════════════════════════════
# Конфигурация
# ═══════════════════════════════════════════════

CONTENT_DIR = os.path.join(BASE_DIR, "vk_content")

GROUPS = {
    "vezemcyp": {
        "env_token": "VK_VEZEMCYP_TOKEN",
        "env_group_id": "VK_VEZEMCYP_GROUP_ID",
        "fallback_group_id": "VK_GROUP_ID",
        "name": "ВезёмЦыплят",
        "content_dir": os.path.join(CONTENT_DIR, "vezemcyp"),
        "posted_log": os.path.join(CONTENT_DIR, "vezemcyp", "posted_log.json"),
        "default_photo_prompt": "Professional photo of adorable fluffy yellow baby chicks on green grass, warm golden sunlight, farm background. No text, no words, no letters, no watermarks.",
    },
    "podvorye": {
        "env_token": "VK_PODVORYE_TOKEN",
        "env_group_id": "VK_PODVORYE_GROUP_ID",
        "fallback_group_id": None,
        "name": "Своё Подворье",
        "content_dir": os.path.join(CONTENT_DIR, "podvorye"),
        "posted_log": os.path.join(CONTENT_DIR, "podvorye", "posted_log.json"),
        "default_photo_prompt": "Charming rural Russian farmstead with wooden house, vegetable garden, free-range chickens on green grass, warm golden hour light. No text, no words, no letters, no watermarks.",
    },
}


# ═══════════════════════════════════════════════
# Парсер постов (универсальный — оба формата)
# ═══════════════════════════════════════════════

def parse_all_posts(content_dir):
    """Парсит все .md файлы в папке, возвращает список постов."""
    all_posts = []

    md_files = sorted([
        f for f in os.listdir(content_dir)
        if f.endswith(".md") and not f.startswith("month") and f != "test_post.md"
    ])

    for md_file in md_files:
        filepath = os.path.join(content_dir, md_file)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Определяем формат
        if "# ПОСТ" in content or "# Рубрика:" in content:
            # Формат B (vk_poster_base стиль)
            posts = parse_posts_from_file(filepath)
            for p in posts:
                p["source_file"] = md_file
                p["post_id_key"] = _make_post_key(p.get("text", ""), md_file, p.get("index", 0))
                all_posts.append(p)
        else:
            # Формат A (## Пост N стиль)
            posts = _parse_format_a(content, md_file)
            all_posts.extend(posts)

    return all_posts


def _parse_format_a(content, source_file):
    """Парсит формат A: ## Пост N — дата + текст + хэштеги."""
    posts = []
    # Разбиваем по разделителям ---
    blocks = re.split(r'\n---\n', content)

    for i, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        meta = {}
        text_lines = []
        hashtags = ""

        for line in lines:
            # Заголовок файла (# ВК-посты: ...)
            if line.startswith("# ") and not line.startswith("## "):
                continue
            # Заголовок поста (## Пост N — дата)
            if line.startswith("## Пост"):
                meta["title"] = line.lstrip("# ").strip()
                # Извлекаем номер поста из заголовка
                m = re.search(r'Пост\s+(\d+)', line)
                if m:
                    meta["post_num"] = int(m.group(1))
                continue
            # Подзаголовок (**текст**)
            if line.startswith("**") and line.endswith("**"):
                text_lines.append(line.strip("*").strip())
                continue
            # Хэштеги в обратных кавычках
            if line.strip().startswith("`#"):
                hashtags = line.strip().strip("`")
                continue
            text_lines.append(line)

        post_text = "\n".join(text_lines).strip()
        if hashtags:
            post_text += "\n\n" + hashtags

        if not post_text or len(post_text) < 20:
            continue

        # Извлекаем ключевые слова из хэштегов для фото
        photo_keywords = " ".join(
            tag.lstrip("#") for tag in hashtags.split()
            if tag.startswith("#")
        )[:100] if hashtags else ""

        # Используем номер из заголовка если есть, иначе enumerate
        post_index = meta.get("post_num", i + 1)

        posts.append({
            "index": post_index,
            "meta": meta,
            "text": post_text,
            "is_poll": False,
            "source_file": source_file,
            "photo_query": photo_keywords,
            "post_id_key": _make_post_key(post_text, source_file, post_index),
        })

    return posts


def _make_post_key(text, source_file, index):
    """Уникальный ключ поста для дедупликации."""
    raw = f"{source_file}:{index}:{text[:100]}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════
# Imagen 4.0 — генерация фото
# ═══════════════════════════════════════════════

def _make_imagen_prompt(post_text, meta, default_prompt):
    """Создаёт АНГЛИЙСКИЙ промпт для Imagen на основе текста поста."""
    # Если есть явный ФОТО-ЗАПРОС в метаданных (уже на английском)
    photo_query = meta.get("photo_query", "")
    if photo_query and all(ord(c) < 128 for c in photo_query.replace(" ", "")):
        return photo_query + ". No text, no words, no letters, no watermarks."

    # Маппинг ключевых тем на английские промпты
    topic_prompts = {
        "бройлер": "White broiler chickens in a clean farm coop with straw bedding, natural lighting",
        "цыплят": "Adorable fluffy yellow baby chicks on green grass, warm golden sunlight, farm",
        "несушк": "Brown laying hens in a free-range farm setting, eggs in a basket, rustic style",
        "индюк": "Large white turkeys on a green farm pasture, rural countryside",
        "утят": "Cute baby ducklings near a pond on a farm, warm natural light",
        "гусят": "White goslings on green grass near water, rural farm setting",
        "инкубатор": "Modern egg incubator with eggs inside, warm glow, farm technology",
        "козь": "Adorable goats on a green pasture, rural farmstead, warm golden hour",
        "огород": "Beautiful vegetable garden in spring with seedlings and green rows, sunny day",
        "доставк": "Delivery truck on a rural road with green fields, sunrise, warm colors",
        "прайс": "Fresh farm produce arranged beautifully, eggs, vegetables, warm rustic setting",
        "подворь": "Charming Russian rural farmstead, wooden house, garden, chickens on grass",
        "посад": "Spring garden planting, hands placing seedlings in soil, warm sunlight",
        "сравнен": "Side by side comparison of two chicken breeds on a farm, professional photo",
        "опрос": "Happy farmers gathering with animals on a green farm, community feel",
        "дайджест": "Beautiful rural farm landscape at golden hour, peaceful countryside scene",
        "видео": "Dynamic farm life scene, chickens running on green grass, vibrant colors",
        "итоги": "Successful farm harvest celebration, abundance of produce and happy animals",
    }

    text_lower = post_text.lower()
    for keyword, prompt in topic_prompts.items():
        if keyword in text_lower:
            return f"{prompt}. Professional photography, vivid colors. No text, no words, no letters, no watermarks."

    return default_prompt


def generate_imagen_photo(prompt, env, aspect="16:9"):
    """Генерация фото через Imagen 4.0 + US SOCKS5 прокси. Возвращает bytes или None."""
    gemini_key = env.get("GEMINI_API_KEY", "")
    proxy = env.get("TELEGRAM_PROXY", "")

    if not gemini_key:
        print("  ⚠️ GEMINI_API_KEY не найден")
        return None

    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": aspect}
    }, ensure_ascii=True)

    cmd = ["curl", "-s", "--max-time", "30", "--connect-timeout", "10"]
    # Прокси (опционально)
    if proxy:
        cmd.extend(["--proxy", proxy])
    cmd.extend([
        "-H", "Content-Type: application/json",
        "-d", body,
        f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict?key={gemini_key}"
    ])

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=40)
        data = json.loads(result.stdout)
        if "predictions" in data:
            img_b64 = data["predictions"][0]["bytesBase64Encoded"]
            photo_bytes = base64.b64decode(img_b64)
            print(f"  ✅ Imagen 4.0: фото сгенерировано ({len(photo_bytes) // 1024} KB)")
            return photo_bytes
        else:
            err = json.dumps(data, ensure_ascii=False)[:200]
            print(f"  ⚠️ Imagen error: {err}")
    except Exception as e:
        print(f"  ⚠️ Imagen exception: {e}")
    return None


def upload_photo_bytes_vk(photo_bytes, group_id, env):
    """Загрузка сгенерированного фото в VK через User Token."""
    user_token = env.get("VK_USER_TOKEN", "")
    if not user_token:
        print("  ⚠️ VK_USER_TOKEN не найден — фото не загрузить")
        return None

    try:
        import requests
    except ImportError:
        # Простой fallback без requests
        print("  ⚠️ requests не установлен, фото пропускаем")
        return None

    # 1. Get upload URL
    r = requests.get("https://api.vk.com/method/photos.getWallUploadServer", params={
        "access_token": user_token, "group_id": group_id, "v": "5.199"
    })
    d = r.json()
    if "error" in d:
        print(f"  ❌ Upload URL: {d['error']['error_msg']}")
        return None
    upload_url = d["response"]["upload_url"]

    # 2. Upload tmp file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(photo_bytes)
        tmp_path = f.name

    try:
        with open(tmp_path, "rb") as f:
            r2 = requests.post(upload_url, files={"photo": f})
        ud = r2.json()
    finally:
        os.unlink(tmp_path)

    # 3. Save
    r3 = requests.get("https://api.vk.com/method/photos.saveWallPhoto", params={
        "access_token": user_token, "group_id": group_id,
        "photo": ud["photo"], "server": ud["server"], "hash": ud["hash"], "v": "5.199"
    })
    sd = r3.json()
    if "error" in sd:
        print(f"  ❌ Save: {sd['error']['error_msg']}")
        return None
    p = sd["response"][0]
    attachment = f"photo{p['owner_id']}_{p['id']}"
    print(f"  📸 Фото загружено в VK: {attachment}")
    return attachment


# ═══════════════════════════════════════════════
# Логика публикации
# ═══════════════════════════════════════════════

def load_posted(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_posted(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_posts(content_dir, posted_log_path, count=1):
    """Возвращает список из count неопубликованных постов."""
    all_posts = parse_all_posts(content_dir)
    posted = load_posted(posted_log_path)
    posted_keys = set(posted.get("_keys", []))

    # Также проверяем по индексу (совместимость со старым форматом)
    posted_indices = set(str(k) for k in posted.keys() if k != "_keys")

    unpublished = []
    for post in all_posts:
        key = post.get("post_id_key", "")
        idx = str(post.get("index", 0))
        if key not in posted_keys and idx not in posted_indices:
            unpublished.append(post)

    return unpublished[:count]


def publish_group(group_key, env, count=1, dry_run=False):
    """Публикует count постов для указанной группы."""
    cfg = GROUPS[group_key]
    token = env.get(cfg["env_token"], "")
    group_id = env.get(cfg["env_group_id"], "")
    if not group_id and cfg.get("fallback_group_id"):
        group_id = env.get(cfg["fallback_group_id"], "")
    group_id = group_id.lstrip("-")

    if not token or not group_id:
        print(f"❌ {cfg['name']}: токен или group_id не найдены в .env")
        return []

    posts = get_next_posts(cfg["content_dir"], cfg["posted_log"], count)
    if not posts:
        print(f"✅ {cfg['name']}: все посты опубликованы!")
        return []

    print(f"\n{'═' * 50}")
    print(f"  📢 {cfg['name']} — {len(posts)} пост(ов) к публикации")
    print(f"{'═' * 50}")

    if dry_run:
        poster = None
    else:
        try:
            poster = VKPoster(token, group_id, env)
            info = poster.check_token()
            if info.get("ok"):
                print(f"  ✅ Группа: {info['name']} ({info['members']} подписчиков)")
            else:
                print(f"  ⚠️ Проверка токена: {info.get('error', '?')}")
        except Exception as e:
            print(f"  ❌ Ошибка инициализации VKPoster: {e}")
            return []

    results = []
    posted_log = load_posted(cfg["posted_log"])
    posted_keys = set(posted_log.get("_keys", []))

    for i, post in enumerate(posts):
        print(f"\n  [{i + 1}/{len(posts)}] {post['text'][:60]}...")

        if dry_run:
            print("  🔸 DRY-RUN: пропуск публикации")
            results.append({"status": "dry-run", "text": post["text"][:50]})
            continue

        # Фото через Imagen 4.0
        attachment = None
        prompt = _make_imagen_prompt(post["text"], post.get("meta", {}), cfg["default_photo_prompt"])
        print(f"  🎨 Imagen 4.0: «{prompt[:60]}»...")
        photo_bytes = generate_imagen_photo(prompt, env)
        if photo_bytes:
            attachment = upload_photo_bytes_vk(photo_bytes, group_id, env)

        # Публикация
        print("  📝 Публикую...")
        post_id = poster.post(post["text"], attachments=attachment)

        if post_id:
            url = f"https://vk.com/wall-{group_id}_{post_id}"
            print(f"  ✅ Опубликован: {url}")

            # Обновляем лог
            key = post.get("post_id_key", str(post.get("index", i)))
            posted_keys.add(key)
            posted_log[str(post.get("index", i + 1))] = {
                "post_id": post_id,
                "url": url,
                "posted_at": datetime.now().isoformat(),
                "source_file": post.get("source_file", "?"),
                "text_preview": post["text"][:80],
                "has_photo": bool(attachment),
            }
            posted_log["_keys"] = list(posted_keys)
            save_posted(cfg["posted_log"], posted_log)

            results.append({"status": "ok", "post_id": post_id, "url": url})
        else:
            print("  ❌ Не опубликован")
            results.append({"status": "fail"})

        # Пауза между постами (VK rate limit: 1 запрос/сек)
        if i < len(posts) - 1:
            print("  ⏳ Пауза 5 сек...")
            time.sleep(5)

    return results


# ═══════════════════════════════════════════════
# TG уведомление
# ═══════════════════════════════════════════════

def send_tg_report(results_all, env):
    """Отправляет сводку в Telegram."""
    tg_token = env.get("ANGELOCHKA_BOT_TOKEN", "")
    chat_id = env.get("OWNER_CHAT_ID", "176203333")
    if not tg_token:
        return

    total = sum(len(r) for r in results_all.values())
    ok = sum(1 for rs in results_all.values() for r in rs if r.get("status") == "ok")

    lines = [f"📢 *VK Autoposter* — {datetime.now().strftime('%d.%m.%Y %H:%M')}", ""]
    for group, results in results_all.items():
        name = GROUPS[group]["name"]
        for r in results:
            if r.get("status") == "ok":
                lines.append(f"✅ {name}: [пост]({r['url']})")
            elif r.get("status") == "dry-run":
                lines.append(f"🔸 {name}: dry-run")
            else:
                lines.append(f"❌ {name}: ошибка")

    lines.append(f"\nИтого: {ok}/{total}")

    text = "\n".join(lines)

    try:
        import urllib.parse
        import urllib.request
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            data=data,
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  ⚠️ TG: {e}")


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="VK Smart Autoposter")
    parser.add_argument("group", choices=["vezemcyp", "podvorye", "all"], help="Группа для постинга")
    parser.add_argument("--count", "-n", type=int, default=1, help="Количество постов (по умолчанию 1)")
    parser.add_argument("--dry-run", action="store_true", help="Без публикации (только просмотр)")
    parser.add_argument("--list", action="store_true", help="Показать все неопубликованные посты")
    args = parser.parse_args()

    env = load_env()

    groups = [args.group] if args.group != "all" else ["vezemcyp", "podvorye"]

    if args.list:
        for g in groups:
            cfg = GROUPS[g]
            posts = get_next_posts(cfg["content_dir"], cfg["posted_log"], count=100)
            print(f"\n{'═' * 50}")
            print(f"  {cfg['name']}: {len(posts)} неопубликованных")
            print(f"{'═' * 50}")
            for i, p in enumerate(posts[:10], 1):
                print(f"  {i}. [{p.get('source_file', '?')}] {p['text'][:70]}...")
        return

    results_all = {}
    for g in groups:
        results = publish_group(g, env, count=args.count, dry_run=args.dry_run)
        results_all[g] = results

    # TG отчёт
    if not args.dry_run:
        send_tg_report(results_all, env)

    # Итог
    total = sum(len(r) for r in results_all.values())
    ok = sum(1 for rs in results_all.values() for r in rs if r.get("status") == "ok")
    print(f"\n{'═' * 50}")
    print(f"  📊 ИТОГО: {ok}/{total} опубликовано")
    print(f"{'═' * 50}")


if __name__ == "__main__":
    main()
