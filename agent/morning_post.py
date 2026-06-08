#!/usr/bin/env python3
"""
☀️ MORNING POST — Утренний генератор контента для Content Hub.

Генерирует пост + фото и отправляет превью в TG-бот с inline-кнопками.
Игорь решает: отправить / ещё / два поста.

Каналы:
  - «Своё Подворье»: TG @svoye_podvorye → VK → Дзен
  - «ВезёмЦыплят»:   TG (бот) → Сайт → VK → Дзен

Использование:
  python3 morning_post.py                    # Пост для Своё Подворье
  python3 morning_post.py --brand vezemcyp   # Пост для ВезёмЦыплят
  python3 morning_post.py --topic "бройлеры" # На конкретную тему
"""

import json
import os
import subprocess
import sys
from datetime import datetime

# --- Пути ---
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(AGENT_DIR)
sys.path.insert(0, AGENT_DIR)

# --- Загрузка .env ---
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

ENV = load_env()

# --- Конфиг брендов ---
BRANDS = {
    "podvorye": {
        "name": "Своё Подворье",
        "emoji": "🧑‍🌾",
        "tg_channel": ENV.get("TG_CHANNEL_ID", "@svoye_podvorye"),
        "dzen_bridge": ENV.get("DZEN_BRIDGE_CHANNEL_ID", "@podvorye_dzen"),
        "vk_group_id": ENV.get("VK_PODVORYE_GROUP_ID", ""),
        "vk_token": ENV.get("VK_PODVORYE_TOKEN", ""),
        "platforms": ["tg", "vk", "dzen", "ok", "site"],
        "generator": "tikhon",
    },
    "vezemcyp": {
        "name": "ВезёмЦыплят",
        "emoji": "🐣",
        "tg_channel": None,  # через бот лично Игорю, не в канал
        "dzen_bridge": ENV.get("DZEN_BRIDGE_CHANNEL_ID", "@podvorye_dzen"),  # TODO: отдельный канал?
        "vk_group_id": ENV.get("VK_VEZEMCYP_GROUP_ID", ""),
        "vk_token": ENV.get("VK_VEZEMCYP_TOKEN", ""),
        "platforms": ["tg", "site", "vk", "dzen"],
        "generator": "vezemcyp",
    },
}

# --- Буфер для pending постов ---
PENDING_DIR = os.path.join(BASE_DIR, "data", "pending_posts")
os.makedirs(PENDING_DIR, exist_ok=True)


def generate_post_text(brand_key: str, topic: str = None) -> dict | None:
    """Генерирует текст поста через Тихона/коммерческий генератор."""
    brand = BRANDS[brand_key]

    if brand["generator"] == "tikhon":
        from tikhon_content_gen import generate_posts
        from tikhon_content_gen import load_env as tikhon_load_env
        env = tikhon_load_env()
        posts = generate_posts(count=1, topic=topic, env=env)
        if posts:
            return posts[0]
    elif brand["generator"] == "vezemcyp":
        # Коммерческий контент для ВезёмЦыплят
        from tikhon_content_gen import call_gemini
        from tikhon_content_gen import load_env as tikhon_load_env
        env = tikhon_load_env()

        now = datetime.now()
        prompt = f"""Ты — SMM-менеджер компании «ВезёмЦыплят» (vezemcip.ru).
Компания продаёт суточных цыплят, индюшат, утят, гусят с доставкой по всей России.

Напиши ОДИН пост для социальных сетей:
- Формат: эмодзи + заголовок, текст 200-400 символов, призыв к действию
- Стиль: дружелюбный, профессиональный, с заботой о клиенте
- Сезон: {now.strftime('%B %Y')}
- Тема: {topic or 'актуальное предложение по цыплятам или акции'}
- В конце: ссылка vezemcip.ru и телефон 8-800-...
- Хэштеги: #ВезёмЦыплят #цыплята #птицеводство (3-5 штук)

НЕ используй шаблонные фразы типа «Друзья!», «Внимание!», «Спешите!»."""

        text = call_gemini(prompt, env)
        if text:
            import re
            text = re.sub(r'^```\w*\n?', '', text.strip())
            text = re.sub(r'\n?```$', '', text).strip()
            return {
                "index": 1,
                "rubric": "Коммерческий",
                "emoji": "🐣",
                "text": text,
                "generated_at": now.isoformat(),
            }

    return None


