#!/usr/bin/env python3
"""
price_updater.py — Живой прайс-лист Заботкиной
================================================
Парсит свежие посты из всех источников и обновляет config/prices.json

Источники (по приоритету актуальности):
  1. VK группа — свежие посты с ценами
  2. Telegram канал — свежие посты с ценами
  3. incubird.ru — страницы каталога (запасной, меняется редко)

Запуск:
  python3 price_updater.py              # полное обновление
  python3 price_updater.py --dry-run   # показать что нашёл, не сохранять
  python3 price_updater.py --source vk # только VK

Cron на VPS (каждые 3 дня в 08:00):
  0 8 */3 * * cd /root/antigravity/ai-eggs && python3 agent/price_updater.py >> logs/price_updater.log 2>&1
"""

import argparse
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ─── Пути ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config" / "prices.json"
LOG_PATH = ROOT / "agent" / "logs" / "price_updater.log"

# ─── Логирование ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("price_updater")

# ─── ENV ─────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

VK_TOKEN   = os.getenv("VK_SERVICE_TOKEN")   # сервисный токен VK
VK_OWNER_ID = os.getenv("VK_INCUBIRD_GROUP_ID", "-162359356")  # vk.com/incubird
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHANNEL   = os.getenv("TG_PRICE_CHANNEL", "@AzovskyIncubator")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# VK API и incubird.ru — российские сайты, не работают через US SOCKS-прокси.
# ВАЖНО: proxies={None} не переопределяет env-переменные HTTPS_PROXY!
# Единственный надёжный способ — Session(trust_env=False).
def _ru_session() -> requests.Session:
    """Session без прокси — для российских сайтов (VK, incubird.ru)."""
    s = requests.Session()
    s.trust_env = False  # игнорирует HTTP_PROXY / HTTPS_PROXY из env
    return s

# ─── LLM — извлечение цен из текста поста ────────────────────────────────────

PRICE_EXTRACT_PROMPT = """Ты извлекаешь прайс-лист из поста инкубатора.
Найди ВСЕ цены на птицу. Верни ТОЛЬКО JSON-массив объектов:
[
  {{"name": "Кобб-500", "category": "broilers", "price": 90, "price_from": 20}},
  {{"name": "Ломан Браун", "category": "layers", "price": 60}}
]

Категории: broilers (бройлеры), meat_egg (мясояичные), layers (несушки),
           turkeys (индюшата), ducks (утята), geese (гусята), guinea_fowl (цесарки)

Если цена зависит от объёма — добавь "price_from": <минимальное кол-во>.
Если цен нет — верни пустой массив [].

ТЕКСТ ПОСТА:
{text}
"""


# Породы → категории (для шага 3 в _detect_category)
BREED_MAP = {
    "кобб": "broilers", "росс": "broilers", "r500": "broilers", "р500": "broilers",
    "биг-6": "turkeys", "биг6": "turkeys", "индюш": "turkeys",
    "мулард": "ducks", "утят": "ducks",
    "гусят": "geese",
    "цесар": "guinea_fowl",
    "ломан": "layers", "хайсекс": "layers", "фокси": "layers", "несуш": "layers",
    "бройлер": "broilers",
}

# Метки страниц сайта → категория
SITE_LABEL_MAP = {
    "chickens": "broilers", "turkeys": "turkeys", "ducks": "ducks",
    "geese": "geese", "guinea_fowl": "guinea_fowl",
}

# Категорийные слова (обновляют ВСЕ позиции в категории)
CATEGORY_LABELS = {
    "утята": "ducks", "гусята": "geese", "индюшата": "turkeys",
    "цесарки": "guinea_fowl", "несушки": "layers", "бройлеры": "broilers",
    "мясояичн": "meat_egg", "мясо-яичн": "meat_egg",
}

def _detect_category(name: str, context: str = "") -> str:
    """Определяет категорию: приоритет — тег страницы [label], потом имя, потом контекст."""
    # 1. Тег страницы сайта [ducks], [geese] и т.д.
    site_tag = re.search(r"\[(\w+)\]", context)
    if site_tag and site_tag.group(1) in SITE_LABEL_MAP:
        return SITE_LABEL_MAP[site_tag.group(1)]
    # 2. Точное слово-категория (Утята, Гусята...)
    n = name.lower()
    for label, cat in CATEGORY_LABELS.items():
        if label in n:
            return cat
    # 3. Порода в имени
    for keyword, cat in BREED_MAP.items():
        if keyword in n:
            return cat
    return "broilers"

