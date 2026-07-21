#!/usr/bin/env python3
"""
🧠 Habr Intelligence v2 — глобальный LLM-дайджест для AI-экосистемы.

Парсит RSS хабов Хабра, скорит по ключевым словам, затем прогоняет
Топ-5 статей через LLM и получает практические рекомендации:
«Как применить в нашей AI-экосистеме (ai-eggs, ai-bureau, agent-lab)?»

Место: /freelance-2026/tools/ (глобальный инструмент)
Cron:  5 9 * * * cd /Users/igorvasin/freelance-2026 && python3 tools/habr_intelligence.py

Использует корневой .env (/freelance-2026/.env)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape

import requests
from dotenv import load_dotenv

# ── Пути ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

# ── Конфиг ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.getenv("ANGELOCHKA_BOT_TOKEN", "")
OWNER_CHAT_ID   = int(os.getenv("ADMIN_TELEGRAM_ID", "176203333"))
PROXY_URL       = os.getenv("HTTPS_PROXY", os.getenv("TELEGRAM_PROXY", ""))
OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_KEY      = os.getenv("GEMINI_API_KEY", "")
GEMINI_BACKUP   = os.getenv("GEMINI_BACKUP_KEY", "")
OLLAMA_HOST     = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:latest")

STATE_FILE = os.path.join(BASE_DIR, "data", "habr_intelligence_state.json")

# Глобальная сессия БЕЗ прокси — Habr, Gemini, OpenRouter доступны напрямую из РФ
# Прокси из .env нужен ТОЛЬКО для Telegram (отдельная сессия там где нужно)
NO_PROXY_SESSION = requests.Session()
NO_PROXY_SESSION.trust_env = False

# ── Хабы ──────────────────────────────────────────────────────────────────────
HABR_HUBS = [
    # AI / LLM
    "artificial_intelligence",
    "machine_learning",
    "natural_language_processing",
    # chatgpt → 404, хаб удалён с Хабра
    # Разработка
    "python",
    "api",
    "devops",
    "data_engineering",
    # Маркетинг / SEO
    "seo",
    "internetmarketing",
    "search_technologies",
    # Менеджмент
    "dev_management",
]

# ── Ключевые слова (вес 1-3) ───────────────────────────────────────────────────
KEYWORDS: dict[str, int] = {
    # SEO/GEO/AEO
    "seo": 3, "geo": 3, "aeo": 3, "serp": 3,
    "нейровыдача": 3, "ai overview": 3, "ai mode": 3,
    "поисковая оптимизация": 2, "яндекс": 2, "google search": 2,
    # AI агенты
    "agentic": 3, "ai agent": 3, "мультиагент": 3,
    "llm": 3, "large language model": 3,
    "gpt": 2, "gemini": 2, "claude": 2, "deepseek": 2, "qwen": 2,
    "промпт": 2, "prompt engineering": 3, "system prompt": 2,
    "rag": 3, "retrieval": 2, "embedding": 2, "vector": 2,
    "fine-tuning": 3, "дообучение": 3,
    "tool use": 3, "function calling": 3,
    "langchain": 2, "langgraph": 3, "crewai": 2,
    # Инфра / DevOps
    "fastapi": 2, "async": 1, "python": 1,
    "pm2": 2, "docker": 1, "ci/cd": 1, "deploy": 1,
    "cron": 2, "scheduler": 2, "webhook": 2,
    # Telegram / боты
    "telegram bot": 3, "бот": 2, "чат-бот": 2,
    # CRM / Продажи
    "bitrix": 3, "crm": 2, "воронка": 2, "автоматизация": 2,
    "лидогенерация": 3, "конверсия": 2,
    # Маркетинг
    "контент-маркетинг": 2, "smm": 2, "email": 1,
    # Аналитика
    "дашборд": 2, "аналитика": 1, "метрики": 2,
    # Медиа / Парсинг
    "парсинг": 2, "scraping": 2, "rss": 1,
    "youtube": 2, "транскрибация": 3, "whisper": 3,
}

STOP_KEYWORDS = [
    "gamedev", "counter-strike", "factorio", "unity", "unreal",
    "блокчейн", "crypto", "nft", "web3",
    "arduino", "raspberry", "электроника", "схема", "паяльник",
]

TG_CHANNELS = [
    "vibecoding_tg",
    "dailyprompts",
    "geekneural",
    "neyroseti_dr",
]

# ── Карта агентов экосистемы ───────────────────────────────────────────────────
ECOSYSTEM = """
Наша AI-экосистема состоит из следующих компонентов:

