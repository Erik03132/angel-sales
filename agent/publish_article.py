#!/usr/bin/env python3
"""
🚀 publish_article.py — Пайплайн: Генерация → Imagen4 → ВК → Astro → Build
Использование:
  python3 publish_article.py --channel vezemcyp --topic "Хайсекс Браун: обзор породы"
  python3 publish_article.py --batch  # Публикует 2 статьи по расписанию
"""
import argparse
import base64
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent  # ai-eggs/
ENV_FILE = BASE_DIR / ".env"
# Принудительно очищаем старые значения и перечитываем
for _k in ["OPENROUTER_API_KEY","GEMINI_API_KEY","GEMINI_BACKUP_KEY","VK_USER_TOKEN","TELEGRAM_PROXY","PERPLEXITY_API_KEY"]:
    os.environ.pop(_k, None)
load_dotenv(ENV_FILE, override=True)

# === КОНФИГ ===
OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY")
GEMINI_KEY      = os.getenv("GEMINI_API_KEY")          # BZV6 — для Imagen4
GEMINI_BACKUP   = os.getenv("GEMINI_BACKUP_KEY")        # C9l5 — резерв
PROXY           = os.getenv("TELEGRAM_PROXY", "")
VK_TOKEN        = os.getenv("VK_USER_TOKEN")
VK_GROUPS = {
    "vezemcyp": "-238316002",   # ВезёмЦыплят
    "podvorye":  "-238230663",  # Своё Подворье
}
ASTRO_DIR    = BASE_DIR / "vezem"
BLOG_DIR     = ASTRO_DIR / "src" / "content" / "blog"
ASSETS_DIR   = ASTRO_DIR / "src" / "assets" / "blog"
LOG_PATH     = BASE_DIR / "vk_content" / "posted_log_unified.json"

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ─── 1. ГЕНЕРАЦИЯ ТЕКСТА (OpenRouter) ────────────────────────────────────────
def generate_text(topic: str, channel: str) -> dict:
    """Возвращает dict: title, description, body_md, tags, vk_text, image_prompt"""
    import requests as _req
    channel_ctx = {
        "vezemcyp": "ВезёмЦыплят — инкубатор, продажа суточных цыплят, доставка по ЮФО. SEO-статья для сайта vezemcip.ru.",
        "podvorye": "Своё Подворье — экспертный контент о домашнем птицеводстве, огороде, животноводстве.",
    }[channel]

    prompt = f"""Напиши SEO-статью для сайта. Контекст: {channel_ctx}

Тема: {topic}

Верни СТРОГО JSON (без markdown блоков):
{{
  "title": "Точный заголовок H1 (до 70 символов)",
  "description": "Мета-описание (120-160 символов)",
  "tags": ["тег1", "тег2", "тег3"],
  "body_md": "Полный текст статьи в Markdown (600-900 слов). H2 заголовки, списки, цифры, CTA в конце.",
  "vk_text": "Пост для ВКонтакте (200-400 символов). Эмодзи, хэштеги. Анонс статьи со ссылкой {{SITE_URL}}.",
  "image_prompt": "English prompt for Imagen4 (realistic photo style, farm/poultry theme, no text)"
}}"""

    try:
        r = _req.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://vezemcip.ru",
                "X-Title": "VezemCip Publisher",
            },
            json={"model": "deepseek/deepseek-chat",
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 3000},
            timeout=60,
            proxies={"http": None, "https": None},  # БЕЗ прокси!
        )
        resp = r.json()
        raw = resp["choices"][0]["message"]["content"].strip()
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        log(f"❌ OpenRouter ошибка: {e}")

        # Try Perplexity next
        if os.getenv('PERPLEXITY_API_KEY'):
            try:
                key = os.getenv('PERPLEXITY_API_KEY')
                r = _req.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-sonar-large-128k-online", "messages": [{"role": "user", "content": prompt}], "max_tokens": 3000},
                    timeout=60,
                    proxies={"http": None, "https": None},
                )
                resp = r.json()
                raw = resp["choices"][0]["message"]["content"].strip()
                raw = re.sub(r'^```json\\s*', '', raw)
                raw = re.sub(r'\\s*```$', '', raw)
                return json.loads(raw)
            except Exception as e2:
                log(f"❌ Perplexity ошибка: {e2}")

        # Finally try Gemini
        if GEMINI_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_KEY)
                model = genai.GenerativeModel('gemini-2.0-flash')
                response = model.generate_content(prompt)
                raw = response.text.strip()
                raw = re.sub(r'^```json\\s*', '', raw)
                raw = re.sub(r'\\s*```$', '', raw)
                return json.loads(raw)
            except Exception as e3:
                log(f"❌ Gemini ошибка: {e3}")
        return None

