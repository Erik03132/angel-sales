#!/usr/bin/env python3
"""
🐣 Анжелочка — Режим «Приёмная» (Receive-Only + Avito Activation)

Пассивный бот: слушает сообщения в Битрикс24 мессенджере.
Когда Андрей пришлёт API-ключ Авито → авто-активация аудита.

СЦЕНАРИЙ:
1. Анжелочка сидит на линии, отвечает на вопросы через ядро
2. Если приходит сообщение с паттерном «ключ авито: ...» или «avito api»
3. Анжелочка:
   a) Сохраняет ключ в .env
   b) Запускает avitolog.py (полный аудит)
   c) Отчёт отправляет обратно в Битрикс

Запуск: python3 bitrix_receiver.py
Фоновый: nohup python3 bitrix_receiver.py > logs/receiver.log 2>&1 &

v1.0 — 16.04.2026
"""
import os
import sys
import re
import json
import time
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# Импортируем существующие модули
from bitrix_bot import (
    bitrix_call, get_recent_dialogs, get_unread_messages,
    get_user_name, send_reply, mark_all_read, forward_to_owner,
    acquire_lock, is_killed, rate_limit_ok,
    BITRIX_URL, ANGELOCHKA_USER_ID, LOG_DIR,
    processed_messages, user_histories
)
from angelochka_core import get_answer

POLL_INTERVAL = 15
ENV_PATH = os.path.join(BASE_DIR, '.env')

# Паттерны для распознавания API-ключей Авито
AVITO_KEY_PATTERNS = [
    # "client_id: xxx, client_secret: yyy"
    r'client[_\s]?id\s*[:=]\s*([A-Za-z0-9_-]+).*?client[_\s]?secret\s*[:=]\s*([A-Za-z0-9_-]+)',
    # "авито ключ: xxx / yyy" или "avito api: xxx yyy"
    r'(?:авито|avito)\s+(?:ключ|api|key|токен|token)\s*[:=]?\s*([A-Za-z0-9_-]{10,})\s+([A-Za-z0-9_-]{10,})',
    # "id=xxx secret=yyy"
    r'id\s*[:=]\s*([A-Za-z0-9_-]{10,})[\s,;/]+secret\s*[:=]\s*([A-Za-z0-9_-]{10,})',
]

# Паттерны для определения что сообщение содержит авито-ключ (более мягкие)
AVITO_MENTION_PATTERNS = [
    r'(?:авито|avito)\s*(?:ключ|api|key|токен|token|доступ|access)',
    r'client[_\s]?id.*client[_\s]?secret',
    r'(?:вот|держи|лови|передаю)\s+(?:ключ|доступ)',
]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def extract_avito_keys(text):
    """Пытаемся извлечь API-ключи Авито из текста сообщения.
    
    Returns: (client_id, client_secret) или None
    """
    for pattern in AVITO_KEY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1), match.group(2)
    return None


