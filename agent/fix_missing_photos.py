#!/usr/bin/env python3
"""
🔧 Исправление постов без фото.
Генерирует картинки через Imagen 4.0 (US прокси) и добавляет к существующим постам ВК.

Использование:
  python3 fix_missing_photos.py           # Исправить все посты без фото
  python3 fix_missing_photos.py --dry-run # Только показать что нужно исправить
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(BASE_DIR, "agent")
sys.path.insert(0, AGENT_DIR)

from vk_poster_base import load_env

# ═══════════════════════════════════════════════
# Посты без фото (из posted_log.json)
# ═══════════════════════════════════════════════

POSTS_TO_FIX = [
    {
        "group": "podvorye",
        "group_id": "238230663",
        "post_id": 55,
        "log_key": "8",
        "prompt": "Happy goats on green pasture with morning dew, rustic farm setting, golden hour light. Professional photography. No text, no words, no letters, no watermarks.",
        "text_hint": "Козье молоко — заработок 2026",
    },
    {
        "group": "podvorye",
        "group_id": "238230663",
        "post_id": 56,
        "log_key": "9",
        "prompt": "Side by side comparison of white Cobb and Ross broiler chickens on a farm, professional photography, vivid colors, green grass background. No text, no words, no letters, no watermarks.",
        "text_hint": "ТЗ для видео — Кобб или Росс",
    },
    {
        "group": "podvorye",
        "group_id": "238230663",
        "post_id": 57,
        "log_key": "10",
        "prompt": "Home egg incubator with eggs inside, warm amber glow, cozy farm kitchen background, professional macro photography. No text, no words, no letters, no watermarks.",
        "text_hint": "Инкубаторы Несушка vs Золушка",
    },
    {
        "group": "podvorye",
        "group_id": "238230663",
        "post_id": 58,
        "log_key": "11",
        "prompt": "Beautiful rural Russian farmstead panorama with wooden house, vegetable garden, free-range chickens and ducks on green grass, warm golden hour light, newsletter digest feel. No text, no words, no letters, no watermarks.",
        "text_hint": "Дайджест Своего Подворья — неделя 2",
    },
]


def generate_imagen(prompt, gemini_key, proxy):
    """Генерация через Imagen 4.0 Fast + US SOCKS5 прокси."""
    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}
    }, ensure_ascii=True)

    cmd = ["curl", "-s", "--max-time", "30", "--connect-timeout", "10"]
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
            print(f"  ✅ Imagen 4.0: {len(photo_bytes) // 1024} KB")
            return photo_bytes
        else:
            err = json.dumps(data, ensure_ascii=False)[:200]
            print(f"  ❌ Imagen error: {err}")
    except Exception as e:
        print(f"  ❌ Imagen exception: {e}")
    return None


def _vk_api(method, params):
    """Вызов VK API через curl (urllib дает TLS timeout на этом Mac)."""
    import urllib.parse
    qs = urllib.parse.urlencode(params)
    url = f"https://api.vk.com/method/{method}?{qs}"
    result = subprocess.run(
        ["curl", "-s", "--max-time", "30", "--connect-timeout", "10", url],
        capture_output=True, timeout=40
    )
    return json.loads(result.stdout)


def _multipart_upload(upload_url, photo_bytes):
    """Multipart upload фото через curl (более надёжный для VK)."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(photo_bytes)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "60", "--connect-timeout", "15",
             "-F", f"photo=@{tmp_path}",
             upload_url],
            capture_output=True, timeout=70
        )
        return json.loads(result.stdout)
    finally:
        os.unlink(tmp_path)


def upload_photo_vk(photo_bytes, group_id, user_token):
    """Загрузка фото в VK (stdlib only)."""
    # 1. Get upload URL
    d = _vk_api("photos.getWallUploadServer", {
        "access_token": user_token, "group_id": group_id, "v": "5.199"
    })
    if "error" in d:
        print(f"  ❌ Upload URL: {d['error']['error_msg']}")
        return None
    upload_url = d["response"]["upload_url"]

    # 2. Upload
    ud = _multipart_upload(upload_url, photo_bytes)

    # 3. Save
    sd = _vk_api("photos.saveWallPhoto", {
        "access_token": user_token, "group_id": group_id,
        "photo": ud["photo"], "server": ud["server"], "hash": ud["hash"], "v": "5.199"
    })
    if "error" in sd:
        print(f"  ❌ Save: {sd['error']['error_msg']}")
        return None
    p = sd["response"][0]
    attachment = f"photo{p['owner_id']}_{p['id']}"
    print(f"  📸 Фото: {attachment}")
    return attachment