# ─── 2. ГЕНЕРАЦИЯ КАРТИНКИ (Imagen4 через прокси) ────────────────────────────
def generate_image(image_prompt: str, slug: str) -> str | None:
    """Генерирует изображение через Imagen4 и сохраняет его в assets. Возвращает относительный путь к файлу."""
    """Сохраняет картинку, возвращает путь /assets/blog/SLUG.jpg"""
    keys = [k for k in [GEMINI_KEY, GEMINI_BACKUP] if k]
    for key in keys:
        try:
            import socket

            import socks
            # Настраиваем SOCKS5 прокси
            proxy_parts = PROXY.replace("socks5h://", "").replace("socks5://", "")
            auth, hostport = proxy_parts.split("@")
            user, pwd = auth.split(":")
            host, port = hostport.split(":")
            socks.set_default_proxy(socks.SOCKS5, host, int(port), username=user, password=pwd)
            socket.socket = socks.socksocket

            url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict?key={key}"
            body = json.dumps({
                "instances": [{"prompt": image_prompt}],
                "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}
            }).encode()
            req = urllib.request.Request(url, data=body,
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())

            if "predictions" in data:
                img_b64 = data["predictions"][0].get("bytesBase64Encoded", "")
                out_path = ASSETS_DIR / f"{slug}.jpg"
                out_path.write_bytes(base64.b64decode(img_b64))
                log(f"🖼️ Картинка сохранена: {out_path.name}")
                return f"/assets/blog/{slug}.jpg"
            log(f"⚠️ Imagen4 ({key[:8]}...): {data.get('error','?')}")
        except Exception as e:
            log(f"⚠️ Imagen4 ошибка: {e}")
        finally:
            # Сбрасываем прокси
            try:
                import socket as _s

                import socks
                socks.set_default_proxy()
                import socket
                socket.socket = _s.socket
            except: pass
    return None

# ─── 3. ЗАПИСЬ .MD ФАЙЛА В ASTRO ─────────────────────────────────────────────
def write_astro_article(slug: str, article: dict, image_path: str | None,
                         channel: str, pub_date: str) -> Path:
    tags_yaml = json.dumps(article["tags"], ensure_ascii=False)
    img_line  = f'image: "{image_path}"' if image_path else ""
    frontmatter = f"""---
title: "{article['title'].replace('"', "'")}"
description: "{article['description'].replace('"', "'")}"
date: {pub_date}
{img_line}
tags: {tags_yaml}
vk_channel: "{channel}"
draft: false
---

"""
    md_path = BLOG_DIR / f"{slug}.md"
    md_path.write_text(frontmatter + article["body_md"], encoding="utf-8")
    log(f"📝 Astro статья: {md_path.name}")
    return md_path

# ─── 4. КЕШИРОВАНИЕ ФОТО В ВК (без публикации) ───────────────────────────────
def cache_image_vk(image_path: Path, channel: str) -> str | None:
    """Загружает изображение в VK и возвращает photo‑attachment string, не публикуя пост."""
    group_id = VK_GROUPS[channel]
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
            "Content-Type: image/jpeg\r\n\r\n"
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
        pid = f"photo{saved['owner_id']}_{saved['id']}"
        log(f"📦 Фото закешировано в VK: {pid}")
        return pid
    except Exception as e:
        log(f"⚠️ Ошибка кеширования фото в ВК: {e}")
        return None

# ─── 5. ПУБЛИКАЦИЯ В ВК ──────────────────────────────────────────────────────
def publish_to_vk(channel: str, vk_text: str, image_path: Path | None, photo_id: str = None) -> int | None:
    """Публикует пост в стену группы ВК. Принимает готовый photo_id или загружает файл сам."""
    group_id = VK_GROUPS[channel]
    photo_ids = [photo_id] if photo_id else []

    if image_path and image_path.exists() and not photo_id:
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
                "Content-Type: image/jpeg\r\n\r\n"
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
            log(f"📸 Фото загружено в ВК: {photo_ids[-1]}")
        except Exception as e:
            log(f"⚠️ Ошибка загрузки фото в ВК: {e}")

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
        log(f"✅ ВК пост опубликован: {post_id}")
        return post_id
    except Exception as e:
        log(f"❌ Ошибка публикации в ВК: {e}")
        return None

