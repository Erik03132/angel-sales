#!/usr/bin/env python3
"""Публикация поста с фото через VPS (User Token привязан к VPS IP)."""

import os
import sys

import requests

# Конфигурация
USER_TOKEN = os.environ.get("VK_USER_TOKEN", "")
GROUP_TOKEN = os.environ.get("VK_VEZEMCYP_TOKEN", "")
GROUP_ID = os.environ.get("VK_GROUP_ID", "").lstrip("-")
PHOTO_PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/vezemcip_avatar.png"
TEXT = sys.argv[2] if len(sys.argv) > 2 else ""

if not TEXT:
    TEXT = """🐣 Проверка связи!

Группа «ВезёмЦыплят» запускается! 🎉

Мы — инкубатор «Азовский» из Крыма. Более 10 лет выводим и доставляем суточных цыплят по всему Югу России и до Москвы.

🐔 Бройлеры • 🥚 Несушки • 🦃 Индюки • 🦆 Утята • 🪿 Гусята

Скоро здесь:
✅ Актуальные прайсы и графики выводов
✅ Отзывы клиентов
✅ Гайды по выращиванию
✅ Акции и скидки для подписчиков

📞 Пишите в сообщения — ответим за 30 минут!
🌐 vezemcyp.ru

#ВезёмЦыплят #цыплята #бройлеры"""


def main():
    print("=" * 50)
    print("  📝 VK POST WITH PHOTO")
    print("=" * 50)

    if not USER_TOKEN:
        print("❌ VK_USER_TOKEN not set")
        sys.exit(1)
    if not GROUP_TOKEN:
        print("❌ VK_VEZEMCYP_TOKEN not set")
        sys.exit(1)

    print(f"  Photo: {PHOTO_PATH}")
    print(f"  Group: {GROUP_ID}")
    print()

    # 1. Get upload URL
    print("📸 Step 1: Getting upload URL...")
    r = requests.get("https://api.vk.com/method/photos.getWallUploadServer", params={
        "access_token": USER_TOKEN,
        "group_id": GROUP_ID,
        "v": "5.199"
    })
    data = r.json()
    if "error" in data:
        print(f"❌ Error: {data['error']['error_msg']}")
        sys.exit(1)
    upload_url = data["response"]["upload_url"]
    print("  ✅ Upload URL obtained")

    # 2. Upload photo
    print("📸 Step 2: Uploading photo...")
    with open(PHOTO_PATH, "rb") as f:
        r2 = requests.post(upload_url, files={"photo": f})
    upload_data = r2.json()
    print(f"  ✅ Photo uploaded (server={upload_data.get('server','')})")

    # 3. Save wall photo
    print("📸 Step 3: Saving wall photo...")
    r3 = requests.get("https://api.vk.com/method/photos.saveWallPhoto", params={
        "access_token": USER_TOKEN,
        "group_id": GROUP_ID,
        "photo": upload_data["photo"],
        "server": upload_data["server"],
        "hash": upload_data["hash"],
        "v": "5.199"
    })
    save_data = r3.json()
    if "error" in save_data:
        print(f"❌ Error: {save_data['error']['error_msg']}")
        sys.exit(1)
    p = save_data["response"][0]
    attachment = f"photo{p['owner_id']}_{p['id']}"
    print(f"  ✅ Attachment: {attachment}")

    # 4. Post with GROUP token
    print("📝 Step 4: Publishing post...")
    r4 = requests.get("https://api.vk.com/method/wall.post", params={
        "access_token": GROUP_TOKEN,
        "owner_id": f"-{GROUP_ID}",
        "from_group": 1,
        "message": TEXT,
        "attachments": attachment,
        "v": "5.199"
    })
    result = r4.json()
    if "error" in result:
        print(f"❌ Error: {result['error']['error_msg']}")
        sys.exit(1)

    post_id = result["response"]["post_id"]
    print(f"\n{'=' * 50}")
    print(f"  ✅ POST PUBLISHED! post_id={post_id}")
    print(f"  🔗 https://vk.com/wall-{GROUP_ID}_{post_id}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