def generate_photo(post_text: str, brand_key: str) -> str | None:
    """Генерирует/находит фото для поста. Возвращает путь к файлу."""
    env = load_env()

    # Извлекаем тему из текста поста
    import re
    first_line = post_text.split("\n")[0][:120] if post_text else ""
    clean = re.sub(r'[^\w\sа-яёА-ЯЁ]', '', first_line).strip()

    # Переводим тему в английский промпт для Leonardo (слово целиком, не подстрока!)
    import re as _re
    topic_keywords = {
        r"\bперц\w*": "bell peppers growing in garden bed",
        r"\bогур\w*": "cucumbers growing in open ground garden bed",
        r"\bпомидор\w*": "tomatoes growing in greenhouse",
        r"\bтомат\w*": "tomatoes growing in greenhouse",
        r"\bкуриц\w*": "chickens on free range farm",
        r"\bцыплят\w*": "baby chicks brooder chicken coop",
        r"\bбройлер\w*": "broiler chickens poultry farm",
        r"\bиндюк\w*": "turkey poultry farming",
        r"\bутк\w*": "ducks on pond farm",
        r"\bгус\w*": "geese on farm pond",
        r"\bкоз\w*": "goats on pasture farm animals",
        r"\bкролик\w*": "rabbits in wooden hutch farm",
        r"\bпчел\w*": "beehives bees in apiary garden",
        r"\bсад\b": "fruit garden orchard spring summer",
        r"\bгрядк\w*": "raised garden beds vegetable garden",
        r"\bрассад\w*": "seedlings in greenhouse gardening",
        r"\bтеплиц\w*": "polycarbonate greenhouse vegetable growing",
        r"\bяйц\w*": "chicken eggs nest basket poultry",
        r"\bкорм\w*": "chicken feed grain poultry feeding",
        r"\bкурятник\w*": "chicken coop interior poultry house",
        r"\bпород\w*": "farm animals livestock variety",
        r"\bинкубатор\w*": "incubator with chicken eggs hatching, close-up view",
        r"\bовоскоп\w*": "eggs candling inspection chicken farm",
        r"\bнаседк\w*": "hen sitting on eggs in nest",
        r"\bвылуп\w*": "baby chick hatching from egg shell, close-up",
        r"\bсуточн\w*": "day old baby chicks in brooder under heat lamp",
    }
    prompt_en = "russian countryside farm rural homestead, slavic village, central Russia, wooden house, birch trees, no american style, no cowboy"
    for pattern, en_prompt in topic_keywords.items():
        if _re.search(pattern, clean.lower()):
            prompt_en = en_prompt
            break

    print(f"📸 Генерация фото, тема: {clean[:60]} → {prompt_en}")

    # Каскад: Leonardo.ai → FAL Flux → стоки
    leo_key = env.get("LEONARDO_API_KEY", "")
    if leo_key:
        from photo_cascade import generate_leonardo
        path = generate_leonardo(prompt_en, leo_key)
        if path:
            return path

    # FAL Flux — лучшее качество за $0.003
    fal_key = env.get("FAL_KEY", "")
    if fal_key:
        from photo_cascade import generate_fal_flux
        url = generate_fal_flux(prompt_en, fal_key)
        if url:
            from photo_cascade import download_photo
            path = download_photo(url)
            if path:
                return path

    # Стоки: Unsplash → Pexels → Pixabay
    from photo_cascade import (
        download_photo,
        fetch_pexels,
        fetch_pixabay,
        fetch_unsplash,
    )
    for fetcher, key_name in [
        (fetch_unsplash, "UNSPLASH_ACCESS_KEY"),
        (fetch_pexels, "PEXELS_API_KEY"),
        (fetch_pixabay, "PIXABAY_API_KEY"),
    ]:
        api_key = env.get(key_name, "")
        if api_key:
            url = fetcher(prompt_en, api_key)
            if url:
                path = download_photo(url)
                if path:
                    return path

    print("⚠️ Фото не сгенерировано — пост пойдёт без картинки")
    return None


