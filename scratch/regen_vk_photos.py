#!/usr/bin/env python3
"""
Генерация фото через IMAGEN 4.0 (Google, US прокси) + замена в отложенных постах ВК.
Посты: 7, 8, 9, 10, 12, 13, 14 мая (ID=25,26,27,28,30,31,32)

ПРАВИЛО: ТОЛЬКО Imagen 4.0. FAL мёртв (баланс 0). Imagen бесплатный через Gemini Pro.
"""
import os
import sys
import json
import time
import base64
import requests
from pathlib import Path

# --- Конфиг ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB7g7QQLPO4E8sVxSnFVc3IBTaDjx3lh1A")
US_PROXY = os.getenv("TELEGRAM_PROXY", "socks5h://Q3NeJXTY:dsBaWh2L@172.120.21.141:64469")
VK_USER_TOKEN = os.getenv("VK_USER_TOKEN", "vk1.a.ky6cfAxtPfZqjDdUgh_aWTYheHGFJrP6qOZXFNqicJ80OQWwyXZTI2vbBsrrjPM_0grRSCVbELHl8yYux0SgFp3mfLgrbA5PFtOuu-DsM8tKpQ4d-gUKbTgyqYS8geF1aA5R6aWchv62RiM48-9lANYnuQTZH4by01cc76UbkQCmU-dEO093Q9D06f6H2z4-HDYkvJXFqGWbsFkr7eQJcQ")
GROUP_ID = 238316002
OUT_DIR = Path(os.path.expanduser("~/Pictures/content/vk_vezemcyp"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

IMAGEN_URL = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict?key={GEMINI_API_KEY}"

# --- Задания: post_id → промпт ---
TASKS = [
    {
        "post_id": 25,
        "date": "07.05",
        "filename": "07may_delivery_map.png",
        "prompt": "Professional realistic photograph of a white commercial delivery van with ventilation driving on a road through beautiful southern Russian green fields landscape with distant mountains, golden hour warm lighting. NO TEXT, NO WORDS, NO LETTERS, NO WATERMARKS"
    },
    {
        "post_id": 26,
        "date": "08.05",
        "filename": "08may_pricelist.png",
        "prompt": "Professional product photograph: five different adorable day-old baby chicks in a row on soft bedding — yellow broiler, brown layer hen chick, white duckling, fluffy gosling, turkey poult. Soft studio lighting, white clean background, cute, commercial poultry farm. NO TEXT, NO WORDS, NO LETTERS"
    },
    {
        "post_id": 27,
        "date": "09.05",
        "filename": "09may_calendar.png",
        "prompt": "Realistic photo: several fluffy yellow baby chicks sitting around a desk calendar on a rustic wooden table, warm natural window lighting, shallow depth of field, cozy farm feeling. NO TEXT, NO WORDS, NO LETTERS, NO WATERMARKS"
    },
    {
        "post_id": 28,
        "date": "10.05",
        "filename": "10may_incubator.png",
        "prompt": "Inside a modern poultry incubator facility: rows of eggs in trays under warm orange glow, some eggs cracking with tiny wet chicks emerging. Clean industrial look, dramatic warm lighting, documentary style. NO TEXT, NO WORDS, NO LETTERS"
    },
    {
        "post_id": 30,
        "date": "12.05",
        "filename": "12may_review_loman.png",
        "prompt": "Happy middle-aged woman farmer in rural backyard with several reddish-brown Lohmann Brown laying hens around her, holding basket of fresh eggs, smiling. Countryside with vineyards in background. Natural golden sunlight, lifestyle photography. NO TEXT, NO WORDS, NO LETTERS"
    },
    {
        "post_id": 31,
        "date": "13.05",
        "filename": "13may_howto_order.png",
        "prompt": "Professional flat lay overhead: smartphone with chat app, notepad with pen, cardboard box with fluffy yellow chicks peeking out, arranged neatly on clean white wooden surface. Bright natural lighting, organized layout. NO TEXT, NO WORDS, NO LETTERS"
    },
    {
        "post_id": 32,
        "date": "14.05",
        "filename": "14may_checklist.png",
        "prompt": "Professional flat lay on rustic wooden table: infrared heat lamp, digital thermometer, plastic water drinker, round chick feeder with grain, wood shavings, small vitamin bottle, and clipboard. Items needed before baby chick arrival. Warm lighting, organized product layout. NO TEXT, NO WORDS, NO LETTERS"
    },
]


def generate_imagen(prompt: str, output_path: Path) -> bool:
    """Генерация через Imagen 4.0 Fast (Google AI, US прокси). ЕДИНСТВЕННЫЙ метод."""
    print(f"  🎨 Imagen 4.0 Fast через US прокси...")
    try:
        resp = requests.post(
            IMAGEN_URL,
            headers={"Content-Type": "application/json"},
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": "1:1",
                }
            },
            proxies={"http": US_PROXY, "https": US_PROXY},
            timeout=60,
        )

        if resp.status_code != 200:
            print(f"  ❌ HTTP {resp.status_code}: {resp.text[:200]}")
            return False

        data = resp.json()
        predictions = data.get("predictions", [])
        if not predictions:
            print(f"  ❌ Нет predictions: {json.dumps(data)[:200]}")
            return False

        b64_data = predictions[0].get("bytesBase64Encoded")
        if not b64_data:
            print(f"  ❌ Нет bytesBase64Encoded")
            return False

        img_bytes = base64.b64decode(b64_data)
        output_path.write_bytes(img_bytes)
        size_kb = len(img_bytes) / 1024
        print(f"  ✅ Сохранено: {output_path.name} ({size_kb:.0f} KB)")
        return True

    except Exception as e:
        print(f"  ❌ Imagen error: {e}")
        return False


