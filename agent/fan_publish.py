#!/usr/bin/env python3
"""
📡 FAN PUBLISH — Веерная публикация поста на все площадки.

Принимает pending post по ID и публикует на выбранные площадки:
  - TG: @svoye_podvorye или @podvorye_dzen
  - VK: wall.post через VK API
  - Дзен: через TG-мост @podvorye_dzen → автоимпорт
  - Сайт: создание файла для деплоя (vezemcip.ru)

Использование:
  from fan_publish import fan_publish
  results = fan_publish(post_id, platforms=["tg", "vk", "dzen"])
"""

import json
import os
import subprocess
import sys

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(AGENT_DIR)
sys.path.insert(0, AGENT_DIR)

PENDING_DIR = os.path.join(BASE_DIR, "data", "pending_posts")


def _load_env():
    env = {}
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env


def load_pending(post_id: str) -> dict | None:
    """Загружает pending пост из буфера."""
    filepath = os.path.join(PENDING_DIR, f"{post_id}.json")
    if not os.path.exists(filepath):
        print(f"❌ Пост {post_id} не найден в буфере")
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def update_pending_status(post_id: str, status: str, results: dict = None):
    """Обновляет статус поста в буфере."""
    filepath = os.path.join(PENDING_DIR, f"{post_id}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["status"] = status
        if results:
            data["publish_results"] = results
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# --- Публикация в TG канал ---
def _publish_tg(pending: dict, env: dict) -> bool:
    """Публикация в TG канал через Bot API."""
    from morning_post import BRANDS
    brand_key = pending["brand"]
    brand = BRANDS.get(brand_key, {})
    channel_id = brand.get("tg_channel")

    if not channel_id:
        print(f"   ⚠️ TG канал не настроен для {brand_key}")
        return False

    bot_token = env.get("TG_BOT_TOKEN", "")
    if not bot_token:
        print("   ❌ TG_BOT_TOKEN не найден")
        return False

    post = pending["post"]
    photo_path = pending.get("photo_path")
    caption = post["text"][:1024]
    base_url = f"https://api.telegram.org/bot{bot_token}"

    PROXY = env.get("TELEGRAM_PROXY", "")
    PROXY_FLAG = ["--proxy", PROXY] if PROXY else []
    RESOLVE = ["--resolve", "api.telegram.org:443:149.154.167.220"]

    try:
        if photo_path and os.path.exists(photo_path):
            cmd = [
                "curl", "-s", "--max-time", "30",
                *RESOLVE, *PROXY_FLAG,
                "--form-string", f"chat_id={channel_id}",
                "--form-string", f"caption={caption}",
                "-F", "parse_mode=HTML",
                "-F", f"photo=@{photo_path}",
                f"{base_url}/sendPhoto",
            ]
        else:
            body = json.dumps({
                "chat_id": channel_id,
                "text": caption,
                "parse_mode": "HTML",
            })
            cmd = [
                "curl", "-s", "--max-time", "15",
                *RESOLVE, *PROXY_FLAG,
                "-H", "Content-Type: application/json",
                "-d", body,
                f"{base_url}/sendMessage",
            ]

        result = subprocess.run(cmd, capture_output=True, timeout=35)
        resp = json.loads(result.stdout)
        if resp.get("ok"):
            print(f"   ✅ TG канал {channel_id}")
            return True
        else:
            print(f"   ❌ TG: {resp.get('description', 'unknown error')}")
            return False
    except Exception as e:
        print(f"   ❌ TG: {e}")
        return False


# --- Публикация в Дзен (через TG-мост) ---
def _publish_dzen(pending: dict, env: dict) -> bool:
    """Публикация в Дзен через TG-канал-мост."""
    import re

    from morning_post import BRANDS
    brand_key = pending["brand"]
    brand = BRANDS.get(brand_key, {})
    dzen_channel = brand.get("dzen_bridge")

    if not dzen_channel:
        print(f"   ⚠️ Дзен-мост не настроен для {brand_key}")
        return False

    bot_token = env.get("TG_BOT_TOKEN", "")
    if not bot_token:
        print("   ❌ TG_BOT_TOKEN не найден")
        return False

    post = pending["post"]
    photo_path = pending.get("photo_path")
    # Компактный текст для Дзена
    text = re.sub(r'\n{3,}', '\n\n', post["text"]).strip()
    caption = text[:1024]
    base_url = f"https://api.telegram.org/bot{bot_token}"

    PROXY = env.get("TELEGRAM_PROXY", "")
    PROXY_FLAG = ["--proxy", PROXY] if PROXY else []
    RESOLVE = ["--resolve", "api.telegram.org:443:149.154.167.220"]

    try:
        if photo_path and os.path.exists(photo_path):
            cmd_photo = [
                "curl", "-s", "--max-time", "30",
                *RESOLVE, *PROXY_FLAG,
                "--form-string", f"chat_id={dzen_channel}",
                "-F", f"photo=@{photo_path}",
                f"{base_url}/sendPhoto",
            ]
            r = subprocess.run(cmd_photo, capture_output=True, timeout=35)
            resp = json.loads(r.stdout) if r.stdout else {}
            if not resp.get("ok"):
                print(f"   ❌ Дзен фото: {resp.get('description', 'unknown')}")
                return False
            print(f"   ✅ Фото в Дзен")

        body = json.dumps({
            "chat_id": dzen_channel,
            "text": caption,
            "parse_mode": "HTML",
        })
        cmd_text = [
            "curl", "-s", "--max-time", "15",
            *RESOLVE, *PROXY_FLAG,
            "-H", "Content-Type: application/json",
            "-d", body,
            f"{base_url}/sendMessage",
        ]
        r = subprocess.run(cmd_text, capture_output=True, timeout=20)
        resp = json.loads(r.stdout) if r.stdout else {}
        if resp.get("ok"):
            print(f"   ✅ Дзен-мост {dzen_channel}")
            return True
        else:
            print(f"   ❌ Дзен текст: {resp.get('description', 'unknown error')}")
            return False
    except Exception as e:
        print(f"   ❌ Дзен: {e}")
        return False


# --- Публикация в VK ---
def _clean_text(text: str) -> str:
    """Очищает текст от служебных маркеров перед публикацией."""
    lines = text.strip().split('\n')
    cleaned = []
    skip_section = False
    for line in lines:
        if 'AEO-блок' in line or 'AEO block' in line.lower():
            skip_section = True
            continue
        if skip_section:
            if line.strip() == '---':
                skip_section = False
            continue
        if line.startswith('📹 ТЗ') or line.startswith('🎥 СЦЕНАРИЙ'):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def _adapt_text_for_vk(text: str) -> str:
    """
    Адаптация текста под формат ВК.
    Заголовки: ЗАГЛАВНЫМИ БУКВАМИ (работает везде, не зависит от VK Markdown).
    """
    result = _clean_text(text)

    HEADER_EMOJIS = {'❌', '✅', '🌱', '💡', '🌿', '📌', '⬇️', '👇', '🔑', '⚡', '🌟', '🔥'}

    adapted = []
    for i, line in enumerate(result.split('\n')):
        stripped = line.strip()
        if not stripped:
            adapted.append(line)
            continue

        if stripped.startswith('#'):
            adapted.append(line)
            continue

        is_header = (i == 0) or (stripped[0] in HEADER_EMOJIS and len(stripped) < 150)
        if is_header:
            adapted.append(stripped.upper())
        else:
            adapted.append(line)

    result = '\n'.join(adapted)

    if not any(h in result for h in ['#', '👇', '↓']):
        result += "\n\n👇 Пишите в комментариях!"

    return result[:4000]


def _publish_vk(pending: dict, env: dict) -> bool:
    """Публикация в VK через wall.post API."""
    import urllib.parse

    from morning_post import BRANDS
    brand_key = pending["brand"]
    brand = BRANDS.get(brand_key, {})

    vk_token = brand.get("vk_token") or env.get("VK_PODVORYE_TOKEN", "")
    vk_group_id = brand.get("vk_group_id") or env.get("VK_PODVORYE_GROUP_ID", "")
    
    vk_user_token = env.get("VK_USER_TOKEN", "")

    if not vk_token or not vk_group_id:
        print(f"   ⚠️ VK токен/группа не настроены для {brand_key}")
        return False

    post = pending["post"]
    photo_path = pending.get("photo_path")
    
    message = _adapt_text_for_vk(post["text"])
    print(f"   📝 VK текст адаптирован ({len(message)} симв.)")

    attachment = ""
    if photo_path:
        if os.path.exists(photo_path):
            try:
                from photo_cascade import upload_photo_to_vk
                gid = vk_group_id.lstrip("-")
                upload_token = vk_user_token if vk_user_token else vk_token
                att = upload_photo_to_vk(photo_path, upload_token, gid)
                if att:
                    attachment = att
                    print(f"   ✅ Фото загружено: {attachment}")
                else:
                    print("   ⚠️ Фото не загружено (ошибка API)")
            except Exception as e:
                print(f"   ⚠️ VK фото не загружено: {e}")
        else:
            print(f"   ⚠️ Файл фото удалён ({photo_path}) — пост без фото")

    # wall.post (через user token для жирного шрифта)
    try:
        owner_id = vk_group_id if vk_group_id.startswith("-") else f"-{vk_group_id}"
        params = {
            "owner_id": owner_id,
            "message": message,
            "access_token": vk_user_token or vk_token,  # User token для жирного шрифта
            "v": "5.199",
        }
        if attachment:
            params["attachments"] = attachment

        cmd = ["curl", "-s", "--max-time", "15", "https://api.vk.com/method/wall.post"]
        for k, v in params.items():
            cmd += ["-d", f"{k}={urllib.parse.quote(str(v))}"]

        result = subprocess.run(cmd, capture_output=True, timeout=20)
        resp = json.loads(result.stdout)

        if "response" in resp:
            post_vk_id = resp["response"].get("post_id", "?")
            print(f"   ✅ VK (post_id: {post_vk_id})")
            return True
        else:
            err = resp.get("error", {}).get("error_msg", "unknown")
            print(f"   ❌ VK: {err}")
            return False
    except Exception as e:
        print(f"   ❌ VK: {e}")
        return False


# --- Сохранение в OK (для ручного размещения) ---
def _save_to_ok(pending: dict, env: dict) -> bool:
    """Сохраняет пост в data/ok_posts/ для ручной публикации в ОК."""
    from datetime import datetime

    post = pending["post"]
    photo_path = pending.get("photo_path")
    now = datetime.now()
    folder_name = now.strftime("%Y-%m-%d_%H%M")
    brand_key = pending.get("brand", "podvorye")

    ok_dir = os.path.join(BASE_DIR, "data", "ok_posts", brand_key, folder_name)
    os.makedirs(ok_dir, exist_ok=True)

    lines = post["text"].split("\n")
    title = lines[0].strip()[:100] if lines else "Новый пост"
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else post["text"]

    with open(os.path.join(ok_dir, "post.txt"), "w", encoding="utf-8") as f:
        f.write(f"{title}\n\n{body}")

    if photo_path and os.path.exists(photo_path):
        import shutil
        shutil.copy2(photo_path, os.path.join(ok_dir, "photo.png"))

    print(f"   ✅ OK: {ok_dir}")
    return True


# --- Определение типа поста ---
def _is_poultry_post(text: str) -> bool:
    """Проверяет, относится ли пост к цыплятам/утятам/птице."""
    import re
    poultry_keywords = [
        r"\bцыплят", r"\bутят", r"\bбройлер", r"\bкуриц", r"\bкурам",
        r"\bкуры\b", r"\bпетух", r"\bнесушк", r"\bиндюк", r"\bиндейк",
        r"\bпород\w*\s+кур", r"\bинкубатор", r"\bвылуп", r"\bсуточн.*цып",
        r"\bкормление.*цып", r"\bзабивать.*бройлер", r"\bубой.*бройлер",
        r"\bутк\w*\s+на\s+мясо", r"\bптицевод",
    ]
    clean = text.lower()
    for pattern in poultry_keywords:
        if re.search(pattern, clean):
            return True
    return False


# --- Публикация на сайт (ВезёмЦыплят) ---
def _publish_site(pending: dict, env: dict) -> bool:
    """Создаёт файл для публикации на vezemcip.ru (только для птицы)."""
    from datetime import datetime

    post = pending["post"]
    text = post["text"]

    if not _is_poultry_post(text):
        print("   ⏭️ Сайт: только для постов про цыплят/утят — пропущен")
        return True

    now = datetime.now()
    slug = f"post-{now.strftime('%Y%m%d-%H%M')}"

    site_content_dir = os.path.join(BASE_DIR, "data", "site_posts")
    os.makedirs(site_content_dir, exist_ok=True)

    filepath = os.path.join(site_content_dir, f"{slug}.md")

    lines = text.split("\n")
    title = lines[0].strip()[:100] if lines else "Новый пост"
    import re
    clean_title = re.sub(r'[^\w\s\-,.:!?]', '', title).strip()

    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else text

    content = f"""---
title: "{clean_title}"
description: "{clean_title[:160]}"
pubDate: "{now.isoformat()}"
draft: false
---

{body}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"   ✅ Сайт: {filepath}")
    return True


# --- Главная функция веера ---
def fan_publish(post_id: str, platforms: list[str] = None) -> dict:
    """Веерная публикация поста на все/выбранные площадки.

    Returns: {"tg": True, "vk": False, "dzen": True, ...}
    """
    pending = load_pending(post_id)
    if not pending:
        return {}

    env = _load_env()

    if platforms is None:
        platforms = pending.get("platforms", ["tg", "vk", "dzen"])

    print(f"\n📡 Веерная публикация: {pending['brand_name']}")
    print(f"   Площадки: {' → '.join(platforms)}")
    print(f"   {'─' * 40}")

    publishers = {
        "tg": _publish_tg,
        "dzen": _publish_dzen,
        "vk": _publish_vk,
        "ok": _save_to_ok,
        "site": _publish_site,
    }

    results = {}
    for platform in platforms:
        publisher = publishers.get(platform)
        if publisher:
            results[platform] = publisher(pending, env)
        else:
            print(f"   ⚠️ Неизвестная площадка: {platform}")
            results[platform] = False

    # Обновляем статус
    all_ok = all(results.values())
    update_pending_status(post_id, "published" if all_ok else "partial", results)

    print(f"   {'─' * 40}")
    ok_count = sum(1 for v in results.values() if v)
    print(f"   📊 Результат: {ok_count}/{len(results)} площадок\n")

    return results


# --- CLI ---
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="📡 Fan Publish — веерная публикация")
    parser.add_argument("post_id", help="ID поста из pending_posts/")
    parser.add_argument("--platforms", "-p", nargs="+", help="Площадки (tg vk dzen site)")
    args = parser.parse_args()

    fan_publish(args.post_id, args.platforms)