def is_avito_key_message(text):
    """Проверяем, упоминается ли Авито/ключ в сообщении."""
    for pattern in AVITO_MENTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def save_avito_keys(client_id, client_secret):
    """Сохраняет API-ключи Авито в .env файл."""
    log(f"  💾 Сохраняю API-ключи Авито в .env...")
    
    # Читаем текущий .env
    with open(ENV_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Обновляем или добавляем ключи
    if 'AVITO_CLIENT_ID=' in content:
        content = re.sub(
            r'AVITO_CLIENT_ID=.*', 
            f'AVITO_CLIENT_ID={client_id}', 
            content
        )
    else:
        content += f'\nAVITO_CLIENT_ID={client_id}'
    
    if 'AVITO_CLIENT_SECRET=' in content:
        content = re.sub(
            r'AVITO_CLIENT_SECRET=.*', 
            f'AVITO_CLIENT_SECRET={client_secret}', 
            content
        )
    else:
        content += f'\nAVITO_CLIENT_SECRET={client_secret}'
    
    with open(ENV_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Перезагружаем .env
    load_dotenv(ENV_PATH, override=True)
    log(f"  ✅ Ключи Авито обновлены: ID={client_id[:8]}..., Secret={client_secret[:8]}...")
    return True


def run_avito_audit():
    """Запускает полный аудит Авито через avitolog.py."""
    log("🎯 ЗАПУСК АУДИТА АВИТО...")
    
    try:
        from avitolog import Avitolog
        agent = Avitolog()
        report = agent.run_full_audit()
        
        if report:
            log(f"✅ Аудит завершён! {len(agent.audit_results)} объявлений проанализировано")
            return report
        else:
            return "❌ Не удалось провести аудит. Возможно, ключи неверные. Попросите Андрея проверить."
    except Exception as e:
        log(f"❌ Ошибка аудита: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Ошибка при аудите Авито: {e}"


def process_message_with_avito_detection(msg, dialog_id):
    """Обрабатываем сообщение с детекцией API-ключей Авито."""
    msg_id = msg.get("id", msg.get("ID", 0))
    author_id = str(msg.get("author_id", msg.get("AUTHOR_ID", "")))
    text = msg.get("text", msg.get("TEXT", msg.get("message", "")))
    
    # Пропускаем свои сообщения
    if str(author_id) == str(ANGELOCHKA_USER_ID):
        return
    
    # Пропускаем обработанные
    if msg_id in processed_messages:
        return
    
    # Очищаем HTML/BB-теги
    text = re.sub(r'<[^>]+>', '', text).strip()
    text = re.sub(r'\[/?[A-Z]+[^\]]*\]', '', text).strip()
    
    if not text:
        return
    
    processed_messages.add(msg_id)
    
    user_name = get_user_name(author_id)
    log(f"📩 {user_name} (ID:{author_id}): {text[:100]}...")
    
    # === ДЕТЕКЦИЯ API-КЛЮЧЕЙ АВИТО ===
    keys = extract_avito_keys(text)
    
    if keys:
        client_id, client_secret = keys
        log(f"🔑 ОБНАРУЖЕНЫ API-КЛЮЧИ АВИТО!")
        
        # Сохраняем ключи
        save_avito_keys(client_id, client_secret)
        
        # Подтверждаем получение
        send_reply(dialog_id, 
            f"🔑 Получила API-ключи Авито! Спасибо, {user_name}!\n\n"
            f"Сейчас запущу полный аудит объявлений... ⏳\n"
            f"Это займёт 1-2 минуты."
        )
        
        # Запускаем аудит
        report = run_avito_audit()
        
        if report and not report.startswith("❌"):
            # Отправляем краткую сводку (полный отчёт — в файле)
            # Битрикс ограничивает длину сообщения
            summary = report[:3500] if len(report) > 3500 else report
            send_reply(dialog_id,
                f"✅ Аудит Авито завершён!\n\n{summary}\n\n"
                f"📄 Полный отчёт: data/avito/AVITO_AUDIT_REPORT.md"
            )
        else:
            send_reply(dialog_id, report or "❌ Что-то пошло не так при аудите.")
        
        # Шпионский мониторинг
        forward_to_owner(user_name, "[AVITO API KEY RECEIVED]", "Ключи сохранены, аудит запущен")
        return
    
    # Если упоминается Авито, но ключи не распознаны
    if is_avito_key_message(text):
        send_reply(dialog_id,
            f"👀 {user_name}, вижу что вы передаёте данные для Авито!\n\n"
            f"Пожалуйста, отправьте в формате:\n"
            f"client_id: ВАШ_ID\n"
            f"client_secret: ВАШ_СЕКРЕТ\n\n"
            f"Или просто двумя строками — ID и секрет, я разберусь 😊"
        )
        return
    
    # === ОБЫЧНАЯ ОБРАБОТКА ЧЕРЕЗ ЯДРО АНЖЕЛОЧКИ ===
    if author_id not in user_histories:
        user_histories[author_id] = []
    history = user_histories[author_id]
    
    try:
        response = get_answer(text, history)
        response = re.sub(r'^Анжелочка:\s*', '', response, flags=re.IGNORECASE)
        response = re.sub(r'^Анжела:\s*', '', response, flags=re.IGNORECASE)
        
        history.append({"role": "user", "parts": [text]})
        history.append({"role": "model", "parts": [response]})
        user_histories[author_id] = history[-10:]
        
        msg_result = send_reply(dialog_id, response)
        
        if msg_result:
            log(f"  ✅ Ответ: {response[:60]}...")
        else:
            log(f"  ⚠️ Не удалось отправить ответ")
        
        forward_to_owner(user_name, text, response)
        
        # Логирование
        try:
            with open(os.path.join(LOG_DIR, "receiver_history.md"), "a", encoding="utf-8") as f:
                f.write(f"**[{user_name}]**: {text}\n\n")
                f.write(f"**🤖 [Анжела]**: {response}\n\n---\n\n")
        except Exception:
            pass
        
    except Exception as e:
        log(f"  ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        send_reply(dialog_id, "Простите, мини-сбой... Повторите через пару секунд! 🐣")


def poll_cycle():
    """Один цикл проверки входящих."""
    counters = bitrix_call("im.counters.get")
    result = counters.get("result", {})
    unread = result.get("DIALOG", result.get("dialogs", {}))
    
    if not unread:
        return 0
    
    processed_count = 0
    
    for dialog_id_str, count in unread.items():
        if int(count) == 0:
            continue
        
        try:
            dialog_id = int(dialog_id_str)
        except ValueError:
            dialog_id = dialog_id_str
        
        messages = get_unread_messages(dialog_id, limit=int(count))
        
        for msg in messages:
            process_message_with_avito_detection(msg, dialog_id)
            processed_count += 1
        
        bitrix_call("im.dialog.read", {"DIALOG_ID": dialog_id})
    
    return processed_count


def main():
    # Kill Switch
    if is_killed():
        print("🛑 KILL SWITCH АКТИВЕН! Бот НЕ запустится.")
        sys.exit(0)
    
    # Lock (используем отдельный lock чтобы не конфликтовать с bitrix_bot)
    # acquire_lock()  # Пока не используем — может конфликтовать
    
    log("🐣 Анжелочка — Режим «Приёмная» v1.0")
    log(f"   PID: {os.getpid()}")
    log(f"   Bitrix URL: {BITRIX_URL[:50]}...")
    log(f"   Интервал: {POLL_INTERVAL} сек")
    log(f"   🔑 Авито-детекция: АКТИВНА")
    log(f"   📝 Текущий AVITO_CLIENT_ID: {os.getenv('AVITO_CLIENT_ID', 'НЕ ЗАДАН')[:10]}...")
    log("")
    log("   Жду сообщения... Когда Андрей пришлёт ключ Авито — запущу аудит.")
    log("")
    
    # Помечаем старые как прочитанные
    mark_all_read()
    log("   Слушаю ТОЛЬКО новые сообщения...")
    log("")
    
    cycle_count = 0
    
    while True:
        try:
            if is_killed():
                log("🛑 KILL SWITCH! Остановка.")
                break
            
            if not rate_limit_ok():
                log("   🚦 Rate limit! Пропускаю цикл")
                time.sleep(POLL_INTERVAL)
                continue
            
            processed = poll_cycle()
            cycle_count += 1
            
            if processed > 0:
                log(f"   Обработано {processed} сообщений")
            
            # Heartbeat каждые ~25 мин
            if cycle_count % 100 == 0:
                if len(processed_messages) > 500:
                    recent = sorted(processed_messages)[-200:]
                    processed_messages.clear()
                    processed_messages.update(recent)
                log(f"   [heartbeat] Цикл #{cycle_count}")
            
        except KeyboardInterrupt:
            log("⛔ Остановлено пользователем")
            break
        except Exception as e:
            log(f"   ❌ Ошибка цикла: {e}")
        
        time.sleep(POLL_INTERVAL)
    
    log("👋 Приёмная закрыта.")


if __name__ == "__main__":
    main()
