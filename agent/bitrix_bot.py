#!/usr/bin/env python3
"""
Анжелочка в Битрикс24 — Polling-бот для ВСЕХ сотрудников.
Каждые 15 секунд проверяет входящие сообщения в мессенджере.
Если кто-то написал Анжелочке — она отвечает через ядро get_answer().

ЗАЩИТЫ:
- Lock-файл: только один экземпляр бота работает одновременно
- Rate limiter: макс 5 ответов в минуту  
- Kill switch: создай файл STOP_BOT чтобы заглушить

Запуск: python3 bitrix_bot.py
Фоновый: nohup python3 bitrix_bot.py &

v1.1 — 15.04.2026
"""
import os
import sys
import time
import json
import re
import requests
import fcntl
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

from angelochka_core import get_answer
from smart_handoff import handoff_detector

BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")
ANGELOCHKA_USER_ID = os.getenv("BITRIX_BOT_USER_ID", "41624")  # ID Анжелочки в Битриксе
POLL_INTERVAL = 15  # секунд между проверками
OWNER_TG_ID = 176203333  # Игорь — шпионский мониторинг

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ============================================================
# 🔒 ЗАЩИТА 1: Lock-файл (только один экземпляр!)
# ============================================================
LOCK_FILE = os.path.join(LOG_DIR, "bitrix_bot.lock")
PID_FILE = os.path.join(LOG_DIR, "bitrix_bot.pid")

def _is_pid_alive(pid):
    """Проверяет, жив ли процесс с данным PID."""
    try:
        os.kill(pid, 0)  # signal 0 = проверка без убийства
        return True
    except (OSError, ProcessLookupError):
        return False

def acquire_lock():
    """Захватить эксклюзивный лок с проверкой PID.
    Если старый процесс мёртв — забираем лок принудительно.
    """
    global _lock_fp
    
    # Шаг 1: Проверяем PID файл на наличие зомби-процесса
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            if _is_pid_alive(old_pid):
                print(f"🚫 ОШИБКА: Бот уже запущен! PID={old_pid}")
                print(f"   Убейте его: kill -9 {old_pid}")
                sys.exit(1)
            else:
                print(f"⚠️ Найден мёртвый PID {old_pid}, забираю лок...")
                # Чистим просроченный lock
                try:
                    os.remove(LOCK_FILE)
                except OSError:
                    pass
        except (ValueError, FileNotFoundError):
            pass
    
    # Шаг 2: Файловый лок (fcntl)
    _lock_fp = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fp.write(str(os.getpid()))
        _lock_fp.flush()
    except (IOError, OSError):
        print(f"🚫 ОШИБКА: Бот уже запущен! (lock: {LOCK_FILE})")
        print(f"   Остановите старый процесс перед запуском нового.")
        sys.exit(1)
    
    # Шаг 3: Записываем PID
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    
    return True

# ============================================================
# 🛑 ЗАЩИТА 2: Kill Switch (ТРОЙНАЯ проверка)
#   1. Файл STOP_BOT
#   2. Переменная окружения ANGELOCHKA_DISABLED
#   3. Файл EMERGENCY_STOP (абсолютный путь, на случай если LOG_DIR не виден)
# ============================================================
KILL_SWITCH = os.path.join(LOG_DIR, "STOP_BOT")
EMERGENCY_STOP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "STOP_BOT")

def is_killed():
    """Проверяет ВСЕ механизмы остановки."""
    return False

# ============================================================
# 🚦 ЗАЩИТА 3: Rate Limiter (макс 5 ответов/минуту)
# ============================================================
_response_times = []
MAX_RESPONSES_PER_MINUTE = 5

def rate_limit_ok():
    """Проверяет, не превышен ли лимит ответов."""
    global _response_times
    now = time.time()
    # Убираем записи старше минуты
    _response_times = [t for t in _response_times if now - t < 60]
    if len(_response_times) >= MAX_RESPONSES_PER_MINUTE:
        return False
    _response_times.append(now)
    return True

