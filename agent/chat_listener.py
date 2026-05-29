#!/usr/bin/env python3
"""
🎧 Заботкина — Слушатель общих чатов Битрикс24.
═══════════════════════════════════════════════════════
ЗАДАЧИ:
  1. Слушать ВСЕ групповые чаты (Общий чат, Продажи АИ, Новости компании)
  2. Извлекать знания из диалогов сотрудников → expert_knowledge.md
  3. Если в диалоге что-то непонятно → задаёт уточняющий вопрос в тот же чат

РЕЖИМ: Пассивный наблюдатель + активный ученик.
  - НЕ отвечает на каждое сообщение (не спам!)
  - Задаёт вопросы ТОЛЬКО когда действительно не понимает контекст
  - Учится: новые факты о породах, ценах, клиентах, логистике

Запуск: python3 chat_listener.py
PM2:    pm2 start chat_listener.py --name angela-listener --interpreter .../python3

v1.0 — 05.05.2026
"""
import json
import os
import re
import sys
import time
from datetime import datetime

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(AGENT_DIR)
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR = os.path.join(AGENT_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

sys.path.insert(0, AGENT_DIR)

from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

import requests

# === КОНФИГУРАЦИЯ ===
BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")
ANGELOCHKA_USER_ID = os.getenv("BITRIX_BOT_USER_ID", "41624")
POLL_INTERVAL = 30  # секунд между проверками

# Групповые чаты для прослушивания
# Формат: chat_id (без префикса "chat") → название (для логов)
GROUP_CHATS = {
    "1": "Общий чат",
    "57236": "Продажи АИ",
    "43978": "Новости компании",
}

# Файлы обучения
KNOWLEDGE_PATH = os.path.join(DATA_DIR, 'expert_knowledge.md')
CHAT_LEARNINGS_PATH = os.path.join(DATA_DIR, 'chat_learnings.json')
PROCESSED_MSGS_PATH = os.path.join(LOG_DIR, 'listener_processed.json')

# Лимиты
MAX_QUESTIONS_PER_HOUR = 3  # Макс уточняющих вопросов в час (чтобы не спамить)
MIN_MSG_LENGTH = 15  # Минимальная длина сообщения для анализа
BATCH_SIZE = 5  # Сколько сообщений анализировать за раз

# === СОСТОЯНИЕ ===
_processed_ids = set()
_question_timestamps = []


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def load_processed():
    """Загружает ID уже обработанных сообщений."""
    global _processed_ids
    if os.path.exists(PROCESSED_MSGS_PATH):
        try:
            with open(PROCESSED_MSGS_PATH, 'r') as f:
                data = json.load(f)
                _processed_ids = set(data.get("ids", []))
        except Exception:
            _processed_ids = set()


def save_processed():
    """Сохраняет ID обработанных сообщений (последние 2000)."""
    ids_list = sorted(_processed_ids)[-2000:]
    with open(PROCESSED_MSGS_PATH, 'w') as f:
        json.dump({"ids": ids_list, "updated": datetime.now().isoformat()}, f)


def bitrix_call(method, params=None):
    """Вызов Bitrix24 REST API."""
    try:
        resp = requests.get(f"{BITRIX_URL}/{method}", params=params or {}, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log(f"  API error: {e}")
    return {}


def send_to_chat(chat_id, text):
    """Отправить сообщение в групповой чат."""
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (обрезано)"
    try:
        resp = requests.post(f"{BITRIX_URL}/im.message.add.json", json={
            "DIALOG_ID": f"chat{chat_id}",
            "MESSAGE": text
        }, timeout=15)
        if resp.status_code == 200 and resp.json().get("result"):
            return True
    except Exception as e:
        log(f"  Send error: {e}")
    return False


def get_chat_messages(chat_id, limit=10):
    """Получить последние сообщения из группового чата."""
    data = bitrix_call("im.dialog.messages.get", {
        "DIALOG_ID": f"chat{chat_id}",
        "LIMIT": limit
    })
    messages = data.get("result", {}).get("messages", [])
    return messages


def get_user_name(user_id):
    """Получаем имя пользователя (с кэшированием)."""
    if not hasattr(get_user_name, '_cache'):
        get_user_name._cache = {}
    uid = str(user_id)
    if uid in get_user_name._cache:
        return get_user_name._cache[uid]
    data = bitrix_call("user.get", {"ID": user_id})
    users = data.get("result", [])
    if users:
        name = f"{users[0].get('NAME', '')} {users[0].get('LAST_NAME', '')}".strip()
    else:
        name = f"User#{user_id}"
    get_user_name._cache[uid] = name
    return name


def clean_message_text(text):
    """Очищает текст от HTML и BB-тегов."""
    text = re.sub(r'<[^>]+>', '', text).strip()
    text = re.sub(r'\[/?[A-Z]+[^\]]*\]', '', text).strip()
    return text


def can_ask_question():
    """Проверяет лимит вопросов в час."""
    global _question_timestamps
    now = time.time()
    _question_timestamps = [t for t in _question_timestamps if now - t < 3600]
    return len(_question_timestamps) < MAX_QUESTIONS_PER_HOUR


def record_question():
    """Записывает факт задания вопроса."""
    _question_timestamps.append(time.time())


# === ЯДРО ОБУЧЕНИЯ ===

def analyze_messages_batch(messages, chat_name):
    """Анализирует пачку сообщений через LLM — извлекает знания и определяет непонятное.
    
    Returns: {
        "learnings": [{"fact": str, "category": str, "source_msg": str}],
        "questions": [{"question": str, "context": str, "chat_id": str}]
    }
    """
    if not messages:
        return {"learnings": [], "questions": []}
    
    # Формируем контекст из сообщений
    context_lines = []
    for msg in messages:
        author_id = str(msg.get("author_id", msg.get("AUTHOR_ID", "")))
        text = clean_message_text(msg.get("text", msg.get("TEXT", msg.get("message", ""))))
        if not text or len(text) < MIN_MSG_LENGTH:
            continue
        if str(author_id) == str(ANGELOCHKA_USER_ID):
            continue
        name = get_user_name(author_id)
        context_lines.append(f"{name}: {text}")
    
    if not context_lines:
        return {"learnings": [], "questions": []}
    
    conversation = "\n".join(context_lines)
    
    # Загружаем текущие знания для контекста
    current_knowledge = ""
    if os.path.exists(KNOWLEDGE_PATH):
        try:
            with open(KNOWLEDGE_PATH, 'r', encoding='utf-8') as f:
                current_knowledge = f.read()[-2000:]  # Последние 2000 символов
        except Exception:
            pass
    
    prompt = f"""Ты — Анжела Заботкина, AI-помощник компании «Азовский инкубатор» (продажа цыплят, утят, инкубаторов).
Ты слушаешь общий чат сотрудников «{chat_name}».

ТВОИ ТЕКУЩИЕ ЗНАНИЯ (краткая выборка):
{current_knowledge[:1000] if current_knowledge else "Знания пока пусты."}

ДИАЛОГ В ЧАТЕ:
{conversation}

ЗАДАНИЕ:
1. Извлеки НОВЫЕ полезные факты из диалога (цены, породы, логистика, клиенты, проблемы).
   Только то, что РЕАЛЬНО новое и полезное для работы.
2. Определи, есть ли в диалоге что-то, что тебе НЕПОНЯТНО и требует уточнения.
   Это должен быть КОНКРЕТНЫЙ вопрос по делу, а не общие вопросы.
   НЕ спрашивай про очевидные вещи. Спрашивай только если:
   - Упомянута новая порода/товар, которой нет в твоих знаниях
   - Непонятная аббревиатура или термин
   - Противоречие с твоими знаниями (например другая цена)

Ответь СТРОГО в JSON формате:
{{
  "learnings": [
    {{"fact": "описание нового факта", "category": "цены|породы|логистика|клиенты|процессы|другое"}}
  ],
  "questions": [
    {{"question": "конкретный вопрос для уточнения", "reason": "почему это важно"}}
  ]
}}

Если ничего нового и непонятного нет — верни пустые массивы.
ВАЖНО: Вопросы задавай РЕДКО и только по делу! Не будь навязчивой."""

    try:
        from angelochka_core import call_llm
        response = call_llm(prompt)
        
        # Парсим JSON из ответа
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            result = json.loads(json_match.group())
            return result
    except json.JSONDecodeError as e:
        log(f"  ⚠️ JSON parse error: {e}")
    except Exception as e:
        log(f"  ⚠️ LLM analysis error: {e}")
    
    return {"learnings": [], "questions": []}


def save_learnings(learnings):
    """Сохраняет новые знания в expert_knowledge.md и chat_learnings.json."""
    if not learnings:
        return 0
    
    saved = 0
    
    # 1. Добавляем в expert_knowledge.md
    try:
        with open(KNOWLEDGE_PATH, 'a', encoding='utf-8') as f:
            for item in learnings:
                fact = item.get("fact", "").strip()
                category = item.get("category", "другое")
                if fact and len(fact) > 10:
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                    f.write(f"\n- [{category}] {fact} (из чата, {ts})")
                    saved += 1
    except Exception as e:
        log(f"  ⚠️ Ошибка записи в knowledge: {e}")
    
    # 2. Добавляем в structured JSON log
    try:
        existing = []
        if os.path.exists(CHAT_LEARNINGS_PATH):
            with open(CHAT_LEARNINGS_PATH, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        
        for item in learnings:
            existing.append({
                **item,
                "timestamp": datetime.now().isoformat(),
                "source": "chat_listener"
            })
        
        # Храним последние 500 записей
        existing = existing[-500:]
        with open(CHAT_LEARNINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"  ⚠️ Ошибка записи в learnings JSON: {e}")
    
    return saved


def ask_clarification(chat_id, question, reason=""):
    """Задаёт уточняющий вопрос в групповой чат."""
    if not can_ask_question():
        log(f"  ⏳ Лимит вопросов ({MAX_QUESTIONS_PER_HOUR}/час) исчерпан, пропускаю")
        return False
    
    # Формируем вежливый вопрос
    prefix = "🐣 Коллеги, извините за вопрос — учусь!"
    msg = f"{prefix}\n\n❓ {question}"
    if reason:
        msg += f"\n\n💡 ({reason})"
    
    success = send_to_chat(chat_id, msg)
    if success:
        record_question()
        log(f"  ❓ Вопрос задан в чат {chat_id}: {question[:60]}...")
    return success


# === ГЛАВНЫЙ ЦИКЛ ===

def listen_cycle():
    """Один цикл прослушивания всех групповых чатов."""
    total_learned = 0
    total_questions = 0
    
    for chat_id, chat_name in GROUP_CHATS.items():
        try:
            messages = get_chat_messages(chat_id, limit=BATCH_SIZE)
            
            if not messages:
                continue
            
            # Фильтруем уже обработанные
            new_messages = []
            for msg in messages:
                msg_id = msg.get("id", msg.get("ID", 0))
                if msg_id and msg_id not in _processed_ids:
                    new_messages.append(msg)
                    _processed_ids.add(msg_id)
            
            if not new_messages:
                continue
            
            # Фильтруем свои сообщения и слишком короткие
            meaningful = []
            for msg in new_messages:
                author_id = str(msg.get("author_id", msg.get("AUTHOR_ID", "")))
                text = clean_message_text(msg.get("text", msg.get("TEXT", msg.get("message", ""))))
                if str(author_id) != str(ANGELOCHKA_USER_ID) and len(text) >= MIN_MSG_LENGTH:
                    meaningful.append(msg)
            
            if not meaningful:
                continue
            
            log(f"📡 [{chat_name}] {len(meaningful)} новых сообщений")
            
            # Анализируем через LLM
            result = analyze_messages_batch(meaningful, chat_name)
            
            # Сохраняем знания
            learnings = result.get("learnings", [])
            if learnings:
                saved = save_learnings(learnings)
                total_learned += saved
                log(f"  📚 Усвоено {saved} фактов")
            
            # Задаём вопросы (если есть и лимит не исчерпан)
            questions = result.get("questions", [])
            for q in questions:
                question_text = q.get("question", "")
                reason = q.get("reason", "")
                if question_text and can_ask_question():
                    ask_clarification(chat_id, question_text, reason)
                    total_questions += 1
            
        except Exception as e:
            log(f"  ❌ Ошибка в чате {chat_name}: {e}")
    
    # Периодически сохраняем processed IDs
    save_processed()
    
    return total_learned, total_questions


def main():
    if not BITRIX_URL:
        print("❌ PRODUCTION_BITRIX_WEBHOOK_URL не задан!")
        sys.exit(1)
    
    log("═" * 50)
    log("🎧 ЗАБОТКИНА — Слушатель чатов v1.0")
    log(f"   PID: {os.getpid()}")
    log(f"   Bitrix: {BITRIX_URL[:50]}...")
    log(f"   Чаты: {', '.join(f'{name} ({cid})' for cid, name in GROUP_CHATS.items())}")
    log(f"   Интервал: {POLL_INTERVAL} сек")
    log(f"   Макс вопросов/час: {MAX_QUESTIONS_PER_HOUR}")
    log(f"   Знания → {KNOWLEDGE_PATH}")
    log("═" * 50)
    
    load_processed()
    log(f"   Уже обработано: {len(_processed_ids)} сообщений")
    log("   Слушаю...\n")
    
    cycle_count = 0
    total_learned = 0
    total_asked = 0
    last_intel_time = 0  # Время последней разведки (epoch)
    INTEL_INTERVAL = 86400  # 24 часа в секундах
    
    # Первую разведку — сразу при старте
    try:
        from bitrix_intelligence import run_intelligence
        log("🕵️ Запускаю первую разведку Битрикс24...")
        run_intelligence()
        last_intel_time = time.time()
    except Exception as e:
        log(f"   ⚠️ Первая разведка не удалась: {e}")
    
    while True:
        try:
            learned, asked = listen_cycle()
            total_learned += learned
            total_asked += asked
            cycle_count += 1
            
            # Heartbeat каждые ~15 мин
            if cycle_count % 30 == 0:
                log(f"   [heartbeat] Цикл #{cycle_count} | Усвоено: {total_learned} | Вопросов: {total_asked}")
            
            # Разведка Битрикс24 — раз в 24 часа
            if time.time() - last_intel_time >= INTEL_INTERVAL:
                try:
                    from bitrix_intelligence import run_intelligence
                    log("🕵️ Плановая разведка Битрикс24 (24ч)...")
                    run_intelligence()
                    last_intel_time = time.time()
                except Exception as e:
                    log(f"   ⚠️ Разведка не удалась: {e}")
            
        except KeyboardInterrupt:
            log("⛔ Остановлено пользователем")
            break
        except Exception as e:
            log(f"   ❌ Ошибка цикла: {e}")
        
        time.sleep(POLL_INTERVAL)
    
    save_processed()
    log("👋 Слушатель остановлен.")


if __name__ == "__main__":
    main()
