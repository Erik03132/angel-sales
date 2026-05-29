#!/usr/bin/env python3
"""
🚀 Прямая публикация постов Тихона — без vk_api, только curl.
Генерирует фото через Imagen 4.0, загружает в VK, публикует.
"""

import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.parse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env():
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


def vk_api(method, params):
    """VK API через curl."""
    qs = urllib.parse.urlencode(params)
    url = f"https://api.vk.com/method/{method}?{qs}"
    r = subprocess.run(["curl", "-s", "--max-time", "30", url], capture_output=True, timeout=40)
    return json.loads(r.stdout)


def generate_imagen(prompt, gemini_key, proxy):
    """Imagen 4.0 через US прокси."""
    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}
    })
    cmd = ["curl", "-s", "--max-time", "30", "--connect-timeout", "10"]
    if proxy:
        cmd.extend(["--proxy", proxy])
    cmd.extend([
        "-H", "Content-Type: application/json", "-d", body,
        f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict?key={gemini_key}"
    ])
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=40)
        data = json.loads(r.stdout)
        if "predictions" in data:
            return base64.b64decode(data["predictions"][0]["bytesBase64Encoded"])
    except Exception as e:
        print(f"  ❌ Imagen: {e}")
    return None


def upload_photo(photo_bytes, group_id, user_token):
    """Загрузка фото в VK через curl."""
    # 1. Upload URL
    d = vk_api("photos.getWallUploadServer", {
        "access_token": user_token, "group_id": group_id, "v": "5.199"
    })
    if "error" in d:
        print(f"  ❌ {d['error']['error_msg']}")
        return None
    upload_url = d["response"]["upload_url"]

    # 2. Upload file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(photo_bytes)
        tmp = f.name
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "60", "-F", f"photo=@{tmp}", upload_url],
            capture_output=True, timeout=70
        )
        ud = json.loads(r.stdout)
    finally:
        os.unlink(tmp)

    # 3. Save
    sd = vk_api("photos.saveWallPhoto", {
        "access_token": user_token, "group_id": group_id,
        "photo": ud["photo"], "server": ud["server"], "hash": ud["hash"], "v": "5.199"
    })
    if "error" in sd:
        print(f"  ❌ {sd['error']['error_msg']}")
        return None
    p = sd["response"][0]
    att = f"photo{p['owner_id']}_{p['id']}"
    print(f"  📸 {att}")
    return att


def post_to_wall(text, attachment, group_id, token):
    """Публикация на стену через group token."""
    params = {
        "owner_id": f"-{group_id}",
        "from_group": 1,
        "message": text,
        "access_token": token,
        "v": "5.199"
    }
    if attachment:
        params["attachments"] = attachment
    d = vk_api("wall.post", params)
    if "error" in d:
        print(f"  ❌ wall.post: {d['error']['error_msg']}")
        return None
    return d["response"]["post_id"]


# ═══════════════════════════════════════════════
# Два поста Тихона
# ═══════════════════════════════════════════════

POSTS = [
    {
        "group": "podvorye",
        "prompt": "Veterinarian examining sick baby chicks with bloody droppings, coccidiosis prevention treatment, clean farm clinic setting, warm natural light, professional veterinary photography. No text, no words, no letters, no watermarks.",
        "file": "tikhon_2026_05_12.md",
        "post_index": 12,
    },
    {
        "group": "podvorye",
        "prompt": "Professional cost calculation spreadsheet with white broiler chickens, feed bags, money bills, calculator and eggs arranged on rustic wooden table, farm accounting concept, warm golden light. No text, no words, no letters, no watermarks.",
        "file": "tikhon_2026_05_12.md",
        "post_index": 13,
    },
]


def main():
    env = load_env()
    gemini_key = env.get("GEMINI_API_KEY", "")
    proxy = env.get("TELEGRAM_PROXY", "")
    user_token = env.get("VK_USER_TOKEN", "")

    podvorye_token = env.get("VK_PODVORYE_TOKEN", "")
    podvorye_gid = env.get("VK_PODVORYE_GROUP_ID", "").lstrip("-")

    if not all([gemini_key, user_token, podvorye_token, podvorye_gid]):
        print("❌ Не хватает ключей в .env!")
        return

    # Читаем тексты из файла
    content_file = os.path.join(BASE_DIR, "vk_content", "podvorye", "tikhon_2026_05_12.md")
    with open(content_file) as f:
        content = f.read()

    # Парсим два блока через ---
    import re
    blocks = re.split(r'\n---\n', content)

    texts = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        text_lines = []
        for line in lines:
            if line.startswith("# ") and not line.startswith("## "):
                continue
            if line.startswith("## Пост"):
                continue
            if line.startswith("**") and line.endswith("**"):
                text_lines.append(line.strip("*").strip())
                continue
            text_lines.append(line)
        text = "\n".join(text_lines).strip()
        if len(text) > 20:
            texts.append(text)

    if len(texts) < 2:
        print(f"❌ Нашёл только {len(texts)} текст(ов)")
        return

    print("🚀 Публикация 2 постов Тихона Полевадова → Своё Подворье")
    print(f"   Группа: {podvorye_gid}")
    print(f"   Imagen 4.0: {'✅' if proxy else '⚠️ без прокси'}\n")

    # Лог
    log_path = os.path.join(BASE_DIR, "vk_content", "podvorye", "posted_log.json")
    posted_log = {}
    if os.path.exists(log_path):
        with open(log_path) as f:
            posted_log = json.load(f)

    for i, (post_cfg, text) in enumerate(zip(POSTS, texts)):
        print(f"[{i+1}/2] {text[:60]}...")

        # Генерация фото
        print(f"  🎨 Imagen: «{post_cfg['prompt'][:60]}»...")
        photo = generate_imagen(post_cfg["prompt"], gemini_key, proxy)
        if photo:
            print(f"  ✅ Фото: {len(photo)//1024} KB")
        else:
            print("  ⚠️ Без фото")

        # Загрузка в VK
        attachment = None
        if photo:
            attachment = upload_photo(photo, podvorye_gid, user_token)

        # Публикация
        print("  📝 Публикую...")
        post_id = post_to_wall(text, attachment, podvorye_gid, podvorye_token)
        if post_id:
            url = f"https://vk.com/wall-{podvorye_gid}_{post_id}"
            print(f"  ✅ {url}")

            # Обновляем лог
            posted_log[str(post_cfg["post_index"])] = {
                "post_id": post_id,
                "url": url,
                "posted_at": __import__("datetime").datetime.now().isoformat(),
                "source_file": post_cfg["file"],
                "text_preview": text[:80],
                "has_photo": bool(attachment),
            }
            keys = set(posted_log.get("_keys", []))
            keys.add(f"tikhon_{post_cfg['post_index']}")
            posted_log["_keys"] = list(keys)
        else:
            print("  ❌ Не опубликован")

        if i < 1:
            print("  ⏳ Пауза 5 сек...\n")
            time.sleep(5)

    # Сохраняем лог
    with open(log_path, "w") as f:
        json.dump(posted_log, f, ensure_ascii=False, indent=2)

    print(f"\n{'═'*50}")
    print(f"  ✅ Готово! Лог обновлён: {log_path}")
    print(f"{'═'*50}")


if __name__ == "__main__":
    main()