def extract_prices_regex(text: str) -> list[dict]:
    """
    Извлекает цены regex-паттернами — работает без LLM и без прокси.
    Примеры: "Кобб-500 — 90 руб", "от 85р/гол", "Бройлер 75-90 руб/шт"
    """
    results = []
    seen = set()

    # Паттерн: <название_породы> ... <цена> руб|р|₽
    pattern = re.compile(
        r"([А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z0-9\-\s]{2,30}?)"   # название
        r"[\s\-–—:]*"
        r"(?:от\s*)?"
        r"(\d{2,4})"                                              # цена
        r"\s*(?:руб|р\b|₽)",
        re.IGNORECASE | re.UNICODE,
    )

    for m in pattern.finditer(text):
        name = m.group(1).strip()
        price = int(m.group(2))

        # Фильтр: цена должна быть реалистичной для птицы (20–2000 руб)
        if not (20 <= price <= 2000):
            continue
        # Фильтр: имя не должно быть служебным словом
        if len(name) < 3 or name.lower() in ("цена", "стоит", "руб", "опт"):
            continue

        key = (name.lower(), price)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "name": name,
            "category": _detect_category(name, text[:50]),  # text[:50] содержит [label]
            "price": price,
        })

    if results:
        log.info(f"  🔍 Regex нашёл {len(results)} цен: {[r['name'] for r in results]}")
    return results