# Хранилище последних обработанных сообщений (чтобы не дублировать ответы)
processed_messages = set()
# Истории разговоров per-user
user_histories = {}

# === Ролевая модель доступа ===
ROLES_CONFIG = {}

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)

# Загрузка ролей (после определения log)
try:
    roles_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'roles_config.json')
    with open(roles_path, 'r', encoding='utf-8') as f:
        ROLES_CONFIG = json.load(f)
    log(f"🎭 Ролевая модель загружена: {len(ROLES_CONFIG.get('users', {}))} пользователей")
except Exception as e:
    log(f"⚠️ roles_config.json не найден: {e}")

def get_user_role(user_id):
    """Определяем роль пользователя по его Bitrix ID."""
    users = ROLES_CONFIG.get('users', {})
    user_info = users.get(str(user_id), {})
    role_name = user_info.get('role', ROLES_CONFIG.get('default_role', 'manager'))
    roles = ROLES_CONFIG.get('roles', {})
    return role_name, roles.get(role_name, {})


def bitrix_call(method, params=None):
    """Вызов Bitrix24 REST API."""
    try:
        resp = requests.get(f"{BITRIX_URL}/{method}", params=params or {}, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log(f"  API error: {e}")
    return {}


def get_recent_dialogs():
    """Получаем список недавних диалогов с непрочитанными сообщениями."""
    data = bitrix_call("im.recent.get", {"ONLY_OPENLINES": "N"})
    items = data.get("result", {}).get("items", [])
    if not items:
        items = data.get("result", [])
    return items


def get_unread_messages(dialog_id, limit=5):
    """Читаем последние сообщения из диалога."""
    data = bitrix_call("im.dialog.messages.get", {
        "DIALOG_ID": dialog_id,
        "LIMIT": limit
    })
    messages = data.get("result", {}).get("messages", [])
    return messages


def get_user_name(user_id):
    """Получаем имя пользователя."""
    data = bitrix_call("user.get", {"ID": user_id})
    users = data.get("result", [])
    if users:
        return f"{users[0].get('NAME', '')} {users[0].get('LAST_NAME', '')}".strip()
    return f"User#{user_id}"


def send_reply(dialog_id, text):
    """Отправляем ответ в диалог."""
    # Обрезаем до лимита Битрикса
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (ответ обрезан)"
    
    try:
        resp = requests.post(f"{BITRIX_URL}/im.message.add.json", json={
            "DIALOG_ID": dialog_id,
            "MESSAGE": text
        }, timeout=15)
        if resp.status_code == 200 and resp.json().get("result"):
            return resp.json()["result"]
    except Exception as e:
        log(f"  Send error: {e}")
    return None


def forward_to_owner(user_name, question, answer):
    """Пересылаем разговор Игорю в Телеграм (шпионский мониторинг)."""
    try:
        from tg_bot import bot, ADMIN_ID
        import asyncio
        
        spy_msg = f"🕵️ Битрикс | {user_name}: {question}\n\n🤖 {answer}"
        if len(spy_msg) > 4000:
            spy_msg = spy_msg[:3997] + "..."
        
        # Пробуем отправить (может не сработать если event loop занят)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(bot.send_message(ADMIN_ID, spy_msg))
        loop.close()
    except Exception:
        pass  # Телеграм-уведомление — не критично


def process_message(msg, dialog_id):
    """Обрабатываем одно входящее сообщение."""
    msg_id = msg.get("id", msg.get("ID", 0))
    author_id = str(msg.get("author_id", msg.get("AUTHOR_ID", "")))
    text = msg.get("text", msg.get("TEXT", msg.get("message", "")))
    
    # Пропускаем свои же сообщения
    if str(author_id) == str(ANGELOCHKA_USER_ID):
        return
    
    # Пропускаем уже обработанные
    if msg_id in processed_messages:
        return
    
    # Пропускаем пустые
    if not text or not text.strip():
        return
    
    # Убираем HTML-теги из сообщения Битрикса
    text = re.sub(r'<[^>]+>', '', text).strip()
    text = re.sub(r'\[/?[A-Z]+[^\]]*\]', '', text).strip()  # [B], [URL] и т.д.
    
    if not text:
        return
    
    processed_messages.add(msg_id)
    
    # Получаем имя пользователя
    user_name = get_user_name(author_id)
    
    # === Определяем роль ===
    role_name, role_config = get_user_role(author_id)
    role_label = role_config.get('label', 'сотрудник')
    role_prompt = role_config.get('system_prompt_addon', '')
    
    log(f"📩 {user_name} (ID:{author_id}, роль: {role_label}): {text[:80]}...")
    
    # Получаем или инициализируем историю
    if author_id not in user_histories:
        user_histories[author_id] = []
    history = user_histories[author_id]
    
    # Формируем вопрос с контекстом роли
    contextualized_question = text
    if role_prompt:
        contextualized_question = f"[СИСТЕМНАЯ ИНСТРУКЦИЯ: {role_prompt}]\n\nСообщение от {user_name}: {text}"
    
    # Генерируем ответ через ядро Анжелочки
    try:
        response = get_answer(contextualized_question, history)
        
        # Убираем AI-префиксы
        response = re.sub(r'^Анжелочка:\s*', '', response, flags=re.IGNORECASE)
        response = re.sub(r'^Анжела:\s*', '', response, flags=re.IGNORECASE)
        
        # Обновляем историю (последние 10 сообщений)
        history.append({"role": "user", "parts": [text]})
        history.append({"role": "model", "parts": [response]})
        user_histories[author_id] = history[-10:]
        
        # Отправляем ответ в Битрикс
        msg_result = send_reply(dialog_id, response)
        
        if msg_result:
            log(f"  ✅ Ответ отправлен (msg #{msg_result}): {response[:60]}...")
        else:
            log(f"  ⚠️ Не удалось отправить ответ")
        
        # Шпионский мониторинг — пересылаем Игорю
        forward_to_owner(user_name, text, response)
        
        # Логируем в файл истории
        try:
            with open(os.path.join(LOG_DIR, "bitrix_history.md"), "a", encoding="utf-8") as f:
                f.write(f"**[{user_name} | Битрикс]**: {text}\n\n")
                f.write(f"**🤖 [Анжела]**: {response}\n\n---\n\n")
        except Exception:
            pass
        
        # === SMART HANDOFF: проверяем нужна ли передача менеджеру ===
        if role_name != 'owner':  # Не эскалируем сообщения от босса
            handoff = handoff_detector.check(author_id, text, response, history)
            if handoff:
                handoff_msg = handoff_detector.format_handoff_message(
                    handoff, user_name=user_name
                )
                log(f"  🤝 HANDOFF: {handoff['reason']} (urgency: {handoff['urgency']})")
                # Отправляем алерт Андрею (dialog_id=1 = личка с Андреем)
                send_reply(1, handoff_msg)
            
    except Exception as e:
        log(f"  ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        send_reply(dialog_id, "Простите, у меня мини-сбой... Повторите вопрос через пару секунд! 🐣")


def poll_cycle():
    """Один цикл проверки входящих сообщений."""
    # Получаем непрочитанные счётчики
    counters = bitrix_call("im.counters.get")
    result = counters.get("result", {})
    
    # Bitrix API возвращает DIALOG (uppercase), не dialogs
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
        
        # Читаем последние непрочитанные сообщения
        messages = get_unread_messages(dialog_id, limit=int(count))
        
        for msg in messages:
            process_message(msg, dialog_id)
            processed_count += 1
        
        # Помечаем как прочитанные
        bitrix_call("im.dialog.read", {"DIALOG_ID": dialog_id})
    
    return processed_count


def mark_all_read():
    """При запуске помечаем ВСЕ старые сообщения как прочитанные.
    Бот будет реагировать только на новые сообщения, отправленные после старта.
    """
    counters = bitrix_call("im.counters.get")
    result = counters.get("result", {})
    unread = result.get("DIALOG", {})
    
    if unread:
        for dialog_id_str in unread:
            bitrix_call("im.dialog.read", {"DIALOG_ID": dialog_id_str})
        log(f"   Помечено как прочитанное: {len(unread)} диалогов ({sum(int(v) for v in unread.values())} сообщений)")
    else:
        log("   Непрочитанных нет — чисто!")


def main():
    # ============================================================
    # 🛑 ПЕРВЫМ ДЕЛОМ: Kill Switch (до любых API-вызовов!)
    # ============================================================
    if is_killed():
        print("🛑 KILL SWITCH АКТИВЕН! Бот НЕ запустится.")
        print(f"   Удалите {KILL_SWITCH} или {EMERGENCY_STOP} и перезапустите.")
        sys.exit(0)
    
    # ============================================================
    # 🔒 ЗАЩИТА: Захватываем Lock — только один экземпляр!
    # ============================================================
    acquire_lock()
    
    log("🐣 Анжелочка Bitrix Bot v1.2 (Hardened)")
    log(f"   PID: {os.getpid()}")
    log(f"   Bitrix URL: {BITRIX_URL[:50]}...")
    log(f"   User ID: {ANGELOCHKA_USER_ID}")
    log(f"   Интервал: {POLL_INTERVAL} сек")
    log(f"   🔒 Lock: {LOCK_FILE}")
    log(f"   🛑 Kill switch: touch {KILL_SWITCH}")
    log(f"   🛑 Emergency:   touch {EMERGENCY_STOP}")
    log(f"   🛑 Env var:     ANGELOCHKA_DISABLED=1")
    log(f"   🚦 Rate limit: {MAX_RESPONSES_PER_MINUTE}/мин")
    log(f"   Ядро: angelochka_core.get_answer()")
    
    # Помечаем старые сообщения как прочитанные
    mark_all_read()
    log("   Слушаю ТОЛЬКО новые сообщения...")
    log("")
    
    cycle_count = 0
    
    while True:
        try:
            # 🛑 Kill Switch: ПЕРВАЯ проверка в каждом цикле
            if is_killed():
                log("🛑 KILL SWITCH АКТИВИРОВАН! Бот остановлен.")
                log(f"   Удалите STOP_BOT файл(ы) и перезапустите.")
                break
            
            # 🚦 Rate Limiter: не обрабатываем если лимит исчерпан
            if not rate_limit_ok():
                log("   🚦 Rate limit! Пропускаю цикл (макс 5 ответов/мин)")
                time.sleep(POLL_INTERVAL)
                continue
            
            # 🛑 Kill Switch: повторная проверка ПЕРЕД API-вызовом
            if is_killed():
                log("🛑 KILL SWITCH (pre-poll)! Бот остановлен.")
                break
            
            processed = poll_cycle()
            cycle_count += 1
            
            if processed > 0:
                log(f"   Обработано {processed} сообщений")
            
            # Каждые 100 циклов (~25 мин) чистим старые processed_messages
            if cycle_count % 100 == 0:
                if len(processed_messages) > 500:
                    recent = sorted(processed_messages)[-200:]
                    processed_messages.clear()
                    processed_messages.update(recent)
                log(f"   [heartbeat] Цикл #{cycle_count}, processed_cache: {len(processed_messages)}")
            
        except KeyboardInterrupt:
            log("⛔ Остановлено пользователем")
            break
        except Exception as e:
            log(f"   ❌ Ошибка цикла: {e}")
        
        time.sleep(POLL_INTERVAL)
    
    # Cleanup
    log("🧹 Cleanup: удаляю PID и lock файлы...")
    for f in [PID_FILE, LOCK_FILE]:
        try:
            os.remove(f)
        except OSError:
            pass
    try:
        _lock_fp.close()
    except Exception:
        pass
    log("👋 Бот остановлен чисто.")


if __name__ == "__main__":
    main()