def upload_photo_to_vk(image_path: Path) -> str:
    """Загружает фото на сервер ВК и возвращает attachment string."""
    # 1. Получаем URL для загрузки
    resp = requests.get(
        "https://api.vk.com/method/photos.getWallUploadServer",
        params={
            "group_id": GROUP_ID,
            "access_token": VK_USER_TOKEN,
            "v": "5.199",
        },
        timeout=15,
    )
    data = resp.json()
    if "error" in data:
        raise Exception(f"VK getWallUploadServer: {data['error']}")
    upload_url = data["response"]["upload_url"]

    # 2. Загружаем файл
    with open(image_path, "rb") as f:
        upload_resp = requests.post(
            upload_url,
            files={"photo": (image_path.name, f, "image/png")},
            timeout=60,
        )
    upload_data = upload_resp.json()

    # 3. Сохраняем фото
    save_resp = requests.get(
        "https://api.vk.com/method/photos.saveWallPhoto",
        params={
            "group_id": GROUP_ID,
            "photo": upload_data["photo"],
            "server": upload_data["server"],
            "hash": upload_data["hash"],
            "access_token": VK_USER_TOKEN,
            "v": "5.199",
        },
        timeout=15,
    )
    save_data = save_resp.json()
    if "error" in save_data:
        raise Exception(f"VK saveWallPhoto: {save_data['error']}")
    photo = save_data["response"][0]
    attachment = f"photo{photo['owner_id']}_{photo['id']}"
    print(f"  📤 VK фото: {attachment}")
    return attachment


def update_post_photo(post_id: int, attachment: str) -> bool:
    """Обновляет отложенный пост — заменяет фото."""
    resp = requests.get(
        "https://api.vk.com/method/wall.edit",
        params={
            "owner_id": f"-{GROUP_ID}",
            "post_id": post_id,
            "attachments": attachment,
            "access_token": VK_USER_TOKEN,
            "v": "5.199",
        },
        timeout=15,
    )
    data = resp.json()
    if "error" in data:
        print(f"  ❌ VK wall.edit: {data['error']}")
        return False
    if data.get("response", {}).get("post_id") or data.get("response") == 1:
        print(f"  ✅ Пост ID={post_id} обновлён!")
        return True
    print(f"  ⚠️ Неожиданный ответ: {data}")
    return False


def main():
    print(f"🖼 IMAGEN 4.0 — перегенерация фото для {len(TASKS)} постов ВезёмЦыплят")
    print(f"🔑 API Key: {GEMINI_API_KEY[:10]}...")
    print(f"🌐 Прокси: {US_PROXY.split('@')[1] if '@' in US_PROXY else US_PROXY}")
    print(f"📂 Сохранение: {OUT_DIR}")
    print()

    success = 0
    for i, task in enumerate(TASKS, 1):
        print(f"[{i}/{len(TASKS)}] Пост {task['date']} (ID={task['post_id']})")

        img_path = OUT_DIR / task["filename"]

        # 1. Генерируем фото через Imagen 4.0
        if not generate_imagen(task["prompt"], img_path):
            print(f"  ⚠️ Пропускаю пост {task['post_id']}")
            print()
            continue

        # 2. Загружаем в ВК
        try:
            attachment = upload_photo_to_vk(img_path)
        except Exception as e:
            print(f"  ❌ VK upload failed: {e}")
            print()
            continue

        # 3. Обновляем пост
        try:
            if update_post_photo(task["post_id"], attachment):
                success += 1
        except Exception as e:
            print(f"  ❌ VK edit failed: {e}")

        # Пауза (VK rate limit + Google quota)
        if i < len(TASKS):
            time.sleep(3)

        print()

    print(f"\n{'='*50}")
    print(f"✅ Обновлено: {success}/{len(TASKS)} постов")
    if success < len(TASKS):
        print(f"⚠️ Не обновлено: {len(TASKS) - success}")


if __name__ == "__main__":
    main()