def extract_prices_with_llm(post_text: str) -> list[dict]:
    """Отправляет текст поста в LLM, получает структурированный прайс."""
    if not OPENROUTER_KEY:
        log.warning("OPENROUTER_API_KEY не задан — LLM-извлечение пропущено")
        return []

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-chat",
                "messages": [
                    {"role": "user", "content": PRICE_EXTRACT_PROMPT.format(text=post_text[:3000])}
                ],
                "temperature": 0.1,
                "max_tokens": 1000,
            },
            timeout=15,  # уменьшаем — если прокси лежит, не ждём 30с
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        log.debug(f"LLM raw: {content[:300]}")

        # Чистим ```json ... ``` фенсинг
        content = re.sub(r"```(?:json)?\s*", "", content).strip("` \n")

        # Ищем массив [...] или объект {...}
        json_match = re.search(r"\[.*?\]|\{.*?\}", content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            return parsed if isinstance(parsed, list) else [parsed]
        log.warning(f"LLM вернул не-JSON: {content[:100]}")
        return []
    except Exception as e:
        log.warning(f"LLM недоступен (прокси?): {type(e).__name__} — используем только regex")
        return []



# ─── Источник 1: VK API ───────────────────────────────────────────────────────

def fetch_vk_posts(count: int = 10) -> list[str]:
    """
    Получает свежие посты из VK-сообщества incubird (vk.com/incubird).
    Использует: VK_SERVICE_TOKEN + VK_INCUBIRD_GROUP_ID=-162359356

    ⚠️ VK API не работает через SOCKS-прокси (US) — proxies=_NO_PROXY обязательно!
    """
    if not VK_TOKEN:
        log.warning("⚠️ VK_SERVICE_TOKEN не задан — VK-парсинг пропущен")
        return []

    try:
        session = _ru_session()  # без US SOCKS — VK российский
        resp = session.get(
            "https://api.vk.com/method/wall.get",
            params={
                "owner_id": VK_OWNER_ID,
                "count": count,
                "filter": "owner",
                "access_token": VK_TOKEN,
                "v": "5.199",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            log.error(f"VK API ошибка: {data['error']}")
            return []

        posts = data.get("response", {}).get("items", [])
        texts = [p.get("text", "") for p in posts if p.get("text")]
        log.info(f"✅ VK incubird: получено {len(texts)} постов")
        return texts

    except Exception as e:
        log.error(f"VK fetch ошибка: {e}")
        return []


# ─── Источник 2: Telegram Bot API ─────────────────────────────────────────────

def fetch_telegram_posts(count: int = 20) -> list[str]:
    """
    Получает свежие сообщения из Telegram канала.

    ВАЖНО: Bot API НЕ умеет читать публичные каналы напрямую.
    Варианты:
      А) Добавить бота как администратора канала → getUpdates
      Б) Использовать Telethon (userbot) — нужен номер телефона
      В) Читать через t.me/<channel>/s/ (публичный preview)

    Сейчас реализован вариант В — публичный preview (без токена).
    """
    try:
        # t.me — глобальный сервис, US SOCKS его только ломает → _ru_session()
        channel_name = TG_CHANNEL.lstrip("@")
        session = _ru_session()
        resp = session.get(
            f"https://t.me/s/{channel_name}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning(f"Telegram preview недоступен: {resp.status_code}")
            return []

        # Извлекаем тексты постов из HTML
        texts = re.findall(
            r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            resp.text,
            re.DOTALL,
        )
        # Чистим HTML-теги
        clean = [re.sub(r"<[^>]+>", " ", t).strip() for t in texts]
        clean = [t for t in clean if len(t) > 20][:count]
        log.info(f"Telegram: получено {len(clean)} сообщений")
        return clean

    except Exception as e:
        log.error(f"Telegram fetch ошибка: {e}")
        return []


# ─── Источник 3: incubird.ru (запасной) ──────────────────────────────────────

CATALOG_PAGES = [
    ("https://incubird.ru/cypljata-azovskij-inkubator.html",  "chickens"),
    ("https://incubird.ru/indjushata-azovskij-inkubator.html", "turkeys"),
    ("https://incubird.ru/utjata-azovskij-inkubator.html",     "ducks"),
    ("https://incubird.ru/gusjata-azovskij-inkubator.html",    "geese"),
    ("https://incubird.ru/cesarki-azovskij-inkubator.html",    "guinea_fowl"),
    ("https://incubird.ru/realizacija-grafik-azovskij-inkubator.html", "schedule"),
]

def fetch_site_texts() -> list[str]:
    """Скачивает страницы каталога incubird.ru и возвращает их текст."""
    texts = []
    for url, label in CATALOG_PAGES:
        try:
            session = _ru_session()  # incubird.ru — российский, без US SOCKS
            resp = session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            # Убираем HTML-теги, оставляем текст
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            texts.append(f"[{label}] {text[:3000]}")
            log.info(f"Site: {label} — {len(text)} символов")
        except Exception as e:
            log.error(f"Site fetch {url}: {e}")
    return texts


# ─── Merge: применяем найденные цены к prices.json ────────────────────────────

def apply_price_updates(prices_data: dict, found_prices: list[dict]) -> tuple[dict, int]:
    """
    Применяет найденные цены к структуре prices.json.
    Возвращает (обновлённый_dict, кол-во_изменений).
    """
    changes = 0
    categories = prices_data.get("categories", {})

    for item in found_prices:
        name = item.get("name", "").strip()
        new_price = item.get("price")
        cat_hint = item.get("category", "")
        if not name or new_price is None:
            continue

        matched = False

        # 1. Точное/частичное совпадение имени
        for cat_key, cat_data in categories.items():
            for item_name, item_data in cat_data.get("items", {}).items():
                if name.lower() in item_name.lower() or item_name.lower() in name.lower():
                    old_price = item_data.get("price")
                    if old_price != new_price:
                        log.info(f"  💰 {item_name}: {old_price}₽ → {new_price}₽")
                        item_data["price"] = new_price
                        changes += 1
                    matched = True

        # 2. Категорийное обновление: "Утята" → все позиции в ducks
        if not matched and cat_hint and cat_hint in categories:
            cat_data = categories[cat_hint]
            for item_name, item_data in cat_data.get("items", {}).items():
                old_price = item_data.get("price")
                if old_price != new_price:
                    log.info(f"  💰 [{cat_hint}] {item_name}: {old_price}₽ → {new_price}₽")
                    item_data["price"] = new_price
                    changes += 1

                    # Обновляем тарифную сетку для бройлеров
                    if "price_from" in item and "prices" in item_data:
                        # TODO: обновление тарифных ступеней
                        pass

    return prices_data, changes


# ─── Главная функция ───────────────────────────────────────────────────────────

def run(dry_run: bool = False, source: str = "all") -> None:
    log.info("=" * 60)
    log.info(f"🔄 price_updater старт — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info(f"   dry_run={dry_run}, source={source}")

    # Проверяем нужно ли обновлять (раз в 3 дня)
    prices_data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    last_crawl = prices_data.get("knowledge_update", {}).get("last_crawl")

    if last_crawl and not dry_run:
        last_dt = datetime.fromisoformat(last_crawl)
        schedule_days = prices_data.get("knowledge_update", {}).get("schedule_days", 3)
        if datetime.now() - last_dt < timedelta(days=schedule_days):
            log.info(f"⏭️ Обновление не нужно (последнее: {last_crawl}). Пропускаем.")
            return

    # Собираем тексты из источников
    all_texts = []

    if source in ("all", "vk"):
        vk_posts = fetch_vk_posts(count=15)
        all_texts.extend(vk_posts)

    if source in ("all", "telegram"):
        tg_posts = fetch_telegram_posts(count=20)
        all_texts.extend(tg_posts)

    if source in ("all", "site") or len(all_texts) == 0:
        site_texts = fetch_site_texts()
        all_texts.extend(site_texts)

    log.info(f"📚 Итого текстов для анализа: {len(all_texts)}")

    # Прокси-чек: одна быстрая проверка перед циклом LLM
    proxy_alive = False
    if OPENROUTER_KEY:
        try:
            requests.head("https://openrouter.ai", timeout=3)
            proxy_alive = True
            log.info("✅ Прокси живой — LLM включён")
        except Exception:
            log.warning("⚠️ Прокси недоступен — работаем только через regex")

    # Извлекаем цены: сначала regex (без прокси), потом LLM как дополнение
    all_found_prices = []
    PRICE_KEYWORDS = [
        "руб", "₽", "цена", "цен", "стоит",
        "кобб", "росс", "мулард", "биг",
        "бройлер", "несуш", "индюш", "утят", "гусят", "цесар",
        "ломан", "хайсекс", "фокси", "r500",
        "за голову", "за штуку", "прайс",
    ]
    seen_keys = set()

    for text in all_texts:
        if not any(kw in text.lower() for kw in PRICE_KEYWORDS):
            continue

        # 1️⃣ Regex — мгновенно, без сети
        regex_found = extract_prices_regex(text)
        for item in regex_found:
            key = (item["name"].lower(), item["price"])
            if key not in seen_keys:
                seen_keys.add(key)
                all_found_prices.append(item)

        # 2️⃣ LLM — только если regex ничего не нашёл И прокси живой
        if not regex_found and proxy_alive:
            llm_found = extract_prices_with_llm(text)
            for item in llm_found:
                key = (item.get("name", "").lower(), item.get("price"))
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_found_prices.append(item)


    log.info(f"💰 Всего найдено цен: {len(all_found_prices)}")

    if not all_found_prices:
        log.warning("Цен не найдено — prices.json не изменён")
        # Всё равно обновляем время проверки
        if not dry_run:
            prices_data["knowledge_update"]["last_crawl"] = datetime.now().isoformat()
            CONFIG_PATH.write_text(json.dumps(prices_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # Применяем к prices.json
    updated_data, changes_count = apply_price_updates(prices_data, all_found_prices)

    if dry_run:
        log.info(f"[DRY-RUN] Было бы изменений: {changes_count}")
        log.info("[DRY-RUN] Найденные цены:")
        for p in all_found_prices:
            log.info(f"  {p}")
        return

    # Сохраняем
    updated_data["_meta"]["updated_at"] = datetime.now().isoformat()
    updated_data["_meta"]["updated_by"] = "price_updater.py"
    updated_data["knowledge_update"]["last_crawl"] = datetime.now().isoformat()

    CONFIG_PATH.write_text(
        json.dumps(updated_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log.info(f"✅ prices.json обновлён — {changes_count} изменений")

    # Уведомление в Telegram если были изменения цен
    if changes_count > 0 and TG_BOT_TOKEN:
        notify_admin(changes_count, all_found_prices)


def notify_admin(changes: int, found_prices: list[dict]) -> None:
    """Отправляет уведомление владельцу при изменении цен."""
    admin_id = os.getenv("ADMIN_TELEGRAM_ID", "176203333")
    text = f"💰 *Прайс обновлён* — {changes} изменений\n\n"
    for p in found_prices[:10]:
        text += f"• {p.get('name')}: {p.get('price')}₽\n"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": admin_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        log.error(f"Уведомление не отправлено: {e}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Обновление прайса Заботкиной")
    parser.add_argument("--dry-run", action="store_true", help="Показать найденное, не сохранять")
    parser.add_argument("--source", choices=["all", "vk", "telegram", "site"], default="all")
    parser.add_argument("--force", action="store_true", help="Обновить даже если не вышел срок")
    args = parser.parse_args()

    if args.force:
        # Сбросим last_crawl чтобы форсировать обновление
        data = json.loads(CONFIG_PATH.read_text())
        data["knowledge_update"]["last_crawl"] = None
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    run(dry_run=args.dry_run, source=args.source)
