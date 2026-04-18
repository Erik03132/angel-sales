#!/usr/bin/env python3
"""
🧠 AI LEARNER V2 — Извлечение мудрости из всех каналов (Звонки, Чаты, Лиды).
Автор: Анжелочка
"""
import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

DATA_DIR = os.path.join(BASE_DIR, "data")
SHADOW_DIR = os.path.join(DATA_DIR, "shadow_learning")
LEARNING_PATH = os.path.join(DATA_DIR, "daily_learning.json")
EXPERT_WISDOM_PATH = os.path.join(DATA_DIR, "expert_knowledge.md")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎓 {msg}", flush=True)

def api_call_gemini(prompt):
    """Вызывает Gemini для анализа данных."""
    if not GEMINI_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(url, json=payload, timeout=60)
        return r.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        log(f"Gemini Error: {e}")
        return None

def collect_raw_evidence():
    """Собирает за день все переписки и звонки для анализа."""
    evidence = []
    today = datetime.now().strftime("%Y%m%d")
    
    # 1. Звонки (транскрипции)
    calls_path = os.path.join(SHADOW_DIR, "calls", "transcripts.json")
    if os.path.exists(calls_path):
        with open(calls_path, 'r', encoding='utf-8') as f:
            calls = json.load(f)
            # Берем только свежие (лимит 10 для анализа за раз)
            evidence.append(f"📞 ТРАНСКРИПЦИИ ЗВОНКОВ (Марина/Аня/Эльзара):\n{json.dumps(calls[-15:], ensure_ascii=False)}")

    # 2. Чаты открытых линий
    chats_path = os.path.join(SHADOW_DIR, "chats", f"open_lines_{today}.json")
    if os.path.exists(chats_path):
        with open(chats_path, 'r', encoding='utf-8') as f:
            chats = json.load(f)
            evidence.append(f"📱 ПЕРЕПИСКИ ТЕЛЕГРАМ/АВИТО:\n{json.dumps(chats[:20], ensure_ascii=False)}")

    return "\n\n---\n\n".join(evidence)

def run_deep_learning():
    """Анализирует собранные данные и выделяет правила."""
    log("Запуск глубокого обучения...")
    evidence = collect_raw_evidence()
    
    if not evidence or len(evidence) < 100:
        log("Недостаточно данных для обучения.")
        return

    prompt = f"""
Ты — Анжелочка, самообучающийся AI-аналитик.
Проанализируй эти РЕАЛЬНЫЕ диалоги менеджеров и клиентов.
Выдели знания в ДВЕ категории:
1. [RULE] — Постоянные правила бизнеса (логистика, скрипты, нормы).
2. [STATUS] — Временная оперативная информация (конкретные даты машин, текущие акции, дедлайны).

ФОРМАТ ОТВЕТА (строго JSON-список строк с префиксами):
["[RULE] Правило...", "[STATUS] Текущая дата..."]

ДАННЫЕ ДЛЯ АНАЛИЗА:
{evidence}
"""
    
    log("Отправка на анализ в Gemini...")
    result_raw = api_call_gemini(prompt)
    if not result_raw:
        return

    # Очистка JSON
    try:
        clean_json = result_raw.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
            
        new_rules = json.loads(clean_json)
        
        # Сохраняем ежедневный результат
        today_str = datetime.now().strftime("%Y-%m-%d")
        learning_db = {}
        if os.path.exists(LEARNING_PATH):
            with open(LEARNING_PATH, 'r', encoding='utf-8') as f:
                learning_db = json.load(f)
        
        learning_db[today_str] = new_rules
        with open(LEARNING_PATH, 'w', encoding='utf-8') as f:
            json.dump(learning_db, f, ensure_ascii=False, indent=2)

        # Обновляем ГЛОБАЛЬНУЮ базу экспертных знаний (Expert Wisdom)
        with open(EXPERT_WISDOM_PATH, 'a', encoding='utf-8') as f:
            f.write(f"\n\n### 🎓 Добавлено авто-обучением {today_str}:\n")
            for rule in new_rules:
                f.write(f"- {rule}\n")
        
        log(f"Успешно выучено {len(new_rules)} новых правил!")
        return new_rules

    except Exception as e:
        log(f"Ошибка парсинга правил: {e}. Сырой вывод: {result_raw[:200]}")
        return None

if __name__ == "__main__":
    run_deep_learning()