# ─── 5. BUILD ASTRO ──────────────────────────────────────────────────────────
def build_astro():
    log("🔨 Запуск npm run build...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=ASTRO_DIR,
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode == 0:
        log("✅ Astro build успешен!")
        return True
    log(f"❌ Astro build ошибка:\n{result.stderr[-500:]}")
    return False

# ─── 6. ЛОГИРОВАНИЕ ──────────────────────────────────────────────────────────
def save_log(slug: str, article: dict, channel: str, vk_post_id: int | None,
             image_path: str | None, site_url: str):
    db = {}
    if LOG_PATH.exists():
        db = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    db[slug] = {
        "title":      article["title"],
        "channel":    channel,
        "date":       datetime.now().strftime("%Y-%m-%d"),
        "vk_post_id": vk_post_id,
        "site_url":   site_url,
        "image":      image_path,
        "status":     "full" if vk_post_id and site_url else "partial",
    }
    LOG_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

# ─── ГЛАВНАЯ ФУНКЦИЯ ─────────────────────────────────────────────────────────
def publish_one(topic: str, channel: str, pub_date: str = None, dry: bool = False) -> bool:
    if not pub_date:
        pub_date = datetime.now().strftime("%Y-%m-%d")

    log(f"📌 Тема: {topic} | Канал: {channel} | Дата: {pub_date}")

    # 1. Генерируем текст
    log("✍️  Генерация текста (OpenRouter/DeepSeek)...")
    article = generate_text(topic, channel)
    if not article:
        return False

    # Slug из заголовка
    slug = re.sub(r'[^a-z0-9а-яё]', '-', article["title"].lower(), flags=re.UNICODE)
    slug = re.sub(r'-+', '-', slug).strip('-')[:60]
    slug = f"{pub_date}-{slug}"

    # 2. Генерируем картинку
    log(f"🖼️  Генерация Imagen4: {article['image_prompt'][:60]}...")
    image_path = generate_image(article["image_prompt"], slug)

    # 3. Пишем .md в Astro
    write_astro_article(slug, article, image_path, channel, pub_date)

    # 4. Публикуем в ВК (если не dry)
    site_url = f"https://vezemcip.ru/blog/{slug}"
    vk_text  = article["vk_text"].replace("{SITE_URL}", site_url)
    img_file = (ASSETS_DIR / f"{slug}.jpg") if image_path else None
    vk_id = None
    vk_cache_photo_id = None
    if not dry:
        vk_id = publish_to_vk(channel, vk_text, img_file)
    else:
        # Кешируем изображение в VK без публикации поста
        if img_file and img_file.exists():
            vk_cache_photo_id = cache_image_vk(img_file, channel)
        log("⚙️ Dry‑run: пост не опубликован, изображение закешировано в VK" if dry else "✅ Пост опубликован")

    # 5. Build Astro
    built = build_astro()

    # 6. Лог
    save_log(slug, article, channel, vk_id, image_path, site_url if built else "")
    if dry and vk_cache_photo_id:
        # Добавляем информацию о закешированном фото в лог для удобства ручного поста
        log(f"📦 Кешированный VK фото ID: {vk_cache_photo_id}")

    log(f"🎉 Готово! ВК: {vk_id} | Сайт: {site_url}")
    return True


BATCH_PLAN = [
    # (channel, topic)
    ("vezemcyp", "Хайсекс Браун: 320 яиц в год — полный обзор породы и экономика 100 голов"),
    ("podvorye",  "Помидоры в жару: 8 сортов для Юга, которые не сбрасывают завязь"),
]

def publish_batch():
    today = datetime.now().strftime("%Y-%m-%d")
    for channel, topic in BATCH_PLAN:
        publish_one(topic, channel, today)
        log("⏸️  Пауза 30 сек...")
        import time; time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Публикация статей ВК + Astro сайт")
    parser.add_argument("--channel", choices=["vezemcyp", "podvorye"], default="vezemcyp")
    parser.add_argument("--topic",   type=str, help="Тема статьи")
    parser.add_argument("--date",    type=str, help="Дата YYYY-MM-DD (по умолчанию сегодня)")
    parser.add_argument("--batch",   action="store_true", help="Запустить пакетную публикацию")
    parser.add_argument("--dry",     action="store_true", help="Только кэшировать в VK без публикации поста")
    args = parser.parse_args()

    if args.batch:
        # batch mode respects dry flag as well
        if args.dry:
            for ch, tp in BATCH_PLAN:
                publish_one(tp, ch, datetime.now().strftime("%Y-%m-%d"), dry=True)
        else:
            publish_batch()
    elif args.topic:
        publish_one(args.topic, args.channel, args.date, dry=args.dry)
    else:
        parser.print_help()
