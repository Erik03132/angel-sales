"""
Habr Daily Digest -- ежедневный дайджест релевантных статей с Хабра.

Парсит RSS нужных хабов, фильтрует по ключевым словам,
ранжирует по релевантности и отправляет ТОП-5 в Telegram.

Запуск: python3 habr_digest.py
Cron:   0 9 * * * (каждый день в 9:00 MSK)
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# === CONFIG ===

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
PROXY_URL = os.getenv("TELEGRAM_PROXY")
ADMIN_CHAT_ID = 444248782   # Андрей
OWNER_CHAT_ID = 176203333   # Игорь

# Хабы для мониторинга
HABR_HUBS = [
    "seo",
    "artificial_intelligence",
    "machine_learning",
    "internetmarketing",
    "search_technologies",
    "natural_language_processing",
    "dev_management",
    "api",
]

# Ключевые слова для ранжирования (вес от 1 до 3)
KEYWORDS = {
    # SEO/GEO/AEO -- наш хлеб
    "seo": 3, "geo": 3, "aeo": 3, "serp": 3,
    "поисковая оптимизация": 3, "нейровыдача": 3,
    "ai overview": 3, "ai mode": 3, "query fan-out": 3,
    "яндекс поиск": 2, "google search": 2,
    # AI агенты
    "agentic": 3, "ai agent": 3, "ai-агент": 3,
    "llm": 2, "gpt": 2, "gemini": 2, "claude": 2,
    "промпт": 2, "prompt engineering": 2,
    "rag": 2, "retrieval": 2, "embedding": 2,
    # CRM / Продажи / Bitrix
    "bitrix": 3, "crm": 2, "воронка продаж": 2,
    "автоматизация продаж": 3, "чат-бот": 2,
    "telegram bot": 2, "avito": 2,
    # Маркетинг
    "контент-маркетинг": 2, "smm": 2, "email-маркетинг": 2,
    "конверсия": 2, "лид": 2, "лидогенерация": 3,
    # DevOps / Инфра (для Кулибина)
    "pm2": 2, "deploy": 1, "ci/cd": 1,
    "docker": 1, "nginx": 1, "fastapi": 2,
    # Транскрибация (актуально для звонков)
    "whisper": 3, "speech-to-text": 3, "транскрибация": 3,
    "stt": 2, "распознавание речи": 2,
    # E-commerce
    "e-commerce": 2, "маркетплейс": 2, "интернет-магазин": 2,
}

# Стоп-слова (понижают рейтинг)
STOP_KEYWORDS = [
    "gamedev", "игр", "counter-strike", "factorio", "unity",
    "блокчейн", "crypto", "nft", "web3",
    "arduino", "raspberry", "электроника",
]

# Файл для дедупликации (не отправлять одно и то же дважды)
DIGEST_STATE_FILE = os.path.join(BASE_DIR, "data", "habr_digest_state.json")

# === FUNCTIONS ===

def fetch_hub_rss(hub_name, max_items=20):
    """Получить статьи из RSS хаба."""
    url = f"https://habr.com/ru/rss/hubs/{hub_name}/"
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Antigravity-HabrDigest/1.0"
        })
        if resp.status_code != 200:
            print(f"  [!] {hub_name}: HTTP {resp.status_code}")
            return []
        
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            description = item.findtext("description", "")
            pub_date = item.findtext("pubDate", "")
            categories = [c.text for c in item.findall("category") if c.text]
            
            # Убираем HTML из description
            desc_clean = re.sub(r'<[^>]+>', '', unescape(description or ""))
            desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()[:300]
            
            items.append({
                "title": title,
                "link": link,
                "description": desc_clean,
                "pub_date": pub_date,
                "categories": categories,
                "hub": hub_name,
            })
        return items
    except Exception as e:
        print(f"  [!] {hub_name}: {e}")
        return []


def score_article(article):
    """Оценить релевантность статьи (0-100)."""
    text = f"{article['title']} {article['description']} {' '.join(article['categories'])}".lower()
    
    score = 0
    matched_keywords = []
    
    for keyword, weight in KEYWORDS.items():
        if keyword.lower() in text:
            score += weight * 10
            matched_keywords.append(keyword)
    
    # Штраф за стоп-слова
    for stop in STOP_KEYWORDS:
        if stop.lower() in text:
            score -= 20
    
    # Бонус за свежесть (статьи за последние 24 часа)
    # pubDate формат: "Tue, 29 Apr 2026 18:00:00 GMT"
    
    article["_score"] = max(score, 0)
    article["_keywords"] = matched_keywords
    return score


def load_sent_links():
    """Загрузить уже отправленные ссылки."""
    if os.path.exists(DIGEST_STATE_FILE):
        try:
            with open(DIGEST_STATE_FILE, 'r') as f:
                data = json.load(f)
            return set(data.get("sent_links", []))
        except Exception:
            pass
    return set()


def save_sent_links(links):
    """Сохранить отправленные ссылки (хранить последние 200)."""
    os.makedirs(os.path.dirname(DIGEST_STATE_FILE), exist_ok=True)
    with open(DIGEST_STATE_FILE, 'w') as f:
        json.dump({"sent_links": list(links)[-200:], "last_run": datetime.now().isoformat()}, f)


def send_telegram(text):
    """Отправить сообщение в Telegram (обоим руководителям)."""
    if not TELEGRAM_TOKEN:
        print("[!] ANGELOCHKA_BOT_TOKEN не задан")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Прокси (как в autopilot.py)
    proxies = {}
    if PROXY_URL:
        p = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": p, "http": p}
    
    success = False
    # ⛔ Андрею — НИЧЕГО в TG! (решение от 12.05.2026)
    # ТОЛЬКО Игорю
    for chat_id in [OWNER_CHAT_ID]:
        try:
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, proxies=proxies, timeout=30)
            if resp.status_code == 200:
                print(f"[+] Дайджест отправлен в TG (chat_id={chat_id})")
                success = True
            else:
                print(f"[!] TG error ({chat_id}): {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"[!] TG send error ({chat_id}): {e}")
    
    return success


def format_digest(articles):
    """Форматировать дайджест для TG."""
    today = datetime.now().strftime("%d.%m.%Y")
    
    lines = [
        f"<b>HABR DIGEST -- {today}</b>",
        "",
    ]
    
    # Маппинг агентов
    agent_map = {
        "seo": "Marketer",
        "artificial_intelligence": "Kulibin",
        "machine_learning": "Kulibin",
        "internetmarketing": "Marketer",
        "search_technologies": "Marketer",
        "natural_language_processing": "Kulibin",
        "dev_management": "Igorek",
        "api": "Artemiy",
    }
    
    for i, art in enumerate(articles[:5], 1):
        # Звёзды по скорингу
        score = art["_score"]
        if score >= 40:
            stars = "***"
        elif score >= 20:
            stars = "**"
        else:
            stars = "*"
        
        hub_label = art.get("hub", "")
        agent = agent_map.get(hub_label, "")
        agent_tag = f" [{agent}]" if agent else ""
        
        # Ключевые слова
        kw = ", ".join(art["_keywords"][:3]) if art["_keywords"] else hub_label
        
        lines.append(f"{i}. <a href=\"{art['link']}\">{art['title']}</a>")
        lines.append(f"   {stars} | {kw}{agent_tag}")
        lines.append(f"   {art['description'][:120]}...")
        lines.append("")
    
    lines.append("---")
    lines.append("Antigravity Habr Scout")
    
    return "\n".join(lines)


def run_digest():
    """Основная функция дайджеста."""
    print(f"\n{'='*50}")
    print(f"HABR DIGEST -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    
    sent_links = load_sent_links()
    all_articles = []
    
    # Парсим все хабы
    for hub in HABR_HUBS:
        print(f"  Парсю хаб: {hub}...")
        articles = fetch_hub_rss(hub)
        all_articles.extend(articles)
        print(f"    -> {len(articles)} статей")
    
    print(f"\nВсего статей: {len(all_articles)}")
    
    # Дедупликация по ссылкам
    seen = set()
    unique = []
    for art in all_articles:
        if art["link"] not in seen and art["link"] not in sent_links:
            seen.add(art["link"])
            unique.append(art)
    
    print(f"Уникальных новых: {len(unique)}")
    
    # Скоринг
    for art in unique:
        score_article(art)
    
    # Сортировка по релевантности
    ranked = sorted(unique, key=lambda x: x["_score"], reverse=True)
    
    # Фильтр: только с положительным скором
    relevant = [a for a in ranked if a["_score"] > 0]
    
    print(f"Релевантных (score > 0): {len(relevant)}")
    
    if not relevant:
        print("Нет релевантных статей. Пропускаю.")
        return
    
    # Топ-5
    top5 = relevant[:5]
    for art in top5:
        print(f"  [{art['_score']:3d}] {art['title'][:60]}...")
    
    # Формируем и отправляем
    digest_text = format_digest(top5)
    print(f"\n--- DIGEST TEXT ---\n{digest_text}\n---")
    
    if send_telegram(digest_text):
        # Сохраняем отправленные
        sent_links.update(a["link"] for a in top5)
        save_sent_links(sent_links)
        print("State saved.")
    else:
        print("[!] Не удалось отправить. State НЕ обновлён.")


if __name__ == "__main__":
    run_digest()
