#!/usr/bin/env python3
"""
🐣 SANDBOX INITIATOR — Модуль «выполнения обещаний» Анжелочки.
Публикует утренние новости и советы в песочницу Bitrix24.

v1.0 — 22.04.2026
"""
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# ПЕСОЧНИЦА (webhook из чата)
SANDBOX_URL = "https://b24-mjxvhq.bitrix24.ru/rest/1/9ydrtvi31y1oqay7/"
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def _call_llm(prompt: str) -> str:
    """Генерация через OpenRouter."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    try:
        resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"LLM Error: {e}")
        return "💡 AI-анализ временно недоступен."

def generate_morning_brief():
    """Собирает утренний дайджест."""
    log("📝 Генерация утреннего дайджеста...")
    
    # Данные из поиска (уже найдены в текущей сессии)
    search_data = """
    Цены Крым (апрель 2026):
    - Бройлер суточный: 70-135 руб (Кобб-500, Росс-308)
    - Индюшата суточные: 350-450 руб (Биг-6)
    - Муларды: 290-300 руб
    - Несушки: 90-150 руб
    
    Новости:
    - Власти Крыма создают племенной центр для независимости от импорта.
    - СП Октябрьское и Партизан наращивают объемы.
    - Снижение производства мяса птицы в РФ на 2.7% из-за себестоимости и конкуренции со свининой.
    """
    
    prompt = f"""
    Ты — Анжелочка, проактивный AI-ассистент инкубатора «IncuBird».
    Напиши «Утреннюю Птичью Сводку» для Андрея в песочницу Bitrix24.
    
    ИСПОЛЬЗУЙ ДАННЫЕ:
    {search_data}
    
    СТРУКТУРА:
    1. 📰 НОВОСТЬ ДНЯ (главное из отрасли в Крыму)
    2. 💰 ЦЕНОВОЙ ДОЗОР (сравнение цен конкурентов с нашими из прайса: Кобб-500 у нас 90р, Биг-6 450р, Мулард 250р)
    3. 💡 СОВЕТ АНЖЕЛОЧКИ (проактивная рекомендация менеджерам на сегодня)
    
    СТИЛЬ:
    Живой, энергичный, с эмодзи. Ты обещала это делать каждое утро! Покажи уровень.
    """
    
    return _call_llm(prompt)

def post_to_sandbox_feed(text):
    """Публикация в Живую Ленту песочницы."""
    log("🚀 Публикация в Живую Ленту песочницы...")
    
    title = f"🐣 Утренняя Сводка Анжелочки — {datetime.now().strftime('%d.%m')}"
    
    params = {
        "POST_TITLE": title,
        "MESSAGE": text,
        "DEST": ["UA"] # Всем сотрудникам
    }
    
    method = "log.blogpost.add.json"
    try:
        resp = requests.post(f"{SANDBOX_URL}/{method}", json=params, timeout=20)
        result = resp.json()
        if result.get("result"):
            log(f"✅ Успешно опубликовано! ID: {result['result']}")
            return True
        else:
            log(f"❌ Ошибка Bitrix: {result}")
    except Exception as e:
        log(f"❌ Ошибка сети: {e}")
    return False

if __name__ == "__main__":
    brief = generate_morning_brief()
    print("\n--- ГЕНЕРИРУЕМЫЙ КОНТЕНТ ---\n")
    print(brief)
    print("\n---------------------------\n")
    
    # Спрашиваем подтверждение или просто постим (в песочницу можно без спроса)
    post_to_sandbox_feed(brief)