def edit_post_add_photo(owner_id, post_id, attachment, token):
    """Добавляет фото к существующему посту через wall.edit (stdlib only)."""
    # Получаем текущий пост
    d = _vk_api("wall.getById", {
        "posts": f"-{owner_id}_{post_id}",
        "access_token": token,
        "v": "5.199"
    })
    if "error" in d:
        print(f"  ❌ getById: {d['error']['error_msg']}")
        return False

    items = d.get("response", {}).get("items", [])
    if not items:
        print("  ❌ Пост не найден")
        return False

    post = items[0]
    original_text = post.get("text", "")

    # Собираем существующие вложения
    existing_attachments = []
    for att in post.get("attachments", []):
        att_type = att.get("type")
        if att_type == "photo":
            p = att["photo"]
            existing_attachments.append(f"photo{p['owner_id']}_{p['id']}")
        elif att_type == "poll":
            p = att["poll"]
            existing_attachments.append(f"poll{p['owner_id']}_{p['id']}")

    # Добавляем новое фото
    all_attachments = existing_attachments + [attachment]

    # Редактируем пост
    ed = _vk_api("wall.edit", {
        "owner_id": f"-{owner_id}",
        "post_id": post_id,
        "message": original_text,
        "attachments": ",".join(all_attachments),
        "access_token": token,
        "v": "5.199"
    })
    if "error" in ed:
        print(f"  ❌ wall.edit: {ed['error']['error_msg']}")
        return False

    print("  ✅ Пост обновлён!")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fix posts without photos")
    parser.add_argument("--dry-run", action="store_true", help="Только показать")
    args = parser.parse_args()

    env = load_env()
    gemini_key = env.get("GEMINI_API_KEY", "")
    proxy = env.get("TELEGRAM_PROXY", "")
    user_token = env.get("VK_USER_TOKEN", "")

    if not gemini_key:
        print("❌ GEMINI_API_KEY не найден!")
        return
    if not user_token:
        print("❌ VK_USER_TOKEN не найден!")
        return

    print(f"🔧 Исправление {len(POSTS_TO_FIX)} постов без фото")
    print(f"   Imagen 4.0 через US прокси: {'✅' if proxy else '⚠️ без прокси'}")
    print()

    fixed = 0
    for i, task in enumerate(POSTS_TO_FIX):
        print(f"[{i+1}/{len(POSTS_TO_FIX)}] {task['text_hint']}")
        print(f"   URL: https://vk.com/wall-{task['group_id']}_{task['post_id']}")

        if args.dry_run:
            print(f"   🎨 Промпт: {task['prompt'][:80]}...")
            print("   🔸 DRY-RUN\n")
            continue

        # 1. Генерируем фото
        print(f"  🎨 Imagen: «{task['prompt'][:60]}»...")
        photo_bytes = generate_imagen(task["prompt"], gemini_key, proxy)
        if not photo_bytes:
            print("  ⚠️ Пропуск — фото не сгенерировано\n")
            continue

        # 2. Загружаем в VK
        attachment = upload_photo_vk(photo_bytes, task["group_id"], user_token)
        if not attachment:
            print("  ⚠️ Пропуск — не загрузилось\n")
            continue

        # 3. Обновляем пост
        success = edit_post_add_photo(task["group_id"], task["post_id"], attachment, user_token)
        if success:
            fixed += 1

            # 4. Обновляем posted_log
            log_path = os.path.join(BASE_DIR, "vk_content", task["group"], "posted_log.json")
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    log = json.load(f)
                if task["log_key"] in log and isinstance(log[task["log_key"]], dict):
                    log[task["log_key"]]["has_photo"] = True
                    log[task["log_key"]]["photo_fixed"] = True
                    with open(log_path, "w") as f:
                        json.dump(log, f, ensure_ascii=False, indent=2)
                    print("  📝 Лог обновлён")

        print()
        # Пауза между постами
        if i < len(POSTS_TO_FIX) - 1:
            print("  ⏳ Пауза 3 сек...")
            time.sleep(3)

    print(f"\n{'═' * 50}")
    print(f"  📊 Исправлено: {fixed}/{len(POSTS_TO_FIX)}")
    print(f"{'═' * 50}")


if __name__ == "__main__":
    main()
