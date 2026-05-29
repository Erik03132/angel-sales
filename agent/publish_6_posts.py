#!/usr/bin/env python3
"""
🚀 Публикация 6 постов (3 ВезёмЦыплят + 3 Своё Подворье) с фото через Imagen 4.0.
"""

import base64
import json
import os
import subprocess
import sys
import time

import requests

# ═══════════════════════════════════════
# Загрузка .env
# ═══════════════════════════════════════
env = {}
with open("/Users/igorvasin/freelance-2026/ai-eggs/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()

USER_TOKEN = env.get("VK_USER_TOKEN", "")
GEMINI_KEY = env.get("GEMINI_API_KEY", "")
PROXY = env.get("TELEGRAM_PROXY", "")

GROUPS = {
    "vezemcyp": {
        "id": env.get("VK_GROUP_ID", "").lstrip("-"),
        "token": env.get("VK_VEZEMCYP_TOKEN", ""),
        "name": "ВезёмЦыплят",
    },
    "podvorye": {
        "id": env.get("VK_PODVORYE_GROUP_ID", "").lstrip("-"),
        "token": env.get("VK_PODVORYE_TOKEN", ""),
        "name": "Своё Подворье",
    },
}

# ═══════════════════════════════════════
# 6 ПОСТОВ
# ═══════════════════════════════════════

POSTS = [
    # --- ВезёмЦыплят: 3 поста ---
    {
        "group": "vezemcyp",
        "text": """🐣 Добро пожаловать в «ВезёмЦыплят»!

Мы — сервис прямых поставок здорового молодняка птицы от ведущих инкубаторов России.

Что мы делаем:
🚚 Доставляем суточных цыплят, утят, индюшат и гусят прямо к вашему порогу
🏆 Работаем только с проверенными инкубаторами — качество гарантировано
📋 Каждая партия — с ветеринарным свидетельством

Наш ассортимент:
🐔 Бройлеры — КОББ-500, РОСС-308
🥚 Несушки — Ломан Браун, Хайсекс, Доминант
🦃 Индюки — БИГ-6
🦆 Утята — Мулард, Черри Велли
🪿 Гусята — Линда

📍 Работаем в Южном и Центральном федеральных округах:
Краснодар • Ростов • Крым • Ставрополье • Москва и МО

✅ Качество • ✅ Своевременная доставка • ✅ Честные цены

📞 Заказать — пишите в сообщения!
🌐 vezemcyp.ru

#ВезёмЦыплят #цыплята #доставкацыплят #бройлеры #молоднякптицы""",
        "photo_prompt": "Professional photo of adorable fluffy yellow baby chicks on green grass, warm golden sunlight, farm background with green fields, cheerful atmosphere. No text, no words, no letters, no watermarks.",
        "aspect": "16:9",
    },
    {
        "group": "vezemcyp",
        "text": """💰 ПРАЙС-ЛИСТ — МАЙ 2026

Актуальные цены на суточный молодняк с доставкой:

🐔 БРОЙЛЕРЫ:
▫️ КОББ-500 — от 75 ₽/гол
▫️ РОСС-308 — от 70 ₽/гол
▫️ Цветной бройлер — от 120 ₽/гол

🥚 НЕСУШКИ:
▫️ Ломан Браун — от 100 ₽/гол
▫️ Хайсекс Браун — от 110 ₽/гол
▫️ Доминант — от 130 ₽/гол

🦃 ИНДЮКИ:
▫️ БИГ-6 — от 350 ₽/гол

🦆 УТЯТА:
▫️ Мулард — от 180 ₽/гол
▫️ Черри Велли — от 150 ₽/гол

🪿 ГУСЯТА:
▫️ Линда — от 250 ₽/гол

📦 Минимальный заказ: от 30 голов
🚚 Доставка: бесплатно от 100 голов (Юг РФ)

⚡ Цены действительны при заказе до 15 мая
📞 Оформить заказ → пишите в сообщения!

#ВезёмЦыплят #цыплятацена #бройлерыцена #прайс #несушки""",
        "photo_prompt": "Cute fluffy yellow baby chicks in a clean wooden box with straw, warm sunlight, farm setting, professional product photography. No text, no words, no letters.",
        "aspect": "16:9",
    },
    {
        "group": "vezemcyp",
        "text": """🚚 КАК МЫ ДОСТАВЛЯЕМ ЦЫПЛЯТ

Главный вопрос: «Как суточные цыплята переносят дорогу?»

Отвечаем — отлично! Вот почему:

🌡 Специальный транспорт:
▫️ Обогрев кузова 30-32°C — как в инкубаторе
▫️ Вентиляция — свежий воздух без сквозняков
▫️ Коробки с подстилкой — мягко и тепло

⏱ Скорость:
▫️ Крым — 1-2 дня
▫️ Краснодар, Ростов — 2-3 дня
▫️ Москва и МО — 3-5 дней
▫️ Цыплята отправляются в ДЕНЬ ВЫЛУПЛЕНИЯ

📋 Гарантии:
▫️ Ветеринарное свидетельство на каждую партию
▫️ Замена при падеже в первые 48 часов (при соблюдении условий)
▫️ Консультация по приёму и пропойке — бесплатно

📍 Более 200 успешных доставок за 2025 год!

📞 Узнать ближайшую дату доставки → пишите в сообщения!
🌐 vezemcyp.ru

#ВезёмЦыплят #доставкацыплят #суточныецыплята #купитьцыплят""",
        "photo_prompt": "A delivery truck van on a rural road with green fields and blue sky, warm sunrise lighting, professional transport photography. No text, no words, no letters.",
        "aspect": "16:9",
    },

    # --- Своё Подворье: 3 поста ---
    {
        "group": "podvorye",
        "text": """🐔 КОББ-500 vs РОСС-308: честный разбор для тех, кто выбирает первых бройлеров

Если вы впервые берёте бройлеров — скорее всего, уже запутались в советах. Разбираемся на цифрах.

📊 СРАВНЕНИЕ:

▪️ Набор массы
Кобб-500 — к 42 дню: 2,5–2,8 кг. Грудка мощная, тушка «жёлтая».
Росс-308 — к 42 дню: 2,3–2,6 кг. Набирает стабильно и равномерно.

▪️ Конверсия корма
Кобб-500: ~1,7 кг корма на 1 кг привеса (лучший в отрасли)
Росс-308: ~1,8 кг на 1 кг привеса

▪️ Выживаемость
Росс-308 — устойчивее к перепадам и ошибкам новичков.
Кобб-500 — требовательнее к микроклимату.

🏁 ВЕРДИКТ:
🟢 Кобб-500 — если есть опыт и хороший брудер
🟡 Росс-308 — если первый раз и хотите меньше риска
🔵 Идеал — взять 50/50 и сравнить на своём подворье!

💬 А вы каких бройлеров держите? Пишите в комментариях!

#СвоёПодворье #бройлеры #Кобб500 #Росс308 #птицеводство""",
        "photo_prompt": "White broiler chickens on a farm, healthy big chickens in a clean coop with straw, natural lighting, rural farming scene. No text, no words, no letters.",
        "aspect": "16:9",
    },
    {
        "group": "podvorye",
        "text": """🥕 ЧТО ПОСАДИТЬ В МАЕ НА ЮГЕ РОССИИ

Май — золотое окно посадки. Земля прогрелась, заморозков уже нет. Вот что гарантированно даст урожай:

🟢 СЕЙЧАС (начало мая):
1. Помидоры (рассада) — в грунт после 5 мая
2. Перец — вместе с томатами
3. Огурцы — прямо в грядку, под плёнку на ночь
4. Кабачки — 3-4 куста хватит на семью
5. Фасоль — без ухода, обогащает почву
6. Кукуруза — сажать блоками 4×4

🟡 СЕРЕДИНА МАЯ:
7. Морковь (второй посев) — самая сладкая
8. Свёкла — любит тепло
9. Тыква — 2-3 семечка на семью
10. Арбузы и дыни — на Юге успевают из семян

🔵 КОНЕЦ МАЯ:
11. Базилик — к шашлыку!
12. Подсолнечник — красиво + семечки

⚡ ЛАЙФХАК: Мульчируйте соломой из курятника — двойная польза! Куриный помёт — лучшее удобрение, но ТОЛЬКО перепревший.

💬 Что уже посадили? Делитесь!

#СвоёПодворье #огород #дача #посадки #май2026""",
        "photo_prompt": "Beautiful vegetable garden in spring, seedlings growing in neat rows, tomatoes peppers cucumbers, warm sunlight, rural Russian countryside. No text, no words, no letters.",
        "aspect": "16:9",
    },
    {
        "group": "podvorye",
        "text": """🏡 Добро пожаловать в «Своё Подворье»!

Здесь собираются те, кто живёт на земле — или мечтает об этом.

Мы — сообщество фермеров, дачников и птицеводов Юга России. Делимся опытом, помогаем советами и поддерживаем друг друга.

О чём пишем:
🐔 Птицеводство — от суточных цыплят до первого яйца
🥕 Огород и сад — что сажать, чем кормить, когда собирать
🏠 Подворье — обустройство, инструменты, лайфхаки
💬 Живые обсуждения — ваш опыт ценнее любого учебника

Кому будет полезно:
✅ Фермерам и владельцам ЛПХ
✅ Дачникам и огородникам
✅ Тем, кто только планирует переехать на землю

📢 Подписывайтесь — будем расти вместе!
💬 Расскажите в комментариях: что у вас на подворье?

#СвоёПодворье #фермер #деревня #дача #подворье #птицеводство""",
        "photo_prompt": "Charming rural Russian farmstead with a wooden house, vegetable garden, free-range chickens walking on green grass, sunflowers, warm golden hour light. No text, no words, no letters.",
        "aspect": "16:9",
    },
]


# ═══════════════════════════════════════
# Генерация фото через Imagen 4.0
# ═══════════════════════════════════════

def generate_photo(prompt, aspect="16:9"):
    """Генерация через Imagen 4.0 + US SOCKS5 прокси."""
    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": aspect}
    })
    cmd = [
        "curl", "-s", "--max-time", "30", "--connect-timeout", "10",
        "--proxy", PROXY,
        "-H", "Content-Type: application/json",
        "-d", body,
        f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict?key={GEMINI_KEY}"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=40)
        data = json.loads(result.stdout)
        if "predictions" in data:
            img_b64 = data["predictions"][0]["bytesBase64Encoded"]
            return base64.b64decode(img_b64)
        else:
            print(f"  ⚠️ Imagen error: {json.dumps(data)[:200]}")
    except Exception as e:
        print(f"  ⚠️ Imagen exception: {e}")
    return None


def upload_photo_vk(photo_bytes, group_id):
    """Загрузка фото в VK через User Token."""
    # 1. Get upload URL
    r = requests.get("https://api.vk.com/method/photos.getWallUploadServer", params={
        "access_token": USER_TOKEN, "group_id": group_id, "v": "5.199"
    })
    d = r.json()
    if "error" in d:
        print(f"  ❌ Upload URL: {d['error']['error_msg']}")
        return None
    upload_url = d["response"]["upload_url"]

    # 2. Upload
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(photo_bytes)
        tmp_path = f.name

    with open(tmp_path, "rb") as f:
        r2 = requests.post(upload_url, files={"photo": f})
    ud = r2.json()
    os.unlink(tmp_path)

    # 3. Save
    r3 = requests.get("https://api.vk.com/method/photos.saveWallPhoto", params={
        "access_token": USER_TOKEN, "group_id": group_id,
        "photo": ud["photo"], "server": ud["server"], "hash": ud["hash"], "v": "5.199"
    })
    sd = r3.json()
    if "error" in sd:
        print(f"  ❌ Save: {sd['error']['error_msg']}")
        return None
    p = sd["response"][0]
    return f"photo{p['owner_id']}_{p['id']}"


def publish_post(group_token, group_id, text, attachment=None):
    """Публикация поста через Community Token."""
    params = {
        "access_token": group_token,
        "owner_id": f"-{group_id}",
        "from_group": 1,
        "message": text,
        "v": "5.199",
    }
    if attachment:
        params["attachments"] = attachment

    r = requests.get("https://api.vk.com/method/wall.post", params=params)
    d = r.json()
    if "error" in d:
        print(f"  ❌ Post: {d['error']['error_msg']}")
        return None
    return d["response"]["post_id"]


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

def main():
    print("=" * 60)
    print("  🚀 ПУБЛИКАЦИЯ 6 ПОСТОВ С ФОТО")
    print("=" * 60)

    if not USER_TOKEN:
        print("❌ VK_USER_TOKEN не найден!")
        sys.exit(1)

    results = []

    for i, post in enumerate(POSTS):
        group = GROUPS[post["group"]]
        print(f"\n{'─' * 50}")
        print(f"  [{i+1}/6] {group['name']} | {post['text'][:50]}...")
        print(f"{'─' * 50}")

        # 1. Генерация фото
        print("  📸 Генерация фото...")
        photo_bytes = generate_photo(post["photo_prompt"], post.get("aspect", "16:9"))

        attachment = None
        if photo_bytes:
            print(f"  ✅ Фото сгенерировано ({len(photo_bytes)//1024} KB)")
            # 2. Загрузка в VK
            print("  📤 Загрузка в VK...")
            attachment = upload_photo_vk(photo_bytes, group["id"])
            if attachment:
                print(f"  ✅ {attachment}")
            else:
                print("  ⚠️ Фото не загрузилось, публикую без фото")
        else:
            print("  ⚠️ Фото не сгенерировалось, публикую без фото")

        # 3. Публикация
        print("  📝 Публикация...")
        post_id = publish_post(group["token"], group["id"], post["text"], attachment)

        if post_id:
            url = f"https://vk.com/wall-{group['id']}_{post_id}"
            print(f"  ✅ ОПУБЛИКОВАНО! {url}")
            results.append({"group": group["name"], "post_id": post_id, "url": url, "photo": bool(attachment)})
        else:
            print("  ❌ Не опубликовано")
            results.append({"group": group["name"], "post_id": None, "url": None, "photo": False})

        # Пауза между постами (VK rate limit)
        if i < len(POSTS) - 1:
            print("  ⏳ Пауза 5 сек...")
            time.sleep(5)

    # Итоги
    print(f"\n{'=' * 60}")
    print("  📊 ИТОГИ")
    print(f"{'=' * 60}")
    ok = sum(1 for r in results if r["post_id"])
    photo_ok = sum(1 for r in results if r["photo"])
    print(f"  Опубликовано: {ok}/6")
    print(f"  С фото: {photo_ok}/6")
    for r in results:
        status = "✅" if r["post_id"] else "❌"
        photo = "📸" if r["photo"] else "📝"
        print(f"  {status} {photo} {r['group']}: {r.get('url', 'FAIL')}")
    print()


if __name__ == "__main__":
    main()