def save_pending(brand_key: str, post_data: dict, photo_path: str | None) -> str:
    """Сохраняет пост в буфер pending_posts/. Возвращает ID поста."""
    post_id = f"{brand_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Копируем фото в стабильное место
    stable_photo = None
    if photo_path and os.path.exists(photo_path):
        stable_photo = os.path.join(PENDING_DIR, f"{post_id}.jpg")
        import shutil
        shutil.copy2(photo_path, stable_photo)
        # Верифицируем копию
        if not os.path.exists(stable_photo):
            print("   ⚠️ Копия фото не создана — ошибка записи")
            stable_photo = None
        else:
            print(f"   💾 Фото скопировано: {os.path.getsize(stable_photo)//1024}KB")
        # Удаляем временный файл
        try:
            os.unlink(photo_path)
        except Exception:
            pass

    pending = {
        "id": post_id,
        "brand": brand_key,
        "brand_name": BRANDS[brand_key]["name"],
        "platforms": BRANDS[brand_key]["platforms"],
        "post": post_data,
        "photo_path": stable_photo,
        "created_at": datetime.now().isoformat(),
        "status": "pending",
    }

    filepath = os.path.join(PENDING_DIR, f"{post_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

    print(f"💾 Сохранён в буфер: {filepath}")
    return post_id


def send_preview_to_admin(post_id: str) -> bool:
    """Отправляет превью поста админу (Игорю) в TG-бот с inline-кнопками."""

    filepath = os.path.join(PENDING_DIR, f"{post_id}.json")
    with open(filepath, "r", encoding="utf-8") as f:
        pending = json.load(f)

    brand = BRANDS[pending["brand"]]
    post = pending["post"]
    photo_path = pending.get("photo_path")

    # Формируем текст превью (первая строка — ЗАГЛАВНЫМИ)
    post_text = post['text']
    first_newline = post_text.find('\n')
    if first_newline > 0:
        post_text = post_text[:first_newline].upper() + post_text[first_newline:]

    platforms_str = " → ".join(pending["platforms"]).upper()
    caption = (
        f"{brand['emoji']} <b>{brand['name']}</b> | {post.get('rubric', '')}\n"
        f"📡 {platforms_str}\n"
        f"{'─' * 30}\n\n"
        f"{post_text}\n\n"
        f"{'─' * 30}\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    # Inline-кнопки
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Отправить", "callback_data": f"content_approve:{post_id}"},
                {"text": "🔄 Ещё", "callback_data": f"content_more:{post_id}"},
            ],
            [
                {"text": "📡 Только TG", "callback_data": f"content_only:tg:{post_id}"},
                {"text": "📡 Только Дзен", "callback_data": f"content_only:dzen:{post_id}"},
            ],
            [
                {"text": "📡 Только VK", "callback_data": f"content_only:vk:{post_id}"},
            ],
            [
                {"text": "🗑 Удалить", "callback_data": f"content_delete:{post_id}"},
            ],
        ]
    }

    bot_token = ENV.get("ANGELOCHKA_BOT_TOKEN", "")
    admin_id = "176203333"

    if not bot_token:
        print("❌ ANGELOCHKA_BOT_TOKEN не найден!")
        return False

    # ⚠️ api.telegram.org не резолвится через штатный DNS в РФ — используем --resolve + --proxy
    PROXY = os.getenv("TELEGRAM_PROXY") or ENV.get("TELEGRAM_PROXY", "")
    PROXY_FLAG = ["--proxy", PROXY] if PROXY else []
    RESOLVE = ["--resolve", "api.telegram.org:443:149.154.167.220"]
    BASE = f"https://api.telegram.org/bot{bot_token}"

    try:
        if photo_path and os.path.exists(photo_path):
            cmd = [
                "curl", "-s", "--max-time", "30",
                *RESOLVE,
                *PROXY_FLAG,
                "-F", f"chat_id={admin_id}",
                "-F", f"photo=@{photo_path}",
                "-F", f"caption=📸 {brand['emoji']} {post.get('text','')[:80]}...",
                f"{BASE}/sendPhoto",
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=40)
            d = json.loads(r.stdout)
            if d.get("ok"):
                print("  ✅ Фото отправлено")
            else:
                print(f"  ⚠️ TG sendPhoto: {d.get('description', 'unknown')}")

        body = json.dumps({
            "chat_id": admin_id,
            "text": caption,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }, ensure_ascii=False)

        cmd = [
            "curl", "-s", "--max-time", "15",
            *RESOLVE,
            *PROXY_FLAG,
            "-H", "Content-Type: application/json",
            "-d", body,
            f"{BASE}/sendMessage",
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=20)
        d = json.loads(r.stdout)
        if d.get("ok"):
            print("📱 Текст + кнопки отправлены")
            return True
        else:
            print(f"❌ TG sendMessage: {d.get('description', 'unknown')}")
            return False

    except Exception as e:
        print(f"❌ Ошибка отправки превью: {e}")
        return False