- **ai-eggs** (Python) — AI-агент для птицеводческого бизнеса (Азовский инкубатор).
  Агенты: Заботкина (CRM, Bitrix24), Птенчикова (контент, VK, OK).
  Модули: Habr-дайджест, фото-каскад, публикация на Авито.

- **ai-bureau** (Vite+React+TS) — Агентство AI-систем. RAG, GEO, кастомные агенты.
  Агенты: Игорек (архитектор), Кулибин (DevOps/интеграции), Артемий (фронтенд),
  Маркетолог (SEO/GEO/AEO), Шекспир (контент E-E-A-T), Шерл (разведка рынка).

- **ai-scout** (React+Vite+TS+Supabase) — Сбор и саммари из Telegram и YouTube.
  Библиотека избранного контента.

- **ai-sinergy** — Поиск и генерация новых идей и стартапов.

- **agent-lab** (Python) — Лаборатория: LLM-каскад, поисковый каскад, фото-каскад.
  Прототипы и эксперименты перед боевым деплоем.

- **tools/** (глобальные скрипты) — chronicle.sh, morning_dream.sh,
  habr_intelligence.py и другие общесистемные инструменты.
"""

# ── RSS-парсинг ────────────────────────────────────────────────────────────────

def fetch_hub_rss(hub: str, max_items: int = 15) -> list[dict]:
    url = f"https://habr.com/ru/rss/hub/{hub}/all/"
    try:
        resp = NO_PROXY_SESSION.get(url, timeout=15, headers={"User-Agent": "Antigravity-HabrIntelligence/2.0"})
        if resp.status_code != 200:
            print(f"  ⚠ {hub}: HTTP {resp.status_code}")
            return []
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title       = item.findtext("title", "")
            link        = item.findtext("link", "")
            description = item.findtext("description", "")
            pub_date    = item.findtext("pubDate", "")
            categories  = [c.text for c in item.findall("category") if c.text]
            desc_clean  = re.sub(r"<[^>]+>", "", unescape(description or ""))
            desc_clean  = re.sub(r"\s+", " ", desc_clean).strip()[:400]
            items.append({
                "title": title, "link": link,
                "description": desc_clean, "pub_date": pub_date,
                "categories": categories,                 "hub": hub, "source": "habr",
            })
        return items
    except Exception as e:
        print(f"  ⚠ {hub}: {e}")
        return []


def fetch_vc_rss(max_items: int = 20) -> list[dict]:
    url = "https://vc.ru/rss"
    try:
        resp = NO_PROXY_SESSION.get(url, timeout=15, headers={"User-Agent": "Antigravity-HabrIntelligence/2.0"})
        if resp.status_code != 200:
            print(f"  ⚠ VC.ru: HTTP {resp.status_code}")
            return []
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title       = item.findtext("title", "")
            link        = item.findtext("link", "")
            description = item.findtext("description", "")
            pub_date    = item.findtext("pubDate", "")
            categories  = [c.text for c in item.findall("category") if c.text]
            desc_clean  = re.sub(r"<[^>]+>", "", unescape(description or ""))
            desc_clean  = re.sub(r"\s+", " ", desc_clean).strip()[:400]
            items.append({
                "title": title, "link": link,
                "description": desc_clean, "pub_date": pub_date,
                "categories": categories, "hub": "vc", "source": "vc",
            })
        return items
    except Exception as e:
        print(f"  ⚠ VC.ru error: {e}")
        return []


def fetch_github_trending(max_items: int = 10) -> list[dict]:
    url = "https://github.com/trending"
    try:
        resp = NO_PROXY_SESSION.get(url, timeout=15, headers={"User-Agent": "Antigravity-HabrIntelligence/2.0"})
        if resp.status_code != 200:
            print(f"  ⚠ GitHub Trending: HTTP {resp.status_code}")
            return []
        html = resp.text
        articles = html.split('<article class=\"Box-row\"')
        items = []
        for art in articles[1:max_items+1]:
            # Repo name
            name_match = re.findall(r'href=\"/([^\"\s]+/[^\"\s]+?)\"', art)
            repo_names = [n for n in name_match if '/' in n and 'sponsor' not in n and 'login' not in n]
            seen = set()
            unique = []
            for rn in repo_names:
                if rn not in seen:
                    seen.add(rn)
                    unique.append(rn)
            repo = unique[0] if unique else "?"
            # Description
            desc_match = re.search(r'<p class=\"col-9[^\"]*\"[^>]*>(.*?)</p>', art, re.DOTALL)
            desc = ""
            if desc_match:
                desc = re.sub(r"<[^>]+>", "", unescape(desc_match.group(1))).strip()[:300]
            # Stars today
            stars_today = ""
            st = re.findall(r'([\d,.]+)\s*stars?\s*today', art, re.IGNORECASE)
            if st:
                stars_today = f"{st[0]} ★ today"
            items.append({
                "title": f"{repo}: {desc}" if desc else repo,
                "link": f"https://github.com/{repo}",
                "description": f"{desc} | {stars_today}" if stars_today else desc,
                "pub_date": "",
                "categories": ["github", repo.split("/")[0]],
                "hub": "github", "source": "github",
            })
        return items
    except Exception as e:
        print(f"  ⚠ GitHub Trending error: {e}")
        return []


def fetch_telegram_posts(channel: str, max_items: int = 10) -> list[dict]:
    url = f"https://t.me/s/{channel}"
    try:
        resp = NO_PROXY_SESSION.get(url, timeout=15, headers={"User-Agent": "Antigravity-HabrIntelligence/2.0"})
        if resp.status_code != 200:
            print(f"  ⚠ Telegram @{channel}: HTTP {resp.status_code}")
            return []
        html = resp.text
        blocks = html.split('<div class=\"tgme_widget_message_wrap')
        items = []
        for block in blocks[1:max_items+1]:
            text_match = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, re.DOTALL)
            text = ""
            if text_match:
                text = re.sub(r"<[^>]+>", "", unescape(text_match.group(1))).strip()[:400]
            if not text:
                continue
            date_match = re.search(r'<time datetime=\"([^\"]+)\"', block)
            pub_date = date_match.group(1) if date_match else ""
            link_match = re.search(r'href=\"(https://t\.me/[^\"]+/\d+)\"', block)
            link = link_match.group(1) if link_match else f"https://t.me/s/{channel}"
            items.append({
                "title": text[:100],
                "link": link,
                "description": text,
                "pub_date": pub_date,
                "categories": [f"@{channel}"],
                "hub": f"tg/{channel}", "source": "telegram",
            })
        return items
    except Exception as e:
        print(f"  ⚠ Telegram @{channel} error: {e}")
        return []


def fetch_all_sources() -> list[dict]:
    print("  📡 Habr...")
    habr = []
    for hub in HABR_HUBS:
        items = fetch_hub_rss(hub)
        habr.extend(items)
    print(f"     → {len(habr)} статей")

    print("  📡 VC.ru...")
    vc = fetch_vc_rss()
    print(f"     → {len(vc)} статей")

    print("  📡 GitHub Trending...")
    gh = fetch_github_trending()
    print(f"     → {len(gh)} репозиториев")

    print("  📡 Telegram...")
    tg = []
    for ch in TG_CHANNELS:
        posts = fetch_telegram_posts(ch)
        tg.extend(posts)
    print(f"     → {len(tg)} постов")

    return habr + vc + gh + tg


def fetch_full_article(article: dict) -> dict:
    if article.get("source") != "habr":
        return article
    try:
        resp = NO_PROXY_SESSION.get(
            article["link"], timeout=15,
            headers={"User-Agent": "Antigravity-HabrIntelligence/2.0"}
        )
        if resp.status_code != 200:
            return article
        html = resp.text
        match = re.search(
            r'div class="article-formatted-body[^"]*"[^>]*>(.*?)</div>\s*<div class="article-formatted-body_version-',
            html, re.DOTALL
        )
        if not match:
            match = re.search(
                r'article-formatted-body[^>]*>(.*?)(?:<footer|<div class="article__footer|</article)',
                html, re.DOTALL
            )
        if match:
            text = re.sub(r"<[^>]+>", "", unescape(match.group(1)))
            text = re.sub(r"\s+", " ", text).strip()[:3000]
            if len(text) > 200:
                article["full_text"] = text
        return article
    except Exception as e:
        print(f"    ⚠ fetch_full_article: {e}")
        return article


SOURCE_LABELS = {
    "habr": "📡 Habr",
    "vc": "📡 VC.ru",
    "github": "📡 GitHub",
    "telegram": "📡 Telegram",
}


# ── Скоринг ───────────────────────────────────────────────────────────────────

def score_article(article: dict) -> int:
    text = f"{article['title']} {article['description']} {' '.join(article['categories'])}".lower()
    score = 0
    matched: list[str] = []
    for kw, w in KEYWORDS.items():
        if kw.lower() in text:
            score += w * 10
            matched.append(kw)
    for stop in STOP_KEYWORDS:
        if stop.lower() in text:
            score -= 25
    article["_score"]    = max(score, 0)
    article["_keywords"] = matched
    return article["_score"]


# ── LLM-анализ ────────────────────────────────────────────────────────────────

def _build_prompt(article: dict) -> str:
    content = article.get("full_text") or article["description"][:300]
    return f"""Ты — технический директор AI-экосистемы. Твоя задача: найти конкретную ФИЧУ или ТЕХНИКУ из статьи, оценить её полезность для наших проектов и предложить: ставить или пропустить.

{ECOSYSTEM}

СТАТЬЯ:
Заголовок: {article['title']}
Содержание: {content[:2500]}
Теги: {', '.join(article['categories'][:5])}

Ответь СТРОГО в формате (без маркдауна, без пояснений):
ФИЧА: <название конкретной фичи/технологии из статьи, 5-8 слов>
ОЦЕНКА: <цифра 1-10 и одна фраза почему это важно для нас>
ПЛАН: <3 конкретных шага для внедрения, через запятую>
ПРОЕКТ: <одно из: ai-eggs | ai-bureau | ai-scout | ai-sinergy | agent-lab | tools>
АГЕНТ: <одно из: Кулибин | Игорек | Маркетолог | Заботкина | Артемий | Шерл | Шекспир | —>
РЕШЕНИЕ: <СТАВИМ если оценка 7+ | ПРОПУСКАЕМ если оценка ниже 7>
"""


def analyze_with_gemini(article: dict) -> dict:
    """LLM-анализ через Gemini REST API. Пробует основной, потом резервный ключ.
    Gemini доступен из РФ напрямую — прокси НЕ нужен.
    (PROXY_URL используется только для Telegram)
    """
    for key in filter(None, [GEMINI_KEY, GEMINI_BACKUP]):
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash:generateContent?key={key}"
            )
            payload = {
                "contents": [{"parts": [{"text": _build_prompt(article)}]}],
                "generationConfig": {"maxOutputTokens": 256, "temperature": 0.4},
            }
            # NO_PROXY_SESSION: trust_env=False — игнорирует системный HTTPS_PROXY/SOCKS5
            resp = NO_PROXY_SESSION.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                print("  ✅ Gemini OK")
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return _parse_llm_response(text)
            elif resp.status_code == 429:
                print("  ⚠ Gemini 429 (квота), пробую резерв...")
                continue
            else:
                print(f"  ⚠ Gemini {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"  ⚠ Gemini error: {e}")
    return {"фича": "—", "оценка": "—", "план": "—", "применение": "—", "проект": "—", "агент": "—", "решение": "—"}


def analyze_with_openrouter(article: dict) -> dict:
    """LLM-анализ через OpenRouter (бесплатные free-модели, через прокси)."""
    if not OPENROUTER_KEY:
        return {"фича": "—", "оценка": "—", "план": "—", "применение": "—", "проект": "—", "агент": "—", "решение": "—"}
    # Каскад free-моделей OpenRouter (актуально на июль 2026)
    free_models = [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "openai/gpt-oss-20b:free",
    ]
    for model in free_models:
        try:
            resp = NO_PROXY_SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": _build_prompt(article)}],
                    "max_tokens": 256,
                },
                timeout=25,
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"]
                result = _parse_llm_response(text)
                if result["фича"] != "—":
                    print(f"  ✅ OpenRouter/free/{model} OK")
                    return result
                print(f"  ⚠ OpenRouter/free/{model}: ответ не распознан")
            else:
                print(f"  ⚠ OpenRouter/free/{model}: {resp.status_code}")
        except Exception as e:
            print(f"  ⚠ OpenRouter/free/{model} error: {e}")
    return {"фича": "—", "оценка": "—", "план": "—", "применение": "—", "проект": "—", "агент": "—", "решение": "—"}


def _build_ollama_prompt(article: dict) -> str:
    content = article.get("full_text") or article["description"][:200]
    return f"""Ты — технический директор. Найди КОНКРЕТНУЮ ФИЧУ из статьи и реши: внедрять или нет.

Статья: {article['title']}
Содержание: {content[:1500]}

Проекты: ai-eggs (птицеводство/CRM), ai-bureau (AI агентство), ai-scout (сбор контента), agent-lab (эксперименты)
Агенты: Кулибин (DevOps), Маркетолог (SEO), Заботкина (CRM), Шерл (разведка), Шекспир (контент), Игорек (архитектор)

Ответь СТРОГО в 5 строк:
ФИЧА: <конкретное название технологии/подхода из статьи, 4-6 слов>
ОЦЕНКА: <число 1-10> — <одна фраза почему полезно>
ПРОЕКТ: <одно: ai-eggs | ai-bureau | ai-scout | agent-lab | tools>
АГЕНТ: <одно: Кулибин | Игорек | Маркетолог | Заботкина | Шерл | Шекспир | —>
РЕШЕНИЕ: <СТАВИМ если оценка 7 и выше, ПРОПУСКАЕМ если ниже 7>"""


def analyze_with_ollama(article: dict) -> dict:
    """Fallback: LLM-анализ через локальный Ollama (без прокси, без квот).
    Использует /api/chat — корректный endpoint для chat-моделей.
    Поддерживает thinking-модели (gemma4): fallback на поле thinking.
    """
    try:
        resp = NO_PROXY_SESSION.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "Ты краткий AI-ассистент. Отвечай ТОЛЬКО в запрошенном формате, без рассуждений, без markdown, без лишних слов.",
                    },
                    {"role": "user", "content": _build_ollama_prompt(article)},
                ],
                "stream": False,
                "think": False,  # отключаем thinking mode если модель поддерживает
                "options": {"temperature": 0.3, "top_p": 0.9},
            },
            timeout=120,
        )
        if resp.status_code == 200:
            body = resp.json()
            msg = body.get("message", {})
            # Пробуем content, потом thinking как fallback
            text = msg.get("content", "").strip()
            if not text:
                text = msg.get("thinking", "").strip()
            result = _parse_llm_response(text)
            if result["фича"] != "—" or result["применение"] != "—":
                print(f"  ✅ Ollama ({OLLAMA_MODEL}) OK")
                return result
            else:
                print(f"  ⚠ Ollama: ответ не распознан → {text[:120]}")
        else:
            print(f"  ⚠ Ollama HTTP {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"  ⚠ Ollama error: {e}")
    return {"фича": "—", "оценка": "—", "план": "—", "применение": "—", "проект": "—", "агент": "—", "решение": "—"}


def _parse_llm_response(text: str) -> dict:
    result = {
        "фича": "—", "оценка": "—", "план": "—",
        "проект": "—", "агент": "—", "решение": "—",
        # обратная совместимость со старым форматом
        "применение": "—",
    }
    for line in text.strip().splitlines():
        line = line.strip()
        if line.startswith("ФИЧА:"):
            result["фича"] = line.replace("ФИЧА:", "").strip()
            result["применение"] = result["фича"]  # compat
        elif line.startswith("ОЦЕНКА:"):
            result["оценка"] = line.replace("ОЦЕНКА:", "").strip()
        elif line.startswith("ПЛАН:"):
            result["план"] = line.replace("ПЛАН:", "").strip()
        elif line.startswith("ПРОЕКТ:"):
            result["проект"] = line.replace("ПРОЕКТ:", "").strip()
        elif line.startswith("АГЕНТ:"):
            result["агент"] = line.replace("АГЕНТ:", "").strip()
        elif line.startswith("РЕШЕНИЕ:"):
            result["решение"] = line.replace("РЕШЕНИЕ:", "").strip()
        # старый формат (fallback)
        elif line.startswith("ПРИМЕНЕНИЕ:") and result["фича"] == "—":
            result["применение"] = line.replace("ПРИМЕНЕНИЕ:", "").strip()
            result["фича"] = result["применение"]
    return result


def analyze_article(article: dict) -> dict:
    """Каскад: Gemini Direct → Ollama (local) → OpenRouter."""
    print(f"    🧠 LLM-анализ: {article['title'][:55]}...")
    result = analyze_with_gemini(article)
    if result["фича"] == "—":
        print("    🔄 Gemini недоступен → Ollama (local)")
        result = analyze_with_ollama(article)
    if result["фича"] == "—" and OPENROUTER_KEY:
        print("    🔄 Ollama недоступен → OpenRouter")
        result = analyze_with_openrouter(article)
    article["_llm"] = result
    return article


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print("⚠ ANGELOCHKA_BOT_TOKEN не задан")
        return False
    # Telegram доступен напрямую из РФ без прокси
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = NO_PROXY_SESSION.post(url, json={
            "chat_id": OWNER_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=30)
        if resp.status_code == 200:
            print(f"✅ Отправлено в TG (chat_id={OWNER_CHAT_ID})")
            return True
        else:
            print(f"⚠ TG error: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"⚠ TG send error: {e}")
    return False


# ── Форматирование ────────────────────────────────────────────────────────────

def format_digest(articles: list[dict]) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    lines = [
        f"🧠 <b>HABR INTELLIGENCE — {today}</b>",
        "",
    ]
    for i, art in enumerate(articles, 1):
        source_label = SOURCE_LABELS.get(art.get("source", ""), f"📡 {art.get('hub', '?')}")
        score = art["_score"]
        stars = "⭐⭐⭐" if score >= 40 else ("⭐⭐" if score >= 20 else "⭐")
        kw_str = ", ".join(art["_keywords"][:3]) or art["hub"]
        llm = art.get("_llm", {})
        фича    = llm.get("фича", llm.get("применение", "—"))
        оценка  = llm.get("оценка", "—")
        план    = llm.get("план", "—")
        проект  = llm.get("проект", "—")
        агент   = llm.get("агент", "—")
        решение = llm.get("решение", "—")
        значок  = "🔥" if "СТАВИМ" in решение else "📌"

        lines.append(f"{source_label}")
        lines.append(f"{i}. <a href=\"{art['link']}\">{art['title']}</a>")
        lines.append(f"   {stars} | {kw_str}")
        if фича != "—":
            lines.append(f"   {значок} <b>{фича}</b>")
            if оценка != "—":
                lines.append(f"   📊 {оценка}")
            if план != "—":
                lines.append(f"   📋 {план}")
            lines.append(f"   📂 {проект} · 🤖 {агент} · {решение}")
        lines.append("")

    lines += ["─" * 20, "Antigravity · Habr Intelligence v2"]
    return "\n".join(lines)


# ── Дедупликация ──────────────────────────────────────────────────────────────

def load_sent_links() -> set[str]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return set(json.load(f).get("sent_links", []))
        except Exception:
            pass
    return set()


def save_sent_links(links: set[str]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"sent_links": list(links)[-300:], "last_run": datetime.now().isoformat()}, f)


# ── Главная функция ───────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> None:
    print(f"\n{'='*55}")
    print(f"HABR INTELLIGENCE v2 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}\n")

    sent_links = load_sent_links()

    # Сбор со всех источников
    all_articles = fetch_all_sources()

    print(f"\nВсего: {len(all_articles)} статей/постов")

    # Дедупликация
    seen: set[str] = set()
    unique: list[dict] = []
    for art in all_articles:
        if art["link"] not in seen and art["link"] not in sent_links:
            seen.add(art["link"])
            unique.append(art)
    print(f"Новых уникальных: {len(unique)}")

    # Скоринг
    for art in unique:
        score_article(art)

    ranked = sorted(unique, key=lambda x: x["_score"], reverse=True)
    relevant = [a for a in ranked if a["_score"] > 0]
    print(f"Релевантных (score > 0): {len(relevant)}\n")

    if not relevant:
        print("Нет релевантных статей. Пропускаю.")
        return

    top5 = relevant[:5]
    print("ТОП-5:")
    for art in top5:
        src = SOURCE_LABELS.get(art.get("source", ""), art.get("hub", "?"))
        print(f"  [{src}] [{art['_score']:3d}] {art['title'][:60]}")

    # Полный текст для Habr-статей
    print("\n📄 Полные тексты...")
    for art in top5:
        fetch_full_article(art)

    # LLM-анализ (с полным текстом, если есть)
    print("\n🧠 LLM-анализ...")
    for art in top5:
        analyze_article(art)

    digest = format_digest(top5)
    print(f"\n{'─'*55}\n{digest}\n{'─'*55}")

    if dry_run:
        print("\n[DRY RUN] В Telegram не отправляем.")
        return

    if send_telegram(digest):
        sent_links.update(a["link"] for a in top5)
        save_sent_links(sent_links)
        print("State сохранён.")
    else:
        print("⚠ Не удалось отправить. State НЕ обновлён.")


# ── Точка входа ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Habr Intelligence v2")
    parser.add_argument("--dry-run", action="store_true", help="Не отправлять в Telegram")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