def is_valid_ok_post(post_text: str) -> bool:
    """
    Проверяет, является ли пост классическим (не ТЗ на видео/медиа).
    
    Исключает:
    - ТЗ для видео (VK Clip, Reels, Shorts)
    - ТЗ для фото/картинок
    - Сценарии для съёмки
    - Технические задания для дизайнера
    """
    # Маркеры не-постов
    invalid_markers = [
        "📹 ТЗ ДЛЯ ВИДЕО",
        "ТЗ ДЛЯ ВИДЕО",
        "VK Clip",
        "Reels",
        "Shorts",
        "Сценарий:",
        "1.", "2.", "3.", "4.", "5.",  # Нумерация шагов сценария
        "ТЗ ДЛЯ ФОТО",
        "ТЗ ДЛЯ ДИЗАЙНЕРА",
        "КАДР 1",
        "КАДР 2",
        "КАДР 3",
        "🎥 СЦЕНАРИЙ",
        "ВИДЕОРОЛИК",
        "СЪЁМКА",
        "ТЕМА ДЛЯ КЛИПА",
        "ДЛЯ КЛИПА",
        "🎥",
    ]
    
    first_lines = post_text.split('\n')[:5]  # Проверяем первые 5 строк
    
    for line in first_lines:
        line_upper = line.upper().strip()
        for marker in invalid_markers:
            if marker.upper() in line_upper:
                return False
    
    return True


def load_ok_post(date_str: str) -> dict | None:
    """
    Проверяет папку /ok/ на наличие готового поста на дату.
    Если есть — возвращает текст и фото.
    
    Формат папок: /ok/YYYY-MM-DD_XX/ (XX = 01..05)
    """
    import glob
    
    # Папка /ok/ лежит в корне проекта: /Users/igorvasin/freelance-2026/ok/
    ok_base = "/Users/igorvasin/freelance-2026/ok"
    
    if not os.path.exists(ok_base):
        return None
    
    # Ищем папки на сегодня: 2026-05-16_01, 2026-05-16_02, ...
    pattern = os.path.join(ok_base, f"{date_str}_*")
    folders = sorted(glob.glob(pattern))
    
    if not folders:
        return None
    
    # Ищем первую VALID папку (не ТЗ на видео)
    for folder in folders:
        post_file = os.path.join(folder, "post.txt")
        photo_file = os.path.join(folder, "photo.png")
        
        folder_name = os.path.basename(folder)
        
        if os.path.exists(post_file):
            with open(post_file, "r", encoding="utf-8") as f:
                post_text = f.read()

            # Проверяем, что это классический пост (не ТЗ)
            if not is_valid_ok_post(post_text):
                print(f"   ⏭️ Пропущено (ТЗ): {folder_name}")
                continue

            photo_path = photo_file if os.path.exists(photo_file) else None
            
            # Если фото нет — генерируем через каскад (начало: Leonardo AI)
            if not photo_path:
                print("   ⚠️ Фото не найдено — генерируем...")
                photo_path = generate_photo(post_text, "podvorye")
                
                # Сохраняем в папку ОК
                if photo_path:
                    import shutil
                    ok_photo = os.path.join(folder, "photo.png")
                    shutil.copy2(photo_path, ok_photo)
                    print(f"   💾 Сохранено в /ok/{folder_name}/photo.png")
                else:
                    print("   ⚠️ Фото не сгенерировано — пост без картинки")

            print(f"✅ Найдено в ОК: {folder_name}")
            return {
                "text": post_text,
                "photo_path": photo_path,
                "folder": folder_name,
            }
    
    return None


def mark_ok_published(folder_name: str):
    """Помечает пост как опубликованный (просто лог)"""
    print(f"   📝 {folder_name} → опубликовано")


def _load_content_plan(brand_key: str = "podvorye") -> str | None:
    """Читает контент-план и возвращает тему на сегодня."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    month = datetime.now().month
    plan_files = {
        5: "month1_content_plan.md",   # май
        6: "month2_content_plan.md",   # июнь
    }
    plan_file = plan_files.get(month, "month1_content_plan.md")
    plan_path = os.path.join(base, "vk_content", brand_key, plan_file)
    if not os.path.exists(plan_path):
        plan_path = os.path.join(base, "vk_content", brand_key, "month1_content_plan.md")
    if not os.path.exists(plan_path):
        return None

    today = datetime.now().strftime("%d.%m")
    with open(plan_path) as f:
        for line in f:
            line = line.strip()
            if today in line and "—" in line and line.startswith("###"):
                topic = line.split("—", 1)[-1].strip()
                topic = topic.strip("«»\"'")
                print(f"   📅 Контент-план → {topic}")
                return topic
    return None


def morning_generate(brand_key: str = "podvorye", topic: str = None) -> str | None:
    """Полный цикл: проверка ОК → генерация → фото → сохранение → превью.
    Возвращает post_id или None.
    """
    brand = BRANDS.get(brand_key)
    if not brand:
        print(f"❌ Бренд '{brand_key}' не найден. Доступно: {list(BRANDS.keys())}")
        return None

    print(f"\n{'=' * 55}")
    print(f"  ☀️ MORNING POST — {brand['name']}")
    print(f"{'=' * 55}\n")

    today = datetime.now().strftime("%Y-%m-%d")

    # 1. ПРОВЕРКА ПАПКИ /ok/ — приоритет готовому контенту
    print("🔍 Проверка папки /ok/ на готовые посты...")
    ok_data = load_ok_post(today)
    
    if ok_data:
        # ✅ Берём готовое из ОК
        print(f"   ✅ Найдено: {ok_data['folder']}")
        post = {
            "text": ok_data["text"],
            "rubric": "Из ОК (готовое)",
            "emoji": brand["emoji"],
            "generated_at": datetime.now().isoformat(),
        }
        photo_path = ok_data["photo_path"]
    else:
        # ❌ Генерируем новое
        print("   ⚠️ Не найдено — генерируем новое...")

        # Берём тему из контент-плана, если не задана явно
        if not topic:
            topic = _load_content_plan(brand_key)
        
        print("📝 Генерация текста...")
        post = generate_post_text(brand_key, topic)
        if not post:
            print("❌ Не удалось сгенерировать пост")
            return None
        print(f"   ✅ {post['text'][:80]}...")

        print("\n📸 Генерация фото...")
        photo_path = generate_photo(post["text"], brand_key)
        if photo_path:
            print(f"   ✅ Фото: {photo_path}")
        else:
            print("   ⚠️ Без фото")

    # 2. Сохранение в буфер
    post_id = save_pending(brand_key, post, photo_path)

    # 3. Отправка превью
    print("\n📱 Отправка превью в Telegram...")
    ok = send_preview_to_admin(post_id)

    if ok:
        print(f"\n{'=' * 55}")
        print(f"  ✅ Пост готов к модерации (ID: {post_id})")
        print("  📱 Проверь Telegram — там превью с кнопками")
        print(f"{'=' * 55}\n")
        
        # Если взяли из ОК — помечаем как опубликованное
        if ok_data:
            mark_ok_published(ok_data["folder"])
            print(f"   📝 {ok_data['folder']} отмечен как опубликованный")
    else:
        print(f"\n⚠️ Превью не отправлено, но пост сохранён: {post_id}")

    return post_id


# --- CLI ---
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="☀️ Morning Post — утренний генератор контента")
    parser.add_argument("--brand", "-b", default="podvorye",
                        choices=list(BRANDS.keys()),
                        help="Бренд: podvorye или vezemcyp")
    parser.add_argument("--topic", "-t", type=str, help="Конкретная тема")
    args = parser.parse_args()

    morning_generate(brand_key=args.brand, topic=args.topic)
